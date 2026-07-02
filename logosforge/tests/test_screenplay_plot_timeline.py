"""Tests for screenplay-aware Plot and Timeline integration."""

from __future__ import annotations

from logosforge.db import Database
from logosforge.ui.story_grid_view import StoryGridView, _SceneCard


# =========================================================================
# Helpers
# =========================================================================

def _make_screenplay_project(db: Database):
    return db.create_project("Film Noir", format_mode="screenplay")


def _make_screenplay_scenes(db: Database, project_id: int):
    """Create a set of screenplay scenes with cinematic metadata."""
    s1 = db.create_scene(
        project_id,
        title="INT. APARTMENT - NIGHT",
        act="Act 1",
        location="Apartment",
        interior_exterior="INT",
        time_of_day="NIGHT",
        estimated_duration_minutes=3,
        dramatic_turn="From safety to threat",
        cinematic_pacing="slow",
        setup_payoff_links="gun on table → Act 3 confrontation",
    )
    s2 = db.create_scene(
        project_id,
        title="EXT. ROOFTOP - DAY",
        act="Act 1",
        location="Rooftop",
        interior_exterior="EXT",
        time_of_day="DAY",
        estimated_duration_minutes=2,
        emotional_turn="From hope to despair",
        cinematic_pacing="fast",
        montage_group="chase sequence",
    )
    s3 = db.create_scene(
        project_id,
        title="INT. INTERROGATION - NIGHT",
        act="Act 2",
        location="Police Station",
        interior_exterior="INT",
        time_of_day="NIGHT",
        estimated_duration_minutes=5,
        dramatic_turn="Confession",
        cinematic_pacing="medium",
        visible_conflict="Detective vs suspect",
    )
    return s1, s2, s3


# =========================================================================
# 1. PLOT GRID — screenplay blocks
# =========================================================================

def test_grid_screenplay_mode_detected():
    db = Database()
    proj = _make_screenplay_project(db)
    view = StoryGridView(db, proj.id)
    assert view.get_format_mode() == "screenplay"


def test_grid_screenplay_block_label():
    db = Database()
    proj = _make_screenplay_project(db)
    view = StoryGridView(db, proj.id)
    assert view._block_unit == "scene"
    assert view._block_number_label(1) == "Scene 1"


def test_grid_screenplay_has_extra_color_modes():
    db = Database()
    proj = _make_screenplay_project(db)
    view = StoryGridView(db, proj.id)
    items = [view._color_combo.itemText(i) for i in range(view._color_combo.count())]
    assert "Pacing" in items
    assert "Continuity" in items


def test_grid_novel_lacks_screenplay_color_modes():
    db = Database()
    proj = db.create_project("Novel", format_mode="novel")
    view = StoryGridView(db, proj.id)
    items = [view._color_combo.itemText(i) for i in range(view._color_combo.count())]
    assert "Pacing" not in items
    assert "Continuity" not in items


def test_grid_screenplay_has_location_grouping():
    db = Database()
    proj = _make_screenplay_project(db)
    view = StoryGridView(db, proj.id)
    items = [view._group_combo.itemText(i) for i in range(view._group_combo.count())]
    assert "By Location" in items


def test_grid_group_by_location():
    db = Database()
    proj = _make_screenplay_project(db)
    _make_screenplay_scenes(db, proj.id)
    view = StoryGridView(db, proj.id)
    # Switch to "By Location" (index 2 in screenplay mode)
    view._group_combo.setCurrentIndex(2)
    assert view.get_group_by() == "location"
    # Should have 3 locations: Apartment, Rooftop, Police Station
    assert view.column_count() == 3


def test_grid_screenplay_card_shows_duration():
    db = Database()
    proj = _make_screenplay_project(db)
    s1, _, _ = _make_screenplay_scenes(db, proj.id)
    scene = db.get_scene_by_id(s1.id)
    card = _SceneCard(scene, zoom=2, screenplay_mode=True)
    assert "3m" in card._screenplay_label.text()


def test_grid_screenplay_card_shows_location():
    db = Database()
    proj = _make_screenplay_project(db)
    s1, _, _ = _make_screenplay_scenes(db, proj.id)
    scene = db.get_scene_by_id(s1.id)
    card = _SceneCard(scene, zoom=2, screenplay_mode=True)
    assert "Apartment" in card._screenplay_label.text()


def test_grid_screenplay_card_shows_int_ext_tod():
    db = Database()
    proj = _make_screenplay_project(db)
    s1, _, _ = _make_screenplay_scenes(db, proj.id)
    scene = db.get_scene_by_id(s1.id)
    card = _SceneCard(scene, zoom=2, screenplay_mode=True)
    text = card._screenplay_label.text()
    assert "INT" in text
    assert "NIGHT" in text


def test_grid_screenplay_card_shows_dramatic_turn():
    db = Database()
    proj = _make_screenplay_project(db)
    s1, _, _ = _make_screenplay_scenes(db, proj.id)
    scene = db.get_scene_by_id(s1.id)
    card = _SceneCard(scene, zoom=2, screenplay_mode=True)
    assert "safety to threat" in card._turn_label.text()


def test_grid_screenplay_card_shows_setup_payoff_marker():
    db = Database()
    proj = _make_screenplay_project(db)
    s1, _, _ = _make_screenplay_scenes(db, proj.id)
    scene = db.get_scene_by_id(s1.id)
    card = _SceneCard(scene, zoom=2, screenplay_mode=True)
    assert "⚓" in card._turn_label.text()


def test_grid_novel_card_has_no_screenplay_data():
    db = Database()
    proj = db.create_project("Novel", format_mode="novel")
    scene = db.create_scene(proj.id, "Chapter 1", content="Once upon a time.")
    card = _SceneCard(scene, zoom=2, screenplay_mode=False)
    assert card._screenplay_label.text() == ""
    assert card._turn_label.text() == ""


# =========================================================================
# 2. DURATION DISPLAY
# =========================================================================

def test_duration_displayed_on_card():
    db = Database()
    proj = _make_screenplay_project(db)
    scene = db.create_scene(
        proj.id, "Quick shot", estimated_duration_minutes=1,
    )
    card = _SceneCard(db.get_scene_by_id(scene.id), zoom=2, screenplay_mode=True)
    assert "1m" in card._screenplay_label.text()


def test_zero_duration_not_displayed():
    db = Database()
    proj = _make_screenplay_project(db)
    scene = db.create_scene(proj.id, "No duration")
    card = _SceneCard(db.get_scene_by_id(scene.id), zoom=2, screenplay_mode=True)
    # No duration → empty or no "0m"
    assert "0m" not in card._screenplay_label.text()


# =========================================================================
# 3. TIMELINE CONTINUITY — pacing and continuity color maps
# =========================================================================

def test_pacing_color_map():
    db = Database()
    proj = _make_screenplay_project(db)
    s1, s2, s3 = _make_screenplay_scenes(db, proj.id)
    view = StoryGridView(db, proj.id)
    scenes = db.get_all_scenes(proj.id)
    view._color_mode = "pacing"
    color_map = view._build_color_map(scenes)
    # s1=slow→blue, s2=fast→red, s3=medium→amber
    assert color_map.get(s1.id) == "#60a5fa"  # blue
    assert color_map.get(s2.id) == "#f87171"  # red
    assert color_map.get(s3.id) == "#facc15"  # amber


def test_continuity_color_map_tracked():
    db = Database()
    proj = _make_screenplay_project(db)
    s1, _, _ = _make_screenplay_scenes(db, proj.id)
    char = db.create_character(proj.id, name="DETECTIVE")
    db.create_scene(proj.id, "Extra", character_ids=[char.id])
    db.add_memory(proj.id, s1.id, "continuity_wound", "DETECTIVE", "bruised knuckles")
    view = StoryGridView(db, proj.id)
    scenes = db.get_all_scenes(proj.id)
    view._color_mode = "continuity"
    color_map = view._build_color_map(scenes)
    assert color_map.get(s1.id) == "#4ade80"  # green — tracked


def test_continuity_color_map_untracked_with_characters():
    db = Database()
    proj = _make_screenplay_project(db)
    char = db.create_character(proj.id, name="HERO")
    scene = db.create_scene(proj.id, "Untracked", character_ids=[char.id])
    view = StoryGridView(db, proj.id)
    scenes = db.get_all_scenes(proj.id)
    view._color_mode = "continuity"
    color_map = view._build_color_map(scenes)
    assert color_map.get(scene.id) == "#f87171"  # red — characters but no continuity


# =========================================================================
# 4. SETUP/PAYOFF LINKING
# =========================================================================

def test_setup_payoff_on_card_tooltip():
    db = Database()
    proj = _make_screenplay_project(db)
    scene = db.create_scene(
        proj.id, "Setup Scene",
        setup_payoff_links="gun on table → Act 3",
    )
    card = _SceneCard(db.get_scene_by_id(scene.id), zoom=2, screenplay_mode=True)
    assert "gun on table" in card._turn_label.toolTip()


def test_setup_payoff_marker_present():
    db = Database()
    proj = _make_screenplay_project(db)
    scene = db.create_scene(
        proj.id, "Payoff Scene",
        setup_payoff_links="photo reveal",
    )
    card = _SceneCard(db.get_scene_by_id(scene.id), zoom=2, screenplay_mode=True)
    assert "⚓" in card._turn_label.text()


def test_no_setup_payoff_no_marker():
    db = Database()
    proj = _make_screenplay_project(db)
    scene = db.create_scene(proj.id, "Plain Scene")
    card = _SceneCard(db.get_scene_by_id(scene.id), zoom=2, screenplay_mode=True)
    assert "⚓" not in card._turn_label.text()


# =========================================================================
# 5. ZOOM LEVELS with screenplay data
# =========================================================================

def test_zoom_0_hides_screenplay_data():
    db = Database()
    proj = _make_screenplay_project(db)
    s1, _, _ = _make_screenplay_scenes(db, proj.id)
    scene = db.get_scene_by_id(s1.id)
    card = _SceneCard(scene, zoom=0, screenplay_mode=True)
    assert not card._screenplay_label.isVisible()
    assert not card._turn_label.isVisible()


def test_zoom_1_shows_screenplay_meta():
    db = Database()
    proj = _make_screenplay_project(db)
    s1, _, _ = _make_screenplay_scenes(db, proj.id)
    scene = db.get_scene_by_id(s1.id)
    card = _SceneCard(scene, zoom=1, screenplay_mode=True)
    # isVisibleTo(card) checks the widget's own visibility flag, not the parent chain
    assert card._screenplay_label.isVisibleTo(card)


def test_zoom_2_shows_all_screenplay_data():
    db = Database()
    proj = _make_screenplay_project(db)
    s1, _, _ = _make_screenplay_scenes(db, proj.id)
    scene = db.get_scene_by_id(s1.id)
    card = _SceneCard(scene, zoom=2, screenplay_mode=True)
    assert card._screenplay_label.isVisibleTo(card)
    assert card._turn_label.isVisibleTo(card)
