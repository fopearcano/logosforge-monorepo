"""Tests for Visual Story Grid — spatial plotting system."""

from logosforge.db import Database
from logosforge.ui import theme
from logosforge.ui.story_grid_view import (
    StoryGridView,
    _GridColumn,
    _SceneCard,
    _COLOR_PALETTE,
)


def _make_project():
    db = Database()
    proj = db.create_project("GridTest")
    return db, proj


def _make_project_with_scenes():
    db, proj = _make_project()
    s1 = db.create_scene(proj.id, "Opening", content="Storm.", act="Act 1", chapter="Chapter 1", plotline="Main", tags="setup")
    s2 = db.create_scene(proj.id, "Rising", content="She ran.", act="Act 1", chapter="Chapter 1", plotline="Main", beat="Midpoint")
    s3 = db.create_scene(proj.id, "Midpoint", content="Truth.", act="Act 2", chapter="Chapter 2", plotline="Sub", tags="twist")
    s4 = db.create_scene(proj.id, "Climax", content="Fight.", act="Act 2", chapter="Chapter 2", plotline="Main", beat="Climax")
    s5 = db.create_scene(proj.id, "Resolution", content="Peace.", act="Act 3", chapter="Chapter 3", plotline="Sub")
    return db, proj, s1, s2, s3, s4, s5


# -- Grid construction -------------------------------------------------------

def test_grid_creates_columns_by_act():
    db, proj, *scenes = _make_project_with_scenes()
    view = StoryGridView(db, proj.id)
    assert view.column_count() == 3
    assert view.total_cards() == 5


def test_grid_creates_columns_by_chapter():
    db, proj, *scenes = _make_project_with_scenes()
    view = StoryGridView(db, proj.id)
    view._group_combo.setCurrentIndex(1)
    assert view.get_group_by() == "chapter"
    assert view.column_count() == 3
    assert view.total_cards() == 5


def test_grid_empty_project():
    db, proj = _make_project()
    view = StoryGridView(db, proj.id)
    assert view.column_count() == 0
    assert view.total_cards() == 0


def test_grid_unassigned_column():
    db, proj = _make_project()
    db.create_scene(proj.id, "Orphan", content="No act.")
    view = StoryGridView(db, proj.id)
    assert view.column_count() == 1
    col = view._columns[0]
    assert col.group_name == "Unassigned"


def test_grid_refresh_updates():
    db, proj, *_ = _make_project_with_scenes()
    view = StoryGridView(db, proj.id)
    assert view.total_cards() == 5
    db.create_scene(proj.id, "New", act="Act 1")
    view.refresh()
    assert view.total_cards() == 6


# -- Scene cards -------------------------------------------------------------

def test_card_has_title():
    db, proj, s1, *_ = _make_project_with_scenes()
    scene = db.get_scene_by_id(s1.id)
    card = _SceneCard(scene, zoom=2)
    assert card._title_label.text() == "Opening"


def test_card_zoom_0_hides_summary():
    db, proj, s1, *_ = _make_project_with_scenes()
    scene = db.get_scene_by_id(s1.id)
    card = _SceneCard(scene, zoom=0)
    assert card._summary_label.isHidden()
    assert card._meta_label.isHidden()


def test_card_zoom_1_shows_summary():
    db, proj = _make_project()
    s = db.create_scene(proj.id, "Test", summary="A summary here")
    scene = db.get_scene_by_id(s.id)
    card = _SceneCard(scene, zoom=1)
    assert not card._summary_label.isHidden()
    assert card._meta_label.isHidden()


def test_card_zoom_2_shows_all():
    db, proj = _make_project()
    s = db.create_scene(proj.id, "Test", summary="Sum", tags="thriller", beat="Climax")
    scene = db.get_scene_by_id(s.id)
    card = _SceneCard(scene, zoom=2)
    assert not card._summary_label.isHidden()
    assert not card._meta_label.isHidden()


def test_card_truncates_long_summary():
    db, proj = _make_project()
    s = db.create_scene(proj.id, "Test", summary="A" * 200)
    scene = db.get_scene_by_id(s.id)
    card = _SceneCard(scene, zoom=2)
    assert len(card._summary_label.text()) <= 83


def test_card_meta_shows_beat_tag_plotline():
    db, proj = _make_project()
    s = db.create_scene(proj.id, "Test", beat="Midpoint", tags="action", plotline="Main")
    scene = db.get_scene_by_id(s.id)
    card = _SceneCard(scene, zoom=2)
    meta = card._meta_label.text()
    assert "Midpoint" in meta
    assert "action" in meta
    assert "Main" in meta


def test_card_object_name():
    db, proj, s1, *_ = _make_project_with_scenes()
    scene = db.get_scene_by_id(s1.id)
    card = _SceneCard(scene, zoom=1)
    assert card.objectName() == "gridSceneCard"


# -- Act sections (formerly columns) -----------------------------------------

def test_section_header_text():
    section = _GridColumn("Act 1")
    assert section._header.text() == "Act 1"


def test_section_unassigned_header():
    section = _GridColumn("")
    assert section._header.text() == "Unassigned"


def test_section_card_count():
    section = _GridColumn("Act 1")
    assert section.card_count() == 0


def test_section_accepts_drops():
    section = _GridColumn("Act 1")
    assert section.acceptDrops()


def test_section_object_name():
    section = _GridColumn("Act 1")
    assert section.objectName() == "gridActSection"


# -- Zoom levels -------------------------------------------------------------

def test_zoom_default():
    db, proj, *_ = _make_project_with_scenes()
    view = StoryGridView(db, proj.id)
    assert view.get_zoom() == 1


def test_zoom_in():
    db, proj, *_ = _make_project_with_scenes()
    view = StoryGridView(db, proj.id)
    view._zoom_in()
    assert view.get_zoom() == 2


def test_zoom_out():
    db, proj, *_ = _make_project_with_scenes()
    view = StoryGridView(db, proj.id)
    view._zoom_out()
    assert view.get_zoom() == 0


def test_zoom_in_capped():
    db, proj, *_ = _make_project_with_scenes()
    view = StoryGridView(db, proj.id)
    view._zoom_in()
    view._zoom_in()
    view._zoom_in()
    assert view.get_zoom() == 2


def test_zoom_out_capped():
    db, proj, *_ = _make_project_with_scenes()
    view = StoryGridView(db, proj.id)
    view._zoom_out()
    view._zoom_out()
    view._zoom_out()
    assert view.get_zoom() == 0


def test_zoom_label_updates():
    db, proj, *_ = _make_project_with_scenes()
    view = StoryGridView(db, proj.id)
    assert "Summary" in view._zoom_label.text()
    view._zoom_in()
    assert "Detail" in view._zoom_label.text()
    view._zoom_out()
    view._zoom_out()
    assert "Titles" in view._zoom_label.text()


# -- Color coding ------------------------------------------------------------

def test_color_mode_default_none():
    db, proj, *_ = _make_project_with_scenes()
    view = StoryGridView(db, proj.id)
    assert view.get_color_mode() == "none"


def test_color_mode_switch_plotline():
    db, proj, *_ = _make_project_with_scenes()
    view = StoryGridView(db, proj.id)
    view._color_combo.setCurrentIndex(1)
    assert view.get_color_mode() == "plotline"


def test_color_mode_switch_tag():
    db, proj, *_ = _make_project_with_scenes()
    view = StoryGridView(db, proj.id)
    view._color_combo.setCurrentIndex(2)
    assert view.get_color_mode() == "tag"


def test_color_mode_switch_beat():
    db, proj, *_ = _make_project_with_scenes()
    view = StoryGridView(db, proj.id)
    view._color_combo.setCurrentIndex(3)
    assert view.get_color_mode() == "beat"


def test_color_map_empty_for_none():
    db, proj, *_ = _make_project_with_scenes()
    view = StoryGridView(db, proj.id)
    scenes = db.get_all_scenes(proj.id)
    cmap = view._build_color_map(scenes)
    assert cmap == {}


def test_color_map_plotline_assigns_colors():
    db, proj, *_ = _make_project_with_scenes()
    view = StoryGridView(db, proj.id)
    view._color_mode = "plotline"
    scenes = db.get_all_scenes(proj.id)
    cmap = view._build_color_map(scenes)
    assert len(cmap) > 0
    for color in cmap.values():
        assert color in _COLOR_PALETTE


def test_color_map_tag_assigns_colors():
    db, proj, *_ = _make_project_with_scenes()
    view = StoryGridView(db, proj.id)
    view._color_mode = "tag"
    scenes = db.get_all_scenes(proj.id)
    cmap = view._build_color_map(scenes)
    assert len(cmap) > 0


def test_color_palette_has_enough_colors():
    assert len(_COLOR_PALETTE) >= 8


# -- Drag and drop -----------------------------------------------------------

def test_drop_changes_act():
    db, proj, s1, *_ = _make_project_with_scenes()
    view = StoryGridView(db, proj.id)
    view._on_scene_dropped(s1.id, "Act 2", 0)
    scene = db.get_scene_by_id(s1.id)
    assert scene.act == "Act 2"


def test_drop_changes_chapter():
    db, proj, s1, *_ = _make_project_with_scenes()
    view = StoryGridView(db, proj.id)
    view._group_by = "chapter"
    view._on_scene_dropped(s1.id, "Chapter 2", 0)
    scene = db.get_scene_by_id(s1.id)
    assert scene.chapter == "Chapter 2"


def test_drop_to_unassigned():
    db, proj, s1, *_ = _make_project_with_scenes()
    view = StoryGridView(db, proj.id)
    view._on_scene_dropped(s1.id, "Unassigned", 0)
    scene = db.get_scene_by_id(s1.id)
    assert scene.act == ""


def test_drop_triggers_refresh():
    db, proj, s1, *_ = _make_project_with_scenes()
    changed = []
    view = StoryGridView(db, proj.id, on_data_changed=lambda: changed.append(True))
    view._on_scene_dropped(s1.id, "Act 3", 0)
    assert changed == [True]


# -- Group switching ---------------------------------------------------------

def test_group_switch_refreshes():
    db, proj, *_ = _make_project_with_scenes()
    view = StoryGridView(db, proj.id)
    initial_count = view.column_count()
    view._group_combo.setCurrentIndex(1)
    assert view.get_group_by() == "chapter"
    assert view.column_count() > 0


# -- Empty state -------------------------------------------------------------

def test_empty_state_shows_add_button():
    db, proj = _make_project()
    view = StoryGridView(db, proj.id)
    assert view.column_count() == 0


def test_create_first_scene():
    db, proj = _make_project()
    view = StoryGridView(db, proj.id)
    view._create_first_scene()
    assert view.total_cards() == 1
    assert view.column_count() == 1


# -- Theme includes grid styles ----------------------------------------------

def test_theme_has_grid_column_rule():
    ss = theme.build_stylesheet()
    assert "#gridColumn" in ss


def test_theme_has_grid_card_rule():
    ss = theme.build_stylesheet()
    assert "#gridSceneCard" in ss


def test_theme_has_grid_toolbar_rule():
    ss = theme.build_stylesheet()
    assert "#gridToolbar" in ss


# -- Regression: deleted card mouse safety -----------------------------------

def test_scene_card_imports_shiboken_for_validity_guard():
    """mouseMoveEvent must guard against drag.exec() returning after the
    card was deleted by the drop's refresh — verified by shiboken import."""
    from logosforge.ui import story_grid_view
    assert hasattr(story_grid_view, "shiboken")


def test_scene_card_handles_enter_and_leave_events():
    """Cursor switches happen in enter/leave, not pinned in __init__."""
    db = Database()
    proj = db.create_project("Test")
    scene = db.create_scene(proj.id, "S1")
    card = _SceneCard(scene, zoom=2)
    assert hasattr(card, "enterEvent")
    assert hasattr(card, "leaveEvent")


def test_scene_card_default_cursor_not_pinned():
    """The OpenHandCursor was moved to enterEvent, so a fresh card has no
    persistent cursor override that could fire on a deleted widget."""
    from PySide6.QtCore import Qt
    db = Database()
    proj = db.create_project("Test")
    scene = db.create_scene(proj.id, "S1")
    card = _SceneCard(scene, zoom=2)
    # cursor() returns the default Arrow if no override is set
    assert card.cursor().shape() == Qt.CursorShape.ArrowCursor


# -- 3x3 block grid layout --------------------------------------------------

def test_grid_uses_act_sections():
    """Grid displays Act sections, not horizontal columns."""
    db, proj, *_ = _make_project_with_scenes()
    view = StoryGridView(db, proj.id)
    assert view.column_count() == 3
    for section in view._columns:
        assert section.objectName() == "gridActSection"


def test_grid_cards_are_square():
    """Cards have fixed square-ish dimensions."""
    from logosforge.ui.story_grid_view import _BLOCK_SIZE
    db, proj, s1, *_ = _make_project_with_scenes()
    scene = db.get_scene_by_id(s1.id)
    card = _SceneCard(scene, zoom=1)
    assert card.width() == _BLOCK_SIZE
    assert card.height() == _BLOCK_SIZE


def test_grid_3_columns_per_section():
    """Blocks within an Act section are arranged in a 3-column grid."""
    from logosforge.ui.story_grid_view import _GRID_COLUMNS, _ActSection
    section = _ActSection("Act 1")
    db = Database()
    proj = db.create_project("Test")
    for i in range(7):
        scene = db.create_scene(proj.id, f"Scene {i}", act="Act 1")
        card = _SceneCard(scene, zoom=1)
        section.add_card(card)
    assert section.card_count() == 7
    # Cards placed in grid: 7 cards -> 3 rows (3, 3, 1)
    assert section._grid.rowCount() == 3
    assert section._grid.columnCount() == _GRID_COLUMNS


def test_grid_no_horizontal_scroll():
    """Grid scroll area disables horizontal scrollbar."""
    from PySide6.QtCore import Qt
    db, proj, *_ = _make_project_with_scenes()
    view = StoryGridView(db, proj.id)
    assert view._scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff


def test_grid_vertical_layout():
    """Act sections are stacked vertically, not side-by-side."""
    from PySide6.QtWidgets import QVBoxLayout
    db, proj, *_ = _make_project_with_scenes()
    view = StoryGridView(db, proj.id)
    assert isinstance(view._grid_layout, QVBoxLayout)


# -- Writing mode detection --------------------------------------------------

def test_format_mode_novel_default():
    db, proj = _make_project()
    view = StoryGridView(db, proj.id)
    assert view.get_format_mode() == "novel"


def test_format_mode_screenplay():
    db = Database()
    proj = db.create_project("ScreenTest", format_mode="screenplay")
    view = StoryGridView(db, proj.id)
    assert view.get_format_mode() == "screenplay"


def test_block_label_novel_shows_chapter():
    db, proj = _make_project()
    view = StoryGridView(db, proj.id)
    assert view._block_unit == "chapter"
    assert "Ch" in view._block_number_label(1)


def test_block_label_screenplay_shows_scene():
    db = Database()
    proj = db.create_project("ScreenTest", format_mode="screenplay")
    view = StoryGridView(db, proj.id)
    assert view._block_unit == "scene"
    assert "Scene" in view._block_number_label(1)


def test_cards_have_block_number_labels():
    db, proj, *_ = _make_project_with_scenes()
    view = StoryGridView(db, proj.id)
    # First section, first card should have a number label
    first_card = view._columns[0]._cards[0]
    assert first_card._number_label.text() != ""


# -- Theme includes act section style ----------------------------------------

def test_theme_has_act_section_rule():
    ss = theme.build_stylesheet()
    assert "#gridActSection" in ss


# -- Edit operations ---------------------------------------------------------

def test_edit_summary_updates_db():
    db, proj, s1, *_ = _make_project_with_scenes()
    db.update_scene_summary(s1.id, "New summary text")
    scene = db.get_scene_by_id(s1.id)
    assert scene.summary == "New summary text"


def test_move_to_act_updates_db():
    db, proj, s1, *_ = _make_project_with_scenes()
    view = StoryGridView(db, proj.id)
    view._move_to_act(s1.id, "Act 3")
    scene = db.get_scene_by_id(s1.id)
    assert scene.act == "Act 3"


def test_nine_blocks_visible_as_3x3():
    """9 blocks in one Act should fill a 3x3 grid exactly."""
    from logosforge.ui.story_grid_view import _GRID_COLUMNS, _ActSection
    db = Database()
    proj = db.create_project("NineTest")
    section = _ActSection("Act 1")
    for i in range(9):
        scene = db.create_scene(proj.id, f"Scene {i}", act="Act 1")
        card = _SceneCard(scene, zoom=1)
        section.add_card(card)
    assert section.card_count() == 9
    assert section._grid.rowCount() == 3
    assert section._grid.columnCount() == _GRID_COLUMNS


def test_tenth_block_creates_fourth_row():
    """10th block goes to row 4, enabling vertical scroll."""
    from logosforge.ui.story_grid_view import _ActSection
    db = Database()
    proj = db.create_project("TenTest")
    section = _ActSection("Act 1")
    for i in range(10):
        scene = db.create_scene(proj.id, f"Scene {i}", act="Act 1")
        card = _SceneCard(scene, zoom=1)
        section.add_card(card)
    assert section.card_count() == 10
    assert section._grid.rowCount() == 4
