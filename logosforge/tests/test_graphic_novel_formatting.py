"""Tests for Graphic Novel manuscript block system and formatting.

Covers the block types, the ModeFormat dropdown, visual distinction
between blocks, page separation, and editor stability when authoring a
graphic-novel script.
"""

import pytest

from logosforge.db import Database
from logosforge.writing_formats import ALL_FORMATS, GRAPHIC_NOVEL
from logosforge.ui.writing_core_view import (
    WritingCoreView,
    _BlockData,
    _element_bg_color,
    _element_text_color,
)


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    yield
    settings._instance = None


def _gn_project(db):
    return db.create_project(
        "GN",
        narrative_engine="graphic_novel",
        default_writing_format="graphic_novel",
    )


def _gn_view():
    db = Database()
    proj = _gn_project(db)
    db.create_scene(proj.id, "Issue 1", content="PAGE ONE")
    return db, proj, WritingCoreView(db, proj.id)


# =========================================================================
# 1. Block types (§1)
# =========================================================================

def test_all_required_block_types_exist():
    names = {e.name for e in GRAPHIC_NOVEL.elements}
    for required in (
        "page", "panel", "caption", "dialogue", "sfx",
        "art_direction", "internal_thought", "transition", "note",
    ):
        assert required in names


def test_default_block_is_panel():
    assert GRAPHIC_NOVEL.default_element == "panel"


# =========================================================================
# 2. ModeFormat dropdown exposes the blocks (§5)
# =========================================================================

def test_modeformat_dropdown_lists_graphic_novel_blocks():
    db, proj, view = _gn_view()
    labels = {
        view._element_combo.itemText(i)
        for i in range(view._element_combo.count())
    }
    for expected in ("Page", "Panel", "Dialogue", "Caption", "Sfx", "Art Direction"):
        assert expected in labels


def test_dropdown_data_uses_element_names():
    db, proj, view = _gn_view()
    data = {
        view._element_combo.itemData(i)
        for i in range(view._element_combo.count())
    }
    assert "page" in data
    assert "art_direction" in data


# =========================================================================
# 3. Visual formatting distinction (§4)
# =========================================================================

def test_page_header_is_large_and_bold():
    page = next(e for e in GRAPHIC_NOVEL.elements if e.name == "page")
    body_like = next(e for e in GRAPHIC_NOVEL.elements if e.name == "dialogue")
    assert page.font_size > body_like.font_size  # larger
    assert page.bold and page.all_caps


def test_description_is_indented_and_boxed():
    desc = next(e for e in GRAPHIC_NOVEL.elements if e.name == "description")
    assert desc.left_margin > 0          # indented
    assert desc.background_key == "panel"  # boxed band


def test_art_direction_is_muted():
    art = next(e for e in GRAPHIC_NOVEL.elements if e.name == "art_direction")
    assert art.color_key == "muted"
    assert art.italic


def test_sfx_is_stylized():
    sfx = next(e for e in GRAPHIC_NOVEL.elements if e.name == "sfx")
    assert sfx.bold and sfx.all_caps
    assert sfx.color_key == "accent"
    assert sfx.background_key == "sfx"


def test_blocks_are_visually_distinct():
    """No two block types share an identical visual signature."""
    sigs = [
        (
            e.font_size, e.bold, e.italic, e.all_caps, e.align,
            e.left_margin, e.color_key, e.background_key,
        )
        for e in GRAPHIC_NOVEL.elements
    ]
    assert len(sigs) == len(set(sigs))


def test_color_and_bg_resolvers():
    assert _element_text_color("muted")
    assert _element_text_color("accent")
    assert _element_text_color("") == ""
    assert _element_bg_color("panel")
    assert _element_bg_color("sfx")
    assert _element_bg_color("") == ""


# =========================================================================
# 4. Editor applies blocks (create page / panels / dialogue) (§7)
# =========================================================================

def test_create_page_block():
    db, proj, view = _gn_view()
    scene = db.get_all_scenes(proj.id)[0]
    editor = view._editors[scene.id]
    view._apply_element_to_block(editor, "page")
    data = editor.textCursor().block().userData()
    assert isinstance(data, _BlockData)
    assert data.element == "page"


def test_create_multiple_panels():
    db, proj, view = _gn_view()
    scene = db.get_all_scenes(proj.id)[0]
    editor = view._editors[scene.id]
    cursor = editor.textCursor()
    # Page header, then two panels with descriptions.
    view._apply_element_to_block(editor, "page")
    cursor.insertText("\n")
    view._apply_element_to_block(editor, "panel")
    cursor.insertText("\n")
    view._apply_element_to_block(editor, "panel")
    # Walk the document and count panel blocks.
    panels = 0
    block = editor.document().begin()
    while block.isValid():
        d = block.userData()
        if isinstance(d, _BlockData) and d.element == "panel":
            panels += 1
        block = block.next()
    assert panels >= 2


def test_dialogue_formatting_applies():
    db, proj, view = _gn_view()
    scene = db.get_all_scenes(proj.id)[0]
    editor = view._editors[scene.id]
    view._apply_element_to_block(editor, "dialogue")
    block = editor.textCursor().block()
    data = block.userData()
    assert isinstance(data, _BlockData) and data.element == "dialogue"
    # Dialogue is indented toward the balloon column.
    assert block.blockFormat().leftMargin() == 180


def test_sfx_block_gets_band_background():
    db, proj, view = _gn_view()
    scene = db.get_all_scenes(proj.id)[0]
    editor = view._editors[scene.id]
    view._apply_element_to_block(editor, "sfx")
    block = editor.textCursor().block()
    brush = block.blockFormat().background()
    # A non-transparent band is applied.
    assert brush.color().alpha() > 0


def test_page_separation_via_top_spacing():
    """Pages read as separated sections via generous top spacing."""
    db, proj, view = _gn_view()
    scene = db.get_all_scenes(proj.id)[0]
    editor = view._editors[scene.id]
    view._apply_element_to_block(editor, "page")
    top = editor.textCursor().block().blockFormat().topMargin()
    assert top >= 40


# =========================================================================
# 5. Editor stability (§7)
# =========================================================================

def test_editor_stable_across_all_block_types():
    db, proj, view = _gn_view()
    scene = db.get_all_scenes(proj.id)[0]
    editor = view._editors[scene.id]
    for name in [e.name for e in GRAPHIC_NOVEL.elements]:
        # Applying every block type in turn must not raise.
        view._apply_element_to_block(editor, name)
        data = editor.textCursor().block().userData()
        assert isinstance(data, _BlockData) and data.element == name


def test_switching_block_clears_previous_background():
    """Re-styling a boxed block to a plain one removes the band."""
    db, proj, view = _gn_view()
    scene = db.get_all_scenes(proj.id)[0]
    editor = view._editors[scene.id]
    view._apply_element_to_block(editor, "sfx")  # has a band
    view._apply_element_to_block(editor, "dialogue")  # no band
    brush = editor.textCursor().block().blockFormat().background()
    assert brush.color().alpha() == 0  # band cleared


def test_format_badge_shows_graphic_novel():
    db, proj, view = _gn_view()
    assert "Graphic Novel" in view._format_badge.text()


def test_no_raw_markdown_in_block_model():
    """Block identity is metadata, not markdown — element names carry no
    markdown syntax."""
    for e in GRAPHIC_NOVEL.elements:
        assert "#" not in e.name
        assert "*" not in e.name
