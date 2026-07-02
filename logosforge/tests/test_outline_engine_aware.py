"""Tests: Outline generation respects the project's Narrative Engine."""

import pytest

from logosforge.db import Database
from logosforge.outline_actions import (
    build_outline_generation_prompt,
    engine_structural_units,
)


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    yield
    settings._instance = None


# =========================================================================
# 1. Structural units come from the NarrativeEngine registry
# =========================================================================

def test_engine_structural_units_per_engine():
    assert engine_structural_units("novel") == ("part", "chapter", "scene")
    assert engine_structural_units("screenplay") == (
        "act", "sequence", "scene", "beat")
    assert engine_structural_units("graphic_novel") == (
        "issue", "chapter", "sequence", "page", "panel")
    assert engine_structural_units("stage_script")[:2] == ("act", "scene")
    assert engine_structural_units("series")[:3] == (
        "series", "season", "episode")


def test_unknown_engine_falls_back_to_novel():
    assert engine_structural_units("nonsense") == ("part", "chapter", "scene")


def _guide_line(prompt: str) -> str:
    return next(l for l in prompt.splitlines() if l.startswith("Structure as"))


# =========================================================================
# 2. Full-outline prompt reflects engine vocabulary
# =========================================================================

def test_novel_guide():
    g = _guide_line(build_outline_generation_prompt("full", engine="novel"))
    assert "Part" in g and "Chapter" in g and "Scene" in g
    assert "Sequence" not in g and "Panel" not in g


def test_screenplay_guide():
    g = _guide_line(build_outline_generation_prompt("full", engine="screenplay"))
    assert "Act" in g and "Sequence" in g and "Beat" in g


def test_graphic_novel_guide():
    g = _guide_line(build_outline_generation_prompt("full", engine="graphic_novel"))
    assert "Issue" in g and "Page" in g and "Panel" in g
    assert "Part" not in g


def test_series_guide():
    g = _guide_line(build_outline_generation_prompt("full", engine="series"))
    assert "Season" in g and "Episode" in g
    assert "A/B/C Plot" in g          # plotline rendered as A/B/C Plot


def test_stage_script_guide_renders_entrance_exit():
    g = _guide_line(build_outline_generation_prompt("full", engine="stage_script"))
    assert "Entrance/Exit" in g


# =========================================================================
# 3. Scope tiers map to the engine's units (not generic Act/Chapter)
# =========================================================================

def _gen_line(prompt: str) -> str:
    return next(l for l in prompt.splitlines() if l.startswith("Generate ONE"))


def test_top_tier_per_engine():
    assert "ONE Part" in _gen_line(build_outline_generation_prompt("act", engine="novel"))
    assert "ONE Act" in _gen_line(build_outline_generation_prompt("act", engine="screenplay"))
    assert "ONE Issue" in _gen_line(build_outline_generation_prompt("act", engine="graphic_novel"))
    assert "ONE Series" in _gen_line(build_outline_generation_prompt("act", engine="series"))


def test_second_tier_per_engine():
    assert "ONE Chapter" in _gen_line(
        build_outline_generation_prompt("chapter", engine="novel"))
    assert "ONE Sequence" in _gen_line(
        build_outline_generation_prompt("chapter", engine="screenplay"))
    assert "ONE Chapter" in _gen_line(
        build_outline_generation_prompt("chapter", engine="graphic_novel"))


def test_format_instruction_lists_engine_units():
    p = build_outline_generation_prompt("full", engine="graphic_novel")
    # The "Prefix items with ..." instruction lists the GN units.
    assert "Panel" in p and "Issue" in p


# =========================================================================
# 4. Template + PSYKE still fold in (engine-agnostic extras)
# =========================================================================

def test_template_and_psyke_still_included():
    p = build_outline_generation_prompt(
        "full", engine="screenplay", template_name="Save the Cat",
        template_beats=["Opening Image"], psyke_context="[PSYKE] Hero",
    )
    assert "Save the Cat" in p
    assert "Opening Image" in p
    assert "Hero" in p
    assert "Sequence" in _guide_line(p)   # engine vocabulary still present


# =========================================================================
# 5. Outline UI labels adapt to the engine
# =========================================================================

def _view(db, project_id):
    from logosforge.ui.outline_view import OutlineView
    return OutlineView(db, project_id)


def _toolbar_add_labels(view):
    from PySide6.QtWidgets import QPushButton
    return [b.text() for b in view.findChildren(QPushButton)
            if b.text().startswith("+ ")]


def test_novel_ui_labels():
    db = Database()
    p = db.create_project("Novel", narrative_engine="novel",
                          default_writing_format="novel")
    labels = _toolbar_add_labels(_view(db, p.id))
    assert "+ Part" in labels
    assert "+ Scene" in labels


def test_screenplay_ui_labels():
    db = Database()
    p = db.create_project("SP", narrative_engine="screenplay",
                          default_writing_format="screenplay")
    labels = _toolbar_add_labels(_view(db, p.id))
    assert "+ Act" in labels
    assert "+ Beat" in labels


def test_graphic_novel_ui_labels():
    db = Database()
    p = db.create_project("GN", narrative_engine="graphic_novel",
                          default_writing_format="graphic_novel")
    labels = _toolbar_add_labels(_view(db, p.id))
    assert "+ Issue" in labels
    assert "+ Panel" in labels


def test_contextual_ai_button_uses_engine_units():
    db = Database()
    p = db.create_project("GN", narrative_engine="graphic_novel",
                          default_writing_format="graphic_novel")
    issue = db.create_outline_node(p.id, "Issue 1", parent_id=None)
    ch = db.create_outline_node(p.id, "Chapter 1", parent_id=issue.id)
    view = _view(db, p.id)
    view._load_outline()
    view._select_node(issue.id)
    assert view._ai_node_btn.text() == "✨ AI Generate Issue"
    view._select_node(ch.id)
    assert view._ai_node_btn.text() == "✨ AI Generate Chapter"


def test_editor_label_uses_engine_unit():
    db = Database()
    p = db.create_project("Novel", narrative_engine="novel",
                          default_writing_format="novel")
    part = db.create_outline_node(p.id, "Part 1", parent_id=None)
    view = _view(db, p.id)
    view._load_outline()
    view._select_node(part.id)
    assert view._editor_label.text() == "Part"


# =========================================================================
# 6. View generation prompt is engine-aware end-to-end
# =========================================================================

def test_view_generation_prompt_screenplay():
    db = Database()
    p = db.create_project("SP", narrative_engine="screenplay",
                          default_writing_format="screenplay")
    view = _view(db, p.id)
    prompt = view.build_generation_prompt("full", None)
    assert "Sequence" in prompt
    assert "Part" not in _guide_line(prompt)


def test_view_generation_prompt_graphic_novel():
    db = Database()
    p = db.create_project("GN", narrative_engine="graphic_novel",
                          default_writing_format="graphic_novel")
    view = _view(db, p.id)
    prompt = view.build_generation_prompt("full", None)
    assert "Panel" in prompt and "Issue" in prompt
