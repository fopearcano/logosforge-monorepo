"""Graphic Novel Mode — Phase 7 acceptance suite.

Graphic Novel Review Dashboard: a deterministic, read-only project roll-up
(per-scene breakdown/plan/body/health/flow/continuity/Timeline/PSYKE-Notes/export
status in canonical order + summary metrics + next actions), a dashboard view
(cards/table/filters/navigation/copy), and a Logos action. Reporting only — never
mutates, and explicitly no image generation.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge import graphic_novel_pipeline as gp
from logosforge import graphic_novel_dashboard as gnd


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


def _sc(db, pid, title, content, *, act="Act I", chapter="Chapter 1", summary="s"):
    return ss.create_scene(db, pid, act=act, chapter=chapter, title=title,
                           content=content, summary=summary).id


def _two_scene(db):
    """Beta (Act II) first, Alpha (Act I) second -> canonical Alpha, Beta."""
    pid = _gn(db)
    b = ss.create_scene(
        db, pid, act="Act II", chapter="Chapter 2", title="Beta",
        content="PAGE 1\n\nPANEL 1\nVisual: In the lab, Mary works.\n"
                "Dialogue: MARY: Hi.", summary="Beta").id
    a = ss.create_scene(
        db, pid, act="Act I", chapter="Chapter 1", title="Alpha",
        content="PAGE 1\n\nPANEL 1\nVisual: In the kitchen, Maria waits.",
        summary="Alpha").id
    db.reorder_scenes(pid, [a, b])
    return pid, a, b


def _row(rep, title):
    return next(r for r in rep.rows if r.title == title)


# ==========================================================================
# 1-15  Model
# ==========================================================================


def test_report_in_canonical_order():
    db = Database()
    pid, a, b = _two_scene(db)
    rep = gnd.build_graphic_novel_review(db, pid)
    assert [r.scene_id for r in rep.rows] == [a, b]
    assert [r.title for r in rep.rows] == ["Alpha", "Beta"]


def test_counts_total_scenes():
    db = Database()
    pid, a, b = _two_scene(db)
    assert gnd.build_graphic_novel_review(db, pid).total_scenes == 2


def test_counts_total_pages():
    db = Database()
    pid, a, b = _two_scene(db)
    assert gnd.build_graphic_novel_review(db, pid).total_pages == 2


def test_counts_total_panels():
    db = Database()
    pid, a, b = _two_scene(db)
    assert gnd.build_graphic_novel_review(db, pid).total_panels == 2


def test_detects_missing_page_breakdown():
    db = Database()
    pid, a, b = _two_scene(db)
    gp.save_page_breakdown(db, pid, gp.PageBreakdown(scene_id=a, pacing_goal="x"))
    rep = gnd.build_graphic_novel_review(db, pid)
    assert _row(rep, "Alpha").breakdown_status == gnd.ST_OK
    assert _row(rep, "Beta").breakdown_status == gnd.ST_MISSING


def test_detects_missing_panel_plan():
    db = Database()
    pid, a, b = _two_scene(db)
    gp.save_panel_plan(db, pid, gp.PanelPlan(scene_id=a, pages=[gp.PlannedPage(
        number=1, panels=[gp.PlannedPanel(visual_beat="kitchen")])]))
    rep = gnd.build_graphic_novel_review(db, pid)
    assert _row(rep, "Alpha").plan_status == gnd.ST_OK
    assert _row(rep, "Beta").plan_status == gnd.ST_MISSING


def test_detects_missing_body():
    db = Database()
    pid = _gn(db)
    _sc(db, pid, "Empty", "")
    rep = gnd.build_graphic_novel_review(db, pid)
    assert _row(rep, "Empty").body_status == gnd.ST_MISSING


def test_detects_empty_pages():
    db = Database()
    pid = _gn(db)
    _sc(db, pid, "A", "PAGE 1: Intro\nSummary: setup\n\nPAGE 2\n\nPANEL 1\nVisual: x.")
    rep = gnd.build_graphic_novel_review(db, pid)
    assert _row(rep, "A").empty_page_count >= 1 and rep.empty_pages >= 1


def test_detects_empty_panels():
    db = Database()
    pid = _gn(db)
    _sc(db, pid, "A", "PAGE 1\n\nPANEL 1\nVisual: x.\n\nPANEL 2\n")
    rep = gnd.build_graphic_novel_review(db, pid)
    assert _row(rep, "A").empty_panel_count >= 1 and rep.empty_panels >= 1


def test_detects_panels_missing_visual():
    db = Database()
    pid = _gn(db)
    _sc(db, pid, "A", "PAGE 1\n\nPANEL 1\nCaption: a caption only.")
    rep = gnd.build_graphic_novel_review(db, pid)
    assert _row(rep, "A").missing_visual_count >= 1
    assert _row(rep, "A").visuals_status == gnd.ST_WARNING


def test_detects_dialogue_caption_status():
    db = Database()
    pid = _gn(db)
    dh = "Dialogue: BOB: " + " ".join(["talk"] * 40)
    _sc(db, pid, "A", f"PAGE 1\n\nPANEL 1\nVisual: In the room, x.\n{dh}")
    rep = gnd.build_graphic_novel_review(db, pid)
    assert _row(rep, "A").dialogue_heavy_count >= 1
    assert _row(rep, "A").dialogue_caption_status == gnd.ST_WARNING


def test_detects_flow_warnings():
    db = Database()
    pid = _gn(db)
    _sc(db, pid, "A", "PAGE 1\n\nPANEL 1\nCaption: a.\n\nPANEL 2\nCaption: b.")
    rep = gnd.build_graphic_novel_review(db, pid)
    assert _row(rep, "A").flow_status == gnd.ST_WARNING
    assert rep.with_flow_warnings >= 1


def test_continuity_status_field_present():
    db = Database()
    pid, a, b = _two_scene(db)
    rep = gnd.build_graphic_novel_review(db, pid)
    assert all(r.continuity_status in (gnd.ST_OK, gnd.ST_WARNING) for r in rep.rows)


def test_detects_timeline_link():
    db = Database()
    pid, a, b = _two_scene(db)
    db.add_timeline_event(pid, a)
    rep = gnd.build_graphic_novel_review(db, pid)
    assert _row(rep, "Alpha").timeline_status == gnd.ST_OK
    assert _row(rep, "Beta").timeline_status == gnd.ST_MISSING


def test_detects_psyke_notes_status():
    db = Database()
    pid = _gn(db)
    db.create_psyke_entry(pid, "Mary", "character")
    _sc(db, pid, "Linked", "PAGE 1\n\nPANEL 1\nVisual: x.\nDialogue: MARY: Hi.")
    _sc(db, pid, "Unlinked", "PAGE 1\n\nPANEL 1\nVisual: y.\nDialogue: JOHN: Bye.",
        act="Act II", chapter="Chapter 2")
    rep = gnd.build_graphic_novel_review(db, pid)
    assert _row(rep, "Linked").psyke_notes_status == gnd.ST_OK
    assert _row(rep, "Unlinked").psyke_notes_status == gnd.ST_WARNING


# ==========================================================================
# 16-20  Statuses + next action
# ==========================================================================


def test_clean_scene_is_ok_or_warning():
    db = Database()
    pid = _gn(db)
    sid = _sc(db, pid, "Clean",
              "PAGE 1\n\nPANEL 1\nVisual: In the kitchen, Maria slams the door.\n"
              "Dialogue: MARIA: Stop.", summary="clean")
    gp.save_page_breakdown(db, pid, gp.PageBreakdown(scene_id=sid, pacing_goal="x"))
    gp.save_panel_plan(db, pid, gp.PanelPlan(scene_id=sid, pages=[gp.PlannedPage(
        number=1, panels=[gp.PlannedPanel(visual_beat="kitchen")])]))
    r = _row(gnd.build_graphic_novel_review(db, pid), "Clean")
    assert r.body_status == gnd.ST_OK and r.breakdown_status == gnd.ST_OK
    assert r.plan_status == gnd.ST_OK
    assert r.overall_status in (gnd.ST_OK, gnd.ST_WARNING)


def test_no_body_is_needs_work():
    db = Database()
    pid = _gn(db)
    _sc(db, pid, "Empty", "")
    r = _row(gnd.build_graphic_novel_review(db, pid), "Empty")
    assert r.body_status == gnd.ST_MISSING
    assert r.overall_status == gnd.ST_NEEDS_WORK
    assert r.next_action == "Add page breakdown"


def test_missing_visuals_shows_warning():
    db = Database()
    pid = _gn(db)
    _sc(db, pid, "A", "PAGE 1\n\nPANEL 1\nCaption: just a caption.")
    r = _row(gnd.build_graphic_novel_review(db, pid), "A")
    assert r.visuals_status == gnd.ST_WARNING and r.missing_visual_count >= 1


def test_problematic_scene_shows_needs_work():
    db = Database()
    pid = _gn(db)
    _sc(db, pid, "A", "PAGE 1\n\nPANEL 1\nCaption: a.\n\nPANEL 2\nCaption: b.")
    r = _row(gnd.build_graphic_novel_review(db, pid), "A")
    assert r.overall_status in (gnd.ST_WARNING, gnd.ST_NEEDS_WORK)


def test_recommended_next_action_generated():
    db = Database()
    pid, a, b = _two_scene(db)
    rep = gnd.build_graphic_novel_review(db, pid)
    assert all(r.next_action for r in rep.rows)
    assert _row(rep, "Beta").next_action == "Add page breakdown"  # body, no breakdown


# ==========================================================================
# 21-28  UI
# ==========================================================================


def _view(db, pid, **cb):
    from logosforge.ui.graphic_novel_review_view import GraphicNovelReviewView
    return GraphicNovelReviewView(db, pid, **cb)


def test_dashboard_view_opens():
    db = Database()
    pid, a, b = _two_scene(db)
    assert _view(db, pid).objectName() == "graphicNovelReviewView"


def test_summary_cards_shown():
    db = Database()
    pid, a, b = _two_scene(db)
    view = _view(db, pid)
    assert view._cards["Scenes"]._value.text() == "2"
    assert view._cards["Pages"]._value.text() == "2"
    assert set(view._cards) == {"Scenes", "Pages", "Panels", "Planned", "Scripted",
                                "Needs Visuals", "Continuity Risks", "Export Warnings"}


def test_scene_table_shown():
    db = Database()
    pid, a, b = _two_scene(db)
    view = _view(db, pid)
    assert view._table.rowCount() == 2
    assert view._table.item(0, 1).text() == "Alpha"
    assert view._table.item(1, 1).text() == "Beta"


def test_filters_work():
    db = Database()
    pid = _gn(db)
    _sc(db, pid, "Scripted", "PAGE 1\n\nPANEL 1\nVisual: In the room, x.")
    _sc(db, pid, "Empty", "", act="Act II", chapter="Chapter 2")
    view = _view(db, pid)
    view._filter_combo.setCurrentText("Missing Body")
    titles = [view._table.item(i, 1).text() for i in range(view._table.rowCount())]
    assert titles == ["Empty"]
    view._filter_combo.setCurrentText("All")
    assert view._table.rowCount() == 2


def test_open_in_manuscript_selects_correct_scene():
    db = Database()
    pid, a, b = _two_scene(db)
    opened = []
    view = _view(db, pid, on_open_manuscript=lambda s: opened.append(s))
    view._table.selectRow(1)            # Beta
    view._open_manuscript()
    assert opened == [b]


def test_open_in_outline_navigates():
    db = Database()
    pid, a, b = _two_scene(db)
    opened = []
    view = _view(db, pid, on_open_outline=lambda s: opened.append(s))
    view._table.selectRow(0)            # Alpha
    view._open_outline()
    assert opened == [a]


def test_copy_report_produces_markdown():
    db = Database()
    pid, a, b = _two_scene(db)
    view = _view(db, pid)
    md = view.report_markdown()
    assert md.startswith("# Graphic Novel Review")
    assert "| Alpha |" in md and "| Beta |" in md
    view.copy_report()
    assert "Graphic Novel Review" in QApplication.clipboard().text()


# ==========================================================================
# 29-35  Refresh
# ==========================================================================


def test_updating_body_updates_status():
    db = Database()
    pid = _gn(db)
    sid = _sc(db, pid, "S", "")
    view = _view(db, pid)
    assert view._table.item(0, 3 - 1).text() == gnd.ST_MISSING  # Breakdown col (idx 2)
    assert view._cards["Scripted"]._value.text() == "0"
    db.update_scene_content(sid, "PAGE 1\n\nPANEL 1\nVisual: In the room, x.")
    view.refresh()
    assert view._cards["Scripted"]._value.text() == "1"


def test_adding_breakdown_updates_status():
    db = Database()
    pid = _gn(db)
    sid = _sc(db, pid, "S", "PAGE 1\n\nPANEL 1\nVisual: In the room, x.")
    view = _view(db, pid)
    rep1 = gnd.build_graphic_novel_review(db, pid)
    assert _row(rep1, "S").breakdown_status == gnd.ST_MISSING
    gp.save_page_breakdown(db, pid, gp.PageBreakdown(scene_id=sid, pacing_goal="x"))
    view.refresh()
    rep2 = gnd.build_graphic_novel_review(db, pid)
    assert _row(rep2, "S").breakdown_status == gnd.ST_OK


def test_adding_panel_plan_updates_status():
    db = Database()
    pid = _gn(db)
    sid = _sc(db, pid, "S", "PAGE 1\n\nPANEL 1\nVisual: In the room, x.")
    assert _row(gnd.build_graphic_novel_review(db, pid), "S").plan_status == gnd.ST_MISSING
    gp.save_panel_plan(db, pid, gp.PanelPlan(scene_id=sid, pages=[gp.PlannedPage(
        number=1, panels=[gp.PlannedPanel(visual_beat="room")])]))
    assert _row(gnd.build_graphic_novel_review(db, pid), "S").plan_status == gnd.ST_OK


def test_moving_scene_updates_order():
    db = Database()
    pid, a, b = _two_scene(db)
    view = _view(db, pid)
    assert view._table.item(0, 1).text() == "Alpha"
    db.reorder_scenes(pid, [b, a])
    view.refresh()
    assert view._table.item(0, 1).text() == "Beta"


def test_timeline_link_change_updates_status():
    db = Database()
    pid, a, b = _two_scene(db)
    db.add_timeline_event(pid, a)
    assert _row(gnd.build_graphic_novel_review(db, pid), "Alpha").timeline_status == gnd.ST_OK
    db.remove_timeline_event(pid, a)
    rep2 = gnd.build_graphic_novel_review(db, pid)
    assert _row(rep2, "Alpha").timeline_status != gnd.ST_OK   # nothing linked now


def test_notes_link_change_updates_status():
    db = Database()
    pid = _gn(db)
    sid = _sc(db, pid, "S", "PAGE 1\n\nPANEL 1\nVisual: In the room, x.")
    assert _row(gnd.build_graphic_novel_review(db, pid), "S").psyke_notes_status \
        == gnd.ST_NOT_CHECKED
    note = db.create_note(pid, "ctx", "body")
    db.link_note_to_scene(getattr(note, "id", note), sid)
    assert _row(gnd.build_graphic_novel_review(db, pid), "S").psyke_notes_status \
        == gnd.ST_OK


def test_project_switch_via_mainwindow(tmp_path):
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.graphic_novel_review_view import GraphicNovelReviewView
    db = Database(str(tmp_path / "gn.db"))
    a = _gn(db, "ProjA")
    _sc(db, a, "OnlyA", "PAGE 1\n\nPANEL 1\nVisual: In the room, x.")
    b = _gn(db, "ProjB")
    win = MainWindow(db, a)
    win._show_graphic_novel_review()
    assert isinstance(win.content_area, GraphicNovelReviewView)
    assert "OnlyA" in win.content_area.report_markdown()
    win._switch_project(b)
    win._show_graphic_novel_review()
    assert "OnlyA" not in win.content_area.report_markdown()


# ==========================================================================
# 36-41  Safety (no mutation, no secrets)
# ==========================================================================


def test_build_does_not_mutate_manuscript_or_outline():
    db = Database()
    pid = _gn(db)
    sid = _sc(db, pid, "S", "PAGE 1\n\nPANEL 1\nVisual: x.", summary="SUM")
    before = (db.get_scene_by_id(sid).content, db.get_scene_by_id(sid).summary)
    gnd.build_graphic_novel_review(db, pid)
    after = (db.get_scene_by_id(sid).content, db.get_scene_by_id(sid).summary)
    assert before == after


def test_build_does_not_mutate_timeline():
    db = Database()
    pid, a, b = _two_scene(db)
    db.add_timeline_event(pid, a)
    before = db.get_timeline_event_ids(pid)
    gnd.build_graphic_novel_review(db, pid)
    assert db.get_timeline_event_ids(pid) == before


def test_build_does_not_mutate_psyke():
    db = Database()
    pid, a, b = _two_scene(db)
    db.create_psyke_entry(pid, "Bob", "character")
    before = len(db.get_all_psyke_entries(pid))
    gnd.build_graphic_novel_review(db, pid)
    assert len(db.get_all_psyke_entries(pid)) == before == 1


def test_build_does_not_mutate_notes_or_plan():
    db = Database()
    pid, a, b = _two_scene(db)
    db.create_note(pid, "n", "b")
    gp.save_page_breakdown(db, pid, gp.PageBreakdown(scene_id=a, pacing_goal="KEEP"))
    before_notes = len(db.get_all_notes(pid))
    gnd.build_graphic_novel_review(db, pid)
    assert len(db.get_all_notes(pid)) == before_notes
    assert gp.get_page_breakdown(db, pid, a).pacing_goal == "KEEP"


def test_report_excludes_api_keys():
    db = Database()
    from logosforge.settings import get_manager
    get_manager().set("ai_api_key", "SECRET_KEY_SENTINEL")
    pid, a, b = _two_scene(db)
    md = gnd.build_graphic_novel_review(db, pid).to_markdown()
    assert "SECRET_KEY_SENTINEL" not in md


def test_review_isolated_across_projects(tmp_path):
    db = Database(str(tmp_path / "gn.db"))
    a = _gn(db, "A")
    _sc(db, a, "OnlyA", "PAGE 1\n\nPANEL 1\nVisual: x.")
    b = _gn(db, "B")
    rep_b = gnd.build_graphic_novel_review(db, b)
    assert rep_b.total_scenes == 0
    assert not any(r.title == "OnlyA" for r in rep_b.rows)


# ==========================================================================
# 42-45  No image generation
# ==========================================================================


def test_no_image_generation_code_or_actions():
    import os, tokenize
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(here, "logosforge", "graphic_novel_dashboard.py")
    code_tokens = []
    with open(src, "rb") as fh:
        for tok in tokenize.tokenize(fh.readline):
            name = tokenize.tok_name[tok.type]
            if tok.type == tokenize.COMMENT or name.endswith("STRING"):
                continue
            code_tokens.append(tok.string.lower())
    skeleton = " ".join(code_tokens)
    for banned in ("comfyui", "image generation", "image prompt", "lora",
                   "render", "stable diffusion", "img2img", "txt2img"):
        assert banned not in skeleton, banned
    from logosforge.logos import actions as A
    names = " ".join(a.name + " " + a.label for a in A.list_actions()).lower()
    for banned in ("comfyui", "image gen", "generate image", "image prompt"):
        assert banned not in names


def test_no_image_provider_setting_required():
    db = Database()
    pid, a, b = _two_scene(db)
    assert gnd.build_graphic_novel_review(db, pid).to_markdown()


def test_report_mentions_no_render_or_image_workflows():
    db = Database()
    pid, a, b = _two_scene(db)
    md = gnd.build_graphic_novel_review(db, pid).to_markdown().lower()
    for banned in ("comfyui", "image generation", "render", "stable diffusion",
                   "lora", "img2img"):
        assert banned not in md


# ==========================================================================
# Logos action + novel-mode gating
# ==========================================================================


def test_logos_dropdown_includes_review_dashboard():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("G", narrative_engine="graphic_novel")
    ctl = LogosController(db)
    for sec in ("Manuscript", "Timeline", "Outline"):
        names = [a.name for a in ctl.available_actions(sec, writing_mode="graphic_novel")]
        assert "gn_review_dashboard" in names
    novel = [a.name for a in ctl.available_actions("Manuscript", writing_mode="novel")]
    assert "gn_review_dashboard" not in novel


def test_review_action_runs_deterministically():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def _boom(*a, **k):
        raise AssertionError("deterministic action must not call the LLM")

    db = Database()
    pid, a, b = _two_scene(db)
    ctl = LogosController(db, provider_resolver=_boom, chat_fn=_boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=None)
    res = ctl.run(ctx, "gn_review_dashboard")
    assert res.ok and res.title == "Graphic Novel Review Dashboard"
    assert "# Graphic Novel Review" in res.message and res.proposed_operations == []


def test_novel_mode_unaffected():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("Book", narrative_engine="novel")
    for sec in ("Manuscript", "Timeline", "Outline"):
        names = [a.name for a in
                 LogosController(db).available_actions(sec, writing_mode="novel")]
        assert "gn_review_dashboard" not in names
