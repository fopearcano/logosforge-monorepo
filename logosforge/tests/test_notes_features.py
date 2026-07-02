"""Notes UX features: search/filter, pin-to-top, Markdown preview, undo-delete,
searchable link picker for large lists, and navigable link chips."""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox

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


# -- 1. Search / filter ------------------------------------------------------

def test_search_filters_list():
    db = Database()
    pid = _proj(db)
    db.create_note(pid, "Apple note", "about fruit")
    db.create_note(pid, "Banana note", "it is yellow")
    view = NotesView(db, pid)
    assert view._list.count() == 2
    view._search_input.setText("apple")          # title match
    assert view._list.count() == 1 and "Apple" in view._list.item(0).text()
    view._search_input.setText("yellow")         # content match
    assert view._list.count() == 1 and "Banana" in view._list.item(0).text()
    view._search_input.setText("")
    assert view._list.count() == 2


# -- 2. Pin-to-top -----------------------------------------------------------

def test_pinned_notes_float_to_top():
    db = Database()
    pid = _proj(db)
    db.create_note(pid, "Zeta", "x")
    db.create_note(pid, "Alpha", "x", pinned=True)
    view = NotesView(db, pid)
    top = view._list.item(0).text()
    assert top.startswith("📌") and "Alpha" in top   # pinned first despite Z<A order


# -- 3. Markdown preview -----------------------------------------------------

def test_markdown_preview_toggle_renders():
    db = Database()
    pid = _proj(db)
    a = db.create_note(pid, "A", "# Heading\n\n**bold** text").id
    view = NotesView(db, pid)
    view.select_note(a)
    assert view._content_preview.isHidden()
    view._preview_btn.setChecked(True)
    assert view._content_input.isHidden() and not view._content_preview.isHidden()
    html = view._content_preview.toHtml()
    assert "bold" in html and "**bold**" not in html   # markdown was rendered
    view._preview_btn.setChecked(False)
    assert not view._content_input.isHidden() and view._content_preview.isHidden()


def test_preview_resets_to_edit_on_note_load():
    db = Database()
    pid = _proj(db)
    a = db.create_note(pid, "A", "x").id
    b = db.create_note(pid, "B", "y").id
    view = NotesView(db, pid)
    view.select_note(a)
    view._preview_btn.setChecked(True)            # preview on
    view.select_note(b)                           # switching reloads in edit mode
    assert not view._preview_btn.isChecked()
    assert not view._content_input.isHidden()


def test_preview_resets_on_new_note():
    db = Database()
    pid = _proj(db)
    a = db.create_note(pid, "A", "x").id
    view = NotesView(db, pid)
    view.select_note(a)
    view._preview_btn.setChecked(True)
    view._clear_form()                            # "+ New Note" → editable form
    assert not view._preview_btn.isChecked()
    assert not view._content_input.isHidden()


# -- 4. Undo delete ----------------------------------------------------------

def test_undo_delete_restores_note_and_links(monkeypatch):
    db = Database()
    pid = _proj(db)
    sc = db.create_scene(pid, "Scene1").id
    n = db.create_note(pid, "ToDelete", "body", tags="t1", pinned=True).id
    db.link_note_to_scene(n, sc)
    view = NotesView(db, pid)
    view.select_note(n)
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    view._on_delete()
    assert db.get_note_by_id(n) is None
    assert not view._undo_btn.isHidden()          # undo offered
    view._on_undo_delete()
    restored = [x for x in db.get_all_notes(pid) if x.title == "ToDelete"]
    assert restored and restored[0].content == "body" and restored[0].pinned
    assert sc in db.get_note_scene_links(restored[0].id)   # link restored too
    assert view._undo_btn.isHidden()


# -- 5. Link menu scale ------------------------------------------------------

def test_link_menu_uses_picker_for_large_lists():
    db = Database()
    pid = _proj(db)
    n = db.create_note(pid, "N", "x").id
    view = NotesView(db, pid)
    view.select_note(n)
    menu = QMenu()
    view._link_category(menu, "Few", [(f"S{i}", i) for i in range(5)], lambda v: None)
    view._link_category(menu, "Many", [(f"S{i}", i) for i in range(30)], lambda v: None)
    few = next(a for a in menu.actions() if a.text() == "Few")
    many = next(a for a in menu.actions() if "Many" in a.text())
    assert few.menu() is not None and len(few.menu().actions()) == 5   # inline submenu
    assert many.menu() is None and "(30)" in many.text()              # → picker action


# -- 6. Navigable link chips -------------------------------------------------

def test_link_chip_navigates_scene_and_psyke():
    calls = []
    db = Database()
    pid = _proj(db)
    sc = db.create_scene(pid, "Scene1").id
    entry = db.create_psyke_entry(pid, "Gandalf", "character").id
    n = db.create_note(pid, "N", "x").id
    db.link_note_to_scene(n, sc)
    db.link_note_to_psyke(n, entry)
    view = NotesView(db, pid, on_link_clicked=lambda t, i: calls.append((t, i)))
    view.select_note(n)
    links = view._collect_links()
    view._navigate_link(next(l for l in links if l["kind"] == "scene"))
    view._navigate_link(next(l for l in links if l["kind"] == "psyke"))
    assert ("Scene", sc) in calls and ("PsykeEntry", entry) in calls


def test_save_clears_filter_that_hides_the_note():
    # Saving a note that doesn't match the active search filter must not leave it
    # invisible/unselectable — the filter is cleared so the user sees it.
    db = Database()
    pid = _proj(db)
    db.create_note(pid, "Apple", "x")
    view = NotesView(db, pid)
    view._search_input.setText("apple")           # filter hides non-matches
    assert view._list.count() == 1
    view._title_input.setText("Banana")           # new note, doesn't match
    view._on_save()
    assert view._search_input.text() == ""        # filter cleared
    assert view._list_contains(view._selected_id)
    assert db.get_note_by_id(view._selected_id).title == "Banana"


def test_undo_skips_link_to_deleted_target(monkeypatch):
    db = Database()
    pid = _proj(db)
    sc = db.create_scene(pid, "S").id
    n = db.create_note(pid, "N", "body").id
    db.link_note_to_scene(n, sc)
    view = NotesView(db, pid)
    view.select_note(n)
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    view._on_delete()
    db.delete_scene(sc)                           # target gone before undo
    view._on_undo_delete()
    restored = [x for x in db.get_all_notes(pid) if x.title == "N"][0]
    assert db.get_note_scene_links(restored.id) == []   # dangling link skipped


def test_act_chip_not_navigable():
    # Act/Chapter links have no navigation target → chip label stays inert.
    db = Database()
    pid = _proj(db)
    db.create_scene(pid, "S", act="Act I")
    n = db.create_note(pid, "N", "x").id
    db.add_note_structure_link(n, pid, "act", "Act I")
    view = NotesView(db, pid, on_link_clicked=lambda t, i: None)
    view.select_note(n)
    act_link = next(l for l in view._collect_links() if l["kind"] == "act")
    chip = view._make_chip(act_link)            # builds without error
    assert chip is not None
