"""Narrative Suggestion Engine — structured beat suggestions from PSYKE state.

Generates compact, typed narrative direction suggestions (not prose) using
the temporal graph, PSYKE entries, and current scene context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from logosforge.context_builder import gather_scene_context
from logosforge.orchestration import (
    MODE_BRAINSTORM,
    format_orchestration_debug,
    orchestrate_psyke_context,
)


SUGGESTION_PROMPT = """\
Based on the scene and story bible context, suggest exactly 5 possible \
next narrative directions. Use these exact types in this order:

1. Escalation
2. Reversal
3. Delay / Interruption
4. Internal Shift
5. Reveal

Rules:
- Each suggestion is 1-2 lines max
- Use → prefix for each description
- No dialogue, no full paragraphs, no prose
- Ground suggestions in the characters, relationships, and states provided
- Do not repeat the scene content
- Do not invent elements unconnected to the provided context
- Avoid generic suggestions — be specific to these characters and situation
- Respect character progression states (don't suggest resolved conflicts)

Format exactly like this:
1. Escalation
   → [specific suggestion]

2. Reversal
   → [specific suggestion]

3. Delay / Interruption
   → [specific suggestion]

4. Internal Shift
   → [specific suggestion]

5. Reveal
   → [specific suggestion]
"""


@dataclass
class SuggestionContext:
    """Metadata about what influenced the suggestions."""

    scene_id: int
    scene_order: int
    entries_used: list[str]
    temporal_used: bool
    relations_used: bool
    orchestration_decisions: list[str]
    psyke_context: str


def build_suggestion_messages(
    db: Any,
    project_id: int,
    scene_id: int,
) -> tuple[list[dict], SuggestionContext | None]:
    """Build messages for the narrative suggestion request.

    Returns (messages, context_metadata) or ([], None) on failure.
    """
    scene_ctx = gather_scene_context(db, project_id, scene_id)
    if not scene_ctx:
        return [], None

    all_scenes = db.get_all_scenes(project_id)
    scene_order_map = {s.id: s.sort_order for s in all_scenes}
    current_order = scene_order_map.get(scene_id, 0)

    orch_result = orchestrate_psyke_context(
        db, project_id, scene_id, MODE_BRAINSTORM,
    )

    system = (
        "You are a narrative structure advisor. You suggest story directions "
        "— not prose, not dialogue, not full scenes. Your suggestions are "
        "compact structural beats that a writer can choose to develop. "
        "Ground every suggestion in the provided character states and "
        "story context."
    )

    user_parts: list[str] = []
    if orch_result.psyke_context:
        user_parts.append(orch_result.psyke_context)
        user_parts.append("")
    user_parts.append(scene_ctx)
    user_parts.append("")
    user_parts.append(SUGGESTION_PROMPT)

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n".join(user_parts)},
    ]

    ctx = SuggestionContext(
        scene_id=scene_id,
        scene_order=current_order,
        entries_used=orch_result.entries_included,
        temporal_used=orch_result.temporal_used,
        relations_used=orch_result.relations_used,
        orchestration_decisions=orch_result.decisions,
        psyke_context=orch_result.psyke_context,
    )

    return messages, ctx


def format_suggestion_debug(ctx: SuggestionContext) -> str:
    """Format suggestion metadata for the context preview panel."""
    lines = [
        "--- Narrative Suggestions (brainstorm mode) ---",
        f"Scene order: {ctx.scene_order}",
        f"Entries: {', '.join(ctx.entries_used) or '(none)'}",
        f"Temporal: {'yes' if ctx.temporal_used else 'no'}",
        f"Relations: {'yes' if ctx.relations_used else 'no'}",
    ]
    for d in ctx.orchestration_decisions:
        lines.append(f"  • {d}")
    return "\n".join(lines)
