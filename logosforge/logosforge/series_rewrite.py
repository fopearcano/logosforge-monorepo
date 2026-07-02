"""Series controlled rewrite — targeted revision preview, diff, confirmed apply (Phase 5).

A safe rewrite layer for Series scenes. The AI **never** overwrites the
Manuscript: a rewrite is always *requested → previewed (with a block diff) →
confirmed → applied through Controlled Apply*. This module is the deterministic
orchestration around that flow; the actual generation call is the caller's (UI),
exactly like the Phase 2 draft pipeline. Mirrors ``stage_script_rewrite`` /
``screenplay_rewrite``.

It builds on, and never duplicates, the existing machinery:
* parse/serialize + validation reuse :mod:`logosforge.series_blocks`;
* fence-stripping + leak phrases + the draft validation dataclass reuse
  :mod:`logosforge.series_pipeline`;
* apply + checkpoint reuse :mod:`logosforge.controlled_apply`
  (``target_type="scene"`` → ``Scene.content``);
* context grounding reuses the Phase 2 Season/Arc + Episode plans, the Phase 3
  health checks, and the Phase 4 reflection.

Targets: a selected block (by index), selected text, or the whole scene — each
applied by block-index surgery so only the target changes. Apply only ever
touches ``Scene.content``; Outline summaries, the Season/Arc plan, the Episode
beat plan, Timeline events/links, PSYKE entries, and Notes are all preserved.
Pure logic + DB service calls; no Qt; no provider/API keys ever read or emitted;
and no image generation.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any

from logosforge import series_blocks as sbk
from logosforge import series_pipeline as spp

# -- Rewrite targets ---------------------------------------------------------
TARGET_SELECTION = "selection"     # arbitrary selected text (best-effort replace)
TARGET_BLOCK = "block"             # one or more blocks by index
TARGET_SCENE = "scene"             # the whole scene body
TARGETS = (TARGET_SELECTION, TARGET_BLOCK, TARGET_SCENE)

# -- Apply modes -------------------------------------------------------------
MODE_REPLACE = "replace"
MODE_APPEND_ALTERNATE = "append_alternate"
MODE_COPY_ONLY = "copy_only"
MODE_REVISION_CANDIDATE = "revision_candidate"
MODE_CANCEL = "cancel"
APPLY_MODES = (MODE_REPLACE, MODE_APPEND_ALTERNATE, MODE_COPY_ONLY,
               MODE_REVISION_CANDIDATE, MODE_CANCEL)

# Wrong-mode formatting that must NOT leak into a Series teleplay. Stage Script
# uses labelled cue lines; Graphic Novel uses PAGE/PANEL headers. (INT./EXT. and
# CUT TO: are valid Series teleplay, unlike Stage Script.)
_STAGE_CUE_RE = re.compile(r"(?im)^\s*(stage|enter|exit|light|sound|set)\s*:")
_GN_PANEL_RE = re.compile(r"(?im)^\s*(page|panel)\s*[:#]?\s*(\d+|one|two|three|four)\b")


# Instruction registry: key -> (label, guidance line for the prompt).
INSTRUCTIONS: dict[str, tuple[str, str]] = {
    "rewrite_block": (
        "Rewrite Series Block",
        "Rewrite the selected block(s), preserving teleplay block types where "
        "possible."),
    "rewrite_scene": (
        "Rewrite Series Scene",
        "Rewrite the whole scene as teleplay script."),
    "tighten_dialogue": (
        "Tighten Dialogue",
        "Trim and sharpen the dialogue — cut filler, keep subtext and voice."),
    "reduce_exposition": (
        "Reduce Exposition",
        "Cut expositional dialogue; dramatize the information through action."),
    "add_action": (
        "Add Visible Action",
        "Add visible action so the scene plays on screen, not just in talk."),
    "strengthen_act_break": (
        "Strengthen the Act Break",
        "Build the act-out to a reversal or decision that creates pressure for the "
        "next act."),
    "sharpen_cold_open": (
        "Sharpen the Cold Open",
        "Make the cold open / teaser raise a sharp question that pulls the viewer in."),
    "improve_tag": (
        "Improve the Tag / Button",
        "Make the tag land — an earned button tied to the episode's turn."),
    "strengthen_a_story": (
        "Strengthen the A-Story",
        "Make the scene serve the A-story more clearly and escalate it."),
    "strengthen_b_story": (
        "Strengthen the B-Story",
        "Advance the B-story meaningfully within the scene."),
    "clarify_character_arc": (
        "Clarify the Character Arc",
        "Make the character's want and change visible through action and line."),
    "connect_to_season_arc": (
        "Connect to the Season Arc",
        "Tie the scene to the season/arc question, a setup/payoff, or a recurring "
        "motif."),
    "from_showrunner": (
        "Rewrite from Showrunner Notes",
        "Address the showrunner notes: the scene's job, A/B/C balance, escalation."),
    "from_reflection": (
        "Rewrite from Reflection Notes",
        "Address the reflection's most important audience, showrunner, character, "
        "and episode-structure gaps."),
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
    writing_mode: str = "series"
    act: str = ""
    chapter: str = ""
    episode_label: str = ""
    scene_title: str = ""
    outline_summary: str = ""
    season_plan_text: str = ""
    episode_plan_text: str = ""
    original_body: str = ""
    selected_text: str = ""
    target: str = TARGET_SCENE
    target_block_indices: list[int] = field(default_factory=list)
    reflection_text: str = ""
    health_warnings: list[str] = field(default_factory=list)
    psyke_characters: list[str] = field(default_factory=list)
    instruction_key: str = "custom"
    user_instruction: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id, "scene_id": self.scene_id,
            "writing_mode": self.writing_mode, "act": self.act,
            "chapter": self.chapter, "episode_label": self.episode_label,
            "scene_title": self.scene_title, "outline_summary": self.outline_summary,
            "season_plan_text": self.season_plan_text,
            "episode_plan_text": self.episode_plan_text,
            "original_body": self.original_body, "selected_text": self.selected_text,
            "target": self.target,
            "target_block_indices": list(self.target_block_indices),
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
    target_block_indices: list[int] | None = None,
    include_reflection: bool = True, include_health: bool = True,
) -> RewriteRequest:
    """Gather the rewrite context for a Series scene. Read-only; never reads
    provider settings / API keys."""
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
    req.episode_label = sbk.episode_label(req.chapter) if req.chapter else ""
    req.scene_title = (getattr(scene, "title", "") or "").strip()
    req.outline_summary = (getattr(scene, "summary", "") or "").strip()
    req.original_body = getattr(scene, "content", "") or ""

    try:
        from logosforge.writing_modes import get_project_writing_mode_by_id
        req.writing_mode = get_project_writing_mode_by_id(db, project_id)
    except Exception:
        pass
    try:
        if req.act:
            season = spp.get_season_plan(db, project_id, req.act)
            if season is not None and not season.is_empty():
                req.season_plan_text = season.to_text()
        if req.chapter:
            episode = spp.get_episode_plan(db, project_id, req.chapter)
            if episode is not None and not episode.is_empty():
                req.episode_plan_text = episode.to_text()
    except Exception:
        pass
    try:
        req.psyke_characters = sbk.character_cues(
            sbk.load_scene_script(db, scene_id))
    except Exception:
        pass
    if include_health:
        try:
            from logosforge.series_diagnostics import analyze_scene_by_id
            diag = analyze_scene_by_id(db, project_id, scene_id)
            req.health_warnings = [f"{i.label}: {i.evidence}"
                                   for i in diag.top_issues(6)]
        except Exception:
            pass
    if include_reflection:
        try:
            from logosforge.series_reflection import build_scene_reflection
            req.reflection_text = build_scene_reflection(
                db, project_id, scene_id).to_text()
        except Exception:
            pass
    return req


# ===========================================================================
# Prompt building
# ===========================================================================

_REWRITE_SYSTEM = (
    "You are a television writer performing a targeted revision. Rewrite ONLY what "
    "is requested and return teleplay script: scene headings (INT./EXT.), action, "
    "CHARACTER cues in caps, dialogue, (parentheticals), transitions (CUT TO:), and "
    "serial markers on their own line (COLD OPEN, ACT BREAK, TAG). No markdown, no "
    "code fences, no commentary, no Stage Script cue labels (STAGE:/ENTER:/LIGHT:), "
    "no Graphic Novel page/panel structure, no prose paragraphs masquerading as a "
    "novel, and never restate the plan or notes."
)


def build_rewrite_prompt(request: RewriteRequest) -> str:
    """Deterministic rewrite prompt grounded in the scene context. Never embeds API
    keys or provider settings."""
    label, guidance = INSTRUCTIONS.get(request.instruction_key,
                                       INSTRUCTIONS["custom"])
    parts: list[str] = [f"Revision goal: {label}."]
    if guidance:
        parts.append(guidance)
    if request.user_instruction.strip():
        parts.append(f"Writer's instruction: {request.user_instruction.strip()}")

    if request.target in (TARGET_SELECTION, TARGET_BLOCK) and request.selected_text.strip():
        parts.append("Rewrite ONLY this selected material (keep it teleplay "
                     f"blocks):\n\"\"\"\n{request.selected_text.strip()}\n\"\"\"")
    else:
        parts.append("Rewrite the whole scene as teleplay script.")
        if request.original_body.strip():
            parts.append("Current scene script:\n\"\"\"\n"
                         f"{request.original_body.strip()}\n\"\"\"")

    where = " / ".join(p for p in (request.act, request.episode_label) if p)
    if where:
        parts.append(f"Scene location: {where}")
    if request.scene_title:
        parts.append(f"Scene title: {request.scene_title}")
    if request.outline_summary:
        parts.append(f"Scene purpose (Outline): {request.outline_summary}")
    if request.season_plan_text:
        parts.append("Season / Arc plan (respect it; do not restate it):\n"
                     + request.season_plan_text)
    if request.episode_plan_text:
        parts.append("Episode beat plan (respect it; do not restate it):\n"
                     + request.episode_plan_text)
    if request.instruction_key == "from_reflection" and request.reflection_text:
        parts.append("Reflection to address:\n" + request.reflection_text)
    elif request.health_warnings:
        parts.append("Issues to address:\n- " + "\n- ".join(request.health_warnings))

    parts.append("Return only the revised teleplay script.")
    return "\n\n".join(parts)


def rewrite_messages(prompt: str) -> list[dict]:
    return [{"role": "system", "content": _REWRITE_SYSTEM},
            {"role": "user", "content": prompt}]


# ===========================================================================
# Output parsing + validation
# ===========================================================================


def parse_rewrite_output(text: str, scene_id: int | None = None) -> sbk.SeriesScript:
    """Parse an AI rewrite reply into a SeriesScript (strips fences; reuses the
    Phase 1 scene-body parser)."""
    script = sbk.parse_series_text(spp._strip_fences(text or ""))
    if scene_id is not None:
        for b in script.blocks:
            b.scene_id = scene_id
    return script


def _scene_body(db, scene_id: int) -> str:
    scene = db.get_scene_by_id(scene_id)
    return (getattr(scene, "content", "") or "") if scene is not None else ""


def validate_rewrite_output(
    text: str, *, target: str = TARGET_SCENE, db=None, scene_id: int | None = None,
    target_block_indices: list[int] | None = None,
) -> spp.DraftValidation:
    """Validate rewrite output. Errors block apply; warnings allow it.

    Errors: empty, assistant/system-prompt leakage, wrong-mode formatting (Stage
    Script cues or Graphic Novel page/panel structure), and a block-target
    mismatch. Code fences are *cleaned* (a warning)."""
    report = spp.DraftValidation()
    cleaned = spp._strip_fences(text or "")
    if not cleaned.strip():
        report.errors.append("The rewrite is empty.")
        report.is_valid = False
        return report

    low = cleaned.lower()
    if any(p in low for p in spp._LEAK_PHRASES):
        report.errors.append("The rewrite contains assistant commentary or leaked context.")
    if _STAGE_CUE_RE.search(cleaned):
        report.errors.append("The rewrite uses Stage Script cue formatting "
                             "(STAGE:/ENTER:/LIGHT:…), not Series teleplay.")
    if _GN_PANEL_RE.search(cleaned):
        report.errors.append("The rewrite uses Graphic Novel page/panel structure, "
                             "not Series teleplay.")
    if "```" in (text or ""):
        report.warnings.append("Code fences were removed from the rewrite.")

    if target == TARGET_SELECTION:
        report.errors = list(dict.fromkeys(report.errors))
        report.warnings = list(dict.fromkeys(report.warnings))
        report.is_valid = not report.errors
        return report

    script = sbk.parse_series_text(cleaned)
    if script.is_empty():
        report.errors.append("The rewrite has no Series blocks.")
    sv = sbk.validate_series_script(script)
    report.warnings.extend(w for w in sv.warnings if "no script" not in w.lower())

    if target == TARGET_BLOCK and not target_block_indices:
        report.errors.append("Block rewrite needs a target block.")
    if db is not None and scene_id is not None and target == TARGET_BLOCK \
            and target_block_indices:
        cur = sbk.parse_series_text(_scene_body(db, scene_id))
        if cur.blocks and not any(0 <= i < len(cur.blocks)
                                  for i in target_block_indices):
            report.errors.append("Target block not found in the scene.")

    report.errors = list(dict.fromkeys(report.errors))
    report.warnings = list(dict.fromkeys(report.warnings))
    report.is_valid = not report.errors
    return report


# ===========================================================================
# Block diff + body composition (no mutation)
# ===========================================================================


def _block_keys(script: sbk.SeriesScript) -> list[str]:
    return [f"{b.block_type}|{(b.text or '').strip()}" for b in script.blocks]


def diff_blocks(old: sbk.SeriesScript, new: sbk.SeriesScript) -> dict:
    """A simple, deterministic block diff: counts of added / removed / changed /
    unchanged blocks (compared by type+text, by position)."""
    sm = difflib.SequenceMatcher(a=_block_keys(old), b=_block_keys(new),
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
    return {"added": added, "removed": removed, "changed": changed,
            "unchanged": unchanged, "blocks_old": len(old.blocks),
            "blocks_new": len(new.blocks)}


def _compose_proposed_body(
    db, scene_id: int, text: str, *, target: str,
    target_block_indices: list[int] | None, mode: str, selected_text: str = "",
) -> str:
    """Compose the resulting Scene body for *mode*/*target* WITHOUT mutating.

    Block targets perform index surgery so only the targeted blocks change; the
    rest of the body is preserved verbatim."""
    current = _scene_body(db, scene_id)
    cleaned = spp._strip_fences(text or "")

    if mode == MODE_APPEND_ALTERNATE:
        new = sbk.parse_series_text(cleaned)
        existing = sbk.parse_series_text(current)
        if not existing.is_empty():
            merged = sbk.SeriesScript(blocks=list(existing.blocks) + list(new.blocks))
            sbk._renumber(merged)
            return sbk.serialize_series_script(merged)
        return sbk.serialize_series_script(new)

    if target == TARGET_SELECTION:
        repl = cleaned.strip()
        if selected_text and selected_text in current:
            return current.replace(selected_text, repl, 1)
        return repl if not current.strip() else current.rstrip() + "\n\n" + repl

    new = sbk.parse_series_text(cleaned)
    if target == TARGET_SCENE or not current.strip():
        return sbk.serialize_series_script(new)
    cur = sbk.parse_series_text(current)
    if target == TARGET_BLOCK and target_block_indices:
        idxs = sorted(i for i in target_block_indices if 0 <= i < len(cur.blocks))
        if not idxs:
            return sbk.serialize_series_script(new)
        start, end = idxs[0], idxs[-1]
        merged = sbk.SeriesScript(
            blocks=cur.blocks[:start] + list(new.blocks) + cur.blocks[end + 1:])
        sbk._renumber(merged)
        return sbk.serialize_series_script(merged)
    return sbk.serialize_series_script(new)


@dataclass
class RewritePreview:
    scene_id: int | None = None
    target: str = TARGET_SCENE
    target_block_indices: list[int] = field(default_factory=list)
    target_description: str = ""
    original_text: str = ""
    proposed_text: str = ""
    block_diff: dict = field(default_factory=dict)
    diff: dict = field(default_factory=dict)
    changed_blocks: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    can_apply: bool = True
    body_is_empty: bool = True
    apply_options: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id, "target": self.target,
            "target_block_indices": list(self.target_block_indices),
            "target_description": self.target_description,
            "original_text": self.original_text, "proposed_text": self.proposed_text,
            "block_diff": dict(self.block_diff), "diff": dict(self.diff),
            "changed_blocks": self.changed_blocks, "warnings": list(self.warnings),
            "errors": list(self.errors), "can_apply": self.can_apply,
            "body_is_empty": self.body_is_empty,
            "apply_options": list(self.apply_options),
        }


def _target_description(target: str, indices: list[int] | None) -> str:
    if target == TARGET_SELECTION:
        return "Selected text"
    if target == TARGET_BLOCK:
        idxs = indices or []
        return ("Selected block " + ", ".join(str(i + 1) for i in idxs)
                if idxs else "Selected block")
    return "Whole Series scene"


def build_rewrite_preview(
    db, project_id: int, scene_id: int, text: str, *,
    target: str = TARGET_SCENE, target_block_indices: list[int] | None = None,
    mode: str = MODE_REPLACE, selected_text: str = "",
) -> RewritePreview:
    """Build a non-mutating preview: original vs proposed body, a block diff, a text
    diff, the target description, and validation. **No mutation.**"""
    current = _scene_body(db, scene_id)
    preview = RewritePreview(
        scene_id=scene_id, target=target,
        target_block_indices=list(target_block_indices or []),
        target_description=_target_description(target, target_block_indices),
        original_text=current, body_is_empty=not current.strip())
    validation = validate_rewrite_output(
        text, target=target, db=db, scene_id=scene_id,
        target_block_indices=target_block_indices)
    preview.errors = list(validation.errors)
    preview.warnings = list(validation.warnings)
    preview.can_apply = validation.is_valid

    proposed = _compose_proposed_body(
        db, scene_id, text, target=target,
        target_block_indices=target_block_indices, mode=mode,
        selected_text=selected_text)
    preview.proposed_text = proposed

    try:
        old_script = sbk.parse_series_text(current)
        new_full = sbk.parse_series_text(proposed)
        preview.block_diff = diff_blocks(old_script, new_full)
        preview.changed_blocks = (preview.block_diff.get("added", 0)
                                  + preview.block_diff.get("removed", 0)
                                  + preview.block_diff.get("changed", 0))
    except Exception:
        preview.block_diff = {}
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
    target: str = TARGET_SCENE, target_block_indices: list[int] | None = None,
    mode: str = MODE_REPLACE, selected_text: str = "", confirmed: bool = False,
    label: str = "",
) -> dict:
    """Apply a rewrite. **Requires ``confirmed=True``** — the AI never overwrites on
    its own. Only ``Scene.content`` is touched; Outline / Season-Arc plan / Episode
    plan / Timeline / PSYKE / Notes are preserved. A checkpoint is created by
    Controlled Apply."""
    if mode == MODE_CANCEL:
        return {"ok": False, "cancelled": True}
    if mode == MODE_COPY_ONLY:
        return {"ok": True, "copied": True, "mutated": False,
                "text": spp._strip_fences(text or "")}
    if mode == MODE_REVISION_CANDIDATE:
        return save_rewrite_candidate(db, project_id, scene_id, text, label=label,
                                      confirmed=confirmed)

    validation = validate_rewrite_output(
        text, target=target, db=db, scene_id=scene_id,
        target_block_indices=target_block_indices)
    if not validation.is_valid:
        return {"ok": False, "error": "Rewrite failed validation.",
                "validation": validation.to_dict()}

    proposed = _compose_proposed_body(
        db, scene_id, text, target=target,
        target_block_indices=target_block_indices, mode=mode,
        selected_text=selected_text)

    from logosforge.controlled_apply.service import apply_operation
    result = apply_operation(
        db, project_id, target_type="scene", target_id=scene_id,
        proposed_text=proposed, apply_mode="replace", confirmed=confirmed,
        source_type="series_rewrite")
    if result.get("ok"):
        result["mode"] = mode
        result["target"] = target
    return result


def save_rewrite_candidate(
    db, project_id: int, scene_id: int, text: str, *,
    label: str = "", confirmed: bool = False,
) -> dict:
    """Save a rewrite as a scene-linked revision-candidate Note (non-destructive to
    the body). **Requires ``confirmed=True``.**"""
    if not confirmed:
        return {"ok": False,
                "error": "Saving a revision candidate requires confirmation."}
    scene = db.get_scene_by_id(scene_id)
    if scene is None:
        return {"ok": False, "error": "Scene not found."}
    title = (f"Rewrite candidate — {(getattr(scene, 'title', '') or 'Scene').strip()}"
             + (f" ({label})" if label else ""))
    body = spp._strip_fences(text or "")
    try:
        note = db.create_note(project_id, title, body, tags="rewrite-candidate")
        note_id = getattr(note, "id", note)
        db.link_note_to_scene(note_id, scene_id)
    except Exception as exc:
        return {"ok": False, "error": f"Could not save candidate: {exc}"}
    return {"ok": True, "note_id": note_id, "scene_id": scene_id, "mutated": False}
