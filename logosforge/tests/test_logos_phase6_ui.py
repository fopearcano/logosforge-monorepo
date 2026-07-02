"""Logos Phase 6 — health drawer + MainWindow integration tests."""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.ui.logos.logos_health import LogosHealthDrawer
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


def _window():
    db = Database()
    pid = db.create_project("Saga", narrative_engine="novel").id
    db.create_psyke_entry(pid, "Alice", "character")
    db.create_psyke_entry(pid, "Justice", "theme")
    for i in range(3):
        db.create_scene(pid, f"S{i}", act="Act I",
                        content="Alice acts. Justice.", summary="x" if i == 0 else "")
    win = MainWindow(db, pid)
    win.resize(1400, 900)
    return win, db, pid


# -- Drawer widget -----------------------------------------------------------


def test_drawer_does_not_steal_focus():
    from PySide6.QtCore import Qt
    drawer = LogosHealthDrawer()
    assert drawer.focusPolicy() == Qt.FocusPolicy.NoFocus


def test_drawer_sets_report():
    from logosforge.logos.health import HealthEngine
    drawer = LogosHealthDrawer()
    db = Database(); pid = db.create_project("P").id
    rep = HealthEngine(db, pid).generate_report()
    drawer.set_report(rep)
    assert drawer.report() is rep


# -- MainWindow integration --------------------------------------------------


def test_window_has_health_engine_and_drawer():
    win, *_ = _window()
    assert hasattr(win, "_health_engine")
    assert isinstance(win._health_drawer, LogosHealthDrawer)
    assert win._health_drawer.isHidden()  # hidden by default


def test_toggle_health_generates_and_shows():
    win, *_ = _window()
    win._toggle_health()
    QApplication.instance().processEvents()
    assert not win._health_drawer.isHidden()
    rep = win._health_drawer.report()
    assert rep is not None and len(rep.metrics) == 12


def test_refresh_health_command():
    win, *_ = _window()
    win._refresh_health()
    assert win._health_report is not None
    assert win._health_report.overall_status in (
        "stable", "watch", "weak", "critical", "unknown",
    )


def test_health_action_opens_toolbar():
    win, db, pid = _window()
    win._logos_controller._provider_resolver = lambda: object()
    win._logos_controller._chat_fn = lambda m, p: "detail"
    win._refresh_health()
    recs = [r for r in win._health_report.recommendations if r.suggested_action]
    assert recs
    win._logos_visible = False
    win._on_health_action(recs[0], recs[0].suggested_action)
    assert win._logos_visible is True


def test_export_health_json_and_markdown(tmp_path, monkeypatch):
    win, *_ = _window()
    win._refresh_health()
    from PySide6.QtWidgets import QFileDialog
    jpath = str(tmp_path / "h.json")
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (jpath, "JSON (*.json)")))
    win._export_health("json")
    import os, json
    assert os.path.exists(jpath)
    assert isinstance(json.load(open(jpath)), dict)

    mpath = str(tmp_path / "h.md")
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (mpath, "Markdown (*.md)")))
    win._export_health("markdown")
    assert os.path.exists(mpath)
    assert open(mpath).read().startswith("# Narrative Health")


def test_disabled_setting_yields_no_report():
    import logosforge.settings as settings
    win, *_ = _window()
    settings.get_manager().set("health_enabled", False)
    win._refresh_health()
    assert win._health_report is None
    assert win._health_drawer.report() is None


def test_health_does_not_mutate_db():
    win, db, pid = _window()
    before = len(db.get_all_psyke_entries(pid))
    win._refresh_health()
    win._toggle_health()
    QApplication.instance().processEvents()
    assert len(db.get_all_psyke_entries(pid)) == before


def test_assistant_unchanged_by_phase6():
    win, *_ = _window()
    assert hasattr(win, "_assistant_panel") and hasattr(win, "_assistant_dock")
    assert win._assistant_dock.panel is win._assistant_panel
