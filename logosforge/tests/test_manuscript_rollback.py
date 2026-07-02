"""Manuscript rollback: scene-based WritingCoreView for ALL modes; only the
add-button LABEL is mode-aware (Novel '+ Chapter', else '+ Scene')."""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

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


def _proj(db, engine, fmt=""):
    return db.create_project("P", narrative_engine=engine,
                             default_writing_format=fmt or engine).id


# ==========================================================================
# Manuscript is the scene editor for every mode; add label is mode-aware
# ==========================================================================


def test_manuscript_opens_as_writing_core_view_for_all_modes():
    db = Database()
    for engine in ("novel", "screenplay", "graphic_novel", "stage_script", "series"):
        pid = _proj(db, engine)
        view = WritingCoreView(db, pid)   # constructs without crashing
        assert hasattr(view, "add_button_text")


def test_novel_add_button_label_is_chapter():
    db = Database()
    view = WritingCoreView(db, _proj(db, "novel"))
    assert view.add_button_text() == "+ Chapter"


@pytest.mark.parametrize("engine,fmt", [
    ("screenplay", "screenplay"),
    ("graphic_novel", "graphic_novel"),
    ("stage_script", "stage_script"),
    ("series", "series"),
])
def test_non_novel_add_button_label_is_scene(engine, fmt):
    db = Database()
    view = WritingCoreView(db, _proj(db, engine, fmt))
    assert view.add_button_text() == "+ Scene"


def test_empty_state_button_uses_mode_label():
    db = Database()
    # Empty Novel manuscript → the visible "+ Chapter" button.
    view = WritingCoreView(db, _proj(db, "novel"))
    labels = [b.text() for b in view.findChildren(QPushButton)
              if b.text().startswith("+ ")]
    assert "+ Chapter" in labels and "+ Scene" not in labels


def test_changing_mode_updates_label_on_switch(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    nov = _proj(db, "novel")
    scr = _proj(db, "screenplay", "screenplay")
    win = MainWindow(db, nov)
    win.sidebar_buttons["Manuscript"].click()
    assert isinstance(win.content_area, WritingCoreView)
    assert win.content_area.add_button_text() == "+ Chapter"
    win._switch_project(scr)
    win.sidebar_buttons["Manuscript"].click()
    assert isinstance(win.content_area, WritingCoreView)
    assert win.content_area.add_button_text() == "+ Scene"
    win._switch_project(nov)
    win.sidebar_buttons["Manuscript"].click()
    assert win.content_area.add_button_text() == "+ Chapter"


# ==========================================================================
# Behavior preserved: body = scene.content (no outline-desc leak); isolation
# ==========================================================================


def test_manuscript_body_is_scene_content_not_summary():
    db = Database()
    pid = _proj(db, "screenplay", "screenplay")
    sid = db.create_scene(pid, "S1", summary="OUTLINE_DESC_SENTINEL", content="").id
    view = WritingCoreView(db, pid)
    ed = next(e for e in view.findChildren(_SceneEditor)
              if getattr(e, "_scene_id", None) == sid)
    assert ed.toPlainText().strip() == ""                  # empty body
    assert "OUTLINE_DESC_SENTINEL" not in ed.toPlainText()  # not the summary


def test_existing_manuscript_text_displays():
    db = Database()
    pid = _proj(db, "novel")
    db.create_scene(pid, "S1", content="REAL PROSE HERE")
    view = WritingCoreView(db, pid)
    bodies = " ".join(e.toPlainText() for e in view.findChildren(_SceneEditor))
    assert "REAL PROSE HERE" in bodies


def test_new_project_does_not_show_previous_manuscript(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    a = _proj(db, "novel")
    db.create_scene(a, "A-scene", content="MANUSCRIPT_A_SENTINEL")
    b = _proj(db, "novel")
    win = MainWindow(db, a)
    win.sidebar_buttons["Manuscript"].click()
    win._switch_project(b)
    win.sidebar_buttons["Manuscript"].click()
    bodies_b = " ".join(e.toPlainText()
                        for e in win.content_area.findChildren(_SceneEditor))
    assert "MANUSCRIPT_A_SENTINEL" not in bodies_b


def test_no_chapter_manuscript_view_module():
    import importlib
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("logosforge.ui.chapter_manuscript_view")
