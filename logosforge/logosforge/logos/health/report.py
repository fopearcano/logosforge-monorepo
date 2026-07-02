"""NarrativeHealthReport — the project-level health snapshot + exporters.

Serializable to JSON and Markdown. Carries the overall status, every category
metric, the top risks, strengths, prioritized recommendations, and the ids of
the diagnostics that fed it. No fake quality score — overall status is an
explainable label derived from the metrics.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from logosforge.logos.health.metric import (
    STATUS_LABEL,
    STATUS_UNKNOWN,
    NarrativeHealthMetric,
)


@dataclass
class HealthRecommendation:
    problem: str
    why: str
    evidence: str
    suggested_action: str = ""
    action_label: str = ""
    target_type: str = ""
    target_id: str = ""
    category: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "problem": self.problem,
            "why": self.why,
            "evidence": self.evidence,
            "suggested_action": self.suggested_action,
            "action_label": self.action_label,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "category": self.category,
        }


@dataclass
class NarrativeHealthReport:
    project_id: int
    project_title: str = ""
    generated_at: float = field(default_factory=time.time)
    overall_status: str = STATUS_UNKNOWN
    metrics: list[NarrativeHealthMetric] = field(default_factory=list)
    top_risks: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    recommendations: list[HealthRecommendation] = field(default_factory=list)
    diagnostic_ids: list[str] = field(default_factory=list)
    section_summaries: dict[str, str] = field(default_factory=dict)
    writing_mode: str = ""   # Phase 9 — project medium the report was built for

    @property
    def overall_label(self) -> str:
        return STATUS_LABEL.get(self.overall_status, self.overall_status)

    def metric_for(self, category: str) -> NarrativeHealthMetric | None:
        for m in self.metrics:
            if m.category == category:
                return m
        return None

    # -- Serialization -------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "project_title": self.project_title,
            "generated_at": self.generated_at,
            "overall_status": self.overall_status,
            "overall_label": self.overall_label,
            "metrics": [m.to_dict() for m in self.metrics],
            "top_risks": list(self.top_risks),
            "strengths": list(self.strengths),
            "recommendations": [r.to_dict() for r in self.recommendations],
            "diagnostic_ids": list(self.diagnostic_ids),
            "section_summaries": dict(self.section_summaries),
            "writing_mode": self.writing_mode,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def to_markdown(self) -> str:
        import datetime as _dt
        when = _dt.datetime.fromtimestamp(self.generated_at).strftime("%Y-%m-%d %H:%M")
        lines = [
            f"# Narrative Health — {self.project_title or 'Project'}",
            "",
            f"**Overall:** {self.overall_label}  ",
            f"**Generated:** {when}",
            "",
            "## Category Status",
            "",
        ]
        for m in self.metrics:
            line = f"- **{m.name}:** {m.status_label}"
            if m.evidence:
                line += f" — {m.evidence}"
            lines.append(line)

        if self.top_risks:
            lines += ["", "## Top Risks", ""]
            lines += [f"- {r}" for r in self.top_risks]
        if self.strengths:
            lines += ["", "## Strengths", ""]
            lines += [f"- {s}" for s in self.strengths]
        if self.recommendations:
            lines += ["", "## Recommendations", ""]
            for r in self.recommendations:
                lines.append(f"- **{r.problem}** — {r.why}")
                if r.evidence:
                    lines.append(f"  - Evidence: {r.evidence}")
                if r.action_label:
                    lines.append(f"  - Suggested action: {r.action_label}")
        lines.append("")
        return "\n".join(lines)
