"""Tests for the Idea di Controllo plugin and core module."""

from __future__ import annotations

import json

import pytest

from logosforge.assistant import build_messages
from logosforge.controlling_idea import (
    ALIGNMENT_LABELS,
    CI_KEY,
    VALID_CHARGES,
    ControllingIdea,
    check,
    clear,
    ensure_theme_entry,
    gather_controlling_idea_context,
    handle_command,
    link_psyke_entry,
    load,
    save,
    set_psyke_alignment,
    set_scene_alignment,
)
from logosforge.db import Database
from logosforge.plugin_manager import PluginManager
from logosforge.psyke_command_registry import CommandContext, CommandRegistry
from logosforge.psyke_system_commands import SystemCommandHandlers


def _setup():
    db = Database()
    proj = db.create_project("Test")
    return db, proj


# ==========================================================================
# 1. Plugin loads
# ==========================================================================

def test_plugin_manifest_valid():
    import json as _json
    from pathlib import Path
    path = (
        Path(__file__).resolve().parents[1]
        / "plugins" / "idea_di_controllo" / "plugin.json"
    )
    manifest = _json.loads(path.read_text())
    assert manifest["id"] == "idea_di_controllo"
    assert manifest["name"] == "Idea di Controllo"
    assert manifest["enabled_by_default"] is True


def test_plugin_loads_via_manager(monkeypatch, tmp_path):
    import logosforge.plugin_manager as pm
    from pathlib import Path
    repo_plugins = Path(__file__).resolve().parents[1] / "plugins"
    monkeypatch.setattr(pm, "PLUGINS_DIR", repo_plugins)
    manager = PluginManager()
    manager.discover()
    target = [p for p in manager.plugins if p.id == "idea_di_controllo"]
    assert len(target) == 1
    info = target[0]
    db, proj = _setup()
    manager.set_app_context(db, proj.id)
    manager.load_enabled()
    info = [p for p in manager.plugins if p.id == "idea_di_controllo"][0]
    assert info.loaded is True
    assert info.error == ""
    # The plugin registers exactly three menu actions
    titles = [name for name, _ in info.menu_actions]
    assert "Idea di Controllo: Show" in titles
    assert "Idea di Controllo: Check" in titles
    assert "Idea di Controllo: Create / Update PSYKE Theme" in titles


# ==========================================================================
# 2. CRUD + persistence per project
# ==========================================================================

def test_default_idea_is_undefined():
    db, proj = _setup()
    idea = load(db, proj.id)
    assert idea.is_defined() is False
    assert idea.value == ""
    assert idea.cause == ""


def test_save_load_roundtrip():
    db, proj = _setup()
    idea = ControllingIdea(
        enabled=True,
        value_charge="positive",
        value="justice",
        cause="when the hero sacrifices safety for truth",
        statement="Justice prevails when the hero sacrifices safety for truth.",
        counter_idea="Cynicism wins when comfort is preferred to action.",
        notes="Pilot premise.",
    )
    save(db, proj.id, idea)
    reloaded = load(db, proj.id)
    assert reloaded.statement.startswith("Justice prevails")
    assert reloaded.value == "justice"
    assert reloaded.value_charge == "positive"
    assert reloaded.is_defined() is True


def test_new_project_does_not_inherit_old_idea():
    db, proj1 = _setup()
    save(db, proj1.id, ControllingIdea(
        enabled=True, value="freedom", cause="when truth is told",
        statement="x", counter_idea="y",
    ))
    proj2 = db.create_project("Other")
    other = load(db, proj2.id)
    assert other.is_defined() is False
    assert other.value == ""


def test_clear_removes_idea():
    db, proj = _setup()
    save(db, proj.id, ControllingIdea(value="x", cause="y", statement="z"))
    clear(db, proj.id)
    settings = db.get_project_settings(proj.id) or {}
    assert CI_KEY not in settings
    assert load(db, proj.id).is_defined() is False


def test_invalid_charge_falls_back_to_positive():
    db, proj = _setup()
    settings = {"controlling_idea": {"value_charge": "lemon", "value": "x", "cause": "y"}}
    db.save_project_settings(proj.id, settings)
    idea = load(db, proj.id)
    assert idea.value_charge == "positive"


# ==========================================================================
# 3. PSYKE linking
# ==========================================================================

def test_ensure_theme_entry_creates_psyke_entry():
    db, proj = _setup()
    save(db, proj.id, ControllingIdea(
        value="justice", cause="when truth is told",
        statement="Justice prevails.",
    ))
    entry_id = ensure_theme_entry(db, proj.id)
    assert entry_id is not None
    entry = db.get_psyke_entry_by_id(entry_id)
    assert entry.entry_type == "theme"
    assert "Justice prevails." in entry.notes
    # Idea now remembers the entry id
    assert load(db, proj.id).theme_psyke_entry_id == entry_id


def test_ensure_theme_entry_updates_existing():
    db, proj = _setup()
    save(db, proj.id, ControllingIdea(
        value="justice", cause="when truth is told", statement="v1",
    ))
    e1 = ensure_theme_entry(db, proj.id)
    # Mutate idea and re-link
    idea = load(db, proj.id)
    idea.statement = "v2 — restated"
    save(db, proj.id, idea)
    e2 = ensure_theme_entry(db, proj.id)
    assert e1 == e2  # same entry, updated
    entry = db.get_psyke_entry_by_id(e2)
    assert "v2 — restated" in entry.notes


def test_ensure_theme_entry_returns_none_when_undefined():
    db, proj = _setup()
    assert ensure_theme_entry(db, proj.id) is None


def test_link_and_alignment_persist():
    db, proj = _setup()
    save(db, proj.id, ControllingIdea(value="x", cause="y", statement="z"))
    char = db.create_psyke_entry(proj.id, "John", entry_type="character")
    link_psyke_entry(db, proj.id, char.id)
    set_psyke_alignment(db, proj.id, char.id, "tests")
    idea = load(db, proj.id)
    assert char.id in idea.linked_psyke_entries
    assert idea.psyke_alignment[str(char.id)] == "tests"


def test_invalid_scene_alignment_raises():
    db, proj = _setup()
    save(db, proj.id, ControllingIdea(value="x", cause="y", statement="z"))
    scene = db.create_scene(proj.id, "S1")
    with pytest.raises(ValueError):
        set_scene_alignment(db, proj.id, scene.id, "rainbow")


def test_clearing_scene_alignment():
    db, proj = _setup()
    save(db, proj.id, ControllingIdea(value="x", cause="y", statement="z"))
    scene = db.create_scene(proj.id, "S1")
    set_scene_alignment(db, proj.id, scene.id, "supports")
    set_scene_alignment(db, proj.id, scene.id, None)
    idea = load(db, proj.id)
    assert str(scene.id) not in idea.scene_alignment


# ==========================================================================
# 4. Assistant context inclusion / exclusion
# ==========================================================================

def test_context_block_empty_when_undefined():
    db, proj = _setup()
    assert gather_controlling_idea_context(db, proj.id) == ""


def test_context_block_contains_idea_fields():
    db, proj = _setup()
    save(db, proj.id, ControllingIdea(
        value="justice", value_charge="positive",
        cause="when truth is told",
        statement="Justice prevails when truth is told.",
        counter_idea="Cynicism wins when silence is chosen.",
    ))
    block = gather_controlling_idea_context(db, proj.id)
    assert "[Idea di Controllo]" in block
    assert "Justice prevails" in block
    assert "Value: justice (positive)" in block
    assert "Cause: when truth is told" in block
    assert "Counter-Idea: Cynicism" in block


def test_context_block_lists_active_scene_alignment():
    db, proj = _setup()
    save(db, proj.id, ControllingIdea(value="x", cause="y", statement="z"))
    scene = db.create_scene(proj.id, "Turning Point")
    set_scene_alignment(db, proj.id, scene.id, "transforms")
    block = gather_controlling_idea_context(db, proj.id, scene_id=scene.id)
    assert "This scene currently: transforms" in block


def test_context_block_lists_linked_psyke_with_alignment():
    db, proj = _setup()
    save(db, proj.id, ControllingIdea(value="x", cause="y", statement="z"))
    char = db.create_psyke_entry(proj.id, "Lara", entry_type="character")
    set_psyke_alignment(db, proj.id, char.id, "opposes")
    block = gather_controlling_idea_context(db, proj.id)
    assert "Lara (opposes)" in block


def test_build_messages_includes_controlling_idea_block():
    block = "[Idea di Controllo]\nStatement: Justice prevails."
    messages = build_messages(
        "Improve this scene", "scene context here",
        controlling_idea_context=block,
    )
    user_msg = messages[1]["content"]
    assert "[Idea di Controllo]" in user_msg


def test_build_messages_omits_block_when_empty():
    messages = build_messages("Improve this scene", "scene context here")
    user_msg = messages[1]["content"]
    assert "[Idea di Controllo]" not in user_msg


# ==========================================================================
# 5. /idea slash command
# ==========================================================================

def _make_handlers(db, proj_id):
    return SystemCommandHandlers(db, proj_id)


def _run_idea(handlers, *args):
    ctx = CommandContext(command="idea", args=list(args), raw="/idea " + " ".join(args))
    return handlers.handle_idea(ctx)


def test_idea_set_creates_statement():
    db, proj = _setup()
    handlers = _make_handlers(db, proj.id)
    result = _run_idea(
        handlers, "set", 'value="justice"',
        'cause="when truth is told"',
    )
    assert result["ok"] is True
    idea = load(db, proj.id)
    assert idea.value == "justice"
    assert idea.cause == "when truth is told"
    assert idea.statement.startswith("Justice prevails")


def test_idea_explain_returns_block():
    db, proj = _setup()
    save(db, proj.id, ControllingIdea(value="x", cause="y", statement="z"))
    handlers = _make_handlers(db, proj.id)
    result = _run_idea(handlers, "explain")
    assert result["ok"] is True
    assert "[Idea di Controllo]" in result["message"]


def test_idea_check_returns_report():
    db, proj = _setup()
    save(db, proj.id, ControllingIdea(value="x", cause="y", statement="z"))
    db.create_scene(proj.id, "Open")
    sc = db.create_scene(proj.id, "Mid")
    set_scene_alignment(db, proj.id, sc.id, "supports")
    handlers = _make_handlers(db, proj.id)
    result = _run_idea(handlers, "check")
    assert result["ok"] is True
    assert "Supports" in result["message"]


def test_idea_link_to_psyke_with_alignment():
    db, proj = _setup()
    save(db, proj.id, ControllingIdea(value="x", cause="y", statement="z"))
    char = db.create_psyke_entry(proj.id, "John", entry_type="character")
    handlers = _make_handlers(db, proj.id)
    result = _run_idea(handlers, "link", str(char.id), "tests")
    assert result["ok"] is True
    idea = load(db, proj.id)
    assert char.id in idea.linked_psyke_entries
    assert idea.psyke_alignment[str(char.id)] == "tests"


def test_idea_link_no_args_creates_theme_entry():
    db, proj = _setup()
    save(db, proj.id, ControllingIdea(value="x", cause="y", statement="z"))
    handlers = _make_handlers(db, proj.id)
    result = _run_idea(handlers, "link")
    assert result["ok"] is True
    entry_id = load(db, proj.id).theme_psyke_entry_id
    assert entry_id is not None
    assert db.get_psyke_entry_by_id(entry_id).entry_type == "theme"


def test_idea_unknown_subcommand_errors():
    db, proj = _setup()
    handlers = _make_handlers(db, proj.id)
    result = _run_idea(handlers, "delete-everything")
    assert result["ok"] is False


def test_idea_scene_clear():
    db, proj = _setup()
    save(db, proj.id, ControllingIdea(value="x", cause="y", statement="z"))
    sc = db.create_scene(proj.id, "S1")
    set_scene_alignment(db, proj.id, sc.id, "supports")
    handlers = _make_handlers(db, proj.id)
    result = _run_idea(handlers, "scene", str(sc.id), "clear")
    assert result["ok"] is True
    assert str(sc.id) not in load(db, proj.id).scene_alignment


def test_idea_command_triggers_on_data_changed():
    db, proj = _setup()
    calls = []
    handlers = SystemCommandHandlers(
        db, proj.id, on_data_changed=lambda: calls.append(True),
    )
    _run_idea(handlers, "set", 'value="x"', 'cause="y"')
    assert len(calls) == 1


# ==========================================================================
# 6. Checker behavior
# ==========================================================================

def test_check_with_no_idea_returns_hint():
    db, proj = _setup()
    report = check(db, proj.id)
    assert report.statement == ""
    assert any("No Controlling Idea" in s for s in report.suggestions)


def test_check_buckets_scenes_correctly():
    db, proj = _setup()
    save(db, proj.id, ControllingIdea(
        value="x", cause="y", statement="z", counter_idea="cc",
    ))
    s1 = db.create_scene(proj.id, "S1")
    s2 = db.create_scene(proj.id, "S2")
    s3 = db.create_scene(proj.id, "S3")
    s4 = db.create_scene(proj.id, "S4")
    set_scene_alignment(db, proj.id, s1.id, "supports")
    set_scene_alignment(db, proj.id, s2.id, "opposes")
    set_scene_alignment(db, proj.id, s3.id, "transforms")
    # s4 left unmarked
    report = check(db, proj.id)
    assert len(report.aligned_scenes) == 1
    assert len(report.opposed_scenes) == 1
    assert len(report.transformed_scenes) == 1
    assert len(report.unmarked_scenes) == 1
    text = report.format()
    assert "Supports (1)" in text


def test_check_flags_unaligned_psyke():
    db, proj = _setup()
    save(db, proj.id, ControllingIdea(value="x", cause="y", statement="z"))
    db.create_psyke_entry(proj.id, "Stranger", entry_type="character")
    report = check(db, proj.id)
    assert any(name == "Stranger" for _, name in report.unaligned_psyke)


def test_check_suggests_counter_idea_when_missing():
    db, proj = _setup()
    save(db, proj.id, ControllingIdea(value="x", cause="y", statement="z"))
    report = check(db, proj.id)
    assert any("counter-idea" in s.lower() for s in report.suggestions)


# ==========================================================================
# 7. Cache invalidation when CI changes
# ==========================================================================

def test_changing_idea_changes_context_block():
    db, proj = _setup()
    save(db, proj.id, ControllingIdea(value="x", cause="y", statement="ALPHA"))
    block_a = gather_controlling_idea_context(db, proj.id)
    save(db, proj.id, ControllingIdea(value="x", cause="y", statement="BETA"))
    block_b = gather_controlling_idea_context(db, proj.id)
    assert block_a != block_b
    assert "ALPHA" in block_a and "BETA" in block_b


def test_changing_idea_invalidates_assistant_cache():
    """Different CI context produces a different build_messages payload,
    so the assistant cache key (sha256 of messages+provider) differs."""
    import hashlib
    from logosforge.providers import ProviderConfig

    msgs_a = build_messages(
        "Improve scene", "scene ctx",
        controlling_idea_context="[Idea di Controllo]\nStatement: A",
    )
    msgs_b = build_messages(
        "Improve scene", "scene ctx",
        controlling_idea_context="[Idea di Controllo]\nStatement: B",
    )
    key_a = hashlib.sha256(
        (json.dumps(msgs_a, sort_keys=True) + "u" + "m").encode()
    ).hexdigest()
    key_b = hashlib.sha256(
        (json.dumps(msgs_b, sort_keys=True) + "u" + "m").encode()
    ).hexdigest()
    assert key_a != key_b


# ==========================================================================
# 8. Go McKee detection
# ==========================================================================

def test_gomckee_hint_only_when_enabled(monkeypatch):
    """The hint follows the real enabled toggle, not mere load state."""

    class FakeMgr:
        def __init__(self):
            self.plugins = []
            self._states = {}

        def is_enabled(self, pid):
            return self._states.get(pid, False)

    fake = FakeMgr()
    monkeypatch.setattr(
        "logosforge.plugin_manager.get_plugin_manager",
        lambda: fake,
    )
    db, proj = _setup()
    save(db, proj.id, ControllingIdea(value="x", cause="y", statement="z"))

    # No Go McKee plugin at all → no hint.
    assert "Go McKee" not in gather_controlling_idea_context(db, proj.id)

    # Plugin present but DISABLED (loaded is irrelevant) → no hint.
    class GMPlugin:
        id = "gomckee_plugin"
        loaded = True
        enabled = False
    fake.plugins = [GMPlugin()]
    assert "Go McKee" not in gather_controlling_idea_context(db, proj.id)

    # Plugin ENABLED → hint appears.
    fake._states["gomckee_plugin"] = True
    assert "Go McKee" in gather_controlling_idea_context(db, proj.id)
