"""Tests for screenplay editor formatting — block styles, Tab cycling, Enter transitions."""

from __future__ import annotations

import pytest

from logosforge.writing_formats import (
    ALL_FORMATS,
    SCREENPLAY,
    NOVEL,
    ElementStyle,
    WritingFormat,
)
from logosforge.ui.writing_core_view import (
    _BlockData,
    _ELEMENT_TRANSITIONS,
)


# -- ElementStyle definitions -------------------------------------------------

def test_screenplay_scene_heading_is_bold_allcaps():
    elem = _get_elem(SCREENPLAY, "scene_heading")
    assert elem.bold is True
    assert elem.all_caps is True
    assert elem.align == "left"


def test_screenplay_action_is_plain():
    elem = _get_elem(SCREENPLAY, "action")
    assert elem.bold is False
    assert elem.italic is False
    assert elem.all_caps is False
    assert elem.left_margin == 0
    assert elem.right_margin == 0


def test_screenplay_character_is_allcaps_indented():
    elem = _get_elem(SCREENPLAY, "character")
    assert elem.all_caps is True
    assert elem.left_margin == 264


def test_screenplay_dialogue_has_margins():
    elem = _get_elem(SCREENPLAY, "dialogue")
    assert elem.left_margin == 120
    assert elem.right_margin == 180
    assert elem.bold is False


def test_screenplay_parenthetical_is_italic():
    elem = _get_elem(SCREENPLAY, "parenthetical")
    assert elem.italic is True
    assert elem.left_margin == 180
    assert elem.right_margin == 240


def test_screenplay_transition_is_right_aligned_allcaps():
    elem = _get_elem(SCREENPLAY, "transition")
    assert elem.all_caps is True
    assert elem.align == "right"


def test_screenplay_default_element_is_action():
    assert SCREENPLAY.default_element == "action"


def test_screenplay_has_six_elements():
    assert len(SCREENPLAY.elements) == 6
    names = [e.name for e in SCREENPLAY.elements]
    assert names == [
        "scene_heading", "action", "character",
        "dialogue", "parenthetical", "transition",
    ]


# -- Element transitions (Enter key) -----------------------------------------

def test_screenplay_enter_transitions_defined():
    tr = _ELEMENT_TRANSITIONS["screenplay"]
    assert tr["scene_heading"] == "action"
    assert tr["action"] == "action"
    assert tr["character"] == "dialogue"
    assert tr["dialogue"] == "action"
    assert tr["parenthetical"] == "dialogue"
    assert tr["transition"] == "scene_heading"


def test_novel_enter_transitions_defined():
    tr = _ELEMENT_TRANSITIONS["novel"]
    assert tr["chapter"] == "body"
    assert tr["body"] == "body"


def test_all_formats_have_transitions():
    for key in ALL_FORMATS:
        assert key in _ELEMENT_TRANSITIONS, f"Missing transitions for {key}"


# -- BlockData ----------------------------------------------------------------

def test_block_data_stores_element():
    bd = _BlockData("scene_heading")
    assert bd.element == "scene_heading"


def test_block_data_default_empty():
    bd = _BlockData()
    assert bd.element == ""


# -- All formats have consistent element refs in transitions ------------------

def test_transition_targets_exist_in_format():
    for fmt_name, transitions in _ELEMENT_TRANSITIONS.items():
        fmt = ALL_FORMATS.get(fmt_name)
        if fmt is None:
            continue
        element_names = {e.name for e in fmt.elements}
        for src, dst in transitions.items():
            assert src in element_names, (
                f"{fmt_name}: transition source '{src}' not in format elements"
            )
            assert dst in element_names, (
                f"{fmt_name}: transition target '{dst}' not in format elements"
            )


# -- Screenplay format completeness ------------------------------------------

def test_screenplay_elements_all_have_shortcuts():
    for elem in SCREENPLAY.elements:
        assert elem.shortcut, f"{elem.name} has no shortcut"


def test_screenplay_all_elements_same_font_size():
    sizes = {e.font_size for e in SCREENPLAY.elements}
    assert len(sizes) == 1
    assert 15 in sizes


# -- Cross-format parity checks ----------------------------------------------

def test_all_formats_have_default_element_in_elements():
    for key, fmt in ALL_FORMATS.items():
        names = [e.name for e in fmt.elements]
        assert fmt.default_element in names, (
            f"{key}: default_element '{fmt.default_element}' not in elements"
        )


def test_all_format_names_are_lowercase():
    for key in ALL_FORMATS:
        assert key == key.lower()
        assert ALL_FORMATS[key].name == key


# -- helpers ------------------------------------------------------------------

def _get_elem(fmt: WritingFormat, name: str) -> ElementStyle:
    for e in fmt.elements:
        if e.name == name:
            return e
    raise ValueError(f"No element '{name}' in format '{fmt.name}'")
