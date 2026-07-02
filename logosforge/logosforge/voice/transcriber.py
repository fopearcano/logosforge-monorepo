"""Local transcription backends for the voice MVP.

A small interface plus a mock and a **local** faster-whisper backend. Everything
is local-first: no cloud speech API, no audio leaves the machine. The optional
``faster-whisper`` dependency is **lazy-imported** and only ever loads a model
from an explicit **local path** — it never auto-downloads a model. If the backend
or model is unavailable, ``availability()`` returns ``(False, message)`` and the
app stays usable (the UI shows a non-blocking setup message).
"""

from __future__ import annotations

import os
import wave
from io import BytesIO

from logosforge.voice.types import SETUP_MESSAGE, TranscriptSegment


def pcm_to_wav_bytes(pcm: bytes, sample_rate: int = 16000, *,
                     channels: int = 1, sample_width: int = 2) -> bytes:
    """Wrap raw PCM as an in-memory WAV (what file/CLI backends expect)."""
    buf = BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


class Transcriber:
    """Interface. Backends transcribe a finalized PCM segment locally."""

    name = "base"

    def availability(self) -> tuple[bool, str]:
        """``(available, message)``. message is a setup hint when unavailable."""
        return (False, SETUP_MESSAGE)

    def transcribe(self, pcm: bytes, *, sample_rate: int = 16000,
                   language: str = "auto") -> TranscriptSegment:
        raise NotImplementedError


class MockTranscriber(Transcriber):
    """Deterministic, dependency-free backend for tests / no-setup demos."""

    name = "mock"

    def __init__(self, text: str = "mock transcript") -> None:
        self._text = text

    def availability(self) -> tuple[bool, str]:
        return (True, "")

    def transcribe(self, pcm: bytes, *, sample_rate: int = 16000,
                   language: str = "auto") -> TranscriptSegment:
        if not pcm:
            return TranscriptSegment(text="", is_final=True)
        frames = len(pcm) // 2
        return TranscriptSegment(
            text=self._text, is_final=True,
            language=("en" if language == "auto" else language),
            duration_s=frames / float(sample_rate) if sample_rate else 0.0)


class FasterWhisperTranscriber(Transcriber):
    """Local faster-whisper backend (optional, lazy). Loads a model only from an
    existing **local path** — never auto-downloads."""

    name = "faster-whisper"

    def __init__(self, model_path: str = "", *, device: str = "cpu",
                 compute_type: str = "int8") -> None:
        self.model_path = (model_path or "").strip()
        self.device = device
        self.compute_type = compute_type
        self._model = None

    def availability(self) -> tuple[bool, str]:
        try:
            import faster_whisper  # noqa: F401  (lazy optional import)
        except Exception:
            return (False, "Install 'faster-whisper' to enable local voice. "
                           + SETUP_MESSAGE)
        if not self.model_path or not os.path.exists(self.model_path):
            return (False, "Set a local Whisper model path (no model will be "
                           "downloaded automatically). " + SETUP_MESSAGE)
        return (True, "")

    def _ensure_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel  # lazy
            # model_path is a validated local path -> no network download.
            self._model = WhisperModel(self.model_path, device=self.device,
                                       compute_type=self.compute_type)
        return self._model

    def transcribe(self, pcm: bytes, *, sample_rate: int = 16000,
                   language: str = "auto") -> TranscriptSegment:
        ok, msg = self.availability()
        if not ok:
            return TranscriptSegment(text="", is_final=True, error=msg)
        if not pcm:
            return TranscriptSegment(text="", is_final=True)
        try:
            model = self._ensure_model()
            wav = pcm_to_wav_bytes(pcm, sample_rate)
            lang = None if language in ("", "auto") else language
            segments, info = model.transcribe(BytesIO(wav), language=lang)
            text = " ".join(s.text.strip() for s in segments).strip()
            return TranscriptSegment(
                text=text, is_final=True,
                language=getattr(info, "language", "") or (lang or ""),
                duration_s=len(pcm) // 2 / float(sample_rate) if sample_rate else 0.0)
        except Exception as exc:  # never crash the app on a transcription error
            return TranscriptSegment(text="", is_final=True,
                                     error=f"Transcription failed: {exc}")


class DisabledTranscriber(Transcriber):
    """Backend-mode "disabled": always unavailable with a clear message."""

    name = "disabled"

    def availability(self) -> tuple[bool, str]:
        from logosforge.voice.types import BACKEND_DISABLED_MESSAGE
        return (False, BACKEND_DISABLED_MESSAGE)

    def transcribe(self, pcm: bytes, *, sample_rate: int = 16000,
                   language: str = "auto") -> TranscriptSegment:
        from logosforge.voice.types import BACKEND_DISABLED_MESSAGE
        return TranscriptSegment(text="", is_final=True,
                                 error=BACKEND_DISABLED_MESSAGE)


def build_transcriber(settings) -> Transcriber:
    """Construct the backend for the *resolved* backend mode.

    Modes: ``disabled`` | ``mock`` | ``local_process`` (faster-whisper, local
    model path only) | ``lan_server`` (trusted local-network Whisper server).
    """
    resolver = getattr(settings, "resolved_backend_mode", None)
    mode = resolver() if callable(resolver) else "local_process"
    if mode == "disabled":
        return DisabledTranscriber()
    if mode == "mock":
        return MockTranscriber()
    if mode == "lan_server":
        from logosforge.voice.lan_server import LanWhisperTranscriber
        return LanWhisperTranscriber(settings)
    if mode == "whisper_cpp":
        return WhisperCppTranscriber(settings)
    # local_process — the local PC backend (faster-whisper kind for Alpha;
    # a "mock" kind keeps the dependency-free path available).
    kind = (getattr(settings, "backend", "") or "faster-whisper").lower()
    if kind == "mock":
        return MockTranscriber()
    return FasterWhisperTranscriber(
        getattr(settings, "model_path", "") or "",
        device=(getattr(settings, "local_device", "auto") or "auto"),
        compute_type=(getattr(settings, "local_compute_type", "int8") or "int8"))


class WhisperCppTranscriber(Transcriber):
    """Local whisper.cpp backend (Phase 8): runs the USER-CONFIGURED
    executable on a temporary WAV per segment. Nothing is installed or
    downloaded; the binary and model paths come from Voice Setup. The temp
    file is always deleted; audio never leaves the machine."""

    def __init__(self, settings) -> None:
        self._exe = (getattr(settings, "executable_path", "") or "").strip()
        self._model = (getattr(settings, "model_path", "") or "").strip()
        self._language = (getattr(settings, "language", "") or "auto")
        self._beam_size = int(getattr(settings, "beam_size", 0) or 0)

    def availability(self) -> tuple[bool, str]:
        import os
        if not self._exe:
            return False, ("whisper.cpp executable is not configured. "
                           "Open Voice Setup.")
        if not os.path.isfile(self._exe):
            return False, "whisper.cpp executable not found at the set path."
        if not os.access(self._exe, os.X_OK):
            return False, "whisper.cpp executable is not runnable."
        if not self._model:
            return False, "whisper.cpp model path is not configured."
        if not os.path.exists(self._model):
            return False, "whisper.cpp model not found at the set path."
        return True, "whisper.cpp ready."

    def transcribe(self, pcm: bytes, *, sample_rate: int,
                   language: str | None = None) -> TranscriptSegment:
        ok, msg = self.availability()
        if not ok:
            return TranscriptSegment(text="", error=msg)
        import os
        import subprocess
        import tempfile
        import wave
        wav_path = ""
        try:
            fd, wav_path = tempfile.mkstemp(suffix=".wav")
            with os.fdopen(fd, "wb") as handle:
                with wave.open(handle, "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(sample_rate)
                    wav.writeframes(pcm)
            cmd = [self._exe, "-m", self._model, "-f", wav_path, "-nt"]
            lang = (language or self._language or "auto")
            if lang and lang != "auto":
                cmd += ["-l", lang]
            if self._beam_size > 0:
                cmd += ["-bs", str(self._beam_size)]
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    timeout=120)
            if result.returncode != 0:
                err = (result.stderr or "").strip().splitlines()
                return TranscriptSegment(
                    text="", error="whisper.cpp failed: "
                    + (err[-1] if err else f"exit {result.returncode}"))
            text = (result.stdout or "").strip()
            return TranscriptSegment(text=text, language=lang,
                                     source="whisper_cpp")
        except subprocess.TimeoutExpired:
            return TranscriptSegment(text="", error="whisper.cpp timed out.")
        except Exception as exc:
            return TranscriptSegment(text="",
                                     error=f"whisper.cpp error: {exc}")
        finally:
            if wav_path:
                try:
                    os.unlink(wav_path)       # never retain audio
                except OSError:
                    pass
