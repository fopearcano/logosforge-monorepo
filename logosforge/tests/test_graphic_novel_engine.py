"""Tests for the Graphic Novel narrative engine."""

from __future__ import annotations

from logosforge.db import Database
from logosforge.narrative_engines import (
    ALL_ENGINES,
    ENGINE_ORDER,
    GRAPHIC_NOVEL_ENGINE,
    NOVEL_ENGINE,
    SCREENPLAY_ENGINE,
    NarrativeEngine,
    engine_for_project,
    get_engine,
)
from logosforge.project_compat import (
    ENGINE_GRAPHIC_NOVEL,
    FORMAT_GRAPHIC_NOVEL,
    get_project_narrative_engine,
)


# =========================================================================
# A. Registry surface
# =========================================================================

def test_graphic_novel_engine_registered():
    assert "graphic_novel" in ALL_ENGINES
    assert ALL_ENGINES["graphic_novel"] is GRAPHIC_NOVEL_ENGINE


def test_graphic_novel_in_engine_order():
    assert "graphic_novel" in ENGINE_ORDER
    assert set(ENGINE_ORDER) <= set(ALL_ENGINES.keys())


def test_get_engine_returns_graphic_novel():
    assert get_engine("graphic_novel") is GRAPHIC_NOVEL_ENGINE


def test_engine_is_typed():
    assert isinstance(GRAPHIC_NOVEL_ENGINE, NarrativeEngine)


def test_engine_id_matches_project_compat_constant():
    assert GRAPHIC_NOVEL_ENGINE.name == ENGINE_GRAPHIC_NOVEL


# =========================================================================
# B. Structural units / plot unit / timeline (§2, §4, §5)
# =========================================================================

def test_structural_units_hierarchy():
    assert GRAPHIC_NOVEL_ENGINE.structural_units == (
        "issue", "chapter", "sequence", "page", "panel",
    )


def test_plot_unit_is_sequence_not_chapter():
    assert GRAPHIC_NOVEL_ENGINE.get_plot_block_unit() == "sequence"
    assert GRAPHIC_NOVEL_ENGINE.get_plot_block_unit() != "chapter"


def test_timeline_semantics_is_reading_progression():
    assert GRAPHIC_NOVEL_ENGINE.get_timeline_semantics() == "reading_progression"
    # Distinct from the other engines' timelines.
    assert (
        GRAPHIC_NOVEL_ENGINE.get_timeline_semantics()
        != SCREENPLAY_ENGINE.get_timeline_semantics()
    )
    assert (
        GRAPHIC_NOVEL_ENGINE.get_timeline_semantics()
        != NOVEL_ENGINE.get_timeline_semantics()
    )


# =========================================================================
# C. Engine priorities (§3)
# =========================================================================

def test_priorities_cover_comics_craft():
    p = GRAPHIC_NOVEL_ENGINE.get_assistant_priorities()
    for expected in (
        "panel rhythm",
        "page turns",
        "visual reveal timing",
        "composition",
        "image/text balance",
        "visual continuity",
        "symbolic recurrence",
        "silhouette readability",
        "panel flow",
        "emotional page energy",
    ):
        assert expected in p


# =========================================================================
# D. PSYKE visual extensions (§6) + review checks (§7)
# =========================================================================

def test_psyke_rules_are_visual_memory():
    rules = GRAPHIC_NOVEL_ENGINE.get_psyke_context_rules()
    for expected in (
        "character visual identity",
        "motif recurrence",
        "object continuity",
        "costume continuity",
        "shape language",
        "symbolic tracking",
    ):
        assert expected in rules


def test_review_checks_cover_panel_and_page_concerns():
    checks = GRAPHIC_NOVEL_ENGINE.get_review_checks()
    for expected in (
        "panel readability",
        "exposition density",
        "page turn impact",
        "visual pacing",
        "balloon overload",
        "symbolic recurrence",
    ):
        assert expected in checks


def test_engine_has_feedback_patterns_and_overlay():
    assert GRAPHIC_NOVEL_ENGINE.feedback_patterns
    assert GRAPHIC_NOVEL_ENGINE.system_prompt_overlay
    # Reasons as comics, not prose/film.
    overlay = GRAPHIC_NOVEL_ENGINE.system_prompt_overlay.lower()
    assert "comics" in overlay or "panel" in overlay


# =========================================================================
# E. Format pairing
# =========================================================================

def test_default_format_is_graphic_novel():
    assert GRAPHIC_NOVEL_ENGINE.default_format == FORMAT_GRAPHIC_NOVEL


# =========================================================================
# F. Engine selectable / project stores engine (§8)
# =========================================================================

def test_project_stores_graphic_novel_engine():
    db = Database()
    proj = db.create_project(
        "My GN",
        narrative_engine="graphic_novel",
        default_writing_format="graphic_novel",
    )
    assert proj.narrative_engine == "graphic_novel"
    assert get_project_narrative_engine(proj) == "graphic_novel"


def test_engine_for_project_resolves_graphic_novel():
    db = Database()
    proj = db.create_project("My GN", narrative_engine="graphic_novel")
    assert engine_for_project(proj) is GRAPHIC_NOVEL_ENGINE


def test_engine_for_project_legacy_format_mode():
    """A legacy project carrying only format_mode='graphic_novel' resolves
    to the real engine now (previously fell back to Novel)."""
    db = Database()
    proj = db.create_project("Legacy GN", format_mode="graphic_novel")
    assert engine_for_project(proj) is GRAPHIC_NOVEL_ENGINE


# =========================================================================
# G. Plot / timeline adapt (§4, §5)
# =========================================================================

def test_plot_and_timeline_adapt_per_engine():
    db = Database()
    gn = db.create_project("GN", narrative_engine="graphic_novel")
    novel = db.create_project("Nov", narrative_engine="novel")
    gn_engine = engine_for_project(gn)
    novel_engine = engine_for_project(novel)
    # Plot block unit differs from novel (sequence vs chapter).
    assert gn_engine.get_plot_block_unit() == "sequence"
    assert novel_engine.get_plot_block_unit() == "chapter"
    # Timeline semantics differ.
    assert gn_engine.get_timeline_semantics() == "reading_progression"
    assert novel_engine.get_timeline_semantics() != "reading_progression"


def test_context_block_identifies_graphic_novel():
    block = GRAPHIC_NOVEL_ENGINE.format_context_block()
    assert "[Narrative Engine: Graphic Novel]" in block
    assert "Plot block: sequence" in block
    assert "Timeline: reading_progression" in block
    assert "panel rhythm" in block


# =========================================================================
# H. Backward compatibility (§8)
# =========================================================================

def test_old_novel_projects_unaffected():
    db = Database()
    proj = db.create_project("Book")  # default novel
    assert engine_for_project(proj) is NOVEL_ENGINE


def test_screenplay_projects_unaffected():
    db = Database()
    proj = db.create_project("Film", format_mode="screenplay")
    assert engine_for_project(proj) is SCREENPLAY_ENGINE


def test_unknown_engine_still_falls_back():
    assert get_engine("nonsense") is NOVEL_ENGINE


def test_graphic_novel_block_differs_from_others():
    gn = GRAPHIC_NOVEL_ENGINE.format_context_block()
    assert gn != NOVEL_ENGINE.format_context_block()
    assert gn != SCREENPLAY_ENGINE.format_context_block()
