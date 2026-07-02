"""Graphic Novel Review Dashboard — project-level status aggregation (Phase 7).

A deterministic, read-only roll-up of everything the earlier Graphic Novel phases
compute, into one place: per-scene status (page breakdown / panel plan / page-panel
body / health / visual flow / continuity / Timeline / PSYKE-Notes / export) in
canonical order, project summary metrics, and a recommended next action per scene.
Reporting only — it never rewrites, applies, or creates data.

It consolidates (never re-implements):
* canonical chain + visual-flow + continuity + Timeline — Phase 6
  ``graphic_novel_continuity``,
* per-scene page/panel health — Phase 3 ``graphic_novel_diagnostics``,
* page breakdown / panel plan presence — Phase 2 ``graphic_novel_pipeline``,
* rewrite candidates — Phase 5 scene-linked Notes (tag ``rewrite-candidate``).

This module is the model behind ``ui/graphic_novel_review_view`` and the
``gn_review_dashboard`` Logos action. No Qt, no LLM, no API keys. Markdown export
excludes all provider settings, and there is no image-generation surface anywhere.
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

# Map Phase 3 / Phase 6 severities (info/watch/weak/critical) onto review severity.
_MAP_SEV = {"info": SEV_INFO, "watch": SEV_WARNING, "weak": SEV_HIGH,
            "critical": SEV_CRITICAL}

# Filters the UI exposes (key -> predicate over a GNReviewRow).
FILTERS: tuple[str, ...] = (
    "All", "Missing Page Breakdown", "Missing Panel Plan", "Missing Body",
    "Empty Panels", "Missing Visual Description", "Dialogue Heavy",
    "Caption Heavy", "Continuity Risk", "Not Linked to Timeline",
    "Export Warning", "Needs Reflection",
)


@dataclass
class GNReviewRow:
    scene_id: int
    number: str = ""
    title: str = ""
    summary_present: bool = False
    breakdown_status: str = ST_MISSING
    plan_status: str = ST_MISSING
    body_status: str = ST_MISSING
    page_count: int = 0
    panel_count: int = 0
    empty_page_count: int = 0
    empty_panel_count: int = 0
    missing_visual_count: int = 0
    dialogue_heavy_count: int = 0
    caption_heavy_count: int = 0
    dialogue_caption_status: str = ST_OK
    visuals_status: str = ST_OK
    flow_status: str = ST_OK
    flow_severity: str = SEV_INFO
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
            "breakdown_status": self.breakdown_status,
            "plan_status": self.plan_status, "body_status": self.body_status,
            "page_count": self.page_count, "panel_count": self.panel_count,
            "empty_page_count": self.empty_page_count,
            "empty_panel_count": self.empty_panel_count,
            "missing_visual_count": self.missing_visual_count,
            "dialogue_heavy_count": self.dialogue_heavy_count,
            "caption_heavy_count": self.caption_heavy_count,
            "dialogue_caption_status": self.dialogue_caption_status,
            "visuals_status": self.visuals_status, "flow_status": self.flow_status,
            "flow_severity": self.flow_severity,
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
class GraphicNovelReviewReport:
    project_id: int | None = None
    project_title: str = ""
    rows: list[GNReviewRow] = field(default_factory=list)
    # Summary metrics.
    total_scenes: int = 0
    with_breakdown: int = 0
    with_plan: int = 0
    scripted: int = 0
    total_pages: int = 0
    total_panels: int = 0
    empty_pages: int = 0
    empty_panels: int = 0
    panels_missing_visual: int = 0
    dialogue_heavy_panels: int = 0
    caption_heavy_panels: int = 0
    with_flow_warnings: int = 0
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
            "total_scenes": self.total_scenes, "with_breakdown": self.with_breakdown,
            "with_plan": self.with_plan, "scripted": self.scripted,
            "total_pages": self.total_pages, "total_panels": self.total_panels,
            "empty_pages": self.empty_pages, "empty_panels": self.empty_panels,
            "panels_missing_visual": self.panels_missing_visual,
            "dialogue_heavy_panels": self.dialogue_heavy_panels,
            "caption_heavy_panels": self.caption_heavy_panels,
            "with_flow_warnings": self.with_flow_warnings,
            "with_continuity_warnings": self.with_continuity_warnings,
            "timeline_linked": self.timeline_linked,
            "with_psyke_links": self.with_psyke_links,
            "with_export_warnings": self.with_export_warnings,
            "needs_work": self.needs_work, "export_ready": self.export_ready,
        }

    def filtered_rows(self, filter_key: str) -> list[GNReviewRow]:
        f = filter_key or "All"
        if f == "Missing Page Breakdown":
            return [r for r in self.rows if r.breakdown_status == ST_MISSING]
        if f == "Missing Panel Plan":
            return [r for r in self.rows if r.plan_status == ST_MISSING]
        if f == "Missing Body":
            return [r for r in self.rows if r.body_status == ST_MISSING]
        if f == "Empty Panels":
            return [r for r in self.rows if r.empty_panel_count > 0]
        if f == "Missing Visual Description":
            return [r for r in self.rows if r.missing_visual_count > 0]
        if f == "Dialogue Heavy":
            return [r for r in self.rows if r.dialogue_heavy_count > 0]
        if f == "Caption Heavy":
            return [r for r in self.rows if r.caption_heavy_count > 0]
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
        """Copy-friendly Markdown. Never includes provider settings / API keys, and
        contains no image-generation / render workflow content."""
        lines = [f"# Graphic Novel Review — {self.project_title or 'Untitled'}", ""]
        lines.append(
            f"- Scenes: **{self.total_scenes}**  ·  Pages: **{self.total_pages}**  ·  "
            f"Panels: **{self.total_panels}**  ·  Scripted: **{self.scripted}**")
        lines.append(
            f"- Planned: breakdown {self.with_breakdown}/{self.total_scenes}, plan "
            f"{self.with_plan}/{self.total_scenes}  ·  Needs visuals: "
            f"{self.panels_missing_visual} panel(s)  ·  Empty panels: {self.empty_panels}")
        lines.append(
            f"- Flow warnings: {self.with_flow_warnings}  ·  Continuity risks: "
            f"{self.with_continuity_warnings}  ·  Export warnings: "
            f"{self.with_export_warnings}")
        lines.append(
            f"- Timeline-linked: {self.timeline_linked}/{self.total_scenes}  ·  "
            f"Export ready: **{'Yes' if self.export_ready else 'No'}**")
        lines.append("")
        lines.append("| # | Scene | Breakdown | Panel Plan | Pages | Panels | Visuals "
                     "| Dialogue/Captions | Flow | Continuity | Timeline | "
                     "PSYKE/Notes | Next Action |")
        lines.append("|---|-------|-----------|-----------|-------|--------|---------|"
                     "-------------------|------|-----------|----------|------------|"
                     "-------------|")
        for r in self.rows:
            lines.append(
                f"| {r.number or '-'} | {r.title or 'Untitled'} | {r.breakdown_status}"
                f" | {r.plan_status} | {r.page_count} | {r.panel_count} | "
                f"{r.visuals_status} | {r.dialogue_caption_status} | {r.flow_status} "
                f"| {r.continuity_status} | {r.timeline_status} | "
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


def _scene_has_notes(db, scene_id: int) -> bool:
    try:
        return bool(db.get_scene_note_links(scene_id))
    except Exception:
        return False


def _scene_speakers(db, scene_id: int) -> set[str]:
    """Uppercased dialogue speakers in a GN scene (read-only)."""
    try:
        from logosforge import graphic_novel_blocks as gnb
        from logosforge.graphic_novel_continuity import _speakers
        return _speakers(gnb.load_scene_script(db, scene_id))
    except Exception:
        return set()


def _next_action(row: GNReviewRow) -> tuple[str, str]:
    """Return (next_action, overall_status) for a row (worst-first)."""
    if row.body_status == ST_MISSING:
        if row.breakdown_status == ST_MISSING:
            return ("Add page breakdown", ST_NEEDS_WORK)
        if row.plan_status == ST_MISSING:
            return ("Generate panel plan", ST_NEEDS_WORK)
        return ("Script panels", ST_NEEDS_WORK)
    if row.missing_visual_count > 0:
        return ("Add visual descriptions", ST_NEEDS_WORK)
    if row.empty_panel_count > 0:
        return ("Fill empty panels", ST_NEEDS_WORK)
    if _SEV_RANK.get(row.flow_severity, 0) >= _SEV_RANK[SEV_HIGH] \
            or _SEV_RANK.get(row.continuity_severity, 0) >= _SEV_RANK[SEV_HIGH]:
        return ("Review scene", ST_NEEDS_WORK)
    if row.continuity_status != ST_OK:
        return ("Check continuity", ST_WARNING)
    if row.flow_status != ST_OK:
        return ("Clarify page flow", ST_WARNING)
    if row.dialogue_heavy_count > 0:
        return ("Reduce dialogue", ST_WARNING)
    if row.caption_heavy_count > 0:
        return ("Tighten captions", ST_WARNING)
    if row.breakdown_status == ST_MISSING:
        return ("Add page breakdown", ST_WARNING)
    if row.plan_status == ST_MISSING:
        return ("Generate panel plan", ST_WARNING)
    if row.timeline_status == ST_MISSING:
        return ("Link to Timeline", ST_WARNING)
    return ("Ready for export", ST_OK)


def build_graphic_novel_review(db, project_id: int) -> GraphicNovelReviewReport:
    """Build the project-level Graphic Novel review. Deterministic, read-only."""
    report = GraphicNovelReviewReport(project_id=project_id)
    project = db.get_project_by_id(project_id)
    report.project_title = getattr(project, "title", "") if project else ""

    # -- Phase 6 spine: canonical chain + visual-flow + continuity + Timeline --
    chain = []
    flow_sev_by_scene: dict[int, str] = {}
    cont_sev_by_scene: dict[int, str] = {}
    timeline_has_any = False
    try:
        from logosforge.graphic_novel_continuity import (
            build_graphic_novel_continuity_report,
        )
        cont = build_graphic_novel_continuity_report(db, project_id)
        chain = cont.scene_chain
        for f in cont.visual_flow:
            sev = _MAP_SEV.get(f.severity, SEV_INFO)
            for sid in f.scene_ids:
                if _SEV_RANK.get(sev, 0) >= _SEV_RANK.get(
                        flow_sev_by_scene.get(sid, SEV_INFO), 0):
                    flow_sev_by_scene[sid] = sev
        for f in (cont.character_continuity + cont.object_place_continuity
                  + cont.motif_echo + cont.setup_payoff):
            sev = _MAP_SEV.get(f.severity, SEV_INFO)
            for sid in f.scene_ids:
                if _SEV_RANK.get(sev, 0) >= _SEV_RANK.get(
                        cont_sev_by_scene.get(sid, SEV_INFO), 0):
                    cont_sev_by_scene[sid] = sev
        timeline_has_any = any(e.timeline_linked for e in chain)
    except Exception:
        chain = []

    candidates = _rewrite_candidate_scene_ids(db, project_id)
    try:
        from logosforge.screenplay_diagnostics import _psyke_character_map
        psyke_map = _psyke_character_map(db, project_id)
    except Exception:
        psyke_map = {}

    from logosforge import graphic_novel_diagnostics as gd

    for e in chain:
        sid = e.scene_id
        row = GNReviewRow(
            scene_id=sid, number=e.number, title=e.title,
            summary_present=bool(e.purpose),
            page_count=e.page_count, panel_count=e.panel_count,
            breakdown_status=ST_OK if e.has_breakdown else ST_MISSING,
            plan_status=ST_OK if e.has_plan else ST_MISSING,
            body_status=ST_OK if e.has_body else ST_MISSING)

        if e.has_body:
            try:
                diag = gd.analyze_scene_by_id(db, project_id, sid)
            except Exception:
                diag = None
            if diag is not None:
                row.empty_panel_count = diag.empty_panels
                row.missing_visual_count = diag.panels_without_visual
                row.dialogue_heavy_count = diag.dialogue_heavy_panels
                row.caption_heavy_count = diag.caption_heavy_panels
                row.empty_page_count = sum(
                    1 for i in diag.issues if i.id.startswith("empty_page_"))
            row.visuals_status = (ST_WARNING if row.missing_visual_count
                                  else ST_OK)
            row.dialogue_caption_status = (
                ST_WARNING if (row.dialogue_heavy_count or row.caption_heavy_count)
                else ST_OK)
            # Export readiness for this scene: body present and no empty/no-visual
            # panels (script-clarity only; nothing to do with image production).
            row.export_status = (ST_WARNING if (row.missing_visual_count
                                 or row.empty_panel_count or row.empty_page_count)
                                 else ST_OK)
        else:
            row.visuals_status = ST_NOT_CHECKED
            row.dialogue_caption_status = ST_NOT_CHECKED
            row.export_status = ST_NOT_CHECKED

        # Visual-flow severity (Phase 6).
        fsev = flow_sev_by_scene.get(sid)
        if fsev and _SEV_RANK.get(fsev, 0) >= _SEV_RANK[SEV_WARNING]:
            row.flow_severity = fsev
            row.flow_status = ST_WARNING
        # Continuity severity (Phase 6).
        csev = cont_sev_by_scene.get(sid)
        if csev and _SEV_RANK.get(csev, 0) >= _SEV_RANK[SEV_WARNING]:
            row.continuity_severity = csev
            row.continuity_status = ST_WARNING

        row.timeline_status = ST_OK if e.timeline_linked else (
            ST_MISSING if timeline_has_any else ST_NOT_CHECKED)

        # PSYKE / Notes status (per scene — only flag "missing" when a Story Bible
        # exists and this scene's speakers aren't all in it).
        if psyke_map:
            speakers = _scene_speakers(db, sid)
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

    # -- Summary metrics --
    rows = report.rows
    report.total_scenes = len(rows)
    report.with_breakdown = sum(1 for r in rows if r.breakdown_status == ST_OK)
    report.with_plan = sum(1 for r in rows if r.plan_status == ST_OK)
    report.scripted = sum(1 for r in rows if r.body_status == ST_OK)
    report.total_pages = sum(r.page_count for r in rows)
    report.total_panels = sum(r.panel_count for r in rows)
    report.empty_pages = sum(r.empty_page_count for r in rows)
    report.empty_panels = sum(r.empty_panel_count for r in rows)
    report.panels_missing_visual = sum(r.missing_visual_count for r in rows)
    report.dialogue_heavy_panels = sum(r.dialogue_heavy_count for r in rows)
    report.caption_heavy_panels = sum(r.caption_heavy_count for r in rows)
    report.with_flow_warnings = sum(1 for r in rows if r.flow_status != ST_OK)
    report.with_continuity_warnings = sum(
        1 for r in rows if r.continuity_status != ST_OK)
    report.timeline_linked = sum(1 for r in rows if r.timeline_status == ST_OK)
    report.with_psyke_links = sum(1 for r in rows if r.psyke_notes_status == ST_OK)
    report.with_export_warnings = sum(1 for r in rows if r.export_status == ST_WARNING)
    report.needs_work = sum(1 for r in rows
                            if r.overall_status in (ST_NEEDS_WORK, ST_ERROR))
    report.export_ready = report.scripted > 0 and report.with_export_warnings == 0
    return report
