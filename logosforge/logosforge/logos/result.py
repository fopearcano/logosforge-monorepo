"""Structured result returned by every Logos action.

Logos is the inline/contextual assistant layer. A :class:`LogosResult` is a
plain, serializable value object — it never carries ORM rows, widgets, or
provider secrets, so it is safe to log and to ship to a UI or an API later.

Phase 0 is non-destructive: ``proposed_operations`` is always empty (preview
only) and nothing is auto-applied.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LogosResult:
    ok: bool
    action: str
    title: str = ""
    message: str = ""
    suggestions: list[str] = field(default_factory=list)
    # Phase 0: preview-only. Each op (in later phases) will describe a proposed,
    # confirmable change — never auto-applied here.
    proposed_operations: list[dict] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "action": self.action,
            "title": self.title,
            "message": self.message,
            "suggestions": list(self.suggestions),
            "proposed_operations": list(self.proposed_operations),
            "error": self.error,
        }

    @classmethod
    def failure(cls, action: str, error: str) -> "LogosResult":
        return cls(ok=False, action=action, title="Logos", message="", error=error)
