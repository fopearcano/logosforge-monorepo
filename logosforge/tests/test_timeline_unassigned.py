"""Timeline 'Unassigned' lane behavior — user-controlled events + clear inbox.

A Scene is a Timeline *event* only if it has a lane (non-empty plotline) or is
in the explicit event-membership set. Outline scenes are NOT auto-events, so
creating an Act/lane never reveals an Unassigned lane. 'Unassigned Events' is a
computed fallback shown only when events without a lane exist (e.g. after a lane
is deleted), and it is actionable.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge.ui.main_window import MainWindow
from logosforge.ui.plot_timeline_view import PlotTimelineView, _UNASSIGNED


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


def _rows(view):
    return [name for _, name, _ in view._rows]


def _set_text(monkeypatch, value):
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: (value, True)))


# ==========================================================================
# 1-3  No auto events/lanes from Outline; adding a lane stays clean
# ==========================================================================


def test_creating_act_creates_no_timeline_lane_or_event(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    pid = _novel(db)
    win = MainWindow(db, pid)
    ss.create_act(db, pid, "Act I")             # Outline Act (seeds a scene)
    win.sidebar_buttons["Timeline"].click()
    assert win.content_area._rows == []          # no lane, no event
    assert db.get_timeline_lanes(pid) == []
    assert db.get_timeline_event_ids(pid) == set()


def test_adding_lane_does_not_create_unassigned():
    db = Database()
    pid = _novel(db)
    ss.create_act(db, pid, "Act I")             # plotline-less Outline scene
    db.create_timeline_lane(pid, "Main", "green")
    view = PlotTimelineView(db, pid)
    assert _rows(view) == ["Main"]               # only the real lane, no inbox


def test_outline_scene_is_not_a_timeline_event():
    db = Database()
    pid = _novel(db)
    ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="S")  # no plotline
    view = PlotTimelineView(db, pid)
    assert view._rows == []                       # not shown as an event


# ==========================================================================
# 4-7  Unassigned appears only for lane-less events; hides when empty
# ==========================================================================


def test_unassigned_appears_only_when_lane_less_event_exists():
    db = Database()
    pid = _novel(db)
    lane = db.create_timeline_lane(pid, "Main", "green")
    ev = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="E",
                         plotline="Main").id
    view = PlotTimelineView(db, pid)
    assert _rows(view) == ["Main"]                # event on a lane → no inbox
    view._delete_lane(lane.id)                    # lane gone → event lane-less
    view.refresh()
    assert _UNASSIGNED in _rows(view)
    assert ev in view._unassigned_event_ids()


def test_assigning_unassigned_event_to_lane_clears_inbox():
    db = Database()
    pid = _novel(db)
    lane = db.create_timeline_lane(pid, "Main", "green")
    ev = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="E",
                         plotline="Main").id
    view = PlotTimelineView(db, pid)
    view._delete_lane(lane.id)                    # ev now unassigned
    view.refresh()
    assert _UNASSIGNED in _rows(view)
    db.create_timeline_lane(pid, "Sub", "amber")
    view.refresh()
    view._assign_lane(ev, "Sub")                  # move the event to a lane
    assert db.get_scene_by_id(ev).plotline == "Sub"
    assert _UNASSIGNED not in _rows(view)         # inbox empty → hidden


def test_empty_unassigned_is_hidden():
    db = Database()
    pid = _novel(db)
    db.create_timeline_lane(pid, "Main", "green")
    ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="E",
                    plotline="Main")
    view = PlotTimelineView(db, pid)
    assert _UNASSIGNED not in _rows(view)         # all events have a lane


def test_case_only_plotlines_share_one_lane():
    # "Main" and "main" are one logical plotline: they must collapse onto a
    # single lane, and the off-case event must NOT land in Unassigned.
    db = Database()
    pid = _novel(db)
    a = ss.create_scene(db, pid, title="A", plotline="Main").id
    b = ss.create_scene(db, pid, title="B", plotline="main").id
    view = PlotTimelineView(db, pid)
    assert _rows(view) == ["Main"]                 # one lane, no fragmentation
    assert _UNASSIGNED not in _rows(view)          # off-case event not orphaned
    lane_scenes = view._rows[0][2]                 # both events on the one lane
    assert {s.id for s in lane_scenes} == {a, b}


# ==========================================================================
# 8-9  Real lane edit actions + Unassigned actions
# ==========================================================================


def test_real_lane_edit_actions(monkeypatch):
    db = Database()
    pid = _novel(db)
    lane = db.create_timeline_lane(pid, "Main", "green")
    view = PlotTimelineView(db, pid)
    _set_text(monkeypatch, "Main Arc")
    view._rename_lane(lane)
    view._set_lane_color(lane.id, "violet")
    ln = db.get_timeline_lanes(pid)[0]
    assert ln.name == "Main Arc" and ln.color_label == "violet"
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    view._confirm_delete_lane(ln)
    assert db.get_timeline_lanes(pid) == []


def test_create_lane_from_unassigned(monkeypatch):
    db = Database()
    pid = _novel(db)
    lane = db.create_timeline_lane(pid, "Main", "green")
    a = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="A",
                        plotline="Main").id
    view = PlotTimelineView(db, pid)
    view._delete_lane(lane.id)                    # a → unassigned event
    view.refresh()
    _set_text(monkeypatch, "Recovered")
    view._create_lane_from_unassigned()
    assert db.get_scene_by_id(a).plotline == "Recovered"
    view.refresh()
    assert _UNASSIGNED not in _rows(view)


def test_assign_all_unassigned(monkeypatch):
    db = Database()
    pid = _novel(db)
    lane = db.create_timeline_lane(pid, "Main", "green")
    a = ss.create_scene(db, pid, title="A", plotline="Main").id
    b = ss.create_scene(db, pid, title="B", plotline="Main").id
    view = PlotTimelineView(db, pid)
    view._delete_lane(lane.id)                    # a,b → unassigned
    db.create_timeline_lane(pid, "Sub", "amber")
    view.refresh()
    view._assign_all_unassigned("Sub")
    assert db.get_scene_by_id(a).plotline == "Sub"
    assert db.get_scene_by_id(b).plotline == "Sub"


# ==========================================================================
# Add existing scene / Remove from Timeline
# ==========================================================================


def test_add_existing_scene_to_lane(monkeypatch):
    db = Database()
    pid = _novel(db)
    db.create_timeline_lane(pid, "Main", "green")
    sid = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="S").id  # not event
    view = PlotTimelineView(db, pid)
    assert sid not in {s.id for s in db.get_all_scenes(pid)
                       if (s.plotline or "")}
    monkeypatch.setattr(QInputDialog, "getItem",
                        staticmethod(lambda *a, **k: (a[3][0], True)))  # first item
    view._add_existing_scene_to_lane("Main")
    assert db.get_scene_by_id(sid).plotline == "Main"   # now an event on Main


def test_remove_event_keeps_scene(monkeypatch):
    db = Database()
    pid = _novel(db)
    db.create_timeline_lane(pid, "Main", "green")
    sid = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="S",
                          plotline="Main", content="BODY").id
    view = PlotTimelineView(db, pid)
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    view._remove_event(sid)
    s = db.get_scene_by_id(sid)
    assert s is not None and s.content == "BODY"        # Scene preserved
    assert (s.plotline or "") == "" and sid not in db.get_timeline_event_ids(pid)
    assert sid not in PlotTimelineView(db, pid)._card_by_scene   # no card shown


# ==========================================================================
# 10-12  Canonical label + isolation
# ==========================================================================


def test_event_keeps_canonical_label():
    db = Database()
    pid = _novel(db)
    db.create_timeline_lane(pid, "Main", "green")
    ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="Opening",
                    plotline="Main")
    from PySide6.QtWidgets import QLabel
    view = PlotTimelineView(db, pid)
    text = " ".join(w.text() for w in view.findChildren(QLabel))
    assert "1.1.1" in text


def test_event_membership_project_isolated(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    a = _novel(db)
    sa = ss.create_scene(db, a, title="A", plotline="Main").id
    db.add_timeline_event(a, sa)
    b = _novel(db)
    assert db.get_timeline_event_ids(b) == set()
    win = MainWindow(db, a)
    win.sidebar_buttons["Timeline"].click()
    win._switch_project(b)
    win.sidebar_buttons["Timeline"].click()
    assert win.content_area._rows == []                  # B clean
