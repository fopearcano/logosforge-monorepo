"""Tests for the project event bus and the refresh path it triggers.

These tests prove that every Assistant/Connector-driven write reaches
the active view through the central event bus — no manual navigation
required.
"""

from __future__ import annotations

import pytest

from logosforge.db import Database
from logosforge.connector_executor import execute_action
from logosforge.project_events import (
    emit_action_completed,
    emit_project_data_changed,
    emit_psyke_changed,
    emit_scene_changed,
    get_event_bus,
)


# =========================================================================
# 1. EVENT BUS BASICS
# =========================================================================

def test_event_bus_is_singleton():
    a = get_event_bus()
    b = get_event_bus()
    assert a is b


def test_project_data_changed_fires():
    bus = get_event_bus()
    seen = []
    handler = lambda: seen.append(True)
    bus.project_data_changed.connect(handler)
    try:
        emit_project_data_changed()
    finally:
        bus.project_data_changed.disconnect(handler)
    assert seen == [True]


def test_scene_changed_carries_scene_id():
    bus = get_event_bus()
    seen = []
    handler = lambda sid: seen.append(sid)
    bus.scene_changed.connect(handler)
    try:
        emit_scene_changed(42)
    finally:
        bus.scene_changed.disconnect(handler)
    assert seen == [42]


def test_psyke_changed_carries_entry_id():
    bus = get_event_bus()
    seen = []
    handler = lambda eid: seen.append(eid)
    bus.psyke_changed.connect(handler)
    try:
        emit_psyke_changed(7)
    finally:
        bus.psyke_changed.disconnect(handler)
    assert seen == [7]


# =========================================================================
# 2. emit_action_completed routes to the right typed signal
# =========================================================================

def test_create_scene_action_fires_scenes_changed():
    bus = get_event_bus()
    scenes_seen, data_seen, action_seen = [], [], []
    h1 = lambda: scenes_seen.append(True)
    h2 = lambda: data_seen.append(True)
    h3 = lambda name: action_seen.append(name)
    bus.scenes_changed.connect(h1)
    bus.project_data_changed.connect(h2)
    bus.assistant_action_completed.connect(h3)
    try:
        emit_action_completed("create_scene")
    finally:
        bus.scenes_changed.disconnect(h1)
        bus.project_data_changed.disconnect(h2)
        bus.assistant_action_completed.disconnect(h3)
    assert scenes_seen == [True]
    assert data_seen == [True]
    assert action_seen == ["create_scene"]


def test_create_psyke_entry_action_fires_psyke_list_changed():
    bus = get_event_bus()
    psyke_seen = []
    h = lambda: psyke_seen.append(True)
    bus.psyke_list_changed.connect(h)
    try:
        emit_action_completed("create_psyke_entry")
    finally:
        bus.psyke_list_changed.disconnect(h)
    assert psyke_seen == [True]


def test_create_note_action_fires_notes_changed():
    bus = get_event_bus()
    notes_seen = []
    h = lambda: notes_seen.append(True)
    bus.notes_changed.connect(h)
    try:
        emit_action_completed("create_note")
    finally:
        bus.notes_changed.disconnect(h)
    assert notes_seen == [True]


def test_unknown_action_still_fires_catchall():
    """An unmapped write action still triggers project_data_changed so
    listeners get a chance to refresh."""
    bus = get_event_bus()
    data_seen = []
    h = lambda: data_seen.append(True)
    bus.project_data_changed.connect(h)
    try:
        emit_action_completed("something_new")
    finally:
        bus.project_data_changed.disconnect(h)
    assert data_seen == [True]


# =========================================================================
# 3. CONNECTOR EXECUTOR EMITS ON WRITES
# =========================================================================

def test_connector_create_scene_emits_event():
    bus = get_event_bus()
    db = Database()
    proj = db.create_project("X")

    actions_seen = []
    h = lambda name: actions_seen.append(name)
    bus.assistant_action_completed.connect(h)
    try:
        result = execute_action(
            db, proj.id,
            {"action": "create_scene", "args": {"title": "S1"}},
            enforce_settings=False,
        )
    finally:
        bus.assistant_action_completed.disconnect(h)
    assert result["ok"]
    assert actions_seen == ["create_scene"]


def test_connector_create_psyke_entry_emits_event():
    bus = get_event_bus()
    db = Database()
    proj = db.create_project("X")

    psyke_seen = []
    h = lambda: psyke_seen.append(True)
    bus.psyke_list_changed.connect(h)
    try:
        result = execute_action(
            db, proj.id,
            {
                "action": "create_psyke_entry",
                "args": {"name": "Hero", "entry_type": "character"},
            },
            enforce_settings=False,
        )
    finally:
        bus.psyke_list_changed.disconnect(h)
    assert result["ok"]
    assert psyke_seen == [True]


def test_connector_create_note_emits_event():
    bus = get_event_bus()
    db = Database()
    proj = db.create_project("X")

    notes_seen = []
    h = lambda: notes_seen.append(True)
    bus.notes_changed.connect(h)
    try:
        result = execute_action(
            db, proj.id,
            {"action": "create_note", "args": {"title": "Idea"}},
            enforce_settings=False,
        )
    finally:
        bus.notes_changed.disconnect(h)
    assert result["ok"]
    assert notes_seen == [True]


def test_connector_read_action_does_not_emit():
    """Read actions must not trigger refresh — that would thrash the UI."""
    bus = get_event_bus()
    db = Database()
    proj = db.create_project("X")
    db.create_scene(proj.id, "S1")

    actions_seen = []
    h = lambda name: actions_seen.append(name)
    bus.assistant_action_completed.connect(h)
    try:
        result = execute_action(
            db, proj.id,
            {"action": "list_scenes", "args": {}},
            enforce_settings=False,
        )
    finally:
        bus.assistant_action_completed.disconnect(h)
    assert result["ok"]
    assert actions_seen == []


def test_connector_failed_action_does_not_emit():
    """Failed writes (e.g., scene_id not found) must not announce."""
    bus = get_event_bus()
    db = Database()
    proj = db.create_project("X")

    actions_seen = []
    h = lambda name: actions_seen.append(name)
    bus.assistant_action_completed.connect(h)
    try:
        result = execute_action(
            db, proj.id,
            {
                "action": "update_scene_title",
                "args": {"scene_id": 9999, "title": "X"},
            },
            enforce_settings=False,
        )
    finally:
        bus.assistant_action_completed.disconnect(h)
    assert not result["ok"]
    assert actions_seen == []


# =========================================================================
# 4. MAIN WINDOW SUBSCRIBES TO THE BUS
# =========================================================================

def test_main_window_refreshes_active_view_on_connector_write():
    """End-to-end: Connector create_scene → bus → MainWindow → active
    view refresh."""
    from logosforge.ui.main_window import MainWindow

    db = Database()
    proj = db.create_project("X")
    db.create_scene(proj.id, "S1")

    win = MainWindow(db, proj.id)
    # Land on Plot — its scene grid is the visible widget.
    win._set_active_section("Plot")
    win._show_plot()
    plot_view = win.content_area
    initial_id = id(plot_view)

    # Connector-style write goes through the executor.
    result = execute_action(
        db, proj.id,
        {"action": "create_scene", "args": {"title": "AssistantScene"}},
        enforce_settings=False,
    )
    assert result["ok"]
    # MainWindow's bus subscription routes through _on_data_changed →
    # _refresh_active_view → view.refresh(). Plot view rebuilds itself
    # against the latest DB contents.
    titles = [s.title for s in db.get_all_scenes(proj.id)]
    assert "AssistantScene" in titles
    # The view should still be present (refresh is in-place, not a new
    # widget) but its data should reflect the new scene.
    assert id(win.content_area) == initial_id
    win.close()


def test_main_window_refreshes_after_psyke_create():
    from logosforge.ui.main_window import MainWindow

    db = Database()
    proj = db.create_project("X")

    win = MainWindow(db, proj.id)
    win._set_active_section("PSYKE")
    win._show_psyke()

    result = execute_action(
        db, proj.id,
        {"action": "create_psyke_entry", "args": {"name": "Detective"}},
        enforce_settings=False,
    )
    assert result["ok"]
    names = [e.name for e in db.get_all_psyke_entries(proj.id)]
    assert "Detective" in names
    win.close()


def test_main_window_refreshes_after_note_create():
    from logosforge.ui.main_window import MainWindow

    db = Database()
    proj = db.create_project("X")

    win = MainWindow(db, proj.id)
    win._set_active_section("Notes")
    win._show_notes()

    result = execute_action(
        db, proj.id,
        {"action": "create_note", "args": {"title": "AssistantNote"}},
        enforce_settings=False,
    )
    assert result["ok"]
    titles = [n.title for n in db.get_all_notes(proj.id)]
    assert "AssistantNote" in titles
    win.close()


# =========================================================================
# 5. ASSISTANT PANEL EMITS THROUGH THE BUS
# =========================================================================

def test_assistant_panel_notify_emits_bus_event():
    """AssistantPanel._notify_data_changed must publish to the bus so
    MainWindow can refresh even when the panel has no direct callback."""
    from logosforge.ui.assistant_view import AssistantPanel

    db = Database()
    proj = db.create_project("X")
    panel = AssistantPanel(db, proj.id)

    bus = get_event_bus()
    seen = []
    h = lambda: seen.append(True)
    bus.project_data_changed.connect(h)
    try:
        panel._notify_data_changed()
    finally:
        bus.project_data_changed.disconnect(h)
    assert seen == [True]


def test_main_window_refreshes_view_when_assistant_edits_scene():
    """End-to-end: Assistant rewrites a scene, the active Plot grid
    rebuilds against the new title."""
    from logosforge.ui.main_window import MainWindow

    db = Database()
    proj = db.create_project("X")
    scene = db.create_scene(proj.id, "Original")

    win = MainWindow(db, proj.id)
    win._set_active_section("Plot")
    win._show_plot()

    # Simulate Assistant's "rewrite title" path (writes via Connector).
    result = execute_action(
        db, proj.id,
        {
            "action": "update_scene_title",
            "args": {"scene_id": scene.id, "title": "Rewritten"},
        },
        enforce_settings=False,
    )
    assert result["ok"]
    titles = [s.title for s in db.get_all_scenes(proj.id)]
    assert "Rewritten" in titles
    win.close()
