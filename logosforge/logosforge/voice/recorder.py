"""Microphone capture for the voice MVP — local, optional, lazy.

A small recorder interface plus a mock (for tests / no-mic environments) and a
``sounddevice`` backend (optional, lazy-imported). The recorder produces raw
**16-bit mono PCM** chunks and pushes them to a callback. It never sends audio
anywhere — capture is purely local. Missing dependency or microphone is handled
gracefully via ``availability()`` (the app never crashes).
"""

from __future__ import annotations

from collections.abc import Callable


class VoiceRecorder:
    """Interface. ``start(on_chunk)`` streams PCM chunks until ``stop()``."""

    name = "base"

    def availability(self) -> tuple[bool, str]:
        return (False, "No microphone backend available.")

    def start(self, on_chunk: Callable[[bytes], None]) -> bool:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    @property
    def is_recording(self) -> bool:
        return False


class MockRecorder(VoiceRecorder):
    """Test/no-mic recorder. ``feed_chunk`` lets tests drive audio synchronously."""

    name = "mock"

    def __init__(self) -> None:
        self._on_chunk: Callable[[bytes], None] | None = None
        self._recording = False

    def availability(self) -> tuple[bool, str]:
        return (True, "")

    def start(self, on_chunk: Callable[[bytes], None]) -> bool:
        self._on_chunk = on_chunk
        self._recording = True
        return True

    def stop(self) -> None:
        self._recording = False
        self._on_chunk = None

    @property
    def is_recording(self) -> bool:
        return self._recording

    def feed_chunk(self, pcm: bytes) -> None:
        if self._recording and self._on_chunk is not None:
            self._on_chunk(pcm)


class SoundDeviceRecorder(VoiceRecorder):
    """Local microphone capture via the optional ``sounddevice`` package."""

    name = "sounddevice"

    def __init__(self, sample_rate: int = 16000, *, channels: int = 1,
                 blocksize: int = 1600) -> None:   # 1600 frames = 100 ms @16k
        self.sample_rate = sample_rate
        self.channels = channels
        self.blocksize = blocksize
        self._stream = None
        self._on_chunk: Callable[[bytes], None] | None = None

    def availability(self) -> tuple[bool, str]:
        try:
            import sounddevice  # noqa: F401  (lazy optional import)
        except Exception:
            return (False, "Install 'sounddevice' to capture microphone audio.")
        return (True, "")

    def start(self, on_chunk: Callable[[bytes], None]) -> bool:
        if self._stream is not None:       # never open a second mic stream
            self.stop()
        ok, _ = self.availability()
        if not ok:
            return False
        try:
            import sounddevice as sd

            self._on_chunk = on_chunk

            def _cb(indata, _frames, _time, _status) -> None:
                # indata: int16 numpy array -> raw little-endian PCM bytes.
                cb = self._on_chunk
                if cb is not None:
                    try:
                        cb(bytes(indata))
                    except Exception:
                        pass

            self._stream = sd.RawInputStream(
                samplerate=self.sample_rate, channels=self.channels,
                dtype="int16", blocksize=self.blocksize, callback=_cb)
            self._stream.start()
            return True
        except Exception:
            # Microphone unavailable / permission denied / device error.
            self._stream = None
            self._on_chunk = None
            return False

    def stop(self) -> None:
        stream = self._stream
        self._stream = None
        self._on_chunk = None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass

    @property
    def is_recording(self) -> bool:
        return self._stream is not None


def build_recorder(settings) -> VoiceRecorder:
    """Construct a recorder for the resolved backend mode.

    Capture is ALWAYS local — in ``lan_server`` mode the microphone is still
    recorded on this machine; only finalized segments go to the LAN server.
    """
    resolver = getattr(settings, "resolved_backend_mode", None)
    mode = resolver() if callable(resolver) else ""
    kind = (getattr(settings, "backend", "") or "").lower()
    # "disabled" gets a MockRecorder so availability() surfaces the backend's
    # "choose a backend" message instead of a microphone-install hint.
    if mode in ("mock", "disabled") or (mode == "local_process" and kind == "mock") \
            or (not mode and kind == "mock"):
        return MockRecorder()
    return SoundDeviceRecorder(getattr(settings, "sample_rate", 16000))
