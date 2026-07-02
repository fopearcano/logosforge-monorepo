"""PSYKE entry search — cached, fuzzy, case-insensitive."""

from __future__ import annotations

from dataclasses import dataclass

from logosforge.db import Database
from logosforge.models.models import PsykeEntry

MAX_RESULTS = 8


@dataclass(frozen=True)
class SearchResult:
    entry_id: int
    name: str
    entry_type: str
    matched_on: str
    score: float


class PsykeSearchIndex:
    """In-memory search index over PSYKE entries for a project."""

    def __init__(self, db: Database, project_id: int, *, lazy: bool = False) -> None:
        self._db = db
        self._project_id = project_id
        self._entries: list[PsykeEntry] = []
        self._index: list[tuple[PsykeEntry, list[str]]] = []
        if not lazy:
            self.rebuild()

    def rebuild(self) -> None:
        self.rebuild_from(self._db.get_all_psyke_entries(self._project_id))

    def rebuild_from(self, entries: list[PsykeEntry]) -> None:
        self._entries = entries
        self._index = []
        for entry in self._entries:
            tokens = [entry.name.lower()]
            if entry.aliases:
                for alias in entry.aliases.split(","):
                    alias = alias.strip().lower()
                    if alias:
                        tokens.append(alias)
            self._index.append((entry, tokens))

    def resolve_entity(self, name: str) -> SearchResult | None:
        """Return the single best match if it scores above the confidence threshold."""
        results = self.search(name, max_results=1)
        if results and results[0].score >= 0.6:
            return results[0]
        return None

    def search(self, query: str, max_results: int = MAX_RESULTS) -> list[SearchResult]:
        query = query.strip().lower()
        if not query:
            return []

        scored: list[SearchResult] = []
        for entry, tokens in self._index:
            best_score = 0.0
            best_match = ""
            for token in tokens:
                s = _score(query, token)
                if s > best_score:
                    best_score = s
                    best_match = token
            if best_score > 0:
                scored.append(SearchResult(
                    entry_id=entry.id,
                    name=entry.name,
                    entry_type=entry.entry_type,
                    matched_on=best_match,
                    score=best_score,
                ))

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:max_results]


def _score(query: str, target: str) -> float:
    """Score how well *query* matches *target*. Higher is better, 0 = no match."""
    if not query or not target:
        return 0.0

    # Exact match
    if query == target:
        return 1.0

    # Starts-with
    if target.startswith(query):
        return 0.9 + 0.1 * (len(query) / len(target))

    # Contains (substring)
    idx = target.find(query)
    if idx >= 0:
        return 0.6 + 0.1 * (len(query) / len(target))

    # Fuzzy: all query chars appear in order in target
    qi = 0
    matched = 0
    for ch in target:
        if qi < len(query) and ch == query[qi]:
            qi += 1
            matched += 1
    if qi == len(query):
        return 0.3 + 0.2 * (matched / len(target))

    # Word-initial match: query chars match first letters of words
    words = target.split()
    if len(query) <= len(words):
        initials_match = all(
            query[i] == words[i][0] for i in range(len(query)) if words[i]
        )
        if initials_match:
            return 0.25

    return 0.0
