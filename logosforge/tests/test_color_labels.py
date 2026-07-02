"""Tests for shared scene color labels in Plot and Timeline."""

import json

import pytest

from logosforge.db import Database
from logosforge.export import export_json
from logosforge.import_data import import_json, validate_import_data
from logosforge.ui import color_labels
from logosforge.ui.color_labels import (
    COLOR_LABELS,
    build_color_menu,
    color_hex,
    is_valid_label,
)
from logosforge.ui.multi_plot_view import MultiPlotView, _TimelineStrip
from logosforge.ui.story_grid_view import StoryGridView
from logosforge.ui.timeline_view import TimelineView


def _setup():
    db = Database()
    proj = db.create_project("Test")
    return db, proj


# ==========================================================================
# 1. Palette helper
# ==========================================================================

def test_palette_includes_default_and_named_colors():
    assert "" in COLOR_LABELS
    for key in ("red", "orange", "amber", "yellow",
                "green", "teal", "blue", "purple", "gray"):
        assert key in COLOR_LABELS


def test_color_hex_returns_none_for_default():
    assert color_hex("") is None
    assert color_hex(None) is None


def test_color_hex_returns_value_for_known_keys():
    for key in COLOR_LABELS:
        if key:
            assert color_hex(key) is not None
            assert color_hex(key).startswith("#")


def test_is_valid_label_accepts_palette_and_empty():
    for key in COLOR_LABELS:
        assert is_valid_label(key)
    assert is_valid_label("") is True
    assert is_valid_label(None) is True


def test_is_valid_label_rejects_unknown():
    assert is_valid_label("rainbow") is False


def test_build_color_menu_creates_submenu():
    from PySide6.QtWidgets import QMenu
    parent = QMenu()
    captured = []
    sub = build_color_menu(parent, "red", lambda key: captured.append(key))
    assert sub.title() == "Color"
    # Action count equals palette size
    assert len(sub.actions()) == len(COLOR_LABELS)
    # Triggering the first action ("None") invokes callback with ""
    sub.actions()[0].trigger()
    assert captured == [""]


# ==========================================================================
# 2. Scene.color_label persistence
# ==========================================================================

def test_create_scene_has_default_empty_color():
    db, proj = _setup()
    scene = db.create_scene(proj.id, "S1", content="x")
    assert scene.color_label == ""


def test_create_scene_accepts_color_label():
    db, proj = _setup()
    scene = db.create_scene(proj.id, "S1", color_label="red")
    stored = db.get_scene_by_id(scene.id)
    assert stored.color_label == "red"


def test_update_scene_color():
    db, proj = _setup()
    scene = db.create_scene(proj.id, "S1")
    db.update_scene_color(scene.id, "blue")
    assert db.get_scene_by_id(scene.id).color_label == "blue"


def test_update_scene_color_to_empty_clears_it():
    db, proj = _setup()
    scene = db.create_scene(proj.id, "S1", color_label="purple")
    db.update_scene_color(scene.id, "")
    assert db.get_scene_by_id(scene.id).color_label == ""


def test_update_scene_preserves_color_when_not_passed():
    """update_scene() without color_label kwarg must not overwrite color."""
    db, proj = _setup()
    scene = db.create_scene(proj.id, "S1", color_label="green")
    db.update_scene(
        scene_id=scene.id, title="S1-renamed",
        summary="", synopsis="", goal="", conflict="", outcome="",
        beat="", tags="", act="", content="", chapter="", plotline="",
    )
    assert db.get_scene_by_id(scene.id).color_label == "green"


def test_update_scene_with_explicit_color_overrides():
    db, proj = _setup()
    scene = db.create_scene(proj.id, "S1", color_label="green")
    db.update_scene(
        scene_id=scene.id, title="S1",
        summary="", synopsis="", goal="", conflict="", outcome="",
        beat="", tags="", act="", content="", chapter="", plotline="",
        color_label="amber",
    )
    assert db.get_scene_by_id(scene.id).color_label == "amber"


# ==========================================================================
# 3. Plot ↔ Timeline color sharing (same scene)
# ==========================================================================

def test_plot_set_color_visible_in_timeline():
    db, proj = _setup()
    scene = db.create_scene(proj.id, "Shared", content="x")
    plot = StoryGridView(db, proj.id)
    plot._set_color(scene.id, "blue")

    timeline = TimelineView(db, proj.id)
    timeline.refresh()
    # Color value flows through DB
    assert db.get_scene_by_id(scene.id).color_label == "blue"
    # Plot reads the same
    plot.refresh()
    assert db.get_scene_by_id(scene.id).color_label == "blue"


def test_timeline_set_color_visible_in_plot():
    db, proj = _setup()
    scene = db.create_scene(proj.id, "Shared", content="x")
    timeline = TimelineView(db, proj.id)
    timeline._set_scene_color(scene.id, "purple")

    plot = StoryGridView(db, proj.id)
    plot.refresh()
    assert db.get_scene_by_id(scene.id).color_label == "purple"


def test_multi_plot_view_set_color_reaches_db():
    db, proj = _setup()
    scene = db.create_scene(proj.id, "Shared", content="x")
    strip = _TimelineStrip(db, proj.id)
    strip._set_color(scene.id, "teal")
    assert db.get_scene_by_id(scene.id).color_label == "teal"


# ==========================================================================
# 4. Reload — color survives export/import
# ==========================================================================

def test_color_persists_across_export_import():
    db, proj = _setup()
    scene = db.create_scene(proj.id, "S1", color_label="red")

    raw = export_json(db, proj.id)
    data, _ = validate_import_data(raw)

    db2 = Database()
    new_id = import_json(db2, data)
    scenes = db2.get_all_scenes(new_id)
    assert len(scenes) == 1
    assert scenes[0].color_label == "red"


def test_color_field_in_export_json():
    db, proj = _setup()
    db.create_scene(proj.id, "S1", color_label="amber")
    raw = export_json(db, proj.id)
    obj = json.loads(raw)
    assert obj["scenes"][0]["color_label"] == "amber"


# ==========================================================================
# 5. New project doesn't leak old colors
# ==========================================================================

def test_new_project_has_no_color_leak():
    db, proj1 = _setup()
    db.create_scene(proj1.id, "Old", color_label="purple")

    proj2 = db.create_project("New")
    scenes = db.get_all_scenes(proj2.id)
    assert scenes == []

    new_scene = db.create_scene(proj2.id, "Fresh")
    assert new_scene.color_label == ""


# ==========================================================================
# 6. Migration adds column to legacy DBs
# ==========================================================================

def test_migration_adds_color_column_to_legacy_db(tmp_path):
    """A pre-existing scene table without color_label gets the column added."""
    import sqlite3
    db_path = tmp_path / "legacy.db"

    # Build a minimal legacy schema by hand — no color_label column on scene.
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE project (
            id INTEGER PRIMARY KEY, title TEXT, created_at TEXT,
            format_mode TEXT DEFAULT 'novel', settings_json TEXT DEFAULT ''
        );
        CREATE TABLE scene (
            id INTEGER PRIMARY KEY, project_id INTEGER, title TEXT,
            summary TEXT DEFAULT '', synopsis TEXT DEFAULT '',
            goal TEXT DEFAULT '', conflict TEXT DEFAULT '', outcome TEXT DEFAULT '',
            beat TEXT DEFAULT '', tags TEXT DEFAULT '', act TEXT DEFAULT '',
            content TEXT DEFAULT '', chapter TEXT DEFAULT '', plotline TEXT DEFAULT '',
            sort_order INTEGER DEFAULT 0, created_at TEXT
        );
        INSERT INTO project (id, title, created_at)
            VALUES (1, 'Legacy', '2024-01-01T00:00:00');
        INSERT INTO scene (id, project_id, title, created_at)
            VALUES (1, 1, 'Old Scene', '2024-01-01T00:00:00');
    """)
    conn.commit()
    conn.close()

    db = Database(str(db_path))
    scene = db.get_scene_by_id(1)
    assert scene is not None
    assert scene.color_label == ""
    db.update_scene_color(1, "green")
    assert db.get_scene_by_id(1).color_label == "green"


# ==========================================================================
# 7. Card visual marker respects color
# ==========================================================================

def test_plot_card_with_color_has_styled_border():
    db, proj = _setup()
    scene = db.create_scene(proj.id, "S1", color_label="red")
    strip = _TimelineStrip(db, proj.id)
    strip.refresh()
    cards = strip._cards
    assert len(cards) == 1
    style = cards[0].styleSheet()
    # Should contain the user color hex as a left border
    assert "border-left" in style
    assert color_hex("red") in style


def test_plot_card_without_color_has_no_user_border():
    db, proj = _setup()
    db.create_scene(proj.id, "S1")
    strip = _TimelineStrip(db, proj.id)
    strip.refresh()
    cards = strip._cards
    assert len(cards) == 1
    # No user color → no inline stylesheet from the color helper
    assert cards[0].styleSheet() == ""


def test_timeline_card_with_color_has_styled_border():
    db, proj = _setup()
    db.create_scene(proj.id, "S1", color_label="blue")
    timeline = TimelineView(db, proj.id)
    timeline.refresh()
    # Find the card by walking the table
    found_color = False
    for row in range(timeline._table.rowCount()):
        for col in range(timeline._table.columnCount()):
            w = timeline._table.cellWidget(row, col)
            if w is not None and color_hex("blue") in w.styleSheet():
                found_color = True
    assert found_color
