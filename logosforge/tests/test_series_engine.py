"""Tests for the Series narrative engine."""

from __future__ import annotations

from logosforge.db import Database
from logosforge.narrative_engines import (
    ALL_ENGINES,
    ENGINE_ORDER,
    NOVEL_ENGINE,
    SCREENPLAY_ENGINE,
    SERIES_ENGINE,
    NarrativeEngine,
    engine_for_project,
    get_engine,
)
from logosforge.project_compat import (
    ENGINE_SERIES,
    FORMAT_SERIES,
    get_project_narrative_engine,
)


# =========================================================================
# A. Registry surface
# =========================================================================

def test_series_engine_registered():
    assert "series" in ALL_ENGINES
    assert ALL_ENGINES["series"] is SERIES_ENGINE


def test_series_in_engine_order():
    assert "series" in ENGINE_ORDER
    assert set(ENGINE_ORDER) <= set(ALL_ENGINES.keys())


def test_get_engine_returns_series():
    assert get_engine("series") is SERIES_ENGINE


def test_engine_is_typed():
    assert isinstance(SERIES_ENGINE, NarrativeEngine)


def test_engine_id_matches_project_compat_constant():
    assert SERIES_ENGINE.name == ENGINE_SERIES


# =========================================================================
# B. Structural units / plot unit / timeline (§2, §4, §5)
# =========================================================================

def test_structural_units_hierarchy():
    assert SERIES_ENGINE.structural_units == (
        "series", "season", "episode", "act", "scene", "plotline", "arc",
    )


def test_plot_unit_is_episode():
    assert SERIES_ENGINE.get_plot_block_unit() == "episode"


def test_timeline_semantics_is_episode_season():
    assert SERIES_ENGINE.get_timeline_semantics() == "episode_season_progression"
    assert (
        SERIES_ENGINE.get_timeline_semantics()
        != SCREENPLAY_ENGINE.get_timeline_semantics()
    )
    assert (
        SERIES_ENGINE.get_timeline_semantics()
        != NOVEL_ENGINE.get_timeline_semantics()
    )


def test_terminology_block_is_episode():
    term = SERIES_ENGINE.assistant_terminology
    assert term["block"] == "episode"
    assert term["chapter"] == "season"


# =========================================================================
# C. Engine priorities (§3)
# =========================================================================

def test_priorities_cover_series_craft():
    p = SERIES_ENGINE.get_assistant_priorities()
    for expected in (
        "episode engine", "season arc", "series arc", "A/B/C plot balance",
        "continuity", "recurring motifs", "cliffhangers", "callbacks",
        "delayed payoff", "character progression across episodes",
        "unresolved threads", "serialized vs procedural balance",
    ):
        assert expected in p


# =========================================================================
# D. PSYKE series extensions (§6) + review checks (§7)
# =========================================================================

def test_psyke_rules_are_long_form():
    rules = SERIES_ENGINE.get_psyke_context_rules()
    for expected in (
        "long-running character states", "relationship evolution across episodes",
        "unresolved arcs", "mystery boxes", "recurring motifs",
        "continuity ledger", "episode memory", "season-level stakes",
    ):
        assert expected in rules


def test_review_checks_cover_series_concerns():
    checks = SERIES_ENGINE.get_review_checks()
    for expected in (
        "episode function", "season arc movement", "A/B/C plot interaction",
        "cliffhanger effectiveness", "continuity integrity",
        "long arc progression", "payoff timing",
    ):
        assert expected in checks


def test_engine_has_feedback_patterns_and_overlay():
    assert SERIES_ENGINE.feedback_patterns
    overlay = SERIES_ENGINE.system_prompt_overlay.lower()
    assert "showrunner" in overlay or "episode" in overlay


# =========================================================================
# E. Format pairing
# =========================================================================

def test_default_format_is_series():
    assert SERIES_ENGINE.default_format == FORMAT_SERIES


# =========================================================================
# F. Engine selectable / project stores engine (§8)
# =========================================================================

def test_project_stores_series_engine():
    db = Database()
    proj = db.create_project(
        "My Show", narrative_engine="series", default_writing_format="series",
    )
    assert proj.narrative_engine == "series"
    assert get_project_narrative_engine(proj) == "series"


def test_engine_for_project_resolves_series():
    db = Database()
    proj = db.create_project("Show", narrative_engine="series")
    assert engine_for_project(proj) is SERIES_ENGINE


def test_engine_for_project_legacy_format_mode():
    db = Database()
    proj = db.create_project("Legacy Show", format_mode="series")
    assert engine_for_project(proj) is SERIES_ENGINE


# =========================================================================
# G. Plot / timeline adapt (§4, §5)
# =========================================================================

def test_plot_and_timeline_adapt():
    db = Database()
    show = db.create_project("Show", narrative_engine="series")
    novel = db.create_project("Nov", narrative_engine="novel")
    se = engine_for_project(show)
    ne = engine_for_project(novel)
    assert se.get_plot_block_unit() == "episode"
    assert se.get_timeline_semantics() == "episode_season_progression"
    assert ne.get_plot_block_unit() == "chapter"


def test_context_block_identifies_series():
    block = SERIES_ENGINE.format_context_block()
    assert "[Narrative Engine: Series]" in block
    assert "Plot block: episode" in block
    assert "Timeline: episode_season_progression" in block
    assert "episode engine" in block


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
    assert get_engine("") is NOVEL_ENGINE


def test_block_differs_from_other_engines():
    block = SERIES_ENGINE.format_context_block()
    assert block != NOVEL_ENGINE.format_context_block()
    assert block != SCREENPLAY_ENGINE.format_context_block()
