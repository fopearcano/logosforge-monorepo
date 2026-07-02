"""Tests for project-switch state isolation.

Switching projects must fully reset old caches and the active content
view. These tests pretend to be the user creating/opening a project B
after using project A and assert that nothing from A leaks into B.
"""

from __future__ import annotations

from logosforge.db import Database
from logosforge.project_lifecycle import (
    clear_project_caches,
    register_project_clear_hook,
)


# =========================================================================
# 1. PROJECT_LIFECYCLE HOOKS
# =========================================================================

def test_clear_project_caches_runs_registered_hooks():
    seen: list[int | None] = []

    def hook(pid: int | None) -> None:
        seen.append(pid)

    register_project_clear_hook(hook)
    try:
        clear_project_caches(42)
    finally:
        # Best-effort cleanup — the registry is module-level so this hook
        # would otherwise fire in every other test.
        from logosforge import project_lifecycle as pl
        if hook in pl._CLEAR_HOOKS:
            pl._CLEAR_HOOKS.remove(hook)
    assert 42 in seen


def test_clear_project_caches_tolerates_broken_hook():
    """A broken hook must not strand the switch."""

    def broken(_pid: int | None) -> None:
        raise RuntimeError("boom")

    register_project_clear_hook(broken)
    try:
        clear_project_caches(1)  # must not raise
    finally:
        from logosforge import project_lifecycle as pl
        if broken in pl._CLEAR_HOOKS:
            pl._CLEAR_HOOKS.remove(broken)


def test_clear_project_caches_none_is_safe():
    """First-load case: no previous project to clear."""
    clear_project_caches(None)  # must not raise


# =========================================================================
# 2. QUANTUM STATE ISOLATION
# =========================================================================

def test_quantum_state_cleared_on_project_switch():
    from logosforge.quantum_outliner.state import (
        _STATES,
        get_state,
    )
    # Pretend Project A had quantum state cached.
    _ = get_state(101)
    assert 101 in _STATES
    clear_project_caches(101)
    assert 101 not in _STATES


def test_quantum_state_for_other_projects_preserved():
    """Clearing project A's state must not touch project B's."""
    from logosforge.quantum_outliner.state import (
        _STATES,
        get_state,
        reset_state,
    )
    reset_state(202)
    reset_state(203)
    _ = get_state(202)
    _ = get_state(203)
    clear_project_caches(202)
    assert 202 not in _STATES
    assert 203 in _STATES
    reset_state(203)


# =========================================================================
# 3. PARAGRAPH ENERGY CACHE
# =========================================================================

def test_paragraph_energy_cache_cleared_on_switch():
    from logosforge.paragraph_energy import (
        _cache_put,
        _energy_cache,
        ParagraphEnergy,
    )
    _cache_put("dummy text", ParagraphEnergy(paragraph_id=1, scene_id=1))
    assert _energy_cache
    clear_project_caches(1)
    assert not _energy_cache


# =========================================================================
# 4. LOOKAHEAD CACHE
# =========================================================================

def test_lookahead_cache_invalidated_on_switch():
    from logosforge.quantum_outliner.lookahead_cache import (
        _global_cache,
    )
    _global_cache._cache["fake_key"] = "fake_value"
    clear_project_caches(1)
    assert "fake_key" not in _global_cache._cache


# =========================================================================
# 5. GRAPH STATE IS PROJECT-SCOPED
# =========================================================================

def test_graph_state_key_scoped_to_project():
    from logosforge.ui.focus_graph_view import FocusGraphView
    db = Database()
    p1 = db.create_project("A")
    p2 = db.create_project("B")
    v1 = FocusGraphView(db, p1.id)
    v2 = FocusGraphView(db, p2.id)
    assert v1._graph_state_key() != v2._graph_state_key()
    assert str(p1.id) in v1._graph_state_key()
    assert str(p2.id) in v2._graph_state_key()


def _isolated_settings(tmp_path, monkeypatch):
    """Repoint SettingsManager at a temp file and return a fresh instance."""
    from logosforge import settings as settings_mod
    fake_path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_mod, "SETTINGS_FILE", fake_path)
    monkeypatch.setattr(settings_mod, "_instance", None)
    return settings_mod.get_manager()


def test_graph_state_does_not_leak_across_projects(tmp_path, monkeypatch):
    """Graph filter state saved for project A must not affect project B."""
    mgr = _isolated_settings(tmp_path, monkeypatch)

    from logosforge.ui.focus_graph_view import (
        FocusGraphView,
        MODE_RELATIONSHIP,
        MODE_THEME,
    )

    db = Database()
    p1 = db.create_project("A")
    p2 = db.create_project("B")

    v1 = FocusGraphView(db, p1.id)
    v1.set_mode(MODE_RELATIONSHIP)  # persists graph_state:<p1.id>

    v2 = FocusGraphView(db, p2.id)
    v2.set_mode(MODE_THEME)  # persists graph_state:<p2.id>

    # Project A's saved state still says relationship; B's says theme.
    state_a = mgr.get(f"graph_state:{p1.id}")
    state_b = mgr.get(f"graph_state:{p2.id}")
    assert state_a is not None and state_a.get("mode") == MODE_RELATIONSHIP
    assert state_b is not None and state_b.get("mode") == MODE_THEME


def test_graph_presets_scoped_per_project(tmp_path, monkeypatch):
    _isolated_settings(tmp_path, monkeypatch)

    from logosforge.ui.focus_graph_view import FocusGraphView

    db = Database()
    p1 = db.create_project("A")
    p2 = db.create_project("B")

    v1 = FocusGraphView(db, p1.id)
    v1.save_preset("PresetA")

    v2 = FocusGraphView(db, p2.id)
    # B's preset list must not include A's preset.
    assert "PresetA" not in v2.get_saved_presets()


# =========================================================================
# 6. MAIN WINDOW: VIEW REBUILDS ON SWITCH
# =========================================================================

def test_switch_project_rebuilds_active_view():
    """The visible content widget must reflect the new project_id."""
    from logosforge.ui.main_window import MainWindow

    db = Database()
    p1 = db.create_project("Project A")
    p2 = db.create_project("Project B")

    win = MainWindow(db, p1.id)
    # Navigate to Plot to put a project-A view on screen.
    win._set_active_section("Plot")
    win._show_plot()
    plot_a = win.content_area
    assert plot_a._project_id == p1.id

    # Switch to project B without forcing a section change.
    win._switch_project(p2.id)
    plot_b = win.content_area
    # New view instance, pointing at project B.
    assert plot_b is not plot_a
    assert plot_b._project_id == p2.id
    win.close()


def test_switch_project_keeps_user_on_current_section():
    """If the user was on Manuscript, switching projects keeps them on
    Manuscript (not silently dragged to Dashboard)."""
    from logosforge.ui.main_window import MainWindow

    db = Database()
    p1 = db.create_project("A")
    p2 = db.create_project("B")

    win = MainWindow(db, p1.id)
    win._set_active_section("Manuscript")
    win._show_manuscript()
    assert win._current_section == "Manuscript"

    win._switch_project(p2.id)
    assert win._current_section == "Manuscript"
    # And the content widget should be a fresh Manuscript bound to B.
    assert win.content_area._project_id == p2.id
    win.close()


def test_switch_project_clears_quantum_state_for_old_id():
    from logosforge.ui.main_window import MainWindow
    from logosforge.quantum_outliner.state import (
        _STATES,
        get_state,
    )

    db = Database()
    p1 = db.create_project("A")
    p2 = db.create_project("B")

    win = MainWindow(db, p1.id)
    _ = get_state(p1.id)
    assert p1.id in _STATES

    win._switch_project(p2.id)
    assert p1.id not in _STATES
    win.close()


def test_switch_project_clears_paragraph_energy_cache():
    from logosforge.ui.main_window import MainWindow
    from logosforge.paragraph_energy import (
        _cache_put,
        _energy_cache,
        ParagraphEnergy,
    )

    db = Database()
    p1 = db.create_project("A")
    p2 = db.create_project("B")

    win = MainWindow(db, p1.id)
    _cache_put("snippet", ParagraphEnergy(paragraph_id=2, scene_id=2))
    assert _energy_cache

    win._switch_project(p2.id)
    assert not _energy_cache
    win.close()


def test_switch_project_resets_cached_scenes_view():
    from logosforge.ui.main_window import MainWindow

    db = Database()
    p1 = db.create_project("A")
    p2 = db.create_project("B")

    win = MainWindow(db, p1.id)
    win._show_scenes()
    cached = win._cached_scenes_view
    assert cached is not None

    win._switch_project(p2.id)
    # Old ScenesView instance must not be reused for project B.
    assert win._cached_scenes_view is not cached
    win.close()


def test_switch_project_drops_assistant_pending_messages():
    from logosforge.ui.main_window import MainWindow

    db = Database()
    p1 = db.create_project("A")
    p2 = db.create_project("B")

    win = MainWindow(db, p1.id)
    win._assistant_panel._pending_messages = [{"role": "user", "content": "old"}]
    win._switch_project(p2.id)
    assert win._assistant_panel._pending_messages is None
    win.close()


def test_switch_project_updates_subsystems():
    from logosforge.ui.main_window import MainWindow

    db = Database()
    p1 = db.create_project("A")
    p2 = db.create_project("B")

    win = MainWindow(db, p1.id)
    win._switch_project(p2.id)
    assert win._project_id == p2.id
    assert win._autosave._project_id == p2.id
    assert win._versions._project_id == p2.id
    assert win._assistant_panel._project_id == p2.id
    assert win._psyke_console._project_id == p2.id
    win.close()


# =========================================================================
# 7. NEW PROJECT INHERITS FRESH STATE
# =========================================================================

def test_new_project_then_switch_back_starts_fresh():
    """After creating B and returning to A via switch, A's state is
    rebuilt from the DB rather than reused from stale in-memory caches."""
    from logosforge.ui.main_window import MainWindow
    from logosforge.quantum_outliner.state import get_state

    db = Database()
    p1 = db.create_project("A")
    p2 = db.create_project("B")

    win = MainWindow(db, p1.id)
    state_a_first = get_state(p1.id)
    win._switch_project(p2.id)
    win._switch_project(p1.id)
    state_a_after = get_state(p1.id)
    # Returning to A produced a fresh NarrativeState instance.
    assert state_a_first is not state_a_after
    win.close()
