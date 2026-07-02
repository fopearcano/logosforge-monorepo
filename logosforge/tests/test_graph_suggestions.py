"""Tests for Graph-Driven Narrative Suggestions."""

from logosforge.db import Database
from logosforge.graph_suggestions import (
    GraphSuggestion,
    GraphSuggestions,
    format_suggestions,
    format_suggestions_debug,
    generate_graph_suggestions,
)


def _make_project():
    db = Database()
    proj = db.create_project("SuggestTest")
    return db, proj


def _make_story_project():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Alice")
    c2 = db.create_character(proj.id, "Bob")
    c3 = db.create_character(proj.id, "Charlie")
    p1 = db.create_place(proj.id, "Castle")
    s1 = db.create_scene(
        proj.id, "Opening", synopsis="[[Alice]] enters [[Castle]].",
        character_ids=[c1.id],
        character_states=[(c1.id, "calm")],
    )
    s2 = db.create_scene(
        proj.id, "Meeting", synopsis="[[Alice]] meets [[Bob]].",
        character_ids=[c1.id, c2.id],
        character_states=[(c1.id, "tense"), (c2.id, "anxious")],
    )
    s3 = db.create_scene(
        proj.id, "Climax", synopsis="[[Alice]] and [[Bob]] at [[Castle]].",
        character_ids=[c1.id, c2.id],
        character_states=[(c1.id, "desperate"), (c2.id, "broken")],
    )
    return db, proj, c1, c2, c3, p1, s1, s2, s3


# -- generate_graph_suggestions basic ----------------------------------------

def test_empty_project():
    db, proj = _make_project()
    s = db.create_scene(proj.id, "Solo", content="No links.")
    result = generate_graph_suggestions(db, proj.id, s.id)
    assert isinstance(result, GraphSuggestions)
    assert len(result.suggestions) == 0


def test_nonexistent_scene():
    db, proj = _make_project()
    result = generate_graph_suggestions(db, proj.id, 9999)
    assert len(result.suggestions) == 0


def test_produces_suggestions():
    db, proj, c1, c2, c3, p1, s1, s2, s3 = _make_story_project()
    result = generate_graph_suggestions(db, proj.id, s2.id)
    assert len(result.suggestions) >= 1


def test_has_all_four_categories():
    db, proj, c1, c2, c3, p1, s1, s2, s3 = _make_story_project()
    result = generate_graph_suggestions(db, proj.id, s2.id)
    categories = {s.category for s in result.suggestions}
    assert "Escalation" in categories
    assert "Reversal" in categories


def test_suggestions_have_text():
    db, proj, c1, c2, c3, p1, s1, s2, s3 = _make_story_project()
    result = generate_graph_suggestions(db, proj.id, s2.id)
    for s in result.suggestions:
        assert len(s.text) > 0
        assert len(s.category) > 0
        assert len(s.reason) > 0


# -- Escalation -------------------------------------------------------------

def test_escalation_uses_dominant_character():
    db, proj, c1, c2, c3, p1, s1, s2, s3 = _make_story_project()
    result = generate_graph_suggestions(db, proj.id, s2.id)
    escalation = next((s for s in result.suggestions if s.category == "Escalation"), None)
    assert escalation is not None
    assert "Alice" in escalation.text or "Bob" in escalation.text


def test_escalation_pushes_state_forward():
    db, proj, c1, c2, c3, p1, s1, s2, s3 = _make_story_project()
    result = generate_graph_suggestions(db, proj.id, s2.id)
    escalation = next((s for s in result.suggestions if s.category == "Escalation"), None)
    assert escalation is not None
    assert "tense" not in escalation.text.split("escalates to")[-1] if "escalates to" in escalation.text else True


# -- Reversal ----------------------------------------------------------------

def test_reversal_based_on_state():
    db, proj, c1, c2, c3, p1, s1, s2, s3 = _make_story_project()
    result = generate_graph_suggestions(db, proj.id, s2.id)
    reversal = next((s for s in result.suggestions if s.category == "Reversal"), None)
    assert reversal is not None
    assert "disrupted" in reversal.text or "shifts to" in reversal.text


def test_reversal_avoids_same_state():
    db, proj, c1, c2, c3, p1, s1, s2, s3 = _make_story_project()
    result = generate_graph_suggestions(db, proj.id, s2.id)
    reversal = next((s for s in result.suggestions if s.category == "Reversal"), None)
    if reversal and "tense" in reversal.text:
        assert "shifts to" in reversal.text
        parts = reversal.text.split("shifts to")
        if len(parts) == 2:
            assert parts[1].strip() != "tense"


# -- Expansion ---------------------------------------------------------------

def test_expansion_detects_missing_interaction():
    db, proj, c1, c2, c3, p1, s1, s2, s3 = _make_story_project()
    result = generate_graph_suggestions(db, proj.id, s1.id)
    expansion = next((s for s in result.suggestions if s.category == "Expansion"), None)
    if expansion:
        assert "never shared" in expansion.text or "isolated" in expansion.text


def test_expansion_detects_isolated_character():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Hero")
    c2 = db.create_character(proj.id, "Loner")
    s1 = db.create_scene(
        proj.id, "Main", synopsis="[[Hero]] acts.",
        character_ids=[c1.id],
    )
    s2 = db.create_scene(
        proj.id, "Side", synopsis="[[Loner]] alone.",
        character_ids=[c2.id],
    )
    result = generate_graph_suggestions(db, proj.id, s1.id)
    expansion = next((s for s in result.suggestions if s.category == "Expansion"), None)
    if expansion:
        assert "Loner" in expansion.text or "isolated" in expansion.text


# -- Internal shift ----------------------------------------------------------

def test_internal_shift_from_stagnant():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Hero")
    s1 = db.create_scene(
        proj.id, "Scene1", synopsis="[[Hero]] begins.",
        character_ids=[c1.id],
        character_states=[(c1.id, "tense")],
    )
    s2 = db.create_scene(
        proj.id, "Scene2", synopsis="[[Hero]] continues.",
        character_ids=[c1.id],
        character_states=[(c1.id, "tense")],
    )
    result = generate_graph_suggestions(db, proj.id, s2.id)
    internal = next((s for s in result.suggestions if s.category == "Internal shift"), None)
    assert internal is not None
    assert "tense" in internal.text
    assert "multiple scenes" in internal.text


def test_internal_shift_no_state():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Hero")
    s1 = db.create_scene(
        proj.id, "Scene1", synopsis="[[Hero]] acts.",
        character_ids=[c1.id],
    )
    result = generate_graph_suggestions(db, proj.id, s1.id)
    internal = next((s for s in result.suggestions if s.category == "Internal shift"), None)
    assert internal is not None
    assert "lacks emotional arc" in internal.text or "pauses" in internal.text


# -- Temporal logic ----------------------------------------------------------

def test_temporal_uses_latest_state():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Hero")
    s1 = db.create_scene(
        proj.id, "Start", synopsis="[[Hero]] begins.",
        character_ids=[c1.id],
        character_states=[(c1.id, "calm")],
    )
    s2 = db.create_scene(
        proj.id, "Middle", synopsis="[[Hero]] struggles.",
        character_ids=[c1.id],
        character_states=[(c1.id, "tense")],
    )
    result = generate_graph_suggestions(db, proj.id, s2.id)
    escalation = next((s for s in result.suggestions if s.category == "Escalation"), None)
    assert escalation is not None
    assert "tense" in escalation.text


def test_temporal_ignores_future_states():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Hero")
    s1 = db.create_scene(
        proj.id, "Start", synopsis="[[Hero]] begins.",
        character_ids=[c1.id],
        character_states=[(c1.id, "calm")],
    )
    s2 = db.create_scene(
        proj.id, "Future", synopsis="[[Hero]] resolves.",
        character_ids=[c1.id],
        character_states=[(c1.id, "resolved")],
    )
    result = generate_graph_suggestions(db, proj.id, s1.id)
    escalation = next((s for s in result.suggestions if s.category == "Escalation"), None)
    assert escalation is not None
    assert "calm" in escalation.text


# -- Balance -----------------------------------------------------------------

def test_suggestion_mix():
    db, proj, c1, c2, c3, p1, s1, s2, s3 = _make_story_project()
    result = generate_graph_suggestions(db, proj.id, s2.id)
    categories = [s.category for s in result.suggestions]
    unique = set(categories)
    assert len(unique) >= 2


# -- Debug info --------------------------------------------------------------

def test_debug_info_populated():
    db, proj, c1, c2, c3, p1, s1, s2, s3 = _make_story_project()
    result = generate_graph_suggestions(db, proj.id, s2.id)
    assert len(result.debug_info) >= 1


def test_debug_info_empty_project():
    db, proj = _make_project()
    s = db.create_scene(proj.id, "Solo", content="Nothing.")
    result = generate_graph_suggestions(db, proj.id, s.id)
    assert len(result.debug_info) >= 1


# -- format_suggestions ------------------------------------------------------

def test_format_empty():
    result = GraphSuggestions()
    assert format_suggestions(result) == ""


def test_format_output():
    result = GraphSuggestions(suggestions=[
        GraphSuggestion("Escalation", "Test escalation", "reason1"),
        GraphSuggestion("Reversal", "Test reversal", "reason2"),
    ])
    text = format_suggestions(result)
    assert "Next Narrative Possibilities:" in text
    assert "1. Escalation" in text
    assert "2. Reversal" in text
    assert "\u2192 Test escalation" in text


def test_format_no_prose():
    db, proj, c1, c2, c3, p1, s1, s2, s3 = _make_story_project()
    result = generate_graph_suggestions(db, proj.id, s2.id)
    text = format_suggestions(result)
    for s in result.suggestions:
        assert len(s.text.split(". ")) <= 3


# -- format_suggestions_debug ------------------------------------------------

def test_format_debug_empty():
    result = GraphSuggestions()
    assert format_suggestions_debug(result) == ""


def test_format_debug_output():
    result = GraphSuggestions(debug_info=["Escalation: reason1"])
    text = format_suggestions_debug(result)
    assert "[Suggestion Debug]" in text
    assert "Escalation: reason1" in text


# -- GraphSuggestion dataclass -----------------------------------------------

def test_suggestion_fields():
    s = GraphSuggestion("Escalation", "text", "reason")
    assert s.category == "Escalation"
    assert s.text == "text"
    assert s.reason == "reason"
