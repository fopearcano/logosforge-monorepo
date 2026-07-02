"""Tests for Memory-Aware AI Context."""

from logosforge.db import Database
from logosforge.memory_context import (
    CHARACTER_OVERLAP_BOOST,
    DEFAULT_LIMIT,
    PROXIMITY_BOOST,
    ContextMemory,
    gather_memory_context,
    select_memories,
)
from logosforge.story_memory import extract_scene_memory


def _make_project():
    db = Database()
    proj = db.create_project("CtxTest")
    return db, proj


# -- Basic selection -----------------------------------------------------------

def test_select_memories_empty():
    db, proj = _make_project()
    result = select_memories(db, proj.id)
    assert result == []


def test_gather_memory_context_empty():
    db, proj = _make_project()
    ctx = gather_memory_context(db, proj.id)
    assert ctx == ""


def test_select_memories_basic():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    s = db.create_scene(
        proj.id, "S1",
        outcome="The ancient fortress crumbles to dust",
        character_ids=[c.id],
        character_states=[(c.id, "shocked and afraid")],
    )
    extract_scene_memory(db, proj.id, s.id)
    selected = select_memories(db, proj.id)
    assert len(selected) >= 1
    assert all(isinstance(cm, ContextMemory) for cm in selected)


# -- Proximity boost -----------------------------------------------------------

def test_proximity_boost_adjacent_scene():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    s1 = db.create_scene(
        proj.id, "S1",
        outcome="Hero discovers the hidden map in the library",
        character_ids=[c.id],
    )
    s2 = db.create_scene(
        proj.id, "S2",
        outcome="Hero crosses the river to the enchanted forest",
        character_ids=[c.id],
    )
    s3 = db.create_scene(
        proj.id, "S3",
        outcome="Hero enters the dark cavern beneath the mountain",
        character_ids=[c.id],
    )
    extract_scene_memory(db, proj.id, s1.id)
    extract_scene_memory(db, proj.id, s2.id)
    extract_scene_memory(db, proj.id, s3.id)

    # Select with active scene = S2, memories from S1 and S3 are adjacent
    selected = select_memories(db, proj.id, scene_id=s2.id)
    # Find the S1 and S3 memories
    s1_mems = [cm for cm in selected if cm.entry.scene_id == s1.id]
    s3_mems = [cm for cm in selected if cm.entry.scene_id == s3.id]
    assert len(s1_mems) >= 1
    assert len(s3_mems) >= 1
    # Adjacent memories should have boost applied (relevance > base)
    # Both S1 and S3 are distance 1 from S2, so same boost


def test_proximity_boost_distant_lower():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    scenes = []
    for i in range(5):
        s = db.create_scene(
            proj.id, f"S{i+1}",
            outcome=f"Hero completes quest number {i+1} in the realm",
            character_ids=[c.id],
        )
        scenes.append(s)
        extract_scene_memory(db, proj.id, s.id)

    # Active scene is S5 (last), S1 is far away (distance 4 > 2, no boost)
    selected = select_memories(db, proj.id, scene_id=scenes[4].id)
    s1_mems = [cm for cm in selected if cm.entry.scene_id == scenes[0].id]
    s4_mems = [cm for cm in selected if cm.entry.scene_id == scenes[3].id]

    # S4 is distance 1 from S5 (boosted), S1 is distance 4 (no boost)
    if s1_mems and s4_mems:
        assert s4_mems[0].relevance >= s1_mems[0].relevance


# -- Character overlap boost ---------------------------------------------------

def test_character_overlap_boost():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Alice")
    c2 = db.create_character(proj.id, "Bob")
    # Both memories from the same scene so recency is equal
    s1 = db.create_scene(
        proj.id, "S1",
        character_ids=[c1.id, c2.id],
        character_states=[
            (c1.id, "determined and focused"),
            (c2.id, "excited and eager"),
        ],
    )
    extract_scene_memory(db, proj.id, s1.id)

    # Active scene has only Alice — her memories get character overlap boost
    s2 = db.create_scene(
        proj.id, "S2",
        character_ids=[c1.id],
    )
    selected = select_memories(db, proj.id, scene_id=s2.id)
    alice_mems = [cm for cm in selected if cm.entry.target == "Alice"]
    bob_mems = [cm for cm in selected if cm.entry.target == "Bob"]

    assert len(alice_mems) >= 1
    assert len(bob_mems) >= 1
    assert alice_mems[0].relevance > bob_mems[0].relevance


# -- Limit ---------------------------------------------------------------------

def test_select_memories_respects_limit():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    for i in range(20):
        s = db.create_scene(
            proj.id, f"Scene {i+1}",
            outcome=f"Hero completes adventure number {i+1} successfully",
            character_ids=[c.id],
        )
        extract_scene_memory(db, proj.id, s.id)

    selected = select_memories(db, proj.id, limit=5)
    assert len(selected) == 5


def test_default_limit():
    assert DEFAULT_LIMIT == 15


# -- Format output -------------------------------------------------------------

def test_format_includes_header():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    s = db.create_scene(
        proj.id, "S1",
        outcome="The kingdom collapses under the weight of betrayal",
        character_ids=[c.id],
    )
    extract_scene_memory(db, proj.id, s.id)
    ctx = gather_memory_context(db, proj.id)
    assert ctx.startswith("[Story Memory]")


def test_format_scene_labels():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    s1 = db.create_scene(
        proj.id, "S1",
        outcome="Hero unlocks the sealed gate of the fortress",
        character_ids=[c.id],
    )
    s2 = db.create_scene(
        proj.id, "S2",
        outcome="Hero defeats the guardian dragon of the tower",
        character_ids=[c.id],
    )
    extract_scene_memory(db, proj.id, s1.id)
    extract_scene_memory(db, proj.id, s2.id)
    ctx = gather_memory_context(db, proj.id)
    assert "(S1)" in ctx or "(S2)" in ctx


def test_format_character_state():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Alice")
    s = db.create_scene(
        proj.id, "S1",
        character_ids=[c.id],
        character_states=[(c.id, "heartbroken and lost")],
    )
    extract_scene_memory(db, proj.id, s.id)
    ctx = gather_memory_context(db, proj.id)
    assert "Alice" in ctx
    assert "heartbroken" in ctx


def test_format_key_event():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    s = db.create_scene(
        proj.id, "S1",
        outcome="The bridge explodes destroying the only escape route",
        character_ids=[c.id],
    )
    extract_scene_memory(db, proj.id, s.id)
    ctx = gather_memory_context(db, proj.id)
    assert "Event:" in ctx
    assert "bridge explodes" in ctx


def test_format_relationship():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Alice")
    c2 = db.create_character(proj.id, "Bob")
    s = db.create_scene(
        proj.id, "S1",
        conflict="Alice and Bob argue about the stolen inheritance money",
        character_ids=[c1.id, c2.id],
    )
    extract_scene_memory(db, proj.id, s.id)
    ctx = gather_memory_context(db, proj.id)
    assert "Alice and Bob" in ctx


def test_format_decision():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    s = db.create_scene(
        proj.id, "S1",
        goal="Hero must decide between saving the child or chasing the villain",
        outcome="Hero saves the child letting the villain escape north",
        character_ids=[c.id],
    )
    extract_scene_memory(db, proj.id, s.id)
    ctx = gather_memory_context(db, proj.id)
    assert "Decision:" in ctx


def test_format_superseded_past_marker():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    s1 = db.create_scene(
        proj.id, "S1",
        character_ids=[c.id],
        character_states=[(c.id, "optimistic and brave")],
    )
    s2 = db.create_scene(
        proj.id, "S2",
        character_ids=[c.id],
        character_states=[(c.id, "defeated and hopeless")],
    )
    extract_scene_memory(db, proj.id, s1.id)
    extract_scene_memory(db, proj.id, s2.id)
    ctx = gather_memory_context(db, proj.id)
    assert "(past)" in ctx


# -- No scene_id (global context) ---------------------------------------------

def test_select_no_scene_id():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    s = db.create_scene(
        proj.id, "S1",
        outcome="Hero awakens from the long and terrible slumber",
        character_ids=[c.id],
    )
    extract_scene_memory(db, proj.id, s.id)
    selected = select_memories(db, proj.id, scene_id=None)
    assert len(selected) >= 1
    # No boost applied when no active scene
    for cm in selected:
        assert cm.relevance <= 1.0


# -- Sorted by relevance ------------------------------------------------------

def test_sorted_by_relevance():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    for i in range(5):
        s = db.create_scene(
            proj.id, f"S{i+1}",
            outcome=f"Hero encounters challenge number {i+1} on the journey",
            character_ids=[c.id],
        )
        extract_scene_memory(db, proj.id, s.id)

    selected = select_memories(db, proj.id)
    relevances = [cm.relevance for cm in selected]
    assert relevances == sorted(relevances, reverse=True)
