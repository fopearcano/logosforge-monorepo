"""Outline header cleanup, movable Chapters, and the Timeline Unassigned-lane fix.

- The Outline header no longer shows the visible "Classical" badge (mode logic
  is preserved internally).
- Chapters are reorderable within an Act and movable to another Act; numbering,
  Manuscript and Timeline all follow; body is preserved.
- Creating an Act in Outline no longer reveals a Timeline "Unassigned" lane;
  that holding row appears only alongside a real, editable lane.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication, QInputDialog, QLabel, QMessageBox, QPushButton

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge.quantum_outliner.state import get_outline_mode
from logosforge.ui.main_window import MainWindow
from logosforge.ui.plan_view import PlanView
from logosforge.ui.plot_timeline_view import PlotTimelineView


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


def _abc(db, pid):
    """Act I → chapters Ch A / Ch B / Ch C, each with one scene."""
    a = ss.create_scene(db, pid, act="Act I", chapter="Ch A", title="sA").id
    b = ss.create_scene(db, pid, act="Act I", chapter="Ch B", title="sB").id
    c = ss.create_scene(db, pid, act="Act I", chapter="Ch C", title="sC").id
    return a, b, c


def _chapters(db, pid, act="Act I"):
    return [c for a, chs in ss.build_structure_tree(db, pid) if a == act
            for c, _ in chs]


# ==========================================================================
# Issue 1 — Outline header: no visible "Classical"
# ==========================================================================


def test_outline_header_hides_classical_badge():
    db = Database()
    pid = _novel(db)
    ss.create_act(db, pid, "Act I")
    view = PlanView(db, pid)
    badge = [w for w in view.findChildren(QLabel)
             if w.objectName() == "planModeBadge"][0]
    assert badge.isVisible() is False        # not shown beside the title


def test_outline_generation_and_template_logic_intact():
    db = Database()
    pid = _novel(db)
    ss.create_act(db, pid, "Act I")
    view = PlanView(db, pid)
    # Template selector + Generate buttons still present; mode logic still works.
    assert hasattr(view, "_template_combo")
    texts = " ".join(b.text() for b in view.findChildren(QPushButton))
    assert "Generate Outline" in texts
    view._refresh_mode_badge()               # mode logic runs without error
    assert get_outline_mode(pid) is not None


# ==========================================================================
# Issue 2 — Chapters are movable (structure actually changes)
# ==========================================================================


def test_move_chapter_within_act():
    db = Database()
    pid = _novel(db)
    _abc(db, pid)
    assert _chapters(db, pid) == ["Ch A", "Ch B", "Ch C"]
    PlanView(db, pid).move_chapter_to_act("Act I", "Ch C", "Act I", 0)  # C → front
    assert _chapters(db, pid) == ["Ch C", "Ch A", "Ch B"]


def test_move_chapter_up_down_helpers():
    db = Database()
    pid = _novel(db)
    _abc(db, pid)
    PlanView(db, pid).move_chapter("Act I", "Ch C", -1)   # "Move Chapter Left"
    assert _chapters(db, pid) == ["Ch A", "Ch C", "Ch B"]


def test_move_chapter_to_another_act():
    db = Database()
    pid = _novel(db)
    ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="x")
    s2 = ss.create_scene(db, pid, act="Act II", chapter="Ch2", title="y").id
    PlanView(db, pid).move_chapter_to_act("Act I", "Ch1", "Act II")
    assert db.get_scene_by_id(
        [s.id for s in db.get_all_scenes(pid) if s.chapter == "Ch1"][0]
    ).act == "Act II"
    assert "Ch1" not in _chapters(db, pid, "Act I")


def test_chapter_move_updates_numbering_and_child_scenes():
    db = Database()
    pid = _novel(db)
    a, b, c = _abc(db, pid)
    PlanView(db, pid).move_chapter_to_act("Act I", "Ch C", "Act I", 0)
    nums = ss.compute_structural_numbers(ss.build_structure_tree(db, pid), True)
    assert nums["chapters"][("Act I", "Ch C")] == "1.1"
    assert nums["scenes"][c] == "1.1.1"          # child scene renumbered
    assert nums["scenes"][a] == "1.2.1"


def test_chapter_move_preserves_body():
    db = Database()
    pid = _novel(db)
    a = ss.create_scene(db, pid, act="Act I", chapter="Ch A", title="sA",
                        content="BODY A").id
    ss.create_scene(db, pid, act="Act I", chapter="Ch B", title="sB")
    PlanView(db, pid).move_chapter_to_act("Act I", "Ch A", "Act I", 1)
    assert db.get_scene_by_id(a).content == "BODY A"


def test_chapter_move_persists_after_reload(tmp_path):
    path = str(tmp_path / "sp.db")
    db = Database(path)
    pid = _novel(db)
    _abc(db, pid)
    PlanView(db, pid).move_chapter_to_act("Act I", "Ch C", "Act I", 0)
    assert _chapters(Database(path), pid) == ["Ch C", "Ch A", "Ch B"]


def test_manuscript_and_timeline_follow_chapter_move():
    db = Database()
    pid = _novel(db)
    s1 = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="S1",
                        plotline="Main").id
    s2 = ss.create_scene(db, pid, act="Act II", chapter="Ch2", title="S2",
                        plotline="Main").id
    db.create_timeline_lane(pid, "Main", "green")
    PlanView(db, pid).move_chapter_to_act("Act II", "Ch2", "Act I")
    # Manuscript reads canonical order; Timeline numbers follow.
    assert ss.canonical_scene_order(db, pid) == [s1, s2]
    nums = PlotTimelineView(db, pid)._structure_numbers["scenes"]
    assert nums[s2] == "1.2.1"


def test_chapter_menu_uses_left_right_labels():
    # Chapters are horizontal columns inside an Act, so the move controls read
    # "Left/Right" (not the old, misleading "Up/Down").
    import inspect
    import logosforge.ui.plan_view as pv
    src = inspect.getsource(pv.PlanView._show_chapter_menu)
    assert "Move Chapter Left" in src and "Move Chapter Right" in src
    assert "Move Chapter Up" not in src and "Move Chapter Down" not in src


# ==========================================================================
# Issue 3 — Timeline: creating an Act does not create an Unassigned lane
# ==========================================================================


def test_creating_act_does_not_create_timeline_lane(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    pid = _novel(db)
    win = MainWindow(db, pid)
    win.sidebar_buttons["Outline"].click()
    ss.create_act(db, pid, "Act I")            # create an Act (as Outline does)
    win.sidebar_buttons["Timeline"].click()
    assert isinstance(win.content_area, PlotTimelineView)
    assert win.content_area._rows == []         # no Unassigned lane revealed
    assert db.get_timeline_lanes(pid) == []     # and no real lane created


def test_unassigned_row_only_for_events_without_lane():
    # An Outline scene is not an event → no Unassigned even with a real lane.
    db = Database()
    pid = _novel(db)
    ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="S")  # no plotline
    lane = db.create_timeline_lane(pid, "Main", "green")
    view = PlotTimelineView(db, pid)
    assert [n for _, n, _ in view._rows] == ["Main"]     # no Unassigned row
    # Put an event on the lane, then delete the lane → it becomes unassigned.
    ev = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="E",
                         plotline="Main").id
    view._delete_lane(lane.id)
    view.refresh()
    names = [n for _, n, _ in view._rows]
    assert any("Unassigned" in n for n in names)         # now it appears
    assert ev in view._unassigned_event_ids()


def test_real_lane_is_editable():
    db = Database()
    pid = _novel(db)
    lane = db.create_timeline_lane(pid, "Main", "green")
    view = PlotTimelineView(db, pid)
    # rename + recolor work
    monkey = lambda *a, **k: ("Main Arc", True)
    import logosforge.ui.plot_timeline_view as m
    m.QInputDialog.getText = staticmethod(monkey)
    view._rename_lane(lane)
    view._set_lane_color(lane.id, "violet")
    ln = db.get_timeline_lanes(pid)[0]
    assert ln.name == "Main Arc" and ln.color_label == "violet"


def test_lane_delete_requires_confirmation(monkeypatch):
    db = Database()
    pid = _novel(db)
    lane = db.create_timeline_lane(pid, "Main", "green")
    view = PlotTimelineView(db, pid)
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    view._confirm_delete_lane(lane)
    assert db.get_timeline_lanes(pid)             # cancelled → still there
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    view._confirm_delete_lane(lane)
    assert db.get_timeline_lanes(pid) == []       # confirmed → deleted


def test_lane_delete_keeps_events():
    db = Database()
    pid = _novel(db)
    lane = db.create_timeline_lane(pid, "Main", "green")
    sid = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="S",
                          plotline="Main").id
    PlotTimelineView(db, pid)._delete_lane(lane.id)
    assert db.get_scene_by_id(sid) is not None     # event preserved
    assert (db.get_scene_by_id(sid).plotline or "") == ""   # just unassigned


def test_timeline_lanes_project_isolated(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    a = _novel(db)
    db.create_timeline_lane(a, "A-Lane", "green")
    b = _novel(db)
    win = MainWindow(db, a)
    win.sidebar_buttons["Timeline"].click()
    assert [ln.name for ln in win.content_area._lanes] == ["A-Lane"]
    win._switch_project(b)
    win.sidebar_buttons["Timeline"].click()
    assert win.content_area._lanes == []           # B has none
    assert win.content_area._rows == []


def test_canvas_plot_still_hidden(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    win = MainWindow(db, _novel(db))
    assert "Plot" not in win._nav_labels
