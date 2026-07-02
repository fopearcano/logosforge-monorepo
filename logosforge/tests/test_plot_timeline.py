"""Plot-lane Timeline: persistence, lanes, events, links, colours, isolation."""

from __future__ import annotations

import json
import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.export import export_json
from logosforge.import_data import import_json
from logosforge.ui.plot_timeline_view import PlotTimelineView, RULER_H, LANE_H


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


def _row_y(view, lane_name):
    """Top y of the lane row with *lane_name* in the canvas."""
    y = RULER_H
    for lane, name, scenes in view._rows:
        h = 30 if (lane is not None and lane.collapsed) else LANE_H
        if name == lane_name:
            return y
        y += h
    raise AssertionError(f"lane {lane_name!r} not found")


# ==========================================================================
# DB layer — lanes / links persistence
# ==========================================================================


def test_lanes_persist_and_reload(tmp_path):
    path = str(tmp_path / "t.db")
    db = Database(path)
    pid = db.create_project("P").id
    db.create_timeline_lane(pid, "Main", color_label="green")
    db.create_timeline_lane(pid, "B-Plot", color_label="amber")
    db2 = Database(path)
    names = [(ln.name, ln.color_label) for ln in db2.get_timeline_lanes(pid)]
    assert names == [("Main", "green"), ("B-Plot", "amber")]


def test_ensure_lanes_materializes_existing_plotlines():
    db = Database()
    pid = db.create_project("P").id
    db.create_scene(pid, "S", plotline="Mystery")
    lanes = db.ensure_timeline_lanes(pid)
    assert [ln.name for ln in lanes] == ["Mystery"]
    # Idempotent.
    assert len(db.ensure_timeline_lanes(pid)) == 1


def test_ensure_lanes_dedupes_case_insensitively():
    """Two scenes whose plotlines differ only in case map to ONE lane, and the
    off-case scene is re-pointed so it never silently falls into 'Unassigned'."""
    db = Database()
    pid = db.create_project("P").id
    a = db.create_scene(pid, "A", plotline="Main").id
    b = db.create_scene(pid, "B", plotline="main").id    # case-only duplicate
    lanes = db.ensure_timeline_lanes(pid)
    assert len(lanes) == 1                                # one lane, not two
    canon = lanes[0].name
    assert canon == "Main"                               # first-seen casing wins
    # Both scenes now carry the canonical plotline → both land on the one lane.
    assert db.get_scene_by_id(a).plotline == canon
    assert db.get_scene_by_id(b).plotline == canon
    # Idempotent: a second pass adds nothing and changes nothing.
    assert len(db.ensure_timeline_lanes(pid)) == 1


def test_ensure_lanes_trims_plotline_whitespace():
    """A padded plotline materialises a trimmed lane and the scene is healed."""
    db = Database()
    pid = db.create_project("P").id
    sid = db.create_scene(pid, "S", plotline=" Mystery ").id
    lanes = db.ensure_timeline_lanes(pid)
    assert [ln.name for ln in lanes] == ["Mystery"]
    assert db.get_scene_by_id(sid).plotline == "Mystery"


def test_ensure_lanes_prefers_existing_lane_casing():
    """An existing lane's casing is canonical; an off-case scene re-points to it
    rather than spawning a second lane."""
    db = Database()
    pid = db.create_project("P").id
    db.create_timeline_lane(pid, "Main")
    sid = db.create_scene(pid, "S", plotline="MAIN").id
    lanes = db.ensure_timeline_lanes(pid)
    assert [ln.name for ln in lanes] == ["Main"]
    assert db.get_scene_by_id(sid).plotline == "Main"


def test_get_scene_chapters_strips_whitespace():
    """get_scene_chapters mirrors get_scene_acts: padded labels are stripped and
    de-duplicated, so ' Ch1 ' and 'Ch1' are one chapter."""
    db = Database()
    pid = db.create_project("P").id
    db.create_scene(pid, "A", chapter="Ch1")
    db.create_scene(pid, "B", chapter=" Ch1 ")
    assert db.get_scene_chapters(pid) == ["Ch1"]


def test_delete_lane_unassigns_scenes_not_deletes():
    db = Database()
    pid = db.create_project("P").id
    sid = db.create_scene(pid, "S", plotline="Main").id
    lane = db.create_timeline_lane(pid, "Main")
    db.delete_timeline_lane(lane.id)
    assert db.get_timeline_lanes(pid) == []
    assert db.get_scene_by_id(sid) is not None             # scene kept
    assert db.get_scene_by_id(sid).plotline == ""          # just unassigned


def test_link_dedup_and_reverse():
    db = Database()
    pid = db.create_project("P").id
    a = db.create_scene(pid, "A").id
    b = db.create_scene(pid, "B").id
    l1 = db.add_timeline_link(pid, a, b)
    l2 = db.add_timeline_link(pid, b, a)   # reverse duplicate
    assert l2.id == l1.id
    assert db.add_timeline_link(pid, a, a) is None  # self-link rejected


def test_remove_link_keeps_scenes():
    db = Database()
    pid = db.create_project("P").id
    a = db.create_scene(pid, "A").id
    b = db.create_scene(pid, "B").id
    link = db.add_timeline_link(pid, a, b)
    db.remove_timeline_link(link.id)
    assert db.get_timeline_links(pid) == []
    assert len(db.get_all_scenes(pid)) == 2


# ==========================================================================
# View — opens, clean state, moves, colours, links
# ==========================================================================


def test_timeline_opens_without_crashing():
    db = Database()
    pid = db.create_project("P").id
    db.create_scene(pid, "Opening", plotline="Main")
    view = PlotTimelineView(db, pid)
    assert hasattr(view, "refresh")
    assert "Main" in [name for _, name, _ in view._rows]
    assert set(view._card_by_scene) == {s.id for s in db.get_all_scenes(pid)}


def test_new_project_has_clean_timeline():
    db = Database()
    pid = db.create_project("Fresh").id
    view = PlotTimelineView(db, pid)
    assert view._rows == []
    assert view._card_by_scene == {}
    assert db.get_timeline_lanes(pid) == []
    assert db.get_timeline_links(pid) == []


def test_event_move_within_lane_persists():
    db = Database()
    pid = db.create_project("P").id
    s1 = db.create_scene(pid, "First", plotline="Main").id
    s2 = db.create_scene(pid, "Second", plotline="Main").id
    view = PlotTimelineView(db, pid)
    # Drop s2 at column 0 (front of the timeline axis).
    view._handle_drop(s2, 14, _row_y(view, "Main") + 10)
    # Timeline order is now timeline-specific: s2 moves to the front WITHOUT
    # touching Scene.sort_order (the Outline/Manuscript order is preserved).
    assert db.get_timeline_order(pid)[0] == s2
    assert [s.id for s in db.get_all_scenes(pid)] == [s1, s2]   # Outline intact


def test_event_move_between_lanes_persists():
    db = Database()
    pid = db.create_project("P").id
    sid = db.create_scene(pid, "Floating").id
    db.create_timeline_lane(pid, "Romance", color_label="purple")
    view = PlotTimelineView(db, pid)
    view._handle_drop(sid, 14, _row_y(view, "Romance") + 10)
    assert db.get_scene_by_id(sid).plotline == "Romance"


def test_event_color_persists():
    db = Database()
    pid = db.create_project("P").id
    sid = db.create_scene(pid, "S", plotline="Main").id
    view = PlotTimelineView(db, pid)
    view._set_event_color(sid, "blue")
    assert db.get_scene_by_id(sid).color_label == "blue"


def test_link_creation_and_color_persist():
    db = Database()
    pid = db.create_project("P").id
    a = db.create_scene(pid, "A", plotline="Main").id
    b = db.create_scene(pid, "B", plotline="Main").id
    view = PlotTimelineView(db, pid)
    view._start_link(a)
    view._finish_link(b, "causality", "green")
    links = db.get_timeline_links(pid)
    assert len(links) == 1
    assert links[0].color_label == "green" and links[0].link_type == "causality"
    # Change link colour.
    db.set_timeline_link_color(links[0].id, "red")
    assert db.get_timeline_links(pid)[0].color_label == "red"


def test_link_has_endpoints_for_drawing():
    db = Database()
    pid = db.create_project("P").id
    a = db.create_scene(pid, "A", plotline="Main").id
    b = db.create_scene(pid, "B", plotline="Main").id
    db.add_timeline_link(pid, a, b, color_label="teal")
    view = PlotTimelineView(db, pid)
    # Both endpoints have positioned card rects so the line can be drawn.
    assert a in view._card_rects and b in view._card_rects


def test_lane_color_and_collapse_persist():
    db = Database()
    pid = db.create_project("P").id
    db.create_scene(pid, "S", plotline="Main")
    view = PlotTimelineView(db, pid)
    lane = db.get_timeline_lanes(pid)[0]
    view._set_lane_color(lane.id, "cyan" if False else "teal")
    view._toggle_lane(lane.id)
    reloaded = db.get_timeline_lanes(pid)[0]
    assert reloaded.color_label == "teal"
    assert reloaded.collapsed is True


# ==========================================================================
# Export / import round-trip
# ==========================================================================


def test_export_contains_timeline_data():
    db = Database()
    pid = db.create_project("P").id
    a = db.create_scene(pid, "A", plotline="Main", color_label="blue").id
    b = db.create_scene(pid, "B", plotline="Main").id
    db.create_timeline_lane(pid, "Main", color_label="green")
    db.add_timeline_link(pid, a, b, color_label="amber", link_type="setup_payoff")
    data = json.loads(export_json(db, pid))
    assert "plot_timeline" in data
    assert [l["name"] for l in data["plot_timeline"]["lanes"]] == ["Main"]
    assert len(data["plot_timeline"]["links"]) == 1
    assert data["plot_timeline"]["links"][0]["color_label"] == "amber"


def test_timeline_import_round_trip():
    db = Database()
    pid = db.create_project("P").id
    a = db.create_scene(pid, "Alpha", plotline="Main").id
    b = db.create_scene(pid, "Beta", plotline="Main").id
    db.create_timeline_lane(pid, "Main", color_label="green")
    db.add_timeline_link(pid, a, b, color_label="purple", link_type="echo")
    data = json.loads(export_json(db, pid))
    new_pid = import_json(db, data)
    assert [l.name for l in db.get_timeline_lanes(new_pid)] == ["Main"]
    new_links = db.get_timeline_links(new_pid)
    assert len(new_links) == 1
    assert new_links[0].color_label == "purple" and new_links[0].link_type == "echo"


# ==========================================================================
# Project switching isolation
# ==========================================================================


def test_project_switch_no_timeline_leak():
    from logosforge.ui.main_window import MainWindow
    db = Database()
    a = db.create_project("A").id
    db.create_scene(a, "A-event", plotline="A-Plot")
    db.create_timeline_lane(a, "A-Plot", color_label="green")
    b = db.create_project("B").id
    win = MainWindow(db, a)
    win.sidebar_buttons["Timeline"].click()
    view_a = win.content_area
    assert isinstance(view_a, PlotTimelineView)
    assert "A-Plot" in [n for _, n, _ in view_a._rows]

    win._switch_project(b)
    win.sidebar_buttons["Timeline"].click()
    view_b = win.content_area
    assert isinstance(view_b, PlotTimelineView)
    names_b = [n for _, n, _ in view_b._rows]
    assert "A-Plot" not in names_b
    assert view_b._card_by_scene == {}            # no leaked events
    assert db.get_timeline_lanes(b) == []          # B has its own (empty) lanes


def test_timeline_refreshes_on_data_change_without_section_switch():
    from logosforge.ui.main_window import MainWindow
    db = Database()
    pid = db.create_project("P").id
    db.create_scene(pid, "S1", plotline="Main")
    win = MainWindow(db, pid)
    win.sidebar_buttons["Timeline"].click()
    view = win.content_area
    assert hasattr(view, "refresh")
    calls = []
    view.refresh = lambda *a, **k: calls.append(1)
    win._on_data_changed()
    assert calls, "Timeline did not refresh on data change"
