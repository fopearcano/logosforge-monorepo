"""Logos Phase 0 — MainWindow + toolbar integration tests.

Verifies the inline Logos entry points in Manuscript and Outline, that the
toolbar is section-aware and non-intrusive, and — critically — that the
existing AssistantPanel / AssistantDock are present and unchanged.
"""

from __future__ import annotations

import time
import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.ui.logos.logos_toolbar import LogosToolbar
from logosforge.ui.main_window import MainWindow


def _wait_for_action(toolbar: LogosToolbar, timeout_ms: int = 15000) -> None:
    """Deterministically wait for the toolbar's async action to finish.

    The action runs on a ``_LogosWorker`` QThread and signals completion via the
    cross-thread ``done`` → ``action_completed`` chain. The previous helper spun
    a plain event loop against a fixed 4s timeout, which under heavy full-suite
    load could expire *before* the worker delivered its result (a flaky race).

    Instead, join the worker thread itself (the toolbar clears ``_worker`` to
    ``None`` in ``_on_done`` once the queued result has been rendered) and drain
    queued signals, so the ``action_completed`` slots have definitely run before
    the caller asserts. Falls back to the timeout only as a hard safety stop.
    """
    app = QApplication.instance()
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        app.processEvents()
        worker = toolbar._worker
        if worker is None:
            # Either the action ran synchronously (no worker started) or
            # _on_done already cleared it; drain any last queued slots.
            app.processEvents()
            return
        worker.wait(50)  # block until the QThread's run() returns
    app.processEvents()


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
    pid = db.create_project("P", narrative_engine="novel").id
    db.create_scene(pid, "Opening", act="Act I", content="The hero walks.")
    win = MainWindow(db, pid)
    win.resize(1400, 900)
    return win, db, pid


def test_window_has_logos_controller_and_hidden_toolbar():
    win, _, _ = _window()
    assert hasattr(win, "_logos_controller")
    assert isinstance(win._logos_toolbar, LogosToolbar)
    assert win._logos_visible is False  # hidden / non-intrusive by default


def test_assistant_panel_and_dock_unchanged_by_logos():
    win, _, _ = _window()
    # The Phase 1 assistant architecture is still intact and separate.
    assert hasattr(win, "_assistant_panel")
    assert hasattr(win, "_assistant_dock")
    assert win._assistant_dock.panel is win._assistant_panel
    # Logos toolbar is not the assistant panel.
    assert win._logos_toolbar is not win._assistant_panel


def test_toggle_logos_shows_manuscript_actions():
    win, _, _ = _window()
    win._show_manuscript()
    win._set_active_section("Manuscript")
    win._toggle_logos()
    QApplication.instance().processEvents()
    assert win._logos_visible is True
    combo = win._logos_toolbar._action_combo
    labels = [combo.itemText(i) for i in range(combo.count())]
    assert "Explain Selection" in labels
    assert "Rewrite Options" in labels
    assert "Counterpart Critique" in labels


def test_toolbar_actions_update_on_section_switch():
    win, _, _ = _window()
    win._show_manuscript(); win._set_active_section("Manuscript")
    win._toggle_logos()  # show
    win._show_plan(); win._set_active_section("Outline")
    QApplication.instance().processEvents()
    combo = win._logos_toolbar._action_combo
    labels = [combo.itemText(i) for i in range(combo.count())]
    assert "Identify Structure Problem" in labels
    assert "Explain Selection" not in labels  # manuscript-only


def test_build_logos_context_from_window():
    win, _, pid = _window()
    win._show_manuscript(); win._set_active_section("Manuscript")
    QApplication.instance().processEvents()
    ctx = win._build_logos_context()
    assert ctx.project_id == pid
    assert ctx.section_name == "Manuscript"
    assert ctx.narrative_engine == "novel"


def test_outline_context_has_template_field():
    win, _, _ = _window()
    win._show_plan(); win._set_active_section("Outline")
    QApplication.instance().processEvents()
    ctx = win._build_logos_context()
    assert ctx.section_name == "Outline"
    assert ctx.active_block_type == "outline_node"
    assert hasattr(ctx, "outline_template")


def test_toolbar_run_action_renders_result_with_injected_chat():
    win, _, sid = _window()
    win._show_manuscript(); win._set_active_section("Manuscript")
    win._toggle_logos()
    win._logos_controller._provider_resolver = lambda: object()
    win._logos_controller._chat_fn = lambda m, p: "A weakness.\n- point A"
    # identify_weakness does not require a selection.
    win._detect_active_scene_id = lambda: sid
    done = []
    win._logos_toolbar.action_completed.connect(lambda n, ok: done.append((n, ok)))
    win._logos_toolbar.run_action("identify_weakness")
    _wait_for_action(win._logos_toolbar)
    assert done == [("identify_weakness", True)]
    assert "A weakness." in win._logos_toolbar.result_text()
    # Result is copyable and dismissible.
    assert win._logos_toolbar._copy_btn.isEnabled()
    win._logos_toolbar.clear_result()
    assert win._logos_toolbar.result_text() == ""


def test_outline_node_run_via_descriptor():
    win, _, sid = _window()
    win._show_plan(); win._set_active_section("Outline")
    win._logos_controller._provider_resolver = lambda: object()
    win._logos_controller._chat_fn = lambda m, p: "Node summary."
    done = []
    win._logos_toolbar.action_completed.connect(lambda n, ok: done.append((n, ok)))
    win._run_logos_outline(
        {"kind": "scene", "scene_id": sid, "label": "Opening"}, "summarize_node",
    )
    _wait_for_action(win._logos_toolbar)
    assert done == [("summarize_node", True)]
    assert "Node summary." in win._logos_toolbar.result_text()


def test_toolbar_does_not_grab_focus():
    win, _, _ = _window()
    from PySide6.QtCore import Qt
    assert win._logos_toolbar.focusPolicy() == Qt.FocusPolicy.NoFocus


def test_logos_toggle_does_not_mutate_db():
    win, db, pid = _window()
    before = len(db.get_all_scenes(pid))
    win._show_manuscript(); win._set_active_section("Manuscript")
    win._toggle_logos()
    win._logos_controller._provider_resolver = lambda: None  # offline preview
    win._logos_toolbar.run_action("identify_weakness")
    _wait_for_action(win._logos_toolbar)
    assert len(db.get_all_scenes(pid)) == before
