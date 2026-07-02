"""Voice MVP Phase 8 — local setup, diagnostics, backend profiles, guardrails.

Backend profile validation (faster-whisper / whisper.cpp / mock / LAN) with
clear statuses, conservative performance profiles, safe microphone
diagnostics, a file-based local test transcription (never committed, never
retained, never sent to AI) and a copyable secrets-free diagnostics
summary. The Voice Room gates Start on a valid setup; everything degrades
to clear messages instead of crashes; nothing is installed or downloaded.
"""

from __future__ import annotations

import os
import stat
import sys
import types
import warnings
import wave

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.voice import setup as vs
from logosforge.voice.setup import (
    PERFORMANCE_PROFILES,
    SETUP_REQUIRED_MESSAGE,
    ST_DISABLED,
    ST_ERROR,
    ST_MISSING_DEPENDENCY,
    ST_MISSING_EXECUTABLE,
    ST_MISSING_MODEL,
    ST_READY,
    apply_performance_profile,
    build_backend_profile,
    diagnostics_summary,
    microphone_diagnostics,
    run_test_transcription,
)
from logosforge.voice.transcriber import WhisperCppTranscriber
from logosforge.voice.types import VoiceSettings


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


def _settings(**over):
    base = dict(enabled=True, backend_mode="mock")
    base.update(over)
    return VoiceSettings(**base)


def _stub_exe(tmp_path, body='#!/bin/sh\necho "stub transcript"\n',
              executable=True):
    exe = tmp_path / "whisper-main"
    exe.write_text(body)
    if executable:
        exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return str(exe)


def _model_file(tmp_path):
    model = tmp_path / "ggml-tiny.bin"
    model.write_bytes(b"\x00fakemodel")
    return str(model)


def _wav_file(tmp_path, seconds=0.3, rate=16000):
    path = tmp_path / "test.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\x10\x00" * int(rate * seconds))
    return str(path)


# ==========================================================================
# 1-8  Settings defaults / persistence / safety
# ==========================================================================


def test_voice_settings_default_disabled_with_safe_fallbacks():
    from logosforge.settings import DEFAULTS, get_manager
    assert DEFAULTS["enable_voice_mode"] is False
    assert DEFAULTS["voice_backend_mode"] == "disabled"
    assert DEFAULTS["voice_performance_profile"] == "balanced"
    assert DEFAULTS["voice_beam_size"] == 0
    settings = VoiceSettings.from_store(get_manager().get)
    assert settings.enabled is False
    assert settings.performance_profile == "balanced"


def test_setup_settings_persist():
    from logosforge.settings import get_manager
    mgr = get_manager()
    mgr.set("voice_backend_mode", "whisper_cpp")
    mgr.set("voice_whisper_model_path", "/m/odel")
    mgr.set("voice_whisper_executable_path", "/bin/whisper")
    mgr.set("voice_language", "it")
    mgr.set("voice_performance_profile", "accurate")
    settings = VoiceSettings.from_store(mgr.get)
    assert settings.resolved_backend_mode() == "whisper_cpp"
    assert settings.model_path == "/m/odel"
    assert settings.executable_path == "/bin/whisper"
    assert settings.language == "it"
    assert settings.performance_profile == "accurate"


def test_invalid_paths_never_crash():
    settings = _settings(backend_mode="whisper_cpp",
                         executable_path="/no/such/exe\x00bad",
                         model_path="/no/such/model")
    profile = build_backend_profile(settings)
    assert profile.status in (ST_MISSING_EXECUTABLE, ST_ERROR)
    settings2 = _settings(backend_mode="local_process",
                          model_path="/definitely/not/here")
    profile2 = build_backend_profile(settings2)
    assert profile2.status in (ST_MISSING_DEPENDENCY, ST_MISSING_MODEL)


# ==========================================================================
# 9-15  Backend diagnostics
# ==========================================================================


def test_faster_whisper_missing_dependency_reported():
    # CI has no faster-whisper installed.
    assert "faster_whisper" not in sys.modules
    status, msg = vs.check_faster_whisper(_settings(model_path="/m"))
    assert status == ST_MISSING_DEPENDENCY
    assert "faster-whisper" in msg


def test_faster_whisper_ready_with_mocked_module(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "faster_whisper",
                        types.ModuleType("faster_whisper"))
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    status, msg = vs.check_faster_whisper(
        _settings(model_path=str(model_dir)))
    assert status == ST_READY
    status2, _msg = vs.check_faster_whisper(_settings(model_path=""))
    assert status2 == ST_MISSING_MODEL


def test_whisper_cpp_statuses(tmp_path):
    model = _model_file(tmp_path)
    # Missing executable path / file.
    assert vs.check_whisper_cpp(_settings(model_path=model))[0] == \
        ST_MISSING_EXECUTABLE
    assert vs.check_whisper_cpp(_settings(
        executable_path=str(tmp_path / "nope"), model_path=model))[0] == \
        ST_MISSING_EXECUTABLE
    # Present but not runnable.
    not_exec = _stub_exe(tmp_path, executable=False)
    assert vs.check_whisper_cpp(_settings(
        executable_path=not_exec, model_path=model))[0] == ST_ERROR
    # Runnable but missing model.
    exe = _stub_exe(tmp_path)
    assert vs.check_whisper_cpp(_settings(
        executable_path=exe, model_path=""))[0] == ST_MISSING_MODEL
    # Fully configured -> ready (+ the safe --help probe responds).
    status, msg = vs.check_whisper_cpp(_settings(
        executable_path=exe, model_path=model))
    assert status == ST_READY
    ok, probe = vs.probe_whisper_cpp(exe)
    assert ok is True and "responded" in probe


def test_mock_backend_ready_but_labelled_test_only():
    profile = build_backend_profile(_settings(backend_mode="mock"))
    assert profile.ready is True
    assert "test" in profile.message.lower()
    assert any("production" in n.lower() for n in profile.notes)


def test_disabled_and_diagnostics_mutate_nothing():
    profile = build_backend_profile(_settings(enabled=False))
    assert profile.status == ST_DISABLED and not profile.ready
    from logosforge.db import Database
    db = Database()
    pid = db.create_project("N", narrative_engine="novel").id
    build_backend_profile(_settings())
    microphone_diagnostics(_settings())
    assert db.get_all_notes(pid) == []                  # read-only checks


# ==========================================================================
# 16-19  Microphone diagnostics
# ==========================================================================


def test_microphone_mock_backend_available():
    ok, msg = microphone_diagnostics(_settings(backend_mode="mock"))
    assert ok is True and msg


def test_microphone_unavailable_is_graceful():
    # local_process needs sounddevice — absent in CI: clear message, no crash.
    ok, msg = microphone_diagnostics(_settings(backend_mode="local_process"))
    assert ok is False
    assert msg                                          # actionable message


def test_microphone_failure_handled(monkeypatch):
    from logosforge.voice import recorder as rec
    monkeypatch.setattr(rec, "build_recorder",
                        lambda s: (_ for _ in ()).throw(RuntimeError("boom")))
    ok, msg = microphone_diagnostics(_settings())
    assert ok is False and "boom" in msg


# ==========================================================================
# 20-25  Test transcription
# ==========================================================================


def test_test_transcription_blocked_when_backend_missing():
    ok, msg = run_test_transcription(
        _settings(backend_mode="local_process", model_path=""))
    assert ok is False and msg


def test_test_transcription_mock_no_file_needed():
    ok, text = run_test_transcription(_settings(backend_mode="mock"))
    assert ok is True and "mock transcript" in text


def test_test_transcription_via_whisper_cpp_stub(tmp_path):
    exe = _stub_exe(tmp_path)
    model = _model_file(tmp_path)
    wav = _wav_file(tmp_path)
    settings = _settings(backend_mode="whisper_cpp", executable_path=exe,
                         model_path=model)
    ok, text = run_test_transcription(settings, wav_path=wav)
    assert ok is True and text == "stub transcript"


def test_test_transcription_failure_non_blocking(tmp_path):
    exe = _stub_exe(tmp_path, body="#!/bin/sh\necho bad >&2\nexit 3\n")
    model = _model_file(tmp_path)
    wav = _wav_file(tmp_path)
    settings = _settings(backend_mode="whisper_cpp", executable_path=exe,
                         model_path=model)
    ok, msg = run_test_transcription(settings, wav_path=wav)
    assert ok is False and "whisper.cpp" in msg


def test_whisper_cpp_transcriber_deletes_temp_audio(tmp_path, monkeypatch):
    import tempfile
    created = []
    real_mkstemp = tempfile.mkstemp

    def tracking_mkstemp(*a, **k):
        fd, path = real_mkstemp(*a, **k)
        created.append(path)
        return fd, path

    monkeypatch.setattr(tempfile, "mkstemp", tracking_mkstemp)
    exe = _stub_exe(tmp_path)
    settings = _settings(backend_mode="whisper_cpp", executable_path=exe,
                         model_path=_model_file(tmp_path))
    seg = WhisperCppTranscriber(settings).transcribe(
        b"\x00\x00" * 1600, sample_rate=16000)
    assert seg.text == "stub transcript"
    assert created and not any(os.path.exists(p) for p in created)


def test_test_transcription_never_commits():
    from logosforge.voice.editor_commit import EditorCommitTarget
    from PySide6.QtWidgets import QTextEdit
    editor = QTextEdit()
    target = EditorCommitTarget()
    target.note_focus(editor)
    ok, _text = run_test_transcription(_settings(backend_mode="mock"))
    assert ok is True
    assert editor.toPlainText() == ""                   # nothing inserted


# ==========================================================================
# 26-30  Performance profiles
# ==========================================================================


def test_profiles_map_to_safe_settings():
    fast = PERFORMANCE_PROFILES["fast_draft"]
    balanced = PERFORMANCE_PROFILES["balanced"]
    accurate = PERFORMANCE_PROFILES["accurate"]
    assert fast["voice_silence_ms"] < balanced["voice_silence_ms"] \
        <= accurate["voice_silence_ms"]
    assert fast["voice_max_segment_seconds"] \
        < balanced["voice_max_segment_seconds"] \
        < accurate["voice_max_segment_seconds"]
    assert fast["voice_beam_size"] <= 1
    assert accurate["voice_beam_size"] >= 5


def test_apply_profile_writes_settings_and_custom_keeps_values():
    from logosforge.settings import get_manager
    mgr = get_manager()
    assert apply_performance_profile(mgr.set, "fast_draft") is True
    assert mgr.get("voice_silence_ms") == 600
    assert mgr.get("voice_max_segment_seconds") == 12
    mgr.set("voice_silence_ms", 777)                    # user's custom value
    assert apply_performance_profile(mgr.set, "custom") is True
    assert mgr.get("voice_silence_ms") == 777           # untouched
    assert mgr.get("voice_performance_profile") == "custom"
    assert apply_performance_profile(mgr.set, "warp9") is False


def test_no_gpu_required_by_default():
    settings = VoiceSettings()
    assert settings.local_device in ("auto", "cpu")     # CPU-safe default
    profile = build_backend_profile(_settings())
    assert profile.device in ("auto", "cpu")


# ==========================================================================
# 31-35  Diagnostics summary
# ==========================================================================


def test_summary_excludes_secrets_and_transcripts():
    from logosforge.settings import get_manager
    mgr = get_manager()
    mgr.set("ai_api_key", "SECRET-API-KEY")
    mgr.set("voice_lan_auth_token", "SECRET-LAN-TOKEN")
    settings = _settings(lan_auth_token="SECRET-LAN-TOKEN")
    summary = diagnostics_summary(settings,
                                  last_error="PRIVATE TRANSCRIPT LINE? no")
    assert "SECRET-API-KEY" not in summary
    assert "SECRET-LAN-TOKEN" not in summary
    assert "api_key" not in summary.lower()


def test_summary_includes_status_mic_and_local_statement():
    summary = diagnostics_summary(_settings(backend_mode="mock"))
    assert "backend status: ready" in summary
    assert "microphone:" in summary
    assert "performance profile: balanced" in summary
    assert vs.LOCAL_ONLY_STATEMENT in summary
    assert "model path configured: no" in summary       # presence, not path


# ==========================================================================
# 36-40  Voice Room / panel integration
# ==========================================================================


def _ui_window(**voice_settings):
    from logosforge.settings import get_manager
    mgr = get_manager()
    mgr.set("enable_voice_mode", True)
    mgr.set("voice_backend_mode", "mock")
    for key, value in voice_settings.items():
        mgr.set(key, value)
    from logosforge.db import Database
    from logosforge.ui.main_window import MainWindow
    db = Database()
    pid = db.create_project("P", narrative_engine="novel").id
    win = MainWindow(db, pid)
    win._toggle_voice_panel()
    return db, pid, win


def test_invalid_setup_disables_start_with_message():
    _db, _pid, win = _ui_window(voice_backend_mode="local_process",
                                voice_whisper_model_path="")
    panel = win._voice_panel
    panel.sync_enabled_state()
    assert panel._start_btn.isEnabled() is False
    assert SETUP_REQUIRED_MESSAGE in panel._start_btn.toolTip()
    assert SETUP_REQUIRED_MESSAGE in panel._status_label.text()


def test_valid_setup_enables_start():
    _db, _pid, win = _ui_window()                       # mock backend: ready
    panel = win._voice_panel
    panel.sync_enabled_state()
    assert panel._start_btn.isEnabled() is True
    assert panel._start_btn.toolTip() == ""


def test_dictation_works_without_billy_and_glossary():
    from logosforge.settings import get_manager
    from PySide6.QtWidgets import QTextEdit
    db, pid, win = _ui_window()
    get_manager().set("ai_provider", "")
    get_manager().set("ai_base_url", "")
    get_manager().set("enable_voice_glossary", False)
    panel = win._voice_panel
    panel._refresh_billy_ops()
    assert panel._billy_generate_btn.isEnabled() is False  # Billy only
    from logosforge.voice.types import TranscriptSegment
    panel._apply_final_segment(TranscriptSegment(text="still dictating"))
    assert panel._history.entries[0].corrections == []  # glossary absent
    editor = QTextEdit()
    win._voice_commit.note_focus(editor)
    assert panel.commit() is True                       # dictation fine
    assert "still dictating" in editor.toPlainText()


def test_setup_dialog_opens_parented_and_updates_status():
    from logosforge.settings import get_manager
    _db, _pid, win = _ui_window()
    panel = win._voice_panel
    before = set(QApplication.topLevelWidgets())
    panel._on_setup_open()
    dlg = panel._setup_dialog
    assert dlg is not None
    assert dlg.parent() is win._voice_window            # parented chain
    new_visible = [w for w in (set(QApplication.topLevelWidgets()) - before)
                   if w.isVisible() and w is not dlg]
    assert new_visible == []
    assert dlg._backend_status.text() == "[ready]"      # mock backend
    idx = dlg._backend.findData("local_process")
    dlg._backend.setCurrentIndex(idx)                   # not configured
    assert get_manager().get("voice_backend_mode") == "local_process"
    assert dlg._backend_status.text() in (
        "[missing_dependency]", "[missing_model]")
    dlg._on_test_backend()
    assert dlg._result.toPlainText()                    # message, no crash


def test_setup_dialog_test_transcription_mock_shows_result_only():
    db, pid, win = _ui_window()
    panel = win._voice_panel
    panel._on_setup_open()
    dlg = panel._setup_dialog
    dlg._on_test_transcription()
    assert "mock transcript" in dlg._result.toPlainText()
    assert "not committed" in dlg._result.toPlainText()
    assert db.get_all_notes(pid) == []                  # nothing entered app


def test_setup_module_local_only():
    # Ban actual network/download MECHANISMS (the prose deliberately says
    # "never downloaded automatically").
    import inspect
    src = inspect.getsource(vs).lower()
    for banned in ("urllib", "requests", "openai", "http://", "https://",
                   "huggingface", "hf_hub", "comfyui", "socket"):
        assert banned not in src, banned
