"""Tests for Graph-Aware AI Context."""

from logosforge.assistant import build_messages
from logosforge.context_builder import (
    gather_graph_context,
    gather_graph_context_debug,
    GRAPH_DIRECT_MAX,
    GRAPH_HIGH_INFLUENCE_MAX,
    GRAPH_ISOLATED_MAX,
)
from logosforge.db import Database


def _make_project():
    db = Database()
    proj = db.create_project("GraphCtxTest")
    return db, proj


def _make_linked_project():
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


# -- gather_graph_context output structure -----------------------------------

def test_graph_context_empty_project():
    db, proj = _make_project()
    s = db.create_scene(proj.id, "Solo", content="No links.")
    result = gather_graph_context(db, proj.id, s.id)
    assert result == ""


def test_graph_context_has_header():
    db, proj, c1, c2, c3, p1, s1, s2, s3 = _make_linked_project()
    result = gather_graph_context(db, proj.id, s1.id)
    assert "[Graph Context]" in result


def test_graph_context_shows_current_scene():
    db, proj, c1, c2, c3, p1, s1, s2, s3 = _make_linked_project()
    result = gather_graph_context(db, proj.id, s1.id)
    assert "Current: Opening" in result


def test_graph_context_shows_connections():
    db, proj, c1, c2, c3, p1, s1, s2, s3 = _make_linked_project()
    result = gather_graph_context(db, proj.id, s1.id)
    assert "Connected to:" in result
    assert "Alice" in result


def test_graph_context_character_state_included():
    db, proj, c1, c2, c3, p1, s1, s2, s3 = _make_linked_project()
    result = gather_graph_context(db, proj.id, s3.id)
    assert "[desperate]" in result or "[broken]" in result


def test_graph_context_no_scene_in_graph():
    db, proj = _make_project()
    db.create_character(proj.id, "Unused")
    s = db.create_scene(proj.id, "Isolated", content="No links at all.")
    result = gather_graph_context(db, proj.id, s.id)
    assert result == ""


def test_graph_context_weakly_connected():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Loner")
    c2 = db.create_character(proj.id, "Hero")
    p1 = db.create_place(proj.id, "Village")
    s1 = db.create_scene(
        proj.id, "Main", synopsis="[[Hero]] in [[Village]].",
        character_ids=[c2.id],
    )
    s2 = db.create_scene(
        proj.id, "Side", synopsis="[[Loner]] alone.",
        character_ids=[c1.id],
    )
    result = gather_graph_context(db, proj.id, s1.id)
    assert "Weakly connected:" in result or "Loner" in result


def test_graph_context_high_influence():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Hub")
    scenes = []
    for i in range(5):
        s = db.create_scene(
            proj.id, f"Scene{i}", synopsis=f"[[Hub]] does thing {i}.",
            character_ids=[c1.id],
        )
        scenes.append(s)
    result = gather_graph_context(db, proj.id, scenes[0].id)
    assert "Hub" in result


# -- Prioritization ----------------------------------------------------------

def test_current_scene_always_first():
    db, proj, c1, c2, c3, p1, s1, s2, s3 = _make_linked_project()
    result = gather_graph_context(db, proj.id, s2.id)
    lines = result.split("\n")
    current_line = next(l for l in lines if "Current:" in l)
    assert "Meeting" in current_line


def test_direct_before_indirect():
    db, proj, c1, c2, c3, p1, s1, s2, s3 = _make_linked_project()
    result = gather_graph_context(db, proj.id, s1.id)
    connected_idx = result.find("Connected to:")
    high_idx = result.find("High influence:")
    if high_idx >= 0:
        assert connected_idx < high_idx


# -- Limits ------------------------------------------------------------------

def test_max_direct_limit():
    assert GRAPH_DIRECT_MAX == 8


def test_max_high_influence_limit():
    assert GRAPH_HIGH_INFLUENCE_MAX == 3


def test_max_isolated_limit():
    assert GRAPH_ISOLATED_MAX == 3


# -- Debug transparency ------------------------------------------------------

def test_debug_returns_list():
    db, proj, c1, c2, c3, p1, s1, s2, s3 = _make_linked_project()
    entries = gather_graph_context_debug(db, proj.id, s1.id)
    assert isinstance(entries, list)
    assert len(entries) > 0


def test_debug_focal_first():
    db, proj, c1, c2, c3, p1, s1, s2, s3 = _make_linked_project()
    entries = gather_graph_context_debug(db, proj.id, s1.id)
    assert entries[0]["reason"] == "focal (current scene)"
    assert entries[0]["name"] == "Opening"


def test_debug_direct_connections():
    db, proj, c1, c2, c3, p1, s1, s2, s3 = _make_linked_project()
    entries = gather_graph_context_debug(db, proj.id, s1.id)
    direct = [e for e in entries if "direct connection" in e["reason"]]
    assert len(direct) > 0


def test_debug_includes_node_ids():
    db, proj, c1, c2, c3, p1, s1, s2, s3 = _make_linked_project()
    entries = gather_graph_context_debug(db, proj.id, s1.id)
    for entry in entries:
        assert "node_id" in entry
        assert "name" in entry
        assert "reason" in entry


def test_debug_empty_project():
    db, proj = _make_project()
    s = db.create_scene(proj.id, "Empty", content="Nothing.")
    entries = gather_graph_context_debug(db, proj.id, s.id)
    assert entries == []


# -- Integration with build_messages -----------------------------------------

def test_build_messages_includes_graph_context():
    msgs = build_messages(
        "Write a paragraph",
        "[Scene Context]\nTitle: Test",
        graph_context="[Graph Context]\nCurrent: Test\nConnected to: Alice (character)",
    )
    user_content = msgs[1]["content"]
    assert "[Graph Context]" in user_content
    assert "Connected to: Alice" in user_content


def test_build_messages_graph_context_before_scene():
    msgs = build_messages(
        "Write",
        "[Scene Context]\nTitle: Test",
        graph_context="[Graph Context]\nCurrent: Test",
    )
    user_content = msgs[1]["content"]
    graph_idx = user_content.find("[Graph Context]")
    scene_idx = user_content.find("[Scene Context]")
    assert graph_idx < scene_idx


def test_build_messages_empty_graph_omitted():
    msgs = build_messages(
        "Write",
        "[Scene Context]\nTitle: Test",
        graph_context="",
    )
    user_content = msgs[1]["content"]
    assert "[Graph Context]" not in user_content


# -- gather_graph_context with character states at different points -----------

def test_character_state_temporal():
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
    s3 = db.create_scene(
        proj.id, "End", synopsis="[[Hero]] breaks.",
        character_ids=[c1.id],
        character_states=[(c1.id, "broken")],
    )
    result_s1 = gather_graph_context(db, proj.id, s1.id)
    result_s3 = gather_graph_context(db, proj.id, s3.id)
    assert "[calm]" in result_s1
    assert "[broken]" in result_s3


def test_graph_context_scene_not_in_graph():
    db, proj = _make_project()
    s = db.create_scene(proj.id, "NoLinks", synopsis="No [[links]] here at all.")
    result = gather_graph_context(db, proj.id, s.id)
    assert result == "" or "[Graph Context]" in result
