"""Tests for Story Memory Management — priority, decay, limits."""

from logosforge.db import Database
from logosforge.memory_manager import (
    CONTEXT_LIMIT,
    ScoredMemory,
    compute_priority,
    compute_recency,
    compute_relevance,
    format_managed_context,
    get_active_memories,
    memory_stats,
    priority_level,
    score_memories,
    supersede_old_states,
)
from logosforge.story_memory import extract_scene_memory


def _make_project():
    db = Database()
    proj = db.create_project("MgrTest")
    return db, proj


# -- Priority assignment -------------------------------------------------------

def test_priority_key_event():
    db, proj = _make_project()
    c = db.create_character(proj.id, "A")
    s = db.create_scene(proj.id, "S1", character_ids=[c.id])
    entry = db.add_memory(proj.id, s.id, "key_event", "", "The castle burns")
    mems = db.get_memories(proj.id)
    p = compute_priority(entry, mems)
    assert p == 1.0


def test_priority_decision():
    db, proj = _make_project()
    c = db.create_character(proj.id, "A")
    s = db.create_scene(proj.id, "S1", character_ids=[c.id])
    entry = db.add_memory(proj.id, s.id, "decision", "", "Choose exile")
    mems = db.get_memories(proj.id)
    p = compute_priority(entry, mems)
    assert p == 1.0


def test_priority_relationship():
    db, proj = _make_project()
    c = db.create_character(proj.id, "A")
    s = db.create_scene(proj.id, "S1", character_ids=[c.id])
    entry = db.add_memory(proj.id, s.id, "relationship", "A and B", "conflict")
    mems = db.get_memories(proj.id)
    p = compute_priority(entry, mems)
    assert p == 0.7


def test_priority_character_state_current():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    s = db.create_scene(proj.id, "S1", character_ids=[c.id])
    entry = db.add_memory(proj.id, s.id, "character_state", "Hero", "angry")
    mems = db.get_memories(proj.id)
    p = compute_priority(entry, mems)
    assert p == 0.7


def test_priority_character_state_superseded():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    s1 = db.create_scene(proj.id, "S1", character_ids=[c.id])
    s2 = db.create_scene(proj.id, "S2", character_ids=[c.id])
    old = db.add_memory(proj.id, s1.id, "character_state", "Hero", "angry")
    db.add_memory(proj.id, s2.id, "character_state", "Hero", "calm")
    mems = db.get_memories(proj.id)
    p = compute_priority(old, mems)
    assert p == 0.4  # Demoted to low


# -- Priority level ------------------------------------------------------------

def test_priority_level_high():
    assert priority_level(1.0) == "high"
    assert priority_level(0.9) == "high"


def test_priority_level_medium():
    assert priority_level(0.7) == "medium"
    assert priority_level(0.6) == "medium"


def test_priority_level_low():
    assert priority_level(0.4) == "low"
    assert priority_level(0.1) == "low"


# -- Recency -------------------------------------------------------------------

def test_recency_latest_scene():
    db, proj = _make_project()
    c = db.create_character(proj.id, "A")
    s1 = db.create_scene(proj.id, "S1", character_ids=[c.id])
    s2 = db.create_scene(proj.id, "S2", character_ids=[c.id])
    s3 = db.create_scene(proj.id, "S3", character_ids=[c.id])
    entry = db.add_memory(proj.id, s3.id, "key_event", "", "Event")
    scenes = db.get_all_scenes(proj.id)
    scene_ids = [s.id for s in scenes]
    r = compute_recency(entry, len(scenes), scene_ids)
    assert r == 1.0


def test_recency_oldest_scene():
    db, proj = _make_project()
    c = db.create_character(proj.id, "A")
    s1 = db.create_scene(proj.id, "S1", character_ids=[c.id])
    s2 = db.create_scene(proj.id, "S2", character_ids=[c.id])
    s3 = db.create_scene(proj.id, "S3", character_ids=[c.id])
    entry = db.add_memory(proj.id, s1.id, "key_event", "", "Event")
    scenes = db.get_all_scenes(proj.id)
    scene_ids = [s.id for s in scenes]
    r = compute_recency(entry, len(scenes), scene_ids)
    assert r < 0.5


def test_recency_single_scene():
    db, proj = _make_project()
    c = db.create_character(proj.id, "A")
    s1 = db.create_scene(proj.id, "S1", character_ids=[c.id])
    entry = db.add_memory(proj.id, s1.id, "key_event", "", "Event")
    r = compute_recency(entry, 1, [s1.id])
    assert r == 1.0


# -- Relevance -----------------------------------------------------------------

def test_relevance_high_priority_recent():
    r = compute_relevance(1.0, 1.0)
    assert r == 1.0


def test_relevance_low_priority_old():
    r = compute_relevance(0.4, 0.0)
    # Low priority + old = heavily decayed
    assert r < 0.2


def test_relevance_high_priority_old():
    r = compute_relevance(1.0, 0.0)
    # High priority barely decays
    assert r > 0.5


def test_relevance_never_zero():
    r = compute_relevance(0.4, 0.0)
    assert r > 0


# -- Score memories ------------------------------------------------------------

def test_score_memories_empty():
    db, proj = _make_project()
    scored = score_memories(db, proj.id)
    assert scored == []


def test_score_memories_sorted_by_relevance():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    s1 = db.create_scene(proj.id, "S1", character_ids=[c.id])
    s2 = db.create_scene(proj.id, "S2", character_ids=[c.id])
    s3 = db.create_scene(proj.id, "S3", character_ids=[c.id])
    db.add_memory(proj.id, s1.id, "character_state", "Hero", "angry")
    db.add_memory(proj.id, s3.id, "key_event", "", "Kingdom falls")
    scored = score_memories(db, proj.id)
    assert len(scored) == 2
    relevances = [s.relevance for s in scored]
    assert relevances == sorted(relevances, reverse=True)


def test_score_memories_marks_superseded():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    s1 = db.create_scene(proj.id, "S1", character_ids=[c.id])
    s2 = db.create_scene(proj.id, "S2", character_ids=[c.id])
    db.add_memory(proj.id, s1.id, "character_state", "Hero", "angry")
    db.add_memory(proj.id, s2.id, "character_state", "Hero", "calm")
    scored = score_memories(db, proj.id)
    old_scored = [s for s in scored if s.entry.value == "angry"]
    assert len(old_scored) == 1
    assert old_scored[0].superseded is True


# -- Supersede detection -------------------------------------------------------

def test_supersede_old_states():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    s1 = db.create_scene(proj.id, "S1", character_ids=[c.id])
    s2 = db.create_scene(proj.id, "S2", character_ids=[c.id])
    s3 = db.create_scene(proj.id, "S3", character_ids=[c.id])
    db.add_memory(proj.id, s1.id, "character_state", "Hero", "angry")
    db.add_memory(proj.id, s2.id, "character_state", "Hero", "frustrated")
    db.add_memory(proj.id, s3.id, "character_state", "Hero", "calm")
    count = supersede_old_states(db, proj.id)
    assert count == 2  # Two older states superseded


def test_supersede_no_change_single():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    s1 = db.create_scene(proj.id, "S1", character_ids=[c.id])
    db.add_memory(proj.id, s1.id, "character_state", "Hero", "happy")
    count = supersede_old_states(db, proj.id)
    assert count == 0


# -- Context limit -------------------------------------------------------------

def test_active_memories_respects_limit():
    db, proj = _make_project()
    c = db.create_character(proj.id, "A")
    # Create more memories than limit
    for i in range(CONTEXT_LIMIT + 5):
        s = db.create_scene(proj.id, f"S{i}", character_ids=[c.id])
        db.add_memory(proj.id, s.id, "key_event", "", f"Event number {i} happened")
    active = get_active_memories(db, proj.id)
    assert len(active) == CONTEXT_LIMIT


def test_active_memories_under_limit():
    db, proj = _make_project()
    c = db.create_character(proj.id, "A")
    s = db.create_scene(proj.id, "S1", character_ids=[c.id])
    db.add_memory(proj.id, s.id, "key_event", "", "Something happened")
    active = get_active_memories(db, proj.id)
    assert len(active) == 1


def test_active_memories_custom_limit():
    db, proj = _make_project()
    c = db.create_character(proj.id, "A")
    for i in range(10):
        s = db.create_scene(proj.id, f"S{i}", character_ids=[c.id])
        db.add_memory(proj.id, s.id, "key_event", "", f"Event {i} is important")
    active = get_active_memories(db, proj.id, limit=5)
    assert len(active) == 5


# -- format_managed_context ----------------------------------------------------

def test_format_managed_context_empty():
    db, proj = _make_project()
    ctx = format_managed_context(db, proj.id)
    assert ctx == ""


def test_format_managed_context_basic():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    s = db.create_scene(proj.id, "S1", character_ids=[c.id])
    db.add_memory(proj.id, s.id, "key_event", "", "The kingdom falls")
    db.add_memory(proj.id, s.id, "character_state", "Hero", "devastated")
    ctx = format_managed_context(db, proj.id)
    assert "[Story Memory]" in ctx
    assert "kingdom falls" in ctx
    assert "Hero" in ctx


def test_format_managed_context_superseded_marked():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    s1 = db.create_scene(proj.id, "S1", character_ids=[c.id])
    s2 = db.create_scene(proj.id, "S2", character_ids=[c.id])
    db.add_memory(proj.id, s1.id, "character_state", "Hero", "angry")
    db.add_memory(proj.id, s2.id, "character_state", "Hero", "calm")
    ctx = format_managed_context(db, proj.id)
    assert "(past)" in ctx
    assert "calm" in ctx


def test_format_managed_context_respects_limit():
    db, proj = _make_project()
    c = db.create_character(proj.id, "A")
    for i in range(30):
        s = db.create_scene(proj.id, f"S{i}", character_ids=[c.id])
        db.add_memory(proj.id, s.id, "key_event", "", f"Event number {i} is important")
    ctx = format_managed_context(db, proj.id, limit=5)
    lines = [l for l in ctx.split("\n") if l.startswith("- ")]
    assert len(lines) == 5


# -- memory_stats --------------------------------------------------------------

def test_memory_stats_empty():
    db, proj = _make_project()
    stats = memory_stats(db, proj.id)
    assert stats["total"] == 0
    assert stats["high"] == 0


def test_memory_stats():
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")
    s1 = db.create_scene(proj.id, "S1", character_ids=[c.id])
    s2 = db.create_scene(proj.id, "S2", character_ids=[c.id])
    db.add_memory(proj.id, s1.id, "key_event", "", "Major event")
    db.add_memory(proj.id, s1.id, "character_state", "Hero", "angry")
    db.add_memory(proj.id, s2.id, "character_state", "Hero", "calm")
    stats = memory_stats(db, proj.id)
    assert stats["total"] == 3
    assert stats["high"] >= 1
    assert stats["superseded"] >= 1


# -- Integration: extraction + management -------------------------------------

def test_extract_then_manage():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Alice")
    c2 = db.create_character(proj.id, "Bob")
    s1 = db.create_scene(
        proj.id, "S1",
        outcome="Alice discovers the hidden passage beneath the castle",
        conflict="Alice and Bob argue over who should lead the expedition",
        character_ids=[c1.id, c2.id],
        character_states=[(c1.id, "determined and focused")],
    )
    s2 = db.create_scene(
        proj.id, "S2",
        outcome="The expedition succeeds beyond all expectations",
        character_ids=[c1.id, c2.id],
        character_states=[(c1.id, "triumphant and relieved")],
    )
    extract_scene_memory(db, proj.id, s1.id)
    extract_scene_memory(db, proj.id, s2.id)

    scored = score_memories(db, proj.id)
    assert len(scored) >= 3

    # Alice's first state should be superseded
    old_states = [s for s in scored if s.entry.value == "determined and focused"]
    assert len(old_states) == 1
    assert old_states[0].superseded is True

    # Context should include current state prominently
    ctx = format_managed_context(db, proj.id)
    assert "triumphant" in ctx


# -- Memory evolution over time ------------------------------------------------

def test_memory_evolution():
    """Simulate 5 scenes, showing how memory evolves."""
    db, proj = _make_project()
    c = db.create_character(proj.id, "Hero")

    # Scene 1: Hero angry
    s1 = db.create_scene(proj.id, "S1", character_ids=[c.id],
                         character_states=[(c.id, "angry and bitter")])
    extract_scene_memory(db, proj.id, s1.id)

    # Scene 2: Hero conflicted
    s2 = db.create_scene(proj.id, "S2", character_ids=[c.id],
                         character_states=[(c.id, "conflicted but hopeful")])
    extract_scene_memory(db, proj.id, s2.id)

    # Scene 3: Major event
    s3 = db.create_scene(proj.id, "S3",
                         outcome="Hero saves the village from destruction",
                         character_ids=[c.id],
                         character_states=[(c.id, "proud and resolved")])
    extract_scene_memory(db, proj.id, s3.id)

    scored = score_memories(db, proj.id)

    # Latest state should have highest relevance among states
    state_scored = [s for s in scored if s.entry.memory_type == "character_state"]
    latest_state = [s for s in state_scored if s.entry.value == "proud and resolved"]
    assert len(latest_state) == 1
    assert latest_state[0].superseded is False

    # Older states are superseded
    older_states = [s for s in state_scored if s.superseded]
    assert len(older_states) == 2

    # Key event should rank high
    events = [s for s in scored if s.entry.memory_type == "key_event"]
    assert len(events) == 1
    assert events[0].priority == 1.0
