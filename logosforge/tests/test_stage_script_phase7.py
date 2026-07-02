"""Stage Script Mode — Phase 7 acceptance suite.

Stage Script Review Dashboard: a deterministic, read-only project roll-up
(per-scene beat/blocking plan, body, dialogue/stage-action/entrance-exit/cue/
continuity status, Timeline/PSYKE, export readiness + next actions in canonical
order), a dashboard view (cards/table/filters/navigation/copy), and a Logos
action. Reporting only — never mutates.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge import stage_script_pipeline as ssp
from logosforge import stage_script_dashboard as ssd


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


def _sc(db, pid, title, content, *, act="Act I", chapter="Chapter 1", summary="s"):
    return ss.create_scene(db, pid, act=act, chapter=chapter, title=title,
                           content=content, summary=summary).id


def _two_scene(db):
    pid = _stage(db)
    b = ss.create_scene(
        db, pid, act="Act II", chapter="Chapter 2", title="Beta",
        content="STAGE: In the lab, Mary works but then stops.\n\n"
                "CHARACTER: MARY\nI won't.", summary="Beta").id
    a = ss.create_scene(
        db, pid, act="Act I", chapter="Chapter 1", title="Alpha",
        content="STAGE: In the kitchen, Maria waits but then turns.\n\n"
                "CHARACTER: MARIA\nNo.", summary="Alpha").id
    db.reorder_scenes(pid, [a, b])
    return pid, a, b


def _row(rep, title):
    return next(r for r in rep.rows if r.title == title)


# ==========================================================================
# 1-14  Model
# ==========================================================================


def test_report_in_canonical_order():
    db = Database()
    pid, a, b = _two_scene(db)
    rep = ssd.build_stage_script_review(db, pid)
    assert [r.scene_id for r in rep.rows] == [a, b]
    assert [r.title for r in rep.rows] == ["Alpha", "Beta"]


def test_counts_total_scenes():
    db = Database()
    pid, a, b = _two_scene(db)
    assert ssd.build_stage_script_review(db, pid).total_scenes == 2


def test_detects_missing_beat_plan():
    db = Database()
    pid, a, b = _two_scene(db)
    ssp.save_beat_plan(db, pid, ssp.StageBeatPlan(scene_id=a, objective="go"))
    rep = ssd.build_stage_script_review(db, pid)
    assert _row(rep, "Alpha").beat_plan_status == ssd.ST_OK
    assert _row(rep, "Beta").beat_plan_status == ssd.ST_MISSING


def test_detects_missing_blocking_plan():
    db = Database()
    pid, a, b = _two_scene(db)
    ssp.save_blocking_plan(db, pid, ssp.BlockingCuePlan(scene_id=a,
                                                        staging_area_notes="x"))
    rep = ssd.build_stage_script_review(db, pid)
    assert _row(rep, "Alpha").blocking_plan_status == ssd.ST_OK
    assert _row(rep, "Beta").blocking_plan_status == ssd.ST_MISSING


def test_detects_missing_body():
    db = Database()
    pid = _stage(db)
    _sc(db, pid, "Empty", "")
    rep = ssd.build_stage_script_review(db, pid)
    assert _row(rep, "Empty").body_status == ssd.ST_MISSING


def test_counts_stage_blocks():
    db = Database()
    pid, a, b = _two_scene(db)
    assert ssd.build_stage_script_review(db, pid).total_blocks == 6


def test_detects_dialogue_heavy():
    db = Database()
    pid = _stage(db)
    body = "STAGE: A room.\n\nCHARACTER: MARIA\n" + "\n".join(
        f"Line {i}." for i in range(1, 6))
    _sc(db, pid, "Talky", body)
    rep = ssd.build_stage_script_review(db, pid)
    assert _row(rep, "Talky").dialogue_status == ssd.ST_WARNING


def test_detects_missing_stage_action():
    db = Database()
    pid = _stage(db)
    _sc(db, pid, "A", "CHARACTER: MARIA\nHi.\n\nCHARACTER: JOHN\nBye.")
    rep = ssd.build_stage_script_review(db, pid)
    assert _row(rep, "A").stage_action_status == ssd.ST_WARNING


def test_detects_entrance_exit_warning():
    db = Database()
    pid = _stage(db)
    _sc(db, pid, "A", "STAGE: A room.\n\nENTER:")
    rep = ssd.build_stage_script_review(db, pid)
    assert _row(rep, "A").entrance_exit_status == ssd.ST_WARNING


def test_detects_cue_warning():
    db = Database()
    pid = _stage(db)
    _sc(db, pid, "A", "STAGE: A room.\n\nLIGHT:")
    rep = ssd.build_stage_script_review(db, pid)
    assert _row(rep, "A").cue_status == ssd.ST_WARNING


def test_detects_blocking_warning():
    db = Database()
    pid = _stage(db)
    _sc(db, pid, "A", "CHARACTER: MARIA\nHi.\n\nCHARACTER: JOHN\nBye.")
    rep = ssd.build_stage_script_review(db, pid)
    assert _row(rep, "A").blocking_status == ssd.ST_WARNING


def test_detects_continuity_warning():
    db = Database()
    pid = _stage(db)
    _sc(db, pid, "A", "CHARACTER: MARIA\nI leave.\n\nEXIT: Maria exits.\n\n"
        "CHARACTER: MARIA\nWait.")
    rep = ssd.build_stage_script_review(db, pid)
    assert _row(rep, "A").continuity_status == ssd.ST_WARNING


def test_detects_timeline_link():
    db = Database()
    pid, a, b = _two_scene(db)
    db.add_timeline_event(pid, a)
    rep = ssd.build_stage_script_review(db, pid)
    assert _row(rep, "Alpha").timeline_status == ssd.ST_OK
    assert _row(rep, "Beta").timeline_status == ssd.ST_MISSING


def test_detects_psyke_notes_status():
    db = Database()
    pid = _stage(db)
    db.create_psyke_entry(pid, "Mary", "character")
    _sc(db, pid, "Linked", "STAGE: x.\n\nCHARACTER: MARY\nHi.")
    _sc(db, pid, "Unlinked", "STAGE: y.\n\nCHARACTER: JOHN\nBye.",
        act="Act II", chapter="Chapter 2")
    rep = ssd.build_stage_script_review(db, pid)
    assert _row(rep, "Linked").psyke_notes_status == ssd.ST_OK
    assert _row(rep, "Unlinked").psyke_notes_status == ssd.ST_WARNING


# ==========================================================================
# 15-19  Statuses + next action
# ==========================================================================


def test_clean_scene_is_ok_or_warning():
    db = Database()
    pid = _stage(db)
    sid = _sc(db, pid, "Clean",
              "STAGE: In the kitchen, Maria crosses to the window but then turns.\n\n"
              "CHARACTER: MARIA\nI won't go.", summary="clean")
    ssp.save_beat_plan(db, pid, ssp.StageBeatPlan(scene_id=sid, objective="go"))
    ssp.save_blocking_plan(db, pid, ssp.BlockingCuePlan(scene_id=sid,
                                                        staging_area_notes="x"))
    r = _row(ssd.build_stage_script_review(db, pid), "Clean")
    assert r.body_status == ssd.ST_OK and r.beat_plan_status == ssd.ST_OK
    assert r.blocking_plan_status == ssd.ST_OK
    assert r.overall_status in (ssd.ST_OK, ssd.ST_WARNING)


def test_no_body_is_needs_work():
    db = Database()
    pid = _stage(db)
    _sc(db, pid, "Empty", "")
    r = _row(ssd.build_stage_script_review(db, pid), "Empty")
    assert r.body_status == ssd.ST_MISSING
    assert r.overall_status == ssd.ST_NEEDS_WORK
    assert r.next_action == "Add Stage Beat Plan"


def test_cue_warning_shows_warning():
    db = Database()
    pid = _stage(db)
    _sc(db, pid, "A", "STAGE: A room.\n\nLIGHT:")
    r = _row(ssd.build_stage_script_review(db, pid), "A")
    assert r.cue_status == ssd.ST_WARNING
    assert r.overall_status in (ssd.ST_WARNING, ssd.ST_NEEDS_WORK)


def test_continuity_issue_shows_warning():
    db = Database()
    pid = _stage(db)
    _sc(db, pid, "A", "CHARACTER: MARIA\nI leave.\n\nEXIT: Maria exits.\n\n"
        "CHARACTER: MARIA\nWait.")
    r = _row(ssd.build_stage_script_review(db, pid), "A")
    assert r.overall_status in (ssd.ST_WARNING, ssd.ST_NEEDS_WORK)


def test_recommended_next_action_generated():
    db = Database()
    pid, a, b = _two_scene(db)
    rep = ssd.build_stage_script_review(db, pid)
    assert all(r.next_action for r in rep.rows)
    assert _row(rep, "Beta").next_action == "Add Stage Beat Plan"


# ==========================================================================
# 20-27  UI
# ==========================================================================


def _view(db, pid, **cb):
    from logosforge.ui.stage_script_review_view import StageScriptReviewView
    return StageScriptReviewView(db, pid, **cb)


def test_dashboard_view_opens():
    db = Database()
    pid, a, b = _two_scene(db)
    assert _view(db, pid).objectName() == "stageScriptReviewView"


def test_summary_cards_shown():
    db = Database()
    pid, a, b = _two_scene(db)
    view = _view(db, pid)
    assert view._cards["Scenes"]._value.text() == "2"
    assert set(view._cards) == {"Scenes", "Written", "Planned", "Blocking/Cue Plans",
                                "Dialogue Heavy", "Cue Warnings", "Continuity Risks",
                                "Export Warnings"}


def test_scene_table_shown():
    db = Database()
    pid, a, b = _two_scene(db)
    view = _view(db, pid)
    assert view._table.rowCount() == 2
    assert view._table.item(0, 1).text() == "Alpha"
    assert view._table.item(1, 1).text() == "Beta"


def test_filters_work():
    db = Database()
    pid = _stage(db)
    _sc(db, pid, "Written", "STAGE: In the room, action.")
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
    assert md.startswith("# Stage Script Review")
    assert "| Alpha |" in md and "| Beta |" in md
    view.copy_report()
    assert "Stage Script Review" in QApplication.clipboard().text()


# ==========================================================================
# 28-34  Refresh
# ==========================================================================


def test_updating_body_updates_status():
    db = Database()
    pid = _stage(db)
    sid = _sc(db, pid, "S", "")
    view = _view(db, pid)
    assert view._cards["Written"]._value.text() == "0"
    db.update_scene_content(sid, "STAGE: In the room, action.")
    view.refresh()
    assert view._cards["Written"]._value.text() == "1"


def test_adding_beat_plan_updates_status():
    db = Database()
    pid = _stage(db)
    sid = _sc(db, pid, "S", "STAGE: In the room, action.")
    assert _row(ssd.build_stage_script_review(db, pid), "S").beat_plan_status == ssd.ST_MISSING
    ssp.save_beat_plan(db, pid, ssp.StageBeatPlan(scene_id=sid, objective="go"))
    assert _row(ssd.build_stage_script_review(db, pid), "S").beat_plan_status == ssd.ST_OK


def test_adding_blocking_plan_updates_status():
    db = Database()
    pid = _stage(db)
    sid = _sc(db, pid, "S", "STAGE: In the room, action.")
    assert _row(ssd.build_stage_script_review(db, pid), "S").blocking_plan_status \
        == ssd.ST_MISSING
    ssp.save_blocking_plan(db, pid, ssp.BlockingCuePlan(scene_id=sid,
                                                        staging_area_notes="x"))
    assert _row(ssd.build_stage_script_review(db, pid), "S").blocking_plan_status \
        == ssd.ST_OK


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
    assert _row(ssd.build_stage_script_review(db, pid), "Alpha").timeline_status == ssd.ST_OK
    db.remove_timeline_event(pid, a)
    assert _row(ssd.build_stage_script_review(db, pid), "Alpha").timeline_status != ssd.ST_OK


def test_notes_link_change_updates_status():
    db = Database()
    pid = _stage(db)
    sid = _sc(db, pid, "S", "STAGE: In the room, action.")
    assert _row(ssd.build_stage_script_review(db, pid), "S").psyke_notes_status \
        == ssd.ST_NOT_CHECKED
    note = db.create_note(pid, "ctx", "body")
    db.link_note_to_scene(getattr(note, "id", note), sid)
    assert _row(ssd.build_stage_script_review(db, pid), "S").psyke_notes_status == ssd.ST_OK


def test_project_switch_via_mainwindow(tmp_path):
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.stage_script_review_view import StageScriptReviewView
    db = Database(str(tmp_path / "st.db"))
    a = _stage(db, "ProjA")
    _sc(db, a, "OnlyAScene", "STAGE: In the room, action.")
    b = _stage(db, "ProjB")
    win = MainWindow(db, a)
    win._show_stage_script_review()
    assert isinstance(win.content_area, StageScriptReviewView)
    assert "OnlyAScene" in win.content_area.report_markdown()
    win._switch_project(b)
    win._show_stage_script_review()
    assert "OnlyAScene" not in win.content_area.report_markdown()


# ==========================================================================
# 35-40  Safety
# ==========================================================================


def test_build_does_not_mutate_manuscript_or_outline():
    db = Database()
    pid = _stage(db)
    sid = _sc(db, pid, "S", "STAGE: x.", summary="SUM")
    before = (db.get_scene_by_id(sid).content, db.get_scene_by_id(sid).summary)
    ssd.build_stage_script_review(db, pid)
    after = (db.get_scene_by_id(sid).content, db.get_scene_by_id(sid).summary)
    assert before == after


def test_build_does_not_mutate_timeline():
    db = Database()
    pid, a, b = _two_scene(db)
    db.add_timeline_event(pid, a)
    before = db.get_timeline_event_ids(pid)
    ssd.build_stage_script_review(db, pid)
    assert db.get_timeline_event_ids(pid) == before


def test_build_does_not_mutate_psyke():
    db = Database()
    pid, a, b = _two_scene(db)
    db.create_psyke_entry(pid, "Bob", "character")
    before = len(db.get_all_psyke_entries(pid))
    ssd.build_stage_script_review(db, pid)
    assert len(db.get_all_psyke_entries(pid)) == before == 1


def test_build_does_not_mutate_notes_or_plans():
    db = Database()
    pid, a, b = _two_scene(db)
    db.create_note(pid, "n", "b")
    ssp.save_beat_plan(db, pid, ssp.StageBeatPlan(scene_id=a, objective="KEEP"))
    before_notes = len(db.get_all_notes(pid))
    ssd.build_stage_script_review(db, pid)
    assert len(db.get_all_notes(pid)) == before_notes
    assert ssp.get_beat_plan(db, pid, a).objective == "KEEP"


def test_report_excludes_api_keys():
    db = Database()
    from logosforge.settings import get_manager
    get_manager().set("ai_api_key", "SECRET_KEY_SENTINEL")
    pid, a, b = _two_scene(db)
    md = ssd.build_stage_script_review(db, pid).to_markdown()
    assert "SECRET_KEY_SENTINEL" not in md


def test_review_isolated_across_projects(tmp_path):
    db = Database(str(tmp_path / "st.db"))
    a = _stage(db, "A")
    _sc(db, a, "OnlyA", "STAGE: x.")
    b = _stage(db, "B")
    rep_b = ssd.build_stage_script_review(db, b)
    assert rep_b.total_scenes == 0 and not any(r.title == "OnlyA" for r in rep_b.rows)


# ==========================================================================
# Logos action + novel gating
# ==========================================================================


def test_logos_dropdown_includes_review_dashboard():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("ST", narrative_engine="stage_script",
                      default_writing_format="stage_script")
    ctl = LogosController(db)
    for sec in ("Manuscript", "Timeline", "Outline"):
        names = [a.name for a in ctl.available_actions(sec, writing_mode="stage_script")]
        assert "stage_review_dashboard" in names
    novel = [a.name for a in ctl.available_actions("Manuscript", writing_mode="novel")]
    assert "stage_review_dashboard" not in novel


def test_review_action_runs_deterministically():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def _boom(*a, **k):
        raise AssertionError("deterministic action must not call the LLM")

    db = Database()
    pid, a, b = _two_scene(db)
    ctl = LogosController(db, provider_resolver=_boom, chat_fn=_boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=None)
    res = ctl.run(ctx, "stage_review_dashboard")
    assert res.ok and res.title == "Stage Script Review Dashboard"
    assert "# Stage Script Review" in res.message and res.proposed_operations == []
