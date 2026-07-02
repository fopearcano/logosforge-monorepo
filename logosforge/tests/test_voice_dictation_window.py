"""Voice Dictation floating window — toggle, safety, transcript preservation.

The Voice Dictation panel lives in a floating, **modeless, resizable**
``VoiceDictationWindow`` parented to the main window (never a parentless
top-level window — the rule that keeps it clear of the old standalone-Pages
fullscreen-minimize bug). One instance exists; the menu action / Ctrl+Shift+V
toggle shows and hides it repeatedly; the panel's Hide button, the title-bar
close and Esc all *hide* it. Hiding while recording stops the session safely
and keeps the transcript preview; commit stays manual and auto-commit stays
OFF by default. All headless with the mock backend — no cloud, no real audio.
"""

from __future__ import annotations

import array
import warnings

import pytest
from PySide6.QtWidgets import QApplication, QTextEdit

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.voice.editor_commit import EditorCommitTarget
from logosforge.voice.types import VoiceStatus

_SR = 16000


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


def _speech(ms: int) -> bytes:
    n = int(_SR * ms / 1000)
    return array.array("h", [6000 if i % 2 else -6000 for i in range(n)]).tobytes()


def _silence(ms: int) -> bytes:
    n = int(_SR * ms / 1000)
    return b"\x00\x00" * n


def _enable_voice(mock=True):
    from logosforge.settings import get_manager
    mgr = get_manager()
    mgr.set("enable_voice_mode", True)
    if mock:
        mgr.set("voice_backend_mode", "mock")
        mgr.set("voice_silence_ms", 300)


def _window(parent=None):
    from logosforge.ui.voice_panel import VoiceDictationWindow, VoicePanel
    panel = VoicePanel(commit_target=EditorCommitTarget())
    return VoiceDictationWindow(panel, parent=parent)


def _main_window(engine="novel"):
    from logosforge.ui.main_window import MainWindow
    db = Database()
    pid = db.create_project("P", narrative_engine=engine).id
    return MainWindow(db, pid)


def _dictate(panel) -> None:
    """Drive the mock backend through one finalized segment."""
    panel.start()
    rec = panel._controller._recorder
    rec.feed_chunk(_speech(500))
    rec.feed_chunk(_silence(400))
    panel.stop()


# ==========================================================================
# 1-2  Default visibility / openability
# ==========================================================================


def test_window_hidden_by_default_when_feature_disabled():
    win = _main_window()
    assert win._voice_window.isVisible() is False
    assert win._voice_panel.isVisible() is False


def test_window_opens_when_feature_enabled():
    _enable_voice()
    win = _main_window()
    win._toggle_voice_panel()
    assert win._voice_window.isVisible() is True


def test_window_opens_even_when_disabled_with_inert_message():
    # Toggling with the flag off must still work both ways (the old strip
    # could be shown in this state but never hidden again — the Alpha bug).
    win = _main_window()
    win._toggle_voice_panel()
    assert win._voice_window.isVisible() is True
    assert "off" in win._voice_panel._status_label.text().lower()
    assert win._voice_panel._start_btn.isEnabled() is False
    win._toggle_voice_panel()
    assert win._voice_window.isVisible() is False      # it hides again


# ==========================================================================
# 3-8  Toggle / close / single instance
# ==========================================================================


def test_toggle_opens_then_hides_then_reopens():
    _enable_voice()
    win = _main_window()
    win._toggle_voice_panel()
    assert win._voice_window.isVisible() is True       # 3: opens
    win._toggle_voice_panel()
    assert win._voice_window.isVisible() is False      # 4: hides
    win._toggle_voice_panel()
    assert win._voice_window.isVisible() is True       # 5: reopens


def test_panel_hide_button_hides_window():
    _enable_voice()
    win = _main_window()
    win._toggle_voice_panel()
    win._voice_panel._hide_btn.click()
    assert win._voice_window.isVisible() is False


def test_titlebar_close_hides_not_destroys():
    _enable_voice()
    win = _main_window()
    win._toggle_voice_panel()
    win._voice_window.close()                          # title-bar close
    assert win._voice_window.isVisible() is False
    win._toggle_voice_panel()                          # same instance reopens
    assert win._voice_window.isVisible() is True


def test_escape_reject_hides_window():
    _enable_voice()
    win = _main_window()
    win._toggle_voice_panel()
    win._voice_window.reject()                         # Esc path
    assert win._voice_window.isVisible() is False


def test_repeated_toggles_keep_single_instance():
    from logosforge.ui.voice_panel import VoiceDictationWindow
    _enable_voice()
    win = _main_window()
    first = win._voice_window
    for _ in range(6):
        win._toggle_voice_panel()
    assert win._voice_window is first                  # 8: same object
    assert len(win.findChildren(VoiceDictationWindow)) == 1   # 7: no duplicates


# ==========================================================================
# 9-13  Transcript preservation / manual commit / recording policy
# ==========================================================================


def test_preview_persists_across_hide_show():
    _enable_voice()
    win = _main_window()
    win._toggle_voice_panel()
    win._voice_panel._preview.setPlainText("dictated draft")
    win._toggle_voice_panel()                          # hide
    win._toggle_voice_panel()                          # show again
    assert win._voice_panel._preview.toPlainText() == "dictated draft"


def test_clear_removes_preview():
    _enable_voice()
    win = _main_window()
    win._toggle_voice_panel()
    win._voice_panel._preview.setPlainText("dictated draft")
    win._voice_panel.clear_preview()
    assert win._voice_panel._preview.toPlainText() == ""


def test_commit_is_manual_only():
    _enable_voice()
    dlg = _window()
    panel = dlg.panel
    editor = QTextEdit()
    panel._commit.note_focus(editor)
    _dictate(panel)
    assert "mock transcript" in panel._preview.toPlainText()
    assert editor.toPlainText() == ""                  # nothing auto-inserted
    assert panel.commit() is True
    assert "mock transcript" in editor.toPlainText()


def test_auto_commit_default_off():
    from logosforge.settings import DEFAULTS
    assert DEFAULTS["voice_auto_commit"] is False
    dlg = _window()
    assert dlg.panel._auto_commit.isChecked() is False


def test_hide_while_recording_stops_safely_and_keeps_preview():
    _enable_voice()
    win = _main_window()
    win._toggle_voice_panel()
    panel = win._voice_panel
    panel.start()
    rec = panel._controller._recorder
    rec.feed_chunk(_speech(500))
    rec.feed_chunk(_silence(400))                      # finalized segment
    assert panel._status in (VoiceStatus.LISTENING, VoiceStatus.PROCESSING,
                             VoiceStatus.TRANSCRIPT_READY)
    win._toggle_voice_panel()                          # hide while active
    assert win._voice_window.isVisible() is False
    assert panel._controller.status == VoiceStatus.OFF  # stopped safely
    assert "mock transcript" in panel._preview.toPlainText()  # kept


def test_escape_while_recording_stops_safely():
    _enable_voice()
    dlg = _window()
    panel = dlg.panel
    dlg.toggle()
    panel.start()
    dlg.reject()
    assert panel._controller.status == VoiceStatus.OFF
    assert dlg.isVisible() is False


# ==========================================================================
# 14-16  Window safety
# ==========================================================================


def test_window_is_parented_never_parentless():
    _enable_voice()
    win = _main_window()
    before = set(QApplication.topLevelWidgets())
    win._toggle_voice_panel()
    new_visible = [w for w in (set(QApplication.topLevelWidgets()) - before)
                   if w.isVisible()]
    # The only new top-level-ish widget is the dialog itself — parented to
    # the main window (a parented dialog is never a parentless window).
    assert new_visible in ([], [win._voice_window])
    assert win._voice_window.parent() is win
    assert win._voice_window.isModal() is False        # modeless


def test_toggle_never_touches_main_window_state():
    _enable_voice()
    win = _main_window()
    calls = {"min": 0, "hide": 0, "close": 0}
    win.showMinimized = lambda: calls.__setitem__("min", calls["min"] + 1)  # type: ignore
    win.hide = lambda: calls.__setitem__("hide", calls["hide"] + 1)         # type: ignore
    win.close = lambda: calls.__setitem__("close", calls["close"] + 1)      # type: ignore
    for _ in range(4):
        win._toggle_voice_panel()
    assert calls == {"min": 0, "hide": 0, "close": 0}


def test_toggle_does_not_dirty_project_or_reenable_pages():
    _enable_voice()
    win = _main_window()
    win._dirty = False
    win._toggle_voice_panel()
    win._toggle_voice_panel()
    assert win._dirty is False                         # no project mutation
    assert "Pages" not in win._nav_labels              # stays disabled
    assert "Pages" not in win.sidebar_buttons


def test_window_resizable_with_readable_preview():
    dlg = _window()
    assert dlg.isSizeGripEnabled() is True
    assert dlg.minimumWidth() >= 400 and dlg.minimumHeight() >= 240
    assert dlg.maximumWidth() > dlg.minimumWidth()     # actually resizable
    assert dlg.panel._preview.minimumHeight() >= 100   # readable preview


def test_window_not_auto_shown_and_no_auto_recording():
    _enable_voice()
    win = _main_window()
    assert win._voice_window.isVisible() is False      # no auto-show on launch
    win._toggle_voice_panel()
    panel = win._voice_panel
    assert panel._controller is None                   # no auto-start
    assert panel._status in (VoiceStatus.OFF, VoiceStatus.DISABLED)


# ==========================================================================
# 17  Backend behavior unchanged (settings + LAN guard + dictation pipeline)
# ==========================================================================


def test_backend_defaults_and_settings_unchanged():
    from logosforge.settings import DEFAULTS
    assert DEFAULTS["enable_voice_mode"] is False
    assert DEFAULTS["voice_backend_mode"] == "disabled"
    assert DEFAULTS["voice_lan_base_url"] == ""
    assert DEFAULTS["voice_lan_auth_token"] == ""


def test_lan_public_urls_still_blocked():
    from logosforge.voice.lan_server import LanWhisperTranscriber
    from logosforge.voice.types import LAN_PUBLIC_URL_MESSAGE, VoiceSettings
    s = VoiceSettings(enabled=True, backend_mode="lan_server",
                      lan_base_url="https://abc.ngrok.io")
    ok, msg = LanWhisperTranscriber(s).availability()
    assert ok is False and msg == LAN_PUBLIC_URL_MESSAGE


def test_voice_and_lan_settings_reachable_in_panel():
    _enable_voice()
    dlg = _window()
    panel = dlg.panel
    labels = [panel._backend_combo.itemText(i)
              for i in range(panel._backend_combo.count())]
    assert "Local PC" in labels and "Local LAN Server" in labels
    # Selecting LAN mode exposes the LAN URL field + health check.
    idx = next(i for i in range(panel._backend_combo.count())
               if panel._backend_combo.itemData(i) == "lan_server")
    panel._backend_combo.setCurrentIndex(idx)
    assert panel._config_edit.isVisibleTo(panel) is True
    assert panel._lan_check_btn.isVisibleTo(panel) is True


def test_privacy_note_shown_in_panel():
    from logosforge.voice.types import PRIVACY_NOTE
    dlg = _window()
    assert dlg.panel.findChild(object, "voicePrivacyNote").text() == PRIVACY_NOTE
    assert "local transcription" in PRIVACY_NOTE
