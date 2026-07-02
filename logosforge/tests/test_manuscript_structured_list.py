"""Manuscript = focused continuous WRITING PAGE (matches manuscript_target.png).

Centered Act header, large Chapter heading, a dominant editor, a per-scene
context line, and inline + New Scene / + New Chapter. No left tree, no numbered
gutter, no foldable blocks. Body is scene.content only.
"""

from __future__ import annotations

import re
import warnings

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

warnings.filterwarnings("ignore")

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


def _screenplay(db):
    return db.create_project("P", narrative_engine="screenplay",
                             default_writing_format="screenplay").id


def _novel(db):
    return db.create_project("N", narrative_engine="novel").id


def _manuscript(db, pid):
    return WritingCoreView(db, pid, structured_list=True)


def _texts(view, obj):
    return [w.text() for w in view.findChildren(QLabel) if w.objectName() == obj]


def _btns(view, obj):
    return [b.text() for b in view.findChildren(QPushButton)
            if b.objectName() == obj]


# ==========================================================================
# Heavy / left-tree structure is gone; writing-page marker present
# ==========================================================================


def test_no_heavy_structures_and_marker():
    assert not hasattr(WritingCoreView, "_scene_number")
    assert not hasattr(WritingCoreView, "_toggle_fold")
    import logosforge.ui.writing_core_view as wcv
    assert not hasattr(wcv, "_FoldHeader")
    db = Database()
    pid = _screenplay(db)
    db.create_scene(pid, "S", act="Act I", chapter="Ch1", content="x")
    view = _manuscript(db, pid)
    assert view.objectName() == "manuscript_target_writing_page_view"
    assert not hasattr(view, "_structure_tree")     # no left outliner tree
    for w in view.findChildren(QLabel):
        assert not re.search(r"\b\d+\.\d+\.\d+\b", w.text() or "")  # no gutter nums


# ==========================================================================
# Continuous writing page: Act/Chapter headers + per-scene context
# ==========================================================================


def test_writing_page_headers_and_context():
    db = Database()
    pid = _novel(db)
    db.create_scene(pid, "Open", act="Act 1", chapter="Chapter 1", content="a")
    db.create_scene(pid, "Two", act="Act 1", chapter="Chapter 1", content="b")
    view = _manuscript(db, pid)
    assert any("ACT 1" in a for a in _texts(view, "writingActHeader"))
    assert any("Chapter 1" in c for c in _texts(view, "writingChapterHeader"))
    ctx = _texts(view, "writingSceneContext")
    assert len(ctx) == 2 and "SCENE 1" in ctx[0]    # one context line per scene
    assert len(view._editors) == 2                   # continuous (both shown)


def test_writing_area_dominant_placeholder():
    db = Database()
    pid = _screenplay(db)
    db.create_scene(pid, "S", act="Act I", content="")
    view = _manuscript(db, pid)
    eds = view.findChildren(_SceneEditor)
    assert eds
    assert eds[0].placeholderText() == "Start writing, or type '/' for commands…"


def test_body_is_content_not_summary():
    db = Database()
    pid = _screenplay(db)
    db.create_scene(pid, "S", act="Act I", summary="PLAN_SENTINEL",
                    content="REAL_BODY")
    view = _manuscript(db, pid)
    bodies = " ".join(e.toPlainText() for e in view.findChildren(_SceneEditor))
    assert "REAL_BODY" in bodies and "PLAN_SENTINEL" not in bodies
    # Summary surfaced only as compact read-only metadata.
    assert any("PLAN_SENTINEL" in m
               for m in _texts(view, "writingSceneSummaryMeta"))


def test_existing_body_editable():
    db = Database()
    pid = _screenplay(db)
    db.create_scene(pid, "S", act="Act I", content="hello world")
    view = _manuscript(db, pid)
    ed = next(iter(view._editors.values()))
    assert "hello world" in ed.toPlainText() and not ed.isReadOnly()


# ==========================================================================
# Inline + New Scene / + New Chapter (mode-aware)
# ==========================================================================


def test_inline_add_controls_mode_aware():
    db = Database()
    nv = _novel(db)
    db.create_scene(nv, "S", act="Act 1", chapter="Ch1", content="x")
    adds = _btns(_manuscript(db, nv), "writingInlineAdd")
    assert "+ New Scene" in adds and "+ New Chapter" in adds
    sp = _screenplay(db)
    db.create_scene(sp, "S", act="Act I", content="x")
    adds2 = _btns(_manuscript(db, sp), "writingInlineAdd")
    assert "+ New Scene" in adds2 and "+ New Chapter" not in adds2


def test_add_button_text_mode_aware():
    db = Database()
    assert _manuscript(db, _novel(db)).add_button_text() == "+ Chapter"
    assert _manuscript(db, _screenplay(db)).add_button_text() == "+ Scene"


def test_new_chapter_creates_chapter():
    db = Database()
    pid = _novel(db)
    db.create_scene(pid, "S", act="Act 1", chapter="Ch1", content="x")
    view = _manuscript(db, pid)
    view._page_new_chapter("Act 1")
    chapters = {(s.chapter or "") for s in db.get_all_scenes(pid)}
    assert "New Chapter" in chapters


# ==========================================================================
# Routing + project switch
# ==========================================================================


def test_via_mainwindow_is_writing_page():
    db = Database()
    pid = _screenplay(db)
    db.create_scene(pid, "S", act="Act I", content="x")
    win = MainWindow(db, pid)
    win.sidebar_buttons["Manuscript"].click()
    assert isinstance(win.content_area, WritingCoreView)
    assert win.content_area._structured_list is True
    assert win.content_area.objectName() == "manuscript_target_writing_page_view"


def test_project_switch_reloads_writing_page():
    db = Database()
    a = _screenplay(db)
    db.create_scene(a, "A-scene", act="Act A", content="x")
    b = _screenplay(db)
    win = MainWindow(db, a)
    win.sidebar_buttons["Manuscript"].click()
    assert len(win.content_area._editors) == 1
    win._switch_project(b)
    win.sidebar_buttons["Manuscript"].click()
    assert win.content_area._editors == {}           # B empty, fresh page
