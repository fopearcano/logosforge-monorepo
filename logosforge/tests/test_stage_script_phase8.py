"""Stage Script Mode — Phase 8 integration / integrity audit suite.

End-to-end verification that the Stage Script phases work together as one writing
system and don't break the rest of Logosforge. No new features — this exercises
the existing Phase 1-7 surfaces: smoke flow, no-auto-mutation, canonical order,
Novel/Screenplay/Graphic Novel regression, project isolation, export/report
privacy, no image-generation / production-management scope creep, and UI routing.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge import stage_script_blocks as ssb
from logosforge import stage_script_pipeline as ssp
from logosforge import stage_script_diagnostics as ssd
from logosforge import stage_script_reflection as ssr
from logosforge import stage_script_rewrite as srw
from logosforge import stage_script_continuity as ssc
from logosforge import stage_script_dashboard as ssdash

_STAGE_MODULES = (
    "stage_script_blocks", "stage_script_pipeline", "stage_script_diagnostics",
    "stage_script_reflection", "stage_script_rewrite", "stage_script_continuity",
    "stage_script_dashboard", "ui/stage_script_review_view",
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


def _stage(db, title="ST"):
    return db.create_project(title, narrative_engine="stage_script",
                             default_writing_format="stage_script").id


def _scene(db, pid, title, content="", *, act="Act I", chapter="Chapter 1",
           summary="s"):
    return ss.create_scene(db, pid, act=act, chapter=chapter, title=title,
                           content=content, summary=summary).id


# ==========================================================================
# 1  Full Stage Script smoke flow
# ==========================================================================


def test_full_stage_script_smoke_flow():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, "Confrontation", "", summary="Maria confronts John")
    assert db.get_scene_by_id(sid).content == ""

    # Beat plan + blocking/cue plan (stored separately; not body).
    ssp.save_beat_plan(db, pid, ssp.StageBeatPlan(
        scene_id=sid, objective="get John to leave", conflict="he refuses"))
    ssp.save_blocking_plan(db, pid, ssp.BlockingCuePlan(
        scene_id=sid, staging_area_notes="thrust stage", lighting_cues=["dim"]))
    assert db.get_scene_by_id(sid).content == ""

    # Draft from plan -> preview (no mutation) then confirmed apply.
    draft = ssb.parse_stage_script_text(
        "SCENE: Throne Room\n\nSTAGE: A bare hall. Maria turns from the window "
        "but stops.\n\nCHARACTER: MARIA\nIt ends now.\n\nCHARACTER: JOHN\nNo.")
    prev = ssp.preview_draft_apply(db, pid, sid, draft, mode=ssp.APPLY_TO_EMPTY)
    assert prev is not None and db.get_scene_by_id(sid).content == ""   # preview only
    res = ssp.apply_draft(db, pid, sid, draft, mode=ssp.APPLY_TO_EMPTY, confirmed=True)
    assert res["ok"]
    body = db.get_scene_by_id(sid).content
    assert "It ends now" in body

    # Health check (deterministic; no mutation).
    health = ssd.analyze_scene_by_id(db, pid, sid)
    assert health.character_count == 2 and db.get_scene_by_id(sid).content == body

    # Counterpart reflection (non-mutating; multi-perspective).
    refl = ssr.build_scene_reflection(db, pid, sid)
    assert ssr.SEC_AUDIENCE in refl.to_text() and ssr.SEC_DRAMATURG in refl.to_text()
    assert db.get_scene_by_id(sid).content == body

    # Controlled rewrite -> preview, then cancel (no mutation).
    rprev = srw.build_rewrite_preview(db, pid, sid, "STAGE: Maria slams the door.",
                                      target=srw.TARGET_BLOCK, target_block_indices=[1])
    assert "slams the door" in rprev.proposed_text
    assert db.get_scene_by_id(sid).content == body
    cancel = srw.apply_rewrite(db, pid, sid, "STAGE: Maria slams the door.",
                               target=srw.TARGET_BLOCK, target_block_indices=[1],
                               mode=srw.MODE_CANCEL, confirmed=True)
    assert cancel["ok"] is False and db.get_scene_by_id(sid).content == body

    # Export + continuity + dashboard.
    md = ssb.export_project_markdown(db, pid)
    assert "It ends now" in md
    cont = ssc.build_stage_script_continuity_report(db, pid)
    assert cont.scene_chain and cont.scene_chain[0].scene_id == sid
    review = ssdash.build_stage_script_review(db, pid)
    assert review.written == 1 and review.with_beat_plan == 1


# ==========================================================================
# 2  No auto-mutation
# ==========================================================================


def test_previews_and_reports_do_not_mutate_body():
    db = Database()
    pid = _stage(db)
    body = "STAGE: In the office, Maria reads.\n\nCHARACTER: MARIA\nHello."
    sid = _scene(db, pid, "S", body, summary="keep")
    ssp.save_beat_plan(db, pid, ssp.StageBeatPlan(scene_id=sid, objective="x"))
    before = (db.get_scene_by_id(sid).content, db.get_scene_by_id(sid).summary)

    ssd.analyze_scene_by_id(db, pid, sid)
    ssr.build_scene_reflection(db, pid, sid)
    ssc.build_stage_script_continuity_report(db, pid)
    ssdash.build_stage_script_review(db, pid)
    srw.build_rewrite_preview(db, pid, sid, "STAGE: A new beat.",
                              target=srw.TARGET_BLOCK, target_block_indices=[0])
    srw.apply_rewrite(db, pid, sid, "STAGE: A new beat.", target=srw.TARGET_SCENE,
                      mode=srw.MODE_REPLACE, confirmed=False)  # unconfirmed -> blocked

    after = (db.get_scene_by_id(sid).content, db.get_scene_by_id(sid).summary)
    assert before == after


# ==========================================================================
# 3  Canonical order across surfaces
# ==========================================================================


def test_canonical_order_across_surfaces():
    db = Database()
    pid = _stage(db)
    b = _scene(db, pid, "Beta", "STAGE: Beta room.", act="Act II", chapter="Chapter 2")
    a = _scene(db, pid, "Alpha", "STAGE: Alpha room.", act="Act I", chapter="Chapter 1")
    db.reorder_scenes(pid, [a, b])

    assert [r.title for r in ssdash.build_stage_script_review(db, pid).rows] == \
        ["Alpha", "Beta"]
    assert [e.title for e in
            ssc.build_stage_script_continuity_report(db, pid).scene_chain] == \
        ["Alpha", "Beta"]
    md = ssb.export_project_markdown(db, pid)
    assert md.index("Alpha room") < md.index("Beta room")

    db.reorder_scenes(pid, [b, a])
    assert [r.title for r in ssdash.build_stage_script_review(db, pid).rows] == \
        ["Beta", "Alpha"]


# ==========================================================================
# 4-6  Novel / Screenplay / Graphic Novel regression
# ==========================================================================


def test_novel_mode_unaffected():
    from logosforge.logos.controller import LogosController
    db = Database()
    pid = db.create_project("Book", narrative_engine="novel").id
    sid = _scene(db, pid, "Ch1", "Plain prose paragraph.", chapter="Chapter 1")
    ssdash.build_stage_script_review(db, pid)            # building doesn't touch novel
    assert db.get_scene_by_id(sid).content == "Plain prose paragraph."
    names = [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="novel")]
    assert not any(n.startswith("stage_") for n in names)


def test_screenplay_mode_unaffected():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("Film", narrative_engine="screenplay",
                      default_writing_format="screenplay")
    names = [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="screenplay")]
    assert "sp_review_dashboard" in names and "sp_continuity_check" in names
    assert not any(n.startswith("stage_") for n in names)


def test_graphic_novel_mode_unaffected():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("GN", narrative_engine="graphic_novel",
                      default_writing_format="graphic_novel")
    names = [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="graphic_novel")]
    assert "gn_review_dashboard" in names and "gn_continuity_check" in names
    assert not any(n.startswith("stage_") for n in names)


# ==========================================================================
# 7  Project isolation
# ==========================================================================


def test_stage_isolation_across_projects(tmp_path):
    db = Database(str(tmp_path / "st.db"))
    a = _stage(db, "A")
    sid_a = _scene(db, a, "SentinelA",
                   "STAGE: AAA_SENTINEL in the hall.\n\nCHARACTER: MARIA\nHi.")
    ssp.save_beat_plan(db, a, ssp.StageBeatPlan(scene_id=sid_a, objective="AAA"))
    db.create_psyke_entry(a, "Alice", "character")
    b = _stage(db, "B")

    rev_b = ssdash.build_stage_script_review(db, b)
    assert rev_b.total_scenes == 0
    assert "AAA_SENTINEL" not in ssb.export_project_markdown(db, b)
    cont_b = ssc.build_stage_script_continuity_report(db, b)
    assert cont_b.scene_chain == []
    assert "ALICE" not in " ".join(f.title for f in cont_b.psyke_notes).upper()
    assert ssp.get_beat_plan(db, b, sid_a) is None     # A's plan not visible in B

    rev_a = ssdash.build_stage_script_review(db, a)
    assert rev_a.total_scenes == 1
    assert "AAA_SENTINEL" in ssb.export_project_markdown(db, a)


# ==========================================================================
# 8  Privacy
# ==========================================================================


def test_exports_and_reports_exclude_secrets():
    db = Database()
    from logosforge.settings import get_manager
    get_manager().set("ai_api_key", "SECRET_KEY_SENTINEL")
    pid = _stage(db)
    _scene(db, pid, "S", "STAGE: In the room, action.\n\nCHARACTER: MARIA\nHi.")
    for text in (ssb.export_project_markdown(db, pid),
                 ssdash.build_stage_script_review(db, pid).to_markdown(),
                 ssc.build_stage_script_continuity_report(db, pid).to_text()):
        assert "SECRET_KEY_SENTINEL" not in text


# ==========================================================================
# 9  No scope creep (image generation + production management)
# ==========================================================================


def test_no_image_generation_or_production_scope():
    import os, tokenize
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    banned = ("comfyui", "image generation", "image prompt", "lora", "render",
              "stable diffusion", "img2img", "txt2img", "rehearsal",
              "production schedule", "lighting board", "stage diagram")
    for mod in _STAGE_MODULES:
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
    # No image-gen / production Logos actions in the whole registry.
    from logosforge.logos import actions as A
    names = " ".join(a.name + " " + a.label for a in A.list_actions()).lower()
    for b in ("comfyui", "image gen", "generate image", "image prompt",
              "rehearsal schedule", "lighting board", "stage diagram",
              "production schedule"):
        assert b not in names


# ==========================================================================
# 10  UI routing
# ==========================================================================


def test_ui_routing_mounts_correct_views(tmp_path):
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.writing_core_view import WritingCoreView
    from logosforge.ui.stage_script_review_view import StageScriptReviewView
    from logosforge.ui.plot_timeline_view import PlotTimelineView
    db = Database(str(tmp_path / "st.db"))
    pid = _stage(db, "STUI")
    _scene(db, pid, "S", "STAGE: In the room, action.")
    win = MainWindow(db, pid)

    win._show_manuscript()
    assert isinstance(win.content_area, WritingCoreView)
    assert win.content_area.on_open_review == win._show_stage_script_review

    win._show_timeline()
    assert isinstance(win.content_area, PlotTimelineView)

    win._show_stage_script_review()
    assert isinstance(win.content_area, StageScriptReviewView)


def test_writing_mode_identification():
    from logosforge.writing_modes import get_project_writing_mode_by_id, STAGE_SCRIPT
    db = Database()
    st = _stage(db, "G")
    nv = db.create_project("N", narrative_engine="novel").id
    assert get_project_writing_mode_by_id(db, st) == STAGE_SCRIPT
    assert get_project_writing_mode_by_id(db, nv) != STAGE_SCRIPT
