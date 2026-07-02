"""Tests for Logosforge Plugin System."""

import logosforge.plugins  # noqa: F401 — registers built-in plugins

from logosforge.db import Database
from logosforge.plugin_base import (
    LogosforgePlugin,
    PluginContext,
    PluginResult,
    SceneSnapshot,
    Suggestion,
)
from logosforge.plugin_executor import build_plugin_context, run_plugin
from logosforge.plugin_registry import (
    clear_registry,
    describe_all_plugins,
    describe_plugin,
    get_plugin,
    list_plugin_names,
    list_plugins,
    list_plugins_by_category,
    register_plugin,
)


def _make_project():
    db = Database()
    proj = db.create_project("PluginTest")
    return db, proj


# =============================================================================
# REGISTRY
# =============================================================================

def test_builtin_plugins_registered():
    names = list_plugin_names()
    assert "dialogue_tension" in names
    assert "character_presence" in names


def test_list_plugins():
    plugins = list_plugins()
    assert len(plugins) >= 2


def test_get_plugin():
    p = get_plugin("dialogue_tension")
    assert p is not None
    assert p.name == "dialogue_tension"


def test_get_plugin_unknown():
    p = get_plugin("nonexistent_plugin")
    assert p is None


def test_describe_plugin():
    desc = describe_plugin("dialogue_tension")
    assert desc is not None
    assert desc["name"] == "dialogue_tension"
    assert "description" in desc
    assert "category" in desc


def test_describe_all_plugins():
    all_desc = describe_all_plugins()
    assert len(all_desc) >= 2
    names = [d["name"] for d in all_desc]
    assert "dialogue_tension" in names


def test_list_by_category():
    analysis = list_plugins_by_category("analysis")
    assert any(p.name == "dialogue_tension" for p in analysis)
    structure = list_plugins_by_category("structure")
    assert any(p.name == "character_presence" for p in structure)


def test_register_custom_plugin():
    class TestPlugin(LogosforgePlugin):
        @property
        def name(self): return "test_custom"
        @property
        def description(self): return "Test"
        def execute(self, ctx):
            return PluginResult(plugin_name=self.name, summary="OK")

    register_plugin(TestPlugin())
    assert get_plugin("test_custom") is not None
    # Cleanup
    from logosforge.plugin_registry import _PLUGINS
    _PLUGINS.pop("test_custom", None)


# =============================================================================
# CONTEXT BUILDING
# =============================================================================

def test_build_context_empty_project():
    db, proj = _make_project()
    ctx = build_plugin_context(db, proj.id)
    assert ctx.project_id == proj.id
    assert ctx.project_title == "PluginTest"
    assert ctx.scenes == []
    assert ctx.active_scene is None


def test_build_context_with_scene():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    s = db.create_scene(
        proj.id, "Battle",
        content="Hero draws sword.",
        goal="Survive",
        character_ids=[c.id],
    )
    ctx = build_plugin_context(db, proj.id, scene_id=s.id)
    assert ctx.active_scene is not None
    assert ctx.active_scene.title == "Battle"
    assert ctx.active_scene.goal == "Survive"
    assert "Hero" in ctx.active_scene.character_names


def test_build_context_includes_characters():
    db, proj = _make_project()
    db.create_character(proj.id, "Alice")
    db.create_character(proj.id, "Bob")
    ctx = build_plugin_context(db, proj.id)
    assert len(ctx.characters) == 2
    names = [c.name for c in ctx.characters]
    assert "Alice" in names
    assert "Bob" in names


def test_build_context_includes_psyke():
    db, proj = _make_project()
    db.create_psyke_entry(proj.id, "Magic", entry_type="worldbuilding")
    ctx = build_plugin_context(db, proj.id)
    assert len(ctx.psyke_entries) == 1
    assert ctx.psyke_entries[0].name == "Magic"


def test_build_context_includes_memories():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    s = db.create_scene(
        proj.id, "S1",
        outcome="The kingdom falls to the dark army",
        character_ids=[c.id],
    )
    from logosforge.story_memory import extract_scene_memory
    extract_scene_memory(db, proj.id, s.id)
    ctx = build_plugin_context(db, proj.id, scene_id=s.id)
    assert len(ctx.memories) >= 1


def test_build_context_no_db_reference():
    db, proj = _make_project()
    ctx = build_plugin_context(db, proj.id)
    assert not hasattr(ctx, "db")
    assert not hasattr(ctx, "_db")


# =============================================================================
# EXECUTOR
# =============================================================================

def test_run_plugin_not_found():
    db, proj = _make_project()
    result = run_plugin(db, proj.id, "nonexistent")
    assert result.plugin_name == "nonexistent"
    assert "not found" in result.summary


def test_run_plugin_requires_scene():
    db, proj = _make_project()
    result = run_plugin(db, proj.id, "dialogue_tension", scene_id=None)
    assert "requires an active scene" in result.summary


def test_run_plugin_no_scene_required():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    for i in range(4):
        db.create_scene(proj.id, f"S{i+1}", character_ids=[c.id])
    result = run_plugin(db, proj.id, "character_presence", scene_id=None)
    assert result.plugin_name == "character_presence"
    assert "error" not in result.metadata


def test_run_plugin_returns_valid_result():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    s = db.create_scene(
        proj.id, "S1",
        content='"Stay back!" Hero shouted.\n"Why?" she asked.\n"Because I said so."',
        character_ids=[c.id],
    )
    result = run_plugin(db, proj.id, "dialogue_tension", scene_id=s.id)
    assert isinstance(result, PluginResult)
    assert result.plugin_name == "dialogue_tension"
    assert isinstance(result.suggestions, list)


# =============================================================================
# DIALOGUE TENSION PLUGIN
# =============================================================================

def test_dialogue_high_density():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Alice")
    content = "\n".join([
        '"Line one," Alice said.',
        '"Line two," she replied.',
        '"Line three."',
        '"Line four."',
        '"Line five."',
        '"Line six."',
        '"Line seven."',
        '"Line eight."',
        '"Line nine."',
        '"Line ten."',
    ])
    s = db.create_scene(proj.id, "TalkScene", content=content, character_ids=[c.id])
    result = run_plugin(db, proj.id, "dialogue_tension", scene_id=s.id)
    texts = [sg.text for sg in result.suggestions]
    assert any("heavily dialogue-driven" in t for t in texts)


def test_dialogue_low_density():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    content = "\n".join([
        "The wind howled across the plains.",
        "Mountains rose in the distance.",
        "Snow covered the trail ahead.",
        "The horse stumbled on a rock.",
        "Night was falling quickly now.",
        "Stars appeared one by one above.",
    ])
    s = db.create_scene(proj.id, "SilentScene", content=content, character_ids=[c.id])
    result = run_plugin(db, proj.id, "dialogue_tension", scene_id=s.id)
    texts = [sg.text for sg in result.suggestions]
    assert any("little dialogue" in t.lower() for t in texts)


def test_dialogue_conflict_no_tension():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    # Long, calm dialogue with no tension patterns: no ellipsis, no dashes,
    # no short quotes, no ? or ! inside quotes
    content = "\n".join([
        'Hero said "I suppose we should discuss the arrangement sometime soon"',
        'She replied "That sounds perfectly reasonable to me actually"',
        'He mentioned "The weather has been remarkably pleasant this season"',
        'She noted "I heard the harvest is expected to be quite good this year"',
    ])
    s = db.create_scene(
        proj.id, "FlatConflict",
        content=content,
        conflict="Hero confronts the betrayal that shattered everything",
        character_ids=[c.id],
    )
    result = run_plugin(db, proj.id, "dialogue_tension", scene_id=s.id)
    texts = [sg.text for sg in result.suggestions]
    assert any("tension markers" in t for t in texts)


def test_dialogue_metadata():
    db, proj = _make_project()
    c = db.create_character(proj.id, "A")
    content = '"Yes," she said.\n"No," he replied.\nSilence fell.'
    s = db.create_scene(proj.id, "S1", content=content, character_ids=[c.id])
    result = run_plugin(db, proj.id, "dialogue_tension", scene_id=s.id)
    assert "dialogue_lines" in result.metadata
    assert "dialogue_ratio" in result.metadata


def test_dialogue_empty_content():
    db, proj = _make_project()
    c = db.create_character(proj.id, "A")
    s = db.create_scene(proj.id, "Empty", content="", character_ids=[c.id])
    result = run_plugin(db, proj.id, "dialogue_tension", scene_id=s.id)
    assert "insufficient" in result.summary.lower()


# =============================================================================
# CHARACTER PRESENCE PLUGIN
# =============================================================================

def test_presence_disappearance():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Vanisher")
    c2 = db.create_character(proj.id, "Constant")
    # Vanisher appears in first 2, then gone for 5
    for i in range(7):
        char_ids = [c2.id]
        if i < 2:
            char_ids.append(c1.id)
        db.create_scene(proj.id, f"S{i+1}", character_ids=char_ids)

    result = run_plugin(db, proj.id, "character_presence")
    texts = [sg.text for sg in result.suggestions]
    assert any("Vanisher" in t and "absence" in t.lower() for t in texts)


def test_presence_clustering():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Cluster")
    c2 = db.create_character(proj.id, "Spread")
    # Create 10 scenes. Cluster only in 3-5.
    for i in range(10):
        char_ids = [c2.id]
        if 2 <= i <= 4:
            char_ids.append(c1.id)
        db.create_scene(proj.id, f"S{i+1}", character_ids=char_ids)

    result = run_plugin(db, proj.id, "character_presence")
    texts = [sg.text for sg in result.suggestions]
    assert any("Cluster" in t and "span" in t for t in texts)


def test_presence_too_few_scenes():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    db.create_scene(proj.id, "S1", character_ids=[c.id])
    db.create_scene(proj.id, "S2", character_ids=[c.id])
    result = run_plugin(db, proj.id, "character_presence")
    assert "at least 3" in result.summary.lower()


def test_presence_no_characters():
    db, proj = _make_project()
    for i in range(5):
        db.create_scene(proj.id, f"S{i+1}")
    result = run_plugin(db, proj.id, "character_presence")
    assert "No characters" in result.summary


def test_presence_metadata():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    for i in range(5):
        db.create_scene(proj.id, f"S{i+1}", character_ids=[c.id])
    result = run_plugin(db, proj.id, "character_presence")
    assert "total_characters" in result.metadata
    assert "total_scenes" in result.metadata
    assert "presence_ratios" in result.metadata


# =============================================================================
# PLUGIN SAFETY
# =============================================================================

def test_plugin_context_is_snapshot():
    """PluginContext contains data copies, no DB reference."""
    db, proj = _make_project()
    c = db.create_character(proj.id, "A")
    db.create_scene(proj.id, "S1", character_ids=[c.id])
    ctx = build_plugin_context(db, proj.id)
    # Modifying the context should not affect the DB
    ctx.scenes[0] = SceneSnapshot(
        id=999, title="Fake", chapter="", plotline="", act="",
        goal="", conflict="", outcome="", content="",
        character_names=[], sort_order=0,
    )
    real_scenes = db.get_all_scenes(proj.id)
    assert real_scenes[0].title == "S1"


def test_plugin_result_validation():
    """Invalid suggestions are filtered out by executor."""
    class BadPlugin(LogosforgePlugin):
        @property
        def name(self): return "_bad_test"
        @property
        def description(self): return "Test"
        def execute(self, ctx):
            return PluginResult(
                plugin_name=self.name,
                suggestions=[
                    Suggestion(text="Valid", category="test"),
                    Suggestion(text="", category="test"),  # Empty — should be filtered
                ],
            )

    register_plugin(BadPlugin())
    db, proj = _make_project()
    db.create_scene(proj.id, "S1")
    result = run_plugin(db, proj.id, "_bad_test", scene_id=1)
    assert len(result.suggestions) == 1
    assert result.suggestions[0].text == "Valid"
    # Cleanup
    from logosforge.plugin_registry import _PLUGINS
    _PLUGINS.pop("_bad_test", None)


def test_plugin_crash_handled():
    """If a plugin raises, executor returns error result."""
    class CrashPlugin(LogosforgePlugin):
        @property
        def name(self): return "_crash_test"
        @property
        def description(self): return "Test"
        def execute(self, ctx):
            raise RuntimeError("Boom")

    register_plugin(CrashPlugin())
    db, proj = _make_project()
    db.create_scene(proj.id, "S1")
    result = run_plugin(db, proj.id, "_crash_test", scene_id=1)
    assert "failed" in result.summary.lower()
    assert result.metadata.get("error") is True
    # Cleanup
    from logosforge.plugin_registry import _PLUGINS
    _PLUGINS.pop("_crash_test", None)
