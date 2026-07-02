"""Projects section stability: Save As label, list refresh, fullscreen-safe
new project, and the close-save prompt + dirty state."""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QPushButton

warnings.filterwarnings("ignore")

import logosforge.ui.main_window as mw
from logosforge.db import Database
from logosforge.ui.dashboard_view import DashboardView
from logosforge.ui.main_window import MainWindow
from logosforge.ui.projects_view import ProjectsView


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


def _win(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    pid = db.create_project("P").id
    return db, pid, MainWindow(db, pid)


def _fake_new_dialog(monkeypatch, title="NEW"):
    import logosforge.ui.new_project_dialog as npd

    class _FD:
        def __init__(self, *a, **k):
            self.modality = None
        def setWindowModality(self, m):
            self.modality = m
        def exec(self):
            return True
        def get_title(self):
            return title
        def get_engine(self):
            return "novel"
        def get_format(self):
            return "novel"

    monkeypatch.setattr(npd, "NewProjectDialog", _FD)


def _stub_save_dialog(monkeypatch, path):
    monkeypatch.setattr(mw.QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (path, "JSON")))
    monkeypatch.setattr(mw.QMessageBox, "information",
                        staticmethod(lambda *a, **k: None))


# ==========================================================================
# Fix 2 — Save As label
# ==========================================================================


def test_save_as_button_label_is_save_as():
    view = ProjectsView(on_open_file=lambda p: None, on_save_as=lambda: None,
                        on_new_project=lambda: None)
    labels = [b.text() for b in view.findChildren(QPushButton)]
    assert "Save As" in labels
    assert "Save As / Export…" not in labels
    assert "Save As / Export ..." not in labels


# ==========================================================================
# Fix 3 — project list refresh + no duplicates
# ==========================================================================


def test_save_as_refreshes_projects_view(tmp_path, monkeypatch):
    db, pid, win = _win(tmp_path)
    win.sidebar_buttons["Projects"].click()
    assert isinstance(win.content_area, ProjectsView)
    calls = []
    orig = win.content_area.refresh
    win.content_area.refresh = lambda *a, **k: (calls.append(1), orig())[1]
    _stub_save_dialog(monkeypatch, str(tmp_path / "mystory.json"))
    win._on_save_as()
    assert calls, "Projects list was not refreshed after Save As"


def test_saved_project_card_appears_after_save_as(tmp_path, monkeypatch):
    db, pid, win = _win(tmp_path)
    win.sidebar_buttons["Projects"].click()
    saved = tmp_path / "mystory.json"
    _stub_save_dialog(monkeypatch, str(saved))
    win._on_save_as()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.instance().processEvents()
    names = {lbl.text() for lbl in win.content_area.findChildren(QLabel)}
    assert "mystory.json" in names


def test_repeated_refresh_no_duplicate_cards(tmp_path, monkeypatch):
    from logosforge import recent_projects
    p1 = tmp_path / "one.json"
    p1.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(recent_projects, "clean", lambda: [str(p1)])
    view = ProjectsView(on_open_file=lambda p: None, on_save_as=lambda: None,
                        on_new_project=lambda: None)
    view.refresh(); view.refresh(); view.refresh()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.instance().processEvents()
    names = [lbl.text() for lbl in view.findChildren(QLabel)]
    assert names.count("one.json") == 1


# ==========================================================================
# Fix 1 — fullscreen-safe new project
# ==========================================================================


def test_new_project_one_navigation_target(tmp_path, monkeypatch):
    db, pid, win = _win(tmp_path)
    _fake_new_dialog(monkeypatch, "FRESH")
    win._on_new_project()
    assert isinstance(win.content_area, DashboardView)
    assert win._current_section == "Dashboard"


def test_new_project_does_not_minimize_or_shownormal(tmp_path, monkeypatch):
    db, pid, win = _win(tmp_path)
    _fake_new_dialog(monkeypatch)
    calls = {"min": 0, "normal": 0}
    monkeypatch.setattr(win, "showMinimized",
                        lambda: calls.__setitem__("min", calls["min"] + 1))
    monkeypatch.setattr(win, "showNormal",
                        lambda: calls.__setitem__("normal", calls["normal"] + 1))
    win._on_new_project()
    assert calls == {"min": 0, "normal": 0}


def test_new_project_dialog_is_window_modal():
    # The dialog itself is window-modal (sheet on macOS), so it can't drop the
    # main window out of fullscreen.
    from PySide6.QtCore import Qt
    from logosforge.ui.new_project_dialog import NewProjectDialog
    dlg = NewProjectDialog()
    assert dlg.windowModality() == Qt.WindowModality.WindowModal


def test_new_project_makes_no_window_state_calls(tmp_path, monkeypatch):
    # New contract: the create flow NEVER mutates window state. The window-modal
    # sheet keeps the window in its current Space (fullscreen preserved), and
    # calling showFullScreen mid-teardown was the cause of the macOS slide /
    # minimise — so it is gone entirely, even when fullscreen looks "dropped".
    db, pid, win = _win(tmp_path)
    _fake_new_dialog(monkeypatch)
    monkeypatch.setattr(win, "isFullScreen", lambda: False)  # even if it reports dropped
    calls = []
    monkeypatch.setattr(win, "showFullScreen", lambda: calls.append("fullscreen"))
    monkeypatch.setattr(win, "showNormal", lambda: calls.append("normal"))
    monkeypatch.setattr(win, "showMinimized", lambda: calls.append("minimized"))
    win._on_new_project()
    assert calls == []        # zero window-state mutations


def test_new_project_no_restore_when_fullscreen_kept(tmp_path, monkeypatch):
    db, pid, win = _win(tmp_path)
    _fake_new_dialog(monkeypatch)
    monkeypatch.setattr(win, "isFullScreen", lambda: True)  # stays fullscreen
    restored = []
    monkeypatch.setattr(win, "showFullScreen", lambda: restored.append(1))
    win._on_new_project()
    assert restored == []     # no spurious showFullScreen call


# ==========================================================================
# Fix 4 — close-save prompt + dirty state
# ==========================================================================


def test_close_clean_project_no_prompt(tmp_path, monkeypatch):
    db, pid, win = _win(tmp_path)
    win._dirty = False

    def _boom(*a, **k):
        raise AssertionError("must not prompt when clean")
    monkeypatch.setattr(mw.QMessageBox, "warning", staticmethod(_boom))
    ev = QCloseEvent()
    win.closeEvent(ev)
    assert ev.isAccepted()


def test_close_dirty_cancel_aborts(tmp_path, monkeypatch):
    db, pid, win = _win(tmp_path)
    win._dirty = True
    win._modified_since_save = True
    win._read_only = False
    monkeypatch.setattr(mw.QMessageBox, "warning",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Cancel))
    ev = QCloseEvent()
    win.closeEvent(ev)
    assert not ev.isAccepted()


def test_close_dirty_save_file_backed_saves_and_closes(tmp_path, monkeypatch):
    db, pid, win = _win(tmp_path)
    win._dirty = True
    win._modified_since_save = True
    win._read_only = False
    win._current_file = str(tmp_path / "f.json")
    saved = []
    monkeypatch.setattr(win, "_auto_save", lambda: saved.append(1))
    monkeypatch.setattr(win, "_versions", win._versions)
    monkeypatch.setattr(mw.QMessageBox, "warning",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Save))
    ev = QCloseEvent()
    win.closeEvent(ev)
    assert saved == [1] and ev.isAccepted()


def test_close_dirty_dont_save_closes_without_saving(tmp_path, monkeypatch):
    db, pid, win = _win(tmp_path)
    win._dirty = True
    win._modified_since_save = True
    win._read_only = False
    win._current_file = str(tmp_path / "f.json")
    saved = []
    monkeypatch.setattr(win, "_auto_save", lambda: saved.append(1))
    monkeypatch.setattr(mw.QMessageBox, "warning",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Discard))
    ev = QCloseEvent()
    win.closeEvent(ev)
    assert saved == [] and ev.isAccepted()


def test_close_dirty_new_project_save_cancelled_aborts(tmp_path, monkeypatch):
    db, pid, win = _win(tmp_path)
    win._dirty = True
    win._modified_since_save = True
    win._read_only = False
    win._current_file = None
    monkeypatch.setattr(mw.QMessageBox, "warning",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Save))
    # User cancels the Save As file dialog → _current_file stays None.
    monkeypatch.setattr(mw.QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: ("", "")))
    ev = QCloseEvent()
    win.closeEvent(ev)
    assert not ev.isAccepted()   # close aborted because save was cancelled


# ==========================================================================
# Dirty state on edits + cleared on save
# ==========================================================================


def test_data_change_marks_dirty(tmp_path):
    db, pid, win = _win(tmp_path)
    win._dirty = False
    win._on_data_changed()
    assert win._dirty is True


def test_scene_content_save_marks_dirty(tmp_path):
    db, pid, win = _win(tmp_path)
    win._dirty = False
    win._on_scene_content_saved()
    assert win._dirty is True


def test_save_as_clears_dirty(tmp_path, monkeypatch):
    db, pid, win = _win(tmp_path)
    win._on_data_changed()
    assert win._dirty is True
    _stub_save_dialog(monkeypatch, str(tmp_path / "s.json"))
    win._on_save_as()
    assert win._dirty is False
