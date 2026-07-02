"""Standalone Pages section disabled for Alpha; navigation lives in the Manuscript.

The standalone left-panel Pages route was fullscreen-hostile, so it is **disabled
for Alpha** (hidden in every mode; its handler is inert and never mounts the old
standalone Pages widget). Graphic Novel Page/Panel navigation lives **inside the
Manuscript** as the inline comics script editor (``GraphicNovelManuscriptView``)
over the shared ``Scene.content`` body — see ``test_gn_manuscript_script_editor.py`` for
the navigator's behaviour.

These tests assert the sidebar/route safety (Pages hidden everywhere, route inert
and never mounts the old widget, no minimize/hide, no top-level window, embedded
content) plus shared-body/export safety and the documentation note. True macOS
fullscreen behaviour must still be confirmed manually.
"""

from __future__ import annotations

import os
import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import graphic_novel_blocks as gnb
from logosforge import story_structure as ss

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


def _gn(db, title="GN"):
    return db.create_project(title, narrative_engine="graphic_novel",
                             default_writing_format="graphic_novel").id


def _scene(db, pid, title="P1"):
    return ss.create_scene(db, pid, act="Act 1", chapter="Chapter 1",
                           title=title).id


# ==========================================================================
# 12-13  Pages nav item hidden + route inert (cannot open the broken section)
# ==========================================================================


@pytest.mark.parametrize("engine", ["graphic_novel", "novel", "screenplay",
                                    "stage_script", "series"])
def test_pages_hidden_in_every_mode(engine):
    # The standalone Pages section is disabled for Alpha (fullscreen-hostile) —
    # hidden in EVERY mode, including Graphic Novel.
    from logosforge.ui.main_window import MainWindow
    db = Database()
    pid = db.create_project(engine, narrative_engine=engine,
                            default_writing_format=engine).id
    win = MainWindow(db, pid)
    assert "Pages" not in win._nav_labels
    assert "Pages" not in win.sidebar_buttons
    btn = getattr(win, "_pages_btn", None)
    if btn is not None:
        assert btn.property("nav_available") is False


def test_pages_route_does_not_mount_old_standalone_widget():
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.graphic_novel_scene_pages_view import (
        GraphicNovelScenePagesView)
    db = Database()
    pid = _gn(db)
    _scene(db, pid)
    win = MainWindow(db, pid)
    win._show_gn_pages()                       # inert: never mounts the old widget
    assert not isinstance(win.content_area, GraphicNovelScenePagesView)


def test_pages_route_redirects_gn_to_embedded_navigator():
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.graphic_novel_manuscript_view import (
        GraphicNovelManuscriptView)  # noqa: F401 (legacy, not routed)
    db = Database()
    pid = _gn(db)
    _scene(db, pid)
    win = MainWindow(db, pid)
    win._show_gn_pages()
    # Routes to the Manuscript, which is the GN comics script editor.
    from logosforge.ui.writing_core_view import WritingCoreView
    assert isinstance(win.content_area, WritingCoreView)


# ==========================================================================
# 1-4  Route safety: no minimize/hide/close, no parentless top-level windows
# ==========================================================================


def test_pages_route_does_not_minimize_hide_close_main_window():
    from logosforge.ui.main_window import MainWindow
    db = Database()
    pid = _gn(db)
    _scene(db, pid)
    win = MainWindow(db, pid)
    calls = {"min": 0, "hide": 0, "close": 0}
    win.showMinimized = lambda: calls.__setitem__("min", calls["min"] + 1)  # type: ignore
    win.hide = lambda: calls.__setitem__("hide", calls["hide"] + 1)         # type: ignore
    win.close = lambda: calls.__setitem__("close", calls["close"] + 1)      # type: ignore
    win._show_gn_pages()
    assert calls == {"min": 0, "hide": 0, "close": 0}


def test_pages_route_creates_no_new_visible_top_level_window():
    from logosforge.ui.main_window import MainWindow
    db = Database()
    pid = _gn(db)
    _scene(db, pid)
    win = MainWindow(db, pid)
    before = set(QApplication.topLevelWidgets())
    win._show_gn_pages()
    new_visible = [w for w in (set(QApplication.topLevelWidgets()) - before)
                   if w.isVisible()]
    assert new_visible == []


def test_pages_content_is_embedded_in_central_dock():
    from logosforge.ui.main_window import MainWindow
    db = Database()
    pid = _gn(db)
    _scene(db, pid)
    win = MainWindow(db, pid)
    win._show_gn_pages()
    # The mounted content is a child embedded in the assistant dock, never a
    # parentless top-level window.
    assert win.content_area.window() is win


# ==========================================================================
# 14-15  Manuscript remains the Page/Panel access path; export still works
# ==========================================================================


def test_manuscript_hosts_shared_editor_for_gn():
    """The GN Manuscript route hosts the SHARED full editor (the embedded
    page/panel navigator was replaced by schema-driven shared components)."""
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.writing_core_view import WritingCoreView
    db = Database()
    pid = _gn(db)
    _scene(db, pid)
    win = MainWindow(db, pid)
    win._show_manuscript()
    view = win.content_area
    assert isinstance(view, WritingCoreView)
    assert view.window() is win                   # embedded, fullscreen-safe


def test_page_panel_editing_round_trips_through_shared_body():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    script = gnb.GraphicNovelScript(pages=[gnb.Page(
        number=1, panels=[gnb.Panel(number=1, visual_description="A wide shot")])])
    gnb.save_scene_script(db, sid, script)
    # The Manuscript path (Scene.content) sees Page/Panel content — shared body.
    assert "A wide shot" in (db.get_scene_by_id(sid).content or "")
    reloaded = gnb.load_scene_script(db, sid)
    assert reloaded.pages[0].panels[0].visual_description == "A wide shot"


def test_graphic_novel_export_uses_shared_body():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    script = gnb.GraphicNovelScript(pages=[gnb.Page(
        number=1, panels=[gnb.Panel(number=1, visual_description="EXPORTABLE")])])
    gnb.save_scene_script(db, sid, script)
    md = gnb.scene_markdown(gnb.load_scene_script(db, sid), title="P1")
    assert "EXPORTABLE" in md


def test_page_panel_body_has_no_image_generation_fields():
    fields = set(vars(gnb.Panel()).keys())
    for banned in ("image", "prompt", "comfyui", "lora", "seed", "sampler"):
        assert not any(banned in f for f in fields), banned


# ==========================================================================
# 16  Documentation records the temporary Alpha limitation
# ==========================================================================


def test_known_limitations_documents_pages_editor():
    text = open(os.path.join(_ROOT, "docs",
                             "KNOWN_LIMITATIONS_ALPHA.md")).read().lower()
    assert "pages" in text
    assert "panel" in text
    assert "scene.content" in text or "shared" in text
