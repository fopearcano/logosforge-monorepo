"""Story Memory Management — priority, decay, deduplication, and context limits.

Maintains a clean, relevant memory layer by scoring entries and controlling
what surfaces in the AI context window.
"""

from __future__ import annotations

from dataclasses import dataclass

from logosforge.db import Database
from logosforge.models import StoryMemoryEntry


CONTEXT_LIMIT = 20

_BASE_PRIORITY = {
    "key_event": 1.0,
    "decision": 1.0,
    "relationship": 0.7,
    "character_state": 0.7,
}

_DECAY_RATE = {
    "high": 0.3,
    "medium": 0.6,
    "low": 0.9,
}


@dataclass
class ScoredMemory:
    entry: StoryMemoryEntry
    priority: float
    recency: float
    relevance: float
    superseded: bool


def compute_priority(entry: StoryMemoryEntry, all_memories: list[StoryMemoryEntry]) -> float:
    """Compute priority for a memory entry, accounting for superseding."""
    base = _BASE_PRIORITY.get(entry.memory_type, 0.4)

    if entry.memory_type == "character_state" and entry.target:
        newer_exists = any(
            m.memory_type == "character_state"
            and m.target == entry.target
            and m.scene_id > entry.scene_id
            for m in all_memories
        )
        if newer_exists:
            return 0.4  # Demoted to low
    return base


def priority_level(priority: float) -> str:
    """Map numeric priority to level name."""
    if priority >= 0.9:
        return "high"
    elif priority >= 0.6:
        return "medium"
    return "low"


def compute_recency(entry: StoryMemoryEntry, total_scenes: int, scene_ids: list[int]) -> float:
    """Compute recency factor based on distance from latest scene."""
    if total_scenes <= 1:
        return 1.0

    if entry.scene_id in scene_ids:
        position = scene_ids.index(entry.scene_id)
    else:
        position = 0

    distance = total_scenes - 1 - position
    return 1.0 - (distance / total_scenes)


def compute_relevance(priority: float, recency: float) -> float:
    """Compute effective relevance from priority and recency."""
    level = priority_level(priority)
    decay_rate = _DECAY_RATE[level]
    decayed_recency = 1.0 - (1.0 - recency) * decay_rate
    return priority * max(0.1, decayed_recency)


def score_memories(db: Database, project_id: int) -> list[ScoredMemory]:
    """Score all memories in a project by priority, recency, and relevance."""
    memories = db.get_memories(project_id)
    if not memories:
        return []

    scenes = db.get_all_scenes(project_id)
    scene_ids = [s.id for s in scenes]
    total_scenes = len(scenes)

    scored: list[ScoredMemory] = []
    for mem in memories:
        priority = compute_priority(mem, memories)
        recency = compute_recency(mem, total_scenes, scene_ids)
        relevance = compute_relevance(priority, recency)
        superseded = priority < _BASE_PRIORITY.get(mem.memory_type, 0.4)

        scored.append(ScoredMemory(
            entry=mem,
            priority=priority,
            recency=recency,
            relevance=relevance,
            superseded=superseded,
        ))

    scored.sort(key=lambda s: s.relevance, reverse=True)
    return scored


def supersede_old_states(db: Database, project_id: int) -> int:
    """Mark older character states as superseded when newer ones exist.

    Returns count of entries that were identified as superseded.
    """
    memories = db.get_memories(project_id)
    char_states: dict[str, list[StoryMemoryEntry]] = {}

    for mem in memories:
        if mem.memory_type == "character_state" and mem.target:
            char_states.setdefault(mem.target, []).append(mem)

    superseded_count = 0
    for target, entries in char_states.items():
        if len(entries) <= 1:
            continue
        entries_sorted = sorted(entries, key=lambda e: e.scene_id)
        # All but the latest are superseded
        superseded_count += len(entries_sorted) - 1

    return superseded_count


def get_active_memories(db: Database, project_id: int, limit: int = CONTEXT_LIMIT) -> list[ScoredMemory]:
    """Get top memories by relevance, respecting context limit."""
    scored = score_memories(db, project_id)
    return scored[:limit]


def format_managed_context(db: Database, project_id: int, limit: int = CONTEXT_LIMIT) -> str:
    """Format managed memory as context block, respecting priority and limits."""
    active = get_active_memories(db, project_id, limit=limit)
    if not active:
        return ""

    lines: list[str] = ["[Story Memory]"]
    for sm in active:
        mem = sm.entry
        if mem.memory_type == "character_state":
            prefix = "(past) " if sm.superseded else ""
            lines.append(f"- {prefix}{mem.target} → {mem.value}")
        elif mem.memory_type == "key_event":
            lines.append(f"- Event: {mem.value}")
        elif mem.memory_type == "relationship":
            lines.append(f"- {mem.target}: {mem.value}")
        elif mem.memory_type == "decision":
            lines.append(f"- Decision: {mem.value}")

    return "\n".join(lines)


def memory_stats(db: Database, project_id: int) -> dict[str, int]:
    """Get memory statistics for a project."""
    scored = score_memories(db, project_id)
    total = len(scored)
    high = sum(1 for s in scored if priority_level(s.priority) == "high")
    medium = sum(1 for s in scored if priority_level(s.priority) == "medium")
    low = sum(1 for s in scored if priority_level(s.priority) == "low")
    superseded = sum(1 for s in scored if s.superseded)
    active = min(total, CONTEXT_LIMIT)

    return {
        "total": total,
        "high": high,
        "medium": medium,
        "low": low,
        "superseded": superseded,
        "active_in_context": active,
    }
