"""Graphic Novel Outline/Page/Panel — post-fix integrity gate.

A focused gate that re-verifies the Graphic Novel architecture (canonical
**Act → Page → Scene → Panel**: an Act owns its Pages and Scenes, a Panel
belongs to one Scene and sits on one Page, a Scene spans Pages, a Page can
hold Panels from several Scenes, Outline ⇄ Manuscript mirror the same shared
body, chapters hidden, standalone Pages disabled). It complements the
detailed suites (`test_gn_outline.py`, `test_gn_act_page_structure.py`,
`test_gn_manuscript_script_editor.py`, `test_gn_pages_manuscript_sync.py`)
with the audit's specific data-integrity, standalone-Pages-safety, export,
and no-image-generation invariants.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import graphic_novel_blocks as gnb
from logosforge import graphic_novel_outline as gno
from logosforge import story_structure as ss


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


def _body(db, sid):
    return gnb.load_scene_script(db, sid)


# ==========================================================================
# Data-model integrity (§2)
# ==========================================================================


def test_move_panel_to_page_preserves_body():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    gno.add_page(db, sid)
    gno.add_panel(db, sid, 0)
    gno.set_panel_field(db, sid, 0, 0, "visual_description", "KEEP_BODY")
    gno.add_page(db, sid)
    assert gno.move_panel_to_page(db, sid, 0, 0, 1)
    body = _body(db, sid)
    assert body.pages[1].panels[0].visual_description == "KEEP_BODY"
    assert len(body.pages[0].panels) == 0


def test_reorder_scenes_preserves_panels():
    db = Database()
    pid = _gn(db)
    a = _scene(db, pid, "A")
    b = _scene(db, pid, "B")
    gno.add_page(db, a); gno.add_panel(db, a, 0); gno.add_panel(db, a, 0)
    before = _body(db, a).panel_count()
    db.reorder_scenes(pid, [b, a])
    assert _body(db, a).panel_count() == before == 2


def test_round_trip_no_duplicate_panels():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    gno.add_page(db, sid)
    gno.add_panel(db, sid, 0); gno.add_panel(db, sid, 0)
    content = db.get_scene_by_id(sid).content
    reparsed = gnb.parse_graphic_novel_text(content)
    assert reparsed.panel_count() == 2


def test_panel_has_single_canonical_body():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    gno.add_page(db, sid); gno.add_panel(db, sid, 0)
    gno.set_panel_field(db, sid, 0, 0, "dialogue", "ONCE_ONLY")
    content = db.get_scene_by_id(sid).content
    assert content.count("ONCE_ONLY") == 1


def test_rename_page_persists():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    gno.add_page(db, sid)
    assert gno.set_page_field(db, sid, 0, "title", "Splash Page")
    assert _body(db, sid).pages[0].title == "Splash Page"


def test_page_lists_its_panels_and_scene_lists_its_panels():
    db = Database()
    pid = _gn(db)
    a = _scene(db, pid, "A")
    b = _scene(db, pid, "B")
    gno.add_page(db, a); gno.add_panel(db, a, 0)      # A page 1
    gno.add_panel(db, b, None)                        # B page 1
    scenes = gno.scenes_in_chapter(db, pid, "Act 1", "Chapter 1")
    pv = dict(gno.chapter_page_view(db, scenes))
    # Page 1 lists panels from both scenes; each scene lists its own panel.
    assert len(pv[1]) == 2
    assert _body(db, a).panel_count() == 1 and _body(db, b).panel_count() == 1


# ==========================================================================
# Outline ⇄ Manuscript mirror the SAME body (§5)
# ==========================================================================


def test_outline_and_manuscript_share_one_body():
    from logosforge.ui.graphic_novel_outline_view import GraphicNovelOutlineView
    from logosforge.ui.graphic_novel_manuscript_view import (
        GraphicNovelManuscriptView)
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    # Edit via the Outline data layer.
    gno.add_page(db, sid); gno.add_panel(db, sid, 0)
    gno.set_panel_field(db, sid, 0, 0, "visual_description", "MIRROR")
    # Both views read the same Scene.content.
    o = GraphicNovelOutlineView(db, pid, on_data_changed=lambda: None)
    m = GraphicNovelManuscriptView(db, pid, on_data_changed=lambda: None)
    m.select_scene(sid)
    assert "MIRROR" in (db.get_scene_by_id(sid).content or "")
    # Outline cards show the panel snippet.
    from PySide6.QtWidgets import QLabel
    snippets = [w.text() for w in o.findChildren(QLabel)
                if w.objectName() == "gnOutlinePanelSnippet"]
    assert any("MIRROR" in t for t in snippets)


# ==========================================================================
# Standalone Pages disabled + fullscreen safety (§6)
# ==========================================================================


def test_standalone_pages_hidden_and_inert():
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.graphic_novel_scene_pages_view import (
        GraphicNovelScenePagesView)
    db = Database()
    win = MainWindow(db, _gn(db))
    assert "Pages" not in win._nav_labels and "Pages" not in win.sidebar_buttons
    win._show_gn_pages()
    assert not isinstance(win.content_area, GraphicNovelScenePagesView)


def test_outline_activation_fullscreen_safe():
    from logosforge.ui.main_window import MainWindow
    db = Database()
    win = MainWindow(db, _gn(db))
    calls = {"min": 0, "hide": 0, "close": 0}
    win.showMinimized = lambda: calls.__setitem__("min", calls["min"] + 1)  # type: ignore
    win.hide = lambda: calls.__setitem__("hide", calls["hide"] + 1)         # type: ignore
    win.close = lambda: calls.__setitem__("close", calls["close"] + 1)      # type: ignore
    before = set(QApplication.topLevelWidgets())
    win._show_plan()
    new_visible = [w for w in (set(QApplication.topLevelWidgets()) - before)
                   if w.isVisible()]
    assert calls == {"min": 0, "hide": 0, "close": 0}
    assert new_visible == [] and win.content_area.window() is win


# ==========================================================================
# Export (§7) + no image generation (§8)
# ==========================================================================


def test_export_has_page_and_scene_assignment_no_secrets():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, "Cold Open")
    gno.add_page(db, sid); gno.add_panel(db, sid, 0)
    gno.set_panel_field(db, sid, 0, 0, "visual_description", "PANELBODY")
    settings = db.get_project_settings(pid) or {}
    settings["api_key"] = "sk-SECRET"
    db.save_project_settings(pid, settings)
    md = gno.export_outline_markdown(db, pid)
    assert "Cold Open" in md and "Page 1" in md and "PANELBODY" in md
    # Explicit Panel → Scene and Panel → Page assignment, page-first order.
    assert "(Scene: Cold Open → Page 1)" in md
    assert "SECRET" not in md and "sk-" not in md
    low = md.lower()
    for banned in ("comfyui", "image prompt", "lora", "img2img", "txt2img"):
        assert banned not in low


def test_logos_registry_has_no_image_or_comfyui_action():
    from logosforge.logos import actions as A
    blob = " ".join((a.name + " " + a.label).lower() for a in A.list_actions())
    for banned in ("comfyui", "image gen", "generate image", "image prompt",
                   "img2img", "txt2img", "lora "):
        assert banned not in blob, banned


def test_canvas_plot_hidden_in_gn_mode():
    from logosforge.ui.main_window import MainWindow
    db = Database()
    win = MainWindow(db, _gn(db))
    assert "Plot" not in win._nav_labels
    btn = win.sidebar_buttons.get("Plot")
    assert btn is None or btn.property("nav_available") is False


def test_panel_model_has_no_image_generation_fields():
    fields = set(vars(gnb.Panel()).keys())
    assert fields == {"number", "visual_description", "caption", "dialogue",
                      "sfx", "notes"}


# ==========================================================================
# Post-refactor gate pins (Act → Page → Scene → Panel audit, 2026-06-11)
# ==========================================================================


def _gate_outline(db, pid, counter):
    from logosforge.ui.graphic_novel_outline_view import GraphicNovelOutlineView
    return GraphicNovelOutlineView(
        db, pid, on_data_changed=lambda: counter.append(1),
        on_open_manuscript=lambda i: None)


def test_selection_and_cancelled_actions_never_mark_dirty(monkeypatch):
    from logosforge.ui import safe_dialogs
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    gno.add_page(db, sid); gno.add_panel(db, sid, 0)
    dirty = []
    v = _gate_outline(db, pid, dirty)
    # Selecting cards never mutates / never marks dirty.
    for card in v._cards:
        v._select(card.gn_data)
    assert dirty == []
    # A cancelled delete neither mutates nor marks dirty …
    v._sel = {"kind": "panel", "act": "Act 1", "scene_id": sid,
              "page": 0, "panel": 0}
    monkeypatch.setattr(safe_dialogs, "question", lambda *a, **k: False)
    v._delete_selected()
    assert dirty == [] and _body(db, sid).panel_count() == 1
    # … while the confirmed one does exactly once.
    monkeypatch.setattr(safe_dialogs, "question", lambda *a, **k: True)
    v._delete_selected()
    assert dirty == [1] and _body(db, sid).panel_count() == 0



def test_card_selection_highlight_is_safe():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    gno.add_page(db, sid); gno.add_panel(db, sid, 0)
    before = db.get_scene_by_id(sid).content
    dirty = []
    v = _gate_outline(db, pid, dirty)
    panel = next(c for c in v._cards if c.gn_data["kind"] == "panel")
    v._select(panel.gn_data)
    assert panel.property("selected") == "true"      # highlighted
    others = [c for c in v._cards if c is not panel]
    assert all(c.property("selected") == "false" for c in others)
    assert db.get_scene_by_id(sid).content == before
    assert dirty == []



def test_scene_rename_from_outline_card():
    from PySide6.QtWidgets import QLineEdit
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, "Untitled Scene")
    gno.add_page(db, sid)
    dirty = []
    v = _gate_outline(db, pid, dirty)
    group = next(c for c in v._cards
                 if c.gn_data.get("kind") == "scene_page")
    edit = group.findChild(QLineEdit, "gnOutlineSceneTitle")
    assert edit is not None and edit.text() == "Untitled Scene"
    v._commit_scene_title(sid, "  Cold Open  ")
    assert db.get_scene_by_id(sid).title == "Cold Open"   # trimmed + saved
    assert dirty == [1]
    v._commit_scene_title(sid, "   ")                     # empty refused
    v._commit_scene_title(sid, "Cold Open")               # no-op rename
    assert db.get_scene_by_id(sid).title == "Cold Open"
    assert dirty == [1]                                   # still exactly one



def test_manuscript_panel_ref_validated_against_live_script(monkeypatch):
    from logosforge.ui import safe_dialogs
    from logosforge.ui.graphic_novel_manuscript_view import (
        GraphicNovelManuscriptView)
    db = Database()
    pid = _gn(db)
    b = _scene(db, pid, "B")
    gno.add_page(db, b); gno.add_panel(db, b, 0)
    m = GraphicNovelManuscriptView(db, pid, on_data_changed=lambda: None)
    assert m.current_panel_ref() is None             # nothing focused yet
    m.select_scene(b)
    m.select_panel(0, 0)
    assert m.current_panel_ref() == (b, 0, 0)
    monkeypatch.setattr(safe_dialogs, "question", lambda *a, **k: True)
    m._delete_page(b, 0)                             # target disappears
    assert m.current_panel_ref() is None             # no stale Panel target
