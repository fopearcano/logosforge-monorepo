"""Voice session controller — orchestrates recorder + buffer + transcriber.

Pure Python (no Qt): a recorder pushes PCM chunks to :meth:`feed_chunk`, the
:class:`AudioBuffer` finalizes segments on silence / max-duration, and the
transcriber turns a finalized segment into text. Status changes and final
transcripts are delivered through injected callbacks, so the UI can marshal them
onto the Qt thread (e.g. via signals) while this object stays headless-testable.

Local-first: it owns only the injected backends; it never sends audio anywhere
and never auto-commits — committing a transcript to the editor is a separate,
explicit step (see :mod:`logosforge.voice.editor_commit`).
"""

from __future__ import annotations

from collections.abc import Callable

from logosforge.voice.audio_buffer import AudioBuffer
from logosforge.voice.recorder import VoiceRecorder
from logosforge.voice.silence_detector import rms as _rms
from logosforge.voice.transcriber import Transcriber
from logosforge.voice.types import (
    TranscriptSegment,
    VoiceSettings,
    VoiceStatus,
)


class VoiceSessionController:
    def __init__(self, settings: VoiceSettings, recorder: VoiceRecorder,
                 transcriber: Transcriber, *,
                 on_status: Callable[[VoiceStatus], None] | None = None,
                 on_final_transcript: Callable[[TranscriptSegment], None] | None = None,
                 on_notice: Callable[[str], None] | None = None,
                 on_level: Callable[[float], None] | None = None
                 ) -> None:
        self._settings = settings
        self._recorder = recorder
        self._transcriber = transcriber
        self._on_status = on_status
        self._on_final = on_final_transcript
        # Surface a plain-language notice when a session ends having captured
        # audio but produced no transcript — otherwise a too-quiet mic looks
        # like the feature silently doing nothing.
        self._on_notice = on_notice
        # Live input level (int16 RMS per chunk) for a UI meter.
        self._on_level = on_level
        self._buffer = AudioBuffer(
            settings.sample_rate, silence_ms=settings.silence_ms,
            max_segment_seconds=settings.max_segment_seconds,
            channels=settings.channels)
        self._status = VoiceStatus.OFF
        self._paused = False
        # Per-session feedback tracking (reset on each start).
        self._session_active = False
        self._got_audio = False
        self._produced_transcript = False
        self._had_error = False

    # -- status --------------------------------------------------------------
    @property
    def status(self) -> VoiceStatus:
        return self._status

    def get_voice_status(self) -> VoiceStatus:
        return self._status

    def _set_status(self, status: VoiceStatus) -> None:
        if status == self._status:
            return
        self._status = status
        if self._on_status is not None:
            self._on_status(status)

    def availability(self) -> tuple[bool, str]:
        if not self._settings.enabled:
            from logosforge.voice.types import SETUP_MESSAGE
            return (False, SETUP_MESSAGE)
        # Backend config first: its message (choose a backend / set the model
        # path / LAN URL invalid) is the actionable one; the microphone check
        # surfaces once the backend is configured.
        ok_t, msg_t = self._transcriber.availability()
        if not ok_t:
            return (False, msg_t)
        ok_r, msg_r = self._recorder.availability()
        if not ok_r:
            return (False, msg_r)
        return (True, "")

    # -- lifecycle -----------------------------------------------------------
    def start_voice_session(self) -> bool:
        # Idempotent: never start a second, overlapping recorder state.
        if self._status in (VoiceStatus.LISTENING, VoiceStatus.PROCESSING):
            return True
        ok, _msg = self.availability()
        if not ok:
            self._set_status(VoiceStatus.DISABLED)
            return False
        self._buffer.clear()
        self._paused = False
        self._got_audio = False
        self._produced_transcript = False
        self._had_error = False
        if not self._recorder.start(self._on_chunk):
            self._set_status(VoiceStatus.ERROR)
            return False
        self._session_active = True
        self._set_status(VoiceStatus.LISTENING)
        return True

    def stop_voice_session(self) -> None:
        try:
            self._recorder.stop()
        except Exception:
            pass
        # Finalize whatever remains, then go idle.
        remaining = self._buffer.flush()
        if remaining:
            self.transcribe_buffered_segment(remaining)
        # Feedback: a session that captured audio but never produced a
        # transcript almost always means the mic level was below the speech
        # threshold (or the wrong input device). Say so, instead of nothing —
        # unless a transcription error already explained the failure.
        if (self._session_active and not self._produced_transcript
                and not self._had_error):
            self._emit_no_transcript_notice()
        self._session_active = False
        self._set_status(VoiceStatus.OFF)

    def _emit_no_transcript_notice(self) -> None:
        if self._on_notice is None:
            return
        if self._got_audio:
            self._on_notice(
                "No speech was transcribed. If you spoke, your microphone "
                "level may be too low — raise the input level or enable "
                "Microphone Boost in your system sound settings.")
        else:
            self._on_notice(
                "No audio reached the recorder. Check that the right "
                "microphone is selected as your system input device.")

    def pause_voice_session(self) -> None:
        self._paused = True

    def resume_voice_session(self) -> None:
        self._paused = False

    # -- audio path ----------------------------------------------------------
    def _on_chunk(self, pcm: bytes) -> None:
        if self._paused or self._status not in (VoiceStatus.LISTENING,
                                                VoiceStatus.PROCESSING,
                                                VoiceStatus.TRANSCRIPT_READY):
            return
        if pcm:
            self._got_audio = True
            if self._on_level is not None:
                self._on_level(_rms(pcm))
        segment = self._buffer.feed(pcm)
        if segment is not None:
            self.transcribe_buffered_segment(segment)

    def transcribe_buffered_segment(self, pcm: bytes) -> TranscriptSegment:
        """Transcribe a finalized PCM segment and emit the result. No mutation of
        any editor — committing is explicit and separate."""
        if not pcm:
            return TranscriptSegment(text="", is_final=True)
        self._set_status(VoiceStatus.PROCESSING)
        # Resolve the transcription language from the Dexter mode (project /
        # auto / explicit) — the backend only ever sees a valid Whisper code.
        mode = self._settings.resolved_language_mode()
        effective = self._settings.effective_language()
        seg = self._transcriber.transcribe(
            pcm, sample_rate=self._settings.sample_rate,
            language=effective)
        # Keep the segment's local PCM in memory (session-only) so the history
        # panel can offer "Retry transcription". Local-first: the bytes never
        # touch disk and are dropped on discard/clear.
        seg.audio_bytes = pcm
        seg.sample_rate = self._settings.sample_rate
        # Language metadata: what was asked for vs. what the backend found,
        # plus the project coordination fields (Dexter language update).
        selected = (effective or "auto").lower()
        seg.selected_language_code = selected
        seg.project_language_code = (
            self._settings.project_language_code or "").lower()
        seg.dexter_language_mode = mode
        detected = (seg.language or "").lower()
        if detected and detected != "auto":
            seg.detected_language_code = detected
        if selected in ("", "auto"):
            seg.language_source = ("backend_detected"
                                   if seg.detected_language_code else "auto")
        elif mode == "project":
            seg.language_source = "project_language"
        else:
            seg.language_source = "user_selected"
        if seg.error:
            self._had_error = True
            self._set_status(VoiceStatus.ERROR)
            # Surface the actual cause, not just a generic "error" status.
            if self._on_notice is not None:
                self._on_notice(f"Transcription error: {seg.error}")
        elif not seg.is_empty():
            self._produced_transcript = True
            self._set_status(VoiceStatus.TRANSCRIPT_READY)
            if self._on_final is not None:
                self._on_final(seg)
        # If still recording, return to LISTENING for the next segment.
        if self._recorder.is_recording and self._status != VoiceStatus.ERROR:
            self._set_status(VoiceStatus.LISTENING)
        return seg
