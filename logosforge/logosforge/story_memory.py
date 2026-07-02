"""Story Memory Extraction — extract continuity-relevant facts from scenes.

Scans structured fields (goal, conflict, outcome, synopsis) and character states
to produce memory entries. Filters noise via minimum length and deduplication.
"""

from __future__ import annotations

from dataclasses import dataclass

from logosforge.db import Database
from logosforge.models import StoryMemoryEntry


MIN_VALUE_LENGTH = 15


@dataclass
class ExtractionResult:
    scene_id: int
    added: list[StoryMemoryEntry]
    skipped: int


def extract_scene_memory(db: Database, project_id: int, scene_id: int) -> ExtractionResult:
    """Extract memory entries from a single scene. Deduplicates against existing."""
    scenes = db.get_all_scenes(project_id)
    scene = None
    for s in scenes:
        if s.id == scene_id:
            scene = s
            break

    if scene is None:
        return ExtractionResult(scene_id=scene_id, added=[], skipped=0)

    characters = db.get_all_characters(project_id)
    char_map = {c.id: c.name for c in characters}
    scene_char_ids = db.get_scene_character_ids(scene_id)
    scene_states = db.get_scene_character_states(scene_id)

    candidates: list[tuple[str, str, str]] = []  # (type, target, value)

    # Character state changes
    for cid, state in scene_states:
        if state and len(state) >= 3:
            name = char_map.get(cid, f"Character {cid}")
            candidates.append(("character_state", name, state))

    # Key events from outcome
    outcome = (scene.outcome or "").strip()
    if len(outcome) >= MIN_VALUE_LENGTH:
        candidates.append(("key_event", "", outcome))

    # Relationship from conflict when 2+ characters present
    conflict = (scene.conflict or "").strip()
    if len(conflict) >= MIN_VALUE_LENGTH and len(scene_char_ids) >= 2:
        names = [char_map[cid] for cid in scene_char_ids[:2] if cid in char_map]
        if len(names) >= 2:
            target = f"{names[0]} and {names[1]}"
            candidates.append(("relationship", target, conflict))

    # Decision from goal when outcome exists (resolved choice)
    goal = (scene.goal or "").strip()
    if len(goal) >= MIN_VALUE_LENGTH and outcome:
        candidates.append(("decision", "", goal))

    # Deduplicate and store
    added: list[StoryMemoryEntry] = []
    skipped = 0

    for mem_type, target, value in candidates:
        if db.memory_exists(scene_id, mem_type, target):
            skipped += 1
            continue
        entry = db.add_memory(project_id, scene_id, mem_type, target, value)
        added.append(entry)

    return ExtractionResult(scene_id=scene_id, added=added, skipped=skipped)


def extract_project_memory(db: Database, project_id: int) -> list[ExtractionResult]:
    """Extract memory from all scenes in a project."""
    scenes = db.get_all_scenes(project_id)
    results: list[ExtractionResult] = []
    for scene in scenes:
        result = extract_scene_memory(db, project_id, scene.id)
        results.append(result)
    return results


def format_memory_context(db: Database, project_id: int) -> str:
    """Format all memories as a context block for the AI assistant."""
    memories = db.get_memories(project_id)
    if not memories:
        return ""

    lines: list[str] = ["[Story Memory]"]
    for mem in memories:
        if mem.memory_type == "character_state":
            lines.append(f"- {mem.target} → {mem.value}")
        elif mem.memory_type == "key_event":
            lines.append(f"- Event: {mem.value}")
        elif mem.memory_type == "relationship":
            lines.append(f"- {mem.target}: {mem.value}")
        elif mem.memory_type == "decision":
            lines.append(f"- Decision: {mem.value}")

    return "\n".join(lines)


def get_memory_for_scene(db: Database, project_id: int, scene_id: int) -> list[StoryMemoryEntry]:
    """Get all memory entries associated with a specific scene."""
    return db.get_memories(project_id, scene_id=scene_id)
