"""Tests for temporal narrative flow in the Graph view."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from logosforge.db import Database
from logosforge.graph_flow import (
    BAND_BEGINNING,
    BAND_ENDING,
    BAND_MIDDLE,
    FLOW_ACTS,
    FLOW_ARC,
    FLOW_CAUSAL,
    FLOW_TIMELINE,
    FLOW_TYPES,
    FlowSegment,
    band_color,
    compute_flow,
    position_band,
    scene_bands,
)
from logosforge.ui.focus_graph_view import FocusGraphView


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_five_scene_project():
    db = Database()
    proj = db.create_project("Flow")
    c = db.create_character(proj.id, "Hero")
    s1 = db.create_scene(proj.id, "Opening", act="Act I", character_ids=[c.id])
    s2 = db.create_scene(proj.id, "Inciting", act="Act I", character_ids=[c.id])
    s3 = db.create_scene(proj.id, "Midpoint", act="Act II", character_ids=[c.id])
    s4 = db.create_scene(proj.id, "Crisis", act="Act III", character_ids=[c.id])
    s5 = db.create_scene(proj.id, "Climax", act="Act III", character_ids=[c.id])
    return db, proj, c, s1, s2, s3, s4, s5


# -- position_band -----------------------------------------------------------

def test_position_band_first_third_is_beginning():
    assert position_band(0, 9) == BAND_BEGINNING


def test_position_band_middle_third_is_middle():
    assert position_band(4, 9) == BAND_MIDDLE


def test_position_band_last_third_is_ending():
    assert position_band(8, 9) == BAND_ENDING


def test_position_band_single_scene():
    assert position_band(0, 1) == BAND_BEGINNING


def test_position_band_handles_zero_total():
    assert position_band(0, 0) == BAND_MIDDLE


# -- band_color --------------------------------------------------------------

def test_band_color_each_band_is_distinct():
    colors = {band_color(b) for b in (BAND_BEGINNING, BAND_MIDDLE, BAND_ENDING)}
    assert len(colors) == 3


def test_band_color_unknown_band_returns_neutral():
    assert band_color("nope") == "#9e9e9e"


# -- compute_flow timeline ---------------------------------------------------

def test_timeline_flow_has_n_minus_one_segments():
    db, proj, *_ = _make_five_scene_project()
    segments = compute_flow(db, proj.id, FLOW_TIMELINE)
    assert len(segments) == 4  # 5 scenes -> 4 transitions


def test_timeline_flow_connects_consecutive_scenes():
    db, proj, _c, s1, s2, s3, s4, s5 = _make_five_scene_project()
    segments = compute_flow(db, proj.id, FLOW_TIMELINE)
    assert segments[0].from_scene_id == s1.id
    assert segments[0].to_scene_id == s2.id
    assert segments[-1].from_scene_id == s4.id
    assert segments[-1].to_scene_id == s5.id


def test_timeline_flow_assigns_bands_correctly():
    db, proj, *_ = _make_five_scene_project()
    segments = compute_flow(db, proj.id, FLOW_TIMELINE)
    bands = [seg.band for seg in segments]
    assert BAND_BEGINNING in bands
    assert BAND_ENDING in bands


def test_empty_project_returns_no_segments():
    db = Database()
    proj = db.create_project("Empty")
    assert compute_flow(db, proj.id, FLOW_TIMELINE) == []


def test_single_scene_project_returns_no_segments():
    db = Database()
    proj = db.create_project("One")
    db.create_scene(proj.id, "Only")
    assert compute_flow(db, proj.id, FLOW_TIMELINE) == []


# -- compute_flow acts -------------------------------------------------------

def test_acts_flow_marks_act_boundaries():
    db, proj, *_ = _make_five_scene_project()
    segments = compute_flow(db, proj.id, FLOW_ACTS)
    # Boundaries: Act I → Act II (after Inciting), Act II → Act III (after Midpoint).
    boundary_count = sum(1 for s in segments if s.act_boundary)
    assert boundary_count == 2


def test_acts_flow_internal_segments_not_marked_boundary():
    db, proj, *_ = _make_five_scene_project()
    segments = compute_flow(db, proj.id, FLOW_ACTS)
    # First segment (Opening → Inciting) is intra-act.
    assert segments[0].act_boundary is False


# -- compute_flow arc -------------------------------------------------------

def test_arc_flow_same_topology_as_timeline():
    db, proj, *_ = _make_five_scene_project()
    timeline = compute_flow(db, proj.id, FLOW_TIMELINE)
    arc = compute_flow(db, proj.id, FLOW_ARC)
    timeline_pairs = [(s.from_scene_id, s.to_scene_id) for s in timeline]
    arc_pairs = [(s.from_scene_id, s.to_scene_id) for s in arc]
    assert timeline_pairs == arc_pairs


# -- compute_flow causal ----------------------------------------------------

def test_causal_flow_uses_mention_links():
    db = Database()
    proj = db.create_project("Causal")
    s1 = db.create_scene(proj.id, "Opening", content="The hero leaves home.")
    s2 = db.create_scene(proj.id, "Aftermath",
                         content="After [[Opening]] the hero presses on.")
    segments = compute_flow(db, proj.id, FLOW_CAUSAL)
    assert len(segments) == 1
    assert segments[0].from_scene_id == s2.id
    assert segments[0].to_scene_id == s1.id


def test_causal_flow_no_links_no_segments():
    db, proj, *_ = _make_five_scene_project()
    segments = compute_flow(db, proj.id, FLOW_CAUSAL)
    assert segments == []


def test_causal_flow_skips_self_references():
    db = Database()
    proj = db.create_project("Self")
    s1 = db.create_scene(proj.id, "Loop",
                         content="A note about [[Loop]] itself.")
    db.create_scene(proj.id, "Other")
    segments = compute_flow(db, proj.id, FLOW_CAUSAL)
    assert all(s.from_scene_id != s.to_scene_id for s in segments)


# -- scene_bands -------------------------------------------------------------

def test_scene_bands_covers_all_scenes():
    db, proj, *_ = _make_five_scene_project()
    bands = scene_bands(db, proj.id)
    assert len(bands) == 5
    assert set(bands.values()) >= {BAND_BEGINNING, BAND_MIDDLE, BAND_ENDING}


# -- view integration -------------------------------------------------------

def test_view_flow_default_off():
    db, proj, *_ = _make_five_scene_project()
    view = FocusGraphView(db, proj.id)
    assert view.is_flow_enabled() is False
    assert not view._flow_combo.isEnabled()


def test_view_flow_toggle_enables_combo():
    db, proj, *_ = _make_five_scene_project()
    view = FocusGraphView(db, proj.id)
    view._on_flow_toggled(True)
    assert view.is_flow_enabled()
    assert view._flow_combo.isEnabled()


def test_view_flow_disables_combo_when_off():
    db, proj, *_ = _make_five_scene_project()
    view = FocusGraphView(db, proj.id)
    view._on_flow_toggled(True)
    view._on_flow_toggled(False)
    assert not view._flow_combo.isEnabled()


def test_view_set_flow_changes_type():
    db, proj, *_ = _make_five_scene_project()
    view = FocusGraphView(db, proj.id)
    view.set_flow(True, FLOW_ACTS)
    assert view.get_flow_type() == FLOW_ACTS
    assert view.is_flow_enabled()


def test_view_set_flow_ignores_unknown_type():
    db, proj, *_ = _make_five_scene_project()
    view = FocusGraphView(db, proj.id)
    original = view.get_flow_type()
    view.set_flow(True, "nonsense")
    assert view.get_flow_type() == original


def test_flow_types_constant_lists_all_four():
    assert set(FLOW_TYPES) == {FLOW_TIMELINE, FLOW_ACTS, FLOW_ARC, FLOW_CAUSAL}


def test_view_flow_overlay_draws_path_items():
    """With Flow on and scenes visible, at least one path item is added."""
    db, proj, *_ = _make_five_scene_project()
    view = FocusGraphView(db, proj.id)
    # Make sure scenes are in the visible set — switch to Structure mode.
    from logosforge.ui.focus_graph_view import MODE_STRUCTURE
    view.set_mode(MODE_STRUCTURE)
    view.set_flow(True, FLOW_TIMELINE)
    from PySide6.QtWidgets import QGraphicsPathItem
    path_items = [
        item for item in view._gscene.items()
        if isinstance(item, QGraphicsPathItem)
    ]
    assert len(path_items) >= 1


def test_view_flow_overlay_inactive_in_quantum_mode():
    """Flow is meaningless in Quantum mode (no scenes) — should silently skip."""
    db, proj, *_ = _make_five_scene_project()
    view = FocusGraphView(db, proj.id)
    from logosforge.ui.focus_graph_view import MODE_QUANTUM
    view.set_mode(MODE_QUANTUM)
    view.set_flow(True, FLOW_TIMELINE)
    from PySide6.QtWidgets import QGraphicsPathItem
    path_items = [
        item for item in view._gscene.items()
        if isinstance(item, QGraphicsPathItem)
    ]
    assert path_items == []
