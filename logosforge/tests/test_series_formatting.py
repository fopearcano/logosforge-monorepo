"""Tests for Series Mode manuscript block system and formatting."""

import pytest

from logosforge.writing_formats import SERIES
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


def _series_view():
    from logosforge.db import Database
    db = Database()
    proj = db.create_project(
        "Show", narrative_engine="series", default_writing_format="series",
    )
    scene = db.create_scene(proj.id, "Pilot", content="FADE IN")
    return db, proj, scene, WritingCoreView(db, proj.id)


def _elem(name):
    return next(e for e in SERIES.elements if e.name == name)


# =========================================================================
# 1. Block types (§1)
# =========================================================================

def test_all_required_block_types_exist():
    names = {e.name for e in SERIES.elements}
    for required in (
        "season_heading", "episode_heading", "act_heading", "scene_heading",
        "a_plot", "b_plot", "c_plot", "teaser", "cold_open", "tag",
        "cliffhanger", "recap_note", "continuity_note",
    ):
        assert required in names


def test_default_block_is_action():
    assert SERIES.default_element == "action"


# =========================================================================
# 2. ModeFormat dropdown (§3)
# =========================================================================

def test_modeformat_dropdown_lists_series_blocks():
    db, proj, scene, view = _series_view()
    labels = {
        view._element_combo.itemText(i)
        for i in range(view._element_combo.count())
    }
    for expected in (
        "Season Heading", "Episode Heading", "Act Heading", "Scene Heading",
        "A Plot", "B Plot", "C Plot", "Cold Open", "Tag", "Cliffhanger",
        "Continuity Note",
    ):
        assert expected in labels


# =========================================================================
# 3. Visual formatting (§2)
# =========================================================================

def test_season_heading_strong_separator():
    e = _elem("season_heading")
    assert e.all_caps and e.bold and e.align == "center"
    assert e.top_spacing >= 48          # strong section separator
    assert e.font_size > _elem("episode_heading").font_size


def test_episode_heading_clear_title():
    e = _elem("episode_heading")
    assert e.all_caps and e.bold and e.align == "center"


def test_act_heading_compact_divider():
    e = _elem("act_heading")
    assert e.all_caps and e.align == "center"


def test_abc_plots_are_colored_tags():
    a, b, c = _elem("a_plot"), _elem("b_plot"), _elem("c_plot")
    assert a.color_key == "accent"
    assert b.color_key == "secondary"
    assert c.color_key == "muted"
    # All three read as compact tag labels.
    for e in (a, b, c):
        assert e.all_caps and e.font_size < _elem("action").font_size


def test_cold_open_and_teaser_distinctive():
    for name in ("cold_open", "teaser"):
        e = _elem(name)
        assert e.background_key  # banded opener block
        assert e.align == "center"


def test_cliffhanger_marked_not_loud():
    e = _elem("cliffhanger")
    assert e.italic and e.color_key == "accent"
    assert not e.all_caps  # not loud


def test_continuity_note_muted():
    e = _elem("continuity_note")
    assert e.italic and e.color_key == "muted"


def test_recap_note_muted():
    e = _elem("recap_note")
    assert e.italic and e.color_key == "muted"


# =========================================================================
# 4. Editor applies blocks (§6)
# =========================================================================

def _apply(view, scene_id, name):
    editor = view._editors[scene_id]
    view._apply_element_to_block(editor, name)
    return editor


def test_create_season_heading():
    db, proj, scene, view = _series_view()
    editor = _apply(view, scene.id, "season_heading")
    data = editor.textCursor().block().userData()
    assert isinstance(data, _BlockData) and data.element == "season_heading"
    assert editor.textCursor().block().blockFormat().topMargin() >= 48


def test_create_episode_heading():
    db, proj, scene, view = _series_view()
    editor = _apply(view, scene.id, "episode_heading")
    assert editor.textCursor().block().userData().element == "episode_heading"


def test_create_abc_plot_blocks():
    db, proj, scene, view = _series_view()
    editor = view._editors[scene.id]
    cursor = editor.textCursor()
    for name in ("a_plot", "b_plot", "c_plot"):
        view._apply_element_to_block(editor, name)
        cursor.insertText("\n")
    elems = []
    block = editor.document().begin()
    while block.isValid():
        d = block.userData()
        if isinstance(d, _BlockData) and d.element:
            elems.append(d.element)
        block = block.next()
    assert "a_plot" in elems and "b_plot" in elems and "c_plot" in elems


def test_abc_plot_band_background():
    db, proj, scene, view = _series_view()
    editor = _apply(view, scene.id, "a_plot")
    brush = editor.textCursor().block().blockFormat().background()
    assert brush.color().alpha() > 0   # colored tag band


def test_create_cliffhanger():
    db, proj, scene, view = _series_view()
    editor = _apply(view, scene.id, "cliffhanger")
    assert editor.textCursor().block().userData().element == "cliffhanger"


def test_create_continuity_note():
    db, proj, scene, view = _series_view()
    editor = _apply(view, scene.id, "continuity_note")
    assert editor.textCursor().block().userData().element == "continuity_note"


def test_switching_clears_band():
    db, proj, scene, view = _series_view()
    editor = _apply(view, scene.id, "a_plot")       # banded
    view._apply_element_to_block(editor, "action")   # plain
    brush = editor.textCursor().block().blockFormat().background()
    assert brush.color().alpha() == 0


def test_editor_stable_across_all_blocks():
    db, proj, scene, view = _series_view()
    editor = view._editors[scene.id]
    for e in SERIES.elements:
        view._apply_element_to_block(editor, e.name)
        assert editor.textCursor().block().userData().element == e.name


def test_format_badge_shows_series():
    db, proj, scene, view = _series_view()
    assert "Series" in view._format_badge.text()


# =========================================================================
# 5. Keyboard flow + no markdown (§4, §5)
# =========================================================================

def test_series_transitions():
    t = _ELEMENT_TRANSITIONS["series"]
    assert t["season_heading"] == "episode_heading"
    assert t["episode_heading"] == "act_heading"
    assert t["character"] == "dialogue"
    assert t["dialogue"] == "action"


def test_no_markdown_in_block_model():
    for e in SERIES.elements:
        assert "#" not in e.name and "*" not in e.name
