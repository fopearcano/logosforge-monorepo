"""Voice consistency checker — flags dialogue that deviates from a character's profile.

For each ``DialogueSegment`` whose speaker has a ``VoiceProfile``, computes
a deviation score (0–1) across tone, sentence length, vocabulary, and
punctuation.  Lines above the threshold are returned with 1–2 human-readable
reasons.

Primary API:
    ``check_consistency(segments, profiles)``
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from logosforge.dialogue_attribution import DialogueSegment
from logosforge.voice_learner import (
    _CONTRACTION_RE,
    _ELEVATED_WORDS,
    _SENTENCE_RE,
    _SIMPLE_INDICATORS,
)


@dataclass(slots=True)
class VoiceDeviation:
    """A flagged dialogue line that deviates from the speaker's profile."""

    segment: DialogueSegment
    deviation_score: float
    reasons: list[str]


_DEFAULT_THRESHOLD = 0.45

VOICE_SENSITIVITY_LEVELS = ("low", "medium", "high")

_SENSITIVITY_THRESHOLDS: dict[str, float] = {
    "low": 0.60,
    "medium": 0.45,
    "high": 0.30,
}


def sensitivity_threshold(level: str) -> float:
    """Return the deviation threshold for a sensitivity level."""
    return _SENSITIVITY_THRESHOLDS.get(level, _DEFAULT_THRESHOLD)

_TONE_DISTANCE: dict[tuple[str, str], float] = {
    ("formal", "casual"): 1.0,
    ("casual", "formal"): 1.0,
    ("formal", "neutral"): 0.4,
    ("neutral", "formal"): 0.4,
    ("casual", "neutral"): 0.4,
    ("neutral", "casual"): 0.4,
}

_SL_DISTANCE: dict[tuple[str, str], float] = {
    ("short", "long"): 1.0,
    ("long", "short"): 1.0,
    ("short", "medium"): 0.4,
    ("medium", "short"): 0.4,
    ("medium", "long"): 0.4,
    ("long", "medium"): 0.4,
}

_VOCAB_DISTANCE: dict[tuple[str, str], float] = {
    ("simple", "elevated"): 1.0,
    ("elevated", "simple"): 1.0,
    ("simple", "standard"): 0.4,
    ("standard", "simple"): 0.4,
    ("standard", "elevated"): 0.4,
    ("elevated", "standard"): 0.4,
}

_TONE_REASONS = {
    ("casual", "formal"): "too formal for this character",
    ("formal", "casual"): "too casual for this character",
    ("neutral", "formal"): "too formal for this character",
    ("neutral", "casual"): "too casual for this character",
    ("casual", "neutral"): "unusually restrained tone",
    ("formal", "neutral"): "unusually informal tone",
}

_SL_REASONS = {
    ("short", "long"): "sentence length unusually long",
    ("short", "medium"): "sentence length unusually long",
    ("long", "short"): "sentence length unusually short",
    ("long", "medium"): "sentence length unusually short",
    ("medium", "long"): "sentence length unusually long",
    ("medium", "short"): "sentence length unusually short",
}


def _line_avg_sentence_length(text: str) -> float:
    counts: list[int] = []
    for m in _SENTENCE_RE.finditer(text):
        words = m.group().split()
        if words:
            counts.append(len(words))
    return sum(counts) / max(len(counts), 1)


def _classify_sentence_length(avg: float) -> str:
    if avg <= 6:
        return "short"
    if avg <= 14:
        return "medium"
    return "long"


def _line_contraction_rate(text: str) -> float:
    words = text.split()
    if not words:
        return 0.0
    return len(_CONTRACTION_RE.findall(text)) / len(words)


def _line_tone(text: str) -> str:
    cr = _line_contraction_rate(text)
    avg_sl = _line_avg_sentence_length(text)
    if cr >= 0.08 and avg_sl <= 8:
        return "casual"
    if cr <= 0.02 and avg_sl >= 10:
        return "formal"
    return "neutral"


def _line_vocabulary(text: str) -> str:
    words = re.findall(r"[a-z']+", text.lower())
    if not words:
        return "standard"
    total = len(words)
    elevated = sum(1 for w in words if w in _ELEVATED_WORDS)
    simple = sum(1 for w in words if w in _SIMPLE_INDICATORS)
    if elevated / total >= 0.03:
        return "elevated"
    if simple / total >= 0.05:
        return "simple"
    return "standard"


def _line_punctuation(text: str) -> dict[str, float]:
    return {
        "exclamations": 1.0 if "!" in text else 0.0,
        "questions": 1.0 if "?" in text else 0.0,
        "ellipses": 1.0 if ("..." in text or "…" in text) else 0.0,
        "dashes": 1.0 if ("—" in text or "--" in text) else 0.0,
    }


def _punctuation_deviation(
    profile_style: dict[str, float],
    line_style: dict[str, float],
) -> float:
    if not profile_style:
        return 0.0
    diffs: list[float] = []
    for key in ("exclamations", "questions", "ellipses", "dashes"):
        p_val = profile_style.get(key, 0.0)
        l_val = line_style.get(key, 0.0)
        diffs.append(abs(p_val - l_val))
    return sum(diffs) / len(diffs)


def _score_segment(
    text: str,
    profile: dict,
) -> tuple[float, list[str]]:
    """Compute deviation score and reasons for a single dialogue line."""
    scores: list[tuple[float, str | None]] = []

    line_t = _line_tone(text)
    prof_t = profile["tone"]
    tone_d = _TONE_DISTANCE.get((prof_t, line_t), 0.0)
    tone_reason = _TONE_REASONS.get((prof_t, line_t))
    scores.append((tone_d, tone_reason))

    avg_sl = _line_avg_sentence_length(text)
    line_sl = _classify_sentence_length(avg_sl)
    prof_sl = profile["sentence_length"]
    sl_d = _SL_DISTANCE.get((prof_sl, line_sl), 0.0)
    sl_reason = _SL_REASONS.get((prof_sl, line_sl))
    scores.append((sl_d, sl_reason))

    line_v = _line_vocabulary(text)
    prof_v = profile["vocabulary_level"]
    vocab_d = _VOCAB_DISTANCE.get((prof_v, line_v), 0.0)
    vocab_reason: str | None = None
    if vocab_d > 0:
        vocab_reason = "vocabulary mismatch"
    scores.append((vocab_d, vocab_reason))

    prof_punct = profile.get("punctuation_style", {})
    line_punct = _line_punctuation(text)
    punct_d = _punctuation_deviation(prof_punct, line_punct)
    punct_reason: str | None = None
    if punct_d >= 0.4:
        punct_reason = "punctuation style mismatch"
    scores.append((punct_d, punct_reason))

    deviation = sum(s for s, _ in scores) / len(scores)
    deviation = round(min(deviation, 1.0), 3)

    ranked = sorted(scores, key=lambda x: -x[0])
    reasons = [r for _, r in ranked if r is not None][:2]

    return deviation, reasons


def check_consistency(
    segments: list[DialogueSegment],
    profiles: dict[int, dict],
    *,
    threshold: float = _DEFAULT_THRESHOLD,
) -> list[VoiceDeviation]:
    """Check dialogue segments against their speakers' voice profiles.

    *profiles* maps ``character_id`` → deserialized profile dict (as
    returned by ``db.get_voice_profile_data()``).  Segments whose
    speaker is ``None`` or has no profile are silently skipped.

    Returns a list of ``VoiceDeviation`` for segments whose deviation
    score exceeds *threshold*.
    """
    deviations: list[VoiceDeviation] = []

    for seg in segments:
        if seg.speaker_id is None:
            continue
        profile = profiles.get(seg.speaker_id)
        if profile is None:
            continue

        text = seg.text.strip()
        if not text:
            continue

        score, reasons = _score_segment(text, profile)

        if score >= threshold:
            deviations.append(VoiceDeviation(
                segment=seg,
                deviation_score=score,
                reasons=reasons,
            ))

    return deviations
