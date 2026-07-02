"""Project Voice Glossary — local correction layer (Phase 7).

Improves dictation quality for project vocabulary (character/place/object/
lore names, invented words, repeated Whisper slips) plus spoken punctuation
— **locally and review-first**. Suggestion generation never mutates
anything; applying corrections changes TRANSCRIPT text only (the Manuscript
is still reached exclusively through the Commit Router after explicit
commit). Glossary terms are project-scoped rows (`VoiceGlossaryTerm`) — no
cross-project leakage, no audio, no secrets, no AI required, and importing
candidates from PSYKE/Outline is read-only on those sources.

Correction strategy (conservative, in priority order): exact
common-misrecognition matches → exact spoken-form matches → canonical-case
normalization → spoken punctuation phrases → cautious fuzzy suggestions
(disabled by default). Whole-word matching prevents inside-word mutation;
nothing is replaced silently.
"""

from __future__ import annotations

import difflib
import re
import time
import uuid
from dataclasses import dataclass, field

PROJECT_MISMATCH_CORRECTIONS = (
    "Project changed since this transcript was captured. Switch back or "
    "retarget before applying corrections.")

GLOSSARY_CATEGORIES = ("character", "place", "object", "lore", "theme",
                       "style", "custom", "punctuation", "formatting")

# Spoken punctuation / formatting phrases (local; preview like everything).
SPOKEN_PUNCTUATION = (
    ("new paragraph", "\n\n"),
    ("new line", "\n"),
    ("comma", ","),
    ("full stop", "."),
    ("period", "."),
    ("question mark", "?"),
    ("exclamation mark", "!"),
    ("exclamation point", "!"),
    ("semicolon", ";"),
    ("colon", ":"),
    ("open quote", "“"),
    ("close quote", "”"),
    ("ellipsis", "…"),
    ("dash", "—"),
)


@dataclass
class CorrectionSuggestion:
    """One proposed transcript fix. Generating it mutates nothing."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    project_id: int = 0
    original_text: str = ""
    replacement_text: str = ""
    start_offset: int = 0
    end_offset: int = 0
    source_term_id: int | None = None
    source: str = ""                     # misrecognition/spoken_form/
                                         # canonical_case/punctuation/fuzzy
    reason: str = ""
    confidence: float | None = None
    applied: bool = False
    created_at: float = field(default_factory=time.time)


def _forms(raw: str) -> list[str]:
    return [f.strip() for f in re.split(r"[\n,;]+", raw or "") if f.strip()]


def validate_glossary_term(canonical_text: str) -> tuple[bool, str]:
    text = (canonical_text or "").strip()
    if not text:
        return False, "Canonical text is required."
    if any(ord(ch) < 32 and ch not in "\n\t" for ch in text):
        return False, "Canonical text contains control characters."
    return True, ""


def _word_pattern(phrase: str, *, whole_word: bool) -> re.Pattern:
    escaped = re.escape(phrase)
    if whole_word:
        # \b fails around non-ASCII letters; lookarounds on \w are safer.
        return re.compile(rf"(?<!\w){escaped}(?!\w)", re.IGNORECASE
                          | re.UNICODE)
    return re.compile(escaped, re.IGNORECASE | re.UNICODE)


def _exact_pattern(phrase: str, *, whole_word: bool) -> re.Pattern:
    escaped = re.escape(phrase)
    if whole_word:
        return re.compile(rf"(?<!\w){escaped}(?!\w)", re.UNICODE)
    return re.compile(escaped, re.UNICODE)


def suggest_transcript_corrections(
        db, project_id: int, text: str, *,
        spoken_punctuation: bool = True,
        fuzzy: bool = False) -> list[CorrectionSuggestion]:
    """Build suggestions for *text* from THIS project's glossary. Read-only."""
    suggestions: list[CorrectionSuggestion] = []
    if not (text or "").strip():
        return suggestions
    taken: list[tuple[int, int]] = []

    def overlaps(start: int, end: int) -> bool:
        return any(not (end <= s or start >= e) for s, e in taken)

    def add(match: re.Match, replacement: str, *, term=None, source: str,
            reason: str, confidence: float | None = None) -> None:
        start, end = match.start(), match.end()
        if overlaps(start, end) or match.group(0) == replacement:
            return
        taken.append((start, end))
        suggestions.append(CorrectionSuggestion(
            project_id=project_id, original_text=match.group(0),
            replacement_text=replacement, start_offset=start, end_offset=end,
            source_term_id=getattr(term, "id", None), source=source,
            reason=reason, confidence=confidence))

    terms = [t for t in db.get_voice_glossary_terms(project_id) if t.enabled]
    terms.sort(key=lambda t: -int(t.priority or 0))

    # 1. Exact common misrecognitions (highest priority).
    for term in terms:
        for slip in _forms(term.common_misrecognitions):
            pattern = (_exact_pattern(slip, whole_word=term.whole_word_only)
                       if term.case_sensitive else
                       _word_pattern(slip, whole_word=term.whole_word_only))
            for match in pattern.finditer(text):
                add(match, term.canonical_text, term=term,
                    source="misrecognition",
                    reason=f"Known misrecognition of “{term.canonical_text}”")
    # 2. Exact spoken forms.
    for term in terms:
        for form in _forms(term.spoken_forms):
            pattern = (_exact_pattern(form, whole_word=term.whole_word_only)
                       if term.case_sensitive else
                       _word_pattern(form, whole_word=term.whole_word_only))
            for match in pattern.finditer(text):
                add(match, term.canonical_text, term=term,
                    source="spoken_form",
                    reason=f"Spoken form of “{term.canonical_text}”")
    # 3. Canonical-case normalization (e.g. "zampanò" -> "Zampanò").
    for term in terms:
        if term.case_sensitive:
            continue
        pattern = _word_pattern(term.canonical_text,
                                whole_word=term.whole_word_only)
        for match in pattern.finditer(text):
            if match.group(0) != term.canonical_text:
                add(match, term.canonical_text, term=term,
                    source="canonical_case",
                    reason="Project spelling/capitalization")
    # 4. Spoken punctuation / formatting phrases.
    if spoken_punctuation:
        for phrase, symbol in SPOKEN_PUNCTUATION:
            for match in _word_pattern(phrase,
                                       whole_word=True).finditer(text):
                add(match, symbol, source="punctuation",
                    reason=f"Spoken punctuation: “{phrase}”")
    # 5. Cautious fuzzy suggestions (OFF by default; long tokens only).
    if fuzzy:
        canonicals = [t for t in terms
                      if len(t.canonical_text) >= 5
                      and t.category != "punctuation"]
        for match in re.finditer(r"(?<!\w)\w{5,}(?!\w)", text,
                                 re.UNICODE):
            token = match.group(0)
            for term in canonicals:
                ratio = difflib.SequenceMatcher(
                    None, token.lower(),
                    term.canonical_text.lower()).ratio()
                if 0.84 <= ratio < 1.0:
                    add(match, term.canonical_text, term=term,
                        source="fuzzy", confidence=ratio,
                        reason=f"Looks like “{term.canonical_text}”")
                    break
    suggestions.sort(key=lambda s: s.start_offset)
    return suggestions


def apply_selected_corrections(text: str,
                               corrections: list[CorrectionSuggestion]
                               ) -> str:
    """Apply ONLY the given suggestions to *text* (transcript-level; never a
    document). Replacements run right-to-left so offsets stay valid."""
    out = text or ""
    for suggestion in sorted(corrections, key=lambda s: -s.start_offset):
        if not suggestion.replacement_text and \
                suggestion.source != "punctuation":
            continue                      # empty replacement is invalid
        if out[suggestion.start_offset:suggestion.end_offset] != \
                suggestion.original_text:
            continue                      # text drifted: skip, never guess
        out = (out[:suggestion.start_offset] + suggestion.replacement_text
               + out[suggestion.end_offset:])
        suggestion.applied = True
    # Tidy spacing around punctuation we may have introduced.
    out = re.sub(r"[ \t]+([,.;:!?…])", r"\1", out)
    out = re.sub(r"“[ \t]+", "“", out)
    out = re.sub(r"[ \t]+”", "”", out)
    out = re.sub(r"[ \t]*\n[ \t]*", "\n", out)
    return out


def learn_correction(db, project_id: int, original: str, corrected: str,
                     *, category: str = "custom"):
    """Remember a CONFIRMED manual correction pair for this project. If the
    canonical term already exists, the misrecognition is appended (no
    duplicates); otherwise a new learned term is created."""
    original = (original or "").strip()
    corrected = (corrected or "").strip()
    ok, _reason = validate_glossary_term(corrected)
    if not ok or not original or original == corrected:
        return None
    if category not in GLOSSARY_CATEGORIES:
        category = "custom"
    for term in db.get_voice_glossary_terms(project_id):
        if term.canonical_text.lower() == corrected.lower():
            slips = _forms(term.common_misrecognitions)
            if original.lower() in (s.lower() for s in slips):
                return term
            slips.append(original)
            return db.update_voice_glossary_term(
                term.id, common_misrecognitions="\n".join(slips))
    return db.create_voice_glossary_term(
        project_id, corrected, common_misrecognitions=original,
        category=category, source="learned_from_correction")


def diff_correction_pairs(original_text: str,
                          corrected_text: str) -> list[tuple[str, str]]:
    """Word-level (original, corrected) pairs from a manual edit — the
    candidates offered for learning (always confirmed, never silent)."""
    before = re.findall(r"\w+", original_text or "", re.UNICODE)
    after = re.findall(r"\w+", corrected_text or "", re.UNICODE)
    pairs: list[tuple[str, str]] = []
    matcher = difflib.SequenceMatcher(None, [w.lower() for w in before],
                                      [w.lower() for w in after])
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "replace" and (i2 - i1) == (j2 - j1):
            for offset in range(i2 - i1):
                pairs.append((before[i1 + offset], after[j1 + offset]))
    return [(a, b) for a, b in pairs if a.lower() != b.lower()]


# ---------------------------------------------------------------------------
# Import candidates from project data (read-only on PSYKE/Outline)
# ---------------------------------------------------------------------------

_PSYKE_CATEGORY = {"character": "character", "place": "place",
                   "object": "object", "lore": "lore", "theme": "theme"}


def build_import_candidates(db, project_id: int,
                            sources: tuple = ("psyke", "characters",
                                              "outline")) -> list[dict]:
    """Collect candidate terms from project data. READ-ONLY — PSYKE and the
    Outline are never mutated; nothing is created until import_candidates."""
    existing = {t.canonical_text.lower()
                for t in db.get_voice_glossary_terms(project_id)}
    seen = set(existing)
    candidates: list[dict] = []

    def add(name: str, category: str, source: str) -> None:
        name = (name or "").strip()
        if len(name) < 2 or name.lower() in seen:
            return
        seen.add(name.lower())
        candidates.append({"canonical_text": name, "category": category,
                           "source": source})

    if "psyke" in sources:
        try:
            for entry in db.get_all_psyke_entries(project_id):
                add(entry.name,
                    _PSYKE_CATEGORY.get(entry.entry_type, "custom"),
                    "imported_from_psyke")
        except Exception:
            pass
    if "characters" in sources:
        try:
            for character in db.get_all_characters(project_id):
                add(character.name, "character", "imported_from_psyke")
        except Exception:
            pass
    if "outline" in sources:
        try:
            from logosforge import story_structure as ss
            for scene in ss.list_scenes(db, project_id):
                add(getattr(scene, "title", ""), "custom",
                    "imported_from_outline")
        except Exception:
            pass
    return candidates


def import_candidates(db, project_id: int, candidates: list[dict]) -> int:
    """Create glossary terms from CONFIRMED candidates. De-duplicated."""
    existing = {t.canonical_text.lower()
                for t in db.get_voice_glossary_terms(project_id)}
    created = 0
    for candidate in candidates:
        name = (candidate.get("canonical_text") or "").strip()
        if not name or name.lower() in existing:
            continue
        db.create_voice_glossary_term(
            project_id, name,
            category=candidate.get("category", "custom"),
            source=candidate.get("source", "manual"))
        existing.add(name.lower())
        created += 1
    return created
