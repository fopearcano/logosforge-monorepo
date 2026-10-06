"""Transactional Narrative Knowledge Graph edge-review commands."""

from __future__ import annotations

import json
import threading

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from logosforge.api import create_api
from logosforge.api.serializers import knowledge_graph_wire_key
from logosforge.db import Database, KnowledgeGraphReviewStateCorrupt
from logosforge.knowledge_graph import provenance as P
from logosforge.knowledge_graph.builder import build_knowledge_graph
from logosforge.knowledge_graph.collector import hide_edge as legacy_hide_edge
from logosforge.models import (
    KnowledgeGraphCommandReceipt,
    KnowledgeGraphEdge,
    KnowledgeGraphNode,
)


def _project(*, path: str | None = None, title: str = "Graph commands"):
    db = Database(path)
    project = db.create_project(title, narrative_engine="novel")
    db.create_scene(project.id, "First")
    db.create_scene(project.id, "Second")
    return TestClient(create_api(db=db)), db, project.id


def _graph(client: TestClient, project_id: int, **params) -> dict:
    response = client.get(
        f"/api/projects/{project_id}/knowledge-graph",
        params=params or None,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _inferred_edge(graph: dict) -> dict:
    return next(
        edge for edge in graph["edges"]
        if edge["is_inferred"] and not edge["is_hidden"]
    )


def _command(
    client: TestClient,
    project_id: int,
    *,
    key: str | None,
    kind: str,
    revision: str,
    edge: dict,
):
    return client.post(
        f"/api/projects/{project_id}/knowledge-graph/commands",
        headers=None if key is None else {"Idempotency-Key": key},
        json={
            "kind": kind,
            "expected_revision": revision,
            "source": edge["source"],
            "target": edge["target"],
            "edge_type": edge["edge_type"],
        },
    )


def test_hide_restore_confirm_and_hidden_read_contract():
    client, db, project_id = _project()
    initial = _graph(client, project_id)
    edge = _inferred_edge(initial)
    assert len(initial["revision"]) == 64
    assert initial["hidden_edges"] == []
    assert initial["hidden_edge_count"] == 0

    hidden_response = _command(
        client,
        project_id,
        key="graph-hide-edge-0001",
        kind="hide_edge",
        revision=initial["revision"],
        edge=edge,
    )
    assert hidden_response.status_code == 200, hidden_response.text
    hidden = hidden_response.json()
    assert hidden["changed"] is True and hidden["replayed"] is False
    assert hidden["applied_revision"] != initial["revision"]
    assert hidden["knowledge_graph"]["revision"] == hidden["applied_revision"]
    assert hidden["knowledge_graph"]["hidden_edge_count"] == 1
    reviewed = hidden["knowledge_graph"]["hidden_edges"][0]
    assert reviewed["is_hidden"] is True
    assert reviewed["is_user_confirmed"] is False
    assert not any(
        item["source"] == edge["source"]
        and item["target"] == edge["target"]
        and item["edge_type"] == edge["edge_type"]
        for item in hidden["knowledge_graph"]["edges"]
    )

    restored_response = _command(
        client,
        project_id,
        key="graph-unhide-edge-01",
        kind="unhide_edge",
        revision=hidden["knowledge_graph"]["revision"],
        edge=reviewed,
    )
    assert restored_response.status_code == 200, restored_response.text
    restored = restored_response.json()
    assert restored["knowledge_graph"]["hidden_edge_count"] == 0
    visible = next(
        item for item in restored["knowledge_graph"]["edges"]
        if item["source"] == edge["source"]
        and item["target"] == edge["target"]
        and item["edge_type"] == edge["edge_type"]
    )
    assert visible["is_inferred"] is True

    confirmed_response = _command(
        client,
        project_id,
        key="graph-confirm-edge-01",
        kind="confirm_edge",
        revision=restored["knowledge_graph"]["revision"],
        edge=visible,
    )
    assert confirmed_response.status_code == 200, confirmed_response.text
    confirmed = next(
        item for item in confirmed_response.json()["knowledge_graph"]["edges"]
        if item["source"] == edge["source"]
        and item["target"] == edge["target"]
        and item["edge_type"] == edge["edge_type"]
    )
    assert confirmed["is_user_confirmed"] is True
    assert confirmed["is_inferred"] is False
    assert confirmed["confidence"] == P.CONF_CONFIRMED
    assert len(db.get_kg_edges(project_id)) == 1


def test_command_requires_capability_and_enforces_action_eligibility():
    client, _db, project_id = _project()
    current = _graph(client, project_id)
    edge = _inferred_edge(current)
    missing = _command(
        client,
        project_id,
        key=None,
        kind="hide_edge",
        revision=current["revision"],
        edge=edge,
    )
    assert missing.status_code == 400

    confirmed = _command(
        client,
        project_id,
        key="graph-confirm-eligibility",
        kind="confirm_edge",
        revision=current["revision"],
        edge=edge,
    ).json()
    canonical = next(
        item for item in confirmed["knowledge_graph"]["edges"]
        if item["source"] == edge["source"]
        and item["target"] == edge["target"]
        and item["edge_type"] == edge["edge_type"]
    )
    rejected = _command(
        client,
        project_id,
        key="graph-hide-confirmed-01",
        kind="hide_edge",
        revision=confirmed["knowledge_graph"]["revision"],
        edge=canonical,
    )
    assert rejected.status_code == 400
    assert "visible inferred edge" in rejected.json()["error"]["message"]


def test_exact_replay_returns_current_map_and_original_applied_revision():
    client, db, project_id = _project()
    initial = _graph(client, project_id)
    edge = _inferred_edge(initial)
    key = "graph-durable-retry-01"
    cursor = client.app.state.broker.latest_id()
    applied_response = _command(
        client,
        project_id,
        key=key,
        kind="hide_edge",
        revision=initial["revision"],
        edge=edge,
    )
    assert applied_response.status_code == 200, applied_response.text
    applied = applied_response.json()

    # Remove both persisted endpoint rows and the inferred basis.  The builder
    # exposes only reference placeholders for the durable hidden decision, and
    # the exact receipt must still recover despite that source-state change.
    scene_ids = [scene.id for scene in db.get_all_scenes(project_id)]
    with Session(db._engine) as session:
        for row in session.exec(select(KnowledgeGraphNode)).all():
            session.delete(row)
        # Remove the inferred basis as well, leaving only the durable receipt
        # and its now-dangling hidden review row.
        from logosforge.models import Scene
        for scene_id in scene_ids:
            stored = session.get(Scene, scene_id)
            if stored is not None:
                session.delete(stored)
        session.commit()
    current = _graph(client, project_id)
    assert current["revision"] != applied["knowledge_graph"]["revision"]
    assert current["hidden_edge_count"] == 1
    assert len(current["hidden_edges"]) == 1

    replay_response = _command(
        client,
        project_id,
        key=key,
        kind="hide_edge",
        revision=initial["revision"],
        edge=edge,
    )
    assert replay_response.status_code == 200, replay_response.text
    replay = replay_response.json()
    assert replay["replayed"] is True and replay["changed"] is False
    assert replay["applied_revision"] == applied["applied_revision"]
    assert replay["knowledge_graph"]["revision"] == current["revision"]
    assert [event["event"] for event in client.app.state.broker.events_since(
        cursor, project_id,
    )] == ["knowledge_graph_changed"]


def test_key_reuse_stale_revision_and_foreign_edge_fail_without_receipts():
    client, db, project_id = _project()
    current = _graph(client, project_id)
    edge = _inferred_edge(current)
    key = "graph-key-conflict-001"
    applied = _command(
        client,
        project_id,
        key=key,
        kind="hide_edge",
        revision=current["revision"],
        edge=edge,
    )
    assert applied.status_code == 200
    mismatch = _command(
        client,
        project_id,
        key=key,
        kind="confirm_edge",
        revision=current["revision"],
        edge=edge,
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "idempotency_key_conflict"

    stale_key = "graph-stale-revision-1"
    stale = _command(
        client,
        project_id,
        key=stale_key,
        kind="confirm_edge",
        revision=current["revision"],
        edge=edge,
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "knowledge_graph_conflict"
    assert db.get_knowledge_graph_command_receipt(project_id, stale_key) is None

    other = db.create_project("Foreign", narrative_engine="novel")
    db.create_scene(other.id, "Foreign first")
    db.create_scene(other.id, "Foreign second")
    foreign_edge = _inferred_edge(_graph(client, other.id))
    foreign_key = "graph-foreign-edge-01"
    foreign = _command(
        client,
        project_id,
        key=foreign_key,
        kind="hide_edge",
        revision=applied.json()["knowledge_graph"]["revision"],
        edge=foreign_edge,
    )
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "not_found"
    assert db.get_knowledge_graph_command_receipt(project_id, foreign_key) is None


def test_receipt_is_capability_scoped_hashed_and_no_store():
    client, db, project_id = _project()
    current = _graph(client, project_id)
    edge = _inferred_edge(current)
    key = "graph-receipt-proof-01"
    applied = _command(
        client,
        project_id,
        key=key,
        kind="hide_edge",
        revision=current["revision"],
        edge=edge,
    ).json()
    response = client.get(
        f"/api/projects/{project_id}/knowledge-graph/command-receipt",
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert {part.strip() for part in response.headers["vary"].split(",")} >= {
        "Authorization", "Idempotency-Key",
    }
    receipt = response.json()
    assert receipt["command_kind"] == "hide_edge"
    assert receipt["applied_revision"] == applied["applied_revision"]
    assert receipt["original_affected_edge"] == {
        key: edge[key] for key in ("source", "target", "edge_type")
    }
    with db._engine.connect() as connection:
        stored = connection.execute(text(
            "SELECT idempotency_key_hash, result_json "
            "FROM knowledgegraphcommandreceipt"
        )).one()
    assert len(stored[0]) == 64
    assert key not in stored[0] and key not in stored[1]

    for bad, expected in ((None, 400), ("unknown-receipt-01", 404)):
        missing = client.get(
            f"/api/projects/{project_id}/knowledge-graph/command-receipt",
            headers=None if bad is None else {"Idempotency-Key": bad},
        )
        assert missing.status_code == expected
        assert missing.headers["cache-control"] == "no-store"


def test_same_capability_is_project_scoped_and_project_delete_removes_receipt():
    client, db, first_id = _project()
    second = db.create_project("Second", narrative_engine="novel")
    db.create_scene(second.id, "One")
    db.create_scene(second.id, "Two")
    key = "graph-project-scope-01"
    first_graph = _graph(client, first_id)
    second_graph = _graph(client, second.id)
    first = _command(
        client,
        first_id,
        key=key,
        kind="hide_edge",
        revision=first_graph["revision"],
        edge=_inferred_edge(first_graph),
    )
    second_result = _command(
        client,
        second.id,
        key=key,
        kind="hide_edge",
        revision=second_graph["revision"],
        edge=_inferred_edge(second_graph),
    )
    assert first.status_code == second_result.status_code == 200
    assert db.get_knowledge_graph_command_receipt(first_id, key) is not None
    assert db.get_knowledge_graph_command_receipt(second.id, key) is not None

    db.delete_project(first_id)
    assert db.get_knowledge_graph_command_receipt(first_id, key) is None
    assert db.get_knowledge_graph_command_receipt(second.id, key) is not None


def test_hidden_review_queue_is_completely_reachable_by_pagination():
    client, db, project_id = _project()
    for index in range(31):
        source = f"custom:test:source-{index:02d}"
        target = f"custom:test:target-{index:02d}"
        for key in (source, target):
            db.upsert_kg_node(
                project_id,
                key,
                node_type="custom",
                source_type="test",
                source_id=key.rsplit(":", 1)[-1],
                label=key,
                summary="",
                metadata_json="{}",
            )
        db.upsert_kg_edge(
            project_id,
            source,
            target,
            "relates_to",
            confidence=P.CONF_POSSIBLE,
            provenance=P.PROV_USER_GRAPH_LINK,
            source_system=P.SS_USER,
            explanation="Hidden test edge.",
            metadata_json="{}",
            is_user_confirmed=False,
            is_hidden=True,
        )

    root = f"/api/projects/{project_id}/knowledge-graph/hidden-edges"
    pages = [
        client.get(root, params={"offset": offset, "limit": 10}).json()
        for offset in (0, 10, 20, 30)
    ]
    assert all(page["hidden_edge_count"] == 31 for page in pages)
    assert [page["returned_edge_count"] for page in pages] == [10, 10, 10, 1]
    identities = {
        (edge["source"], edge["target"], edge["edge_type"])
        for page in pages for edge in page["edges"]
    }
    assert len(identities) == 31
    assert all(edge["is_hidden"] for page in pages for edge in page["edges"])
    assert all(page["revision"] == pages[0]["revision"] for page in pages)
    for page in pages:
        node_keys = {node["key"] for node in page["nodes"]}
        endpoint_keys = {
            key for edge in page["edges"]
            for key in (edge["source"], edge["target"])
        }
        assert node_keys == endpoint_keys
    assert client.get(root, params={"limit": 101}).status_code == 422
    assert client.get(
        "/api/projects/999999/knowledge-graph/hidden-edges"
    ).status_code == 404

    # Even a very small Project Map exposes one endpoint-complete restore item;
    # pagination is the complete mechanism beyond that diagnostic subset.
    tiny = _graph(client, project_id, limit=2)
    assert tiny["hidden_edge_count"] == 31
    assert len(tiny["hidden_edges"]) == 1


def test_receipt_failure_rolls_back_review_mutation(tmp_path):
    _client, db, project_id = _project(path=str(tmp_path / "rollback.db"))
    graph = build_knowledge_graph(db, project_id).graph
    edge = next(item for item in graph.edges if item.is_inferred)
    source_node = graph.get_node(edge.source)
    target_node = graph.get_node(edge.target)
    assert source_node is not None and target_node is not None
    with db._engine.begin() as connection:
        connection.execute(text("""
            CREATE TRIGGER reject_graph_receipt
            BEFORE INSERT ON knowledgegraphcommandreceipt
            BEGIN
                SELECT RAISE(ABORT, 'forced graph receipt rollback');
            END;
        """))
    try:
        with pytest.raises(IntegrityError):
            db.execute_knowledge_graph_command(
                project_id,
                kind="hide_edge",
                expected_revision=graph.revision,
                source=knowledge_graph_wire_key(edge.source),
                target=knowledge_graph_wire_key(edge.target),
                edge_type=edge.edge_type,
                idempotency_key="graph-rollback-key-01",
                edge=edge,
                source_node=source_node,
                target_node=target_node,
            )
    finally:
        with db._engine.begin() as connection:
            connection.execute(text("DROP TRIGGER reject_graph_receipt"))
    assert db.get_kg_edges(project_id) == []
    assert db.get_kg_nodes(project_id) == []
    assert db.get_knowledge_graph_command_receipt(
        project_id, "graph-rollback-key-01",
    ) is None


def test_impossible_no_op_receipt_fails_closed():
    client, db, project_id = _project()
    current = _graph(client, project_id)
    edge = _inferred_edge(current)
    key = "graph-corrupt-noop-001"
    applied = _command(
        client,
        project_id,
        key=key,
        kind="hide_edge",
        revision=current["revision"],
        edge=edge,
    )
    assert applied.status_code == 200
    with Session(db._engine) as session:
        receipt = session.exec(select(KnowledgeGraphCommandReceipt)).one()
        payload = json.loads(receipt.result_json)
        payload["original_changed"] = False
        payload["applied_revision"] = payload["expected_revision"]
        receipt.result_json = json.dumps(payload)
        session.add(receipt)
        session.commit()
    with pytest.raises(RuntimeError, match="invalid result data"):
        db.get_knowledge_graph_command_receipt(project_id, key)


def test_receipt_semantics_must_match_its_canonical_request_digest():
    client, db, project_id = _project()
    current = _graph(client, project_id)
    edge = _inferred_edge(current)
    key = "graph-corrupt-binding-01"
    applied = _command(
        client,
        project_id,
        key=key,
        kind="hide_edge",
        revision=current["revision"],
        edge=edge,
    )
    assert applied.status_code == 200

    with Session(db._engine) as session:
        receipt = session.exec(select(KnowledgeGraphCommandReceipt)).one()
        payload = json.loads(receipt.result_json)
        payload["original_affected_edge"]["edge_type"] = "corrupted_relation"
        receipt.result_json = json.dumps(payload)
        session.add(receipt)
        session.commit()

    with pytest.raises(RuntimeError, match="does not match its request digest"):
        db.get_knowledge_graph_command_receipt(project_id, key)
    with pytest.raises(RuntimeError, match="does not match its request digest"):
        db.replay_knowledge_graph_command(
            project_id,
            kind="hide_edge",
            expected_revision=current["revision"],
            source=edge["source"],
            target=edge["target"],
            edge_type=edge["edge_type"],
            idempotency_key=key,
        )
    fail_closed_client = TestClient(
        client.app,
        raise_server_exceptions=False,
    )
    receipt_response = fail_closed_client.get(
        f"/api/projects/{project_id}/knowledge-graph/command-receipt",
        headers={"Idempotency-Key": key},
    )
    replay_response = _command(
        fail_closed_client,
        project_id,
        key=key,
        kind="hide_edge",
        revision=current["revision"],
        edge=edge,
    )
    assert receipt_response.status_code == 500
    assert replay_response.status_code == 500


def test_graph_read_maps_project_deleted_during_build_to_not_found(monkeypatch):
    client, db, project_id = _project()
    monkeypatch.setattr(
        db,
        "read_knowledge_graph_review_snapshot",
        lambda _project_id: None,
    )

    response = client.get(f"/api/projects/{project_id}/knowledge-graph")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_concurrent_same_key_is_exactly_once_across_database_instances(tmp_path):
    path = str(tmp_path / "concurrent.db")
    _client, seed, project_id = _project(path=path)
    first_db = Database(path)
    second_db = Database(path)
    first_graph = build_knowledge_graph(first_db, project_id).graph
    second_graph = build_knowledge_graph(second_db, project_id).graph
    first_edge = next(item for item in first_graph.edges if item.is_inferred)
    second_edge = next(item for item in second_graph.edges if item.dedupe_key == first_edge.dedupe_key)
    barrier = threading.Barrier(3)
    results = []
    errors = []

    def apply(database: Database, graph, edge) -> None:
        barrier.wait()
        try:
            results.append(database.execute_knowledge_graph_command(
                project_id,
                kind="hide_edge",
                expected_revision=graph.revision,
                source=knowledge_graph_wire_key(edge.source),
                target=knowledge_graph_wire_key(edge.target),
                edge_type=edge.edge_type,
                idempotency_key="graph-concurrent-key-01",
                edge=edge,
                source_node=graph.get_node(edge.source),
                target_node=graph.get_node(edge.target),
            ))
        except Exception as exc:  # pragma: no cover - assertion reports it
            errors.append(exc)

    threads = [
        threading.Thread(target=apply, args=(first_db, first_graph, first_edge)),
        threading.Thread(target=apply, args=(second_db, second_graph, second_edge)),
    ]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=10)
    assert errors == []
    assert sorted((result.changed, result.replayed) for result in results) == [
        (False, True), (True, False),
    ]
    assert len(seed.get_kg_edges(project_id)) == 1
    with seed._engine.connect() as connection:
        assert connection.execute(text(
            "SELECT COUNT(*) FROM knowledgegraphcommandreceipt"
        )).scalar_one() == 1


def test_overlong_wire_identity_and_confirmed_hidden_restore():
    client, db, project_id = _project()
    long_source = "custom:test:" + "x" * 700
    target = "custom:test:target"
    for key, label in ((long_source, "Long"), (target, "Target")):
        db.upsert_kg_node(
            project_id,
            key,
            node_type="custom",
            source_type="test",
            source_id=label,
            label=label,
            summary="",
            metadata_json="{}",
        )
    db.upsert_kg_edge(
        project_id,
        long_source,
        target,
        "relates_to",
        confidence=P.CONF_CONFIRMED,
        provenance=P.PROV_USER_GRAPH_LINK,
        source_system=P.SS_USER,
        explanation="Legacy confirmed hidden review.",
        metadata_json="{}",
        is_user_confirmed=True,
        is_hidden=True,
    )
    current = _graph(client, project_id)
    hidden = next(
        edge for edge in current["hidden_edges"]
        if edge["edge_type"] == "relates_to"
    )
    assert hidden["source"].startswith("kg:sha256:")
    response = _command(
        client,
        project_id,
        key="graph-long-unhide-001",
        kind="unhide_edge",
        revision=current["revision"],
        edge=hidden,
    )
    assert response.status_code == 200, response.text
    restored = next(
        edge for edge in response.json()["knowledge_graph"]["edges"]
        if edge["edge_type"] == "relates_to"
    )
    assert restored["source"] == hidden["source"]
    assert restored["is_user_confirmed"] is True
    assert restored["is_hidden"] is False


def test_legacy_hidden_edge_without_endpoints_restores_after_basis_disappears():
    client, db, project_id = _project()
    graph = build_knowledge_graph(db, project_id).graph
    edge = next(item for item in graph.edges if item.is_inferred)
    legacy_hide_edge(db, project_id, edge)
    assert db.get_kg_nodes(project_id) == []
    for scene in db.get_all_scenes(project_id):
        db.delete_scene(scene.id)

    page_response = client.get(
        f"/api/projects/{project_id}/knowledge-graph/hidden-edges"
    )
    assert page_response.status_code == 200, page_response.text
    page = page_response.json()
    assert page["hidden_edge_count"] == 1
    hidden = page["edges"][0]
    assert {
        hidden["source"], hidden["target"],
    } == {node["key"] for node in page["nodes"]}

    restored = _command(
        client,
        project_id,
        key="graph-legacy-unhide-01",
        kind="unhide_edge",
        revision=page["revision"],
        edge=hidden,
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["knowledge_graph"]["hidden_edge_count"] == 0
    assert db.get_kg_edges(project_id) == []
    assert db.get_kg_nodes(project_id) == []


def test_project_identity_prevents_delayed_command_after_id_reuse():
    client, db, project_id = _project()
    old = _graph(client, project_id)
    old_edge = _inferred_edge(old)
    db.delete_project(project_id)
    replacement = db.create_project("Replacement", narrative_engine="novel")
    assert replacement.id == project_id
    db.create_scene(project_id, "First")
    db.create_scene(project_id, "Second")
    delayed = _command(
        client,
        project_id,
        key="graph-project-aba-001",
        kind="hide_edge",
        revision=old["revision"],
        edge=old_edge,
    )
    assert delayed.status_code == 409
    assert delayed.json()["error"]["code"] == "knowledge_graph_conflict"


def test_unrelated_duplicate_rows_fail_closed_but_exact_receipt_recovers():
    client, db, project_id = _project()
    initial = _graph(client, project_id)
    edge = _inferred_edge(initial)
    committed_key = "graph-dedupe-committed"
    committed = _command(
        client,
        project_id,
        key=committed_key,
        kind="hide_edge",
        revision=initial["revision"],
        edge=edge,
    )
    assert committed.status_code == 200

    duplicate_identity = ("custom:legacy:a", "custom:legacy:b", "relates_to")
    with Session(db._engine) as session:
        for _ in range(2):
            session.add(KnowledgeGraphEdge(
                project_id=project_id,
                source_node_key=duplicate_identity[0],
                target_node_key=duplicate_identity[1],
                edge_type=duplicate_identity[2],
                confidence=P.CONF_POSSIBLE,
                provenance=P.PROV_USER_GRAPH_LINK,
                source_system=P.SS_USER,
                explanation="Contradictory legacy duplicate.",
                is_user_confirmed=False,
                is_hidden=True,
            ))
        session.commit()

    # Receipt comparison is deliberately earlier than global corruption
    # validation, so the already-committed action remains recoverable.
    replay = db.execute_knowledge_graph_command(
        project_id,
        kind="hide_edge",
        expected_revision=initial["revision"],
        source=edge["source"],
        target=edge["target"],
        edge_type=edge["edge_type"],
        idempotency_key=committed_key,
    )
    assert replay.replayed is True and replay.changed is False

    with pytest.raises(KnowledgeGraphReviewStateCorrupt):
        db.read_knowledge_graph_review_snapshot(project_id)
    safe_client = TestClient(client.app, raise_server_exceptions=False)
    primary = safe_client.get(
        f"/api/projects/{project_id}/knowledge-graph"
    )
    assert primary.status_code == 500
    assert primary.json() == {
        "error": {
            "code": "knowledge_graph_review_state_corrupt",
            "message": (
                "Knowledge Graph review state is inconsistent. "
                "Repair it before continuing edge review."
            ),
        }
    }
    hidden_page = safe_client.get(
        f"/api/projects/{project_id}/knowledge-graph/hidden-edges"
    )
    assert hidden_page.status_code == 500
    assert hidden_page.json() == primary.json()
    response = _command(
        safe_client,
        project_id,
        key="graph-dedupe-command-01",
        kind="confirm_edge",
        revision=committed.json()["knowledge_graph"]["revision"],
        edge=edge,
    )
    assert response.status_code == 500
    assert response.json() == primary.json()
    rows = [
        row for row in db.get_kg_edges(project_id)
        if (row.source_node_key, row.target_node_key, row.edge_type)
        == duplicate_identity
    ]
    assert len(rows) == 2
    assert all(row.is_hidden is True for row in rows)
    assert db.get_knowledge_graph_command_receipt(
        project_id, "graph-dedupe-command-01",
    ) is None
