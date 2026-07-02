"""Stage Script planning pipeline (Phase 2).

The deterministic, safety-critical bridge:

    Outline Scene summary  →  Stage Beat Plan  →  Blocking / Cue Plan  →
    stage-script draft preview  →  confirmed apply to the Scene body

Design contract (non-negotiable):
* The AI **never** overwrites the Manuscript body. Generation only ever produces
  a *stage beat plan*, a *blocking/cue plan*, or a *draft preview*; nothing
  reaches ``Scene.content`` until the author confirms and the change passes
  through Controlled Apply.
* The **beat plan** and **blocking/cue plan** are planning artifacts, stored
  separately from the Manuscript body (``Scene.content``) and the Outline summary
  (``Scene.summary``) — in project settings (``stage_beat_plans`` /
  ``stage_blocking_plans``). **No schema change.**
* Apply reuses the existing Controlled Apply gate (``target_type="scene"`` →
  ``Scene.content``), so the draft lands on the body only via the validated
  adapter, after a checkpoint, and only with ``confirmed=True``.

Pure logic: no Qt, no provider/LLM client. Prompt builders return strings; the
parsers turn an LLM reply into structured data; validation is rule-based; the UI
owns the actual provider call and the confirm dialogs. Mirrors
``graphic_novel_pipeline`` / ``screenplay_pipeline``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from logosforge import stage_script_blocks as ssb

# Project-settings keys (keyed by str(scene_id)).
BEAT_KEY = "stage_beat_plans"
BLOCKING_KEY = "stage_blocking_plans"

# Apply-mode tokens (UI-level intents) — mirror the other pipelines.
APPLY_TO_EMPTY = "apply_to_empty"
APPLY_REPLACE = "replace"
APPLY_APPEND = "append"
APPLY_CANCEL = "cancel"
APPLY_MODES = (APPLY_TO_EMPTY, APPLY_REPLACE, APPLY_APPEND, APPLY_CANCEL)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean_list(items) -> list[str]:
    return [str(x).strip() for x in (items or []) if str(x).strip()]


# ===========================================================================
# Stage Beat Plan model
# ===========================================================================


@dataclass
class StageBeatPlan:
    """A scene's stage beat plan — separate from body and Outline summary."""

    scene_id: int | None = None
    objective: str = ""
    dramatic_question: str = ""
    conflict: str = ""
    turning_point: str = ""
    emotional_shift: str = ""
    dialogue_beats: list[str] = field(default_factory=list)
    stage_action_beats: list[str] = field(default_factory=list)
    entrances: list[str] = field(default_factory=list)
    exits: list[str] = field(default_factory=list)
    continuity_notes: str = ""
    created_at: str = ""
    updated_at: str = ""

    def is_empty(self) -> bool:
        return not any((
            self.objective.strip(), self.dramatic_question.strip(),
            self.conflict.strip(), self.turning_point.strip(),
            self.emotional_shift.strip(), self.continuity_notes.strip(),
            _clean_list(self.dialogue_beats), _clean_list(self.stage_action_beats),
            _clean_list(self.entrances), _clean_list(self.exits)))

    def to_dict(self) -> dict[str, Any]:
        return {"scene_id": self.scene_id, "objective": self.objective,
                "dramatic_question": self.dramatic_question,
                "conflict": self.conflict, "turning_point": self.turning_point,
                "emotional_shift": self.emotional_shift,
                "dialogue_beats": list(self.dialogue_beats),
                "stage_action_beats": list(self.stage_action_beats),
                "entrances": list(self.entrances), "exits": list(self.exits),
                "continuity_notes": self.continuity_notes,
                "created_at": self.created_at, "updated_at": self.updated_at}

    @classmethod
    def from_dict(cls, d: dict) -> "StageBeatPlan":
        d = d or {}
        return cls(
            scene_id=d.get("scene_id"), objective=d.get("objective", "") or "",
            dramatic_question=d.get("dramatic_question", "") or "",
            conflict=d.get("conflict", "") or "",
            turning_point=d.get("turning_point", "") or "",
            emotional_shift=d.get("emotional_shift", "") or "",
            dialogue_beats=[str(x) for x in (d.get("dialogue_beats") or [])],
            stage_action_beats=[str(x) for x in (d.get("stage_action_beats") or [])],
            entrances=[str(x) for x in (d.get("entrances") or [])],
            exits=[str(x) for x in (d.get("exits") or [])],
            continuity_notes=d.get("continuity_notes", "") or "",
            created_at=d.get("created_at", "") or "",
            updated_at=d.get("updated_at", "") or "")

    def to_text(self) -> str:
        lines: list[str] = []
        for label, val in (("Objective", self.objective),
                           ("Dramatic Question", self.dramatic_question),
                           ("Conflict", self.conflict),
                           ("Turning Point", self.turning_point),
                           ("Emotional Shift", self.emotional_shift),
                           ("Continuity Notes", self.continuity_notes)):
            if val.strip():
                lines.append(f"{label}: {val.strip()}")
        for label, items in (("Dialogue Beats", self.dialogue_beats),
                             ("Stage Action Beats", self.stage_action_beats),
                             ("Entrances", self.entrances), ("Exits", self.exits)):
            its = _clean_list(items)
            if its:
                lines.append(f"{label}:")
                lines.extend(f"- {i}" for i in its)
        return "\n".join(lines)


# ===========================================================================
# Blocking / Cue Plan model
# ===========================================================================


@dataclass
class BlockingCuePlan:
    """A scene's blocking / cue plan — planning data, never Manuscript body."""

    scene_id: int | None = None
    staging_area_notes: str = ""
    character_positions: list[str] = field(default_factory=list)
    movement_beats: list[str] = field(default_factory=list)
    entrance_exit_plan: list[str] = field(default_factory=list)
    lighting_cues: list[str] = field(default_factory=list)
    sound_cues: list[str] = field(default_factory=list)
    prop_notes: list[str] = field(default_factory=list)
    set_notes: str = ""
    transition_notes: str = ""
    created_at: str = ""
    updated_at: str = ""

    def is_empty(self) -> bool:
        return not any((
            self.staging_area_notes.strip(), self.set_notes.strip(),
            self.transition_notes.strip(),
            _clean_list(self.character_positions), _clean_list(self.movement_beats),
            _clean_list(self.entrance_exit_plan), _clean_list(self.lighting_cues),
            _clean_list(self.sound_cues), _clean_list(self.prop_notes)))

    def to_dict(self) -> dict[str, Any]:
        return {"scene_id": self.scene_id,
                "staging_area_notes": self.staging_area_notes,
                "character_positions": list(self.character_positions),
                "movement_beats": list(self.movement_beats),
                "entrance_exit_plan": list(self.entrance_exit_plan),
                "lighting_cues": list(self.lighting_cues),
                "sound_cues": list(self.sound_cues),
                "prop_notes": list(self.prop_notes), "set_notes": self.set_notes,
                "transition_notes": self.transition_notes,
                "created_at": self.created_at, "updated_at": self.updated_at}

    @classmethod
    def from_dict(cls, d: dict) -> "BlockingCuePlan":
        d = d or {}
        return cls(
            scene_id=d.get("scene_id"),
            staging_area_notes=d.get("staging_area_notes", "") or "",
            character_positions=[str(x) for x in (d.get("character_positions") or [])],
            movement_beats=[str(x) for x in (d.get("movement_beats") or [])],
            entrance_exit_plan=[str(x) for x in (d.get("entrance_exit_plan") or [])],
            lighting_cues=[str(x) for x in (d.get("lighting_cues") or [])],
            sound_cues=[str(x) for x in (d.get("sound_cues") or [])],
            prop_notes=[str(x) for x in (d.get("prop_notes") or [])],
            set_notes=d.get("set_notes", "") or "",
            transition_notes=d.get("transition_notes", "") or "",
            created_at=d.get("created_at", "") or "",
            updated_at=d.get("updated_at", "") or "")

    def to_text(self) -> str:
        lines: list[str] = []
        if self.staging_area_notes.strip():
            lines.append(f"Staging Area: {self.staging_area_notes.strip()}")
        for label, items in (("Character Positions", self.character_positions),
                             ("Movement Beats", self.movement_beats),
                             ("Entrance / Exit Plan", self.entrance_exit_plan),
                             ("Lighting Cues", self.lighting_cues),
                             ("Sound Cues", self.sound_cues),
                             ("Prop Notes", self.prop_notes)):
            its = _clean_list(items)
            if its:
                lines.append(f"{label}:")
                lines.extend(f"- {i}" for i in its)
        if self.set_notes.strip():
            lines.append(f"Set Notes: {self.set_notes.strip()}")
        if self.transition_notes.strip():
            lines.append(f"Transition Notes: {self.transition_notes.strip()}")
        return "\n".join(lines)


# ===========================================================================
# Settings-backed storage (project-bound; keyed by scene id) — no schema change
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


def get_beat_plan(db, project_id: int, scene_id: int) -> StageBeatPlan | None:
    raw = _read(db, project_id, BEAT_KEY).get(str(scene_id))
    if not isinstance(raw, dict):
        return None
    plan = StageBeatPlan.from_dict(raw)
    plan.scene_id = scene_id
    return plan


def has_beat_plan(db, project_id: int, scene_id: int) -> bool:
    plan = get_beat_plan(db, project_id, scene_id)
    return plan is not None and not plan.is_empty()


def save_beat_plan(db, project_id: int, plan: StageBeatPlan) -> StageBeatPlan:
    if plan.scene_id is None:
        raise ValueError("save_beat_plan requires scene_id")
    store = _read(db, project_id, BEAT_KEY)
    existing = store.get(str(plan.scene_id))
    if isinstance(existing, dict) and existing.get("created_at"):
        plan.created_at = existing["created_at"]
    elif not plan.created_at:
        plan.created_at = _now()
    plan.updated_at = _now()
    store[str(plan.scene_id)] = plan.to_dict()
    _write(db, project_id, BEAT_KEY, store)
    return plan


def clear_beat_plan(db, project_id: int, scene_id: int) -> bool:
    store = _read(db, project_id, BEAT_KEY)
    if str(scene_id) in store:
        del store[str(scene_id)]
        _write(db, project_id, BEAT_KEY, store)
        return True
    return False


def get_blocking_plan(db, project_id: int, scene_id: int) -> BlockingCuePlan | None:
    raw = _read(db, project_id, BLOCKING_KEY).get(str(scene_id))
    if not isinstance(raw, dict):
        return None
    plan = BlockingCuePlan.from_dict(raw)
    plan.scene_id = scene_id
    return plan


def has_blocking_plan(db, project_id: int, scene_id: int) -> bool:
    plan = get_blocking_plan(db, project_id, scene_id)
    return plan is not None and not plan.is_empty()


def save_blocking_plan(db, project_id: int, plan: BlockingCuePlan) -> BlockingCuePlan:
    if plan.scene_id is None:
        raise ValueError("save_blocking_plan requires scene_id")
    store = _read(db, project_id, BLOCKING_KEY)
    existing = store.get(str(plan.scene_id))
    if isinstance(existing, dict) and existing.get("created_at"):
        plan.created_at = existing["created_at"]
    elif not plan.created_at:
        plan.created_at = _now()
    plan.updated_at = _now()
    store[str(plan.scene_id)] = plan.to_dict()
    _write(db, project_id, BLOCKING_KEY, store)
    return plan


def clear_blocking_plan(db, project_id: int, scene_id: int) -> bool:
    store = _read(db, project_id, BLOCKING_KEY)
    if str(scene_id) in store:
        del store[str(scene_id)]
        _write(db, project_id, BLOCKING_KEY, store)
        return True
    return False


# ===========================================================================
# Prompt builders
# ===========================================================================

_BEAT_SYSTEM = (
    "You are a dramaturg. Produce a concise STAGE BEAT PLAN — the dramatic spine "
    "of a stage scene — not stage script or dialogue. Output only the labelled plan."
)
_BLOCKING_SYSTEM = (
    "You are a stage director. Produce a concise BLOCKING / CUE PLAN — staging, "
    "movement, entrances/exits, and light/sound cues — not finished stage script. "
    "Output only the labelled plan."
)
_DRAFT_SYSTEM = (
    "You are a playwright. Write a stage-play SCRIPT realizing ONLY the supplied "
    "beat plan and blocking/cue plan. Output stage script only, using labelled "
    "lines: SCENE:, STAGE:, CHARACTER:, dialogue lines, (parentheticals), ENTER:, "
    "EXIT:, LIGHT:, SOUND:, SET:, TRANSITION:, NOTE:. No markdown, no code fences, "
    "no commentary, and do not restate the plan."
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


def build_beat_plan_prompt(db, project_id: int, scene_id: int) -> str:
    meta = _scene_meta(db, scene_id)
    parts = ["Create a STAGE BEAT PLAN for this scene, based on its intent "
             "(summary), not on any drafted stage script. Be concrete and concise."]
    where = " / ".join(p for p in (meta["act"], meta["chapter"]) if p)
    if where:
        parts.append(f"Scene location: {where}")
    if meta["title"]:
        parts.append(f"Scene title: {meta['title']}")
    if meta["summary"]:
        parts.append(f"Scene summary (intent):\n\"\"\"\n{meta['summary']}\n\"\"\"")
    else:
        parts.append("Scene summary: (none — infer a minimal plausible plan).")
    existing = get_beat_plan(db, project_id, scene_id)
    if existing is not None and not existing.is_empty():
        parts.append("Existing beat plan to refine:\n" + existing.to_text())
    mode = _mode_block(db, project_id)
    if mode:
        parts.append(mode)
    parts.append(
        "Respond with ONLY this labelled format (omit a line if not applicable):\n"
        "Objective: <...>\nDramatic Question: <...>\nConflict: <...>\n"
        "Turning Point: <...>\nEmotional Shift: <start -> end>\n"
        "Dialogue Beats:\n- <beat>\nStage Action Beats:\n- <beat>\n"
        "Entrances:\n- <who / when>\nExits:\n- <who / when>\n"
        "Continuity Notes: <...>")
    return "\n\n".join(parts)


def build_blocking_plan_prompt(db, project_id: int, scene_id: int,
                              beat: StageBeatPlan | None = None) -> str:
    bp = beat or get_beat_plan(db, project_id, scene_id)
    meta = _scene_meta(db, scene_id)
    parts = ["Create a BLOCKING / CUE PLAN for this stage scene — staging, "
             "movement, entrances/exits, and light/sound cues. Not finished script."]
    if meta["title"]:
        parts.append(f"Scene title: {meta['title']}")
    if bp is not None and not bp.is_empty():
        parts.append("Stage beat plan:\n" + bp.to_text())
    elif meta["summary"]:
        parts.append(f"Scene summary:\n\"\"\"\n{meta['summary']}\n\"\"\"")
    parts.append(
        "Respond with ONLY this labelled format (omit a line if not applicable):\n"
        "Staging Area: <...>\nCharacter Positions:\n- <who / where>\n"
        "Movement Beats:\n- <...>\nEntrance / Exit Plan:\n- <...>\n"
        "Lighting Cues:\n- <...>\nSound Cues:\n- <...>\nProp Notes:\n- <...>\n"
        "Set Notes: <...>\nTransition Notes: <...>")
    return "\n\n".join(parts)


def build_draft_prompt(db, project_id: int, scene_id: int,
                       beat: StageBeatPlan | None = None,
                       blocking: BlockingCuePlan | None = None) -> str:
    bp = beat or get_beat_plan(db, project_id, scene_id)
    bk = blocking or get_blocking_plan(db, project_id, scene_id)
    meta = _scene_meta(db, scene_id)
    parts = ["Write the stage-play SCRIPT for this scene, realizing ONLY the beat "
             "plan and blocking/cue plan. Script only — no commentary, no markdown."]
    if meta["title"]:
        parts.append(f"Scene title: {meta['title']}")
    if bp is not None and not bp.is_empty():
        parts.append("Stage beat plan:\n" + bp.to_text())
    if bk is not None and not bk.is_empty():
        parts.append("Blocking / cue plan:\n" + bk.to_text())
    if (bp is None or bp.is_empty()) and (bk is None or bk.is_empty()) and meta["summary"]:
        parts.append(f"Scene summary:\n\"\"\"\n{meta['summary']}\n\"\"\"")
    parts.append(
        "Use exactly this labelled body format:\nSCENE: <title>\n\n"
        "STAGE: <stage direction>\n\nCHARACTER: NAME\n(parenthetical)\n<dialogue>\n\n"
        "ENTER: <who enters>\n\nLIGHT: <cue>\n\nSOUND: <cue>\n\nSET: <note>\n\n"
        "TRANSITION: <blackout / transition>")
    return "\n\n".join(parts)


def beat_plan_messages(prompt: str) -> list[dict]:
    return [{"role": "system", "content": _BEAT_SYSTEM},
            {"role": "user", "content": prompt}]


def blocking_plan_messages(prompt: str) -> list[dict]:
    return [{"role": "system", "content": _BLOCKING_SYSTEM},
            {"role": "user", "content": prompt}]


def draft_messages(prompt: str) -> list[dict]:
    return [{"role": "system", "content": _DRAFT_SYSTEM},
            {"role": "user", "content": prompt}]


# ===========================================================================
# Parsers
# ===========================================================================

_FENCE_RE = re.compile(r"^\s*```[\w-]*\s*$")
_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.*)$")


def _strip_fences(text: str) -> str:
    if "```" not in (text or ""):
        return text or ""
    lines = (text or "").splitlines()
    idx = [i for i, ln in enumerate(lines) if _FENCE_RE.match(ln)]
    if len(idx) >= 2:
        return "\n".join(lines[idx[0] + 1:idx[1]])
    return "\n".join(ln for ln in lines if not _FENCE_RE.match(ln))


_BEAT_SINGLE = (
    (("objective",), "objective"),
    (("dramatic question", "question"), "dramatic_question"),
    (("conflict",), "conflict"),
    (("turning point", "turn"), "turning_point"),
    (("emotional shift", "emotion"), "emotional_shift"),
    (("continuity notes", "continuity"), "continuity_notes"),
)
_BEAT_LIST = {
    "dialogue beats": "dialogue_beats", "dialogue": "dialogue_beats",
    "stage action beats": "stage_action_beats", "stage action": "stage_action_beats",
    "action beats": "stage_action_beats",
    "entrances": "entrances", "exits": "exits",
}


def parse_beat_plan_response(text: str, scene_id: int | None = None) -> StageBeatPlan:
    plan = StageBeatPlan(scene_id=scene_id)
    cur_list: str | None = None
    for raw in _strip_fences(text or "").splitlines():
        line = raw.rstrip()
        if ":" in line and not _BULLET_RE.match(line):
            head, _, val = line.partition(":")
            key = head.strip().lower()
            single = next((f for labels, f in _BEAT_SINGLE if key in labels), None)
            if single:
                setattr(plan, single, val.strip())
                cur_list = None
                continue
            if key in _BEAT_LIST:
                cur_list = _BEAT_LIST[key]
                if val.strip():
                    getattr(plan, cur_list).append(val.strip())
                continue
        bullet = _BULLET_RE.match(line)
        if cur_list and bullet:
            getattr(plan, cur_list).append(bullet.group(1).strip())
        elif cur_list and line.strip():
            getattr(plan, cur_list).append(line.strip())
    return plan


_BLOCK_SINGLE = (
    (("staging area", "staging"), "staging_area_notes"),
    (("set notes", "set"), "set_notes"),
    (("transition notes", "transition"), "transition_notes"),
)
_BLOCK_LIST = {
    "character positions": "character_positions", "positions": "character_positions",
    "movement beats": "movement_beats", "movement": "movement_beats",
    "entrance / exit plan": "entrance_exit_plan", "entrance/exit plan": "entrance_exit_plan",
    "entrances / exits": "entrance_exit_plan", "entrance exit plan": "entrance_exit_plan",
    "lighting cues": "lighting_cues", "lighting": "lighting_cues",
    "sound cues": "sound_cues", "sound": "sound_cues",
    "prop notes": "prop_notes", "props": "prop_notes",
}


def parse_blocking_plan_response(text: str, scene_id: int | None = None) -> BlockingCuePlan:
    plan = BlockingCuePlan(scene_id=scene_id)
    cur_list: str | None = None
    for raw in _strip_fences(text or "").splitlines():
        line = raw.rstrip()
        if ":" in line and not _BULLET_RE.match(line):
            head, _, val = line.partition(":")
            key = head.strip().lower()
            single = next((f for labels, f in _BLOCK_SINGLE if key in labels), None)
            if single:
                setattr(plan, single, val.strip())
                cur_list = None
                continue
            if key in _BLOCK_LIST:
                cur_list = _BLOCK_LIST[key]
                if val.strip():
                    getattr(plan, cur_list).append(val.strip())
                continue
        bullet = _BULLET_RE.match(line)
        if cur_list and bullet:
            getattr(plan, cur_list).append(bullet.group(1).strip())
        elif cur_list and line.strip():
            getattr(plan, cur_list).append(line.strip())
    return plan


def parse_draft_response(text: str, scene_id: int | None = None) -> ssb.StageScript:
    """Parse a stage-script draft reply into a StageScript (strips fences; reuses
    the Phase 1 scene-body parser)."""
    return ssb.parse_stage_script_text(_strip_fences(text or ""))


# ===========================================================================
# Validation
# ===========================================================================

_LEAK_PHRASES = (
    "as an ai", "as a language model", "i cannot ", "i can't ",
    "here is the script", "here's the script", "sure, here", "sure! here",
    "[stage beat plan]", "[blocking", "[project mode]", "system prompt",
)
_PLAN_LABELS_IN_BODY = ("objective:", "dramatic question:", "staging area:",
                        "movement beats:")


@dataclass
class DraftValidation:
    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"is_valid": self.is_valid, "errors": list(self.errors),
                "warnings": list(self.warnings)}


def validate_draft_script(script: ssb.StageScript) -> DraftValidation:
    """Rule-based check of a parsed stage draft. Errors block; warnings allow.

    Errors guard the body from junk (empty, leaked fences/commentary, leaked plan
    labels). Structural quirks (no heading, dialogue without character, empty cue)
    are warnings via the Phase 1 validator."""
    report = DraftValidation()
    if script is None or script.is_empty():
        report.errors.append("The draft has no stage blocks.")
        report.is_valid = False
        return report

    body = ssb.serialize_stage_script(script)
    low = body.lower()
    if "```" in body:
        report.errors.append("The draft contains markdown code fences.")
    if any(p in low for p in _LEAK_PHRASES):
        report.errors.append("The draft contains assistant commentary or leaked context.")
    for b in script.blocks:
        first = (b.text or "").strip().lower().split("\n", 1)[0]
        if b.block_type == ssb.BT_STAGE_DIRECTION and any(
                first.startswith(lbl) for lbl in _PLAN_LABELS_IN_BODY):
            report.errors.append("The draft contains the plan instead of stage script.")
            break

    # Structural warnings from the Phase 1 validator (advisory, never block here).
    sv = ssb.validate_stage_script(script)
    report.warnings.extend(w for w in sv.warnings
                           if "no stage script" not in w.lower())
    if not any(b.block_type == ssb.BT_SCENE_HEADING for b in script.blocks):
        report.warnings.append("The draft has no scene heading.")

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


def _compose_body(db, scene_id: int, script: ssb.StageScript,
                  effective_mode: str) -> str:
    """Compose the resulting Scene body for the mode. Append continues after the
    existing blocks (no overwrite)."""
    if effective_mode == APPLY_APPEND:
        existing = ssb.parse_stage_script_text(_scene_body(db, scene_id))
        if not existing.is_empty():
            merged = ssb.StageScript(blocks=list(existing.blocks) + list(script.blocks))
            ssb._renumber(merged)
            return ssb.serialize_stage_script(merged)
    return ssb.serialize_stage_script(script)


def preview_draft_apply(db, project_id: int, scene_id: int,
                        script: ssb.StageScript, *, mode: str = APPLY_REPLACE):
    """Build a Controlled-Apply preview for the draft. **No mutation.** Returns the
    ApplyPreview, or None on a mode error."""
    effective, _confirm, err = resolve_apply_mode(db, project_id, scene_id, mode)
    if err:
        return None
    from logosforge.controlled_apply.service import build_apply_preview
    return build_apply_preview(
        db, project_id, target_type="scene", target_id=scene_id,
        proposed_text=_compose_body(db, scene_id, script, effective),
        apply_mode="replace", source_type="stage_pipeline")


def apply_draft(db, project_id: int, scene_id: int,
                script: ssb.StageScript, *,
                mode: str = APPLY_REPLACE, confirmed: bool = False) -> dict:
    """Apply a stage-script draft to the Scene body via Controlled Apply.

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
        apply_mode="replace", confirmed=confirmed, source_type="stage_pipeline")


# ===========================================================================
# Assistant / Logos context
# ===========================================================================


def stage_planning_context(db, project_id: int, scene_id: int | None) -> str:
    """A short, labelled ``[Stage Plan]`` block for the Assistant.

    Empty for non-stage-script projects or scenes without a beat/blocking plan."""
    if scene_id is None:
        return ""
    try:
        from logosforge.writing_modes import (
            get_project_writing_mode_by_id, STAGE_SCRIPT)
        if get_project_writing_mode_by_id(db, project_id) != STAGE_SCRIPT:
            return ""
    except Exception:
        return ""
    beat = get_beat_plan(db, project_id, scene_id)
    blocking = get_blocking_plan(db, project_id, scene_id)
    parts: list[str] = []
    if beat is not None and not beat.is_empty():
        parts.append("Stage beat plan:\n" + beat.to_text())
    if blocking is not None and not blocking.is_empty():
        parts.append("Blocking / cue plan:\n" + blocking.to_text())
    if not parts:
        return ""
    return "[Stage Plan]\n" + "\n\n".join(parts)
