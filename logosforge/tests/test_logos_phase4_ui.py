"""Logos Phase 4 — suggestion-bar + MainWindow integration tests."""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.ui.logos.logos_suggestions import LogosSuggestionBar
from logosforge.ui.main_window import MainWindow
from logosforge.logos.proactive.suggestion import LogosSuggestion, TYPE_PSYKE


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


def _suggestion():
    return LogosSuggestion(
        type=TYPE_PSYKE, title="Alice has no details", message="m",
        section_name="PSYKE", evidence="empty", confidence=0.9,
        severity="warning", target_type="psyke_entry", target_id="1",
        suggested_actions=["find_missing_details"],
    )


def _window():
    db = Database()
    pid = db.create_project("P", narrative_engine="novel").id
    db.create_psyke_entry(pid, "Alice", "character")
    db.create_scene(pid, "Opening", content="Alice walks. " * 30, summary="Alice", act="Act I")
    win = MainWindow(db, pid)
    win.resize(1400, 900)
    return win, db, pid


# -- Bar widget --------------------------------------------------------------


def test_bar_hidden_with_no_suggestions():
    bar = LogosSuggestionBar()
    bar.set_suggestions([])
    assert bar.suggestions() == []


def test_bar_renders_pills():
    bar = LogosSuggestionBar()
    bar.set_suggestions([_suggestion()])
    assert len(bar._pills) == 1


def test_bar_label_shows_count():
    bar = LogosSuggestionBar()
    bar.set_suggestions([])
    assert bar._label.text() == "Logos · no suggestions"
    bar.set_suggestions([_suggestion()])
    assert bar._label.text() == "Logos · 1 suggestion"          # singular
    bar.set_suggestions([_suggestion(), _suggestion()])
    assert bar._label.text() == "Logos · 2 suggestions"         # plural


def test_bar_does_not_steal_focus():
    from PySide6.QtCore import Qt
    bar = LogosSuggestionBar()
    assert bar.focusPolicy() == Qt.FocusPolicy.NoFocus


def test_bar_run_action_signal():
    bar = LogosSuggestionBar()
    s = _suggestion()
    bar.set_suggestions([s])
    captured = []
    bar.run_action.connect(lambda sug, name: captured.append((sug.id, name)))
    bar.run_action.emit(s, "find_missing_details")
    assert captured == [(s.id, "find_missing_details")]


# -- MainWindow integration --------------------------------------------------


def test_window_has_proactive_engine_and_bar():
    win, *_ = _window()
    assert hasattr(win, "_logos_engine")
    assert isinstance(win._logos_suggestions, LogosSuggestionBar)


def test_section_switch_scans_psyke():
    win, *_ = _window()
    win._logos_enabled = True  # inline Logos layer must be ON for suggestions
    win._show_psyke()
    win._set_active_section("PSYKE")
    QApplication.instance().processEvents()
    titles = [s.title for s in win._logos_suggestions.suggestions()]
    assert any("no details" in t for t in titles)


def test_bar_shown_when_suggestions_exist():
    win, *_ = _window()
    win._logos_enabled = True
    win._show_psyke()
    win._set_active_section("PSYKE")
    QApplication.instance().processEvents()
    assert not win._logos_suggestions.isHidden()  # visible (explicit setVisible)


def test_suppress_dismiss_removes_suggestion():
    win, *_ = _window()
    win._logos_enabled = True
    win._show_psyke(); win._set_active_section("PSYKE")
    QApplication.instance().processEvents()
    suggestions = win._logos_suggestions.suggestions()
    assert suggestions
    target = suggestions[0]
    win._on_logos_suggestion_suppress(target, "dismiss")
    QApplication.instance().processEvents()
    assert target.id not in {s.id for s in win._logos_suggestions.suggestions()}


def test_suggestion_action_opens_toolbar(monkeypatch):
    win, db, pid = _window()
    win._logos_enabled = True
    win._logos_controller._provider_resolver = lambda: object()
    win._logos_controller._chat_fn = lambda m, p: "Some detail"
    win._show_psyke(); win._set_active_section("PSYKE")
    QApplication.instance().processEvents()
    s = win._logos_suggestions.suggestions()[0]
    win._logos_visible = False
    win._on_logos_suggestion_action(s, s.suggested_actions[0])
    assert win._logos_visible is True  # toolbar revealed


def test_disabled_setting_hides_bar():
    import logosforge.settings as settings
    from logosforge.logos.proactive import ProactiveEngine
    win, db, pid = _window()
    settings.get_manager().set("logos_proactive_enabled", False)
    win._logos_engine = ProactiveEngine(db, pid)
    win._show_psyke(); win._set_active_section("PSYKE")
    QApplication.instance().processEvents()
    assert win._logos_suggestions.suggestions() == []
    assert win._logos_suggestions.isHidden()


def test_proactive_does_not_mutate_db():
    win, db, pid = _window()
    before = len(db.get_all_psyke_entries(pid))
    win._show_psyke(); win._set_active_section("PSYKE")
    win._refresh_logos_suggestions_command()
    QApplication.instance().processEvents()
    assert len(db.get_all_psyke_entries(pid)) == before


def test_assistant_unchanged_by_phase4():
    win, *_ = _window()
    assert hasattr(win, "_assistant_panel") and hasattr(win, "_assistant_dock")
    assert win._assistant_dock.panel is win._assistant_panel
