"""Tests for the Semantic Narrative Graph redesign.

Covers: subtype-aware nodes, Act cluster nodes, edge typing
(participation/containment/psyke_relation/mention), the Layers panel,
the Skeleton button, and zoom-based culling.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from logosforge.db import Database
from logosforge.ui.focus_graph_view import (
    EDGE_CONTAINMENT,
    EDGE_MENTION,
    EDGE_PARTICIPATION,
    EDGE_PSYKE_RELATION,
    EDGE_STYLE,
    FocusGraphView,
    LAYER_KINDS,
    NODE_KIND_ACT,
    NODE_KIND_CHARACTER,
    NODE_KIND_LORE,
    NODE_KIND_OBJECT,
    NODE_KIND_OTHER,
    NODE_KIND_PLACE,
    NODE_KIND_SCENE,
    NODE_KIND_THEME,
    SKELETON_LAYERS,
    _ZOOM_HIDE_LABELS,
    _ZOOM_HIDE_MENTIONS,
    _ZOOM_HIDE_WEAK_EDGES,
    build_graph_data,
    default_skeleton_layers,
    filter_by_layers,
    node_kind,
)


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_project_with_psyke_types():
    db = Database()
    proj = db.create_project("SemanticTest")
    c = db.create_character(proj.id, "Alice")
    p = db.create_place(proj.id, "Castle")
    s1 = db.create_scene(
        proj.id, "Opening",
        content="Alice arrives.",
        act="Act I",
        character_ids=[c.id],
        place_ids=[p.id],
    )
    s2 = db.create_scene(
        proj.id, "Midpoint",
        content="The truth comes out.",
        act="Act II",
        character_ids=[c.id],
    )
    theme = db.create_psyke_entry(proj.id, "Justice", "theme")
    lore = db.create_psyke_entry(proj.id, "The Kingdom Law", "lore")
    obj = db.create_psyke_entry(proj.id, "Crown of Sorrows", "object")
    db.add_psyke_relation(theme.id, lore.id)
    return db, proj, c, p, s1, s2, theme, lore, obj


# -- subtype-aware nodes ----------------------------------------------------

def test_psyke_theme_gets_theme_subtype():
    db, proj, *_ = _make_project_with_psyke_types()
    data = build_graph_data(db, proj.id)
    theme_node = next(
        n for n in data.nodes.values()
        if n.name == "Justice"
    )
    assert theme_node.subtype == NODE_KIND_THEME
    assert node_kind(theme_node) == NODE_KIND_THEME


def test_psyke_lore_gets_lore_subtype():
    db, proj, *_ = _make_project_with_psyke_types()
    data = build_graph_data(db, proj.id)
    lore_node = next(n for n in data.nodes.values() if n.name == "The Kingdom Law")
    assert lore_node.subtype == NODE_KIND_LORE
    assert node_kind(lore_node) == NODE_KIND_LORE


def test_psyke_object_gets_object_subtype():
    db, proj, *_ = _make_project_with_psyke_types()
    data = build_graph_data(db, proj.id)
    obj_node = next(n for n in data.nodes.values() if n.name == "Crown of Sorrows")
    assert obj_node.subtype == NODE_KIND_OBJECT


def test_psyke_relation_edge_is_typed():
    db, proj, *_ = _make_project_with_psyke_types()
    data = build_graph_data(db, proj.id)
    psyke_edges = [e for e in data.edges if e.edge_type == EDGE_PSYKE_RELATION]
    assert len(psyke_edges) >= 1


# -- Act nodes ---------------------------------------------------------------

def test_act_nodes_created_from_distinct_acts():
    db, proj, *_ = _make_project_with_psyke_types()
    data = build_graph_data(db, proj.id)
    act_nodes = [n for n in data.nodes.values() if n.etype == "Act"]
    act_names = {n.name for n in act_nodes}
    assert "Act I" in act_names
    assert "Act II" in act_names
    assert len(act_nodes) == 2


def test_no_act_nodes_when_no_acts():
    db = Database()
    proj = db.create_project("NoActs")
    db.create_scene(proj.id, "S1", content="...")
    data = build_graph_data(db, proj.id)
    assert not any(n.etype == "Act" for n in data.nodes.values())


def test_containment_edges_connect_act_to_scene():
    db, proj, *_ = _make_project_with_psyke_types()
    data = build_graph_data(db, proj.id)
    cont_edges = [e for e in data.edges if e.edge_type == EDGE_CONTAINMENT]
    assert len(cont_edges) == 2
    for e in cont_edges:
        assert e.source_id.startswith("Act:")
        assert e.target_id.startswith("Scene:")


# -- Participation edges -----------------------------------------------------

def test_participation_edges_link_scene_to_character():
    db, proj, c, _p, s1, *_ = _make_project_with_psyke_types()
    data = build_graph_data(db, proj.id)
    part_edges = [
        e for e in data.edges
        if e.edge_type == EDGE_PARTICIPATION
        and e.source_id == f"Scene:{s1.id}"
        and e.target_id == f"Character:{c.id}"
    ]
    assert len(part_edges) == 1


def test_participation_edges_link_scene_to_place():
    db, proj, _c, p, s1, *_ = _make_project_with_psyke_types()
    data = build_graph_data(db, proj.id)
    part_edges = [
        e for e in data.edges
        if e.edge_type == EDGE_PARTICIPATION
        and e.target_id == f"Place:{p.id}"
    ]
    assert len(part_edges) == 1


# -- Layer mask --------------------------------------------------------------

def test_filter_by_layers_empty_returns_empty():
    db, proj, *_ = _make_project_with_psyke_types()
    data = build_graph_data(db, proj.id)
    assert filter_by_layers(data, set()) == set()


def test_filter_by_layers_only_themes():
    db, proj, *_ = _make_project_with_psyke_types()
    data = build_graph_data(db, proj.id)
    result = filter_by_layers(data, {NODE_KIND_THEME})
    for nid in result:
        assert node_kind(data.nodes[nid]) == NODE_KIND_THEME


def test_filter_by_layers_skeleton():
    db, proj, *_ = _make_project_with_psyke_types()
    data = build_graph_data(db, proj.id)
    skel = filter_by_layers(data, set(SKELETON_LAYERS))
    allowed = SKELETON_LAYERS
    for nid in skel:
        assert node_kind(data.nodes[nid]) in allowed


def test_skeleton_layers_constant():
    skel = default_skeleton_layers()
    assert NODE_KIND_CHARACTER in skel
    assert NODE_KIND_THEME in skel
    assert NODE_KIND_ACT in skel
    assert NODE_KIND_PLACE not in skel  # narrative skeleton excludes places


def test_layer_kinds_complete():
    """All semantic kinds appear in LAYER_KINDS so the panel can toggle them."""
    expected = {
        NODE_KIND_CHARACTER, NODE_KIND_PLACE, NODE_KIND_OBJECT,
        NODE_KIND_THEME, NODE_KIND_LORE, NODE_KIND_SCENE,
        NODE_KIND_ACT, NODE_KIND_OTHER,
    }
    assert expected <= set(LAYER_KINDS)


# -- View integration --------------------------------------------------------

def test_view_constructs_layer_panel():
    db, proj, *_ = _make_project_with_psyke_types()
    view = FocusGraphView(db, proj.id)
    # Layer toggles now live inside the compact Filters dropdown menu rather
    # than a permanent side panel, but the per-kind checkboxes still exist.
    assert hasattr(view, "_layer_checks")
    for kind in LAYER_KINDS:
        assert kind in view._layer_checks


def test_view_layer_toggle_filters_nodes():
    db, proj, *_ = _make_project_with_psyke_types()
    view = FocusGraphView(db, proj.id)
    initial = view.get_visible_count()
    # Uncheck Scenes — scene + containment-only nodes should disappear.
    view._on_layer_toggled(NODE_KIND_SCENE, False)
    no_scenes = view.get_visible_count()
    assert no_scenes <= initial
    for nid in view._node_items:
        assert node_kind(view._graph_data.nodes[nid]) != NODE_KIND_SCENE


def test_view_skeleton_button_activates_skeleton_set():
    db, proj, *_ = _make_project_with_psyke_types()
    view = FocusGraphView(db, proj.id)
    view._on_skeleton_toggled(True)
    assert view._active_layers == set(SKELETON_LAYERS)
    for cb_kind, cb in view._layer_checks.items():
        assert cb.isChecked() == (cb_kind in SKELETON_LAYERS)


def test_view_skeleton_button_off_restores_all_layers():
    db, proj, *_ = _make_project_with_psyke_types()
    view = FocusGraphView(db, proj.id)
    view._on_skeleton_toggled(True)
    view._on_skeleton_toggled(False)
    assert view._active_layers == set(LAYER_KINDS)


def test_view_manual_layer_change_unsets_skeleton_button():
    db, proj, *_ = _make_project_with_psyke_types()
    view = FocusGraphView(db, proj.id)
    # Drive the button (fires the toggled signal and the connected slot).
    view._skeleton_btn.setChecked(True)
    assert view._skeleton_btn.isChecked()
    # Now flip a layer back on that wasn't in the skeleton set — the button
    # should clear because the active layers no longer match the skeleton.
    view._on_layer_toggled(NODE_KIND_PLACE, True)
    assert not view._skeleton_btn.isChecked()


# -- Edge styling ------------------------------------------------------------

def test_each_edge_type_has_distinct_style():
    seen_colors = set()
    for etype in (EDGE_PARTICIPATION, EDGE_CONTAINMENT, EDGE_PSYKE_RELATION, EDGE_MENTION):
        style = EDGE_STYLE[etype]
        seen_colors.add(style["color"])
    assert len(seen_colors) == 4, "Edge types must have distinct colors"


def test_mention_edges_use_dashed_style():
    assert EDGE_STYLE[EDGE_MENTION]["dash"] == "dash"


def test_containment_edges_are_thicker_than_mentions():
    assert EDGE_STYLE[EDGE_CONTAINMENT]["width"] > EDGE_STYLE[EDGE_MENTION]["width"]


# -- Zoom culling ------------------------------------------------------------

def test_zoom_culling_hides_labels_when_zoomed_out():
    db, proj, *_ = _make_project_with_psyke_types()
    view = FocusGraphView(db, proj.id)
    view._on_zoom(_ZOOM_HIDE_LABELS - 0.1)
    assert any(not lbl.isVisible() for lbl in view._label_items.values())


def test_zoom_culling_shows_labels_when_zoomed_in():
    db, proj, *_ = _make_project_with_psyke_types()
    view = FocusGraphView(db, proj.id)
    # Density mode gates which labels show; set "all" to isolate zoom culling.
    view._set_label_mode("all")
    view._on_zoom(1.0)
    assert all(lbl.isVisible() for lbl in view._label_items.values())


def test_zoom_culling_hides_mention_edges_at_low_zoom():
    db, proj, c, p, s1, *_ = _make_project_with_psyke_types()
    # Add a scene that mentions [[Alice]] to generate a mention edge.
    db.create_scene(proj.id, "Mentions", synopsis="[[Alice]] returns.")
    view = FocusGraphView(db, proj.id)
    view._on_zoom(_ZOOM_HIDE_MENTIONS - 0.1)
    mention_items = [
        e for e in view._edge_items if e.data(0) == EDGE_MENTION
    ]
    assert all(not e.isVisible() for e in mention_items)


def test_zoom_culling_keeps_containment_edges_at_lowest_zoom():
    db, proj, *_ = _make_project_with_psyke_types()
    view = FocusGraphView(db, proj.id)
    view._on_zoom(_ZOOM_HIDE_WEAK_EDGES - 0.1)
    cont_items = [
        e for e in view._edge_items if e.data(0) == EDGE_CONTAINMENT
    ]
    if cont_items:
        assert all(e.isVisible() for e in cont_items)


# -- node_kind resolver ------------------------------------------------------

def test_node_kind_uses_subtype_when_set():
    from logosforge.ui.focus_graph_view import GraphNode
    n = GraphNode("PSYKE:1", "PSYKE", 1, "X", subtype=NODE_KIND_THEME)
    assert node_kind(n) == NODE_KIND_THEME


def test_node_kind_falls_back_to_etype():
    from logosforge.ui.focus_graph_view import GraphNode
    n = GraphNode("Character:1", "Character", 1, "Alice")
    assert node_kind(n) == NODE_KIND_CHARACTER


def test_node_kind_psyke_without_subtype_is_other():
    from logosforge.ui.focus_graph_view import GraphNode
    n = GraphNode("PSYKE:1", "PSYKE", 1, "X")
    assert node_kind(n) == NODE_KIND_OTHER
