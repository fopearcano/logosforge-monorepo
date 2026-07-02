"""Graphic Novel Mode — Phase 8 integration / integrity audit suite.

End-to-end verification that the Graphic Novel phases work together as one
writing system and don't break the rest of Logosforge. No new features — this
exercises the existing Phase 1-7 surfaces: smoke flow, no-auto-mutation,
canonical order across surfaces, Novel/Screenplay regression, project isolation,
export/report privacy, no image-generation scope creep, and UI routing.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge import graphic_novel_blocks as gnb
from logosforge import graphic_novel_pipeline as gp
from logosforge import graphic_novel_diagnostics as gd
from logosforge import graphic_novel_reflection as gr
from logosforge import graphic_novel_rewrite as grw
from logosforge import graphic_novel_continuity as grc
from logosforge import graphic_novel_dashboard as gnd

# Authored Phase 1-7 modules (the universal-Manuscript scene-script surface).
_GN_MODULES = (
    "graphic_novel_blocks", "graphic_novel_pipeline", "graphic_novel_diagnostics",
    "graphic_novel_reflection", "graphic_novel_rewrite", "graphic_novel_continuity",
    "graphic_novel_dashboard",
)


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


def _scene(db, pid, title, content="", *, act="Act I", chapter="Chapter 1",
           summary="s"):
    return ss.create_scene(db, pid, act=act, chapter=chapter, title=title,
                           content=content, summary=summary).id


# ==========================================================================
# 1  Full Graphic Novel smoke flow
# ==========================================================================


def test_full_graphic_novel_smoke_flow():
    db = Database()
    pid = _gn(db)
    # Act -> Chapter -> Scene with an Outline intent but an empty body.
    sid = _scene(db, pid, "Confrontation", "", summary="Maria confronts John")
    assert db.get_scene_by_id(sid).content == ""

    # Page breakdown (stored separately; does not become body).
    gp.save_page_breakdown(db, pid, gp.PageBreakdown(
        scene_id=sid, target_page_count=1, pacing_goal="build tension"))
    assert db.get_scene_by_id(sid).content == ""

    # Panel plan (stored separately).
    gp.save_panel_plan(db, pid, gp.PanelPlan(scene_id=sid, pages=[gp.PlannedPage(
        number=1, panels=[gp.PlannedPanel(visual_beat="Maria at the window")])]))
    assert db.get_scene_by_id(sid).content == ""

    # Draft panels from the plan -> preview (no mutation) then confirmed apply.
    draft = gnb.parse_graphic_novel_text(
        "PAGE 1\n\nPANEL 1\nVisual: INT. kitchen. Maria turns from the window.\n"
        "Dialogue: MARIA: It ends now.\n\nPANEL 2\nVisual: John steps back but "
        "refuses to move.\nDialogue: JOHN: No.")
    prev = gp.preview_draft_apply(db, pid, sid, draft, mode=gp.APPLY_TO_EMPTY)
    assert prev is not None and db.get_scene_by_id(sid).content == ""   # preview only
    res = gp.apply_draft(db, pid, sid, draft, mode=gp.APPLY_TO_EMPTY, confirmed=True)
    assert res["ok"]
    body = db.get_scene_by_id(sid).content
    assert "Maria turns from the window" in body and "PANEL 2" in body

    # Health check (deterministic; no mutation).
    health = gd.analyze_scene_by_id(db, pid, sid)
    assert health.total_panels == 2 and db.get_scene_by_id(sid).content == body

    # Counterpart reflection (non-mutating; multi-perspective).
    refl = gr.build_scene_reflection(db, pid, sid)
    assert gr.SEC_READER in refl.to_text() and gr.SEC_ARTIST in refl.to_text()
    assert db.get_scene_by_id(sid).content == body

    # Controlled rewrite -> preview, then cancel (no mutation).
    new_panel = "Visual: Maria hurls the glass at the wall.\nSFX: CRASH"
    rprev = grw.build_rewrite_preview(db, pid, sid, new_panel,
                                      target=grw.TARGET_PANEL, target_page=1,
                                      target_panel=1)
    assert "hurls the glass" in rprev.proposed_text
    assert db.get_scene_by_id(sid).content == body                      # preview only
    cancel = grw.apply_rewrite(db, pid, sid, new_panel, target=grw.TARGET_PANEL,
                               target_page=1, target_panel=1,
                               mode=grw.MODE_CANCEL, confirmed=True)
    assert cancel["ok"] is False and db.get_scene_by_id(sid).content == body

    # Export (canonical order; body only) + dashboard.
    md = gnb.export_project_markdown(db, pid)
    assert "Maria turns from the window" in md
    review = gnd.build_graphic_novel_review(db, pid)
    assert review.scripted == 1 and review.total_panels == 2
    cont = grc.build_graphic_novel_continuity_report(db, pid)
    assert cont.scene_chain and cont.scene_chain[0].scene_id == sid


# ==========================================================================
# 2  No auto-mutation: previews/reports never touch the body
# ==========================================================================


def test_previews_and_reports_do_not_mutate_body():
    db = Database()
    pid = _gn(db)
    body = "PAGE 1\n\nPANEL 1\nVisual: In the office, Maria reads."
    sid = _scene(db, pid, "S", body, summary="keep")
    gp.save_page_breakdown(db, pid, gp.PageBreakdown(scene_id=sid, pacing_goal="x"))
    before = (db.get_scene_by_id(sid).content, db.get_scene_by_id(sid).summary)

    gd.analyze_scene_by_id(db, pid, sid)
    gr.build_scene_reflection(db, pid, sid)
    grc.build_graphic_novel_continuity_report(db, pid)
    gnd.build_graphic_novel_review(db, pid)
    grw.build_rewrite_preview(db, pid, sid, "Visual: A new beat.",
                              target=grw.TARGET_PANEL, target_page=1, target_panel=1)
    grw.apply_rewrite(db, pid, sid, "Visual: A new beat.", target=grw.TARGET_SCENE,
                      mode=grw.MODE_REPLACE, confirmed=False)  # unconfirmed -> blocked

    after = (db.get_scene_by_id(sid).content, db.get_scene_by_id(sid).summary)
    assert before == after


# ==========================================================================
# 3  Canonical order across surfaces (move a scene -> all reflect it)
# ==========================================================================


def test_canonical_order_across_surfaces():
    db = Database()
    pid = _gn(db)
    b = _scene(db, pid, "Beta", "PAGE 1\n\nPANEL 1\nVisual: lab.",
               act="Act II", chapter="Chapter 2")
    a = _scene(db, pid, "Alpha", "PAGE 1\n\nPANEL 1\nVisual: kitchen.",
               act="Act I", chapter="Chapter 1")
    db.reorder_scenes(pid, [a, b])

    assert [r.title for r in gnd.build_graphic_novel_review(db, pid).rows] == \
        ["Alpha", "Beta"]
    assert [e.title for e in
            grc.build_graphic_novel_continuity_report(db, pid).scene_chain] == \
        ["Alpha", "Beta"]
    md = gnb.export_project_markdown(db, pid)
    assert md.index("kitchen") < md.index("lab")          # Alpha before Beta

    db.reorder_scenes(pid, [b, a])
    assert [r.title for r in gnd.build_graphic_novel_review(db, pid).rows] == \
        ["Beta", "Alpha"]
    md2 = gnb.export_project_markdown(db, pid)
    assert md2.index("lab") < md2.index("kitchen")        # Beta before Alpha now


# ==========================================================================
# 4-5  Novel + Screenplay regression
# ==========================================================================


def test_novel_mode_unaffected_by_graphic_novel():
    from logosforge.logos.controller import LogosController
    db = Database()
    pid = db.create_project("Book", narrative_engine="novel").id
    sid = _scene(db, pid, "Ch1", "Plain prose paragraph.", chapter="Chapter 1")
    # Novel body is untouched by GN report builders.
    gnd.build_graphic_novel_review(db, pid)
    assert db.get_scene_by_id(sid).content == "Plain prose paragraph."
    names = [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="novel")]
    assert not any(n.startswith("gn_") for n in names)


def test_screenplay_mode_unaffected_by_graphic_novel():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("Film", narrative_engine="screenplay",
                      default_writing_format="screenplay")
    names = [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="screenplay")]
    assert "sp_review_dashboard" in names and "sp_continuity_check" in names
    assert not any(n.startswith("gn_") for n in names)


# ==========================================================================
# 6  Project isolation across all GN surfaces
# ==========================================================================


def test_graphic_novel_isolation_across_projects(tmp_path):
    db = Database(str(tmp_path / "gn.db"))
    a = _gn(db, "A")
    sid_a = _scene(db, a, "SentinelA",
                   "PAGE 1\n\nPANEL 1\nVisual: AAA_SENTINEL in the room.")
    gp.save_page_breakdown(db, a, gp.PageBreakdown(scene_id=sid_a, pacing_goal="AAA"))
    db.create_psyke_entry(a, "Alice", "character")
    b = _gn(db, "B")

    # Project B sees none of A.
    rev_b = gnd.build_graphic_novel_review(db, b)
    assert rev_b.total_scenes == 0
    assert "AAA_SENTINEL" not in gnb.export_project_markdown(db, b)
    cont_b = grc.build_graphic_novel_continuity_report(db, b)
    assert cont_b.scene_chain == []
    assert "ALICE" not in " ".join(f.title for f in cont_b.psyke_notes).upper()

    # Project A still intact.
    rev_a = gnd.build_graphic_novel_review(db, a)
    assert rev_a.total_scenes == 1
    assert "AAA_SENTINEL" in gnb.export_project_markdown(db, a)


# ==========================================================================
# 7  Privacy: exports/reports exclude secrets; no image-generation anywhere
# ==========================================================================


def test_exports_and_reports_exclude_secrets():
    db = Database()
    from logosforge.settings import get_manager
    get_manager().set("ai_api_key", "SECRET_KEY_SENTINEL")
    pid = _gn(db)
    sid = _scene(db, pid, "S", "PAGE 1\n\nPANEL 1\nVisual: In the room, x.")
    for text in (gnb.export_project_markdown(db, pid),
                 gnd.build_graphic_novel_review(db, pid).to_markdown(),
                 grc.build_graphic_novel_continuity_report(db, pid).to_text()):
        assert "SECRET_KEY_SENTINEL" not in text


def test_no_image_generation_across_all_gn_modules():
    import os, tokenize
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    banned = ("comfyui", "image generation", "image prompt", "lora", "render",
              "stable diffusion", "img2img", "txt2img", "diffusion model")
    for mod in _GN_MODULES + ("ui/graphic_novel_review_view",):
        src = os.path.join(here, "logosforge", *(mod.split("/"))) + ".py"
        toks = []
        with open(src, "rb") as fh:
            for tok in tokenize.tokenize(fh.readline):
                name = tokenize.tok_name[tok.type]
                if tok.type == tokenize.COMMENT or name.endswith("STRING"):
                    continue
                toks.append(tok.string.lower())
        skel = " ".join(toks)
        for b in banned:
            assert b not in skel, f"{mod}: {b}"
    # No image-generation Logos actions in the whole registry.
    from logosforge.logos import actions as A
    names = " ".join(a.name + " " + a.label for a in A.list_actions()).lower()
    for b in ("comfyui", "image gen", "generate image", "image prompt", "lora",
              "img2img", "txt2img", "render image"):
        assert b not in names


def test_no_image_generation_in_gn_reports_text():
    db = Database()
    pid = _gn(db)
    _scene(db, pid, "S", "PAGE 1\n\nPANEL 1\nVisual: In the room, Maria waits.\n"
           "Dialogue: MARIA: Hi.")
    texts = [
        gnb.export_project_markdown(db, pid).lower(),
        gnd.build_graphic_novel_review(db, pid).to_markdown().lower(),
        grc.build_graphic_novel_continuity_report(db, pid).to_text().lower(),
        gr.build_scene_reflection(db, pid, db.get_all_scenes(pid)[0].id).to_text().lower(),
    ]
    for t in texts:
        for b in ("comfyui", "image generation", "stable diffusion", "img2img",
                  "lora", "render workflow"):
            assert b not in t


# ==========================================================================
# 8  UI routing: correct views mount; review is mode-aware
# ==========================================================================


def test_ui_routing_mounts_correct_views(tmp_path):
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.graphic_novel_manuscript_view import (
        GraphicNovelManuscriptView)
    from logosforge.ui.graphic_novel_review_view import GraphicNovelReviewView
    from logosforge.ui.plot_timeline_view import PlotTimelineView
    db = Database(str(tmp_path / "gn.db"))
    pid = _gn(db, "GNUI")
    _scene(db, pid, "S", "PAGE 1\n\nPANEL 1\nVisual: In the room, x.")
    win = MainWindow(db, pid)

    # GN Manuscript now mounts the SHARED editor family (the legacy
    # GraphicNovelManuscriptView is no longer routed); standalone Pages
    # stays disabled for fullscreen safety.
    from logosforge.ui.writing_core_view import WritingCoreView
    win._show_manuscript()
    assert isinstance(win.content_area, WritingCoreView)
    assert not isinstance(win.content_area, GraphicNovelManuscriptView)

    win._show_timeline()
    assert isinstance(win.content_area, PlotTimelineView)

    # The GN Review Dashboard is still reachable directly.
    win._show_graphic_novel_review()
    assert isinstance(win.content_area, GraphicNovelReviewView)


def test_review_hook_is_screenplay_for_screenplay_project(tmp_path):
    from logosforge.ui.main_window import MainWindow
    db = Database(str(tmp_path / "sp.db"))
    pid = db.create_project("Film", narrative_engine="screenplay",
                            default_writing_format="screenplay").id
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="S",
                    content="INT. X - DAY\n\nAction.")
    win = MainWindow(db, pid)
    win._show_manuscript()
    assert win.content_area.on_open_review == win._show_screenplay_review


# ==========================================================================
# 9  Mode identification (Assistant/Logos context)
# ==========================================================================


def test_writing_mode_identification():
    from logosforge.writing_modes import get_project_writing_mode_by_id, GRAPHIC_NOVEL
    db = Database()
    gn = _gn(db, "G")
    nv = db.create_project("N", narrative_engine="novel").id
    sp = db.create_project("S", narrative_engine="screenplay",
                           default_writing_format="screenplay").id
    assert get_project_writing_mode_by_id(db, gn) == GRAPHIC_NOVEL
    assert get_project_writing_mode_by_id(db, nv) != GRAPHIC_NOVEL
    assert get_project_writing_mode_by_id(db, sp) != GRAPHIC_NOVEL
