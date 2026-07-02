"""Semantic Continuity Engine data model (Phase 10Q).

In-memory dataclasses for facts, states, issues and reports. Facts and states are
**rebuilt** on every check (not persisted); only issue *status* and check-run
summaries are persisted (see ``logosforge.models``). Pure data: no Qt, no LLM,
no DB. Evidence stores short excerpts/references, never full manuscript text.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

# -- Dimensions -------------------------------------------------------------
DIM_CHARACTER = "character"
DIM_TEMPORAL = "temporal"
DIM_SPATIAL = "spatial"
DIM_OBJECT = "object"
DIM_PLOT = "plot"
DIM_LORE = "lore"
DIM_THEME = "theme"
DIM_DIALOGUE = "dialogue"
DIM_PRODUCTION = "production"
DIM_MODE = "mode_specific"
DIMENSIONS = (DIM_CHARACTER, DIM_TEMPORAL, DIM_SPATIAL, DIM_OBJECT, DIM_PLOT,
              DIM_LORE, DIM_THEME, DIM_DIALOGUE, DIM_PRODUCTION, DIM_MODE)

# -- Issue types ------------------------------------------------------------
IT_CONTRADICTION = "contradiction"
IT_MISSING_TRANSITION = "missing_transition"
IT_STATE_DRIFT = "state_drift"
IT_UNRESOLVED_SETUP = "unresolved_setup"
IT_PAYOFF_WITHOUT_SETUP = "payoff_without_setup"
IT_CONTINUITY_GAP = "continuity_gap"
IT_TEMPORAL_IMPOSSIBILITY = "temporal_impossibility"
IT_LOCATION_JUMP = "location_jump"
IT_OBJECT_DISCONTINUITY = "object_discontinuity"
IT_RELATIONSHIP_INCONSISTENCY = "relationship_inconsistency"
IT_VOICE_DRIFT = "voice_drift"
IT_WORLD_RULE_VIOLATION = "world_rule_violation"
IT_PRODUCTION_RISK = "production_continuity_risk"

# -- Severity ---------------------------------------------------------------
SEV_INFO = "info"
SEV_SUGGESTION = "suggestion"
SEV_WARNING = "warning"
SEV_BLOCKING = "blocking"
_SEV_RANK = {SEV_BLOCKING: 0, SEV_WARNING: 1, SEV_SUGGESTION: 2, SEV_INFO: 3}

# -- Confidence -------------------------------------------------------------
CONF_CONFIRMED = "confirmed"
CONF_LIKELY = "likely"
CONF_POSSIBLE = "possible"
CONF_UNKNOWN = "unknown"

# -- Fact types -------------------------------------------------------------
FT_CHARACTER_STATE = "character_state"
FT_RELATIONSHIP_STATE = "relationship_state"
FT_LOCATION_STATE = "location_state"
FT_OBJECT_STATE = "object_state"
FT_TEMPORAL_MARKER = "temporal_marker"
FT_LORE_RULE = "lore_rule"
FT_SETUP = "setup"
FT_PAYOFF = "payoff"
FT_MOTIF = "motif"
FT_DIALOGUE_VOICE = "dialogue_voice"
FT_PRODUCTION = "production_continuity"


@dataclass
class ContinuityFact:
    fact_type: str
    subject_type: str = ""
    subject_id: int | None = None
    scene_id: int | None = None
    chapter: str = ""
    act: str = ""
    value: str = ""
    confidence: str = CONF_POSSIBLE
    provenance: str = ""
    source_system: str = ""
    order_index: int = 0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"fact_type": self.fact_type, "subject_type": self.subject_type,
                "subject_id": self.subject_id, "scene_id": self.scene_id,
                "value": self.value, "confidence": self.confidence,
                "provenance": self.provenance, "source_system": self.source_system,
                "order_index": self.order_index, "metadata": dict(self.metadata)}


@dataclass
class ContinuityState:
    subject_type: str
    subject_id: int | None
    dimension: str
    label: str = ""
    # ordered (order_index, scene_id, value) observations
    observations: list = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"subject_type": self.subject_type, "subject_id": self.subject_id,
                "dimension": self.dimension, "label": self.label,
                "observations": list(self.observations)}


@dataclass
class ContinuityIssueData:
    issue_type: str
    dimension: str
    severity: str
    confidence: str
    title: str
    explanation: str = ""
    suggested_action: str = ""
    evidence: list = field(default_factory=list)
    related_scene_ids: list = field(default_factory=list)
    related_node_ids: list = field(default_factory=list)
    status: str = "open"

    @property
    def rank(self) -> int:
        return _SEV_RANK.get(self.severity, 4)

    @property
    def issue_key(self) -> str:
        base = (f"{self.issue_type}|{self.dimension}|"
                f"{','.join(str(s) for s in sorted(self.related_scene_ids))}|"
                f"{self.title}")
        return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {"issue_type": self.issue_type, "dimension": self.dimension,
                "severity": self.severity, "confidence": self.confidence,
                "title": self.title, "explanation": self.explanation,
                "suggested_action": self.suggested_action,
                "evidence": list(self.evidence),
                "related_scene_ids": list(self.related_scene_ids),
                "related_node_ids": list(self.related_node_ids),
                "status": self.status, "issue_key": self.issue_key}


@dataclass
class ContinuityReport:
    project_id: int
    writing_mode: str = "novel"
    scope: str = "project"
    target_type: str | None = None
    target_id: int | None = None
    issues: list = field(default_factory=list)         # list[ContinuityIssueData]
    facts: list = field(default_factory=list)          # list[ContinuityFact]
    states: list = field(default_factory=list)         # list[ContinuityState]
    unavailable: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def open_issues(self) -> list:
        return [i for i in self.issues if i.status == "open"]

    @property
    def blocking_count(self) -> int:
        return sum(1 for i in self.open_issues() if i.severity == SEV_BLOCKING)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.open_issues() if i.severity == SEV_WARNING)

    def top_issues(self, n: int = 5) -> list:
        return sorted(self.open_issues(), key=lambda i: i.rank)[:n]

    def summary_line(self) -> str:
        oi = self.open_issues()
        return (f"Continuity ({self.writing_mode}): {len(oi)} open issue(s), "
                f"{self.blocking_count} blocking, {self.warning_count} warning.")

    def to_dict(self) -> dict[str, Any]:
        return {"project_id": self.project_id, "writing_mode": self.writing_mode,
                "scope": self.scope, "issues": [i.to_dict() for i in self.issues],
                "unavailable": list(self.unavailable),
                "warnings": list(self.warnings)}


@dataclass
class ContinuityChangeValidation:
    target_type: str
    target_id: int | None
    writing_mode: str = "novel"
    blocking: list = field(default_factory=list)       # list[str]
    warnings: list = field(default_factory=list)       # list[str]
    suggestions: list = field(default_factory=list)    # list[str]
    related_psyke: list = field(default_factory=list)  # list[str]
    suggested_apply_mode: str = "replace"
    follow_up_checks: list = field(default_factory=list)

    @property
    def is_safe(self) -> bool:
        return not self.blocking

    def summary_line(self) -> str:
        return (f"Continuity validation: {len(self.blocking)} blocking, "
                f"{len(self.warnings)} warning(s)."
                + ("" if self.is_safe else " Review before applying."))

    def to_dict(self) -> dict[str, Any]:
        return {"target_type": self.target_type, "target_id": self.target_id,
                "writing_mode": self.writing_mode, "blocking": list(self.blocking),
                "warnings": list(self.warnings), "suggestions": list(self.suggestions),
                "related_psyke": list(self.related_psyke),
                "suggested_apply_mode": self.suggested_apply_mode,
                "follow_up_checks": list(self.follow_up_checks),
                "is_safe": self.is_safe}
