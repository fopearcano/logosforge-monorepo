"""Local voice-to-script MVP — buffered dictation, local Whisper, manual commit.

Covers the pure-logic core (settings default-off, status state machine, buffer
segmentation, missing-backend fallbacks, mock transcriber) and the UI panel
(hidden when flag off, setup message when backend missing, start/stop, commit,
clear, no top-level window) — all headless with mocks. No cloud, no real audio.
"""

from __future__ import annotations

import array
import warnings

import pytest
from PySide6.QtWidgets import QApplication, QTextEdit

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.voice.audio_buffer import AudioBuffer
from logosforge.voice.editor_commit import EditorCommitTarget
from logosforge.voice.recorder import MockRecorder, build_recorder
from logosforge.voice.session import VoiceSessionController
from logosforge.voice.silence_detector import SimpleSilenceDetector, rms
from logosforge.voice.transcriber import (
    FasterWhisperTranscriber,
    MockTranscriber,
    build_transcriber,
)
from logosforge.voice.types import TranscriptSegment, VoiceSettings, VoiceStatus

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


def _settings(**over) -> VoiceSettings:
    base = dict(enabled=True, backend="mock", silence_ms=300,
                max_segment_seconds=25)
    base.update(over)
    return VoiceSettings(**base)


def _get(d: dict):
    from logosforge.settings import DEFAULTS
    merged = {**DEFAULTS, **d}
    return merged.get


# ==========================================================================
# 1  Settings default disabled
# ==========================================================================


def test_voice_disabled_by_default():
    from logosforge.settings import DEFAULTS, get_manager
    assert DEFAULTS["enable_voice_mode"] is False
    assert bool(get_manager().get("enable_voice_mode")) is False


def test_voice_settings_from_store_defaults_off():
    vs = VoiceSettings.from_store(_get({}))
    assert vs.enabled is False and vs.backend == "faster-whisper"
    assert vs.language == "auto" and vs.auto_commit is False


# ==========================================================================
# 2  Status state machine: off -> listening -> processing -> ready -> off
# ==========================================================================


def test_status_transitions_off_listening_processing_ready_off():
    statuses, finals = [], []
    ctl = VoiceSessionController(
        _settings(), MockRecorder(), MockTranscriber("hello"),
        on_status=lambda s: statuses.append(s.value),
        on_final_transcript=lambda seg: finals.append(seg.text))
    assert ctl.status == VoiceStatus.OFF
    assert ctl.start_voice_session() is True
    rec = ctl._recorder
    rec.feed_chunk(_speech(500))
    rec.feed_chunk(_silence(400))           # silence > 300ms -> segment
    ctl.stop_voice_session()
    assert statuses == ["listening", "processing", "transcript_ready",
                        "listening", "off"]
    assert finals == ["hello"]


def test_double_start_is_idempotent_no_overlapping_recorder():
    ctl = VoiceSessionController(_settings(), MockRecorder(), MockTranscriber())
    assert ctl.start_voice_session() is True
    rec = ctl._recorder
    assert ctl.start_voice_session() is True       # idempotent no-op
    assert ctl.status == VoiceStatus.LISTENING
    assert rec.is_recording                        # single recorder state


def test_panel_double_start_does_not_leak_recorder():
    from logosforge.ui.voice_panel import VoicePanel
    p = VoicePanel(settings_get=_get(dict(enable_voice_mode=True,
                   voice_backend_mode="mock", voice_silence_ms=300)),
                   commit_target=EditorCommitTarget())
    p.start()
    c1, r1 = p._controller, p._controller._recorder
    p.start()                                      # second start while listening
    assert p._controller is c1                     # controller kept, no orphan
    p.stop()
    assert not r1.is_recording


def test_repeated_start_stop_cycles_are_clean():
    from logosforge.ui.voice_panel import VoicePanel
    p = VoicePanel(settings_get=_get(dict(enable_voice_mode=True,
                   voice_backend_mode="mock", voice_silence_ms=300)),
                   commit_target=EditorCommitTarget())
    for _ in range(3):
        p.start()
        rec = p._controller._recorder
        assert rec.is_recording
        p.stop()
        assert not rec.is_recording
    assert p._status == VoiceStatus.OFF


def test_stop_finalizes_valid_segment():
    finals = []
    ctl = VoiceSessionController(
        _settings(silence_ms=999999), MockRecorder(), MockTranscriber("tail"),
        on_final_transcript=lambda seg: finals.append(seg.text))
    ctl.start_voice_session()
    ctl._recorder.feed_chunk(_speech(500))          # no silence boundary yet
    ctl.stop_voice_session()                        # Stop flushes the remainder
    assert finals == ["tail"]
    assert ctl.status == VoiceStatus.OFF


def test_buffer_is_bounded_by_max_segment_duration():
    buf = AudioBuffer(_SR, silence_ms=999999, max_segment_seconds=1)
    max_bytes = 0
    for _ in range(50):                             # 5 s of speech
        buf.feed(_speech(100))
        max_bytes = max(max_bytes, buf._bytes)
    # Internal accumulation never exceeds one max-duration segment (1 s + chunk).
    assert max_bytes <= int(_SR * 1.2) * 2


def test_backend_availability_check_needs_no_network(monkeypatch):
    import socket
    def _no_net(*a, **k):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket, "create_connection", _no_net)
    ok, msg = FasterWhisperTranscriber(model_path="").availability()
    assert ok is False and msg                      # offline check only
    assert MockTranscriber().availability() == (True, "")


# ==========================================================================
# 3-4  Missing backend / model path -> disabled/setup, no crash
# ==========================================================================


def test_missing_transcriber_backend_disables_no_crash():
    # MockRecorder available, transcriber unavailable.
    class _Unavail(MockTranscriber):
        def availability(self):
            return (False, "setup needed")
    ctl = VoiceSessionController(_settings(), MockRecorder(), _Unavail())
    ok, msg = ctl.availability()
    assert ok is False and msg == "setup needed"
    assert ctl.start_voice_session() is False
    assert ctl.status == VoiceStatus.DISABLED


def test_faster_whisper_missing_model_path_unavailable():
    t = FasterWhisperTranscriber(model_path="")
    ok, msg = t.availability()
    assert ok is False and msg                  # non-empty setup message
    # Transcribe returns an error segment, never raises.
    seg = t.transcribe(_speech(100), sample_rate=_SR)
    assert isinstance(seg, TranscriptSegment) and seg.error


def test_disabled_flag_reports_unavailable():
    ctl = VoiceSessionController(_settings(enabled=False), MockRecorder(),
                                MockTranscriber())
    assert ctl.availability()[0] is False


# ==========================================================================
# 5-7  Buffer segmentation
# ==========================================================================


def test_buffer_finalizes_after_silence():
    buf = AudioBuffer(_SR, silence_ms=300, max_segment_seconds=30)
    assert buf.feed(_speech(500)) is None
    seg = buf.feed(_silence(400))
    assert seg is not None and len(seg) > 0


def test_buffer_finalizes_at_max_duration():
    buf = AudioBuffer(_SR, silence_ms=999999, max_segment_seconds=1)
    out = None
    for _ in range(12):                         # 1200 ms > 1 s
        out = buf.feed(_speech(100)) or out
    assert out is not None


def test_buffer_ignores_silence_only_and_empty():
    buf = AudioBuffer(_SR, silence_ms=100, max_segment_seconds=30)
    assert buf.feed(_silence(500)) is None
    assert buf.flush() is None
    assert buf.feed(b"") is None


def test_silence_detector_rms_distinguishes():
    assert rms(_speech(100)) > rms(_silence(100))
    d = SimpleSilenceDetector(_SR, silence_ms=200)
    d.feed(_speech(100))
    assert d.had_speech and not d.silence_reached()
    d.feed(_silence(300))
    assert d.silence_reached()


# ==========================================================================
# 8  Transcriber interface mockable + builder
# ==========================================================================


def test_mock_transcriber_returns_text():
    seg = MockTranscriber("xyz").transcribe(_speech(100), sample_rate=_SR)
    assert seg.text == "xyz" and seg.is_final


def test_build_backends_from_settings():
    assert isinstance(build_transcriber(_settings(backend="mock")), MockTranscriber)
    assert isinstance(build_recorder(_settings(backend="mock")), MockRecorder)
    assert isinstance(build_transcriber(_settings(backend="faster-whisper")),
                      FasterWhisperTranscriber)


# ==========================================================================
# 9-11  Editor commit adapter
# ==========================================================================


def test_commit_inserts_plain_text():
    ed = QTextEdit()
    tgt = EditorCommitTarget()
    tgt.note_focus(ed)
    assert tgt.insert_as_plain_text("hello world") is True
    assert "hello world" in ed.toPlainText()


def test_commit_noop_without_editor():
    tgt = EditorCommitTarget()
    assert tgt.has_target() is False
    assert tgt.insert_as_plain_text("nothing") is False


def test_commit_empty_text_is_noop():
    ed = QTextEdit()
    tgt = EditorCommitTarget()
    tgt.note_focus(ed)
    assert tgt.insert_as_plain_text("   ") is False
    assert ed.toPlainText() == ""


def test_commit_target_clear_prevents_stale_commit():
    ed = QTextEdit()
    tgt = EditorCommitTarget()
    tgt.note_focus(ed)
    tgt.clear()                                 # e.g. on project switch
    assert tgt.insert_as_plain_text("x") is False


def test_classification_hooks_are_deferred():
    tgt = EditorCommitTarget()
    for fn, args in [("insert_as_action", ("a",)),
                     ("insert_as_note", ("n",)),
                     ("send_to_outline", ("o",)),
                     ("send_to_psyke", ("p",))]:
        with pytest.raises(NotImplementedError):
            getattr(tgt, fn)(*args)


# ==========================================================================
# 12-17  UI panel
# ==========================================================================


def _panel(**settings):
    from logosforge.ui.voice_panel import VoicePanel
    base = dict(enable_voice_mode=True, voice_backend_mode="mock",
                voice_silence_ms=300)
    base.update(settings)
    return VoicePanel(settings_get=_get(base), commit_target=EditorCommitTarget())


def test_panel_hidden_when_flag_off():
    from logosforge.ui.voice_panel import VoicePanel
    p = VoicePanel(settings_get=_get({"enable_voice_mode": False}),
                   commit_target=EditorCommitTarget())
    assert p.isVisible() is False and p.is_enabled() is False


def test_panel_setup_message_when_backend_missing():
    p = _panel(voice_whisper_backend="faster-whisper",
               voice_whisper_model_path="")
    p.start()
    assert p._status_label.text()                # a non-empty setup message
    # No crash; controls remain usable.
    assert p._controller is not None


def test_panel_start_stop_updates_status():
    p = _panel()
    p.start()
    assert p._status == VoiceStatus.LISTENING
    p.stop()
    assert p._status == VoiceStatus.OFF


def test_panel_commit_disabled_without_transcript():
    p = _panel()
    assert p._commit_btn.isEnabled() is False
    p._preview.setPlainText("some text")
    assert p._commit_btn.isEnabled() is True


def test_panel_clear_removes_preview():
    p = _panel()
    p._preview.setPlainText("draft")
    p.clear_preview()
    assert p._preview.toPlainText() == ""


def test_panel_dictation_to_preview_and_commit():
    from logosforge.ui.voice_panel import VoicePanel
    ed = QTextEdit()
    tgt = EditorCommitTarget()
    tgt.note_focus(ed)
    p = VoicePanel(settings_get=_get(dict(enable_voice_mode=True,
                   voice_backend_mode="mock", voice_silence_ms=300)),
                   commit_target=tgt)
    p.start()
    rec = p._controller._recorder
    rec.feed_chunk(_speech(500)); rec.feed_chunk(_silence(400))
    p.stop()
    assert "mock transcript" in p._preview.toPlainText()
    assert p.commit() is True
    assert "mock transcript" in ed.toPlainText()


def test_panel_creates_no_top_level_window():
    before = set(QApplication.topLevelWidgets())
    p = _panel()
    p.toggle_panel()                            # show
    new_visible = [w for w in (set(QApplication.topLevelWidgets()) - before)
                   if w.isVisible() and w is not p.window()]
    assert new_visible == []


# ==========================================================================
# 18-30  Regression — main window builds with voice; app safe when flag off
# ==========================================================================


def test_main_window_builds_with_voice_panel_hidden():
    from logosforge.ui.main_window import MainWindow
    db = Database()
    pid = db.create_project("N", narrative_engine="novel").id
    win = MainWindow(db, pid)
    assert win._voice_panel is not None
    assert win._voice_panel.isVisible() is False           # never auto-shown
    # The panel lives inside the floating Voice Dictation window, which is
    # parented to the main window (never a parentless top-level window) and
    # stays hidden until toggled.
    assert win._voice_panel.window() is win._voice_window
    assert win._voice_window.parent() is win
    assert win._voice_window.isVisible() is False


def test_voice_shortcut_has_no_conflicts():
    # Ctrl+Shift+V must be unique across all menu actions (no clash with the
    # existing Ctrl+L / Ctrl+B / Ctrl+Shift+{D,H,F} or paste variants).
    from PySide6.QtGui import QAction
    from logosforge.ui.main_window import MainWindow
    db = Database()
    pid = db.create_project("N", narrative_engine="novel").id
    win = MainWindow(db, pid)
    shortcuts: dict[str, list[str]] = {}
    for action in win.findChildren(QAction):
        for ks in action.shortcuts():
            key = ks.toString()
            if key:
                shortcuts.setdefault(key, []).append(action.text())
    assert any("Dexter" in t for t in shortcuts.get("Ctrl+Shift+V", []))
    assert len(shortcuts.get("Ctrl+Shift+V", [])) == 1      # unique


def test_toggle_voice_panel_when_disabled_is_safe():
    from logosforge.ui.main_window import MainWindow
    db = Database()
    pid = db.create_project("N", narrative_engine="novel").id
    win = MainWindow(db, pid)
    win._toggle_voice_panel()                   # flag off -> shows inert message
    assert win._voice_panel is not None         # no crash


def test_project_switch_stops_voice_and_clears_commit_target():
    from logosforge.ui.main_window import MainWindow
    db = Database()
    a = db.create_project("A", narrative_engine="novel").id
    b = db.create_project("B", narrative_engine="novel").id
    win = MainWindow(db, a)
    # Simulate a tracked editor + active panel, then switch.
    ed = QTextEdit()
    win._voice_commit.note_focus(ed)
    win._switch_project(b)
    assert win._voice_commit.has_target() is False         # cleared on switch


def test_no_cloud_client_imports_in_voice_package():
    # The voice package must not import any cloud/SaaS client. Stdlib urllib is
    # allowed ONLY in lan_server.py (trusted private-LAN transport with the
    # public-host validator + no-redirect opener).
    import os
    import re
    import logosforge.voice as vp
    pkg_dir = list(vp.__path__)[0]
    banned = re.compile(
        r"^\s*(import|from)\s+(requests|openai|httpx|boto3|aiohttp|websockets"
        r"|google\.cloud|azure)\b", re.M)
    urllib_re = re.compile(r"^\s*import\s+urllib|^\s*from\s+urllib", re.M)
    for name in os.listdir(pkg_dir):
        if not name.endswith(".py"):
            continue
        src = open(os.path.join(pkg_dir, name), encoding="utf-8").read()
        assert not banned.search(src), f"cloud client import in {name}"
        if name != "lan_server.py":
            assert not urllib_re.search(src), f"network import in {name}"
