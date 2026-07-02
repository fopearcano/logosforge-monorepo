"""Continuity → text serializers (Phase 10Q).

Concise, capped summaries for the Assistant context block and Logos messages.
Deterministic; no LLM; no DB write.
"""

from __future__ import annotations

from logosforge.continuity.collector import (
    build_continuity_report,
    check_scene_continuity,
)
from logosforge.continuity.models import ContinuityReport


def explain_issue(issue) -> str:
    lines = [f"[{issue.severity}] {issue.title}",
             f"Dimension: {issue.dimension}; confidence: {issue.confidence}."]
    if issue.explanation:
        lines.append(issue.explanation)
    if issue.evidence:
        lines.append("Evidence: " + "; ".join(str(e) for e in issue.evidence[:3]))
    if issue.suggested_action:
        lines.append("Suggested: " + issue.suggested_action)
    return "\n".join(lines)


def get_continuity_summary_for_assistant(db, project_id: int, *,
                                         section_name: str | None = None,
                                         scene_id: int | None = None,
                                         max_items: int = 5,
                                         report: ContinuityReport | None = None,
                                         ) -> str:
    """Capped ``[Continuity]`` block — top open issues for the current scope.

    Only emits when there are open issues. Scene-scoped when a scene is open.
    Deterministic; no LLM/DB write; no cross-project leak; no full dump.
    """
    try:
        if report is None:
            report = (check_scene_continuity(db, project_id, scene_id)
                      if scene_id is not None
                      else build_continuity_report(db, project_id))
    except Exception:
        return ""
    top = report.top_issues(max_items)
    if not top:
        return ""
    lines = ["[Continuity]", report.summary_line()]
    for i in top:
        lines.append(f"- [{i.severity}/{i.confidence}] {i.title}")
    lines.append("Advisory only — never auto-fix or dismiss; the user decides.")
    return "\n".join(lines)
