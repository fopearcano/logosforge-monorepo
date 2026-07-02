from __future__ import annotations

from typing import Any, Dict


def build_psyche_snapshot(project_data: Dict[str, Any] | None) -> Dict[str, Any]:
    project_data = project_data or {}
    current_scene = project_data.get("current_scene") or {}
    nearby_scenes = project_data.get("nearby_scenes") or []
    entries = project_data.get("psyke_entries") or []
    character_states = project_data.get("character_states") or {}
    relations = project_data.get("relations") or []
    story_memory = project_data.get("story_memory") or []
    return {
        "current_scene": current_scene,
        "nearby_scenes": nearby_scenes,
        "psyke_entries": entries,
        "character_states": character_states,
        "relations": relations,
        "story_memory": story_memory,
        "scene_count": project_data.get("scene_count"),
        "project_title": project_data.get("project_title"),
        "signals": {
            "has_current_scene": bool(current_scene),
            "has_relations": bool(relations),
            "has_progression": bool(character_states),
            "has_story_memory": bool(story_memory),
            "has_neighbor_scenes": bool(nearby_scenes),
        },
    }
