"""Style analysis for manuscript paragraphs.

Computes per-paragraph style metrics (clarity, concision, rhythm,
tone_consistency, dialogue_naturalness) using heuristic rules.
No external dependencies required.

Primary API: ``analyze_style(text)`` returns cached ``ParagraphStyle``.
Optional: ``StyleRefineWorker`` runs an async LLM call to refine heuristics.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass
class ParagraphStyle:
    """Style metrics for a single paragraph."""

    paragraph_id: int
    metrics: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    last_updated: float = 0.0

    def __post_init__(self) -> None:
        if not self.last_updated:
            self.last_updated = time.time()


@dataclass(frozen=True)
class StyleHint:
    """A single inline style issue with character-level position."""

    start: int
    end: int
    hint_type: str
    message: str


@dataclass(frozen=True)
class StyleSuggestion:
    """A single actionable style suggestion."""

    category: str
    message: str


@dataclass
class StyleContext:
    """PSYKE-derived context that adjusts style expectations."""

    stress_level: float = 0.0
    formality_level: float = 0.0
    emotional_intensity: float = 0.0


# ---------------------------------------------------------------------------
# PSYKE signal words for style context
# ---------------------------------------------------------------------------

_STRESS_SIGNALS = frozenset({
    "stressed", "tense", "anxious", "nervous", "panicked", "rushed",
    "urgent", "frantic", "desperate", "afraid", "scared", "terrified",
    "hunted", "trapped", "cornered", "fleeing", "fearful", "restless",
})

_FORMALITY_SIGNALS = frozenset({
    "formal", "dignified", "regal", "noble", "composed", "proper",
    "educated", "aristocratic", "diplomatic", "refined", "ceremonial",
    "professional", "scholarly", "authoritative", "reserved", "stiff",
})

_EMOTION_INTENSITY_SIGNALS = frozenset({
    "grief", "rage", "ecstasy", "despair", "anguish", "fury",
    "passion", "agony", "torment", "devastated", "overwhelmed",
    "elated", "heartbroken", "euphoric", "shattered", "hysterical",
})

_STYLE_PSYKE_WEIGHT = 0.15
_STYLE_SIGNAL_DIVISOR = 3


def build_style_context(
    db: object, project_id: int, scene_id: int,
) -> StyleContext:
    """Build style context from PSYKE character states and memories."""
    texts: list[str] = []
    for _cid, state in db.get_scene_character_states(scene_id):
        texts.append(state)
    for mem in db.get_memories(project_id, scene_id):
        texts.append(mem.value)
    if not texts:
        return StyleContext()
    combined = " ".join(texts).lower()
    found = set(re.findall(r"[a-z]+", combined))
    if not found:
        return StyleContext()
    return StyleContext(
        stress_level=min(1.0, len(found & _STRESS_SIGNALS) / _STYLE_SIGNAL_DIVISOR),
        formality_level=min(1.0, len(found & _FORMALITY_SIGNALS) / _STYLE_SIGNAL_DIVISOR),
        emotional_intensity=min(1.0, len(found & _EMOTION_INTENSITY_SIGNALS) / _STYLE_SIGNAL_DIVISOR),
    )


def apply_style_context(
    style: ParagraphStyle, context: StyleContext,
) -> ParagraphStyle:
    """Adjust style metrics based on PSYKE context.

    When writing matches character state, scores are boosted:
    - stress → short uniform rhythm is appropriate
    - formality → formal tone and structured dialogue expected
    - emotional intensity → tone shifts are expressive, not inconsistent
    """
    if (
        not context.stress_level
        and not context.formality_level
        and not context.emotional_intensity
    ):
        return style
    m = dict(style.metrics)
    w = _STYLE_PSYKE_WEIGHT
    if "rhythm" in m:
        m["rhythm"] = min(1.0, round(m["rhythm"] + context.stress_level * w, 3))
    if "tone_consistency" in m:
        m["tone_consistency"] = min(
            1.0,
            round(
                m["tone_consistency"]
                + context.formality_level * w
                + context.emotional_intensity * w,
                3,
            ),
        )
    if "dialogue_naturalness" in m:
        m["dialogue_naturalness"] = min(
            1.0,
            round(m["dialogue_naturalness"] + context.formality_level * w, 3),
        )
    return ParagraphStyle(
        paragraph_id=style.paragraph_id,
        metrics=m,
        notes=list(style.notes),
        last_updated=style.last_updated,
    )


# ---------------------------------------------------------------------------
# Style sensitivity
# ---------------------------------------------------------------------------

STYLE_SENSITIVITY_LEVELS = ("low", "medium", "high")

_SENSITIVITY_CONFIG: dict[str, dict[str, int]] = {
    "low":    {"max_hints": 1, "long_sent": 40, "repeat_count": 4, "min_sents_rhythm": 6},
    "medium": {"max_hints": 3, "long_sent": 30, "repeat_count": 3, "min_sents_rhythm": 4},
    "high":   {"max_hints": 5, "long_sent": 20, "repeat_count": 2, "min_sents_rhythm": 3},
}


# ---------------------------------------------------------------------------
# Heuristic helpers
# ---------------------------------------------------------------------------

_FILLER_WORDS = frozenset({
    "very", "really", "just", "quite", "rather", "somewhat", "basically",
    "actually", "literally", "honestly", "simply", "totally", "completely",
    "absolutely", "definitely", "certainly", "perhaps", "maybe",
})

_WEAK_VERBS = frozenset({
    "is", "was", "were", "are", "am", "been", "being",
    "has", "have", "had", "do", "does", "did",
    "seem", "seems", "seemed", "appear", "appears", "appeared",
})

_SUBORDINATE_STARTERS = frozenset({
    "which", "that", "who", "whom", "whose", "where", "when",
    "although", "because", "since", "while", "whereas",
})

_ADVERBS = frozenset({
    "very", "really", "extremely", "incredibly", "absolutely", "totally",
    "completely", "utterly", "thoroughly", "remarkably", "terribly",
    "awfully", "exceedingly", "immensely", "enormously", "vastly",
    "deeply", "highly", "greatly", "strongly", "firmly", "slightly",
    "barely", "hardly", "nearly", "mostly", "largely", "roughly",
    "quickly", "slowly", "suddenly", "immediately", "eventually",
    "finally", "constantly", "frequently", "occasionally", "rarely",
})

_DIALOGUE_RE = re.compile(
    r'["“][^"”]*["”]'
    r"|"
    r"['‘][^'’]*['’]",
)


def _words(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z']+", text.lower())


def _sentences(text: str) -> list[str]:
    parts = re.split(r'[.!?]+', text)
    return [s.strip() for s in parts if s.strip()]


# ---------------------------------------------------------------------------
# Metric computations
# ---------------------------------------------------------------------------

def _repeated_word_ratio(words: list[str]) -> float:
    if len(words) < 4:
        return 0.0
    skip = {"the", "a", "an", "and", "or", "but", "in", "on", "of", "to",
            "is", "was", "it", "he", "she", "i", "we", "they", "his", "her"}
    content = [w for w in words if w not in skip and len(w) > 2]
    if not content:
        return 0.0
    from collections import Counter
    counts = Counter(content)
    repeated = sum(c - 1 for c in counts.values() if c > 1)
    return repeated / len(content)


def _clarity(text: str, words: list[str], sentences: list[str]) -> float:
    if not words or not sentences:
        return 1.0
    avg_sentence_len = len(words) / len(sentences)
    long_word_ratio = sum(1 for w in words if len(w) > 12) / len(words)
    subordinate_count = sum(1 for w in words if w in _SUBORDINATE_STARTERS)
    subordinate_ratio = subordinate_count / len(sentences) if sentences else 0
    repeat_ratio = _repeated_word_ratio(words)

    score = 1.0
    if avg_sentence_len > 25:
        score -= min(0.3, (avg_sentence_len - 25) * 0.015)
    if avg_sentence_len > 40:
        score -= 0.2
    score -= long_word_ratio * 1.5
    score -= subordinate_ratio * 0.15
    score -= repeat_ratio * 0.8
    return max(0.0, min(1.0, score))


def _adverb_ratio(words: list[str]) -> float:
    if not words:
        return 0.0
    return sum(1 for w in words if w in _ADVERBS) / len(words)


def _concision(text: str, words: list[str], sentences: list[str]) -> float:
    if not words:
        return 1.0
    filler_count = sum(1 for w in words if w in _FILLER_WORDS)
    filler_ratio = filler_count / len(words)

    weak_verb_count = sum(1 for w in words if w in _WEAK_VERBS)
    weak_ratio = weak_verb_count / len(words)

    prep_count = sum(1 for w in words if w in {"of", "in", "on", "at", "to", "for", "with", "by"})
    prep_ratio = prep_count / len(words)

    adverb_r = _adverb_ratio(words)

    avg_sentence_len = len(words) / max(len(sentences), 1)

    score = 1.0
    score -= filler_ratio * 4.0
    score -= max(0, weak_ratio - 0.08) * 2.0
    score -= max(0, prep_ratio - 0.12) * 1.5
    score -= max(0, adverb_r - 0.05) * 3.0
    if avg_sentence_len > 30:
        score -= min(0.25, (avg_sentence_len - 30) * 0.012)
    return max(0.0, min(1.0, score))


def _rhythm(sentences: list[str]) -> float:
    if len(sentences) < 2:
        return 1.0
    lengths = [len(s.split()) for s in sentences]
    avg = sum(lengths) / len(lengths)
    if avg == 0:
        return 1.0

    variance = sum((l - avg) ** 2 for l in lengths) / len(lengths)
    cv = (variance ** 0.5) / avg

    if cv < 0.1:
        return 0.5
    if cv > 1.5:
        return 0.5
    if 0.3 <= cv <= 0.8:
        return 1.0
    if cv < 0.3:
        return 0.5 + (cv - 0.1) * 2.5
    return 1.0 - (cv - 0.8) * 0.7


def _tone_consistency(sentences: list[str]) -> float:
    if len(sentences) < 2:
        return 1.0

    def _sentence_register(s: str) -> str:
        w = s.lower().split()
        exclaim = s.endswith("!")
        question = s.endswith("?")
        has_contraction = any("'" in word for word in w)
        avg_word_len = sum(len(word) for word in w) / max(len(w), 1)
        if exclaim or has_contraction or avg_word_len < 4.5:
            return "informal"
        if avg_word_len > 6.0:
            return "formal"
        return "neutral"

    registers = [_sentence_register(s) for s in sentences]
    unique = set(registers)
    if len(unique) <= 1:
        return 1.0
    if "formal" in unique and "informal" in unique:
        return 0.5
    return 0.8


def _dialogue_naturalness(text: str) -> float | None:
    matches = _DIALOGUE_RE.findall(text)
    if not matches:
        return None

    scores: list[float] = []
    for quote in matches:
        inner = quote[1:-1].strip()
        words = inner.split()
        if not words:
            continue
        score = 1.0
        if len(words) > 50:
            score -= 0.3
        if len(words) > 80:
            score -= 0.2
        semicolons = inner.count(";")
        if semicolons > 0:
            score -= semicolons * 0.15
        colons = inner.count(":")
        if colons > 1:
            score -= 0.1
        ellipsis_count = inner.count("...") + inner.count("…")
        if ellipsis_count > 2:
            score -= 0.1
        excl = inner.count("!")
        if excl > 3:
            score -= min(0.2, (excl - 3) * 0.05)
        long_words = sum(1 for w in words if len(w) > 10)
        if long_words / max(len(words), 1) > 0.15:
            score -= 0.2
        has_contraction = any("'" in w or "’" in w for w in words)
        if has_contraction:
            score += 0.05
        scores.append(max(0.0, min(1.0, score)))

    return sum(scores) / len(scores) if scores else None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_paragraph(paragraph_id: int, text: str) -> ParagraphStyle:
    """Compute style metrics for a paragraph of text."""
    words = _words(text)
    sentences = _sentences(text)

    metrics: dict[str, float] = {
        "clarity": round(_clarity(text, words, sentences), 3),
        "concision": round(_concision(text, words, sentences), 3),
        "rhythm": round(_rhythm(sentences), 3),
        "tone_consistency": round(_tone_consistency(sentences), 3),
    }

    dialogue = _dialogue_naturalness(text)
    if dialogue is not None:
        metrics["dialogue_naturalness"] = round(dialogue, 3)

    notes: list[str] = []
    if metrics["clarity"] < 0.6:
        notes.append("Sentences may be too complex or long")
    if _repeated_word_ratio(words) > 0.15:
        notes.append("Some words repeat frequently")
    if metrics["concision"] < 0.6:
        notes.append("Consider removing filler words")
    if _adverb_ratio(words) > 0.1:
        notes.append("Excessive adverbs weaken the prose")
    if metrics["rhythm"] < 0.6:
        notes.append("Sentence lengths are too uniform")
    if metrics["tone_consistency"] < 0.7:
        notes.append("Tone shifts between formal and informal")
    if dialogue is not None and dialogue < 0.6:
        notes.append("Dialogue may sound unnatural")

    return ParagraphStyle(
        paragraph_id=paragraph_id,
        metrics=metrics,
        notes=notes,
    )


def analyze_paragraphs(text: str) -> list[ParagraphStyle]:
    """Analyze all paragraphs in a block of text."""
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    return [analyze_paragraph(i, p) for i, p in enumerate(paragraphs)]


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_style_cache: dict[str, ParagraphStyle] = {}
_STYLE_CACHE_MAX = 512


def _cache_key(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _cache_get(text: str) -> ParagraphStyle | None:
    return _style_cache.get(_cache_key(text))


def _cache_put(text: str, style: ParagraphStyle) -> None:
    if len(_style_cache) >= _STYLE_CACHE_MAX:
        _style_cache.clear()
    _style_cache[_cache_key(text)] = style


def clear_cache() -> None:
    """Clear the style analysis cache."""
    _style_cache.clear()


# ---------------------------------------------------------------------------
# Cached public API
# ---------------------------------------------------------------------------

def analyze_style(text: str) -> ParagraphStyle:
    """Compute style metrics with caching. Primary public API."""
    cached = _cache_get(text)
    if cached is not None:
        return cached
    result = analyze_paragraph(0, text)
    _cache_put(text, result)
    return result


# ---------------------------------------------------------------------------
# Inline style hints — character-level spans for underlines
# ---------------------------------------------------------------------------

_SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+')
_LONG_SENTENCE_THRESHOLD = 30
_MAX_HINTS_PER_PARAGRAPH = 3
_REPEAT_SKIP = frozenset({
    "the", "a", "an", "and", "or", "but", "in", "on", "of", "to",
    "is", "was", "it", "he", "she", "i", "we", "they", "his", "her",
    "that", "this", "for", "with", "not", "had", "has", "have",
})


def detect_style_hints(
    text: str,
    sensitivity: str = "medium",
) -> list[StyleHint]:
    """Detect inline style issues with character-level positions.

    *sensitivity* controls how aggressively hints are generated
    (``"low"`` / ``"medium"`` / ``"high"``).
    """
    cfg = _SENSITIVITY_CONFIG.get(sensitivity, _SENSITIVITY_CONFIG["medium"])
    max_hints = cfg["max_hints"]
    long_sent_threshold = cfg["long_sent"]
    repeat_count = cfg["repeat_count"]
    min_sents_rhythm = cfg["min_sents_rhythm"]

    hints: list[StyleHint] = []
    if not text.strip():
        return hints

    sentences = _SENTENCE_SPLIT_RE.split(text)
    sent_starts: list[int] = []
    pos = 0
    for s in sentences:
        idx = text.find(s, pos)
        sent_starts.append(idx)
        pos = idx + len(s)

    for i, sent in enumerate(sentences):
        if len(hints) >= max_hints:
            break
        word_count = len(sent.split())
        if word_count > long_sent_threshold:
            start = sent_starts[i]
            hints.append(StyleHint(
                start=start,
                end=start + len(sent),
                hint_type="clarity",
                message="Sentence may be too long",
            ))

    if len(hints) < max_hints:
        words_with_pos: list[tuple[str, int, int]] = [
            (m.group().lower(), m.start(), m.end())
            for m in re.finditer(r"[a-zA-Z']+", text)
        ]
        content_words: dict[str, list[tuple[int, int]]] = {}
        for w, s, e in words_with_pos:
            if w not in _REPEAT_SKIP and len(w) > 2:
                content_words.setdefault(w, []).append((s, e))
        flagged: set[str] = set()
        for word, positions in content_words.items():
            if len(hints) >= max_hints:
                break
            if len(positions) >= repeat_count and word not in flagged:
                flagged.add(word)
                s, e = positions[1]
                hints.append(StyleHint(
                    start=s, end=e,
                    hint_type="repetition",
                    message="Repetition detected",
                ))

    if len(hints) < max_hints and len(sentences) >= min_sents_rhythm:
        lengths = [len(s.split()) for s in sentences]
        avg = sum(lengths) / len(lengths) if lengths else 0
        if avg > 0:
            variance = sum((l - avg) ** 2 for l in lengths) / len(lengths)
            cv = (variance ** 0.5) / avg
            if cv < 0.15:
                start = sent_starts[0]
                end = sent_starts[0] + len(sentences[0])
                hints.append(StyleHint(
                    start=start, end=end,
                    hint_type="rhythm",
                    message="Rhythm feels monotonous",
                ))

    dialogue_matches = list(_DIALOGUE_RE.finditer(text))
    if len(hints) < max_hints and dialogue_matches:
        for m in dialogue_matches:
            if len(hints) >= max_hints:
                break
            inner = m.group()[1:-1]
            inner_words = inner.split()
            if len(inner_words) > 50:
                hints.append(StyleHint(
                    start=m.start(), end=m.end(),
                    hint_type="dialogue",
                    message="Dialogue feels stiff",
                ))

    return hints


# ---------------------------------------------------------------------------
# On-demand style suggestions
# ---------------------------------------------------------------------------

_MAX_SUGGESTIONS = 3


def _build_rewrite(text: str, words: list[str]) -> str | None:
    """Attempt a lightweight heuristic rewrite by removing filler words."""
    result = text
    for filler in _FILLER_WORDS:
        result = re.sub(
            rf"\b{re.escape(filler)}\b\s*",
            "",
            result,
            flags=re.IGNORECASE,
        )
    result = re.sub(r"  +", " ", result).strip()
    if result == text.strip() or len(result) < 10:
        return None
    return result


def generate_style_suggestions(
    text: str,
    context: StyleContext | None = None,
) -> tuple[list[StyleSuggestion], str | None]:
    """Analyze *text* and return 1-3 suggestions plus an optional rewrite.

    When *context* is provided, thresholds shift so writing that matches
    the character's PSYKE state produces fewer (or different) suggestions.

    Returns ``(suggestions, rewrite)`` where *rewrite* is ``None`` when no
    meaningful improvement can be produced heuristically.
    """
    if not text.strip():
        return [], None

    w = _words(text)
    sents = _sentences(text)
    suggestions: list[StyleSuggestion] = []

    pw = _STYLE_PSYKE_WEIGHT
    stress = context.stress_level if context else 0.0
    formality = context.formality_level if context else 0.0
    emotion = context.emotional_intensity if context else 0.0

    clarity_score = _clarity(text, w, sents)
    if clarity_score < 0.7:
        avg_len = len(w) / max(len(sents), 1)
        if avg_len > 25 and stress > 0.3:
            suggestions.append(StyleSuggestion(
                "clarity", "Short, punchy sentences suit this character's tension",
            ))
        elif avg_len > 25:
            suggestions.append(StyleSuggestion(
                "clarity", "Break long sentences for readability",
            ))
        elif _repeated_word_ratio(w) > 0.12:
            suggestions.append(StyleSuggestion(
                "clarity", "Vary word choice to avoid repetition",
            ))
        else:
            suggestions.append(StyleSuggestion(
                "clarity", "Simplify sentence structure",
            ))

    concision_score = _concision(text, w, sents)
    if len(suggestions) < _MAX_SUGGESTIONS and concision_score < 0.7:
        filler_count = sum(1 for word in w if word in _FILLER_WORDS)
        adverb_r = _adverb_ratio(w)
        if filler_count > 0:
            suggestions.append(StyleSuggestion(
                "concision", "Remove filler words (very, really, just…)",
            ))
        elif adverb_r > 0.05:
            suggestions.append(StyleSuggestion(
                "concision", "Use stronger verbs instead of adverbs",
            ))
        else:
            suggestions.append(StyleSuggestion(
                "concision", "Tighten the prose — fewer words, same meaning",
            ))

    rhythm_score = _rhythm(sents)
    rhythm_adjusted = rhythm_score + stress * pw
    if len(suggestions) < _MAX_SUGGESTIONS and rhythm_adjusted < 0.65:
        if stress > 0.3:
            suggestions.append(StyleSuggestion(
                "rhythm", "Staccato rhythm works — but vary slightly for impact",
            ))
        else:
            suggestions.append(StyleSuggestion(
                "rhythm", "Vary sentence lengths for better flow",
            ))

    tone_score = _tone_consistency(sents)
    tone_adjusted = tone_score + formality * pw + emotion * pw
    if len(suggestions) < _MAX_SUGGESTIONS and tone_adjusted < 0.7:
        if emotion > 0.3:
            suggestions.append(StyleSuggestion(
                "tone", "Tone shifts can work here — lean into the emotion",
            ))
        else:
            suggestions.append(StyleSuggestion(
                "tone", "Tone shifts between formal and informal",
            ))

    dialogue = _dialogue_naturalness(text)
    dialogue_adjusted = (dialogue or 0.0) + formality * pw if dialogue is not None else None
    if (
        len(suggestions) < _MAX_SUGGESTIONS
        and dialogue_adjusted is not None
        and dialogue_adjusted < 0.6
    ):
        if formality > 0.3:
            suggestions.append(StyleSuggestion(
                "dialogue", "Structured dialogue fits — keep it purposeful",
            ))
        else:
            suggestions.append(StyleSuggestion(
                "dialogue", "Shorten dialogue or add contractions",
            ))

    suggestions = suggestions[:_MAX_SUGGESTIONS]

    rewrite = _build_rewrite(text, w) if suggestions else None

    return suggestions, rewrite


# ---------------------------------------------------------------------------
# Optional async LLM refinement
# ---------------------------------------------------------------------------

_STYLE_KEYS = ("clarity", "concision", "rhythm", "tone_consistency")

_REFINE_SYSTEM_PROMPT = (
    "You are a writing style analyst. Given a paragraph of fiction, "
    "rate these metrics on a 0.0–1.0 scale:\n"
    "- clarity: how easy the text is to follow (1.0 = crystal clear)\n"
    "- concision: how economical the word choice is (1.0 = no waste)\n"
    "- rhythm: how well sentence lengths vary (1.0 = great flow)\n"
    "- tone_consistency: how uniform the register is (1.0 = consistent)\n"
    "- dialogue_naturalness: how natural the dialogue sounds "
    "(1.0 = very natural, omit if no dialogue)\n\n"
    "Respond with ONLY a JSON object, e.g.: "
    '{"clarity": 0.8, "concision": 0.7, "rhythm": 0.9, "tone_consistency": 0.8}'
)


def _build_provider():
    # Delegates to the single shared provider builder (Phase 8B).
    from logosforge.providers import build_active_provider
    return build_active_provider()


def _parse_style_metrics(raw: str) -> dict[str, float] | None:
    """Extract style metrics dict from LLM response text."""
    match = re.search(r"\{[^}]+\}", raw)
    if not match:
        return None
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return None
    if not set(_STYLE_KEYS).issubset(data):
        return None
    result: dict[str, float] = {}
    for k in (*_STYLE_KEYS, "dialogue_naturalness"):
        if k in data:
            result[k] = max(0.0, min(1.0, float(data[k])))
    return result


try:
    from PySide6.QtCore import QThread, Signal

    class StyleRefineWorker(QThread):
        """Async LLM call to refine heuristic style metrics."""

        completed = Signal(object)  # ParagraphStyle
        failed = Signal(str)

        def __init__(self, style: ParagraphStyle, text: str) -> None:
            super().__init__()
            self._style = style
            self._text = text

        def run(self) -> None:
            from logosforge.assistant import chat_completion
            try:
                provider = _build_provider()
                messages = [
                    {"role": "system", "content": _REFINE_SYSTEM_PROMPT},
                    {"role": "user", "content": self._text},
                ]
                result, _ = chat_completion(
                    messages, provider=provider, timeout=15,
                    use_cache=True, response_language="en",
                )
                refined = _parse_style_metrics(result)
                if refined is None:
                    self.failed.emit("LLM returned unparseable response")
                    return

                blended: dict[str, float] = {}
                for key in self._style.metrics:
                    h = self._style.metrics[key]
                    l = refined.get(key)
                    if l is not None:
                        blended[key] = round(h * 0.4 + l * 0.6, 3)
                    else:
                        blended[key] = h

                updated = ParagraphStyle(
                    paragraph_id=self._style.paragraph_id,
                    metrics=blended,
                    notes=list(self._style.notes),
                )
                _cache_put(self._text, updated)
                self.completed.emit(updated)
            except Exception as e:
                log.debug("LLM style refinement failed: %s", e)
                self.failed.emit(str(e))

except ImportError:
    pass
