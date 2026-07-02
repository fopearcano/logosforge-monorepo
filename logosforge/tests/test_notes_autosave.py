"""Notes auto-save / dirty-guard: in-progress edits must never be silently
lost when switching note, starting a new one, or navigating away."""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtGui import QHideEvent
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.ui.notes_view import NotesView


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
    yield
    settings._instance = None


def _proj(db):
    return db.create_project("P", narrative_engine="novel").id


def test_switching_notes_autosaves_edits():
    db = Database()
    pid = _proj(db)
    a = db.create_note(pid, "A", "orig A").id
    b = db.create_note(pid, "B", "orig B").id
    view = NotesView(db, pid)
    view.select_note(a)
    view._content_input.setPlainText("orig A EDITED")     # in-progress edit
    assert view._dirty
    view.select_note(b)                                   # switch away
    assert db.get_note_by_id(a).content == "orig A EDITED"  # auto-saved, not lost
    assert not view._dirty                                # B loaded clean


def test_dirty_flag_and_unsaved_label():
    db = Database()
    pid = _proj(db)
    a = db.create_note(pid, "A", "x").id
    view = NotesView(db, pid)
    view.select_note(a)
    assert not view._dirty and "unsaved" not in view._form_label.text()
    view._content_input.setPlainText("edited")
    assert view._dirty and "unsaved" in view._form_label.text()
    view._on_save()
    assert not view._dirty and "unsaved" not in view._form_label.text()


def test_new_note_with_content_autosaved_on_new():
    db = Database()
    pid = _proj(db)
    view = NotesView(db, pid)
    view._title_input.setText("Fresh")
    view._content_input.setPlainText("draft body")
    assert view._dirty and view._selected_id is None
    view._clear_form()                                    # "+ New Note"
    notes = db.get_all_notes(pid)
    assert any(n.title == "Fresh" and n.content == "draft body" for n in notes)


def test_hide_event_flushes_edits():
    db = Database()
    pid = _proj(db)
    a = db.create_note(pid, "A", "x").id
    view = NotesView(db, pid)
    view.select_note(a)
    view._content_input.setPlainText("saved on navigate-away")
    view.hideEvent(QHideEvent())                          # leaving the section
    assert db.get_note_by_id(a).content == "saved on navigate-away"


def test_empty_title_save_shows_hint_not_silent():
    db = Database()
    pid = _proj(db)
    view = NotesView(db, pid)
    view._content_input.setPlainText("body but no title")
    view._on_save()
    assert "add a title" in view._form_label.text().lower()
    assert db.get_all_notes(pid) == []                    # explicit Save did nothing
