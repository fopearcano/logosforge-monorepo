"""Plugin Executor — builds context, runs plugins, validates output.

Bridges the gap between app state (db, project) and the plugin sandbox.
Constructs PluginContext from existing context engines, executes a plugin,
validates the result, and returns it.
"""

from __future__ import annotations

from logosforge.character_balance import compute_balance
from logosforge.context_builder import (
    gather_graph_context,
    gather_outline_context,
    gather_psyke_context,
    gather_scene_context,
)
from logosforge.db import Database
from logosforge.memory_context import select_memories
from logosforge.plugin_base import (
    CharacterSnapshot,
    LogosforgePlugin,
    MemorySnapshot,
    PluginContext,
    PluginResult,
    PsykeSnapshot,
    SceneSnapshot,
    Suggestion,
)
from logosforge.plugin_registry import get_plugin
from logosforge.temporal_psyke import TemporalGraph


def build_plugin_context(
    db: Database,
    project_id: int,
    scene_id: int | None = None,
) -> PluginContext:
    """Build a PluginContext from the current app state.

    Assembles structured data and formatted text from all context engines.
    The resulting context contains no database reference.
    """
    proj = db.get_project_by_id(project_id)
    project_title = proj.title if proj else ""

    # Scenes
    all_scenes = db.get_all_scenes(project_id)
    all_characters = db.get_all_characters(project_id)
    char_name_map = {c.id: c.name for c in all_characters}

    scene_snapshots: list[SceneSnapshot] = []
    for s in all_scenes:
        char_ids = db.get_scene_character_ids(s.id)
        char_names = [char_name_map[cid] for cid in char_ids if cid in char_name_map]
        scene_snapshots.append(SceneSnapshot(
            id=s.id,
            title=s.title,
            chapter=s.chapter,
            plotline=s.plotline,
            act=s.act,
            goal=s.goal,
            conflict=s.conflict,
            outcome=s.outcome,
            content=s.content or "",
            character_names=char_names,
            sort_order=s.sort_order,
        ))

    active_scene: SceneSnapshot | None = None
    if scene_id is not None:
        for ss in scene_snapshots:
            if ss.id == scene_id:
                active_scene = ss
                break

    # Characters with balance data
    balance = compute_balance(db, project_id)
    char_snapshots: list[CharacterSnapshot] = []
    for cp in balance.characters:
        char = next((c for c in all_characters if c.id == cp.char_id), None)
        char_snapshots.append(CharacterSnapshot(
            id=cp.char_id,
            name=cp.name,
            description=char.description if char else "",
            scene_count=cp.scene_count,
            flag=cp.flag,
        ))

    # PSYKE entries at current temporal position
    psyke_snapshots: list[PsykeSnapshot] = []
    entries = db.get_all_psyke_entries(project_id)
    if scene_id is not None and all_scenes:
        scene_order_map = {s.id: s.sort_order for s in all_scenes}
        current_order = scene_order_map.get(scene_id, 0)
        tg = TemporalGraph(db, project_id)
        for entry in entries:
            state = tg.get_entry_state_at(entry.id, current_order)
            psyke_snapshots.append(PsykeSnapshot(
                id=entry.id,
                name=entry.name,
                entry_type=entry.entry_type,
                notes=entry.notes,
                is_global=entry.is_global,
                progression_text=state.progression_text if state else "",
            ))
    else:
        for entry in entries:
            psyke_snapshots.append(PsykeSnapshot(
                id=entry.id,
                name=entry.name,
                entry_type=entry.entry_type,
                notes=entry.notes,
                is_global=entry.is_global,
                progression_text="",
            ))

    # Story memory
    memory_snapshots: list[MemorySnapshot] = []
    context_memories = select_memories(db, project_id, scene_id=scene_id)
    for cm in context_memories:
        memory_snapshots.append(MemorySnapshot(
            memory_type=cm.entry.memory_type,
            target=cm.entry.target,
            value=cm.entry.value,
            scene_label=cm.scene_label,
            relevance=cm.relevance,
            superseded=cm.superseded,
        ))

    # Pre-formatted text contexts
    scene_ctx_text = ""
    psyke_ctx_text = ""
    graph_ctx_text = ""
    if scene_id is not None:
        scene_ctx_text = gather_scene_context(db, project_id, scene_id)
        psyke_ctx_text = gather_psyke_context(db, project_id, scene_id)
        graph_ctx_text = gather_graph_context(db, project_id, scene_id)
    outline_ctx_text = gather_outline_context(db, project_id)
    memory_ctx_text = ""
    if context_memories:
        from logosforge.memory_context import gather_memory_context
        memory_ctx_text = gather_memory_context(db, project_id, scene_id=scene_id)

    return PluginContext(
        project_id=project_id,
        project_title=project_title,
        active_scene=active_scene,
        scenes=scene_snapshots,
        characters=char_snapshots,
        psyke_entries=psyke_snapshots,
        memories=memory_snapshots,
        scene_context_text=scene_ctx_text,
        psyke_context_text=psyke_ctx_text,
        memory_context_text=memory_ctx_text,
        graph_context_text=graph_ctx_text,
        outline_context_text=outline_ctx_text,
    )


def run_plugin(
    db: Database,
    project_id: int,
    plugin_name: str,
    scene_id: int | None = None,
) -> PluginResult:
    """Run a plugin by name with full context.

    Builds context, executes plugin, validates result.
    Returns PluginResult on success, error result on failure.
    """
    plugin = get_plugin(plugin_name)
    if plugin is None:
        return _error_result(plugin_name, f"Plugin '{plugin_name}' not found.")

    if plugin.requires_scene and scene_id is None:
        return _error_result(plugin_name, "This plugin requires an active scene.")

    context = build_plugin_context(db, project_id, scene_id=scene_id)

    try:
        result = plugin.execute(context)
    except Exception as e:
        return _error_result(plugin_name, f"Plugin execution failed: {e}")

    if not isinstance(result, PluginResult):
        return _error_result(plugin_name, "Plugin returned invalid result type.")

    # Validate suggestions
    valid_suggestions: list[Suggestion] = []
    for s in result.suggestions:
        if isinstance(s, Suggestion) and s.text:
            valid_suggestions.append(s)
    result.suggestions = valid_suggestions

    return result


def _error_result(plugin_name: str, message: str) -> PluginResult:
    return PluginResult(
        plugin_name=plugin_name,
        summary=message,
        suggestions=[],
        metadata={"error": True},
    )
