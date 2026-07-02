"""Regression tests for the Manuscript editor not being destroyed mid-typing.

Bug: Typing in the manuscript editor triggered a 500ms autosave timer that
called the parent's `_on_data_changed`, which in turn called
`_refresh_active_view()` → `WritingCoreView.refresh()` → `_clear_canvas()`,
which destroyed the active editor widget via `deleteLater()`.  The visible
symptom was the editor appearing greyed out / non-editable.

Fix: routine content saves and in-place format changes route through a
lightweight `on_content_saved` callback that updates dirty/version state but
does NOT trigger a view refresh of the editor itself.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from logosforge.db import Database
from logosforge.ui.writing_core_view import WritingCoreView


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_project(db: Database):
    proj = db.create_project("Novel")
    s1 = db.create_scene(proj.id, "Opening", content="The storm began.")
    s2 = db.create_scene(proj.id, "Rising", content="She ran.")
    return proj, s1, s2


# -- callback wiring ---------------------------------------------------------

def test_save_scene_uses_content_saved_callback_not_data_changed():
    db = Database()
    proj, s1, _ = _make_project(db)
    data_calls = []
    content_calls = []
    view = WritingCoreView(
        db, proj.id,
        on_data_changed=lambda: data_calls.append(1),
        on_content_saved=lambda: content_calls.append(1),
    )
    view._save_scene(s1.id)
    assert content_calls == [1]
    assert data_calls == []


def test_format_change_uses_content_saved_callback():
    db = Database()
    proj, _, _ = _make_project(db)
    data_calls = []
    content_calls = []
    view = WritingCoreView(
        db, proj.id,
        on_data_changed=lambda: data_calls.append(1),
        on_content_saved=lambda: content_calls.append(1),
    )
    db.update_project_writing_format(proj.id, "screenplay")
    view.reload_project_format()
    assert content_calls, "Expected content_saved to be called on format change"
    assert data_calls == []


def test_falls_back_to_on_data_changed_when_no_content_saved():
    db = Database()
    proj, s1, _ = _make_project(db)
    data_calls = []
    view = WritingCoreView(
        db, proj.id,
        on_data_changed=lambda: data_calls.append(1),
    )
    view._save_scene(s1.id)
    assert data_calls == [1]


def test_create_scene_after_uses_content_saved():
    db = Database()
    proj, s1, _ = _make_project(db)
    data_calls = []
    content_calls = []
    view = WritingCoreView(
        db, proj.id,
        on_data_changed=lambda: data_calls.append(1),
        on_content_saved=lambda: content_calls.append(1),
    )
    view._create_scene_after(s1.id)
    assert content_calls, "Expected content_saved when continuation scene created"
    assert data_calls == []


# -- the actual regression: editor must not be destroyed during typing ------

def test_save_scene_does_not_destroy_editor():
    """The editor widget the user is typing in must survive its own autosave."""
    db = Database()
    proj, s1, _ = _make_project(db)

    rebuilt = []

    def fake_refresh_callback():
        rebuilt.append(1)

    view = WritingCoreView(
        db, proj.id,
        on_data_changed=fake_refresh_callback,
        on_content_saved=lambda: None,
    )
    editor_before = view._editors[s1.id]
    editor_id_before = id(editor_before)

    view._save_scene(s1.id)

    editor_after = view._editors[s1.id]
    assert id(editor_after) == editor_id_before
    assert editor_after is editor_before
    assert rebuilt == [], "on_data_changed (refresh trigger) must NOT fire on a content save"


def test_save_scene_persists_content_to_db():
    """Content saves still happen — only the destructive refresh is skipped."""
    db = Database()
    proj, s1, _ = _make_project(db)
    view = WritingCoreView(db, proj.id, on_content_saved=lambda: None)
    editor = view._editors[s1.id]
    editor.setPlainText("Brand new paragraph.")
    view._save_scene(s1.id)
    scene = db.get_scene_by_id(s1.id)
    assert "Brand new paragraph" in (scene.content or "")


# -- main window wiring ------------------------------------------------------

def test_main_window_has_on_scene_content_saved_method():
    from logosforge.ui.main_window import MainWindow
    assert hasattr(MainWindow, "_on_scene_content_saved"), (
        "MainWindow must expose _on_scene_content_saved for the lightweight save path"
    )


def test_on_scene_content_saved_does_not_refresh_active_view():
    """The whole point of the split: content saves must not refresh the view."""
    import inspect
    from logosforge.ui.main_window import MainWindow
    source = inspect.getsource(MainWindow._on_scene_content_saved)
    assert "_refresh_active_view" not in source, (
        "_on_scene_content_saved must NOT call _refresh_active_view "
        "(that's what destroyed the editor during typing)"
    )


def test_on_data_changed_still_refreshes_active_view():
    """Structural changes (new/deleted scene from outside Manuscript) still refresh."""
    import inspect
    from logosforge.ui.main_window import MainWindow
    source = inspect.getsource(MainWindow._on_data_changed)
    assert "_refresh_active_view" in source


# -- refresh must not lose in-progress keystrokes or steal focus -------------

def test_refresh_flushes_pending_keystrokes():
    """A legitimate refresh (e.g. Assistant/Logos apply) must flush unsaved
    typing first, so the rebuild reads the user's latest text — never the
    pre-typing version."""
    db = Database()
    proj, s1, _ = _make_project(db)
    view = WritingCoreView(db, proj.id, on_content_saved=lambda: None)
    editor = view._editors[s1.id]
    editor.setPlainText("Unsaved sentence in flight.")
    # Simulate the 500ms debounce being pending (user just typed).
    view._schedule_save(s1.id)
    assert view._save_timers[s1.id].isActive()

    view.refresh()  # rebuild triggered while a save is pending

    scene = db.get_scene_by_id(s1.id)
    assert "Unsaved sentence in flight" in (scene.content or "")
    # And the rebuilt editor shows it (no keystroke loss).
    assert "Unsaved sentence in flight" in view._editors[s1.id].toPlainText()


def test_flush_pending_saves_persists_and_stops_timer():
    db = Database()
    proj, s1, _ = _make_project(db)
    view = WritingCoreView(db, proj.id, on_content_saved=lambda: None)
    view._editors[s1.id].setPlainText("Flush me.")
    view._schedule_save(s1.id)
    view._flush_pending_saves()
    assert not view._save_timers[s1.id].isActive()
    assert "Flush me" in (db.get_scene_by_id(s1.id).content or "")


def test_refresh_restores_cursor_for_focused_scene(monkeypatch):
    db = Database()
    proj, s1, s2 = _make_project(db)
    view = WritingCoreView(db, proj.id, on_content_saved=lambda: None)
    editor = view._editors[s2.id]
    # Make this editor report focus + place the cursor a few chars in.
    monkeypatch.setattr(editor, "hasFocus", lambda: True)
    cur = editor.textCursor()
    cur.setPosition(3)
    editor.setTextCursor(cur)

    view.refresh()

    # The scene still exists; the rebuilt editor restores the cursor position.
    new_editor = view._editors[s2.id]
    assert new_editor.textCursor().position() == 3


def test_refresh_keeps_editor_enabled_and_editable():
    db = Database()
    proj, s1, _ = _make_project(db)
    view = WritingCoreView(db, proj.id, on_content_saved=lambda: None)
    view.refresh()
    editor = view._editors[s1.id]
    assert editor.isEnabled() is True
    assert editor.isReadOnly() is False
