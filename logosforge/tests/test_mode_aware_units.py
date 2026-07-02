"""Mode-aware primary writing unit: Novel = Chapters, others = Scenes.

Covers navigation visibility per writing mode, project-switch updates, clean
new-project state, legacy scene preservation, the additive Chapter store, and
selection clearing on switch. No destructive migration; scenes are never deleted.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.ui.chapters_view import ChaptersView
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


def _project(db, engine, fmt=""):
    return db.create_project("P", narrative_engine=engine,
                             default_writing_format=fmt or engine).id


def _avail(win, name):
    btn = win.sidebar_buttons.get(name)
    return None if btn is None else btn.property("nav_available")


# ==========================================================================
# Section visibility per mode
# ==========================================================================


@pytest.mark.parametrize("engine,fmt", [
    ("novel", "novel"),
    ("screenplay", "screenplay"),
    ("graphic_novel", "graphic_novel"),
    ("stage_script", "stage_script"),
    ("series", "series"),
])
def test_chapters_and_scenes_hidden_from_nav(tmp_path, engine, fmt):
    # Structure is consolidated into Outline: neither Chapters nor Scenes is a
    # visible main section in any mode.
    db = Database(str(tmp_path / "sp.db"))
    pid = _project(db, engine, fmt)
    win = MainWindow(db, pid)
    assert _avail(win, "Chapters") is False
    assert _avail(win, "Scenes") is False
    assert "Chapters" not in win._nav_labels
    assert "Scenes" not in win._nav_labels
    # Outline is the structural section.
    win.sidebar_buttons["Outline"].click()
    from logosforge.ui.plan_view import PlanView
    from logosforge.ui.graphic_novel_outline_view import GraphicNovelOutlineView
    # Outline is the structural section: PlanView in most modes; the GN-aware
    # Page/Panel Outline in Graphic Novel mode.
    assert isinstance(win.content_area, (PlanView, GraphicNovelOutlineView))


def test_chapters_handler_kept_as_legacy(tmp_path):
    # The handler/button are preserved (data reachable) but not in the nav.
    db = Database(str(tmp_path / "sp.db"))
    pid = _project(db, "novel")
    win = MainWindow(db, pid)
    assert "Chapters" in win._nav_section_handlers   # legacy/debug handler kept
    win.sidebar_buttons["Chapters"].click()           # still builds if invoked
    assert isinstance(win.content_area, ChaptersView)


# ==========================================================================
# Project switching keeps the sections hidden (no stale restoration)
# ==========================================================================


def test_switch_keeps_sections_hidden(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    nov = _project(db, "novel")
    scr = _project(db, "screenplay", "screenplay")
    win = MainWindow(db, nov)
    assert _avail(win, "Chapters") is False and _avail(win, "Scenes") is False
    win._switch_project(scr)
    assert _avail(win, "Chapters") is False and _avail(win, "Scenes") is False
    win._switch_project(nov)
    assert _avail(win, "Chapters") is False and _avail(win, "Scenes") is False
    assert "Chapters" not in win._nav_labels and "Scenes" not in win._nav_labels


# ==========================================================================
# Clean new-project state
# ==========================================================================


def test_new_novel_project_clean_chapter_state(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    pid = _project(db, "novel")
    MainWindow(db, pid)
    assert db.get_chapters(pid) == []      # no chapters yet
    assert db.get_all_scenes(pid) == []    # and no scenes


def test_new_screenplay_project_clean_scene_state(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    pid = _project(db, "screenplay", "screenplay")
    MainWindow(db, pid)
    assert db.get_all_scenes(pid) == []
    assert db.get_chapters(pid) == []


# ==========================================================================
# Legacy preservation
# ==========================================================================


def test_existing_scenes_preserved_when_switching_to_novel(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    nov = _project(db, "novel")
    db.create_scene(nov, "Legacy scene", content="old prose")
    scr = _project(db, "screenplay", "screenplay")
    win = MainWindow(db, scr)
    win._switch_project(nov)
    # Scenes are NOT deleted; they surface inside the Outline (PlanView) tree.
    assert len(db.get_all_scenes(nov)) == 1
    from logosforge.ui.plan_view import build_plan_tree
    assert build_plan_tree(db, nov) != []      # reachable via Outline
    assert _avail(win, "Scenes") is False       # no separate Scenes section
    assert _avail(win, "Chapters") is False     # no separate Chapters section


# ==========================================================================
# Chapter store CRUD + isolation
# ==========================================================================


def test_chapter_crud_and_ordering():
    db = Database()
    pid = db.create_project("N", narrative_engine="novel").id
    c1 = db.create_chapter(pid, title="One", summary="s1", content="b1")
    db.create_chapter(pid, title="Two")
    c3 = db.create_chapter(pid, title="Three")
    assert [c.title for c in db.get_chapters(pid)] == ["One", "Two", "Three"]
    db.update_chapter(c1.id, title="Chapter One", content="edited")
    assert db.get_chapter_by_id(c1.id).title == "Chapter One"
    db.reorder_chapter(c3.id, 0)
    assert [c.title for c in db.get_chapters(pid)][0] == "Three"
    db.delete_chapter(c1.id)
    assert all(c.id != c1.id for c in db.get_chapters(pid))


def test_chapters_project_scoped():
    db = Database()
    a = db.create_project("A", narrative_engine="novel").id
    b = db.create_project("B", narrative_engine="novel").id
    db.create_chapter(a, title="A-chap")
    assert [c.title for c in db.get_chapters(a)] == ["A-chap"]
    assert db.get_chapters(b) == []


def test_chapters_view_crud_and_selection_reset(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    pid = _project(db, "novel")
    view = ChaptersView(db, pid)
    view._new_chapter()
    view._new_chapter()
    assert len(db.get_chapters(pid)) == 2
    assert view._selected_id is not None
    # A freshly built view (e.g. after a project switch) carries no selection.
    view2 = ChaptersView(db, _project(db, "novel"))
    assert view2._selected_id is None


def test_selected_ids_cleared_on_switch(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    nov = _project(db, "novel")
    db.create_chapter(nov, title="C1")
    nov2 = _project(db, "novel")
    win = MainWindow(db, nov)
    win.sidebar_buttons["Chapters"].click()
    win.content_area._select_id(db.get_chapters(nov)[0].id)
    assert win.content_area._selected_id is not None
    win._switch_project(nov2)
    win.sidebar_buttons["Chapters"].click()
    # New project's Chapters view has no carried-over selection.
    assert win.content_area._selected_id is None
