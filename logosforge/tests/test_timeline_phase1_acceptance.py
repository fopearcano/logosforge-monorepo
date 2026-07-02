"""Timeline Phase 1 — consolidated Plottr-like acceptance suite.

A cross-cutting spec-traceability check over the existing colored-lane / linked-
event Timeline (PlotTimelineView + TimelineLane/TimelineLink/TimelineStructureLink
+ canonical structure adapter). It asserts the Phase 1 *requirements* end to end
against the public APIs — no new production code. Detailed unit coverage lives in
test_timeline_{planner_upgrade,links,unassigned,canonical_order}.py and
test_plot_timeline.py.
"""

from __future__ import annotations

import json
import warnings

import pytest
from PySide6.QtWidgets import QApplication, QInputDialog, QPushButton

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge.export import export_json
from logosforge.ui.main_window import MainWindow
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


def _text(monkeypatch, value):
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: (value, True)))


# ==========================================================================
# 1  Routing + empty state (no ghost Unassigned, Add Lane present)
# ==========================================================================


def test_sidebar_mounts_marked_view_and_empty_state(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    win = MainWindow(db, _novel(db))
    win.sidebar_buttons["Timeline"].click()
    view = win.content_area
    assert isinstance(view, PlotTimelineView)
    assert view.objectName() == "timeline_target_colored_lane_link_view"
    # Empty project: an "Add Lane" affordance, and NO rows at all (no ghost
    # "Unassigned" lane, no auto lanes).
    btns = [b.text() for b in view.findChildren(QPushButton)]
    assert any("Lane" in t for t in btns)
    assert view._rows == []


# ==========================================================================
# 2  Lane lifecycle (create / rename / color / persist)
# ==========================================================================


def test_lane_lifecycle_and_color_persist(tmp_path, monkeypatch):
    path = str(tmp_path / "sp.db")
    db = Database(path)
    pid = _novel(db)
    view = PlotTimelineView(db, pid)
    _text(monkeypatch, "Main Plot")
    view._add_lane()
    lane = db.get_timeline_lanes(pid)[0]
    assert lane.name == "Main Plot"
    _text(monkeypatch, "Main Arc")
    view._rename_lane(lane)
    view._set_lane_color(lane.id, "violet")
    reopened = Database(path).get_timeline_lanes(pid)[0]   # survives reload
    assert reopened.name == "Main Arc" and reopened.color_label == "violet"


def test_creating_act_does_not_create_lane_or_unassigned():
    db = Database()
    pid = _novel(db)
    ss.create_act(db, pid, "Act I")               # canonical structure only
    assert db.get_timeline_lanes(pid) == []        # no auto lane
    assert db.get_timeline_event_ids(pid) == set() # no auto events


# ==========================================================================
# 3  Event lifecycle — body is never written by the Timeline
# ==========================================================================


def test_event_lifecycle_never_touches_body(tmp_path, monkeypatch):
    path = str(tmp_path / "sp.db")
    db = Database(path)
    pid = _novel(db)
    db.create_timeline_lane(pid, "Main", "green")
    view = PlotTimelineView(db, pid)
    _text(monkeypatch, "Inciting Incident")
    view._add_event_to_lane("Main")
    sid = next(s.id for s in db.get_all_scenes(pid) if s.plotline == "Main")
    assert db.get_scene_by_id(sid).content == ""        # Timeline never writes body
    view._set_event_color(sid, "amber")
    _text(monkeypatch, "Renamed")
    view._rename_event(sid)
    re = Database(path).get_scene_by_id(sid)
    assert re.title == "Renamed" and re.color_label == "amber" and re.content == ""


# ==========================================================================
# 4  Movement persists; Outline order is NOT touched
# ==========================================================================


def test_move_event_persists_without_moving_outline(tmp_path):
    path = str(tmp_path / "sp.db")
    db = Database(path)
    pid = _novel(db)
    a = db.create_scene(pid, "A", plotline="Main", content="x").id
    b = db.create_scene(pid, "B", plotline="Main", content="y").id
    view = PlotTimelineView(db, pid)
    view._move_event(b, -1)                        # B earlier on the Timeline
    db2 = Database(path)
    assert db2.get_timeline_order(pid) == [b, a]    # timeline order persisted
    assert [s.id for s in db2.get_all_scenes(pid)] == [a, b]   # Outline untouched


def test_move_event_to_lane_persists_without_body_change(tmp_path):
    path = str(tmp_path / "sp.db")
    db = Database(path)
    pid = _novel(db)
    db.create_timeline_lane(pid, "Main", "green")
    db.create_timeline_lane(pid, "Sub", "amber")
    sid = db.create_scene(pid, "S", plotline="Main", content="keep").id
    PlotTimelineView(db, pid)._assign_lane(sid, "Sub")
    moved = Database(path).get_scene_by_id(sid)
    assert moved.plotline == "Sub" and moved.content == "keep"


# ==========================================================================
# 5  Structure links — canonical numbering, safe missing target
# ==========================================================================


def test_structure_link_canonical_label_and_missing_safe():
    db = Database()
    pid = _novel(db)
    sid = db.create_scene(pid, "S", act="Act I", chapter="Ch1",
                          plotline="Main", content="x").id
    view = PlotTimelineView(db, pid)
    view._add_structure_link(sid, "act", "Act I")
    view._add_structure_link(sid, "chapter", "Ch1")
    view.refresh()
    links = db.get_timeline_structure_links(sid)
    labels = {view._struct_ref_label(sl) for sl in links}
    assert "Act 1" in labels and "Ch 1.1" in labels      # canonical numbering
    # A renamed/missing target falls back to its raw ref, never crashes.
    view._add_structure_link(sid, "act", "Ghost Act")
    view.refresh()
    ghost = [sl for sl in db.get_timeline_structure_links(sid)
             if sl.target_ref == "Ghost Act"][0]
    assert view._struct_ref_label(ghost) == "Ghost Act"


def test_structure_link_number_follows_outline_move():
    db = Database()
    pid = _novel(db)
    a = db.create_scene(pid, "A", act="Act I", chapter="Ch1", content="x").id
    db.create_scene(pid, "B", act="Act II", chapter="Ch2", content="y")
    sid = db.create_scene(pid, "Ev", act="Act II", chapter="Ch2",
                          plotline="Main", content="z").id
    view = PlotTimelineView(db, pid)
    view._add_structure_link(sid, "act", "Act II")
    view.refresh()
    link = db.get_timeline_structure_links(sid)[0]
    assert view._struct_ref_label(link) == "Act 2"
    # Remove Act I entirely (move its only scene to Act II) -> Act II becomes 1.
    db.set_scene_structure(a, "Act II", "Ch2")
    view.refresh()
    link = db.get_timeline_structure_links(sid)[0]
    assert view._struct_ref_label(link) == "Act 1"        # number followed the move


# ==========================================================================
# 6  Event-to-event links — same/cross lane, color, remove keeps events
# ==========================================================================


def test_event_links_same_and_cross_lane_color_and_remove():
    db = Database()
    pid = _novel(db)
    a = db.create_scene(pid, "A", plotline="Main", content="x").id
    b = db.create_scene(pid, "B", plotline="Main", content="y").id
    c = db.create_scene(pid, "C", plotline="Sub", content="z").id
    link1 = db.add_timeline_link(pid, a, b, color_label="cyan", label="setup→payoff")
    db.add_timeline_link(pid, a, c, color_label="red")     # cross-lane
    assert len(db.get_timeline_links(pid)) == 2
    assert link1.color_label == "cyan" and link1.label == "setup→payoff"
    db.remove_timeline_link(link1.id)
    assert len(db.get_timeline_links(pid)) == 1
    # Removing a link never deletes the events.
    assert db.get_scene_by_id(a) is not None and db.get_scene_by_id(b) is not None


# ==========================================================================
# 7  Unassigned gating
# ==========================================================================


def test_unassigned_only_when_laneless_event_exists():
    db = Database()
    pid = _novel(db)
    # A lane-less event (plotline that matches no lane) creates the inbox row.
    sid = db.create_scene(pid, "Loose", plotline="", content="x").id
    db.add_timeline_event(pid, sid)
    from logosforge.ui.plot_timeline_view import _UNASSIGNED
    view = PlotTimelineView(db, pid)
    rows = lambda v: [name for _, name, _ in v._rows]   # rendered row names
    assert _UNASSIGNED in rows(view)
    # Assigning it to a real lane empties — and hides — the inbox.
    db.create_timeline_lane(pid, "Main", "green")
    view._assign_lane(sid, "Main")
    view.refresh()
    assert _UNASSIGNED not in rows(view)
    assert "Main" in rows(view)


# ==========================================================================
# 8  Project isolation
# ==========================================================================


def test_timeline_data_isolated_across_projects(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    a = _novel(db)
    db.create_timeline_lane(a, "A-LANE", "green")
    sa = db.create_scene(a, "A-EV", plotline="A-LANE", content="x").id
    db.add_timeline_event(a, sa)
    b = _novel(db)
    assert db.get_timeline_lanes(b) == []
    assert db.get_timeline_event_ids(b) == set()
    assert db.get_timeline_links(b) == []
    # New project C: clean.
    c = _novel(db)
    assert db.get_timeline_lanes(c) == [] and db.get_timeline_event_ids(c) == set()


def test_project_switch_clears_selection_and_no_leak(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    a = _novel(db)
    sa = db.create_scene(a, "A-EV", plotline="Main", content="x").id
    b = _novel(db)
    win = MainWindow(db, a)
    win.sidebar_buttons["Timeline"].click()
    view_a = win.content_area
    view_a._pending_link_source = sa               # a dangling selection
    win._switch_project(b)
    win.sidebar_buttons["Timeline"].click()
    view_b = win.content_area
    assert view_b._pending_link_source is None       # selection cleared on switch
    assert view_b._project_id == b


# ==========================================================================
# 9  Export carries timeline data, never secrets
# ==========================================================================


def test_export_has_timeline_data_and_no_secrets():
    db = Database()
    from logosforge.settings import get_manager
    get_manager().set("ai_api_key", "SECRET_KEY_SENTINEL")
    pid = _novel(db)
    db.create_timeline_lane(pid, "Main", "green")
    a = db.create_scene(pid, "A", plotline="Main", content="x").id
    b = db.create_scene(pid, "B", plotline="Main", content="y").id
    db.add_timeline_event(pid, a)
    db.add_timeline_link(pid, a, b, color_label="cyan")
    blob = export_json(db, pid)
    data = json.loads(blob)
    assert "timeline_links" in data or "timeline" in data or "lanes" in str(data)
    assert "SECRET_KEY_SENTINEL" not in blob          # never leaks provider secrets
