"""Tests that the Go McKee plugin operationally influences the Assistant.

Verifies the toggle genuinely changes Assistant context, that PSYKE is
read into Go McKee's craft pressure, and that Go McKee never silently
mutates PSYKE.
"""

import pytest

from logosforge.db import Database
from logosforge.plugin_manager import get_plugin_manager
from logosforge.gomckee_bridge import (
    gather_gomckee_context,
    is_gomckee_enabled,
)
from logosforge.ui.assistant_view import AssistantPanel


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    yield
    settings._instance = None


@pytest.fixture(autouse=True)
def _discovered_plugins():
    mgr = get_plugin_manager()
    mgr.discover()
    yield


def _gomckee_id():
    mgr = get_plugin_manager()
    for p in mgr.plugins:
        if p.id.lower().startswith("gomckee"):
            return p.id
    return None


def _project_with_psyke():
    db = Database()
    proj = db.create_project("P")
    c = db.create_character(proj.id, name="ALICE")
    e1 = db.create_psyke_entry(proj.id, "ALICE", entry_type="character")
    e2 = db.create_psyke_entry(proj.id, "Justice", entry_type="theme")
    db.add_psyke_relation(e1.id, e2.id, relation_type="thematic_echo")
    scene = db.create_scene(
        proj.id, "Opening",
        content="Alice argues with Bob about justice.",
        character_ids=[c.id],
    )
    get_plugin_manager().set_app_context(db, proj.id)
    return db, proj, scene


# =========================================================================
# 1. Plugin discovery + toggle is real (persisted)
# =========================================================================

def test_gomckee_plugin_is_discovered():
    assert _gomckee_id() is not None


def test_toggle_persists_and_gates_enabled_flag():
    gid = _gomckee_id()
    mgr = get_plugin_manager()
    mgr.set_enabled(gid, True)
    assert is_gomckee_enabled() is True
    mgr.set_enabled(gid, False)
    assert is_gomckee_enabled() is False


def test_gomckee_menu_enable_disable_persists():
    # The plugin's own Enable/Disable menu actions must drive the persisted
    # toggle (is_gomckee_enabled), not just a local instance flag.
    gid = _gomckee_id()
    mgr = get_plugin_manager()
    mgr.set_enabled(gid, True)
    info = next(p for p in mgr.plugins if p.id == gid)
    mgr._load_plugin(info)                         # load only Go McKee
    assert not info.error, info.error
    actions = dict(info.menu_actions)
    assert "Go McKee: Disable" in actions and "Go McKee: Enable" in actions

    actions["Go McKee: Disable"]()
    assert is_gomckee_enabled() is False           # menu Disable persisted
    actions["Go McKee: Enable"]()
    assert is_gomckee_enabled() is True            # menu Enable persisted


def test_toggle_survives_manager_reset():
    from logosforge.settings import get_manager
    gid = _gomckee_id()
    get_plugin_manager().set_enabled(gid, False)
    # plugin_states persisted to settings.
    states = get_manager().get("plugin_states")
    assert states.get(gid) is False


# =========================================================================
# 2. Bridge context: ON produces craft constraints, OFF is empty
# =========================================================================

def test_context_present_when_enabled():
    db, proj, scene = _project_with_psyke()
    get_plugin_manager().set_enabled(_gomckee_id(), True)
    ctx = gather_gomckee_context(db, proj.id, scene.id, query_text="flat scene")
    assert ctx.startswith("[Go McKee]")
    assert "craft" in ctx.lower()


def test_context_empty_when_disabled():
    db, proj, scene = _project_with_psyke()
    get_plugin_manager().set_enabled(_gomckee_id(), False)
    ctx = gather_gomckee_context(db, proj.id, scene.id, query_text="flat scene")
    assert ctx == ""


def test_context_lists_active_domains():
    db, proj, scene = _project_with_psyke()
    get_plugin_manager().set_enabled(_gomckee_id(), True)
    ctx = gather_gomckee_context(db, proj.id, scene.id, query_text="x")
    assert "Active craft domains" in ctx


# =========================================================================
# 3. PSYKE is read into Go McKee's pressure
# =========================================================================

def test_psyke_signals_feed_constraints():
    db, proj, scene = _project_with_psyke()
    get_plugin_manager().set_enabled(_gomckee_id(), True)
    ctx = gather_gomckee_context(db, proj.id, scene.id, query_text="x")
    # The DB-derived snapshot (scene + PSYKE relations) drives PSYKE-aware
    # craft constraints.
    assert "PSYKE" in ctx


def test_no_psyke_silent_mutation():
    db, proj, scene = _project_with_psyke()
    before = {(e.name, e.entry_type) for e in db.get_all_psyke_entries(proj.id)}
    get_plugin_manager().set_enabled(_gomckee_id(), True)
    gather_gomckee_context(db, proj.id, scene.id, query_text="x")
    after = {(e.name, e.entry_type) for e in db.get_all_psyke_entries(proj.id)}
    assert before == after  # Go McKee read PSYKE but did not change it.


# =========================================================================
# 4. Assistant context builder reflects the toggle
# =========================================================================

# structural_ctx is index 8 in the _build_context tuple; Go McKee is
# folded into it.
_STRUCT_IDX = 8


def test_assistant_context_changes_with_toggle():
    db, proj, scene = _project_with_psyke()
    panel = AssistantPanel(db, proj.id)
    panel._prompt_input.setPlainText("This scene feels flat.")

    get_plugin_manager().set_enabled(_gomckee_id(), True)
    on_struct = panel._build_context()[_STRUCT_IDX]

    get_plugin_manager().set_enabled(_gomckee_id(), False)
    off_struct = panel._build_context()[_STRUCT_IDX]

    assert "[Go McKee]" in on_struct
    assert "[Go McKee]" not in off_struct
    # The two contexts genuinely differ → behavior changes with the toggle.
    assert on_struct != off_struct


def test_assistant_context_off_by_default_disabled_plugin():
    db, proj, scene = _project_with_psyke()
    get_plugin_manager().set_enabled(_gomckee_id(), False)
    panel = AssistantPanel(db, proj.id)
    panel._prompt_input.setPlainText("Advice please.")
    struct = panel._build_context()[_STRUCT_IDX]
    assert "[Go McKee]" not in struct


# =========================================================================
# 5. Controlling Idea note honors the real toggle
# =========================================================================

def test_controlling_idea_note_follows_toggle():
    from logosforge.controlling_idea import _gomckee_active
    gid = _gomckee_id()
    get_plugin_manager().set_enabled(gid, True)
    assert _gomckee_active() is True
    get_plugin_manager().set_enabled(gid, False)
    assert _gomckee_active() is False
