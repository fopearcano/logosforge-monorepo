"""POST-FIX INTEGRITY GATE — Voice Dictation floating window + Preferences.

Audit-driven gate for the two Alpha UI fixes. The focused behavior suites
(`test_voice_dictation_window.py`, `test_preferences_dialog.py`) cover the
basics; this gate pins the remaining contract points found in the audit:
single shared entry point, no duplicate signal connections after repeated
toggles (no double commits / double status appends), error-state rendering,
plain-text commit into the real mode editors (WritingCoreView + the Graphic
Novel comics-script field — without breaking its commit-on-focus-out
persistence), modeless/movable window structure, fullscreen-safety with the
voice window open, deferred-classification hooks still inert, no
cloud/realtime/tunnel references in the voice UI code, and Preferences
reopen-persistence. All headless; no cloud, no real audio.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTextEdit

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge.voice.editor_commit import EditorCommitTarget
from logosforge.voice.types import VoiceStatus


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


def _enable_voice():
    from logosforge.settings import get_manager
    mgr = get_manager()
    mgr.set("enable_voice_mode", True)
    mgr.set("voice_backend_mode", "mock")


def _main_window(engine="novel"):
    from logosforge.ui.main_window import MainWindow
    db = Database()
    pid = db.create_project("P", narrative_engine=engine).id
    return db, pid, MainWindow(db, pid)


# ==========================================================================
# Entry points + duplicate-connection symptoms
# ==========================================================================


def test_single_shared_entry_point_with_unique_shortcut():
    from PySide6.QtGui import QAction
    _db, _pid, win = _main_window()
    voice_actions = [a for a in win.findChildren(QAction)
                     if "Dexter" in a.text()]
    assert len(voice_actions) == 1                      # one menu action
    assert voice_actions[0].shortcut().toString() == "Ctrl+Shift+V"
    _enable_voice()
    voice_actions[0].trigger()                          # routes to the toggle
    assert win._voice_window.isVisible() is True
    voice_actions[0].trigger()
    assert win._voice_window.isVisible() is False


def test_no_duplicate_commit_after_repeated_toggles():
    _enable_voice()
    _db, _pid, win = _main_window()
    for _ in range(6):                                  # re-toggle repeatedly
        win._toggle_voice_panel()
    panel = win._voice_panel
    editor = QTextEdit()
    win._voice_commit.note_focus(editor)
    panel._preview.setPlainText("once only")
    assert panel.commit() is True
    assert editor.toPlainText().count("once only") == 1  # exactly one insert


def test_no_duplicate_status_or_transcript_after_repeated_toggles():
    _enable_voice()
    _db, _pid, win = _main_window()
    for _ in range(6):
        win._toggle_voice_panel()
    panel = win._voice_panel
    panel._final_text.emit("segment-a")                 # one emission …
    assert panel._preview.toPlainText().count("segment-a") == 1  # … one append
    panel._status_changed.emit(VoiceStatus.LISTENING.value)
    assert "listening" in panel._status_label.text().lower()


def test_error_status_renders_in_panel():
    _enable_voice()
    _db, _pid, win = _main_window()
    panel = win._voice_panel
    panel._status_changed.emit(VoiceStatus.ERROR.value)
    assert "error" in panel._status_label.text().lower()


def test_commit_with_empty_preview_is_inert():
    _enable_voice()
    _db, _pid, win = _main_window()
    panel = win._voice_panel
    editor = QTextEdit()
    win._voice_commit.note_focus(editor)
    panel._preview.clear()
    assert panel.commit() is False
    assert editor.toPlainText() == ""
    assert panel._commit_btn.isEnabled() is False


# ==========================================================================
# Floating-window structure (modeless, movable, editing continues)
# ==========================================================================


def test_window_structure_modeless_movable_dialog():
    _enable_voice()
    _db, _pid, win = _main_window()
    dlg = win._voice_window
    assert dlg.isWindow() is True                       # real floating window
    assert dlg.isModal() is False                       # modeless
    flags = dlg.windowFlags()
    assert flags & Qt.WindowType.Dialog                 # plain dialog window
    assert not (flags & Qt.WindowType.FramelessWindowHint)   # movable chrome
    assert not (flags & Qt.WindowType.WindowStaysOnTopHint)  # no aggressive flag
    assert dlg.parent() is win


def test_editing_continues_while_window_open():
    _enable_voice()
    _db, _pid, win = _main_window()
    win._toggle_voice_panel()                           # window open
    editor = QTextEdit()
    cur = editor.textCursor()
    cur.insertText("still typing")                      # editor not blocked
    assert editor.toPlainText() == "still typing"
    assert win._voice_window.isVisible() is True


# ==========================================================================
# Commit into the REAL mode editors
# ==========================================================================


def test_commit_into_writing_core_scene_editor():
    # Novel / Screenplay / Stage / Series Manuscript = WritingCoreView.
    _enable_voice()
    db, pid, win = _main_window("novel")
    sid = ss.create_scene(db, pid, act="Act 1", chapter="Chapter 1",
                          title="S").id
    win._show_manuscript()
    view = win.content_area
    editor = view._editors[sid]
    win._voice_commit.note_focus(editor)
    panel = win._voice_panel
    panel._preview.setPlainText("dictated prose")
    assert panel.commit() is True
    assert "dictated prose" in editor.toPlainText()     # plain text, no format


def test_commit_into_graphic_novel_field_keeps_field_working():
    # GN now uses the SHARED Manuscript editor: voice inserts at the cursor
    # inside the focused scene editor; the panel position resolves from the
    # cursor (gnb.panel_at_offset) and the body still persists afterwards.
    _enable_voice()
    db, pid, win = _main_window("graphic_novel")
    from logosforge import graphic_novel_outline as gno
    sid = ss.create_scene(db, pid, act="Act 1", chapter="Chapter 1",
                          title="S").id
    gno.add_page(db, sid)
    gno.add_panel(db, sid, 0)
    win._show_manuscript()
    from logosforge.ui.writing_core_view import WritingCoreView
    view = win.content_area
    assert isinstance(view, WritingCoreView)             # shared editor
    editor = view._editors[sid]
    from logosforge import graphic_novel_blocks as gnb
    offset = gnb.panel_offset(editor.toPlainText(), 0, 0)
    cursor = editor.textCursor()
    cursor.setPosition(offset)
    editor.setTextCursor(cursor)
    win._voice_commit.note_focus(editor)
    panel = win._voice_panel
    panel._preview.setPlainText("a windswept rooftop")
    assert panel.commit() is True
    assert "a windswept rooftop" in editor.toPlainText() # inserted in place
    view._save_scene(sid)                                # editor persists
    body = gnb.load_scene_script(db, sid)
    assert "a windswept rooftop" in body.pages[0].panels[0].visual_description


def test_commit_with_no_editor_is_nonblocking():
    _enable_voice()
    _db, _pid, win = _main_window()
    win._voice_commit.clear()
    panel = win._voice_panel
    panel._preview.setPlainText("orphan transcript")
    assert panel.commit() is False                      # message, no crash
    assert "editor" in panel._status_label.text().lower()
    assert panel._preview.toPlainText() == "orphan transcript"  # kept


def test_classification_hooks_still_deferred():
    # No auto-formatting / classification / Outline-PSYKE routing crept in.
    tgt = EditorCommitTarget()
    for hook, args in (
        ("insert_as_screenplay_dialogue", ("HERO", "line")),
        ("insert_as_action", ("runs",)),
        ("insert_as_note", ("note",)),
        ("send_to_outline", ("beat",)),
        ("send_to_psyke", ("lore",)),
        ("send_to_graphic_novel_panel", (1, "visual_description", "x")),
        ("send_to_stage_direction", ("exits",)),
        ("send_to_series_outline", ("arc",)),
    ):
        with pytest.raises(NotImplementedError):
            getattr(tgt, hook)(*args)


# ==========================================================================
# Fullscreen safety with the voice window open + scope guards
# ==========================================================================


def test_gn_sections_safe_with_voice_window_open():
    _enable_voice()
    _db, _pid, win = _main_window("graphic_novel")
    calls = {"min": 0, "hide": 0, "close": 0}
    win.showMinimized = lambda: calls.__setitem__("min", calls["min"] + 1)  # type: ignore
    win.hide = lambda: calls.__setitem__("hide", calls["hide"] + 1)         # type: ignore
    win.close = lambda: calls.__setitem__("close", calls["close"] + 1)      # type: ignore
    win._toggle_voice_panel()                           # voice window open
    win._show_plan()                                    # GN Outline
    win._show_manuscript()                              # GN comics editor
    win._show_gn_pages()                                # inert Pages route
    assert calls == {"min": 0, "hide": 0, "close": 0}
    assert "Pages" not in win._nav_labels               # still disabled
    assert win._voice_window.isVisible() is True        # untouched by nav


def test_project_switch_with_window_open_is_isolated():
    _enable_voice()
    from logosforge.ui.main_window import MainWindow
    db = Database()
    a = db.create_project("A", narrative_engine="novel").id
    b = db.create_project("B", narrative_engine="novel").id
    win = MainWindow(db, a)
    win._toggle_voice_panel()
    panel = win._voice_panel
    panel.start()
    win._voice_commit.note_focus(QTextEdit())
    win._switch_project(b)
    assert panel._controller.status == VoiceStatus.OFF  # stopped on switch
    assert win._voice_commit.active_editor() is None    # target forgotten


def test_voice_ui_code_has_no_cloud_realtime_or_tunnel_refs():
    import inspect
    from logosforge.ui import voice_panel as mod
    src = inspect.getsource(mod).lower()
    for banned in ("openai", "realtime api", "ngrok", "wss://",
                   "speech.googleapis", "azure.cognitiveservices"):
        assert banned not in src, banned


# ==========================================================================
# Preferences — reopen persistence + no unsafe windows
# ==========================================================================


def _prefs(parent=None):
    from logosforge.ui.settings_dialog import SettingsDialog
    return SettingsDialog(on_theme_changed=lambda name: None, parent=parent)


def test_preferences_reopen_shows_saved_settings():
    dlg = _prefs()
    dlg._conn_enabled.setChecked(True)
    dlg._default_folder_input.setText("/tmp/keepers")
    dlg.accept()
    dlg2 = _prefs()                                     # fresh instance
    assert dlg2._conn_enabled.isChecked() is True
    assert dlg2._default_folder_input.text() == "/tmp/keepers"


def test_preferences_creates_no_parentless_window():
    _db, _pid, win = _main_window()
    before = set(QApplication.topLevelWidgets())
    dlg = _prefs(parent=win)
    dlg.show()
    new_visible = [w for w in (set(QApplication.topLevelWidgets()) - before)
                   if w.isVisible()]
    assert new_visible in ([], [dlg])
    assert dlg.parent() is win
    dlg.close()


def test_preferences_scroll_keeps_all_sections_reachable():
    from PySide6.QtWidgets import QScrollArea
    dlg = _prefs()
    scroll = dlg.findChild(QScrollArea, "prefsScrollArea")
    content = scroll.widget()
    # Every settings section lives inside the scrollable content => reachable
    # by scrolling regardless of screen height.
    for w in (dlg._provider_widget, dlg._conn_enabled, dlg._conn_actions_list,
              dlg._default_folder_input):
        assert content.isAncestorOf(w)
