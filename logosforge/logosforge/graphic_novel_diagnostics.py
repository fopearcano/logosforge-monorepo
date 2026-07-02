"""Deterministic Graphic Novel page/panel script intelligence (Phase 3).

Evaluates a Graphic Novel *Scene* (its page/panel script body) as a comic script —
panel structure, visual clarity, dialogue/caption balance, page flow, dramatic
function, plan alignment, and PSYKE continuity — with conservative, rule-based
heuristics. Mirrors ``screenplay_diagnostics``.

This is a WRITING checker, not an image-production tool: it evaluates script
clarity only. No image generation, no image prompts, no ComfyUI, no render/model
fields. No LLM, no DB writes, no Qt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from logosforge import graphic_novel_blocks as gnb

# Severity (shared scale with screenplay diagnostics).
SEV_INFO = "info"
SEV_WATCH = "watch"
SEV_WEAK = "weak"
SEV_CRITICAL = "critical"
_SEV_RANK = {SEV_INFO: 0, SEV_WATCH: 1, SEV_WEAK: 2, SEV_CRITICAL: 3}

# Categories (canonical render order).
CAT_STRUCTURE = "Panel Structure"
CAT_VISUAL = "Visual Clarity"
CAT_BALANCE = "Dialogue / Caption Balance"
CAT_FLOW = "Page Flow"
CAT_DRAMATIC = "Dramatic Function"
CAT_ALIGNMENT = "Plan Alignment"
CAT_CONTINUITY = "Continuity / PSYKE"
_CATEGORY_ORDER = (CAT_STRUCTURE, CAT_VISUAL, CAT_BALANCE, CAT_FLOW,
                   CAT_DRAMATIC, CAT_ALIGNMENT, CAT_CONTINUITY)

# Documented thresholds.
PANELS_PER_PAGE_HIGH = 9       # a page this dense is hard to read
PANELS_PER_PAGE_LOW = 1        # a multi-page scene with single-panel pages
VAGUE_VISUAL_WORDS = 3         # a visual description this short is likely vague
DIALOGUE_HEAVY_WORDS = gnb.DIALOGUE_HEAVY_WORDS
CAPTION_LONG_WORDS = gnb.CAPTION_LONG_WORDS
SFX_LONG_CHARS = gnb.SFX_LONG_CHARS

# Internal-state vocabulary — comics must *show*, so emotion in a visual should
# read as visible behavior, not narrated interiority.
INTERNAL_STATE_WORDS = (
    "thinks", "think", "feels", "feel", "felt", "realizes", "realises",
    "remembers", "knows", "understands", "wonders", "hopes", "wishes",
)
OBJECTIVE_MARKERS = (
    "want", "wants", "need", "needs", "must", "trying to", "going to",
    "has to", "have to", "to find", "to stop", "to save", "to escape",
)
TURN_MARKERS = (
    "but", "however", "suddenly", "then", "finally", "until", "instead",
    "no longer", "everything changes", "reveal", "twist",
)
CONFLICT_WORDS = (
    "but", "no", "won't", "wont", "refuse", "stop", "against", "fight",
    "argue", "threat", "can't", "cant", "struggle", "block", "attack",
)


def _words(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def _content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z']+", (text or "").lower()) if len(w) > 3}


def _dialogue_speaker(dialogue: str) -> str:
    """Extract an uppercased speaker name from 'NAME: line', else ''."""
    s = (dialogue or "").strip()
    if ":" not in s:
        return ""
    name = s.split(":", 1)[0].strip()
    if name and len(name) <= 30 and re.search(r"[A-Za-z]", name):
        return name.upper()
    return ""


@dataclass
class GraphicNovelDiagnosticIssue:
    id: str
    label: str
    category: str
    severity: str = SEV_INFO
    evidence: str = ""
    page_number: int | None = None
    panel_number: int | None = None
    suggested_action: str = ""

    @property
    def severity_rank(self) -> int:
        return _SEV_RANK.get(self.severity, 0)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label, "category": self.category,
                "severity": self.severity, "evidence": self.evidence,
                "page_number": self.page_number, "panel_number": self.panel_number,
                "suggested_action": self.suggested_action}


@dataclass
class GraphicNovelSceneReport:
    scene_id: int | None = None
    total_pages: int = 0
    total_panels: int = 0
    avg_panels_per_page: float = 0.0
    panels_without_visual: int = 0
    empty_panels: int = 0
    dialogue_heavy_panels: int = 0
    caption_heavy_panels: int = 0
    sfx_count: int = 0
    visual_word_count: int = 0
    dialogue_word_count: int = 0
    caption_word_count: int = 0
    issues: list[GraphicNovelDiagnosticIssue] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    confidence: float = 0.0
    summary: str = ""

    def top_issues(self, n: int = 5) -> list[GraphicNovelDiagnosticIssue]:
        return sorted(self.issues, key=lambda i: (i.severity_rank, i.label),
                      reverse=True)[:n]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id, "total_pages": self.total_pages,
            "total_panels": self.total_panels,
            "avg_panels_per_page": self.avg_panels_per_page,
            "panels_without_visual": self.panels_without_visual,
            "empty_panels": self.empty_panels,
            "dialogue_heavy_panels": self.dialogue_heavy_panels,
            "caption_heavy_panels": self.caption_heavy_panels,
            "sfx_count": self.sfx_count, "visual_word_count": self.visual_word_count,
            "dialogue_word_count": self.dialogue_word_count,
            "caption_word_count": self.caption_word_count,
            "issues": [i.to_dict() for i in self.issues],
            "strengths": list(self.strengths),
            "confidence": round(self.confidence, 2), "summary": self.summary,
        }


def group_issues_by_category(
    report: GraphicNovelSceneReport,
) -> dict[str, list[GraphicNovelDiagnosticIssue]]:
    grouped: dict[str, list[GraphicNovelDiagnosticIssue]] = {}
    for issue in report.issues:
        grouped.setdefault(issue.category, []).append(issue)
    return {k: grouped[k] for k in _CATEGORY_ORDER if k in grouped}


# ===========================================================================
# Core analysis (pure: operates on a parsed GraphicNovelScript)
# ===========================================================================


def analyze_scene(
    script: gnb.GraphicNovelScript, *, scene_id: int | None = None,
    outline_summary: str = "", breakdown: Any | None = None,
    plan: Any | None = None, psyke_characters: dict[str, bool] | None = None,
) -> GraphicNovelSceneReport:
    """Deterministically analyze one Graphic Novel scene's page/panel script."""
    report = GraphicNovelSceneReport(scene_id=scene_id)
    psyke_characters = psyke_characters or {}
    issues: list[GraphicNovelDiagnosticIssue] = []

    pages = script.pages if script else []
    report.total_pages = len(pages)
    report.total_panels = sum(len(p.panels) for p in pages)
    report.avg_panels_per_page = (round(report.total_panels / len(pages), 1)
                                  if pages else 0.0)

    if not pages:
        report.summary = "Empty scene — no pages/panels to analyze."
        report.confidence = 1.0
        if outline_summary.strip() or (breakdown is not None
                                       and not _is_empty(breakdown)):
            issues.append(GraphicNovelDiagnosticIssue(
                id="no_pages", label="No pages yet", category=CAT_STRUCTURE,
                severity=SEV_WATCH,
                evidence="The scene has a summary/breakdown but no page/panel body.",
                suggested_action="Draft panels from the plan, or add a page."))
        report.issues = issues
        return report

    body = gnb.serialize_graphic_novel_script(script)
    body_words = set(re.findall(r"[a-z']+", body.lower()))
    seen_visuals: dict[str, tuple[int, int]] = {}

    # -- Per-page / per-panel checks (A, B, C, page-level for D) --
    for page in pages:
        panel_count = len(page.panels)
        # A. Panel structure — page with no panels.
        if panel_count == 0:
            issues.append(GraphicNovelDiagnosticIssue(
                id=f"empty_page_{page.number}", label="Page has no panels",
                category=CAT_STRUCTURE, severity=SEV_WATCH, page_number=page.number,
                evidence=f"Page {page.number} has no panels.",
                suggested_action="Add at least one panel, or remove the page."))
        # D. Page flow — panel density.
        if panel_count > PANELS_PER_PAGE_HIGH:
            issues.append(GraphicNovelDiagnosticIssue(
                id=f"page_overloaded_{page.number}", label="Page may be overloaded",
                category=CAT_FLOW, severity=SEV_WATCH, page_number=page.number,
                evidence=f"Page {page.number} has {panel_count} panels.",
                suggested_action="Consider splitting across pages for readability."))
        elif len(pages) > 1 and panel_count == PANELS_PER_PAGE_LOW:
            issues.append(GraphicNovelDiagnosticIssue(
                id=f"page_sparse_{page.number}", label="Single-panel page",
                category=CAT_FLOW, severity=SEV_INFO, page_number=page.number,
                evidence=f"Page {page.number} has one panel — confirm a splash is "
                         "intended.", suggested_action="Confirm the splash is intended."))

        page_dialogue_heavy = 0
        for panel in page.panels:
            pn = panel.number
            report.visual_word_count += _words(panel.visual_description)
            report.dialogue_word_count += _words(panel.dialogue)
            report.caption_word_count += _words(panel.caption)
            if panel.sfx.strip():
                report.sfx_count += 1

            if panel.is_empty():
                report.empty_panels += 1
                issues.append(GraphicNovelDiagnosticIssue(
                    id=f"empty_panel_{page.number}_{pn}", label="Empty panel",
                    category=CAT_STRUCTURE, severity=SEV_WEAK,
                    page_number=page.number, panel_number=pn,
                    evidence="Panel has no content.",
                    suggested_action="Add a visual description or remove the panel."))
                continue

            # A. Panel without visual description.
            if not panel.visual_description.strip():
                report.panels_without_visual += 1
                if panel.notes.strip():
                    issues.append(GraphicNovelDiagnosticIssue(
                        id=f"notes_no_visual_{page.number}_{pn}",
                        label="Notes present but no visual description",
                        category=CAT_STRUCTURE, severity=SEV_WATCH,
                        page_number=page.number, panel_number=pn,
                        evidence="Artist notes are filled but the panel has no "
                                 "visual description.",
                        suggested_action="Move the panel's action into Visual."))
                else:
                    issues.append(GraphicNovelDiagnosticIssue(
                        id=f"no_visual_{page.number}_{pn}",
                        label="Panel has no visual description",
                        category=CAT_STRUCTURE, severity=SEV_WATCH,
                        page_number=page.number, panel_number=pn,
                        evidence="No visual description.",
                        suggested_action="Describe what the panel shows."))
            else:
                vis = panel.visual_description
                low = vis.lower()
                # B. Visual clarity.
                if _words(vis) <= VAGUE_VISUAL_WORDS:
                    issues.append(GraphicNovelDiagnosticIssue(
                        id=f"vague_visual_{page.number}_{pn}",
                        label="Vague visual description", category=CAT_VISUAL,
                        severity=SEV_INFO, page_number=page.number, panel_number=pn,
                        evidence=f"Visual is only {_words(vis)} word(s).",
                        suggested_action="Clarify the subject and action."))
                if sum(1 for w in INTERNAL_STATE_WORDS
                       if re.search(rf"\b{re.escape(w)}\b", low)) >= 1:
                    issues.append(GraphicNovelDiagnosticIssue(
                        id=f"internal_visual_{page.number}_{pn}",
                        label="Emotion described, not shown", category=CAT_VISUAL,
                        severity=SEV_WATCH, page_number=page.number, panel_number=pn,
                        evidence="Visual narrates interior state "
                                 "(thinks/feels/realizes…).",
                        suggested_action="Show the emotion as visible behavior."))
                key = re.sub(r"\s+", " ", low.strip())
                if key in seen_visuals:
                    issues.append(GraphicNovelDiagnosticIssue(
                        id=f"static_repeat_{page.number}_{pn}",
                        label="Repeated/static panel", category=CAT_VISUAL,
                        severity=SEV_INFO, page_number=page.number, panel_number=pn,
                        evidence="Visual repeats an earlier panel verbatim.",
                        suggested_action="Vary the framing or progress the action."))
                else:
                    seen_visuals[key] = (page.number, pn)

            # C. Dialogue / caption balance.
            if _words(panel.dialogue) >= DIALOGUE_HEAVY_WORDS:
                report.dialogue_heavy_panels += 1
                page_dialogue_heavy += 1
                issues.append(GraphicNovelDiagnosticIssue(
                    id=f"dialogue_heavy_{page.number}_{pn}",
                    label="Too much dialogue in one panel", category=CAT_BALANCE,
                    severity=SEV_WATCH, page_number=page.number, panel_number=pn,
                    evidence=f"{_words(panel.dialogue)} words of dialogue.",
                    suggested_action="Split across panels or trust the art."))
            if panel.dialogue.strip() and not _dialogue_speaker(panel.dialogue):
                issues.append(GraphicNovelDiagnosticIssue(
                    id=f"dialogue_no_name_{page.number}_{pn}",
                    label="Dialogue without a speaker name", category=CAT_BALANCE,
                    severity=SEV_INFO, page_number=page.number, panel_number=pn,
                    evidence="Dialogue has no 'NAME:' speaker prefix.",
                    suggested_action="Prefix the line with the character's name."))
            if _words(panel.caption) >= CAPTION_LONG_WORDS:
                report.caption_heavy_panels += 1
                issues.append(GraphicNovelDiagnosticIssue(
                    id=f"caption_heavy_{page.number}_{pn}",
                    label="Caption is long / exposition-heavy", category=CAT_BALANCE,
                    severity=SEV_WATCH, page_number=page.number, panel_number=pn,
                    evidence=f"{_words(panel.caption)} words of caption.",
                    suggested_action="Tighten the caption; let the image carry it."))
            if len(panel.sfx.strip()) >= SFX_LONG_CHARS:
                issues.append(GraphicNovelDiagnosticIssue(
                    id=f"sfx_long_{page.number}_{pn}", label="SFX is long",
                    category=CAT_BALANCE, severity=SEV_INFO, page_number=page.number,
                    panel_number=pn, evidence="SFX text is long.",
                    suggested_action="Keep SFX punchy."))

        # D. Page flow — all panels dialogue-heavy / all static.
        if panel_count >= 2 and page_dialogue_heavy == panel_count:
            issues.append(GraphicNovelDiagnosticIssue(
                id=f"page_all_talk_{page.number}", label="Page is all dialogue",
                category=CAT_FLOW, severity=SEV_WATCH, page_number=page.number,
                evidence="Every panel on the page is dialogue-heavy.",
                suggested_action="Add a visual beat to vary the rhythm."))

    # -- Page-turn / reveal (D) — only meaningful for multi-page scenes --
    target = getattr(breakdown, "target_page_count", 0) if breakdown else 0
    if len(pages) > 1 and target > 1:
        turns = (getattr(breakdown, "page_turns", "") or "").strip() if breakdown else ""
        if not turns:
            issues.append(GraphicNovelDiagnosticIssue(
                id="no_page_turn", label="No page-turn / reveal noted",
                category=CAT_FLOW, severity=SEV_INFO,
                evidence="A multi-page scene has no page-turn/reveal in the breakdown.",
                suggested_action="Plan where the page-turn reveal lands."))

    # -- E. Dramatic function (confidence-aware, never asserts absence) --
    if not any(re.search(rf"\b{re.escape(m)}\b", body.lower())
               for m in OBJECTIVE_MARKERS) and not outline_summary.strip():
        issues.append(GraphicNovelDiagnosticIssue(
            id="objective_unclear", label="Scene objective unclear",
            category=CAT_DRAMATIC, severity=SEV_WATCH,
            evidence="No want/need language and no Outline summary.",
            suggested_action="Clarify what the scene is for."))
    if report.total_panels >= 2 and not any(
            re.search(rf"\b{re.escape(w)}\b", body.lower()) for w in CONFLICT_WORDS):
        issues.append(GraphicNovelDiagnosticIssue(
            id="conflict_unclear", label="Visible conflict unclear",
            category=CAT_DRAMATIC, severity=SEV_WATCH,
            evidence="No opposition/struggle language detected (heuristic).",
            suggested_action="Make the obstacle visible in a panel."))
    if report.total_panels >= 2 and not any(
            re.search(rf"\b{re.escape(m)}\b", body.lower()) for m in TURN_MARKERS):
        issues.append(GraphicNovelDiagnosticIssue(
            id="turn_unclear", label="Turning point unclear",
            category=CAT_DRAMATIC, severity=SEV_INFO,
            evidence="No contrast/turn markers detected (heuristic).",
            suggested_action="Check the scene's value changes by the last panel."))

    # -- F. Plan alignment --
    if plan is not None and not _is_empty(plan):
        for pg in getattr(plan, "pages", []):
            for planned in getattr(pg, "panels", []):
                beat = getattr(planned, "visual_beat", "")
                cw = _content_words(beat)
                if cw and not (cw & body_words):
                    issues.append(GraphicNovelDiagnosticIssue(
                        id=f"plan_beat_missing_{pg.number}_{beat[:12]}",
                        label="Planned beat not in the body", category=CAT_ALIGNMENT,
                        severity=SEV_INFO, page_number=getattr(pg, "number", None),
                        evidence=f'Planned beat ("{beat.strip()[:50]}") isn\'t in '
                                 "the script.",
                        suggested_action="Draft this beat or update the plan."))

    # -- G. Continuity / PSYKE (warning-only; only when a Story Bible exists) --
    if psyke_characters:
        speakers: set[str] = set()
        for page in pages:
            for panel in page.panels:
                name = _dialogue_speaker(panel.dialogue)
                if name:
                    speakers.add(name)
        for name in sorted(speakers):
            if name not in psyke_characters:
                issues.append(GraphicNovelDiagnosticIssue(
                    id=f"character_not_in_psyke_{name}",
                    label=f"{name} not in Story Bible", category=CAT_CONTINUITY,
                    severity=SEV_INFO,
                    evidence=f"Speaker '{name}' has no PSYKE entry.",
                    suggested_action=f"Add {name} to PSYKE to track continuity."))

    # -- Strengths --
    if report.total_panels and report.panels_without_visual == 0:
        report.strengths.append("Every panel has a visual description.")
    if report.total_pages > 1 and report.avg_panels_per_page <= PANELS_PER_PAGE_HIGH:
        report.strengths.append("Panel density looks readable.")

    # De-duplicate, finalize.
    seen_ids: set[str] = set()
    deduped: list[GraphicNovelDiagnosticIssue] = []
    for i in issues:
        if i.id not in seen_ids:
            seen_ids.add(i.id)
            deduped.append(i)
    report.issues = deduped
    report.confidence = 0.7
    report.summary = _summary(report)
    return report


def _is_empty(obj: Any) -> bool:
    fn = getattr(obj, "is_empty", None)
    try:
        return bool(fn()) if callable(fn) else True
    except Exception:
        return True


def _summary(report: GraphicNovelSceneReport) -> str:
    head = (f"{report.total_pages} page(s), {report.total_panels} panel(s) "
            f"(avg {report.avg_panels_per_page}/page).")
    top = report.top_issues(3)
    if not top:
        return head + " No notable issues detected."
    return head + " Top issues: " + "; ".join(i.label for i in top) + "."


# ===========================================================================
# DB adapters (read-only)
# ===========================================================================


def analyze_scene_by_id(db, project_id: int, scene_id: int) -> GraphicNovelSceneReport:
    """Analyze one Graphic Novel scene by id (read-only). Loads the page/panel
    body + page breakdown + panel plan + PSYKE map."""
    scene = None
    try:
        scene = db.get_scene_by_id(scene_id)
    except Exception:
        scene = None
    if scene is None:
        return GraphicNovelSceneReport(scene_id=scene_id, summary="Scene not found.")
    script = gnb.load_scene_script(db, scene_id)
    outline_summary = (getattr(scene, "summary", "") or "")
    breakdown = plan = None
    try:
        from logosforge import graphic_novel_pipeline as gp
        breakdown = gp.get_page_breakdown(db, project_id, scene_id)
        plan = gp.get_panel_plan(db, project_id, scene_id)
    except Exception:
        breakdown = plan = None
    psyke = {}
    try:
        from logosforge.screenplay_diagnostics import _psyke_character_map
        psyke = _psyke_character_map(db, project_id)
    except Exception:
        psyke = {}
    return analyze_scene(script, scene_id=scene_id, outline_summary=outline_summary,
                         breakdown=breakdown, plan=plan, psyke_characters=psyke)
