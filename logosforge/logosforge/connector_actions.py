"""CONNECTOR Action Definitions — safe app actions for local AI.

Defines read and write actions with handlers. Each handler receives
(db, project_id, **validated_args) and returns a serializable result.
"""

from __future__ import annotations

from logosforge.connector_registry import ActionDef, ActionParam, register
from logosforge.db import Database
from logosforge.live_context import get_live_context


# =============================================================================
# READ ACTIONS
# =============================================================================

register(ActionDef(
    name="get_project",
    description="Get current project metadata (id, title, description).",
    category="read",
    params=[],
))

register(ActionDef(
    name="list_scenes",
    description="List all scenes in the project (id, title, chapter, plotline, act).",
    category="read",
    params=[],
))

register(ActionDef(
    name="get_scene",
    description="Get a scene by id with all structured fields.",
    category="read",
    params=[ActionParam("scene_id", "int")],
))

register(ActionDef(
    name="list_characters",
    description="List all characters in the project (id, name, description).",
    category="read",
    params=[],
))

register(ActionDef(
    name="list_psyke_entries",
    description="List all story bible entries (id, name, type, is_global).",
    category="read",
    params=[],
))

register(ActionDef(
    name="get_psyke_entry",
    description="Get a story bible entry by id with details and notes.",
    category="read",
    params=[ActionParam("entry_id", "int")],
))

register(ActionDef(
    name="list_notes",
    description="List all notes in the project (id, title).",
    category="read",
    params=[],
))

register(ActionDef(
    name="get_note",
    description="Get a note by id with full content.",
    category="read",
    params=[ActionParam("note_id", "int")],
))

register(ActionDef(
    name="search",
    description="Full-text search across the project.",
    category="read",
    params=[ActionParam("query", "str")],
))

register(ActionDef(
    name="list_available_actions",
    description="List all available CONNECTOR actions with descriptions.",
    category="read",
    params=[],
))

# -- LIVE editor context (only meaningful when the API runs in-process) -------

register(ActionDef(
    name="get_live_context",
    description="Get the desktop's live editing context: current project id, "
                "the scene currently open in the editor, and whether text is "
                "selected. 'available' is false when the API is not running "
                "inside the desktop app.",
    category="read",
    params=[],
))

register(ActionDef(
    name="get_current_selection",
    description="Get the text currently selected in the manuscript editor "
                "(live). Empty when nothing is selected or the API is not "
                "running inside the desktop app.",
    category="read",
    params=[],
))

register(ActionDef(
    name="get_active_scene",
    description="Get the scene the user currently has open in the editor "
                "(live), with all structured fields.",
    category="read",
    params=[],
))


# =============================================================================
# WRITE ACTIONS (non-destructive only)
# =============================================================================

register(ActionDef(
    name="create_scene",
    description="Create a new scene with a title.",
    category="write",
    params=[
        ActionParam("title", "str"),
        ActionParam("chapter", "str", required=False, default=""),
        ActionParam("plotline", "str", required=False, default=""),
    ],
))

register(ActionDef(
    name="update_scene_title",
    description="Rename an existing scene.",
    category="write",
    params=[
        ActionParam("scene_id", "int"),
        ActionParam("title", "str"),
    ],
))

register(ActionDef(
    name="create_psyke_entry",
    description="Create a new story bible entry.",
    category="write",
    params=[
        ActionParam("name", "str"),
        ActionParam("entry_type", "str", required=False, default="other"),
        ActionParam("notes", "str", required=False, default=""),
    ],
))

register(ActionDef(
    name="create_note",
    description="Create a new note.",
    category="write",
    params=[
        ActionParam("title", "str"),
        ActionParam("content", "str", required=False, default=""),
    ],
))


# =============================================================================
# HANDLERS
# =============================================================================

def _handle_get_project(db: Database, project_id: int, **kwargs) -> dict:
    proj = db.get_project_by_id(project_id)
    if proj is None:
        return {"error": "Project not found"}
    return {
        "id": proj.id,
        "title": proj.title,
        "description": proj.description,
    }


def _handle_list_scenes(db: Database, project_id: int, **kwargs) -> list:
    scenes = db.get_all_scenes(project_id)
    return [
        {
            "id": s.id,
            "title": s.title,
            "chapter": s.chapter,
            "plotline": s.plotline,
            "act": s.act,
            "sort_order": s.sort_order,
        }
        for s in scenes
    ]


def _handle_get_scene(db: Database, project_id: int, *, scene_id: int, **kwargs) -> dict:
    scene = db.get_scene_by_id(scene_id)
    if scene is None:
        return {"error": "Scene not found"}
    if scene.project_id != project_id:
        return {"error": "Scene does not belong to this project"}
    char_ids = db.get_scene_character_ids(scene_id)
    place_ids = db.get_scene_place_ids(scene_id)
    return {
        "id": scene.id,
        "title": scene.title,
        "chapter": scene.chapter,
        "plotline": scene.plotline,
        "act": scene.act,
        "summary": scene.summary,
        "synopsis": scene.synopsis,
        "goal": scene.goal,
        "conflict": scene.conflict,
        "outcome": scene.outcome,
        "beat": scene.beat,
        "tags": scene.tags,
        "content_length": len(scene.content or ""),
        "character_ids": char_ids,
        "place_ids": place_ids,
    }


def _handle_list_characters(db: Database, project_id: int, **kwargs) -> list:
    chars = db.get_all_characters(project_id)
    return [
        {"id": c.id, "name": c.name, "description": c.description}
        for c in chars
    ]


def _handle_list_psyke_entries(db: Database, project_id: int, **kwargs) -> list:
    entries = db.get_all_psyke_entries(project_id)
    return [
        {
            "id": e.id,
            "name": e.name,
            "entry_type": e.entry_type,
            "is_global": e.is_global,
        }
        for e in entries
    ]


def _handle_get_psyke_entry(db: Database, project_id: int, *, entry_id: int, **kwargs) -> dict:
    entry = db.get_psyke_entry_by_id(entry_id)
    if entry is None:
        return {"error": "Entry not found"}
    if entry.project_id != project_id:
        return {"error": "Entry does not belong to this project"}
    details = db.get_psyke_entry_details(entry_id)
    return {
        "id": entry.id,
        "name": entry.name,
        "entry_type": entry.entry_type,
        "aliases": entry.aliases,
        "notes": entry.notes,
        "is_global": entry.is_global,
        "details": details,
    }


def _handle_list_notes(db: Database, project_id: int, **kwargs) -> list:
    notes = db.get_all_notes(project_id)
    return [{"id": n.id, "title": n.title} for n in notes]


def _handle_get_note(db: Database, project_id: int, *, note_id: int, **kwargs) -> dict:
    note = db.get_note_by_id(note_id)
    if note is None:
        return {"error": "Note not found"}
    if note.project_id != project_id:
        return {"error": "Note does not belong to this project"}
    return {
        "id": note.id,
        "title": note.title,
        "content": note.content,
    }


def _handle_search(db: Database, project_id: int, *, query: str, **kwargs) -> list:
    results = db.search_project(project_id, query)
    return results[:20]


def _handle_list_available_actions(db: Database, project_id: int, **kwargs) -> list:
    from logosforge.connector_registry import describe_all_actions
    return describe_all_actions()


def _handle_get_live_context(db: Database, project_id: int, **kwargs) -> dict:
    ctx = get_live_context()
    return {
        "available": ctx.available,
        "project_id": ctx.project_id,
        "active_scene_id": ctx.active_scene_id,
        "has_selection": ctx.has_selection,
        "selection_length": len(ctx.selection),
    }


def _handle_get_current_selection(db: Database, project_id: int, **kwargs) -> dict:
    ctx = get_live_context()
    return {
        "available": ctx.available,
        "selection": ctx.selection,
        "length": len(ctx.selection),
    }


def _handle_get_active_scene(db: Database, project_id: int, **kwargs) -> dict:
    ctx = get_live_context()
    if not ctx.available or ctx.active_scene_id is None:
        return {
            "error": "No active scene. The API may not be running inside the "
                     "desktop app, or no scene is currently open.",
        }
    # Reuse the validated get_scene serializer (also checks project ownership).
    return _handle_get_scene(db, project_id, scene_id=ctx.active_scene_id)


def _handle_create_scene(
    db: Database, project_id: int, *,
    title: str, chapter: str = "", plotline: str = "", **kwargs,
) -> dict:
    scene = db.create_scene(
        project_id, title, chapter=chapter, plotline=plotline,
    )
    return {"id": scene.id, "title": scene.title}


def _handle_update_scene_title(
    db: Database, project_id: int, *, scene_id: int, title: str, **kwargs,
) -> dict:
    scene = db.get_scene_by_id(scene_id)
    if scene is None:
        return {"error": "Scene not found"}
    if scene.project_id != project_id:
        return {"error": "Scene does not belong to this project"}
    updated = db.update_scene(scene_id, title=title, summary=scene.summary,
                              synopsis=scene.synopsis, goal=scene.goal,
                              conflict=scene.conflict, outcome=scene.outcome,
                              beat=scene.beat, tags=scene.tags, act=scene.act,
                              content=scene.content, chapter=scene.chapter,
                              plotline=scene.plotline)
    return {"id": updated.id, "title": updated.title}


def _handle_create_psyke_entry(
    db: Database, project_id: int, *,
    name: str, entry_type: str = "other", notes: str = "", **kwargs,
) -> dict:
    entry = db.create_psyke_entry(
        project_id, name, entry_type=entry_type, notes=notes,
    )
    return {"id": entry.id, "name": entry.name, "entry_type": entry.entry_type}


def _handle_create_note(
    db: Database, project_id: int, *,
    title: str, content: str = "", **kwargs,
) -> dict:
    note = db.create_note(project_id, title, content=content)
    return {"id": note.id, "title": note.title}


# =============================================================================
# BIND HANDLERS TO REGISTRY
# =============================================================================

def _bind_handlers() -> None:
    from logosforge.connector_registry import get_action

    bindings = {
        "get_project": _handle_get_project,
        "list_scenes": _handle_list_scenes,
        "get_scene": _handle_get_scene,
        "list_characters": _handle_list_characters,
        "list_psyke_entries": _handle_list_psyke_entries,
        "get_psyke_entry": _handle_get_psyke_entry,
        "list_notes": _handle_list_notes,
        "get_note": _handle_get_note,
        "search": _handle_search,
        "list_available_actions": _handle_list_available_actions,
        "get_live_context": _handle_get_live_context,
        "get_current_selection": _handle_get_current_selection,
        "get_active_scene": _handle_get_active_scene,
        "create_scene": _handle_create_scene,
        "update_scene_title": _handle_update_scene_title,
        "create_psyke_entry": _handle_create_psyke_entry,
        "create_note": _handle_create_note,
    }
    for name, handler in bindings.items():
        action = get_action(name)
        if action is not None:
            action.handler = handler


_bind_handlers()
