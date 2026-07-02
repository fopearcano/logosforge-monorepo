"""Screenplay scene-planning pipeline (Phase 2).

The deterministic, safety-critical core of the planning pipeline:

    Outline scene summary  →  Beat Plan  →  Screenplay draft preview  →  confirmed apply

Design contract (non-negotiable):
* The AI **never** overwrites the Manuscript body. Generation only ever produces
  a *beat plan* or a *draft preview*; nothing reaches ``Scene.content`` until the
  author confirms and the change passes through Controlled Apply.
* The **beat plan is a third artifact**, stored separately from the Manuscript
  body (``Scene.content``) and the Outline summary (``Scene.summary``). It lives
  in project settings (``screenplay_beat_plans``) — **no schema change**.
* All apply paths reuse the existing Controlled Apply gate
  (``controlled_apply.service``) with ``target_type="screenplay_block"``, so the
  draft lands on ``Scene.content`` only via the validated adapter, after a
  checkpoint, and only with ``confirmed=True``.

Pure logic: no Qt, no provider/LLM client. The prompt builders return strings;
the parsers turn an LLM reply into structured data; validation is rule-based; the
UI owns the actual provider call and the confirm dialogs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from logosforge import screenplay as sp
from logosforge.screenplay_blocks import (
    ScreenplayBlock,
    parse_screenplay_text,
    serialize_blocks,
)

# Project-settings key holding all beat plans for a project, keyed by str(scene_id).
SETTINGS_KEY = "screenplay_beat_plans"

# Apply-mode tokens for the controlled draft apply (UI-level intents).
APPLY_TO_EMPTY = "apply_to_empty"   # only when the body is empty (no data loss)
APPLY_REPLACE = "replace"           # replace existing body (UI must double-confirm)
APPLY_APPEND = "append"             # append to existing body
APPLY_CANCEL = "cancel"             # do nothing
APPLY_MODES = (APPLY_TO_EMPTY, APPLY_REPLACE, APPLY_APPEND, APPLY_CANCEL)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ===========================================================================
# Beat plan model
# ===========================================================================


@dataclass
class ScreenplayBeatPlan:
    """A scene's dramatic plan — separate from body and from Outline summary.

    Captures *intent* (what the scene must accomplish), never finished screenplay
    text. ``visual_beats`` / ``dialogue_intentions`` are ordered lists of short
    descriptions; the rest are single fields.
    """

    scene_id: int | None = None
    objective: str = ""            # what the POV character wants in the scene
    dramatic_question: str = ""    # the question the scene poses
    conflict: str = ""             # the opposition / obstacle
    turning_point: str = ""        # the value shift the scene turns on
    emotional_shift: str = ""      # start emotion -> end emotion
    visual_beats: list[str] = field(default_factory=list)         # filmable beats
    dialogue_intentions: list[str] = field(default_factory=list)  # what lines must do
    continuity_notes: str = ""     # setups/payoffs/callbacks to respect
    created_at: str = ""
    updated_at: str = ""

    # -- lifecycle -----------------------------------------------------------

    def is_empty(self) -> bool:
        return not any((
            self.objective.strip(), self.dramatic_question.strip(),
            self.conflict.strip(), self.turning_point.strip(),
            self.emotional_shift.strip(), self.continuity_notes.strip(),
            [b for b in self.visual_beats if b.strip()],
            [d for d in self.dialogue_intentions if d.strip()],
        ))

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "objective": self.objective,
            "dramatic_question": self.dramatic_question,
            "conflict": self.conflict,
            "turning_point": self.turning_point,
            "emotional_shift": self.emotional_shift,
            "visual_beats": list(self.visual_beats),
            "dialogue_intentions": list(self.dialogue_intentions),
            "continuity_notes": self.continuity_notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ScreenplayBeatPlan":
        d = d or {}
        return cls(
            scene_id=d.get("scene_id"),
            objective=d.get("objective", "") or "",
            dramatic_question=d.get("dramatic_question", "") or "",
            conflict=d.get("conflict", "") or "",
            turning_point=d.get("turning_point", "") or "",
            emotional_shift=d.get("emotional_shift", "") or "",
            visual_beats=[str(x) for x in (d.get("visual_beats") or [])],
            dialogue_intentions=[str(x) for x in (d.get("dialogue_intentions") or [])],
            continuity_notes=d.get("continuity_notes", "") or "",
            created_at=d.get("created_at", "") or "",
            updated_at=d.get("updated_at", "") or "",
        )

    def to_text(self) -> str:
        """Render the plan in the canonical labelled format (round-trips through
        :func:`parse_beat_plan_response`). Empty fields are omitted."""
        lines: list[str] = []
        if self.objective.strip():
            lines.append(f"Objective: {self.objective.strip()}")
        if self.dramatic_question.strip():
            lines.append(f"Dramatic Question: {self.dramatic_question.strip()}")
        if self.conflict.strip():
            lines.append(f"Conflict: {self.conflict.strip()}")
        if self.turning_point.strip():
            lines.append(f"Turning Point: {self.turning_point.strip()}")
        if self.emotional_shift.strip():
            lines.append(f"Emotional Shift: {self.emotional_shift.strip()}")
        beats = [b.strip() for b in self.visual_beats if b.strip()]
        if beats:
            lines.append("Visual Beats:")
            lines.extend(f"- {b}" for b in beats)
        intents = [d.strip() for d in self.dialogue_intentions if d.strip()]
        if intents:
            lines.append("Dialogue Intentions:")
            lines.extend(f"- {d}" for d in intents)
        if self.continuity_notes.strip():
            lines.append(f"Continuity Notes: {self.continuity_notes.strip()}")
        return "\n".join(lines)


# ===========================================================================
# Settings-based storage (no schema migration)
# ===========================================================================


def _read_store(db, project_id: int) -> dict:
    try:
        settings = db.get_project_settings(project_id) or {}
    except Exception:
        return {}
    store = settings.get(SETTINGS_KEY)
    return dict(store) if isinstance(store, dict) else {}


def _write_store(db, project_id: int, store: dict) -> None:
    try:
        settings = db.get_project_settings(project_id) or {}
    except Exception:
        settings = {}
    settings[SETTINGS_KEY] = store
    db.save_project_settings(project_id, settings)


def get_beat_plan(db, project_id: int, scene_id: int) -> ScreenplayBeatPlan | None:
    """Return the stored beat plan for *scene_id*, or ``None`` if none exists."""
    raw = _read_store(db, project_id).get(str(scene_id))
    if not isinstance(raw, dict):
        return None
    plan = ScreenplayBeatPlan.from_dict(raw)
    plan.scene_id = scene_id
    return plan


def has_beat_plan(db, project_id: int, scene_id: int) -> bool:
    plan = get_beat_plan(db, project_id, scene_id)
    return plan is not None and not plan.is_empty()


def save_beat_plan(db, project_id: int, plan: ScreenplayBeatPlan) -> ScreenplayBeatPlan:
    """Persist *plan* (separate from body/summary). Stamps timestamps.

    This writes ONLY the beat-plan store inside project settings — it never
    touches ``Scene.content`` or ``Scene.summary``.
    """
    if plan.scene_id is None:
        raise ValueError("save_beat_plan requires plan.scene_id")
    store = _read_store(db, project_id)
    existing = store.get(str(plan.scene_id))
    if isinstance(existing, dict) and existing.get("created_at"):
        plan.created_at = existing["created_at"]
    elif not plan.created_at:
        plan.created_at = _now()
    plan.updated_at = _now()
    store[str(plan.scene_id)] = plan.to_dict()
    _write_store(db, project_id, store)
    return plan


def clear_beat_plan(db, project_id: int, scene_id: int) -> bool:
    """Remove a scene's beat plan. Returns True if one was removed."""
    store = _read_store(db, project_id)
    if str(scene_id) in store:
        del store[str(scene_id)]
        _write_store(db, project_id, store)
        return True
    return False


def all_beat_plans(db, project_id: int) -> dict[int, ScreenplayBeatPlan]:
    out: dict[int, ScreenplayBeatPlan] = {}
    for key, raw in _read_store(db, project_id).items():
        try:
            sid = int(key)
        except (TypeError, ValueError):
            continue
        if isinstance(raw, dict):
            plan = ScreenplayBeatPlan.from_dict(raw)
            plan.scene_id = sid
            out[sid] = plan
    return out


# ===========================================================================
# Prompt builders (deterministic strings)
# ===========================================================================

_BEAT_PLAN_SYSTEM = (
    "You are a screenplay development assistant. You produce a concise scene "
    "BEAT PLAN — the scene's dramatic intent — not finished screenplay text. "
    "Never write scene description, action lines, or dialogue. Output only the "
    "labelled plan."
)

_DRAFT_SYSTEM = (
    "You are a screenwriter. You write a short, lean screenplay draft for a "
    "single scene, realizing ONLY the supplied beat plan. Output screenplay text "
    "only — scene heading, action, character cues, dialogue, parentheticals, "
    "transitions. No markdown, no code fences, no commentary, no labels, and do "
    "not restate the beat plan."
)

_BEAT_PLAN_TEMPLATE = (
    "Objective: <what the viewpoint character wants in the scene>\n"
    "Dramatic Question: <the question the scene poses>\n"
    "Conflict: <the opposition or obstacle>\n"
    "Turning Point: <the value shift the scene turns on>\n"
    "Emotional Shift: <from-emotion to to-emotion>\n"
    "Visual Beats:\n- <a filmable beat>\n- <another filmable beat>\n"
    "Dialogue Intentions:\n- <what a line must accomplish, not the line itself>\n"
    "Continuity Notes: <setups/payoffs/callbacks to respect, or 'none'>"
)


def _scene_meta(db, project_id: int, scene_id: int) -> dict[str, str]:
    scene = db.get_scene_by_id(scene_id)
    if scene is None:
        return {"title": "", "summary": "", "act": "", "chapter": "", "content": ""}
    return {
        "title": (getattr(scene, "title", "") or "").strip(),
        "summary": (getattr(scene, "summary", "") or "").strip(),
        "act": (getattr(scene, "act", "") or "").strip(),
        "chapter": (getattr(scene, "chapter", "") or "").strip(),
        "content": getattr(scene, "content", "") or "",
    }


def _mode_block(db, project_id: int) -> str:
    try:
        from logosforge.writing_modes import (
            get_project_writing_mode_by_id,
            mode_context_block,
        )
        return mode_context_block(get_project_writing_mode_by_id(db, project_id))
    except Exception:
        return ""


def build_beat_plan_prompt(db, project_id: int, scene_id: int) -> str:
    """The user prompt for generating/refining a scene's beat plan.

    Grounded in the Outline **summary** (intent), never the body — so generating
    a plan is independent of whatever is (or isn't) drafted yet.
    """
    meta = _scene_meta(db, project_id, scene_id)
    parts: list[str] = [
        "Create a beat plan for this screenplay scene. Base it on the scene's "
        "intent (its summary), not on any drafted text. Be concrete and concise.",
    ]
    where = " / ".join(p for p in (meta["act"], meta["chapter"]) if p)
    if where:
        parts.append(f"Scene location in structure: {where}")
    if meta["title"]:
        parts.append(f"Scene title: {meta['title']}")
    if meta["summary"]:
        parts.append(f"Scene summary (intent):\n\"\"\"\n{meta['summary']}\n\"\"\"")
    else:
        parts.append("Scene summary (intent): (none provided — infer a minimal, "
                     "plausible plan from the title and structure)")

    existing = get_beat_plan(db, project_id, scene_id)
    if existing is not None and not existing.is_empty():
        parts.append("There is an existing beat plan to refine (improve, do not "
                     "discard its intent):\n" + existing.to_text())

    mode_block = _mode_block(db, project_id)
    if mode_block:
        parts.append(mode_block)

    parts.append("Respond with ONLY this labelled format (omit a line if truly "
                 "not applicable):\n" + _BEAT_PLAN_TEMPLATE)
    return "\n\n".join(parts)


def build_draft_prompt(
    db, project_id: int, scene_id: int,
    beat_plan: ScreenplayBeatPlan | None = None,
) -> str:
    """The user prompt for drafting screenplay text from a beat plan."""
    plan = beat_plan or get_beat_plan(db, project_id, scene_id)
    meta = _scene_meta(db, project_id, scene_id)
    parts: list[str] = [
        "Write a short, lean screenplay draft for this single scene that "
        "realizes ONLY the beat plan below. Enter late and leave early; prefer "
        "visible action and subtextual dialogue. Do not invent material beyond "
        "the plan. Output screenplay text only — no commentary, no markdown.",
    ]
    if meta["title"]:
        parts.append(f"Scene title: {meta['title']}")
    if plan is not None and not plan.is_empty():
        parts.append("Beat plan:\n" + plan.to_text())
    else:
        parts.append("Beat plan: (none — keep the draft minimal and faithful to "
                     "the scene summary)")
        if meta["summary"]:
            parts.append(f"Scene summary:\n\"\"\"\n{meta['summary']}\n\"\"\"")

    parts.append("Begin with a scene heading (e.g. INT. LOCATION - DAY) when one "
                 "is implied. Use UPPERCASE character cues above their dialogue.")
    return "\n\n".join(parts)


def beat_plan_messages(prompt: str) -> list[dict]:
    """System+user message pair for a beat-plan generation request."""
    return [
        {"role": "system", "content": _BEAT_PLAN_SYSTEM},
        {"role": "user", "content": prompt},
    ]


def draft_messages(prompt: str) -> list[dict]:
    """System+user message pair for a draft generation request."""
    return [
        {"role": "system", "content": _DRAFT_SYSTEM},
        {"role": "user", "content": prompt},
    ]


# ===========================================================================
# Parsers (LLM reply -> structured data)
# ===========================================================================

_FENCE_RE = re.compile(r"^\s*```[\w-]*\s*$")


def _strip_code_fences(text: str) -> str:
    """Return the content of the first fenced block if present, else the text
    with stray fence lines removed."""
    if "```" not in (text or ""):
        return text or ""
    lines = (text or "").splitlines()
    fence_idx = [i for i, ln in enumerate(lines) if _FENCE_RE.match(ln)]
    if len(fence_idx) >= 2:
        inner = lines[fence_idx[0] + 1:fence_idx[1]]
        return "\n".join(inner)
    # Unbalanced — just drop fence lines.
    return "\n".join(ln for ln in lines if not _FENCE_RE.match(ln))


# Label -> field mapping for the beat-plan parser (longest/most-specific first).
_SINGLE_LABELS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("dramatic question", "central question", "question"), "dramatic_question"),
    (("turning point", "turn", "reversal"), "turning_point"),
    (("emotional shift", "value shift", "emotion"), "emotional_shift"),
    (("objective", "goal", "want"), "objective"),
    (("conflict", "obstacle", "opposition"), "conflict"),
    (("continuity notes", "continuity", "setups/payoffs", "setups", "payoffs"),
     "continuity_notes"),
)
_LIST_LABELS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("visual beats", "action beats", "beats"), "visual_beats"),
    (("dialogue intentions", "dialogue goals", "dialogue"), "dialogue_intentions"),
)
_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.*)$")


def _match_label(line: str) -> tuple[str, str, str] | None:
    """Return (kind, field, value) for a labelled line, else None.

    kind is 'single' or 'list'. value is the inline remainder after the colon.
    """
    if ":" not in line:
        return None
    head, _, rest = line.partition(":")
    key = head.strip().lower()
    for labels, fieldname in _SINGLE_LABELS:
        if key in labels:
            return ("single", fieldname, rest.strip())
    for labels, fieldname in _LIST_LABELS:
        if key in labels:
            return ("list", fieldname, rest.strip())
    return None


def parse_beat_plan_response(
    text: str, scene_id: int | None = None,
) -> ScreenplayBeatPlan:
    """Tolerant parser: turn a labelled (or loosely labelled) reply into a plan.

    Recognizes the canonical labels case-insensitively; collects bullet lines
    under list labels (Visual Beats / Dialogue Intentions). Unlabelled prose is
    ignored rather than guessed into a field.
    """
    plan = ScreenplayBeatPlan(scene_id=scene_id)
    cleaned = _strip_code_fences(text or "")
    lines = cleaned.replace("\r\n", "\n").split("\n")

    current_list: list[str] | None = None
    current_single: str | None = None  # field currently accumulating wrapped text

    for raw in lines:
        line = raw.rstrip()
        matched = _match_label(line)
        if matched is not None:
            kind, fieldname, value = matched
            current_list = None
            current_single = None
            if kind == "list":
                current_list = getattr(plan, fieldname)
                if value:
                    current_list.append(value)
            else:  # single
                setattr(plan, fieldname, value)
                current_single = fieldname if not value else None
            continue

        stripped = line.strip()
        if not stripped:
            current_single = None
            continue

        bullet = _BULLET_RE.match(line)
        if current_list is not None and bullet:
            current_list.append(bullet.group(1).strip())
            continue
        if current_list is not None and not bullet:
            # A non-bullet line right under a list label still counts as one item.
            current_list.append(stripped)
            continue
        if current_single is not None:
            # Wrapped continuation of a single-value field.
            prev = getattr(plan, current_single)
            setattr(plan, current_single, (prev + " " + stripped).strip())
            continue
        # Otherwise: unlabelled prose — ignore (do not guess).

    return plan


def parse_draft_blocks(
    text: str, scene_id: int | None = None,
) -> list[ScreenplayBlock]:
    """Parse a screenplay draft reply into typed blocks (no DB write).

    Strips markdown code fences, then reuses the conservative
    :func:`screenplay_blocks.parse_screenplay_text`.
    """
    cleaned = _strip_code_fences(text or "")
    return parse_screenplay_text(cleaned, scene_id=scene_id)


# ===========================================================================
# Deterministic validation
# ===========================================================================

# Phrases that indicate the model leaked commentary / the prompt instead of a
# clean draft — these BLOCK the apply (protect the body).
_LEAK_PHRASES = (
    "as an ai", "as a language model", "i cannot ", "i can't ",
    "here is the screenplay", "here's the screenplay", "here is a screenplay",
    "here is the draft", "here's the draft", "sure, here", "sure! here",
    "[beat plan]", "[scene context]", "[project mode]", "system prompt",
)
# Beat-plan labels that must NOT appear as draft body lines.
_PLAN_LABELS_IN_BODY = (
    "objective:", "dramatic question:", "turning point:", "emotional shift:",
    "dialogue intentions:", "visual beats:", "continuity notes:",
)


@dataclass
class DraftValidation:
    is_valid: bool = True
    errors: list[str] = field(default_factory=list)      # block the apply
    warnings: list[str] = field(default_factory=list)     # allow, but surface

    def to_dict(self) -> dict[str, Any]:
        return {"is_valid": self.is_valid,
                "errors": list(self.errors), "warnings": list(self.warnings)}


def validate_draft_blocks(
    blocks: list[ScreenplayBlock], *, require_scene_heading: bool = False,
) -> DraftValidation:
    """Rule-based check of a parsed draft. Errors block; warnings don't.

    Errors guard the Manuscript body from junk: an empty draft, leaked markdown
    fences, the beat plan pasted as body, or assistant commentary. Structural
    quirks (orphan dialogue, missing heading) are warnings — the author decides.
    """
    report = DraftValidation()
    if not blocks:
        report.errors.append("The draft is empty.")
        report.is_valid = False
        return report

    body = serialize_blocks(blocks)
    if not body.strip():
        report.errors.append("The draft is empty.")
        report.is_valid = False
        return report

    low = body.lower()
    if "```" in body:
        report.errors.append("The draft contains markdown code fences.")
    for phrase in _LEAK_PHRASES:
        if phrase in low:
            report.errors.append(
                "The draft contains assistant commentary or leaked context.")
            break
    for block in blocks:
        first = (block.text or "").strip().lower().split("\n", 1)[0]
        if any(first.startswith(lbl) for lbl in _PLAN_LABELS_IN_BODY):
            report.errors.append(
                "The draft contains the beat plan instead of screenplay text.")
            break

    # -- structural warnings --
    has_heading = any(b.element_type == "scene_heading" for b in blocks)
    if not has_heading:
        msg = "No scene heading; one is expected for screenplay export."
        if require_scene_heading:
            report.errors.append(msg)
        else:
            report.warnings.append(msg)

    in_dialogue = False
    for b in blocks:
        et = b.element_type
        if et == "character":
            in_dialogue = True
            continue
        if et in ("scene_heading", "action", "transition", "shot", "note"):
            in_dialogue = False
            continue
        if et == "dialogue" and not in_dialogue:
            report.warnings.append("Dialogue without a preceding character cue.")
        elif et == "parenthetical" and not in_dialogue:
            report.warnings.append("Parenthetical without dialogue context.")

    # De-duplicate while preserving order.
    report.errors = list(dict.fromkeys(report.errors))
    report.warnings = list(dict.fromkeys(report.warnings))
    report.is_valid = not report.errors
    return report


# ===========================================================================
# Controlled apply (preview -> confirmed apply)
# ===========================================================================


def _scene_body(db, scene_id: int) -> str:
    scene = db.get_scene_by_id(scene_id)
    return getattr(scene, "content", "") or "" if scene is not None else ""


def resolve_apply_mode(
    db, project_id: int, scene_id: int, requested: str,
) -> tuple[str, bool, str]:
    """Map a UI apply intent to a Controlled-Apply mode.

    Returns ``(controlled_mode, requires_extra_confirm, error)``:
    * ``apply_to_empty`` is only allowed when the body is empty (no data loss);
      otherwise it errors so an empty-only action can never clobber real text.
    * ``replace`` always asks the UI to double-confirm.
    * ``append`` is additive.
    """
    body = _scene_body(db, scene_id)
    is_empty = not body.strip()
    if requested == APPLY_CANCEL:
        return ("", False, "cancelled")
    if requested == APPLY_TO_EMPTY:
        if is_empty:
            return ("replace", False, "")
        return ("", False,
                "The scene body is not empty — choose Replace or Append.")
    if requested == APPLY_REPLACE:
        # Replacing an empty body is harmless; replacing real text needs confirm.
        return ("replace", not is_empty, "")
    if requested == APPLY_APPEND:
        return ("append", False, "")
    return ("", False, f"Unknown apply mode: {requested!r}")


def preview_draft_apply(
    db, project_id: int, scene_id: int,
    blocks: list[ScreenplayBlock], *, mode: str = APPLY_REPLACE,
):
    """Build a Controlled-Apply preview for the draft. **No mutation.**

    Returns the ``ApplyPreview`` (diff + conflicts) or ``None`` on a mode error.
    """
    controlled_mode, _confirm, err = resolve_apply_mode(
        db, project_id, scene_id, mode)
    if err:
        return None
    from logosforge.controlled_apply.service import build_apply_preview
    return build_apply_preview(
        db, project_id, target_type="screenplay_block", target_id=scene_id,
        proposed_text=serialize_blocks(blocks), apply_mode=controlled_mode,
        source_type="screenplay_beat_plan")


def apply_draft(
    db, project_id: int, scene_id: int,
    blocks: list[ScreenplayBlock], *,
    mode: str = APPLY_REPLACE, confirmed: bool = False,
) -> dict:
    """Apply a draft to the Manuscript body through Controlled Apply.

    The AI never reaches here on its own: ``confirmed`` defaults to ``False`` and
    the underlying ``apply_operation`` refuses without it. The draft is also
    validated (errors block) before any write.
    """
    if mode == APPLY_CANCEL:
        return {"ok": False, "cancelled": True}

    validation = validate_draft_blocks(blocks)
    if not validation.is_valid:
        return {"ok": False, "error": "Draft failed validation.",
                "validation": validation.to_dict()}

    controlled_mode, _requires_confirm, err = resolve_apply_mode(
        db, project_id, scene_id, mode)
    if err:
        return {"ok": False, "error": err}

    from logosforge.controlled_apply.service import apply_operation
    return apply_operation(
        db, project_id, target_type="screenplay_block", target_id=scene_id,
        proposed_text=serialize_blocks(blocks), apply_mode=controlled_mode,
        confirmed=confirmed, source_type="screenplay_beat_plan")


# ===========================================================================
# Assistant / Logos context
# ===========================================================================


def beat_plan_context(db, project_id: int, scene_id: int | None) -> str:
    """A short, labelled ``[Beat Plan]`` block for the Assistant scene context.

    Returns ``""`` for non-screenplay projects or when no usable plan exists, so
    it adds nothing for Novel work or unplanned scenes.
    """
    if scene_id is None:
        return ""
    try:
        from logosforge.writing_modes import get_project_writing_mode_by_id, SCREENPLAY
        if get_project_writing_mode_by_id(db, project_id) != SCREENPLAY:
            return ""
    except Exception:
        return ""
    plan = get_beat_plan(db, project_id, scene_id)
    if plan is None or plan.is_empty():
        return ""
    return "[Beat Plan]\n" + plan.to_text()
