"""Continuity → Decision Radar cards (Phase 10Q).

Deterministic, traceable to actual continuity issues. No AI; no auto-fixes;
actions route through existing safe systems. Kept as a dedicated feed so the
core Project Intelligence radar contract is unchanged.
"""

from __future__ import annotations

from logosforge.continuity import models as M
from logosforge.continuity.collector import build_continuity_report
from logosforge.project_intelligence.decision_radar import (
    SEV_BLOCKING,
    SEV_SUGGESTION,
    SEV_WARNING,
    DecisionCard,
    DecisionEvidence,
)

# continuity severity -> radar severity
_SEV_MAP = {M.SEV_BLOCKING: SEV_BLOCKING, M.SEV_WARNING: SEV_WARNING,
            M.SEV_SUGGESTION: SEV_SUGGESTION, M.SEV_INFO: SEV_SUGGESTION}
_CARD_CAP = 8
_EVIDENCE_CAP = 5


def _project_scenes(db, project_id: int) -> dict[int, str]:
    """Return the only scene identities continuity cards may publish."""
    return {
        int(scene.id): (getattr(scene, "title", "") or f"Scene {scene.id}")
        for scene in db.get_all_scenes(project_id)
        if isinstance(getattr(scene, "id", None), int)
        and not isinstance(scene.id, bool)
        and scene.id > 0
    }


def _issue_evidence(
    issue,
    scene_titles: dict[int, str],
) -> tuple[list[DecisionEvidence], int]:
    issue_key = issue.issue_key
    evidence = [DecisionEvidence(
        kind="continuity_issue",
        label=issue.title,
        detail=f"{issue.issue_type.replace('_', ' ')} · {issue.dimension}",
        confidence=issue.confidence,
        source_system="semantic_continuity",
        provenance=f"continuity:{issue.issue_type}",
        related_section="Continuity",
        related_target_type="continuity_issue",
        related_target_key=issue_key,
    )]

    seen_scene_ids: set[int] = set()
    for raw_scene_id in issue.related_scene_ids:
        if (
            not isinstance(raw_scene_id, int)
            or isinstance(raw_scene_id, bool)
            or raw_scene_id <= 0
            or raw_scene_id not in scene_titles
            or raw_scene_id in seen_scene_ids
        ):
            continue
        seen_scene_ids.add(raw_scene_id)
        evidence.append(DecisionEvidence(
            kind="scene",
            label=scene_titles[raw_scene_id],
            detail=f"Scene #{raw_scene_id} is explicitly related to this issue.",
            confidence=issue.confidence,
            source_system="manuscript",
            provenance=f"scene:{raw_scene_id}",
            related_section="Manuscript",
            related_target_type="scene",
            related_target_id=raw_scene_id,
        ))

    seen_details: set[str] = set()
    for item in issue.evidence:
        detail = str(item or "").strip()
        if not detail or detail in seen_details:
            continue
        seen_details.add(detail)
        evidence.append(DecisionEvidence(
            kind="continuity_detail",
            label="Detector evidence",
            detail=detail,
            confidence=issue.confidence,
            source_system="semantic_continuity",
            provenance=f"continuity:{issue.issue_type}",
            related_section="Continuity",
            related_target_type="continuity_issue",
            related_target_key=issue_key,
        ))

    return evidence[:_EVIDENCE_CAP], len(evidence)


def build_continuity_decision_cards(db, project_id: int, *, report=None,
                                    cap: int = 8) -> list[DecisionCard]:
    if report is None:
        report = build_continuity_report(db, project_id)
    report_project_id = getattr(report, "project_id", None)
    if (
        not isinstance(report_project_id, int)
        or isinstance(report_project_id, bool)
        or report_project_id != project_id
    ):
        raise ValueError("continuity report does not belong to this project")
    bounded_cap = min(max(int(cap), 0), _CARD_CAP)
    if bounded_cap == 0:
        return []
    scene_titles = _project_scenes(db, project_id)
    ordered_issues = sorted(
        report.open_issues(),
        key=lambda issue: (issue.rank, issue.issue_key),
    )
    issues = []
    seen_issue_keys: set[str] = set()
    for issue in ordered_issues:
        if issue.issue_key in seen_issue_keys:
            continue
        seen_issue_keys.add(issue.issue_key)
        issues.append(issue)
        if len(issues) >= bounded_cap:
            break
    cards: list[DecisionCard] = []
    for issue in issues:
        evidence, evidence_total = _issue_evidence(issue, scene_titles)
        cards.append(DecisionCard(
            id=f"continuity_{issue.issue_key}", category="continuity",
            severity=_SEV_MAP.get(issue.severity, SEV_SUGGESTION),
            confidence=issue.confidence, title=issue.title,
            explanation=issue.explanation,
            suggested_action=issue.suggested_action,
            related_section="Continuity",
            related_target_type="continuity_issue",
            related_target_key=issue.issue_key,
            created_from="semantic_continuity",
            evidence=evidence,
            evidence_total=evidence_total,
        ))
    return cards
