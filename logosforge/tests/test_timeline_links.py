"""Timeline: colored lanes, event/lane data, event↔event links, and the new
event→Act/Chapter structure links + badges. Project-isolated; export-aware.
"""

from __future__ import annotations

import json
import warnings

import pytest
from PySide6.QtWidgets import QApplication, QLabel

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.export import export_json
from logosforge.ui.main_window import MainWindow
from logosforge.ui.plot_timeline_view import PlotTimelineView, _EventCard


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


def _proj(db):
    return db.create_project("P", narrative_engine="novel").id


# ==========================================================================
# Lanes + colour
# ==========================================================================


def test_create_and_color_lane_persists():
    db = Database()
    pid = _proj(db)
    lane = db.create_timeline_lane(pid, "Main", "green")
    db.set_timeline_lane_color(lane.id, "violet")
    db.rename_timeline_lane(lane.id, "Main Arc")
    lanes = db.get_timeline_lanes(pid)
    assert lanes[0].name == "Main Arc"
    assert lanes[0].color_label == "violet"


def test_view_builds_colored_lane_bands():
    db = Database()
    pid = _proj(db)
    db.create_scene(pid, "S", plotline="Main", content="x")
    db.create_timeline_lane(pid, "Main", "amber")
    view = PlotTimelineView(db, pid)
    # One band per rendered row; the Main lane band carries a colour.
    assert view._lane_bands
    assert any(chex for _, _, chex in view._lane_bands)


# ==========================================================================
# Events + event↔event links
# ==========================================================================


def test_event_color_persists():
    db = Database()
    pid = _proj(db)
    s = db.create_scene(pid, "S", plotline="Main", content="x").id
    db.update_scene_color(s, "cyan")
    assert db.get_scene_by_id(s).color_label == "cyan"


def test_link_event_to_event_cross_lane_with_color():
    db = Database()
    pid = _proj(db)
    a = db.create_scene(pid, "A", plotline="Main", content="x").id
    b = db.create_scene(pid, "B", plotline="Sub", content="y").id
    link = db.add_timeline_link(pid, a, b, color_label="cyan",
                               link_type="causality")
    assert link is not None and link.color_label == "cyan"
    assert len(db.get_timeline_links(pid)) == 1


def test_remove_event_link_keeps_events():
    db = Database()
    pid = _proj(db)
    a = db.create_scene(pid, "A", content="x").id
    b = db.create_scene(pid, "B", content="y").id
    link = db.add_timeline_link(pid, a, b)
    db.remove_timeline_link(link.id)
    assert db.get_timeline_links(pid) == []
    assert db.get_scene_by_id(a) is not None
    assert db.get_scene_by_id(b) is not None


# ==========================================================================
# Event → Act / Chapter / Scene structure links
# ==========================================================================


def test_link_event_to_act_and_chapter():
    db = Database()
    pid = _proj(db)
    s = db.create_scene(pid, "S", act="Act I", chapter="Ch1", content="x").id
    db.add_timeline_structure_link(pid, s, "act", "Act II")
    db.add_timeline_structure_link(pid, s, "chapter", "Ch2")
    links = {(l.target_type, l.target_ref)
             for l in db.get_timeline_structure_links(s)}
    assert links == {("act", "Act II"), ("chapter", "Ch2")}


def test_structure_link_idempotent_and_validated():
    db = Database()
    pid = _proj(db)
    s = db.create_scene(pid, "S", content="x").id
    db.add_timeline_structure_link(pid, s, "act", "Act I")
    db.add_timeline_structure_link(pid, s, "act", "Act I")
    assert len(db.get_timeline_structure_links(s)) == 1
    # Invalid target_type is rejected.
    assert db.add_timeline_structure_link(pid, s, "scene", "x") is None


def test_link_event_to_scene_via_view():
    db = Database()
    pid = _proj(db)
    a = db.create_scene(pid, "A", content="x").id
    b = db.create_scene(pid, "B", content="y").id
    view = PlotTimelineView(db, pid)
    view._link_to_scene_direct(a, b)
    assert len(db.get_timeline_links(pid)) == 1


def test_add_structure_link_via_view():
    db = Database()
    pid = _proj(db)
    s = db.create_scene(pid, "S", act="Act I", content="x").id
    view = PlotTimelineView(db, pid)
    view._add_structure_link(s, "act", "Act I")
    assert len(db.get_timeline_structure_links(s)) == 1


def test_remove_structure_link_keeps_event():
    db = Database()
    pid = _proj(db)
    s = db.create_scene(pid, "S", act="Act I", content="x").id
    link = db.add_timeline_structure_link(pid, s, "act", "Act I")
    db.remove_timeline_structure_link(link.id)
    assert db.get_timeline_structure_links(s) == []
    assert db.get_scene_by_id(s) is not None


def test_structure_badge_appears_on_card():
    db = Database()
    pid = _proj(db)
    s = db.create_scene(pid, "S", act="Act I", plotline="Main", content="x").id
    db.add_timeline_structure_link(pid, s, "act", "Act II")
    view = PlotTimelineView(db, pid)
    labels = " ".join(w.text() for w in view.findChildren(QLabel))
    assert "🔗" in labels and "Act II" in labels


def test_missing_structure_target_safe():
    db = Database()
    pid = _proj(db)
    s = db.create_scene(pid, "S", plotline="Main", content="x").id
    # Link to an Act no scene uses → stored, rendered, no crash.
    db.add_timeline_structure_link(pid, s, "act", "Ghost Act")
    view = PlotTimelineView(db, pid)
    assert view._struct_by_scene.get(s)            # present
    view.refresh()                                  # must not raise


# ==========================================================================
# Cleanup + isolation
# ==========================================================================


def test_delete_scene_cleans_timeline_and_structure_links():
    db = Database()
    pid = _proj(db)
    a = db.create_scene(pid, "A", content="x").id
    b = db.create_scene(pid, "B", content="y").id
    db.add_timeline_link(pid, a, b)
    db.add_timeline_structure_link(pid, a, "act", "Act I")
    db.delete_scene(a)
    assert db.get_timeline_links(pid) == []                 # orphan link gone
    assert db.get_all_timeline_structure_links(pid) == []   # structure link gone


def test_links_do_not_leak_across_projects():
    db = Database()
    a = _proj(db)
    b = _proj(db)
    sa = db.create_scene(a, "A", content="x").id
    db.add_timeline_structure_link(a, sa, "act", "A-ACT")
    db.create_timeline_lane(a, "A-LANE", "green")
    assert db.get_all_timeline_structure_links(b) == []
    assert db.get_timeline_lanes(b) == []


def test_project_switch_reloads_timeline(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    a = _proj(db)
    db.create_scene(a, "A-scene", plotline="A-LANE", content="x")
    db.create_timeline_lane(a, "A-LANE", "green")
    b = _proj(db)
    win = MainWindow(db, a)
    win.sidebar_buttons["Timeline"].click()
    assert isinstance(win.content_area, PlotTimelineView)
    assert [ln.name for ln in win.content_area._lanes] == ["A-LANE"]
    win._switch_project(b)
    win.sidebar_buttons["Timeline"].click()
    assert win.content_area._lanes == []                    # B starts empty
    assert win.content_area._struct_by_scene == {}


# ==========================================================================
# Export
# ==========================================================================


def test_export_includes_timeline_links_no_cross_project():
    db = Database()
    a = _proj(db)
    b = _proj(db)
    s = db.create_scene(a, "Open", act="Act I", plotline="Main", content="x").id
    db.create_timeline_lane(a, "Main", "green")
    s2 = db.create_scene(a, "Next", content="y").id
    db.add_timeline_link(a, s, s2, color_label="cyan")
    db.add_timeline_structure_link(a, s, "act", "Act I")
    db.create_scene(b, "B-SCENE-SENTINEL", plotline="B-LANE", content="z")
    db.create_timeline_lane(b, "B-LANE")

    blob = export_json(db, a)
    tl = json.loads(blob)["plot_timeline"]
    assert [ln["name"] for ln in tl["lanes"]] == ["Main"]
    assert tl["links"][0]["color_label"] == "cyan"
    assert {"source_order": 1, "source_title": "Open",
            "target_type": "act", "target_ref": "Act I"} in tl["structure_links"]
    assert "B-SCENE-SENTINEL" not in blob and "B-LANE" not in blob
