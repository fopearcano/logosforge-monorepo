"""Tests for Adaptive AI Mode Engine."""

from logosforge.adaptive_mode import (
    AIMode,
    HealthState,
    ModeResult,
    StoryStage,
    compute_mode,
    detect_health,
    detect_stage,
    mode_context_block,
    select_mode,
)
from logosforge.db import Database


def _make_project():
    db = Database()
    proj = db.create_project("ModeTest")
    return db, proj


# -- detect_stage -------------------------------------------------------------

def test_stage_empty():
    db, proj = _make_project()
    assert detect_stage(db, proj.id) == StoryStage.EARLY


def test_stage_few_scenes():
    db, proj = _make_project()
    c = db.create_character(proj.id, "A")
    for i in range(4):
        db.create_scene(proj.id, f"S{i}", character_ids=[c.id])
    assert detect_stage(db, proj.id) == StoryStage.EARLY


def test_stage_early_no_structure():
    db, proj = _make_project()
    c = db.create_character(proj.id, "A")
    for i in range(7):
        db.create_scene(proj.id, f"S{i}", character_ids=[c.id])
    assert detect_stage(db, proj.id) == StoryStage.EARLY


def test_stage_mid_with_acts():
    db, proj = _make_project()
    c = db.create_character(proj.id, "A")
    for i in range(10):
        act = "Act 1" if i < 5 else "Act 2"
        db.create_scene(proj.id, f"S{i}", act=act, character_ids=[c.id])
    assert detect_stage(db, proj.id) == StoryStage.MID


def test_stage_mid_with_plotlines():
    db, proj = _make_project()
    c = db.create_character(proj.id, "A")
    for i in range(8):
        pl = "Main" if i % 2 == 0 else "Sub"
        db.create_scene(proj.id, f"S{i}", plotline=pl, character_ids=[c.id])
    assert detect_stage(db, proj.id) == StoryStage.MID


def test_stage_late():
    db, proj = _make_project()
    c = db.create_character(proj.id, "A")
    for i in range(21):
        act = "Act 1" if i < 7 else ("Act 2" if i < 14 else "Act 3")
        pl = "Main" if i % 2 == 0 else "Sub"
        db.create_scene(proj.id, f"S{i}", act=act, plotline=pl, character_ids=[c.id])
    assert detect_stage(db, proj.id) == StoryStage.LATE


def test_stage_many_scenes_no_structure():
    db, proj = _make_project()
    c = db.create_character(proj.id, "A")
    for i in range(25):
        db.create_scene(proj.id, f"S{i}", character_ids=[c.id])
    assert detect_stage(db, proj.id) == StoryStage.EARLY


# -- detect_health ------------------------------------------------------------

def test_health_empty():
    db, proj = _make_project()
    assert detect_health(db, proj.id) == HealthState.FRAGMENTED


def test_health_balanced():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "A")
    c2 = db.create_character(proj.id, "B")
    for i in range(6):
        act = "Act 1" if i < 3 else "Act 2"
        db.create_scene(proj.id, f"S{i}", plotline="Main", act=act,
                        character_ids=[c1.id, c2.id])
    assert detect_health(db, proj.id) == HealthState.BALANCED


def test_health_uneven():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Hero")
    c2 = db.create_character(proj.id, "Side")
    # Hero dominates, Side underused
    for i in range(8):
        db.create_scene(proj.id, f"S{i}", plotline="Main", character_ids=[c1.id])
    db.create_scene(proj.id, "Cameo", plotline="Sub", character_ids=[c2.id])
    health = detect_health(db, proj.id)
    # At least uneven (1-2 flags)
    assert health in (HealthState.UNEVEN, HealthState.FRAGMENTED)


def test_health_fragmented():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "A")
    c2 = db.create_character(proj.id, "B")
    c3 = db.create_character(proj.id, "C")
    c4 = db.create_character(proj.id, "D")
    # One character dominates, 3 are ghosts
    for i in range(10):
        db.create_scene(proj.id, f"S{i}", plotline="Main", character_ids=[c1.id])
    assert detect_health(db, proj.id) == HealthState.FRAGMENTED


# -- select_mode --------------------------------------------------------------

def test_mode_early_any():
    assert select_mode(StoryStage.EARLY, HealthState.BALANCED) == AIMode.STRUCTURE
    assert select_mode(StoryStage.EARLY, HealthState.UNEVEN) == AIMode.STRUCTURE
    assert select_mode(StoryStage.EARLY, HealthState.FRAGMENTED) == AIMode.STRUCTURE


def test_mode_mid_fragmented():
    assert select_mode(StoryStage.MID, HealthState.FRAGMENTED) == AIMode.STRUCTURE


def test_mode_mid_uneven():
    assert select_mode(StoryStage.MID, HealthState.UNEVEN) == AIMode.BALANCE


def test_mode_mid_balanced():
    assert select_mode(StoryStage.MID, HealthState.BALANCED) == AIMode.REFINEMENT


def test_mode_late_balanced():
    assert select_mode(StoryStage.LATE, HealthState.BALANCED) == AIMode.REFINEMENT


def test_mode_late_uneven():
    assert select_mode(StoryStage.LATE, HealthState.UNEVEN) == AIMode.BALANCE


def test_mode_late_fragmented():
    assert select_mode(StoryStage.LATE, HealthState.FRAGMENTED) == AIMode.STRUCTURE


# -- compute_mode -------------------------------------------------------------

def test_compute_mode_early():
    db, proj = _make_project()
    c = db.create_character(proj.id, "A")
    for i in range(3):
        db.create_scene(proj.id, f"S{i}", character_ids=[c.id])
    result = compute_mode(db, proj.id)
    assert isinstance(result, ModeResult)
    assert result.mode == AIMode.STRUCTURE
    assert result.stage == StoryStage.EARLY


def test_compute_mode_mid_balanced():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "A")
    c2 = db.create_character(proj.id, "B")
    for i in range(10):
        act = "Act 1" if i < 5 else "Act 2"
        chars = [c1.id, c2.id]
        db.create_scene(proj.id, f"S{i}", act=act, plotline="Main",
                        character_ids=chars)
    result = compute_mode(db, proj.id)
    assert result.mode == AIMode.REFINEMENT
    assert result.stage == StoryStage.MID


def test_compute_mode_late_balanced():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "A")
    c2 = db.create_character(proj.id, "B")
    for i in range(21):
        act = "Act 1" if i < 7 else ("Act 2" if i < 14 else "Act 3")
        pl = "Main" if i % 2 == 0 else "Sub"
        chars = [c1.id, c2.id]
        db.create_scene(proj.id, f"S{i}", act=act, plotline=pl,
                        character_ids=chars)
    result = compute_mode(db, proj.id)
    assert result.mode == AIMode.REFINEMENT
    assert result.stage == StoryStage.LATE
    assert result.health == HealthState.BALANCED


# -- mode_context_block -------------------------------------------------------

def test_mode_context_block_format():
    result = ModeResult(
        mode=AIMode.STRUCTURE,
        stage=StoryStage.EARLY,
        health=HealthState.FRAGMENTED,
        description="Focus on scaffolding...",
    )
    block = mode_context_block(result)
    assert "[AI Mode: Structure]" in block
    assert "early" in block
    assert "fragmented" in block
    assert "Focus on scaffolding" in block


def test_mode_context_block_refinement():
    result = ModeResult(
        mode=AIMode.REFINEMENT,
        stage=StoryStage.LATE,
        health=HealthState.BALANCED,
        description="Focus on polish...",
    )
    block = mode_context_block(result)
    assert "[AI Mode: Refinement]" in block
    assert "late" in block
    assert "balanced" in block


# -- ModeResult properties ----------------------------------------------------

def test_mode_name_property():
    result = ModeResult(
        mode=AIMode.BALANCE,
        stage=StoryStage.MID,
        health=HealthState.UNEVEN,
        description="test",
    )
    assert result.mode_name == "Balance"


# -- Integration: build_messages includes mode --------------------------------

def test_build_messages_includes_mode():
    from logosforge.assistant import build_messages
    messages = build_messages(
        "Rewrite this",
        "Scene text here",
        mode_context="[AI Mode: Structure]\nGuidance: scaffold",
    )
    user_content = messages[1]["content"]
    assert "[AI Mode: Structure]" in user_content
    assert "scaffold" in user_content


def test_build_messages_mode_first():
    from logosforge.assistant import build_messages
    messages = build_messages(
        "Rewrite",
        "Scene",
        mode_context="[AI Mode: Refinement]",
        story_memory_context="Memory here",
    )
    user_content = messages[1]["content"]
    mode_pos = user_content.index("[AI Mode:")
    memory_pos = user_content.index("Memory here")
    assert mode_pos < memory_pos
