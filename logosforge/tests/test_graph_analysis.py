"""Tests for graph_analysis — per-node analysis + global insights + view wiring."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from logosforge.db import Database
from logosforge.graph_analysis import (
    NodeAnalysis,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    analyze_node,
    compose_assistant_context,
    explain_structure,
    find_disconnected_nodes,
    find_weak_thematic_clusters,
    suggest_missing_relations,
)
from logosforge.ui.focus_graph_view import (
    FocusGraphView,
    GraphData,
    GraphEdge,
    GraphNode,
    build_graph_data,
)


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_project():
    db = Database()
    proj = db.create_project("Analysis")
    alice = db.create_character(proj.id, "Alice")
    bob = db.create_character(proj.id, "Bob")
    carol = db.create_character(proj.id, "Carol")
    castle = db.create_place(proj.id, "Castle")
    s1 = db.create_scene(proj.id, "Opening", act="Act I",
                         character_ids=[alice.id, bob.id], place_ids=[castle.id],
                         plotline="Main")
    s2 = db.create_scene(proj.id, "Inciting", act="Act I",
                         character_ids=[alice.id, bob.id],
                         plotline="Main")
    s3 = db.create_scene(proj.id, "Midpoint", act="Act II",
                         character_ids=[alice.id], plotline="Main")
    s4 = db.create_scene(proj.id, "Climax", act="Act III",
                         character_ids=[alice.id, carol.id],
                         plotline="Side")
    justice = db.create_psyke_entry(proj.id, "Justice", "theme")
    lore = db.create_psyke_entry(proj.id, "Old Law", "lore")
    db.add_psyke_relation(justice.id, lore.id)
    return db, proj, alice, bob, carol, castle, s1, s2, s3, s4, justice, lore


# -- analyze_node -----------------------------------------------------------

def test_analyze_node_returns_none_for_unknown():
    db, proj, *_ = _make_project()
    data = build_graph_data(db, proj.id)
    assert analyze_node(db, proj.id, data, "Nope:999") is None


def test_analyze_character_lists_scenes_and_arcs():
    db, proj, alice, *_ = _make_project()
    data = build_graph_data(db, proj.id)
    a = analyze_node(db, proj.id, data, f"Character:{alice.id}")
    assert a is not None
    assert a.name == "Alice"
    assert a.kind == "character"
    # Alice appears in 4 scenes → all 4 should be listed.
    assert len(a.scenes) == 4
    assert set(a.arcs) >= {"Main", "Side"}


def test_analyze_theme_psyke_lists_related_lore():
    db, proj, *_, justice, lore = _make_project()
    data = build_graph_data(db, proj.id)
    a = analyze_node(db, proj.id, data, f"PSYKE:{justice.id}")
    assert a is not None
    assert a.kind == "theme"
    # Lore is a related PSYKE entry — should appear in `relations`.
    assert any("Old Law" in r for r in a.relations)


def test_analyze_scene_picks_up_ci_alignment():
    db = Database()
    proj = db.create_project("CI Scene Analysis")
    c = db.create_character(proj.id, "Hero")
    s = db.create_scene(proj.id, "Pivot", character_ids=[c.id], content="...")
    from logosforge.controlling_idea import (
        ControllingIdea, save, set_scene_alignment,
    )
    ci = ControllingIdea(enabled=True, value="Truth", cause="x", statement="x x x")
    save(db, proj.id, ci)
    set_scene_alignment(db, proj.id, s.id, "tests")
    data = build_graph_data(db, proj.id)
    a = analyze_node(db, proj.id, data, f"Scene:{s.id}")
    assert a is not None
    assert a.ci_alignment == "tests"


# -- explain_structure ------------------------------------------------------

def test_explain_structure_empty_project():
    db = Database()
    proj = db.create_project("Empty")
    data = build_graph_data(db, proj.id)
    text = explain_structure(db, proj.id, data)
    assert "empty" in text.lower()


def test_explain_structure_mentions_counts():
    db, proj, *_ = _make_project()
    data = build_graph_data(db, proj.id)
    text = explain_structure(db, proj.id, data)
    assert "characters" in text
    assert "scenes" in text


def test_explain_structure_mentions_most_connected():
    db, proj, *_ = _make_project()
    data = build_graph_data(db, proj.id)
    text = explain_structure(db, proj.id, data)
    assert "Most connected" in text


# -- find_disconnected_nodes ------------------------------------------------

def test_disconnected_nodes_empty_when_all_connected():
    db, proj, *_ = _make_project()
    data = build_graph_data(db, proj.id)
    insights = find_disconnected_nodes(data)
    # Everything in the rich project has at least one neighbour.
    assert insights == []


def test_disconnected_nodes_detects_isolated_psyke_entry():
    db = Database()
    proj = db.create_project("Lonely")
    c = db.create_character(proj.id, "Hero")
    db.create_scene(proj.id, "S1", character_ids=[c.id])
    # Add a PSYKE entry with no relations and no mentions.
    db.create_psyke_entry(proj.id, "Solitude", "lore")
    data = build_graph_data(db, proj.id)
    insights = find_disconnected_nodes(data)
    assert len(insights) == 1
    assert insights[0].severity == SEVERITY_WARNING
    assert "Solitude" in insights[0].message


def test_disconnected_nodes_ignores_acts():
    # Acts with no scenes are not in the graph in the first place, so this
    # just sanity-checks the path doesn't surface a normal Act as isolated.
    db, proj, *_ = _make_project()
    data = build_graph_data(db, proj.id)
    insights = find_disconnected_nodes(data)
    for ins in insights:
        for nid in ins.node_ids:
            assert not nid.startswith("Act:")


# -- suggest_missing_relations ----------------------------------------------

def test_suggest_missing_relations_returns_empty_when_no_psyke_chars():
    db, proj, *_ = _make_project()
    data = build_graph_data(db, proj.id)
    # Project has no PSYKE entries for the characters → no suggestions possible.
    insights = suggest_missing_relations(db, proj.id, data)
    assert insights == []


def test_suggest_missing_relations_finds_shared_scenes_without_relation():
    db = Database()
    proj = db.create_project("Suggest")
    alice = db.create_character(proj.id, "Alice")
    bob = db.create_character(proj.id, "Bob")
    # Make PSYKE entries that mirror the characters.
    db.create_psyke_entry(proj.id, "Alice", "character")
    db.create_psyke_entry(proj.id, "Bob", "character")
    # Two shared scenes, no PSYKE relation between them.
    db.create_scene(proj.id, "S1", character_ids=[alice.id, bob.id])
    db.create_scene(proj.id, "S2", character_ids=[alice.id, bob.id])
    data = build_graph_data(db, proj.id)
    insights = suggest_missing_relations(db, proj.id, data)
    assert any("Alice" in i.message and "Bob" in i.message for i in insights)


def test_suggest_missing_relations_skips_when_relation_exists():
    db = Database()
    proj = db.create_project("LinkedSuggest")
    alice = db.create_character(proj.id, "Alice")
    bob = db.create_character(proj.id, "Bob")
    pa = db.create_psyke_entry(proj.id, "Alice", "character")
    pb = db.create_psyke_entry(proj.id, "Bob", "character")
    db.add_psyke_relation(pa.id, pb.id)
    db.create_scene(proj.id, "S1", character_ids=[alice.id, bob.id])
    db.create_scene(proj.id, "S2", character_ids=[alice.id, bob.id])
    data = build_graph_data(db, proj.id)
    insights = suggest_missing_relations(db, proj.id, data)
    assert not any("Alice" in i.message and "Bob" in i.message for i in insights)


# -- find_weak_thematic_clusters --------------------------------------------

def test_weak_thematic_clusters_detects_act_imbalance():
    db = Database()
    proj = db.create_project("Weak")
    c = db.create_character(proj.id, "Hero")
    db.create_scene(proj.id, "S1", act="Act I",
                    character_ids=[c.id], synopsis="The Justice was on his mind.")
    db.create_scene(proj.id, "S2", act="Act I",
                    character_ids=[c.id], synopsis="More about Justice arose.")
    db.create_scene(proj.id, "S3", act="Act II", character_ids=[c.id],
                    synopsis="A normal day, no theme involved.")
    db.create_scene(proj.id, "S4", act="Act III", character_ids=[c.id],
                    synopsis="A normal evening.")
    db.create_psyke_entry(proj.id, "Justice", "theme")
    data = build_graph_data(db, proj.id)
    insights = find_weak_thematic_clusters(db, proj.id, data)
    assert any(
        "Justice" in i.title and "absent" in i.message
        for i in insights
    )


def test_weak_thematic_clusters_no_themes_returns_empty():
    db, proj, *_ = _make_project()
    # Drop the existing theme so the project has none.
    db_no_theme = Database()
    p = db_no_theme.create_project("No theme")
    c = db_no_theme.create_character(p.id, "Hero")
    db_no_theme.create_scene(p.id, "S1", act="Act I", character_ids=[c.id])
    data = build_graph_data(db_no_theme, p.id)
    assert find_weak_thematic_clusters(db_no_theme, p.id, data) == []


# -- compose_assistant_context ----------------------------------------------

def test_compose_node_analysis_includes_key_lines():
    na = NodeAnalysis(
        node_id="Character:1", name="Alice", kind="character",
        themes=["Justice"], relations=["Bob (character)"],
        scenes=["Opening", "Climax"], arcs=["Main"],
        ci_alignment="supports",
    )
    text = compose_assistant_context(na)
    assert "[Graph Analysis: Alice]" in text
    assert "Justice" in text
    assert "Bob" in text
    assert "Opening" in text
    assert "Main" in text
    assert "supports" in text


def test_compose_insights_empty_lists():
    text = compose_assistant_context([])
    assert "No issues detected" in text


def test_compose_insights_marks_warnings():
    from logosforge.graph_analysis import GraphInsight
    text = compose_assistant_context([
        GraphInsight("T", SEVERITY_WARNING, "msg"),
    ])
    assert "T" in text
    assert "msg" in text


# -- View integration --------------------------------------------------------

def test_view_analysis_panel_starts_hidden():
    db, proj, *_ = _make_project()
    view = FocusGraphView(db, proj.id)
    assert not view.is_analysis_visible()
    assert not view._analysis_panel.isVisible()


def test_view_analysis_toggle_shows_panel():
    db, proj, *_ = _make_project()
    view = FocusGraphView(db, proj.id)
    view.show()
    view._on_analysis_toggled(True)
    assert view.is_analysis_visible()


def test_view_analysis_panel_populates_on_focus():
    db, proj, alice, *_ = _make_project()
    view = FocusGraphView(db, proj.id)
    view._on_analysis_toggled(True)
    view.focus_on(f"Character:{alice.id}")
    na = view.get_last_node_analysis()
    assert na is not None
    assert na.name == "Alice"


def test_view_send_to_assistant_callback_fires():
    db, proj, alice, *_ = _make_project()
    sent: list[str] = []
    view = FocusGraphView(
        db, proj.id,
        on_send_to_assistant=lambda t: sent.append(t),
    )
    view._on_analysis_toggled(True)
    view.focus_on(f"Character:{alice.id}")
    view._send_node_to_assistant()
    assert sent
    assert "Alice" in sent[0]


def test_view_send_insights_to_assistant():
    db, proj, *_ = _make_project()
    sent: list[str] = []
    view = FocusGraphView(
        db, proj.id,
        on_send_to_assistant=lambda t: sent.append(t),
    )
    view._on_analysis_toggled(True)
    view._send_insights_to_assistant()
    assert sent
    assert "[Graph Insights]" in sent[0]


def test_view_send_to_assistant_no_op_without_callback():
    """When no callback is wired the helpers silently skip — no exception."""
    db, proj, alice, *_ = _make_project()
    view = FocusGraphView(db, proj.id)
    view._on_analysis_toggled(True)
    view.focus_on(f"Character:{alice.id}")
    # Should not raise even though no on_send_to_assistant was given.
    view._send_node_to_assistant()
    view._send_insights_to_assistant()
