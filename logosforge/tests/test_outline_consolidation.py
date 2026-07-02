"""Structural consolidation: Outline is the single structural section
(Act → Chapter → Scene); separate Chapters/Scenes sections are hidden from nav.
Manuscript stays stable; data is preserved; project isolation holds."""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.ui.main_window import MainWindow
from logosforge.ui.plan_view import PlanView, build_plan_tree
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


def _project(db, engine="novel", fmt=""):
    return db.create_project("P", narrative_engine=engine,
                             default_writing_format=fmt or engine).id


def _avail(win, name):
    b = win.sidebar_buttons.get(name)
    return None if b is None else b.property("nav_available")


# ==========================================================================
# Navigation: Chapters/Scenes hidden; Outline present
# ==========================================================================


@pytest.mark.parametrize("engine", ["novel", "screenplay", "graphic_novel",
                                    "stage_script", "series"])
def test_chapters_scenes_not_visible_outline_is(tmp_path, engine):
    db = Database(str(tmp_path / "sp.db"))
    win = MainWindow(db, _project(db, engine, engine))
    assert _avail(win, "Chapters") is False
    assert _avail(win, "Scenes") is False
    assert "Chapters" not in win._nav_labels and "Scenes" not in win._nav_labels
    win.sidebar_buttons["Outline"].click()
    from logosforge.ui.graphic_novel_outline_view import GraphicNovelOutlineView
    # Outline is the structural section: PlanView in most modes; the GN-aware
    # Page/Panel Outline in Graphic Novel mode.
    assert isinstance(win.content_area, (PlanView, GraphicNovelOutlineView))


def test_project_switch_does_not_restore_hidden_sections(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    a = _project(db, "novel")
    b = _project(db, "screenplay", "screenplay")
    win = MainWindow(db, a)
    win._switch_project(b)
    win._switch_project(a)
    assert _avail(win, "Chapters") is False and _avail(win, "Scenes") is False


# ==========================================================================
# Outline manages Act → Chapter → Scene (optional), scene-derived
# ==========================================================================


def test_outline_supports_act_chapter_scene_hierarchy():
    db = Database()
    pid = _project(db, "novel")
    # A chapter may exist without scenes; a scene lives under a chapter.
    db.create_scene(pid, "Ch1-placeholder", act="Act I", chapter="Chapter 1")
    db.create_scene(pid, "Opening", act="Act I", chapter="Chapter 1")
    tree = build_plan_tree(db, pid)
    acts = [a for a, _ in tree]
    assert acts == ["Act I"]
    chapters = [ch for _, chs in tree for ch, _ in chs]
    assert "Chapter 1" in chapters
    # Scenes are optional: a chapter can hold just a placeholder.
    db.create_scene(pid, "ActOnly", act="Act II", chapter="")
    assert "Act II" in [a for a, _ in build_plan_tree(db, pid)]


def test_outline_view_has_add_act_chapter_scene_and_generate():
    db = Database()
    pid = _project(db, "novel")
    db.create_scene(pid, "S1", act="Act I", chapter="Ch1")
    view = PlanView(db, pid)
    from PySide6.QtWidgets import QPushButton
    texts = " ".join(b.text() for b in view.findChildren(QPushButton))
    assert "Add Act" in texts
    assert "New Chapter" in texts
    assert "New Scene" in texts
    assert "Generate Outline" in texts


def test_outline_generation_writes_only_to_outline_not_manuscript():
    from logosforge.outline_actions import (
        apply_outline_as_scenes,
        parse_outline_response,
        repair_outline_ops,
    )
    db = Database()
    pid = _project(db, "novel")
    ops, _ = repair_outline_ops(parse_outline_response(
        "# Act 1\n## Chapter 1\n- Scene: Opening — the hero wakes"))
    created = apply_outline_as_scenes(db, pid, ops)
    assert created
    # Structure landed as scene planning rows (summary), with EMPTY manuscript
    # body — never written as prose.
    for sid in created:
        s = db.get_scene_by_id(sid)
        assert (s.content or "") == ""
        assert (s.summary or "").strip() or s.title


def test_outline_reloads_per_project_after_switch(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    a = _project(db, "novel")
    db.create_scene(a, "A-act", act="Act A", chapter="Ch")
    b = _project(db, "novel")
    win = MainWindow(db, a)
    win.sidebar_buttons["Outline"].click()
    assert build_plan_tree(db, a) != []
    win._switch_project(b)
    win.sidebar_buttons["Outline"].click()
    assert build_plan_tree(db, b) == []     # new project: clean Outline


# ==========================================================================
# Manuscript stays stable (scene-based; no outline-desc leak)
# ==========================================================================


def test_manuscript_stable_and_no_outline_leak(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    pid = _project(db, "screenplay", "screenplay")
    db.create_scene(pid, "S1", summary="OUTLINE_PLANNING", content="REAL PROSE")
    win = MainWindow(db, pid)
    win.sidebar_buttons["Manuscript"].click()
    assert isinstance(win.content_area, WritingCoreView)
    bodies = " ".join(e.toPlainText()
                      for e in win.content_area.findChildren(_SceneEditor))
    assert "REAL PROSE" in bodies
    assert "OUTLINE_PLANNING" not in bodies   # summary not shown as body


def test_new_project_no_stale_outline(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    a = _project(db, "novel")
    db.create_scene(a, "A-scene", act="Act A", chapter="Ch")
    b = _project(db, "novel")
    win = MainWindow(db, a)
    win._switch_project(b)
    assert build_plan_tree(db, b) == []
    assert db.get_chapters(b) == []
