"""Screenplay Review Dashboard — project-level status aggregation (Phase 8).

A deterministic, read-only roll-up of everything the earlier phases compute, into
one place: per-scene status (plan / body / health / continuity / Timeline / PSYKE
/ export) in canonical order, project summary metrics, and a recommended next
action per scene. Reporting only — it never rewrites, applies, or creates data.

It consolidates (never re-implements):
* canonical chain + continuity + Timeline/PSYKE — Phase 7 ``screenplay_continuity``,
* per-scene health — Phase 3 ``screenplay_diagnostics.analyze_project``,
* beat plans — Phase 2 ``screenplay_pipeline``,
* export readiness — Phase 4 ``screenplay_interchange``,
* rewrite candidates — Phase 6 scene-linked Notes (tag ``rewrite-candidate``).

No Qt, no LLM, no API keys. Markdown export excludes all provider settings.
"""

from __future__ import annotations

import re
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

# Map Phase 3 issue severities onto our review severity.
_HEALTH_SEV = {"info": SEV_INFO, "watch": SEV_WARNING, "weak": SEV_HIGH,
               "critical": SEV_CRITICAL}
# Map Phase 7 finding severities.
_CONT_SEV = {"info": SEV_INFO, "watch": SEV_WARNING, "weak": SEV_HIGH,
             "critical": SEV_CRITICAL}

# Filters the UI exposes (key -> predicate over a SceneReviewRow).
FILTERS: tuple[str, ...] = (
    "All", "Missing Beat Plan", "Missing Body", "Needs Work",
    "Continuity Risk", "Export Warning", "Not Linked to Timeline",
    "No PSYKE Links",
)


def _words(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


@dataclass
class SceneReviewRow:
    scene_id: int
    number: str = ""
    title: str = ""
    summary_present: bool = False
    beat_plan_status: str = ST_MISSING
    body_status: str = ST_MISSING
    word_count: int = 0
    block_count: int = 0
    scene_heading_status: str = ST_MISSING
    health_status: str = ST_NOT_CHECKED
    health_severity: str = SEV_INFO
    continuity_status: str = ST_OK
    continuity_severity: str = SEV_INFO
    reflection_status: str = ST_NOT_CHECKED
    timeline_status: str = ST_MISSING
    psyke_status: str = ST_NOT_CHECKED
    export_status: str = ST_OK
    has_rewrite_candidate: bool = False
    next_action: str = ""
    overall_status: str = ST_OK

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id, "number": self.number, "title": self.title,
            "summary_present": self.summary_present,
            "beat_plan_status": self.beat_plan_status,
            "body_status": self.body_status, "word_count": self.word_count,
            "block_count": self.block_count,
            "scene_heading_status": self.scene_heading_status,
            "health_status": self.health_status,
            "health_severity": self.health_severity,
            "continuity_status": self.continuity_status,
            "continuity_severity": self.continuity_severity,
            "reflection_status": self.reflection_status,
            "timeline_status": self.timeline_status,
            "psyke_status": self.psyke_status, "export_status": self.export_status,
            "has_rewrite_candidate": self.has_rewrite_candidate,
            "next_action": self.next_action, "overall_status": self.overall_status,
        }


@dataclass
class ScreenplayReviewReport:
    project_id: int | None = None
    project_title: str = ""
    rows: list[SceneReviewRow] = field(default_factory=list)
    # Summary metrics.
    total_scenes: int = 0
    written: int = 0
    planned: int = 0
    needs_work: int = 0
    with_health_warnings: int = 0
    with_continuity_warnings: int = 0
    with_export_warnings: int = 0
    timeline_linked: int = 0
    with_psyke_links: int = 0
    export_ready: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id, "project_title": self.project_title,
            "rows": [r.to_dict() for r in self.rows],
            "total_scenes": self.total_scenes, "written": self.written,
            "planned": self.planned, "needs_work": self.needs_work,
            "with_health_warnings": self.with_health_warnings,
            "with_continuity_warnings": self.with_continuity_warnings,
            "with_export_warnings": self.with_export_warnings,
            "timeline_linked": self.timeline_linked,
            "with_psyke_links": self.with_psyke_links,
            "export_ready": self.export_ready,
        }

    def filtered_rows(self, filter_key: str) -> list[SceneReviewRow]:
        f = filter_key or "All"
        if f == "Missing Beat Plan":
            return [r for r in self.rows if r.beat_plan_status == ST_MISSING]
        if f == "Missing Body":
            return [r for r in self.rows if r.body_status == ST_MISSING]
        if f == "Needs Work":
            return [r for r in self.rows
                    if r.overall_status in (ST_NEEDS_WORK, ST_ERROR)]
        if f == "Continuity Risk":
            return [r for r in self.rows if r.continuity_status != ST_OK]
        if f == "Export Warning":
            return [r for r in self.rows if r.export_status == ST_WARNING]
        if f == "Not Linked to Timeline":
            return [r for r in self.rows if r.timeline_status != ST_OK]
        if f == "No PSYKE Links":
            return [r for r in self.rows
                    if r.psyke_status in (ST_MISSING, ST_WARNING)]
        return list(self.rows)

    def to_markdown(self) -> str:
        """Copy-friendly Markdown. Never includes provider settings / API keys."""
        lines = [f"# Screenplay Review — {self.project_title or 'Untitled'}", ""]
        lines.append(
            f"- Total scenes: **{self.total_scenes}**  ·  Written: **{self.written}**"
            f"  ·  Planned: **{self.planned}**  ·  Needs work: **{self.needs_work}**")
        lines.append(
            f"- Health warnings: {self.with_health_warnings}  ·  Continuity risks: "
            f"{self.with_continuity_warnings}  ·  Export warnings: "
            f"{self.with_export_warnings}")
        lines.append(
            f"- Timeline-linked: {self.timeline_linked}/{self.total_scenes}  ·  "
            f"Export ready: **{'Yes' if self.export_ready else 'No'}**")
        lines.append("")
        lines.append("| # | Scene | Plan | Body | Health | Continuity | Timeline | "
                     "PSYKE | Export | Next Action |")
        lines.append("|---|-------|------|------|--------|-----------|----------|"
                     "-------|--------|-------------|")
        for r in self.rows:
            lines.append(
                f"| {r.number or '-'} | {r.title or 'Untitled'} | {r.beat_plan_status}"
                f" | {r.body_status} | {r.health_status} | {r.continuity_status} | "
                f"{r.timeline_status} | {r.psyke_status} | {r.export_status} | "
                f"{r.next_action} |")
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
        tags = (getattr(note, "tags", "") or "")
        if "rewrite-candidate" in tags or "continuity" in tags:
            try:
                for sid in db.get_note_scene_links(getattr(note, "id", note)):
                    out.add(sid)
            except Exception:
                continue
    return out


def _next_action(row: SceneReviewRow) -> tuple[str, str]:
    """Return (next_action, overall_status) for a row (worst-first)."""
    if row.body_status == ST_MISSING:
        return ("Write scene body", ST_NEEDS_WORK)
    if row.beat_plan_status == ST_MISSING:
        return ("Add beat plan", ST_WARNING)
    if row.scene_heading_status == ST_MISSING:
        return ("Add scene heading", ST_WARNING)
    if _SEV_RANK.get(row.health_severity, 0) >= _SEV_RANK[SEV_HIGH]:
        return ("Review scene", ST_NEEDS_WORK)
    if row.continuity_status != ST_OK:
        return ("Check continuity", ST_WARNING)
    if row.export_status == ST_WARNING:
        return ("Review formatting", ST_WARNING)
    if row.health_status == ST_WARNING:
        return ("Review dialogue/action", ST_WARNING)
    if row.timeline_status == ST_MISSING:
        return ("Link to timeline", ST_WARNING)
    return ("Ready for export", ST_OK)


def build_screenplay_review(db, project_id: int) -> ScreenplayReviewReport:
    """Build the project-level screenplay review. Deterministic, read-only."""
    report = ScreenplayReviewReport(project_id=project_id)
    project = db.get_project_by_id(project_id)
    report.project_title = getattr(project, "title", "") if project else ""

    # -- Phase 7 spine: canonical chain + continuity + timeline + PSYKE --
    chain = []
    continuity_by_scene: dict[int, str] = {}
    psyke_unlinked_names: set[str] = set()
    timeline_has_any = False
    try:
        from logosforge.screenplay_continuity import build_screenplay_continuity_report
        cont = build_screenplay_continuity_report(db, project_id)
        chain = cont.scene_chain
        for f in cont.causal_flow + cont.character_continuity:
            sev = _CONT_SEV.get(f.severity, SEV_INFO)
            for sid in f.scene_ids:
                if _SEV_RANK.get(sev, 0) >= _SEV_RANK.get(
                        continuity_by_scene.get(sid, SEV_INFO), 0):
                    continuity_by_scene[sid] = sev
        for f in cont.psyke_consistency:
            m = re.match(r"(.+?) not in Story Bible", f.title)
            if m:
                psyke_unlinked_names.add(m.group(1).strip().upper())
        timeline_has_any = any(e.timeline_linked for e in chain)
    except Exception:
        chain = []

    # -- Phase 3 health per scene --
    health_by_scene: dict[int, Any] = {}
    try:
        from logosforge.screenplay_diagnostics import analyze_project
        for r in analyze_project(db, project_id):
            if r.scene_id is not None:
                health_by_scene[r.scene_id] = r
    except Exception:
        pass

    # -- PSYKE in use? (only flag "missing" when a Story Bible exists) --
    try:
        from logosforge.screenplay_diagnostics import _psyke_character_map
        psyke_map = _psyke_character_map(db, project_id)
    except Exception:
        psyke_map = {}

    # -- Project export readiness (Phase 4) --
    try:
        from logosforge.screenplay_interchange import validate_fountain_export_readiness
        report.export_ready = validate_fountain_export_readiness(db, project_id).is_ready
    except Exception:
        report.export_ready = False

    candidates = _rewrite_candidate_scene_ids(db, project_id)

    scenes_by_id = {s.id: s for s in db.get_all_scenes(project_id)}
    # Use the canonical chain order; fall back to scene id order only if chain empty.
    order = [e.scene_id for e in chain] or list(scenes_by_id.keys())

    for entry_idx, sid in enumerate(order):
        scene = scenes_by_id.get(sid)
        if scene is None:
            continue
        e = chain[entry_idx] if entry_idx < len(chain) and chain[entry_idx].scene_id == sid else None
        content = getattr(scene, "content", "") or ""
        row = SceneReviewRow(
            scene_id=sid,
            number=(e.number if e else ""),
            title=(getattr(scene, "title", "") or "").strip(),
            summary_present=bool((getattr(scene, "summary", "") or "").strip()),
            word_count=_words(content),
        )
        row.body_status = ST_OK if content.strip() else ST_MISSING
        has_plan = e.has_beat_plan if e else False
        if not has_plan:
            try:
                from logosforge.screenplay_pipeline import has_beat_plan
                has_plan = has_beat_plan(db, project_id, sid)
            except Exception:
                has_plan = False
        row.beat_plan_status = ST_OK if has_plan else ST_MISSING

        # Parse blocks once for heading / export / PSYKE derivation (export uses a
        # heading *block* or a slugline — a scene title does NOT count as a heading).
        eblocks = []
        if content.strip():
            try:
                from logosforge import screenplay_blocks as _sb
                eblocks = _sb.parse_screenplay_text(content)
            except Exception:
                eblocks = []
        slug = (getattr(scene, "slugline", "") or "").strip()
        has_heading = bool(slug) or any(
            b.element_type == "scene_heading" for b in eblocks)

        health = health_by_scene.get(sid)
        if health is not None:
            row.block_count = health.block_count
            issues = [i for i in health.issues
                      if _SEV_RANK.get(_HEALTH_SEV.get(i.severity, SEV_INFO), 0)
                      >= _SEV_RANK[SEV_WARNING]]
            if issues:
                row.health_severity = max(
                    (_HEALTH_SEV.get(i.severity, SEV_INFO) for i in issues),
                    key=lambda s: _SEV_RANK.get(s, 0))
                row.health_status = (ST_NEEDS_WORK
                                     if _SEV_RANK.get(row.health_severity, 0)
                                     >= _SEV_RANK[SEV_HIGH] else ST_WARNING)
            else:
                row.health_status = ST_OK if content.strip() else ST_NOT_CHECKED

        if content.strip():
            row.scene_heading_status = ST_OK if has_heading else ST_MISSING
            # Export readiness for this scene (Phase 4 block check; slugline
            # satisfies the heading requirement).
            try:
                from logosforge.screenplay_interchange import validate_export_blocks
                ewarn = validate_export_blocks(eblocks).warnings
                if slug:
                    ewarn = [w for w in ewarn if "scene heading" not in w.lower()]
                row.export_status = ST_WARNING if ewarn else ST_OK
            except Exception:
                row.export_status = ST_OK
        else:
            row.health_status = ST_NOT_CHECKED
            row.scene_heading_status = ST_NOT_CHECKED
            row.export_status = ST_NOT_CHECKED

        # Continuity severity for this scene (Phase 7).
        csev = continuity_by_scene.get(sid)
        if csev and _SEV_RANK.get(csev, 0) >= _SEV_RANK[SEV_WARNING]:
            row.continuity_severity = csev
            row.continuity_status = ST_WARNING
        else:
            row.continuity_status = ST_OK

        # Timeline link.
        row.timeline_status = ST_OK if (e and e.timeline_linked) else (
            ST_MISSING if timeline_has_any else ST_NOT_CHECKED)

        # PSYKE link status (only meaningful when a Story Bible exists).
        if psyke_map:
            cues = set()
            try:
                from logosforge import screenplay_blocks as sb
                cues = set(sb.character_cues(eblocks))
            except Exception:
                cues = set()
            if not cues:
                row.psyke_status = ST_NOT_CHECKED
            elif any(c not in psyke_map for c in cues):
                row.psyke_status = ST_WARNING
            else:
                row.psyke_status = ST_OK
        else:
            row.psyke_status = ST_NOT_CHECKED

        row.reflection_status = ST_NOT_CHECKED   # reflections are on-demand
        row.has_rewrite_candidate = sid in candidates

        row.next_action, row.overall_status = _next_action(row)
        report.rows.append(row)

    # -- Summary metrics --
    report.total_scenes = len(report.rows)
    report.written = sum(1 for r in report.rows if r.body_status == ST_OK)
    report.planned = sum(1 for r in report.rows if r.beat_plan_status == ST_OK)
    report.needs_work = sum(1 for r in report.rows
                            if r.overall_status in (ST_NEEDS_WORK, ST_ERROR))
    report.with_health_warnings = sum(
        1 for r in report.rows if r.health_status in (ST_WARNING, ST_NEEDS_WORK))
    report.with_continuity_warnings = sum(
        1 for r in report.rows if r.continuity_status != ST_OK)
    report.with_export_warnings = sum(
        1 for r in report.rows if r.export_status == ST_WARNING)
    report.timeline_linked = sum(1 for r in report.rows if r.timeline_status == ST_OK)
    report.with_psyke_links = sum(1 for r in report.rows if r.psyke_status == ST_OK)
    return report
