"""Graphic Novel Outline — canonical Act → Page → Scene → Panel structure.

The standalone Pages section is disabled for Alpha; the Graphic Novel
**Outline** is the canonical structure navigator: one page-first tree
(``Act → Page → Scene → Panel``) over the shared `Scene.content` body (so it
mirrors the Manuscript), with act-wide page coordinates from
:mod:`graphic_novel_structure`. Chapters are hidden in Graphic Novel mode
(storage labels only). These tests cover the data layer, Outline visibility,
editing, mirroring, export, navigation, isolation, fullscreen safety, and
non-GN regression; the act-wide page coordinate suite lives in
`test_gn_act_page_structure.py`.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication, QLineEdit

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import graphic_novel_blocks as gnb
from logosforge import graphic_novel_outline as gno
from logosforge import story_structure as ss
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


def _gn(db, title="GN"):
    return db.create_project(title, narrative_engine="graphic_novel",
                             default_writing_format="graphic_novel").id


def _scene(db, pid, title="S", act="Act 1", chapter="Chapter 1"):
    return ss.create_scene(db, pid, act=act, chapter=chapter, title=title).id


def _outline(db, pid):
    from logosforge.ui.graphic_novel_outline_view import GraphicNovelOutlineView
    return GraphicNovelOutlineView(db, pid, on_data_changed=lambda: None,
                                   on_open_manuscript=lambda i: None)


def _body(db, sid):
    return gnb.load_scene_script(db, sid)


def _find(tree, predicate):
    stack = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
    while stack:
        it = stack.pop()
        if predicate(it):
            return it
        for i in range(it.childCount()):
            stack.append(it.child(i))
    return None


# ==========================================================================
# 1-8  Data model
# ==========================================================================


def test_scene_owns_panels_via_pages():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    gno.add_page(db, sid); gno.add_panel(db, sid, 0)
    assert _body(db, sid).pages[0].panels


def test_panel_assigned_to_page_by_containment():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    gno.add_page(db, sid); gno.add_page(db, sid)
    gno.add_panel(db, sid, 1)                  # panel on page index 1
    script = _body(db, sid)
    assert len(script.pages[1].panels) == 1 and len(script.pages[0].panels) == 0


def test_scene_can_span_multiple_pages():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    gno.add_page(db, sid); gno.add_panel(db, sid, 0)
    gno.add_page(db, sid); gno.add_panel(db, sid, 1)
    assert len(_body(db, sid).pages) == 2


def test_chapter_page_view_spans_multiple_scenes():
    db = Database()
    pid = _gn(db)
    a = _scene(db, pid, "Scene A")
    b = _scene(db, pid, "Scene B")
    gno.add_page(db, a); gno.add_panel(db, a, 0)      # Scene A page 1
    gno.add_panel(db, b, None)                        # Scene B page 1 (auto-seed)
    scenes = gno.scenes_in_chapter(db, pid, "Act 1", "Chapter 1")
    pv = dict(gno.chapter_page_view(db, scenes))
    titles = sorted({s.title for s, _pi, _ci, _p in pv[1]})
    assert titles == ["Scene A", "Scene B"]           # one page, two scenes


def test_no_duplicate_panel_body():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    gno.add_page(db, sid); gno.add_panel(db, sid, 0)
    gno.set_panel_field(db, sid, 0, 0, "visual_description", "UNIQUE_BODY")
    body = _body(db, sid)
    count = sum(p.visual_description.count("UNIQUE_BODY")
                for pg in body.pages for p in pg.panels)
    assert count == 1


# ==========================================================================
# 9-13  Outline visibility
# ==========================================================================


def test_outline_mounts_shared_planner_for_graphic_novel():
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.plan_view import PlanView
    from logosforge.ui.graphic_novel_outline_view import GraphicNovelOutlineView
    db = Database()
    win = MainWindow(db, _gn(db))
    win._show_plan()
    # The SHARED block/card planner renders the GN schema; the legacy
    # GraphicNovelOutlineView is no longer routed.
    assert isinstance(win.content_area, PlanView)
    assert not isinstance(win.content_area, GraphicNovelOutlineView)


@pytest.mark.parametrize("engine", ["novel", "screenplay", "stage_script",
                                    "series"])
def test_outline_unchanged_for_non_gn(engine):
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.plan_view import PlanView
    db = Database()
    pid = db.create_project(engine, narrative_engine=engine,
                            default_writing_format=engine).id
    win = MainWindow(db, pid)
    win._show_plan()
    assert isinstance(win.content_area, PlanView)


def test_outline_shows_act_page_scene_panel_chapter_hidden():
    from PySide6.QtWidgets import QFrame, QLabel
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, "Cold Open")
    gno.add_page(db, sid); gno.add_panel(db, sid, 0)
    v = _outline(db, pid)
    # Canonical block/card hierarchy: Act card > Page card > Scene group >
    # Panel card (the shared Outline UX, not a tree).
    kinds = [c.gn_data.get("kind") for c in v._cards]
    assert kinds.count("act") == 1
    assert kinds.count("act_page") == 1
    assert kinds.count("scene_page") == 1
    assert kinds.count("panel") == 1
    panel = next(c for c in v._cards if c.gn_data["kind"] == "panel")
    # Nesting: the panel card lives inside scene group inside page inside act.
    names = []
    w = panel.parentWidget()
    while w is not None:
        if isinstance(w, QFrame) and w.objectName().startswith("gn"):
            names.append(w.objectName())
        w = w.parentWidget()
    assert names[:3] == ["gnSceneGroup", "gnPageCard", "gnActCard"]
    # Chapters are HIDDEN from the Graphic Novel Outline.
    assert not any("Chapter" in lbl.text()
                   for lbl in v.findChildren(QLabel))



def test_outline_page_first_order_shows_scene_under_page():
    from PySide6.QtWidgets import QLabel
    db = Database()
    pid = _gn(db)
    a = _scene(db, pid, "Scene A")
    gno.add_page(db, a); gno.add_panel(db, a, 0)
    v = _outline(db, pid)
    page = next(c for c in v._cards if c.gn_data.get("kind") == "act_page")
    assert page.gn_data["page_no"] == 1
    labels = [w.text() for w in page.findChildren(QLabel)
              if w.objectName() == "gnOutlineSceneLabel"]
    assert labels and "Scene A" in labels[0]



def test_add_page_from_outline():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    v = _outline(db, pid)
    v._sel = {"kind": "scene", "act": "Act 1", "scene_id": sid}
    v._add_page()
    assert len(_body(db, sid).pages) == 1


def test_add_panel_from_outline():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    v = _outline(db, pid)
    v._sel = {"kind": "scene", "act": "Act 1", "scene_id": sid}
    v._add_page(); v._add_panel()
    assert len(_body(db, sid).pages[0].panels) == 1


@pytest.mark.parametrize("field,value", [
    ("visual_description", "Rooftop"),
    ("caption", "Midnight"),
    ("dialogue", "Run!"),
    ("sfx", "BOOM"),
    ("notes", "wide"),
])
def test_edit_panel_field_from_outline(field, value):
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    gno.add_page(db, sid); gno.add_panel(db, sid, 0)
    assert gno.set_panel_field(db, sid, 0, 0, field, value)
    assert getattr(_body(db, sid).pages[0].panels[0], field) == value


def test_assign_panel_to_another_page():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    gno.add_page(db, sid); gno.add_panel(db, sid, 0)
    gno.add_page(db, sid)
    assert gno.move_panel_to_page(db, sid, 0, 0, 1)
    body = _body(db, sid)
    assert len(body.pages[0].panels) == 0 and len(body.pages[1].panels) == 1


def test_move_panel_within_scene():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    gno.add_page(db, sid)
    gno.add_panel(db, sid, 0); gno.set_panel_field(db, sid, 0, 0, "visual_description", "first")
    gno.add_panel(db, sid, 0); gno.set_panel_field(db, sid, 0, 1, "visual_description", "second")
    assert gno.move_panel(db, sid, 0, 1, -1)
    assert _body(db, sid).pages[0].panels[0].visual_description == "second"


def test_delete_panel_from_outline_with_confirmation(monkeypatch):
    monkeypatch.setattr(safe_dialogs, "question", lambda *a, **k: True)
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    gno.add_page(db, sid); gno.add_panel(db, sid, 0); gno.add_panel(db, sid, 0)
    v = _outline(db, pid)
    v._sel = {"kind": "panel", "act": "Act 1",
              "scene_id": sid, "page": 0, "panel": 0}
    v._delete_selected()
    assert len(_body(db, sid).pages[0].panels) == 1


def test_delete_page_cancel_keeps_data(monkeypatch):
    monkeypatch.setattr(safe_dialogs, "question", lambda *a, **k: False)
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    gno.add_page(db, sid); gno.add_panel(db, sid, 0)
    v = _outline(db, pid)
    v._sel = {"kind": "scene_page", "act": "Act 1",
              "scene_id": sid, "page": 0, "page_no": 1, "continued": False}
    v._delete_selected()
    assert len(_body(db, sid).pages) == 1


def test_add_scene_to_act_from_outline():
    db = Database()
    pid = _gn(db)
    _scene(db, pid, "First")
    v = _outline(db, pid)
    v._sel = {"kind": "act", "act": "Act 1"}
    v._add_scene()
    scenes = ss.list_scenes(db, pid)
    titles = {s.title for s in scenes}
    assert "Untitled Scene" in titles
    # The new scene lands under the selected Act (chapter stays hidden).
    assert all(s.act == "Act 1" for s in scenes)


# ==========================================================================
# 28-34  Mirroring Outline <-> Manuscript (shared body)
# ==========================================================================


def test_outline_edit_visible_in_manuscript():
    from logosforge.ui.graphic_novel_manuscript_view import (
        GraphicNovelManuscriptView)
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    gno.add_page(db, sid); gno.add_panel(db, sid, 0)
    gno.set_panel_field(db, sid, 0, 0, "visual_description", "FROM_OUTLINE")
    # The Manuscript reads the same Scene.content body.
    m = GraphicNovelManuscriptView(db, pid, on_data_changed=lambda: None)
    m.select_scene(sid)
    assert "FROM_OUTLINE" in (db.get_scene_by_id(sid).content or "")


def test_manuscript_edit_visible_in_outline():
    from PySide6.QtWidgets import QLabel
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    # Manuscript-side authoring straight into the shared body.
    script = gnb.GraphicNovelScript(pages=[gnb.Page(
        number=1, panels=[gnb.Panel(number=1, visual_description="FROM_MS")])])
    gnb.save_scene_script(db, sid, script)
    v = _outline(db, pid)
    snippets = [w.text() for w in v.findChildren(QLabel)
                if w.objectName() == "gnOutlinePanelSnippet"]
    assert any("FROM_MS" in t for t in snippets)



def test_project_switch_isolation(tmp_path):
    db = Database(str(tmp_path / "iso.db"))
    a = _gn(db, "A")
    sa = _scene(db, a, "A-scene")
    gno.add_page(db, sa); gno.add_panel(db, sa, 0)
    b = _gn(db, "B")
    vb = _outline(db, b)
    assert vb._cards == []                        # B has no acts/scenes
    from PySide6.QtWidgets import QLabel
    assert any(w.objectName() == "gnOutlineEmpty"
               for w in vb.findChildren(QLabel))



def test_double_click_scene_opens_manuscript():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, "Opener")
    opened = []
    from logosforge.ui.graphic_novel_outline_view import GraphicNovelOutlineView
    v = GraphicNovelOutlineView(db, pid, on_open_manuscript=lambda i: opened.append(i))
    card = next(c for c in v._cards
                if c.gn_data.get("kind") in ("scene", "scene_page")
                and c.gn_data.get("scene_id") == sid)
    v._activate(card.gn_data)
    assert opened == [sid]



def test_double_click_panel_opens_manuscript():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    gno.add_page(db, sid); gno.add_panel(db, sid, 0)
    opened = []
    from logosforge.ui.graphic_novel_outline_view import GraphicNovelOutlineView
    v = GraphicNovelOutlineView(db, pid, on_open_manuscript=lambda i: opened.append(i))
    card = next(c for c in v._cards if c.gn_data.get("kind") == "panel")
    v._activate(card.gn_data)                     # no on_open_panel wired →
    assert opened == [sid]                        # falls back to the scene



def test_selection_does_not_mutate():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    gno.add_page(db, sid); gno.add_panel(db, sid, 0)
    before = db.get_scene_by_id(sid).content
    v = _outline(db, pid)
    for card in v._cards:
        v._select(card.gn_data)                   # selection only
    assert db.get_scene_by_id(sid).content == before



def test_standalone_pages_hidden():
    from logosforge.ui.main_window import MainWindow
    db = Database()
    win = MainWindow(db, _gn(db))
    assert "Pages" not in win._nav_labels and "Pages" not in win.sidebar_buttons


def test_pages_route_does_not_mount_old_widget():
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.graphic_novel_scene_pages_view import (
        GraphicNovelScenePagesView)
    db = Database()
    win = MainWindow(db, _gn(db))
    win._show_gn_pages()
    assert not isinstance(win.content_area, GraphicNovelScenePagesView)


def test_outline_creates_no_top_level_window():
    from logosforge.ui.main_window import MainWindow
    db = Database()
    win = MainWindow(db, _gn(db))
    before = set(QApplication.topLevelWidgets())
    win._show_plan()
    new_visible = [w for w in (set(QApplication.topLevelWidgets()) - before)
                   if w.isVisible()]
    assert new_visible == [] and win.content_area.window() is win


def test_outline_activation_does_not_minimize():
    from logosforge.ui.main_window import MainWindow
    db = Database()
    win = MainWindow(db, _gn(db))
    calls = {"min": 0, "hide": 0}
    win.showMinimized = lambda: calls.__setitem__("min", calls["min"] + 1)  # type: ignore
    win.hide = lambda: calls.__setitem__("hide", calls["hide"] + 1)         # type: ignore
    win._show_plan()
    assert calls == {"min": 0, "hide": 0}


# ==========================================================================
# 42-49  Export
# ==========================================================================


def test_export_includes_pages_panels_scene_and_page_assignment():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, "Cold Open")
    gno.add_page(db, sid); gno.add_panel(db, sid, 0)
    gno.set_panel_field(db, sid, 0, 0, "visual_description", "EXPORTABLE")
    md = gno.export_outline_markdown(db, pid)
    assert "Cold Open" in md            # scene
    assert "Page 1" in md               # page
    assert "EXPORTABLE" in md           # panel body
    # Explicit Panel → Scene / Panel → Page assignment, page-first order.
    assert "(Scene: Cold Open → Page 1)" in md


def test_export_no_duplicate_panel_text():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    gno.add_page(db, sid); gno.add_panel(db, sid, 0)
    gno.set_panel_field(db, sid, 0, 0, "dialogue", "ONLY_ONCE_LINE")
    md = gnb.export_project_markdown(db, pid)
    assert md.count("ONLY_ONCE_LINE") == 1


def test_export_no_image_or_comfyui_or_secrets():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    gno.add_page(db, sid); gno.add_panel(db, sid, 0)
    settings = db.get_project_settings(pid) or {}
    settings["api_key"] = "sk-SECRET"
    db.save_project_settings(pid, settings)
    md = gno.export_outline_markdown(db, pid)
    low = md.lower()
    for banned in ("comfyui", "image prompt", "lora", "img2img", "txt2img"):
        assert banned not in low
    assert "sk-SECRET" not in md and "SECRET" not in md


def test_panel_model_has_no_image_fields():
    fields = set(vars(gnb.Panel()).keys())
    for banned in ("image", "prompt", "comfyui", "lora", "seed", "sampler"):
        assert not any(banned in f for f in fields), banned
