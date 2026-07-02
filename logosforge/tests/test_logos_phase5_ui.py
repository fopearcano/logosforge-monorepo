"""Logos Phase 5 — diagnostics drawer + MainWindow integration tests."""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.logos.diagnostics.diagnostic import (
    CAT_CHARACTER,
    SEVERITY_WARNING,
    NarrativeDiagnostic,
)
from logosforge.ui.logos.logos_diagnostics import LogosDiagnosticsDrawer
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
    yield
    settings._instance = None


def _diag():
    return NarrativeDiagnostic(
        category=CAT_CHARACTER, title="Alice has no goals", message="m",
        section_name="PSYKE", evidence="empty", confidence=0.9,
        severity=SEVERITY_WARNING, target_type="psyke_entry", target_id="1",
        suggested_actions=["find_missing_details"],
    )


def _window():
    db = Database()
    pid = db.create_project("P", narrative_engine="novel").id
    db.create_psyke_entry(pid, "Alice", "character")
    db.create_scene(pid, "S1", act="Act I", content="Alice arrives. " * 10, summary="Alice")
    win = MainWindow(db, pid)
    win.resize(1400, 900)
    return win, db, pid


# -- Drawer widget -----------------------------------------------------------


def test_drawer_badge_and_rows():
    drawer = LogosDiagnosticsDrawer()
    drawer.set_diagnostics([_diag()])
    assert drawer._badge.text() == "1"
    assert len(drawer.diagnostics()) == 1


def test_drawer_does_not_steal_focus():
    from PySide6.QtCore import Qt
    drawer = LogosDiagnosticsDrawer()
    assert drawer.focusPolicy() == Qt.FocusPolicy.NoFocus


def test_drawer_run_action_signal():
    drawer = LogosDiagnosticsDrawer()
    d = _diag()
    drawer.set_diagnostics([d])
    captured = []
    drawer.run_action.connect(lambda diag, name: captured.append((diag.id, name)))
    drawer.run_action.emit(d, "find_missing_details")
    assert captured == [(d.id, "find_missing_details")]


# -- MainWindow integration --------------------------------------------------


def test_window_has_diagnostics_engine_and_drawer():
    win, *_ = _window()
    assert hasattr(win, "_diagnostics_engine")
    assert isinstance(win._diagnostics_drawer, LogosDiagnosticsDrawer)
    assert win._diagnostics_drawer.isHidden()  # hidden by default


def test_toggle_diagnostics_scans_and_shows():
    win, *_ = _window()
    win._show_psyke(); win._set_active_section("PSYKE")
    win._toggle_diagnostics()
    QApplication.instance().processEvents()
    assert not win._diagnostics_drawer.isHidden()
    titles = [d.title for d in win._diagnostics_drawer.diagnostics()]
    assert any("goals" in t or "no relations" in t.lower() for t in titles)


def test_project_scan_command_shows_drawer():
    win, *_ = _window()
    win._scan_diagnostics_project()
    QApplication.instance().processEvents()
    assert not win._diagnostics_drawer.isHidden()
    assert win._diagnostics_drawer.diagnostics()


def test_dismiss_diagnostic_removes_it():
    win, *_ = _window()
    win._show_psyke(); win._set_active_section("PSYKE")
    win._toggle_diagnostics()
    QApplication.instance().processEvents()
    diags = win._diagnostics_drawer.diagnostics()
    assert diags
    target = diags[0]
    win._on_diagnostic_suppress(target, "dismiss")
    QApplication.instance().processEvents()
    assert target.id not in {d.id for d in win._diagnostics_drawer.diagnostics()}


def test_diagnostic_action_opens_toolbar():
    win, db, pid = _window()
    win._logos_controller._provider_resolver = lambda: object()
    win._logos_controller._chat_fn = lambda m, p: "detail"
    win._show_psyke(); win._set_active_section("PSYKE")
    win._toggle_diagnostics()
    QApplication.instance().processEvents()
    d = win._diagnostics_drawer.diagnostics()[0]
    win._logos_visible = False
    win._on_diagnostic_action(d, d.suggested_actions[0])
    assert win._logos_visible is True


def test_diagnostics_scan_does_not_mutate_db():
    win, db, pid = _window()
    before = len(db.get_all_psyke_entries(pid))
    win._scan_diagnostics_project()
    QApplication.instance().processEvents()
    assert len(db.get_all_psyke_entries(pid)) == before


def test_assistant_unchanged_by_phase5():
    win, *_ = _window()
    assert hasattr(win, "_assistant_panel") and hasattr(win, "_assistant_dock")
    assert win._assistant_dock.panel is win._assistant_panel
