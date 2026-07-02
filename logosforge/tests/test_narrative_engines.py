"""Tests for the narrative-engine registry and the screenplay engine."""

from __future__ import annotations

import pytest

from logosforge.db import Database
from logosforge.narrative_engines import (
    ALL_ENGINES,
    ENGINE_ORDER,
    NOVEL_ENGINE,
    SCREENPLAY_ENGINE,
    NarrativeEngine,
    engine_for_project,
    get_engine,
)


# -- Registry surface --------------------------------------------------------

def test_registry_contains_novel_and_screenplay():
    assert NOVEL_ENGINE.name in ALL_ENGINES
    assert SCREENPLAY_ENGINE.name in ALL_ENGINES


def test_engine_order_matches_registry():
    assert set(ENGINE_ORDER) <= set(ALL_ENGINES.keys())


def test_get_engine_returns_novel_for_empty():
    assert get_engine("") is NOVEL_ENGINE
    assert get_engine(None) is NOVEL_ENGINE


def test_get_engine_returns_screenplay():
    assert get_engine("screenplay") is SCREENPLAY_ENGINE


def test_unknown_engine_falls_back_to_novel():
    """Truly unknown engine names fall back to Novel, never crash. All
    five named engines (novel/screenplay/graphic_novel/stage_script/series)
    are real.
    """
    assert get_engine("nonsense") is NOVEL_ENGINE
    assert get_engine("brand_new_engine") is NOVEL_ENGINE


def test_engine_for_project_none_returns_novel():
    assert engine_for_project(None) is NOVEL_ENGINE


def test_engine_for_project_screenplay():
    db = Database()
    proj = db.create_project("Film", format_mode="screenplay")
    assert engine_for_project(proj) is SCREENPLAY_ENGINE


def test_engine_for_project_default_novel():
    db = Database()
    proj = db.create_project("Book")  # default format_mode == "novel"
    assert engine_for_project(proj) is NOVEL_ENGINE


# -- Novel engine -----------------------------------------------------------

def test_novel_engine_structural_units():
    assert NOVEL_ENGINE.structural_units == ("part", "chapter", "scene")


def test_novel_engine_plot_block_is_chapter():
    assert NOVEL_ENGINE.get_plot_block_unit() == "chapter"


def test_novel_engine_priorities_include_interiority():
    priorities = NOVEL_ENGINE.get_assistant_priorities()
    assert "interiority" in priorities
    assert "prose rhythm" in priorities


def test_novel_engine_review_checks_include_chapter_purpose():
    assert "chapter purpose" in NOVEL_ENGINE.get_review_checks()


# -- Screenplay engine ------------------------------------------------------

def test_screenplay_engine_structural_units():
    assert SCREENPLAY_ENGINE.structural_units == ("act", "sequence", "scene", "beat")


def test_screenplay_engine_plot_block_is_scene():
    assert SCREENPLAY_ENGINE.get_plot_block_unit() == "scene"


def test_screenplay_engine_timeline_semantics_is_screen_time():
    assert SCREENPLAY_ENGINE.get_timeline_semantics() == "screen_time"


def test_screenplay_engine_priorities_include_setup_payoff():
    priorities = SCREENPLAY_ENGINE.get_assistant_priorities()
    assert "setup/payoff" in priorities
    assert "visual action" in priorities
    assert "dialogue economy" in priorities
    assert "blocking" in priorities
    assert "subtext" in priorities


def test_screenplay_engine_review_checks_include_scene_turns():
    checks = SCREENPLAY_ENGINE.get_review_checks()
    assert "scene turns" in checks
    assert "dialogue economy" in checks


def test_screenplay_engine_psyke_rules_include_subtext():
    rules = SCREENPLAY_ENGINE.get_psyke_context_rules()
    assert "subtext state" in rules
    assert "visual motifs" in rules


# -- Prompt block ------------------------------------------------------------

def test_engine_format_context_block_includes_label_and_priorities():
    block = SCREENPLAY_ENGINE.format_context_block()
    assert "[Narrative Engine: Screenplay]" in block
    assert "visual action" in block
    assert "Plot block: scene" in block
    assert "Timeline: screen_time" in block


def test_novel_engine_block_differs_from_screenplay():
    a = NOVEL_ENGINE.format_context_block()
    b = SCREENPLAY_ENGINE.format_context_block()
    assert a != b
    assert "interiority" in a
    assert "interiority" not in b


# -- Engine is engine (NarrativeEngine instance) ----------------------------

def test_engine_instances_are_typed():
    assert isinstance(NOVEL_ENGINE, NarrativeEngine)
    assert isinstance(SCREENPLAY_ENGINE, NarrativeEngine)
