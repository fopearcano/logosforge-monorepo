"""Series Review Dashboard — project-level status aggregation (Phase 7).

A deterministic, read-only roll-up of everything the earlier Series phases compute,
organized as Season / Arc -> Episode -> Scene: per-scene status (Episode beat plan /
Season plan / body / scene function / A/B/C / act breaks / cold open-tag /
continuity / Timeline / PSYKE-Notes / export) in canonical order, per-episode and
per-season summaries, project metrics, and a recommended next action per row.
Reporting only — it never rewrites, applies, or creates data.

It consolidates (never re-implements):
* canonical chain + cross-episode continuity — Phase 6 ``series_continuity``,
* per-scene health — Phase 3 ``series_diagnostics``,
* Season/Arc + Episode beat plans — Phase 2 ``series_pipeline`` (via the chain),
* rewrite candidates — Phase 5 scene-linked Notes (tag ``rewrite-candidate``).

This module is the model behind ``ui/series_review_view`` and the
``series_review_dashboard`` Logos action. No Qt, no LLM, no API keys. Markdown
export excludes all provider settings. No new Season/Episode storage.
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
    "All", "Missing Season / Arc Plan", "Missing Episode Beat Plan",
    "Missing Scene Body", "A/B/C Story Warning", "Weak Act Break",
    "Cold Open / Tag Warning", "Continuity Risk", "Not Linked to Timeline",
    "Export Warning", "Needs Reflection", "Needs Rewrite",
)


def _worse(a: str, b: str) -> str:
    return a if _SEV_RANK.get(a, 0) >= _SEV_RANK.get(b, 0) else b


# ===========================================================================
# Row models
# ===========================================================================


@dataclass
class SeasonReviewRow:
    act: str
    number: str = ""
    title: str = ""
    season_plan_status: str = ST_MISSING
    episode_count: int = 0
    written_episode_count: int = 0
    abc_status: str = ST_OK
    setup_payoff_status: str = ST_OK
    continuity_severity: str = SEV_INFO
    next_action: str = ""
    overall_status: str = ST_OK

    def to_dict(self) -> dict[str, Any]:
        return {"act": self.act, "number": self.number, "title": self.title,
                "season_plan_status": self.season_plan_status,
                "episode_count": self.episode_count,
                "written_episode_count": self.written_episode_count,
                "abc_status": self.abc_status,
                "setup_payoff_status": self.setup_payoff_status,
                "continuity_severity": self.continuity_severity,
                "next_action": self.next_action, "overall_status": self.overall_status}


@dataclass
class EpisodeReviewRow:
    chapter: str
    episode_label: str = ""
    act: str = ""
    number: str = ""
    title: str = ""
    summary_present: bool = False
    episode_plan_status: str = ST_MISSING
    season_plan_status: str = ST_MISSING
    scene_count: int = 0
    written_scene_count: int = 0
    abc_status: str = ST_OK
    act_break_status: str = ST_OK
    cold_open_tag_status: str = ST_OK
    continuity_status: str = ST_OK
    continuity_severity: str = SEV_INFO
    timeline_status: str = ST_MISSING
    psyke_notes_status: str = ST_NOT_CHECKED
    export_status: str = ST_OK
    next_action: str = ""
    overall_status: str = ST_OK

    def to_dict(self) -> dict[str, Any]:
        return {"chapter": self.chapter, "episode_label": self.episode_label,
                "act": self.act, "number": self.number, "title": self.title,
                "summary_present": self.summary_present,
                "episode_plan_status": self.episode_plan_status,
                "season_plan_status": self.season_plan_status,
                "scene_count": self.scene_count,
                "written_scene_count": self.written_scene_count,
                "abc_status": self.abc_status, "act_break_status": self.act_break_status,
                "cold_open_tag_status": self.cold_open_tag_status,
                "continuity_status": self.continuity_status,
                "continuity_severity": self.continuity_severity,
                "timeline_status": self.timeline_status,
                "psyke_notes_status": self.psyke_notes_status,
                "export_status": self.export_status, "next_action": self.next_action,
                "overall_status": self.overall_status}


@dataclass
class SceneReviewRow:
    scene_id: int
    number: str = ""
    title: str = ""
    episode: str = ""
    episode_label: str = ""
    act: str = ""
    season_plan_status: str = ST_MISSING
    episode_plan_status: str = ST_MISSING
    body_status: str = ST_MISSING
    block_count: int = 0
    dialogue_action_ratio: float = 0.0
    scene_function_status: str = ST_OK
    abc_status: str = ST_OK
    act_break_status: str = ST_OK
    cold_open_tag_status: str = ST_OK
    continuity_status: str = ST_OK
    continuity_severity: str = SEV_INFO
    timeline_status: str = ST_MISSING
    psyke_notes_status: str = ST_NOT_CHECKED
    export_status: str = ST_OK
    reflection_status: str = ST_NOT_CHECKED
    has_rewrite_candidate: bool = False
    next_action: str = ""
    overall_status: str = ST_OK

    def to_dict(self) -> dict[str, Any]:
        return {"scene_id": self.scene_id, "number": self.number, "title": self.title,
                "episode": self.episode, "episode_label": self.episode_label,
                "act": self.act, "season_plan_status": self.season_plan_status,
                "episode_plan_status": self.episode_plan_status,
                "body_status": self.body_status, "block_count": self.block_count,
                "dialogue_action_ratio": self.dialogue_action_ratio,
                "scene_function_status": self.scene_function_status,
                "abc_status": self.abc_status, "act_break_status": self.act_break_status,
                "cold_open_tag_status": self.cold_open_tag_status,
                "continuity_status": self.continuity_status,
                "continuity_severity": self.continuity_severity,
                "timeline_status": self.timeline_status,
                "psyke_notes_status": self.psyke_notes_status,
                "export_status": self.export_status,
                "reflection_status": self.reflection_status,
                "has_rewrite_candidate": self.has_rewrite_candidate,
                "next_action": self.next_action, "overall_status": self.overall_status}


@dataclass
class SeriesReviewReport:
    project_id: int | None = None
    project_title: str = ""
    seasons: list[SeasonReviewRow] = field(default_factory=list)
    episodes: list[EpisodeReviewRow] = field(default_factory=list)
    scenes: list[SceneReviewRow] = field(default_factory=list)
    # Summary metrics.
    total_seasons: int = 0
    total_episodes: int = 0
    total_scenes: int = 0
    episodes_with_season_plan: int = 0
    episodes_with_beat_plan: int = 0
    written_scenes: int = 0
    unwritten_scenes: int = 0
    total_blocks: int = 0
    dialogue_heavy: int = 0
    missing_scene_heading: int = 0
    episodes_with_abc_warning: int = 0
    episodes_with_act_break_warning: int = 0
    episodes_with_cold_open_tag_warning: int = 0
    episodes_with_continuity_warning: int = 0
    scenes_timeline_linked: int = 0
    scenes_with_psyke: int = 0
    scenes_with_notes: int = 0
    with_export_warnings: int = 0
    needs_work: int = 0
    export_ready: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id, "project_title": self.project_title,
            "seasons": [s.to_dict() for s in self.seasons],
            "episodes": [e.to_dict() for e in self.episodes],
            "scenes": [s.to_dict() for s in self.scenes],
            "total_seasons": self.total_seasons, "total_episodes": self.total_episodes,
            "total_scenes": self.total_scenes,
            "episodes_with_season_plan": self.episodes_with_season_plan,
            "episodes_with_beat_plan": self.episodes_with_beat_plan,
            "written_scenes": self.written_scenes,
            "unwritten_scenes": self.unwritten_scenes,
            "total_blocks": self.total_blocks, "dialogue_heavy": self.dialogue_heavy,
            "missing_scene_heading": self.missing_scene_heading,
            "episodes_with_abc_warning": self.episodes_with_abc_warning,
            "episodes_with_act_break_warning": self.episodes_with_act_break_warning,
            "episodes_with_cold_open_tag_warning": self.episodes_with_cold_open_tag_warning,
            "episodes_with_continuity_warning": self.episodes_with_continuity_warning,
            "scenes_timeline_linked": self.scenes_timeline_linked,
            "scenes_with_psyke": self.scenes_with_psyke,
            "scenes_with_notes": self.scenes_with_notes,
            "with_export_warnings": self.with_export_warnings,
            "needs_work": self.needs_work, "export_ready": self.export_ready,
        }

    def filtered_rows(self, filter_key: str) -> list[SceneReviewRow]:
        """Scene-centric filtering (the dashboard table is scene rows)."""
        f = filter_key or "All"
        if f == "Missing Season / Arc Plan":
            return [r for r in self.scenes if r.season_plan_status == ST_MISSING]
        if f == "Missing Episode Beat Plan":
            return [r for r in self.scenes if r.episode_plan_status == ST_MISSING]
        if f == "Missing Scene Body":
            return [r for r in self.scenes if r.body_status == ST_MISSING]
        if f == "A/B/C Story Warning":
            return [r for r in self.scenes if r.abc_status == ST_WARNING]
        if f == "Weak Act Break":
            return [r for r in self.scenes if r.act_break_status == ST_WARNING]
        if f == "Cold Open / Tag Warning":
            return [r for r in self.scenes if r.cold_open_tag_status == ST_WARNING]
        if f == "Continuity Risk":
            return [r for r in self.scenes if r.continuity_status != ST_OK]
        if f == "Not Linked to Timeline":
            return [r for r in self.scenes if r.timeline_status != ST_OK]
        if f == "Export Warning":
            return [r for r in self.scenes if r.export_status == ST_WARNING]
        if f == "Needs Reflection":
            return [r for r in self.scenes
                    if r.overall_status in (ST_NEEDS_WORK, ST_ERROR)]
        if f == "Needs Rewrite":
            return [r for r in self.scenes if r.has_rewrite_candidate
                    or r.overall_status == ST_ERROR]
        return list(self.scenes)

    def to_markdown(self) -> str:
        """Copy-friendly Markdown. Never includes provider settings / API keys."""
        lines = [f"# Series Review — {self.project_title or 'Untitled'}", ""]
        lines.append(
            f"- Seasons/Arcs: **{self.total_seasons}**  ·  Episodes: "
            f"**{self.total_episodes}**  ·  Scenes: **{self.total_scenes}**  ·  "
            f"Written: **{self.written_scenes}**  ·  Series blocks: "
            f"**{self.total_blocks}**")
        lines.append(
            f"- Planned: season {self.episodes_with_season_plan}/{self.total_episodes}, "
            f"episode beat {self.episodes_with_beat_plan}/{self.total_episodes}  ·  "
            f"Dialogue-heavy: {self.dialogue_heavy}  ·  Missing scene heading: "
            f"{self.missing_scene_heading}")
        lines.append(
            f"- A/B/C warnings: {self.episodes_with_abc_warning}  ·  Act-break: "
            f"{self.episodes_with_act_break_warning}  ·  Cold open/tag: "
            f"{self.episodes_with_cold_open_tag_warning}  ·  Continuity: "
            f"{self.episodes_with_continuity_warning}  ·  Export warnings: "
            f"{self.with_export_warnings}")
        lines.append(
            f"- Timeline-linked scenes: {self.scenes_timeline_linked}/"
            f"{self.total_scenes}  ·  Export ready: "
            f"**{'Yes' if self.export_ready else 'No'}**")
        lines.append("")
        lines.append("| # | Episode / Scene | Plan | Body | A/B/C | Act Breaks | "
                     "Cold Open / Tag | Continuity | Timeline | PSYKE/Notes | "
                     "Next Action |")
        lines.append("|---|-----------------|------|------|-------|------------|"
                     "-----------------|------------|----------|-------------|"
                     "-------------|")
        for r in self.scenes:
            label = f"{r.episode_label} · {r.title or 'Untitled'}"
            lines.append(
                f"| {r.number or '-'} | {label} | {r.episode_plan_status} | "
                f"{r.body_status} | {r.abc_status} | {r.act_break_status} | "
                f"{r.cold_open_tag_status} | {r.continuity_status} | "
                f"{r.timeline_status} | {r.psyke_notes_status} | {r.next_action} |")
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


def _scene_next_action(row: SceneReviewRow) -> tuple[str, str]:
    if row.body_status == ST_MISSING:
        if row.episode_plan_status == ST_MISSING:
            return ("Add Episode Beat Plan", ST_NEEDS_WORK)
        return ("Write Scene", ST_NEEDS_WORK)
    if row.scene_function_status == ST_WARNING and "heading" in row._fn_reason:
        return ("Add Scene Heading", ST_NEEDS_WORK)
    if row.abc_status == ST_WARNING:
        return ("Clarify A/B/C story", ST_NEEDS_WORK)
    if row.act_break_status == ST_WARNING:
        return ("Strengthen Act Break", ST_WARNING)
    if row.cold_open_tag_status == ST_WARNING:
        return ("Clarify Cold Open / Tag", ST_WARNING)
    if row.continuity_status != ST_OK:
        return ("Check Continuity", ST_WARNING)
    if row.scene_function_status == ST_WARNING:
        return ("Clarify scene function", ST_WARNING)
    if row.episode_plan_status == ST_MISSING:
        return ("Add Episode Beat Plan", ST_WARNING)
    if row.season_plan_status == ST_MISSING:
        return ("Add Season / Arc Plan", ST_WARNING)
    if row.timeline_status == ST_MISSING:
        return ("Link to Timeline", ST_WARNING)
    return ("Ready for export", ST_OK)


def build_series_review(db, project_id: int) -> SeriesReviewReport:
    """Build the project-level Series review. Deterministic, read-only."""
    report = SeriesReviewReport(project_id=project_id)
    project = db.get_project_by_id(project_id)
    report.project_title = getattr(project, "title", "") if project else ""

    from logosforge import series_continuity as scont
    from logosforge import series_diagnostics as sd
    from logosforge import story_structure as ss

    try:
        cont = scont.build_series_continuity_report(db, project_id)
    except Exception:
        cont = scont.SeriesContinuityReport(project_id=project_id)
    try:
        tree = ss.build_structure_tree(db, project_id)
        numbers = ss.compute_structural_numbers(tree, ss.is_novel_project(db, project_id))
    except Exception:
        tree, numbers = [], {"acts": {}, "chapters": {}, "scenes": {}}
    scene_nums = numbers.get("scenes", {})
    act_nums = numbers.get("acts", {})

    # Per-episode status derived from the continuity findings (keyed by label).
    ep_abc: dict[str, bool] = {}
    ep_actbreak: dict[str, bool] = {}
    ep_coldtag: dict[str, bool] = {}
    ep_cont_sev: dict[str, str] = {}
    for f in cont.abc_tracking:
        if f.episode and _SEV_RANK.get(_MAP_SEV.get(f.severity, SEV_INFO), 0) \
                >= _SEV_RANK[SEV_WARNING]:
            ep_abc[f.episode] = True
    for f in cont.episode_structure:
        t = (f.title or "").lower()
        if "act break" in t:
            ep_actbreak[f.episode] = True
        if "teaser" in t or "cold open" in t or "tag" in t:
            ep_coldtag[f.episode] = True
    for f in cont.progression:
        t = (f.title or "").lower()
        if "cold open" in t or "tag" in t:
            ep_coldtag[f.episode] = True
    # Continuity column draws from the continuity-proper sections only (A/B/C,
    # act-break and cold-open/tag have their own columns above).
    _cont_sources = (cont.character_arc + cont.timeline_alignment
                     + cont.psyke_notes + cont.setup_payoff)
    for f in _cont_sources:
        if f.episode:
            ep_cont_sev[f.episode] = _worse(
                ep_cont_sev.get(f.episode, SEV_INFO),
                _MAP_SEV.get(f.severity, SEV_INFO))
    # Per-scene continuity severity from finding scene_ids.
    scene_cont_sev: dict[int, str] = {}
    for f in _cont_sources:
        for sid in f.scene_ids:
            scene_cont_sev[sid] = _worse(scene_cont_sev.get(sid, SEV_INFO),
                                         _MAP_SEV.get(f.severity, SEV_INFO))

    chain_by_chapter = {e.chapter: e for e in cont.episode_chain}
    try:
        from logosforge.screenplay_diagnostics import _psyke_character_map
        psyke_map = _psyke_character_map(db, project_id)
    except Exception:
        psyke_map = {}
    candidates = _rewrite_candidate_scene_ids(db, project_id)
    try:
        events = db.get_timeline_event_ids(project_id) or set()
    except Exception:
        events = set()
    timeline_has_any = bool(events) and any(
        e.timeline_linked_count for e in cont.episode_chain)

    # -- Scenes (canonical Season->Episode->Scene) --
    for act, chapters in tree:
        for chapter, scenes in chapters:
            if chapter == ss.UNASSIGNED_CHAPTER:
                continue
            e = chain_by_chapter.get(chapter)
            ep_label = sd.sbk.episode_label(chapter)
            for scene in scenes:
                sid = scene.id
                row = SceneReviewRow(
                    scene_id=sid, number=scene_nums.get(sid, "") or "",
                    title=(getattr(scene, "title", "") or "").strip(),
                    episode=chapter, episode_label=ep_label, act=act,
                    season_plan_status=ST_OK if (e and e.has_season_plan) else ST_MISSING,
                    episode_plan_status=ST_OK if (e and e.has_episode_plan)
                    else ST_MISSING)
                body = getattr(scene, "content", "") or ""
                row.body_status = ST_OK if body.strip() else ST_MISSING
                row._fn_reason = ""  # type: ignore[attr-defined]

                if row.body_status == ST_OK:
                    try:
                        diag = sd.analyze_scene_by_id(db, project_id, sid)
                    except Exception:
                        diag = None
                    if diag is not None:
                        row.block_count = diag.metrics.total_blocks
                        row.dialogue_action_ratio = diag.metrics.dialogue_action_ratio
                        ids = {i.id for i in diag.issues}
                        fn_issues = [i for i in diag.issues
                                     if i.category == sd.CAT_FUNCTION]
                        if any(i.id == "no_scene_heading" for i in diag.issues):
                            row.scene_function_status = ST_WARNING
                            row._fn_reason = "heading"  # type: ignore[attr-defined]
                        elif fn_issues:
                            row.scene_function_status = ST_WARNING
                        if "no_abc_connection" in ids:
                            row.abc_status = ST_WARNING
                        if any(i.id == "dialogue_heavy" for i in diag.issues):
                            row.export_status = row.export_status  # noted via metrics
                    row.timeline_status = ST_OK if sid in events else (
                        ST_MISSING if timeline_has_any else ST_NOT_CHECKED)
                else:
                    row.scene_function_status = ST_NOT_CHECKED
                    row.abc_status = ST_NOT_CHECKED
                    row.timeline_status = (ST_MISSING if timeline_has_any
                                           else ST_NOT_CHECKED)

                # Inherit episode-level signals.
                if ep_abc.get(ep_label) and row.abc_status != ST_NOT_CHECKED:
                    row.abc_status = ST_WARNING
                if ep_actbreak.get(ep_label):
                    row.act_break_status = ST_WARNING
                if ep_coldtag.get(ep_label):
                    row.cold_open_tag_status = ST_WARNING

                sev = _worse(scene_cont_sev.get(sid, SEV_INFO),
                             ep_cont_sev.get(ep_label, SEV_INFO))
                if _SEV_RANK.get(sev, 0) >= _SEV_RANK[SEV_WARNING]:
                    row.continuity_status = ST_WARNING
                    row.continuity_severity = sev

                # PSYKE / Notes.
                if psyke_map and row.body_status == ST_OK:
                    speakers = set(sd.sbk.character_cues(
                        sd.sbk.load_scene_script(db, sid)))
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

                if row.body_status == ST_OK:
                    row.export_status = ST_WARNING if (
                        row.scene_function_status == ST_WARNING
                        and row._fn_reason == "heading") else ST_OK
                else:
                    row.export_status = ST_NOT_CHECKED

                row.has_rewrite_candidate = sid in candidates
                row.next_action, row.overall_status = _scene_next_action(row)
                report.scenes.append(row)

    # -- Episodes (roll-up per chapter) --
    for e in cont.episode_chain:
        ep_label = e.episode_label
        ep_scenes = [r for r in report.scenes if r.episode == e.chapter]
        erow = EpisodeReviewRow(
            chapter=e.chapter, episode_label=ep_label, act=e.act,
            title=ep_label, summary_present=bool(e.premise or e.objective),
            episode_plan_status=ST_OK if e.has_episode_plan else ST_MISSING,
            season_plan_status=ST_OK if e.has_season_plan else ST_MISSING,
            scene_count=e.scene_count, written_scene_count=e.body_scene_count,
            abc_status=ST_WARNING if ep_abc.get(ep_label) else ST_OK,
            act_break_status=ST_WARNING if ep_actbreak.get(ep_label) else ST_OK,
            cold_open_tag_status=ST_WARNING if ep_coldtag.get(ep_label) else ST_OK,
            timeline_status=ST_OK if e.timeline_linked_count else (
                ST_MISSING if timeline_has_any else ST_NOT_CHECKED))
        csev = ep_cont_sev.get(ep_label, SEV_INFO)
        if _SEV_RANK.get(csev, 0) >= _SEV_RANK[SEV_WARNING]:
            erow.continuity_status = ST_WARNING
            erow.continuity_severity = csev
        erow.psyke_notes_status = (
            ST_WARNING if any(r.psyke_notes_status == ST_WARNING for r in ep_scenes)
            else (ST_OK if any(r.psyke_notes_status == ST_OK for r in ep_scenes)
                  else ST_NOT_CHECKED))
        erow.export_status = (ST_WARNING if any(r.export_status == ST_WARNING
                              for r in ep_scenes) else ST_OK)
        if e.body_scene_count == 0:
            erow.next_action, erow.overall_status = (
                ("Add Episode Beat Plan", ST_NEEDS_WORK) if not e.has_episode_plan
                else ("Write Scenes", ST_NEEDS_WORK))
        elif erow.abc_status == ST_WARNING:
            erow.next_action, erow.overall_status = ("Clarify A/B/C story", ST_NEEDS_WORK)
        elif erow.act_break_status == ST_WARNING:
            erow.next_action, erow.overall_status = ("Strengthen Act Break", ST_WARNING)
        elif erow.cold_open_tag_status == ST_WARNING:
            erow.next_action, erow.overall_status = ("Clarify Cold Open / Tag", ST_WARNING)
        elif erow.continuity_status == ST_WARNING:
            erow.next_action, erow.overall_status = ("Check Continuity", ST_WARNING)
        elif not e.has_episode_plan:
            erow.next_action, erow.overall_status = ("Add Episode Beat Plan", ST_WARNING)
        else:
            erow.next_action, erow.overall_status = ("Ready for export", ST_OK)
        report.episodes.append(erow)

    # -- Seasons (roll-up per act) --
    acts_seen: list[str] = []
    for e in cont.episode_chain:
        if e.act not in acts_seen:
            acts_seen.append(e.act)
    setup_acts = {f.episode for f in cont.setup_payoff if f.episode}
    for act in acts_seen:
        eps = [er for er in report.episodes if er.act == act]
        has_season = any(er.season_plan_status == ST_OK for er in eps)
        srow = SeasonReviewRow(
            act=act, number=act_nums.get(act, "") or "", title=act,
            season_plan_status=ST_OK if has_season else ST_MISSING,
            episode_count=len(eps),
            written_episode_count=sum(1 for er in eps if er.written_scene_count > 0),
            abc_status=ST_WARNING if any(er.abc_status == ST_WARNING for er in eps)
            else ST_OK,
            setup_payoff_status=ST_WARNING if act in setup_acts else ST_OK)
        worst = SEV_INFO
        for er in eps:
            worst = _worse(worst, er.continuity_severity)
        srow.continuity_severity = worst
        if not has_season:
            srow.next_action, srow.overall_status = ("Add Season / Arc Plan", ST_NEEDS_WORK)
        elif srow.abc_status == ST_WARNING:
            srow.next_action, srow.overall_status = ("Balance A/B/C stories", ST_WARNING)
        elif srow.setup_payoff_status == ST_WARNING:
            srow.next_action, srow.overall_status = ("Resolve setup/payoff", ST_WARNING)
        elif srow.written_episode_count < srow.episode_count:
            srow.next_action, srow.overall_status = ("Write remaining episodes", ST_WARNING)
        else:
            srow.next_action, srow.overall_status = ("Ready for export", ST_OK)
        report.seasons.append(srow)

    # -- Summary --
    scenes = report.scenes
    report.total_seasons = len(report.seasons)
    report.total_episodes = len(report.episodes)
    report.total_scenes = len(scenes)
    report.episodes_with_season_plan = sum(
        1 for er in report.episodes if er.season_plan_status == ST_OK)
    report.episodes_with_beat_plan = sum(
        1 for er in report.episodes if er.episode_plan_status == ST_OK)
    report.written_scenes = sum(1 for r in scenes if r.body_status == ST_OK)
    report.unwritten_scenes = sum(1 for r in scenes if r.body_status == ST_MISSING)
    report.total_blocks = sum(r.block_count for r in scenes)
    report.dialogue_heavy = sum(1 for r in scenes if r.dialogue_action_ratio >= 4.0)
    report.missing_scene_heading = sum(
        1 for r in scenes if getattr(r, "_fn_reason", "") == "heading")
    report.episodes_with_abc_warning = sum(
        1 for er in report.episodes if er.abc_status == ST_WARNING)
    report.episodes_with_act_break_warning = sum(
        1 for er in report.episodes if er.act_break_status == ST_WARNING)
    report.episodes_with_cold_open_tag_warning = sum(
        1 for er in report.episodes if er.cold_open_tag_status == ST_WARNING)
    report.episodes_with_continuity_warning = sum(
        1 for er in report.episodes if er.continuity_status == ST_WARNING)
    report.scenes_timeline_linked = sum(1 for r in scenes if r.timeline_status == ST_OK)
    report.scenes_with_psyke = sum(1 for r in scenes if r.psyke_notes_status == ST_OK)
    report.scenes_with_notes = sum(1 for r in scenes if _scene_has_notes(db, r.scene_id))
    report.with_export_warnings = sum(1 for r in scenes if r.export_status == ST_WARNING)
    report.needs_work = sum(1 for r in scenes
                            if r.overall_status in (ST_NEEDS_WORK, ST_ERROR))
    report.export_ready = report.written_scenes > 0 and report.with_export_warnings == 0
    return report
