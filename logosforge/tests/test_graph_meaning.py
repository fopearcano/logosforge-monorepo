"""Tests for Graph Meaning Layer — narrative insight."""

from logosforge.db import Database
from logosforge.graph_meaning import (
    MeaningData,
    NodeMeaning,
    compute_meaning,
    importance_radius_delta,
    state_color,
    warmth_from_state,
)
from logosforge.ui.focus_graph_view import (
    FocusGraphView,
    build_graph_data,
    _arc_color,
)


def _make_project():
    db = Database()
    proj = db.create_project("MeaningTest")
    return db, proj


def _make_full_project():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Alice")
    c2 = db.create_character(proj.id, "Bob")
    p1 = db.create_place(proj.id, "Castle")
    s1 = db.create_scene(
        proj.id, "Opening", synopsis="[[Alice]] enters [[Castle]].",
        beat="Hook", tags="setup,intro",
        plotline="Main",
        character_ids=[c1.id],
        character_states=[(c1.id, "calm")],
    )
    s2 = db.create_scene(
        proj.id, "Rising", synopsis="[[Alice]] meets [[Bob]].",
        beat="Inciting", tags="action",
        plotline="Main",
        character_ids=[c1.id, c2.id],
        character_states=[(c1.id, "tense"), (c2.id, "anxious")],
    )
    s3 = db.create_scene(
        proj.id, "Midpoint", synopsis="[[Bob]] at [[Castle]].",
        tags="twist",
        plotline="Sub",
        character_ids=[c2.id],
        character_states=[(c2.id, "broken")],
    )
    s4 = db.create_scene(
        proj.id, "Climax", synopsis="[[Alice]] and [[Bob]] fight.",
        beat="Climax", tags="action,climax",
        plotline="Main",
        character_ids=[c1.id, c2.id],
        character_states=[(c1.id, "desperate"), (c2.id, "broken")],
    )
    return db, proj, c1, c2, p1, s1, s2, s3, s4


# -- warmth_from_state -------------------------------------------------------

def test_warmth_calm():
    assert warmth_from_state("calm") == "cool"


def test_warmth_tense():
    assert warmth_from_state("tense") == "warm"


def test_warmth_broken():
    assert warmth_from_state("broken") == "hot"


def test_warmth_unknown():
    assert warmth_from_state("mysterious") == "neutral"


def test_warmth_case_insensitive():
    assert warmth_from_state("Calm") == "cool"
    assert warmth_from_state("TENSE") == "warm"


# -- state_color -------------------------------------------------------------

def test_state_color_cool():
    assert state_color("cool") == "#4ade80"


def test_state_color_warm():
    assert state_color("warm") == "#f59e0b"


def test_state_color_hot():
    assert state_color("hot") == "#ef4444"


def test_state_color_neutral():
    assert state_color("neutral") == "#9ca3af"


# -- importance_radius_delta -------------------------------------------------

def test_radius_delta_zero():
    assert importance_radius_delta(0.0) == 0.0


def test_radius_delta_max():
    assert importance_radius_delta(1.0) == 6.0


def test_radius_delta_mid():
    assert importance_radius_delta(0.5) == 3.0


# -- compute_meaning ---------------------------------------------------------

def test_compute_meaning_empty_project():
    db, proj = _make_project()
    result = compute_meaning(db, proj.id, set())
    assert isinstance(result, MeaningData)
    assert len(result.node_meanings) == 0


def test_compute_character_state():
    db, proj, c1, c2, p1, s1, s2, s3, s4 = _make_full_project()
    data = build_graph_data(db, proj.id)
    visible = set(data.nodes.keys())
    result = compute_meaning(db, proj.id, visible)
    alice_meaning = result.node_meanings.get(f"Character:{c1.id}")
    assert alice_meaning is not None
    assert alice_meaning.state_warmth == "hot"


def test_compute_character_state_bob():
    db, proj, c1, c2, p1, s1, s2, s3, s4 = _make_full_project()
    data = build_graph_data(db, proj.id)
    visible = set(data.nodes.keys())
    result = compute_meaning(db, proj.id, visible)
    bob_meaning = result.node_meanings.get(f"Character:{c2.id}")
    assert bob_meaning is not None
    assert bob_meaning.state_warmth == "hot"


def test_compute_scene_importance_varies():
    db, proj, c1, c2, p1, s1, s2, s3, s4 = _make_full_project()
    data = build_graph_data(db, proj.id)
    visible = set(data.nodes.keys())
    result = compute_meaning(db, proj.id, visible)
    climax = result.node_meanings.get(f"Scene:{s4.id}")
    opening = result.node_meanings.get(f"Scene:{s1.id}")
    assert climax is not None
    assert opening is not None
    assert climax.importance >= opening.importance


def test_compute_scene_with_beat_more_important():
    db, proj, c1, c2, p1, s1, s2, s3, s4 = _make_full_project()
    data = build_graph_data(db, proj.id)
    visible = set(data.nodes.keys())
    result = compute_meaning(db, proj.id, visible)
    midpoint = result.node_meanings.get(f"Scene:{s3.id}")
    opening = result.node_meanings.get(f"Scene:{s1.id}")
    assert midpoint is not None
    assert opening is not None
    assert opening.importance > midpoint.importance


def test_compute_arc_group():
    db, proj, c1, c2, p1, s1, s2, s3, s4 = _make_full_project()
    data = build_graph_data(db, proj.id)
    visible = set(data.nodes.keys())
    result = compute_meaning(db, proj.id, visible)
    opening = result.node_meanings.get(f"Scene:{s1.id}")
    assert opening is not None
    assert opening.arc_group == "Main"


def test_compute_arc_links():
    db, proj, c1, c2, p1, s1, s2, s3, s4 = _make_full_project()
    data = build_graph_data(db, proj.id)
    visible = set(data.nodes.keys())
    result = compute_meaning(db, proj.id, visible)
    main_arcs = [a for a in result.arc_links if a.plotline == "Main"]
    assert len(main_arcs) >= 2
    sub_arcs = [a for a in result.arc_links if a.plotline == "Sub"]
    assert len(sub_arcs) == 0


def test_compute_flow_pairs():
    db, proj, c1, c2, p1, s1, s2, s3, s4 = _make_full_project()
    data = build_graph_data(db, proj.id)
    visible = set(data.nodes.keys())
    result = compute_meaning(db, proj.id, visible)
    assert len(result.flow_pairs) >= 1


def test_dead_zone_detection():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Loner")
    s1 = db.create_scene(proj.id, "Solo", synopsis="[[Loner]] alone.")
    data = build_graph_data(db, proj.id)
    visible = set(data.nodes.keys())
    result = compute_meaning(db, proj.id, visible)
    loner_meaning = result.node_meanings.get(f"Character:{c1.id}")
    assert loner_meaning is not None
    assert loner_meaning.is_dead_zone is True


def test_non_dead_zone():
    db, proj, c1, c2, p1, s1, s2, s3, s4 = _make_full_project()
    data = build_graph_data(db, proj.id)
    visible = set(data.nodes.keys())
    result = compute_meaning(db, proj.id, visible)
    alice_meaning = result.node_meanings.get(f"Character:{c1.id}")
    assert alice_meaning is not None
    assert alice_meaning.is_dead_zone is False


def test_psyke_glow_threshold():
    db, proj = _make_project()
    e1 = db.create_psyke_entry(proj.id, "Theme", "Hope")
    e2 = db.create_psyke_entry(proj.id, "Theme", "Loss")
    e3 = db.create_psyke_entry(proj.id, "Theme", "Growth")
    e4 = db.create_psyke_entry(proj.id, "Theme", "Fear")
    db.add_psyke_relation(e1.id, e2.id)
    db.add_psyke_relation(e1.id, e3.id)
    db.add_psyke_relation(e1.id, e4.id)
    data = build_graph_data(db, proj.id)
    visible = set(data.nodes.keys())
    result = compute_meaning(db, proj.id, visible)
    hope_meaning = result.node_meanings.get(f"PSYKE:{e1.id}")
    assert hope_meaning is not None
    assert hope_meaning.psyke_glow is True


def test_psyke_no_glow_few_connections():
    db, proj = _make_project()
    e1 = db.create_psyke_entry(proj.id, "Theme", "Lone")
    data = build_graph_data(db, proj.id)
    visible = set(data.nodes.keys())
    result = compute_meaning(db, proj.id, visible)
    lone_meaning = result.node_meanings.get(f"PSYKE:{e1.id}")
    assert lone_meaning is not None
    assert lone_meaning.psyke_glow is False


# -- arc_color helper --------------------------------------------------------

def test_arc_color_consistent():
    c1 = _arc_color("Main")
    c2 = _arc_color("Main")
    assert c1 == c2


def test_arc_color_different_plotlines():
    c1 = _arc_color("Main")
    c2 = _arc_color("Sub")
    assert isinstance(c1, str)
    assert isinstance(c2, str)


# -- FocusGraphView meaning integration --------------------------------------

def test_meaning_toggle():
    db, proj, *_ = _make_full_project()
    view = FocusGraphView(db, proj.id)
    assert not view.is_meaning_enabled()
    view._on_meaning_toggled(True)
    assert view.is_meaning_enabled()
    assert view.get_meaning_data() is not None


def test_meaning_off_no_data():
    db, proj, *_ = _make_full_project()
    view = FocusGraphView(db, proj.id)
    assert view.get_meaning_data() is None


def test_meaning_on_has_node_meanings():
    db, proj, c1, c2, p1, s1, s2, s3, s4 = _make_full_project()
    view = FocusGraphView(db, proj.id)
    view._on_meaning_toggled(True)
    md = view.get_meaning_data()
    assert md is not None
    assert len(md.node_meanings) > 0


def test_meaning_with_focus():
    db, proj, c1, *_ = _make_full_project()
    view = FocusGraphView(db, proj.id)
    view._on_meaning_toggled(True)
    view.focus_on(f"Character:{c1.id}")
    md = view.get_meaning_data()
    assert md is not None
    assert f"Character:{c1.id}" in md.node_meanings


def test_meaning_arc_links_present():
    db, proj, *_ = _make_full_project()
    view = FocusGraphView(db, proj.id)
    view._on_meaning_toggled(True)
    md = view.get_meaning_data()
    assert md is not None
    assert len(md.arc_links) > 0


def test_meaning_flow_pairs_present():
    db, proj, *_ = _make_full_project()
    view = FocusGraphView(db, proj.id)
    view._on_meaning_toggled(True)
    md = view.get_meaning_data()
    assert md is not None
    assert len(md.flow_pairs) > 0


def test_meaning_toggle_off_clears():
    db, proj, *_ = _make_full_project()
    view = FocusGraphView(db, proj.id)
    view._on_meaning_toggled(True)
    assert view.get_meaning_data() is not None
    view._on_meaning_toggled(False)
    assert view.get_meaning_data() is None


# -- NodeMeaning defaults ----------------------------------------------------

def test_node_meaning_defaults():
    m = NodeMeaning()
    assert m.importance == 0.0
    assert m.state_warmth == "neutral"
    assert m.is_dead_zone is False
    assert m.psyke_glow is False
    assert m.arc_group == ""
