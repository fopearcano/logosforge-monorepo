"""Tests for Graph Feedback Loop — visual + AI integration."""

from logosforge.db import Database
from logosforge.graph_suggestions import (
    GraphSuggestion,
    GraphSuggestions,
    generate_graph_suggestions,
)
from logosforge.ui import theme
from logosforge.ui.focus_graph_view import FocusGraphView


def _make_project():
    db = Database()
    proj = db.create_project("FeedbackTest")
    return db, proj


def _make_story():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Alice")
    c2 = db.create_character(proj.id, "Bob")
    c3 = db.create_character(proj.id, "Charlie")
    s1 = db.create_scene(
        proj.id, "Opening", synopsis="[[Alice]] begins.",
        character_ids=[c1.id],
        character_states=[(c1.id, "calm")],
    )
    s2 = db.create_scene(
        proj.id, "Meeting", synopsis="[[Alice]] meets [[Bob]].",
        character_ids=[c1.id, c2.id],
        character_states=[(c1.id, "tense"), (c2.id, "anxious")],
    )
    s3 = db.create_scene(
        proj.id, "Alone", synopsis="[[Charlie]] isolated.",
        character_ids=[c3.id],
    )
    return db, proj, c1, c2, c3, s1, s2, s3


# -- Trace nodes in suggestions ---------------------------------------------

def test_suggestions_have_trace_nodes():
    db, proj, c1, c2, c3, s1, s2, s3 = _make_story()
    result = generate_graph_suggestions(db, proj.id, s2.id)
    for s in result.suggestions:
        assert isinstance(s.trace_nodes, list)


def test_escalation_traces_dominant_char():
    db, proj, c1, c2, c3, s1, s2, s3 = _make_story()
    result = generate_graph_suggestions(db, proj.id, s2.id)
    escalation = next((s for s in result.suggestions if s.category == "Escalation"), None)
    assert escalation is not None
    assert len(escalation.trace_nodes) >= 1
    assert escalation.trace_nodes[0].startswith("Character:")


def test_reversal_traces_character():
    db, proj, c1, c2, c3, s1, s2, s3 = _make_story()
    result = generate_graph_suggestions(db, proj.id, s2.id)
    reversal = next((s for s in result.suggestions if s.category == "Reversal"), None)
    assert reversal is not None
    assert len(reversal.trace_nodes) >= 1


def test_expansion_traces_both_chars():
    db, proj, c1, c2, c3, s1, s2, s3 = _make_story()
    result = generate_graph_suggestions(db, proj.id, s2.id)
    expansion = next((s for s in result.suggestions if s.category == "Expansion"), None)
    if expansion:
        assert len(expansion.trace_nodes) >= 1


def test_internal_traces_character():
    db, proj, c1, c2, c3, s1, s2, s3 = _make_story()
    result = generate_graph_suggestions(db, proj.id, s2.id)
    internal = next((s for s in result.suggestions if s.category == "Internal shift"), None)
    if internal:
        assert len(internal.trace_nodes) >= 1
        assert internal.trace_nodes[0].startswith("Character:")


# -- FocusGraphView suggestion panel -----------------------------------------

def test_suggestion_panel_hidden_by_default():
    db, proj, *_ = _make_story()
    view = FocusGraphView(db, proj.id)
    assert not view.is_suggestions_visible()
    assert view._suggest_panel.isHidden()


def test_suggestion_toggle_shows_panel():
    db, proj, *_ = _make_story()
    view = FocusGraphView(db, proj.id)
    view._on_suggestions_toggled(True)
    assert view.is_suggestions_visible()
    assert not view._suggest_panel.isHidden()


def test_suggestion_toggle_hides_panel():
    db, proj, *_ = _make_story()
    view = FocusGraphView(db, proj.id)
    view._on_suggestions_toggled(True)
    view._on_suggestions_toggled(False)
    assert not view.is_suggestions_visible()
    assert view._suggest_panel.isHidden()


def test_suggestions_populated_on_scene_focus():
    db, proj, c1, c2, c3, s1, s2, s3 = _make_story()
    view = FocusGraphView(db, proj.id)
    view._on_suggestions_toggled(True)
    view.focus_on(f"Scene:{s2.id}")
    suggestions = view.get_suggestions()
    assert suggestions is not None
    assert len(suggestions.suggestions) >= 1


def test_suggestions_empty_without_scene_focus():
    db, proj, c1, c2, c3, s1, s2, s3 = _make_story()
    view = FocusGraphView(db, proj.id)
    view._on_suggestions_toggled(True)
    view.focus_on(f"Character:{c1.id}")
    suggestions = view.get_suggestions()
    # Should still find a scene (falls back to first scene in graph)
    assert suggestions is not None


# -- Highlight trace ---------------------------------------------------------

def test_highlight_trace_sets_nodes():
    db, proj, c1, c2, c3, s1, s2, s3 = _make_story()
    view = FocusGraphView(db, proj.id)
    trace = [f"Character:{c1.id}"]
    view.highlight_trace(trace)
    assert view.get_trace_highlight() == trace


def test_clear_trace_resets():
    db, proj, c1, c2, c3, s1, s2, s3 = _make_story()
    view = FocusGraphView(db, proj.id)
    trace = [f"Character:{c1.id}"]
    view.highlight_trace(trace)
    view.clear_trace()
    assert view.get_trace_highlight() == []


def test_suggestion_click_focuses_and_highlights():
    db, proj, c1, c2, c3, s1, s2, s3 = _make_story()
    view = FocusGraphView(db, proj.id)
    view._on_suggestions_toggled(True)
    view.focus_on(f"Scene:{s2.id}")
    suggestions = view.get_suggestions()
    if suggestions and suggestions.suggestions:
        first = suggestions.suggestions[0]
        view._on_suggestion_clicked(first)
        if first.trace_nodes:
            assert view.get_trace_highlight() == first.trace_nodes


def test_toggle_off_clears_trace():
    db, proj, c1, c2, c3, s1, s2, s3 = _make_story()
    view = FocusGraphView(db, proj.id)
    view._on_suggestions_toggled(True)
    view.highlight_trace([f"Character:{c1.id}"])
    view._on_suggestions_toggled(False)
    assert view.get_trace_highlight() == []


def test_new_suggestion_click_clears_old_trace():
    db, proj, c1, c2, c3, s1, s2, s3 = _make_story()
    view = FocusGraphView(db, proj.id)
    view._on_suggestions_toggled(True)
    view.focus_on(f"Scene:{s2.id}")
    view.highlight_trace([f"Character:{c1.id}"])
    suggestions = view.get_suggestions()
    if suggestions and len(suggestions.suggestions) >= 2:
        second = suggestions.suggestions[1]
        view._on_suggestion_clicked(second)
        assert f"Character:{c1.id}" not in view.get_trace_highlight() or \
               view.get_trace_highlight() == second.trace_nodes


# -- Tooltip shows trace info ------------------------------------------------

def test_suggestion_tooltip_content():
    s = GraphSuggestion(
        "Escalation",
        "Alice escalates",
        "dominant char",
        ["Character:1"],
    )
    assert s.trace_nodes == ["Character:1"]
    assert s.reason == "dominant char"


# -- Theme styles for suggest panel ------------------------------------------

def test_theme_has_suggest_panel():
    ss = theme.build_stylesheet()
    assert "#suggestPanel" in ss


def test_theme_has_suggest_btn():
    ss = theme.build_stylesheet()
    assert "#suggestBtn" in ss


def test_theme_has_suggest_desc():
    ss = theme.build_stylesheet()
    assert "#suggestDesc" in ss


def test_theme_has_suggest_header():
    ss = theme.build_stylesheet()
    assert "#suggestHeader" in ss
