"""Semantic Continuity orchestration + persistence (Phase 10Q).

Builds the in-memory continuity report from the detectors, merges persisted
issue *status* (dismiss/resolve/defer) by stable key, and optionally records a
check run. Deterministic, read-only by default, current-project-only, capped.
"""

from __future__ import annotations

import json

from logosforge.continuity import contradiction_detector as CD
from logosforge.continuity import issue_detector as ID
from logosforge.continuity import models as M
from logosforge.continuity import transition_detector as TD
from logosforge.continuity.facts import extract_facts
from logosforge.continuity.state_tracker import build_states
from logosforge.writing_modes import get_project_writing_mode_by_id, normalize_mode

_MAX_ISSUES = 120


def build_continuity_report(db, project_id: int, *, scope: str = "project",
                            scene_id: int | None = None,
                            chapter_id: int | None = None,
                            writing_mode: str | None = None,
                            options: dict | None = None) -> M.ContinuityReport:
    mode = normalize_mode(writing_mode
                          or get_project_writing_mode_by_id(db, project_id))
    report = M.ContinuityReport(project_id=project_id, writing_mode=mode,
                                scope=scope, target_type=("scene" if scene_id else None),
                                target_id=scene_id)
    pf = extract_facts(db, project_id)
    report.facts = pf.facts
    report.unavailable = list(pf.unavailable)
    report.states = build_states(pf)

    issues: list[M.ContinuityIssueData] = []
    issues += CD.detect_contradictions(db, project_id, pf, mode)
    issues += TD.detect_missing_transitions(pf, mode)
    issues += ID.detect_production(pf, mode)
    issues += ID.detect_character_drift(pf)
    issues += ID.detect_scenes_missing_psyke(pf)

    # Mode-specific deferred placeholders (no false warnings).
    if mode in ("graphic_novel", "stage_script", "series"):
        report.unavailable.append(f"{mode}_continuity")

    issues = _merge_status(db, project_id, issues)[:_MAX_ISSUES]
    issues.sort(key=lambda i: i.rank)
    report.issues = issues
    return report


def _merge_status(db, project_id: int, issues: list) -> list:
    """Apply persisted user status (dismissed/resolved/deferred) by issue_key."""
    try:
        rows = {r.issue_key: r for r in db.get_continuity_issues(project_id)}
    except Exception:
        rows = {}
    for issue in issues:
        row = rows.get(issue.issue_key)
        if row is not None and row.status != "open":
            issue.status = row.status
    return issues


def check_scene_continuity(db, project_id: int, scene_id: int, *,
                           include_previous: bool = True,
                           include_next: bool = True) -> M.ContinuityReport:
    """Continuity issues touching a scene (and optionally its neighbors)."""
    full = build_continuity_report(db, project_id, scope="scene", scene_id=scene_id)
    scenes = list(db.get_all_scenes(project_id))
    ids = [getattr(s, "id", None) for s in scenes]
    relevant = {scene_id}
    if scene_id in ids:
        i = ids.index(scene_id)
        if include_previous and i > 0:
            relevant.add(ids[i - 1])
        if include_next and i < len(ids) - 1:
            relevant.add(ids[i + 1])
    full.issues = [iss for iss in full.issues
                   if not iss.related_scene_ids
                   or relevant & set(iss.related_scene_ids)]
    return full


def persist_check_run(db, project_id: int, report: M.ContinuityReport):
    oi = report.open_issues()
    try:
        return db.create_continuity_check_run(
            project_id, scope=report.scope,
            target_type=report.target_type, target_id=report.target_id,
            writing_mode=report.writing_mode, summary=report.summary_line(),
            issue_count=len(oi), blocking_count=report.blocking_count,
            warning_count=report.warning_count)
    except Exception:
        return None


def set_issue_status(db, project_id: int, issue: M.ContinuityIssueData,
                     status: str):
    """Persist a dismiss/resolve/defer (issue metadata only — no content)."""
    return db.upsert_continuity_issue(
        project_id, issue.issue_key, issue_type=issue.issue_type,
        dimension=issue.dimension, severity=issue.severity,
        confidence=issue.confidence, title=issue.title,
        explanation=issue.explanation,
        evidence_json=json.dumps(issue.evidence)[:2000],
        related_scene_ids_json=json.dumps(issue.related_scene_ids),
        suggested_action=issue.suggested_action, status=status)


def get_continuity_issues(db, project_id: int, *, severity: str | None = None,
                          dimension: str | None = None, status: str | None = None,
                          limit: int = 50) -> list[M.ContinuityIssueData]:
    report = build_continuity_report(db, project_id)
    out = report.issues
    if status is not None:
        out = [i for i in out if i.status == status]
    else:
        out = [i for i in out if i.status == "open"]
    if severity is not None:
        out = [i for i in out if i.severity == severity]
    if dimension is not None:
        out = [i for i in out if i.dimension == dimension]
    return out[:limit]
