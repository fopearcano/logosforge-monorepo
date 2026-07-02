"""Pages section — fullscreen-safe Create New / dialogs (Alpha blocker fix).

On macOS, an application-modal (or parentless) dialog shown while the main window
is in a fullscreen Space pulls the window out of fullscreen ("minimize/flicker").
The cure is a **window-modal** dialog parented to the top-level window
(`logosforge.ui.safe_dialogs`). These tests verify:

* the shared helper is window-modal and parented to the top-level window;
* the Graphic Novel Pages section's create actions are inline (no dialog) and
  never minimize/hide the main window;
* the Pages confirmations route through the window-modal helper;
* cancel does not mutate, confirm creates, the shared body + dirty flag update;
* the previous Project "Create New" fix (window-modal NewProjectDialog) holds.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QInputDialog, QMessageBox, QWidget

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import graphic_novel_blocks as gnb
from logosforge.ui import safe_dialogs


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


# -- builders ---------------------------------------------------------------


def _gn(db):
    return db.create_project("GN", narrative_engine="graphic_novel",
                             default_writing_format="graphic_novel").id


def _scene(db, pid, title="P1"):
    from logosforge import story_structure as ss
    return ss.create_scene(db, pid, act="Act 1", chapter="Chapter 1",
                           title=title).id


def _view(db, pid, scene_id=None, **cb):
    from logosforge.ui.graphic_novel_scene_pages_view import (
        GraphicNovelScenePagesView)
    return GraphicNovelScenePagesView(db, pid, scene_id=scene_id, **cb)


def _body(db, sid):
    return gnb.load_scene_script(db, sid)


# ==========================================================================
# 1-4  Shared fullscreen-safe helper
# ==========================================================================


def test_helper_question_is_window_modal_and_top_level_parented(monkeypatch):
    captured = {}

    def fake_exec(self):
        captured["modality"] = self.windowModality()
        captured["parent"] = self.parent()
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    host = QWidget()                       # a top-level window
    assert safe_dialogs.question(host, "T", "msg?") is True
    assert captured["modality"] == Qt.WindowModality.WindowModal
    assert captured["parent"] is host


def test_helper_parents_to_top_level_not_child_widget(monkeypatch):
    captured = {}
    monkeypatch.setattr(QMessageBox, "exec",
                        lambda self: captured.setdefault("parent", self.parent())
                        or QMessageBox.StandardButton.No)
    win = QWidget()
    child = QWidget(win)                   # nested child, not a window
    safe_dialogs.question(child, "T", "msg?")
    assert captured["parent"] is win       # resolved to the top-level window


def test_helper_question_returns_false_on_no(monkeypatch):
    monkeypatch.setattr(QMessageBox, "exec",
                        lambda self: QMessageBox.StandardButton.No)
    assert safe_dialogs.question(QWidget(), "T", "msg?") is False


def test_helper_get_text_is_window_modal(monkeypatch):
    captured = {}

    def fake_exec(self):
        captured["modality"] = self.windowModality()
        self.setTextValue("typed")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QInputDialog, "exec", fake_exec)
    value, ok = safe_dialogs.get_text(QWidget(), "T", "Label:")
    assert ok is True and value == "typed"
    assert captured["modality"] == Qt.WindowModality.WindowModal


# ==========================================================================
# 5-9  Pages Create New is inline + fullscreen-safe (no minimize/hide/dialog)
# ==========================================================================


def test_add_page_opens_no_dialog(monkeypatch):
    # Any modal dialog during create would be the fullscreen-hostile pattern.
    def boom(*a, **k):
        raise AssertionError("create must not open a dialog")
    monkeypatch.setattr(QMessageBox, "exec", boom)
    monkeypatch.setattr(QInputDialog, "exec", boom)
    monkeypatch.setattr(safe_dialogs, "question", boom)
    monkeypatch.setattr(safe_dialogs, "get_text", boom)
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    v = _view(db, pid, scene_id=sid)
    v._add_page()                          # inline — no dialog
    v._add_panel()                         # inline — no dialog
    assert len(_body(db, sid).pages) >= 1


def test_pages_route_lands_on_editor_without_minimizing_main_window():
    # The standalone Pages nav item is disabled; the Pages route redirects to the
    # Manuscript, which for Graphic Novel is the inline comics script editor.
    # It mounts via the fullscreen-safe Manuscript path and must never minimize/hide.
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.graphic_novel_manuscript_view import (
        GraphicNovelManuscriptView)
    db = Database()
    pid = _gn(db)
    _scene(db, pid)
    win = MainWindow(db, pid)
    calls = {"min": 0, "hide": 0}
    win.showMinimized = lambda: calls.__setitem__("min", calls["min"] + 1)  # type: ignore
    win.hide = lambda: calls.__setitem__("hide", calls["hide"] + 1)         # type: ignore
    win._show_gn_pages()                       # -> Manuscript script editor
    from logosforge.ui.writing_core_view import WritingCoreView
    assert isinstance(win.content_area, WritingCoreView)
    assert calls == {"min": 0, "hide": 0}


def test_add_page_marks_dirty_via_callback():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    changed = []
    v = _view(db, pid, scene_id=sid, on_data_changed=lambda: changed.append(1))
    v._add_page()
    assert changed                          # host notified -> project dirty


def test_add_page_updates_shared_manuscript_body():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    v = _view(db, pid, scene_id=sid)
    before = len(_body(db, sid).pages)
    v._add_page()
    # The Manuscript path (Scene.content) sees the new page — shared single source.
    assert len(_body(db, sid).pages) == before + 1


def test_add_panel_updates_shared_manuscript_body():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    v = _view(db, pid, scene_id=sid)
    v._add_page()
    before = _body(db, sid).pages[-1].panels
    v._add_panel()
    assert len(_body(db, sid).pages[-1].panels) == len(before) + 1


# ==========================================================================
# 10-13  Pages confirmations use the window-modal helper
# ==========================================================================


def test_delete_panel_routes_through_safe_helper(monkeypatch):
    seen = {}
    monkeypatch.setattr(safe_dialogs, "question",
                        lambda *a, **k: seen.setdefault("called", True) or True)
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    v = _view(db, pid, scene_id=sid)
    v._add_page(); v._add_panel(); v._add_panel()
    n = len(_body(db, sid).pages[-1].panels)
    v._delete_panel(len(_body(db, sid).pages) - 1, 0, confirm=True)
    assert seen.get("called") is True       # used the fullscreen-safe helper
    assert len(_body(db, sid).pages[-1].panels) == n - 1


def test_cancel_delete_panel_does_not_mutate(monkeypatch):
    monkeypatch.setattr(safe_dialogs, "question", lambda *a, **k: False)  # cancel
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    v = _view(db, pid, scene_id=sid)
    v._add_page(); v._add_panel()
    n = len(_body(db, sid).pages[-1].panels)
    v._delete_panel(len(_body(db, sid).pages) - 1, 0, confirm=True)
    assert len(_body(db, sid).pages[-1].panels) == n     # unchanged


def test_cancel_delete_page_does_not_mutate(monkeypatch):
    monkeypatch.setattr(safe_dialogs, "question", lambda *a, **k: False)
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    v = _view(db, pid, scene_id=sid)
    v._add_page(); v._add_page()
    n = len(_body(db, sid).pages)
    v._delete_page(0, confirm=True)
    assert len(_body(db, sid).pages) == n                # unchanged


def test_confirm_delete_page_mutates(monkeypatch):
    monkeypatch.setattr(safe_dialogs, "question", lambda *a, **k: True)
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    v = _view(db, pid, scene_id=sid)
    v._add_page(); v._add_page()
    n = len(_body(db, sid).pages)
    v._delete_page(0, confirm=True)
    assert len(_body(db, sid).pages) == n - 1


# ==========================================================================
# 14-15  Regression: the original Project Create New fix still holds
# ==========================================================================


def test_new_project_dialog_is_window_modal():
    from logosforge.ui.new_project_dialog import NewProjectDialog
    dlg = NewProjectDialog()
    assert dlg.windowModality() == Qt.WindowModality.WindowModal


def test_pages_view_uses_safe_dialogs_module():
    # The Pages section must go through the shared fullscreen-safe helper, not
    # raw application-modal QMessageBox statics.
    import logosforge.ui.graphic_novel_scene_pages_view as mod
    assert getattr(mod, "safe_dialogs", None) is safe_dialogs


# ==========================================================================
# 16  Project switch clears stale Pages/Panels (isolation)
# ==========================================================================


def test_project_switch_clears_stale_pages(tmp_path):
    db = Database(str(tmp_path / "iso.db"))
    a = _gn(db)
    sid_a = _scene(db, a, "A-scene")
    va = _view(db, a, scene_id=sid_a)
    va._add_page()
    b = _gn(db)                              # empty GN project
    vb = _view(db, b)
    # B has no scenes -> empty state, none of A's pages visible.
    assert vb._scene_id is None
