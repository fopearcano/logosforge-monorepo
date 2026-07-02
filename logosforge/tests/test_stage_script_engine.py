"""Tests for the Stage Script narrative engine."""

from __future__ import annotations

from logosforge.db import Database
from logosforge.narrative_engines import (
    ALL_ENGINES,
    ENGINE_ORDER,
    NOVEL_ENGINE,
    SCREENPLAY_ENGINE,
    STAGE_SCRIPT_ENGINE,
    NarrativeEngine,
    engine_for_project,
    get_engine,
)
from logosforge.project_compat import (
    ENGINE_STAGE_SCRIPT,
    FORMAT_STAGE_SCRIPT,
    get_project_narrative_engine,
)


# =========================================================================
# A. Registry surface
# =========================================================================

def test_stage_script_engine_registered():
    assert "stage_script" in ALL_ENGINES
    assert ALL_ENGINES["stage_script"] is STAGE_SCRIPT_ENGINE


def test_stage_script_in_engine_order():
    assert "stage_script" in ENGINE_ORDER
    assert set(ENGINE_ORDER) <= set(ALL_ENGINES.keys())


def test_get_engine_returns_stage_script():
    assert get_engine("stage_script") is STAGE_SCRIPT_ENGINE


def test_engine_is_typed():
    assert isinstance(STAGE_SCRIPT_ENGINE, NarrativeEngine)


def test_engine_id_matches_project_compat_constant():
    assert STAGE_SCRIPT_ENGINE.name == ENGINE_STAGE_SCRIPT


# =========================================================================
# B. Structural units / plot unit / timeline (§2, §4, §5)
# =========================================================================

def test_structural_units_hierarchy():
    assert STAGE_SCRIPT_ENGINE.structural_units == (
        "act", "scene", "beat", "entrance_exit", "cue",
    )


def test_plot_unit_is_scene():
    assert STAGE_SCRIPT_ENGINE.get_plot_block_unit() == "scene"


def test_scenes_grouped_by_acts():
    # block -> scene, chapter -> act terminology expresses the grouping.
    term = STAGE_SCRIPT_ENGINE.assistant_terminology
    assert term["block"] == "scene"
    assert term["chapter"] == "act"


def test_timeline_semantics_is_performance_order():
    assert STAGE_SCRIPT_ENGINE.get_timeline_semantics() == "performance_order"
    assert (
        STAGE_SCRIPT_ENGINE.get_timeline_semantics()
        != SCREENPLAY_ENGINE.get_timeline_semantics()
    )
    assert (
        STAGE_SCRIPT_ENGINE.get_timeline_semantics()
        != NOVEL_ENGINE.get_timeline_semantics()
    )


# =========================================================================
# C. Engine priorities (§3)
# =========================================================================

def test_priorities_cover_theatre_craft():
    p = STAGE_SCRIPT_ENGINE.get_assistant_priorities()
    for expected in (
        "playable conflict", "spoken pressure", "subtext", "actor motivation",
        "entrances/exits", "stage blocking", "physical business",
        "stageable action", "audience visibility", "prop continuity",
        "act breaks", "scene objective",
    ):
        assert expected in p


# =========================================================================
# D. PSYKE theatre extensions (§6) + review checks (§7)
# =========================================================================

def test_psyke_rules_are_theatrical():
    rules = STAGE_SCRIPT_ENGINE.get_psyke_context_rules()
    for expected in (
        "character stage objective", "spoken strategy", "subtext",
        "relationship pressure", "entrances/exits", "prop ownership",
        "offstage knowledge", "stage position",
    ):
        assert expected in rules


def test_review_checks_cover_stage_concerns():
    checks = STAGE_SCRIPT_ENGINE.get_review_checks()
    for expected in (
        "dialogue tension", "playable action", "actor motivation",
        "blocking clarity", "stage feasibility", "dramatic pressure",
        "actorial subtext",
    ):
        assert expected in checks


def test_engine_has_feedback_patterns_and_overlay():
    assert STAGE_SCRIPT_ENGINE.feedback_patterns
    overlay = STAGE_SCRIPT_ENGINE.system_prompt_overlay.lower()
    assert "playwright" in overlay or "stage" in overlay


# =========================================================================
# E. Format pairing
# =========================================================================

def test_default_format_is_stage_script():
    assert STAGE_SCRIPT_ENGINE.default_format == FORMAT_STAGE_SCRIPT


# =========================================================================
# F. Engine selectable / project stores engine (§8)
# =========================================================================

def test_project_stores_stage_script_engine():
    db = Database()
    proj = db.create_project(
        "My Play",
        narrative_engine="stage_script",
        default_writing_format="stage_script",
    )
    assert proj.narrative_engine == "stage_script"
    assert get_project_narrative_engine(proj) == "stage_script"


def test_engine_for_project_resolves_stage_script():
    db = Database()
    proj = db.create_project("Play", narrative_engine="stage_script")
    assert engine_for_project(proj) is STAGE_SCRIPT_ENGINE


def test_engine_for_project_legacy_format_mode():
    db = Database()
    proj = db.create_project("Legacy Play", format_mode="stage_script")
    assert engine_for_project(proj) is STAGE_SCRIPT_ENGINE


# =========================================================================
# G. Plot / timeline adapt (§4, §5)
# =========================================================================

def test_plot_and_timeline_adapt():
    db = Database()
    play = db.create_project("Play", narrative_engine="stage_script")
    novel = db.create_project("Nov", narrative_engine="novel")
    pe = engine_for_project(play)
    ne = engine_for_project(novel)
    assert pe.get_plot_block_unit() == "scene"          # scenes (grouped by acts)
    assert pe.get_timeline_semantics() == "performance_order"
    assert ne.get_plot_block_unit() == "chapter"
    assert ne.get_timeline_semantics() != "performance_order"


def test_context_block_identifies_stage_script():
    block = STAGE_SCRIPT_ENGINE.format_context_block()
    assert "[Narrative Engine: Stage Script]" in block
    assert "Plot block: scene" in block
    assert "Timeline: performance_order" in block
    assert "playable conflict" in block


# =========================================================================
# H. Backward compatibility (§8)
# =========================================================================

def test_old_novel_projects_unaffected():
    db = Database()
    proj = db.create_project("Book")
    assert engine_for_project(proj) is NOVEL_ENGINE


def test_screenplay_projects_unaffected():
    db = Database()
    proj = db.create_project("Film", format_mode="screenplay")
    assert engine_for_project(proj) is SCREENPLAY_ENGINE


def test_unknown_engine_falls_back():
    assert get_engine("nonsense") is NOVEL_ENGINE


def test_block_differs_from_other_engines():
    block = STAGE_SCRIPT_ENGINE.format_context_block()
    assert block != NOVEL_ENGINE.format_context_block()
    assert block != SCREENPLAY_ENGINE.format_context_block()
