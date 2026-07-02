"""Rolling audio buffer + segmentation for near-live buffered dictation.

Accumulates raw 16-bit mono PCM chunks and finalizes a segment when either a
silence pause is detected or the max segment duration is reached. Pure Python (no
numpy / audio deps) so the segmentation logic is unit-testable with synthetic
bytes. A segment is only finalized if it actually contains speech — leading
silence and empty/too-short input never produce a segment.
"""

from __future__ import annotations

from logosforge.voice.silence_detector import (
    DEFAULT_THRESHOLD_RMS,
    SimpleSilenceDetector,
)

# Drop segments shorter than this (avoids transcribing stray clicks).
MIN_SEGMENT_MS = 250.0


class AudioBuffer:
    """Buffer that yields finalized PCM segments on silence / max-duration."""

    def __init__(self, sample_rate: int = 16000, *, silence_ms: int = 900,
                 max_segment_seconds: int = 25, sample_width: int = 2,
                 channels: int = 1,
                 threshold_rms: float = DEFAULT_THRESHOLD_RMS) -> None:
        self.sample_rate = sample_rate
        self.sample_width = sample_width
        self.channels = channels
        self.max_segment_seconds = max_segment_seconds
        self._chunks: list[bytes] = []
        self._bytes = 0
        self._detector = SimpleSilenceDetector(
            sample_rate, silence_ms, threshold_rms=threshold_rms,
            sample_width=sample_width)

    # -- accumulation --------------------------------------------------------
    @property
    def duration_s(self) -> float:
        frames = self._bytes // max(1, self.sample_width * self.channels)
        return frames / float(self.sample_rate) if self.sample_rate else 0.0

    @property
    def has_speech(self) -> bool:
        return self._detector.had_speech

    def _pop(self) -> bytes | None:
        pcm = b"".join(self._chunks)
        self._chunks.clear()
        self._bytes = 0
        had_speech = self._detector.had_speech
        self._detector.reset()
        ms = (len(pcm) // max(1, self.sample_width)) / float(self.sample_rate) * 1000.0
        if not had_speech or ms < MIN_SEGMENT_MS:
            return None
        return pcm

    def feed(self, pcm: bytes) -> bytes | None:
        """Add a chunk; return a finalized segment (bytes) at a boundary, else None."""
        if not pcm:
            return None
        self._chunks.append(pcm)
        self._bytes += len(pcm)
        self._detector.feed(pcm)
        if self._detector.silence_reached():
            return self._pop()
        if self.duration_s >= self.max_segment_seconds:
            return self._pop()
        return None

    def flush(self) -> bytes | None:
        """Finalize whatever remains (e.g. on Stop). None if no real speech."""
        if not self._chunks:
            return None
        return self._pop()

    def clear(self) -> None:
        self._chunks.clear()
        self._bytes = 0
        self._detector.reset()
