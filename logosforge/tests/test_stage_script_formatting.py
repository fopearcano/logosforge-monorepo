"""Tests for Stage Script manuscript block system and formatting."""

import pytest

from logosforge.writing_formats import STAGE_SCRIPT
from logosforge.ui.writing_core_view import (
    WritingCoreView,
    _BlockData,
    _ELEMENT_TRANSITIONS,
)


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    yield
    settings._instance = None


def _ss_view():
    from logosforge.db import Database
    db = Database()
    proj = db.create_project(
        "Play", narrative_engine="stage_script",
        default_writing_format="stage_script",
    )
    scene = db.create_scene(proj.id, "Act One", content="The lights rise.")
    return db, proj, scene, WritingCoreView(db, proj.id)


def _elem(name):
    return next(e for e in STAGE_SCRIPT.elements if e.name == name)


# =========================================================================
# 1. Block types (§1)
# =========================================================================

def test_all_required_block_types_exist():
    names = {e.name for e in STAGE_SCRIPT.elements}
    for required in (
        "act_heading", "scene_heading", "character", "dialogue",
        "stage_direction", "parenthetical", "aside", "cue",
        "transition", "note",
    ):
        assert required in names


def test_default_block_is_dialogue():
    assert STAGE_SCRIPT.default_element == "dialogue"


# =========================================================================
# 2. ModeFormat dropdown (§3)
# =========================================================================

def test_modeformat_dropdown_lists_theatre_blocks():
    db, proj, scene, view = _ss_view()
    labels = {
        view._element_combo.itemText(i)
        for i in range(view._element_combo.count())
    }
    for expected in (
        "Act Heading", "Scene Heading", "Character", "Dialogue",
        "Stage Direction", "Parenthetical", "Aside", "Cue", "Note",
    ):
        assert expected in labels


def test_dropdown_data_uses_element_names():
    db, proj, scene, view = _ss_view()
    data = {
        view._element_combo.itemData(i)
        for i in range(view._element_combo.count())
    }
    assert "act_heading" in data
    assert "stage_direction" in data


# =========================================================================
# 3. Visual formatting (§2)
# =========================================================================

def test_act_heading_uppercase_centered_separated():
    e = _elem("act_heading")
    assert e.all_caps and e.align == "center"
    assert e.top_spacing >= 40  # strongly separated
    assert e.font_size > _elem("dialogue").font_size


def test_scene_heading_is_heading():
    e = _elem("scene_heading")
    assert e.all_caps and e.bold


def test_character_uppercase():
    e = _elem("character")
    assert e.all_caps


def test_dialogue_full_width():
    e = _elem("dialogue")
    assert e.left_margin == 0 and e.right_margin == 0


def test_stage_direction_italic_muted_enclosed():
    e = _elem("stage_direction")
    assert e.italic
    assert e.color_key == "muted"
    assert e.background_key == "panel"   # enclosed / visually distinct


def test_aside_marked_not_loud():
    e = _elem("aside")
    assert e.italic and e.color_key == "secondary"


def test_cue_is_compact_marker():
    e = _elem("cue")
    assert e.font_size < _elem("dialogue").font_size
    assert e.all_caps and e.color_key == "accent"


def test_note_muted_editorial():
    e = _elem("note")
    assert e.italic and e.color_key == "muted"


def test_transition_right_aligned_caps():
    e = _elem("transition")
    assert e.align == "right" and e.all_caps


def test_blocks_visually_distinct():
    sigs = [
        (e.font_size, e.bold, e.italic, e.all_caps, e.align,
         e.left_margin, e.color_key, e.background_key)
        for e in STAGE_SCRIPT.elements
    ]
    assert len(sigs) == len(set(sigs))


# =========================================================================
# 4. Editor applies blocks (§6)
# =========================================================================

def _apply(view, scene_id, name):
    editor = view._editors[scene_id]
    view._apply_element_to_block(editor, name)
    return editor


def test_create_act_heading():
    db, proj, scene, view = _ss_view()
    editor = _apply(view, scene.id, "act_heading")
    data = editor.textCursor().block().userData()
    assert isinstance(data, _BlockData) and data.element == "act_heading"
    assert editor.textCursor().block().blockFormat().topMargin() >= 40


def test_create_scene_heading():
    db, proj, scene, view = _ss_view()
    editor = _apply(view, scene.id, "scene_heading")
    assert editor.textCursor().block().userData().element == "scene_heading"


def test_character_dialogue_exchange():
    db, proj, scene, view = _ss_view()
    editor = view._editors[scene.id]
    cursor = editor.textCursor()
    view._apply_element_to_block(editor, "character")
    cursor.insertText("\n")
    view._apply_element_to_block(editor, "dialogue")
    cursor.insertText("\n")
    view._apply_element_to_block(editor, "character")
    elems = []
    block = editor.document().begin()
    while block.isValid():
        d = block.userData()
        if isinstance(d, _BlockData) and d.element:
            elems.append(d.element)
        block = block.next()
    assert elems.count("character") >= 2
    assert "dialogue" in elems


def test_create_stage_direction_has_band():
    db, proj, scene, view = _ss_view()
    editor = _apply(view, scene.id, "stage_direction")
    brush = editor.textCursor().block().blockFormat().background()
    assert brush.color().alpha() > 0


def test_create_cue():
    db, proj, scene, view = _ss_view()
    editor = _apply(view, scene.id, "cue")
    assert editor.textCursor().block().userData().element == "cue"


def test_switching_clears_band():
    db, proj, scene, view = _ss_view()
    editor = _apply(view, scene.id, "stage_direction")  # banded
    view._apply_element_to_block(editor, "dialogue")     # plain
    brush = editor.textCursor().block().blockFormat().background()
    assert brush.color().alpha() == 0


def test_editor_stable_across_all_blocks():
    db, proj, scene, view = _ss_view()
    editor = view._editors[scene.id]
    for e in STAGE_SCRIPT.elements:
        view._apply_element_to_block(editor, e.name)
        assert editor.textCursor().block().userData().element == e.name


def test_format_badge_shows_stage_script():
    db, proj, scene, view = _ss_view()
    assert "Stage Script" in view._format_badge.text()


# =========================================================================
# 5. Keyboard flow (§4)
# =========================================================================

def test_transitions_character_dialogue_cycle():
    t = _ELEMENT_TRANSITIONS["stage_script"]
    assert t["character"] == "dialogue"
    assert t["dialogue"] == "character"
    assert t["stage_direction"] == "dialogue"
    assert t["act_heading"] == "scene_heading"


# =========================================================================
# 6. No raw markdown (§5)
# =========================================================================

def test_no_markdown_in_block_model():
    for e in STAGE_SCRIPT.elements:
        assert "#" not in e.name and "*" not in e.name
