"""NarrativeDiagnostic — a structured, PSYKE-aware narrative finding.

A diagnostic is a *non-destructive* analysis result: a category, evidence, a
confidence and severity, the entities it touches, and the existing Logos actions
that could address it. It never mutates data and never holds ORM rows, widgets,
or secrets. High-severity diagnostics convert to a Phase-4 ``LogosSuggestion``
via :meth:`to_suggestion`.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any

# -- Categories --------------------------------------------------------------
CAT_CHARACTER = "character"
CAT_RELATIONSHIP = "relationship"
CAT_THEME = "theme"
CAT_CONTINUITY = "continuity"
CAT_STRUCTURE = "structure"
CAT_SETUP_PAYOFF = "setup_payoff"
CAT_TIMELINE = "timeline"
CAT_GRAPH = "graph"
CAT_PSYKE = "psyke"

# -- Severity ----------------------------------------------------------------
SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_IMPORTANT = "important"
SEVERITY_CRITICAL = "critical"

_SEVERITY_RANK = {
    SEVERITY_INFO: 0,
    SEVERITY_WARNING: 1,
    SEVERITY_IMPORTANT: 2,
    SEVERITY_CRITICAL: 3,
}

# Diagnostic category -> the LogosSuggestion type used when surfaced as a pill.
_CATEGORY_TO_SUGGESTION_TYPE = {
    CAT_CHARACTER: "character",
    CAT_RELATIONSHIP: "psyke",
    CAT_THEME: "theme",
    CAT_CONTINUITY: "continuity",
    CAT_STRUCTURE: "structure",
    CAT_SETUP_PAYOFF: "structure",
    CAT_TIMELINE: "timeline",
    CAT_GRAPH: "graph",
    CAT_PSYKE: "psyke",
}


@dataclass
class NarrativeDiagnostic:
    category: str
    title: str
    message: str
    section_name: str = ""
    evidence: str = ""
    confidence: float = 0.0
    severity: str = SEVERITY_INFO
    target_type: str = ""
    target_id: str = ""
    related_scene_ids: list[int] = field(default_factory=list)
    related_psyke_entry_ids: list[int] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    @property
    def id(self) -> str:
        """Stable identity = sha1(category:target_type:target_id:evidence).

        Stable across scans (so dismissals stick) yet sensitive to the
        evidence, so a changed/fixed finding yields a new id.
        """
        raw = f"{self.category}:{self.target_type}:{self.target_id}:{self.evidence}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    @property
    def severity_rank(self) -> int:
        return _SEVERITY_RANK.get(self.severity, 0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "title": self.title,
            "message": self.message,
            "section_name": self.section_name,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "severity": self.severity,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "related_scene_ids": list(self.related_scene_ids),
            "related_psyke_entry_ids": list(self.related_psyke_entry_ids),
            "suggested_actions": list(self.suggested_actions),
            "created_at": self.created_at,
        }

    def to_suggestion(self):
        """Convert to a Phase-4 ``LogosSuggestion`` (id preserved for dedupe).

        The suggestion's id is derived the same way (type:target_type:target_id:
        evidence). We mirror the diagnostic's evidence + target so a dismissed
        suggestion and its source diagnostic share suppression semantics.
        """
        from logosforge.logos.proactive.suggestion import LogosSuggestion

        sug_type = _CATEGORY_TO_SUGGESTION_TYPE.get(self.category, "psyke")
        # Map critical -> important (the suggestion bar has no 'critical').
        severity = self.severity
        if severity == SEVERITY_CRITICAL:
            from logosforge.logos.proactive.suggestion import SEVERITY_IMPORTANT
            severity = SEVERITY_IMPORTANT
        return LogosSuggestion(
            type=sug_type,
            title=self.title,
            message=self.message,
            section_name=self.section_name,
            evidence=self.evidence,
            confidence=self.confidence,
            severity=severity,
            target_type=self.target_type,
            target_id=self.target_id,
            suggested_actions=list(self.suggested_actions),
        )
