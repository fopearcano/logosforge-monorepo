"""Cross-episode Series continuity / coherence (Phase 6).

A cross-EPISODE consolidator: it does NOT re-implement scene/episode analysis — it
ties the deterministic engines already in the codebase into one structured,
writer-facing report about how the *series* works together across episodes:

* canonical Act→Chapter→Scene chain read as Season→Episode→Scene (never id order),
* episode chain / serialized progression (cold-open & tag follow-through,
  empty episodes, episode progression vs the Season plan),
* A/B/C story tracking (per-episode scene support via the Episode beat plan;
  introduced-then-abandoned; unavailable when no threads are configured),
* character-arc continuity across episodes,
* setup/payoff + recurring motifs (``screenplay_setup_payoff`` + story links +
  Season plan aggregate),
* episode-structure alignment (folds ``series_diagnostics.analyze_episode``),
* Timeline alignment (linkage + order vs structure, canonical numbering),
* PSYKE / Notes consistency,
* cross-scene continuity (``logosforge.continuity``).

Read-only and deterministic: no mutation of Manuscript / Outline / Timeline /
PSYKE / Notes, no LLM, no new persistent links this phase, and no image
generation. An optional AI pass may *expand* the report; it never rewrites or
applies. No API keys are read. Mirrors ``stage_script_continuity``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from logosforge import series_blocks as sbk
from logosforge import series_diagnostics as sd

# Section keys (canonical render order).
SEC_SEASON = "Season / Arc Overview"
SEC_CHAIN = "Episode Chain / Serialized Progression"
SEC_ABC = "A/B/C Story Tracking"
SEC_CHARACTER = "Character Arc Continuity"
SEC_SETUP = "Setup / Payoff / Motif Tracking"
SEC_STRUCTURE = "Episode Structure Alignment"
SEC_TIMELINE = "Timeline / Structure Alignment"
SEC_PSYKE = "PSYKE / Notes Consistency"
SEC_FIXES = "Recommended Fixes"

SEV_INFO = sd.SEV_INFO
SEV_WATCH = sd.SEV_WATCH
SEV_WEAK = sd.SEV_WEAK
SEV_CRITICAL = sd.SEV_CRITICAL
_SEV_RANK = {SEV_INFO: 0, SEV_WATCH: 1, SEV_WEAK: 2, SEV_CRITICAL: 3}

LONG_ABSENCE = 3            # episodes a character can vanish before it's flagged

# How analyze_episode issue ids map into the cross-episode report sections.
_EP_STRUCTURE_IDS = {
    "episode_no_scenes", "episode_no_bodies", "episode_no_plan",
    "teaser_expected_missing", "act_break_expected_missing", "tag_expected_missing",
    "climax_missing", "climax_not_represented",
}
_EP_ABC_IDS = {"abc_none", "abc_weak"}

_DIMENSION_SECTION = {
    "character": SEC_CHARACTER, "temporal": SEC_TIMELINE, "object": SEC_SETUP,
    "spatial": SEC_STRUCTURE, "theme": SEC_SETUP, "plot": SEC_SETUP,
    "dialogue": SEC_CHARACTER, "lore": SEC_PSYKE, "mode": SEC_STRUCTURE,
}


@dataclass
class ContinuityFinding:
    section: str
    title: str
    detail: str = ""
    severity: str = SEV_INFO
    episode: str = ""
    scene_ids: list[int] = field(default_factory=list)
    thread: str = ""
    suggested_action: str = ""

    @property
    def rank(self) -> int:
        return _SEV_RANK.get(self.severity, 0)

    def to_dict(self) -> dict[str, Any]:
        return {"section": self.section, "title": self.title, "detail": self.detail,
                "severity": self.severity, "episode": self.episode,
                "scene_ids": list(self.scene_ids), "thread": self.thread,
                "suggested_action": self.suggested_action}


@dataclass
class EpisodeChainEntry:
    chapter: str
    episode_label: str = ""
    act: str = ""
    premise: str = ""
    objective: str = ""
    scene_count: int = 0
    body_scene_count: int = 0
    has_episode_plan: bool = False
    has_season_plan: bool = False
    timeline_linked_count: int = 0
    markers: list[str] = field(default_factory=list)
    abc_defined: list[str] = field(default_factory=list)
    abc_support: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"chapter": self.chapter, "episode_label": self.episode_label,
                "act": self.act, "premise": self.premise, "objective": self.objective,
                "scene_count": self.scene_count,
                "body_scene_count": self.body_scene_count,
                "has_episode_plan": self.has_episode_plan,
                "has_season_plan": self.has_season_plan,
                "timeline_linked_count": self.timeline_linked_count,
                "markers": list(self.markers), "abc_defined": list(self.abc_defined),
                "abc_support": dict(self.abc_support)}


@dataclass
class SeriesContinuityReport:
    project_id: int | None = None
    episode_chain: list[EpisodeChainEntry] = field(default_factory=list)
    season_overview: list[ContinuityFinding] = field(default_factory=list)
    progression: list[ContinuityFinding] = field(default_factory=list)
    abc_tracking: list[ContinuityFinding] = field(default_factory=list)
    character_arc: list[ContinuityFinding] = field(default_factory=list)
    setup_payoff: list[ContinuityFinding] = field(default_factory=list)
    episode_structure: list[ContinuityFinding] = field(default_factory=list)
    timeline_alignment: list[ContinuityFinding] = field(default_factory=list)
    psyke_notes: list[ContinuityFinding] = field(default_factory=list)
    recommended_fixes: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def _sections(self):
        return (
            (SEC_SEASON, self.season_overview), (SEC_CHAIN, self.progression),
            (SEC_ABC, self.abc_tracking), (SEC_CHARACTER, self.character_arc),
            (SEC_SETUP, self.setup_payoff), (SEC_STRUCTURE, self.episode_structure),
            (SEC_TIMELINE, self.timeline_alignment), (SEC_PSYKE, self.psyke_notes),
        )

    def all_findings(self) -> list[ContinuityFinding]:
        out: list[ContinuityFinding] = []
        for _, findings in self._sections():
            out.extend(findings)
        return out

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "project_id": self.project_id,
            "episode_chain": [e.to_dict() for e in self.episode_chain]}
        for header, findings in self._sections():
            out[header] = [f.to_dict() for f in findings]
        out["recommended_fixes"] = list(self.recommended_fixes)
        out["metrics"] = dict(self.metrics)
        return out

    def to_text(self) -> str:
        lines: list[str] = [
            f"Series Continuity — {len(self.episode_chain)} episode(s)", ""]
        lines.append(SEC_SEASON + ":")
        if self.episode_chain:
            for e in self.episode_chain:
                flags = []
                if e.body_scene_count == 0:
                    flags.append("no body")
                if not e.has_episode_plan:
                    flags.append("no beat plan")
                if e.timeline_linked_count:
                    flags.append("timeline")
                if e.abc_defined:
                    flags.append("ABC:" + "/".join(e.abc_defined))
                tag = f"  [{', '.join(flags)}]" if flags else ""
                obj = f" — {e.premise or e.objective}" if (e.premise or e.objective) else ""
                lines.append(f"- {e.episode_label} ({e.chapter}) · "
                             f"{e.body_scene_count}/{e.scene_count} scene(s){obj}{tag}")
        else:
            lines.append("- No episodes.")
        for header, findings in self._sections():
            if header == SEC_SEASON:
                continue
            lines.append("")
            lines.append(header + ":")
            if findings:
                for f in sorted(findings, key=lambda x: x.rank, reverse=True):
                    ep = f" [{f.episode}]" if f.episode else ""
                    lines.append(f"- [{f.severity}]{ep} {f.title} — {f.detail}")
            else:
                lines.append("- Nothing flagged.")
        lines.append("")
        lines.append(SEC_FIXES + ":")
        lines.extend(f"- {s}" for s in (self.recommended_fixes or ["None."]))
        return "\n".join(lines)


# ===========================================================================
# Episode chain
# ===========================================================================


def _episode_chain(db, project_id: int):
    """Canonical Season→Episode→Scene chain. Returns (chain, episodes_data, events)
    where episodes_data is [(entry, scenes, scripts, scene_words)]."""
    from logosforge import story_structure as ss
    from logosforge import series_pipeline as spp
    try:
        tree = ss.build_structure_tree(db, project_id)
    except Exception:
        tree = []
    try:
        events = db.get_timeline_event_ids(project_id) or set()
    except Exception:
        events = set()

    chain: list[EpisodeChainEntry] = []
    episodes_data: list = []
    for act, chapters in tree:
        season = None
        try:
            season = spp.get_season_plan(db, project_id, act) if act != ss.UNASSIGNED_ACT else None
        except Exception:
            season = None
        for chapter, scenes in chapters:
            if chapter == ss.UNASSIGNED_CHAPTER:
                continue
            scripts = [sbk.parse_series_text(getattr(s, "content", "") or "")
                       for s in scenes]
            scene_words = [
                (sd._content_words(sbk.serialize_series_script(sc))
                 | sd._content_words(getattr(s, "summary", "") or ""))
                for s, sc in zip(scenes, scripts)]
            markers: set[str] = set()
            for sc in scripts:
                for b in sc.blocks:
                    if b.block_type in sbk._SERIES_MARKERS:
                        markers.add(b.block_type)
            ep_plan = None
            try:
                ep_plan = spp.get_episode_plan(db, project_id, chapter)
            except Exception:
                ep_plan = None
            entry = EpisodeChainEntry(
                chapter=chapter, episode_label=sbk.episode_label(chapter), act=act,
                scene_count=len(scenes),
                body_scene_count=sum(1 for sc in scripts if not sc.is_empty()),
                has_episode_plan=not _is_empty(ep_plan),
                has_season_plan=not _is_empty(season),
                timeline_linked_count=sum(1 for s in scenes if s.id in events),
                markers=sorted(markers))
            if ep_plan is not None and not ep_plan.is_empty():
                entry.premise = (ep_plan.episode_premise or "").strip()[:120]
                entry.objective = (ep_plan.episode_objective or "").strip()[:120]
                abc = ep_plan.has_abc()
                entry.abc_defined = [k for k, v in abc.items() if v]
                threads = {"A": ep_plan.a_story, "B": ep_plan.b_story,
                           "C": ep_plan.c_story}
                for t in entry.abc_defined:
                    tw = sd._content_words(threads[t])
                    entry.abc_support[t] = sum(1 for sw in scene_words if tw & sw) \
                        if tw else 0
            chain.append(entry)
            episodes_data.append((entry, scenes, scripts, scene_words))
    return chain, episodes_data, events


def _is_empty(obj: Any) -> bool:
    if obj is None:
        return True
    try:
        return bool(obj.is_empty())
    except Exception:
        return False


# ===========================================================================
# Section builders
# ===========================================================================


def _season_overview(db, project_id: int, chain) -> list[ContinuityFinding]:
    from logosforge import series_pipeline as spp
    out: list[ContinuityFinding] = []
    acts: dict[str, list[EpisodeChainEntry]] = {}
    for e in chain:
        acts.setdefault(e.act, []).append(e)
    for act, entries in acts.items():
        season = None
        try:
            season = spp.get_season_plan(db, project_id, act)
        except Exception:
            season = None
        if _is_empty(season):
            out.append(ContinuityFinding(
                section=SEC_SEASON, title=f"No Season / Arc plan for {act}",
                detail="This Act / Season has no Season / Arc plan to anchor its "
                       "episodes.", severity=SEV_WATCH,
                suggested_action=f"Generate a Season / Arc plan for {act}."))
            continue
        prog = [p for p in (season.episode_progression or []) if str(p).strip()]
        if prog and len(prog) != len(entries):
            out.append(ContinuityFinding(
                section=SEC_SEASON, title=f"Episode progression mismatch in {act}",
                detail=f"The Season plan lists {len(prog)} progression beat(s) but "
                       f"the Act has {len(entries)} episode(s).", severity=SEV_INFO,
                suggested_action="Align the episode progression with the actual "
                                 "episodes, or update the plan."))
    return out


def _progression_findings(episodes_data) -> list[ContinuityFinding]:
    out: list[ContinuityFinding] = []
    from logosforge import series_pipeline as spp  # noqa: F401 (kept for parity)
    for entry, scenes, scripts, scene_words in episodes_data:
        # Cold open / teaser without a follow-up scene.
        teaser_idx = next((i for i, sc in enumerate(scripts)
                           if any(b.block_type == sbk.BT_TEASER for b in sc.blocks)),
                          None)
        if teaser_idx is not None:
            has_follow = any(not scripts[j].is_empty()
                             for j in range(teaser_idx + 1, len(scripts)))
            if not has_follow:
                out.append(ContinuityFinding(
                    section=SEC_CHAIN, title="Cold Open without a follow-up scene",
                    detail="The Episode opens with a Cold Open / Teaser but no later "
                           "scene picks up its momentum.", severity=SEV_WATCH,
                    episode=entry.episode_label,
                    scene_ids=[scenes[teaser_idx].id] if teaser_idx < len(scenes) else [],
                    suggested_action="Add a scene that pays off the cold open's hook."))
        # Tag not connected to a turn (no act break, no climax, no turn language).
        if sbk.BT_TAG in entry.markers:
            has_turn = sbk.BT_ACT_BREAK in entry.markers
            body_low = " ".join(sbk.serialize_series_script(sc).lower()
                                for sc in scripts)
            if sd._has_any(body_low, sd.TURN_MARKERS):
                has_turn = True
            if not has_turn:
                out.append(ContinuityFinding(
                    section=SEC_CHAIN, title="Tag not connected to an episode turn",
                    detail="A Tag / button is present but the Episode shows no act "
                           "break or clear turn for it to land on.", severity=SEV_WATCH,
                    episode=entry.episode_label,
                    suggested_action="Tie the tag to the episode's turn, or cut it."))
    return out


def _abc_findings(chain) -> list[ContinuityFinding]:
    out: list[ContinuityFinding] = []
    for e in chain:
        if not e.has_episode_plan:
            continue
        if not e.abc_defined:
            out.append(ContinuityFinding(
                section=SEC_ABC, title="A/B/C tracking unavailable",
                detail="The Episode beat plan defines no A/B/C story thread.",
                severity=SEV_INFO, episode=e.episode_label,
                suggested_action="Define at least an A story to track threads."))
            continue
        for thread in e.abc_defined:
            if e.abc_support.get(thread, 0) == 0:
                out.append(ContinuityFinding(
                    section=SEC_ABC, title=f"{thread}-story has no scene support",
                    detail=f"The Episode defines a {thread}-story but no scene echoes "
                           "it.", severity=SEV_WATCH, episode=e.episode_label,
                    thread=thread,
                    suggested_action=f"Write a scene that advances the {thread}-story, "
                                     "or update the plan."))
    # Introduced-then-abandoned across episodes within an Act.
    by_act: dict[str, list[EpisodeChainEntry]] = {}
    for e in chain:
        by_act.setdefault(e.act, []).append(e)
    for entries in by_act.values():
        for thread in ("A", "B", "C"):
            seen_supported = False
            for e in entries:
                if thread not in e.abc_defined:
                    continue
                sup = e.abc_support.get(thread, 0)
                if sup > 0:
                    seen_supported = True
                elif seen_supported and sup == 0:
                    out.append(ContinuityFinding(
                        section=SEC_ABC,
                        title=f"{thread}-story introduced earlier but abandoned",
                        detail=f"The {thread}-story had scene support in an earlier "
                               f"episode but none in {e.episode_label}.",
                        severity=SEV_WATCH, episode=e.episode_label, thread=thread,
                        suggested_action=f"Continue the {thread}-story or resolve it."))
    return out


def _character_findings(episodes_data) -> list[ContinuityFinding]:
    out: list[ContinuityFinding] = []
    appears: dict[str, list[int]] = {}
    for pos, (entry, scenes, scripts, _w) in enumerate(episodes_data):
        speakers: set[str] = set()
        for sc in scripts:
            speakers |= set(sbk.character_cues(sc))
        for name in speakers:
            appears.setdefault(name, []).append(pos)
    n = len(episodes_data)
    for name, positions in appears.items():
        if len(positions) == 1 and n >= 3:
            out.append(ContinuityFinding(
                section=SEC_CHARACTER, title=f"{name}: appears in only one episode",
                detail="Speaks in a single episode across the series.",
                severity=SEV_INFO,
                suggested_action="Confirm the one-episode appearance is intended."))
        elif len(positions) >= 2:
            gap = max(b - a for a, b in zip(positions, positions[1:]))
            if gap >= LONG_ABSENCE:
                out.append(ContinuityFinding(
                    section=SEC_CHARACTER, title=f"{name}: long absence then return",
                    detail=f"Disappears for ~{gap} episode(s), then returns.",
                    severity=SEV_INFO,
                    suggested_action="Re-establish the character on return."))
    return out


def _setup_payoff_findings(db, project_id: int) -> list[ContinuityFinding]:
    """Setup/payoff candidates (mode-agnostic engine) + confirmed story links. The
    Season-plan aggregate (arc/setup/cliffhanger/motif) lives in
    :func:`_season_alignment_findings`."""
    out: list[ContinuityFinding] = []
    try:
        from logosforge.screenplay_setup_payoff import analyze_setup_payoff
        rep = analyze_setup_payoff(db, project_id)
    except Exception:
        rep = None
    if rep is not None:
        for c in getattr(rep, "unresolved_setups", []) or []:
            out.append(ContinuityFinding(
                section=SEC_SETUP, title="Setup without payoff",
                detail=f"{getattr(c, 'label', '')} — {getattr(c, 'evidence', '')}",
                severity=SEV_WATCH,
                scene_ids=[c.scene_id] if getattr(c, "scene_id", None) else [],
                suggested_action=getattr(c, "suggested_action", "")
                or "Plant a payoff or cut the setup."))
        for c in getattr(rep, "possible_payoffs", []) or []:
            out.append(ContinuityFinding(
                section=SEC_SETUP, title="Possible payoff without a setup",
                detail=f"{getattr(c, 'label', '')} — {getattr(c, 'evidence', '')}",
                severity=SEV_INFO,
                scene_ids=[c.scene_id] if getattr(c, "scene_id", None) else []))
    try:
        confirmed = list(db.get_story_links(project_id, status="confirmed") or [])
    except Exception:
        confirmed = []
    for link in confirmed:
        out.append(ContinuityFinding(
            section=SEC_SETUP,
            title=f"Confirmed {getattr(link, 'link_type', 'story')} link",
            detail=getattr(link, "label", "") or "Confirmed story link.",
            severity=SEV_INFO))
    return out


def _season_alignment_findings(db, project_id: int, chain,
                               episodes_data) -> list[ContinuityFinding]:
    """Per-Act Season/Arc support, aggregated across the Act's episodes so a thread
    supported by *any* episode is not falsely flagged."""
    from logosforge import series_pipeline as spp
    out: list[ContinuityFinding] = []
    act_words: dict[str, set[str]] = {}
    for entry, scenes, scripts, scene_words in episodes_data:
        words = set()
        for sw in scene_words:
            words |= sw
        act_words.setdefault(entry.act, set()).update(words)
    seen_acts: set[str] = set()
    for e in chain:
        if e.act in seen_acts:
            continue
        seen_acts.add(e.act)
        season = None
        try:
            season = spp.get_season_plan(db, project_id, e.act)
        except Exception:
            season = None
        if _is_empty(season):
            continue
        issues: list = []
        sd._arc_alignment(season, act_words.get(e.act, set()), issues)
        for issue in issues:
            section = SEC_SEASON if issue.id == "arc_question_unsupported" else SEC_SETUP
            out.append(ContinuityFinding(
                section=section, title=issue.label, detail=issue.evidence,
                severity=issue.severity, episode=e.act,
                suggested_action=issue.suggested_action))
    return out


def _episode_structure_findings(db, project_id: int,
                                chain) -> tuple[list, list, list, list]:
    """Fold series_diagnostics.analyze_episode per episode into the structure / ABC /
    setup / timeline sections (episode-level)."""
    structure: list[ContinuityFinding] = []
    abc: list[ContinuityFinding] = []
    setup: list[ContinuityFinding] = []
    timeline: list[ContinuityFinding] = []
    for e in chain:
        try:
            ep = sd.analyze_episode(db, project_id, e.chapter)
        except Exception:
            continue
        for issue in ep.issues:
            if issue.id in _EP_STRUCTURE_IDS:
                bucket, section = structure, SEC_STRUCTURE
            elif issue.id in _EP_ABC_IDS:
                bucket, section = abc, SEC_ABC
            elif issue.id == "timeline_order_mismatch":
                bucket, section = timeline, SEC_TIMELINE
            elif issue.id in ("setup_payoff_unsupported", "cliffhanger_unsupported",
                              "motif_undeveloped"):
                bucket, section = setup, SEC_SETUP
            else:
                continue
            bucket.append(ContinuityFinding(
                section=section, title=issue.label, detail=issue.evidence,
                severity=issue.severity, episode=e.episode_label,
                thread=getattr(issue, "thread", ""),
                suggested_action=issue.suggested_action))
    return structure, abc, setup, timeline


def _timeline_findings(db, project_id: int, chain, events) -> list[ContinuityFinding]:
    from logosforge import story_structure as ss
    out: list[ContinuityFinding] = []
    try:
        order = ss.canonical_scene_order(db, project_id)
    except Exception:
        order = []
    if events:
        # Episodes with body but no Timeline link, while others are linked.
        linked_any = any(e.timeline_linked_count for e in chain)
        if linked_any:
            for e in chain:
                if e.body_scene_count and e.timeline_linked_count == 0:
                    out.append(ContinuityFinding(
                        section=SEC_TIMELINE,
                        title=f"{e.episode_label}: not linked to the Timeline",
                        detail="The Episode has written scenes but no Timeline event, "
                               "while other episodes do.", severity=SEV_WATCH,
                        episode=e.episode_label,
                        suggested_action="Link the Episode's scenes to Timeline "
                                         "events, or confirm they're off-timeline."))
    try:
        mode = db.get_timeline_order_mode(project_id)
        torder = list(db.get_timeline_order(project_id) or [])
    except Exception:
        mode, torder = "structural", []
    t_filtered = [s for s in torder if s in set(order)]
    if mode == "custom" and t_filtered and t_filtered != [
            s for s in order if s in set(t_filtered)]:
        out.append(ContinuityFinding(
            section=SEC_TIMELINE, title="Timeline order differs from structure",
            detail="The custom Timeline order doesn't match the Outline's "
                   "Season→Episode→Scene order (may be intentional).", severity=SEV_INFO,
            suggested_action="Confirm the divergence is intended."))
    # Canonical numbering for linked scenes (linked labels use the Outline numbers).
    if events and order:
        try:
            tree = ss.build_structure_tree(db, project_id)
            nums = ss.compute_structural_numbers(
                tree, ss.is_novel_project(db, project_id)).get("scenes", {})
            labels = [nums.get(s, "") for s in order if s in events and nums.get(s, "")]
            if labels:
                out.append(ContinuityFinding(
                    section=SEC_TIMELINE, title="Timeline-linked scenes (canonical)",
                    detail="Linked scenes: " + ", ".join(labels) + ".",
                    severity=SEV_INFO))
        except Exception:
            pass
    return out


def _psyke_notes_findings(db, project_id: int, episodes_data) -> list[ContinuityFinding]:
    out: list[ContinuityFinding] = []
    try:
        from logosforge.screenplay_diagnostics import _psyke_character_map
        psyke = _psyke_character_map(db, project_id)
    except Exception:
        psyke = {}
    if psyke:
        all_cues: set[str] = set()
        for entry, scenes, scripts, _w in episodes_data:
            for sc in scripts:
                all_cues |= set(sbk.character_cues(sc))
        for name in sorted(n for n in all_cues if n not in psyke):
            out.append(ContinuityFinding(
                section=SEC_PSYKE, title=f"{name} not in Story Bible",
                detail="Speaks across the series but has no PSYKE entry.",
                severity=SEV_INFO,
                suggested_action=f"Add {name} to PSYKE for continuity tracking."))
    try:
        linked = 0
        for entry, scenes, scripts, _w in episodes_data:
            for s in scenes:
                linked += len(db.get_scene_note_links(s.id) or [])
        if linked:
            out.append(ContinuityFinding(
                section=SEC_PSYKE, title="Scene-linked Notes present",
                detail=f"{linked} note link(s) across scenes — review for continuity "
                       "context.", severity=SEV_INFO))
    except Exception:
        pass
    return out


def _fold_cross_scene(db, project_id: int) -> dict[str, list[ContinuityFinding]]:
    out: dict[str, list[ContinuityFinding]] = {}
    try:
        from logosforge.continuity import build_continuity_report
        issues = build_continuity_report(db, project_id).open_issues()
    except Exception:
        return out
    for issue in issues:
        section = _DIMENSION_SECTION.get(
            (getattr(issue, "dimension", "") or "").lower(), SEC_CHARACTER)
        sev = {"blocking": SEV_WEAK, "warning": SEV_WATCH}.get(
            getattr(issue, "severity", ""), SEV_INFO)
        out.setdefault(section, []).append(ContinuityFinding(
            section=section, title=getattr(issue, "title", "Continuity issue"),
            detail=getattr(issue, "explanation", "") or getattr(issue, "title", ""),
            severity=sev,
            scene_ids=list(getattr(issue, "related_scene_ids", []) or []),
            suggested_action=getattr(issue, "suggested_action", "") or ""))
    return out


# ===========================================================================
# Builder (read-only)
# ===========================================================================


def build_series_continuity_report(db, project_id: int) -> SeriesContinuityReport:
    """Build the consolidated cross-episode Series continuity report. Read-only —
    never mutates Manuscript / Outline / Timeline / PSYKE / Notes; never calls the
    LLM."""
    report = SeriesContinuityReport(project_id=project_id)
    chain, episodes_data, events = _episode_chain(db, project_id)
    report.episode_chain = chain
    folded = _fold_cross_scene(db, project_id)

    report.season_overview = _season_overview(db, project_id, chain)
    report.season_overview += _season_alignment_findings(
        db, project_id, chain, episodes_data)
    report.progression = _progression_findings(episodes_data)
    report.abc_tracking = _abc_findings(chain)
    report.character_arc = _character_findings(episodes_data)
    report.character_arc += folded.get(SEC_CHARACTER, [])
    report.setup_payoff = _setup_payoff_findings(db, project_id)
    report.setup_payoff += folded.get(SEC_SETUP, [])

    structure, abc_ep, setup_ep, timeline_ep = _episode_structure_findings(
        db, project_id, chain)
    report.episode_structure = structure + folded.get(SEC_STRUCTURE, [])
    report.abc_tracking += abc_ep
    report.setup_payoff += setup_ep
    report.timeline_alignment = _timeline_findings(db, project_id, chain, events)
    report.timeline_alignment += timeline_ep + folded.get(SEC_TIMELINE, [])
    report.psyke_notes = _psyke_notes_findings(db, project_id, episodes_data)
    report.psyke_notes += folded.get(SEC_PSYKE, [])

    fixes: list[str] = []
    for f in sorted(report.all_findings(), key=lambda x: x.rank, reverse=True):
        if f.suggested_action:
            fixes.append(f.suggested_action)
    report.recommended_fixes = list(dict.fromkeys(fixes))[:12]

    report.metrics = {
        "episode_count": len(chain),
        "episodes_without_body": sum(1 for e in chain if e.body_scene_count == 0),
        "episodes_without_plan": sum(1 for e in chain if not e.has_episode_plan),
        "timeline_linked_episodes": sum(1 for e in chain if e.timeline_linked_count),
        "scene_count": sum(e.scene_count for e in chain),
        "finding_count": len(report.all_findings()),
    }
    return report


# ===========================================================================
# Optional AI seam + Note save
# ===========================================================================


def build_continuity_messages(report: SeriesContinuityReport) -> list[dict]:
    """Messages for an optional AI pass that *expands* the continuity report.
    Deterministic to build; the AI never rewrites, applies, or schedules."""
    system = (
        "You are a series continuity editor. Given a deterministic cross-episode "
        "continuity report, explain the most important serialized problems (arc "
        "coherence, A/B/C threads, setup/payoff, cliffhanger follow-through) and "
        "suggest concrete, non-destructive fixes. Do not rewrite scenes, do not "
        "apply changes, and do not produce production schedules, writers-room plans, "
        "or showrunner automation."
    )
    return [{"role": "system", "content": system},
            {"role": "user", "content": "Continuity report:\n" + report.to_text()}]


def save_continuity_as_note(db, project_id: int, report: SeriesContinuityReport, *,
                            confirmed: bool = False) -> dict:
    """Save the continuity report as a project Note. **Requires ``confirmed=True``.**"""
    if not confirmed:
        return {"ok": False,
                "error": "Saving a continuity note requires confirmation."}
    try:
        note = db.create_note(project_id, "Series Continuity Report",
                              report.to_text(), tags="continuity")
        return {"ok": True, "note_id": getattr(note, "id", note)}
    except Exception as exc:
        return {"ok": False, "error": f"Could not save note: {exc}"}
