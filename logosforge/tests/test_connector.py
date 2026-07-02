"""Tests for CONNECTOR — local AI control bridge."""

import pytest

from logosforge.connector_executor import execute_action
from logosforge.connector_registry import (
    describe_action,
    describe_all_actions,
    get_action,
    list_action_names,
    list_actions,
)
from logosforge.db import Database
from logosforge.settings import get_manager as get_settings


@pytest.fixture(autouse=True)
def _connector_enabled():
    """Enable the Connector for every test in this module."""
    mgr = get_settings()
    prev_enabled = mgr.get("connector_enabled")
    prev_writes = mgr.get("connector_allow_writes")
    prev_disabled = list(mgr.get("connector_disabled_actions") or [])
    mgr.set("connector_enabled", True)
    mgr.set("connector_allow_writes", True)
    mgr.set("connector_disabled_actions", [])
    yield
    mgr.set("connector_enabled", prev_enabled)
    mgr.set("connector_allow_writes", prev_writes)
    mgr.set("connector_disabled_actions", prev_disabled)


def _make_project():
    db = Database()
    proj = db.create_project("ConnectorTest")
    return db, proj


# =============================================================================
# REGISTRY TESTS
# =============================================================================

def test_registry_has_actions():
    names = list_action_names()
    assert len(names) >= 10


def test_registry_list_actions():
    actions = list_actions()
    assert all(a.name for a in actions)
    assert all(a.description for a in actions)


def test_describe_action_known():
    desc = describe_action("get_project")
    assert desc is not None
    assert desc["name"] == "get_project"
    assert desc["category"] == "read"


def test_describe_action_unknown():
    desc = describe_action("nonexistent_action")
    assert desc is None


def test_describe_all_actions():
    all_desc = describe_all_actions()
    assert len(all_desc) >= 10
    names = [d["name"] for d in all_desc]
    assert "get_project" in names
    assert "create_scene" in names


def test_action_has_handler():
    action = get_action("get_project")
    assert action is not None
    assert action.handler is not None


def test_all_actions_have_handlers():
    for action in list_actions():
        assert action.handler is not None, f"{action.name} missing handler"


# =============================================================================
# EXECUTOR — VALIDATION
# =============================================================================

def test_missing_action_field():
    db, proj = _make_project()
    result = execute_action(db, proj.id, {})
    assert result["ok"] is False
    assert "Missing" in result["error"]


def test_unknown_action():
    db, proj = _make_project()
    result = execute_action(db, proj.id, {"action": "destroy_everything"})
    assert result["ok"] is False
    assert "Unknown action" in result["error"]


def test_invalid_args_type():
    db, proj = _make_project()
    result = execute_action(db, proj.id, {"action": "get_project", "args": "bad"})
    assert result["ok"] is False
    assert "must be a dict" in result["error"]


def test_missing_required_param():
    db, proj = _make_project()
    result = execute_action(db, proj.id, {"action": "get_scene", "args": {}})
    assert result["ok"] is False
    assert "Missing required" in result["error"]


def test_invalid_param_type():
    db, proj = _make_project()
    result = execute_action(db, proj.id, {
        "action": "get_scene",
        "args": {"scene_id": "not_a_number"},
    })
    assert result["ok"] is False
    assert "must be an integer" in result["error"]


def test_param_coercion_int_from_string():
    db, proj = _make_project()
    c = db.create_character(proj.id, "A")
    s = db.create_scene(proj.id, "S1", character_ids=[c.id])
    result = execute_action(db, proj.id, {
        "action": "get_scene",
        "args": {"scene_id": str(s.id)},
    })
    assert result["ok"] is True


# =============================================================================
# READ ACTIONS
# =============================================================================

def test_get_project():
    db, proj = _make_project()
    result = execute_action(db, proj.id, {"action": "get_project"})
    assert result["ok"] is True
    assert result["result"]["title"] == "ConnectorTest"
    assert result["result"]["id"] == proj.id


def test_list_scenes_empty():
    db, proj = _make_project()
    result = execute_action(db, proj.id, {"action": "list_scenes"})
    assert result["ok"] is True
    assert result["result"] == []


def test_list_scenes():
    db, proj = _make_project()
    db.create_scene(proj.id, "First Scene", chapter="Ch1")
    db.create_scene(proj.id, "Second Scene", chapter="Ch2")
    result = execute_action(db, proj.id, {"action": "list_scenes"})
    assert result["ok"] is True
    assert len(result["result"]) == 2
    assert result["result"][0]["title"] == "First Scene"
    assert result["result"][0]["chapter"] == "Ch1"


def test_get_scene():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    s = db.create_scene(
        proj.id, "Battle", goal="Survive",
        conflict="Outnumbered", character_ids=[c.id],
    )
    result = execute_action(db, proj.id, {
        "action": "get_scene",
        "args": {"scene_id": s.id},
    })
    assert result["ok"] is True
    assert result["result"]["title"] == "Battle"
    assert result["result"]["goal"] == "Survive"
    assert c.id in result["result"]["character_ids"]


def test_get_scene_not_found():
    db, proj = _make_project()
    result = execute_action(db, proj.id, {
        "action": "get_scene",
        "args": {"scene_id": 99999},
    })
    assert result["ok"] is False
    assert "not found" in result["error"]


def test_get_scene_wrong_project():
    db = Database()
    proj1 = db.create_project("P1")
    proj2 = db.create_project("P2")
    s = db.create_scene(proj1.id, "Secret")
    result = execute_action(db, proj2.id, {
        "action": "get_scene",
        "args": {"scene_id": s.id},
    })
    assert result["ok"] is False
    assert "does not belong" in result["error"]


def test_list_characters():
    db, proj = _make_project()
    db.create_character(proj.id, "Alice", description="The protagonist")
    db.create_character(proj.id, "Bob")
    result = execute_action(db, proj.id, {"action": "list_characters"})
    assert result["ok"] is True
    assert len(result["result"]) == 2
    assert result["result"][0]["name"] == "Alice"
    assert result["result"][0]["description"] == "The protagonist"


def test_list_psyke_entries():
    db, proj = _make_project()
    db.create_psyke_entry(proj.id, "Magic System", entry_type="worldbuilding")
    result = execute_action(db, proj.id, {"action": "list_psyke_entries"})
    assert result["ok"] is True
    assert len(result["result"]) == 1
    assert result["result"][0]["name"] == "Magic System"
    assert result["result"][0]["entry_type"] == "worldbuilding"


def test_get_psyke_entry():
    db, proj = _make_project()
    entry = db.create_psyke_entry(proj.id, "Eldoria", notes="A hidden realm")
    result = execute_action(db, proj.id, {
        "action": "get_psyke_entry",
        "args": {"entry_id": entry.id},
    })
    assert result["ok"] is True
    assert result["result"]["name"] == "Eldoria"
    assert result["result"]["notes"] == "A hidden realm"


def test_get_psyke_entry_not_found():
    db, proj = _make_project()
    result = execute_action(db, proj.id, {
        "action": "get_psyke_entry",
        "args": {"entry_id": 99999},
    })
    assert result["ok"] is False


def test_list_notes():
    db, proj = _make_project()
    db.create_note(proj.id, "Plot Ideas", content="...")
    result = execute_action(db, proj.id, {"action": "list_notes"})
    assert result["ok"] is True
    assert len(result["result"]) == 1
    assert result["result"][0]["title"] == "Plot Ideas"


def test_get_note():
    db, proj = _make_project()
    note = db.create_note(proj.id, "Themes", content="Redemption, Loss")
    result = execute_action(db, proj.id, {
        "action": "get_note",
        "args": {"note_id": note.id},
    })
    assert result["ok"] is True
    assert result["result"]["content"] == "Redemption, Loss"


def test_get_note_not_found():
    db, proj = _make_project()
    result = execute_action(db, proj.id, {
        "action": "get_note",
        "args": {"note_id": 99999},
    })
    assert result["ok"] is False


def test_search():
    db, proj = _make_project()
    db.create_scene(proj.id, "The Dragon Battle")
    db.create_scene(proj.id, "Quiet Morning")
    result = execute_action(db, proj.id, {
        "action": "search",
        "args": {"query": "Dragon"},
    })
    assert result["ok"] is True
    assert len(result["result"]) >= 1


def test_list_available_actions():
    db, proj = _make_project()
    result = execute_action(db, proj.id, {"action": "list_available_actions"})
    assert result["ok"] is True
    names = [a["name"] for a in result["result"]]
    assert "get_project" in names
    assert "create_scene" in names
    assert "list_available_actions" in names


# =============================================================================
# WRITE ACTIONS
# =============================================================================

def test_create_scene():
    db, proj = _make_project()
    result = execute_action(db, proj.id, {
        "action": "create_scene",
        "args": {"title": "New Adventure"},
    })
    assert result["ok"] is True
    assert result["result"]["title"] == "New Adventure"
    assert result["result"]["id"] is not None
    scenes = db.get_all_scenes(proj.id)
    assert any(s.title == "New Adventure" for s in scenes)


def test_create_scene_with_chapter():
    db, proj = _make_project()
    result = execute_action(db, proj.id, {
        "action": "create_scene",
        "args": {"title": "S1", "chapter": "Chapter 3"},
    })
    assert result["ok"] is True
    scene = db.get_scene_by_id(result["result"]["id"])
    assert scene.chapter == "Chapter 3"


def test_create_scene_missing_title():
    db, proj = _make_project()
    result = execute_action(db, proj.id, {
        "action": "create_scene",
        "args": {},
    })
    assert result["ok"] is False
    assert "Missing required" in result["error"]


def test_update_scene_title():
    db, proj = _make_project()
    s = db.create_scene(proj.id, "Old Title")
    result = execute_action(db, proj.id, {
        "action": "update_scene_title",
        "args": {"scene_id": s.id, "title": "New Title"},
    })
    assert result["ok"] is True
    assert result["result"]["title"] == "New Title"
    updated = db.get_scene_by_id(s.id)
    assert updated.title == "New Title"


def test_update_scene_title_not_found():
    db, proj = _make_project()
    result = execute_action(db, proj.id, {
        "action": "update_scene_title",
        "args": {"scene_id": 99999, "title": "X"},
    })
    assert result["ok"] is False


def test_create_psyke_entry():
    db, proj = _make_project()
    result = execute_action(db, proj.id, {
        "action": "create_psyke_entry",
        "args": {"name": "The Prophecy", "entry_type": "lore"},
    })
    assert result["ok"] is True
    assert result["result"]["name"] == "The Prophecy"
    assert result["result"]["entry_type"] == "lore"
    entries = db.get_all_psyke_entries(proj.id)
    assert any(e.name == "The Prophecy" for e in entries)


def test_create_note():
    db, proj = _make_project()
    result = execute_action(db, proj.id, {
        "action": "create_note",
        "args": {"title": "Brainstorm", "content": "Ideas for Act 3"},
    })
    assert result["ok"] is True
    assert result["result"]["title"] == "Brainstorm"
    note = db.get_note_by_id(result["result"]["id"])
    assert note.content == "Ideas for Act 3"


# =============================================================================
# SAFETY
# =============================================================================

def test_no_delete_action():
    names = list_action_names()
    assert "delete_scene" not in names
    assert "delete_character" not in names
    assert "delete_psyke_entry" not in names
    assert "delete_note" not in names


def test_no_content_overwrite():
    names = list_action_names()
    assert "update_scene_content" not in names
    assert "overwrite_content" not in names


def test_no_raw_db_action():
    names = list_action_names()
    assert "execute_sql" not in names
    assert "raw_query" not in names


# =============================================================================
# STRUCTURED RESPONSE FORMAT
# =============================================================================

def test_success_has_ok_true():
    db, proj = _make_project()
    result = execute_action(db, proj.id, {"action": "get_project"})
    assert "ok" in result
    assert result["ok"] is True
    assert "result" in result


def test_failure_has_ok_false():
    db, proj = _make_project()
    result = execute_action(db, proj.id, {"action": "nonexistent"})
    assert "ok" in result
    assert result["ok"] is False
    assert "error" in result


def test_success_includes_action_name():
    db, proj = _make_project()
    result = execute_action(db, proj.id, {"action": "get_project"})
    assert result["action"] == "get_project"


# =============================================================================
# SETTINGS GATING
# =============================================================================

def test_connector_disabled_blocks_execution():
    db, proj = _make_project()
    mgr = get_settings()
    mgr.set("connector_enabled", False)
    try:
        result = execute_action(db, proj.id, {"action": "get_project"})
        assert result["ok"] is False
        assert "disabled" in result["error"].lower()
    finally:
        mgr.set("connector_enabled", True)


def test_write_action_blocked_when_writes_disallowed():
    db, proj = _make_project()
    mgr = get_settings()
    mgr.set("connector_allow_writes", False)
    try:
        result = execute_action(db, proj.id, {
            "action": "create_note",
            "args": {"title": "Nope", "content": "blocked"},
        })
        assert result["ok"] is False
        assert "write" in result["error"].lower()
    finally:
        mgr.set("connector_allow_writes", True)


def test_read_action_still_works_when_writes_disallowed():
    db, proj = _make_project()
    mgr = get_settings()
    mgr.set("connector_allow_writes", False)
    try:
        result = execute_action(db, proj.id, {"action": "get_project"})
        assert result["ok"] is True
    finally:
        mgr.set("connector_allow_writes", True)


def test_disabled_action_list_blocks_specific_action():
    db, proj = _make_project()
    mgr = get_settings()
    mgr.set("connector_disabled_actions", ["get_project"])
    try:
        result = execute_action(db, proj.id, {"action": "get_project"})
        assert result["ok"] is False
        assert "disabled" in result["error"].lower()
        # other actions still work
        result2 = execute_action(db, proj.id, {"action": "list_scenes"})
        assert result2["ok"] is True
    finally:
        mgr.set("connector_disabled_actions", [])


def test_enforce_settings_false_bypasses_gating():
    db, proj = _make_project()
    mgr = get_settings()
    mgr.set("connector_enabled", False)
    try:
        result = execute_action(
            db, proj.id, {"action": "get_project"},
            enforce_settings=False,
        )
        assert result["ok"] is True
    finally:
        mgr.set("connector_enabled", True)
