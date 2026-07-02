"""Workflow recommendations from the Decision Radar (Phase 10O).

Deterministic mapping: given the current Project Intelligence radar + state,
suggest which guided workflow(s) would help most. Reads only; no LLM; no
mutation. The user always chooses whether to start one.
"""

from __future__ import annotations

from dataclasses import dataclass

from logosforge.guided_workflows.registry import (
    get_template,
    list_workflow_templates,
)
from logosforge.writing_modes import normalize_mode

# Decision Radar category -> recommended template id.
_CATEGORY_TEMPLATE = {
    "structure": "classical_outline",
    "psyke": "psyke_story_bible",
    "rewrite": "rewrite",
    "apply": "decision_radar_fix",
    "continuity": "decision_radar_fix",
    "export": "export_readiness",
    "production": "screenplay_production_prep",
    "graph": "psyke_story_bible",
}


@dataclass
class WorkflowRecommendation:
    template_id: str
    title: str
    reason: str
    severity: str = "suggestion"

    def to_dict(self) -> dict:
        return {"template_id": self.template_id, "title": self.title,
                "reason": self.reason, "severity": self.severity}


def build_workflow_recommendations(db, project_id: int, *, cap: int = 4,
                                   ) -> list[WorkflowRecommendation]:
    """Recommend workflows for the current project, ranked by radar severity."""
    try:
        from logosforge.project_intelligence import build_project_intelligence_report
        report = build_project_intelligence_report(db, project_id, light=True)
    except Exception:
        return []

    mode = normalize_mode(report.overview.get("writing_mode"))
    offered = {t.id for t in list_workflow_templates(mode)}

    recs: list[WorkflowRecommendation] = []
    seen: set[str] = set()

    # 1. Empty-project bootstrap.
    if not report.overview.get("total_scenes"):
        tpl = get_template("project_setup")
        if tpl and "project_setup" not in seen:
            recs.append(WorkflowRecommendation(
                tpl.id, tpl.title, "Project has no scenes yet — start here.",
                "suggestion"))
            seen.add(tpl.id)

    # 2. Radar-driven (already severity-ranked).
    for card in report.radar:
        tid = _CATEGORY_TEMPLATE.get(card.category)
        if not tid or tid in seen or tid not in offered:
            continue
        tpl = get_template(tid)
        if tpl is None:
            continue
        recs.append(WorkflowRecommendation(
            tpl.id, tpl.title, card.title, card.severity))
        seen.add(tid)
        if len(recs) >= cap:
            break

    return recs[:cap]
