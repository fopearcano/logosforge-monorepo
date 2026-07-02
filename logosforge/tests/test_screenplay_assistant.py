"""Tests for screenplay-aware Assistant — cinematic reasoning, feedback, context, review."""

from __future__ import annotations

import json

from logosforge.db import Database
from logosforge.narrative_engines import SCREENPLAY_ENGINE, NOVEL_ENGINE, engine_for_project
from logosforge.context_builder import gather_scene_context
from logosforge.creative_layer import generate_scene_hints, compute_review_metrics


# =========================================================================
# 1. SCREENPLAY REASONING — engine carries cinematic system prompt
# =========================================================================

def test_screenplay_engine_has_system_prompt_overlay():
    assert SCREENPLAY_ENGINE.system_prompt_overlay
    assert "cinematically" in SCREENPLAY_ENGINE.system_prompt_overlay.lower()


def test_novel_engine_has_no_system_prompt_overlay():
    assert NOVEL_ENGINE.system_prompt_overlay == ""


def test_screenplay_engine_overlay_mentions_key_concepts():
    overlay = SCREENPLAY_ENGINE.system_prompt_overlay.lower()
    assert "screen time" in overlay
    assert "camera" in overlay
    assert "subtext" in overlay
    assert "blocking" in overlay
    assert "setup/payoff" in overlay
    assert "continuity" in overlay


def test_format_context_block_includes_overlay():
    block = SCREENPLAY_ENGINE.format_context_block()
    assert "Reason cinematically" in block


def test_format_context_block_includes_feedback_signals():
    block = SCREENPLAY_ENGINE.format_context_block()
    assert "Feedback signals:" in block


def test_novel_context_block_has_no_overlay():
    block = NOVEL_ENGINE.format_context_block()
    assert "Reason cinematically" not in block


# =========================================================================
# 2. SCREENPLAY-SPECIFIC FEEDBACK PATTERNS
# =========================================================================

def test_screenplay_engine_has_feedback_patterns():
    assert len(SCREENPLAY_ENGINE.feedback_patterns) >= 5


def test_feedback_patterns_cover_key_weaknesses():
    patterns = " ".join(SCREENPLAY_ENGINE.feedback_patterns).lower()
    assert "turn" in patterns
    assert "expositional" in patterns
    assert "visible conflict" in patterns
    assert "blocking" in patterns
    assert "subtext" in patterns
    assert "setup" in patterns or "payoff" in patterns
    assert "continuity" in patterns
    assert "screen time" in patterns


def test_novel_engine_has_no_feedback_patterns():
    assert NOVEL_ENGINE.feedback_patterns == ()


# =========================================================================
# 3. CONTEXT BUILDER — screenplay analysis section
# =========================================================================

def _make_screenplay_project(db: Database) -> tuple[int, int]:
    """Create a screenplay project with a populated scene."""
    proj = db.create_project("Film Noir", format_mode="screenplay")
    scene = db.create_scene(
        proj.id,
        title="Interrogation",
        content="DETECTIVE stares across the table.",
        visible_conflict="Detective suspects the witness is lying",
        hidden_conflict="Detective knows the witness killed his partner",
        emotional_turn="From suspicion to certainty",
        physical_action="Detective slides photo across table",
        estimated_duration_minutes=3,
        setup_payoff_links="photo from scene 1 → reveal here",
    )
    return proj.id, scene.id


def test_screenplay_context_includes_analysis_section():
    db = Database()
    pid, sid = _make_screenplay_project(db)
    ctx = gather_scene_context(db, pid, sid)
    assert "[Screenplay Analysis]" in ctx


def test_screenplay_context_includes_duration():
    db = Database()
    pid, sid = _make_screenplay_project(db)
    ctx = gather_scene_context(db, pid, sid)
    assert "Estimated duration: 3 min" in ctx


def test_screenplay_context_includes_setup_payoff():
    db = Database()
    pid, sid = _make_screenplay_project(db)
    ctx = gather_scene_context(db, pid, sid)
    assert "Setup/payoff links:" in ctx
    assert "photo from scene 1" in ctx


def test_novel_project_has_no_screenplay_analysis():
    db = Database()
    proj = db.create_project("My Novel", format_mode="novel")
    scene = db.create_scene(
        proj.id,
        title="Chapter 1",
        content="The rain fell steadily.",
    )
    ctx = gather_scene_context(db, proj.id, scene.id)
    assert "[Screenplay Analysis]" not in ctx


def test_screenplay_context_includes_typed_relations():
    db = Database()
    proj = db.create_project("Relations Film", format_mode="screenplay")
    c1 = db.create_character(proj.id, name="ALICE")
    c2 = db.create_character(proj.id, name="BOB")
    scene = db.create_scene(
        proj.id, title="Reunion", character_ids=[c1.id, c2.id],
    )

    e1 = db.create_psyke_entry(proj.id, name="ALICE", entry_type="character")
    e2 = db.create_psyke_entry(proj.id, name="BOB", entry_type="character")
    db.add_psyke_relation(e1.id, e2.id, relation_type="supports_setup")

    ctx = gather_scene_context(db, proj.id, scene.id)
    assert "Typed relations:" in ctx
    assert "supports_setup" in ctx


def test_screenplay_context_empty_when_no_data():
    db = Database()
    proj = db.create_project("Empty Film", format_mode="screenplay")
    scene = db.create_scene(proj.id, title="Blank")
    ctx = gather_scene_context(db, proj.id, scene.id)
    # No duration, no setup/payoff → no analysis section
    assert "[Screenplay Analysis]" not in ctx


# =========================================================================
# 4. REVIEW CHECKS — screenplay-specific scene hints
# =========================================================================

def test_screenplay_hints_no_turn():
    db = Database()
    proj = db.create_project("Check Film", format_mode="screenplay")
    scene = db.create_scene(
        proj.id,
        title="Flat Scene",
        content=" ".join(["word"] * 60),
    )
    hints = generate_scene_hints(db, proj.id, scene.id)
    types = {h.hint_type for h in hints}
    assert "no_turn" in types


def test_screenplay_hints_no_visible_conflict():
    db = Database()
    proj = db.create_project("No Vis", format_mode="screenplay")
    scene = db.create_scene(
        proj.id,
        title="Talky Scene",
        content=" ".join(["word"] * 60),
    )
    hints = generate_scene_hints(db, proj.id, scene.id)
    types = {h.hint_type for h in hints}
    assert "no_visible_conflict" in types


def test_screenplay_hints_static_blocking():
    db = Database()
    proj = db.create_project("Static", format_mode="screenplay")
    scene = db.create_scene(
        proj.id,
        title="Still Scene",
        content=" ".join(["word"] * 60),
    )
    hints = generate_scene_hints(db, proj.id, scene.id)
    types = {h.hint_type for h in hints}
    assert "static_blocking" in types


def test_screenplay_hints_no_subtext():
    db = Database()
    proj = db.create_project("Surface", format_mode="screenplay")
    scene = db.create_scene(
        proj.id,
        title="On the Nose",
        content=" ".join(["word"] * 60),
    )
    hints = generate_scene_hints(db, proj.id, scene.id)
    types = {h.hint_type for h in hints}
    assert "no_subtext" in types


def test_screenplay_hints_no_duration():
    db = Database()
    proj = db.create_project("No Dur", format_mode="screenplay")
    scene = db.create_scene(
        proj.id,
        title="Untimed",
        content=" ".join(["word"] * 60),
    )
    hints = generate_scene_hints(db, proj.id, scene.id)
    types = {h.hint_type for h in hints}
    assert "no_duration" in types


def test_screenplay_hints_no_continuity():
    db = Database()
    proj = db.create_project("No Cont", format_mode="screenplay")
    char = db.create_character(proj.id, name="HERO")
    scene = db.create_scene(
        proj.id,
        title="Untracked",
        content=" ".join(["word"] * 60),
        character_ids=[char.id],
    )
    hints = generate_scene_hints(db, proj.id, scene.id)
    types = {h.hint_type for h in hints}
    assert "no_continuity" in types


def test_screenplay_filled_scene_has_no_screenplay_hints():
    """A properly filled screenplay scene should not trigger screenplay-specific hints."""
    db = Database()
    proj = db.create_project("Good Film", format_mode="screenplay")
    char = db.create_character(proj.id, name="HERO")
    scene = db.create_scene(
        proj.id,
        title="Complete Scene",
        content=" ".join(["word"] * 60),
        visible_conflict="Hero faces villain",
        hidden_conflict="Hero doubts himself",
        emotional_turn="From doubt to resolve",
        physical_action="Hero stands up, slams table",
        blocking_notes="Hero paces, then stops at window",
        estimated_duration_minutes=2,
        character_ids=[char.id],
    )
    db.add_memory(proj.id, scene.id, "continuity_wound", "HERO", "cut on left hand")
    hints = generate_scene_hints(db, proj.id, scene.id)
    screenplay_types = {
        "no_turn", "no_visible_conflict", "static_blocking",
        "no_subtext", "no_continuity", "no_duration",
    }
    flagged = {h.hint_type for h in hints} & screenplay_types
    assert flagged == set()


def test_novel_project_has_no_screenplay_hints():
    """Novel projects should not get screenplay-specific hints."""
    db = Database()
    proj = db.create_project("Novel", format_mode="novel")
    scene = db.create_scene(
        proj.id,
        title="Chapter One",
        content=" ".join(["word"] * 60),
    )
    hints = generate_scene_hints(db, proj.id, scene.id)
    screenplay_types = {
        "no_turn", "no_visible_conflict", "static_blocking",
        "no_subtext", "no_continuity", "no_duration",
    }
    flagged = {h.hint_type for h in hints} & screenplay_types
    assert flagged == set()


def test_review_metrics_include_screenplay_flags():
    db = Database()
    proj = db.create_project("Review Film", format_mode="screenplay")
    db.create_scene(
        proj.id,
        title="Weak Scene",
        content=" ".join(["word"] * 60),
    )
    metrics = compute_review_metrics(db, proj.id)
    flagged_types = {h.hint_type for h in metrics.flagged_scenes}
    assert "no_turn" in flagged_types


# =========================================================================
# 5. ENGINE RESOLUTION
# =========================================================================

def test_engine_resolved_for_screenplay_project():
    db = Database()
    proj = db.create_project("A Script", format_mode="screenplay")
    engine = engine_for_project(proj)
    assert engine.name == "screenplay"
    assert engine.system_prompt_overlay


def test_engine_resolved_for_novel_project():
    db = Database()
    proj = db.create_project("A Book", format_mode="novel")
    engine = engine_for_project(proj)
    assert engine.name == "novel"
    assert not engine.system_prompt_overlay
