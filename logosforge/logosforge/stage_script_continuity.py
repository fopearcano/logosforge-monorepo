"""Multi-scene Stage Script continuity / coherence (Phase 6).

A cross-scene consolidator: it does NOT re-implement analysis — it ties together
the deterministic engines already in the codebase into one structured,
writer-facing report about how the stage play works *together*:

* canonical Act→Chapter→Scene chain (never id/created order),
* character presence / entrances / exits across scene boundaries,
* blocking / movement continuity, props/set continuity, lighting/sound cue
  continuity (body vs the Blocking/Cue Plan),
* setup/payoff + recurring motifs (``screenplay_setup_payoff`` + story links),
* cross-scene continuity issues (``logosforge.continuity``),
* Timeline alignment (linkage + order vs structure, canonical numbering),
* PSYKE / Notes consistency.

Read-only and deterministic: no mutation of Manuscript / Outline / Timeline /
PSYKE / Notes, no LLM, no new persistent links this phase, and no image
generation. An optional AI pass may *expand* the report; it never rewrites or
applies. No API keys are read.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from logosforge import stage_script_blocks as ssb

# Section keys (canonical render order).
SEC_CHAIN = "Scene Chain Overview"
SEC_CHARACTER = "Character Presence / Entrances / Exits"
SEC_BLOCKING = "Blocking / Movement Continuity"
SEC_PROPS = "Props / Set Continuity"
SEC_CUES = "Lighting / Sound Cue Continuity"
SEC_SETUP_PAYOFF = "Dramaturgical Setup / Payoff"
SEC_TIMELINE = "Timeline / Structure Alignment"
SEC_PSYKE = "PSYKE / Notes Consistency"
SEC_FIXES = "Recommended Fixes"

SEV_INFO = "info"
SEV_WATCH = "watch"
SEV_WEAK = "weak"
SEV_CRITICAL = "critical"
_SEV_RANK = {SEV_INFO: 0, SEV_WATCH: 1, SEV_WEAK: 2, SEV_CRITICAL: 3}

MOTIF_MIN_SCENES = 3
LONG_ABSENCE = 5

_DIMENSION_SECTION = {
    "character": SEC_CHARACTER, "temporal": SEC_TIMELINE,
    "object": SEC_PROPS, "spatial": SEC_BLOCKING, "theme": SEC_SETUP_PAYOFF,
    "plot": SEC_SETUP_PAYOFF, "dialogue": SEC_CHARACTER, "lore": SEC_PSYKE,
    "mode": SEC_BLOCKING, "production": SEC_CUES,
}

_LOCATION_CUES = (" in ", " at ", " on ", "room", "stage", "hall", "garden",
                  "street", "house", "kitchen", "office", "forest", "field",
                  "throne", "interior", "exterior", "set", "door", "window")


@dataclass
class ContinuityFinding:
    section: str
    title: str
    detail: str = ""
    severity: str = SEV_INFO
    scene_ids: list[int] = field(default_factory=list)
    suggested_action: str = ""

    @property
    def rank(self) -> int:
        return _SEV_RANK.get(self.severity, 0)

    def to_dict(self) -> dict[str, Any]:
        return {"section": self.section, "title": self.title, "detail": self.detail,
                "severity": self.severity, "scene_ids": list(self.scene_ids),
                "suggested_action": self.suggested_action}


@dataclass
class StageSceneChainEntry:
    scene_id: int
    number: str = ""
    title: str = ""
    purpose: str = ""
    block_count: int = 0
    character_count: int = 0
    entrance_count: int = 0
    exit_count: int = 0
    has_body: bool = False
    has_beat_plan: bool = False
    has_blocking_plan: bool = False
    timeline_linked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"scene_id": self.scene_id, "number": self.number,
                "title": self.title, "purpose": self.purpose,
                "block_count": self.block_count,
                "character_count": self.character_count,
                "entrance_count": self.entrance_count, "exit_count": self.exit_count,
                "has_body": self.has_body, "has_beat_plan": self.has_beat_plan,
                "has_blocking_plan": self.has_blocking_plan,
                "timeline_linked": self.timeline_linked}


@dataclass
class StageScriptContinuityReport:
    project_id: int | None = None
    scene_chain: list[StageSceneChainEntry] = field(default_factory=list)
    character_continuity: list[ContinuityFinding] = field(default_factory=list)
    blocking_continuity: list[ContinuityFinding] = field(default_factory=list)
    props_set: list[ContinuityFinding] = field(default_factory=list)
    cue_continuity: list[ContinuityFinding] = field(default_factory=list)
    setup_payoff: list[ContinuityFinding] = field(default_factory=list)
    timeline_alignment: list[ContinuityFinding] = field(default_factory=list)
    psyke_notes: list[ContinuityFinding] = field(default_factory=list)
    recommended_fixes: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def _sections(self):
        return (
            (SEC_CHARACTER, self.character_continuity),
            (SEC_BLOCKING, self.blocking_continuity),
            (SEC_PROPS, self.props_set), (SEC_CUES, self.cue_continuity),
            (SEC_SETUP_PAYOFF, self.setup_payoff),
            (SEC_TIMELINE, self.timeline_alignment),
            (SEC_PSYKE, self.psyke_notes),
        )

    def all_findings(self) -> list[ContinuityFinding]:
        out: list[ContinuityFinding] = []
        for _, findings in self._sections():
            out.extend(findings)
        return out

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "project_id": self.project_id,
            "scene_chain": [s.to_dict() for s in self.scene_chain]}
        for header, findings in self._sections():
            out[header] = [f.to_dict() for f in findings]
        out["recommended_fixes"] = list(self.recommended_fixes)
        out["metrics"] = dict(self.metrics)
        return out

    def to_text(self) -> str:
        lines: list[str] = [
            f"Stage Script Continuity — {len(self.scene_chain)} scene(s)", ""]
        lines.append(SEC_CHAIN + ":")
        if self.scene_chain:
            for e in self.scene_chain:
                flags = []
                if not e.has_body:
                    flags.append("no body")
                if not e.has_beat_plan:
                    flags.append("no beat plan")
                if not e.has_blocking_plan:
                    flags.append("no blocking plan")
                if e.timeline_linked:
                    flags.append("timeline")
                tag = f"  [{', '.join(flags)}]" if flags else ""
                num = f"{e.number} " if e.number else ""
                obj = f" — {e.purpose}" if e.purpose else ""
                lines.append(f"- {num}{e.title or 'Untitled'}{obj}{tag}")
        else:
            lines.append("- No scenes.")
        for header, findings in self._sections():
            lines.append("")
            lines.append(header + ":")
            if findings:
                for f in sorted(findings, key=lambda x: x.rank, reverse=True):
                    lines.append(f"- [{f.severity}] {f.title} — {f.detail}")
            else:
                lines.append("- Nothing flagged.")
        lines.append("")
        lines.append(SEC_FIXES + ":")
        lines.extend(f"- {s}" for s in (self.recommended_fixes or ["None."]))
        return "\n".join(lines)


# ===========================================================================
# Helpers
# ===========================================================================


def _speakers(script: ssb.StageScript) -> list[str]:
    return ssb.character_cues(script)


def _entrance_blob(script: ssb.StageScript) -> str:
    return " ".join(b.text.lower() for b in script.blocks
                    if b.block_type == ssb.BT_ENTRANCE)


def _exit_blob(script: ssb.StageScript) -> str:
    return " ".join(b.text.lower() for b in script.blocks
                    if b.block_type == ssb.BT_EXIT)


def _terms(script: ssb.StageScript) -> set[str]:
    terms: set[str] = set()
    for b in script.blocks:
        if b.block_type in (ssb.BT_STAGE_DIRECTION, ssb.BT_SET_PROPS):
            terms |= {w for w in re.findall(r"[a-z']+", b.text.lower()) if len(w) > 4}
    return terms


def _has_location(text: str) -> bool:
    low = f" {(text or '').lower()} "
    return any(cue in low for cue in _LOCATION_CUES)


def _cue_types(script: ssb.StageScript) -> set[str]:
    out: set[str] = set()
    for b in script.blocks:
        if b.block_type == ssb.BT_LIGHTING_CUE:
            out.add("lighting")
        elif b.block_type == ssb.BT_SOUND_CUE:
            out.add("sound")
    return out


# ===========================================================================
# Scene chain
# ===========================================================================


def _scene_chain(db, project_id: int):
    from logosforge import story_structure as ss
    try:
        order = ss.canonical_scene_order(db, project_id)
        tree = ss.build_structure_tree(db, project_id)
        numbers = ss.compute_structural_numbers(
            tree, ss.is_novel_project(db, project_id)).get("scenes", {})
    except Exception:
        order, numbers = [], {}
    scenes_by_id = {s.id: s for s in db.get_all_scenes(project_id)}
    if not order:
        order = list(scenes_by_id.keys())
    try:
        events = db.get_timeline_event_ids(project_id) or set()
    except Exception:
        events = set()

    from logosforge import stage_script_pipeline as ssp
    chain: list[StageSceneChainEntry] = []
    scripts_by_scene: dict[int, ssb.StageScript] = {}
    char_by_scene: dict[int, set[str]] = {}
    for sid in order:
        scene = scenes_by_id.get(sid)
        if scene is None:
            continue
        script = ssb.parse_stage_script_text(getattr(scene, "content", "") or "")
        scripts_by_scene[sid] = script
        char_by_scene[sid] = set(_speakers(script))
        has_beat = has_blocking = False
        try:
            has_beat = ssp.has_beat_plan(db, project_id, sid)
            has_blocking = ssp.has_blocking_plan(db, project_id, sid)
        except Exception:
            pass
        chain.append(StageSceneChainEntry(
            scene_id=sid, number=numbers.get(sid, "") or "",
            title=(getattr(scene, "title", "") or "").strip(),
            purpose=(getattr(scene, "summary", "") or "").strip()[:120],
            block_count=len(script.blocks),
            character_count=len(char_by_scene[sid]),
            entrance_count=sum(1 for b in script.blocks
                               if b.block_type == ssb.BT_ENTRANCE),
            exit_count=sum(1 for b in script.blocks if b.block_type == ssb.BT_EXIT),
            has_body=len(script.blocks) > 0, has_beat_plan=has_beat,
            has_blocking_plan=has_blocking, timeline_linked=sid in events))
    return chain, scripts_by_scene, char_by_scene, events


# ===========================================================================
# Section builders
# ===========================================================================


def _character_findings(db, project_id, chain, scripts_by_scene, char_by_scene):
    out: list[ContinuityFinding] = []
    from logosforge import stage_script_pipeline as ssp

    # Per-scene: speaks-without-entrance + exit-then-acts.
    for e in chain:
        script = scripts_by_scene.get(e.scene_id)
        if script is None or not e.has_body:
            continue
        if e.entrance_count:
            enter_blob = _entrance_blob(script)
            for name in _speakers(script):
                if name.lower() not in enter_blob:
                    out.append(ContinuityFinding(
                        section=SEC_CHARACTER,
                        title=f"{name}: speaks without a shown entrance",
                        detail="The scene shows entrances, but this character "
                               "speaks with no entrance — clarify their presence.",
                        severity=SEV_INFO, scene_ids=[e.scene_id],
                        suggested_action=f"Add an entrance for {name}, or "
                                         "establish presence earlier."))
        # exit-then-acts: a character exits, then speaks again with no re-entry.
        exited: set[str] = set()
        for b in script.blocks:
            t = b.text.lower()
            if b.block_type == ssb.BT_EXIT:
                for name in char_by_scene.get(e.scene_id, set()):
                    if name.lower() in t:
                        exited.add(name)
            elif b.block_type == ssb.BT_ENTRANCE:
                for name in list(exited):
                    if name.lower() in t:
                        exited.discard(name)
            elif b.block_type == ssb.BT_DIALOGUE and b.character in exited:
                out.append(ContinuityFinding(
                    section=SEC_CHARACTER,
                    title=f"{b.character}: acts after exiting",
                    detail="The character exits, then speaks again with no "
                           "re-entrance.", severity=SEV_WATCH, scene_ids=[e.scene_id],
                    suggested_action=f"Add a re-entrance for {b.character} or "
                                     "remove the line."))
                exited.discard(b.character)

        # Planned entrances/exits absent from body.
        try:
            blocking = ssp.get_blocking_plan(db, project_id, e.scene_id)
        except Exception:
            blocking = None
        if blocking is not None and not blocking.is_empty():
            planned = [m for m in (blocking.entrance_exit_plan or []) if str(m).strip()]
            if planned and not (e.entrance_count or e.exit_count):
                out.append(ContinuityFinding(
                    section=SEC_CHARACTER,
                    title=f"{e.title or 'Scene'}: planned entrances/exits not staged",
                    detail="The blocking plan has entrance/exit moves the body "
                           "doesn't show.", severity=SEV_WATCH, scene_ids=[e.scene_id],
                    suggested_action="Add the planned entrances/exits, or update "
                                     "the plan."))

    # Cross-scene appearance signals.
    order = [e.scene_id for e in chain]
    appears: dict[str, list[int]] = {}
    for pos, sid in enumerate(order):
        for name in char_by_scene.get(sid, set()):
            appears.setdefault(name, []).append(pos)
    for name, positions in appears.items():
        if len(positions) == 1 and len(order) >= 4:
            out.append(ContinuityFinding(
                section=SEC_CHARACTER, title=f"{name}: single appearance",
                detail="Speaks in only one scene across the play.", severity=SEV_INFO,
                scene_ids=[order[positions[0]]],
                suggested_action="Confirm the one-scene appearance is intended."))
        elif len(positions) >= 2:
            gap = max(b - a for a, b in zip(positions, positions[1:]))
            if gap >= LONG_ABSENCE:
                out.append(ContinuityFinding(
                    section=SEC_CHARACTER, title=f"{name}: long absence then return",
                    detail=f"Disappears for ~{gap} scenes, then returns.",
                    severity=SEV_INFO,
                    suggested_action="Re-establish the character on return."))
    return out


def _blocking_findings(db, project_id, chain, scripts_by_scene):
    out: list[ContinuityFinding] = []
    from logosforge import stage_script_pipeline as ssp
    for e in chain:
        script = scripts_by_scene.get(e.scene_id)
        if script is None or not e.has_body:
            continue
        has_dialogue = any(b.block_type == ssb.BT_DIALOGUE for b in script.blocks)
        has_direction = any(b.block_type == ssb.BT_STAGE_DIRECTION
                            for b in script.blocks)
        if has_dialogue and not has_direction:
            out.append(ContinuityFinding(
                section=SEC_BLOCKING, title=f"{e.title or 'Scene'}: no stage directions",
                detail="Dialogue with no blocking — nothing to watch on stage.",
                severity=SEV_WATCH, scene_ids=[e.scene_id],
                suggested_action="Add blocking / business."))
        # Planned movement missing.
        try:
            blocking = ssp.get_blocking_plan(db, project_id, e.scene_id)
        except Exception:
            blocking = None
        if blocking is not None and not blocking.is_empty():
            moves = [m for m in (blocking.movement_beats or []) if str(m).strip()]
            if moves and not has_direction:
                out.append(ContinuityFinding(
                    section=SEC_BLOCKING,
                    title=f"{e.title or 'Scene'}: planned movement not staged",
                    detail="The blocking plan has movement beats the body doesn't "
                           "show.", severity=SEV_INFO, scene_ids=[e.scene_id],
                    suggested_action="Stage the planned movement, or update the plan."))

    # Set change without orientation: a scene whose first block doesn't orient.
    for pos in range(len(chain)):
        e = chain[pos]
        script = scripts_by_scene.get(e.scene_id)
        if script is None or not script.blocks:
            continue
        first = next((b for b in script.blocks
                      if b.block_type in (ssb.BT_SCENE_HEADING, ssb.BT_STAGE_DIRECTION,
                                          ssb.BT_SET_PROPS)), None)
        if pos > 0 and (first is None or not _has_location(first.text)):
            out.append(ContinuityFinding(
                section=SEC_BLOCKING,
                title=f"{e.title or 'Scene'}: opens without stage orientation",
                detail="The scene changes but its opening doesn't establish where "
                       "we now are.", severity=SEV_INFO, scene_ids=[e.scene_id],
                suggested_action="Open with a scene heading or an orienting "
                                 "stage direction."))
    return out


def _props_findings(db, project_id, chain, scripts_by_scene):
    out: list[ContinuityFinding] = []
    common = {"stage", "enters", "exits", "looks", "turns", "moves", "stands",
              "walks", "crosses", "lights", "sound"}
    term_scenes: dict[str, set[int]] = {}
    for e in chain:
        script = scripts_by_scene.get(e.scene_id)
        if script is None:
            continue
        for term in _terms(script):
            term_scenes.setdefault(term, set()).add(e.scene_id)
    motifs = sorted((t for t, s in term_scenes.items()
                     if len(s) >= MOTIF_MIN_SCENES and t not in common),
                    key=lambda t: (-len(term_scenes[t]), t))
    for term in motifs[:8]:
        sids = sorted(term_scenes[term])
        out.append(ContinuityFinding(
            section=SEC_PROPS, title=f"Recurring prop/set element: “{term}”",
            detail=f"Appears in {len(sids)} scenes — confirm it builds toward a "
                   "payoff.", severity=SEV_INFO, scene_ids=sids,
            suggested_action="Develop the element or cut the repetition."))
    return out


def _cue_findings(db, project_id, chain, scripts_by_scene):
    out: list[ContinuityFinding] = []
    from logosforge import stage_script_pipeline as ssp
    light_scenes: list[int] = []
    sound_scenes: list[int] = []
    for e in chain:
        script = scripts_by_scene.get(e.scene_id)
        if script is None or not e.has_body:
            continue
        types = _cue_types(script)
        if "lighting" in types:
            light_scenes.append(e.scene_id)
        if "sound" in types:
            sound_scenes.append(e.scene_id)
        # Planned cues absent from body.
        try:
            blocking = ssp.get_blocking_plan(db, project_id, e.scene_id)
        except Exception:
            blocking = None
        if blocking is not None and not blocking.is_empty():
            if [c for c in (blocking.lighting_cues or []) if str(c).strip()] \
                    and "lighting" not in types:
                out.append(ContinuityFinding(
                    section=SEC_CUES,
                    title=f"{e.title or 'Scene'}: planned lighting cue not staged",
                    detail="The blocking plan has lighting cues the body doesn't "
                           "show.", severity=SEV_INFO, scene_ids=[e.scene_id],
                    suggested_action="Add the lighting cue, or update the plan."))
            if [c for c in (blocking.sound_cues or []) if str(c).strip()] \
                    and "sound" not in types:
                out.append(ContinuityFinding(
                    section=SEC_CUES,
                    title=f"{e.title or 'Scene'}: planned sound cue not staged",
                    detail="The blocking plan has sound cues the body doesn't show.",
                    severity=SEV_INFO, scene_ids=[e.scene_id],
                    suggested_action="Add the sound cue, or update the plan."))
            if (blocking.transition_notes or "").strip() and not any(
                    b.block_type == ssb.BT_TRANSITION for b in script.blocks):
                out.append(ContinuityFinding(
                    section=SEC_CUES,
                    title=f"{e.title or 'Scene'}: planned transition/blackout not staged",
                    detail="The blocking plan notes a transition the body doesn't "
                           "show.", severity=SEV_INFO, scene_ids=[e.scene_id],
                    suggested_action="Add a transition/blackout, or update the plan."))
    if len(chain) >= 3 and len(light_scenes) == 1:
        out.append(ContinuityFinding(
            section=SEC_CUES, title="Lighting used in only one scene",
            detail="A lighting cue appears once and never returns.",
            severity=SEV_INFO, scene_ids=list(light_scenes)))
    if len(chain) >= 3 and len(sound_scenes) == 1:
        out.append(ContinuityFinding(
            section=SEC_CUES, title="Sound used in only one scene",
            detail="A sound cue appears once and never returns.",
            severity=SEV_INFO, scene_ids=list(sound_scenes)))
    return out


def _setup_payoff_findings(db, project_id: int) -> list[ContinuityFinding]:
    out: list[ContinuityFinding] = []
    try:
        from logosforge.screenplay_setup_payoff import analyze_setup_payoff
        rep = analyze_setup_payoff(db, project_id)
    except Exception:
        rep = None
    if rep is not None:
        for c in getattr(rep, "unresolved_setups", []) or []:
            out.append(ContinuityFinding(
                section=SEC_SETUP_PAYOFF, title="Setup without payoff",
                detail=f"{getattr(c, 'label', '')} — {getattr(c, 'evidence', '')}",
                severity=SEV_WATCH,
                scene_ids=[c.scene_id] if getattr(c, "scene_id", None) else [],
                suggested_action=getattr(c, "suggested_action", "")
                or "Plant a payoff or cut the setup."))
        for c in getattr(rep, "possible_payoffs", []) or []:
            out.append(ContinuityFinding(
                section=SEC_SETUP_PAYOFF, title="Possible payoff without a setup",
                detail=f"{getattr(c, 'label', '')} — {getattr(c, 'evidence', '')}",
                severity=SEV_INFO,
                scene_ids=[c.scene_id] if getattr(c, "scene_id", None) else [],
                suggested_action=getattr(c, "suggested_action", "")
                or "Confirm this is set up earlier."))
    try:
        confirmed = list(db.get_story_links(project_id, status="confirmed") or [])
    except Exception:
        confirmed = []
    for link in confirmed:
        ltype = getattr(link, "link_type", "") or "link"
        out.append(ContinuityFinding(
            section=SEC_SETUP_PAYOFF, title=f"Confirmed {ltype} link",
            detail=getattr(link, "label", "") or "Confirmed story link.",
            severity=SEV_INFO))
    return out


def _timeline_findings(db, project_id, chain, events):
    out: list[ContinuityFinding] = []
    if events:
        unlinked = [e for e in chain if not e.timeline_linked and e.has_body]
        if unlinked:
            out.append(ContinuityFinding(
                section=SEC_TIMELINE, title="Scenes not linked to the Timeline",
                detail=(f"{len(unlinked)} scene(s) have a body but no Timeline "
                        "event, while other scenes do."), severity=SEV_WATCH,
                scene_ids=[e.scene_id for e in unlinked],
                suggested_action="Link these scenes to Timeline events, or confirm "
                                 "they are intentionally off-timeline."))
    try:
        mode = db.get_timeline_order_mode(project_id)
        torder = list(db.get_timeline_order(project_id) or [])
    except Exception:
        mode, torder = "structural", []
    canonical = [e.scene_id for e in chain]
    t_filtered = [s for s in torder if s in set(canonical)]
    if mode == "custom" and t_filtered and t_filtered != [
            s for s in canonical if s in set(t_filtered)]:
        out.append(ContinuityFinding(
            section=SEC_TIMELINE, title="Timeline order differs from structure",
            detail="The custom Timeline order doesn't match the Outline's "
                   "Act→Chapter→Scene order (may be intentional).", severity=SEV_INFO,
            suggested_action="Confirm the divergence is intended."))
    return out


def _psyke_notes_findings(db, project_id, chain, char_by_scene):
    out: list[ContinuityFinding] = []
    try:
        from logosforge.screenplay_diagnostics import _psyke_character_map
        psyke = _psyke_character_map(db, project_id)
    except Exception:
        psyke = {}
    if psyke:
        all_cues: set[str] = set()
        for cues in char_by_scene.values():
            all_cues |= cues
        for name in sorted(n for n in all_cues if n not in psyke):
            out.append(ContinuityFinding(
                section=SEC_PSYKE, title=f"{name} not in Story Bible",
                detail="Speaks across the play but has no PSYKE entry.",
                severity=SEV_INFO,
                suggested_action=f"Add {name} to PSYKE for continuity tracking."))
    try:
        linked = sum(len(db.get_scene_note_links(e.scene_id) or []) for e in chain)
        if linked:
            out.append(ContinuityFinding(
                section=SEC_PSYKE, title="Scene-linked Notes present",
                detail=f"{linked} note link(s) across scenes — review for "
                       "continuity context.", severity=SEV_INFO))
    except Exception:
        pass
    return out


def _continuity_findings(db, project_id: int) -> dict[str, list[ContinuityFinding]]:
    out: dict[str, list[ContinuityFinding]] = {}
    try:
        from logosforge.continuity import build_continuity_report
        report = build_continuity_report(db, project_id)
        issues = report.open_issues()
    except Exception:
        return out
    for issue in issues:
        section = _DIMENSION_SECTION.get(
            (getattr(issue, "dimension", "") or "").lower(), SEC_BLOCKING)
        sev = getattr(issue, "severity", "")
        sev = {"blocking": SEV_WEAK, "warning": SEV_WATCH}.get(sev, SEV_INFO)
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


def build_stage_script_continuity_report(db, project_id: int
                                         ) -> StageScriptContinuityReport:
    """Build the consolidated multi-scene Stage Script continuity report. Read-only."""
    report = StageScriptContinuityReport(project_id=project_id)
    chain, scripts_by_scene, char_by_scene, events = _scene_chain(db, project_id)
    report.scene_chain = chain
    folded = _continuity_findings(db, project_id)

    report.character_continuity = _character_findings(
        db, project_id, chain, scripts_by_scene, char_by_scene)
    report.character_continuity += folded.get(SEC_CHARACTER, [])
    report.blocking_continuity = _blocking_findings(db, project_id, chain,
                                                    scripts_by_scene)
    report.blocking_continuity += folded.get(SEC_BLOCKING, [])
    report.props_set = _props_findings(db, project_id, chain, scripts_by_scene)
    report.props_set += folded.get(SEC_PROPS, [])
    report.cue_continuity = _cue_findings(db, project_id, chain, scripts_by_scene)
    report.cue_continuity += folded.get(SEC_CUES, [])
    report.setup_payoff = _setup_payoff_findings(db, project_id)
    report.setup_payoff += folded.get(SEC_SETUP_PAYOFF, [])
    report.timeline_alignment = _timeline_findings(db, project_id, chain, events)
    report.timeline_alignment += folded.get(SEC_TIMELINE, [])
    report.psyke_notes = _psyke_notes_findings(db, project_id, chain, char_by_scene)
    report.psyke_notes += folded.get(SEC_PSYKE, [])

    fixes: list[str] = []
    for f in sorted(report.all_findings(), key=lambda x: x.rank, reverse=True):
        if f.suggested_action:
            fixes.append(f.suggested_action)
    report.recommended_fixes = list(dict.fromkeys(fixes))[:12]

    report.metrics = {
        "scene_count": len(chain),
        "scenes_without_body": sum(1 for e in chain if not e.has_body),
        "scenes_without_beat_plan": sum(1 for e in chain if not e.has_beat_plan),
        "scenes_without_blocking_plan": sum(1 for e in chain
                                            if not e.has_blocking_plan),
        "timeline_linked": sum(1 for e in chain if e.timeline_linked),
        "total_entrances": sum(e.entrance_count for e in chain),
        "total_exits": sum(e.exit_count for e in chain),
        "finding_count": len(report.all_findings()),
    }
    return report


# ===========================================================================
# Optional AI seam + Note save
# ===========================================================================


def build_continuity_messages(report: StageScriptContinuityReport) -> list[dict]:
    """Messages for an optional AI pass that *expands* the continuity report.
    Deterministic to build; the AI never rewrites, applies, or schedules."""
    system = (
        "You are a stage-play continuity editor. Given a deterministic continuity "
        "report, explain the most important cross-scene problems and suggest "
        "concrete, non-destructive fixes. Do not rewrite scenes, do not apply "
        "changes, and do not produce production schedules or diagrams."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "Continuity report:\n" + report.to_text()},
    ]


def save_continuity_as_note(
    db, project_id: int, report: StageScriptContinuityReport, *,
    confirmed: bool = False,
) -> dict:
    """Save the continuity report as a project Note. **Requires ``confirmed=True``.**"""
    if not confirmed:
        return {"ok": False,
                "error": "Saving a continuity note requires confirmation."}
    try:
        note = db.create_note(project_id, "Stage Script Continuity Report",
                              report.to_text(), tags="continuity")
        return {"ok": True, "note_id": getattr(note, "id", note)}
    except Exception as exc:
        return {"ok": False, "error": f"Could not save note: {exc}"}
