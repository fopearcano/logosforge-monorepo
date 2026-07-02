"""Series Mode — Phase 7 acceptance suite.

Series Review Dashboard: a deterministic, read-only project-level status roll-up
across Season / Arc -> Episode -> Scene (canonical order), with summary cards, a
scene-centric status table, filters, navigation, and copy/save-as-note. Building
the report never mutates story data; the single write is the confirmed Save-as-Note.
No image generation.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge import series_pipeline as spp
from logosforge import series_dashboard as sdash


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


def _series(db, title="SR"):
    return db.create_project(title, narrative_engine="series",
                             default_writing_format="series").id


def _scene(db, pid, content="", *, title="S", summary="s", act="Act I",
           chapter="Episode 1"):
    return ss.create_scene(db, pid, act=act, chapter=chapter, title=title,
                           content=content, summary=summary).id


def _report(db, pid):
    return sdash.build_series_review(db, pid)


def _view(db, pid, **cb):
    from logosforge.ui.series_review_view import SeriesReviewView
    return SeriesReviewView(db, pid, **cb)


def _two_scene(db):
    pid = _series(db)
    a = _scene(db, pid, content="INT. A - DAY\n\nAlpha action.\n\nMARIA\nHi.",
               title="Alpha", act="Act I", chapter="Episode 1")
    b = _scene(db, pid, content="INT. B - DAY\n\nBeta action.", title="Beta",
               act="Act I", chapter="Episode 2")
    db.reorder_scenes(pid, [a, b])
    return pid, a, b


# ==========================================================================
# 1-16  Dashboard model
# ==========================================================================


def test_report_in_canonical_order():
    db = Database()
    pid = _series(db)
    b = _scene(db, pid, content="INT. B - DAY\n\nb.", title="Beta", chapter="Episode 2")
    a = _scene(db, pid, content="INT. A - DAY\n\na.", title="Alpha", chapter="Episode 1")
    db.reorder_scenes(pid, [a, b])
    rep = _report(db, pid)
    assert [r.title for r in rep.scenes] == ["Alpha", "Beta"]
    assert [e.episode_label for e in rep.episodes] == ["Episode 1", "Episode 2"]


def test_counts_total_seasons():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="x", act="Act I", chapter="Episode 1")
    _scene(db, pid, content="x", act="Act II", chapter="Episode 2")
    assert _report(db, pid).total_seasons == 2


def test_counts_total_episodes():
    db = Database()
    pid, a, b = _two_scene(db)
    assert _report(db, pid).total_episodes == 2


def test_counts_total_scenes():
    db = Database()
    pid, a, b = _two_scene(db)
    assert _report(db, pid).total_scenes == 2


def test_detects_missing_season_plan():
    db = Database()
    pid, a, b = _two_scene(db)
    rep = _report(db, pid)
    assert any(s.season_plan_status == sdash.ST_MISSING for s in rep.seasons)


def test_detects_missing_episode_plan():
    db = Database()
    pid, a, b = _two_scene(db)
    rep = _report(db, pid)
    assert any(e.episode_plan_status == sdash.ST_MISSING for e in rep.episodes)


def test_detects_missing_scene_body():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="", chapter="Episode 1")
    rep = _report(db, pid)
    assert any(r.body_status == sdash.ST_MISSING for r in rep.scenes)


def test_counts_series_blocks():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nAction.\n\nMARIA\nHi.", chapter="Episode 1")
    assert _report(db, pid).total_blocks >= 3


def test_detects_missing_scene_heading():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="Maria runs.\n\nMARIA\nGo.", chapter="Episode 1")
    rep = _report(db, pid)
    assert rep.missing_scene_heading >= 1


def test_detects_dialogue_heavy():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content=(
        "INT. X - DAY\n\nAction beat.\n\n"
        "MARIA\nLine one here.\nLine two here.\nLine three here.\nLine four here."),
        chapter="Episode 1")
    assert _report(db, pid).dialogue_heavy >= 1


def test_detects_abc_warning():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nMaria waters plants.", chapter="Episode 1")
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(
        chapter="Episode 1", a_story="the bank heist downtown"))
    assert _report(db, pid).episodes_with_abc_warning >= 1


def test_detects_act_break_warning():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nA beat.", chapter="Episode 1")
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(
        chapter="Episode 1", act_breaks=["end of act one"], climax="c"))
    assert _report(db, pid).episodes_with_act_break_warning >= 1


def test_detects_cold_open_tag_warning():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nA beat.", chapter="Episode 1")
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(
        chapter="Episode 1", teaser_or_cold_open="a cold open", climax="c"))
    assert _report(db, pid).episodes_with_cold_open_tag_warning >= 1


def test_detects_continuity_warning():
    db = Database()
    pid = _series(db)
    a = _scene(db, pid, content="INT. A - DAY\n\na.", chapter="Episode 1")
    _scene(db, pid, content="INT. B - DAY\n\nb.", chapter="Episode 2")
    db.add_timeline_event(pid, a)   # Episode 2 unlinked -> continuity/timeline gap
    assert _report(db, pid).episodes_with_continuity_warning >= 1


def test_detects_timeline_link_status():
    db = Database()
    pid = _series(db)
    a = _scene(db, pid, content="INT. A - DAY\n\na.", chapter="Episode 1")
    db.add_timeline_event(pid, a)
    rep = _report(db, pid)
    assert rep.scenes_timeline_linked >= 1
    assert any(r.timeline_status == sdash.ST_OK for r in rep.scenes)


def test_detects_psyke_notes_status():
    db = Database()
    pid = _series(db)
    db.create_psyke_entry(pid, "Maria", "character")
    _scene(db, pid, content="INT. X - DAY\n\nJOHN\nHi.", chapter="Episode 1")
    rep = _report(db, pid)
    assert any(r.psyke_notes_status == sdash.ST_WARNING for r in rep.scenes)


# ==========================================================================
# 17-21  Statuses
# ==========================================================================


def test_clean_episode_is_ok():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nMaria wants out, but suddenly it turns.",
           chapter="Episode 1")
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(
        chapter="Episode 1", episode_premise="a premise", climax="the fall"))
    rep = _report(db, pid)
    ep = next(e for e in rep.episodes if e.chapter == "Episode 1")
    assert ep.overall_status == sdash.ST_OK


def test_episode_no_scenes_is_needs_work():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="", chapter="Episode 1")
    rep = _report(db, pid)
    ep = next(e for e in rep.episodes if e.chapter == "Episode 1")
    assert ep.overall_status == sdash.ST_NEEDS_WORK


def test_scene_missing_heading_shows_warning():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="Maria runs.\n\nMARIA\nGo.", chapter="Episode 1")
    rep = _report(db, pid)
    assert rep.scenes[0].scene_function_status == sdash.ST_WARNING


def test_episode_abc_issue_shows_warning():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nMaria waters plants.", chapter="Episode 1")
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(
        chapter="Episode 1", a_story="the unrelated bank heist"))
    rep = _report(db, pid)
    ep = next(e for e in rep.episodes if e.chapter == "Episode 1")
    assert ep.abc_status == sdash.ST_WARNING and ep.overall_status == sdash.ST_NEEDS_WORK


def test_recommended_next_action_generated():
    db = Database()
    pid, a, b = _two_scene(db)
    rep = _report(db, pid)
    assert all(r.next_action for r in rep.scenes)


# ==========================================================================
# 22-30  UI
# ==========================================================================


def test_dashboard_view_opens():
    db = Database()
    pid, a, b = _two_scene(db)
    assert _view(db, pid).objectName() == "seriesReviewView"


def test_summary_cards_shown():
    db = Database()
    pid, a, b = _two_scene(db)
    view = _view(db, pid)
    assert view._cards["Scenes"]._value.text() == "2"
    assert set(view._cards) == {"Seasons", "Episodes", "Scenes", "Written", "Planned",
                                "A/B/C Warnings", "Continuity Risks", "Export Warnings"}


def test_scene_table_shown():
    db = Database()
    pid, a, b = _two_scene(db)
    view = _view(db, pid)
    assert view._table.rowCount() == 2
    assert "Alpha" in view._table.item(0, 1).text()
    assert "Beta" in view._table.item(1, 1).text()


def test_filters_work():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nWritten.", title="Written",
           chapter="Episode 1")
    _scene(db, pid, content="", title="Empty", act="Act I", chapter="Episode 2")
    view = _view(db, pid)
    view._filter_combo.setCurrentText("Missing Scene Body")
    titles = [view._table.item(i, 1).text() for i in range(view._table.rowCount())]
    assert all("Empty" in t for t in titles) and len(titles) == 1
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


def test_open_in_manuscript_passes_scene_for_block_selection():
    db = Database()
    pid, a, b = _two_scene(db)
    opened = []
    view = _view(db, pid, on_open_manuscript=lambda s: opened.append(s))
    view._table.selectRow(0)            # Alpha
    view._open_manuscript()
    assert opened == [a]                 # scene id drives Manuscript scroll/selection


def test_open_in_outline_navigates():
    db = Database()
    pid, a, b = _two_scene(db)
    opened = []
    view = _view(db, pid, on_open_outline=lambda s: opened.append(s))
    view._table.selectRow(0)
    view._open_outline()
    assert opened == [a]


def test_open_in_timeline_navigates():
    db = Database()
    pid, a, b = _two_scene(db)
    opened = []
    view = _view(db, pid, on_open_timeline=lambda s: opened.append(s))
    view._table.selectRow(1)
    view._open_timeline()
    assert opened == [b]


def test_copy_report_produces_markdown():
    db = Database()
    pid, a, b = _two_scene(db)
    view = _view(db, pid)
    md = view.report_markdown()
    assert md.startswith("# Series Review")
    assert "Alpha" in md and "Beta" in md
    view.copy_report()
    assert "Series Review" in QApplication.clipboard().text()


# ==========================================================================
# 31-38  Refresh
# ==========================================================================


def test_updating_body_updates_status():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content="", chapter="Episode 1")
    view = _view(db, pid)
    assert view._report.scenes[0].body_status == sdash.ST_MISSING
    db.update_scene_content(sid, "INT. X - DAY\n\nNow written.")
    view.refresh()
    assert view._report.scenes[0].body_status == sdash.ST_OK


def test_adding_season_plan_updates_status():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nx.", act="Act I", chapter="Episode 1")
    view = _view(db, pid)
    assert view._report.seasons[0].season_plan_status == sdash.ST_MISSING
    spp.save_season_plan(db, pid, spp.SeasonArcPlan(act="Act I", premise="p"))
    view.refresh()
    assert view._report.seasons[0].season_plan_status == sdash.ST_OK


def test_adding_episode_plan_updates_status():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nx.", chapter="Episode 1")
    view = _view(db, pid)
    assert view._report.episodes[0].episode_plan_status == sdash.ST_MISSING
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(chapter="Episode 1", a_story="a"))
    view.refresh()
    assert view._report.episodes[0].episode_plan_status == sdash.ST_OK


def test_moving_episode_updates_order():
    db = Database()
    pid, a, b = _two_scene(db)
    rep1 = _report(db, pid)
    assert [e.episode_label for e in rep1.episodes] == ["Episode 1", "Episode 2"]
    db.reorder_scenes(pid, [b, a])
    rep2 = _report(db, pid)
    assert [e.episode_label for e in rep2.episodes] == ["Episode 2", "Episode 1"]


def test_moving_scene_updates_order_numbering():
    db = Database()
    pid, a, b = _two_scene(db)
    db.reorder_scenes(pid, [b, a])
    rep = _report(db, pid)
    assert [r.title for r in rep.scenes] == ["Beta", "Alpha"]


def test_timeline_link_change_updates_status():
    db = Database()
    pid = _series(db)
    a = _scene(db, pid, content="INT. A - DAY\n\na.", chapter="Episode 1")
    view = _view(db, pid)
    db.add_timeline_event(pid, a)
    view.refresh()
    assert view._report.scenes_timeline_linked >= 1


def test_notes_link_change_updates_status():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content="INT. X - DAY\n\nx.", chapter="Episode 1")
    view = _view(db, pid)
    before = view._report.scenes_with_notes
    note = db.create_note(pid, "n", "b")
    db.link_note_to_scene(getattr(note, "id", note), sid)
    view.refresh()
    assert view._report.scenes_with_notes == before + 1


def test_project_switch_clears_data(tmp_path):
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.series_review_view import SeriesReviewView
    db = Database(str(tmp_path / "sr.db"))
    a = _series(db, "ProjA")
    _scene(db, a, content="INT. A - DAY\n\nOnlyAScene action.", title="OnlyAScene")
    b = _series(db, "ProjB")
    win = MainWindow(db, a)
    win._show_series_review()
    assert isinstance(win.content_area, SeriesReviewView)
    assert "OnlyAScene" in win.content_area.report_markdown()
    win._switch_project(b)
    win._show_series_review()
    assert "OnlyAScene" not in win.content_area.report_markdown()


# ==========================================================================
# 39-45  Safety
# ==========================================================================


def test_build_does_not_mutate_manuscript_or_outline():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content="INT. X - DAY\n\nx.", summary="SUM", chapter="Episode 1")
    before = (db.get_scene_by_id(sid).content, db.get_scene_by_id(sid).summary)
    _report(db, pid)
    after = (db.get_scene_by_id(sid).content, db.get_scene_by_id(sid).summary)
    assert before == after


def test_build_does_not_mutate_timeline():
    db = Database()
    pid = _series(db)
    a = _scene(db, pid, content="INT. A - DAY\n\na.", chapter="Episode 1")
    db.add_timeline_event(pid, a)
    before = db.get_timeline_event_ids(pid)
    _report(db, pid)
    assert db.get_timeline_event_ids(pid) == before


def test_build_does_not_mutate_psyke():
    db = Database()
    pid = _series(db)
    db.create_psyke_entry(pid, "Maria", "character")
    _scene(db, pid, content="INT. X - DAY\n\nMARIA\nHi.", chapter="Episode 1")
    before = len(db.get_all_psyke_entries(pid))
    _report(db, pid)
    assert len(db.get_all_psyke_entries(pid)) == before == 1


def test_build_does_not_mutate_notes_or_plans():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content="INT. X - DAY\n\nx.", act="Act I", chapter="Episode 1")
    db.create_note(pid, "n", "b")
    spp.save_season_plan(db, pid, spp.SeasonArcPlan(act="Act I", premise="KEEP_S"))
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(chapter="Episode 1", a_story="KEEP_E"))
    before_notes = len(db.get_all_notes(pid))
    _report(db, pid)
    assert len(db.get_all_notes(pid)) == before_notes
    assert spp.get_season_plan(db, pid, "Act I").premise == "KEEP_S"
    assert spp.get_episode_plan(db, pid, "Episode 1").a_story == "KEEP_E"


def test_report_excludes_api_keys():
    db = Database()
    from logosforge.settings import get_manager
    get_manager().set("ai_api_key", "SECRET_KEY_SENTINEL")
    pid, a, b = _two_scene(db)
    md = _report(db, pid).to_markdown()
    assert "SECRET_KEY_SENTINEL" not in md


def test_no_new_storage_keys_created():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nx.", chapter="Episode 1")
    before = set(db.get_project_settings(pid).keys())
    _report(db, pid)
    assert set(db.get_project_settings(pid).keys()) == before


# ==========================================================================
# Logos + regression guards
# ==========================================================================


def test_logos_includes_review_dashboard():
    from logosforge.logos.controller import LogosController
    db = Database()
    _series(db)
    for section in ("Manuscript", "Outline", "Timeline"):
        names = [x.name for x in LogosController(db).available_actions(
            section, writing_mode="series")]
        assert "series_review_dashboard" in names


def test_review_action_runs_deterministically():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def _boom(*a, **k):
        raise AssertionError("dashboard must not call the LLM")

    db = Database()
    pid, a, b = _two_scene(db)
    ctl = LogosController(db, provider_resolver=_boom, chat_fn=_boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript")
    res = ctl.run(ctx, "series_review_dashboard")
    assert res.ok and res.proposed_operations == [] and "Series Review" in res.message


def test_review_isolated_across_projects(tmp_path):
    db = Database(str(tmp_path / "sr.db"))
    a = _series(db, "A")
    _scene(db, a, content="INT. A - DAY\n\nOnlyA action.", title="OnlyA")
    b = _series(db, "B")
    assert _report(db, b).total_scenes == 0
    assert "OnlyA" not in _report(db, b).to_markdown()


def test_no_image_generation_in_dashboard():
    import os, tokenize
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for rel in ("logosforge/series_dashboard.py",
                "logosforge/ui/series_review_view.py"):
        toks = []
        with open(os.path.join(here, rel), "rb") as fh:
            for tok in tokenize.tokenize(fh.readline):
                name = tokenize.tok_name[tok.type]
                if tok.type == tokenize.COMMENT or name.endswith("STRING"):
                    continue
                toks.append(tok.string.lower())
        skeleton = " ".join(toks)
        for banned in ("comfyui", "image generation", "image prompt", "lora",
                       "stable diffusion", "img2img", "txt2img"):
            assert banned not in skeleton, f"{banned} in {rel}"


def test_review_action_absent_from_other_modes():
    from logosforge.logos.controller import LogosController
    db = Database()
    for engine in ("novel", "screenplay", "graphic_novel", "stage_script"):
        db.create_project(engine, narrative_engine=engine,
                          default_writing_format=engine)
        names = [x.name for x in LogosController(db).available_actions(
            "Manuscript", writing_mode=engine)]
        assert not any(n.startswith("series_") for n in names)
