"""Screenplay Mode — Phase 9 integration / integrity suite.

Cross-cutting checks that Phases 1–8 work together as one coherent system and do
not break the rest of Logosforge: a full smoke flow, no-auto-mutation across every
preview/report step, canonical-order coherence (Manuscript/Timeline/Export/
Dashboard), Novel-mode regression, project isolation (A→B→C), export/report
privacy, and UI routing.

Deterministic — no live LLM. "Generation" steps feed text directly into the
deterministic parsers, exactly as the UI would after a provider call.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge import screenplay_pipeline as spp
from logosforge import screenplay_diagnostics as sd
from logosforge import screenplay_reflection as sref
from logosforge import screenplay_continuity as scont
from logosforge import screenplay_rewrite as srw
from logosforge import screenplay_interchange as si
from logosforge import screenplay_review as srev


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


def _screenplay(db, title="S"):
    return db.create_project(title, narrative_engine="screenplay",
                             default_writing_format="screenplay").id


def _novel(db, title="N"):
    return db.create_project(title, narrative_engine="novel").id


_BODY = "INT. KITCHEN - NIGHT\n\nMaria waits.\n\nMARIA\nWhere were you?"
_PLAN_TEXT = ("Objective: get the truth\nConflict: he stonewalls\n"
              "Emotional Shift: hope to dread\nVisual Beats:\n- she blocks the door")
_DRAFT_TEXT = ("INT. KITCHEN - NIGHT\n\nMaria blocks the door.\n\n"
               "MARIA\nThe truth. Now.\n\nJOHN\nNo.")
_RW_TEXT = "INT. KITCHEN - NIGHT\n\nMaria slams the door and turns the lock."


# ==========================================================================
# 1  Full screenplay smoke flow
# ==========================================================================


def test_full_screenplay_smoke_flow():
    db = Database()
    pid = _screenplay(db, "Film")
    sid = ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="Open",
                          content=_BODY, summary="Maria confronts John").id
    original_body = db.get_scene_by_id(sid).content
    original_summary = db.get_scene_by_id(sid).summary

    # Blocks parse (Phase 1).
    from logosforge.screenplay_blocks import parse_screenplay_text
    blocks = parse_screenplay_text(original_body, scene_id=sid)
    assert [b.element_type for b in blocks][:2] == ["scene_heading", "action"]

    # Beat plan: prompt is deterministic, parse + save (separate from body).
    assert "Maria confronts John" in spp.build_beat_plan_prompt(db, pid, sid)
    plan = spp.parse_beat_plan_response(_PLAN_TEXT, scene_id=sid)
    spp.save_beat_plan(db, pid, plan)
    assert db.get_scene_by_id(sid).content == original_body          # body untouched
    assert spp.get_beat_plan(db, pid, sid).objective == "get the truth"

    # Draft from beat plan: preview = NO mutation; apply requires confirmation.
    draft_blocks = spp.parse_draft_blocks(_DRAFT_TEXT, scene_id=sid)
    preview = spp.preview_draft_apply(db, pid, sid, draft_blocks, mode=spp.APPLY_REPLACE)
    assert preview is not None and db.get_scene_by_id(sid).content == original_body
    refused = spp.apply_draft(db, pid, sid, draft_blocks, mode=spp.APPLY_REPLACE,
                              confirmed=False)
    assert refused["ok"] is False and db.get_scene_by_id(sid).content == original_body
    applied = spp.apply_draft(db, pid, sid, draft_blocks, mode=spp.APPLY_REPLACE,
                              confirmed=True)
    assert applied["ok"] and "blocks the door" in db.get_scene_by_id(sid).content
    assert db.get_scene_by_id(sid).summary == original_summary       # outline kept

    body_after_draft = db.get_scene_by_id(sid).content

    # Health check (Phase 3) — non-mutating.
    health = sd.analyze_scene_by_id(db, pid, sid)
    assert health.block_count > 0
    assert db.get_scene_by_id(sid).content == body_after_draft

    # Counterpart reflection (Phase 5) — non-mutating, has both stances.
    refl = sref.build_scene_reflection(db, pid, sid)
    assert refl.characters and refl.snapshot
    assert db.get_scene_by_id(sid).content == body_after_draft

    # Continuity (Phase 7) — non-mutating.
    cont = scont.build_screenplay_continuity_report(db, pid)
    assert cont.scene_chain and db.get_scene_by_id(sid).content == body_after_draft

    # Controlled rewrite (Phase 6): preview + cancel = NO mutation.
    rw_blocks = srw.parse_rewrite_output(_RW_TEXT, scene_id=sid)
    rprev = srw.build_rewrite_preview(db, pid, sid, rw_blocks, target=srw.TARGET_SCENE)
    assert rprev.proposed_text and db.get_scene_by_id(sid).content == body_after_draft
    cancelled = srw.apply_rewrite(db, pid, sid, rw_blocks, mode=srw.MODE_CANCEL,
                                  confirmed=True)
    assert cancelled["ok"] is False and db.get_scene_by_id(sid).content == body_after_draft

    # Fountain export (Phase 4) — body present, summary absent.
    fountain = si.serialize_project_to_fountain(db, pid).text
    assert "blocks the door" in fountain and "Maria confronts John" not in fountain

    # Review dashboard (Phase 8) — written + planned + canonical.
    review = srev.build_screenplay_review(db, pid)
    assert review.total_scenes == 1 and review.written == 1 and review.planned == 1
    assert review.rows[0].scene_id == sid


# ==========================================================================
# 2  No auto-mutation across preview/report steps
# ==========================================================================


def test_reports_and_previews_never_mutate():
    db = Database()
    pid = _screenplay(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="S",
                          content=_BODY, summary="keep").id
    spp.save_beat_plan(db, pid, spp.ScreenplayBeatPlan(scene_id=sid, objective="x"))
    snapshot = (db.get_scene_by_id(sid).content, db.get_scene_by_id(sid).summary,
                spp.get_beat_plan(db, pid, sid).objective,
                len(db.get_all_psyke_entries(pid)), len(db.get_all_notes(pid)))

    sd.analyze_scene_by_id(db, pid, sid)
    sref.build_scene_reflection(db, pid, sid)
    scont.build_screenplay_continuity_report(db, pid)
    srev.build_screenplay_review(db, pid)
    si.validate_fountain_export_readiness(db, pid)
    si.serialize_project_to_fountain(db, pid)
    srw.build_rewrite_preview(db, pid, sid, srw.parse_rewrite_output(_RW_TEXT))
    spp.preview_draft_apply(db, pid, sid, spp.parse_draft_blocks(_DRAFT_TEXT))

    after = (db.get_scene_by_id(sid).content, db.get_scene_by_id(sid).summary,
             spp.get_beat_plan(db, pid, sid).objective,
             len(db.get_all_psyke_entries(pid)), len(db.get_all_notes(pid)))
    assert snapshot == after


# ==========================================================================
# 3  Canonical order coherence (Manuscript / Timeline / Export / Dashboard)
# ==========================================================================


def test_canonical_order_is_consistent_and_updates_on_move():
    db = Database()
    pid = _screenplay(db)
    b = ss.create_scene(db, pid, act="Act II", chapter="Seq 2", title="Beta",
                        content="INT. BETA - DAY\n\nBeta action.").id
    a = ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="Alpha",
                        content="INT. ALPHA - DAY\n\nAlpha action.").id
    db.reorder_scenes(pid, [a, b])

    def order_views():
        canon = ss.canonical_scene_order(db, pid)
        fountain = si.serialize_project_to_fountain(db, pid).text
        dash = [r.scene_id for r in srev.build_screenplay_review(db, pid).rows]
        chain = [e.scene_id for e in
                 scont.build_screenplay_continuity_report(db, pid).scene_chain]
        return canon, fountain, dash, chain

    canon, fountain, dash, chain = order_views()
    assert canon == [a, b] == dash == chain
    assert fountain.index("ALPHA") < fountain.index("BETA")

    # Move Beta before Alpha — every view follows.
    db.reorder_scenes(pid, [b, a])
    canon, fountain, dash, chain = order_views()
    assert canon == [b, a] == dash == chain
    assert fountain.index("BETA") < fountain.index("ALPHA")


# ==========================================================================
# 4  Novel-mode regression — no screenplay leakage
# ==========================================================================


def test_novel_mode_unchanged_by_screenplay_features():
    from logosforge.writing_modes import current_primary_unit_type
    from logosforge.logos.controller import LogosController
    db = Database()
    pid = _novel(db, "Book")
    proj = db.get_project_by_id(pid)
    assert current_primary_unit_type(proj) == "chapter"     # novel unit unchanged

    sid = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="Ch",
                          content="It was a quiet morning. She thought about home.").id
    body = db.get_scene_by_id(sid).content

    # Screenplay Logos actions are mode-gated OFF for Novel.
    names = [a.name for a in
             LogosController(db).available_actions("Manuscript", writing_mode="novel")]
    for screenplay_only in ("sp_scene_health", "sp_counterpart_reflection",
                            "sp_continuity_check", "sp_review_dashboard",
                            "sp_rewrite_from_counterpart", "sp_beat_plan_alignment"):
        assert screenplay_only not in names

    # Beat-plan context + Manuscript editor are not screenplay-ified for Novel.
    assert spp.beat_plan_context(db, pid, sid) == ""
    from logosforge.ui.writing_core_view import WritingCoreView
    view = WritingCoreView(db, pid, structured_list=True)
    editor = next(iter(view._editors.values()))
    assert editor._screenplay_mode is False
    assert db.get_scene_by_id(sid).content == body            # prose untouched


# ==========================================================================
# 5  Project isolation A → B → C
# ==========================================================================


def test_screenplay_data_isolated_across_projects(tmp_path):
    db = Database(str(tmp_path / "iso.db"))
    # Project A: full screenplay data with sentinels.
    a = _screenplay(db, "ProjA")
    sa = ss.create_scene(db, a, act="Act I", chapter="Seq 1", title="A_SCENE",
                         content="INT. A_ONLY - DAY\n\nA_BODY_SENTINEL action.",
                         summary="A_SUMMARY_SENTINEL").id
    spp.save_beat_plan(db, a, spp.ScreenplayBeatPlan(scene_id=sa, objective="A_PLAN_SENTINEL"))
    db.create_psyke_entry(a, "A_CHAR_SENTINEL", "character")
    db.add_timeline_event(a, sa)
    sref.save_reflection_as_note(db, a, sa, sref.build_scene_reflection(db, a, sa),
                                 confirmed=True)

    # Project B: different/empty.
    b = _screenplay(db, "ProjB")
    ss.create_scene(db, b, act="Act I", chapter="Seq 1", title="B_SCENE",
                    content="INT. B_PLACE - DAY\n\nB action.")

    def b_blobs():
        return " ".join([
            si.serialize_project_to_fountain(db, b).text,
            srev.build_screenplay_review(db, b).to_markdown(),
            scont.build_screenplay_continuity_report(db, b).to_text(),
        ])

    blob = b_blobs()
    for sentinel in ("A_ONLY", "A_BODY_SENTINEL", "A_SUMMARY_SENTINEL",
                     "A_PLAN_SENTINEL", "A_CHAR_SENTINEL"):
        assert sentinel not in blob
    assert spp.get_beat_plan(db, b, sa) is None       # A's plan invisible in B
    assert db.get_timeline_event_ids(b) == set()

    # New Project C: no A/B debris.
    c = _screenplay(db, "ProjC")
    assert srev.build_screenplay_review(db, c).total_scenes == 0
    assert spp.all_beat_plans(db, c) == {}
    assert len(db.get_all_notes(c)) == 0

    # Back to A: data intact.
    assert spp.get_beat_plan(db, a, sa).objective == "A_PLAN_SENTINEL"
    assert "A_BODY_SENTINEL" in si.serialize_project_to_fountain(db, a).text


# ==========================================================================
# 6  Export / report privacy
# ==========================================================================


def test_exports_and_reports_exclude_secrets():
    db = Database()
    from logosforge.settings import get_manager
    mgr = get_manager()
    mgr.set("ai_api_key", "SECRET_API_KEY_SENTINEL")
    mgr.set("ai_base_url", "https://secret.example/v1")
    pid = _screenplay(db, "Film")
    sid = ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="S",
                          content=_BODY, summary="s").id
    spp.save_beat_plan(db, pid, spp.ScreenplayBeatPlan(scene_id=sid, objective="x"))

    blobs = [
        si.serialize_project_to_fountain(db, pid).text,
        si.serialize_scene_to_fountain(db, pid, sid).text,
        srev.build_screenplay_review(db, pid).to_markdown(),
        scont.build_screenplay_continuity_report(db, pid).to_text(),
        sref.build_scene_reflection(db, pid, sid).to_text(),
    ]
    for blob in blobs:
        assert "SECRET_API_KEY_SENTINEL" not in blob
        assert "secret.example" not in blob


# ==========================================================================
# 7  UI routing — correct views mount
# ==========================================================================


def test_ui_routing_mounts_correct_views(tmp_path):
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.writing_core_view import WritingCoreView
    from logosforge.ui.plan_view import PlanView
    from logosforge.ui.plot_timeline_view import PlotTimelineView
    from logosforge.ui.screenplay_review_view import ScreenplayReviewView

    db = Database(str(tmp_path / "ui.db"))
    pid = _screenplay(db, "Film")
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="S", content=_BODY)
    win = MainWindow(db, pid)

    win.sidebar_buttons["Manuscript"].click()
    assert isinstance(win.content_area, WritingCoreView)
    win.sidebar_buttons["Outline"].click()
    assert isinstance(win.content_area, PlanView)
    win.sidebar_buttons["Timeline"].click()
    assert isinstance(win.content_area, PlotTimelineView)
    win._show_screenplay_review()
    assert isinstance(win.content_area, ScreenplayReviewView)


def test_review_navigation_round_trip(tmp_path):
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.writing_core_view import WritingCoreView
    db = Database(str(tmp_path / "nav.db"))
    pid = _screenplay(db, "Film")
    sid = ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="S",
                          content=_BODY).id
    win = MainWindow(db, pid)
    win._show_screenplay_review()
    review = win.content_area
    review._table.selectRow(0)
    review._open_manuscript()                # navigates without mutation
    assert isinstance(win.content_area, WritingCoreView)
    assert db.get_scene_by_id(sid).content == _BODY


# ==========================================================================
# 8  Mode + structure invariant remain intact under screenplay flow
# ==========================================================================


def test_structure_invariant_holds_after_screenplay_flow():
    db = Database()
    pid = _screenplay(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="S",
                          content=_BODY).id
    # Apply a rewrite, then confirm every scene still has Act + Chapter parents.
    srw.apply_rewrite(db, pid, sid, srw.parse_rewrite_output(_RW_TEXT),
                      target=srw.TARGET_SCENE, mode=srw.MODE_REPLACE, confirmed=True)
    for scene in db.get_all_scenes(pid):
        assert (scene.act or "").strip() and (scene.chapter or "").strip()
    assert ss.build_structure_tree(db, pid) is not None
