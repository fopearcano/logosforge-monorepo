"""Graphic Novel scene Reflection — the Counterpart/Logos mirror (Phase 4).

A deterministic, non-mutating reflection layer for a Graphic Novel *Scene* (its
page/panel script). It re-projects the Phase 3 GN diagnostics + Phase 2 page
breakdown / panel plan + PSYKE + Timeline into a writer-facing report seen
through four lenses —

* **Reader** — what the sequence communicates: page flow, page-turn momentum,
  whether captions over-explain the image, whether the opening establishes where.
* **Artist** — whether each panel is drawable: clear subject, setting, single
  readable action, emotion shown as behavior, notes kept out of the description.
* **Story** — objective, conflict, a visible turn, and alignment with the plan.
* **Dialogue / Caption** — balloon/caption load and whether dialogue duplicates
  the visual instead of letting the art carry it.

It produces *feedback and revision questions*, never rewritten panels. An
optional AI pass (the existing Counterpart prompt) may explain/expand this
report; it is grounded in the deterministic findings and never replaces them.

This is a WRITING reflection, not an image-production tool. No image generation,
no image prompts, no ComfyUI, no render/model fields. Pure logic + DB reads:
no Qt, no mutation, no PSYKE/Note creation (the Note save is opt-in + confirmed).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from logosforge import graphic_novel_blocks as gnb
from logosforge import graphic_novel_diagnostics as gd

# Reuse the Phase 3 severity scale (single source of truth).
SEV_INFO = gd.SEV_INFO
SEV_WATCH = gd.SEV_WATCH
SEV_WEAK = gd.SEV_WEAK
SEV_CRITICAL = gd.SEV_CRITICAL

# Section keys (also the canonical render order).
SEC_SNAPSHOT = "Scene Snapshot"
SEC_READER = "Reader Perspective"
SEC_ARTIST = "Artist Perspective"
SEC_FLOW = "Page Flow / Page Turn Notes"
SEC_PANEL_CONTINUITY = "Panel-to-Panel Continuity"
SEC_VISUAL = "Visual Storytelling Notes"
SEC_DIALOGUE = "Dialogue / Caption Notes"
SEC_STORY = "Story Function / Dramatic Turn"
SEC_ALIGN = "Plan Alignment"
SEC_PSYKE = "PSYKE / Continuity Risks"
SEC_QUESTIONS = "Revision Questions"
SEC_ACTIONS = "Suggested Human Actions"

# Documented heuristic thresholds.
VAGUE_VISUAL_WORDS = gd.VAGUE_VISUAL_WORDS    # a caption "carries" a panel this thin
OVERLOADED_SENTENCES = 3                       # this many actions in one visual is a lot
DUPLICATE_OVERLAP = 0.6                        # dialogue/visual word overlap -> duplicate
MIN_DUP_WORDS = 3                              # need this much dialogue to judge overlap
LOW_VISUAL_RATIO = 0.5                         # scene visual words vs. dialogue+caption

# A small, conservative vocabulary that signals a panel establishes *where*.
LOCATION_CUES = (
    "int.", "ext.", "inside", "outside", "indoors", "outdoors", " in ", " at ",
    " on ", " into ", " near ", " by the ", "room", "kitchen", "office",
    "street", "alley", "house", "home", "city", "town", "village", "forest",
    "woods", "field", "park", "bridge", "rooftop", "roof", "garden", "yard",
    "car", "train", "ship", "boat", "plane", "bar", "cafe", "diner", "hall",
    "corridor", "hallway", "bedroom", "kitchen", "school", "hospital", "station",
    "shop", "store", "market", "church", "temple", "castle", "cave", "tunnel",
    "mountain", "beach", "desert", "river", "lake", "sea", "ocean", "sky",
    "space", "lab", "warehouse", "factory", "prison", "cell", "courtroom",
    "window", "doorway", "door", "stairs", "balcony", "deck", "platform",
)


def _words(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def _content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z']+", (text or "").lower()) if len(w) > 3}


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"[.!?]+", text or "") if s.strip()]


def _has_location(visual: str) -> bool:
    low = f" {(visual or '').lower()} "
    return any(cue in low for cue in LOCATION_CUES)


def _has_turn(text: str) -> bool:
    low = (text or "").lower()
    return any(re.search(rf"\b{re.escape(m)}\b", low) for m in gd.TURN_MARKERS)


def _dialogue_body(dialogue: str) -> str:
    """Dialogue text with any leading 'NAME:' speaker prefix removed."""
    s = (dialogue or "").strip()
    return s.split(":", 1)[1] if ":" in s else s


# ===========================================================================
# Data model
# ===========================================================================


@dataclass
class ReflectionItem:
    category: str
    title: str
    detail: str = ""
    severity: str = SEV_INFO
    page_number: int | None = None
    panel_number: int | None = None
    psyke_entry_id: int | None = None
    suggested_action: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category, "title": self.title, "detail": self.detail,
            "severity": self.severity, "page_number": self.page_number,
            "panel_number": self.panel_number, "psyke_entry_id": self.psyke_entry_id,
            "suggested_action": self.suggested_action,
        }


@dataclass
class GraphicNovelReflectionReport:
    scene_id: int | None = None
    snapshot: str = ""
    reader: list[ReflectionItem] = field(default_factory=list)
    artist: list[ReflectionItem] = field(default_factory=list)
    page_flow: list[ReflectionItem] = field(default_factory=list)
    panel_continuity: list[ReflectionItem] = field(default_factory=list)
    visual_storytelling: list[ReflectionItem] = field(default_factory=list)
    dialogue_caption: list[ReflectionItem] = field(default_factory=list)
    story_function: list[ReflectionItem] = field(default_factory=list)
    plan_alignment: list[ReflectionItem] = field(default_factory=list)
    continuity_risks: list[ReflectionItem] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    ai_enhanced: bool = False

    def _sections(self):
        return (
            (SEC_READER, self.reader), (SEC_ARTIST, self.artist),
            (SEC_FLOW, self.page_flow), (SEC_PANEL_CONTINUITY, self.panel_continuity),
            (SEC_VISUAL, self.visual_storytelling),
            (SEC_DIALOGUE, self.dialogue_caption), (SEC_STORY, self.story_function),
            (SEC_ALIGN, self.plan_alignment), (SEC_PSYKE, self.continuity_risks),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"scene_id": self.scene_id, "snapshot": self.snapshot}
        for header, items in self._sections():
            out[header] = [i.to_dict() for i in items]
        out["questions"] = list(self.questions)
        out["suggested_actions"] = list(self.suggested_actions)
        out["metrics"] = dict(self.metrics)
        out["ai_enhanced"] = self.ai_enhanced
        return out

    def to_text(self) -> str:
        """Readable, copy-friendly rendering (used by Logos + the Note save)."""
        lines: list[str] = [f"{SEC_SNAPSHOT}: {self.snapshot}", ""]
        for header, items in self._sections():
            lines.append(header + ":")
            if items:
                for i in items:
                    where = ""
                    if i.page_number is not None:
                        where = f" (page {i.page_number}"
                        where += f", panel {i.panel_number})" if i.panel_number else ")"
                    lines.append(f"- [{i.severity}] {i.title}{where} — {i.detail}")
            else:
                lines.append("- Nothing flagged.")
            lines.append("")
        lines.append(SEC_QUESTIONS + ":")
        lines.extend(f"- {q}" for q in (self.questions or ["—"]))
        lines.append("")
        lines.append(SEC_ACTIONS + ":")
        lines.extend(f"- {a}" for a in (self.suggested_actions or ["None."]))
        return "\n".join(lines).strip()


# ===========================================================================
# Re-projection of Phase 3 issues
# ===========================================================================


def _to_item(issue: gd.GraphicNovelDiagnosticIssue, category: str,
             psyke_id: int | None = None) -> ReflectionItem:
    return ReflectionItem(
        category=category, title=issue.label, detail=issue.evidence,
        severity=issue.severity, page_number=issue.page_number,
        panel_number=issue.panel_number, psyke_entry_id=psyke_id,
        suggested_action=issue.suggested_action)


# ===========================================================================
# New deterministic lenses (operate on the parsed GraphicNovelScript)
# ===========================================================================


def _reader_items(script: gnb.GraphicNovelScript) -> list[ReflectionItem]:
    """Reader lens: caption over-explanation, page-turn momentum, opening setting."""
    items: list[ReflectionItem] = []
    pages = script.pages if script else []

    for page in pages:
        for panel in page.panels:
            if panel.caption.strip() and _words(panel.visual_description) <= VAGUE_VISUAL_WORDS:
                items.append(ReflectionItem(
                    category=SEC_READER, title="Panel leans on caption, not image",
                    detail="A caption carries the panel while the visual is weak or "
                           "absent — the reader is told, not shown.",
                    severity=SEV_WATCH, page_number=page.number,
                    panel_number=panel.number,
                    suggested_action="Turn the caption into a visible action or image."))

    # Page-turn momentum — a non-final page should not end on a static beat.
    if len(pages) > 1:
        for page in pages[:-1]:
            if not page.panels:
                continue
            last = page.panels[-1]
            momentum = bool(last.dialogue.strip() or last.sfx.strip()
                            or _has_turn(last.visual_description))
            if not momentum:
                items.append(ReflectionItem(
                    category=SEC_READER, title="Page ends without a strong turn",
                    detail=f"Page {page.number} ends on a quiet panel — the page turn "
                           "may not pull the reader onward.",
                    severity=SEV_INFO, page_number=page.number,
                    suggested_action="End the page on a question, reveal, or beat."))

    # Opening establishing shot — does panel 1 tell the reader where we are?
    if pages and pages[0].panels:
        first = pages[0].panels[0]
        if first.visual_description.strip() and not _has_location(first.visual_description):
            items.append(ReflectionItem(
                category=SEC_READER, title="Opening may not establish the setting",
                detail="The first panel doesn't signal where the scene takes place — "
                       "the reader may be disoriented.",
                severity=SEV_INFO, page_number=pages[0].number,
                panel_number=first.number,
                suggested_action="Establish the location in or before the first panel."))
    return items


def _artist_extra_items(script: gnb.GraphicNovelScript) -> list[ReflectionItem]:
    """Artist lens additions: overloaded panels and page-opening location gaps."""
    items: list[ReflectionItem] = []
    pages = script.pages if script else []
    for page in pages:
        for idx, panel in enumerate(page.panels):
            # Count substantial action clauses (>=3 words) so location prefixes
            # like "INT." / "EXT." don't read as extra actions.
            actions = [s for s in _sentences(panel.visual_description) if _words(s) >= 3]
            if len(actions) >= OVERLOADED_SENTENCES:
                items.append(ReflectionItem(
                    category=SEC_ARTIST, title="Panel packs in several actions",
                    detail=f"The visual describes {len(actions)} separate actions — "
                           "a single panel can only freeze one moment.",
                    severity=SEV_WATCH, page_number=page.number,
                    panel_number=panel.number,
                    suggested_action="Split the actions across panels or pick one."))
            # The opening panel of each page should orient the artist on location.
            if idx == 0 and panel.visual_description.strip() \
                    and not _has_location(panel.visual_description):
                items.append(ReflectionItem(
                    category=SEC_ARTIST, title="Panel lacks setting information",
                    detail="The page opens without a location cue — the artist can't "
                           "tell where to place the action.",
                    severity=SEV_INFO, page_number=page.number,
                    panel_number=panel.number,
                    suggested_action="Name the setting in the panel's visual."))
    return items


def _visual_storytelling_items(
    script: gnb.GraphicNovelScript, diag: gd.GraphicNovelSceneReport,
) -> list[ReflectionItem]:
    """Does the art carry the story, or does the text restate the picture?"""
    items: list[ReflectionItem] = []
    pages = script.pages if script else []
    for page in pages:
        for panel in page.panels:
            dtext = _dialogue_body(panel.dialogue)
            dw = _content_words(dtext)
            vw = _content_words(panel.visual_description)
            if len(dw) >= MIN_DUP_WORDS and vw:
                overlap = len(dw & vw) / len(dw)
                if overlap >= DUPLICATE_OVERLAP:
                    items.append(ReflectionItem(
                        category=SEC_VISUAL, title="Dialogue restates the visual",
                        detail="The dialogue repeats what the panel already shows — "
                               "let the art do that work.",
                        severity=SEV_INFO, page_number=page.number,
                        panel_number=panel.number,
                        suggested_action="Cut the line, or make it add new information."))

    # Scene-level: is there enough visual storytelling versus text?
    text_words = diag.dialogue_word_count + diag.caption_word_count
    if diag.total_panels >= 2 and text_words > 0:
        ratio = diag.visual_word_count / text_words
        if ratio < LOW_VISUAL_RATIO:
            items.append(ReflectionItem(
                category=SEC_VISUAL, title="Scene leans on text over visuals",
                detail=f"Visual description ({diag.visual_word_count} words) is far "
                       f"lighter than dialogue + caption ({text_words} words).",
                severity=SEV_WATCH,
                suggested_action="Give the art more to carry; trust visual storytelling."))
    return items


# ===========================================================================
# Plan alignment / continuity / questions / actions
# ===========================================================================


def _plan_alignment_items(grouped, breakdown, plan) -> list[ReflectionItem]:
    items = [_to_item(i, SEC_ALIGN) for i in grouped.get(gd.CAT_ALIGNMENT, [])]
    no_breakdown = breakdown is None or gd._is_empty(breakdown)
    no_plan = plan is None or gd._is_empty(plan)
    if no_breakdown and no_plan:
        items.append(ReflectionItem(
            category=SEC_ALIGN, title="No plan to compare against",
            detail="No page breakdown or panel plan exists for this scene — generate "
                   "one to reflect on alignment.", severity=SEV_INFO,
            suggested_action="Run the page breakdown / panel plan pipeline."))
    elif not items:
        items.append(ReflectionItem(
            category=SEC_ALIGN, title="Body reflects the plan",
            detail="Planned beats appear in the script (keyword check).",
            severity=SEV_INFO))
    return items


def _timeline_items(db, project_id: int, scene_id: int) -> list[ReflectionItem]:
    """Note a linked Timeline event if the data is safely available (read-only)."""
    try:
        events = db.get_timeline_event_ids(project_id)
    except Exception:
        return []
    if scene_id in (events or []):
        return [ReflectionItem(
            category=SEC_PSYKE, title="Linked to the Timeline",
            detail="This scene is an explicit Timeline event — keep chronology "
                   "consistent.", severity=SEV_INFO)]
    return []


def _continuity_items(grouped, psyke: dict[str, dict], db, project_id: int,
                      scene_id: int) -> list[ReflectionItem]:
    name_to_id = {n: v.get("id") for n, v in psyke.items()}
    items: list[ReflectionItem] = []
    for issue in grouped.get(gd.CAT_CONTINUITY, []):
        cue = issue.id.replace("character_not_in_psyke_", "")
        items.append(_to_item(issue, SEC_PSYKE, psyke_id=name_to_id.get(cue)))
    items.extend(_timeline_items(db, project_id, scene_id))
    return items


def _questions(diag: gd.GraphicNovelSceneReport, plan) -> list[str]:
    """Reflective questions — never answers, never rewrites."""
    qs: list[str] = []
    ids = {i.id for i in diag.issues}
    if "objective_unclear" in ids:
        qs.append("What does this scene need to accomplish on the page?")
    if any(i.startswith(("no_visual", "notes_no_visual")) for i in ids):
        qs.append("Is every panel drawable from its description alone?")
    if "conflict_unclear" in ids:
        qs.append("Where on the page does the obstacle or opposing force become visible?")
    if "turn_unclear" in ids or "no_page_turn" in ids:
        qs.append("Which panel carries the turn, and does the page turn reveal "
                  "something new?")
    if any(i.startswith(("caption_heavy", "dialogue_heavy")) for i in ids):
        qs.append("Could this dialogue be reduced to one line and one gesture?")
    if plan is not None and not gd._is_empty(plan):
        qs.append("Does each planned beat actually get dramatized in a panel?")
    qs.append("What changes visually from the first panel to the last?")
    qs.append("Which object, pose, or composition could carry the subtext?")
    return list(dict.fromkeys(qs))


def _suggested_actions(diag: gd.GraphicNovelSceneReport,
                       report: GraphicNovelReflectionReport) -> list[str]:
    out: list[str] = []
    for issue in diag.issues:
        if issue.suggested_action:
            out.append(issue.suggested_action)
    for _, items in report._sections():
        for it in items:
            if it.suggested_action:
                out.append(it.suggested_action)
    return list(dict.fromkeys(out))[:12]


# ===========================================================================
# Snapshot + core builder
# ===========================================================================


def _snapshot(scene, diag: gd.GraphicNovelSceneReport, breakdown, plan) -> str:
    where = " / ".join(p for p in ((getattr(scene, "act", "") or "").strip(),
                                   (getattr(scene, "chapter", "") or "").strip()) if p)
    bits = [
        f"{where or 'Unplaced'} · {diag.total_pages} page(s) / "
        f"{diag.total_panels} panel(s) (avg {diag.avg_panels_per_page}/page)",
        f"words — visual {diag.visual_word_count} / dialogue "
        f"{diag.dialogue_word_count} / caption {diag.caption_word_count}",
    ]
    if breakdown is not None and not gd._is_empty(breakdown):
        bits.append("page breakdown: present")
    if plan is not None and not gd._is_empty(plan):
        bits.append("panel plan: present")
    return " · ".join(bits)


def build_scene_reflection(db, project_id: int, scene_id: int
                           ) -> GraphicNovelReflectionReport:
    """Build a deterministic multi-perspective reflection for a GN scene. Read-only."""
    rep = GraphicNovelReflectionReport(scene_id=scene_id)
    scene = None
    try:
        scene = db.get_scene_by_id(scene_id)
    except Exception:
        scene = None
    if scene is None:
        rep.snapshot = "Scene not found."
        return rep

    script = gnb.load_scene_script(db, scene_id)
    diag = gd.analyze_scene_by_id(db, project_id, scene_id)
    grouped = gd.group_issues_by_category(diag)

    breakdown = plan = None
    try:
        from logosforge import graphic_novel_pipeline as gp
        breakdown = gp.get_page_breakdown(db, project_id, scene_id)
        plan = gp.get_panel_plan(db, project_id, scene_id)
    except Exception:
        breakdown = plan = None

    psyke: dict[str, dict] = {}
    try:
        from logosforge.screenplay_reflection import _psyke_characters_by_name
        psyke = _psyke_characters_by_name(db, project_id)
    except Exception:
        psyke = {}

    rep.metrics = {
        "total_pages": diag.total_pages, "total_panels": diag.total_panels,
        "avg_panels_per_page": diag.avg_panels_per_page,
        "panels_without_visual": diag.panels_without_visual,
        "dialogue_heavy_panels": diag.dialogue_heavy_panels,
        "caption_heavy_panels": diag.caption_heavy_panels,
        "sfx_count": diag.sfx_count, "visual_word_count": diag.visual_word_count,
        "dialogue_word_count": diag.dialogue_word_count,
        "caption_word_count": diag.caption_word_count,
    }
    rep.snapshot = _snapshot(scene, diag, breakdown, plan)

    # Reader lens (new heuristics).
    rep.reader = _reader_items(script)

    # Artist lens: drawability from Phase 3 structure + visual issues (minus the
    # cross-panel repetition, which is continuity), plus overloaded/location.
    rep.artist = [_to_item(i, SEC_ARTIST) for i in grouped.get(gd.CAT_STRUCTURE, [])]
    rep.artist += [_to_item(i, SEC_ARTIST) for i in grouped.get(gd.CAT_VISUAL, [])
                   if not i.id.startswith("static_repeat")]
    rep.artist += _artist_extra_items(script)

    # Page flow / page turn (re-projected Phase 3 flow issues).
    rep.page_flow = [_to_item(i, SEC_FLOW) for i in grouped.get(gd.CAT_FLOW, [])]

    # Panel-to-panel continuity (verbatim/static repeats across panels).
    rep.panel_continuity = [_to_item(i, SEC_PANEL_CONTINUITY)
                            for i in grouped.get(gd.CAT_VISUAL, [])
                            if i.id.startswith("static_repeat")]

    # Visual storytelling (new heuristics).
    rep.visual_storytelling = _visual_storytelling_items(script, diag)

    # Dialogue / caption balance (re-projected).
    rep.dialogue_caption = [_to_item(i, SEC_DIALOGUE)
                            for i in grouped.get(gd.CAT_BALANCE, [])]

    # Story function / dramatic turn (re-projected).
    rep.story_function = [_to_item(i, SEC_STORY)
                          for i in grouped.get(gd.CAT_DRAMATIC, [])]

    rep.plan_alignment = _plan_alignment_items(grouped, breakdown, plan)
    rep.continuity_risks = _continuity_items(grouped, psyke, db, project_id, scene_id)
    rep.questions = _questions(diag, plan)
    rep.suggested_actions = _suggested_actions(diag, rep)
    return rep


# ===========================================================================
# AI seam (optional) — grounds the existing Counterpart prompt in the report
# ===========================================================================


def build_reflection_messages(
    report: GraphicNovelReflectionReport, *, scene_context: str = "",
) -> list[dict]:
    """Build messages for an optional AI pass that *explains/expands* the
    deterministic reflection. Reuses the existing Counterpart system prompt; the
    AI never rewrites panels and never produces imagery — it deepens the writer's
    reflection.

    Deterministic to build (no LLM call here). The caller runs it through the
    shared chat backend only if a provider is configured."""
    from logosforge.counterpart import SYSTEM_PROMPT
    parts: list[str] = []
    if scene_context:
        parts.append(scene_context)
        parts.append("")
    parts.append("Deterministic Graphic Novel reflection (ground your feedback in "
                 "this; do not rewrite the panels):")
    parts.append(report.to_text())
    parts.append("")
    parts.append("As COUNTERPART, deepen this reflection from the reader's, the "
                 "artist's, and the story's point of view. Point to the most "
                 "important gaps and ask the writer 2-3 sharper questions. Keep it "
                 "structured. Do NOT produce replacement panel script, visual "
                 "descriptions, or image-generation prompts of any kind.")
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(parts)},
    ]


# ===========================================================================
# Optional: save the reflection as a scene-linked Note (requires confirmation)
# ===========================================================================


def save_reflection_as_note(
    db, project_id: int, scene_id: int, report: GraphicNovelReflectionReport,
    *, confirmed: bool = False,
) -> dict:
    """Save a reflection as a Note linked to the scene. **Requires
    ``confirmed=True``** — nothing is written otherwise. Never auto-saves."""
    if not confirmed:
        return {"ok": False,
                "error": "Saving a reflection note requires confirmation."}
    scene = db.get_scene_by_id(scene_id)
    if scene is None:
        return {"ok": False, "error": "Scene not found."}
    title = f"GN Reflection — {(getattr(scene, 'title', '') or 'Scene').strip()}"
    try:
        note = db.create_note(project_id, title, report.to_text(), tags="reflection")
        note_id = getattr(note, "id", note)
        db.link_note_to_scene(note_id, scene_id)
    except Exception as exc:
        return {"ok": False, "error": f"Could not save note: {exc}"}
    return {"ok": True, "note_id": note_id, "scene_id": scene_id}
