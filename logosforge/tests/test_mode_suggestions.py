"""Tests for Adaptive AI Behavior — mode-specific suggestions."""

from logosforge.adaptive_mode import AIMode, ModeResult, StoryStage, HealthState
from logosforge.mode_suggestions import (
    ModeSuggestion,
    generate_mode_suggestions,
    _structure_suggestions,
    _balance_suggestions,
    _refinement_suggestions,
    MAX_SUGGESTIONS,
)
from logosforge.db import Database
from logosforge.ui import theme
from logosforge.ui.mode_suggestions_view import ModeSuggestionsView


def _make_project():
    db = Database()
    proj = db.create_project("ModeTest")
    return db, proj


# -- Structure mode suggestions -----------------------------------------------

def test_structure_empty_project():
    db, proj = _make_project()
    suggestions = _structure_suggestions(db, proj.id)
    assert len(suggestions) >= 1
    assert any("first scene" in s.text for s in suggestions)


def test_structure_no_acts():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    for i in range(4):
        db.create_scene(proj.id, f"S{i}", character_ids=[c.id])
    suggestions = _structure_suggestions(db, proj.id)
    assert any("act" in s.text.lower() for s in suggestions)


def test_structure_no_plotlines():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    for i in range(4):
        db.create_scene(proj.id, f"S{i}", act="Act 1", character_ids=[c.id])
    suggestions = _structure_suggestions(db, proj.id)
    assert any("plotline" in s.text.lower() for s in suggestions)


def test_structure_unlinked_character():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Hero")
    c2 = db.create_character(proj.id, "Ghost")
    db.create_scene(proj.id, "S1", character_ids=[c1.id])
    suggestions = _structure_suggestions(db, proj.id)
    assert any("Ghost" in s.text for s in suggestions)


def test_structure_all_good():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "A")
    for i in range(4):
        db.create_scene(
            proj.id, f"S{i}",
            act="Act 1" if i < 2 else "Act 2",
            plotline="Main",
            goal="Goal",
            character_ids=[c1.id],
        )
    suggestions = _structure_suggestions(db, proj.id)
    # Should have few or no suggestions
    assert len(suggestions) <= 2


# -- Balance mode suggestions -------------------------------------------------

def test_balance_dominant_character():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Hero")
    c2 = db.create_character(proj.id, "Side")
    c3 = db.create_character(proj.id, "Extra")
    # Hero in 8/9 scenes, Side in 1, Extra in 0 -> Hero flagged dominant
    for i in range(8):
        db.create_scene(proj.id, f"S{i}", plotline="Main", character_ids=[c1.id])
    db.create_scene(proj.id, "S8", plotline="Main", character_ids=[c2.id])
    suggestions = _balance_suggestions(db, proj.id)
    assert any("dominates" in s.text.lower() or "Hero" in s.text for s in suggestions)


def test_balance_underused_character():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Hero")
    c2 = db.create_character(proj.id, "Ghost")
    for i in range(8):
        db.create_scene(proj.id, f"S{i}", plotline="Main", character_ids=[c1.id])
    suggestions = _balance_suggestions(db, proj.id)
    assert any("Ghost" in s.text or "reintroduce" in s.text.lower() for s in suggestions)


def test_balance_thin_arc():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Hero")
    for i in range(6):
        db.create_scene(proj.id, f"S{i}", plotline="Main", act=f"Act {i//2+1}",
                        character_ids=[c1.id])
    db.create_scene(proj.id, "Orphan", plotline="Thin", character_ids=[c1.id])
    suggestions = _balance_suggestions(db, proj.id)
    assert any("needs development" in s.text.lower() for s in suggestions)


def test_balance_monotony():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "A")
    c2 = db.create_character(proj.id, "B")
    for i in range(6):
        db.create_scene(proj.id, f"S{i}", plotline="Main", character_ids=[c1.id, c2.id])
    suggestions = _balance_suggestions(db, proj.id)
    assert any("streak" in s.text.lower() or "break" in s.text.lower() for s in suggestions)


def test_balance_empty():
    db, proj = _make_project()
    suggestions = _balance_suggestions(db, proj.id)
    assert suggestions == []


# -- Refinement mode suggestions ----------------------------------------------

def test_refinement_no_dialogue():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    db.create_scene(
        proj.id, "S1", content="A" * 300,
        character_ids=[c.id],
    )
    db.create_scene(
        proj.id, "S2", content="B" * 300,
        character_ids=[c.id],
    )
    suggestions = _refinement_suggestions(db, proj.id)
    assert any("dialogue" in s.text.lower() for s in suggestions)


def test_refinement_short_scene():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    db.create_scene(
        proj.id, "Long", content="X" * 500,
        character_ids=[c.id],
    )
    db.create_scene(
        proj.id, "Short", content="Y" * 100,
        character_ids=[c.id],
    )
    suggestions = _refinement_suggestions(db, proj.id)
    assert any("Short" in s.text or "thin" in s.text.lower() for s in suggestions)


def test_refinement_stagnant_state():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    for i in range(4):
        db.create_scene(
            proj.id, f"S{i}",
            character_ids=[c.id],
            character_states=[(c.id, "angry")],
        )
    suggestions = _refinement_suggestions(db, proj.id)
    assert any("Hero" in s.text and "angry" in s.text for s in suggestions)


def test_refinement_empty():
    db, proj = _make_project()
    suggestions = _refinement_suggestions(db, proj.id)
    assert suggestions == []


# -- generate_mode_suggestions integration ------------------------------------

def test_generate_early_project():
    db, proj = _make_project()
    c = db.create_character(proj.id, "A")
    for i in range(3):
        db.create_scene(proj.id, f"S{i}", character_ids=[c.id])
    mode_result, suggestions = generate_mode_suggestions(db, proj.id)
    assert mode_result.mode == AIMode.STRUCTURE
    assert all(s.category == "structure" for s in suggestions)


def test_generate_mid_uneven():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Hero")
    c2 = db.create_character(proj.id, "Ghost")
    for i in range(10):
        act = "Act 1" if i < 5 else "Act 2"
        db.create_scene(proj.id, f"S{i}", act=act, plotline="Main",
                        character_ids=[c1.id])
    mode_result, suggestions = generate_mode_suggestions(db, proj.id)
    assert mode_result.mode in (AIMode.BALANCE, AIMode.STRUCTURE)
    assert len(suggestions) <= MAX_SUGGESTIONS


def test_generate_late_balanced():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "A")
    c2 = db.create_character(proj.id, "B")
    for i in range(21):
        act = "Act 1" if i < 7 else ("Act 2" if i < 14 else "Act 3")
        pl = "Main" if i % 2 == 0 else "Sub"
        db.create_scene(proj.id, f"S{i}", act=act, plotline=pl,
                        character_ids=[c1.id, c2.id])
    mode_result, suggestions = generate_mode_suggestions(db, proj.id)
    assert mode_result.mode == AIMode.REFINEMENT
    assert all(s.category == "refinement" for s in suggestions)


def test_max_suggestions_cap():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    for i in range(3):
        db.create_scene(proj.id, f"S{i}", character_ids=[c.id])
    _, suggestions = generate_mode_suggestions(db, proj.id)
    assert len(suggestions) <= MAX_SUGGESTIONS


# -- Same scene different mode demonstration ----------------------------------

def test_same_data_different_suggestions_per_mode():
    """Verify that the three generators produce different outputs for same data."""
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Hero")
    c2 = db.create_character(proj.id, "Ghost")
    for i in range(8):
        db.create_scene(
            proj.id, f"S{i}",
            act="Act 1" if i < 4 else "Act 2",
            plotline="Main",
            content="Some text " * 30,
            character_ids=[c1.id],
        )
    structure = _structure_suggestions(db, proj.id)
    balance = _balance_suggestions(db, proj.id)
    refinement = _refinement_suggestions(db, proj.id)

    # Each mode produces categorized suggestions
    assert all(s.category == "structure" for s in structure)
    assert all(s.category == "balance" for s in balance)
    assert all(s.category == "refinement" for s in refinement)

    # Texts are different across modes
    s_texts = {s.text for s in structure}
    b_texts = {s.text for s in balance}
    r_texts = {s.text for s in refinement}
    assert s_texts != b_texts or s_texts != r_texts


# -- ModeSuggestionsView widget -----------------------------------------------

def test_view_construction():
    db, proj = _make_project()
    c = db.create_character(proj.id, "A")
    for i in range(3):
        db.create_scene(proj.id, f"S{i}", character_ids=[c.id])
    view = ModeSuggestionsView(db, proj.id)
    assert view.get_mode_result() is not None
    assert view.get_mode_result().mode == AIMode.STRUCTURE


def test_view_empty_project():
    db, proj = _make_project()
    view = ModeSuggestionsView(db, proj.id)
    assert view.get_mode_result() is not None


def test_view_refresh():
    db, proj = _make_project()
    view = ModeSuggestionsView(db, proj.id)
    c = db.create_character(proj.id, "A")
    for i in range(5):
        db.create_scene(proj.id, f"S{i}", character_ids=[c.id])
    view.refresh()
    assert len(view.get_suggestions()) > 0


# -- Theme styles -------------------------------------------------------------

def test_theme_has_mode_view():
    ss = theme.build_stylesheet()
    assert "#modeSuggestionsView" in ss


def test_theme_has_mode_badge():
    ss = theme.build_stylesheet()
    assert "#modeBadge" in ss


def test_theme_has_mode_suggestion_row():
    ss = theme.build_stylesheet()
    assert "#modeSuggestionRow" in ss


def test_theme_has_mode_suggestion_text():
    ss = theme.build_stylesheet()
    assert "#modeSuggestionText" in ss
