"""Tests for Narrative Modes in the Graph view."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from logosforge.db import Database
from logosforge.ui.focus_graph_view import (
    EDGE_CONTAINMENT,
    EDGE_MENTION,
    EDGE_PARTICIPATION,
    EDGE_PSYKE_RELATION,
    EDGE_QUANTUM,
    FocusGraphView,
    MODE_ALL,
    MODE_MEANING,
    MODE_ORDER,
    MODE_PROFILES,
    MODE_PSYKE,
    MODE_QUANTUM,
    MODE_RELATIONSHIP,
    MODE_STRUCTURE,
    MODE_THEME,
    NODE_KIND_ACT,
    NODE_KIND_BRANCH,
    NODE_KIND_CHARACTER,
    NODE_KIND_LORE,
    NODE_KIND_OBJECT,
    NODE_KIND_SCENE,
    NODE_KIND_THEME,
    NODE_KIND_WAVEFUNCTION,
    get_mode_profile,
    node_kind,
)


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_full_project():
    db = Database()
    proj = db.create_project("ModesTest")
    c = db.create_character(proj.id, "Alice")
    p = db.create_place(proj.id, "Castle")
    s1 = db.create_scene(
        proj.id, "Opening", content="The story begins.", act="Act I",
        character_ids=[c.id], place_ids=[p.id],
    )
    s2 = db.create_scene(
        proj.id, "Midpoint", content="The truth.", act="Act II",
        character_ids=[c.id],
    )
    theme = db.create_psyke_entry(proj.id, "Justice", "theme")
    lore = db.create_psyke_entry(proj.id, "Kingdom Law", "lore")
    obj = db.create_psyke_entry(proj.id, "Crown", "object")
    db.add_psyke_relation(theme.id, lore.id)
    return db, proj, c, p, s1, s2, theme, lore, obj


# -- Mode profile registry ---------------------------------------------------

def test_all_modes_have_profiles():
    expected = {MODE_ALL, MODE_RELATIONSHIP, MODE_THEME, MODE_STRUCTURE,
                MODE_QUANTUM, MODE_PSYKE, MODE_MEANING}
    assert expected <= set(MODE_PROFILES.keys())


def test_mode_order_matches_registry():
    from logosforge.ui.focus_graph_view import (
        GRAPHIC_NOVEL_MODE_ORDER,
        SCREENPLAY_MODE_ORDER,
        SERIES_MODE_ORDER,
        STAGE_SCRIPT_MODE_ORDER,
    )
    assert (
        set(MODE_ORDER)
        | set(SCREENPLAY_MODE_ORDER)
        | set(GRAPHIC_NOVEL_MODE_ORDER)
        | set(STAGE_SCRIPT_MODE_ORDER)
        | set(SERIES_MODE_ORDER)
    ) == set(MODE_PROFILES.keys())


def test_relationship_profile_characters_only():
    p = get_mode_profile(MODE_RELATIONSHIP)
    assert p.visible_kinds == frozenset({NODE_KIND_CHARACTER})


def test_structure_profile_acts_and_scenes():
    p = get_mode_profile(MODE_STRUCTURE)
    assert p.visible_kinds == frozenset({NODE_KIND_ACT, NODE_KIND_SCENE})
    assert p.layout == "linear_timeline"
    assert p.visible_edge_types == frozenset({EDGE_CONTAINMENT})


def test_theme_profile_theme_centered_layout():
    p = get_mode_profile(MODE_THEME)
    assert NODE_KIND_THEME in p.visible_kinds
    assert p.layout == "theme_centered"
    assert p.prominence.get(NODE_KIND_THEME, 1.0) > 1.0


def test_psyke_profile_has_no_scenes():
    p = get_mode_profile(MODE_PSYKE)
    assert NODE_KIND_SCENE not in p.visible_kinds
    assert NODE_KIND_THEME in p.visible_kinds
    assert NODE_KIND_LORE in p.visible_kinds
    assert NODE_KIND_OBJECT in p.visible_kinds
    assert p.visible_edge_types == frozenset({EDGE_PSYKE_RELATION})


def test_meaning_profile_enables_overlay():
    p = get_mode_profile(MODE_MEANING)
    assert p.meaning_overlay is True


def test_quantum_profile_uses_quantum_data():
    p = get_mode_profile(MODE_QUANTUM)
    assert p.uses_quantum is True
    assert p.layout == "quantum_tree"
    assert p.visible_kinds == frozenset({NODE_KIND_WAVEFUNCTION, NODE_KIND_BRANCH})


def test_unknown_mode_falls_back_to_all():
    p = get_mode_profile("nonexistent")
    assert p.name == MODE_ALL


# -- View construction -------------------------------------------------------

def test_view_constructs_mode_buttons():
    db, proj, *_ = _make_full_project()
    view = FocusGraphView(db, proj.id)
    for mode in MODE_ORDER:
        assert mode in view._mode_buttons


def test_view_default_mode_is_structure():
    db, proj, *_ = _make_full_project()
    view = FocusGraphView(db, proj.id)
    assert view.get_mode() == MODE_STRUCTURE
    assert view._mode_buttons[MODE_STRUCTURE].isChecked()


# -- Mode switching changes visible nodes ------------------------------------

def test_relationship_mode_shows_only_characters():
    db, proj, c, *_ = _make_full_project()
    view = FocusGraphView(db, proj.id)
    view.set_mode(MODE_RELATIONSHIP)
    assert view.get_mode() == MODE_RELATIONSHIP
    for nid in view._node_items:
        assert node_kind(view._graph_data.nodes[nid]) == NODE_KIND_CHARACTER


def test_structure_mode_shows_only_acts_and_scenes():
    db, proj, *_ = _make_full_project()
    view = FocusGraphView(db, proj.id)
    view.set_mode(MODE_STRUCTURE)
    visible_kinds = {
        node_kind(view._graph_data.nodes[nid])
        for nid in view._node_items
    }
    assert visible_kinds <= {NODE_KIND_ACT, NODE_KIND_SCENE}
    assert NODE_KIND_ACT in visible_kinds or NODE_KIND_SCENE in visible_kinds


def test_theme_mode_shows_themes():
    db, proj, *_ = _make_full_project()
    view = FocusGraphView(db, proj.id)
    view.set_mode(MODE_THEME)
    visible_kinds = {
        node_kind(view._graph_data.nodes[nid])
        for nid in view._node_items
    }
    assert NODE_KIND_THEME in visible_kinds
    assert visible_kinds <= {NODE_KIND_THEME, NODE_KIND_CHARACTER, NODE_KIND_SCENE}


def test_psyke_mode_hides_scenes_and_characters():
    db, proj, *_ = _make_full_project()
    view = FocusGraphView(db, proj.id)
    view.set_mode(MODE_PSYKE)
    for nid in view._node_items:
        kind = node_kind(view._graph_data.nodes[nid])
        assert kind not in (NODE_KIND_SCENE, NODE_KIND_ACT)
        assert kind != NODE_KIND_CHARACTER or "PSYKE:" in nid


def test_meaning_mode_activates_meaning_overlay():
    db, proj, *_ = _make_full_project()
    view = FocusGraphView(db, proj.id)
    view.set_mode(MODE_MEANING)
    assert view._meaning_enabled is True


def test_all_mode_restores_full_layers():
    db, proj, *_ = _make_full_project()
    view = FocusGraphView(db, proj.id)
    view.set_mode(MODE_RELATIONSHIP)
    view.set_mode(MODE_ALL)
    from logosforge.ui.focus_graph_view import LAYER_KINDS
    assert view._active_layers == set(LAYER_KINDS)


# -- Edge filtering per mode -------------------------------------------------

def test_structure_mode_draws_only_containment_edges():
    db, proj, *_ = _make_full_project()
    view = FocusGraphView(db, proj.id)
    view.set_mode(MODE_STRUCTURE)
    for edge_item in view._edge_items:
        assert edge_item.data(0) == EDGE_CONTAINMENT


def test_psyke_mode_draws_only_psyke_edges():
    db, proj, *_ = _make_full_project()
    view = FocusGraphView(db, proj.id)
    view.set_mode(MODE_PSYKE)
    for edge_item in view._edge_items:
        assert edge_item.data(0) == EDGE_PSYKE_RELATION


def test_relationship_mode_keeps_participation_edges():
    """Participation edges connect characters via shared scenes — but in
    Relationship mode the scenes themselves are hidden, so the participation
    edges have no visible endpoints and naturally drop out. Only direct
    character↔character psyke_relation / mention edges may remain."""
    db, proj, *_ = _make_full_project()
    view = FocusGraphView(db, proj.id)
    view.set_mode(MODE_RELATIONSHIP)
    for edge_item in view._edge_items:
        assert edge_item.data(0) in (EDGE_PARTICIPATION, EDGE_PSYKE_RELATION, EDGE_MENTION)


# -- Layout per mode ---------------------------------------------------------

def test_structure_layout_arranges_scenes_along_x_axis():
    db, proj, *_ = _make_full_project()
    view = FocusGraphView(db, proj.id)
    view.set_mode(MODE_STRUCTURE)
    visible = view._compute_visible_nodes()
    positions = view._layout_nodes(visible)
    scenes = [nid for nid in positions if nid.startswith("Scene:")]
    if len(scenes) >= 2:
        ys = {positions[s][1] for s in scenes}
        # All scenes share the same Y band in the linear timeline.
        assert len(ys) == 1


def test_structure_layout_puts_acts_above_scenes():
    db, proj, *_ = _make_full_project()
    view = FocusGraphView(db, proj.id)
    view.set_mode(MODE_STRUCTURE)
    visible = view._compute_visible_nodes()
    positions = view._layout_nodes(visible)
    acts = [nid for nid in positions if nid.startswith("Act:")]
    scenes = [nid for nid in positions if nid.startswith("Scene:")]
    if acts and scenes:
        avg_act_y = sum(positions[a][1] for a in acts) / len(acts)
        avg_scene_y = sum(positions[s][1] for s in scenes) / len(scenes)
        # In Qt, +Y goes down, so the act band has the smaller (more-negative) Y.
        assert avg_act_y < avg_scene_y


def test_theme_layout_themes_at_inner_circle():
    db, proj, *_ = _make_full_project()
    view = FocusGraphView(db, proj.id)
    view.set_mode(MODE_THEME)
    visible = view._compute_visible_nodes()
    positions = view._layout_nodes(visible)
    theme_nodes = [
        nid for nid in positions
        if node_kind(view._graph_data.nodes.get(nid)) == NODE_KIND_THEME
    ]
    other_nodes = [
        nid for nid in positions if nid not in theme_nodes
    ]
    if theme_nodes and other_nodes:
        import math
        avg_theme_r = sum(
            math.hypot(*positions[t]) for t in theme_nodes
        ) / len(theme_nodes)
        avg_other_r = sum(
            math.hypot(*positions[n]) for n in other_nodes
        ) / len(other_nodes)
        # Themes are closer to the centre than satellites.
        assert avg_theme_r <= avg_other_r + 1.0


# -- Layers panel is disabled outside All mode -------------------------------

def test_layers_panel_disabled_in_specific_modes():
    db, proj, *_ = _make_full_project()
    view = FocusGraphView(db, proj.id)
    view.set_mode(MODE_THEME)
    for cb in view._layer_checks.values():
        assert not cb.isEnabled()


def test_layers_panel_re_enabled_in_all_mode():
    db, proj, *_ = _make_full_project()
    view = FocusGraphView(db, proj.id)
    view.set_mode(MODE_THEME)
    view.set_mode(MODE_ALL)
    for cb in view._layer_checks.values():
        assert cb.isEnabled()


# -- Quantum mode ------------------------------------------------------------

def test_quantum_mode_with_no_wavefunctions_shows_empty_state():
    db, proj, *_ = _make_full_project()
    view = FocusGraphView(db, proj.id)
    view.set_mode(MODE_QUANTUM)
    # No wavefunctions exist → no nodes drawn.
    assert len(view._node_items) == 0


def test_quantum_mode_loads_active_wavefunctions():
    db, proj, *_ = _make_full_project()
    # Inject a wavefunction into the in-memory quantum state.
    from logosforge.quantum_outliner import get_state
    from logosforge.quantum_outliner.state import Branch, Wavefunction
    state = get_state(proj.id)
    wf = Wavefunction(id="wf-test", anchor="opening")
    wf.branches.append(Branch.new("Branch A", "desc"))
    wf.branches.append(Branch.new("Branch B", "desc"))
    state.add(wf)

    view = FocusGraphView(db, proj.id)
    view.set_mode(MODE_QUANTUM)
    assert any(nid.startswith("Wavefunction:") for nid in view._node_items)
    assert sum(1 for nid in view._node_items if nid.startswith("Branch:")) == 2
    # Edges between wavefunction and its branches.
    for edge_item in view._edge_items:
        assert edge_item.data(0) == EDGE_QUANTUM


def test_quantum_mode_isolation_from_regular_graph():
    """Switching to Quantum mode must not bleed regular project nodes in."""
    db, proj, c, *_ = _make_full_project()
    from logosforge.quantum_outliner import get_state
    from logosforge.quantum_outliner.state import Branch, Wavefunction
    state = get_state(proj.id)
    wf = Wavefunction(id="wf-iso", anchor="opening")
    wf.branches.append(Branch.new("Branch X", "desc"))
    state.add(wf)

    view = FocusGraphView(db, proj.id)
    view.set_mode(MODE_QUANTUM)
    # Regular character node must not be visible in Quantum mode.
    assert f"Character:{c.id}" not in view._node_items


# -- Prominence multiplier ---------------------------------------------------

def test_theme_mode_has_theme_prominence_above_one():
    p = get_mode_profile(MODE_THEME)
    assert p.prominence[NODE_KIND_THEME] > 1.0


def test_structure_mode_has_act_prominence_above_one():
    p = get_mode_profile(MODE_STRUCTURE)
    assert p.prominence[NODE_KIND_ACT] > 1.0


# -- Skeleton button interaction --------------------------------------------

def test_skeleton_button_disabled_in_specific_modes():
    db, proj, *_ = _make_full_project()
    view = FocusGraphView(db, proj.id)
    view.set_mode(MODE_RELATIONSHIP)
    assert not view._skeleton_btn.isEnabled()


def test_skeleton_button_re_enabled_in_all_mode():
    db, proj, *_ = _make_full_project()
    view = FocusGraphView(db, proj.id)
    view.set_mode(MODE_RELATIONSHIP)
    view.set_mode(MODE_ALL)
    assert view._skeleton_btn.isEnabled()
