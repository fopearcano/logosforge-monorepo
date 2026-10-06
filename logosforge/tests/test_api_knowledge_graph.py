"""Canonical HTTP read slice for the Narrative Knowledge Graph."""

from __future__ import annotations

from fastapi.testclient import TestClient

from logosforge.api import create_api
from logosforge.db import Database
from logosforge.knowledge_graph import provenance as P
from logosforge.knowledge_graph.models import node_key


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

    assert API_CONTRACT_VERSION == "1.6.0"
    assert SERVER_VERSION == "1.5.0"


def test_project_map_exposes_traceable_graph_and_pretruncation_diagnostics():
    client, _, project, first, _, alice, lonely = _graph_project()

    response = client.get(f"/api/projects/{project.id}/knowledge-graph")
    assert response.status_code == 200
    body = response.json()

    assert body["project_id"] == project.id
    assert body["focus_key"] is None
    assert body["depth"] == 1
    assert body["include_inferred"] is True
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
    assert client.get(root).status_code == 200

    after = (
        len(db.get_all_scenes(project.id)),
        len(db.get_all_psyke_entries(project.id)),
        len(db.get_kg_edges(project.id)),
    )
    assert after == before


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
