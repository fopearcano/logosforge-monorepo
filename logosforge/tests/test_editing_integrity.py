"""Editing integrity: dirty-state + close-save policy, autosave compatibility,
and Undo/Redo (menu + focused-editor routing)."""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QMessageBox, QPlainTextEdit

warnings.filterwarnings("ignore")

import logosforge.ui.main_window as mw
from logosforge.db import Database
from logosforge.ui.main_window import MainWindow
from logosforge.ui.writing_core_view import WritingCoreView, _SceneEditor


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


def _win(tmp_path, with_scene=False):
    db = Database(str(tmp_path / "sp.db"))
    # Scene-based mode so the Manuscript uses the scene editor (undo/autosave
    # behaviour under test). Novel manuscript now writes chapters.
    pid = db.create_project("P", narrative_engine="screenplay",
                            default_writing_format="screenplay").id
    if with_scene:
        db.create_scene(pid, "S1", content="hello")
    return db, pid, MainWindow(db, pid)


def _editor(win, sid=None):
    win.sidebar_buttons["Manuscript"].click()
    eds = win.content_area.findChildren(_SceneEditor)
    if sid is not None:
        return next(e for e in eds if getattr(e, "_scene_id", None) == sid)
    return eds[0]


# ==========================================================================
# Dirty / close (1–12)
# ==========================================================================


def test_clean_project_closes_without_prompt(tmp_path, monkeypatch):
    db, pid, win = _win(tmp_path)
    monkeypatch.setattr(mw.QMessageBox, "warning",
                        staticmethod(lambda *a, **k: pytest.fail("prompted when clean")))
    ev = QCloseEvent(); win.closeEvent(ev)
    assert ev.isAccepted()


def test_manuscript_edit_marks_dirty(tmp_path):
    db, pid, win = _win(tmp_path)
    assert win._modified_since_save is False
    win._on_scene_content_saved()
    assert win._modified_since_save is True


def test_data_change_marks_dirty(tmp_path):
    db, pid, win = _win(tmp_path)
    win._on_data_changed()
    assert win._modified_since_save is True


def test_explicit_save_clears_dirty(tmp_path):
    db, pid, win = _win(tmp_path)
    win._on_data_changed()
    win._current_file = str(tmp_path / "f.json")
    win._auto_save = lambda: None
    win._on_save()
    assert win._modified_since_save is False


def test_save_as_clears_dirty(tmp_path, monkeypatch):
    db, pid, win = _win(tmp_path)
    win._on_data_changed()
    monkeypatch.setattr(mw.QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(tmp_path / "s.json"), "JSON")))
    monkeypatch.setattr(mw.QMessageBox, "information", staticmethod(lambda *a, **k: None))
    win._on_save_as()
    assert win._modified_since_save is False


def test_close_dirty_shows_prompt_and_cancel_aborts(tmp_path, monkeypatch):
    db, pid, win = _win(tmp_path)
    win._on_data_changed()
    count = {"n": 0}
    monkeypatch.setattr(mw.QMessageBox, "warning",
                        staticmethod(lambda *a, **k: (count.__setitem__("n", count["n"] + 1),
                                                      QMessageBox.StandardButton.Cancel)[1]))
    ev = QCloseEvent(); win.closeEvent(ev)
    assert count["n"] == 1            # prompt shown exactly once
    assert not ev.isAccepted()        # cancel aborts


def test_close_dirty_save_then_close(tmp_path, monkeypatch):
    db, pid, win = _win(tmp_path)
    win._on_data_changed()
    win._current_file = str(tmp_path / "f.json")
    saved = []
    monkeypatch.setattr(win, "_auto_save", lambda: saved.append(1))
    monkeypatch.setattr(mw.QMessageBox, "warning",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Save))
    ev = QCloseEvent(); win.closeEvent(ev)
    assert saved == [1] and ev.isAccepted()


def test_close_dirty_dont_save_closes(tmp_path, monkeypatch):
    db, pid, win = _win(tmp_path)
    win._on_data_changed()
    win._current_file = str(tmp_path / "f.json")
    saved = []
    monkeypatch.setattr(win, "_auto_save", lambda: saved.append(1))
    monkeypatch.setattr(mw.QMessageBox, "warning",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Discard))
    ev = QCloseEvent(); win.closeEvent(ev)
    assert saved == [] and ev.isAccepted()


def test_project_switch_resets_dirty(tmp_path):
    db, pid, win = _win(tmp_path)
    win._on_data_changed()
    assert win._modified_since_save is True
    p2 = db.create_project("P2", narrative_engine="screenplay", default_writing_format="screenplay").id
    win._switch_project(p2)
    assert win._modified_since_save is False


# ==========================================================================
# Autosave compatibility (13–17)
# ==========================================================================


def test_autosave_does_not_clear_modified_flag(tmp_path):
    # The key fix for issue #1: autosave keeps the file safe but the project is
    # still "modified since last explicit save", so close still prompts.
    db, pid, win = _win(tmp_path)
    win._on_data_changed()
    win._on_autosave_status("Saved")       # autosave completed
    assert win._dirty is False             # autosave-facing flag cleared
    assert win._modified_since_save is True  # but user-facing modified stays


def test_autosave_does_not_reload_or_rebuild_editor(tmp_path):
    db, pid, win = _win(tmp_path, with_scene=True)
    ed = _editor(win)
    view = win.content_area
    before_text = ed.toPlainText()
    # The typing-save path + autosave-status must not destroy/replace the editor.
    win._on_scene_content_saved()
    win._on_autosave_status("Saved")
    # Re-query the SAME view (no re-navigation, which would rebuild on purpose).
    ed_after = next(e for e in view.findChildren(_SceneEditor)
                    if getattr(e, "_scene_id", None) == ed._scene_id)
    assert ed_after is ed                  # same widget (undo stack intact)
    assert ed.toPlainText() == before_text


def test_autosave_status_does_not_change_focus(tmp_path):
    db, pid, win = _win(tmp_path, with_scene=True)
    ed = _editor(win)
    ed.setFocus()
    win._on_autosave_status("Saved")
    # Autosave must not steal focus away from the editor.
    assert QApplication.focusWidget() is ed or QApplication.focusWidget() is None


# ==========================================================================
# Undo / Redo (18–27)
# ==========================================================================


def test_manuscript_typing_can_be_undone_and_redone(tmp_path):
    db, pid, win = _win(tmp_path, with_scene=True)
    ed = _editor(win)
    assert ed.isUndoRedoEnabled()
    cur = ed.textCursor(); cur.movePosition(cur.MoveOperation.End); ed.setTextCursor(cur)
    ed.insertPlainText(" UNDO_TEST_SENTINEL")
    assert "UNDO_TEST_SENTINEL" in ed.toPlainText()
    ed.undo()
    assert "UNDO_TEST_SENTINEL" not in ed.toPlainText()
    ed.redo()
    assert "UNDO_TEST_SENTINEL" in ed.toPlainText()


def test_menu_undo_redo_route_to_last_focused_editor(tmp_path, monkeypatch):
    db, pid, win = _win(tmp_path)
    ed = QPlainTextEdit(); ed.setPlainText("hello"); ed.show()
    win._on_focus_changed(None, ed)        # editor held focus
    cur = ed.textCursor(); cur.movePosition(cur.MoveOperation.End); ed.setTextCursor(cur)
    ed.insertPlainText(" WORLD")
    # Opening the Edit menu steals focus → focusWidget() is None.
    win._on_focus_changed(ed, None)
    monkeypatch.setattr(QApplication, "focusWidget", staticmethod(lambda: None))
    win._edit_undo()
    assert ed.toPlainText() == "hello"
    win._edit_redo()
    assert ed.toPlainText() == "hello WORLD"


def test_autosave_after_typing_does_not_break_undo(tmp_path):
    db, pid, win = _win(tmp_path, with_scene=True)
    ed = _editor(win)
    cur = ed.textCursor(); cur.movePosition(cur.MoveOperation.End); ed.setTextCursor(cur)
    ed.insertPlainText(" MORE")
    win._on_scene_content_saved()          # typing-save
    win._on_autosave_status("Saved")       # periodic autosave
    ed.undo()
    assert "MORE" not in ed.toPlainText()


def test_project_switch_clears_undo_stack_safely(tmp_path):
    db, pid, win = _win(tmp_path, with_scene=True)
    ed_a = _editor(win)
    cur = ed_a.textCursor(); cur.movePosition(cur.MoveOperation.End); ed_a.setTextCursor(cur)
    ed_a.insertPlainText(" PROJECT_A_TEXT")
    p2 = db.create_project("P2", narrative_engine="screenplay", default_writing_format="screenplay").id
    db.create_scene(p2, "B1", content="bee")
    win._switch_project(p2)
    ed_b = _editor(win)
    assert ed_b is not ed_a                 # different project → fresh editor
    assert "PROJECT_A_TEXT" not in ed_b.toPlainText()
    # Undo on B's editor cannot reach A's content.
    ed_b.undo()
    assert "PROJECT_A_TEXT" not in ed_b.toPlainText()


# ==========================================================================
# Edit-op safety (Part 6)
# ==========================================================================


def test_edit_ops_no_crash_without_editable_focus(tmp_path, monkeypatch):
    db, pid, win = _win(tmp_path)
    monkeypatch.setattr(QApplication, "focusWidget", staticmethod(lambda: None))
    win._last_edit_widget = None
    # Must be safe no-ops, never crash.
    win._edit_undo(); win._edit_redo(); win._edit_cut()
    win._edit_copy(); win._edit_paste(); win._edit_select_all()


def test_readonly_widget_not_targeted(tmp_path):
    db, pid, win = _win(tmp_path)
    ro = QPlainTextEdit(); ro.setReadOnly(True); ro.setPlainText("locked"); ro.show()
    win._on_focus_changed(None, ro)
    # A read-only widget is never remembered as the edit target.
    assert win._last_edit_widget is not ro
