"""Tests for Stage Script graph modes."""

import pytest

from logosforge.db import Database
from logosforge.ui.focus_graph_view import (
    EDGE_SS_BLOCKING,
    EDGE_SS_CUE,
    EDGE_SS_ENTRANCE_EXIT,
    EDGE_SS_OFFSTAGE,
    EDGE_SS_PRESSURE,
    EDGE_SS_SUBTEXT,
    EDGE_SS_USES_PROP,
    FocusGraphView,
    MODE_ALL,
    MODE_PROFILES,
    MODE_SS_BLOCKING,
    MODE_SS_ENTRANCE_EXIT,
    MODE_SS_OFFSTAGE,
    MODE_SS_PRESSURE,
    MODE_SS_PROP,
    MODE_SS_SUBTEXT,
    NODE_KIND_CHARACTER,
    NODE_KIND_CUE,
    NODE_KIND_OBJECT,
    NODE_KIND_OFFSTAGE,
    NODE_KIND_PLACE,
    NODE_KIND_SCENE,
    STAGE_SCRIPT_MODE_ORDER,
    build_graph_data,
    enrich_stage_script_graph,
    node_kind,
    ss_filter_node_ids,
)


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    yield
    settings._instance = None


def _play(db):
    return db.create_project(
        "Play", narrative_engine="stage_script",
        default_writing_format="stage_script",
    )


def _build(db, project_id):
    h = db.create_character(project_id, "Hamlet")
    c = db.create_character(project_id, "Claudius")
    g = db.create_character(project_id, "Gertrude")
    hp = db.create_psyke_entry(project_id, "Hamlet", entry_type="character")
    cp = db.create_psyke_entry(project_id, "Claudius", entry_type="character")
    gp = db.create_psyke_entry(project_id, "Gertrude", entry_type="character")
    skull = db.create_psyke_entry(project_id, "Skull", entry_type="object")
    place = db.create_place(project_id, "Throne Room")
    # pressure (Hamlet→Claudius) and subtext (Hamlet↔Gertrude) on distinct pairs
    db.add_psyke_relation(hp.id, cp.id, relation_type="confronts")
    db.add_psyke_relation(hp.id, gp.id, relation_type="avoids")
    s = db.create_scene(
        project_id, "Closet", act="Act 3",
        character_ids=[h.id, g.id], place_ids=[place.id],
        offstage_events="Polonius hides",
    )
    db.create_stage_entrance_exit(s.id, character_id=h.id, type="entrance")
    db.create_stage_business(s.id, prop_psyke_entry_id=skull.id,
                             character_id=h.id, stage_action="draws")
    db.create_stage_cue(s.id, cue_type="light", cue_text="dim")
    return h, c, g, skull, place, s


def _enriched(db, project_id):
    data = build_graph_data(db, project_id)
    enrich_stage_script_graph(db, project_id, data)
    return data


# =========================================================================
# 1. Graph modes (§1)
# =========================================================================

def test_stage_modes_registered():
    for mode in STAGE_SCRIPT_MODE_ORDER:
        assert mode in MODE_PROFILES


def test_pressure_mode_profile():
    p = MODE_PROFILES[MODE_SS_PRESSURE]
    assert NODE_KIND_CHARACTER in p.visible_kinds
    assert EDGE_SS_PRESSURE in p.visible_edge_types


def test_entrance_exit_mode_profile():
    p = MODE_PROFILES[MODE_SS_ENTRANCE_EXIT]
    assert {NODE_KIND_SCENE, NODE_KIND_CHARACTER} <= p.visible_kinds
    assert EDGE_SS_ENTRANCE_EXIT in p.visible_edge_types


def test_prop_mode_profile():
    p = MODE_PROFILES[MODE_SS_PROP]
    assert NODE_KIND_OBJECT in p.visible_kinds
    assert EDGE_SS_USES_PROP in p.visible_edge_types


def test_blocking_mode_profile():
    p = MODE_PROFILES[MODE_SS_BLOCKING]
    assert NODE_KIND_PLACE in p.visible_kinds
    assert EDGE_SS_BLOCKING in p.visible_edge_types


def test_subtext_mode_profile():
    assert EDGE_SS_SUBTEXT in MODE_PROFILES[MODE_SS_SUBTEXT].visible_edge_types


def test_offstage_mode_profile():
    p = MODE_PROFILES[MODE_SS_OFFSTAGE]
    assert NODE_KIND_OFFSTAGE in p.visible_kinds
    assert EDGE_SS_OFFSTAGE in p.visible_edge_types


def test_all_stage_modes_have_descriptions():
    for mode in STAGE_SCRIPT_MODE_ORDER:
        assert MODE_PROFILES[mode].description


# =========================================================================
# 2. Graph data mapping (§3)
# =========================================================================

def test_enrich_creates_edges():
    db = Database()
    p = _play(db)
    _build(db, p.id)
    data = _enriched(db, p.id)
    et = {e.edge_type for e in data.edges}
    assert EDGE_SS_PRESSURE in et
    assert EDGE_SS_SUBTEXT in et
    assert EDGE_SS_ENTRANCE_EXIT in et
    assert EDGE_SS_USES_PROP in et
    assert EDGE_SS_BLOCKING in et
    assert EDGE_SS_CUE in et
    assert EDGE_SS_OFFSTAGE in et


def test_enrich_creates_cue_and_offstage_nodes():
    db = Database()
    p = _play(db)
    _build(db, p.id)
    data = _enriched(db, p.id)
    kinds = {node_kind(n) for n in data.nodes.values()}
    assert NODE_KIND_CUE in kinds
    assert NODE_KIND_OFFSTAGE in kinds


def test_enrich_noop_without_scenes():
    db = Database()
    p = _play(db)
    data = build_graph_data(db, p.id)
    before = len(data.nodes)
    enrich_stage_script_graph(db, p.id, data)
    assert len(data.nodes) == before


# =========================================================================
# 3. Filters (§2)
# =========================================================================

def test_filter_props():
    db = Database()
    p = _play(db)
    _build(db, p.id)
    data = _enriched(db, p.id)
    ids = ss_filter_node_ids(data, "props")
    assert all(node_kind(data.nodes[i]) == NODE_KIND_OBJECT for i in ids)
    assert ids


def test_filter_cue_relations():
    db = Database()
    p = _play(db)
    _build(db, p.id)
    data = _enriched(db, p.id)
    ids = ss_filter_node_ids(data, "cue_relations")
    kinds = {node_kind(data.nodes[i]) for i in ids}
    assert kinds <= {NODE_KIND_CUE, NODE_KIND_SCENE}
    assert any(node_kind(data.nodes[i]) == NODE_KIND_CUE for i in ids)


def test_filter_offstage_events():
    db = Database()
    p = _play(db)
    _build(db, p.id)
    data = _enriched(db, p.id)
    ids = ss_filter_node_ids(data, "offstage_events")
    kinds = {node_kind(data.nodes[i]) for i in ids}
    assert kinds <= {NODE_KIND_OFFSTAGE, NODE_KIND_SCENE}


def test_filter_characters():
    db = Database()
    p = _play(db)
    _build(db, p.id)
    data = _enriched(db, p.id)
    ids = ss_filter_node_ids(data, "characters_on_stage")
    assert all(node_kind(data.nodes[i]) == NODE_KIND_CHARACTER for i in ids)


# =========================================================================
# 4. View mode switching + no hairball default (§4, §5)
# =========================================================================

def test_view_detects_stage_mode():
    db = Database()
    p = _play(db)
    view = FocusGraphView(db, p.id)
    assert view._stage_script_mode is True
    for mode in STAGE_SCRIPT_MODE_ORDER:
        assert mode in view._mode_buttons


def test_novel_view_no_stage_buttons():
    db = Database()
    p = db.create_project("Novel")
    view = FocusGraphView(db, p.id)
    assert view._stage_script_mode is False
    for mode in STAGE_SCRIPT_MODE_ORDER:
        assert mode not in view._mode_buttons


def test_switch_modes():
    db = Database()
    p = _play(db)
    _build(db, p.id)
    view = FocusGraphView(db, p.id)
    for mode in STAGE_SCRIPT_MODE_ORDER:
        view.set_mode(mode)
        assert view.get_mode() == mode
    view.set_mode(MODE_ALL)
    assert view.get_mode() == MODE_ALL


def test_blocking_mode_shows_scenes_and_places_only():
    db = Database()
    p = _play(db)
    _build(db, p.id)
    view = FocusGraphView(db, p.id)
    view.set_mode(MODE_SS_BLOCKING)
    assert view._active_layers == {NODE_KIND_SCENE, NODE_KIND_PLACE}
    for nid in view._node_items:
        assert node_kind(view._graph_data.nodes[nid]) in {
            NODE_KIND_SCENE, NODE_KIND_PLACE,
        }


def test_entrance_exit_mode_no_hairball():
    """Entrance/exit mode shows only scenes + characters, not the whole
    graph (props/cues/offstage/places excluded)."""
    db = Database()
    p = _play(db)
    _build(db, p.id)
    view = FocusGraphView(db, p.id)
    view.set_mode(MODE_SS_ENTRANCE_EXIT)
    for nid in view._node_items:
        assert node_kind(view._graph_data.nodes[nid]) in {
            NODE_KIND_SCENE, NODE_KIND_CHARACTER,
        }


def test_prop_mode_includes_object():
    db = Database()
    p = _play(db)
    _build(db, p.id)
    view = FocusGraphView(db, p.id)
    view.set_mode(MODE_SS_PROP)
    kinds = {node_kind(view._graph_data.nodes[nid]) for nid in view._node_items}
    assert NODE_KIND_OBJECT in kinds
