"""Simple energy-based silence detection for buffered dictation.

Pure Python (stdlib ``array``) — no numpy, no audio dependency. Operates on raw
**16-bit signed mono PCM** chunks (the format the recorder produces and the
transcriber consumes), so it is fully unit-testable with synthetic bytes.
"""

from __future__ import annotations

import array
import math

DEFAULT_THRESHOLD_RMS = 500.0     # int16 RMS below this reads as silence


def rms(pcm: bytes, sample_width: int = 2) -> float:
    """Root-mean-square amplitude of 16-bit mono PCM. 0.0 for empty/odd input."""
    if not pcm or sample_width != 2:
        return 0.0
    usable = len(pcm) - (len(pcm) % 2)
    if usable <= 0:
        return 0.0
    samples = array.array("h")
    samples.frombytes(pcm[:usable])
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))


def _chunk_ms(pcm: bytes, sample_rate: int, sample_width: int) -> float:
    frames = len(pcm) // max(1, sample_width)
    return (frames / float(sample_rate)) * 1000.0 if sample_rate else 0.0


class SimpleSilenceDetector:
    """Tracks trailing silence so a segment can be finalized after a pause."""

    def __init__(self, sample_rate: int = 16000, silence_ms: int = 900, *,
                 threshold_rms: float = DEFAULT_THRESHOLD_RMS,
                 sample_width: int = 2) -> None:
        self.sample_rate = sample_rate
        self.silence_ms = silence_ms
        self.threshold_rms = threshold_rms
        self.sample_width = sample_width
        self._trailing_silence_ms = 0.0
        self._had_speech = False

    def is_silent(self, pcm: bytes) -> bool:
        return rms(pcm, self.sample_width) < self.threshold_rms

    def feed(self, pcm: bytes) -> None:
        ms = _chunk_ms(pcm, self.sample_rate, self.sample_width)
        if self.is_silent(pcm):
            self._trailing_silence_ms += ms
        else:
            self._had_speech = True
            self._trailing_silence_ms = 0.0

    @property
    def trailing_silence_ms(self) -> float:
        return self._trailing_silence_ms

    @property
    def had_speech(self) -> bool:
        return self._had_speech

    def silence_reached(self) -> bool:
        """True once speech was heard and a long-enough pause has followed."""
        return self._had_speech and self._trailing_silence_ms >= self.silence_ms

    def reset(self) -> None:
        self._trailing_silence_ms = 0.0
        self._had_speech = False
