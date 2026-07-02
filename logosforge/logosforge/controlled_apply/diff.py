"""Controlled-apply diff preview (Phase 10M). Deterministic; no LLM/DB/Qt."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ApplyDiff:
    before_hash: str = ""
    after_hash: str = ""
    added_terms: list[str] = field(default_factory=list)
    removed_terms: list[str] = field(default_factory=list)
    added_lines: int = 0
    removed_lines: int = 0
    change_size: int = 0
    is_empty_change: bool = False
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "before_hash": self.before_hash, "after_hash": self.after_hash,
            "added_terms": list(self.added_terms),
            "removed_terms": list(self.removed_terms),
            "added_lines": self.added_lines, "removed_lines": self.removed_lines,
            "change_size": self.change_size, "is_empty_change": self.is_empty_change,
            "summary": self.summary,
        }


def build_apply_diff(before_text: str, after_text: str) -> ApplyDiff:
    """Line/term diff between current and resulting text (reuses the 10K diff)."""
    from logosforge.revision_intelligence.diff import create_scene_diff
    d = create_scene_diff(before_text, after_text)
    import difflib
    b, a = (before_text or "").splitlines(), (after_text or "").splitlines()
    nd = list(difflib.ndiff(b, a))
    added = sum(1 for x in nd if x[:1] == "+")
    removed = sum(1 for x in nd if x[:1] == "-")
    return ApplyDiff(
        before_hash=d.before_hash, after_hash=d.after_hash,
        added_terms=d.added_terms, removed_terms=d.removed_terms,
        added_lines=added, removed_lines=removed, change_size=d.change_size,
        is_empty_change=d.is_empty_change, summary=d.change_summary,
    )
