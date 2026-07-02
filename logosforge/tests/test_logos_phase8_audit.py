"""Logos Phase 8 — orchestration cleanup & integrity audit regression tests.

Locks in the fixes/invariants verified during the Phase 8 audit:

* project switch clears stale Logos suggestions and re-points every engine;
* the proactive bar never shows the previous project's findings after a switch;
* Assistant stays decoupled from the Logos analysis layers (no auto-injection);
* a single shared chat backend / provider path (no second client in logos/);
* scans never mutate the DB and never call the LLM.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.ui.main_window import MainWindow


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


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


def _two_projects():
    db = Database()
    p1 = db.create_project("P1", narrative_engine="novel").id
    db.create_psyke_entry(p1, "Alice", "character")  # detail-less -> suggestion
    db.create_scene(p1, "S1", content="Alice acts", summary="Alice")
    p2 = db.create_project("P2", narrative_engine="novel").id  # empty
    return db, p1, p2


# -- Project-switch stale-data (the headline fix) ----------------------------


def test_switch_clears_stale_suggestions():
    db, p1, p2 = _two_projects()
    win = MainWindow(db, p1)
    win.resize(1400, 900)
    win._logos_enabled = True  # inline Logos layer must be ON for suggestions
    win._show_psyke(); win._set_active_section("PSYKE")
    QApplication.instance().processEvents()
    assert win._logos_suggestions.suggestions()  # P1 has findings

    win._switch_project(p2)
    QApplication.instance().processEvents()
    # Empty P2 -> the previous project's suggestions must be gone.
    assert win._logos_suggestions.suggestions() == []


def test_switch_repoints_all_logos_engines():
    db, p1, p2 = _two_projects()
    win = MainWindow(db, p1)
    win._switch_project(p2)
    assert win._logos_engine._project_id == p2
    assert win._diagnostics_engine._project_id == p2
    assert win._health_engine._project_id == p2
    assert win._strategy_router._project_id == p2


def test_switch_clears_diagnostics_and_health_drawers():
    db, p1, p2 = _two_projects()
    win = MainWindow(db, p1)
    win._toggle_diagnostics()           # populate diagnostics for P1
    QApplication.instance().processEvents()
    win._switch_project(p2)
    QApplication.instance().processEvents()
    # Health report reset; diagnostics drawer not showing P1 data.
    assert win._health_report is None
    stale = [d for d in win._diagnostics_drawer.diagnostics()
             if d.target_id == "1"]
    assert stale == []


def test_switch_back_restores_findings():
    db, p1, p2 = _two_projects()
    win = MainWindow(db, p1)
    win._logos_enabled = True
    win._show_psyke(); win._set_active_section("PSYKE")
    win._switch_project(p2)
    win._switch_project(p1)
    QApplication.instance().processEvents()
    assert win._logos_engine._project_id == p1
    assert win._logos_suggestions.suggestions()  # P1 findings return


# -- Architecture invariants -------------------------------------------------


def test_single_logos_toolbar_and_engines():
    db, p1, _ = _two_projects()
    win = MainWindow(db, p1)
    from logosforge.ui.logos.logos_toolbar import LogosToolbar
    toolbars = win.findChildren(LogosToolbar)
    assert len(toolbars) == 1  # created once, not per section


def test_assistant_decoupled_from_logos_analysis():
    """Assistant must not auto-import Logos health/diagnostics/strategy."""
    import pathlib
    src = pathlib.Path("logosforge/ui/assistant_view.py").read_text(encoding="utf-8")
    for forbidden in ("logos.health", "logos.diagnostics", "logos.strategy",
                      "logos.proactive"):
        assert forbidden not in src, f"assistant_view imports {forbidden}"


def test_no_second_chat_client_in_logos():
    """The logos package must never construct its own LLM client."""
    import pathlib
    root = pathlib.Path("logosforge/logos")
    forbidden = ("import openai", "import anthropic", "OpenAI(", "Anthropic(",
                 "import httpx", "import requests")
    for py in root.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{py}: contains {token}"


def test_logos_does_not_store_api_keys():
    import pathlib
    root = pathlib.Path("logosforge/logos")
    for py in root.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        assert "ai_api_key" not in text, f"{py}: references ai_api_key"


# -- Safety: scans never mutate / never call LLM -----------------------------


def test_data_change_scan_is_loop_safe_and_clean(monkeypatch):
    import logosforge.assistant as assistant
    calls = []
    monkeypatch.setattr(assistant, "chat_completion",
                        lambda *a, **k: calls.append(1) or ("", False))
    db, p1, _ = _two_projects()
    win = MainWindow(db, p1)
    win._show_psyke(); win._set_active_section("PSYKE")
    before = (len(db.get_all_scenes(p1)), len(db.get_all_psyke_entries(p1)))
    win._on_data_changed()  # triggers scans
    QApplication.instance().processEvents()
    after = (len(db.get_all_scenes(p1)), len(db.get_all_psyke_entries(p1)))
    assert before == after          # no mutation
    assert calls == []              # no LLM during scans


def test_assistant_unchanged():
    db, p1, _ = _two_projects()
    win = MainWindow(db, p1)
    assert hasattr(win, "_assistant_panel") and hasattr(win, "_assistant_dock")
    assert win._assistant_dock.panel is win._assistant_panel
