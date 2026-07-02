"""Stage Script review checks — data-driven theatrical feedback.

When the StageScriptEngine is active, these checks evaluate the actual
scene + entrance/exit + cue + stage-business data and surface concrete,
theatre-specific notes — never novel/screenplay-style advice.

Pure core/app logic: no UI / Tauri / filesystem / provider imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Words that signal the audience may be obstructed from the key action.
_OBSTRUCTION_WORDS = (
    "hidden", "cannot see", "can't see", "obscured", "not visible",
    "out of sight", "blocked", "offstage",
)


@dataclass
class StageScriptCheck:
    """One review finding. scene_id is None for project-level checks."""

    check_type: str
    message: str
    severity: str = "info"      # "info" | "warning"
    scene_id: int | None = None


def review_stage_script(
    db: Any, project_id: int, scene_id: int | None = None,
) -> list[StageScriptCheck]:
    """Run stage-script review checks (§4).

    With *scene_id*, runs scene-scoped checks only; otherwise runs scene
    checks for every scene plus project-level (act-break) checks.
    """
    checks: list[StageScriptCheck] = []
    scenes = db.get_all_scenes(project_id)
    if not scenes:
        return checks

    target = [s for s in scenes if s.id == scene_id] if scene_id is not None else scenes
    for scene in target:
        checks.extend(_scene_checks(db, project_id, scene))

    if scene_id is None:
        checks.extend(_act_break_checks(scenes))
    return checks


def _has_content(scene: Any) -> bool:
    return bool((scene.content or "").strip()) or bool((scene.summary or "").strip())


def _scene_checks(db: Any, project_id: int, scene: Any) -> list[StageScriptCheck]:
    out: list[StageScriptCheck] = []
    objective = (getattr(scene, "scene_objective", "") or "").strip()
    blocking = (getattr(scene, "blocking_notes", "") or "").strip()
    physical = (getattr(scene, "physical_action", "") or "").strip()
    conflict = (scene.conflict or "").strip()
    turn = (getattr(scene, "dramatic_turn", "") or "").strip()
    ee = db.get_stage_entrances_exits(scene.id)

    # Does each character have a playable objective?
    if _has_content(scene) and not objective:
        out.append(StageScriptCheck(
            "playable_objective",
            f"“{scene.title}” has dialogue but no playable objective.",
            "warning", scene.id,
        ))

    # Is the conflict stageable? (spoken conflict with nothing to play)
    if conflict and not blocking and not physical and not ee:
        out.append(StageScriptCheck(
            "stageable_conflict",
            f"“{scene.title}”: the conflict is spoken but not playable "
            "— no blocking, physical action, or movement.",
            "warning", scene.id,
        ))

    # Are entrances/exits motivated? (no cue text and no notes)
    for e in ee:
        if not (e.cue_text or "").strip() and not (e.notes or "").strip():
            out.append(StageScriptCheck(
                "motivated_exit",
                f"“{scene.title}”: an {e.type} is unmotivated "
                "(no cue or note explaining it).",
                "warning", scene.id,
            ))
            break

    # Are props introduced and tracked? (a prop in business with no
    # continuity note, or prop_notes mentioned but no business tracking)
    business = db.get_stage_business(scene.id)
    for b in business:
        if not (b.continuity_note or "").strip():
            out.append(StageScriptCheck(
                "prop_continuity",
                f"“{scene.title}”: a prop appears without stage "
                "continuity (no continuity note).",
                "warning", scene.id,
            ))
            break
    if not business and (getattr(scene, "prop_notes", "") or "").strip():
        out.append(StageScriptCheck(
            "prop_continuity",
            f"“{scene.title}”: prop notes exist but no prop is "
            "tracked as stage business.",
            "info", scene.id,
        ))

    # Is the audience able to perceive the key action?
    av = (getattr(scene, "audience_visibility_notes", "") or "").strip().lower()
    if av and any(w in av for w in _OBSTRUCTION_WORDS):
        out.append(StageScriptCheck(
            "audience_visibility",
            f"“{scene.title}”: the audience may not see the decisive "
            "action (visibility is obstructed).",
            "warning", scene.id,
        ))

    # Does the scene turn?
    if _has_content(scene) and not turn:
        out.append(StageScriptCheck(
            "scene_turn",
            f"“{scene.title}” does not turn — no dramatic turn defined.",
            "info", scene.id,
        ))

    return out


def _act_break_checks(scenes: list) -> list[StageScriptCheck]:
    """Does the act break create pressure? Flag the last scene of an act
    that resolves without a dramatic turn."""
    out: list[StageScriptCheck] = []
    n = len(scenes)
    for i, scene in enumerate(scenes):
        act = (scene.act or "").strip()
        if not act:
            continue
        next_act = (scenes[i + 1].act or "").strip() if i + 1 < n else None
        is_act_end = (i == n - 1) or (next_act != act)
        if is_act_end:
            turn = (getattr(scene, "dramatic_turn", "") or "").strip()
            if not turn:
                out.append(StageScriptCheck(
                    "act_break_pressure",
                    f"Act break after “{scene.title}” lands on a weak "
                    "beat — no unresolved pressure into the next act.",
                    "warning", scene.id,
                ))
    return out
