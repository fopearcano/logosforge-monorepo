"""LogosSuggestion — a lightweight, serializable proactive signal.

A suggestion is a *non-destructive* observation Logos surfaces while the user
works. It carries evidence, a confidence score, a severity, and the names of
existing Logos actions the user can run to address it. It never mutates data and
never holds ORM rows, widgets, or secrets.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any

# -- Suggestion types --------------------------------------------------------
TYPE_STRUCTURE = "structure"
TYPE_CONFLICT = "conflict"
TYPE_PACING = "pacing"
TYPE_CONTINUITY = "continuity"
TYPE_CHARACTER = "character"
TYPE_THEME = "theme"
TYPE_PSYKE = "psyke"
TYPE_TIMELINE = "timeline"
TYPE_GRAPH = "graph"
TYPE_STYLE = "style"
TYPE_DIALOGUE = "dialogue"

# -- Severities --------------------------------------------------------------
SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_IMPORTANT = "important"

_SEVERITY_RANK = {SEVERITY_INFO: 0, SEVERITY_WARNING: 1, SEVERITY_IMPORTANT: 2}


@dataclass
class LogosSuggestion:
    type: str
    title: str
    message: str
    section_name: str
    evidence: str = ""
    confidence: float = 0.0
    severity: str = SEVERITY_INFO
    target_type: str = ""          # "scene" | "psyke_entry" | "graph_node" | ...
    target_id: str = ""            # stable string id of the target
    suggested_actions: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    dismissed: bool = False
    snoozed_until: float = 0.0

    @property
    def id(self) -> str:
        """Stable identity = sha1(type:target_type:target_id:evidence).

        Stable enough to dedupe the same finding across scans, yet sensitive to
        a change in the underlying evidence (so a fixed/changed issue yields a
        new id rather than staying suppressed forever).
        """
        raw = f"{self.type}:{self.target_type}:{self.target_id}:{self.evidence}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    @property
    def severity_rank(self) -> int:
        return _SEVERITY_RANK.get(self.severity, 0)

    def is_active(self, now: float | None = None) -> bool:
        """A suggestion is shown only if not dismissed and not currently snoozed."""
        if self.dismissed:
            return False
        now = time.time() if now is None else now
        return self.snoozed_until <= now

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "message": self.message,
            "section_name": self.section_name,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "severity": self.severity,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "suggested_actions": list(self.suggested_actions),
            "created_at": self.created_at,
            "dismissed": self.dismissed,
            "snoozed_until": self.snoozed_until,
        }
