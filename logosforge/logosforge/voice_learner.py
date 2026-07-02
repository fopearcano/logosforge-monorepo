"""Voice profile learning — infers traits from a character's dialogue.

Collects dialogue segments per speaker, computes style metrics
(sentence length, contraction rate, punctuation habits, vocabulary
level), and merges inferred traits into the stored VoiceProfile
without overwriting user-defined values.

Primary API:
    ``analyze_voice(segments)``  — pure analysis, returns ``VoiceAnalysis``
    ``learn_voice_profile(db, character_id, segments, user_locked=())``
        — analyzes + merges into the DB profile
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from logosforge.dialogue_attribution import DialogueSegment


@dataclass(slots=True)
class VoiceAnalysis:
    """Inferred voice traits from dialogue samples."""

    sentence_length: str
    vocabulary_level: str
    tone: str
    punctuation_style: dict[str, float]
    quirks: list[str]
    dialogue_markers: list[str]
    confidence: float
    sample_count: int


_CONTRACTION_RE = re.compile(
    r"\b(?:i'm|i'll|i've|i'd|"
    r"you're|you'll|you've|you'd|"
    r"he's|she's|it's|we're|they're|"
    r"he'll|she'll|we'll|they'll|"
    r"he'd|she'd|we'd|they'd|"
    r"isn't|aren't|wasn't|weren't|"
    r"don't|doesn't|didn't|"
    r"won't|wouldn't|couldn't|shouldn't|"
    r"can't|haven't|hasn't|hadn't|"
    r"let's|that's|there's|who's|what's|"
    r"ain't|gonna|wanna|gotta)\b",
    re.IGNORECASE,
)

_SENTENCE_RE = re.compile(r"[^.!?]+[.!?]+|[^.!?]+$")

_ELEVATED_WORDS = frozenset((
    "nevertheless", "furthermore", "consequently", "henceforth",
    "moreover", "notwithstanding", "aforementioned", "pursuant",
    "whereby", "wherein", "therefore", "thus", "hence",
    "whilst", "amongst", "perhaps", "indeed", "certainly",
    "precisely", "undoubtedly", "exceedingly", "remarkably",
    "shall", "whom", "ought", "endeavour", "endeavor",
))

_SIMPLE_INDICATORS = frozenset((
    "yeah", "yep", "nah", "nope", "huh", "wow", "dude",
    "cool", "stuff", "kinda", "sorta", "totally", "like",
    "ok", "okay", "hey", "yo", "damn", "hell", "crap",
    "gotta", "gonna", "wanna", "ain't", "dunno", "lemme",
))

_MARKER_RE = re.compile(
    r"^(well|look|listen|hey|so|right|okay|oh|ah|hmm|"
    r"indeed|actually|honestly|seriously|basically|"
    r"y'know|you see|I mean|I say)\b",
    re.IGNORECASE,
)

_EXISTING_WEIGHT = 0.7
_LEARNED_WEIGHT = 0.3

_MIN_SAMPLES = 3


def _collect_speaker_text(
    segments: list[DialogueSegment],
    character_id: int,
) -> list[str]:
    return [s.text for s in segments if s.speaker_id == character_id and s.text.strip()]


def _avg_sentence_length(lines: list[str]) -> float:
    word_counts: list[int] = []
    for line in lines:
        for sent_m in _SENTENCE_RE.finditer(line):
            words = sent_m.group().split()
            if words:
                word_counts.append(len(words))
    return sum(word_counts) / max(len(word_counts), 1)


def _classify_sentence_length(avg: float) -> str:
    if avg <= 6:
        return "short"
    if avg <= 14:
        return "medium"
    return "long"


def _contraction_rate(lines: list[str]) -> float:
    total_words = sum(len(line.split()) for line in lines)
    if total_words == 0:
        return 0.0
    contraction_count = sum(len(_CONTRACTION_RE.findall(line)) for line in lines)
    return contraction_count / total_words


def _classify_tone(contraction_rate: float, avg_sent_len: float) -> str:
    if contraction_rate >= 0.08 and avg_sent_len <= 8:
        return "casual"
    if contraction_rate <= 0.02 and avg_sent_len >= 10:
        return "formal"
    return "neutral"


def _punctuation_usage(lines: list[str]) -> dict[str, float]:
    total = max(len(lines), 1)
    counts: dict[str, int] = {
        "exclamations": 0,
        "questions": 0,
        "ellipses": 0,
        "dashes": 0,
    }
    for line in lines:
        if "!" in line:
            counts["exclamations"] += 1
        if "?" in line:
            counts["questions"] += 1
        if "..." in line or "…" in line:
            counts["ellipses"] += 1
        if "—" in line or "--" in line:
            counts["dashes"] += 1
    return {k: round(v / total, 3) for k, v in counts.items()}


def _classify_vocabulary(lines: list[str]) -> str:
    words: list[str] = []
    for line in lines:
        words.extend(re.findall(r"[a-z']+", line.lower()))
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


def _detect_quirks(lines: list[str], contraction_rate: float) -> list[str]:
    quirks: list[str] = []
    if contraction_rate < 0.01 and len(lines) >= _MIN_SAMPLES:
        quirks.append("avoids contractions")
    if contraction_rate >= 0.10:
        quirks.append("heavy contraction use")

    ellipsis_count = sum(1 for l in lines if "..." in l or "…" in l)
    if len(lines) >= _MIN_SAMPLES and ellipsis_count / len(lines) >= 0.4:
        quirks.append("trails off frequently")

    excl_count = sum(1 for l in lines if "!" in l)
    if len(lines) >= _MIN_SAMPLES and excl_count / len(lines) >= 0.5:
        quirks.append("exclamatory speaker")

    return quirks


def _detect_markers(lines: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    for line in lines:
        m = _MARKER_RE.match(line.strip())
        if m:
            marker = m.group(1)
            normalised = marker[0].upper() + marker[1:].lower()
            counts[normalised] = counts.get(normalised, 0) + 1
    threshold = max(2, len(lines) // 5)
    return [m for m, c in sorted(counts.items(), key=lambda x: -x[1]) if c >= threshold]


def _confidence(sample_count: int) -> float:
    if sample_count < _MIN_SAMPLES:
        return round(sample_count / _MIN_SAMPLES * 0.3, 2)
    return round(min(0.3 + (sample_count - _MIN_SAMPLES) * 0.07, 1.0), 2)


def analyze_voice(
    segments: list[DialogueSegment],
    character_id: int,
) -> VoiceAnalysis:
    """Analyze dialogue segments for one character, returning inferred traits."""
    lines = _collect_speaker_text(segments, character_id)
    sample_count = len(lines)
    if sample_count == 0:
        return VoiceAnalysis(
            sentence_length="medium",
            vocabulary_level="standard",
            tone="neutral",
            punctuation_style={},
            quirks=[],
            dialogue_markers=[],
            confidence=0.0,
            sample_count=0,
        )

    avg_sl = _avg_sentence_length(lines)
    cr = _contraction_rate(lines)

    return VoiceAnalysis(
        sentence_length=_classify_sentence_length(avg_sl),
        vocabulary_level=_classify_vocabulary(lines),
        tone=_classify_tone(cr, avg_sl),
        punctuation_style=_punctuation_usage(lines),
        quirks=_detect_quirks(lines, cr),
        dialogue_markers=_detect_markers(lines),
        confidence=_confidence(sample_count),
        sample_count=sample_count,
    )


def _merge_field(existing: str, learned: str, locked: bool) -> str:
    if locked or existing == learned:
        return existing
    return learned


def _merge_list(
    existing: list[str],
    learned: list[str],
    locked: bool,
) -> list[str]:
    if locked:
        return existing
    seen: set[str] = set()
    merged: list[str] = []
    for item in existing + learned:
        if item not in seen:
            seen.add(item)
            merged.append(item)
    return merged


def _merge_punctuation(
    existing: dict,
    learned: dict[str, float],
    locked: bool,
) -> dict:
    if locked or not learned:
        return existing
    merged = dict(existing)
    for k, v in learned.items():
        if k in merged:
            merged[k] = round(
                merged[k] * _EXISTING_WEIGHT + v * _LEARNED_WEIGHT, 3,
            )
        else:
            merged[k] = v
    return merged


def learn_voice_profile(
    db,
    character_id: int,
    segments: list[DialogueSegment],
    *,
    user_locked: tuple[str, ...] = (),
    project_id: int | None = None,
) -> VoiceAnalysis:
    """Analyze dialogue and merge inferred traits into the stored profile.

    *user_locked* names fields the user has explicitly set — these are
    never overwritten by inference (e.g. ``("tone", "vocabulary_level")``).

    Creates a new profile if one doesn't exist yet.  When *project_id*
    is provided, the PSYKE character entry's "voice" field is kept in
    sync automatically.
    """
    analysis = analyze_voice(segments, character_id)

    if analysis.confidence == 0.0:
        return analysis

    existing = db.get_voice_profile_data(character_id)

    if existing is None:
        db.create_voice_profile(
            character_id,
            tone=analysis.tone,
            sentence_length=analysis.sentence_length,
            vocabulary_level=analysis.vocabulary_level,
            quirks=analysis.quirks,
            punctuation_style=analysis.punctuation_style,
            dialogue_markers=analysis.dialogue_markers,
        )
    else:
        db.update_voice_profile(
            character_id,
            tone=_merge_field(
                existing["tone"], analysis.tone, "tone" in user_locked,
            ),
            sentence_length=_merge_field(
                existing["sentence_length"],
                analysis.sentence_length,
                "sentence_length" in user_locked,
            ),
            vocabulary_level=_merge_field(
                existing["vocabulary_level"],
                analysis.vocabulary_level,
                "vocabulary_level" in user_locked,
            ),
            quirks=_merge_list(
                existing["quirks"], analysis.quirks, "quirks" in user_locked,
            ),
            punctuation_style=_merge_punctuation(
                existing["punctuation_style"],
                analysis.punctuation_style,
                "punctuation_style" in user_locked,
            ),
            dialogue_markers=_merge_list(
                existing["dialogue_markers"],
                analysis.dialogue_markers,
                "dialogue_markers" in user_locked,
            ),
        )

    if project_id is not None:
        db.sync_voice_to_psyke(character_id, project_id)

    return analysis


# ---------------------------------------------------------------------------
# Voice rewrite — heuristic transforms to match a profile
# ---------------------------------------------------------------------------

_EXPANSION_MAP: dict[str, str] = {
    "i'm": "I am", "i'll": "I will", "i've": "I have", "i'd": "I would",
    "you're": "you are", "you'll": "you will", "you've": "you have",
    "you'd": "you would",
    "he's": "he is", "she's": "she is", "it's": "it is",
    "we're": "we are", "they're": "they are",
    "he'll": "he will", "she'll": "she will",
    "we'll": "we will", "they'll": "they will",
    "he'd": "he would", "she'd": "she would",
    "we'd": "we would", "they'd": "they would",
    "isn't": "is not", "aren't": "are not",
    "wasn't": "was not", "weren't": "were not",
    "don't": "do not", "doesn't": "does not", "didn't": "did not",
    "won't": "will not", "wouldn't": "would not",
    "couldn't": "could not", "shouldn't": "should not",
    "can't": "cannot", "haven't": "have not",
    "hasn't": "has not", "hadn't": "had not",
    "let's": "let us", "that's": "that is",
    "there's": "there is", "who's": "who is", "what's": "what is",
}

_CONTRACTION_MAP: dict[str, str] = {
    "I am": "I'm", "I will": "I'll", "I have": "I've", "I would": "I'd",
    "you are": "you're", "you will": "you'll", "you have": "you've",
    "you would": "you'd",
    "he is": "he's", "she is": "she's", "it is": "it's",
    "we are": "we're", "they are": "they're",
    "he will": "he'll", "she will": "she'll",
    "we will": "we'll", "they will": "they'll",
    "is not": "isn't", "are not": "aren't",
    "was not": "wasn't", "were not": "weren't",
    "do not": "don't", "does not": "doesn't", "did not": "didn't",
    "will not": "won't", "would not": "wouldn't",
    "could not": "couldn't", "should not": "shouldn't",
    "can not": "can't", "cannot": "can't",
    "have not": "haven't", "has not": "hasn't", "had not": "hadn't",
    "let us": "let's", "that is": "that's",
    "there is": "there's",
}


def _expand_contractions(text: str) -> str:
    def _replace(m: re.Match) -> str:
        word = m.group(0)
        expanded = _EXPANSION_MAP.get(word.lower())
        if expanded is None:
            return word
        if word[0].isupper():
            return expanded[0].upper() + expanded[1:]
        return expanded
    return _CONTRACTION_RE.sub(_replace, text)


def _add_contractions(text: str) -> str:
    result = text
    for full, short in sorted(
        _CONTRACTION_MAP.items(), key=lambda x: -len(x[0]),
    ):
        pattern = re.compile(
            r"\b" + re.escape(full) + r"\b", re.IGNORECASE,
        )
        def _repl(m: re.Match, s=short) -> str:
            if m.group(0)[0].isupper():
                return s[0].upper() + s[1:]
            return s
        result = pattern.sub(_repl, result)
    return result


def _shorten_sentences(text: str) -> str:
    sentences: list[str] = []
    for m in _SENTENCE_RE.finditer(text):
        sent = m.group().strip()
        words = sent.split()
        if len(words) > 10:
            mid = len(words) // 2
            for i in range(mid - 2, mid + 3):
                if 0 < i < len(words) and words[i].lower() in (
                    "and", "but", "so", "then", "because", "while",
                ):
                    first = " ".join(words[:i])
                    rest = " ".join(words[i + 1:])
                    if not first.endswith((".", "!", "?")):
                        first += "."
                    if rest and rest[0].islower():
                        rest = rest[0].upper() + rest[1:]
                    sentences.append(first)
                    sentences.append(rest)
                    break
            else:
                sentences.append(sent)
        else:
            sentences.append(sent)
    return " ".join(sentences)


def _lengthen_sentences(text: str) -> str:
    sentences = [m.group().strip() for m in _SENTENCE_RE.finditer(text)]
    if len(sentences) < 2:
        return text
    merged: list[str] = []
    i = 0
    while i < len(sentences):
        sent = sentences[i]
        words = sent.split()
        if len(words) <= 5 and i + 1 < len(sentences):
            next_sent = sentences[i + 1]
            joined = sent.rstrip(".!?") + ", and " + next_sent[0].lower() + next_sent[1:]
            merged.append(joined)
            i += 2
        else:
            merged.append(sent)
            i += 1
    return " ".join(merged)


@dataclass(slots=True)
class VoiceRewrite:
    """A single voice-matched rewrite alternative."""

    text: str
    label: str


# ---------------------------------------------------------------------------
# State-based voice adjustment (PSYKE integration)
# ---------------------------------------------------------------------------

_STRESS_VOICE_SIGNALS = frozenset({
    "stressed", "tense", "anxious", "nervous", "panicked", "rushed",
    "urgent", "frantic", "desperate", "afraid", "scared", "terrified",
    "hunted", "trapped", "cornered", "fleeing",
})

_CONFIDENCE_VOICE_SIGNALS = frozenset({
    "confident", "commanding", "authoritative", "assertive", "bold",
    "decisive", "determined", "powerful", "composed", "resolute",
})

_EMOTION_VOICE_SIGNALS = frozenset({
    "grief", "rage", "ecstasy", "despair", "anguish", "fury",
    "passion", "agony", "devastated", "overwhelmed", "heartbroken",
    "euphoric", "shattered", "hysterical",
})

_SL_ORDER = ("short", "medium", "long")
_TONE_ORDER = ("casual", "neutral", "formal")


def adjust_voice_for_state(profile: dict, state_text: str) -> dict:
    """Return a copy of *profile* shifted by character state.

    Stressed → shorter sentences.
    Confident → more formal/direct tone.
    High emotion → casual tone, shorter sentences.

    Only adjusts when the current value sits on the standard scale
    (short/medium/long, casual/neutral/formal).  Exotic tones like
    "abrasive" are left untouched.
    """
    if not state_text or not profile:
        return dict(profile)

    words = set(re.findall(r"[a-z]+", state_text.lower()))
    if not words:
        return dict(profile)

    stress = len(words & _STRESS_VOICE_SIGNALS)
    confidence = len(words & _CONFIDENCE_VOICE_SIGNALS)
    emotion = len(words & _EMOTION_VOICE_SIGNALS)

    if not stress and not confidence and not emotion:
        return dict(profile)

    adjusted = dict(profile)
    adjusted["quirks"] = list(profile.get("quirks", []))
    adjusted["punctuation_style"] = dict(profile.get("punctuation_style", {}))
    adjusted["dialogue_markers"] = list(profile.get("dialogue_markers", []))

    cur_sl = profile.get("sentence_length", "medium")
    cur_tone = profile.get("tone", "neutral")

    sl_idx = _SL_ORDER.index(cur_sl) if cur_sl in _SL_ORDER else None
    tone_idx = _TONE_ORDER.index(cur_tone) if cur_tone in _TONE_ORDER else None

    if sl_idx is not None:
        if stress >= 1:
            sl_idx = max(0, sl_idx - 1)
        if emotion >= 2:
            sl_idx = max(0, sl_idx - 1)
        adjusted["sentence_length"] = _SL_ORDER[sl_idx]

    if tone_idx is not None:
        if confidence >= 1:
            tone_idx = min(2, tone_idx + 1)
        if emotion >= 2:
            tone_idx = max(0, tone_idx - 1)
        adjusted["tone"] = _TONE_ORDER[tone_idx]

    return adjusted


def voice_profile_summary(profile: dict) -> str:
    """One-line human-readable summary of a voice profile dict."""
    parts: list[str] = []
    if profile.get("tone"):
        parts.append(f"Tone: {profile['tone']}")
    if profile.get("sentence_length"):
        parts.append(f"Sentences: {profile['sentence_length']}")
    if profile.get("vocabulary_level"):
        parts.append(f"Vocabulary: {profile['vocabulary_level']}")
    quirks = profile.get("quirks", [])
    if quirks:
        parts.append(f"Quirks: {', '.join(quirks)}")
    markers = profile.get("dialogue_markers", [])
    if markers:
        parts.append(f"Markers: {', '.join(markers)}")
    return ". ".join(parts) + "." if parts else ""


def generate_voice_rewrites(
    text: str,
    profile: dict,
) -> list[VoiceRewrite]:
    """Return 1–2 heuristic rewrites of *text* to match *profile*.

    Does NOT auto-apply. The caller presents the alternatives and the
    user chooses.
    """
    if not text.strip() or not profile:
        return []

    rewrites: list[VoiceRewrite] = []
    current_tone = _classify_tone(
        _contraction_rate([text]),
        _avg_sentence_length([text]),
    )
    target_tone = profile.get("tone", "neutral")

    target_sl = profile.get("sentence_length", "medium")
    current_sl = _classify_sentence_length(_avg_sentence_length([text]))

    quirks = profile.get("quirks", [])

    candidate = text

    if target_tone == "formal" and current_tone != "formal":
        candidate = _expand_contractions(candidate)
        rewrites.append(VoiceRewrite(
            text=candidate,
            label="More formal tone",
        ))
    elif target_tone == "casual" and current_tone != "casual":
        candidate = _add_contractions(candidate)
        rewrites.append(VoiceRewrite(
            text=candidate,
            label="More casual tone",
        ))

    if target_sl == "short" and current_sl in ("medium", "long"):
        shortened = _shorten_sentences(candidate if rewrites else text)
        if shortened != (candidate if rewrites else text):
            rewrites.append(VoiceRewrite(
                text=shortened,
                label="Shorter sentences",
            ))
    elif target_sl == "long" and current_sl == "short":
        lengthened = _lengthen_sentences(candidate if rewrites else text)
        if lengthened != (candidate if rewrites else text):
            rewrites.append(VoiceRewrite(
                text=lengthened,
                label="Longer sentences",
            ))

    if not rewrites and "avoids contractions" in quirks:
        expanded = _expand_contractions(text)
        if expanded != text:
            rewrites.append(VoiceRewrite(
                text=expanded,
                label="Expand contractions (character quirk)",
            ))

    if not rewrites and "heavy contraction use" in quirks:
        contracted = _add_contractions(text)
        if contracted != text:
            rewrites.append(VoiceRewrite(
                text=contracted,
                label="Add contractions (character quirk)",
            ))

    return rewrites[:2]
