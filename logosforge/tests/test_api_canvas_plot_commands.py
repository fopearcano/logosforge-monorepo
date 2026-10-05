"""Canonical, transactional Canvas Plot API."""

from __future__ import annotations

import json
import threading

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from logosforge.api import create_api
from logosforge.db import (
    CanvasPlotCommandError,
    Database,
)
from logosforge.models import CanvasPlotCommandReceipt, CanvasPlotLink


def _project(*, path: str | None = None):
    db = Database(path)
    project = db.create_project(
        "Canvas commands",
        narrative_engine="novel",
        default_writing_format="novel",
    )
    return TestClient(create_api(db=db)), db, project.id


def _snapshot(client: TestClient, project_id: int) -> dict:
    response = client.get(f"/api/projects/{project_id}/canvas-plot")
    assert response.status_code == 200, response.text
    return response.json()


def _command(
    client: TestClient,
    project_id: int,
    *,
    idempotency_key: str | None = None,
    **body,
):
    return client.post(
        f"/api/projects/{project_id}/canvas-plot/commands",
        json=body,
        headers=(
            {"Idempotency-Key": idempotency_key}
            if idempotency_key is not None else None
        ),
    )


def _create_node(
    client: TestClient, project_id: int, current: dict, title: str, **extra,
) -> dict:
    response = _command(
        client,
        project_id,
        kind="create_node",
        expected_revision=current["revision"],
        title=title,
        **extra,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_create_node_explicit_null_index_appends_like_an_omitted_index():
    client, _db, project_id = _project()
    first = _create_node(
        client, project_id, _snapshot(client, project_id), "First",
    )
    second = _create_node(
        client,
        project_id,
        first["canvas_plot"],
        "Second",
        index=None,
    )

    assert [node["title"] for node in second["canvas_plot"]["nodes"]] == [
        "First", "Second",
    ]
    assert [node["sort_order"] for node in second["canvas_plot"]["nodes"]] == [
        0, 1,
    ]


def test_all_nine_commands_return_canonical_persisted_snapshots(tmp_path):
    path = str(tmp_path / "canvas.db")
    client, db, project_id = _project(path=path)
    scene = db.create_scene(project_id, "Referenced")
    empty = _snapshot(client, project_id)
    assert empty["nodes"] == empty["links"] == empty["frames"] == []
    assert len(empty["revision"]) == 64

    first = _create_node(
        client, project_id, empty, "First", x=10, y=20,
        scene_id=scene.id,
    )
    first_id = first["created_node_id"]
    assert first["affected_node_ids"] == [first_id]
    assert first["canvas_plot"]["nodes"][0] | {"created_at": "ignored"} == {
        "id": first_id,
        "title": "First",
        "body": "",
        "x": 10.0,
        "y": 20.0,
        "width": 180.0,
        "height": 110.0,
        "color_label": "",
        "group_label": "",
        "scene_id": scene.id,
        "sort_order": 0,
        "created_at": "ignored",
    }

    second = _create_node(
        client, project_id, first["canvas_plot"], "Second", index=0,
    )
    second_id = second["created_node_id"]
    assert [row["id"] for row in second["canvas_plot"]["nodes"]] == [
        second_id, first_id,
    ]
    assert [row["sort_order"] for row in second["canvas_plot"]["nodes"]] == [0, 1]

    updated_node = _command(
        client,
        project_id,
        kind="update_node",
        expected_revision=second["canvas_plot"]["revision"],
        node_id=first_id,
        title="First moved",
        body="A complete card",
        x=240,
        y=-35,
        width=320,
        height=190,
        color_label="violet",
        group_label="Act I",
        scene_id=None,
        index=0,
    )
    assert updated_node.status_code == 200, updated_node.text
    node_body = updated_node.json()
    node = node_body["canvas_plot"]["nodes"][0]
    assert node["id"] == first_id and node["scene_id"] is None
    assert (node["x"], node["y"], node["width"], node["height"]) == (
        240.0, -35.0, 320.0, 190.0,
    )
    assert [row["sort_order"] for row in node_body["canvas_plot"]["nodes"]] == [0, 1]

    linked = _command(
        client,
        project_id,
        kind="create_link",
        expected_revision=node_body["canvas_plot"]["revision"],
        source_node_id=first_id,
        target_node_id=second_id,
        label="causes",
        color_label="amber",
        link_type="causality",
    )
    assert linked.status_code == 200, linked.text
    linked_body = linked.json()
    link_id = linked_body["created_link_id"]
    assert linked_body["affected_link_ids"] == [link_id]

    duplicate = _command(
        client,
        project_id,
        kind="create_link",
        expected_revision=linked_body["canvas_plot"]["revision"],
        source_node_id=second_id,
        target_node_id=first_id,
        label="ignored reverse duplicate",
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["changed"] is False
    assert duplicate.json()["canvas_plot"]["revision"] == linked_body["canvas_plot"]["revision"]

    updated_link = _command(
        client,
        project_id,
        kind="update_link",
        expected_revision=linked_body["canvas_plot"]["revision"],
        link_id=link_id,
        label="echoes",
        color_label="blue",
        link_type="echo",
    ).json()
    assert updated_link["canvas_plot"]["links"][0]["label"] == "echoes"

    framed = _command(
        client,
        project_id,
        kind="create_frame",
        expected_revision=updated_link["canvas_plot"]["revision"],
        title="Act I",
        color_label="teal",
        x=-10,
        y=-20,
        width=800,
        height=500,
    ).json()
    frame_id = framed["created_frame_id"]
    updated_frame_response = _command(
        client,
        project_id,
        kind="update_frame",
        expected_revision=framed["canvas_plot"]["revision"],
        frame_id=frame_id,
        title="Act One",
        x=15,
        y=25,
        width=900,
        height=600,
    )
    assert updated_frame_response.status_code == 200, updated_frame_response.text
    updated_frame = updated_frame_response.json()
    assert updated_frame["canvas_plot"]["frames"][0]["title"] == "Act One"

    unlinked = _command(
        client,
        project_id,
        kind="delete_link",
        expected_revision=updated_frame["canvas_plot"]["revision"],
        link_id=link_id,
    ).json()
    assert unlinked["canvas_plot"]["links"] == []
    unframed = _command(
        client,
        project_id,
        kind="delete_frame",
        expected_revision=unlinked["canvas_plot"]["revision"],
        frame_id=frame_id,
    ).json()
    deleted = _command(
        client,
        project_id,
        kind="delete_node",
        expected_revision=unframed["canvas_plot"]["revision"],
        node_id=first_id,
    ).json()
    assert [row["id"] for row in deleted["canvas_plot"]["nodes"]] == [second_id]
    assert deleted["canvas_plot"]["nodes"][0]["sort_order"] == 0

    reopened = TestClient(create_api(db=Database(path)))
    assert _snapshot(reopened, project_id) == deleted["canvas_plot"]


def test_idempotency_receipt_replays_current_board_and_survives_restart(tmp_path):
    path = str(tmp_path / "canvas-receipt.db")
    client, db, project_id = _project(path=path)
    current = _snapshot(client, project_id)
    key = "canvas-retry-00001"
    body = {
        "kind": "create_node",
        "expected_revision": current["revision"],
        "title": "Exactly once",
    }
    cursor = client.app.state.broker.latest_id()

    first = _command(
        client,
        project_id,
        idempotency_key=key,
        **body,
    )
    assert first.status_code == 200, first.text
    applied = first.json()
    created_id = applied["created_node_id"]
    assert applied["changed"] is True
    assert applied["replayed"] is False
    assert applied["applied_revision"] == applied["canvas_plot"]["revision"]

    later = _create_node(
        client,
        project_id,
        applied["canvas_plot"],
        "Later node",
    )
    replay = _command(
        client,
        project_id,
        idempotency_key=key,
        **body,
    )
    assert replay.status_code == 200, replay.text
    replayed = replay.json()
    assert replayed["changed"] is False
    assert replayed["affected_node_ids"] == []
    assert replayed["affected_link_ids"] == []
    assert replayed["affected_frame_ids"] == []
    assert replayed["created_node_id"] is None
    assert replayed["created_link_id"] is None
    assert replayed["created_frame_id"] is None
    assert replayed["replayed"] is True
    assert replayed["applied_revision"] == applied["applied_revision"]
    assert replayed["canvas_plot"] == later["canvas_plot"]
    events = client.app.state.broker.events_since(cursor, project_id)
    assert [event["event"] for event in events] == [
        "canvas_plot_changed",
        "canvas_plot_changed",
    ]

    receipt = client.get(
        f"/api/projects/{project_id}/canvas-plot/command-receipt",
        headers={"Idempotency-Key": key},
    )
    assert receipt.status_code == 200, receipt.text
    assert receipt.headers["cache-control"] == "no-store"
    vary = {value.strip() for value in receipt.headers["vary"].split(",")}
    assert {"Authorization", "Idempotency-Key"} <= vary
    receipt_body = receipt.json()
    assert receipt_body | {"committed_at": "ignored"} == {
        "project_id": project_id,
        "request_digest": receipt_body["request_digest"],
        "command_kind": "create_node",
        "expected_revision": current["revision"],
        "applied_revision": applied["applied_revision"],
        "original_changed": True,
        "original_affected_node_ids": [created_id],
        "original_affected_link_ids": [],
        "original_affected_frame_ids": [],
        "original_created_node_id": created_id,
        "original_created_link_id": None,
        "original_created_frame_id": None,
        "committed_at": "ignored",
    }
    assert len(receipt_body["request_digest"]) == 64
    with db._engine.connect() as connection:
        stored = connection.execute(text(
            "SELECT idempotency_key_hash, result_json "
            "FROM canvasplotcommandreceipt"
        )).fetchone()
    assert stored is not None
    assert len(stored[0]) == 64
    assert key not in stored[0] and key not in stored[1]
    stored_result = json.loads(stored[1])
    assert stored_result["schema_version"] == 1
    assert set(stored_result) == {
        "schema_version",
        "kind",
        "expected_revision",
        "applied_revision",
        "original_changed",
        "original_affected_node_ids",
        "original_affected_link_ids",
        "original_affected_frame_ids",
        "original_created_node_id",
        "original_created_link_id",
        "original_created_frame_id",
    }

    db._engine.dispose()
    reopened = Database(path)
    restarted = TestClient(create_api(db=reopened))
    after_restart = _command(
        restarted,
        project_id,
        idempotency_key=key,
        **body,
    )
    assert after_restart.status_code == 200, after_restart.text
    assert after_restart.json()["replayed"] is True
    assert [node.title for node in reopened.get_canvas_plot_nodes(project_id)] == [
        "Exactly once",
        "Later node",
    ]


def test_idempotency_key_reuse_with_another_canvas_request_conflicts():
    client, db, project_id = _project()
    current = _snapshot(client, project_id)
    key = "canvas-conflict-001"
    first = _command(
        client,
        project_id,
        idempotency_key=key,
        kind="create_node",
        expected_revision=current["revision"],
        title="First",
    )
    assert first.status_code == 200, first.text

    mismatched = _command(
        client,
        project_id,
        idempotency_key=key,
        kind="create_node",
        expected_revision=current["revision"],
        title="Different",
    )
    assert mismatched.status_code == 409
    assert mismatched.json()["error"]["code"] == "idempotency_key_conflict"
    assert [node.title for node in db.get_canvas_plot_nodes(project_id)] == [
        "First",
    ]


def test_idempotency_key_and_canvas_receipt_validation_is_fail_closed():
    client, db, project_id = _project()
    current = _snapshot(client, project_id)
    body = {
        "kind": "create_node",
        "expected_revision": current["revision"],
        "title": "Never created",
    }
    for key in (
        "",
        "A" * 15,
        "A" * 129,
        " leading-space-key",
        "trailing-space-key ",
        "unsafe/key-value",
    ):
        response = _command(
            client,
            project_id,
            idempotency_key=key,
            **body,
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "bad_request"

    with pytest.raises(CanvasPlotCommandError):
        db.execute_canvas_plot_command(
            project_id,
            kind="create_node",
            expected_revision=current["revision"],
            idempotency_key="é" * 16,
            title="Never created",
        )

    minimum = _command(
        client,
        project_id,
        idempotency_key="A" * 16,
        **body,
    )
    assert minimum.status_code == 200, minimum.text
    maximum = _command(
        client,
        project_id,
        idempotency_key="Z" * 128,
        kind="create_frame",
        expected_revision=minimum.json()["canvas_plot"]["revision"],
        title="Maximum key",
    )
    assert maximum.status_code == 200, maximum.text

    missing_header = client.get(
        f"/api/projects/{project_id}/canvas-plot/command-receipt",
    )
    missing_receipt = client.get(
        f"/api/projects/{project_id}/canvas-plot/command-receipt",
        headers={"Idempotency-Key": "unknown-receipt-01"},
    )
    invalid_receipt = client.get(
        f"/api/projects/{project_id}/canvas-plot/command-receipt",
        headers={"Idempotency-Key": "A" * 15},
    )
    assert missing_header.status_code == 400
    assert missing_receipt.status_code == 404
    assert invalid_receipt.status_code == 400
    assert missing_receipt.json()["error"]["code"] == (
        "canvas_plot_receipt_not_found"
    )
    for response in (missing_header, missing_receipt, invalid_receipt):
        assert response.headers["cache-control"] == "no-store"
        vary = {value.strip() for value in response.headers["vary"].split(",")}
        assert {"Authorization", "Idempotency-Key"} <= vary


def test_idempotent_canvas_no_op_commits_receipt_and_replays_current_board():
    client, db, project_id = _project()
    created = _create_node(
        client,
        project_id,
        _snapshot(client, project_id),
        "Stable",
        x=50,
    )
    key = "canvas-noop-00001"
    body = {
        "kind": "update_node",
        "expected_revision": created["canvas_plot"]["revision"],
        "node_id": created["created_node_id"],
        "x": 50,
    }
    no_op = _command(
        client,
        project_id,
        idempotency_key=key,
        **body,
    )
    assert no_op.status_code == 200, no_op.text
    assert no_op.json()["changed"] is False
    assert no_op.json()["replayed"] is False
    receipt = db.get_canvas_plot_command_receipt(project_id, key)
    assert receipt is not None
    assert receipt.original_changed is False
    assert receipt.original_affected_node_ids == ()
    assert receipt.original_affected_link_ids == ()
    assert receipt.original_affected_frame_ids == ()
    assert receipt.original_created_node_id is None
    assert receipt.original_created_link_id is None
    assert receipt.original_created_frame_id is None

    later = _create_node(
        client,
        project_id,
        no_op.json()["canvas_plot"],
        "Later",
    )
    replay = _command(
        client,
        project_id,
        idempotency_key=key,
        **body,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    assert replay.json()["changed"] is False
    assert replay.json()["canvas_plot"] == later["canvas_plot"]


def test_receipt_insert_failure_rolls_back_canvas_mutation(tmp_path):
    _client, db, project_id = _project(
        path=str(tmp_path / "canvas-receipt-rollback.db"),
    )
    snapshot = db.read_canvas_plot_snapshot(project_id)
    assert snapshot is not None
    key = "canvas-insert-fail-001"
    with db._engine.begin() as connection:
        connection.execute(text("""
            CREATE TRIGGER reject_canvas_receipt
            BEFORE INSERT ON canvasplotcommandreceipt
            BEGIN
                SELECT RAISE(ABORT, 'forced receipt rollback');
            END;
        """))

    try:
        with pytest.raises(IntegrityError):
            db.execute_canvas_plot_command(
                project_id,
                kind="create_node",
                expected_revision=snapshot.revision,
                idempotency_key=key,
                title="Must roll back",
            )
    finally:
        with db._engine.begin() as connection:
            connection.execute(text("DROP TRIGGER reject_canvas_receipt"))

    assert db.get_canvas_plot_nodes(project_id) == []
    assert db.get_canvas_plot_command_receipt(project_id, key) is None
    assert db.read_canvas_plot_snapshot(project_id).revision == snapshot.revision

    retried = db.execute_canvas_plot_command(
        project_id,
        kind="create_node",
        expected_revision=snapshot.revision,
        idempotency_key=key,
        title="Must roll back",
    )
    assert retried.changed is True
    assert retried.replayed is False
    assert [node.title for node in db.get_canvas_plot_nodes(project_id)] == [
        "Must roll back",
    ]


def test_same_canvas_key_is_exactly_once_across_database_instances(tmp_path):
    path = str(tmp_path / "canvas-independent-databases.db")
    _client, seed, project_id = _project(path=path)
    snapshot = seed.read_canvas_plot_snapshot(project_id)
    assert snapshot is not None
    first_db = Database(path)
    second_db = Database(path)
    barrier = threading.Barrier(3)
    results = []
    errors = []

    def apply(database: Database) -> None:
        barrier.wait()
        try:
            results.append(database.execute_canvas_plot_command(
                project_id,
                kind="create_node",
                expected_revision=snapshot.revision,
                idempotency_key="canvas-cross-core-001",
                title="One durable node",
            ))
        except Exception as exc:
            errors.append(exc)

    one = threading.Thread(target=apply, args=(first_db,))
    two = threading.Thread(target=apply, args=(second_db,))
    one.start()
    two.start()
    barrier.wait()
    one.join(timeout=10)
    two.join(timeout=10)

    assert not one.is_alive() and not two.is_alive()
    assert errors == []
    assert sorted((result.changed, result.replayed) for result in results) == [
        (False, True),
        (True, False),
    ]
    assert [node.title for node in seed.get_canvas_plot_nodes(project_id)] == [
        "One durable node",
    ]
    with seed._engine.connect() as connection:
        assert connection.execute(text(
            "SELECT COUNT(*) FROM canvasplotcommandreceipt"
        )).scalar_one() == 1
    first_db._engine.dispose()
    second_db._engine.dispose()


def test_canvas_receipt_is_project_scoped_and_removed_before_id_reuse():
    client, db, project_id = _project()
    original = _snapshot(client, project_id)
    key = "canvas-project-aba-001"
    applied = _command(
        client,
        project_id,
        idempotency_key=key,
        kind="create_node",
        expected_revision=original["revision"],
        title="Old project node",
    )
    assert applied.status_code == 200, applied.text
    other = db.create_project("Other", narrative_engine="novel")
    scoped_missing = client.get(
        f"/api/projects/{other.id}/canvas-plot/command-receipt",
        headers={"Idempotency-Key": key},
    )
    assert scoped_missing.status_code == 404
    assert scoped_missing.json()["error"]["code"] == (
        "canvas_plot_receipt_not_found"
    )

    db.delete_project(other.id)
    db.delete_project(project_id)
    replacement = db.create_project(
        "Canvas commands",
        narrative_engine="novel",
        default_writing_format="novel",
    )
    assert replacement.id == project_id
    assert db.get_canvas_plot_command_receipt(project_id, key) is None

    delayed = _command(
        client,
        project_id,
        idempotency_key=key,
        kind="create_node",
        expected_revision=original["revision"],
        title="Old project node",
    )
    assert delayed.status_code == 409
    assert delayed.json()["error"]["code"] == "canvas_plot_conflict"
    assert db.get_canvas_plot_nodes(project_id) == []

    replacement_snapshot = _snapshot(client, project_id)
    reused = _command(
        client,
        project_id,
        idempotency_key=key,
        kind="create_node",
        expected_revision=replacement_snapshot["revision"],
        title="Replacement project node",
    )
    assert reused.status_code == 200, reused.text
    assert reused.json()["replayed"] is False


def test_canvas_domain_failure_has_no_receipt_and_corruption_fails_closed():
    client, db, project_id = _project()
    current = _snapshot(client, project_id)
    bad_key = "canvas-domain-fail-001"
    rejected = _command(
        client,
        project_id,
        idempotency_key=bad_key,
        kind="create_link",
        expected_revision=current["revision"],
        source_node_id=999_991,
        target_node_id=999_992,
    )
    assert rejected.status_code == 404
    assert db.get_canvas_plot_command_receipt(project_id, bad_key) is None

    good_key = "canvas-corrupt-proof-001"
    applied = _command(
        client,
        project_id,
        idempotency_key=good_key,
        kind="create_node",
        expected_revision=current["revision"],
        title="Committed",
    )
    assert applied.status_code == 200, applied.text
    with Session(db._engine) as session:
        receipt = session.exec(
            select(CanvasPlotCommandReceipt).where(
                CanvasPlotCommandReceipt.project_id == project_id
            )
        ).one()
        payload = json.loads(receipt.result_json)
        payload["original_created_node_id"] = None
        receipt.result_json = json.dumps(payload)
        session.add(receipt)
        session.commit()

    with pytest.raises(RuntimeError, match="invalid result data"):
        db.get_canvas_plot_command_receipt(project_id, good_key)
    with pytest.raises(RuntimeError, match="invalid result data"):
        db.execute_canvas_plot_command(
            project_id,
            kind="create_node",
            expected_revision=current["revision"],
            idempotency_key=good_key,
            title="Committed",
        )
    assert [node.title for node in db.get_canvas_plot_nodes(project_id)] == [
        "Committed",
    ]


@pytest.mark.parametrize(
    "corruption",
    ["same_revision", "empty_family_effects", "foreign_family_effects"],
)
def test_changed_canvas_receipt_outcome_invariants_fail_closed(corruption: str):
    client, db, project_id = _project()
    created = _create_node(
        client,
        project_id,
        _snapshot(client, project_id),
        "Before",
    )
    key = "canvas-changed-proof-001"
    updated = _command(
        client,
        project_id,
        idempotency_key=key,
        kind="update_node",
        expected_revision=created["canvas_plot"]["revision"],
        node_id=created["created_node_id"],
        title="After",
    )
    assert updated.status_code == 200, updated.text

    with Session(db._engine) as session:
        receipt = session.exec(
            select(CanvasPlotCommandReceipt).where(
                CanvasPlotCommandReceipt.project_id == project_id
            )
        ).one()
        payload = json.loads(receipt.result_json)
        if corruption == "same_revision":
            payload["applied_revision"] = payload["expected_revision"]
        elif corruption == "empty_family_effects":
            payload["original_affected_node_ids"] = []
        else:
            payload["original_affected_link_ids"] = [
                created["created_node_id"],
            ]
        receipt.result_json = json.dumps(payload)
        session.add(receipt)
        session.commit()

    with pytest.raises(RuntimeError, match="invalid result data"):
        db.get_canvas_plot_command_receipt(project_id, key)


@pytest.mark.parametrize(
    "impossible_kind",
    [
        "create_node",
        "delete_node",
        "delete_link",
        "create_frame",
        "delete_frame",
    ],
)
def test_impossible_canvas_no_op_receipt_fails_closed(impossible_kind: str):
    client, db, project_id = _project()
    created = _create_node(
        client,
        project_id,
        _snapshot(client, project_id),
        "Stable",
    )
    key = "canvas-noop-proof-001"
    no_op = _command(
        client,
        project_id,
        idempotency_key=key,
        kind="update_node",
        expected_revision=created["canvas_plot"]["revision"],
        node_id=created["created_node_id"],
        title="Stable",
    )
    assert no_op.status_code == 200, no_op.text

    with Session(db._engine) as session:
        receipt = session.exec(
            select(CanvasPlotCommandReceipt).where(
                CanvasPlotCommandReceipt.project_id == project_id
            )
        ).one()
        payload = json.loads(receipt.result_json)
        payload["kind"] = impossible_kind
        receipt.result_json = json.dumps(payload)
        session.add(receipt)
        session.commit()

    with pytest.raises(RuntimeError, match="invalid result data"):
        db.get_canvas_plot_command_receipt(project_id, key)


def test_no_op_canvas_receipt_cannot_claim_an_advanced_revision():
    client, db, project_id = _project()
    created = _create_node(
        client,
        project_id,
        _snapshot(client, project_id),
        "Stable",
    )
    key = "canvas-noop-revision-001"
    no_op = _command(
        client,
        project_id,
        idempotency_key=key,
        kind="update_node",
        expected_revision=created["canvas_plot"]["revision"],
        node_id=created["created_node_id"],
        title="Stable",
    )
    assert no_op.status_code == 200, no_op.text

    with Session(db._engine) as session:
        receipt = session.exec(
            select(CanvasPlotCommandReceipt).where(
                CanvasPlotCommandReceipt.project_id == project_id
            )
        ).one()
        payload = json.loads(receipt.result_json)
        payload["applied_revision"] = "0" * 64
        assert payload["applied_revision"] != payload["expected_revision"]
        receipt.result_json = json.dumps(payload)
        session.add(receipt)
        session.commit()

    with pytest.raises(RuntimeError, match="invalid result data"):
        db.get_canvas_plot_command_receipt(project_id, key)


def test_delete_node_receipt_allows_incident_link_effects():
    client, db, project_id = _project()
    first = _create_node(
        client,
        project_id,
        _snapshot(client, project_id),
        "First",
    )
    second = _create_node(
        client,
        project_id,
        first["canvas_plot"],
        "Second",
    )
    linked = _command(
        client,
        project_id,
        kind="create_link",
        expected_revision=second["canvas_plot"]["revision"],
        source_node_id=first["created_node_id"],
        target_node_id=second["created_node_id"],
    )
    assert linked.status_code == 200, linked.text
    key = "canvas-delete-proof-001"
    deleted = _command(
        client,
        project_id,
        idempotency_key=key,
        kind="delete_node",
        expected_revision=linked.json()["canvas_plot"]["revision"],
        node_id=first["created_node_id"],
    )
    assert deleted.status_code == 200, deleted.text

    receipt = db.get_canvas_plot_command_receipt(project_id, key)
    assert receipt is not None
    assert receipt.original_affected_node_ids == (first["created_node_id"],)
    assert receipt.original_affected_link_ids == (linked.json()["created_link_id"],)
    assert receipt.original_affected_frame_ids == ()


def test_duplicate_create_link_is_a_valid_receipted_no_op():
    client, db, project_id = _project()
    first = _create_node(
        client,
        project_id,
        _snapshot(client, project_id),
        "First",
    )
    second = _create_node(
        client,
        project_id,
        first["canvas_plot"],
        "Second",
    )
    linked = _command(
        client,
        project_id,
        kind="create_link",
        expected_revision=second["canvas_plot"]["revision"],
        source_node_id=first["created_node_id"],
        target_node_id=second["created_node_id"],
    )
    assert linked.status_code == 200, linked.text
    key = "canvas-link-noop-001"
    duplicate = _command(
        client,
        project_id,
        idempotency_key=key,
        kind="create_link",
        expected_revision=linked.json()["canvas_plot"]["revision"],
        source_node_id=second["created_node_id"],
        target_node_id=first["created_node_id"],
    )
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["changed"] is False

    receipt = db.get_canvas_plot_command_receipt(project_id, key)
    assert receipt is not None
    assert receipt.kind == "create_link"
    assert receipt.original_changed is False
    assert receipt.applied_revision == receipt.expected_revision


def test_stale_and_exact_no_op_commands_do_not_mutate_or_publish():
    client, db, project_id = _project()
    created = _create_node(client, project_id, _snapshot(client, project_id), "A")
    stale = created["canvas_plot"]
    moved = _command(
        client,
        project_id,
        kind="update_node",
        expected_revision=stale["revision"],
        node_id=created["created_node_id"],
        x=90,
    ).json()
    cursor = client.app.state.broker.latest_id()
    rejected = _command(
        client,
        project_id,
        kind="update_node",
        expected_revision=stale["revision"],
        node_id=created["created_node_id"],
        width=400,
    )
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "canvas_plot_conflict"
    assert _snapshot(client, project_id) == moved["canvas_plot"]
    assert client.app.state.broker.events_since(cursor, project_id) == []

    no_op = _command(
        client,
        project_id,
        kind="update_node",
        expected_revision=moved["canvas_plot"]["revision"],
        node_id=created["created_node_id"],
        x=90,
    )
    assert no_op.status_code == 200 and no_op.json()["changed"] is False
    assert client.app.state.broker.events_since(cursor, project_id) == []
    assert db.get_canvas_plot_nodes(project_id)[0].width == 180.0


def test_legacy_foreign_references_invalid_links_and_duplicates_never_leak():
    client, db, project_id = _project()
    other = db.create_project("Other", narrative_engine="novel")
    foreign_scene = db.create_scene(other.id, "Foreign scene")
    first = db.create_canvas_plot_node(
        project_id, title="First", scene_id=foreign_scene.id,
    )
    second = db.create_canvas_plot_node(project_id, title="Second")
    foreign_node = db.create_canvas_plot_node(other.id, title="Foreign node")
    valid = db.add_canvas_plot_link(project_id, first.id, second.id)
    db.add_canvas_plot_link(project_id, first.id, foreign_node.id)
    with Session(db._engine) as session:
        session.add(CanvasPlotLink(
            project_id=project_id,
            source_node_id=second.id,
            target_node_id=first.id,
            label="duplicate",
        ))
        session.add(CanvasPlotLink(
            project_id=project_id,
            source_node_id=first.id,
            target_node_id=first.id,
            label="self",
        ))
        session.commit()

    snapshot = _snapshot(client, project_id)
    assert snapshot["nodes"][0]["scene_id"] is None
    assert [row["id"] for row in snapshot["links"]] == [valid.id]
    assert all(
        endpoint in {first.id, second.id}
        for row in snapshot["links"]
        for endpoint in (row["source_node_id"], row["target_node_id"])
    )

    deleted = _command(
        client,
        project_id,
        kind="delete_link",
        expected_revision=snapshot["revision"],
        link_id=valid.id,
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["canvas_plot"]["links"] == []

    # Restore one canonical link so node deletion proves that it removes both
    # visible and hidden incident rows owned by this project. The hidden rows
    # include the cross-project endpoint and self-link inserted above.
    relinked = _command(
        client,
        project_id,
        kind="create_link",
        expected_revision=deleted.json()["canvas_plot"]["revision"],
        source_node_id=first.id,
        target_node_id=second.id,
    )
    assert relinked.status_code == 200, relinked.text

    removed_node = _command(
        client,
        project_id,
        kind="delete_node",
        expected_revision=relinked.json()["canvas_plot"]["revision"],
        node_id=first.id,
    )
    assert removed_node.status_code == 200, removed_node.text
    assert all(
        first.id not in (link.source_node_id, link.target_node_id)
        for link in db.get_canvas_plot_links(project_id)
    )
    assert [node.id for node in db.get_canvas_plot_nodes(other.id)] == [
        foreign_node.id,
    ]


def test_delete_node_rejects_foreign_owned_incident_link_without_mutation():
    client, db, project_id = _project()
    other = db.create_project("Other", narrative_engine="novel")
    first = db.create_canvas_plot_node(project_id, title="First")
    second = db.create_canvas_plot_node(project_id, title="Second")
    foreign_node = db.create_canvas_plot_node(other.id, title="Foreign")
    local_link = db.add_canvas_plot_link(project_id, first.id, second.id)
    assert local_link is not None
    with Session(db._engine) as session:
        local_hidden = CanvasPlotLink(
            project_id=project_id,
            source_node_id=first.id,
            target_node_id=first.id,
            label="local hidden self-link",
        )
        foreign_owned = CanvasPlotLink(
            project_id=other.id,
            source_node_id=foreign_node.id,
            target_node_id=first.id,
            label="foreign-owned corrupt link",
        )
        session.add(local_hidden)
        session.add(foreign_owned)
        session.commit()
        session.refresh(local_hidden)
        session.refresh(foreign_owned)
        local_hidden_id = int(local_hidden.id)
        foreign_owned_id = int(foreign_owned.id)

    before = _snapshot(client, project_id)
    cursor = client.app.state.broker.latest_id()
    rejected = _command(
        client,
        project_id,
        kind="delete_node",
        expected_revision=before["revision"],
        node_id=first.id,
    )
    assert rejected.status_code == 400, rejected.text
    message = rejected.json()["error"]["message"]
    assert message == (
        "Canvas Plot node cannot be deleted because the board contains "
        "inconsistent link ownership"
    )
    assert str(foreign_owned_id) not in message
    assert _snapshot(client, project_id) == before
    assert client.app.state.broker.events_since(cursor, project_id) == []
    assert {node.id for node in db.get_canvas_plot_nodes(project_id)} == {
        first.id,
        second.id,
    }
    assert {link.id for link in db.get_canvas_plot_links(project_id)} == {
        local_link.id,
        local_hidden_id,
    }
    assert {link.id for link in db.get_canvas_plot_links(other.id)} == {
        foreign_owned_id,
    }


@pytest.mark.parametrize("via_structure", [False, True])
def test_scene_delete_rotates_revision_clears_reference_and_publishes_event(
    via_structure: bool,
):
    client, db, project_id = _project()
    scene = db.create_scene(project_id, "Anchor")
    created = _create_node(
        client,
        project_id,
        _snapshot(client, project_id),
        "Scene card",
        scene_id=scene.id,
    )
    cursor = client.app.state.broker.latest_id()
    if via_structure:
        structure = client.get(
            f"/api/projects/{project_id}/story-structure",
        ).json()
        deleted = client.post(
            f"/api/projects/{project_id}/story-structure/commands",
            json={
                "kind": "delete_scene",
                "expected_revision": structure["revision"],
                "scene_id": scene.id,
            },
        )
    else:
        deleted = client.delete(f"/api/projects/{project_id}/scenes/{scene.id}")
    assert deleted.status_code == 200
    after = _snapshot(client, project_id)
    assert after["revision"] != created["canvas_plot"]["revision"]
    assert after["nodes"][0]["scene_id"] is None
    assert "canvas_plot_changed" in [
        event["event"]
        for event in client.app.state.broker.events_since(cursor, project_id)
    ]


def test_viewport_settings_do_not_rotate_structural_revision():
    client, db, project_id = _project()
    before = _snapshot(client, project_id)
    db.save_project_settings(project_id, {
        "theme": "midnight",
        "canvas_plot_view": {"zoom": 1.75, "cx": 420, "cy": -80},
    })
    after = _snapshot(client, project_id)
    assert after == before


def test_foreign_scene_and_node_commands_are_indistinguishable_from_missing():
    client, db, project_id = _project()
    local = db.create_canvas_plot_node(project_id, title="Local")
    other = db.create_project("Other", narrative_engine="novel")
    foreign_node = db.create_canvas_plot_node(other.id, title="Foreign")
    foreign_scene = db.create_scene(other.id, "Foreign scene")
    current = _snapshot(client, project_id)

    responses = [
        _command(
            client,
            project_id,
            kind="update_node",
            expected_revision=current["revision"],
            node_id=foreign_node.id,
            title="No",
        ),
        _command(
            client,
            project_id,
            kind="create_link",
            expected_revision=current["revision"],
            source_node_id=local.id,
            target_node_id=foreign_node.id,
        ),
        _command(
            client,
            project_id,
            kind="create_node",
            expected_revision=current["revision"],
            title="No",
            scene_id=foreign_scene.id,
        ),
    ]
    assert [response.status_code for response in responses] == [404, 404, 404]
    assert _snapshot(client, project_id) == current


def test_sql_failure_rolls_back_geometry_transaction(tmp_path):
    _client, db, project_id = _project(path=str(tmp_path / "rollback.db"))
    node = db.create_canvas_plot_node(project_id, title="A", x=1, y=2)
    snapshot = db.read_canvas_plot_snapshot(project_id)
    assert snapshot is not None
    with db._engine.begin() as connection:
        connection.execute(text(f"""
            CREATE TRIGGER reject_canvas_move
            BEFORE UPDATE OF x ON canvasplotnode
            WHEN OLD.id = {node.id}
            BEGIN
                SELECT RAISE(ABORT, 'forced canvas rollback');
            END;
        """))
    try:
        with pytest.raises(IntegrityError):
            db.execute_canvas_plot_command(
                project_id,
                kind="update_node",
                expected_revision=snapshot.revision,
                node_id=node.id,
                x=100,
                y=200,
            )
    finally:
        with db._engine.begin() as connection:
            connection.execute(text("DROP TRIGGER reject_canvas_move"))
    stored = db.get_canvas_plot_nodes(project_id)[0]
    assert (stored.x, stored.y) == (1.0, 2.0)
    assert db.read_canvas_plot_snapshot(project_id).revision == snapshot.revision


def test_concurrent_commands_have_one_winner_and_one_conflict(tmp_path):
    client, db, project_id = _project(path=str(tmp_path / "race.db"))
    revision = _snapshot(client, project_id)["revision"]
    barrier = threading.Barrier(3)
    responses = []

    def create(title: str) -> None:
        local = TestClient(create_api(db=Database(str(tmp_path / "race.db"))))
        barrier.wait()
        responses.append(_command(
            local,
            project_id,
            kind="create_node",
            expected_revision=revision,
            title=title,
        ))

    one = threading.Thread(target=create, args=("One",))
    two = threading.Thread(target=create, args=("Two",))
    one.start()
    two.start()
    barrier.wait()
    one.join(timeout=5)
    two.join(timeout=5)
    assert not one.is_alive() and not two.is_alive()
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert len(db.get_canvas_plot_nodes(project_id)) == 1


def test_command_validation_rejects_bool_nonfinite_null_and_unknown_fields():
    client, db, project_id = _project()
    node = db.create_canvas_plot_node(project_id, title="A")
    revision = _snapshot(client, project_id)["revision"]
    bodies = [
        {"kind": "update_node", "node_id": True, "x": 1},
        {"kind": "update_node", "node_id": node.id, "x": None},
        {"kind": "update_node", "node_id": node.id, "x": "NaN"},
        {"kind": "update_node", "node_id": node.id, "unknown": 1},
        {"kind": "update_node", "node_id": node.id},
        {"kind": "create_frame", "width": -1},
    ]
    for body in bodies:
        response = _command(
            client,
            project_id,
            expected_revision=revision,
            **body,
        )
        assert response.status_code == 422, (body, response.text)
    assert _snapshot(client, project_id)["revision"] == revision


def test_node_creation_identity_prevents_id_reuse_aba():
    client, db, project_id = _project()
    original = db.create_canvas_plot_node(project_id, title="Same")
    stale = _snapshot(client, project_id)
    db.delete_canvas_plot_node(original.id)
    replacement = db.create_canvas_plot_node(project_id, title="Same")
    assert replacement.id == original.id
    current = _snapshot(client, project_id)
    assert current["revision"] != stale["revision"]
    rejected = _command(
        client,
        project_id,
        kind="update_node",
        expected_revision=stale["revision"],
        node_id=replacement.id,
        title="Stale edit",
    )
    assert rejected.status_code == 409
    assert _snapshot(client, project_id) == current
