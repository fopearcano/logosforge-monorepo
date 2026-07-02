"""Dependency / language / Dexter's Room naming update.

requirements.txt now installs the modules the voice/export implementation
actually uses (faster-whisper + sounddevice alongside reportlab/python-docx;
whisper.cpp stays a local executable, never a pip package); the user-facing
voice workspace is renamed **Dexter's Room** (internal VoiceRoom* names
retained; Billy stays Billy, Logos stays Logos); and the language selector
covers the full OpenAI Whisper list — stored by code, aliases resolved
internally, invalid values falling back to Auto detect, with the code
flowing through to every backend and into transcript metadata.
"""

from __future__ import annotations

import re
import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.voice.types import (
    LANGUAGE_ALIASES,
    WHISPER_LANGUAGES,
    TranscriptSegment,
    VoiceSettings,
    normalize_language,
)


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
# 1-6  requirements.txt
# ==========================================================================


def _requirements():
    return open("requirements.txt", encoding="utf-8").read()


def test_requirements_include_voice_and_export_modules():
    text = _requirements()
    for needed in ("faster-whisper", "sounddevice", "reportlab",
                   "python-docx"):
        assert needed in text, needed
    # whisper.cpp is a local EXECUTABLE, never a pip dependency.
    assert not re.search(r"^\s*whisper[-_.]?cpp", text,
                         re.MULTILINE | re.IGNORECASE)
    assert "executable" in text.lower()                # documented instead


def test_requirements_have_no_duplicates_and_no_dev_deps():
    names = []
    for line in _requirements().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        names.append(re.split(r"[><=;\[ ]", line, 1)[0].lower())
    assert len(names) == len(set(names))               # no duplicate lines
    assert "pytest" not in names                       # dev deps stay out


def test_startup_needs_no_model_files_and_degrades_gracefully():
    # Voice disabled by default: building the app-side settings requires no
    # model; an enabled-but-unconfigured backend reports a message, never
    # raises.
    from logosforge.settings import get_manager
    settings = VoiceSettings.from_store(get_manager().get)
    assert settings.enabled is False
    from logosforge.voice.setup import build_backend_profile
    profile = build_backend_profile(VoiceSettings(
        enabled=True, backend_mode="local_process", model_path=""))
    assert profile.ready is False and profile.message


# ==========================================================================
# 7-12  Dexter's Room naming
# ==========================================================================


def _ui_window():
    from logosforge.settings import get_manager
    mgr = get_manager()
    mgr.set("enable_voice_mode", True)
    mgr.set("voice_backend_mode", "mock")
    from logosforge.ui.main_window import MainWindow
    db = Database()
    pid = db.create_project("P", narrative_engine="novel").id
    win = MainWindow(db, pid)
    win._toggle_voice_panel()
    return db, pid, win


def test_dexters_room_labels_in_ui():
    from PySide6.QtGui import QAction
    _db, _pid, win = _ui_window()
    panel = win._voice_panel
    assert "Dexter's Room" in panel._room_label.text()           # header
    assert "Dexter's Room" in win._voice_window.windowTitle()    # window
    actions = [a for a in win.findChildren(QAction)
               if a.text() == "Dexter's Room"]
    assert len(actions) == 1                                     # menu label
    assert "Enter Dexter's Room" in actions[0].toolTip()         # tooltip


def test_privacy_note_uses_dexters_room_wording():
    from logosforge.voice.types import PRIVACY_NOTE
    assert PRIVACY_NOTE.startswith("Dexter's Room uses local transcription.")
    assert "Audio is processed on this device." in PRIVACY_NOTE
    _db, _pid, win = _ui_window()
    note = win._voice_panel.findChild(object, "voicePrivacyNote")
    assert note.text() == PRIVACY_NOTE


def test_billy_and_logos_names_unchanged_no_dester():
    _db, _pid, win = _ui_window()
    panel = win._voice_panel
    assert panel._billy_label.text() == "Billy:"                 # Billy stays
    import subprocess
    out = subprocess.run(
        ["grep", "-ri", "dester", "logosforge", "docs"],
        capture_output=True, text=True)
    assert out.stdout.strip() == ""                              # no typo
    # Internal VoiceRoom names intentionally retained (low-risk policy).
    from logosforge.voice.room import VoiceRoomStateMachine
    assert VoiceRoomStateMachine                                  # importable


def test_docs_use_dexters_room_as_user_facing_name():
    voice_doc = open("docs/VOICE_MVP.md", encoding="utf-8").read()
    assert "Dexter's Room" in voice_doc
    assert "Billy" in voice_doc                                  # Billy stays


# ==========================================================================
# 13-23  Full Whisper language list
# ==========================================================================


def test_language_list_complete_and_auto_first():
    from logosforge.voice.setup import LANGUAGES
    codes = [code for code, _name in LANGUAGES]
    assert codes[0] == "auto"
    for required in ("en", "it", "zh", "yue", "haw", "jw", "nn", "yi"):
        assert required in codes, required
    assert len(codes) == len(WHISPER_LANGUAGES) == 101           # 100 + auto
    # Alphabetical by display name after auto.
    names = [name for code, name in LANGUAGES[1:]]
    assert names == sorted(names)


def test_language_selector_displays_names_and_stores_codes():
    from logosforge.ui.voice_setup_dialog import VoiceSetupDialog
    _db, _pid, win = _ui_window()
    dlg = VoiceSetupDialog(parent=win)
    combo = dlg._language
    # "Use project language" (the default mode) + Auto detect + 100 codes.
    assert combo.count() == 102
    assert combo.itemData(0) == "project"
    assert combo.itemText(1) == "Auto detect"
    assert combo.currentData() == "project"                      # default
    idx_en = combo.findData("en")
    assert combo.itemText(idx_en) == "English (en)"              # friendly
    combo.setCurrentIndex(combo.findData("yue"))
    from logosforge.settings import get_manager
    assert get_manager().get("voice_language") == "yue"          # by code
    assert get_manager().get("voice_language_mode") == "explicit"
    combo.setCurrentIndex(combo.findData("project"))             # and back
    assert get_manager().get("voice_language_mode") == "project"


def test_invalid_saved_language_falls_back_to_auto_with_message():
    from logosforge.settings import get_manager
    from logosforge.ui.voice_setup_dialog import VoiceSetupDialog
    get_manager().set("voice_language", "klingon")
    _db, _pid, win = _ui_window()
    dlg = VoiceSetupDialog(parent=win)
    assert dlg._language.currentData() == "auto"
    assert "no longer supported" in dlg._result.toPlainText()
    assert get_manager().get("voice_language") == "auto"         # repaired
    settings = VoiceSettings.from_store(get_manager().get)
    assert settings.language == "auto"


def test_old_values_and_aliases_normalize():
    for value, expected in (("auto", "auto"), ("en", "en"), ("it", "it"),
                            ("", "auto"), (None, "auto"),
                            ("Mandarin", "zh"), ("cantonese", "yue"),
                            ("Castilian", "es"), ("valencian", "ca"),
                            ("Flemish", "nl"), ("haitian", "ht"),
                            ("Burmese", "my"), ("moldovan", "ro"),
                            ("Panjabi", "pa"), ("pushto", "ps"),
                            ("Sinhalese", "si"), ("French", "fr")):
        assert normalize_language(value) == expected, value
    for alias, code in LANGUAGE_ALIASES.items():
        assert code in WHISPER_LANGUAGES, alias


# ==========================================================================
# 24-30  Backend pass-through + transcript metadata
# ==========================================================================


def test_faster_whisper_auto_maps_to_none():
    import inspect
    from logosforge.voice import transcriber as t
    src = inspect.getsource(t.FasterWhisperTranscriber)
    assert 'None if language in ("", "auto")' in src             # auto -> None


def test_whisper_cpp_language_argument_construction(tmp_path):
    import os
    import stat
    exe = tmp_path / "main"
    exe.write_text('#!/bin/sh\necho "$@" >&2\necho "ok"\n')
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    model = tmp_path / "model.bin"
    model.write_bytes(b"x")
    from logosforge.voice.transcriber import WhisperCppTranscriber

    def args_for(language):
        import subprocess as sp
        calls = {}
        real_run = sp.run

        def spy(cmd, **kw):
            calls["cmd"] = cmd
            return real_run(cmd, **kw)
        sp_run, sp.run = sp.run, spy
        try:
            settings = VoiceSettings(backend_mode="whisper_cpp",
                                     executable_path=str(exe),
                                     model_path=str(model),
                                     language=language)
            WhisperCppTranscriber(settings).transcribe(
                b"\x00\x00" * 1600, sample_rate=16000)
        finally:
            sp.run = sp_run
        return calls["cmd"]

    assert "-l" not in args_for("auto")                          # auto omits
    cmd = args_for("yue")
    assert cmd[cmd.index("-l") + 1] == "yue"                     # code passes
    cmd = args_for("haw")
    assert cmd[cmd.index("-l") + 1] == "haw"


def test_mock_backend_and_segment_language_metadata():
    from logosforge.voice.recorder import MockRecorder
    from logosforge.voice.session import VoiceSessionController
    from logosforge.voice.transcriber import MockTranscriber
    finals = []

    def run(language):
        finals.clear()
        settings = VoiceSettings(enabled=True, backend_mode="mock",
                                 language=language, silence_ms=300)
        controller = VoiceSessionController(
            settings, MockRecorder(), MockTranscriber(),
            on_final_transcript=finals.append)
        controller.start_voice_session()
        import array
        speech = array.array(
            "h", [6000 if i % 2 else -6000 for i in range(8000)]).tobytes()
        controller._recorder.feed_chunk(speech)
        controller._recorder.feed_chunk(b"\x00\x00" * 8000)
        controller.stop_voice_session()
        return finals[0]

    seg = run("it")                                              # selected
    assert seg.selected_language_code == "it"
    assert seg.language_source == "user_selected"
    assert seg.language == "it"                                  # mock keeps it
    seg = run("auto")                                            # auto path
    assert seg.selected_language_code == "auto"
    # The mock reports a language, so auto resolves to backend_detected.
    assert seg.detected_language_code == "en"
    assert seg.language_source == "backend_detected"


def test_language_domain_is_injection_proof_and_no_shell():
    # Whatever is stored, normalize_language yields a member of the fixed
    # list — the whisper.cpp argv can only ever receive a known code.
    for hostile in ("; rm -rf /", "$(reboot)", "en; ls", "yue\nx", "''"):
        assert normalize_language(hostile) in WHISPER_LANGUAGES
    import inspect
    from logosforge.voice import transcriber as t
    assert "shell=True" not in inspect.getsource(t)      # argv lists only


def test_segment_metadata_defaults_do_not_break_history():
    seg = TranscriptSegment(text="plain")
    assert seg.selected_language_code == ""
    assert seg.detected_language_code == ""
    assert seg.language_source == ""
    from logosforge.voice.history import VoiceTranscriptHistory
    history = VoiceTranscriptHistory()
    history.start_session(1)
    entry = history.add_final_segment(seg, project_id=1,
                                      writing_mode="novel")
    assert entry.text == "plain"                                 # unaffected
