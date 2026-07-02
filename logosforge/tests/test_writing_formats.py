"""Tests for writing format definitions."""

from logosforge.writing_formats import (
    ALL_FORMATS,
    FORMAT_ORDER,
    GRAPHIC_NOVEL,
    NOVEL,
    SCREENPLAY,
    SERIES,
    STAGE_SCRIPT,
    ElementStyle,
    WritingFormat,
)


def test_format_count():
    assert len(ALL_FORMATS) == 5


def test_format_order_complete():
    assert set(FORMAT_ORDER) == set(ALL_FORMATS.keys())


def test_format_order_length():
    assert len(FORMAT_ORDER) == len(ALL_FORMATS)


def test_novel_format():
    assert NOVEL.name == "novel"
    assert NOVEL.default_element == "body"
    names = [e.name for e in NOVEL.elements]
    assert "body" in names
    assert "chapter" in names


def test_screenplay_format():
    assert SCREENPLAY.name == "screenplay"
    assert SCREENPLAY.default_element == "action"
    names = [e.name for e in SCREENPLAY.elements]
    assert "scene_heading" in names
    assert "action" in names
    assert "character" in names
    assert "dialogue" in names
    assert "parenthetical" in names
    assert "transition" in names


def test_graphic_novel_format():
    assert GRAPHIC_NOVEL.name == "graphic_novel"
    assert GRAPHIC_NOVEL.default_element == "panel"
    names = [e.name for e in GRAPHIC_NOVEL.elements]
    assert "page" in names
    assert "panel" in names
    assert "dialogue" in names


def test_stage_script_format():
    assert STAGE_SCRIPT.name == "stage_script"
    assert STAGE_SCRIPT.default_element == "dialogue"
    names = [e.name for e in STAGE_SCRIPT.elements]
    assert "act_heading" in names
    assert "scene_heading" in names
    assert "character" in names
    assert "dialogue" in names


def test_series_format():
    assert SERIES.name == "series"
    assert SERIES.default_element == "action"
    names = [e.name for e in SERIES.elements]
    assert "episode_heading" in names
    assert "act_heading" in names
    assert "scene_heading" in names


def test_element_style_defaults():
    e = ElementStyle(name="test")
    assert e.font_size == 15
    assert e.bold is False
    assert e.italic is False
    assert e.all_caps is False
    assert e.align == "left"
    assert e.left_margin == 0
    assert e.right_margin == 0
    assert e.line_height == 1.5
    assert e.color_key == "text"


def test_element_style_frozen():
    e = ElementStyle(name="test")
    try:
        e.name = "other"
        assert False, "Should have raised"
    except AttributeError:
        pass


def test_writing_format_frozen():
    try:
        NOVEL.name = "other"
        assert False, "Should have raised"
    except AttributeError:
        pass


def test_default_element_exists_in_elements():
    for fmt in ALL_FORMATS.values():
        elem_names = [e.name for e in fmt.elements]
        assert fmt.default_element in elem_names, (
            f"{fmt.name}: default_element '{fmt.default_element}' not in elements"
        )


def test_shortcuts_unique_per_format():
    for fmt in ALL_FORMATS.values():
        shortcuts = [e.shortcut for e in fmt.elements if e.shortcut]
        assert len(shortcuts) == len(set(shortcuts)), (
            f"{fmt.name}: duplicate shortcuts"
        )


def test_valid_align_values():
    for fmt in ALL_FORMATS.values():
        for e in fmt.elements:
            assert e.align in ("left", "center", "right"), (
                f"{fmt.name}/{e.name}: invalid align '{e.align}'"
            )
