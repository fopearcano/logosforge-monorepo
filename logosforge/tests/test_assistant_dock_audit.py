"""Post-Phase-1 stabilization audit: lock in the invariants verified after the
AssistantDock refactor so future changes can't silently regress them.

- exactly one AssistantPanel instance, surviving repeated section switches;
- no Qt lifetime errors / stray top-level windows while switching;
- chat state (prompt/response) is NOT reset by section switching;
- the panel stays connected to the current project after a project switch;
- the Scenes inline assistant remains a separate, isolated instance.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.ui.assistant_view import AssistantPanel
from logosforge.ui.main_window import MainWindow

_SECTIONS = [
    "_show_manuscript", "_show_plan", "_show_plot",
    "_show_timeline", "_show_graph", "_show_scenes",
]


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path, raising=False)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json", raising=False)
    yield
    settings._instance = None


def _window():
    db = Database()
    pid = db.create_project("P", narrative_engine="novel").id
    db.create_scene(pid, "S1", act="Act I", plotline="Main", content="Hello")
    win = MainWindow(db, pid)
    win.resize(1400, 900)
    return win, db, pid


def test_single_panel_survives_repeated_section_switches():
    win, _, _ = _window()
    win._toggle_assistant()
    start = id(win._assistant_panel)
    for _ in range(4):
        for show in _SECTIONS:
            getattr(win, show)()
            QApplication.instance().processEvents()
    # Scope to THIS window — the shared QApplication keeps prior test windows
    # alive, so a global allWidgets() scan would count their panels too.
    panels = win.findChildren(AssistantPanel)
    assert len(panels) == 1
    assert id(win._assistant_panel) == start


def test_no_lifetime_errors_or_stray_windows_on_switching():
    win, _, _ = _window()
    win._toggle_assistant()
    app = QApplication.instance()
    for show in _SECTIONS * 3:
        getattr(win, show)()
        app.processEvents()
        # Touching these would raise RuntimeError if a C++ object was deleted.
        assert win._assistant_dock.content() is win.content_area
        _ = win._assistant_panel.objectName()
    stray = [w for w in app.topLevelWidgets() if w.isVisible() and w is not win]
    assert stray == []


def test_chat_state_not_reset_by_section_switch():
    win, _, _ = _window()
    win._toggle_assistant()
    win._assistant_panel._prompt_input.setPlainText("draft prompt kept")
    win._assistant_panel._response_output.setPlainText("previous reply kept")
    win._show_plan(); QApplication.instance().processEvents()
    win._show_graph(); QApplication.instance().processEvents()
    assert win._assistant_panel._prompt_input.toPlainText() == "draft prompt kept"
    assert win._assistant_panel._response_output.toPlainText() == "previous reply kept"


def test_panel_reconnects_to_current_project_after_switch():
    win, db, _ = _window()
    pid2 = db.create_project("P2").id
    before = len(win.findChildren(AssistantPanel))
    win._switch_project(pid2)
    QApplication.instance().processEvents()
    assert win._assistant_panel._project_id == pid2
    # The project switch must not spawn an additional panel for this window.
    assert len(win.findChildren(AssistantPanel)) == before == 1


def test_scenes_inline_assistant_is_isolated_instance():
    win, _, _ = _window()
    win._show_scenes()
    QApplication.instance().processEvents()
    scenes = win.content_area
    assert hasattr(scenes, "_assist_panel")
    # The inline panel is NOT the global docked panel.
    assert scenes._assist_panel is not win._assistant_panel
    # Inline toggle still works without touching the global panel.
    scenes._toggle_assist_panel()
    assert scenes._assist_panel.isVisibleTo(scenes)
