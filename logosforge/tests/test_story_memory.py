"""Tests for Story Memory Extraction."""

from logosforge.db import Database
from logosforge.story_memory import (
    ExtractionResult,
    MIN_VALUE_LENGTH,
    extract_project_memory,
    extract_scene_memory,
    format_memory_context,
    get_memory_for_scene,
)


def _make_project():
    db = Database()
    proj = db.create_project("MemoryTest")
    return db, proj


# -- Character state extraction -----------------------------------------------

def test_extract_character_state():
    db, proj = _make_project()
    c = db.create_character(proj.id, "John")
    s = db.create_scene(
        proj.id, "Betrayal",
        character_ids=[c.id],
        character_states=[(c.id, "trust broken")],
    )
    result = extract_scene_memory(db, proj.id, s.id)
    assert len(result.added) >= 1
    state_mems = [m for m in result.added if m.memory_type == "character_state"]
    assert len(state_mems) == 1
    assert state_mems[0].target == "John"
    assert state_mems[0].value == "trust broken"


def test_skip_short_state():
    db, proj = _make_project()
    c = db.create_character(proj.id, "A")
    s = db.create_scene(
        proj.id, "S1",
        character_ids=[c.id],
        character_states=[(c.id, "ok")],  # Too short (<3 chars)
    )
    result = extract_scene_memory(db, proj.id, s.id)
    state_mems = [m for m in result.added if m.memory_type == "character_state"]
    assert len(state_mems) == 0


# -- Key event extraction -----------------------------------------------------

def test_extract_key_event():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    s = db.create_scene(
        proj.id, "Battle",
        outcome="The city gate falls to the invaders",
        character_ids=[c.id],
    )
    result = extract_scene_memory(db, proj.id, s.id)
    events = [m for m in result.added if m.memory_type == "key_event"]
    assert len(events) == 1
    assert "city gate falls" in events[0].value


def test_skip_short_outcome():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    s = db.create_scene(
        proj.id, "S1",
        outcome="nothing",  # Too short
        character_ids=[c.id],
    )
    result = extract_scene_memory(db, proj.id, s.id)
    events = [m for m in result.added if m.memory_type == "key_event"]
    assert len(events) == 0


# -- Relationship extraction --------------------------------------------------

def test_extract_relationship():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Alice")
    c2 = db.create_character(proj.id, "Bob")
    s = db.create_scene(
        proj.id, "Confrontation",
        conflict="Alice discovers Bob has been lying about the inheritance",
        character_ids=[c1.id, c2.id],
    )
    result = extract_scene_memory(db, proj.id, s.id)
    rels = [m for m in result.added if m.memory_type == "relationship"]
    assert len(rels) == 1
    assert "Alice" in rels[0].target
    assert "Bob" in rels[0].target


def test_no_relationship_single_character():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Solo")
    s = db.create_scene(
        proj.id, "Alone",
        conflict="Solo struggles with inner demons and past choices",
        character_ids=[c1.id],
    )
    result = extract_scene_memory(db, proj.id, s.id)
    rels = [m for m in result.added if m.memory_type == "relationship"]
    assert len(rels) == 0


# -- Decision extraction ------------------------------------------------------

def test_extract_decision():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    s = db.create_scene(
        proj.id, "Crossroads",
        goal="Hero must choose exile or war with the kingdom",
        outcome="Hero chooses exile, leaving the throne behind",
        character_ids=[c.id],
    )
    result = extract_scene_memory(db, proj.id, s.id)
    decisions = [m for m in result.added if m.memory_type == "decision"]
    assert len(decisions) == 1
    assert "exile" in decisions[0].value


def test_no_decision_without_outcome():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    s = db.create_scene(
        proj.id, "Pondering",
        goal="Hero considers leaving the village forever",
        character_ids=[c.id],
    )
    result = extract_scene_memory(db, proj.id, s.id)
    decisions = [m for m in result.added if m.memory_type == "decision"]
    assert len(decisions) == 0


# -- Deduplication ------------------------------------------------------------

def test_deduplication():
    db, proj = _make_project()
    c = db.create_character(proj.id, "John")
    s = db.create_scene(
        proj.id, "S1",
        outcome="The kingdom falls after the siege breaks through",
        character_ids=[c.id],
        character_states=[(c.id, "devastated")],
    )
    result1 = extract_scene_memory(db, proj.id, s.id)
    assert len(result1.added) >= 1
    assert result1.skipped == 0

    result2 = extract_scene_memory(db, proj.id, s.id)
    assert len(result2.added) == 0
    assert result2.skipped >= 1


# -- Empty / missing scenes ---------------------------------------------------

def test_extract_empty_scene():
    db, proj = _make_project()
    c = db.create_character(proj.id, "A")
    s = db.create_scene(proj.id, "Empty", character_ids=[c.id])
    result = extract_scene_memory(db, proj.id, s.id)
    assert result.added == []
    assert result.skipped == 0


def test_extract_nonexistent_scene():
    db, proj = _make_project()
    result = extract_scene_memory(db, proj.id, 99999)
    assert result.added == []


# -- Project-wide extraction --------------------------------------------------

def test_extract_project_memory():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    db.create_scene(
        proj.id, "S1",
        outcome="The ancient seal is broken forever",
        character_ids=[c.id],
    )
    db.create_scene(
        proj.id, "S2",
        outcome="Hero discovers the hidden chamber beneath the castle",
        character_ids=[c.id],
    )
    results = extract_project_memory(db, proj.id)
    assert len(results) == 2
    total_added = sum(len(r.added) for r in results)
    assert total_added == 2


# -- format_memory_context ----------------------------------------------------

def test_format_memory_context_empty():
    db, proj = _make_project()
    ctx = format_memory_context(db, proj.id)
    assert ctx == ""


def test_format_memory_context():
    db, proj = _make_project()
    c = db.create_character(proj.id, "John")
    s = db.create_scene(
        proj.id, "S1",
        outcome="The kingdom falls to the invading army",
        character_ids=[c.id],
        character_states=[(c.id, "devastated and broken")],
    )
    extract_scene_memory(db, proj.id, s.id)
    ctx = format_memory_context(db, proj.id)
    assert "[Story Memory]" in ctx
    assert "John" in ctx
    assert "devastated" in ctx
    assert "Event:" in ctx


def test_format_memory_context_relationship():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Alice")
    c2 = db.create_character(proj.id, "Bob")
    s = db.create_scene(
        proj.id, "S1",
        conflict="Alice and Bob fight over the stolen documents",
        character_ids=[c1.id, c2.id],
    )
    extract_scene_memory(db, proj.id, s.id)
    ctx = format_memory_context(db, proj.id)
    assert "Alice and Bob" in ctx


def test_format_memory_context_decision():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    s = db.create_scene(
        proj.id, "S1",
        goal="Hero chooses between saving the village or chasing the villain",
        outcome="Hero stays to protect the village from destruction",
        character_ids=[c.id],
    )
    extract_scene_memory(db, proj.id, s.id)
    ctx = format_memory_context(db, proj.id)
    assert "Decision:" in ctx


# -- get_memory_for_scene -----------------------------------------------------

def test_get_memory_for_scene():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    s1 = db.create_scene(
        proj.id, "S1",
        outcome="The ancient gates open after centuries sealed",
        character_ids=[c.id],
    )
    s2 = db.create_scene(
        proj.id, "S2",
        outcome="Hero finds the lost artifact in the ruins",
        character_ids=[c.id],
    )
    extract_project_memory(db, proj.id)
    mems = get_memory_for_scene(db, proj.id, s1.id)
    assert len(mems) >= 1
    assert all(m.scene_id == s1.id for m in mems)


# -- DB methods ---------------------------------------------------------------

def test_db_add_and_get_memory():
    db, proj = _make_project()
    c = db.create_character(proj.id, "A")
    s = db.create_scene(proj.id, "S1", character_ids=[c.id])
    entry = db.add_memory(proj.id, s.id, "key_event", "", "Something happened")
    assert entry.id is not None
    mems = db.get_memories(proj.id)
    assert len(mems) == 1
    assert mems[0].value == "Something happened"


def test_db_get_memories_by_type():
    db, proj = _make_project()
    c = db.create_character(proj.id, "A")
    s = db.create_scene(proj.id, "S1", character_ids=[c.id])
    db.add_memory(proj.id, s.id, "key_event", "", "Event one")
    db.add_memory(proj.id, s.id, "character_state", "A", "happy")
    mems = db.get_memories_by_type(proj.id, "key_event")
    assert len(mems) == 1
    assert mems[0].memory_type == "key_event"


def test_db_delete_memories_for_scene():
    db, proj = _make_project()
    c = db.create_character(proj.id, "A")
    s = db.create_scene(proj.id, "S1", character_ids=[c.id])
    db.add_memory(proj.id, s.id, "key_event", "", "Event")
    db.add_memory(proj.id, s.id, "decision", "", "Choice")
    assert len(db.get_memories(proj.id)) == 2
    db.delete_memories_for_scene(s.id)
    assert len(db.get_memories(proj.id)) == 0


def test_db_memory_exists():
    db, proj = _make_project()
    c = db.create_character(proj.id, "A")
    s = db.create_scene(proj.id, "S1", character_ids=[c.id])
    assert db.memory_exists(s.id, "key_event", "") is False
    db.add_memory(proj.id, s.id, "key_event", "", "Event")
    assert db.memory_exists(s.id, "key_event", "") is True


# -- Multiple memory types from one scene -------------------------------------

def test_rich_scene_extracts_multiple():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Alice")
    c2 = db.create_character(proj.id, "Bob")
    s = db.create_scene(
        proj.id, "Climax",
        goal="Alice must decide whether to trust Bob with the truth",
        conflict="Bob reveals he knew about the conspiracy all along",
        outcome="Alice shares the secret, forming an uneasy alliance",
        character_ids=[c1.id, c2.id],
        character_states=[(c1.id, "conflicted but hopeful")],
    )
    result = extract_scene_memory(db, proj.id, s.id)
    types = {m.memory_type for m in result.added}
    assert "character_state" in types
    assert "key_event" in types
    assert "relationship" in types
    assert "decision" in types
