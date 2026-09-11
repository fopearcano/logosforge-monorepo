"""Project-aware context assembly for the Chat section.

Composes existing context-builder functions; does not duplicate any
PSYKE or scene gathering logic.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from logosforge.context_builder import (
    gather_outline_context,
    gather_psyke_context,
    gather_scene_context,
    gather_story_memory,
)
from logosforge.db import Database

CONTEXT_MAX_CHARS = 6000
_LOG = logging.getLogger(__name__)

# Guaranteed first-pass budgets. Short sources give their unused space back;
# the remainder is then shared among longer sources. This prevents a long active
# scene or outline from pushing PSYKE entirely past the global tail cut.
_SOURCE_MIN_CHARS = {
    "project": 300,
    "scene": 1200,
    "outline": 1200,
    "psyke": 1200,
    "memory": 400,
}
_TRUNCATED = "\n[...source truncated]"


def _append_context_source(
    sections: list[tuple[str, str]],
    key: str,
    label: str,
    build: Callable[[], str],
) -> None:
    """Append one source without letting it erase every other grounding source."""
    try:
        block = build()
    except Exception:
        _LOG.exception("Could not build %s assistant context", label)
        sections.append((key, f"[Context Warning] {label} context unavailable for this reply."))
        return
    if block:
        sections.append((key, block))


def _fit_context_sections(sections: list[tuple[str, str]]) -> str:
    """Fit all non-empty sources while preserving every source's leading context.

    The old final-string slice privileged whichever source happened to come
    first and could remove PSYKE altogether. Allocate a minimum to every source,
    then water-fill unused capacity across the still-truncated sources.
    """
    if not sections:
        return ""
    separator_chars = 2 * (len(sections) - 1)
    available = max(0, CONTEXT_MAX_CHARS - separator_chars)
    wanted = [
        min(len(block), _SOURCE_MIN_CHARS.get(key, 400))
        for key, block in sections
    ]
    wanted_total = sum(wanted)
    if wanted_total > available and wanted_total:
        # Defensive fallback if budgets or the global cap are changed later.
        scale = available / wanted_total
        allocations = [int(value * scale) for value in wanted]
    else:
        allocations = wanted

    remaining = available - sum(allocations)
    while remaining > 0:
        open_indexes = [
            index for index, (_key, block) in enumerate(sections)
            if allocations[index] < len(block)
        ]
        if not open_indexes:
            break
        share = max(1, remaining // len(open_indexes))
        spent = 0
        for index in open_indexes:
            need = len(sections[index][1]) - allocations[index]
            add = min(need, share, remaining - spent)
            allocations[index] += add
            spent += add
            if spent >= remaining:
                break
        if spent == 0:
            break
        remaining -= spent

    fitted: list[str] = []
    for (_key, block), limit in zip(sections, allocations):
        if len(block) <= limit:
            fitted.append(block)
        elif limit <= len(_TRUNCATED):
            fitted.append(block[:limit])
        else:
            fitted.append(block[:limit - len(_TRUNCATED)] + _TRUNCATED)
    return "\n\n".join(fitted)


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
    sections: list[tuple[str, str]] = []

    try:
        project = db.get_project_by_id(project_id)
    except Exception:
        _LOG.exception("Could not build project assistant context")
        project = None
        sections.append(("project", "[Context Warning] Project header unavailable for this reply."))
    if project is not None:
        header = f"[Project] {project.title}"
        if project.description:
            header += f" — {project.description.strip()[:200]}"
        sections.append(("project", header))

    if active_scene_id is not None:
        _append_context_source(
            sections,
            "scene",
            "Active scene",
            lambda: gather_scene_context(db, project_id, active_scene_id),
        )

    if include_outline:
        _append_context_source(
            sections,
            "outline",
            "Outline",
            lambda: gather_outline_context(db, project_id),
        )

    if include_psyke:
        _append_context_source(
            sections,
            "psyke",
            "PSYKE",
            lambda: gather_psyke_context(
                db, project_id, scene_id=active_scene_id,
            ),
        )

    if include_memory:
        _append_context_source(
            sections,
            "memory",
            "Story memory",
            lambda: gather_story_memory(db, project_id),
        )

    return _fit_context_sections(sections)


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
