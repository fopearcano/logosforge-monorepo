"""Logos Phase 7 — /strategy command + status indicator integration."""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

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
    # Silence message boxes from command dispatch.
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    # Pin gomckee OFF (process-global plugin singleton may leak from other suites).
    import logosforge.gomckee_bridge as gb
    monkeypatch.setattr(gb, "is_gomckee_enabled", lambda: False)
    yield
    settings._instance = None


def _window(engine="screenplay"):
    db = Database()
    pid = db.create_project("Saga", narrative_engine=engine).id
    db.create_scene(pid, "S1", act="Act I", summary="x")
    win = MainWindow(db, pid)
    win.resize(1400, 900)
    return win, db, pid


def test_window_has_strategy_router():
    win, *_ = _window()
    assert hasattr(win, "_strategy_router")
    d = win._strategy_router.decide("Manuscript")
    assert d.dominant_strategy == "screenplay"


def test_strategy_command_registered():
    win, *_ = _window()
    assert win._command_registry.resolve("strategy") is not None


def test_strategy_command_explain_dispatches():
    win, *_ = _window()
    # Should not raise; explain returns a message dict.
    win._on_console_command("strategy", ["explain"])


def test_strategy_command_mode_override():
    import logosforge.settings as settings
    win, *_ = _window("novel")
    win._on_console_command("strategy", ["mode", "screenplay"])
    assert settings.get_manager().get("strategy_user_mode_override") == "screenplay"
    assert win._strategy_router.decide("Manuscript").dominant_strategy == "screenplay"


def test_strategy_command_off_on():
    import logosforge.settings as settings
    win, *_ = _window()
    win._on_console_command("strategy", ["off"])
    assert settings.get_manager().get("strategy_enabled") is False
    win._on_console_command("strategy", ["on"])
    assert settings.get_manager().get("strategy_enabled") is True


def test_strategy_command_bad_mode_does_not_crash():
    win, *_ = _window()
    win._on_console_command("strategy", ["mode", "does_not_exist"])  # no raise


def test_health_drawer_shows_strategy_indicator():
    win, *_ = _window("screenplay")
    win._toggle_health()
    QApplication.instance().processEvents()
    assert "Screenplay Strategy" in win._health_drawer._strategy.text()


def test_indicator_hidden_when_setting_off():
    import logosforge.settings as settings
    win, *_ = _window()
    settings.get_manager().set("strategy_show_indicator", False)
    win._update_strategy_indicator()
    assert win._health_drawer._strategy.text() == ""


def test_strategy_does_not_mutate_db():
    win, db, pid = _window()
    before = len(db.get_all_scenes(pid))
    win._update_strategy_indicator()
    win._strategy_router.decide("Manuscript")
    assert len(db.get_all_scenes(pid)) == before


def test_assistant_unchanged_by_phase7():
    win, *_ = _window()
    assert hasattr(win, "_assistant_panel") and hasattr(win, "_assistant_dock")
    assert win._assistant_dock.panel is win._assistant_panel
