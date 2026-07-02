"""Screenplay Mode — Phase 8 acceptance suite.

Screenplay Review Dashboard: a deterministic, read-only project roll-up
(per-scene plan/body/health/continuity/Timeline/PSYKE/export status in canonical
order + summary metrics + next actions), a dashboard view (cards/table/filters/
navigation/copy), and a Logos action. Reporting only — never mutates.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge import screenplay_pipeline as spp
from logosforge import screenplay_review as srv


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


def _two_scene(db):
    """Beta (Act II) first, Alpha (Act I) second -> canonical Alpha, Beta."""
    pid = _screenplay(db)
    b = ss.create_scene(db, pid, act="Act II", chapter="Seq 2", title="Beta",
                        content="INT. BETA - DAY\n\nMARY\nHi.", summary="Beta").id
    a = ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="Alpha",
                        content="INT. ALPHA - DAY\n\nAction.", summary="Alpha").id
    db.reorder_scenes(pid, [a, b])
    return pid, a, b


def _row(rep, title):
    return next(r for r in rep.rows if r.title == title)


# ==========================================================================
# 1-10  Model
# ==========================================================================


def test_report_in_canonical_order():
    db = Database()
    pid, a, b = _two_scene(db)
    rep = srv.build_screenplay_review(db, pid)
    assert [r.scene_id for r in rep.rows] == [a, b]
    assert [r.title for r in rep.rows] == ["Alpha", "Beta"]


def test_counts_total_scenes():
    db = Database()
    pid, a, b = _two_scene(db)
    assert srv.build_screenplay_review(db, pid).total_scenes == 2


def test_detects_missing_beat_plan():
    db = Database()
    pid, a, b = _two_scene(db)
    spp.save_beat_plan(db, pid, spp.ScreenplayBeatPlan(scene_id=a, objective="go"))
    rep = srv.build_screenplay_review(db, pid)
    assert _row(rep, "Alpha").beat_plan_status == srv.ST_OK
    assert _row(rep, "Beta").beat_plan_status == srv.ST_MISSING


def test_detects_missing_body():
    db = Database()
    pid = _screenplay(db)
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="Empty", content="")
    rep = srv.build_screenplay_review(db, pid)
    assert _row(rep, "Empty").body_status == srv.ST_MISSING


def test_detects_health_warnings():
    db = Database()
    pid = _screenplay(db)
    # Internal-state action -> a Phase 3 health warning.
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="Weak",
                    content="INT. X - DAY\n\nJohn thinks and remembers and feels and realizes.")
    rep = srv.build_screenplay_review(db, pid)
    assert _row(rep, "Weak").health_status in (srv.ST_WARNING, srv.ST_NEEDS_WORK)
    assert rep.with_health_warnings >= 1


def test_detects_continuity_warnings_field_present():
    db = Database()
    pid, a, b = _two_scene(db)
    rep = srv.build_screenplay_review(db, pid)
    # Continuity status is computed per scene (OK or Warning).
    assert all(r.continuity_status in (srv.ST_OK, srv.ST_WARNING) for r in rep.rows)


def test_detects_export_warnings():
    db = Database()
    pid = _screenplay(db)
    # No scene heading -> export/format warning.
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="NoHead",
                    content="Just an action line, no heading.")
    rep = srv.build_screenplay_review(db, pid)
    assert _row(rep, "NoHead").export_status == srv.ST_WARNING


def test_detects_timeline_link():
    db = Database()
    pid, a, b = _two_scene(db)
    db.add_timeline_event(pid, a)
    rep = srv.build_screenplay_review(db, pid)
    assert _row(rep, "Alpha").timeline_status == srv.ST_OK


def test_detects_missing_timeline_link():
    db = Database()
    pid, a, b = _two_scene(db)
    db.add_timeline_event(pid, a)          # a linked -> b expected but missing
    rep = srv.build_screenplay_review(db, pid)
    assert _row(rep, "Beta").timeline_status == srv.ST_MISSING


def test_detects_psyke_link_status():
    db = Database()
    pid, a, b = _two_scene(db)
    db.create_psyke_entry(pid, "Bob", "character")   # MARY (in Beta) not linked
    rep = srv.build_screenplay_review(db, pid)
    assert _row(rep, "Beta").psyke_status == srv.ST_WARNING


# ==========================================================================
# 11-14  Statuses
# ==========================================================================


def test_clean_scene_is_ok_or_warning_not_needs_work():
    db = Database()
    pid = _screenplay(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="Clean",
                          content="INT. ROOM - DAY\n\nJOHN\nLook out, but then he runs.",
                          summary="clean").id
    spp.save_beat_plan(db, pid, spp.ScreenplayBeatPlan(scene_id=sid, objective="go"))
    rep = srv.build_screenplay_review(db, pid)
    r = _row(rep, "Clean")
    assert r.body_status == srv.ST_OK and r.beat_plan_status == srv.ST_OK
    assert r.overall_status in (srv.ST_OK, srv.ST_WARNING)


def test_no_body_is_needs_work():
    db = Database()
    pid = _screenplay(db)
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="Plan", content="")
    rep = srv.build_screenplay_review(db, pid)
    r = _row(rep, "Plan")
    assert r.body_status == srv.ST_MISSING
    assert r.overall_status == srv.ST_NEEDS_WORK
    assert r.next_action == "Write scene body"


def test_export_warning_shows_warning_status():
    db = Database()
    pid = _screenplay(db)
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="NoHead",
                    content="Action with no heading.")
    rep = srv.build_screenplay_review(db, pid)
    assert _row(rep, "NoHead").export_status == srv.ST_WARNING


def test_recommended_next_action_generated():
    db = Database()
    pid, a, b = _two_scene(db)
    rep = srv.build_screenplay_review(db, pid)
    assert _row(rep, "Beta").next_action == "Add beat plan"   # has body, no plan
    assert all(r.next_action for r in rep.rows)


# ==========================================================================
# 15-21  UI
# ==========================================================================


def _view(db, pid, **cb):
    from logosforge.ui.screenplay_review_view import ScreenplayReviewView
    return ScreenplayReviewView(db, pid, **cb)


def test_dashboard_view_opens():
    db = Database()
    pid, a, b = _two_scene(db)
    view = _view(db, pid)
    assert view.objectName() == "screenplayReviewView"


def test_summary_cards_shown():
    db = Database()
    pid, a, b = _two_scene(db)
    view = _view(db, pid)
    assert view._cards["Total Scenes"]._value.text() == "2"
    assert set(view._cards) == {"Total Scenes", "Written", "Planned",
                                "Needs Work", "Export Warnings", "Continuity Risks"}


def test_scene_table_shown():
    db = Database()
    pid, a, b = _two_scene(db)
    view = _view(db, pid)
    assert view._table.rowCount() == 2
    assert view._table.item(0, 1).text() == "Alpha"
    assert view._table.item(1, 1).text() == "Beta"


def test_filters_work():
    db = Database()
    pid = _screenplay(db)
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="Written",
                    content="INT. X - DAY\n\nAction.")
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="Empty", content="")
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
    assert md.startswith("# Screenplay Review")
    assert "| Alpha |" in md and "| Beta |" in md
    view.copy_report()
    assert "Screenplay Review" in QApplication.clipboard().text()


# ==========================================================================
# 22-26  Refresh
# ==========================================================================


def test_updating_body_updates_status():
    db = Database()
    pid = _screenplay(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="S",
                          content="").id
    view = _view(db, pid)
    assert view._table.item(0, 3).text() == srv.ST_MISSING   # Body column
    db.update_scene_content(sid, "INT. X - DAY\n\nAction.")
    view.refresh()
    assert view._table.item(0, 3).text() == srv.ST_OK


def test_adding_beat_plan_updates_status():
    db = Database()
    pid = _screenplay(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="S",
                          content="INT. X - DAY\n\nAction.").id
    view = _view(db, pid)
    assert view._cards["Planned"]._value.text() == "0"
    spp.save_beat_plan(db, pid, spp.ScreenplayBeatPlan(scene_id=sid, objective="go"))
    view.refresh()
    assert view._cards["Planned"]._value.text() == "1"


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
    view = _view(db, pid)
    assert view._cards["Total Scenes"]._value.text() == "2"
    rep1 = srv.build_screenplay_review(db, pid)
    assert _row(rep1, "Alpha").timeline_status == srv.ST_OK
    db.remove_timeline_event(pid, a)
    view.refresh()
    rep2 = srv.build_screenplay_review(db, pid)
    # No timeline events at all now -> not nagged (Not Checked), not OK.
    assert _row(rep2, "Alpha").timeline_status != srv.ST_OK


def test_project_switch_via_mainwindow(tmp_path):
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.screenplay_review_view import ScreenplayReviewView
    db = Database(str(tmp_path / "sp.db"))
    a = _screenplay(db, "ProjA")
    ss.create_scene(db, a, act="Act I", chapter="Seq 1", title="OnlyA",
                    content="INT. A - DAY\n\nAction.")
    b = _screenplay(db, "ProjB")
    win = MainWindow(db, a)
    win._show_screenplay_review()
    assert isinstance(win.content_area, ScreenplayReviewView)
    md_a = win.content_area.report_markdown()
    assert "OnlyA" in md_a
    win._switch_project(b)
    win._show_screenplay_review()
    assert "OnlyA" not in win.content_area.report_markdown()


# ==========================================================================
# 27-31  Safety (no mutation, no secrets)
# ==========================================================================


def test_build_does_not_mutate_manuscript_or_outline():
    db = Database()
    pid = _screenplay(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="S",
                          content="INT. X - DAY\n\nAction.", summary="SUM").id
    before = (db.get_scene_by_id(sid).content, db.get_scene_by_id(sid).summary)
    srv.build_screenplay_review(db, pid)
    after = (db.get_scene_by_id(sid).content, db.get_scene_by_id(sid).summary)
    assert before == after


def test_build_does_not_mutate_timeline():
    db = Database()
    pid, a, b = _two_scene(db)
    db.add_timeline_event(pid, a)
    before = db.get_timeline_event_ids(pid)
    srv.build_screenplay_review(db, pid)
    assert db.get_timeline_event_ids(pid) == before


def test_build_does_not_mutate_psyke():
    db = Database()
    pid, a, b = _two_scene(db)
    db.create_psyke_entry(pid, "Bob", "character")
    before = len(db.get_all_psyke_entries(pid))
    srv.build_screenplay_review(db, pid)
    assert len(db.get_all_psyke_entries(pid)) == before == 1


def test_build_does_not_mutate_beat_plan():
    db = Database()
    pid, a, b = _two_scene(db)
    spp.save_beat_plan(db, pid, spp.ScreenplayBeatPlan(scene_id=a, objective="KEEP"))
    srv.build_screenplay_review(db, pid)
    assert spp.get_beat_plan(db, pid, a).objective == "KEEP"


def test_report_excludes_api_keys():
    db = Database()
    from logosforge.settings import get_manager
    get_manager().set("ai_api_key", "SECRET_KEY_SENTINEL")
    pid, a, b = _two_scene(db)
    md = srv.build_screenplay_review(db, pid).to_markdown()
    assert "SECRET_KEY_SENTINEL" not in md


def test_review_isolated_across_projects(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    a = _screenplay(db, "A")
    ss.create_scene(db, a, act="Act I", chapter="Seq 1", title="OnlyA",
                    content="INT. A - DAY\n\nAction.")
    b = _screenplay(db, "B")
    rep_b = srv.build_screenplay_review(db, b)
    assert rep_b.total_scenes == 0
    assert not any(r.title == "OnlyA" for r in rep_b.rows)


# ==========================================================================
# Logos action + novel-mode gating
# ==========================================================================


def test_logos_dropdown_includes_review_dashboard():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("S", narrative_engine="screenplay")
    ctl = LogosController(db)
    for sec in ("Manuscript", "Timeline", "Outline"):
        names = [a.name for a in ctl.available_actions(sec, writing_mode="screenplay")]
        assert "sp_review_dashboard" in names
    novel = [a.name for a in ctl.available_actions("Manuscript", writing_mode="novel")]
    assert "sp_review_dashboard" not in novel


def test_review_action_runs_deterministically():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def _boom(*a, **k):
        raise AssertionError("deterministic action must not call the LLM")

    db = Database()
    pid, a, b = _two_scene(db)
    ctl = LogosController(db, provider_resolver=_boom, chat_fn=_boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=None)
    res = ctl.run(ctx, "sp_review_dashboard")
    assert res.ok and res.title == "Screenplay Review Dashboard"
    assert "# Screenplay Review" in res.message and res.proposed_operations == []
