"""Multi-scene Graphic Novel continuity / coherence (Phase 6).

A cross-scene consolidator: it does NOT re-implement analysis — it ties together
the deterministic engines already in the codebase into one structured,
writer-facing report about how the Graphic Novel scenes work *together*:

* canonical Act→Chapter→Scene chain (never id/created order),
* page/panel visual flow across scene boundaries (orientation, transitions),
* recurring visual motifs across scenes,
* setup/payoff + recurring objects (``logosforge.screenplay_setup_payoff`` +
  confirmed ``db.get_story_links``),
* cross-scene continuity issues (``logosforge.continuity``),
* Timeline alignment (linkage + order vs structure, canonical numbering),
* PSYKE / Notes consistency (speakers without a Story Bible entry).

Read-only and deterministic: no mutation of Manuscript / Outline / Timeline /
PSYKE / Notes, no LLM, no new persistent links this phase, and explicitly no
image generation / image prompts / ComfyUI. An optional AI pass may *expand* the
report; it never rewrites or applies. No API keys are read.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from logosforge import graphic_novel_blocks as gnb
from logosforge import graphic_novel_diagnostics as gd

# Section keys (canonical render order).
SEC_CHAIN = "Scene Chain Overview"
SEC_VISUAL_FLOW = "Visual Flow"
SEC_CHARACTER = "Character Continuity"
SEC_OBJECT_PLACE = "Object / Place Continuity"
SEC_MOTIF = "Motif / Echo Tracking"
SEC_SETUP_PAYOFF = "Setup / Payoff"
SEC_TIMELINE = "Timeline / Structure Alignment"
SEC_PSYKE = "PSYKE / Notes Consistency"
SEC_FIXES = "Recommended Fixes"

# Severity (shared vocabulary with Phase 3).
SEV_INFO = "info"
SEV_WATCH = "watch"
SEV_WEAK = "weak"
SEV_CRITICAL = "critical"
_SEV_RANK = {SEV_INFO: 0, SEV_WATCH: 1, SEV_WEAK: 2, SEV_CRITICAL: 3}

# Documented thresholds (conservative).
MOTIF_MIN_SCENES = 3       # a visual term in this many scenes reads as a motif
LONG_ABSENCE = 5           # scenes a character can vanish before we note the return
EMPTY_PANEL_RATIO = 0.5    # this share of empty/no-visual panels flags the scene

# Map the shared continuity engine's dimensions onto our cross-scene sections.
_DIMENSION_SECTION = {
    "character": SEC_CHARACTER,
    "temporal": SEC_TIMELINE,
    "object": SEC_OBJECT_PLACE,
    "spatial": SEC_OBJECT_PLACE,
    "theme": SEC_MOTIF,
    "plot": SEC_SETUP_PAYOFF,
    "dialogue": SEC_VISUAL_FLOW,
    "lore": SEC_PSYKE,
    "mode": SEC_VISUAL_FLOW,
    "production": SEC_VISUAL_FLOW,
}


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
class GNSceneChainEntry:
    scene_id: int
    number: str = ""
    title: str = ""
    purpose: str = ""
    page_count: int = 0
    panel_count: int = 0
    has_body: bool = False
    has_breakdown: bool = False
    has_plan: bool = False
    timeline_linked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"scene_id": self.scene_id, "number": self.number,
                "title": self.title, "purpose": self.purpose,
                "page_count": self.page_count, "panel_count": self.panel_count,
                "has_body": self.has_body, "has_breakdown": self.has_breakdown,
                "has_plan": self.has_plan, "timeline_linked": self.timeline_linked}


@dataclass
class GraphicNovelContinuityReport:
    project_id: int | None = None
    scene_chain: list[GNSceneChainEntry] = field(default_factory=list)
    visual_flow: list[ContinuityFinding] = field(default_factory=list)
    character_continuity: list[ContinuityFinding] = field(default_factory=list)
    object_place_continuity: list[ContinuityFinding] = field(default_factory=list)
    motif_echo: list[ContinuityFinding] = field(default_factory=list)
    setup_payoff: list[ContinuityFinding] = field(default_factory=list)
    timeline_alignment: list[ContinuityFinding] = field(default_factory=list)
    psyke_notes: list[ContinuityFinding] = field(default_factory=list)
    recommended_fixes: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def _sections(self):
        return (
            (SEC_VISUAL_FLOW, self.visual_flow),
            (SEC_CHARACTER, self.character_continuity),
            (SEC_OBJECT_PLACE, self.object_place_continuity),
            (SEC_MOTIF, self.motif_echo),
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
            "scene_chain": [s.to_dict() for s in self.scene_chain],
        }
        for header, findings in self._sections():
            out[header] = [f.to_dict() for f in findings]
        out["recommended_fixes"] = list(self.recommended_fixes)
        out["metrics"] = dict(self.metrics)
        return out

    def to_text(self) -> str:
        lines: list[str] = [
            f"Graphic Novel Continuity — {len(self.scene_chain)} scene(s)", ""]
        lines.append(SEC_CHAIN + ":")
        if self.scene_chain:
            for e in self.scene_chain:
                flags = []
                if not e.has_body:
                    flags.append("no body")
                if not e.has_breakdown:
                    flags.append("no breakdown")
                if not e.has_plan:
                    flags.append("no plan")
                if e.timeline_linked:
                    flags.append("timeline")
                tag = f"  [{', '.join(flags)}]" if flags else ""
                num = f"{e.number} " if e.number else ""
                counts = f" ({e.page_count}p/{e.panel_count}pan)"
                obj = f" — {e.purpose}" if e.purpose else ""
                lines.append(f"- {num}{e.title or 'Untitled'}{counts}{obj}{tag}")
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
# Small helpers
# ===========================================================================


def _dialogue_speaker(dialogue: str) -> str:
    s = (dialogue or "").strip()
    if ":" not in s:
        return ""
    name = s.split(":", 1)[0].strip()
    if name and len(name) <= 30 and re.search(r"[A-Za-z]", name):
        return name.upper()
    return ""


def _speakers(script: gnb.GraphicNovelScript) -> set[str]:
    out: set[str] = set()
    for page in script.pages:
        for panel in page.panels:
            name = _dialogue_speaker(panel.dialogue)
            if name:
                out.add(name)
    return out


def _visual_terms(script: gnb.GraphicNovelScript) -> set[str]:
    terms: set[str] = set()
    for page in script.pages:
        for panel in page.panels:
            terms |= {w for w in re.findall(r"[a-z']+", panel.visual_description.lower())
                      if len(w) > 4}
    return terms


def _has_turn(text: str) -> bool:
    low = (text or "").lower()
    return any(re.search(rf"\b{re.escape(m)}\b", low) for m in gd.TURN_MARKERS)


def _has_location(visual: str) -> bool:
    try:
        from logosforge.graphic_novel_reflection import _has_location as _hl
        return _hl(visual)
    except Exception:
        return False


def _all_panels(script: gnb.GraphicNovelScript) -> list[gnb.Panel]:
    return [pan for page in script.pages for pan in page.panels]


def _scene_metrics(script: gnb.GraphicNovelScript) -> dict:
    panels = _all_panels(script)
    n = len(panels)
    empty = sum(1 for p in panels if p.is_empty())
    no_visual = sum(1 for p in panels if not p.visual_description.strip())
    dlg_heavy = sum(1 for p in panels
                    if len(re.findall(r"\S+", p.dialogue)) >= gnb.DIALOGUE_HEAVY_WORDS)
    return {"panels": n, "empty": empty, "no_visual": no_visual,
            "dialogue_heavy": dlg_heavy}


# ===========================================================================
# Scene chain (canonical order — never id/created order)
# ===========================================================================


def _scene_chain(db, project_id: int):
    """Canonical Act→Chapter→Scene chain with structural numbers + GN per-scene
    state. Returns (chain, scripts_by_scene, char_by_scene, events)."""
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

    from logosforge import graphic_novel_pipeline as gp
    chain: list[GNSceneChainEntry] = []
    scripts_by_scene: dict[int, gnb.GraphicNovelScript] = {}
    char_by_scene: dict[int, set[str]] = {}
    for sid in order:
        scene = scenes_by_id.get(sid)
        if scene is None:
            continue
        script = gnb.parse_graphic_novel_text(getattr(scene, "content", "") or "")
        scripts_by_scene[sid] = script
        char_by_scene[sid] = _speakers(script)
        has_breakdown = has_plan = False
        try:
            bd = gp.get_page_breakdown(db, project_id, sid)
            has_breakdown = bd is not None and not bd.is_empty()
            pl = gp.get_panel_plan(db, project_id, sid)
            has_plan = pl is not None and not pl.is_empty()
        except Exception:
            pass
        chain.append(GNSceneChainEntry(
            scene_id=sid, number=numbers.get(sid, "") or "",
            title=(getattr(scene, "title", "") or "").strip(),
            purpose=(getattr(scene, "summary", "") or "").strip()[:120],
            page_count=len(script.pages), panel_count=script.panel_count(),
            has_body=script.panel_count() > 0, has_breakdown=has_breakdown,
            has_plan=has_plan, timeline_linked=sid in events))
    return chain, scripts_by_scene, char_by_scene, events


# ===========================================================================
# Section builders
# ===========================================================================


def _visual_flow_findings(chain, scripts_by_scene) -> list[ContinuityFinding]:
    out: list[ContinuityFinding] = []
    n_scenes = len(chain)
    for pos, e in enumerate(chain):
        script = scripts_by_scene.get(e.scene_id)
        if script is None:
            continue
        if not e.has_body:
            if e.has_breakdown or e.purpose:
                out.append(ContinuityFinding(
                    section=SEC_VISUAL_FLOW, title=f"{e.title or 'Scene'}: no page/panel body",
                    detail="The scene has a plan or summary but no drawn page/panel "
                           "script.", severity=SEV_WATCH, scene_ids=[e.scene_id],
                    suggested_action="Draft panels from the breakdown / plan."))
            continue
        m = _scene_metrics(script)
        if m["panels"] >= 2 and m["empty"] >= max(1, int(m["panels"] * EMPTY_PANEL_RATIO)):
            out.append(ContinuityFinding(
                section=SEC_VISUAL_FLOW, title=f"{e.title or 'Scene'}: many empty panels",
                detail=f"{m['empty']} of {m['panels']} panels are empty.",
                severity=SEV_WATCH, scene_ids=[e.scene_id],
                suggested_action="Fill or remove the empty panels."))
        if m["panels"] >= 2 and m["no_visual"] >= max(1, int(m["panels"] * EMPTY_PANEL_RATIO)):
            out.append(ContinuityFinding(
                section=SEC_VISUAL_FLOW,
                title=f"{e.title or 'Scene'}: most panels lack a visual",
                detail=f"{m['no_visual']} of {m['panels']} panels have no visual "
                       "description.", severity=SEV_WATCH, scene_ids=[e.scene_id],
                suggested_action="Give each panel a drawable visual."))
        panels = _all_panels(script)
        first = panels[0]
        if first.visual_description.strip() and not _has_location(first.visual_description):
            out.append(ContinuityFinding(
                section=SEC_VISUAL_FLOW,
                title=f"{e.title or 'Scene'}: opening doesn't orient the reader",
                detail="The first panel doesn't establish where the scene is.",
                severity=SEV_INFO, scene_ids=[e.scene_id],
                suggested_action="Establish the location in the opening panel."))
        # Weak final-panel transition (not for the last scene of the book).
        if pos < n_scenes - 1:
            last = panels[-1]
            momentum = bool(last.dialogue.strip() or last.sfx.strip()
                            or _has_turn(last.visual_description))
            if not momentum:
                out.append(ContinuityFinding(
                    section=SEC_VISUAL_FLOW,
                    title=f"{e.title or 'Scene'}: weak transition out of the scene",
                    detail="The final panel is static — it doesn't push toward the "
                           "next scene.", severity=SEV_INFO, scene_ids=[e.scene_id],
                    suggested_action="End on a beat, question, or reveal."))

    # Cross-scene bridges + dialogue-heavy chains.
    for pos in range(n_scenes - 1):
        a, b = chain[pos], chain[pos + 1]
        sa, sba = scripts_by_scene.get(a.scene_id), scripts_by_scene.get(b.scene_id)
        if not (a.has_body and b.has_body and sa and sba):
            continue
        a_panels, b_panels = _all_panels(sa), _all_panels(sba)
        if not (a_panels and b_panels):
            continue
        first_b = b_panels[0]
        bridge = (_visual_terms(gnb.GraphicNovelScript(pages=[gnb.Page(panels=[a_panels[-1]])]))
                  & _visual_terms(gnb.GraphicNovelScript(pages=[gnb.Page(panels=[first_b])])))
        share_char = _speakers(sa) & _speakers(sba)
        if not bridge and not share_char and not _has_location(first_b.visual_description):
            out.append(ContinuityFinding(
                section=SEC_VISUAL_FLOW,
                title=f"Abrupt transition: {a.title or 'scene'} → {b.title or 'scene'}",
                detail="The next scene opens with no shared location, character, or "
                       "visual bridge.", severity=SEV_INFO,
                scene_ids=[a.scene_id, b.scene_id],
                suggested_action="Add an orienting opening panel or a visual bridge."))

    # Consecutive all-dialogue scenes.
    heavy = [e.scene_id for e in chain
             if (m := _scene_metrics(scripts_by_scene.get(e.scene_id) or gnb.GraphicNovelScript()))
             ["panels"] >= 2 and m["dialogue_heavy"] == m["panels"]]
    if len(heavy) >= 2:
        out.append(ContinuityFinding(
            section=SEC_VISUAL_FLOW, title="Several dialogue-heavy scenes",
            detail=f"{len(heavy)} scenes are entirely dialogue-heavy — vary the "
                   "visual rhythm.", severity=SEV_WATCH, scene_ids=heavy,
            suggested_action="Add visual-action beats between talk-heavy scenes."))
    return out


def _character_findings(chain, char_by_scene) -> list[ContinuityFinding]:
    out: list[ContinuityFinding] = []
    order = [e.scene_id for e in chain]
    appears: dict[str, list[int]] = {}
    for pos, sid in enumerate(order):
        for name in char_by_scene.get(sid, set()):
            appears.setdefault(name, []).append(pos)
    for name, positions in appears.items():
        if len(positions) == 1 and len(order) >= 4:
            out.append(ContinuityFinding(
                section=SEC_CHARACTER, title=f"{name}: single appearance",
                detail="Speaks in only one scene across the graphic novel.",
                severity=SEV_INFO, scene_ids=[order[positions[0]]],
                suggested_action="Confirm the one-scene appearance is intended."))
        elif len(positions) >= 2:
            gap = max(b - a for a, b in zip(positions, positions[1:]))
            if gap >= LONG_ABSENCE:
                out.append(ContinuityFinding(
                    section=SEC_CHARACTER, title=f"{name}: long absence then return",
                    detail=f"Disappears for ~{gap} scenes, then returns — consider a "
                           "visual re-introduction.", severity=SEV_INFO,
                    suggested_action="Re-establish the character on return."))
    return out


def _object_place_findings(chain, scripts_by_scene) -> list[ContinuityFinding]:
    """Place-change orientation (conservative; objects handled by setup/payoff)."""
    out: list[ContinuityFinding] = []
    for pos in range(len(chain) - 1):
        a, b = chain[pos], chain[pos + 1]
        sa, sb = scripts_by_scene.get(a.scene_id), scripts_by_scene.get(b.scene_id)
        if not (a.has_body and b.has_body and sa and sb):
            continue
        b_first = _all_panels(sb)[0] if _all_panels(sb) else None
        if b_first is None:
            continue
        # A new scene whose opening gives no location at all is a spatial gap.
        if b_first.visual_description.strip() and not _has_location(b_first.visual_description):
            out.append(ContinuityFinding(
                section=SEC_OBJECT_PLACE,
                title=f"{b.title or 'Scene'}: place change without orientation",
                detail="The scene changes setting but its first panel doesn't show "
                       "where we now are.", severity=SEV_INFO,
                scene_ids=[b.scene_id],
                suggested_action="Open the scene with an establishing location."))
    return out


def _motif_findings(chain, scripts_by_scene) -> list[ContinuityFinding]:
    out: list[ContinuityFinding] = []
    term_scenes: dict[str, set[int]] = {}
    for e in chain:
        script = scripts_by_scene.get(e.scene_id)
        if script is None:
            continue
        for term in _visual_terms(script):
            term_scenes.setdefault(term, set()).add(e.scene_id)
    # Skip very common words; report only distinctive recurring terms.
    common = {"panel", "panels", "shot", "frame", "close", "background",
              "foreground", "image", "scene", "looking", "stands", "walks"}
    motifs = sorted((t for t, s in term_scenes.items()
                     if len(s) >= MOTIF_MIN_SCENES and t not in common),
                    key=lambda t: (-len(term_scenes[t]), t))
    for term in motifs[:8]:
        sids = sorted(term_scenes[term])
        out.append(ContinuityFinding(
            section=SEC_MOTIF, title=f"Recurring visual motif: “{term}”",
            detail=f"Appears in {len(sids)} scenes — confirm it builds toward a "
                   "payoff rather than repeating by accident.", severity=SEV_INFO,
            scene_ids=sids,
            suggested_action="Develop the motif or vary the repetition."))
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


def _timeline_findings(db, project_id: int, chain, events) -> list[ContinuityFinding]:
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
                   "Act→Chapter→Scene order (may be intentional for "
                   "non-chronological storytelling).", severity=SEV_INFO,
            suggested_action="Confirm the divergence is intended."))
    return out


def _psyke_notes_findings(db, project_id: int, chain, char_by_scene
                          ) -> list[ContinuityFinding]:
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
                detail="Speaks across the graphic novel but has no PSYKE entry.",
                severity=SEV_INFO,
                suggested_action=f"Add {name} to PSYKE for continuity tracking."))
    # Linked Notes (read-only inclusion, if any).
    try:
        linked = 0
        for e in chain:
            linked += len(db.get_scene_note_links(e.scene_id) or [])
        if linked:
            out.append(ContinuityFinding(
                section=SEC_PSYKE, title="Scene-linked Notes present",
                detail=f"{linked} note link(s) across scenes — review them for "
                       "continuity context.", severity=SEV_INFO))
    except Exception:
        pass
    return out


def _continuity_findings(db, project_id: int) -> dict[str, list[ContinuityFinding]]:
    """Fold the shared semantic continuity engine's open issues into our sections."""
    out: dict[str, list[ContinuityFinding]] = {}
    try:
        from logosforge.continuity import build_continuity_report
        report = build_continuity_report(db, project_id)
        issues = report.open_issues()
    except Exception:
        return out
    for issue in issues:
        section = _DIMENSION_SECTION.get(
            (getattr(issue, "dimension", "") or "").lower(), SEC_VISUAL_FLOW)
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


def build_graphic_novel_continuity_report(db, project_id: int
                                          ) -> GraphicNovelContinuityReport:
    """Build the consolidated multi-scene GN continuity report. Read-only."""
    report = GraphicNovelContinuityReport(project_id=project_id)
    chain, scripts_by_scene, char_by_scene, events = _scene_chain(db, project_id)
    report.scene_chain = chain
    folded = _continuity_findings(db, project_id)

    report.visual_flow = _visual_flow_findings(chain, scripts_by_scene)
    report.visual_flow += folded.get(SEC_VISUAL_FLOW, [])
    report.character_continuity = _character_findings(chain, char_by_scene)
    report.character_continuity += folded.get(SEC_CHARACTER, [])
    report.object_place_continuity = _object_place_findings(chain, scripts_by_scene)
    report.object_place_continuity += folded.get(SEC_OBJECT_PLACE, [])
    report.motif_echo = _motif_findings(chain, scripts_by_scene)
    report.motif_echo += folded.get(SEC_MOTIF, [])
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
        "scenes_without_breakdown": sum(1 for e in chain if not e.has_breakdown),
        "scenes_without_plan": sum(1 for e in chain if not e.has_plan),
        "timeline_linked": sum(1 for e in chain if e.timeline_linked),
        "total_pages": sum(e.page_count for e in chain),
        "total_panels": sum(e.panel_count for e in chain),
        "finding_count": len(report.all_findings()),
    }
    return report


# ===========================================================================
# Optional AI seam + Note save
# ===========================================================================


def build_continuity_messages(report: GraphicNovelContinuityReport) -> list[dict]:
    """Messages for an optional AI pass that *expands* the continuity report.
    Deterministic to build; the AI never rewrites, applies, or produces imagery."""
    system = (
        "You are a graphic novel continuity editor. Given a deterministic "
        "continuity report, explain the most important cross-scene problems and "
        "suggest concrete, non-destructive fixes. Do not rewrite scenes, do not "
        "apply changes, and do not produce image-generation prompts of any kind."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "Continuity report:\n" + report.to_text()},
    ]


def save_continuity_as_note(
    db, project_id: int, report: GraphicNovelContinuityReport, *,
    confirmed: bool = False,
) -> dict:
    """Save the continuity report as a project Note. **Requires ``confirmed=True``.**"""
    if not confirmed:
        return {"ok": False,
                "error": "Saving a continuity note requires confirmation."}
    try:
        note = db.create_note(project_id, "Graphic Novel Continuity Report",
                              report.to_text(), tags="continuity")
        return {"ok": True, "note_id": getattr(note, "id", note)}
    except Exception as exc:
        return {"ok": False, "error": f"Could not save note: {exc}"}
