"""Timeline planner upgrade — Plottr-like lane/matrix gaps filled on top of the
existing colored-lane / linked-event Timeline.

Focus of this file (complements test_timeline_links.py / test_plot_timeline.py):
the sidebar mounts the real view, lane/event/move operations run through the
*view* and persist, link labels are settable + persistent, double-click opens
the unit in Manuscript (not the hidden Scenes view), and selection/link state
plus all data are project-isolated.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication, QInputDialog, QLabel

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.ui.main_window import MainWindow
from logosforge.ui.plot_timeline_view import PlotTimelineView
from logosforge.ui.writing_core_view import WritingCoreView


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
# 1  Routing — the real view is mounted with its marker objectName
# ==========================================================================


def test_sidebar_timeline_mounts_marked_view(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    win = MainWindow(db, _novel(db))
    win.sidebar_buttons["Timeline"].click()
    assert isinstance(win.content_area, PlotTimelineView)
    assert win.content_area.objectName() == "timeline_target_colored_lane_link_view"


# ==========================================================================
# 2-5  Lanes + colour (through the view; persistent)
# ==========================================================================


def test_create_lane_via_view(monkeypatch):
    db = Database()
    pid = _novel(db)
    view = PlotTimelineView(db, pid)
    _text(monkeypatch, "Main Plot")
    view._add_lane()
    assert [ln.name for ln in db.get_timeline_lanes(pid)] == ["Main Plot"]


def test_rename_lane_via_view(monkeypatch):
    db = Database()
    pid = _novel(db)
    lane = db.create_timeline_lane(pid, "Main", "green")
    view = PlotTimelineView(db, pid)
    _text(monkeypatch, "Main Arc")
    view._rename_lane(lane)
    assert db.get_timeline_lanes(pid)[0].name == "Main Arc"


def test_change_lane_color_via_view():
    db = Database()
    pid = _novel(db)
    lane = db.create_timeline_lane(pid, "Main", "green")
    view = PlotTimelineView(db, pid)
    view._set_lane_color(lane.id, "violet")
    assert db.get_timeline_lanes(pid)[0].color_label == "violet"


def test_lane_color_persists_after_reload(tmp_path):
    path = str(tmp_path / "sp.db")
    db = Database(path)
    pid = _novel(db)
    lane = db.create_timeline_lane(pid, "Main", "green")
    db.set_timeline_lane_color(lane.id, "cyan")
    db2 = Database(path)                       # simulate reopen
    assert db2.get_timeline_lanes(pid)[0].color_label == "cyan"


# ==========================================================================
# 6-9  Events (blocks): create / edit / colour
# ==========================================================================


def test_add_event_to_lane_via_view(monkeypatch):
    db = Database()
    pid = _novel(db)
    db.create_timeline_lane(pid, "Main", "green")
    view = PlotTimelineView(db, pid)
    _text(monkeypatch, "Inciting Incident")
    view._add_event_to_lane("Main")
    mains = [s for s in db.get_all_scenes(pid) if s.plotline == "Main"]
    assert [s.title for s in mains] == ["Inciting Incident"]
    assert mains[0].content == ""             # Timeline never writes body


def test_edit_event_title_via_view(monkeypatch):
    db = Database()
    pid = _novel(db)
    sid = db.create_scene(pid, "Old", plotline="Main", content="x").id
    view = PlotTimelineView(db, pid)
    _text(monkeypatch, "New Title")
    view._rename_event(sid)
    assert db.get_scene_by_id(sid).title == "New Title"
    assert db.get_scene_by_id(sid).content == "x"


def test_change_event_color_and_persist(tmp_path):
    path = str(tmp_path / "sp.db")
    db = Database(path)
    pid = _novel(db)
    sid = db.create_scene(pid, "S", plotline="Main", content="x").id
    PlotTimelineView(db, pid)._set_event_color(sid, "amber")
    assert Database(path).get_scene_by_id(sid).color_label == "amber"


def test_status_chip_renders_on_card():
    db = Database()
    pid = _novel(db)
    db.create_scene(pid, "S", plotline="Main", content="x", tags="status:Draft")
    db.create_timeline_lane(pid, "Main", "green")
    view = PlotTimelineView(db, pid)
    chips = [w.text() for w in view.findChildren(QLabel)
             if w.objectName() == "timelineStatusChip"]
    assert any("Draft" in c for c in chips)


# ==========================================================================
# 10-12  Move blocks (horizontal position + lane); persist
# ==========================================================================


def test_move_block_horizontally(tmp_path):
    path = str(tmp_path / "sp.db")
    db = Database(path)
    pid = _novel(db)
    a = db.create_scene(pid, "A", plotline="Main", content="x").id
    b = db.create_scene(pid, "B", plotline="Main", content="y").id
    view = PlotTimelineView(db, pid)
    assert [s.id for s in db.get_all_scenes(pid)] == [a, b]
    view._move_event(b, -1)                    # B earlier than A on the timeline
    # Timeline order persists and is timeline-specific; the Outline order
    # (Scene.sort_order) is deliberately left unchanged.
    assert Database(path).get_timeline_order(pid) == [b, a]
    assert [s.id for s in Database(path).get_all_scenes(pid)] == [a, b]


def test_move_block_to_another_lane_persists(tmp_path):
    path = str(tmp_path / "sp.db")
    db = Database(path)
    pid = _novel(db)
    db.create_timeline_lane(pid, "Main", "green")
    db.create_timeline_lane(pid, "Sub", "amber")
    sid = db.create_scene(pid, "S", plotline="Main", content="x").id
    PlotTimelineView(db, pid)._assign_lane(sid, "Sub")
    moved = Database(path).get_scene_by_id(sid)
    assert moved.plotline == "Sub" and moved.content == "x"   # body untouched


# ==========================================================================
# 13-20  Links (block↔block, colour + label, outline targets)
# ==========================================================================


def test_link_same_and_cross_lane():
    db = Database()
    pid = _novel(db)
    a = db.create_scene(pid, "A", plotline="Main", content="x").id
    b = db.create_scene(pid, "B", plotline="Main", content="y").id
    c = db.create_scene(pid, "C", plotline="Sub", content="z").id
    view = PlotTimelineView(db, pid)
    view._link_to_scene_direct(a, b)           # same lane
    view._link_to_scene_direct(a, c)           # cross lane
    assert len(db.get_timeline_links(pid)) == 2


def test_link_label_set_and_persist(tmp_path, monkeypatch):
    path = str(tmp_path / "sp.db")
    db = Database(path)
    pid = _novel(db)
    a = db.create_scene(pid, "A", content="x").id
    b = db.create_scene(pid, "B", content="y").id
    link = db.add_timeline_link(pid, a, b, color_label="cyan",
                               link_type="causality")
    view = PlotTimelineView(db, pid)
    _text(monkeypatch, "because of")
    view._set_link_label(link.id)
    reloaded = [l for l in Database(path).get_timeline_links(pid)
                if l.id == link.id][0]
    assert reloaded.label == "because of"
    assert reloaded.color_label == "cyan" and reloaded.link_type == "causality"


def test_set_link_type_and_color_via_view():
    db = Database()
    pid = _novel(db)
    a = db.create_scene(pid, "A", content="x").id
    b = db.create_scene(pid, "B", content="y").id
    link = db.add_timeline_link(pid, a, b)
    view = PlotTimelineView(db, pid)
    view._set_link_type(link.id, "setup_payoff")
    view._set_link_color(link.id, "violet")
    got = [l for l in db.get_timeline_links(pid) if l.id == link.id][0]
    assert got.link_type == "setup_payoff" and got.color_label == "violet"


def test_remove_link_keeps_blocks_via_view():
    db = Database()
    pid = _novel(db)
    a = db.create_scene(pid, "A", content="x").id
    b = db.create_scene(pid, "B", content="y").id
    link = db.add_timeline_link(pid, a, b)
    PlotTimelineView(db, pid)._remove_link(link.id)
    assert db.get_timeline_links(pid) == []
    assert db.get_scene_by_id(a) is not None and db.get_scene_by_id(b) is not None


def test_link_block_to_act_chapter_scene_via_view():
    db = Database()
    pid = _novel(db)
    s = db.create_scene(pid, "S", act="Act I", chapter="Ch1", content="x").id
    other = db.create_scene(pid, "Other", content="y").id
    view = PlotTimelineView(db, pid)
    view._add_structure_link(s, "act", "Act I")        # → Act
    view._add_structure_link(s, "chapter", "Ch1")      # → Chapter
    view._link_to_scene_direct(s, other)               # → Scene (event link)
    targets = {(l.target_type, l.target_ref)
               for l in db.get_timeline_structure_links(s)}
    assert targets == {("act", "Act I"), ("chapter", "Ch1")}
    assert len(db.get_timeline_links(pid)) == 1


def test_missing_link_target_safe_on_reload(tmp_path):
    path = str(tmp_path / "sp.db")
    db = Database(path)
    pid = _novel(db)
    s = db.create_scene(pid, "S", plotline="Main", content="x").id
    db.add_timeline_structure_link(pid, s, "act", "Ghost Act")
    # Reopen and build the view — a target Act no scene uses must not crash.
    PlotTimelineView(Database(path), pid).refresh()


# ==========================================================================
# 21-23  Double-click → Manuscript + project isolation of state
# ==========================================================================


def test_double_click_opens_manuscript(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    pid = _novel(db)
    sid = db.create_scene(pid, "S", act="Act I", chapter="Ch1",
                          plotline="Main", content="x").id
    win = MainWindow(db, pid)
    win.sidebar_buttons["Timeline"].click()
    assert isinstance(win.content_area, PlotTimelineView)
    win.content_area._open_scene(sid)            # what double-click invokes
    assert win._current_section == "Manuscript"
    assert isinstance(win.content_area, WritingCoreView)
    assert sid in win.content_area._editors


def test_timeline_isolated_and_state_clears_on_switch(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    a = _novel(db)
    sa = db.create_scene(a, "A", plotline="A-LANE", content="x").id
    db.create_timeline_lane(a, "A-LANE", "green")
    b = _novel(db)
    win = MainWindow(db, a)
    win.sidebar_buttons["Timeline"].click()
    win.content_area._start_link(sa)             # pending selection on A
    assert win.content_area._pending_link_source == sa
    win._switch_project(b)
    win.sidebar_buttons["Timeline"].click()
    # B is clean: no lanes, no links, no carried-over selection.
    assert win.content_area._lanes == []
    assert win.content_area._links == []
    assert win.content_area._pending_link_source is None


def test_new_project_timeline_is_empty(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    a = _novel(db)
    db.create_timeline_lane(a, "A-LANE", "green")
    b = _novel(db)
    assert db.get_timeline_lanes(b) == []
    assert db.get_timeline_links(b) == []
