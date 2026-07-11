"""Adaptive AI Mode Engine — adjusts AI behavior based on story state.

Combines story maturity (early/mid/late) with health state (balanced/uneven/fragmented)
to select an AI mode: Structure, Balance, or Refinement.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from logosforge.character_balance import compute_balance
from logosforge.db import Database


class StoryStage(Enum):
    EARLY = "early"
    MID = "mid"
    LATE = "late"


class HealthState(Enum):
    BALANCED = "balanced"
    UNEVEN = "uneven"
    FRAGMENTED = "fragmented"


class AIMode(Enum):
    STRUCTURE = "Structure"
    BALANCE = "Balance"
    REFINEMENT = "Refinement"


_MODE_DESCRIPTIONS = {
    AIMode.STRUCTURE: (
        "Focus on scaffolding: suggest scene structure, act divisions, "
        "plotline establishment, and character introductions."
    ),
    AIMode.BALANCE: (
        "Focus on evening out: suggest underused character scenes, "
        "arc development for neglected plotlines, and distribution improvements."
    ),
    AIMode.REFINEMENT: (
        "Focus on polish: suggest prose improvements, tension tuning, "
        "dialogue sharpening, and thematic deepening."
    ),
}


@dataclass
class ModeResult:
    mode: AIMode
    stage: StoryStage
    health: HealthState
    description: str

    @property
    def mode_name(self) -> str:
        return self.mode.value


def detect_stage(db: Database, project_id: int) -> StoryStage:
    """Determine story maturity from scene count and structural signals."""
    scenes = db.get_all_scenes(project_id)
    total = len(scenes)

    acts: set[str] = set()
    plotlines: set[str] = set()
    for s in scenes:
        if s.act:
            acts.add(s.act)
        if s.plotline:
            plotlines.add(s.plotline)

    num_acts = len(acts)
    num_plotlines = len(plotlines)

    if total > 20 and num_acts >= 3 and num_plotlines >= 2:
        return StoryStage.LATE
    elif total >= 8 and (num_acts >= 2 or num_plotlines >= 2):
        return StoryStage.MID
    else:
        # Includes many scenes with no act/plotline structure: that still
        # needs scaffolding, so Structure (early) is the right focus.
        return StoryStage.EARLY


def detect_health(db: Database, project_id: int) -> HealthState:
    """Determine health state from character/arc balance flags."""
    balance = compute_balance(db, project_id)

    if balance.total_scenes == 0:
        return HealthState.FRAGMENTED

    char_flags = [p.flag for p in balance.characters if p.flag]
    arc_flags = [a.flag for a in balance.arcs if a.flag]
    total_flags = len(char_flags) + len(arc_flags)

    total_entities = len(balance.characters) + len(balance.arcs)
    flag_ratio = total_flags / max(total_entities, 1)

    if total_flags >= 3 or flag_ratio > 0.5:
        return HealthState.FRAGMENTED
    elif total_flags >= 1:
        return HealthState.UNEVEN
    else:
        return HealthState.BALANCED


def select_mode(stage: StoryStage, health: HealthState) -> AIMode:
    """Select AI mode from story stage and health state."""
    if stage == StoryStage.EARLY:
        return AIMode.STRUCTURE
    if health == HealthState.FRAGMENTED:
        return AIMode.STRUCTURE
    if stage == StoryStage.MID and health == HealthState.UNEVEN:
        return AIMode.BALANCE
    if stage == StoryStage.LATE and health != HealthState.BALANCED:
        return AIMode.BALANCE
    return AIMode.REFINEMENT


def compute_mode(db: Database, project_id: int) -> ModeResult:
    """Compute the current adaptive AI mode for a project.

    Auto = story stage × health (``select_mode``). A user override
    (global setting ``adaptive_mode_override`` = ``Structure|Balance|Refinement``;
    empty = auto) forces the mode — stage/health are still reported for context.
    The override flows into every consumer (``mode_context_block`` in prompts,
    ``mode_suggestions``, the ``/adapt`` endpoint) because they all read from here.
    """
    stage = detect_stage(db, project_id)
    health = detect_health(db, project_id)
    mode = select_mode(stage, health)
    try:
        from logosforge.settings import get_manager
        override = str(get_manager().get("adaptive_mode_override") or "").strip()
    except Exception:
        override = ""
    if override:
        for m in AIMode:
            if m.value == override:
                mode = m
                break
    return ModeResult(
        mode=mode,
        stage=stage,
        health=health,
        description=_MODE_DESCRIPTIONS[mode],
    )


def mode_context_block(result: ModeResult) -> str:
    """Format mode as a context block for the AI assistant."""
    return (
        f"[AI Mode: {result.mode_name}]\n"
        f"Story stage: {result.stage.value} | Health: {result.health.value}\n"
        f"Guidance: {result.description}"
    )
