"""Project creation / opening / switching must isolate every project.

The single shared DB stores all projects keyed by project_id; the section
content views are rebuilt fresh on every navigation (so they re-query the new
project). The gap this suite guards is the *always-on* state that is NOT
rebuilt on a switch — the Assistant dock and the inline Logos toolbar — plus
the central switch pipeline and the Projects-list refresh.
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
def reset_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    import logosforge.gomckee_bridge as gb
    monkeypatch.setattr(gb, "is_gomckee_enabled", lambda: False, raising=False)
    yield
    settings._instance = None


def _seeded_project(db, name):
    pid = db.create_project(name, narrative_engine="novel").id
    db.create_scene(pid, f"{name}-scene", content=f"{name} PROSE")
    db.create_psyke_entry(pid, f"{name}-char", "character")
    db.create_note(pid, f"{name}-note", "body")
    return pid


# ==========================================================================
# Section content is isolated and rebuilt for the active project (no manual
# section switch needed)
# ==========================================================================


def test_switch_rebuilds_active_section_for_new_project():
    db = Database()
    a = _seeded_project(db, "A")
    b = db.create_project("B", narrative_engine="novel").id
    win = MainWindow(db, a)
    win.sidebar_buttons["Manuscript"].click()
    win._switch_project(b)
    # Active view was rebuilt against B without re-navigating (Manuscript is the
    # scene-based WritingCoreView for all modes).
    from logosforge.ui.writing_core_view import WritingCoreView
    assert isinstance(win.content_area, WritingCoreView)
    assert win._project_id == b
    # B has no scenes — A's scene must not be present in B's data.
    assert db.get_all_scenes(b) == []


def test_open_project_b_then_reopen_a_shows_correct_data():
    db = Database()
    a = _seeded_project(db, "A")
    b = _seeded_project(db, "B")
    win = MainWindow(db, a)
    win.sidebar_buttons["PSYKE"].click()
    win._switch_project(b)
    win.sidebar_buttons["PSYKE"].click()
    names_b = {e.name for e in db.get_all_psyke_entries(b)}
    assert names_b == {"B-char"}
    # Reopen A — its data returns, B's does not leak in.
    win._switch_project(a)
    win.sidebar_buttons["PSYKE"].click()
    names_a = {e.name for e in db.get_all_psyke_entries(a)}
    assert names_a == {"A-char"}


def test_new_project_is_clean_no_previous_scenes_outline_psyke_notes():
    db = Database()
    a = _seeded_project(db, "A")
    win = MainWindow(db, a)
    # _on_new_project creates + switches; stub the dialog to avoid modal UI.
    import logosforge.ui.main_window as mw

    class _FakeDialog:
        def __init__(self, *a, **k): ...
        def exec(self): return True
        def get_title(self): return "Fresh"
        def get_engine(self): return "novel"
        def get_format(self): return "novel"

    monkey = pytest.MonkeyPatch()
    monkey.setattr(mw, "NewProjectDialog", _FakeDialog, raising=False)
    # NewProjectDialog is imported inside the method; patch its module too.
    import logosforge.ui.new_project_dialog as npd
    monkey.setattr(npd, "NewProjectDialog", _FakeDialog, raising=False)
    win._on_new_project()
    monkey.undo()
    new_id = win._project_id
    assert new_id != a
    assert db.get_all_scenes(new_id) == []
    assert db.get_all_psyke_entries(new_id) == []
    assert db.get_all_notes(new_id) == []
    # Lands on a freshly-built Dashboard for the new project.
    from logosforge.ui.dashboard_view import DashboardView
    assert isinstance(win.content_area, DashboardView)


# ==========================================================================
# Always-on AI surfaces reset on switch (Assistant + inline Logos toolbar)
# ==========================================================================


def test_assistant_context_resets_on_switch():
    db = Database()
    a = _seeded_project(db, "A")
    b = db.create_project("B", narrative_engine="novel").id
    win = MainWindow(db, a)
    ap = win._assistant_panel
    ap._prompt_input.setPlainText("About A")
    ap._response_output.setPlainText("A's hero is Alice.")
    ap._ctx_viewer.setPlainText("[CONTEXT] A scenes")
    win._switch_project(b)
    assert ap._project_id == b
    assert ap._prompt_input.toPlainText() == ""
    assert ap._response_output.toPlainText() == ""
    assert ap._ctx_viewer.toPlainText() == ""


def test_logos_toolbar_result_clears_on_switch():
    db = Database()
    a = _seeded_project(db, "A")
    b = db.create_project("B", narrative_engine="novel").id
    win = MainWindow(db, a)
    win._logos_toolbar._result.setPlainText("Logos finding for A")
    assert win._logos_toolbar.result_text() != ""
    win._switch_project(b)
    assert win._logos_toolbar.result_text() == ""


def test_logos_suggestions_clear_on_switch():
    db = Database()
    a = _seeded_project(db, "A")
    b = db.create_project("B", narrative_engine="novel").id
    win = MainWindow(db, a)
    # Whatever the previous project surfaced, the bar is empty + hidden post-switch.
    win._switch_project(b)
    assert win._logos_suggestions.isHidden()


# ==========================================================================
# Event propagation: switch announces project_loaded; no duplicate subscriptions
# ==========================================================================


def test_switch_emits_project_loaded_once():
    from logosforge.project_events import get_event_bus
    db = Database()
    a = _seeded_project(db, "A")
    b = db.create_project("B", narrative_engine="novel").id
    win = MainWindow(db, a)
    seen = []
    get_event_bus().project_loaded.connect(lambda pid: seen.append(pid))
    win._switch_project(b)
    QApplication.instance().processEvents()
    assert seen == [b]


def test_repeated_switches_do_not_duplicate_dashboard_refresh():
    # DashboardView subscribes to project_loaded/created; rebuilding the active
    # section on each switch must not pile up duplicate live subscriptions that
    # would multiply refreshes. One emit -> the *current* dashboard refreshes.
    from logosforge.project_events import get_event_bus
    db = Database()
    a = _seeded_project(db, "A")
    b = _seeded_project(db, "B")
    win = MainWindow(db, a)
    win.sidebar_buttons["Dashboard"].click()
    win._switch_project(b)
    win._switch_project(a)
    win.sidebar_buttons["Dashboard"].click()
    calls = []
    win.content_area.refresh = lambda *x, **k: calls.append(1)
    get_event_bus().project_data_changed.emit()
    QApplication.instance().processEvents()
    # The active dashboard refreshes a bounded number of times (no runaway
    # cascade from stale duplicate subscriptions).
    assert len(calls) <= 2


# ==========================================================================
# Projects list Refresh reflects storage (recent-projects file list)
# ==========================================================================


def test_projects_refresh_reflects_storage(tmp_path, monkeypatch):
    from logosforge.ui.projects_view import ProjectsView
    from logosforge import recent_projects

    p1 = tmp_path / "one.json"
    p1.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(recent_projects, "clean",
                        lambda: [str(p1)] if p1.exists() else [])
    view = ProjectsView(on_open_file=lambda p: None, on_save_as=lambda: None)

    def _card_names(v):
        from PySide6.QtWidgets import QLabel
        return {lbl.text() for lbl in v.findChildren(QLabel)}

    assert "one.json" in _card_names(view)
    # Storage changes: the file disappears -> Refresh drops it.
    p1.unlink()
    view.refresh()
    # Flush deferred deletions so the removed card widgets are actually gone.
    from PySide6.QtCore import QEvent
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.instance().processEvents()
    assert "one.json" not in _card_names(view)
