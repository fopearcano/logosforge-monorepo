"""Project Intelligence Dashboard service (Phase 10N).

Read-only aggregation across existing systems + a deterministic Decision Radar.
Creates no narrative data, mutates nothing, calls no LLM. ``light=True`` skips
the expensive Narrative Health + export-validation passes (used for the cheap
Assistant context block).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from logosforge.project_intelligence import collector as C
from logosforge.project_intelligence.decision_radar import (
    DecisionCard, build_decision_radar,
)


@dataclass
class ProjectIntelligenceReport:
    project_id: int
    overview: dict = field(default_factory=dict)
    psyke: dict = field(default_factory=dict)
    structure: dict = field(default_factory=dict)
    workflow: dict = field(default_factory=dict)
    export: dict = field(default_factory=dict)
    health: dict = field(default_factory=dict)
    radar: list = field(default_factory=list)  # list[DecisionCard]
    light: bool = False

    @property
    def writing_mode(self) -> str:
        return self.overview.get("writing_mode", "novel")

    def top_cards(self, n: int = 3) -> list[DecisionCard]:
        return self.radar[:n]

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id, "overview": dict(self.overview),
            "psyke": dict(self.psyke), "structure": dict(self.structure),
            "workflow": dict(self.workflow), "export": dict(self.export),
            "health": dict(self.health), "light": self.light,
            "radar": [c.to_dict() for c in self.radar],
        }

    def summary_line(self) -> str:
        ov = self.overview
        blocking = sum(1 for c in self.radar if c.severity == "blocking")
        warnings = sum(1 for c in self.radar if c.severity == "warning")
        return (f"{ov.get('title', 'Project')} ({ov.get('writing_mode', 'novel')}): "
                f"{ov.get('total_scenes', 0)} scenes, "
                f"{ov.get('total_psyke_entries', 0)} PSYKE; "
                f"{blocking} blocking, {warnings} warning decision(s).")


def build_project_intelligence_report(
    db, project_id: int, *, section_name: str | None = None,
    writing_mode: str | None = None, options: dict | None = None,
    light: bool = False,
) -> ProjectIntelligenceReport:
    """Build the read-only Project Intelligence report (current project only)."""
    report = ProjectIntelligenceReport(project_id=project_id, light=light)
    report.overview = C.collect_overview(db, project_id)
    report.psyke = C.collect_psyke_summary(db, project_id)
    report.structure = C.collect_structure_summary(db, project_id)
    report.workflow = C.collect_workflow_status(db, project_id)
    report.export = C.collect_export_readiness(db, project_id, light=light)
    report.health = {} if light else C.collect_health_summary(db, project_id)
    report.radar = build_decision_radar(
        report.overview, report.psyke, report.structure, report.workflow,
        report.export, report.health or None)
    return report
