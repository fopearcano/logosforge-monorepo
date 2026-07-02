"""Format-intelligence phase-2 writers: each new authoring path must make its
format graph enricher emit the edge types it was previously starved of. Every test
authors via the API (the path the Studio uses) then runs build_graph_data + the
matching enricher and asserts the new edge types appear."""

from collections import Counter

import pytest
from fastapi.testclient import TestClient

from logosforge.api import ApiConfig, create_api
from logosforge.db import Database
from logosforge import graph_enrichers
from logosforge.graph_data import build_graph_data


@pytest.fixture
def client_db():
    db = Database()
    app = create_api(db=db, config=ApiConfig(mode="desktop"))
    return TestClient(app), db


def _edges(db, pid, enrich):
    data = build_graph_data(db, pid)
    enrich(db, pid, data)
    return Counter(e.edge_type for e in data.edges)


def test_screenplay_knowledge_and_continuity(client_db):
    c, db = client_db
    p = db.create_project("SP", narrative_engine="screenplay")
    mara = db.create_character(p.id, "MARA")
    s1 = db.create_scene(p.id, "A", content="x", character_ids=[mara.id])
    s2 = db.create_scene(p.id, "B", content="x", character_ids=[mara.id])
    for s in (s1, s2):
        assert c.patch(f"/api/projects/{p.id}/scenes/{s.id}", json={"who_knows_what": "MARA knows"}).status_code == 200
        assert c.post(f"/api/projects/{p.id}/scenes/{s.id}/continuity", json={"target": "watch", "kind": "object", "value": "ticking"}).status_code == 200
    e = _edges(db, p.id, graph_enrichers.enrich_screenplay_edges)
    assert e["knowledge"] >= 1 and e["continuity"] >= 1
    assert c.post(f"/api/projects/{p.id}/scenes/99999/continuity", json={"target": "x"}).status_code == 404


def test_series_plotline_and_memory(client_db):
    c, db = client_db
    p = db.create_project("SR", narrative_engine="series")
    se = c.post(f"/api/projects/{p.id}/series/seasons", json={"title": "S1"}).json()
    e1 = c.post(f"/api/projects/{p.id}/series/seasons/{se['id']}/episodes", json={"title": "Pilot"}).json()
    e2 = c.post(f"/api/projects/{p.id}/series/seasons/{se['id']}/episodes", json={"title": "Finale"}).json()
    hero = db.create_psyke_entry(p.id, "Mara", entry_type="character")
    assert c.post(f"/api/projects/{p.id}/series/episodes/{e1['id']}/plotlines", json={"type": "A", "title": "Hunt"}).status_code == 200
    r = c.put(f"/api/projects/{p.id}/psyke/{hero.id}/series-memory",
              json={"continuity_flags": "break", "current_status_by_episode": {str(e1["id"]): "alive", str(e2["id"]): "dead"}})
    assert r.status_code == 200 and r.json()["current_status_by_episode"][str(e1["id"])] == "alive"
    e = _edges(db, p.id, graph_enrichers.enrich_series_graph)
    assert e["sr_echoes"] >= 1 and e["sr_contradicts"] >= 1 and e["sr_contains"] >= 3  # +episode->plotline


def test_gn_sync_from_scenes(client_db):
    c, db = client_db
    p = db.create_project("GN", narrative_engine="graphic_novel")
    body = "PAGE 1: Vault\nPANEL 1\nVisual: Rain on the clock.\nPANEL 2\nVisual: The clock in the rain."
    db.create_scene(p.id, "S1", content=body)
    db.create_scene(p.id, "S2", content="PAGE 1: Roof\nPANEL 1\nVisual: Rain and a clock tower.")
    r = c.post(f"/api/projects/{p.id}/gn/sync-from-scenes").json()
    assert r["pages"] == 2 and r["panels"] == 3 and not r["skipped"]
    e = _edges(db, p.id, graph_enrichers.enrich_graphic_novel_graph)
    assert e["gn_contains"] >= 3 and e["gn_motif"] >= 1
    assert c.post(f"/api/projects/{p.id}/gn/sync-from-scenes").json()["skipped"]  # idempotent

    # GN object-continuity: an item appearing on >=2 pages forms object<->page edges
    # (the one GN edge type with no prior writer).
    pages = c.get(f"/api/projects/{p.id}/gn/pages").json()
    item = c.post(f"/api/projects/{p.id}/gn/continuity-items", json={"name": "Watch", "item_type": "prop"}).json()
    for pg in pages:
        c.post(f"/api/projects/{p.id}/gn/continuity-items/{item['id']}/appearances", json={"page_id": pg["id"]})
    assert _edges(db, p.id, graph_enrichers.enrich_graphic_novel_graph)["gn_object_continuity"] >= 2


def test_stage_sync_from_scenes(client_db):
    c, db = client_db
    p = db.create_project("ST", narrative_engine="stage_script")
    mara = db.create_character(p.id, "Mara")
    eli = db.create_character(p.id, "Eli")
    body = "(Lights up.)\nMARA enters from the wings.\nA bell rings offstage.\nELI enters.\nExit MARA."
    db.create_scene(p.id, "Act I", content=body, character_ids=[mara.id, eli.id])
    r = c.post(f"/api/projects/{p.id}/stage/sync-from-scenes").json()
    assert r["cues"] >= 1 and r["entrances"] >= 2 and r["offstage"] == 1
    e = _edges(db, p.id, graph_enrichers.enrich_stage_script_graph)
    assert e["ss_cue"] >= 1 and e["ss_entrance_exit"] >= 2 and e["ss_offstage"] >= 1


def test_stage_parser_rejects_prose_and_keeps_cues():
    """The stage parser must only fire on stage-direction-shaped lines: prose that
    merely contains 'enter'/'exit' yields NO entrance, and a cue line containing the
    verb is still classified as a cue (not stolen)."""
    from logosforge import stage_structure_sync as sss
    db = Database()
    p = db.create_project("S", narrative_engine="stage_script")
    mara = db.create_character(p.id, "Mara")
    eli = db.create_character(p.id, "Eli")
    body = "\n".join([
        "Mara could not enter the contest without Eli.",      # prose -> no entrance
        "SOUND: a door slams as Mara exits the light booth",  # cue, not entrance
        "(Lights dim near the exit sign.)",                   # cue, not dropped
        "MARA enters from the wings.",                        # 1 entrance
        "Exit MARA.",                                         # 1 exit
    ])
    db.create_scene(p.id, "A", content=body, character_ids=[mara.id, eli.id])
    r = sss.sync_stage_structure_from_scenes(db, p.id)
    assert r["cues"] == 2          # SOUND: + (Lights ...), neither stolen
    assert r["entrances"] == 2     # "MARA enters" + "Exit MARA." — NO phantom from prose
