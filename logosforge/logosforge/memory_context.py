"""Memory-Aware AI Context — scene-relevant memory selection and formatting.

Selects and formats memory entries for AI context injection, boosting entries
by proximity to the active scene and character overlap.
"""

from __future__ import annotations

from dataclasses import dataclass

from logosforge.db import Database
from logosforge.memory_manager import (
    CONTEXT_LIMIT,
    ScoredMemory,
    compute_priority,
    compute_recency,
    compute_relevance,
    priority_level,
)
from logosforge.models import StoryMemoryEntry


PROXIMITY_BOOST = 0.2
CHARACTER_OVERLAP_BOOST = 0.15
DEFAULT_LIMIT = 15


@dataclass
class ContextMemory:
    entry: StoryMemoryEntry
    relevance: float
    superseded: bool
    scene_label: str


def gather_memory_context(
    db: Database,
    project_id: int,
    scene_id: int | None = None,
    limit: int = DEFAULT_LIMIT,
) -> str:
    """Build [Story Memory] context block for AI, optimized for the active scene."""
    selected = select_memories(db, project_id, scene_id=scene_id, limit=limit)
    if not selected:
        return ""
    return _format_context(selected)


def select_memories(
    db: Database,
    project_id: int,
    scene_id: int | None = None,
    limit: int = DEFAULT_LIMIT,
) -> list[ContextMemory]:
    """Select and score memories for context, boosting scene-relevant ones."""
    memories = db.get_memories(project_id)
    if not memories:
        return []

    scenes = db.get_all_scenes(project_id)
    scene_ids = [s.id for s in scenes]
    total_scenes = len(scenes)

    # Build scene title map for labels
    scene_title_map: dict[int, str] = {}
    scene_index_map: dict[int, int] = {}
    for i, s in enumerate(scenes):
        scene_title_map[s.id] = s.title
        scene_index_map[s.id] = i

    # Get characters in active scene for overlap boost
    active_char_names: set[str] = set()
    active_scene_idx: int | None = None
    if scene_id is not None:
        char_ids = db.get_scene_character_ids(scene_id)
        characters = db.get_all_characters(project_id)
        char_name_map = {c.id: c.name for c in characters}
        active_char_names = {char_name_map[cid] for cid in char_ids if cid in char_name_map}
        active_scene_idx = scene_index_map.get(scene_id)

    scored: list[ContextMemory] = []
    for mem in memories:
        priority = compute_priority(mem, memories)
        recency = compute_recency(mem, total_scenes, scene_ids)
        base_relevance = compute_relevance(priority, recency)

        # Proximity boost: memories from adjacent scenes
        boost = 0.0
        if active_scene_idx is not None:
            mem_idx = scene_index_map.get(mem.scene_id)
            if mem_idx is not None:
                distance = abs(active_scene_idx - mem_idx)
                if distance <= 2:
                    boost += PROXIMITY_BOOST * (1.0 - distance / 3.0)

        # Character overlap boost
        if mem.target and active_char_names:
            for name in active_char_names:
                if name in mem.target:
                    boost += CHARACTER_OVERLAP_BOOST
                    break

        final_relevance = min(1.0, base_relevance + boost)
        superseded = priority < 0.5 and mem.memory_type == "character_state"

        scene_label = f"S{scene_index_map.get(mem.scene_id, 0) + 1}"

        scored.append(ContextMemory(
            entry=mem,
            relevance=final_relevance,
            superseded=superseded,
            scene_label=scene_label,
        ))

    scored.sort(key=lambda s: s.relevance, reverse=True)
    return scored[:limit]


def _format_context(selected: list[ContextMemory]) -> str:
    """Format selected memories as a compact context block."""
    lines: list[str] = ["[Story Memory]"]

    for cm in selected:
        mem = cm.entry
        ref = f"({cm.scene_label})"

        if mem.memory_type == "character_state":
            if cm.superseded:
                lines.append(f"- (past) {mem.target}: {mem.value} {ref}")
            else:
                lines.append(f"- {mem.target}: {mem.value} {ref}")
        elif mem.memory_type == "key_event":
            lines.append(f"- Event: {mem.value} {ref}")
        elif mem.memory_type == "relationship":
            lines.append(f"- {mem.target}: {mem.value} {ref}")
        elif mem.memory_type == "decision":
            lines.append(f"- Decision: {mem.value} {ref}")

    return "\n".join(lines)
