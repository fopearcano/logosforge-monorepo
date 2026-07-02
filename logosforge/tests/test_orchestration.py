"""Tests for AI Orchestration with PSYKE (STEP 3)."""

from logosforge.db import Database
from logosforge.orchestration import (
    MODE_BRAINSTORM,
    MODE_DIALOGUE,
    MODE_EXPAND,
    MODE_REWRITE,
    OrchestrationResult,
    format_orchestration_debug,
    orchestrate_psyke_context,
    resolve_mode,
)


def _setup_project_with_entries(db):
    """Create a project with diverse PSYKE entries and a scene."""
    proj = db.create_project("Test")
    scene = db.create_scene(
        proj.id, "Battle Scene",
        content="Arwen drew her sword. Boromir shouted a warning.",
    )

    arwen = db.create_psyke_entry(
        proj.id, "Arwen", entry_type="character",
        notes="Elven warrior princess",
    )
    boromir = db.create_psyke_entry(
        proj.id, "Boromir", entry_type="character",
        notes="Captain of the White Tower",
    )
    sword = db.create_psyke_entry(
        proj.id, "Hadhafang", entry_type="object",
        notes="Arwen's elven blade",
    )
    rule = db.create_psyke_entry(
        proj.id, "Magic Fades", entry_type="lore",
        is_global=True, notes="Elven magic wanes in the Third Age",
    )

    db.add_psyke_relation(arwen.id, boromir.id)
    db.add_psyke_relation(arwen.id, sword.id)

    return proj, scene, arwen, boromir, sword, rule


# -- resolve_mode ---------------------------------------------------------------

def test_resolve_mode_rewrite():
    assert resolve_mode("Rewrite") == MODE_REWRITE
    assert resolve_mode("Tighten") == MODE_REWRITE
    assert resolve_mode("Tension") == MODE_REWRITE
    assert resolve_mode("Pacing") == MODE_REWRITE
    assert resolve_mode("Summarize") == MODE_REWRITE


def test_resolve_mode_dialogue():
    assert resolve_mode("Dialogue") == MODE_DIALOGUE


def test_resolve_mode_expand():
    assert resolve_mode("Expand") == MODE_EXPAND


def test_resolve_mode_brainstorm():
    assert resolve_mode("Next Beat") == MODE_BRAINSTORM
    assert resolve_mode("Brainstorm") == MODE_BRAINSTORM
    assert resolve_mode("Alternatives") == MODE_BRAINSTORM


def test_resolve_mode_unknown_defaults_to_rewrite():
    assert resolve_mode("UnknownAction") == MODE_REWRITE


# -- Same scene, different modes ------------------------------------------------

def test_rewrite_mode_compact():
    db = Database()
    proj, scene, arwen, boromir, sword, rule = _setup_project_with_entries(db)

    result = orchestrate_psyke_context(
        db, proj.id, scene.id, MODE_REWRITE,
    )
    assert result.mode == MODE_REWRITE
    assert "Arwen" in result.psyke_context
    assert "Boromir" in result.psyke_context
    assert result.relations_used is False
    assert "Magic Fades" not in result.psyke_context


def test_dialogue_mode_character_focus():
    db = Database()
    proj, scene, arwen, boromir, sword, rule = _setup_project_with_entries(db)

    result = orchestrate_psyke_context(
        db, proj.id, scene.id, MODE_DIALOGUE,
    )
    assert result.mode == MODE_DIALOGUE
    assert "Arwen" in result.psyke_context
    assert "Boromir" in result.psyke_context
    assert "Characters:" in result.psyke_context


def test_expand_mode_includes_globals():
    db = Database()
    proj, scene, arwen, boromir, sword, rule = _setup_project_with_entries(db)

    result = orchestrate_psyke_context(
        db, proj.id, scene.id, MODE_EXPAND,
    )
    assert result.mode == MODE_EXPAND
    assert "Magic Fades" in result.psyke_context
    assert "Global:" in result.psyke_context
    assert "Relevant:" in result.psyke_context


def test_brainstorm_mode_wide():
    db = Database()
    proj, scene, arwen, boromir, sword, rule = _setup_project_with_entries(db)

    result = orchestrate_psyke_context(
        db, proj.id, scene.id, MODE_BRAINSTORM,
    )
    assert result.mode == MODE_BRAINSTORM
    assert "Magic Fades" in result.psyke_context
    assert "Global:" in result.psyke_context


# -- Character with progression -------------------------------------------------

def test_rewrite_includes_progression():
    db = Database()
    proj, scene, arwen, boromir, sword, rule = _setup_project_with_entries(db)

    db.create_psyke_progression(arwen.id, "Arwen has claimed her birthright")

    result = orchestrate_psyke_context(
        db, proj.id, scene.id, MODE_REWRITE,
    )
    assert result.temporal_used is True
    assert "birthright" in result.psyke_context


def test_dialogue_includes_character_progression():
    db = Database()
    proj, scene, arwen, boromir, sword, rule = _setup_project_with_entries(db)

    db.create_psyke_progression(boromir.id, "Boromir is consumed by doubt")

    result = orchestrate_psyke_context(
        db, proj.id, scene.id, MODE_DIALOGUE,
    )
    assert result.temporal_used is True
    assert "consumed by doubt" in result.psyke_context


# -- Related entries ------------------------------------------------------------

def test_dialogue_includes_character_relations():
    db = Database()
    proj = db.create_project("Test")
    scene = db.create_scene(
        proj.id, "Talk Scene", content="Frodo and Sam spoke quietly.",
    )

    frodo = db.create_psyke_entry(
        proj.id, "Frodo", entry_type="character", notes="Ringbearer",
    )
    sam = db.create_psyke_entry(
        proj.id, "Sam", entry_type="character", notes="Loyal gardener",
    )
    merry = db.create_psyke_entry(
        proj.id, "Merry", entry_type="character", notes="Hobbit of Buckland",
    )
    db.add_psyke_relation(frodo.id, merry.id)

    result = orchestrate_psyke_context(
        db, proj.id, scene.id, MODE_DIALOGUE,
    )
    assert result.relations_used is True
    assert "Merry" in result.psyke_context
    assert "Related:" in result.psyke_context


def test_expand_conservative_relations():
    db = Database()
    proj, scene, arwen, boromir, sword, rule = _setup_project_with_entries(db)

    result = orchestrate_psyke_context(
        db, proj.id, scene.id, MODE_EXPAND,
    )
    if result.relations_used:
        assert "Related:" in result.psyke_context


# -- Globals --------------------------------------------------------------------

def test_globals_only_in_expand_and_brainstorm():
    db = Database()
    proj, scene, arwen, boromir, sword, rule = _setup_project_with_entries(db)

    rewrite_result = orchestrate_psyke_context(
        db, proj.id, scene.id, MODE_REWRITE,
    )
    assert "Magic Fades" not in rewrite_result.psyke_context

    dialogue_result = orchestrate_psyke_context(
        db, proj.id, scene.id, MODE_DIALOGUE,
    )
    assert "Magic Fades" not in dialogue_result.psyke_context

    expand_result = orchestrate_psyke_context(
        db, proj.id, scene.id, MODE_EXPAND,
    )
    assert "Magic Fades" in expand_result.psyke_context

    brainstorm_result = orchestrate_psyke_context(
        db, proj.id, scene.id, MODE_BRAINSTORM,
    )
    assert "Magic Fades" in brainstorm_result.psyke_context


# -- Selected text narrows rewrite context --------------------------------------

def test_rewrite_with_selected_text():
    db = Database()
    proj, scene, arwen, boromir, sword, rule = _setup_project_with_entries(db)

    result = orchestrate_psyke_context(
        db, proj.id, scene.id, MODE_REWRITE,
        selected_text="Arwen drew her sword",
    )
    assert "Arwen" in result.psyke_context
    assert "selection" in result.decisions[0].lower()


# -- Empty / edge cases ---------------------------------------------------------

def test_no_entries_returns_empty():
    db = Database()
    proj = db.create_project("Empty")
    scene = db.create_scene(proj.id, "Blank Scene", content="Nothing here.")

    result = orchestrate_psyke_context(
        db, proj.id, scene.id, MODE_REWRITE,
    )
    assert result.psyke_context == ""
    assert result.entries_included == []
    assert "No PSYKE entries" in result.decisions[0]


def test_scene_not_found():
    db = Database()
    proj = db.create_project("Test")
    db.create_psyke_entry(proj.id, "Hero", entry_type="character")

    result = orchestrate_psyke_context(
        db, proj.id, 9999, MODE_REWRITE,
    )
    assert result.psyke_context == ""
    assert "Scene not found" in result.decisions[0]


def test_no_matches_in_scene():
    db = Database()
    proj = db.create_project("Test")
    scene = db.create_scene(proj.id, "Empty", content="A quiet morning.")
    db.create_psyke_entry(
        proj.id, "Voldemort", entry_type="character", notes="Dark lord",
    )

    result = orchestrate_psyke_context(
        db, proj.id, scene.id, MODE_REWRITE,
    )
    assert result.psyke_context == ""
    assert "No entries matched" in result.decisions[0]


# -- Compact output (max entries) -----------------------------------------------

def test_max_entries_cap():
    db = Database()
    proj = db.create_project("Test")
    scene = db.create_scene(
        proj.id, "Crowd",
        content="Alice Bob Charlie Dave Eve Frank George Harry Ivan.",
    )
    for name in ["Alice", "Bob", "Charlie", "Dave", "Eve", "Frank", "George", "Harry", "Ivan"]:
        db.create_psyke_entry(proj.id, name, entry_type="character")

    result = orchestrate_psyke_context(
        db, proj.id, scene.id, MODE_REWRITE,
    )
    assert len(result.entries_included) <= 4


# -- format_orchestration_debug -------------------------------------------------

def test_format_debug_output():
    result = OrchestrationResult(
        mode=MODE_DIALOGUE,
        psyke_context="[PSYKE Context]\n...",
        entries_included=["Arwen", "Boromir"],
        temporal_used=True,
        relations_used=False,
        decisions=["Found 2 character entries in scene"],
    )
    debug = format_orchestration_debug(result)
    assert "dialogue" in debug
    assert "Arwen, Boromir" in debug
    assert "Temporal: yes" in debug
    assert "Relations: no" in debug
    assert "Found 2 character entries" in debug
