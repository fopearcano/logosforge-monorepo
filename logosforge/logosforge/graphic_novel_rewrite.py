"""Graphic Novel controlled rewrite — targeted revision preview, diff, confirmed apply (Phase 5).

A safe rewrite layer for Graphic Novel scenes. The AI **never** overwrites the
Manuscript: a rewrite is always *requested → previewed (with a page/panel diff) →
confirmed → applied through Controlled Apply*. This module is the deterministic
orchestration around that flow; the actual generation call is the caller's (UI),
exactly like Phase 2's draft pipeline.

It builds on, and never duplicates, the existing machinery:
* parsing/serialization reuse :mod:`logosforge.graphic_novel_blocks`;
* draft cleaning + validation reuse :mod:`logosforge.graphic_novel_pipeline`
  (``parse_draft_response`` / ``validate_draft_script`` / fence stripping);
* apply + checkpoint reuse :mod:`logosforge.controlled_apply`
  (``apply_operation`` with ``target_type="scene"``);
* context grounding reuses the Phase 2 breakdown/plan, Phase 3 health, and Phase 4
  Counterpart reflection.

Targets: a selected panel, a selected page, selected text, or the whole scene —
each applied by page/panel index surgery so only the target changes. Apply only
ever touches ``Scene.content``; Outline summaries, the page breakdown, the panel
plan, Timeline events/links, PSYKE entries, and Notes are all preserved. Pure
logic + DB service calls; no Qt; no provider/API keys ever read or emitted; and
explicitly no image generation, image prompts, or ComfyUI.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Any

from logosforge import graphic_novel_blocks as gnb
from logosforge import graphic_novel_pipeline as gp

# -- Rewrite targets ---------------------------------------------------------
TARGET_SELECTION = "selection"     # arbitrary selected text (best-effort replace)
TARGET_PANEL = "panel"             # one panel, by page number + panel number
TARGET_PAGE = "page"               # one page, by page number
TARGET_SCENE = "scene"             # the whole scene body
TARGETS = (TARGET_SELECTION, TARGET_PANEL, TARGET_PAGE, TARGET_SCENE)

# -- Apply modes -------------------------------------------------------------
MODE_REPLACE = "replace"                       # replace the target
MODE_APPEND_ALTERNATE = "append_alternate"     # add as alternate pages, keep original
MODE_COPY_ONLY = "copy_only"                   # no mutation — just hand back the text
MODE_REVISION_CANDIDATE = "revision_candidate" # save as a scene-linked Note
MODE_CANCEL = "cancel"
APPLY_MODES = (MODE_REPLACE, MODE_APPEND_ALTERNATE, MODE_COPY_ONLY,
               MODE_REVISION_CANDIDATE, MODE_CANCEL)

# Image-generation / art-tool leakage — rejected (this is a WRITING tool).
_GEN_LEAK_PHRASES = (
    "comfyui", "stable diffusion", "img2img", "txt2img", "negative prompt",
    "image prompt", "image generation", "checkpoint:", "cfg scale", "sampler:",
    "denoise", "diffusion model", "midjourney", "dall-e", "dall·e", "lora:",
)


# Instruction registry: key -> (label, guidance line for the prompt).
INSTRUCTIONS: dict[str, tuple[str, str]] = {
    "make_more_visual": (
        "Make More Visual",
        "Recast the panel as a concrete, drawable image — a clear subject, "
        "setting, and action the artist can render. Externalize narration."),
    "reduce_dialogue": (
        "Reduce Dialogue",
        "Cut the dialogue down; let the art and a single essential line carry "
        "the beat."),
    "caption_to_action": (
        "Replace Caption with Action",
        "Turn caption exposition into a visible action or image inside the panel."),
    "clarify_page_turn": (
        "Clarify the Page Turn",
        "Strengthen the last panel of the page so the turn lands on a question, "
        "reveal, or beat that pulls the reader onward."),
    "make_drawable": (
        "Make the Panel Drawable",
        "Make the panel renderable from its description alone — concrete subject, "
        "setting, and action; show emotion as visible behavior."),
    "improve_flow": (
        "Improve Panel Flow",
        "Smooth the panel-to-panel progression so each panel clearly advances "
        "the action."),
    "split_panel": (
        "Split the Overloaded Panel",
        "Split this overloaded panel into a clear sequence of single-action "
        "panels."),
    "strengthen_beat": (
        "Strengthen the Visual Beat",
        "Sharpen the visual beat so the panel's purpose reads at a glance."),
    "establish_location": (
        "Establish the Location",
        "Make the setting clear so the reader and the artist know where this "
        "takes place."),
    "emotion_to_visible": (
        "Make the Emotion Visible",
        "Show the emotional shift through visible behavior, expression, or body "
        "language rather than narration."),
    "from_reflection": (
        "Rewrite from Reflection Notes",
        "Address the Reflection report's most important reader, artist, and "
        "story gaps."),
    "custom": ("Custom Rewrite", ""),
}


def instruction_label(key: str) -> str:
    return INSTRUCTIONS.get(key, INSTRUCTIONS["custom"])[0]


# ===========================================================================
# Rewrite request (context only — never secrets)
# ===========================================================================


@dataclass
class RewriteRequest:
    project_id: int
    scene_id: int
    writing_mode: str = "graphic_novel"
    act: str = ""
    chapter: str = ""
    scene_title: str = ""
    outline_summary: str = ""
    breakdown_text: str = ""
    plan_text: str = ""
    original_body: str = ""
    selected_text: str = ""
    target: str = TARGET_SCENE
    target_page: int | None = None
    target_panel: int | None = None
    reflection_text: str = ""
    health_warnings: list[str] = field(default_factory=list)
    psyke_characters: list[str] = field(default_factory=list)
    instruction_key: str = "custom"
    user_instruction: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id, "scene_id": self.scene_id,
            "writing_mode": self.writing_mode, "act": self.act,
            "chapter": self.chapter, "scene_title": self.scene_title,
            "outline_summary": self.outline_summary,
            "breakdown_text": self.breakdown_text, "plan_text": self.plan_text,
            "original_body": self.original_body, "selected_text": self.selected_text,
            "target": self.target, "target_page": self.target_page,
            "target_panel": self.target_panel,
            "reflection_text": self.reflection_text,
            "health_warnings": list(self.health_warnings),
            "psyke_characters": list(self.psyke_characters),
            "instruction_key": self.instruction_key,
            "user_instruction": self.user_instruction,
        }


def build_rewrite_request(
    db, project_id: int, scene_id: int, *,
    instruction: str = "custom", user_instruction: str = "",
    selected_text: str = "", target: str = TARGET_SCENE,
    target_page: int | None = None, target_panel: int | None = None,
    include_reflection: bool = True, include_health: bool = True,
) -> RewriteRequest:
    """Gather the rewrite context for a scene. Read-only; never reads provider
    settings / API keys."""
    scene = db.get_scene_by_id(scene_id)
    req = RewriteRequest(
        project_id=project_id, scene_id=scene_id,
        instruction_key=instruction if instruction in INSTRUCTIONS else "custom",
        user_instruction=user_instruction, selected_text=selected_text or "",
        target=target if target in TARGETS else TARGET_SCENE,
        target_page=target_page, target_panel=target_panel)
    if scene is None:
        return req
    req.act = (getattr(scene, "act", "") or "").strip()
    req.chapter = (getattr(scene, "chapter", "") or "").strip()
    req.scene_title = (getattr(scene, "title", "") or "").strip()
    req.outline_summary = (getattr(scene, "summary", "") or "").strip()
    req.original_body = getattr(scene, "content", "") or ""

    try:
        from logosforge.writing_modes import get_project_writing_mode_by_id
        req.writing_mode = get_project_writing_mode_by_id(db, project_id)
    except Exception:
        pass
    try:
        bd = gp.get_page_breakdown(db, project_id, scene_id)
        if bd is not None and not bd.is_empty():
            req.breakdown_text = bd.to_text()
        plan = gp.get_panel_plan(db, project_id, scene_id)
        if plan is not None and not plan.is_empty():
            req.plan_text = plan.to_text()
    except Exception:
        pass
    if include_health:
        try:
            from logosforge.graphic_novel_diagnostics import analyze_scene_by_id
            diag = analyze_scene_by_id(db, project_id, scene_id)
            req.health_warnings = [f"{i.label}: {i.evidence}"
                                   for i in diag.top_issues(6)]
        except Exception:
            pass
    if include_reflection:
        try:
            from logosforge.graphic_novel_reflection import build_scene_reflection
            req.reflection_text = build_scene_reflection(
                db, project_id, scene_id).to_text()
        except Exception:
            pass
    return req


# ===========================================================================
# Prompt building
# ===========================================================================

_REWRITE_SYSTEM = (
    "You are a graphic novel scripter performing a targeted revision. Rewrite "
    "ONLY what is requested and return graphic novel page/panel script — PAGE / "
    "PANEL headers and Visual / Caption / Dialogue / SFX / Notes fields. No "
    "markdown, no code fences, no commentary, no image-generation prompts, no "
    "ComfyUI or model/LoRA parameters, and never restate the plan or notes."
)


def build_rewrite_prompt(request: RewriteRequest) -> str:
    """Deterministic rewrite prompt grounded in the scene context. Never embeds
    API keys or provider settings."""
    label, guidance = INSTRUCTIONS.get(request.instruction_key,
                                       INSTRUCTIONS["custom"])
    parts: list[str] = [f"Revision goal: {label}."]
    if guidance:
        parts.append(guidance)
    if request.user_instruction.strip():
        parts.append(f"Writer's instruction: {request.user_instruction.strip()}")

    if request.target == TARGET_PANEL and request.selected_text.strip():
        parts.append("Rewrite ONLY this panel. Return its fields "
                     "(Visual/Caption/Dialogue/SFX/Notes), no PAGE/PANEL header "
                     f"needed:\n\"\"\"\n{request.selected_text.strip()}\n\"\"\"")
    elif request.target == TARGET_PAGE and request.selected_text.strip():
        parts.append("Rewrite ONLY this page. Return its PANELs "
                     f"(PANEL n + fields):\n\"\"\"\n{request.selected_text.strip()}\n\"\"\"")
    elif request.target == TARGET_SELECTION and request.selected_text.strip():
        parts.append("Rewrite ONLY this selected material, returning revised text "
                     f"in the same kind:\n\"\"\"\n{request.selected_text.strip()}\n\"\"\"")
    else:
        parts.append("Rewrite the whole scene as PAGE/PANEL script.")
        if request.original_body.strip():
            parts.append("Current scene script:\n\"\"\"\n"
                         f"{request.original_body.strip()}\n\"\"\"")

    where = " / ".join(p for p in (request.act, request.chapter) if p)
    if where:
        parts.append(f"Scene location: {where}")
    if request.scene_title:
        parts.append(f"Scene title: {request.scene_title}")
    if request.outline_summary:
        parts.append(f"Scene purpose (Outline): {request.outline_summary}")
    if request.breakdown_text:
        parts.append("Page breakdown (respect it; do not restate it):\n"
                     + request.breakdown_text)
    if request.plan_text:
        parts.append("Panel plan (respect it; do not restate it):\n" + request.plan_text)
    if request.instruction_key == "from_reflection" and request.reflection_text:
        parts.append("Reflection to address:\n" + request.reflection_text)
    elif request.health_warnings:
        parts.append("Issues to address:\n- " + "\n- ".join(request.health_warnings))

    parts.append("Return only the revised graphic novel script.")
    return "\n\n".join(parts)


def rewrite_messages(prompt: str) -> list[dict]:
    return [
        {"role": "system", "content": _REWRITE_SYSTEM},
        {"role": "user", "content": prompt},
    ]


# ===========================================================================
# Output parsing + validation (reuse Phase 2)
# ===========================================================================


def parse_rewrite_output(text: str, scene_id: int | None = None
                         ) -> gnb.GraphicNovelScript:
    """Parse an AI rewrite reply into a GraphicNovelScript (strips fences; reuses
    the Phase 1 scene-body parser via the Phase 2 draft parser)."""
    return gp.parse_draft_response(text, scene_id=scene_id)


def _scene_body(db, scene_id: int) -> str:
    scene = db.get_scene_by_id(scene_id)
    return (getattr(scene, "content", "") or "") if scene is not None else ""


def _page_index(script: gnb.GraphicNovelScript, page_number: int | None) -> int | None:
    if page_number is None:
        return None
    for i, page in enumerate(script.pages):
        if page.number == page_number:
            return i
    return None


def _panel_index(page: gnb.Page, panel_number: int | None) -> int | None:
    if panel_number is None:
        return None
    for i, panel in enumerate(page.panels):
        if panel.number == panel_number:
            return i
    return None


def _first_panel(script: gnb.GraphicNovelScript) -> gnb.Panel | None:
    for page in script.pages:
        if page.panels:
            return page.panels[0]
    return None


def validate_rewrite_output(
    text: str, *, target: str = TARGET_SCENE, db=None, scene_id: int | None = None,
    target_page: int | None = None, target_panel: int | None = None,
) -> gp.DraftValidation:
    """Validate rewrite output. Errors block apply; warnings allow it.

    Errors: empty, assistant/system-prompt leakage, image-generation / ComfyUI
    leakage, corrupt structure, and a target mismatch (panel/page target whose
    page/panel doesn't exist or wasn't specified). Code fences are *cleaned*."""
    report = gp.DraftValidation()
    cleaned = gp._strip_fences(text or "")
    if not cleaned.strip():
        report.errors.append("The rewrite is empty.")
        report.is_valid = False
        return report

    low = cleaned.lower()
    if any(p in low for p in gp._LEAK_PHRASES):
        report.errors.append("The rewrite contains assistant commentary or leaked context.")
    if any(p in low for p in _GEN_LEAK_PHRASES):
        report.errors.append("The rewrite contains image-generation / ComfyUI language.")
    if "```" in (text or ""):
        report.warnings.append("Code fences were removed from the rewrite.")

    if target == TARGET_SELECTION:
        report.errors = list(dict.fromkeys(report.errors))
        report.warnings = list(dict.fromkeys(report.warnings))
        report.is_valid = not report.errors
        return report

    # Structured targets: reuse the Phase 2 draft validator (empty/fence/leak/
    # plan-in-body + structural warnings) on the parsed script.
    script = gnb.parse_graphic_novel_text(cleaned)
    draft = gp.validate_draft_script(script)
    report.errors.extend(draft.errors)
    report.warnings.extend(draft.warnings)

    # Target mismatch: a panel/page rewrite must name an existing page/panel.
    if target == TARGET_PANEL and (target_page is None or target_panel is None):
        report.errors.append("Panel rewrite needs a target page and panel.")
    if target == TARGET_PAGE and target_page is None:
        report.errors.append("Page rewrite needs a target page.")
    if db is not None and scene_id is not None and target in (TARGET_PAGE, TARGET_PANEL):
        cur = gnb.parse_graphic_novel_text(_scene_body(db, scene_id))
        if cur.pages and _page_index(cur, target_page) is None:
            report.errors.append("Target page not found in the scene.")
        elif target == TARGET_PANEL:
            pidx = _page_index(cur, target_page)
            if pidx is not None and cur.pages[pidx].panels \
                    and _panel_index(cur.pages[pidx], target_panel) is None:
                report.errors.append("Target panel not found on the page.")

    report.errors = list(dict.fromkeys(report.errors))
    report.warnings = list(dict.fromkeys(report.warnings))
    report.is_valid = not report.errors
    return report


# ===========================================================================
# Page/panel diff + body composition (no mutation)
# ===========================================================================


def _panel_keys(script: gnb.GraphicNovelScript) -> list[str]:
    keys: list[str] = []
    for page in script.pages:
        for p in page.panels:
            keys.append("|".join((p.visual_description.strip(), p.caption.strip(),
                                  p.dialogue.strip(), p.sfx.strip(), p.notes.strip())))
    return keys


def diff_scripts(old: gnb.GraphicNovelScript, new: gnb.GraphicNovelScript) -> dict:
    """A simple, deterministic panel diff: counts of added / removed / changed /
    unchanged panels (compared by field content, by position)."""
    sm = difflib.SequenceMatcher(a=_panel_keys(old), b=_panel_keys(new),
                                 autojunk=False)
    added = removed = changed = unchanged = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            unchanged += (i2 - i1)
        elif tag == "replace":
            changed += max(i2 - i1, j2 - j1)
        elif tag == "delete":
            removed += (i2 - i1)
        elif tag == "insert":
            added += (j2 - j1)
    return {"panels_added": added, "panels_removed": removed,
            "panels_changed": changed, "panels_unchanged": unchanged,
            "pages_old": len(old.pages), "pages_new": len(new.pages)}


def _append_alternate(current: str, new_script: gnb.GraphicNovelScript) -> str:
    existing = gnb.parse_graphic_novel_text(current)
    if existing.is_empty():
        return gnb.serialize_graphic_novel_script(new_script)
    offset = len(existing.pages)
    merged = gnb.GraphicNovelScript(pages=list(existing.pages))
    for i, page in enumerate(new_script.pages, start=1):
        page.number = offset + i
        merged.pages.append(page)
    return gnb.serialize_graphic_novel_script(merged)


def _replace_page(cur: gnb.GraphicNovelScript, new: gnb.GraphicNovelScript,
                  page_number: int | None) -> str:
    if not new.pages:
        return gnb.serialize_graphic_novel_script(cur)
    new_page = new.pages[0]
    out = gnb.GraphicNovelScript(pages=list(cur.pages))
    idx = _page_index(out, page_number)
    if idx is None:
        out.pages.append(gnb.Page(number=len(out.pages) + 1,
                                  title=new_page.title, summary=new_page.summary,
                                  panels=new_page.panels))
    else:
        keep = out.pages[idx]
        keep.title = new_page.title or keep.title
        keep.summary = new_page.summary or keep.summary
        keep.panels = new_page.panels
    gnb._renumber(out)
    return gnb.serialize_graphic_novel_script(out)


def _replace_panel(cur: gnb.GraphicNovelScript, new: gnb.GraphicNovelScript,
                   page_number: int | None, panel_number: int | None) -> str:
    new_panel = _first_panel(new)
    if new_panel is None:
        return gnb.serialize_graphic_novel_script(cur)
    out = gnb.GraphicNovelScript(pages=list(cur.pages))
    pidx = _page_index(out, page_number)
    if pidx is None:
        return gnb.serialize_graphic_novel_script(cur)
    page = out.pages[pidx]
    cidx = _panel_index(page, panel_number)
    if cidx is None:
        page.panels.append(new_panel)
    else:
        page.panels[cidx] = new_panel
    gnb._renumber(out)
    return gnb.serialize_graphic_novel_script(out)


def _compose_proposed_body(
    db, scene_id: int, text: str, *, target: str, target_page: int | None,
    target_panel: int | None, mode: str, selected_text: str = "",
) -> str:
    """Compose the resulting Scene body for *mode*/*target* WITHOUT mutating.

    Structured targets perform page/panel index surgery so only the targeted
    region changes; the rest of the body is preserved verbatim."""
    current = _scene_body(db, scene_id)
    cleaned = gp._strip_fences(text or "")

    if mode == MODE_APPEND_ALTERNATE:
        return _append_alternate(current, gnb.parse_graphic_novel_text(cleaned))

    if target == TARGET_SELECTION:
        repl = cleaned.strip()
        if selected_text and selected_text in current:
            return current.replace(selected_text, repl, 1)
        return repl if not current.strip() else current.rstrip() + "\n\n" + repl

    new_script = gnb.parse_graphic_novel_text(cleaned)
    if target == TARGET_SCENE or not current.strip():
        return gnb.serialize_graphic_novel_script(new_script)
    cur = gnb.parse_graphic_novel_text(current)
    if target == TARGET_PAGE:
        return _replace_page(cur, new_script, target_page)
    if target == TARGET_PANEL:
        return _replace_panel(cur, new_script, target_page, target_panel)
    return gnb.serialize_graphic_novel_script(new_script)


@dataclass
class RewritePreview:
    scene_id: int | None = None
    target: str = TARGET_SCENE
    target_page: int | None = None
    target_panel: int | None = None
    original_text: str = ""
    proposed_text: str = ""
    panel_diff: dict = field(default_factory=dict)
    diff: dict = field(default_factory=dict)
    changed_panels: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    can_apply: bool = True
    body_is_empty: bool = True
    apply_options: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id, "target": self.target,
            "target_page": self.target_page, "target_panel": self.target_panel,
            "original_text": self.original_text, "proposed_text": self.proposed_text,
            "panel_diff": dict(self.panel_diff), "diff": dict(self.diff),
            "changed_panels": self.changed_panels, "warnings": list(self.warnings),
            "errors": list(self.errors), "can_apply": self.can_apply,
            "body_is_empty": self.body_is_empty,
            "apply_options": list(self.apply_options),
        }


def build_rewrite_preview(
    db, project_id: int, scene_id: int, text: str, *,
    target: str = TARGET_SCENE, target_page: int | None = None,
    target_panel: int | None = None, mode: str = MODE_REPLACE,
    selected_text: str = "",
) -> RewritePreview:
    """Build a non-mutating preview: original vs proposed body, a panel diff, a
    text diff, and validation. **No mutation.**"""
    current = _scene_body(db, scene_id)
    preview = RewritePreview(scene_id=scene_id, target=target,
                             target_page=target_page, target_panel=target_panel,
                             original_text=current,
                             body_is_empty=not current.strip())
    validation = validate_rewrite_output(
        text, target=target, db=db, scene_id=scene_id, target_page=target_page,
        target_panel=target_panel)
    preview.errors = list(validation.errors)
    preview.warnings = list(validation.warnings)
    preview.can_apply = validation.is_valid

    proposed = _compose_proposed_body(
        db, scene_id, text, target=target, target_page=target_page,
        target_panel=target_panel, mode=mode, selected_text=selected_text)
    preview.proposed_text = proposed

    try:
        old_script = gnb.parse_graphic_novel_text(current)
        new_full = gnb.parse_graphic_novel_text(proposed)
        preview.panel_diff = diff_scripts(old_script, new_full)
        preview.changed_panels = (preview.panel_diff.get("panels_added", 0)
                                  + preview.panel_diff.get("panels_removed", 0)
                                  + preview.panel_diff.get("panels_changed", 0))
    except Exception:
        preview.panel_diff = {}
    try:
        from logosforge.controlled_apply.diff import build_apply_diff
        preview.diff = build_apply_diff(current, proposed).to_dict()
    except Exception:
        preview.diff = {}
    preview.apply_options = list(APPLY_MODES)
    return preview


# ===========================================================================
# Controlled apply (requires confirmation)
# ===========================================================================


def apply_rewrite(
    db, project_id: int, scene_id: int, text: str, *,
    target: str = TARGET_SCENE, target_page: int | None = None,
    target_panel: int | None = None, mode: str = MODE_REPLACE,
    selected_text: str = "", confirmed: bool = False, label: str = "",
) -> dict:
    """Apply a rewrite. **Requires ``confirmed=True``** — the AI never overwrites
    on its own. Only ``Scene.content`` is touched; Outline/breakdown/plan/
    Timeline/PSYKE/Notes are preserved. A checkpoint is created by Controlled Apply."""
    if mode == MODE_CANCEL:
        return {"ok": False, "cancelled": True}
    if mode == MODE_COPY_ONLY:
        return {"ok": True, "copied": True, "mutated": False,
                "text": gp._strip_fences(text or "")}
    if mode == MODE_REVISION_CANDIDATE:
        return save_rewrite_candidate(db, project_id, scene_id, text, label=label,
                                      confirmed=confirmed)

    validation = validate_rewrite_output(
        text, target=target, db=db, scene_id=scene_id, target_page=target_page,
        target_panel=target_panel)
    if not validation.is_valid:
        return {"ok": False, "error": "Rewrite failed validation.",
                "validation": validation.to_dict()}

    proposed = _compose_proposed_body(
        db, scene_id, text, target=target, target_page=target_page,
        target_panel=target_panel, mode=mode, selected_text=selected_text)

    from logosforge.controlled_apply.service import apply_operation
    result = apply_operation(
        db, project_id, target_type="scene", target_id=scene_id,
        proposed_text=proposed, apply_mode="replace", confirmed=confirmed,
        source_type="graphic_novel_rewrite")
    if result.get("ok"):
        result["mode"] = mode
        result["target"] = target
    return result


def save_rewrite_candidate(
    db, project_id: int, scene_id: int, text: str, *,
    label: str = "", confirmed: bool = False,
) -> dict:
    """Save a rewrite as a scene-linked revision-candidate Note (non-destructive
    to the body). **Requires ``confirmed=True``.**"""
    if not confirmed:
        return {"ok": False,
                "error": "Saving a revision candidate requires confirmation."}
    scene = db.get_scene_by_id(scene_id)
    if scene is None:
        return {"ok": False, "error": "Scene not found."}
    title = (f"Rewrite candidate — {(getattr(scene, 'title', '') or 'Scene').strip()}"
             + (f" ({label})" if label else ""))
    body = gp._strip_fences(text or "")
    try:
        note = db.create_note(project_id, title, body, tags="rewrite-candidate")
        note_id = getattr(note, "id", note)
        db.link_note_to_scene(note_id, scene_id)
    except Exception as exc:
        return {"ok": False, "error": f"Could not save candidate: {exc}"}
    return {"ok": True, "note_id": note_id, "scene_id": scene_id, "mutated": False}
