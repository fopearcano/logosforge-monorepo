"""Live theme propagation to the Assistant (panel + dock).

Changing Appearance must re-theme the Assistant immediately — its child widgets
carry inline stylesheets, so the global stylesheet alone leaves them stale until
restart. AssistantPanel.apply_theme() re-runs those inline styles; AssistantDock
delegates to it; MainWindow._switch_theme drives the whole thing.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication, QLabel

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.ui import theme
from logosforge.ui.assistant_view import AssistantPanel
from logosforge.ui.assistant_dock import AssistantDock
from logosforge.ui.main_window import MainWindow

DARK = "Dark"
WARM = "Light (Warm)"
GREEN = "Light (Green)"


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
    # Keep theme changes from touching the real preferences file.
    import logosforge.preferences as prefs
    monkeypatch.setattr(prefs, "set_string", lambda *a, **k: None, raising=False)
    yield
    settings._instance = None
    theme.set_palette(DARK)


def _panel(db):
    theme.set_palette(DARK)
    pid = db.create_project("P").id
    panel = AssistantPanel(db, pid)
    return panel


# ==========================================================================
# apply_theme re-colours the panel's inline-styled children
# ==========================================================================


def test_panel_registers_themed_widgets():
    db = Database()
    panel = _panel(db)
    assert len(panel._themed_widgets) >= 10        # header/buttons/inputs/response
    assert hasattr(panel, "apply_theme")


def test_apply_theme_recolours_response_and_input():
    db = Database()
    panel = _panel(db)
    before = panel._response_output.styleSheet()
    theme.set_palette(WARM)
    panel.apply_theme()
    after = panel._response_output.styleSheet()
    assert after != before                          # changed
    assert theme.BG_PANEL in after                  # uses the warm palette
    assert theme.BG_PANEL in panel._ctx_viewer.styleSheet()   # input/context field


def test_apply_theme_recolours_buttons_and_tabs():
    db = Database()
    panel = _panel(db)
    send_dark = panel._send_btn.styleSheet()
    tab_dark = panel._assistant_mode_btn.styleSheet()
    theme.set_palette(WARM)
    panel.apply_theme()
    assert panel._send_btn.styleSheet() != send_dark     # Generate button
    assert panel._assistant_mode_btn.styleSheet() != tab_dark  # mode tab


def test_apply_theme_recolours_header_title():
    db = Database()
    panel = _panel(db)
    title = next((w for w in panel.findChildren(QLabel) if w.text() == "Assistant"),
                 None)
    assert title is not None
    before = title.styleSheet()
    theme.set_palette(WARM)
    panel.apply_theme()
    assert title.styleSheet() != before
    assert theme.TEXT_PRIMARY in title.styleSheet()


# ==========================================================================
# Dock delegates; cycling palettes keeps working
# ==========================================================================


def test_dock_apply_theme_delegates_to_panel():
    db = Database()
    panel = _panel(db)
    dock = AssistantDock(panel)
    assert hasattr(dock, "apply_theme")
    theme.set_palette(GREEN)
    dock.apply_theme()
    assert theme.BG_PANEL in panel._response_output.styleSheet()


def test_cycle_dark_warm_green():
    db = Database()
    panel = _panel(db)
    dock = AssistantDock(panel)
    for name in (WARM, GREEN, DARK):
        theme.set_palette(name)
        dock.apply_theme()
        assert theme.BG_PANEL in panel._response_output.styleSheet()


# ==========================================================================
# Through the real MainWindow path
# ==========================================================================


def test_switch_theme_updates_assistant_live(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    win = MainWindow(db, db.create_project("P").id)
    panel = win._assistant_panel
    win._switch_theme(WARM)
    assert theme.BG_PANEL in panel._response_output.styleSheet()
    win._switch_theme(GREEN)
    assert theme.BG_PANEL in panel._response_output.styleSheet()


def test_switching_sections_does_not_revert_theme(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    win = MainWindow(db, db.create_project("P").id)
    panel = win._assistant_panel
    win._switch_theme(WARM)
    warm_bg = theme.BG_PANEL
    win.sidebar_buttons["Outline"].click()          # navigate
    win.sidebar_buttons["Timeline"].click()
    assert warm_bg in panel._response_output.styleSheet()   # still warm


def test_overlay_panel_updates(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    win = MainWindow(db, db.create_project("P").id)
    panel = win._assistant_panel
    panel._overlay_mode = True                       # floating/overlay mode
    win._switch_theme(WARM)
    # The panel (same object whether docked or floating) is re-themed.
    assert theme.BG_PANEL in panel._response_output.styleSheet()
    panel.apply_theme()                              # idempotent, no crash


def test_saved_theme_persists_for_restart(tmp_path):
    from logosforge.settings import get_manager
    db = Database(str(tmp_path / "sp.db"))
    win = MainWindow(db, db.create_project("P").id)
    win._switch_theme(GREEN)
    assert str(get_manager().get("appearance")) == GREEN   # saved → restart loads it
    # Simulate restart: applying the saved palette yields Green colours.
    theme.set_palette(GREEN)
    assert theme.current_palette() == GREEN


def test_apply_theme_is_idempotent():
    db = Database()
    panel = _panel(db)
    theme.set_palette(WARM)
    panel.apply_theme()
    first = panel._response_output.styleSheet()
    panel.apply_theme()
    assert panel._response_output.styleSheet() == first      # stable, no crash
