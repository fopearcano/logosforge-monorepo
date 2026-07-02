"""Deterministic scene diff layer (Phase 10K).

Compares before/after scene text into a lightweight, serializable result —
hashes, added/removed terms, changed lines, truncated excerpts. No LLM, no DB,
no Qt; accent/Unicode-safe; safe for long scenes.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

_EXCERPT = 280
_MAX_TERMS = 40
_WORD = re.compile(r"\w[\w'’\-]*", re.UNICODE)


def _hash(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:16]


def _terms(text: str) -> set[str]:
    return {m.group(0).lower() for m in _WORD.finditer(text or "")}


def _excerpt(text: str) -> str:
    t = (text or "").strip()
    return t if len(t) <= _EXCERPT else t[:_EXCERPT] + "…"


@dataclass
class SceneDiffResult:
    before_hash: str = ""
    after_hash: str = ""
    changed_tokens: list[str] = field(default_factory=list)
    added_terms: list[str] = field(default_factory=list)
    removed_terms: list[str] = field(default_factory=list)
    changed_lines: int = 0
    before_excerpt: str = ""
    after_excerpt: str = ""
    change_size: int = 0
    change_summary: str = ""
    is_empty_change: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "before_hash": self.before_hash, "after_hash": self.after_hash,
            "changed_tokens": list(self.changed_tokens),
            "added_terms": list(self.added_terms),
            "removed_terms": list(self.removed_terms),
            "changed_lines": self.changed_lines,
            "before_excerpt": self.before_excerpt,
            "after_excerpt": self.after_excerpt,
            "change_size": self.change_size,
            "change_summary": self.change_summary,
            "is_empty_change": self.is_empty_change,
        }


def create_scene_diff(before_text: str | None, after_text: str | None) -> SceneDiffResult:
    """Deterministic diff between two scene texts (either may be None)."""
    before = before_text or ""
    after = after_text or ""
    res = SceneDiffResult(
        before_hash=_hash(before), after_hash=_hash(after),
        before_excerpt=_excerpt(before), after_excerpt=_excerpt(after),
    )
    if res.before_hash == res.after_hash:
        res.is_empty_change = True
        res.change_summary = "No change."
        return res

    bt, at = _terms(before), _terms(after)
    added = sorted(at - bt)
    removed = sorted(bt - at)
    res.added_terms = added[:_MAX_TERMS]
    res.removed_terms = removed[:_MAX_TERMS]
    res.changed_tokens = (added + removed)[:_MAX_TERMS]

    b_lines = before.splitlines()
    a_lines = after.splitlines()
    import difflib
    diff = list(difflib.ndiff(b_lines, a_lines))
    res.changed_lines = sum(1 for d in diff if d[:1] in ("+", "-"))
    res.change_size = abs(len(after) - len(before)) + len(added) + len(removed)
    res.change_summary = (
        f"{len(added)} term(s) added, {len(removed)} removed; "
        f"{res.changed_lines} line(s) changed."
    )
    return res
