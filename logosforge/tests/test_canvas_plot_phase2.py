"""Phase 2: Canvas Plot as a free zoomable visual board.

Verifies the QGraphicsView-based board: create/move/edit/delete blocks persist
to the project-owned CanvasPlotNode store; zoom + reset; per-project view state;
and full project isolation (switch / new / reload).
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.ui.canvas_plot_view import CanvasPlotView, _BlockItem


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


# ==========================================================================
# Opens / empty state
# ==========================================================================


def test_canvas_opens_empty():
    db = Database()
    pid = db.create_project("P").id
    view = CanvasPlotView(db, pid)
    assert view._items == {}
    assert hasattr(view, "refresh")
    # It's a real graphics board.
    from PySide6.QtWidgets import QGraphicsView, QGraphicsScene
    assert isinstance(view._view, QGraphicsView)
    assert isinstance(view._scene, QGraphicsScene)


# ==========================================================================
# Create
# ==========================================================================


def test_create_block_persists():
    db = Database()
    pid = db.create_project("P").id
    view = CanvasPlotView(db, pid)
    view._new_block()
    assert len(db.get_canvas_plot_nodes(pid)) == 1
    assert len(view._items) == 1
    # New block is a movable, selectable graphics item.
    item = next(iter(view._items.values()))
    assert isinstance(item, _BlockItem)


def test_multiple_blocks_do_not_exactly_overlap():
    db = Database()
    pid = db.create_project("P").id
    view = CanvasPlotView(db, pid)
    view._new_block()
    view._new_block()
    view._new_block()
    positions = [(n.x, n.y) for n in db.get_canvas_plot_nodes(pid)]
    assert len(set(positions)) == len(positions)   # all distinct


# ==========================================================================
# Move
# ==========================================================================


def test_move_block_persists():
    db = Database()
    pid = db.create_project("P").id
    view = CanvasPlotView(db, pid)
    view._new_block()
    nid = next(iter(view._items))
    view._persist_position(nid, 412.0, 286.0)
    node = db.get_canvas_plot_nodes(pid)[0]
    assert (node.x, node.y) == (412.0, 286.0)


# ==========================================================================
# Edit
# ==========================================================================


def test_edit_block_persists(monkeypatch):
    db = Database()
    pid = db.create_project("P").id
    view = CanvasPlotView(db, pid)
    view._new_block()
    nid = next(iter(view._items))

    # Stub the modal dialog: accept with new values.
    import logosforge.ui.canvas_plot_view as cpv

    class _FakeDialog:
        def __init__(self, node, parent=None): ...
        def exec(self):
            from PySide6.QtWidgets import QDialog
            return QDialog.DialogCode.Accepted
        def values(self):
            return {"title": "Theme", "body": "duty vs love",
                    "group_label": "theme", "color_label": "amber"}

    monkeypatch.setattr(cpv, "_BlockEditDialog", _FakeDialog)
    view._edit_block(nid)
    node = db.get_canvas_plot_nodes(pid)[0]
    assert node.title == "Theme"
    assert node.body == "duty vs love"
    assert node.group_label == "theme"
    assert node.color_label == "amber"


# ==========================================================================
# Delete (confirmed, non-silent)
# ==========================================================================


def test_delete_block_requires_confirmation(monkeypatch):
    db = Database()
    pid = db.create_project("P").id
    view = CanvasPlotView(db, pid)
    view._new_block()
    nid = next(iter(view._items))
    from PySide6.QtWidgets import QMessageBox
    import logosforge.ui.canvas_plot_view as cpv

    # Decline first -> nothing deleted.
    monkeypatch.setattr(cpv.QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    view._delete_block(nid)
    assert len(db.get_canvas_plot_nodes(pid)) == 1
    # Confirm -> deleted.
    monkeypatch.setattr(cpv.QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    view._delete_block(nid)
    assert db.get_canvas_plot_nodes(pid) == []


# ==========================================================================
# Zoom / reset
# ==========================================================================


def test_zoom_in_out_and_reset():
    db = Database()
    pid = db.create_project("P").id
    view = CanvasPlotView(db, pid)
    view._apply_zoom_factor(1.15)
    assert view._zoom > 1.0
    assert view._zoom_label.text().endswith("%")
    view.reset_view()
    assert abs(view._zoom - 1.0) < 1e-6
    assert view._zoom_label.text() == "100%"


def test_zoom_is_clamped():
    db = Database()
    pid = db.create_project("P").id
    view = CanvasPlotView(db, pid)
    for _ in range(40):
        view._apply_zoom_factor(1.15)
    assert view._zoom <= 4.0
    for _ in range(60):
        view._apply_zoom_factor(1 / 1.15)
    assert view._zoom >= 0.25


# ==========================================================================
# Persistence: reload + switch section back + per-project view state
# ==========================================================================


def test_reload_project_restores_blocks_and_positions(tmp_path):
    path = str(tmp_path / "c.db")
    db = Database(path)
    pid = db.create_project("P").id
    view = CanvasPlotView(db, pid)
    view._new_block()
    nid = next(iter(view._items))
    view._persist_position(nid, 250.0, 175.0)
    # Reopen the DB (simulates app restart) and rebuild the view.
    db2 = Database(path)
    view2 = CanvasPlotView(db2, pid)
    assert len(view2._items) == 1
    node = db2.get_canvas_plot_nodes(pid)[0]
    assert (node.x, node.y) == (250.0, 175.0)


def test_switch_section_and_back_preserves_board():
    from logosforge.ui.main_window import MainWindow
    db = Database()
    pid = db.create_project("P").id
    win = MainWindow(db, pid)
    win.sidebar_buttons["Plot"].click()
    win.content_area._new_block()
    assert len(db.get_canvas_plot_nodes(pid)) == 1
    # Leave to another section and come back — board reloads from the store.
    win.sidebar_buttons["Notes"].click()
    win.sidebar_buttons["Plot"].click()
    assert isinstance(win.content_area, CanvasPlotView)
    assert len(win.content_area._items) == 1


def test_view_zoom_state_persists_per_project():
    db = Database()
    pid = db.create_project("P").id
    view = CanvasPlotView(db, pid)
    view._apply_zoom_factor(1.15)
    saved = db.get_project_settings(pid).get("canvas_plot_view")
    assert saved and abs(saved["zoom"] - view._zoom) < 1e-6
    # A fresh view for the same project restores the zoom.
    view2 = CanvasPlotView(db, pid)
    assert abs(view2._zoom - view._zoom) < 1e-6


# ==========================================================================
# Project isolation
# ==========================================================================


def test_switch_project_loads_correct_board():
    from logosforge.ui.main_window import MainWindow
    db = Database()
    a = db.create_project("A").id
    db.create_canvas_plot_node(a, title="A-block", x=10, y=10)
    b = db.create_project("B").id
    win = MainWindow(db, a)
    win.sidebar_buttons["Plot"].click()
    assert len(win.content_area._items) == 1
    win._switch_project(b)
    win.sidebar_buttons["Plot"].click()
    assert isinstance(win.content_area, CanvasPlotView)
    assert win.content_area._items == {}            # B's board is empty
    assert db.get_canvas_plot_nodes(b) == []
    # A's block untouched.
    assert [n.title for n in db.get_canvas_plot_nodes(a)] == ["A-block"]
