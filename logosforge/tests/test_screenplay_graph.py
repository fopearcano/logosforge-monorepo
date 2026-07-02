"""Tests for screenplay-aware graph modes."""

from __future__ import annotations

from logosforge.db import Database
from logosforge.graph_gravity import compute_gravity
from logosforge.ui.focus_graph_view import (
    EDGE_CAUSALITY,
    EDGE_CONTINUITY,
    EDGE_KNOWLEDGE,
    EDGE_SETUP_PAYOFF,
    EDGE_SUBTEXT,
    EDGE_VISUAL_MOTIF,
    MODE_ALL,
    MODE_CAUSALITY,
    MODE_CONTINUITY_GRAPH,
    MODE_KNOWLEDGE,
    MODE_PROFILES,
    MODE_SETUP_PAYOFF,
    MODE_SUBTEXT,
    MODE_VISUAL_MOTIFS,
    NODE_KIND_CHARACTER,
    NODE_KIND_OBJECT,
    NODE_KIND_PLACE,
    NODE_KIND_SCENE,
    NODE_KIND_THEME,
    SCREENPLAY_MODE_ORDER,
    FocusGraphView,
    build_graph_data,
    enrich_screenplay_edges,
)


# =========================================================================
# Helpers
# =========================================================================

def _make_screenplay_project(db: Database):
    return db.create_project("Film Noir", format_mode="screenplay")


def _make_connected_scenes(db: Database, project_id: int):
    """Create scenes with shared characters for causality testing."""
    char1 = db.create_character(project_id, name="DETECTIVE")
    char2 = db.create_character(project_id, name="SUSPECT")
    s1 = db.create_scene(
        project_id,
        "INT. OFFICE - DAY",
        act="Act 1",
        character_ids=[char1.id],
        setup_payoff_links="gun → Act 3",
        estimated_duration_minutes=5,
    )
    s2 = db.create_scene(
        project_id,
        "EXT. ALLEY - NIGHT",
        act="Act 1",
        character_ids=[char1.id, char2.id],
        who_knows_what="DETECTIVE knows about the gun",
        estimated_duration_minutes=3,
    )
    s3 = db.create_scene(
        project_id,
        "INT. STATION - DAY",
        act="Act 2",
        character_ids=[char2.id],
        who_knows_what="SUSPECT knows about the photo",
        estimated_duration_minutes=2,
    )
    return s1, s2, s3, char1, char2


# =========================================================================
# 1. MODE PROFILES
# =========================================================================

def test_screenplay_mode_profiles_exist():
    for mode in SCREENPLAY_MODE_ORDER:
        assert mode in MODE_PROFILES


def test_causality_profile():
    p = MODE_PROFILES[MODE_CAUSALITY]
    assert NODE_KIND_SCENE in p.visible_kinds
    assert NODE_KIND_CHARACTER in p.visible_kinds
    assert EDGE_CAUSALITY in p.visible_edge_types
    assert p.layout == "linear_timeline"


def test_setup_payoff_profile():
    p = MODE_PROFILES[MODE_SETUP_PAYOFF]
    assert NODE_KIND_SCENE in p.visible_kinds
    assert NODE_KIND_OBJECT in p.visible_kinds
    assert EDGE_SETUP_PAYOFF in p.visible_edge_types


def test_knowledge_profile():
    p = MODE_PROFILES[MODE_KNOWLEDGE]
    assert NODE_KIND_CHARACTER in p.visible_kinds
    assert EDGE_KNOWLEDGE in p.visible_edge_types


def test_subtext_profile():
    p = MODE_PROFILES[MODE_SUBTEXT]
    assert NODE_KIND_THEME in p.visible_kinds
    assert EDGE_SUBTEXT in p.visible_edge_types


def test_visual_motifs_profile():
    p = MODE_PROFILES[MODE_VISUAL_MOTIFS]
    assert NODE_KIND_OBJECT in p.visible_kinds
    assert EDGE_VISUAL_MOTIF in p.visible_edge_types


def test_continuity_profile():
    p = MODE_PROFILES[MODE_CONTINUITY_GRAPH]
    assert NODE_KIND_PLACE in p.visible_kinds
    assert EDGE_CONTINUITY in p.visible_edge_types
    assert p.layout == "linear_timeline"


def test_all_screenplay_modes_have_description():
    for mode in SCREENPLAY_MODE_ORDER:
        assert MODE_PROFILES[mode].description


# =========================================================================
# 2. EDGE ENRICHMENT
# =========================================================================

def test_causality_edges_created():
    db = Database()
    proj = _make_screenplay_project(db)
    s1, s2, s3, _, _ = _make_connected_scenes(db, proj.id)
    data = build_graph_data(db, proj.id)
    enrich_screenplay_edges(db, proj.id, data)
    causality = [e for e in data.edges if e.edge_type == EDGE_CAUSALITY]
    assert len(causality) >= 2


def test_causality_edges_require_shared_characters():
    db = Database()
    proj = _make_screenplay_project(db)
    c1 = db.create_character(proj.id, name="ALICE")
    c2 = db.create_character(proj.id, name="BOB")
    db.create_scene(proj.id, "Scene A", character_ids=[c1.id])
    db.create_scene(proj.id, "Scene B", character_ids=[c2.id])
    data = build_graph_data(db, proj.id)
    enrich_screenplay_edges(db, proj.id, data)
    causality = [e for e in data.edges if e.edge_type == EDGE_CAUSALITY]
    assert len(causality) == 0


def test_knowledge_edges_created():
    db = Database()
    proj = _make_screenplay_project(db)
    s1, s2, s3, _, _ = _make_connected_scenes(db, proj.id)
    data = build_graph_data(db, proj.id)
    enrich_screenplay_edges(db, proj.id, data)
    knowledge = [e for e in data.edges if e.edge_type == EDGE_KNOWLEDGE]
    assert len(knowledge) >= 1


def test_continuity_edges_created():
    db = Database()
    proj = _make_screenplay_project(db)
    s1, s2, _, _, _ = _make_connected_scenes(db, proj.id)
    db.add_memory(proj.id, s1.id, "continuity_wound", "DETECTIVE", "bruised knuckles")
    db.add_memory(proj.id, s2.id, "continuity_wound", "DETECTIVE", "still bruised")
    data = build_graph_data(db, proj.id)
    enrich_screenplay_edges(db, proj.id, data)
    cont = [e for e in data.edges if e.edge_type == EDGE_CONTINUITY]
    assert len(cont) >= 1


def test_setup_payoff_edges_from_psyke():
    db = Database()
    proj = _make_screenplay_project(db)
    e1 = db.create_psyke_entry(proj.id, "Gun Plant", entry_type="object")
    e2 = db.create_psyke_entry(proj.id, "Gun Payoff", entry_type="object")
    db.add_psyke_relation(e1.id, e2.id, relation_type="supports_setup")
    data = build_graph_data(db, proj.id)
    enrich_screenplay_edges(db, proj.id, data)
    sp = [e for e in data.edges if e.edge_type == EDGE_SETUP_PAYOFF]
    assert len(sp) >= 1


def test_subtext_edges_from_psyke():
    db = Database()
    proj = _make_screenplay_project(db)
    e1 = db.create_psyke_entry(proj.id, "Hope", entry_type="theme")
    e2 = db.create_psyke_entry(proj.id, "Despair", entry_type="theme")
    db.add_psyke_relation(e1.id, e2.id, relation_type="subtext_opposition")
    data = build_graph_data(db, proj.id)
    enrich_screenplay_edges(db, proj.id, data)
    sub = [e for e in data.edges if e.edge_type == EDGE_SUBTEXT]
    assert len(sub) >= 1


def test_visual_motif_edges_from_psyke():
    db = Database()
    proj = _make_screenplay_project(db)
    e1 = db.create_psyke_entry(proj.id, "Red Door", entry_type="object")
    e2 = db.create_psyke_entry(proj.id, "Red Car", entry_type="object")
    db.add_psyke_relation(e1.id, e2.id, relation_type="visual_motif")
    data = build_graph_data(db, proj.id)
    enrich_screenplay_edges(db, proj.id, data)
    vm = [e for e in data.edges if e.edge_type == EDGE_VISUAL_MOTIF]
    assert len(vm) >= 1


def test_no_duplicate_screenplay_edges():
    db = Database()
    proj = _make_screenplay_project(db)
    _make_connected_scenes(db, proj.id)
    data = build_graph_data(db, proj.id)
    enrich_screenplay_edges(db, proj.id, data)
    causality = [e for e in data.edges if e.edge_type == EDGE_CAUSALITY]
    unique = {(e.source_id, e.target_id) for e in causality}
    assert len(unique) == len(causality)


# =========================================================================
# 3. MODE SWITCHING (UI)
# =========================================================================

def test_screenplay_view_detects_mode():
    db = Database()
    proj = _make_screenplay_project(db)
    view = FocusGraphView(db, proj.id)
    assert view._screenplay_mode is True


def test_novel_view_not_screenplay():
    db = Database()
    proj = db.create_project("Novel", format_mode="novel")
    view = FocusGraphView(db, proj.id)
    assert view._screenplay_mode is False


def test_screenplay_mode_buttons_present():
    db = Database()
    proj = _make_screenplay_project(db)
    view = FocusGraphView(db, proj.id)
    for mode in SCREENPLAY_MODE_ORDER:
        assert mode in view._mode_buttons


def test_novel_no_screenplay_buttons():
    db = Database()
    proj = db.create_project("Novel", format_mode="novel")
    view = FocusGraphView(db, proj.id)
    for mode in SCREENPLAY_MODE_ORDER:
        assert mode not in view._mode_buttons


def test_switch_to_causality_mode():
    db = Database()
    proj = _make_screenplay_project(db)
    _make_connected_scenes(db, proj.id)
    view = FocusGraphView(db, proj.id)
    view.set_mode(MODE_CAUSALITY)
    assert view.get_mode() == MODE_CAUSALITY


def test_switch_to_setup_payoff_mode():
    db = Database()
    proj = _make_screenplay_project(db)
    view = FocusGraphView(db, proj.id)
    view.set_mode(MODE_SETUP_PAYOFF)
    assert view.get_mode() == MODE_SETUP_PAYOFF


def test_switch_back_to_all():
    db = Database()
    proj = _make_screenplay_project(db)
    view = FocusGraphView(db, proj.id)
    view.set_mode(MODE_CAUSALITY)
    view.set_mode(MODE_ALL)
    assert view.get_mode() == MODE_ALL


def test_causality_mode_layers():
    db = Database()
    proj = _make_screenplay_project(db)
    view = FocusGraphView(db, proj.id)
    view.set_mode(MODE_CAUSALITY)
    assert NODE_KIND_SCENE in view._active_layers
    assert NODE_KIND_CHARACTER in view._active_layers
    assert NODE_KIND_THEME not in view._active_layers


def test_knowledge_mode_layers():
    db = Database()
    proj = _make_screenplay_project(db)
    view = FocusGraphView(db, proj.id)
    view.set_mode(MODE_KNOWLEDGE)
    assert NODE_KIND_SCENE in view._active_layers
    assert NODE_KIND_CHARACTER in view._active_layers


# =========================================================================
# 4. SCREENPLAY GRAVITY
# =========================================================================

def test_gravity_boosts_setup_payoff_scene():
    db = Database()
    proj = _make_screenplay_project(db)
    s1, _, _, _, _ = _make_connected_scenes(db, proj.id)
    data = build_graph_data(db, proj.id)
    gravity = compute_gravity(db, proj.id, data, screenplay_mode=True)
    g = gravity.get(f"Scene:{s1.id}")
    assert g is not None
    assert g.structural >= 0.7


def test_gravity_boosts_duration():
    db = Database()
    proj = _make_screenplay_project(db)
    s1, _, s3, _, _ = _make_connected_scenes(db, proj.id)
    data = build_graph_data(db, proj.id)
    gravity = compute_gravity(db, proj.id, data, screenplay_mode=True)
    g1 = gravity.get(f"Scene:{s1.id}")
    g3 = gravity.get(f"Scene:{s3.id}")
    assert g1 is not None and g3 is not None
    assert g1.narrative >= g3.narrative


def test_gravity_no_screenplay_no_boost():
    db = Database()
    proj = _make_screenplay_project(db)
    s1, _, _, _, _ = _make_connected_scenes(db, proj.id)
    data = build_graph_data(db, proj.id)
    g_sp = compute_gravity(db, proj.id, data, screenplay_mode=True)
    g_no = compute_gravity(db, proj.id, data, screenplay_mode=False)
    sp = g_sp.get(f"Scene:{s1.id}")
    no = g_no.get(f"Scene:{s1.id}")
    assert sp is not None and no is not None
    assert sp.total >= no.total


# =========================================================================
# 5. FOCUS READABILITY
# =========================================================================

def test_mode_filters_node_kinds():
    db = Database()
    proj = _make_screenplay_project(db)
    _make_connected_scenes(db, proj.id)
    db.create_psyke_entry(proj.id, "Justice", entry_type="theme")
    view = FocusGraphView(db, proj.id)
    view.set_mode(MODE_CAUSALITY)
    assert NODE_KIND_THEME not in view._active_layers


def test_continuity_mode_includes_places():
    db = Database()
    proj = _make_screenplay_project(db)
    view = FocusGraphView(db, proj.id)
    view.set_mode(MODE_CONTINUITY_GRAPH)
    assert NODE_KIND_PLACE in view._active_layers


def test_novel_enrichment_does_not_crash():
    db = Database()
    proj = db.create_project("Novel", format_mode="novel")
    c = db.create_character(proj.id, name="Hero")
    db.create_scene(proj.id, "Ch 1", character_ids=[c.id])
    db.create_scene(proj.id, "Ch 2", character_ids=[c.id])
    data = build_graph_data(db, proj.id)
    enrich_screenplay_edges(db, proj.id, data)
    causality = [e for e in data.edges if e.edge_type == EDGE_CAUSALITY]
    assert len(causality) >= 1


def test_empty_project_enrichment():
    db = Database()
    proj = _make_screenplay_project(db)
    data = build_graph_data(db, proj.id)
    enrich_screenplay_edges(db, proj.id, data)
    sp_edges = [
        e for e in data.edges
        if e.edge_type in {
            EDGE_CAUSALITY, EDGE_SETUP_PAYOFF, EDGE_KNOWLEDGE,
            EDGE_SUBTEXT, EDGE_VISUAL_MOTIF, EDGE_CONTINUITY,
        }
    ]
    assert len(sp_edges) == 0
