"""General Preferences dialog — scrollable content, reachable bottom controls.

The Preferences (``SettingsDialog``) content lives inside a vertical
``QScrollArea``; the Close button row is sticky **outside** the scroll area so
the bottom controls stay reachable on small screens; the dialog clamps its
height to ~85% of the available screen geometry. Accept/Close persistence is
unchanged. All headless (Qt offscreen).
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication, QPushButton, QScrollArea

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


def _dialog(parent=None):
    from logosforge.ui.settings_dialog import SettingsDialog
    return SettingsDialog(on_theme_changed=lambda name: None, parent=parent)


# ==========================================================================
# 18-19  Scrollable content + sticky bottom button row
# ==========================================================================


def test_settings_content_is_inside_scroll_area():
    dlg = _dialog()
    scroll = dlg.findChild(QScrollArea, "prefsScrollArea")
    assert scroll is not None
    assert scroll.widgetResizable() is True
    content = scroll.widget()
    assert content is not None and content.objectName() == "prefsContent"
    # The settings controls actually live inside the scrollable content.
    assert content.isAncestorOf(dlg._conn_enabled)
    assert content.isAncestorOf(dlg._default_folder_input)


def test_close_button_is_outside_scroll_area():
    dlg = _dialog()
    scroll = dlg.findChild(QScrollArea, "prefsScrollArea")
    close_btn = dlg.findChild(QPushButton, "prefsCloseButton")
    assert close_btn is not None
    assert not scroll.widget().isAncestorOf(close_btn)   # sticky bottom row
    assert dlg.isAncestorOf(close_btn)


def test_close_button_row_reachable_within_window():
    # However tall the content, the dialog's own height is clamped and the
    # button row sits in the dialog (not in the scrolled content), so it can
    # always be clicked.
    dlg = _dialog()
    dlg.show()
    close_btn = dlg.findChild(QPushButton, "prefsCloseButton")
    assert close_btn.isVisibleTo(dlg)
    assert dlg.height() <= dlg.maximumHeight()


# ==========================================================================
# 20-22  Screen-geometry clamp / small screens / fullscreen safety
# ==========================================================================


def test_max_height_clamp_is_85_percent_of_available():
    from logosforge.ui.settings_dialog import SettingsDialog
    assert SettingsDialog._max_dialog_height(1000) == 850
    assert SettingsDialog._max_dialog_height(600) == 510
    # Tiny/odd geometry never collapses below a usable minimum.
    assert SettingsDialog._max_dialog_height(200) == 320


def test_dialog_max_height_respects_screen_geometry():
    dlg = _dialog()
    screen = dlg.screen() or QApplication.primaryScreen()
    if screen is None:
        pytest.skip("no screen in this environment")
    avail = screen.availableGeometry().height()
    assert dlg.maximumHeight() <= max(320, int(avail * 0.9))
    assert dlg.minimumHeight() >= 320


def test_dialog_usable_on_small_screen_height():
    from logosforge.ui.settings_dialog import SettingsDialog
    # Simulate a small laptop: the clamp yields a usable, reachable window.
    h = SettingsDialog._max_dialog_height(700)         # e.g. 768p minus chrome
    assert 320 <= h < 700


def test_open_preferences_does_not_minimize_main_window():
    from logosforge.ui.main_window import MainWindow
    db = Database()
    pid = db.create_project("N", narrative_engine="novel").id
    win = MainWindow(db, pid)
    calls = {"min": 0, "hide": 0, "close": 0}
    win.showMinimized = lambda: calls.__setitem__("min", calls["min"] + 1)  # type: ignore
    win.hide = lambda: calls.__setitem__("hide", calls["hide"] + 1)         # type: ignore
    win.close = lambda: calls.__setitem__("close", calls["close"] + 1)      # type: ignore
    dlg = _dialog(parent=win)
    dlg.show()                                          # modeless for the test
    assert dlg.parent() is win                          # parented, never orphan
    assert calls == {"min": 0, "hide": 0, "close": 0}
    dlg.close()


# ==========================================================================
# 23, 26  Accept/Close persistence + validation unchanged
# ==========================================================================


def test_accept_persists_settings_as_before():
    from logosforge.settings import get_manager
    dlg = _dialog()
    dlg._conn_enabled.setChecked(True)
    dlg._conn_writes.setChecked(True)
    dlg._default_folder_input.setText("/tmp/projects")
    dlg.accept()
    mgr = get_manager()
    assert mgr.get("connector_enabled") is True
    assert mgr.get("connector_allow_writes") is True
    assert mgr.get("default_projects_folder") == "/tmp/projects"


def test_accept_with_empty_provider_fields_safe():
    from logosforge.settings import get_manager
    dlg = _dialog()
    dlg.accept()                                        # nothing filled in
    mgr = get_manager()
    assert isinstance(mgr.get("ai_provider") or "", str)  # stored, no crash


def test_voice_validation_rules_unchanged():
    # Preferences/voice settings remain local/LAN-only: the public-URL guard
    # still rejects non-private hosts regardless of UI changes.
    from logosforge.voice.lan_server import LanWhisperTranscriber
    from logosforge.voice.types import VoiceSettings
    s = VoiceSettings(enabled=True, backend_mode="lan_server",
                      lan_base_url="https://example.com")
    ok, _msg = LanWhisperTranscriber(s).availability()
    assert ok is False


def test_lan_auth_token_not_displayed_in_preferences():
    # The LAN auth token is settings-only; no widget in the Preferences dialog
    # renders it in plain text.
    from PySide6.QtWidgets import QLineEdit
    from logosforge.settings import get_manager
    get_manager().set("voice_lan_auth_token", "sekrit-token")
    dlg = _dialog()
    for edit in dlg.findChildren(QLineEdit):
        if edit.echoMode() == QLineEdit.EchoMode.Normal:
            assert "sekrit-token" not in edit.text()
