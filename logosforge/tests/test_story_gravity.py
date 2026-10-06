"""Tests for the Story Gravity system."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from logosforge.db import Database
from logosforge.graph_gravity import (
    GRAVITY_GLOW_THRESHOLD,
    StoryGravity,
    compute_canonical_gravity_totals,
    compute_gravity,
    gravity_centrality_pull,
    gravity_glow_alpha,
    gravity_radius_multiplier,
)
from logosforge.knowledge_graph import provenance as P
from logosforge.knowledge_graph.builder import build_knowledge_graph
from logosforge.knowledge_graph.models import KGNode, node_key
from logosforge.ui.focus_graph_view import (
    FocusGraphView,
    build_graph_data,
)


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# -- StoryGravity dataclass --------------------------------------------------

def test_default_gravity_is_zero():
    g = StoryGravity()
    assert g.narrative == 0.0
    assert g.thematic == 0.0
    assert g.structural == 0.0
    assert g.total == 0.0


def test_total_weighted_sum():
    g = StoryGravity(narrative=1.0, thematic=0.0, structural=0.0)
    assert g.total == pytest.approx(0.45)
    g = StoryGravity(narrative=0.0, thematic=1.0, structural=0.0)
    assert g.total == pytest.approx(0.35)
    g = StoryGravity(narrative=0.0, thematic=0.0, structural=1.0)
    assert g.total == pytest.approx(0.20)


def test_total_capped_at_one():
    g = StoryGravity(narrative=2.0, thematic=2.0, structural=2.0)
    assert g.total == 1.0


def test_total_clamped_above_zero():
    g = StoryGravity(narrative=-1.0, thematic=-1.0, structural=-1.0)
    assert g.total == 0.0


# -- helpers -----------------------------------------------------------------

def test_radius_multiplier_increases_with_gravity():
    a = gravity_radius_multiplier(StoryGravity(narrative=0.0))
    b = gravity_radius_multiplier(StoryGravity(narrative=1.0, thematic=1.0, structural=1.0))
    assert a == 1.0
    assert b > a


def test_glow_alpha_zero_below_threshold():
    g = StoryGravity(narrative=0.1)
    assert gravity_glow_alpha(g) == 0.0


def test_glow_alpha_positive_above_threshold():
    g = StoryGravity(narrative=1.0, thematic=1.0, structural=1.0)
    assert gravity_glow_alpha(g) > 0.0


def test_centrality_pull_increases_with_gravity():
    a = gravity_centrality_pull(StoryGravity())
    b = gravity_centrality_pull(StoryGravity(narrative=1.0, thematic=1.0, structural=1.0))
    assert a == 1.0
    assert b < a
    assert b >= 0.5  # never collapses to 0


# -- compute_gravity end-to-end ----------------------------------------------

def _make_rich_project():
    db = Database()
    proj = db.create_project("Gravity")
    protag = db.create_character(proj.id, "Hero")
    foil = db.create_character(proj.id, "Sidekick")
    place = db.create_place(proj.id, "Castle")
    s1 = db.create_scene(proj.id, "Opening", act="Act I",
                         character_ids=[protag.id, foil.id], place_ids=[place.id])
    s2 = db.create_scene(proj.id, "Inciting", act="Act I",
                         character_ids=[protag.id])
    s3 = db.create_scene(proj.id, "Midpoint", act="Act II",
                         character_ids=[protag.id, foil.id])
    s4 = db.create_scene(proj.id, "Crisis", act="Act III",
                         character_ids=[protag.id])
    s5 = db.create_scene(proj.id, "Climax", act="Act III",
                         character_ids=[protag.id, foil.id], place_ids=[place.id])
    theme = db.create_psyke_entry(proj.id, "Justice", "theme")
    lore = db.create_psyke_entry(proj.id, "Old Law", "lore")
    db.add_psyke_relation(theme.id, lore.id)
    return db, proj, protag, foil, place, s1, s2, s3, s4, s5, theme, lore


def test_protagonist_has_higher_gravity_than_foil():
    """Hero is in 5/5 scenes, Sidekick in 3/5 — gravity should reflect that."""
    db, proj, protag, foil, *_ = _make_rich_project()
    data = build_graph_data(db, proj.id)
    grav = compute_gravity(db, proj.id, data)
    hero_g = grav[f"Character:{protag.id}"]
    foil_g = grav[f"Character:{foil.id}"]
    assert hero_g.total > foil_g.total


def test_climax_scene_has_higher_structural_than_middle_act_scene():
    """Final scene gets the climax bonus; non-pivot scenes don't."""
    db, proj, _p, _f, _pl, _s1, s2, _s3, _s4, s5, *_ = _make_rich_project()
    data = build_graph_data(db, proj.id)
    grav = compute_gravity(db, proj.id, data)
    climax_g = grav[f"Scene:{s5.id}"]
    inciting_g = grav[f"Scene:{s2.id}"]
    assert climax_g.structural > inciting_g.structural


def test_theme_node_has_high_thematic_weight():
    db, proj, *rest = _make_rich_project()
    theme = rest[-2]
    data = build_graph_data(db, proj.id)
    grav = compute_gravity(db, proj.id, data)
    theme_g = grav[f"PSYKE:{theme.id}"]
    assert theme_g.thematic >= 0.8


def test_lore_neighbour_of_theme_inherits_thematic_weight():
    db, proj, *rest = _make_rich_project()
    lore = rest[-1]
    data = build_graph_data(db, proj.id)
    grav = compute_gravity(db, proj.id, data)
    lore_g = grav[f"PSYKE:{lore.id}"]
    assert lore_g.thematic > 0.0


def test_act_node_gets_structural_baseline():
    db, proj, *_ = _make_rich_project()
    data = build_graph_data(db, proj.id)
    grav = compute_gravity(db, proj.id, data)
    act_grav = [g for nid, g in grav.items() if nid.startswith("Act:")]
    assert all(g.structural >= 0.6 for g in act_grav)


def test_empty_project_returns_empty_gravity():
    db = Database()
    proj = db.create_project("Empty")
    data = build_graph_data(db, proj.id)
    grav = compute_gravity(db, proj.id, data)
    assert grav == {}


def test_canonical_gravity_bridge_uses_only_exact_shared_identities():
    db, proj, protag, _foil, place, first, *_rest = _make_rich_project()
    note = db.create_note(proj.id, "Research", content="See [[Opening]].")
    canonical = build_knowledge_graph(db, proj.id).graph
    character_key = node_key(P.NT_CHARACTER, "character", protag.id)
    place_key = node_key(P.NT_PLACE, "place", place.id)
    canonical.add_node(KGNode(
        key=character_key,
        node_type=P.NT_CHARACTER,
        source_type="character",
        source_id=str(protag.id),
        label=protag.name,
    ))
    canonical.add_node(KGNode(
        key=place_key,
        node_type=P.NT_PLACE,
        source_type="place",
        source_id=str(place.id),
        label=place.name,
    ))

    available, totals = compute_canonical_gravity_totals(
        db, proj.id, canonical,
    )

    assert available is True
    assert node_key(P.NT_SCENE, "scene", first.id) in totals
    assert node_key(P.NT_NOTE, "note", note.id) in totals
    assert node_key(P.NT_ACT, "act", "Act I") in totals
    psyke_keys = {
        key for key, node in canonical.nodes.items()
        if node.source_type == "psyke"
    }
    assert psyke_keys
    assert psyke_keys.issubset(totals)
    # Character and Place table identities are distinct from typed PSYKE
    # entries.  The bridge must never infer equivalence by id or label.
    assert character_key not in totals
    assert place_key not in totals


def test_canonical_gravity_bridge_fails_closed_on_ambiguous_identity():
    db, proj, _protag, _foil, _place, first, *_rest = _make_rich_project()
    canonical = build_knowledge_graph(db, proj.id).graph
    scene_key = node_key(P.NT_SCENE, "scene", first.id)
    duplicate_key = "scene:duplicate:ambiguous"
    canonical.add_node(KGNode(
        key=duplicate_key,
        node_type=P.NT_SCENE,
        source_type="scene",
        source_id=str(first.id),
        label="Ambiguous duplicate",
    ))

    available, totals = compute_canonical_gravity_totals(
        db, proj.id, canonical,
    )

    assert available is True
    assert scene_key not in totals
    assert duplicate_key not in totals


@pytest.mark.parametrize(
    "writing_mode",
    ["novel", "screenplay", "graphic_novel", "stage_script", "series"],
)
def test_canonical_gravity_bridge_runs_in_every_writing_mode(writing_mode):
    db = Database()
    project = db.create_project("Mode gravity", narrative_engine=writing_mode)
    character = db.create_character(project.id, "Hero")
    scene = db.create_scene(
        project.id,
        "Opening",
        act="Act I",
        character_ids=[character.id],
    )
    canonical = build_knowledge_graph(db, project.id).graph

    available, totals = compute_canonical_gravity_totals(
        db, project.id, canonical,
    )

    assert available is True
    assert node_key(P.NT_SCENE, "scene", scene.id) in totals


def test_controlling_idea_theme_entry_gets_max_thematic():
    db = Database()
    proj = db.create_project("CI Test")
    theme = db.create_psyke_entry(proj.id, "Truth", "theme")
    # Wire up the Controlling Idea pointing at this PSYKE theme entry.
    from logosforge.controlling_idea import ControllingIdea, save
    ci = ControllingIdea(
        enabled=True,
        value="Truth",
        cause="when sacrifices are made",
        statement="Truth prevails when sacrifices are made",
        theme_psyke_entry_id=theme.id,
    )
    save(db, proj.id, ci)
    data = build_graph_data(db, proj.id)
    grav = compute_gravity(db, proj.id, data)
    assert grav[f"PSYKE:{theme.id}"].thematic == 1.0


def test_scene_with_ci_alignment_gets_thematic_boost():
    db = Database()
    proj = db.create_project("CI Scene")
    c = db.create_character(proj.id, "Hero")
    # Scene needs a participant so it survives the participation gate.
    s = db.create_scene(proj.id, "Aligned", content="...", character_ids=[c.id])
    from logosforge.controlling_idea import (
        ControllingIdea, save, set_scene_alignment,
    )
    ci = ControllingIdea(
        enabled=True,
        value="Truth", cause="x", statement="x x x",
    )
    save(db, proj.id, ci)
    set_scene_alignment(db, proj.id, s.id, "supports")
    data = build_graph_data(db, proj.id)
    grav = compute_gravity(db, proj.id, data)
    scene_g = grav.get(f"Scene:{s.id}")
    assert scene_g is not None
    assert scene_g.thematic >= 0.7


# -- View integration --------------------------------------------------------

def test_view_gravity_enabled_by_default():
    db, proj, *_ = _make_rich_project()
    view = FocusGraphView(db, proj.id)
    assert view.is_gravity_enabled() is True
    assert view._gravity_check.isChecked()


def test_view_gravity_map_populated_after_refresh():
    db, proj, *_ = _make_rich_project()
    view = FocusGraphView(db, proj.id)
    gmap = view.get_gravity_map()
    assert len(gmap) > 0


def test_view_gravity_toggle_clears_map():
    db, proj, *_ = _make_rich_project()
    view = FocusGraphView(db, proj.id)
    view._on_gravity_toggled(False)
    assert not view.is_gravity_enabled()
    assert view.get_gravity_map() == {}


def test_view_gravity_re_enables_map():
    db, proj, *_ = _make_rich_project()
    view = FocusGraphView(db, proj.id)
    view._on_gravity_toggled(False)
    view._on_gravity_toggled(True)
    assert view.is_gravity_enabled()
    assert len(view.get_gravity_map()) > 0


def test_high_gravity_node_drawn_larger():
    """The protagonist's rendered radius should exceed a minor character's."""
    db, proj, protag, foil, *_ = _make_rich_project()
    view = FocusGraphView(db, proj.id)
    hero_item = view._node_items.get(f"Character:{protag.id}")
    foil_item = view._node_items.get(f"Character:{foil.id}")
    if hero_item is None or foil_item is None:
        pytest.skip("character nodes not visible by default in this setup")
    # Both ellipse-shaped nodes inherit QGraphicsEllipseItem; compare their
    # bounding rect widths.
    assert hero_item.boundingRect().width() > foil_item.boundingRect().width()
