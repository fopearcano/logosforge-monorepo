"""Tests for the Narrative Suggestion Engine."""

from logosforge.db import Database
from logosforge.narrative_suggestions import (
    SUGGESTION_PROMPT,
    SuggestionContext,
    build_suggestion_messages,
    format_suggestion_debug,
)


def _setup_story(db):
    """Create a project with characters, progressions, relations, and scenes."""
    proj = db.create_project("Test Story")

    s1 = db.create_scene(
        proj.id, "The Meeting",
        content="Kael entered the tavern. Lyra was already waiting.",
    )
    s2 = db.create_scene(
        proj.id, "The Betrayal",
        content="Kael confronted Maren about the stolen map.",
    )
    s3 = db.create_scene(
        proj.id, "The Resolution",
        content="Kael stood alone in the ruins, the war finally over.",
    )

    kael = db.create_psyke_entry(
        proj.id, "Kael", entry_type="character",
        notes="Reluctant hero, former soldier",
    )
    lyra = db.create_psyke_entry(
        proj.id, "Lyra", entry_type="character",
        notes="Kael's trusted scout and confidant",
    )
    maren = db.create_psyke_entry(
        proj.id, "Maren", entry_type="character",
        notes="Childhood friend turned rival",
    )
    world_rule = db.create_psyke_entry(
        proj.id, "Blood Oath", entry_type="lore",
        is_global=True, notes="Breaking an oath costs a year of life",
    )

    db.add_psyke_relation(kael.id, lyra.id)
    db.add_psyke_relation(kael.id, maren.id)

    db.create_psyke_progression(kael.id, "Kael reluctantly agrees to lead")
    db.create_psyke_progression(maren.id, "Maren secretly plans betrayal")

    return proj, s1, s2, s3, kael, lyra, maren, world_rule


# -- build_suggestion_messages -------------------------------------------------

def test_builds_messages_for_valid_scene():
    db = Database()
    proj, s1, *_ = _setup_story(db)

    messages, ctx = build_suggestion_messages(db, proj.id, s1.id)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert ctx is not None


def test_messages_contain_suggestion_prompt():
    db = Database()
    proj, s1, *_ = _setup_story(db)

    messages, ctx = build_suggestion_messages(db, proj.id, s1.id)
    user_content = messages[1]["content"]
    assert "Escalation" in user_content
    assert "Reversal" in user_content
    assert "Internal Shift" in user_content


def test_system_prompt_is_narrative_advisor():
    db = Database()
    proj, s1, *_ = _setup_story(db)

    messages, _ = build_suggestion_messages(db, proj.id, s1.id)
    assert "narrative structure advisor" in messages[0]["content"]


def test_psyke_context_included_in_messages():
    db = Database()
    proj, s1, *_ = _setup_story(db)

    messages, ctx = build_suggestion_messages(db, proj.id, s1.id)
    user_content = messages[1]["content"]
    assert "Kael" in user_content
    assert ctx.psyke_context != ""


def test_returns_empty_for_invalid_scene():
    db = Database()
    proj = db.create_project("Empty")

    messages, ctx = build_suggestion_messages(db, proj.id, 9999)
    assert messages == []
    assert ctx is None


# -- Context metadata ----------------------------------------------------------

def test_context_tracks_entries():
    db = Database()
    proj, s1, *_ = _setup_story(db)

    _, ctx = build_suggestion_messages(db, proj.id, s1.id)
    assert "Kael" in ctx.entries_used or "Lyra" in ctx.entries_used


def test_context_tracks_temporal_state():
    db = Database()
    proj, s1, *_ = _setup_story(db)

    _, ctx = build_suggestion_messages(db, proj.id, s1.id)
    assert isinstance(ctx.temporal_used, bool)


def test_context_scene_order():
    db = Database()
    proj, s1, *_ = _setup_story(db)

    _, ctx = build_suggestion_messages(db, proj.id, s1.id)
    assert isinstance(ctx.scene_order, int)
    assert ctx.scene_id == s1.id


# -- Early / mid / late scenes ------------------------------------------------

def test_early_scene_includes_setup_characters():
    db = Database()
    proj, s1, *_ = _setup_story(db)

    messages, ctx = build_suggestion_messages(db, proj.id, s1.id)
    user_content = messages[1]["content"]
    assert "Kael" in user_content or "Lyra" in user_content


def test_mid_scene_includes_conflict_characters():
    db = Database()
    proj, _, s2, *rest = _setup_story(db)

    messages, ctx = build_suggestion_messages(db, proj.id, s2.id)
    user_content = messages[1]["content"]
    assert "Kael" in user_content or "Maren" in user_content


def test_late_scene_respects_progression():
    db = Database()
    proj, _, _, s3, kael, lyra, maren, _ = _setup_story(db)

    db.create_psyke_progression(kael.id, "Kael has won but lost everything")

    messages, ctx = build_suggestion_messages(db, proj.id, s3.id)
    assert ctx.temporal_used is True


# -- Globals in suggestions ---------------------------------------------------

def test_globals_included():
    db = Database()
    proj, s1, *_ = _setup_story(db)

    messages, ctx = build_suggestion_messages(db, proj.id, s1.id)
    user_content = messages[1]["content"]
    assert "Blood Oath" in user_content


# -- Relations influence -------------------------------------------------------

def test_relations_detected():
    db = Database()
    proj, s1, *_ = _setup_story(db)

    _, ctx = build_suggestion_messages(db, proj.id, s1.id)
    assert isinstance(ctx.relations_used, bool)


# -- format_suggestion_debug ---------------------------------------------------

def test_debug_format():
    ctx = SuggestionContext(
        scene_id=1,
        scene_order=5,
        entries_used=["Kael", "Lyra"],
        temporal_used=True,
        relations_used=True,
        orchestration_decisions=["2 global, 3 active at scene order 5"],
        psyke_context="[PSYKE Context]\n...",
    )
    debug = format_suggestion_debug(ctx)
    assert "brainstorm" in debug
    assert "Scene order: 5" in debug
    assert "Kael, Lyra" in debug
    assert "Temporal: yes" in debug
    assert "Relations: yes" in debug


def test_debug_empty_entries():
    ctx = SuggestionContext(
        scene_id=1,
        scene_order=0,
        entries_used=[],
        temporal_used=False,
        relations_used=False,
        orchestration_decisions=["No PSYKE entries"],
        psyke_context="",
    )
    debug = format_suggestion_debug(ctx)
    assert "(none)" in debug
    assert "Temporal: no" in debug


# -- No PSYKE entries ---------------------------------------------------------

def test_no_psyke_entries_still_produces_messages():
    db = Database()
    proj = db.create_project("Bare")
    scene = db.create_scene(proj.id, "Scene 1", content="A dark corridor.")

    messages, ctx = build_suggestion_messages(db, proj.id, scene.id)
    assert len(messages) == 2
    assert ctx is not None
    assert ctx.entries_used == []


# -- Suggestion prompt is well-formed -----------------------------------------

def test_suggestion_prompt_has_all_types():
    assert "Escalation" in SUGGESTION_PROMPT
    assert "Reversal" in SUGGESTION_PROMPT
    assert "Delay / Interruption" in SUGGESTION_PROMPT
    assert "Internal Shift" in SUGGESTION_PROMPT
    assert "Reveal" in SUGGESTION_PROMPT


def test_suggestion_prompt_constrains_format():
    assert "1-2 lines" in SUGGESTION_PROMPT
    assert "No dialogue" in SUGGESTION_PROMPT
    assert "no full paragraphs" in SUGGESTION_PROMPT
