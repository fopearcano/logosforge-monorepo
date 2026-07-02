"""Tests for Multi-View Plotting — dynamic story perspectives."""

from logosforge.db import Database
from logosforge.ui import theme
from logosforge.ui.multi_plot_view import (
    MultiPlotView,
    PlotFilters,
    _ArcLanes,
    _CharLanes,
    _TimelineStrip,
    _VIEW_MODES,
    _apply_filters,
)


def _make_project():
    db = Database()
    proj = db.create_project("MultiPlotTest")
    return db, proj


def _make_full_project():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Alice")
    c2 = db.create_character(proj.id, "Bob")
    s1 = db.create_scene(
        proj.id, "Opening", content="Start.",
        act="Act 1", chapter="Ch 1", plotline="Main", tags="setup",
        character_ids=[c1.id],
    )
    s2 = db.create_scene(
        proj.id, "Rising", content="Rise.",
        act="Act 1", chapter="Ch 1", plotline="Main", tags="action",
        character_ids=[c1.id, c2.id],
    )
    s3 = db.create_scene(
        proj.id, "Midpoint", content="Turn.",
        act="Act 2", chapter="Ch 2", plotline="Sub", tags="twist",
        character_ids=[c2.id],
    )
    s4 = db.create_scene(
        proj.id, "Climax", content="Peak.",
        act="Act 2", chapter="Ch 2", plotline="Main", beat="Climax",
        character_ids=[c1.id, c2.id],
    )
    return db, proj, c1, c2, s1, s2, s3, s4


# -- MultiPlotView construction -----------------------------------------------

def test_multiplot_default_mode_grid():
    db, proj, *_ = _make_full_project()
    view = MultiPlotView(db, proj.id)
    assert view.get_active_mode() == "Grid"


def test_multiplot_has_all_mode_buttons():
    db, proj, *_ = _make_full_project()
    view = MultiPlotView(db, proj.id)
    assert set(view._mode_buttons.keys()) == set(_VIEW_MODES)


def test_multiplot_grid_visible_by_default():
    db, proj, *_ = _make_full_project()
    view = MultiPlotView(db, proj.id)
    assert not view._grid_view.isHidden()
    assert view._timeline_view.isHidden()
    assert view._arc_view.isHidden()
    assert view._char_view.isHidden()


# -- View switching -----------------------------------------------------------

def test_switch_to_timeline():
    db, proj, *_ = _make_full_project()
    view = MultiPlotView(db, proj.id)
    view._switch_mode("Timeline")
    assert view.get_active_mode() == "Timeline"
    assert not view._timeline_view.isHidden()
    assert view._grid_view.isHidden()


def test_switch_to_arc():
    db, proj, *_ = _make_full_project()
    view = MultiPlotView(db, proj.id)
    view._switch_mode("Arc")
    assert view.get_active_mode() == "Arc"
    assert not view._arc_view.isHidden()


def test_switch_to_character():
    db, proj, *_ = _make_full_project()
    view = MultiPlotView(db, proj.id)
    view._switch_mode("Character")
    assert view.get_active_mode() == "Character"
    assert not view._char_view.isHidden()


def test_switch_same_mode_no_op():
    db, proj, *_ = _make_full_project()
    view = MultiPlotView(db, proj.id)
    view._switch_mode("Grid")
    assert view.get_active_mode() == "Grid"


def test_switch_updates_button_checked():
    db, proj, *_ = _make_full_project()
    view = MultiPlotView(db, proj.id)
    view._switch_mode("Arc")
    assert view._mode_buttons["Arc"].isChecked()
    assert not view._mode_buttons["Grid"].isChecked()


# -- Timeline strip -----------------------------------------------------------

def test_timeline_shows_all_scenes():
    db, proj, *_ = _make_full_project()
    strip = _TimelineStrip(db, proj.id)
    strip.refresh()
    assert strip.card_count() == 4


def test_timeline_empty_project():
    db, proj = _make_project()
    strip = _TimelineStrip(db, proj.id)
    strip.refresh()
    assert strip.card_count() == 0


def test_timeline_with_filter():
    db, proj, c1, c2, *_ = _make_full_project()
    strip = _TimelineStrip(db, proj.id)
    strip.refresh(PlotFilters(character_id=c1.id))
    assert strip.card_count() == 3


def test_timeline_tag_filter():
    db, proj, *_ = _make_full_project()
    strip = _TimelineStrip(db, proj.id)
    strip.refresh(PlotFilters(tag="twist"))
    assert strip.card_count() == 1


# -- Arc lanes ----------------------------------------------------------------

def test_arc_shows_lanes():
    db, proj, *_ = _make_full_project()
    arc = _ArcLanes(db, proj.id)
    arc.refresh()
    assert arc.lane_count() == 2  # "Main" and "Sub"


def test_arc_empty_project():
    db, proj = _make_project()
    arc = _ArcLanes(db, proj.id)
    arc.refresh()
    assert arc.lane_count() == 0


def test_arc_with_plotline_filter():
    db, proj, *_ = _make_full_project()
    arc = _ArcLanes(db, proj.id)
    arc.refresh(PlotFilters(plotline="Main"))
    assert arc.lane_count() == 1


def test_arc_unassigned_plotline():
    db, proj = _make_project()
    db.create_scene(proj.id, "Orphan", content="No plotline.")
    arc = _ArcLanes(db, proj.id)
    arc.refresh()
    assert arc.lane_count() == 1


# -- Character lanes ----------------------------------------------------------

def test_char_shows_lanes():
    db, proj, c1, c2, *_ = _make_full_project()
    char_view = _CharLanes(db, proj.id)
    char_view.refresh()
    assert char_view.lane_count() == 2  # Alice and Bob


def test_char_empty_no_links():
    db, proj = _make_project()
    db.create_scene(proj.id, "Solo", content="No chars linked.")
    db.create_character(proj.id, "Ghost")
    char_view = _CharLanes(db, proj.id)
    char_view.refresh()
    assert char_view.lane_count() == 0


def test_char_with_character_filter():
    db, proj, c1, c2, *_ = _make_full_project()
    char_view = _CharLanes(db, proj.id)
    char_view.refresh(PlotFilters(character_id=c1.id))
    assert char_view.lane_count() >= 1


# -- Filter logic -------------------------------------------------------------

def test_filter_by_character():
    db, proj, c1, c2, s1, s2, s3, s4 = _make_full_project()
    scenes = db.get_all_scenes(proj.id)
    filtered = _apply_filters(db, scenes, PlotFilters(character_id=c1.id))
    ids = {s.id for s in filtered}
    assert s1.id in ids
    assert s2.id in ids
    assert s4.id in ids
    assert s3.id not in ids


def test_filter_by_tag():
    db, proj, c1, c2, s1, s2, s3, s4 = _make_full_project()
    scenes = db.get_all_scenes(proj.id)
    filtered = _apply_filters(db, scenes, PlotFilters(tag="twist"))
    assert len(filtered) == 1
    assert filtered[0].id == s3.id


def test_filter_by_plotline():
    db, proj, c1, c2, s1, s2, s3, s4 = _make_full_project()
    scenes = db.get_all_scenes(proj.id)
    filtered = _apply_filters(db, scenes, PlotFilters(plotline="Sub"))
    assert len(filtered) == 1
    assert filtered[0].id == s3.id


def test_filter_combined():
    db, proj, c1, c2, s1, s2, s3, s4 = _make_full_project()
    scenes = db.get_all_scenes(proj.id)
    filtered = _apply_filters(db, scenes, PlotFilters(character_id=c2.id, plotline="Main"))
    ids = {s.id for s in filtered}
    assert s2.id in ids
    assert s4.id in ids
    assert s1.id not in ids


def test_filter_no_filters_returns_all():
    db, proj, *_ = _make_full_project()
    scenes = db.get_all_scenes(proj.id)
    filtered = _apply_filters(db, scenes, PlotFilters())
    assert len(filtered) == len(scenes)


def test_filter_empty_result():
    db, proj, *_ = _make_full_project()
    scenes = db.get_all_scenes(proj.id)
    filtered = _apply_filters(db, scenes, PlotFilters(tag="nonexistent"))
    assert filtered == []


# -- PlotFilters dataclass ----------------------------------------------------

def test_filters_default():
    f = PlotFilters()
    assert f.character_id is None
    assert f.tag == ""
    assert f.plotline == ""


# -- MultiPlotView filter integration -----------------------------------------

def test_multiplot_filter_state():
    db, proj, *_ = _make_full_project()
    view = MultiPlotView(db, proj.id)
    assert view.get_filters().character_id is None
    assert view.get_filters().tag == ""


# -- Theme includes multi-plot styles -----------------------------------------

def test_theme_has_multiplot_toolbar():
    ss = theme.build_stylesheet()
    assert "#multiPlotToolbar" in ss


def test_theme_has_timeline_card():
    ss = theme.build_stylesheet()
    assert "#timelineCard" in ss


def test_theme_has_arc_lane():
    ss = theme.build_stylesheet()
    assert "#arcLane" in ss


def test_theme_has_char_lane():
    ss = theme.build_stylesheet()
    assert "#charLane" in ss


def test_theme_has_mode_btn():
    ss = theme.build_stylesheet()
    assert "#multiPlotModeBtn" in ss
