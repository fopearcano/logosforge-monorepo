"""Graphic Novel page/panel planning pipeline (Phase 2).

The deterministic, safety-critical bridge:

    Outline Scene summary  →  Page Breakdown  →  Panel Plan  →  panel-script draft
    preview  →  confirmed apply to the Scene body

Design contract (non-negotiable):
* The AI **never** overwrites the Manuscript body. Generation only ever produces
  a *page breakdown*, a *panel plan*, or a *draft preview*; nothing reaches
  ``Scene.content`` until the author confirms and the change passes through
  Controlled Apply.
* The **page breakdown** and **panel plan** are planning artifacts, stored
  separately from the Manuscript body (``Scene.content``) and the Outline summary
  (``Scene.summary``) — in project settings (``gn_page_breakdowns`` /
  ``gn_panel_plans``). **No schema change.**
* Apply reuses the existing Controlled Apply gate (``target_type="scene"`` →
  ``Scene.content``), so the draft lands on the body only via the validated
  adapter, after a checkpoint, and only with ``confirmed=True``.

Pure logic: no Qt, no provider/LLM client. Prompt builders return strings; the
parsers turn an LLM reply into structured data; validation is rule-based; the UI
owns the actual provider call and the confirm dialogs. Mirrors
``screenplay_pipeline``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from logosforge import graphic_novel_blocks as gnb

# Project-settings keys (keyed by str(scene_id)).
BREAKDOWN_KEY = "gn_page_breakdowns"
PLAN_KEY = "gn_panel_plans"

# Apply-mode tokens (UI-level intents) — mirror the screenplay pipeline.
APPLY_TO_EMPTY = "apply_to_empty"
APPLY_REPLACE = "replace"
APPLY_APPEND = "append"
APPLY_CANCEL = "cancel"
APPLY_MODES = (APPLY_TO_EMPTY, APPLY_REPLACE, APPLY_APPEND, APPLY_CANCEL)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ===========================================================================
# Page breakdown model
# ===========================================================================


@dataclass
class PageBreakdown:
    """A scene's page-level plan — separate from body and Outline summary."""

    scene_id: int | None = None
    target_page_count: int = 0
    pacing_goal: str = ""
    page_turns: str = ""
    page_summaries: list[str] = field(default_factory=list)
    emotional_progression: str = ""
    visual_rhythm_notes: str = ""
    continuity_notes: str = ""
    created_at: str = ""
    updated_at: str = ""

    def is_empty(self) -> bool:
        return not any((self.target_page_count, self.pacing_goal.strip(),
                        self.page_turns.strip(), self.emotional_progression.strip(),
                        self.visual_rhythm_notes.strip(),
                        self.continuity_notes.strip(),
                        [s for s in self.page_summaries if s.strip()]))

    def to_dict(self) -> dict[str, Any]:
        return {"scene_id": self.scene_id,
                "target_page_count": self.target_page_count,
                "pacing_goal": self.pacing_goal, "page_turns": self.page_turns,
                "page_summaries": list(self.page_summaries),
                "emotional_progression": self.emotional_progression,
                "visual_rhythm_notes": self.visual_rhythm_notes,
                "continuity_notes": self.continuity_notes,
                "created_at": self.created_at, "updated_at": self.updated_at}

    @classmethod
    def from_dict(cls, d: dict) -> "PageBreakdown":
        d = d or {}
        return cls(
            scene_id=d.get("scene_id"),
            target_page_count=int(d.get("target_page_count", 0) or 0),
            pacing_goal=d.get("pacing_goal", "") or "",
            page_turns=d.get("page_turns", "") or "",
            page_summaries=[str(x) for x in (d.get("page_summaries") or [])],
            emotional_progression=d.get("emotional_progression", "") or "",
            visual_rhythm_notes=d.get("visual_rhythm_notes", "") or "",
            continuity_notes=d.get("continuity_notes", "") or "",
            created_at=d.get("created_at", "") or "",
            updated_at=d.get("updated_at", "") or "")

    def to_text(self) -> str:
        lines: list[str] = []
        if self.target_page_count:
            lines.append(f"Target Pages: {self.target_page_count}")
        if self.pacing_goal.strip():
            lines.append(f"Pacing Goal: {self.pacing_goal.strip()}")
        if self.page_turns.strip():
            lines.append(f"Page Turns: {self.page_turns.strip()}")
        if self.emotional_progression.strip():
            lines.append(f"Emotional Progression: {self.emotional_progression.strip()}")
        if self.visual_rhythm_notes.strip():
            lines.append(f"Visual Rhythm: {self.visual_rhythm_notes.strip()}")
        if self.continuity_notes.strip():
            lines.append(f"Continuity Notes: {self.continuity_notes.strip()}")
        pages = [s.strip() for s in self.page_summaries if s.strip()]
        if pages:
            lines.append("Page Summaries:")
            lines.extend(f"- {p}" for p in pages)
        return "\n".join(lines)


# ===========================================================================
# Panel plan model
# ===========================================================================


@dataclass
class PlannedPanel:
    visual_beat: str = ""
    character_action: str = ""
    framing_note: str = ""
    caption_intention: str = ""
    dialogue_intention: str = ""
    sfx_intention: str = ""
    transition_note: str = ""

    def is_empty(self) -> bool:
        return not any(getattr(self, f).strip() for f in (
            "visual_beat", "character_action", "framing_note",
            "caption_intention", "dialogue_intention", "sfx_intention",
            "transition_note"))

    def to_dict(self) -> dict[str, Any]:
        return {"visual_beat": self.visual_beat,
                "character_action": self.character_action,
                "framing_note": self.framing_note,
                "caption_intention": self.caption_intention,
                "dialogue_intention": self.dialogue_intention,
                "sfx_intention": self.sfx_intention,
                "transition_note": self.transition_note}

    @classmethod
    def from_dict(cls, d: dict) -> "PlannedPanel":
        d = d or {}
        return cls(**{k: (d.get(k, "") or "") for k in (
            "visual_beat", "character_action", "framing_note",
            "caption_intention", "dialogue_intention", "sfx_intention",
            "transition_note")})


@dataclass
class PlannedPage:
    number: int = 0
    panels: list[PlannedPanel] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"number": self.number, "panels": [p.to_dict() for p in self.panels]}

    @classmethod
    def from_dict(cls, d: dict) -> "PlannedPage":
        d = d or {}
        return cls(number=int(d.get("number", 0) or 0),
                   panels=[PlannedPanel.from_dict(p) for p in (d.get("panels") or [])])


@dataclass
class PanelPlan:
    scene_id: int | None = None
    pages: list[PlannedPage] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def is_empty(self) -> bool:
        return not any(p.panels for p in self.pages)

    def to_dict(self) -> dict[str, Any]:
        return {"scene_id": self.scene_id,
                "pages": [p.to_dict() for p in self.pages],
                "created_at": self.created_at, "updated_at": self.updated_at}

    @classmethod
    def from_dict(cls, d: dict) -> "PanelPlan":
        d = d or {}
        return cls(scene_id=d.get("scene_id"),
                   pages=[PlannedPage.from_dict(p) for p in (d.get("pages") or [])],
                   created_at=d.get("created_at", "") or "",
                   updated_at=d.get("updated_at", "") or "")

    def to_text(self) -> str:
        lines: list[str] = []
        for page in self.pages:
            lines.append(f"PAGE {page.number}")
            for i, panel in enumerate(page.panels, start=1):
                lines.append(f"PANEL {i}")
                for label, val in (("Visual beat", panel.visual_beat),
                                   ("Action", panel.character_action),
                                   ("Framing", panel.framing_note),
                                   ("Caption", panel.caption_intention),
                                   ("Dialogue", panel.dialogue_intention),
                                   ("SFX", panel.sfx_intention),
                                   ("Transition", panel.transition_note)):
                    if val.strip():
                        lines.append(f"{label}: {val.strip()}")
            lines.append("")
        return "\n".join(lines).strip()


# ===========================================================================
# Settings storage (no schema migration)
# ===========================================================================


def _read(db, project_id: int, key: str) -> dict:
    try:
        settings = db.get_project_settings(project_id) or {}
    except Exception:
        return {}
    store = settings.get(key)
    return dict(store) if isinstance(store, dict) else {}


def _write(db, project_id: int, key: str, store: dict) -> None:
    try:
        settings = db.get_project_settings(project_id) or {}
    except Exception:
        settings = {}
    settings[key] = store
    db.save_project_settings(project_id, settings)


def get_page_breakdown(db, project_id: int, scene_id: int) -> PageBreakdown | None:
    raw = _read(db, project_id, BREAKDOWN_KEY).get(str(scene_id))
    if not isinstance(raw, dict):
        return None
    bd = PageBreakdown.from_dict(raw)
    bd.scene_id = scene_id
    return bd


def has_page_breakdown(db, project_id: int, scene_id: int) -> bool:
    bd = get_page_breakdown(db, project_id, scene_id)
    return bd is not None and not bd.is_empty()


def save_page_breakdown(db, project_id: int, bd: PageBreakdown) -> PageBreakdown:
    if bd.scene_id is None:
        raise ValueError("save_page_breakdown requires scene_id")
    store = _read(db, project_id, BREAKDOWN_KEY)
    existing = store.get(str(bd.scene_id))
    if isinstance(existing, dict) and existing.get("created_at"):
        bd.created_at = existing["created_at"]
    elif not bd.created_at:
        bd.created_at = _now()
    bd.updated_at = _now()
    store[str(bd.scene_id)] = bd.to_dict()
    _write(db, project_id, BREAKDOWN_KEY, store)
    return bd


def clear_page_breakdown(db, project_id: int, scene_id: int) -> bool:
    store = _read(db, project_id, BREAKDOWN_KEY)
    if str(scene_id) in store:
        del store[str(scene_id)]
        _write(db, project_id, BREAKDOWN_KEY, store)
        return True
    return False


def get_panel_plan(db, project_id: int, scene_id: int) -> PanelPlan | None:
    raw = _read(db, project_id, PLAN_KEY).get(str(scene_id))
    if not isinstance(raw, dict):
        return None
    plan = PanelPlan.from_dict(raw)
    plan.scene_id = scene_id
    return plan


def has_panel_plan(db, project_id: int, scene_id: int) -> bool:
    plan = get_panel_plan(db, project_id, scene_id)
    return plan is not None and not plan.is_empty()


def save_panel_plan(db, project_id: int, plan: PanelPlan) -> PanelPlan:
    if plan.scene_id is None:
        raise ValueError("save_panel_plan requires scene_id")
    store = _read(db, project_id, PLAN_KEY)
    existing = store.get(str(plan.scene_id))
    if isinstance(existing, dict) and existing.get("created_at"):
        plan.created_at = existing["created_at"]
    elif not plan.created_at:
        plan.created_at = _now()
    plan.updated_at = _now()
    store[str(plan.scene_id)] = plan.to_dict()
    _write(db, project_id, PLAN_KEY, store)
    return plan


def clear_panel_plan(db, project_id: int, scene_id: int) -> bool:
    store = _read(db, project_id, PLAN_KEY)
    if str(scene_id) in store:
        del store[str(scene_id)]
        _write(db, project_id, PLAN_KEY, store)
        return True
    return False


# ===========================================================================
# Prompt builders
# ===========================================================================

_BREAKDOWN_SYSTEM = (
    "You are a graphic novel editor. Produce a concise PAGE BREAKDOWN — page-level "
    "pacing and structure — not panel script or art. Output only the labelled plan."
)
_PLAN_SYSTEM = (
    "You are a graphic novel artist-writer. Produce a concise PANEL PLAN — the "
    "visual beat of each panel, grouped by page. Not finished panel script. Output "
    "only the labelled plan."
)
_DRAFT_SYSTEM = (
    "You are a graphic novel scripter. Write a page/panel script realizing ONLY the "
    "supplied page breakdown and panel plan. Output script only — PAGE/PANEL headers "
    "and Visual/Caption/Dialogue/SFX/Notes fields. No markdown, no code fences, no "
    "commentary, and do not restate the plan."
)


def _scene_meta(db, scene_id: int) -> dict[str, str]:
    scene = db.get_scene_by_id(scene_id)
    if scene is None:
        return {"title": "", "summary": "", "act": "", "chapter": ""}
    return {"title": (getattr(scene, "title", "") or "").strip(),
            "summary": (getattr(scene, "summary", "") or "").strip(),
            "act": (getattr(scene, "act", "") or "").strip(),
            "chapter": (getattr(scene, "chapter", "") or "").strip()}


def _mode_block(db, project_id: int) -> str:
    try:
        from logosforge.writing_modes import (
            get_project_writing_mode_by_id, mode_context_block)
        return mode_context_block(get_project_writing_mode_by_id(db, project_id))
    except Exception:
        return ""


def build_page_breakdown_prompt(db, project_id: int, scene_id: int,
                               *, target_page_count: int = 0) -> str:
    meta = _scene_meta(db, scene_id)
    parts = ["Create a graphic novel PAGE BREAKDOWN for this scene, based on its "
             "intent (summary), not on any drafted panels. Be concrete and concise."]
    where = " / ".join(p for p in (meta["act"], meta["chapter"]) if p)
    if where:
        parts.append(f"Scene location: {where}")
    if meta["title"]:
        parts.append(f"Scene title: {meta['title']}")
    if meta["summary"]:
        parts.append(f"Scene summary (intent):\n\"\"\"\n{meta['summary']}\n\"\"\"")
    else:
        parts.append("Scene summary: (none — infer a minimal plausible breakdown).")
    if target_page_count:
        parts.append(f"Target page count: {target_page_count}")
    existing = get_page_breakdown(db, project_id, scene_id)
    if existing is not None and not existing.is_empty():
        parts.append("Existing breakdown to refine:\n" + existing.to_text())
    mode = _mode_block(db, project_id)
    if mode:
        parts.append(mode)
    parts.append(
        "Respond with ONLY this labelled format (omit a line if not applicable):\n"
        "Target Pages: <n>\nPacing Goal: <...>\nPage Turns: <reveals/cliffhangers>\n"
        "Emotional Progression: <start -> end>\nVisual Rhythm: <...>\n"
        "Continuity Notes: <...>\nPage Summaries:\n- <page 1 purpose>\n- <page 2 purpose>")
    return "\n\n".join(parts)


def build_panel_plan_prompt(db, project_id: int, scene_id: int,
                            breakdown: PageBreakdown | None = None) -> str:
    bd = breakdown or get_page_breakdown(db, project_id, scene_id)
    meta = _scene_meta(db, scene_id)
    parts = ["Create a graphic novel PANEL PLAN — the visual beat of each panel, "
             "grouped by page — realizing the page breakdown below. Not finished "
             "panel script."]
    if meta["title"]:
        parts.append(f"Scene title: {meta['title']}")
    if bd is not None and not bd.is_empty():
        parts.append("Page breakdown:\n" + bd.to_text())
    elif meta["summary"]:
        parts.append(f"Scene summary:\n\"\"\"\n{meta['summary']}\n\"\"\"")
    parts.append(
        "Respond with ONLY this format:\nPAGE 1\nPANEL 1\nVisual beat: <...>\n"
        "Action: <...>\nFraming: <...>\nCaption: <intention>\nDialogue: <intention>\n"
        "SFX: <intention>\nTransition: <from previous>\nPANEL 2\n...\nPAGE 2\n...")
    return "\n\n".join(parts)


def build_draft_prompt(db, project_id: int, scene_id: int,
                       breakdown: PageBreakdown | None = None,
                       plan: PanelPlan | None = None) -> str:
    bd = breakdown or get_page_breakdown(db, project_id, scene_id)
    pl = plan or get_panel_plan(db, project_id, scene_id)
    meta = _scene_meta(db, scene_id)
    parts = ["Write the graphic novel page/panel SCRIPT for this scene, realizing "
             "ONLY the breakdown and panel plan. Script only — no commentary, no "
             "markdown."]
    if meta["title"]:
        parts.append(f"Scene title: {meta['title']}")
    if bd is not None and not bd.is_empty():
        parts.append("Page breakdown:\n" + bd.to_text())
    if pl is not None and not pl.is_empty():
        parts.append("Panel plan:\n" + pl.to_text())
    if (bd is None or bd.is_empty()) and (pl is None or pl.is_empty()) and meta["summary"]:
        parts.append(f"Scene summary:\n\"\"\"\n{meta['summary']}\n\"\"\"")
    parts.append(
        "Use exactly this body format:\nPAGE 1: <optional title>\n\nPANEL 1\n"
        "Visual: <what the panel shows>\nCaption: <narration>\n"
        "Dialogue: NAME: <line>\nSFX: <sound>\nNotes: <art note>\n\nPANEL 2\n...")
    return "\n\n".join(parts)


def page_breakdown_messages(prompt: str) -> list[dict]:
    return [{"role": "system", "content": _BREAKDOWN_SYSTEM},
            {"role": "user", "content": prompt}]


def panel_plan_messages(prompt: str) -> list[dict]:
    return [{"role": "system", "content": _PLAN_SYSTEM},
            {"role": "user", "content": prompt}]


def draft_messages(prompt: str) -> list[dict]:
    return [{"role": "system", "content": _DRAFT_SYSTEM},
            {"role": "user", "content": prompt}]


# ===========================================================================
# Parsers
# ===========================================================================

_FENCE_RE = re.compile(r"^\s*```[\w-]*\s*$")


def _strip_fences(text: str) -> str:
    if "```" not in (text or ""):
        return text or ""
    lines = (text or "").splitlines()
    idx = [i for i, ln in enumerate(lines) if _FENCE_RE.match(ln)]
    if len(idx) >= 2:
        return "\n".join(lines[idx[0] + 1:idx[1]])
    return "\n".join(ln for ln in lines if not _FENCE_RE.match(ln))


_BD_SINGLE = (
    (("target pages", "pages", "page count"), "target_page_count"),
    (("pacing goal", "pacing"), "pacing_goal"),
    (("page turns", "reveals"), "page_turns"),
    (("emotional progression", "emotion"), "emotional_progression"),
    (("visual rhythm", "rhythm"), "visual_rhythm_notes"),
    (("continuity notes", "continuity"), "continuity_notes"),
)
_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.*)$")


def parse_page_breakdown_response(text: str, scene_id: int | None = None) -> PageBreakdown:
    bd = PageBreakdown(scene_id=scene_id)
    in_summaries = False
    for raw in _strip_fences(text or "").splitlines():
        line = raw.rstrip()
        if ":" in line:
            head, _, val = line.partition(":")
            key = head.strip().lower()
            if key in ("page summaries", "pages summaries", "page summary"):
                in_summaries = True
                if val.strip():
                    bd.page_summaries.append(val.strip())
                continue
            matched = next((f for labels, f in _BD_SINGLE if key in labels), None)
            if matched:
                in_summaries = False
                if matched == "target_page_count":
                    m = re.search(r"\d+", val)
                    bd.target_page_count = int(m.group()) if m else 0
                else:
                    setattr(bd, matched, val.strip())
                continue
        bullet = _BULLET_RE.match(line)
        if in_summaries and bullet:
            bd.page_summaries.append(bullet.group(1).strip())
        elif in_summaries and line.strip():
            bd.page_summaries.append(line.strip())
    return bd


_PAGE_RE = re.compile(r"^\s*PAGE\s+(\d+)", re.IGNORECASE)
_PANEL_RE = re.compile(r"^\s*PANEL\s+(\d+)", re.IGNORECASE)
_PLAN_FIELDS = {
    "visual beat": "visual_beat", "visual": "visual_beat", "beat": "visual_beat",
    "action": "character_action", "framing": "framing_note", "camera": "framing_note",
    "caption": "caption_intention", "dialogue": "dialogue_intention",
    "sfx": "sfx_intention", "transition": "transition_note",
}


def parse_panel_plan_response(text: str, scene_id: int | None = None) -> PanelPlan:
    plan = PanelPlan(scene_id=scene_id)
    cur_page: PlannedPage | None = None
    cur_panel: PlannedPanel | None = None
    for raw in _strip_fences(text or "").splitlines():
        line = raw.rstrip()
        pm = _PAGE_RE.match(line)
        if pm:
            cur_page = PlannedPage(number=int(pm.group(1)))
            plan.pages.append(cur_page)
            cur_panel = None
            continue
        panel_m = _PANEL_RE.match(line)
        if panel_m:
            if cur_page is None:
                cur_page = PlannedPage(number=len(plan.pages) + 1)
                plan.pages.append(cur_page)
            cur_panel = PlannedPanel()
            cur_page.panels.append(cur_panel)
            continue
        if ":" in line and cur_panel is not None:
            head, _, val = line.partition(":")
            f = _PLAN_FIELDS.get(head.strip().lower())
            if f:
                setattr(cur_panel, f, val.strip())
    return plan


def parse_draft_response(text: str, scene_id: int | None = None) -> gnb.GraphicNovelScript:
    """Parse a panel-script draft reply into a GraphicNovelScript (strips fences,
    reuses the Phase 1 scene-body parser)."""
    return gnb.parse_graphic_novel_text(_strip_fences(text or ""))


# ===========================================================================
# Validation
# ===========================================================================

_LEAK_PHRASES = (
    "as an ai", "as a language model", "i cannot ", "i can't ",
    "here is the script", "here's the script", "sure, here", "sure! here",
    "[page breakdown]", "[panel plan]", "[project mode]", "system prompt",
)
_PLAN_LABELS_IN_BODY = ("visual beat:", "framing:", "transition:",
                        "target pages:", "pacing goal:")


@dataclass
class DraftValidation:
    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"is_valid": self.is_valid, "errors": list(self.errors),
                "warnings": list(self.warnings)}


def validate_draft_script(script: gnb.GraphicNovelScript) -> DraftValidation:
    """Rule-based check of a parsed draft. Errors block; warnings allow.

    Errors guard the body from junk (empty, leaked fences, leaked plan/commentary,
    corrupt structure). Structural quirks (empty page, panel without visual,
    dialogue-heavy) are warnings via the Phase 1 validator."""
    report = DraftValidation()
    if script is None or script.is_empty():
        report.errors.append("The draft has no pages/panels.")
        report.is_valid = False
        return report

    body = gnb.serialize_graphic_novel_script(script)
    low = body.lower()
    if "```" in body:
        report.errors.append("The draft contains markdown code fences.")
    if any(p in low for p in _LEAK_PHRASES):
        report.errors.append("The draft contains assistant commentary or leaked context.")
    for page in script.pages:
        for panel in page.panels:
            first = (panel.visual_description or "").strip().lower().split("\n", 1)[0]
            if any(first.startswith(lbl) for lbl in _PLAN_LABELS_IN_BODY):
                report.errors.append(
                    "The draft contains the plan instead of panel script.")
                break

    # Structural warnings from the Phase 1 validator (advisory, never block here).
    gn_report = gnb.validate_graphic_novel_script(script)
    report.warnings.extend(w for w in gn_report.warnings
                           if "Empty graphic novel script" not in w)

    report.errors = list(dict.fromkeys(report.errors))
    report.warnings = list(dict.fromkeys(report.warnings))
    report.is_valid = not report.errors
    return report


# ===========================================================================
# Controlled apply (preview -> confirmed apply)
# ===========================================================================


def _scene_body(db, scene_id: int) -> str:
    scene = db.get_scene_by_id(scene_id)
    return (getattr(scene, "content", "") or "") if scene is not None else ""


def resolve_apply_mode(db, project_id: int, scene_id: int,
                       requested: str) -> tuple[str, bool, str]:
    """Map a UI apply intent to a body-composition decision.

    Returns ``(effective_mode, requires_extra_confirm, error)``. ``apply_to_empty``
    is refused on a non-empty body; ``replace`` on a non-empty body needs the UI
    to double-confirm; ``append`` is additive."""
    body = _scene_body(db, scene_id)
    is_empty = not body.strip()
    if requested == APPLY_CANCEL:
        return ("", False, "cancelled")
    if requested == APPLY_TO_EMPTY:
        if is_empty:
            return (APPLY_REPLACE, False, "")
        return ("", False, "The scene body is not empty — choose Replace or Append.")
    if requested == APPLY_REPLACE:
        return (APPLY_REPLACE, not is_empty, "")
    if requested == APPLY_APPEND:
        return (APPLY_APPEND, False, "")
    return ("", False, f"Unknown apply mode: {requested!r}")


def _compose_body(db, scene_id: int, script: gnb.GraphicNovelScript,
                  effective_mode: str) -> str:
    """Compose the resulting Scene body for the mode. Append continues page
    numbering after the existing pages (no overwrite)."""
    if effective_mode == APPLY_APPEND:
        existing = gnb.parse_graphic_novel_text(_scene_body(db, scene_id))
        if not existing.is_empty():
            offset = len(existing.pages)
            merged = gnb.GraphicNovelScript(pages=list(existing.pages))
            for i, page in enumerate(script.pages, start=1):
                page.number = offset + i
                merged.pages.append(page)
            return gnb.serialize_graphic_novel_script(merged)
    return gnb.serialize_graphic_novel_script(script)


def preview_draft_apply(db, project_id: int, scene_id: int,
                        script: gnb.GraphicNovelScript, *, mode: str = APPLY_REPLACE):
    """Build a Controlled-Apply preview for the draft. **No mutation.** Returns the
    ApplyPreview, or None on a mode error."""
    effective, _confirm, err = resolve_apply_mode(db, project_id, scene_id, mode)
    if err:
        return None
    from logosforge.controlled_apply.service import build_apply_preview
    return build_apply_preview(
        db, project_id, target_type="scene", target_id=scene_id,
        proposed_text=_compose_body(db, scene_id, script, effective),
        apply_mode="replace", source_type="gn_pipeline")


def apply_draft(db, project_id: int, scene_id: int,
                script: gnb.GraphicNovelScript, *,
                mode: str = APPLY_REPLACE, confirmed: bool = False) -> dict:
    """Apply a panel-script draft to the Scene body via Controlled Apply.

    The AI never reaches here on its own: ``confirmed`` defaults to ``False`` and
    the underlying ``apply_operation`` refuses without it. The draft is validated
    (errors block) before any write; only ``Scene.content`` is touched."""
    if mode == APPLY_CANCEL:
        return {"ok": False, "cancelled": True}

    validation = validate_draft_script(script)
    if not validation.is_valid:
        return {"ok": False, "error": "Draft failed validation.",
                "validation": validation.to_dict()}

    effective, _confirm, err = resolve_apply_mode(db, project_id, scene_id, mode)
    if err:
        return {"ok": False, "error": err}

    from logosforge.controlled_apply.service import apply_operation
    return apply_operation(
        db, project_id, target_type="scene", target_id=scene_id,
        proposed_text=_compose_body(db, scene_id, script, effective),
        apply_mode="replace", confirmed=confirmed, source_type="gn_pipeline")


# ===========================================================================
# Assistant / Logos context
# ===========================================================================


def gn_planning_context(db, project_id: int, scene_id: int | None) -> str:
    """A short, labelled ``[Graphic Novel Plan]`` block for the Assistant.

    Empty for non-graphic-novel projects or scenes without a breakdown/plan."""
    if scene_id is None:
        return ""
    try:
        from logosforge.writing_modes import (
            get_project_writing_mode_by_id, GRAPHIC_NOVEL)
        if get_project_writing_mode_by_id(db, project_id) != GRAPHIC_NOVEL:
            return ""
    except Exception:
        return ""
    bd = get_page_breakdown(db, project_id, scene_id)
    plan = get_panel_plan(db, project_id, scene_id)
    parts: list[str] = []
    if bd is not None and not bd.is_empty():
        parts.append("Page breakdown:\n" + bd.to_text())
    if plan is not None and not plan.is_empty():
        parts.append(f"Panel plan: {len(plan.pages)} page(s), "
                     f"{sum(len(p.panels) for p in plan.pages)} planned panel(s).")
    if not parts:
        return ""
    return "[Graphic Novel Plan]\n" + "\n\n".join(parts)
