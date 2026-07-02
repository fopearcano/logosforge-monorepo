"""Writing Methods RAG — keyword retrieval over docs/Writing-Methods_RAG.md."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_DOCS_PATH = Path(__file__).resolve().parents[2] / "docs" / "Writing-Methods_RAG.md"

_sections: list["MethodSection"] | None = None


@dataclass(frozen=True)
class MethodSection:
    title: str
    body: str
    keywords: frozenset[str]


@dataclass(frozen=True)
class MethodResult:
    title: str
    snippet: str
    score: float


def _normalize(text: str) -> str:
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_approx = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9\s]", "", ascii_approx.lower())


def _extract_keywords(title: str, body: str) -> frozenset[str]:
    words = set(_normalize(title).split())
    for line in body.split("\n")[:4]:
        words.update(_normalize(line).split())
    words.discard("")
    return frozenset(words)


def _load_sections(path: Path | None = None) -> list[MethodSection]:
    target = path or _DOCS_PATH
    if not target.exists():
        return []

    text = target.read_text(encoding="utf-8")
    chunks: list[MethodSection] = []
    current_title = ""
    current_lines: list[str] = []

    for line in text.split("\n"):
        if line.startswith("## "):
            if current_title:
                body = "\n".join(current_lines).strip()
                chunks.append(MethodSection(
                    title=current_title,
                    body=body,
                    keywords=_extract_keywords(current_title, body),
                ))
            current_title = line[3:].strip()
            current_lines = []
        elif current_title:
            current_lines.append(line)

    if current_title:
        body = "\n".join(current_lines).strip()
        chunks.append(MethodSection(
            title=current_title,
            body=body,
            keywords=_extract_keywords(current_title, body),
        ))

    return chunks


def _get_sections() -> list[MethodSection]:
    global _sections
    if _sections is None:
        _sections = _load_sections()
    return _sections


def _score_section(section: MethodSection, query_terms: set[str]) -> float:
    if not query_terms:
        return 0.0

    title_norm = _normalize(section.title)
    title_words = set(title_norm.split())

    title_matches = len(query_terms & title_words)
    keyword_matches = len(query_terms & section.keywords)

    body_norm = _normalize(section.body)
    body_hits = sum(1 for t in query_terms if t in body_norm)

    score = (title_matches * 3.0 + keyword_matches * 1.5 + body_hits * 0.5)
    max_possible = len(query_terms) * 5.0
    return min(score / max_possible, 1.0) if max_possible > 0 else 0.0


def get_relevant_writing_methods(
    query: str, max_results: int = 3
) -> list[MethodResult]:
    """Retrieve writing method sections matching the query by keyword overlap."""
    sections = _get_sections()
    if not sections:
        return []

    query_terms = set(_normalize(query).split())
    query_terms.discard("")
    if not query_terms:
        return []

    scored: list[tuple[float, MethodSection]] = []
    for sec in sections:
        s = _score_section(sec, query_terms)
        if s > 0.0:
            scored.append((s, sec))

    scored.sort(key=lambda x: x[0], reverse=True)

    results: list[MethodResult] = []
    for score, sec in scored[:max_results]:
        snippet = sec.body
        if len(snippet) > 300:
            snippet = snippet[:297] + "..."
        results.append(MethodResult(title=sec.title, snippet=snippet, score=round(score, 3)))

    return results


def reload() -> None:
    """Force reload of the markdown file (useful after edits)."""
    global _sections
    _sections = None


_BEAT_LABELS = ("Beats:", "Stages:", "Steps:", "Points:", "Parts:", "Template:")


def extract_beats(snippet: str) -> list[str]:
    """Parse the beat/stage list from a method snippet."""
    for label in _BEAT_LABELS:
        if label not in snippet:
            continue
        beat_line = snippet.split(label, 1)[1].split("\n")[0]
        raw = [b.strip().rstrip(".") for b in beat_line.split(",")]
        return [b for b in raw if b]
    return []
