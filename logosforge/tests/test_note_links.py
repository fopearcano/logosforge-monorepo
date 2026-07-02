"""Notes are simple and linkable to Outline structure (Act / Chapter / Scene).

Covers the new Act/Chapter link table (NoteStructureLink), the existing Scene
links, the simplified NotesView chips UI, project isolation, missing-target
safety, Outline/Manuscript indicators, and export.
"""

from __future__ import annotations

import json
import warnings

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.export import export_json
from logosforge.ui.main_window import MainWindow
from logosforge.ui.notes_view import NotesView
from logosforge.ui.plan_view import PlanView
from logosforge.ui.writing_core_view import WritingCoreView


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


def _proj(db, engine="novel"):
    return db.create_project("P", narrative_engine=engine,
                             default_writing_format=engine).id


def _notes(db, pid):
    return NotesView(db, pid)


# ==========================================================================
# DB layer: Act / Chapter structure links
# ==========================================================================


def test_link_note_to_act_and_chapter():
    db = Database()
    pid = _proj(db)
    db.create_scene(pid, "S", act="Act I", chapter="Ch1", content="x")
    n = db.create_note(pid, "N", "b").id
    db.add_note_structure_link(n, pid, "act", "Act I")
    db.add_note_structure_link(n, pid, "chapter", "Ch1")
    assert set(db.get_note_structure_links(n)) == {("act", "Act I"),
                                                   ("chapter", "Ch1")}


def test_structure_link_is_idempotent():
    db = Database()
    pid = _proj(db)
    n = db.create_note(pid, "N", "b").id
    db.add_note_structure_link(n, pid, "act", "Act I")
    db.add_note_structure_link(n, pid, "act", "Act I")
    assert db.get_note_structure_links(n) == [("act", "Act I")]


def test_note_can_have_multiple_links():
    db = Database()
    pid = _proj(db)
    s = db.create_scene(pid, "S", act="Act I", chapter="Ch1", content="x").id
    n = db.create_note(pid, "N", "b").id
    db.add_note_structure_link(n, pid, "act", "Act I")
    db.add_note_structure_link(n, pid, "chapter", "Ch1")
    db.link_note_to_scene(n, s)
    assert len(db.get_note_structure_links(n)) == 2
    assert db.get_note_scene_links(n) == [s]


def test_remove_link_keeps_note_and_structure():
    db = Database()
    pid = _proj(db)
    s = db.create_scene(pid, "S", act="Act I", content="x").id
    n = db.create_note(pid, "N", "b").id
    db.add_note_structure_link(n, pid, "act", "Act I")
    db.link_note_to_scene(n, s)
    db.remove_note_structure_link(n, "act", "Act I")
    db.unlink_note_from_scene(n, s)
    assert db.get_note_by_id(n) is not None        # note survives
    assert db.get_scene_by_id(s) is not None        # scene survives
    assert db.get_note_structure_links(n) == []


def test_delete_note_cascades_structure_links():
    db = Database()
    pid = _proj(db)
    n = db.create_note(pid, "N", "b").id
    db.add_note_structure_link(n, pid, "act", "Act I")
    db.delete_note(n)
    assert db.get_note_structure_links(n) == []


def test_structure_links_project_bound():
    db = Database()
    a = _proj(db)
    b = _proj(db)
    na = db.create_note(a, "A-note", "b").id
    db.add_note_structure_link(na, a, "act", "Act I")
    assert db.get_structure_note_count(a, "act", "Act I") == 1
    assert db.get_structure_note_count(b, "act", "Act I") == 0   # isolated


def test_missing_target_handled_safely():
    db = Database()
    pid = _proj(db)
    n = db.create_note(pid, "N", "b").id
    # Link to an Act that no scene uses → still stored, still removable, no crash.
    db.add_note_structure_link(n, pid, "act", "Ghost Act")
    assert ("act", "Ghost Act") in db.get_note_structure_links(n)
    view = _notes(db, pid)
    view.select_note(n)
    links = view._collect_links()
    assert any(l["missing"] for l in links)         # flagged missing, no crash
    db.remove_note_structure_link(n, "act", "Ghost Act")
    assert db.get_note_structure_links(n) == []


# ==========================================================================
# NotesView UI: create / edit / delete / link chips
# ==========================================================================


def test_create_and_edit_note_via_view():
    db = Database()
    pid = _proj(db)
    view = _notes(db, pid)
    view._title_input.setText("My Note")
    view._content_input.setPlainText("hello")
    view._on_save()
    assert view._selected_id is not None
    assert db.get_note_by_id(view._selected_id).title == "My Note"
    view._title_input.setText("Renamed")
    view._on_save()
    assert db.get_note_by_id(view._selected_id).title == "Renamed"


def test_delete_note_confirms(monkeypatch):
    db = Database()
    pid = _proj(db)
    nid = db.create_note(pid, "Doomed", "b").id
    view = _notes(db, pid)
    view.select_note(nid)
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Yes)
    view._on_delete()
    assert db.get_note_by_id(nid) is None


def test_link_chips_add_and_remove():
    db = Database()
    pid = _proj(db)
    s = db.create_scene(pid, "S", act="Act I", chapter="Ch1", content="x").id
    nid = db.create_note(pid, "N", "b").id
    view = _notes(db, pid)
    view.select_note(nid)
    view._add_structure("act", "Act I")
    view._add_structure("chapter", "Ch1")
    view._add_scene(s)
    assert view._links_list.count() == 3            # three chips
    view._remove_link({"kind": "scene", "ref": s})
    assert view._links_list.count() == 2
    assert db.get_note_scene_links(nid) == []        # scene unlinked


def test_notes_view_has_refresh():
    db = Database()
    pid = _proj(db)
    assert hasattr(_notes(db, pid), "refresh")


# ==========================================================================
# Canonical structure display (path / numbering, updates on move)
# ==========================================================================


def test_note_link_label_canonical_numbers_novel():
    from logosforge.story_structure import note_link_label
    db = Database()
    pid = _proj(db)
    a = db.create_scene(pid, "Alpha", act="Act I", chapter="Ch1", content="x").id
    db.create_scene(pid, "Beta", act="Act II", chapter="Ch2", content="y")
    assert note_link_label(db, pid, "act", "Act I") == ("Act 1 — Act I", False)
    assert note_link_label(db, pid, "act", "Act II") == ("Act 2 — Act II", False)
    assert note_link_label(db, pid, "chapter", "Ch1") == ("Chapter 1.1 — Ch1", False)
    assert note_link_label(db, pid, "scene", a) == ("Scene 1.1.1 — Alpha", False)


def test_note_link_label_flattens_for_screenplay():
    from logosforge.story_structure import note_link_label
    db = Database()
    pid = _proj(db, "screenplay")
    s = db.create_scene(pid, "Sc", act="Act I", chapter="Seq 1", content="z").id
    # Screenplay numbering flattens to Act.Scene (novel is Act.Chapter.Scene).
    assert note_link_label(db, pid, "scene", s) == ("Scene 1.1 — Sc", False)


def test_note_link_label_missing_targets_safe():
    from logosforge.story_structure import note_link_label
    db = Database()
    pid = _proj(db)
    assert note_link_label(db, pid, "act", "Ghost")[1] is True
    assert note_link_label(db, pid, "chapter", "Nope")[1] is True
    assert note_link_label(db, pid, "scene", 99999) == ("Scene — (missing)", True)


def test_chips_show_canonical_path():
    db = Database()
    pid = _proj(db)
    s = db.create_scene(pid, "Alpha", act="Act I", chapter="Ch1", content="x").id
    n = db.create_note(pid, "N", "b").id
    db.add_note_structure_link(n, pid, "act", "Act I")
    db.add_note_structure_link(n, pid, "chapter", "Ch1")
    db.link_note_to_scene(n, s)
    view = _notes(db, pid)
    view.select_note(n)
    labels = {l["label"] for l in view._collect_links()}
    assert "Act 1 — Act I" in labels
    assert "Chapter 1.1 — Ch1" in labels
    assert "Scene 1.1.1 — Alpha" in labels


def test_moving_scene_updates_displayed_number_link_stays_bound():
    db = Database()
    pid = _proj(db)
    a = db.create_scene(pid, "Alpha", act="Act I", chapter="Ch1", content="x").id
    b = db.create_scene(pid, "Beta", act="Act I", chapter="Ch1", content="y").id
    n = db.create_note(pid, "N", "b").id
    db.link_note_to_scene(n, b)                       # Beta is 1.1.2
    view = _notes(db, pid)
    view.select_note(n)
    assert any("Scene 1.1.2 — Beta" == l["label"] for l in view._collect_links())
    db.reorder_scenes(pid, [b, a])                    # move Beta first -> 1.1.1
    view._refresh_links()
    assert any("Scene 1.1.1 — Beta" == l["label"] for l in view._collect_links())
    assert db.get_note_scene_links(n) == [b]          # link still bound to same id


def test_moving_chapter_updates_displayed_path():
    db = Database()
    pid = _proj(db)
    a = db.create_scene(pid, "Alpha", act="Act I", chapter="Ch1", content="x").id
    b = db.create_scene(pid, "Beta", act="Act I", chapter="Ch2", content="y").id
    n = db.create_note(pid, "N", "b").id
    db.add_note_structure_link(n, pid, "chapter", "Ch2")   # Ch2 is 1.2
    view = _notes(db, pid)
    view.select_note(n)
    assert any("Chapter 1.2 — Ch2" == l["label"] for l in view._collect_links())
    db.reorder_scenes(pid, [b, a])                    # Ch2's scene first -> Ch2 is 1.1
    view._refresh_links()
    assert any("Chapter 1.1 — Ch2" == l["label"] for l in view._collect_links())
    # The link is still stored by chapter name (same node), only the number moved.
    assert ("chapter", "Ch2") in db.get_note_structure_links(n)


# ==========================================================================
# Project isolation (UI + MainWindow)
# ==========================================================================


def test_project_switch_reloads_note_links(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    a = _proj(db)
    na = db.create_note(a, "A-note", "b").id
    db.add_note_structure_link(na, a, "act", "A-ACT-SENTINEL")
    b = _proj(db)
    db.create_note(b, "B-note", "b")
    win = MainWindow(db, a)
    win.sidebar_buttons["Notes"].click()
    assert isinstance(win.content_area, NotesView)
    win._switch_project(b)
    win.sidebar_buttons["Notes"].click()
    # B's Notes view shows only B's notes; A's sentinel link is not present.
    titles = []
    lw = win.content_area._list
    for i in range(lw.count()):
        titles.append(lw.item(i).text())
    assert any("B-note" in t for t in titles)
    assert all("A-note" not in t for t in titles)
    assert db.get_structure_note_count(b, "act", "A-ACT-SENTINEL") == 0


# ==========================================================================
# Outline + Manuscript indicators
# ==========================================================================


def test_outline_note_indicator_appears():
    db = Database()
    pid = _proj(db)
    db.create_scene(pid, "S", act="Act I", chapter="Ch1", content="x")
    n = db.create_note(pid, "N", "b").id
    db.add_note_structure_link(n, pid, "act", "Act I")
    inds = [w.objectName() for w in PlanView(db, pid).findChildren(QLabel)
            if w.objectName() == "planNoteIndicator"]
    assert inds                                      # at least the Act indicator


def test_manuscript_note_indicator_in_context_header():
    db = Database()
    pid = _proj(db, "screenplay")
    s = db.create_scene(pid, "Sc", act="Act I", content="y").id
    n = db.create_note(pid, "N", "b").id
    db.link_note_to_scene(n, s)
    view = WritingCoreView(db, pid, structured_list=True)
    from PySide6.QtWidgets import QLabel
    notes = [w.text() for w in view.findChildren(QLabel)
             if w.objectName() == "writingSceneNotes"]
    assert any("📝" in t for t in notes)


# ==========================================================================
# Export
# ==========================================================================


def test_export_includes_structure_links_no_cross_project():
    db = Database()
    a = _proj(db)
    b = _proj(db)
    db.create_scene(a, "S", act="Act I", content="x")
    na = db.create_note(a, "A-note", "body").id
    db.add_note_structure_link(na, a, "act", "Act I")
    db.create_note(b, "B-NOTE-SENTINEL", "x")

    blob = export_json(db, a)
    data = json.loads(blob)
    note = data["notes"][0]
    assert {"type": "act", "ref": "Act I"} in note["structure_links"]
    assert "B-NOTE-SENTINEL" not in blob              # no cross-project leak
