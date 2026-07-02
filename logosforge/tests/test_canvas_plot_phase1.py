"""Phase 1: Plot → Canvas Plot rename, decoupling, and project isolation.

This phase delivers naming + the dedicated Canvas Plot data boundary (a new
project-owned store, independent of Timeline/scenes) + project-switch
correctness. The free canvas editing UI itself lands in a later phase.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database


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


def _win(db, pid):
    from logosforge.ui.main_window import MainWindow
    return MainWindow(db, pid)


# ==========================================================================
# 1. Naming — "Canvas Plot" shows; internal key/handlers unchanged
# ==========================================================================


def test_sidebar_shows_canvas_plot_label():
    db = Database()
    pid = db.create_project("P").id
    win = _win(db, pid)
    # Internal key stays "Plot" (handlers/highlight/tests rely on it); the
    # button + handler are preserved...
    assert "Plot" in win.sidebar_buttons
    assert win._nav_section_handlers["Plot"].__name__ == "_show_plot"
    # ...the visible label is still "Canvas Plot"...
    assert win.sidebar_buttons["Plot"].text() == "Canvas Plot"
    # ...but Canvas Plot is now DEFERRED: removed from the visible navigation in
    # favor of the block-based Outline (non-destructive; data untouched).
    assert "Plot" not in win._nav_labels
    assert win.sidebar_buttons["Plot"].property("nav_available") is False


def test_display_name_map():
    from logosforge.ui.main_window import _display_name
    assert _display_name("Plot") == "Canvas Plot"
    assert _display_name("Timeline") == "Timeline"      # unchanged
    assert _display_name("Outline") == "Outline"


def test_canvas_plot_section_opens():
    from logosforge.ui.canvas_plot_view import CanvasPlotView
    db = Database()
    pid = db.create_project("P").id
    win = _win(db, pid)
    win.sidebar_buttons["Plot"].click()
    assert win._current_section == "Plot"
    assert isinstance(win.content_area, CanvasPlotView)


# ==========================================================================
# 2. Decoupling — Timeline still works and is a different view
# ==========================================================================


def test_timeline_unchanged_and_distinct_from_canvas_plot():
    from logosforge.ui.canvas_plot_view import CanvasPlotView
    from logosforge.ui.plot_timeline_view import PlotTimelineView
    db = Database()
    pid = db.create_project("P").id
    db.create_scene(pid, "S1", plotline="Main")
    win = _win(db, pid)
    win.sidebar_buttons["Timeline"].click()
    assert isinstance(win.content_area, PlotTimelineView)
    win.sidebar_buttons["Plot"].click()
    assert isinstance(win.content_area, CanvasPlotView)
    # The two sections are different view classes (not mirrors).
    assert CanvasPlotView is not PlotTimelineView


def test_timeline_label_still_timeline():
    db = Database()
    pid = db.create_project("P").id
    win = _win(db, pid)
    assert win.sidebar_buttons["Timeline"].text() == "Timeline"


# ==========================================================================
# 3. Canvas Plot storage — dedicated, project-owned, isolated
# ==========================================================================


def test_canvas_plot_store_is_project_scoped():
    db = Database()
    a = db.create_project("A").id
    b = db.create_project("B").id
    db.create_canvas_plot_node(a, title="A idea", x=10, y=10)
    assert [n.title for n in db.get_canvas_plot_nodes(a)] == ["A idea"]
    assert db.get_canvas_plot_nodes(b) == []        # no leak into B


def test_new_project_has_empty_canvas_plot():
    db = Database()
    a = db.create_project("A").id
    db.create_canvas_plot_node(a, title="A idea")
    b = db.create_project("Fresh").id
    assert db.get_canvas_plot_nodes(b) == []


def test_canvas_plot_node_crud_and_persistence(tmp_path):
    path = str(tmp_path / "c.db")
    db = Database(path)
    pid = db.create_project("P").id
    node = db.create_canvas_plot_node(
        pid, title="Theme", body="loyalty", x=5, y=6, color_label="amber",
        group_label="themes",
    )
    db.update_canvas_plot_node(node.id, x=120.0, y=80.0, title="Theme v2")
    # Reload from disk: free-form position/text/colour persisted.
    db2 = Database(path)
    nodes = db2.get_canvas_plot_nodes(pid)
    assert len(nodes) == 1
    n = nodes[0]
    assert n.title == "Theme v2" and n.x == 120.0 and n.y == 80.0
    assert n.color_label == "amber" and n.group_label == "themes"


def test_canvas_plot_node_is_not_scene_derived():
    # A node needs no scene — Canvas Plot owns its own free blocks.
    db = Database()
    pid = db.create_project("P").id
    node = db.create_canvas_plot_node(pid, title="Free block")
    assert node.scene_id is None
    assert db.get_all_scenes(pid) == []   # no scene created as a side effect


def test_delete_and_clear_canvas_plot():
    db = Database()
    pid = db.create_project("P").id
    n1 = db.create_canvas_plot_node(pid, title="one")
    db.create_canvas_plot_node(pid, title="two")
    db.delete_canvas_plot_node(n1.id)
    assert [n.title for n in db.get_canvas_plot_nodes(pid)] == ["two"]
    db.clear_canvas_plot(pid)
    assert db.get_canvas_plot_nodes(pid) == []


# ==========================================================================
# 4. Project switching — no stale Canvas Plot state
# ==========================================================================


def test_project_switch_no_canvas_plot_leak():
    db = Database()
    a = db.create_project("A").id
    db.create_canvas_plot_node(a, title="A-only idea")
    b = db.create_project("B").id
    win = _win(db, a)
    win.sidebar_buttons["Plot"].click()
    assert win._current_section == "Plot"
    win._switch_project(b)
    # Active section rebuilt for B; B owns no Canvas Plot nodes.
    assert win._project_id == b
    assert db.get_canvas_plot_nodes(b) == []
    # A's node is untouched and still A-scoped.
    assert [n.title for n in db.get_canvas_plot_nodes(a)] == ["A-only idea"]
