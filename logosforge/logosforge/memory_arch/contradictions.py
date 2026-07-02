"""Contradiction checker (Phase 4 — deterministic heuristic, non-destructive).

Implements `docs/architecture/MEMORY_OBJECT_SCHEMA.md` writer invariants with a
**simple, local-only, keyword heuristic** — no LLM, no embeddings, no network.
It only *surfaces* likely conflicts; it never mutates memory, never deletes, and
never auto-supersedes. Resolution stays explicit (review service / user).

Heuristic: two memory objects "contradict" when they live in the same scope
(and the same project, for project scope), share a high proportion of
significant keywords, **and** exactly one of them carries a negation/polarity
token. This is intentionally conservative — it flags candidates for human
review, nothing more.
"""

from __future__ import annotations

import re

from logosforge.memory_arch.schema import MemoryObject, MemoryScope

# Tokens that flip the polarity of an otherwise-similar statement.
_NEGATIONS = {
    "not", "no", "never", "none", "without", "cannot", "stop", "stopped",
    "isn't", "aren't", "wasn't", "weren't", "doesn't", "don't", "didn't",
    "won't", "wouldn't", "shouldn't", "can't", "couldn't", "nor", "neither",
}

# Low-signal words ignored when comparing statements.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for",
    "is", "are", "was", "were", "be", "been", "being", "it", "its", "this",
    "that", "these", "those", "we", "i", "you", "they", "he", "she", "as",
    "at", "by", "with", "from", "will", "would", "should", "can", "could",
    "do", "does", "did", "has", "have", "had", "our", "their", "my", "your",
}


def keyword_set(text: str) -> set[str]:
    """Significant lowercase word tokens (no stopwords, len > 2)."""
    words = re.findall(r"[a-z0-9'][a-z0-9'\-]*", (text or "").lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def has_negation(text: str) -> bool:
    words = set(re.findall(r"[a-z']+", (text or "").lower()))
    return bool(words & _NEGATIONS)


def _same_subject(a: MemoryObject, b: MemoryObject) -> bool:
    if a.scope is not b.scope:
        return False
    if a.scope is MemoryScope.PROJECT and a.project_id != b.project_id:
        return False
    if a.scope is MemoryScope.USER and a.user_id != b.user_id:
        return False
    return True


def contradicts(a: MemoryObject, b: MemoryObject,
                overlap_threshold: float = 0.4) -> str | None:
    """Return a human-readable reason if ``a`` and ``b`` likely conflict, else
    ``None``. Pure function: never mutates either object."""
    if a.id == b.id or not _same_subject(a, b):
        return None
    ka, kb = keyword_set(a.content), keyword_set(b.content)
    if not ka or not kb:
        return None
    overlap = len(ka & kb) / len(ka | kb)
    if overlap < overlap_threshold:
        return None
    if has_negation(a.content) != has_negation(b.content):
        return (f"{overlap:.0%} keyword overlap with opposing polarity "
                f"(one statement is negated)")
    return None


def pairwise_contradictions(memories: list[MemoryObject]
                            ) -> list[tuple[MemoryObject, MemoryObject, str]]:
    """All likely-conflicting pairs within a set. Deterministic, read-only."""
    out: list[tuple[MemoryObject, MemoryObject, str]] = []
    items = list(memories)
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            reason = contradicts(items[i], items[j])
            if reason:
                out.append((items[i], items[j], reason))
    return out


class ContradictionChecker:
    """Heuristic, non-destructive contradiction surface."""

    def find_contradictions(self, memory_candidate: MemoryObject,
                            existing_memory: list[MemoryObject]
                            ) -> list[MemoryObject]:
        """Existing memories that likely conflict with the candidate. Empty
        when there is nothing to compare against. Never mutates."""
        return [m for m in (existing_memory or [])
                if contradicts(memory_candidate, m) is not None]

    def propose_resolution(self, memory_candidate: MemoryObject,
                           contradictions: list[MemoryObject]) -> dict:
        """Describe a *suggested* (never auto-applied) resolution. The user or
        review service decides whether to supersede / mark contradicted."""
        if not contradictions:
            return {"action": "none", "candidate_id": memory_candidate.id,
                    "contradictions": [], "note": "no contradictions found."}
        return {
            "action": "review_supersede",
            "candidate_id": memory_candidate.id,
            "contradictions": [m.id for m in contradictions],
            "note": ("possible conflict — review and explicitly supersede or "
                     "mark contradicted; nothing changed automatically."),
        }
