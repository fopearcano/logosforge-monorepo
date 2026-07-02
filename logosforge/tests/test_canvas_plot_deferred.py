"""Canvas Plot is deferred: hidden from normal navigation, data untouched.

The block-based Outline is the planning board now; Canvas Plot overlaps it
without a distinct purpose yet, so it is removed from the visible nav. Its
handler/button/data are preserved (non-destructive) and the app stays stable
even when historical Canvas Plot data exists.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.ui.main_window import MainWindow


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


def test_canvas_plot_hidden_from_navigation():
    db = Database()
    win = MainWindow(db, _proj(db))
    # Removed from the visible nav, marked unavailable.
    assert "Plot" not in win._nav_labels
    assert win.sidebar_buttons["Plot"].property("nav_available") is False


def test_canvas_plot_handler_and_button_preserved():
    # Non-destructive: handler + button stay registered (data reachable).
    db = Database()
    win = MainWindow(db, _proj(db))
    assert win._nav_section_handlers["Plot"].__name__ == "_show_plot"
    assert "Plot" in win.sidebar_buttons


def test_canvas_plot_stays_hidden_across_project_switch():
    db = Database()
    a = _proj(db)
    b = db.create_project("B", narrative_engine="screenplay",
                          default_writing_format="screenplay").id
    win = MainWindow(db, a)
    win._switch_project(b)
    assert "Plot" not in win._nav_labels
    assert win.sidebar_buttons["Plot"].property("nav_available") is False
    win._switch_project(a)
    assert "Plot" not in win._nav_labels


def test_hiding_canvas_plot_does_not_delete_data():
    db = Database()
    pid = _proj(db)
    node = db.create_canvas_plot_node(pid, x=10.0, y=20.0, title="IDEA")
    MainWindow(db, pid)   # building the window must not touch the data
    nodes = db.get_canvas_plot_nodes(pid)
    assert any(n.id == node.id for n in nodes)


def test_app_does_not_crash_with_existing_canvas_data():
    db = Database()
    pid = _proj(db)
    db.create_canvas_plot_node(pid, x=0.0, y=0.0, title="A")
    db.create_canvas_plot_node(pid, x=50.0, y=50.0, title="B")
    # Construction + a project switch with canvas data present must not raise.
    win = MainWindow(db, pid)
    win._switch_project(db.create_project("Other").id)
    win._switch_project(pid)
    assert win._project_id == pid
