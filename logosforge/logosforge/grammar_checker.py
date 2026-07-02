"""Grammar and spell-checking system for the Manuscript editor.

Provides language detection and issue detection (spelling, grammar, style)
with a pluggable backend architecture.  Ships with a built-in rule-based
checker that works without external dependencies.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Protocol


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Issue:
    """A single grammar, spelling, or style issue found in text."""

    start: int
    end: int
    issue_type: str  # "spelling" | "grammar" | "style"
    message: str
    suggestions: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Language detection — trigram frequency comparison
# ---------------------------------------------------------------------------

_TRIGRAM_PROFILES: dict[str, dict[str, float]] = {
    "en": {
        " th": 3.5, "the": 3.2, "he ": 2.8, "and": 2.1, " an": 1.9,
        "nd ": 1.7, "ion": 1.6, "tio": 1.5, " of": 1.4, "of ": 1.3,
        "ed ": 1.2, "ing": 1.2, " in": 1.1, "er ": 1.1, " to": 1.0,
        "to ": 1.0, "hat": 0.9, "tha": 0.9, "ent": 0.8, "for": 0.8,
        " fo": 0.7, " he": 0.7, "her": 0.7, "is ": 0.7, " is": 0.6,
        "re ": 0.6, " re": 0.6, "on ": 0.6, " wa": 0.6, "was": 0.5,
        "as ": 0.5, "all": 0.5, " it": 0.5, "it ": 0.5, " ha": 0.5,
    },
    "es": {
        " de": 3.2, "de ": 3.0, " la": 2.5, "la ": 2.3, "os ": 2.0,
        " el": 1.8, "el ": 1.7, "en ": 1.6, " en": 1.5, "ión": 1.4,
        "ció": 1.3, " qu": 1.2, "que": 1.1, "ue ": 1.0, " co": 1.0,
        "es ": 0.9, " lo": 0.9, "con": 0.8, "ent": 0.8, "las": 0.8,
        " la": 0.7, "los": 0.7, "ado": 0.7, "nte": 0.6, " se": 0.6,
        "por": 0.6, " po": 0.6, " un": 0.5, "ión": 0.5, "sta": 0.5,
    },
    "fr": {
        " de": 3.0, "de ": 2.8, " le": 2.2, "le ": 2.0, "les": 1.8,
        "es ": 1.7, " la": 1.6, "la ": 1.5, "ent": 1.4, " et": 1.3,
        "et ": 1.2, " pa": 1.1, "ion": 1.1, " un": 1.0, " co": 1.0,
        "tio": 0.9, "ons": 0.9, " qu": 0.8, "que": 0.8, "ue ": 0.8,
        "ait": 0.7, " en": 0.7, "en ": 0.7, "sur": 0.6, " da": 0.6,
        "des": 0.6, " le": 0.5, "par": 0.5, " po": 0.5, "ans": 0.5,
    },
    "de": {
        " de": 2.5, "die": 2.3, "der": 2.2, "er ": 2.0, "en ": 1.9,
        " di": 1.8, "ein": 1.6, "ich": 1.5, " ei": 1.4, "und": 1.4,
        " un": 1.3, "nd ": 1.2, "cht": 1.1, " da": 1.0, "das": 1.0,
        "den": 0.9, " in": 0.9, "sch": 0.9, "che": 0.8, " au": 0.8,
        "gen": 0.8, "ung": 0.7, "ine": 0.7, " zu": 0.6, " ge": 0.6,
        "auf": 0.6, "ber": 0.6, "ter": 0.5, "eit": 0.5, "ier": 0.5,
    },
    "pt": {
        " de": 3.3, "de ": 3.1, " qu": 2.0, "que": 1.9, "ue ": 1.8,
        "os ": 1.7, " do": 1.5, " da": 1.4, "ção": 1.3, " co": 1.2,
        "ão ": 1.1, "com": 1.0, " pa": 1.0, "ent": 0.9, "as ": 0.9,
        "do ": 0.8, "da ": 0.8, "uma": 0.7, " um": 0.7, " no": 0.7,
        "por": 0.6, " po": 0.6, "par": 0.6, "est": 0.5, " se": 0.5,
        "nte": 0.5, "ade": 0.5, "dos": 0.5, " em": 0.5, "em ": 0.5,
    },
    "it": {
        " di": 2.8, "di ": 2.6, " la": 2.0, "la ": 1.9, "che": 1.8,
        " ch": 1.7, "he ": 1.6, " il": 1.5, "il ": 1.4, " de": 1.3,
        "del": 1.2, " in": 1.1, "ell": 1.0, "lla": 1.0, "per": 0.9,
        " pe": 0.9, "one": 0.8, "ent": 0.8, " co": 0.8, "con": 0.7,
        "ato": 0.7, "non": 0.6, " no": 0.6, "ion": 0.6, "to ": 0.6,
        "tta": 0.5, "ita": 0.5, "gli": 0.5, " un": 0.5, "zio": 0.5,
        " ne": 0.4, "nel": 0.4, "ell": 0.4, "ere": 0.4, "nte": 0.4,
    },
}


def _text_trigrams(text: str) -> dict[str, float]:
    text = text.lower()[:2000]
    counts: Counter[str] = Counter()
    for i in range(len(text) - 2):
        tri = text[i:i + 3]
        if tri.isspace():
            continue
        counts[tri] += 1
    total = sum(counts.values()) or 1
    return {k: v / total * 100 for k, v in counts.items()}


def _cosine_sim(a: dict[str, float], b: dict[str, float]) -> float:
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
    mag_a = math.sqrt(sum(v * v for v in a.values())) or 1
    mag_b = math.sqrt(sum(v * v for v in b.values())) or 1
    return dot / (mag_a * mag_b)


def detect_language(text: str) -> str:
    """Return ISO 639-1 language code for *text*, defaulting to ``'en'``."""
    if len(text.strip()) < 20:
        return "en"
    profile = _text_trigrams(text)
    best_lang = "en"
    best_score = -1.0
    for lang, ref in _TRIGRAM_PROFILES.items():
        score = _cosine_sim(profile, ref)
        if score > best_score:
            best_score = score
            best_lang = lang
    return best_lang


# ---------------------------------------------------------------------------
# Checker backend protocol
# ---------------------------------------------------------------------------

class CheckerBackend(Protocol):
    """Interface for pluggable grammar/spell-check backends."""

    def check(self, text: str, language: str) -> list[Issue]: ...


# ---------------------------------------------------------------------------
# Built-in rule-based backend
# ---------------------------------------------------------------------------

_COMMON_WORDS_EN: set[str] | None = None


def _get_common_words_en() -> set[str]:
    global _COMMON_WORDS_EN
    if _COMMON_WORDS_EN is not None:
        return _COMMON_WORDS_EN
    _COMMON_WORDS_EN = {
        "a", "about", "above", "across", "act", "add", "after", "again",
        "against", "ago", "agree", "ahead", "air", "all", "allow", "almost",
        "alone", "along", "already", "also", "always", "am", "among", "an",
        "and", "anger", "angry", "animal", "another", "answer", "any",
        "anyone", "anything", "appear", "are", "area", "arm", "arms",
        "around", "arrive", "art", "as", "ask", "at", "attack", "away",
        "back", "bad", "bag", "ball", "bar", "base", "be", "beat",
        "beautiful", "beauty", "because", "become", "bed", "been", "before",
        "began", "begin", "behind", "believe", "below", "beside", "best",
        "better", "between", "beyond", "big", "bit", "black", "blood",
        "blue", "board", "body", "bone", "book", "born", "both", "bottom",
        "box", "boy", "brain", "break", "breath", "bright", "bring",
        "broke", "broken", "brother", "brought", "brown", "build", "built",
        "burn", "bus", "but", "buy", "by", "call", "came", "can", "car",
        "care", "carry", "case", "catch", "caught", "cause", "center",
        "certain", "chair", "chance", "change", "chapter", "character",
        "check", "child", "children", "choice", "choose", "church", "circle",
        "city", "class", "clean", "clear", "close", "closed", "cold",
        "color", "come", "common", "complete", "control", "cool", "corner",
        "could", "country", "couple", "course", "cover", "create", "cross",
        "crowd", "cry", "cup", "cut", "dad", "dark", "daughter", "day",
        "dead", "deal", "dear", "death", "decide", "deep", "did", "die",
        "different", "difficult", "dinner", "do", "doctor", "does", "dog",
        "done", "door", "down", "draw", "dream", "dress", "drink", "drive",
        "drop", "dry", "during", "each", "ear", "early", "earth", "east",
        "easy", "eat", "edge", "eight", "either", "else", "empty", "end",
        "enemy", "energy", "enjoy", "enough", "enter", "entire", "even",
        "evening", "ever", "every", "everyone", "everything", "evil",
        "exactly", "example", "except", "excite", "expect", "experience",
        "explain", "expression", "eye", "eyes", "face", "fact", "fair",
        "fall", "family", "far", "fast", "fat", "father", "fear", "feel",
        "feet", "fell", "felt", "few", "field", "fight", "fill", "final",
        "finally", "find", "fine", "finger", "finish", "fire", "first",
        "fit", "five", "floor", "fly", "follow", "food", "foot", "for",
        "force", "forget", "form", "forward", "found", "four", "free",
        "fresh", "friend", "from", "front", "full", "fun", "game", "garden",
        "gave", "get", "girl", "give", "glad", "glass", "go", "god", "gold",
        "gone", "good", "got", "grass", "gray", "great", "green", "grew",
        "ground", "group", "grow", "guard", "guess", "gun", "guy", "had",
        "hair", "half", "hall", "hand", "hang", "happen", "happy", "hard",
        "has", "hat", "hate", "have", "he", "head", "hear", "heard",
        "heart", "heat", "heavy", "held", "help", "her", "here", "herself",
        "high", "hill", "him", "himself", "his", "hit", "hold", "hole",
        "home", "hope", "horse", "hot", "hotel", "hour", "house", "how",
        "however", "huge", "human", "hundred", "hung", "hunt", "hurry",
        "hurt", "husband", "i", "ice", "idea", "if", "image", "imagine",
        "important", "in", "include", "indeed", "inside", "instead",
        "interest", "into", "iron", "is", "island", "it", "its", "itself",
        "job", "join", "jump", "just", "justice", "keep", "kept", "key",
        "kill", "kind", "king", "kitchen", "knee", "knew", "knock", "know",
        "known", "lack", "lady", "land", "language", "large", "last", "late",
        "later", "laugh", "law", "lay", "lead", "learn", "least", "leave",
        "led", "left", "leg", "less", "let", "letter", "lie", "life",
        "lift", "light", "like", "line", "lip", "list", "listen", "little",
        "live", "long", "look", "lord", "lose", "loss", "lost", "lot",
        "love", "low", "luck", "lunch", "machine", "mad", "made", "main",
        "major", "make", "man", "many", "map", "mark", "master", "matter",
        "may", "maybe", "me", "mean", "meet", "men", "message", "met",
        "middle", "might", "mile", "mind", "mine", "minute", "miss",
        "moment", "money", "month", "moon", "more", "morning", "most",
        "mother", "mountain", "mouth", "move", "movie", "mr", "mrs", "much",
        "murder", "music", "must", "my", "myself", "name", "nation",
        "nature", "near", "nearly", "necessary", "neck", "need", "neither",
        "never", "new", "news", "next", "nice", "night", "nine", "no",
        "nobody", "noise", "none", "nor", "north", "nose", "not", "note",
        "nothing", "notice", "now", "number", "of", "off", "offer",
        "office", "officer", "often", "oh", "ok", "okay", "old", "on",
        "once", "one", "only", "onto", "open", "or", "order", "other",
        "our", "out", "outside", "over", "own", "page", "pain", "pair",
        "paper", "part", "pass", "past", "path", "pay", "peace", "people",
        "perhaps", "period", "person", "pick", "picture", "piece", "place",
        "plan", "plant", "play", "please", "point", "police", "poor",
        "position", "possible", "power", "present", "press", "pretty",
        "price", "private", "probably", "problem", "promise", "protect",
        "prove", "provide", "public", "pull", "push", "put", "question",
        "quick", "quickly", "quiet", "quite", "race", "rain", "raise",
        "ran", "rather", "reach", "read", "ready", "real", "realize",
        "really", "reason", "receive", "record", "red", "remain", "remember",
        "rest", "return", "rich", "ride", "right", "ring", "rise", "river",
        "road", "rock", "roll", "room", "round", "run", "rush", "safe",
        "said", "same", "sat", "save", "saw", "say", "school", "sea",
        "search", "season", "seat", "second", "secret", "see", "seem",
        "seen", "self", "sell", "send", "sense", "sent", "serious", "serve",
        "set", "seven", "several", "shadow", "shake", "shall", "shape",
        "share", "she", "ship", "short", "shot", "should", "shoulder",
        "shout", "show", "shut", "sick", "side", "sight", "sign", "silence",
        "silver", "simple", "since", "sir", "sister", "sit", "situation",
        "six", "size", "skin", "sky", "sleep", "slip", "slow", "slowly",
        "small", "smell", "smile", "snow", "so", "soft", "soldier", "some",
        "somebody", "someone", "something", "sometimes", "son", "song",
        "soon", "sorry", "sort", "soul", "sound", "south", "space", "speak",
        "special", "spend", "spoke", "spot", "spring", "stand", "star",
        "start", "state", "stay", "step", "still", "stone", "stood", "stop",
        "store", "story", "strange", "street", "strong", "student", "such",
        "sudden", "suddenly", "suggest", "summer", "sun", "support", "sure",
        "surprise", "sweet", "table", "take", "talk", "tall", "teach",
        "tell", "ten", "than", "thank", "that", "the", "their", "them",
        "then", "there", "these", "they", "thick", "thin", "thing", "think",
        "third", "this", "those", "though", "thought", "thousand", "three",
        "through", "throw", "time", "tiny", "to", "today", "together",
        "told", "tomorrow", "tonight", "too", "took", "top", "touch",
        "toward", "towards", "town", "tree", "trouble", "true", "trust",
        "truth", "try", "turn", "twelve", "twenty", "two", "type",
        "uncle", "under", "understand", "until", "up", "upon", "us", "use",
        "usual", "usually", "very", "visit", "voice", "wait", "wake",
        "walk", "wall", "want", "war", "warm", "was", "watch", "water",
        "way", "we", "wear", "weather", "week", "weight", "well", "went",
        "were", "west", "what", "when", "where", "whether", "which",
        "while", "white", "who", "whole", "whom", "whose", "why", "wide",
        "wife", "wild", "will", "win", "wind", "window", "winter", "wish",
        "with", "within", "without", "woman", "women", "won", "wonder",
        "wood", "word", "words", "work", "world", "worry", "worse",
        "worst", "worth", "would", "write", "written", "wrong", "wrote",
        "yard", "yeah", "year", "yes", "yesterday", "yet", "you", "young",
        "your",
        "looked", "said", "asked", "walked", "turned", "started", "called",
        "thought", "felt", "knew", "wanted", "needed", "tried", "used",
        "found", "took", "made", "came", "went", "saw", "told", "gave",
        "left", "seemed", "kept", "let", "began", "showed", "heard",
        "played", "ran", "moved", "lived", "believed", "brought", "happened",
        "wrote", "sat", "stood", "lost", "paid", "met", "included",
        "continued", "set", "learned", "changed", "led", "understood",
        "watched", "followed", "stopped", "created", "spoke", "read",
        "spent", "grew", "opened", "walked", "won", "taught", "offered",
        "remembered", "considered", "appeared", "bought", "served",
        "died", "sent", "built", "stayed", "fell", "reached", "remained",
        "suggested", "raised", "passed", "sold", "required", "reported",
        "decided", "pulled", "developed", "pulled",
        "don", "didn", "doesn", "wasn", "weren", "isn", "aren", "hasn",
        "hadn", "wouldn", "couldn", "shouldn", "won",
        "ll", "ve", "re", "don't", "didn't", "doesn't", "wasn't",
        "weren't", "isn't", "aren't", "hasn't", "hadn't", "wouldn't",
        "couldn't", "shouldn't", "won't", "can't", "i'm", "i'll", "i've",
        "i'd", "you're", "you'll", "you've", "you'd", "he's", "he'll",
        "he'd", "she's", "she'll", "she'd", "it's", "it'll", "we're",
        "we'll", "we've", "we'd", "they're", "they'll", "they've", "they'd",
        "that's", "there's", "here's", "what's", "who's", "let's",
    }
    return _COMMON_WORDS_EN


_WORD_RE = re.compile(r"[a-zA-ZÀ-ÿ'']+")
_DOUBLED_WORD_RE = re.compile(r"\b(\w+)\s+\1\b", re.IGNORECASE)
_SENTENCE_RE = re.compile(r"[^.!?]+[.!?]+")
_PASSIVE_RE = re.compile(
    r"\b(was|were|been|being|is|are|am)\s+"
    r"(\w+ed|written|spoken|taken|given|made|done|seen|known|shown|told"
    r"|found|built|kept|left|sent|held|brought|caught|taught|thought"
    r"|thrown|broken|chosen|driven|eaten|fallen|forgotten|frozen|hidden"
    r"|ridden|risen|stolen|sworn|torn|worn|woken|born|drawn|grown)\b",
    re.IGNORECASE,
)
_CAPITALIZATION_RE = re.compile(r"[.!?]\s+([a-z])")


class RuleBasedChecker:
    """Built-in checker using word lists and regex rules.  English only."""

    def check(self, text: str, language: str) -> list[Issue]:
        issues: list[Issue] = []
        if language == "en":
            issues.extend(self._check_spelling_en(text))
        issues.extend(self._check_grammar(text))
        issues.extend(self._check_style(text))
        return issues

    def _check_spelling_en(self, text: str) -> list[Issue]:
        known = _get_common_words_en()
        issues: list[Issue] = []
        for m in _WORD_RE.finditer(text):
            word = m.group()
            if len(word) <= 1:
                continue
            lower = word.lower().replace("’", "'")
            if self._is_known_en(lower, known):
                continue
            if word[0].isupper() and not word.isupper():
                continue
            issues.append(Issue(
                start=m.start(),
                end=m.end(),
                issue_type="spelling",
                message=f"Unknown word: '{word}'",
                suggestions=[],
            ))
        return issues

    @staticmethod
    def _is_known_en(lower: str, known: set[str]) -> bool:
        if lower in known:
            return True
        if lower.endswith("'s") and lower[:-2] in known:
            return True
        for suffix, replacements in (
            ("s", ("", )),
            ("es", ("", "e")),
            ("ly", ("", "e", "y")),
            ("ing", ("", "e")),
            ("ed", ("", "e")),
            ("er", ("", "e")),
            ("est", ("", "e")),
            ("ful", ("", "e")),
            ("fully", ("", "e")),
            ("ness", ("", "e")),
            ("ment", ("", "e")),
            ("tion", ("", "te", "t")),
            ("ous", ("", "e")),
            ("ive", ("", "e")),
            ("able", ("", "e")),
            ("ible", ("", "e")),
        ):
            if lower.endswith(suffix):
                stem = lower[:-len(suffix)]
                if any((stem + r) in known for r in replacements):
                    return True
        return False

    def _check_grammar(self, text: str) -> list[Issue]:
        issues: list[Issue] = []
        for m in _DOUBLED_WORD_RE.finditer(text):
            issues.append(Issue(
                start=m.start(),
                end=m.end(),
                issue_type="grammar",
                message=f"Repeated word: '{m.group(1)}'",
                suggestions=[m.group(1)],
            ))
        for m in _CAPITALIZATION_RE.finditer(text):
            pos = m.start(1)
            ch = m.group(1)
            issues.append(Issue(
                start=pos,
                end=pos + 1,
                issue_type="grammar",
                message="Sentence should start with a capital letter.",
                suggestions=[ch.upper()],
            ))
        return issues

    def _check_style(self, text: str) -> list[Issue]:
        issues: list[Issue] = []
        for m in _PASSIVE_RE.finditer(text):
            issues.append(Issue(
                start=m.start(),
                end=m.end(),
                issue_type="style",
                message="Passive voice detected.",
                suggestions=[],
            ))
        for m in _SENTENCE_RE.finditer(text):
            sentence = m.group().strip()
            word_count = len(sentence.split())
            if word_count > 40:
                issues.append(Issue(
                    start=m.start(),
                    end=m.end(),
                    issue_type="style",
                    message=f"Very long sentence ({word_count} words). Consider splitting.",
                    suggestions=[],
                ))
        return issues


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_default_backend: CheckerBackend = RuleBasedChecker()


def check_text(text: str, backend: CheckerBackend | None = None,
               language: str | None = None) -> list[Issue]:
    """Check *text* for spelling, grammar, and style issues.

    With *language* (a project Writing Language code) the checker runs as
    that language: English gets the full rule set, other word-spaced
    languages the generic rules only, and languages the rule set cannot
    honestly check (no word spaces / RTL — see
    :func:`logosforge.languages.grammar_support`) return no issues at all
    instead of being silently checked as English. Without *language* the
    legacy per-call detection is used. Uses the built-in rule-based backend
    unless an alternative *backend* is provided.
    """
    if not text or not text.strip():
        return []
    if language:
        from logosforge import languages as L
        code = L.normalize_language(language)
        if code == "auto":
            code = detect_language(text)
        elif L.grammar_support(code) == L.GRAMMAR_NONE:
            return []
    else:
        code = detect_language(text)
    checker = backend or _default_backend
    return checker.check(text, code)


def grammar_status(language: str) -> tuple[str, str]:
    """(support_level, user-facing message) for a Writing Language code —
    the graceful-degradation surface ("Grammar checking is not available
    for <language>. You can still write and use AI review.")."""
    from logosforge import languages as L
    code = L.normalize_language(language)
    return L.grammar_support(code), L.grammar_status_message(code)
