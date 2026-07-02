"""Continuity → Decision Radar cards (Phase 10Q).

Deterministic, traceable to actual continuity issues. No AI; no auto-fixes;
actions route through existing safe systems. Kept as a dedicated feed so the
core Project Intelligence radar contract is unchanged.
"""

from __future__ import annotations

from logosforge.continuity.collector import build_continuity_report
from logosforge.continuity import models as M
from logosforge.project_intelligence.decision_radar import (
    SEV_BLOCKING,
    SEV_SUGGESTION,
    SEV_WARNING,
    DecisionCard,
)

# continuity severity -> radar severity
_SEV_MAP = {M.SEV_BLOCKING: SEV_BLOCKING, M.SEV_WARNING: SEV_WARNING,
            M.SEV_SUGGESTION: SEV_SUGGESTION, M.SEV_INFO: SEV_SUGGESTION}


def build_continuity_decision_cards(db, project_id: int, *, report=None,
                                    cap: int = 8) -> list[DecisionCard]:
    if report is None:
        report = build_continuity_report(db, project_id)
    cards: list[DecisionCard] = []
    for issue in report.top_issues(cap):
        cards.append(DecisionCard(
            id=f"continuity_{issue.issue_key}", category="continuity",
            severity=_SEV_MAP.get(issue.severity, SEV_SUGGESTION),
            confidence=issue.confidence, title=issue.title,
            explanation=issue.explanation,
            suggested_action=issue.suggested_action, related_section="Continuity"))
    return cards[:cap]
