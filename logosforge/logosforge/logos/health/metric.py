"""NarrativeHealthMetric — one explainable health reading for a category.

A metric is always evidence-based: its status is derived from the diagnostics
that fed it. When a category has no analyzable data the status is ``unknown``
(never a false negative). No fake percentages — confidence is the max diagnostic
confidence behind the metric, shown only as supporting detail.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

# -- Categories (12) ---------------------------------------------------------
CAT_STRUCTURE = "structure"
CAT_CHARACTER = "character"
CAT_RELATIONSHIP = "relationship"
CAT_THEME = "theme"
CAT_CONTINUITY = "continuity"
CAT_TIMELINE = "timeline"
CAT_PACING = "pacing"
CAT_SCENE_PURPOSE = "scene_purpose"
CAT_SETUP_PAYOFF = "setup_payoff"
CAT_PSYKE = "psyke"
CAT_GRAPH = "graph"
CAT_NOTES = "notes"
# Phase 10L — rewrite sandbox (general / cross-mode; only when an open session
# exists). NOT part of the core 12 and NOT screenplay-only.
CAT_REWRITE_CONTINUITY = "rewrite_continuity_risk"
CAT_PSYKE_PRESERVATION = "psyke_preservation_risk"
CAT_SOURCE_STALENESS = "source_staleness_risk"

ALL_CATEGORIES = (
    CAT_STRUCTURE, CAT_CHARACTER, CAT_RELATIONSHIP, CAT_THEME, CAT_CONTINUITY,
    CAT_TIMELINE, CAT_PACING, CAT_SCENE_PURPOSE, CAT_SETUP_PAYOFF, CAT_PSYKE,
    CAT_GRAPH, CAT_NOTES,
)

# -- Screenplay-mode categories (Phase 10C, appended only for screenplay) -----
# Not part of the core 12; surfaced in addition for screenplay projects.
CAT_VISUAL_ACTION = "visual_action"
CAT_SCENE_ECONOMY = "scene_economy"
CAT_DIALOGUE_ECONOMY = "dialogue_economy"
CAT_SCENE_TURN = "scene_turn"
CAT_CHARACTER_OBJECTIVE = "character_objective"
CAT_SP_SETUP_PAYOFF = "sp_setup_payoff"
CAT_SUBTEXT = "subtext"
CAT_CINEMATIC_CONTINUITY = "cinematic_continuity"
# Phase 10D additions.
CAT_MOTIF_RECURRENCE = "motif_recurrence"
CAT_ON_THE_NOSE = "on_the_nose"
# Phase 10E additions (graph/link coverage).
CAT_LINK_COVERAGE = "confirmed_link_coverage"
CAT_CANDIDATE_DENSITY = "candidate_density"
# Phase 10F additions (export/format readiness — format health, not narrative).
CAT_EXPORT_READINESS = "export_readiness"
CAT_TITLE_PAGE = "title_page_completeness"
CAT_SCENE_HEADING_INTEGRITY = "scene_heading_integrity"
CAT_DIALOGUE_FORMAT = "dialogue_formatting_integrity"
# Phase 10G additions (Fountain format health).
CAT_FOUNTAIN_READINESS = "fountain_export_readiness"
CAT_UNSUPPORTED_ELEMENTS = "unsupported_screenplay_elements"
# Phase 10H additions (professional output health).
CAT_PRO_OUTPUT_READINESS = "professional_output_readiness"
CAT_FDX_COMPAT_RISK = "fdx_compatibility_risk"
# Phase 10J additions (production draft health — only when production active).
CAT_PRODUCTION_READINESS = "production_draft_readiness"
CAT_SCENE_NUMBERING = "scene_numbering_integrity"
CAT_REVISION_SET = "revision_set_integrity"
# Phase 10K additions (revision intelligence — only when a saved report exists).
CAT_REVISION_CAUSALITY = "revision_causality_risk"
CAT_CONTINUITY_REVISION = "continuity_revision_risk"

SCREENPLAY_CATEGORIES = (
    CAT_VISUAL_ACTION, CAT_SCENE_ECONOMY, CAT_DIALOGUE_ECONOMY, CAT_SCENE_TURN,
    CAT_CHARACTER_OBJECTIVE, CAT_SP_SETUP_PAYOFF, CAT_SUBTEXT,
    CAT_CINEMATIC_CONTINUITY, CAT_MOTIF_RECURRENCE, CAT_ON_THE_NOSE,
    CAT_LINK_COVERAGE, CAT_CANDIDATE_DENSITY,
    CAT_EXPORT_READINESS, CAT_TITLE_PAGE, CAT_SCENE_HEADING_INTEGRITY,
    CAT_DIALOGUE_FORMAT, CAT_FOUNTAIN_READINESS, CAT_UNSUPPORTED_ELEMENTS,
    CAT_PRO_OUTPUT_READINESS, CAT_FDX_COMPAT_RISK,
    CAT_PRODUCTION_READINESS, CAT_SCENE_NUMBERING, CAT_REVISION_SET,
    CAT_REVISION_CAUSALITY, CAT_CONTINUITY_REVISION,
)

_CATEGORY_NAMES = {
    CAT_STRUCTURE: "Structure",
    CAT_CHARACTER: "Character",
    CAT_RELATIONSHIP: "Relationships",
    CAT_THEME: "Theme / Motif",
    CAT_CONTINUITY: "Continuity",
    CAT_TIMELINE: "Timeline",
    CAT_PACING: "Pacing",
    CAT_SCENE_PURPOSE: "Scene Purpose",
    CAT_SETUP_PAYOFF: "Setup / Payoff",
    CAT_PSYKE: "PSYKE Completeness",
    CAT_GRAPH: "Graph Connectivity",
    CAT_NOTES: "Notes Integration",
    # Screenplay-mode names.
    CAT_VISUAL_ACTION: "Visual Action",
    CAT_SCENE_ECONOMY: "Scene Economy",
    CAT_DIALOGUE_ECONOMY: "Dialogue Economy",
    CAT_SCENE_TURN: "Scene Turn",
    CAT_CHARACTER_OBJECTIVE: "Character Objective",
    CAT_SP_SETUP_PAYOFF: "Setup / Payoff",
    CAT_SUBTEXT: "Dialogue Subtext",
    CAT_CINEMATIC_CONTINUITY: "Cinematic Continuity",
    CAT_MOTIF_RECURRENCE: "Motif Recurrence",
    CAT_ON_THE_NOSE: "On-the-Nose Dialogue Risk",
    CAT_LINK_COVERAGE: "Confirmed Setup/Payoff Coverage",
    CAT_CANDIDATE_DENSITY: "Unresolved Candidate Density",
    CAT_EXPORT_READINESS: "Export Readiness",
    CAT_TITLE_PAGE: "Title Page Completeness",
    CAT_SCENE_HEADING_INTEGRITY: "Scene Heading Integrity",
    CAT_DIALOGUE_FORMAT: "Dialogue Formatting Integrity",
    CAT_FOUNTAIN_READINESS: "Fountain Export Readiness",
    CAT_UNSUPPORTED_ELEMENTS: "Unsupported Screenplay Elements",
    CAT_PRO_OUTPUT_READINESS: "Professional Output Readiness",
    CAT_FDX_COMPAT_RISK: "FDX Compatibility Risk",
    CAT_PRODUCTION_READINESS: "Production Draft Readiness",
    CAT_SCENE_NUMBERING: "Scene Numbering Integrity",
    CAT_REVISION_SET: "Revision Set Integrity",
    CAT_REVISION_CAUSALITY: "Revision Causality Risk",
    CAT_CONTINUITY_REVISION: "Continuity Revision Risk",
    CAT_REWRITE_CONTINUITY: "Rewrite Continuity Risk",
    CAT_PSYKE_PRESERVATION: "PSYKE Preservation Risk",
    CAT_SOURCE_STALENESS: "Source Staleness Risk",
}

# -- Status ------------------------------------------------------------------
STATUS_UNKNOWN = "unknown"
STATUS_STABLE = "stable"
STATUS_WATCH = "watch"
STATUS_WEAK = "weak"
STATUS_CRITICAL = "critical"

# Worse statuses rank higher.
STATUS_RANK = {
    STATUS_UNKNOWN: -1,
    STATUS_STABLE: 0,
    STATUS_WATCH: 1,
    STATUS_WEAK: 2,
    STATUS_CRITICAL: 3,
}

# User-facing wording (no fake percentages).
STATUS_LABEL = {
    STATUS_UNKNOWN: "Not Enough Data",
    STATUS_STABLE: "Stable",
    STATUS_WATCH: "Needs Attention",
    STATUS_WEAK: "Weak Area",
    STATUS_CRITICAL: "Critical Risk",
}


def category_name(category: str) -> str:
    return _CATEGORY_NAMES.get(category, category.title())


@dataclass
class NarrativeHealthMetric:
    category: str
    status: str = STATUS_UNKNOWN
    name: str = ""
    confidence: float = 0.0
    evidence: str = ""
    related_diagnostics: list[str] = field(default_factory=list)
    target_type: str = ""
    target_id: str = ""
    suggested_actions: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.name:
            self.name = category_name(self.category)

    @property
    def id(self) -> str:
        raw = f"{self.category}:{self.status}:{self.evidence}"
        return "m_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]

    @property
    def status_label(self) -> str:
        return STATUS_LABEL.get(self.status, self.status)

    @property
    def status_rank(self) -> int:
        return STATUS_RANK.get(self.status, -1)

    @property
    def is_known(self) -> bool:
        return self.status != STATUS_UNKNOWN

    @property
    def is_problem(self) -> bool:
        return self.status in (STATUS_WEAK, STATUS_CRITICAL)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "name": self.name,
            "status": self.status,
            "status_label": self.status_label,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "related_diagnostics": list(self.related_diagnostics),
            "target_type": self.target_type,
            "target_id": self.target_id,
            "suggested_actions": list(self.suggested_actions),
        }
