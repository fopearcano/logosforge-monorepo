"""Screenplay controlled rewrite — targeted revision preview, diff, confirmed apply (Phase 6).

A safe rewrite layer for screenplay scenes. The AI **never** overwrites the
Manuscript: a rewrite is always *requested → previewed (with a block diff) →
confirmed → applied through Controlled Apply*. This module is the deterministic
orchestration around that flow; the actual generation call is the caller's (UI),
exactly like Phase 2's draft pipeline.

It builds on, and never duplicates, the existing machinery:
* validation + block parsing reuse :mod:`logosforge.screenplay_pipeline`
  (``parse_draft_blocks`` / ``validate_draft_blocks``);
* apply + checkpoint reuse :mod:`logosforge.controlled_apply`
  (``build_apply_preview`` / ``apply_operation`` with ``screenplay_block``);
* context grounding reuses the Phase 2 beat plan, Phase 3 health, and Phase 5
  Counterpart reflection.

Apply only ever touches ``Scene.content`` — Outline summaries, beat plans,
Timeline events/links, PSYKE entries, and Notes are all preserved. Pure logic +
DB service calls; no Qt; no provider/API keys ever read or emitted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from logosforge import screenplay_blocks as sb
from logosforge import screenplay_pipeline as spp

# -- Rewrite targets ---------------------------------------------------------
TARGET_SELECTION = "selection"      # a contiguous block range (selected text/blocks)
TARGET_BLOCK = "block"              # one or more blocks by index
TARGET_SCENE = "scene"             # the whole scene body
TARGETS = (TARGET_SELECTION, TARGET_BLOCK, TARGET_SCENE)

# -- Apply modes -------------------------------------------------------------
MODE_REPLACE = "replace"                  # replace the target (selection/block/scene)
MODE_APPEND_ALTERNATE = "append_alternate"  # add as an alternate, keep the original
MODE_COPY_ONLY = "copy_only"              # no mutation — just hand back the text
MODE_REVISION_CANDIDATE = "revision_candidate"  # save as a scene-linked Note
MODE_CANCEL = "cancel"
APPLY_MODES = (MODE_REPLACE, MODE_APPEND_ALTERNATE, MODE_COPY_ONLY,
               MODE_REVISION_CANDIDATE, MODE_CANCEL)


# Instruction registry: key -> (label, guidance line for the prompt).
INSTRUCTIONS: dict[str, tuple[str, str]] = {
    "make_more_visual": (
        "Make More Visual",
        "Recast the material as visible, filmable action — what the camera sees "
        "and hears. Externalize interior narration."),
    "tighten_dialogue": (
        "Tighten Dialogue",
        "Tighten the dialogue — cut throat-clearing, on-the-nose exposition, and "
        "redundancy — while preserving intent and subtext."),
    "strengthen_conflict": (
        "Strengthen Conflict",
        "Raise the visible conflict and stakes; make the opposing want or "
        "obstacle concrete and active."),
    "add_subtext": (
        "Add Subtext",
        "Put the feeling and intent under the line rather than in it; let "
        "behavior carry meaning."),
    "reduce_exposition": (
        "Reduce Exposition",
        "Reduce expositional dialogue and interior explanation; convert it into "
        "action, behavior, or implication."),
    "add_turning_point": (
        "Add a Visible Turning Point",
        "Make the scene turn on a clear, visible value shift by the last beat."),
    "reduce_monologue": (
        "Reduce Monologue",
        "Break up long speeches; interrupt with action or another voice."),
    "emotion_to_behavior": (
        "Convert Emotion to Behavior",
        "Convert directly-stated emotion into observable behavior or action."),
    "make_filmable": (
        "Make It More Filmable",
        "Make every line playable on screen — visible, audible, and economical."),
    "from_counterpart": (
        "Rewrite from Counterpart Notes",
        "Address the Counterpart reflection's findings — the most important "
        "internal-character and external-audience gaps it surfaced."),
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
    writing_mode: str = "screenplay"
    act: str = ""
    chapter: str = ""
    scene_title: str = ""
    outline_summary: str = ""
    beat_plan_text: str = ""
    original_body: str = ""
    selected_text: str = ""
    target: str = TARGET_SCENE
    target_block_indices: list[int] = field(default_factory=list)
    counterpart_text: str = ""
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
            "beat_plan_text": self.beat_plan_text,
            "original_body": self.original_body, "selected_text": self.selected_text,
            "target": self.target,
            "target_block_indices": list(self.target_block_indices),
            "counterpart_text": self.counterpart_text,
            "health_warnings": list(self.health_warnings),
            "psyke_characters": list(self.psyke_characters),
            "instruction_key": self.instruction_key,
            "user_instruction": self.user_instruction,
        }


def build_rewrite_request(
    db, project_id: int, scene_id: int, *,
    instruction: str = "custom", user_instruction: str = "",
    selected_text: str = "", target: str = TARGET_SCENE,
    target_block_indices: list[int] | None = None,
    include_counterpart: bool = True, include_health: bool = True,
) -> RewriteRequest:
    """Gather the rewrite context for a scene. Read-only; never reads provider
    settings / API keys."""
    scene = db.get_scene_by_id(scene_id)
    req = RewriteRequest(
        project_id=project_id, scene_id=scene_id,
        instruction_key=instruction if instruction in INSTRUCTIONS else "custom",
        user_instruction=user_instruction, selected_text=selected_text or "",
        target=target if target in TARGETS else TARGET_SCENE,
        target_block_indices=list(target_block_indices or []))
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
        plan = spp.get_beat_plan(db, project_id, scene_id)
        if plan is not None and not plan.is_empty():
            req.beat_plan_text = plan.to_text()
    except Exception:
        pass
    if include_health:
        try:
            from logosforge.screenplay_diagnostics import analyze_scene_by_id
            diag = analyze_scene_by_id(db, project_id, scene_id)
            req.health_warnings = [f"{i.label}: {i.evidence}"
                                   for i in diag.top_issues(6)]
            req.psyke_characters = list(diag.unique_characters)
        except Exception:
            pass
    if include_counterpart:
        try:
            from logosforge.screenplay_reflection import build_scene_reflection
            req.counterpart_text = build_scene_reflection(
                db, project_id, scene_id).to_text()
        except Exception:
            pass
    return req


# ===========================================================================
# Prompt building
# ===========================================================================

_REWRITE_SYSTEM = (
    "You are a screenwriter performing a targeted revision. Rewrite ONLY what is "
    "requested, returning screenplay text — scene heading, action, character "
    "cues, dialogue, parentheticals, transitions. No markdown, no code fences, "
    "no commentary, no labels, and never restate the notes or the beat plan."
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

    if request.target in (TARGET_SELECTION, TARGET_BLOCK) and request.selected_text.strip():
        parts.append("Rewrite ONLY this selected material (keep it screenplay "
                     f"text):\n\"\"\"\n{request.selected_text.strip()}\n\"\"\"")
    else:
        parts.append("Rewrite the whole scene body below.")
        if request.original_body.strip():
            parts.append(f"Current scene body:\n\"\"\"\n{request.original_body.strip()}\n\"\"\"")

    where = " / ".join(p for p in (request.act, request.chapter) if p)
    if where:
        parts.append(f"Scene location: {where}")
    if request.scene_title:
        parts.append(f"Scene title: {request.scene_title}")
    if request.outline_summary:
        parts.append(f"Scene purpose (Outline): {request.outline_summary}")
    if request.beat_plan_text:
        parts.append("Beat plan (respect it; do not restate it):\n"
                     + request.beat_plan_text)
    if request.instruction_key == "from_counterpart" and request.counterpart_text:
        parts.append("Counterpart reflection to address:\n" + request.counterpart_text)
    elif request.health_warnings:
        parts.append("Issues to address:\n- " + "\n- ".join(request.health_warnings))

    parts.append("Return only the revised screenplay text.")
    return "\n\n".join(parts)


def rewrite_messages(prompt: str) -> list[dict]:
    return [
        {"role": "system", "content": _REWRITE_SYSTEM},
        {"role": "user", "content": prompt},
    ]


# ===========================================================================
# Output parsing + validation (reuse Phase 2)
# ===========================================================================


def parse_rewrite_output(text: str, scene_id: int | None = None) -> list[sb.ScreenplayBlock]:
    """Parse an AI rewrite reply into screenplay blocks (strips fences, etc.)."""
    return spp.parse_draft_blocks(text, scene_id=scene_id)


def validate_rewrite_output(
    blocks: list[sb.ScreenplayBlock], *, target: str = TARGET_SCENE,
    original_blocks: list[sb.ScreenplayBlock] | None = None,
) -> spp.DraftValidation:
    """Validate rewrite output. Reuses the Phase 2 draft validation (empty / fence
    / leak / orphan checks) and adds a scene-heading-removal warning for
    whole-scene rewrites. Errors block apply; warnings allow it."""
    report = spp.validate_draft_blocks(blocks)
    if target == TARGET_SCENE and original_blocks is not None:
        had_heading = any(b.element_type == "scene_heading" for b in original_blocks)
        has_heading = any(b.element_type == "scene_heading" for b in blocks)
        if had_heading and not has_heading:
            report.warnings.append(
                "The rewrite drops the scene heading the original had.")
            report.warnings = list(dict.fromkeys(report.warnings))
    return report


# ===========================================================================
# Block diff + preview (no mutation)
# ===========================================================================


def diff_blocks(
    old: list[sb.ScreenplayBlock], new: list[sb.ScreenplayBlock],
) -> dict[str, int]:
    """A simple, deterministic block diff: counts of added / removed / changed /
    unchanged blocks (compared as ``type|text`` by position)."""
    def key(b: sb.ScreenplayBlock) -> str:
        return f"{b.element_type}|{(b.text or '').strip()}"

    old_keys = [key(b) for b in old]
    new_keys = [key(b) for b in new]
    import difflib
    sm = difflib.SequenceMatcher(a=old_keys, b=new_keys, autojunk=False)
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
    return {"added": added, "removed": removed, "changed": changed,
            "unchanged": unchanged}


@dataclass
class RewritePreview:
    scene_id: int | None = None
    target: str = TARGET_SCENE
    original_text: str = ""
    proposed_text: str = ""
    block_diff: dict = field(default_factory=dict)
    diff: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    can_apply: bool = True
    body_is_empty: bool = True
    apply_options: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id, "target": self.target,
            "original_text": self.original_text, "proposed_text": self.proposed_text,
            "block_diff": dict(self.block_diff), "diff": dict(self.diff),
            "warnings": list(self.warnings), "errors": list(self.errors),
            "can_apply": self.can_apply, "body_is_empty": self.body_is_empty,
            "apply_options": list(self.apply_options),
        }


def _scene_body(db, scene_id: int) -> str:
    scene = db.get_scene_by_id(scene_id)
    return (getattr(scene, "content", "") or "") if scene is not None else ""


def _compose_proposed_body(
    db, scene_id: int, new_blocks: list[sb.ScreenplayBlock], *,
    target: str, target_block_indices: list[int] | None, mode: str,
) -> str:
    """Compose the resulting scene body for *mode*/*target* WITHOUT mutating.

    Block/selection targets perform index surgery so only the targeted blocks
    change; the rest of the body is preserved verbatim."""
    current = _scene_body(db, scene_id)
    new_text = sb.serialize_blocks(new_blocks)
    if mode == MODE_APPEND_ALTERNATE:
        return (current + "\n\n" + new_text) if current.strip() else new_text
    if target == TARGET_SCENE or not target_block_indices:
        return new_text
    cur_blocks = sb.parse_screenplay_text(current, scene_id=scene_id)
    idxs = sorted(i for i in target_block_indices if 0 <= i < len(cur_blocks))
    if not idxs:
        return new_text
    start, end = idxs[0], idxs[-1]
    merged = cur_blocks[:start] + list(new_blocks) + cur_blocks[end + 1:]
    return sb.serialize_blocks(merged)


def _apply_options(target: str, body_is_empty: bool) -> list[str]:
    opts = [MODE_REPLACE, MODE_APPEND_ALTERNATE, MODE_COPY_ONLY]
    opts.append(MODE_REVISION_CANDIDATE)
    opts.append(MODE_CANCEL)
    return opts


def build_rewrite_preview(
    db, project_id: int, scene_id: int, new_blocks: list[sb.ScreenplayBlock], *,
    target: str = TARGET_SCENE, target_block_indices: list[int] | None = None,
    mode: str = MODE_REPLACE,
) -> RewritePreview:
    """Build a non-mutating preview: original vs proposed body, a block diff, a
    text diff, and validation. **No mutation.**"""
    current = _scene_body(db, scene_id)
    preview = RewritePreview(scene_id=scene_id, target=target,
                             original_text=current,
                             body_is_empty=not current.strip())
    original_blocks = sb.parse_screenplay_text(current, scene_id=scene_id)
    validation = validate_rewrite_output(new_blocks, target=target,
                                         original_blocks=original_blocks)
    preview.errors = list(validation.errors)
    preview.warnings = list(validation.warnings)
    preview.can_apply = validation.is_valid

    proposed = _compose_proposed_body(
        db, scene_id, new_blocks, target=target,
        target_block_indices=target_block_indices, mode=mode)
    preview.proposed_text = proposed
    preview.block_diff = diff_blocks(original_blocks,
                                     sb.parse_screenplay_text(proposed))

    try:
        from logosforge.controlled_apply.diff import build_apply_diff
        preview.diff = build_apply_diff(current, proposed).to_dict()
    except Exception:
        preview.diff = {}
    preview.apply_options = _apply_options(target, preview.body_is_empty)
    return preview


# ===========================================================================
# Controlled apply (requires confirmation)
# ===========================================================================


def apply_rewrite(
    db, project_id: int, scene_id: int, new_blocks: list[sb.ScreenplayBlock], *,
    target: str = TARGET_SCENE, target_block_indices: list[int] | None = None,
    mode: str = MODE_REPLACE, confirmed: bool = False, label: str = "",
) -> dict:
    """Apply a rewrite. **Requires ``confirmed=True``** — the AI never overwrites
    on its own. Only ``Scene.content`` is touched; Outline/beat plan/Timeline/
    PSYKE/Notes are preserved. A checkpoint is created by Controlled Apply."""
    if mode == MODE_CANCEL:
        return {"ok": False, "cancelled": True}
    if mode == MODE_COPY_ONLY:
        return {"ok": True, "copied": True, "mutated": False,
                "text": sb.serialize_blocks(new_blocks)}
    if mode == MODE_REVISION_CANDIDATE:
        return save_rewrite_candidate(
            db, project_id, scene_id, new_blocks, label=label, confirmed=confirmed)

    original_blocks = sb.parse_screenplay_text(_scene_body(db, scene_id),
                                               scene_id=scene_id)
    validation = validate_rewrite_output(new_blocks, target=target,
                                         original_blocks=original_blocks)
    if not validation.is_valid:
        return {"ok": False, "error": "Rewrite failed validation.",
                "validation": validation.to_dict()}

    proposed = _compose_proposed_body(
        db, scene_id, new_blocks, target=target,
        target_block_indices=target_block_indices, mode=mode)

    from logosforge.controlled_apply.service import apply_operation
    result = apply_operation(
        db, project_id, target_type="screenplay_block", target_id=scene_id,
        proposed_text=proposed, apply_mode="replace", confirmed=confirmed,
        source_type="screenplay_rewrite")
    if result.get("ok"):
        result["mode"] = mode
        result["target"] = target
    return result


def save_rewrite_candidate(
    db, project_id: int, scene_id: int, new_blocks: list[sb.ScreenplayBlock], *,
    label: str = "", confirmed: bool = False,
) -> dict:
    """Save a rewrite as a scene-linked revision-candidate Note (non-destructive
    to the body). **Requires ``confirmed=True``.**"""
    if not confirmed:
        return {"ok": False, "error": "Saving a revision candidate requires confirmation."}
    scene = db.get_scene_by_id(scene_id)
    if scene is None:
        return {"ok": False, "error": "Scene not found."}
    title = (f"Rewrite candidate — {(getattr(scene, 'title', '') or 'Scene').strip()}"
             + (f" ({label})" if label else ""))
    body = sb.serialize_blocks(new_blocks)
    try:
        note = db.create_note(project_id, title, body, tags="rewrite-candidate")
        note_id = getattr(note, "id", note)
        db.link_note_to_scene(note_id, scene_id)
    except Exception as exc:
        return {"ok": False, "error": f"Could not save candidate: {exc}"}
    return {"ok": True, "note_id": note_id, "scene_id": scene_id, "mutated": False}
