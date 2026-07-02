"""Multi-scene screenplay continuity / coherence (Phase 7).

A cross-scene consolidator: it does NOT re-implement analysis — it ties together
the deterministic engines already in the codebase into one structured,
writer-facing report about how the scenes work *together*:

* canonical Act→Chapter→Scene chain (never id/created order),
* causal flow + character/temporal continuity (``logosforge.continuity``),
* setup/payoff + recurring motifs (``logosforge.screenplay_setup_payoff``),
* confirmed story links (``db.get_story_links``),
* Timeline alignment (linkage + order vs structure),
* PSYKE consistency (character cues without a Story Bible entry).

Read-only and deterministic: no mutation of Manuscript / Outline / Timeline /
PSYKE / Notes, no LLM, no new persistent links this phase. An optional AI pass
may *expand* the report; it never rewrites or applies. No API keys are read.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from logosforge import screenplay_blocks as sb

# Section keys (canonical render order).
SEC_CHAIN = "Scene Chain Overview"
SEC_CAUSAL = "Causal Flow"
SEC_SETUP_PAYOFF = "Setup / Payoff"
SEC_CHARACTER = "Character Continuity"
SEC_TIMELINE = "Timeline / Structure Alignment"
SEC_PSYKE = "PSYKE Consistency"
SEC_FIXES = "Recommended Fixes"

# Severity (shared vocabulary with Phase 3).
SEV_INFO = "info"
SEV_WATCH = "watch"
SEV_WEAK = "weak"
SEV_CRITICAL = "critical"
_SEV_RANK = {SEV_INFO: 0, SEV_WATCH: 1, SEV_WEAK: 2, SEV_CRITICAL: 3}

# Map the continuity engine's dimensions onto our cross-scene sections.
_DIMENSION_SECTION = {
    "character": SEC_CHARACTER,
    "temporal": SEC_TIMELINE,
    "object": SEC_SETUP_PAYOFF,
    "theme": SEC_SETUP_PAYOFF,
    "plot": SEC_CAUSAL,
    "spatial": SEC_CAUSAL,
    "dialogue": SEC_CAUSAL,
    "lore": SEC_PSYKE,
    "mode": SEC_CAUSAL,
    "production": SEC_CAUSAL,
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
class SceneChainEntry:
    scene_id: int
    number: str = ""
    title: str = ""
    objective: str = ""
    has_body: bool = False
    has_beat_plan: bool = False
    timeline_linked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"scene_id": self.scene_id, "number": self.number,
                "title": self.title, "objective": self.objective,
                "has_body": self.has_body, "has_beat_plan": self.has_beat_plan,
                "timeline_linked": self.timeline_linked}


@dataclass
class ScreenplayContinuityReport:
    project_id: int | None = None
    scene_chain: list[SceneChainEntry] = field(default_factory=list)
    causal_flow: list[ContinuityFinding] = field(default_factory=list)
    setup_payoff: list[ContinuityFinding] = field(default_factory=list)
    character_continuity: list[ContinuityFinding] = field(default_factory=list)
    timeline_alignment: list[ContinuityFinding] = field(default_factory=list)
    psyke_consistency: list[ContinuityFinding] = field(default_factory=list)
    recommended_fixes: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def all_findings(self) -> list[ContinuityFinding]:
        return (self.causal_flow + self.setup_payoff + self.character_continuity
                + self.timeline_alignment + self.psyke_consistency)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "scene_chain": [s.to_dict() for s in self.scene_chain],
            "causal_flow": [f.to_dict() for f in self.causal_flow],
            "setup_payoff": [f.to_dict() for f in self.setup_payoff],
            "character_continuity": [f.to_dict() for f in self.character_continuity],
            "timeline_alignment": [f.to_dict() for f in self.timeline_alignment],
            "psyke_consistency": [f.to_dict() for f in self.psyke_consistency],
            "recommended_fixes": list(self.recommended_fixes),
            "metrics": dict(self.metrics),
        }

    def to_text(self) -> str:
        lines: list[str] = [f"Screenplay Continuity — {len(self.scene_chain)} scene(s)", ""]
        lines.append(SEC_CHAIN + ":")
        if self.scene_chain:
            for e in self.scene_chain:
                flags = []
                if not e.has_body:
                    flags.append("no body")
                if not e.has_beat_plan:
                    flags.append("no beat plan")
                if e.timeline_linked:
                    flags.append("timeline")
                tag = f"  [{', '.join(flags)}]" if flags else ""
                num = f"{e.number} " if e.number else ""
                obj = f" — {e.objective}" if e.objective else ""
                lines.append(f"- {num}{e.title or 'Untitled'}{obj}{tag}")
        else:
            lines.append("- No scenes.")

        for header, findings in (
            (SEC_CAUSAL, self.causal_flow),
            (SEC_SETUP_PAYOFF, self.setup_payoff),
            (SEC_CHARACTER, self.character_continuity),
            (SEC_TIMELINE, self.timeline_alignment),
            (SEC_PSYKE, self.psyke_consistency),
        ):
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
# Builder (read-only)
# ===========================================================================


def _scene_chain(db, project_id: int):
    """Canonical Act→Chapter→Scene chain with structural numbers. Never sorts by
    id/created_at."""
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
    try:
        from logosforge.screenplay_pipeline import has_beat_plan
    except Exception:
        has_beat_plan = lambda *a, **k: False  # noqa: E731

    chain: list[SceneChainEntry] = []
    char_by_scene: dict[int, set[str]] = {}
    for sid in order:
        scene = scenes_by_id.get(sid)
        if scene is None:
            continue
        content = getattr(scene, "content", "") or ""
        blocks = sb.parse_screenplay_text(content, scene_id=sid)
        char_by_scene[sid] = set(sb.character_cues(blocks))
        objective = ""
        try:
            from logosforge.screenplay_pipeline import get_beat_plan
            plan = get_beat_plan(db, project_id, sid)
            if plan is not None:
                objective = (plan.objective or "").strip()
        except Exception:
            objective = ""
        if not objective:
            objective = (getattr(scene, "summary", "") or "").strip()
        chain.append(SceneChainEntry(
            scene_id=sid, number=numbers.get(sid, "") or "",
            title=(getattr(scene, "title", "") or "").strip(),
            objective=objective[:120],
            has_body=bool(content.strip()),
            has_beat_plan=bool(has_beat_plan(db, project_id, sid)),
            timeline_linked=sid in events))
    return chain, char_by_scene, events


def _continuity_findings(db, project_id: int) -> dict[str, list[ContinuityFinding]]:
    """Fold the semantic continuity engine's open issues into our sections."""
    out: dict[str, list[ContinuityFinding]] = {}
    try:
        from logosforge.continuity import build_continuity_report
        report = build_continuity_report(db, project_id)
        issues = report.open_issues()
    except Exception:
        return out
    for issue in issues:
        section = _DIMENSION_SECTION.get(
            (getattr(issue, "dimension", "") or "").lower(), SEC_CAUSAL)
        sev = getattr(issue, "severity", "")
        sev = {"blocking": SEV_WEAK, "warning": SEV_WATCH}.get(sev, SEV_INFO)
        out.setdefault(section, []).append(ContinuityFinding(
            section=section, title=getattr(issue, "title", "Continuity issue"),
            detail=getattr(issue, "explanation", "") or getattr(issue, "title", ""),
            severity=sev,
            scene_ids=list(getattr(issue, "related_scene_ids", []) or []),
            suggested_action=getattr(issue, "suggested_action", "") or ""))
    return out


def _setup_payoff_findings(db, project_id: int) -> list[ContinuityFinding]:
    out: list[ContinuityFinding] = []
    try:
        from logosforge.screenplay_setup_payoff import analyze_setup_payoff
        rep = analyze_setup_payoff(db, project_id)
    except Exception:
        return out
    for c in rep.unresolved_setups:
        out.append(ContinuityFinding(
            section=SEC_SETUP_PAYOFF, title="Setup without payoff",
            detail=f"{c.label} — {c.evidence}", severity=SEV_WATCH,
            scene_ids=[c.scene_id] if c.scene_id else [],
            suggested_action=c.suggested_action or "Plant a payoff or cut the setup."))
    for c in rep.possible_payoffs:
        out.append(ContinuityFinding(
            section=SEC_SETUP_PAYOFF, title="Possible payoff without a setup",
            detail=f"{c.label} — {c.evidence}", severity=SEV_INFO,
            scene_ids=[c.scene_id] if c.scene_id else [],
            suggested_action=c.suggested_action or "Confirm this is set up earlier."))
    for c in rep.recurring_motifs:
        out.append(ContinuityFinding(
            section=SEC_SETUP_PAYOFF, title="Recurring motif (unclear function)",
            detail=f"{c.label} — {c.evidence}", severity=SEV_INFO,
            scene_ids=[c.scene_id] if c.scene_id else []))
    # Confirmed story links (causes/setup/payoff) — report-only inclusion.
    try:
        confirmed = list(db.get_story_links(project_id, status="confirmed") or [])
        confirmed += list(db.get_story_links(project_id, status="resolved") or [])
    except Exception:
        confirmed = []
    for link in confirmed:
        ltype = (getattr(link, "link_type", "") or "link")
        out.append(ContinuityFinding(
            section=SEC_SETUP_PAYOFF, title=f"Confirmed {ltype} link",
            detail=(getattr(link, "label", "") or "Confirmed story link."),
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
    # Custom Timeline order that diverges from canonical structure order.
    try:
        mode = db.get_timeline_order_mode(project_id)
        torder = [s for s in (db.get_timeline_order(project_id) or [])]
    except Exception:
        mode, torder = "structural", []
    canonical = [e.scene_id for e in chain]
    t_filtered = [s for s in torder if s in set(canonical)]
    if mode == "custom" and t_filtered and t_filtered != [
            s for s in canonical if s in set(t_filtered)]:
        out.append(ContinuityFinding(
            section=SEC_TIMELINE, title="Timeline order differs from structure",
            detail="The custom Timeline order does not match the Outline's "
                   "Act→Chapter→Scene order (this may be intentional for "
                   "non-chronological storytelling).", severity=SEV_INFO,
            suggested_action="Confirm the divergence is intended."))
    return out


def _character_findings(chain, char_by_scene) -> list[ContinuityFinding]:
    """Light, honest cross-scene character-appearance signals."""
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
                detail="Speaks in only one scene across the screenplay.",
                severity=SEV_INFO,
                scene_ids=[order[positions[0]]],
                suggested_action="Confirm the one-scene appearance is intended."))
        elif len(positions) >= 2:
            gap = max(b - a for a, b in zip(positions, positions[1:]))
            if gap >= 5:
                out.append(ContinuityFinding(
                    section=SEC_CHARACTER, title=f"{name}: long absence then return",
                    detail=f"Disappears for ~{gap} scenes, then returns.",
                    severity=SEV_INFO,
                    suggested_action="Check the return is set up / not jarring."))
    return out


def _psyke_findings(db, project_id: int, char_by_scene) -> list[ContinuityFinding]:
    out: list[ContinuityFinding] = []
    try:
        from logosforge.screenplay_diagnostics import _psyke_character_map
        psyke = _psyke_character_map(db, project_id)
    except Exception:
        psyke = {}
    if not psyke:
        return out  # no Story Bible to compare against — never assert "missing"
    all_cues: set[str] = set()
    for cues in char_by_scene.values():
        all_cues |= cues
    missing = sorted(n for n in all_cues if n not in psyke)
    for name in missing:
        out.append(ContinuityFinding(
            section=SEC_PSYKE, title=f"{name} not in Story Bible",
            detail="Speaks across the screenplay but has no PSYKE entry.",
            severity=SEV_INFO,
            suggested_action=f"Add {name} to PSYKE for continuity tracking."))
    return out


def build_screenplay_continuity_report(db, project_id: int) -> ScreenplayContinuityReport:
    """Build the consolidated multi-scene continuity report. Read-only."""
    report = ScreenplayContinuityReport(project_id=project_id)
    chain, char_by_scene, events = _scene_chain(db, project_id)
    report.scene_chain = chain

    folded = _continuity_findings(db, project_id)
    report.causal_flow = folded.get(SEC_CAUSAL, [])
    report.character_continuity = folded.get(SEC_CHARACTER, [])
    report.character_continuity += _character_findings(chain, char_by_scene)
    report.setup_payoff = _setup_payoff_findings(db, project_id)
    report.setup_payoff += folded.get(SEC_SETUP_PAYOFF, [])
    report.timeline_alignment = _timeline_findings(db, project_id, chain, events)
    report.timeline_alignment += folded.get(SEC_TIMELINE, [])
    report.psyke_consistency = _psyke_findings(db, project_id, char_by_scene)
    report.psyke_consistency += folded.get(SEC_PSYKE, [])

    # Recommended fixes: dedup suggested actions across sections, worst-first.
    fixes: list[str] = []
    for f in sorted(report.all_findings(), key=lambda x: x.rank, reverse=True):
        if f.suggested_action:
            fixes.append(f.suggested_action)
    report.recommended_fixes = list(dict.fromkeys(fixes))[:12]

    report.metrics = {
        "scene_count": len(chain),
        "scenes_without_body": sum(1 for e in chain if not e.has_body),
        "scenes_without_beat_plan": sum(1 for e in chain if not e.has_beat_plan),
        "timeline_linked": sum(1 for e in chain if e.timeline_linked),
        "finding_count": len(report.all_findings()),
    }
    return report


# ===========================================================================
# Optional AI seam + Note save
# ===========================================================================


def build_continuity_messages(report: ScreenplayContinuityReport) -> list[dict]:
    """Messages for an optional AI pass that *expands* the continuity report.
    Deterministic to build; the AI never rewrites or applies."""
    system = (
        "You are a screenplay continuity editor. Given a deterministic continuity "
        "report, explain the most important cross-scene problems and suggest "
        "concrete, non-destructive fixes. Do not rewrite scenes or apply changes."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "Continuity report:\n" + report.to_text()},
    ]


def save_continuity_as_note(
    db, project_id: int, report: ScreenplayContinuityReport, *, confirmed: bool = False,
) -> dict:
    """Save the continuity report as a project Note. **Requires ``confirmed=True``.**"""
    if not confirmed:
        return {"ok": False, "error": "Saving a continuity note requires confirmation."}
    try:
        note = db.create_note(project_id, "Screenplay Continuity Report",
                              report.to_text(), tags="continuity")
        return {"ok": True, "note_id": getattr(note, "id", note)}
    except Exception as exc:
        return {"ok": False, "error": f"Could not save note: {exc}"}
