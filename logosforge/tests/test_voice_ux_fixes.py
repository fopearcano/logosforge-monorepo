"""Regression tests for the Dexter's Room UX fixes:

1. Mic-level / no-speech feedback — a session that captures audio but never
   crosses the speech threshold tells the user (instead of failing silently).
2. CUDA DLL auto-discovery — configured dirs are added to the DLL path.
3. Voice window opens wide enough that control labels are not truncated.
4. Enabling Voice Mode applies the shown backend (no "pick a backend" dead-end).
"""

from __future__ import annotations

import os
import warnings

import pytest

warnings.filterwarnings("ignore")

from logosforge.voice.session import VoiceSessionController
from logosforge.voice.types import TranscriptSegment, VoiceSettings


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class _Recorder:
    """Minimal recorder. Real recorders deliver chunks asynchronously *after*
    start() returns (once the session is LISTENING); ``pump()`` mimics that."""

    name = "fake"

    def __init__(self, chunks):
        self._chunks = chunks
        self._cb = None
        self.is_recording = False

    def availability(self):
        return (True, "")

    def start(self, on_chunk):
        self.is_recording = True
        self._cb = on_chunk
        return True

    def pump(self):
        for c in self._chunks:
            if self._cb is not None:
                self._cb(c)

    def stop(self):
        self.is_recording = False


class _Transcriber:
    name = "fake"

    def __init__(self, text="hello world"):
        self._text = text

    def availability(self):
        return (True, "")

    def transcribe(self, pcm, *, sample_rate=16000, language="auto"):
        return TranscriptSegment(text=self._text, is_final=True)


def _settings():
    return VoiceSettings(enabled=True, backend_mode="local_process")


# 16-bit mono PCM helpers (silence threshold is int16 RMS 500).
_LOUD = (b"\x00\x40" * 1600)      # ~0.1s of amplitude 0x4000 -> RMS well over 500
_QUIET = (b"\x10\x00" * 1600)     # ~0.1s of amplitude 16    -> RMS under 500


# ---------------------------------------------------------------------------
# 1. No-speech / too-quiet feedback
# ---------------------------------------------------------------------------

def test_quiet_session_emits_too_quiet_notice():
    notices = []
    # Many quiet chunks — audio arrives but never crosses the speech threshold.
    rec = _Recorder([_QUIET] * 20)
    ctrl = VoiceSessionController(_settings(), rec, _Transcriber(),
                                  on_notice=notices.append)
    ctrl.start_voice_session()
    rec.pump()
    ctrl.stop_voice_session()
    assert notices, "a too-quiet session must surface a notice"
    assert "too low" in notices[-1].lower()


def test_no_audio_session_emits_no_audio_notice():
    notices = []
    rec = _Recorder([])      # recorder delivers nothing
    ctrl = VoiceSessionController(_settings(), rec, _Transcriber(),
                                  on_notice=notices.append)
    ctrl.start_voice_session()
    rec.pump()
    ctrl.stop_voice_session()
    assert notices and "no audio" in notices[-1].lower()


def test_session_with_speech_emits_no_notice():
    notices = []
    finals = []
    # Loud speech then enough quiet to finalize -> real transcript, no notice.
    rec = _Recorder([_LOUD] * 5 + [_QUIET] * 12)
    ctrl = VoiceSessionController(
        _settings(), rec, _Transcriber("ok"),
        on_final_transcript=finals.append, on_notice=notices.append)
    ctrl.start_voice_session()
    rec.pump()
    ctrl.stop_voice_session()
    assert finals, "speech should produce a transcript"
    assert not notices, "a successful session must not nag about a quiet mic"


def test_notice_silent_when_no_callback():
    # No on_notice provided -> must not raise.
    rec = _Recorder([_QUIET] * 5)
    ctrl = VoiceSessionController(_settings(), rec, _Transcriber())
    ctrl.start_voice_session()
    rec.pump()
    ctrl.stop_voice_session()  # no exception


# ---------------------------------------------------------------------------
# P0: live input level + P1: transcription-error surfacing
# ---------------------------------------------------------------------------

class _ErrTranscriber:
    name = "fake"

    def availability(self):
        return (True, "")

    def transcribe(self, pcm, *, sample_rate=16000, language="auto"):
        return TranscriptSegment(text="", is_final=True, error="backend exploded")


def test_on_level_emits_rms_per_chunk():
    levels = []
    rec = _Recorder([_LOUD] * 3 + [_QUIET] * 3)
    ctrl = VoiceSessionController(_settings(), rec, _Transcriber(),
                                  on_level=levels.append)
    ctrl.start_voice_session()
    rec.pump()
    ctrl.stop_voice_session()
    assert len(levels) >= 6                 # one per captured chunk
    assert max(levels) > 500                # loud speech is above threshold
    assert min(levels) < 500                # quiet chunks are below


def test_transcription_error_surfaced_and_suppresses_quiet_notice():
    notices = []
    # Speech then enough silence to finalize -> transcribe -> error.
    rec = _Recorder([_LOUD] * 5 + [_QUIET] * 12)
    ctrl = VoiceSessionController(_settings(), rec, _ErrTranscriber(),
                                  on_notice=notices.append)
    ctrl.start_voice_session()
    rec.pump()
    ctrl.stop_voice_session()
    assert any("backend exploded" in n for n in notices)   # real cause shown
    assert not any("too low" in n.lower() for n in notices)  # no misleading quiet notice


def test_level_meter_value_mapping(_qapp):
    from logosforge.ui.voice_panel import VoicePanel
    p = VoicePanel()
    p._apply_level(5000.0)
    assert p._level_meter.value() == 100 and p._level_quiet is False
    p._apply_level(250.0)
    assert p._level_meter.value() == 5 and p._level_quiet is True   # below 500 = quiet


def test_level_meter_visibility_follows_status(_qapp):
    from logosforge.ui.voice_panel import VoicePanel
    from logosforge.voice.types import VoiceStatus
    p = VoicePanel()
    p._apply_status(VoiceStatus.LISTENING)
    assert p._level_meter.isHidden() is False          # shown while listening
    p._apply_status(VoiceStatus.OFF)
    assert p._level_meter.isHidden() is True            # hidden + reset otherwise
    assert p._level_meter.value() == 0


def test_processing_status_shows_transcribing_timer(_qapp):
    from logosforge.ui.voice_panel import VoicePanel
    from logosforge.voice.types import VoiceStatus
    p = VoicePanel()
    p._apply_status(VoiceStatus.PROCESSING)
    assert "transcribing" in p._status_label.text().lower()
    assert p._proc_timer.isActive()
    p._apply_status(VoiceStatus.TRANSCRIPT_READY)
    assert not p._proc_timer.isActive()                 # timer stops off PROCESSING


# ---------------------------------------------------------------------------
# 2. CUDA DLL auto-discovery
# ---------------------------------------------------------------------------

def test_cuda_paths_adds_existing_dir(tmp_path):
    from logosforge.voice.cuda_paths import ensure_cuda_dll_path
    d = tmp_path / "cuda"
    d.mkdir()
    before = os.environ.get("PATH", "")
    added = ensure_cuda_dll_path([str(d)])
    assert added == [str(d)]
    assert str(d) in os.environ.get("PATH", "")
    os.environ["PATH"] = before  # keep the test side-effect-free


def test_cuda_paths_noop_on_empty_or_missing(tmp_path):
    from logosforge.voice.cuda_paths import ensure_cuda_dll_path
    assert ensure_cuda_dll_path([]) == []
    assert ensure_cuda_dll_path(None) == []
    assert ensure_cuda_dll_path([str(tmp_path / "nope")]) == []


def test_cuda_dll_dirs_setting_default():
    from logosforge.settings import DEFAULTS
    assert DEFAULTS.get("voice_cuda_dll_dirs") == []


# ---------------------------------------------------------------------------
# 3 + 4. UI fixes (need a QApplication)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def _qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def test_voice_window_opens_wide_enough(_qapp):
    from logosforge.ui.voice_panel import VoiceDictationWindow, VoicePanel
    win = VoiceDictationWindow(VoicePanel())
    # Wide enough that the dense control rows don't truncate (they did at 600).
    assert win.width() >= 760
    assert win.minimumWidth() >= 600


def test_enabling_voice_applies_shown_backend(_qapp):
    from logosforge.ui.voice_setup_dialog import VoiceSetupDialog
    store = {"voice_backend_mode": "disabled", "enable_voice_mode": False}
    dlg = VoiceSetupDialog(settings_get=store.get,
                           settings_set=lambda k, v: store.__setitem__(k, v))
    # Precondition: combo shows a real backend even though mode is "disabled".
    assert dlg._backend.currentData() and dlg._backend.currentData() != "disabled"
    dlg._enable.setChecked(True)            # user enables Voice Mode
    assert store["enable_voice_mode"] is True
    # The shown backend is now actually applied -> no "pick a backend" dead-end.
    assert store["voice_backend_mode"] == dlg._backend.currentData()
    assert store["voice_backend_mode"] != "disabled"
