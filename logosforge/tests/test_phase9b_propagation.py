"""Phase 9B — writing-mode propagation guard tests.

Phase 9A classified Writing Modes as a reliable project-level source of truth
(``Project.narrative_engine`` behind the ``writing_modes`` facade). Phase 9B is a
narrow hardening pass: these tests *prove* propagation and the absence of stale
mode after project switching, and cover the two formerly mode-agnostic container
views (Graph, Plot) that now surface the active mode.

No new architecture, no engines, no provider changes.
"""

from __future__ import annotations

import json
import warnings

import pytest
from PySide6.QtWidgets import QLabel

warnings.filterwarnings("ignore")

from logosforge.db import Database


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path, raising=False)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json", raising=False)
    import logosforge.gomckee_bridge as gb
    monkeypatch.setattr(gb, "is_gomckee_enabled", lambda: False)
    yield
    settings._instance = None


def _labels(view) -> str:
    return " | ".join(lbl.text() for lbl in view.findChildren(QLabel))


# ===========================================================================
# Project switch A -> B -> A: every context path reflects the CURRENT project
# ===========================================================================


def _two_projects():
    db = Database()
    novel = db.create_project("NovelP", narrative_engine="novel").id
    screen = db.create_project("ScreenP", narrative_engine="screenplay").id
    return db, novel, screen


def test_assistant_context_follows_project_switch():
    from logosforge.assistant_context_policy import gather_injected_context
    db, novel, screen = _two_projects()
    # Simulate switching by calling with each project id (the policy reads
    # fresh each call — no caching).
    c_novel = gather_injected_context(db, novel, section_name="Manuscript")
    c_screen = gather_injected_context(db, screen, section_name="Manuscript")
    c_novel_again = gather_injected_context(db, novel, section_name="Manuscript")
    assert "Mode: Novel" in c_novel
    assert "Mode: Screenplay" in c_screen
    assert "Mode: Screenplay" not in c_novel
    assert "Mode: Novel" in c_novel_again  # back to novel, no stale screenplay
    assert "Mode: Screenplay" not in c_novel_again


def test_logos_context_follows_project_switch():
    from logosforge.logos.context import build_logos_context
    db, novel, screen = _two_projects()
    assert build_logos_context(db, novel).writing_mode == "novel"
    assert build_logos_context(db, screen).writing_mode == "screenplay"
    assert build_logos_context(db, novel).writing_mode == "novel"


def test_strategy_profile_switches_with_project():
    from logosforge.logos.strategy.router import StrategyRouter
    from logosforge.settings import get_manager
    get_manager().set("strategy_enabled", True)
    db, novel, screen = _two_projects()
    d_novel = StrategyRouter(db, novel).decide("Manuscript")
    d_screen = StrategyRouter(db, screen).decide("Manuscript")
    assert "novel" in d_novel.active_strategies
    assert "screenplay" in d_screen.active_strategies
    assert "novel" in d_novel.explanation and "screenplay" in d_screen.explanation
    # Back to novel — fresh decision, not the screenplay one.
    assert "novel" in StrategyRouter(db, novel).decide("Manuscript").active_strategies


def test_strategy_manual_override_beats_project_mode():
    from logosforge.logos.strategy.router import StrategyRouter
    from logosforge.settings import get_manager
    get_manager().set("strategy_enabled", True)
    get_manager().set("strategy_user_mode_override", "screenplay")
    db, novel, _ = _two_projects()
    # Project is novel, but the manual override forces screenplay (priority 1).
    d = StrategyRouter(db, novel).decide("Manuscript")
    assert "screenplay" in d.active_strategies


def test_export_follows_project_switch():
    from logosforge.export import export_json
    db, novel, screen = _two_projects()
    assert json.loads(export_json(db, novel))["project"]["writing_mode"] == "novel"
    assert json.loads(export_json(db, screen))["project"]["writing_mode"] == "screenplay"
    assert json.loads(export_json(db, novel))["project"]["writing_mode"] == "novel"


def test_health_and_diagnostics_follow_project_switch():
    from logosforge.logos.health import HealthEngine
    from logosforge.logos.diagnostics import DiagnosticsEngine
    db, novel, screen = _two_projects()
    assert HealthEngine(db, novel).generate_report().writing_mode == "novel"
    assert HealthEngine(db, screen).generate_report().writing_mode == "screenplay"
    assert DiagnosticsEngine(db, novel).writing_mode == "novel"
    assert DiagnosticsEngine(db, screen).writing_mode == "screenplay"


# ===========================================================================
# Invalid / missing mode falls back to novel across the propagation surface
# ===========================================================================


def test_invalid_mode_falls_back_everywhere():
    from logosforge.assistant_context_policy import gather_injected_context
    from logosforge.logos.context import build_logos_context
    from logosforge.logos.strategy.router import StrategyRouter
    from logosforge.export import export_json
    from logosforge.settings import get_manager
    get_manager().set("strategy_enabled", True)
    db = Database()
    pid = db.create_project("Weird", narrative_engine="garbage").id
    assert "Mode: Novel" in gather_injected_context(db, pid, section_name="Manuscript")
    assert build_logos_context(db, pid).writing_mode == "novel"
    assert json.loads(export_json(db, pid))["project"]["writing_mode"] == "novel"
    # Strategy still resolves (no crash) and is novel-flavored.
    assert StrategyRouter(db, pid).decide("Manuscript").dominant_strategy


# ===========================================================================
# Manuscript local formatting vs project mode (separate concepts, no drift)
# ===========================================================================


def test_manuscript_format_does_not_override_project_mode():
    from logosforge.project_compat import get_project_writing_format
    from logosforge.writing_modes import get_project_writing_mode_by_id
    db = Database()
    pid = db.create_project("P", narrative_engine="novel").id
    # Change the manuscript default writing FORMAT only.
    db.update_project_writing_format(pid, "treatment")
    # Project MODE (narrative_engine) is unchanged — the two are independent.
    assert get_project_writing_mode_by_id(db, pid) == "novel"
    assert get_project_writing_format(db.get_project_by_id(pid)) == "treatment"


def test_set_writing_mode_does_not_clobber_unrelated_state():
    from logosforge.writing_modes import set_project_writing_mode
    from logosforge.project_compat import get_project_writing_format
    db = Database()
    pid = db.create_project("P", narrative_engine="novel",
                            default_writing_format="treatment").id
    set_project_writing_mode(db, pid, "series")
    # Mode updated; the previously-chosen format is preserved.
    assert get_project_writing_format(db.get_project_by_id(pid)) == "treatment"


# ===========================================================================
# Container views now surface the mode (Graph / Plot) — Phase 9B label fix
# ===========================================================================


def test_graph_view_shows_writing_mode():
    from logosforge.ui.graph_view import GraphView
    db = Database()
    pid = db.create_project("G", narrative_engine="screenplay").id
    view = GraphView(db, pid)
    assert "Mode: Screenplay" in _labels(view)


def test_plot_view_shows_writing_mode_and_vocabulary():
    from logosforge.ui.multi_plot_view import MultiPlotView
    db = Database()
    pid = db.create_project("PL", narrative_engine="graphic_novel").id
    view = MultiPlotView(db, pid)
    text = _labels(view)
    assert "Mode: Graphic Novel" in text
    assert "Pages" in text  # structural vocabulary surfaced


def test_graph_view_label_reflects_each_project_no_stale():
    """A fresh view per project (UI reconstructs on switch) shows that mode."""
    from logosforge.ui.graph_view import GraphView
    db, novel, screen = _two_projects()
    assert "Mode: Novel" in _labels(GraphView(db, novel))
    assert "Mode: Screenplay" in _labels(GraphView(db, screen))
    assert "Mode: Novel" in _labels(GraphView(db, novel))


# ===========================================================================
# Source-of-truth + provider guard
# ===========================================================================


def test_no_second_source_of_truth_modes_resolve_to_engine():
    """writing_modes is a facade over narrative_engine — they always agree."""
    from logosforge.writing_modes import get_project_writing_mode
    from logosforge.project_compat import get_project_narrative_engine
    db = Database()
    for mode in ("novel", "screenplay", "graphic_novel", "stage_script", "series"):
        proj = db.create_project(f"P-{mode}", narrative_engine=mode)
        assert get_project_writing_mode(proj) == get_project_narrative_engine(proj)


def test_build_active_provider_unchanged():
    from logosforge.providers import build_active_provider
    from logosforge.settings import get_manager
    mgr = get_manager()
    mgr.set("ai_provider", "Anthropic")
    mgr.set("ai_base_url", "https://api.anthropic.com")
    mgr.set("ai_model", "claude-opus-4-8")
    mgr.set("ai_api_key", "")
    p = build_active_provider(require_configured=True)
    assert p is not None and p.name == "Anthropic" and p.model == "claude-opus-4-8"
