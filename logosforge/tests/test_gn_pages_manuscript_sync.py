"""Graphic Novel — Manuscript and Pages/Panels share ONE body (Alpha fix).

The GN scene body is Scene.content, parsed/serialized by graphic_novel_blocks into
Pages → Panels. The Manuscript editor and the Pages section both read/write that
same body, so edits round-trip (on refresh / section switch). The new Pages view
is scene-centric over that shared body — not a second store. Panels are
collapsible. No image generation / ComfyUI / prompt fields.
"""

from __future__ import annotations

import os
import tokenize
import warnings

import pytest
from PySide6.QtWidgets import QApplication, QToolButton

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge import graphic_novel_blocks as gnb

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


def _scene(db, pid, content="", *, title="Opening", act="Act 1", chapter="Chapter 1"):
    return ss.create_scene(db, pid, act=act, chapter=chapter, title=title,
                           content=content, summary="").id


def _view(db, pid, **cb):
    from logosforge.ui.graphic_novel_scene_pages_view import GraphicNovelScenePagesView
    return GraphicNovelScenePagesView(db, pid, **cb)


def _manuscript_body(db, sid):
    """The body as the Manuscript / export path sees it (Scene.content)."""
    return gnb.load_scene_script(db, sid)


def _one_panel_view(db):
    pid = _gn(db)
    sid = _scene(db, pid)
    v = _view(db, pid)
    v._add_page()
    v._add_panel()
    return pid, sid, v


# ==========================================================================
# 1-3  Single source of truth
# ==========================================================================


def test_manuscript_and_pages_read_same_body():
    db = Database()
    pid, sid, v = _one_panel_view(db)
    v._set_panel_field(0, 0, "visual_description", "Maria at the window.")
    # The Manuscript/export path (Scene.content) sees the Pages edit.
    man = _manuscript_body(db, sid)
    assert man.pages[0].panels[0].visual_description == "Maria at the window."


def test_no_separate_pages_store_writes_go_to_scene_content():
    db = Database()
    pid, sid, v = _one_panel_view(db)
    v._set_panel_field(0, 0, "dialogue", "MARIA: SENTINEL_LINE")
    # The write landed in Scene.content (the shared body), not a side table.
    assert "SENTINEL_LINE" in (db.get_scene_by_id(sid).content or "")


def test_legacy_plain_text_body_loads_safely():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, content="A legacy prose body with no PAGE/PANEL markers.")
    v = _view(db, pid)                       # must not crash
    assert v._scene_id == sid
    # Lossless: legacy text is preserved as Page 1 / Panel 1 visual.
    man = _manuscript_body(db, sid)
    assert "legacy prose body" in gnb.serialize_graphic_novel_script(man)


# ==========================================================================
# 4-9  Manuscript -> Pages (editing Scene.content shows in the Pages view)
# ==========================================================================


def test_manuscript_edits_show_in_pages_view():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    # Simulate Manuscript-side authoring straight into the shared body.
    script = gnb.GraphicNovelScript()
    page = gnb.add_page(script, title="Opening Page")
    page.summary = "Establish the city."
    gnb.add_panel(page, visual_description="Wide of the skyline.",
                  caption="Night.", dialogue="NARRATOR: It begins.",
                  sfx="BOOM", notes="splash")
    gnb.save_scene_script(db, sid, script)
    v = _view(db, pid)
    v.refresh()
    p = v._script.pages[0]
    assert p.title == "Opening Page" and p.summary == "Establish the city."
    panel = p.panels[0]
    assert panel.visual_description == "Wide of the skyline."
    assert panel.caption == "Night."
    assert panel.dialogue == "NARRATOR: It begins."
    assert panel.sfx == "BOOM"
    assert panel.notes == "splash"


# ==========================================================================
# 10-18  Pages -> Manuscript (Pages edits show via Scene.content)
# ==========================================================================


def test_add_page_reflects_in_manuscript():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    v = _view(db, pid)
    v._add_page()
    assert len(_manuscript_body(db, sid).pages) == 1


def test_add_panel_reflects_in_manuscript():
    db = Database()
    pid, sid, v = _one_panel_view(db)
    assert _manuscript_body(db, sid).panel_count() == 1


@pytest.mark.parametrize("field,value", [
    ("visual_description", "A close-up."), ("caption", "Meanwhile…"),
    ("dialogue", "BOB: Hello."), ("sfx", "KRAK"), ("notes", "two-shot")])
def test_panel_field_edit_reflects_in_manuscript(field, value):
    db = Database()
    pid, sid, v = _one_panel_view(db)
    v._set_panel_field(0, 0, field, value)
    assert getattr(_manuscript_body(db, sid).pages[0].panels[0], field) == value


def test_reorder_panel_reflects_in_manuscript():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    v = _view(db, pid)
    v._add_page()
    v._add_panel(); v._set_panel_field(0, 0, "visual_description", "FIRST")
    v._add_panel(); v._set_panel_field(0, 1, "visual_description", "SECOND")
    v._move_panel(0, 1, -1)              # SECOND moves up
    man = _manuscript_body(db, sid)
    assert man.pages[0].panels[0].visual_description == "SECOND"
    assert man.pages[0].panels[1].visual_description == "FIRST"


def test_delete_panel_reflects_in_manuscript():
    db = Database()
    pid, sid, v = _one_panel_view(db)
    v._add_panel()
    assert _manuscript_body(db, sid).panel_count() == 2
    v._delete_panel(0, 0, confirm=False)
    assert _manuscript_body(db, sid).panel_count() == 1


def test_delete_page_reflects_in_manuscript():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    v = _view(db, pid)
    v._add_page(); v._add_page()
    assert len(_manuscript_body(db, sid).pages) == 2
    v._delete_page(0, confirm=False)
    assert len(_manuscript_body(db, sid).pages) == 1


# ==========================================================================
# 19-22  UI: collapse / compact summary
# ==========================================================================


def test_panel_card_collapse_expand():
    db = Database()
    pid, sid, v = _one_panel_view(db)
    card = v._panel_cards[0]
    assert card.is_collapsed() is False
    card.set_collapsed(True)
    assert card.is_collapsed() is True and card._body.isVisible() is False
    card.set_collapsed(False)
    assert card.is_collapsed() is False


def test_collapsed_panel_shows_compact_summary():
    db = Database()
    pid, sid, v = _one_panel_view(db)
    v._set_panel_field(0, 0, "visual_description", "Maria runs through the alley.")
    v._set_panel_field(0, 0, "dialogue", "MARIA: Faster!")
    v.refresh()
    card = v._panel_cards[0]
    card.set_collapsed(True)
    summary = card.summary_text()
    assert summary.startswith("Panel 1 —") and "Maria runs" in summary


def test_page_group_collapse():
    db = Database()
    pid, sid, v = _one_panel_view(db)
    # Page groups expose collapse toggles; collapse state is session-tracked and
    # honored on re-render.
    assert v._pages_host.findChildren(QToolButton)        # toggles exist
    v._collapsed_pages.add(0)
    v._render_pages()                                      # honor state, no crash
    assert 0 in v._collapsed_pages


# ==========================================================================
# 23-25  Project isolation
# ==========================================================================


def test_pages_isolated_across_projects(tmp_path):
    db = Database(str(tmp_path / "gn.db"))
    a = _gn(db, "A")
    sa = _scene(db, a)
    va = _view(db, a); va._add_page(); va._add_panel()
    va._set_panel_field(0, 0, "visual_description", "A_SENTINEL panel")
    b = _gn(db, "B")
    vb = _view(db, b)
    body_b = " ".join(gnb.serialize_graphic_novel_script(
        _manuscript_body(db, s.id)) for s in db.get_all_scenes(b))
    assert "A_SENTINEL" not in body_b


def test_project_switch_refreshes_pages():
    # The standalone Pages route is deferred for Alpha (no longer mounted via nav),
    # but the scene-centric Pages view stays project-isolated when constructed for
    # each project (it still edits the shared body that the Manuscript syncs with).
    db = Database()
    a = _gn(db, "A")
    _scene(db, a, title="AlphaScene")
    b = _gn(db, "B")
    _scene(db, b, title="BetaScene")
    va = _view(db, a)
    titles_a = [va._scene_list.item(i).text()
                for i in range(va._scene_list.count())]
    assert "AlphaScene" in titles_a
    vb = _view(db, b)
    titles_b = [vb._scene_list.item(i).text()
                for i in range(vb._scene_list.count())]
    assert "BetaScene" in titles_b and "AlphaScene" not in titles_b


def test_new_gn_project_starts_clean():
    db = Database()
    pid = _gn(db)
    v = _view(db, pid)
    assert v._scene_id is None          # no scenes yet
    assert not v._script.pages


# ==========================================================================
# 26-30  Mode safety
# ==========================================================================


@pytest.mark.parametrize("engine", ["novel", "screenplay", "stage_script", "series"])
def test_pages_nav_routes_away_in_non_gn_modes(engine):
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.graphic_novel_scene_pages_view import GraphicNovelScenePagesView
    db = Database()
    pid = db.create_project(engine, narrative_engine=engine,
                            default_writing_format=engine).id
    _scene(db, pid)
    win = MainWindow(db, pid)
    win._show_gn_pages()                 # defensive route — not GN
    assert not isinstance(win.content_area, GraphicNovelScenePagesView)


def test_gn_body_parsed_only_as_graphic_novel():
    db = Database()
    pid, sid, v = _one_panel_view(db)
    # The view always uses the graphic-novel adapter for the body.
    assert isinstance(v._script, gnb.GraphicNovelScript)


# ==========================================================================
# 31-35  Export
# ==========================================================================


def test_export_uses_shared_pages_body():
    db = Database()
    pid, sid, v = _one_panel_view(db)
    v._set_panel_field(0, 0, "visual_description", "EXPORT_SENTINEL visual")
    md = gnb.export_project_markdown(db, pid)
    assert "EXPORT_SENTINEL visual" in md


def test_export_does_not_duplicate_body():
    db = Database()
    pid, sid, v = _one_panel_view(db)
    v._set_panel_field(0, 0, "visual_description", "UNIQUE_PANEL_X")
    md = gnb.export_project_markdown(db, pid)
    assert md.count("UNIQUE_PANEL_X") == 1


def test_export_has_no_image_or_secret_data():
    db = Database()
    from logosforge.settings import get_manager
    get_manager().set("ai_api_key", "SECRET_KEY_SENTINEL")
    pid, sid, v = _one_panel_view(db)
    v._set_panel_field(0, 0, "visual_description", "A panel.")
    md = gnb.export_project_markdown(db, pid).lower()
    for banned in ("secret_key_sentinel", "comfyui", "image prompt", "img2img"):
        assert banned not in md


# ==========================================================================
# Regression guards
# ==========================================================================


def test_no_image_generation_in_pages_view():
    src = os.path.join(_ROOT, "logosforge", "ui", "graphic_novel_scene_pages_view.py")
    toks = []
    with open(src, "rb") as fh:
        for tok in tokenize.tokenize(fh.readline):
            name = tokenize.tok_name[tok.type]
            if tok.type == tokenize.COMMENT or name.endswith("STRING"):
                continue
            toks.append(tok.string.lower())
    skeleton = " ".join(toks)
    for banned in ("comfyui", "image_generation", "imageprompt", "img2img",
                   "txt2img", "stablediffusion", "canvas"):
        assert banned not in skeleton, banned


def test_building_pages_does_not_mutate_outline_or_timeline():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, content="")
    # Give the scene an Outline summary + a Timeline link.
    sc = db.get_scene_by_id(sid)
    db.update_scene(scene_id=sid, title=sc.title, summary="KEEP_SUMMARY",
                    synopsis=sc.synopsis, goal=sc.goal, conflict=sc.conflict,
                    outcome=sc.outcome, beat=sc.beat, tags=sc.tags, act=sc.act,
                    content=sc.content, chapter=sc.chapter, plotline=sc.plotline)
    db.add_timeline_event(pid, sid)
    tl = db.get_timeline_event_ids(pid)
    v = _view(db, pid)
    v._add_page(); v._add_panel()
    v._set_panel_field(0, 0, "visual_description", "x")
    assert db.get_scene_by_id(sid).summary == "KEEP_SUMMARY"   # Outline untouched
    assert db.get_timeline_event_ids(pid) == tl                 # Timeline untouched
