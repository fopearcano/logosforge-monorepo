"""Stage Script Review Dashboard — project-level status aggregation (Phase 7).

A deterministic, read-only roll-up of everything the earlier Stage Script phases
compute, into one place: per-scene status (Stage Beat Plan / Blocking-Cue Plan /
body / dialogue / stage action / entrances-exits / cues / continuity / Timeline /
PSYKE-Notes / export) in canonical order, project summary metrics, and a
recommended next action per scene. Reporting only — it never rewrites, applies, or
creates data.

It consolidates (never re-implements):
* canonical chain + cross-scene continuity — Phase 6 ``stage_script_continuity``,
* per-scene health — Phase 3 ``stage_script_diagnostics``,
* beat / blocking-cue plan presence — Phase 2 ``stage_script_pipeline``,
* rewrite candidates — Phase 5 scene-linked Notes (tag ``rewrite-candidate``).

This module is the model behind ``ui/stage_script_review_view`` and the
``stage_review_dashboard`` Logos action. No Qt, no LLM, no API keys. Markdown
export excludes all provider settings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# -- Status + severity vocab -------------------------------------------------
ST_OK = "OK"
ST_MISSING = "Missing"
ST_WARNING = "Warning"
ST_NEEDS_WORK = "Needs Work"
ST_ERROR = "Error"
ST_NOT_CHECKED = "Not Checked"

SEV_INFO = "info"
SEV_WARNING = "warning"
SEV_HIGH = "high"
SEV_CRITICAL = "critical"
_SEV_RANK = {SEV_INFO: 0, SEV_WARNING: 1, SEV_HIGH: 2, SEV_CRITICAL: 3}

# Map Phase 3 / Phase 6 severities (info/watch/weak/critical) -> review severity.
_MAP_SEV = {"info": SEV_INFO, "watch": SEV_WARNING, "weak": SEV_HIGH,
            "critical": SEV_CRITICAL}

FILTERS: tuple[str, ...] = (
    "All", "Missing Stage Beat Plan", "Missing Blocking / Cue Plan", "Missing Body",
    "Dialogue Heavy", "Missing Stage Action", "Entrance/Exit Warning",
    "Cue Warning", "Blocking Warning", "Continuity Risk", "Not Linked to Timeline",
    "Export Warning", "Needs Reflection",
)


@dataclass
class StageReviewRow:
    scene_id: int
    number: str = ""
    title: str = ""
    summary_present: bool = False
    beat_plan_status: str = ST_MISSING
    blocking_plan_status: str = ST_MISSING
    body_status: str = ST_MISSING
    block_count: int = 0
    dialogue_stage_ratio: float = 0.0
    dialogue_status: str = ST_OK
    stage_action_status: str = ST_OK
    entrance_exit_status: str = ST_OK
    cue_status: str = ST_OK
    blocking_status: str = ST_OK
    health_severity: str = SEV_INFO
    continuity_status: str = ST_OK
    continuity_severity: str = SEV_INFO
    reflection_status: str = ST_NOT_CHECKED
    timeline_status: str = ST_MISSING
    psyke_notes_status: str = ST_NOT_CHECKED
    export_status: str = ST_OK
    has_rewrite_candidate: bool = False
    next_action: str = ""
    overall_status: str = ST_OK

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id, "number": self.number, "title": self.title,
            "summary_present": self.summary_present,
            "beat_plan_status": self.beat_plan_status,
            "blocking_plan_status": self.blocking_plan_status,
            "body_status": self.body_status, "block_count": self.block_count,
            "dialogue_stage_ratio": self.dialogue_stage_ratio,
            "dialogue_status": self.dialogue_status,
            "stage_action_status": self.stage_action_status,
            "entrance_exit_status": self.entrance_exit_status,
            "cue_status": self.cue_status, "blocking_status": self.blocking_status,
            "health_severity": self.health_severity,
            "continuity_status": self.continuity_status,
            "continuity_severity": self.continuity_severity,
            "reflection_status": self.reflection_status,
            "timeline_status": self.timeline_status,
            "psyke_notes_status": self.psyke_notes_status,
            "export_status": self.export_status,
            "has_rewrite_candidate": self.has_rewrite_candidate,
            "next_action": self.next_action, "overall_status": self.overall_status,
        }


@dataclass
class StageScriptReviewReport:
    project_id: int | None = None
    project_title: str = ""
    rows: list[StageReviewRow] = field(default_factory=list)
    total_scenes: int = 0
    with_beat_plan: int = 0
    with_blocking_plan: int = 0
    written: int = 0
    total_blocks: int = 0
    dialogue_heavy: int = 0
    missing_stage_action: int = 0
    with_entrance_exit_warnings: int = 0
    with_cue_warnings: int = 0
    with_blocking_warnings: int = 0
    with_continuity_warnings: int = 0
    timeline_linked: int = 0
    with_psyke_links: int = 0
    with_export_warnings: int = 0
    needs_work: int = 0
    export_ready: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id, "project_title": self.project_title,
            "rows": [r.to_dict() for r in self.rows],
            "total_scenes": self.total_scenes, "with_beat_plan": self.with_beat_plan,
            "with_blocking_plan": self.with_blocking_plan, "written": self.written,
            "total_blocks": self.total_blocks, "dialogue_heavy": self.dialogue_heavy,
            "missing_stage_action": self.missing_stage_action,
            "with_entrance_exit_warnings": self.with_entrance_exit_warnings,
            "with_cue_warnings": self.with_cue_warnings,
            "with_blocking_warnings": self.with_blocking_warnings,
            "with_continuity_warnings": self.with_continuity_warnings,
            "timeline_linked": self.timeline_linked,
            "with_psyke_links": self.with_psyke_links,
            "with_export_warnings": self.with_export_warnings,
            "needs_work": self.needs_work, "export_ready": self.export_ready,
        }

    def filtered_rows(self, filter_key: str) -> list[StageReviewRow]:
        f = filter_key or "All"
        if f == "Missing Stage Beat Plan":
            return [r for r in self.rows if r.beat_plan_status == ST_MISSING]
        if f == "Missing Blocking / Cue Plan":
            return [r for r in self.rows if r.blocking_plan_status == ST_MISSING]
        if f == "Missing Body":
            return [r for r in self.rows if r.body_status == ST_MISSING]
        if f == "Dialogue Heavy":
            return [r for r in self.rows if r.dialogue_status == ST_WARNING]
        if f == "Missing Stage Action":
            return [r for r in self.rows if r.stage_action_status == ST_WARNING]
        if f == "Entrance/Exit Warning":
            return [r for r in self.rows if r.entrance_exit_status == ST_WARNING]
        if f == "Cue Warning":
            return [r for r in self.rows if r.cue_status == ST_WARNING]
        if f == "Blocking Warning":
            return [r for r in self.rows if r.blocking_status == ST_WARNING]
        if f == "Continuity Risk":
            return [r for r in self.rows if r.continuity_status != ST_OK]
        if f == "Not Linked to Timeline":
            return [r for r in self.rows if r.timeline_status != ST_OK]
        if f == "Export Warning":
            return [r for r in self.rows if r.export_status == ST_WARNING]
        if f == "Needs Reflection":
            return [r for r in self.rows
                    if r.overall_status in (ST_NEEDS_WORK, ST_ERROR)]
        return list(self.rows)

    def to_markdown(self) -> str:
        """Copy-friendly Markdown. Never includes provider settings / API keys."""
        lines = [f"# Stage Script Review — {self.project_title or 'Untitled'}", ""]
        lines.append(
            f"- Scenes: **{self.total_scenes}**  ·  Written: **{self.written}**  ·  "
            f"Stage blocks: **{self.total_blocks}**")
        lines.append(
            f"- Planned: beat {self.with_beat_plan}/{self.total_scenes}, "
            f"blocking/cue {self.with_blocking_plan}/{self.total_scenes}  ·  "
            f"Dialogue-heavy: {self.dialogue_heavy}  ·  Missing stage action: "
            f"{self.missing_stage_action}")
        lines.append(
            f"- Cue warnings: {self.with_cue_warnings}  ·  Blocking: "
            f"{self.with_blocking_warnings}  ·  Continuity risks: "
            f"{self.with_continuity_warnings}  ·  Export warnings: "
            f"{self.with_export_warnings}")
        lines.append(
            f"- Timeline-linked: {self.timeline_linked}/{self.total_scenes}  ·  "
            f"Export ready: **{'Yes' if self.export_ready else 'No'}**")
        lines.append("")
        lines.append("| # | Scene | Beat Plan | Blocking/Cues | Body | Dialogue | "
                     "Stage Action | Entrances/Exits | Cues | Continuity | Timeline "
                     "| PSYKE/Notes | Next Action |")
        lines.append("|---|-------|-----------|---------------|------|----------|"
                     "--------------|-----------------|------|-----------|----------|"
                     "------------|-------------|")
        for r in self.rows:
            lines.append(
                f"| {r.number or '-'} | {r.title or 'Untitled'} | {r.beat_plan_status}"
                f" | {r.blocking_plan_status} | {r.body_status} | {r.dialogue_status}"
                f" | {r.stage_action_status} | {r.entrance_exit_status} | "
                f"{r.cue_status} | {r.continuity_status} | {r.timeline_status} | "
                f"{r.psyke_notes_status} | {r.next_action} |")
        return "\n".join(lines)


# ===========================================================================
# Builder (read-only)
# ===========================================================================


def _rewrite_candidate_scene_ids(db, project_id: int) -> set[int]:
    out: set[int] = set()
    try:
        notes = db.get_all_notes(project_id)
    except Exception:
        return out
    for note in notes:
        if "rewrite-candidate" in (getattr(note, "tags", "") or ""):
            try:
                for sid in db.get_note_scene_links(getattr(note, "id", note)):
                    out.add(sid)
            except Exception:
                continue
    return out


def _scene_speakers(db, scene_id: int) -> set[str]:
    try:
        from logosforge import stage_script_blocks as ssb
        return set(ssb.character_cues(ssb.load_scene_script(db, scene_id)))
    except Exception:
        return set()


def _scene_has_notes(db, scene_id: int) -> bool:
    try:
        return bool(db.get_scene_note_links(scene_id))
    except Exception:
        return False


def _worse(a: str, b: str) -> str:
    return a if _SEV_RANK.get(a, 0) >= _SEV_RANK.get(b, 0) else b


def _next_action(row: StageReviewRow) -> tuple[str, str]:
    if row.body_status == ST_MISSING:
        if row.beat_plan_status == ST_MISSING:
            return ("Add Stage Beat Plan", ST_NEEDS_WORK)
        if row.blocking_plan_status == ST_MISSING:
            return ("Add Blocking / Cue Plan", ST_NEEDS_WORK)
        return ("Write Scene", ST_NEEDS_WORK)
    if row.stage_action_status == ST_WARNING:
        return ("Add stage directions", ST_NEEDS_WORK)
    if _SEV_RANK.get(row.health_severity, 0) >= _SEV_RANK[SEV_HIGH] \
            or _SEV_RANK.get(row.continuity_severity, 0) >= _SEV_RANK[SEV_HIGH]:
        return ("Review scene", ST_NEEDS_WORK)
    if row.entrance_exit_status == ST_WARNING:
        return ("Clarify entrance/exit", ST_WARNING)
    if row.cue_status == ST_WARNING:
        return ("Clarify cue", ST_WARNING)
    if row.continuity_status != ST_OK or row.blocking_status == ST_WARNING:
        return ("Check continuity", ST_WARNING)
    if row.dialogue_status == ST_WARNING:
        return ("Reduce dialogue", ST_WARNING)
    if row.beat_plan_status == ST_MISSING:
        return ("Add Stage Beat Plan", ST_WARNING)
    if row.blocking_plan_status == ST_MISSING:
        return ("Add Blocking / Cue Plan", ST_WARNING)
    if row.timeline_status == ST_MISSING:
        return ("Link to Timeline", ST_WARNING)
    return ("Ready for export", ST_OK)


def build_stage_script_review(db, project_id: int) -> StageScriptReviewReport:
    """Build the project-level Stage Script review. Deterministic, read-only."""
    report = StageScriptReviewReport(project_id=project_id)
    project = db.get_project_by_id(project_id)
    report.project_title = getattr(project, "title", "") if project else ""

    from logosforge import stage_script_diagnostics as ssd
    chain = []
    cont_sev: dict[int, str] = {}
    cont_blocking: dict[int, str] = {}
    cont_char: dict[int, str] = {}
    cont_cue: dict[int, str] = {}
    timeline_has_any = False
    try:
        from logosforge.stage_script_continuity import (
            build_stage_script_continuity_report,
        )
        cont = build_stage_script_continuity_report(db, project_id)
        chain = cont.scene_chain
        for f in cont.all_findings():
            sev = _MAP_SEV.get(f.severity, SEV_INFO)
            for sid in f.scene_ids:
                cont_sev[sid] = _worse(cont_sev.get(sid, SEV_INFO), sev)
        for f in cont.blocking_continuity:
            sev = _MAP_SEV.get(f.severity, SEV_INFO)
            for sid in f.scene_ids:
                cont_blocking[sid] = _worse(cont_blocking.get(sid, SEV_INFO), sev)
        for f in cont.character_continuity:
            sev = _MAP_SEV.get(f.severity, SEV_INFO)
            for sid in f.scene_ids:
                cont_char[sid] = _worse(cont_char.get(sid, SEV_INFO), sev)
        for f in cont.cue_continuity:
            sev = _MAP_SEV.get(f.severity, SEV_INFO)
            for sid in f.scene_ids:
                cont_cue[sid] = _worse(cont_cue.get(sid, SEV_INFO), sev)
        timeline_has_any = any(e.timeline_linked for e in chain)
    except Exception:
        chain = []

    try:
        from logosforge.screenplay_diagnostics import _psyke_character_map
        psyke_map = _psyke_character_map(db, project_id)
    except Exception:
        psyke_map = {}
    candidates = _rewrite_candidate_scene_ids(db, project_id)

    for e in chain:
        sid = e.scene_id
        row = StageReviewRow(
            scene_id=sid, number=e.number, title=e.title,
            summary_present=bool(e.purpose), block_count=e.block_count,
            beat_plan_status=ST_OK if e.has_beat_plan else ST_MISSING,
            blocking_plan_status=ST_OK if e.has_blocking_plan else ST_MISSING,
            body_status=ST_OK if e.has_body else ST_MISSING)

        if e.has_body:
            try:
                diag = ssd.analyze_scene_by_id(db, project_id, sid)
            except Exception:
                diag = None
            if diag is not None:
                row.dialogue_stage_ratio = diag.dialogue_stage_ratio
                ids = {i.id for i in diag.issues}
                row.dialogue_status = (ST_WARNING if any(
                    i.startswith(("dialogue_heavy", "long_monologue")) for i in ids)
                    else ST_OK)
                row.stage_action_status = (ST_WARNING if (
                    "no_stage_direction" in ids or "no_visible_action" in ids
                    or "too_many_dialogue" in ids) else ST_OK)
                row.cue_status = (ST_WARNING if any(
                    i.startswith(("empty_cue", "vague_cue")) for i in ids) else ST_OK)
                row.entrance_exit_status = (ST_WARNING if any(
                    i.startswith(("entrance_no_name", "exit_no_name")) for i in ids)
                    else ST_OK)
                warn_issues = [i for i in diag.issues
                               if _SEV_RANK.get(_MAP_SEV.get(i.severity, SEV_INFO), 0)
                               >= _SEV_RANK[SEV_WARNING]]
                if warn_issues:
                    row.health_severity = max(
                        (_MAP_SEV.get(i.severity, SEV_INFO) for i in warn_issues),
                        key=lambda s: _SEV_RANK.get(s, 0))
            # Fold cross-scene character/cue continuity into the columns.
            if cont_char.get(sid) and _SEV_RANK.get(cont_char[sid], 0) >= _SEV_RANK[SEV_WARNING]:
                row.entrance_exit_status = ST_WARNING
            if cont_cue.get(sid) and _SEV_RANK.get(cont_cue[sid], 0) >= _SEV_RANK[SEV_WARNING]:
                row.cue_status = ST_WARNING
            row.export_status = (ST_WARNING if (row.stage_action_status == ST_WARNING
                                 or row.cue_status == ST_WARNING) else ST_OK)
        else:
            row.dialogue_status = row.stage_action_status = ST_NOT_CHECKED
            row.entrance_exit_status = row.cue_status = ST_NOT_CHECKED
            row.export_status = ST_NOT_CHECKED

        bsev = cont_blocking.get(sid)
        if bsev and _SEV_RANK.get(bsev, 0) >= _SEV_RANK[SEV_WARNING]:
            row.blocking_status = ST_WARNING
        csev = cont_sev.get(sid)
        if csev and _SEV_RANK.get(csev, 0) >= _SEV_RANK[SEV_WARNING]:
            row.continuity_severity = csev
            row.continuity_status = ST_WARNING

        row.timeline_status = ST_OK if e.timeline_linked else (
            ST_MISSING if timeline_has_any else ST_NOT_CHECKED)

        if psyke_map:
            speakers = _scene_speakers(db, sid) if e.has_body else set()
            if not speakers:
                row.psyke_notes_status = (ST_OK if _scene_has_notes(db, sid)
                                          else ST_NOT_CHECKED)
            elif any(s not in psyke_map for s in speakers):
                row.psyke_notes_status = ST_WARNING
            else:
                row.psyke_notes_status = ST_OK
        elif _scene_has_notes(db, sid):
            row.psyke_notes_status = ST_OK
        else:
            row.psyke_notes_status = ST_NOT_CHECKED

        row.has_rewrite_candidate = sid in candidates
        row.next_action, row.overall_status = _next_action(row)
        report.rows.append(row)

    rows = report.rows
    report.total_scenes = len(rows)
    report.with_beat_plan = sum(1 for r in rows if r.beat_plan_status == ST_OK)
    report.with_blocking_plan = sum(1 for r in rows if r.blocking_plan_status == ST_OK)
    report.written = sum(1 for r in rows if r.body_status == ST_OK)
    report.total_blocks = sum(r.block_count for r in rows)
    report.dialogue_heavy = sum(1 for r in rows if r.dialogue_status == ST_WARNING)
    report.missing_stage_action = sum(
        1 for r in rows if r.stage_action_status == ST_WARNING)
    report.with_entrance_exit_warnings = sum(
        1 for r in rows if r.entrance_exit_status == ST_WARNING)
    report.with_cue_warnings = sum(1 for r in rows if r.cue_status == ST_WARNING)
    report.with_blocking_warnings = sum(1 for r in rows if r.blocking_status == ST_WARNING)
    report.with_continuity_warnings = sum(
        1 for r in rows if r.continuity_status != ST_OK)
    report.timeline_linked = sum(1 for r in rows if r.timeline_status == ST_OK)
    report.with_psyke_links = sum(1 for r in rows if r.psyke_notes_status == ST_OK)
    report.with_export_warnings = sum(1 for r in rows if r.export_status == ST_WARNING)
    report.needs_work = sum(1 for r in rows
                            if r.overall_status in (ST_NEEDS_WORK, ST_ERROR))
    report.export_ready = report.written > 0 and report.with_export_warnings == 0
    return report
