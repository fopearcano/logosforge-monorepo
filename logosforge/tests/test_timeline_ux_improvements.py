"""Regression tests for the 5 Timeline UX improvements:

1. Discoverability — off-timeline Outline scenes are surfaced + one-click add.
2. Drag-target lane highlight — canvas resolves the hovered lane row.
3. Stale structure links — broken Act/Chapter links are detectable (flagged).
4. Case-insensitive lane names — no silent case-only duplicate lanes.
5. Order-mode toggle — reads as a 2-state toggle (accent when Custom).
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.ui.plot_timeline_view import (
    PlotTimelineView,
    RULER_H,
    _TimelineCanvas,
)


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    import logosforge.gomckee_bridge as gb
    monkeypatch.setattr(gb, "is_gomckee_enabled", lambda: False, raising=False)
    yield
    settings._instance = None


def _novel(db):
    return db.create_project("P", narrative_engine="novel").id


def _text(monkeypatch, value):
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: (value, True)))


# ==========================================================================
# 1 — Discoverability: off-timeline scenes
# ==========================================================================


def test_off_timeline_scenes_detected_and_button_visible():
    db = Database()
    pid = _novel(db)
    db.create_scene(pid, "A", content="x")          # no plotline → off timeline
    db.create_scene(pid, "B", content="x")
    db.create_scene(pid, "C", plotline="Main", content="x")  # on timeline
    view = PlotTimelineView(db, pid)
    ids = {s.id for s in view._off_timeline}
    titles = {db.get_scene_by_id(i).title for i in ids}
    assert titles == {"A", "B"}                      # C excluded (has a lane)
    assert not view._offtl_btn.isHidden()            # shown (own flag, headless-safe)
    assert "2 scenes off timeline" in view._offtl_btn.text()


def test_off_timeline_button_hidden_when_all_on_timeline():
    db = Database()
    pid = _novel(db)
    db.create_scene(pid, "A", plotline="Main", content="x")
    view = PlotTimelineView(db, pid)
    assert view._off_timeline == []
    assert view._offtl_btn.isHidden()


def test_add_all_offtimeline_makes_them_events():
    db = Database()
    pid = _novel(db)
    a = db.create_scene(pid, "A", content="x").id
    b = db.create_scene(pid, "B", content="x").id
    view = PlotTimelineView(db, pid)
    assert view._off_timeline                          # present before
    view._add_all_offtimeline()
    event_ids = db.get_timeline_event_ids(pid)
    assert a in event_ids and b in event_ids           # now events
    assert view._off_timeline == []                    # affordance cleared


def test_add_one_offtimeline_adds_only_that_scene():
    db = Database()
    pid = _novel(db)
    a = db.create_scene(pid, "A", content="x").id
    b = db.create_scene(pid, "B", content="x").id
    view = PlotTimelineView(db, pid)
    view._add_offtimeline_one(a)
    event_ids = db.get_timeline_event_ids(pid)
    assert a in event_ids and b not in event_ids
    assert {s.id for s in view._off_timeline} == {b}   # b still off timeline


# ==========================================================================
# 2 — Drag-target lane highlight
# ==========================================================================


def test_canvas_row_at_resolves_lane_from_y():
    db = Database()
    pid = _novel(db)
    db.create_timeline_lane(pid, "Main")
    db.create_timeline_lane(pid, "Sub")
    db.create_scene(pid, "S", plotline="Main", content="x")
    view = PlotTimelineView(db, pid)
    canvas = view._canvas
    assert isinstance(canvas, _TimelineCanvas)
    # First lane band is just below the ruler.
    assert canvas._row_at(RULER_H + 5) == 0
    assert canvas._row_at(-10) == -1                   # above all rows


def test_canvas_hover_row_updates_and_repaints():
    db = Database()
    pid = _novel(db)
    db.create_timeline_lane(pid, "Main")
    db.create_scene(pid, "S", plotline="Main", content="x")
    view = PlotTimelineView(db, pid)
    canvas = view._canvas
    assert canvas._drag_hover_row == -1
    canvas._set_hover_row(0)
    assert canvas._drag_hover_row == 0
    canvas._set_hover_row(-1)                          # cleared on leave/drop
    assert canvas._drag_hover_row == -1


# ==========================================================================
# 3 — Stale structure links flagged
# ==========================================================================


def test_struct_link_broken_for_missing_act():
    db = Database()
    pid = _novel(db)
    s = db.create_scene(pid, "S", act="Act I", content="x").id
    db.add_timeline_structure_link(pid, s, "act", "Act I")     # real
    db.add_timeline_structure_link(pid, s, "act", "Ghost")     # dangling
    view = PlotTimelineView(db, pid)
    links = {sl.target_ref: sl for sl in db.get_timeline_structure_links(s)}
    assert view._struct_link_broken(links["Ghost"]) is True
    assert view._struct_link_broken(links["Act I"]) is False
    # The clean label is unchanged (other tests depend on it).
    assert view._struct_ref_label(links["Ghost"]) == "Ghost"


def test_struct_link_broken_for_renamed_chapter():
    db = Database()
    pid = _novel(db)
    s = db.create_scene(pid, "S", act="Act I", chapter="Ch1", content="x").id
    db.add_timeline_structure_link(pid, s, "chapter", "Ch1")
    view = PlotTimelineView(db, pid)
    sl = db.get_timeline_structure_links(s)[0]
    assert view._struct_link_broken(sl) is False
    # Rename the chapter on the scene → the old name no longer exists.
    db.update_scene(s, "S", act="Act I", chapter="Chapter One", content="x")
    view.refresh()
    assert view._struct_link_broken(sl) is True


def test_struct_link_not_broken_on_whitespace_mismatch():
    # get_scene_chapters() strips, and target_ref may carry stray whitespace —
    # a benign whitespace difference must NOT read as broken.
    db = Database()
    pid = _novel(db)
    s = db.create_scene(pid, "S", act="Act I", chapter=" Ch1 ", content="x").id
    db.add_timeline_structure_link(pid, s, "chapter", "Ch1")     # stripped ref
    view = PlotTimelineView(db, pid)
    sl = next(x for x in db.get_timeline_structure_links(s)
              if x.target_type == "chapter")
    assert view._struct_link_broken(sl) is False                 # not a false alarm


# ==========================================================================
# 4 — Case-insensitive lane names (no silent duplicates)
# ==========================================================================


def test_add_lane_rejects_case_insensitive_duplicate(monkeypatch):
    db = Database()
    pid = _novel(db)
    db.create_timeline_lane(pid, "Main Plot")
    view = PlotTimelineView(db, pid)
    seen = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: seen.append(a)))
    _text(monkeypatch, "main plot")                    # case-only dup
    view._add_lane()
    assert len(db.get_timeline_lanes(pid)) == 1         # not duplicated
    assert seen                                          # warned the user


def test_lane_with_name_ci_helper():
    db = Database()
    pid = _novel(db)
    db.create_timeline_lane(pid, "Main Plot")
    view = PlotTimelineView(db, pid)
    assert view._lane_with_name_ci("MAIN PLOT") is not None
    assert view._lane_with_name_ci(" main plot ") is not None
    assert view._lane_with_name_ci("Subplot") is None
    # Renaming a lane to a different case of itself is allowed (excluded).
    lane = db.get_timeline_lanes(pid)[0]
    assert view._lane_with_name_ci("main plot", exclude_id=lane.id) is None


def test_distinct_lane_names_still_allowed(monkeypatch):
    db = Database()
    pid = _novel(db)
    db.create_timeline_lane(pid, "Main Plot")
    view = PlotTimelineView(db, pid)
    _text(monkeypatch, "Subplot")
    view._add_lane()
    assert len(db.get_timeline_lanes(pid)) == 2


# ==========================================================================
# 5 — Order-mode toggle prominence
# ==========================================================================


def test_order_toggle_style_reflects_mode():
    from logosforge.ui import theme
    db = Database()
    pid = _novel(db)
    db.create_scene(pid, "S", plotline="Main", content="x")
    view = PlotTimelineView(db, pid)
    # Structural (default): muted, with a hover affordance.
    assert view._order_mode == "structural"
    assert "Order: Structural" in view._order_mode_btn.text()
    assert ":hover" in view._order_mode_btn.styleSheet()
    # Switch to Custom → button styled "active" in accent.
    db.set_timeline_order_mode(pid, "custom")
    view.refresh()
    assert "Order: Custom" in view._order_mode_btn.text()
    assert theme.ACCENT in view._order_mode_btn.styleSheet()
    assert "700" in view._order_mode_btn.styleSheet()  # bold = active state
