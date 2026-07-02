"""Project-aware context assembly for the Chat section.

Composes existing context-builder functions; does not duplicate any
PSYKE or scene gathering logic.
"""

from __future__ import annotations

from logosforge.context_builder import (
    gather_outline_context,
    gather_psyke_context,
    gather_scene_context,
    gather_story_memory,
)
from logosforge.db import Database

CONTEXT_MAX_CHARS = 6000


def build_chat_context(
    db: Database,
    project_id: int,
    *,
    active_scene_id: int | None = None,
    include_outline: bool = True,
    include_psyke: bool = True,
    include_memory: bool = True,
) -> str:
    """Assemble a single context block for a chat turn.

    Reuses the existing gather_* functions. The result is bounded by
    CONTEXT_MAX_CHARS — anything past that is dropped from the tail
    so the most-relevant earlier sections survive.
    """
    sections: list[str] = []

    project = db.get_project_by_id(project_id)
    if project is not None:
        header = f"[Project] {project.title}"
        if project.description:
            header += f" — {project.description.strip()[:200]}"
        sections.append(header)

    if active_scene_id is not None:
        scene_block = gather_scene_context(db, project_id, active_scene_id)
        if scene_block:
            sections.append(scene_block)

    if include_outline:
        outline = gather_outline_context(db, project_id)
        if outline:
            sections.append(outline)

    if include_psyke:
        psyke = gather_psyke_context(
            db, project_id, scene_id=active_scene_id,
        )
        if psyke:
            sections.append(psyke)

    if include_memory:
        memory = gather_story_memory(db, project_id)
        if memory:
            sections.append(memory)

    combined = "\n\n".join(sections)
    if len(combined) > CONTEXT_MAX_CHARS:
        combined = combined[:CONTEXT_MAX_CHARS] + "\n[...context truncated]"
    return combined


def context_summary(
    db: Database,
    project_id: int,
    *,
    active_scene_id: int | None = None,
) -> str:
    """Short human-readable description of what /context would include."""
    parts: list[str] = []
    project = db.get_project_by_id(project_id)
    if project is not None:
        parts.append(f"project: {project.title}")
    if active_scene_id is not None:
        scene = db.get_scene_by_id(active_scene_id)
        if scene is not None:
            parts.append(f"scene: {scene.title}")
    psyke_entries = db.get_all_psyke_entries(project_id)
    if psyke_entries:
        parts.append(f"PSYKE entries: {len(psyke_entries)}")
    scene_count = len(db.get_all_scenes(project_id))
    if scene_count:
        parts.append(f"scenes: {scene_count}")
    return ", ".join(parts) if parts else "(no project context yet)"
