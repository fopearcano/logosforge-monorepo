"""Canonical HTTP read slice for the Narrative Knowledge Graph."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from logosforge.api import create_api, schemas
from logosforge.db import Database
from logosforge.knowledge_graph import provenance as P
from logosforge.knowledge_graph.models import node_key
from pydantic import ValidationError


def _graph_project():
    db = Database()
    project = db.create_project("Graph API", narrative_engine="novel")
    first = db.create_scene(project.id, "Opening", content="Alice arrives.")
    second = db.create_scene(project.id, "Aftermath", content="Silence follows.")
    alice = db.create_psyke_entry(project.id, "Alice", "character")
    lonely = db.create_psyke_entry(project.id, "Lonely Relic", "object")
    client = TestClient(create_api(db=db))
    return client, db, project, first, second, alice, lonely


def test_http_and_mcp_contract_versions_are_deliberately_independent():
    from logosforge.api.app import API_CONTRACT_VERSION
    from logosforge.librechat.mcp_server import SERVER_VERSION

    assert API_CONTRACT_VERSION == "1.14.0"
    assert SERVER_VERSION == "1.10.0"


def test_project_map_exposes_traceable_graph_and_pretruncation_diagnostics():
    client, _, project, first, _, alice, lonely = _graph_project()

    response = client.get(f"/api/projects/{project.id}/knowledge-graph")
    assert response.status_code == 200
    body = response.json()

    assert body["project_id"] == project.id
    assert body["focus_key"] is None
    assert body["depth"] == 1
    assert body["include_inferred"] is True
    assert body["view_mode"] == "project_map"
    assert body["story_gravity_available"] is True
    assert body["story_diagnostics_available"] is True
    assert body["returned_node_count"] == len(body["nodes"])
    assert body["returned_edge_count"] == len(body["edges"])
    assert body["node_count"] >= body["returned_node_count"]
    assert body["edge_count"] >= body["returned_edge_count"]

    keys = {node["key"] for node in body["nodes"]}
    alice_key = node_key(P.NT_CHARACTER, "psyke", alice.id)
    scene_key = node_key(P.NT_SCENE, "scene", first.id)
    lonely_key = node_key(P.NT_OBJECT, "psyke", lonely.id)
    assert {alice_key, scene_key, lonely_key}.issubset(keys)
    assert lonely_key in body["orphan_keys"]
    assert body["orphan_count"] >= 1
    assert body["weak_link_count"] >= 1
    assert body["weak_links"]
    assert all(edge["is_inferred"] for edge in body["weak_links"])
    assert all(edge["source"] in keys and edge["target"] in keys
               for edge in body["weak_links"])

    node_by_key = {node["key"]: node for node in body["nodes"]}
    assert all("story_gravity" in node for node in body["nodes"])
    assert 0.0 <= node_by_key[alice_key]["story_gravity"] <= 1.0
    # The legacy GraphData model intentionally omits isolated scenes, so the
    # canonical scene remains visible with an explicit unsupported value.
    assert node_by_key[scene_key]["story_gravity"] is None
    assert node_by_key[alice_key]["degree"] >= 1
    assert node_by_key[lonely_key]["degree"] == 0
    assert all(edge["source"] in keys and edge["target"] in keys
               for edge in body["edges"])


def test_project_map_limit_is_bounded_and_reserves_orphan_visibility():
    db = Database()
    project = db.create_project("Many orphans")
    for index in range(12):
        db.create_psyke_entry(project.id, f"Orphan {index:02d}", "object")
    client = TestClient(create_api(db=db))

    body = client.get(
        f"/api/projects/{project.id}/knowledge-graph", params={"limit": 4},
    ).json()

    assert len(body["nodes"]) <= 4
    assert len(body["edges"]) <= 4
    assert len(body["weak_links"]) <= 4
    assert body["node_count"] > body["returned_node_count"]
    assert body["orphan_count"] == 12
    assert body["orphan_keys"]
    assert set(body["orphan_keys"]).issubset(
        {node["key"] for node in body["nodes"]}
    )
    assert body["truncated"] is True


def test_diagnostic_cap_marks_an_otherwise_complete_project_map_truncated():
    db = Database()
    project = db.create_project("Many weak links")
    for index in range(30):
        db.create_scene(project.id, f"Scene {index:02d}")
    client = TestClient(create_api(db=db))

    body = client.get(
        f"/api/projects/{project.id}/knowledge-graph", params={"limit": 200},
    ).json()

    assert body["node_count"] == body["returned_node_count"]
    assert body["edge_count"] == body["returned_edge_count"]
    assert body["weak_link_count"] > len(body["weak_links"])
    assert len(body["weak_links"]) == 25
    assert body["truncated"] is True


def test_neighborhood_is_bounded_and_can_exclude_inferred_edges():
    client, _, project, first, second, _, _ = _graph_project()
    focus_key = node_key(P.NT_SCENE, "scene", first.id)

    body = client.get(
        f"/api/projects/{project.id}/knowledge-graph",
        params={
            "focus_key": focus_key,
            "depth": 1,
            "limit": 20,
            "include_inferred": "false",
        },
    ).json()

    assert body["focus_key"] == focus_key
    assert body["include_inferred"] is False
    assert body["nodes"][0]["key"] == focus_key
    assert body["weak_links"] == []
    assert body["weak_link_count"] == 0
    assert all(not edge["is_inferred"] for edge in body["edges"])
    # The only first→second link is inferred manuscript order.
    second_key = node_key(P.NT_SCENE, "scene", second.id)
    assert second_key not in {node["key"] for node in body["nodes"]}

    confirmed_only_second = client.get(
        f"/api/projects/{project.id}/knowledge-graph",
        params={"focus_key": second_key, "include_inferred": "false"},
    ).json()
    assert confirmed_only_second["orphan_keys"] == [second_key]
    with_inferred_second = client.get(
        f"/api/projects/{project.id}/knowledge-graph",
        params={"focus_key": second_key, "include_inferred": "true"},
    ).json()
    assert second_key not in with_inferred_second["orphan_keys"]


def test_graph_read_rejects_foreign_focus_and_never_leaks_foreign_project():
    db = Database()
    owner = db.create_project("Owner")
    foreign = db.create_project("Foreign")
    owner_scene = db.create_scene(owner.id, "Owner Scene")
    foreign_scene = db.create_scene(foreign.id, "TOP SECRET FOREIGN SCENE")
    db.create_psyke_entry(foreign.id, "TOP SECRET FOREIGN CHARACTER", "character")
    client = TestClient(create_api(db=db))

    owner_response = client.get(f"/api/projects/{owner.id}/knowledge-graph")
    assert owner_response.status_code == 200
    assert "TOP SECRET FOREIGN" not in owner_response.text
    owner_keys = {node["key"] for node in owner_response.json()["nodes"]}
    assert node_key(P.NT_SCENE, "scene", owner_scene.id) in owner_keys
    assert node_key(P.NT_SCENE, "scene", foreign_scene.id) not in owner_keys

    stale_focus = client.get(
        f"/api/projects/{owner.id}/knowledge-graph",
        params={"focus_key": node_key(P.NT_SCENE, "scene", foreign_scene.id)},
    )
    assert stale_focus.status_code == 404
    assert stale_focus.json()["error"]["code"] == "not_found"
    assert client.get("/api/projects/999999/knowledge-graph").status_code == 404


def test_graph_query_validation_and_read_only_behavior():
    client, db, project, *_ = _graph_project()
    root = f"/api/projects/{project.id}/knowledge-graph"
    before = (
        len(db.get_all_scenes(project.id)),
        len(db.get_all_psyke_entries(project.id)),
        len(db.get_kg_edges(project.id)),
    )

    assert client.get(root, params={"depth": 0}).status_code == 422
    assert client.get(root, params={"depth": 3}).status_code == 422
    assert client.get(root, params={"limit": 0}).status_code == 422
    assert client.get(root, params={"limit": 201}).status_code == 422
    assert client.get(root, params={"focus_key": "x" * 1025}).status_code == 422
    for view_mode in (
        "project_map", "structure", "recorded_risk", "revision_impact",
    ):
        assert client.get(root, params={"view_mode": view_mode}).status_code == 200
    for invalid_view_mode in ("risk", "Structure", "predictive_risk"):
        assert client.get(
            root, params={"view_mode": invalid_view_mode},
        ).status_code == 422
    assert client.get(root).status_code == 200

    after = (
        len(db.get_all_scenes(project.id)),
        len(db.get_all_psyke_entries(project.id)),
        len(db.get_kg_edges(project.id)),
    )
    assert after == before


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -0.01, 1.01])
def test_story_gravity_contract_rejects_non_finite_or_out_of_range(invalid):
    with pytest.raises(ValidationError):
        schemas.KnowledgeGraphNodeDTO(
            key="scene:scene:1",
            node_type="scene",
            story_gravity=invalid,
        )


def test_overlong_structural_keys_use_stable_focusable_wire_ids():
    db = Database()
    project = db.create_project("Long keys")
    db.create_scene(project.id, "Long-act scene", act="A" * 2000)
    client = TestClient(create_api(db=db))
    root = f"/api/projects/{project.id}/knowledge-graph"

    project_map = client.get(root).json()
    act_node = next(node for node in project_map["nodes"] if node["node_type"] == "act")
    assert act_node["key"].startswith("kg:sha256:")
    assert len(act_node["key"]) <= 512
    assert all(len(node["key"]) <= 512 for node in project_map["nodes"])
    assert all(len(edge[endpoint]) <= 512
               for edge in project_map["edges"] for endpoint in ("source", "target"))

    focused = client.get(root, params={"focus_key": act_node["key"]})
    assert focused.status_code == 200
    assert focused.json()["focus_key"] == act_node["key"]


def test_graph_is_built_once_per_http_request(monkeypatch):
    client, _, project, *_ = _graph_project()
    from logosforge.api.routes import knowledge_graph as route_module

    real_builder = route_module.build_knowledge_graph
    calls = 0

    def counted_builder(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real_builder(*args, **kwargs)

    monkeypatch.setattr(route_module, "build_knowledge_graph", counted_builder)
    response = client.get(f"/api/projects/{project.id}/knowledge-graph")
    assert response.status_code == 200
    assert calls == 1


def test_story_gravity_failure_preserves_canonical_graph(monkeypatch):
    client, _, project, *_ = _graph_project()
    from logosforge import graph_data

    def failed_legacy_graph(*_args, **_kwargs):
        raise RuntimeError("private storage failure must not reach the response")

    monkeypatch.setattr(graph_data, "build_graph_data", failed_legacy_graph)
    response = client.get(f"/api/projects/{project.id}/knowledge-graph")

    assert response.status_code == 200
    assert "private storage failure" not in response.text
    body = response.json()
    assert body["story_gravity_available"] is False
    assert body["nodes"]
    assert all(node["story_gravity"] is None for node in body["nodes"])


def test_precedes_edges_carry_full_manuscript_flow_metadata():
    db = Database()
    project = db.create_project("Flow metadata")
    acts = ("Act I", "Act I", "Act II", "Act II", "Act III")
    for index, act in enumerate(acts):
        db.create_scene(project.id, f"Scene {index + 1}", act=act)
    client = TestClient(create_api(db=db))

    body = client.get(
        f"/api/projects/{project.id}/knowledge-graph",
        params={"view_mode": "structure", "limit": 200},
    ).json()
    flow = sorted(
        (edge for edge in body["edges"] if edge["edge_type"] == P.ET_PRECEDES),
        key=lambda edge: edge["metadata"]["story_order_index"],
    )

    assert len(flow) == 4
    assert [edge["metadata"] for edge in flow] == [
        {
            "act_boundary": False,
            "story_order_band": "beginning",
            "story_order_index": 0,
            "story_order_total": 5,
        },
        {
            "act_boundary": True,
            "story_order_band": "beginning",
            "story_order_index": 1,
            "story_order_total": 5,
        },
        {
            "act_boundary": False,
            "story_order_band": "middle",
            "story_order_index": 2,
            "story_order_total": 5,
        },
        {
            "act_boundary": True,
            "story_order_band": "ending",
            "story_order_index": 3,
            "story_order_total": 5,
        },
    ]


def _risk_graph_project():
    db = Database()
    project = db.create_project("Graph views", narrative_engine="novel")
    first = db.create_scene(
        project.id,
        "Opening",
        content="Alice arrives.",
        act="Act 1",
        chapter="Chapter 1",
    )
    second = db.create_scene(
        project.id,
        "Aftermath",
        content="Silence follows.",
        act="Act 1",
        chapter="Chapter 1",
    )
    unrelated = db.create_scene(
        project.id,
        "Coda",
        act="Act 1",
        chapter="Chapter 1",
    )
    alice = db.create_psyke_entry(project.id, "Alice", "character")
    report = db.create_revision_impact_report(
        project.id,
        scene_id=first.id,
        title="Opening impact",
        impact_level="high",
        confidence="confirmed",
        items=[{
            "target_type": "psyke_entry",
            "target_id": str(alice.id),
            "label": "Alice",
            "impact_kind": "character_change",
            "severity": "warning",
            "confidence": "possible",
            "explanation": "Alice may need a follow-up beat.",
            "suggested_action": "Review Alice's progression.",
        }],
    )
    db.create_apply_operation(
        project.id,
        target_type="scene",
        target_id=second.id,
        status="previewed",
        conflicts=[{
            "conflict_type": "hash_mismatch",
            "severity": "warning",
            "message": "The scene changed.",
        }],
    )
    client = TestClient(create_api(db=db))
    return client, db, project, first, second, unrelated, alice, report


def test_specialty_views_project_before_bounds_with_exact_semantics():
    client, db, project, first, _, _, alice, report = _risk_graph_project()
    for index in range(12):
        db.create_psyke_entry(project.id, f"Noise {index:02d}", "object")
    root = f"/api/projects/{project.id}/knowledge-graph"

    project_map = client.get(root, params={"limit": 200}).json()
    structure = client.get(
        root, params={"view_mode": "structure", "limit": 2},
    ).json()
    assert structure["view_mode"] == "structure"
    assert structure["story_diagnostics_available"] is False
    assert structure["orphan_keys"] == []
    assert structure["orphan_count"] == 0
    assert structure["weak_links"] == []
    assert structure["weak_link_count"] == 0
    assert structure["node_count"] < project_map["node_count"]
    assert structure["node_count"] > structure["returned_node_count"]
    assert structure["truncated"] is True
    assert all(node["node_type"] in {
        "project", "act", "chapter", "scene", "plot_block", "timeline_event",
    } for node in structure["nodes"])
    assert all(edge["edge_type"] in {
        "contains", "belongs_to", "precedes", "follows",
    } for edge in structure["edges"])

    recorded_risk = client.get(
        root, params={"view_mode": "recorded_risk", "limit": 200},
    ).json()
    assert recorded_risk["story_diagnostics_available"] is False
    assert {edge["edge_type"] for edge in recorded_risk["edges"]} == {
        "risks", "contradicts",
    }
    risk_endpoints = {
        key for edge in recorded_risk["edges"]
        for key in (edge["source"], edge["target"])
    }
    assert {node["key"] for node in recorded_risk["nodes"]} == risk_endpoints

    revision = client.get(
        root, params={"view_mode": "revision_impact", "limit": 200},
    ).json()
    assert revision["story_diagnostics_available"] is False
    assert {edge["source_system"] for edge in revision["edges"]} == {
        P.SS_REVISION,
    }
    assert {edge["edge_type"] for edge in revision["edges"]} == {
        P.ET_REVISES, P.ET_RISKS,
    }
    revision_endpoints = {
        key for edge in revision["edges"]
        for key in (edge["source"], edge["target"])
    }
    assert {node["key"] for node in revision["nodes"]} == revision_endpoints
    assert node_key(P.NT_CHARACTER, "psyke", alice.id) in revision_endpoints
    assert node_key(P.NT_PSYKE_ENTRY, "psyke", alice.id) not in revision_endpoints
    item_edge = next(edge for edge in revision["edges"]
                     if edge["edge_type"] == P.ET_RISKS)
    assert item_edge["metadata"] == {
        "impact_kind": "character_change",
        "item_id": db.get_revision_impact_items(report.id)[0].id,
        "label": "Alice",
        "severity": "warning",
        "suggested_action": "Review Alice's progression.",
    }


def test_view_mode_and_inferred_evidence_scope_are_orthogonal():
    client, _, project, first, _, _, alice, _ = _risk_graph_project()
    root = f"/api/projects/{project.id}/knowledge-graph"

    structure_all = client.get(root, params={
        "view_mode": "structure", "include_inferred": "true", "limit": 200,
    }).json()
    structure_confirmed = client.get(root, params={
        "view_mode": "structure", "include_inferred": "false", "limit": 200,
    }).json()
    assert any(edge["edge_type"] == P.ET_PRECEDES
               for edge in structure_all["edges"])
    assert all(edge["edge_type"] != P.ET_PRECEDES
               for edge in structure_confirmed["edges"])
    assert all(not edge["is_inferred"] for edge in structure_confirmed["edges"])

    risk_all = client.get(root, params={
        "view_mode": "recorded_risk", "include_inferred": "true",
    }).json()
    risk_confirmed = client.get(root, params={
        "view_mode": "recorded_risk", "include_inferred": "false",
    }).json()
    assert risk_all["edge_count"] > 0
    assert risk_confirmed["edge_count"] == 0
    assert risk_confirmed["node_count"] == 0

    revision_confirmed = client.get(root, params={
        "view_mode": "revision_impact", "include_inferred": "false",
    }).json()
    assert {edge["edge_type"] for edge in revision_confirmed["edges"]} == {
        P.ET_REVISES,
    }
    assert node_key(P.NT_SCENE, "scene", first.id) in {
        node["key"] for node in revision_confirmed["nodes"]
    }
    assert node_key(P.NT_CHARACTER, "psyke", alice.id) not in {
        node["key"] for node in revision_confirmed["nodes"]
    }


def test_specialty_focus_outside_projection_is_indistinguishable_from_unknown():
    client, _, project, _, _, unrelated, alice, _ = _risk_graph_project()
    root = f"/api/projects/{project.id}/knowledge-graph"

    excluded_structure = client.get(root, params={
        "view_mode": "structure",
        "focus_key": node_key(P.NT_CHARACTER, "psyke", alice.id),
    })
    unknown_structure = client.get(root, params={
        "view_mode": "structure",
        "focus_key": "scene:scene:999999",
    })
    assert excluded_structure.status_code == unknown_structure.status_code == 404
    assert excluded_structure.json() == unknown_structure.json()

    excluded_risk = client.get(root, params={
        "view_mode": "recorded_risk",
        "focus_key": node_key(P.NT_SCENE, "scene", unrelated.id),
    })
    assert excluded_risk.status_code == 404
    assert excluded_risk.json()["error"]["code"] == "not_found"

    evidence_excluded = client.get(root, params={
        "view_mode": "revision_impact",
        "include_inferred": "false",
        "focus_key": node_key(P.NT_CHARACTER, "psyke", alice.id),
    })
    assert evidence_excluded.status_code == 404


def test_specialty_views_are_bounded_deterministic_and_ignore_hidden_injection():
    from logosforge.knowledge_graph import build_knowledge_graph, hide_edge

    client, db, project, *_ = _risk_graph_project()
    graph = build_knowledge_graph(db, project.id).graph
    psyke_edge = next(edge for edge in graph.edges
                      if edge.edge_type == P.ET_APPEARS_IN)
    hide_edge(db, project.id, psyke_edge)
    root = f"/api/projects/{project.id}/knowledge-graph"

    first = client.get(root, params={
        "view_mode": "recorded_risk", "limit": 1,
    }).json()
    second = client.get(root, params={
        "view_mode": "recorded_risk", "limit": 1,
    }).json()
    assert first == second
    assert len(first["nodes"]) <= 1
    assert len(first["edges"]) <= 1
    assert first["hidden_edge_count"] == 1
    assert first["hidden_edges"] == []
    assert first["truncated"] is True

    structure = client.get(root, params={
        "view_mode": "structure", "limit": 200,
    }).json()
    assert structure["hidden_edge_count"] == 1
    assert structure["hidden_edges"] == []
    assert all(node["node_type"] != P.NT_CHARACTER
               for node in structure["nodes"])

    hidden_page = client.get(
        f"{root}/hidden-edges", params={"offset": 0, "limit": 100},
    ).json()
    assert hidden_page["hidden_edge_count"] == 1
    assert hidden_page["returned_edge_count"] == 1
    assert {node["key"] for node in hidden_page["nodes"]} == {
        hidden_page["edges"][0]["source"],
        hidden_page["edges"][0]["target"],
    }

    clean_db = Database()
    clean_project = clean_db.create_project("Hidden only")
    clean_db.create_scene(clean_project.id, "One")
    clean_db.create_scene(clean_project.id, "Two")
    clean_graph = build_knowledge_graph(clean_db, clean_project.id).graph
    hidden_order = next(edge for edge in clean_graph.edges
                        if edge.edge_type == P.ET_PRECEDES)
    hide_edge(clean_db, clean_project.id, hidden_order)
    clean_client = TestClient(create_api(db=clean_db))
    empty_risk = clean_client.get(
        f"/api/projects/{clean_project.id}/knowledge-graph",
        params={"view_mode": "recorded_risk"},
    ).json()
    assert empty_risk["nodes"] == []
    assert empty_risk["edges"] == []
    assert empty_risk["hidden_edges"] == []
    assert empty_risk["hidden_edge_count"] == 1
    assert empty_risk["truncated"] is False
