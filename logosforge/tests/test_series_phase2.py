"""Series Mode — Phase 2 acceptance suite.

Series planning pipeline: Outline Act / Episode / Scene summaries -> Season / Arc
Plan -> Episode Beat Plan -> Series scene draft preview -> confirmed apply. Plans
are stored separately from the body (project settings, Act-/Chapter-name keyed —
no Season/Episode storage hierarchy); the AI never overwrites the Manuscript —
apply requires confirmation, touches only Scene.content, and preserves Outline
summaries / plans / Timeline / PSYKE / Notes. No image generation.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge import series_blocks as sbk
from logosforge import series_pipeline as spp


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
           chapter="Chapter 1"):
    return ss.create_scene(db, pid, act=act, chapter=chapter, title=title,
                           content=content, summary=summary).id


def _set_act_summary(db, pid, act, text):
    s = db.get_project_settings(pid)
    d = dict(s.get("act_summaries", {}) or {})
    d[act] = text
    s["act_summaries"] = d
    db.save_project_settings(pid, s)


def _set_chapter_summary(db, pid, chapter, text):
    s = db.get_project_settings(pid)
    d = dict(s.get("chapter_summaries", {}) or {})
    d[chapter] = text
    s["chapter_summaries"] = d
    db.save_project_settings(pid, s)


_DRAFT = (
    "INT. THRONE ROOM - NIGHT\n\n"
    "Maria opens the door slowly.\n\n"
    "MARIA\n(softly)\nIt ends now.\n\n"
    "CUT TO:\n\n"
    "TAG"
)


# ==========================================================================
# 1-6  Season / Arc Plan
# ==========================================================================


def test_season_prompt_uses_act_and_episode_summaries():
    db = Database()
    pid = _series(db)
    _scene(db, pid, act="Act I", chapter="Episode 1")
    _scene(db, pid, title="S2", act="Act I", chapter="Episode 2")
    _set_act_summary(db, pid, "Act I", "ACT_SUMMARY_SENTINEL")
    _set_chapter_summary(db, pid, "Episode 1", "EP1_SENTINEL")
    _set_chapter_summary(db, pid, "Episode 2", "EP2_SENTINEL")
    prompt = spp.build_season_plan_prompt(db, pid, "Act I")
    assert "ACT_SUMMARY_SENTINEL" in prompt
    assert "EP1_SENTINEL" in prompt and "EP2_SENTINEL" in prompt
    assert "Episode 1" in prompt and "Episode 2" in prompt   # Chapter shown as Episode


def test_season_plan_stored_separately_from_body():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content="INT. X - DAY\n\nKEEP body.", act="Act I")
    spp.save_season_plan(db, pid, spp.SeasonArcPlan(act="Act I", premise="rise & fall"))
    assert db.get_scene_by_id(sid).content == "INT. X - DAY\n\nKEEP body."
    assert spp.get_season_plan(db, pid, "Act I").premise == "rise & fall"


def test_accept_season_plan_stores_it():
    db = Database()
    pid = _series(db)
    _scene(db, pid, act="Act I")
    plan = spp.parse_season_plan_response(
        "Premise: a kingdom unravels\nArc Question: who will rule?\n"
        "Episode Progression:\n- pilot\n- midpoint\n- finale", act="Act I")
    spp.save_season_plan(db, pid, plan)
    got = spp.get_season_plan(db, pid, "Act I")
    assert got.premise == "a kingdom unravels" and len(got.episode_progression) == 3


def test_discard_season_plan_changes_nothing():
    db = Database()
    pid = _series(db)
    _scene(db, pid, act="Act I")
    spp.parse_season_plan_response("Premise: x", act="Act I")   # not saved
    assert spp.get_season_plan(db, pid, "Act I") is None
    assert spp.has_season_plan(db, pid, "Act I") is False


def test_season_plan_project_bound():
    db = Database()
    a = _series(db, "A")
    _scene(db, a, act="Act I")
    b = _series(db, "B")
    _scene(db, b, act="Act I")
    spp.save_season_plan(db, a, spp.SeasonArcPlan(act="Act I", premise="A only"))
    assert spp.get_season_plan(db, a, "Act I").premise == "A only"
    assert spp.get_season_plan(db, b, "Act I") is None         # same act name, no leak


def test_season_plan_isolation_across_projects(tmp_path):
    db = Database(str(tmp_path / "sr.db"))
    a = _series(db, "A")
    _scene(db, a, act="Act I")
    spp.save_season_plan(db, a, spp.SeasonArcPlan(act="Act I", premise="SENTINEL_A"))
    b = _series(db, "B")
    assert spp.get_season_plan(db, b, "Act I") is None         # project switch: no leak


# ==========================================================================
# 7-12  Episode Beat Plan
# ==========================================================================


def test_episode_prompt_uses_parent_season_plan():
    db = Database()
    pid = _series(db)
    _scene(db, pid, act="Act I", chapter="Chapter 1")
    spp.save_season_plan(db, pid, spp.SeasonArcPlan(act="Act I",
                                                    premise="SEASON_SENTINEL"))
    prompt = spp.build_episode_plan_prompt(db, pid, "Chapter 1")
    assert "SEASON_SENTINEL" in prompt


def test_episode_prompt_uses_chapter_summary():
    db = Database()
    pid = _series(db)
    _scene(db, pid, act="Act I", chapter="Episode 1", summary="scene-level")
    _set_chapter_summary(db, pid, "Episode 1", "EP_SUMMARY_SENTINEL")
    prompt = spp.build_episode_plan_prompt(db, pid, "Episode 1")
    assert "EP_SUMMARY_SENTINEL" in prompt and "Episode 1" in prompt


def test_episode_plan_stored_separately_from_body():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content="INT. X - DAY\n\nKEEP.", chapter="Chapter 1")
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(chapter="Chapter 1",
                                                       a_story="the heist"))
    assert db.get_scene_by_id(sid).content == "INT. X - DAY\n\nKEEP."
    assert spp.get_episode_plan(db, pid, "Chapter 1").a_story == "the heist"


def test_accept_episode_plan_stores_it():
    db = Database()
    pid = _series(db)
    _scene(db, pid, chapter="Chapter 1")
    plan = spp.parse_episode_plan_response(
        "Premise: the long night\nA Story: the siege\nB Story: the betrayal\n"
        "Act Breaks:\n- end of act one\n- end of act two\nClimax: the gate falls",
        chapter="Chapter 1")
    spp.save_episode_plan(db, pid, plan)
    got = spp.get_episode_plan(db, pid, "Chapter 1")
    assert got.a_story == "the siege" and got.b_story == "the betrayal"
    assert len(got.act_breaks) == 2 and got.climax == "the gate falls"


def test_discard_episode_plan_changes_nothing():
    db = Database()
    pid = _series(db)
    _scene(db, pid, chapter="Chapter 1")
    spp.parse_episode_plan_response("Premise: x", chapter="Chapter 1")   # not saved
    assert spp.get_episode_plan(db, pid, "Chapter 1") is None


def test_episode_plan_project_bound():
    db = Database()
    a = _series(db, "A")
    _scene(db, a, chapter="Chapter 1")
    b = _series(db, "B")
    spp.save_episode_plan(db, a, spp.EpisodeBeatPlan(chapter="Chapter 1",
                                                     episode_premise="A ep"))
    assert spp.get_episode_plan(db, a, "Chapter 1").episode_premise == "A ep"
    assert spp.get_episode_plan(db, b, "Chapter 1") is None


# ==========================================================================
# 13-17  Draft preview
# ==========================================================================


def test_draft_returns_valid_block_list():
    script = spp.parse_draft_response(_DRAFT)
    kinds = {b.block_type for b in script.blocks}
    assert {sbk.BT_SCENE_HEADING, sbk.BT_ACTION, sbk.BT_CHARACTER,
            sbk.BT_DIALOGUE, sbk.BT_TRANSITION} <= kinds
    assert spp.validate_draft_series_script(script).is_valid


def test_draft_preview_does_not_auto_apply():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content="")
    prev = spp.preview_draft_apply(db, pid, sid, spp.parse_draft_response(_DRAFT),
                                   mode=spp.APPLY_TO_EMPTY)
    assert prev is not None
    assert db.get_scene_by_id(sid).content == ""               # preview only


def test_invalid_block_structure_is_rejected():
    # Empty draft is invalid.
    assert spp.validate_draft_series_script(spp.parse_draft_response("")).is_valid is False
    # A non-empty script with an empty required block is invalid.
    script = sbk.SeriesScript()
    sbk.add_block(script, sbk.BT_SCENE_HEADING, "INT. X - DAY")
    sbk.add_block(script, sbk.BT_DIALOGUE, "")
    v = spp.validate_draft_series_script(script)
    assert v.is_valid is False and any("no text" in e.lower() for e in v.errors)


def test_provider_error_does_not_mutate():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content="INT. KEEP - DAY\n\nExisting.")
    res = spp.apply_draft(db, pid, sid, spp.parse_draft_response(""),
                          mode=spp.APPLY_REPLACE, confirmed=True)
    assert res["ok"] is False
    assert db.get_scene_by_id(sid).content == "INT. KEEP - DAY\n\nExisting."


def test_markdown_fences_are_cleaned():
    script = spp.parse_draft_response("```\nINT. ROOM - DAY\n\nAction line.\n```")
    assert spp.validate_draft_series_script(script).is_valid
    assert "```" not in sbk.serialize_series_script(script)


def test_system_prompt_leakage_is_rejected():
    script = spp.parse_draft_response(
        "As an AI language model, here is the scene you requested.")
    assert spp.validate_draft_series_script(script).is_valid is False


# ==========================================================================
# 18-27  Controlled apply
# ==========================================================================


def test_apply_to_empty_writes_blocks():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content="")
    res = spp.apply_draft(db, pid, sid, spp.parse_draft_response(_DRAFT),
                          mode=spp.APPLY_TO_EMPTY, confirmed=True)
    assert res["ok"]
    body = db.get_scene_by_id(sid).content
    assert "THRONE ROOM" in body and "It ends now" in body


def test_replace_requires_confirmation():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content="INT. ORIGINAL - DAY\n\nKeep me.")
    res = spp.apply_draft(db, pid, sid, spp.parse_draft_response(_DRAFT),
                          mode=spp.APPLY_REPLACE, confirmed=False)
    assert res["ok"] is False
    assert db.get_scene_by_id(sid).content == "INT. ORIGINAL - DAY\n\nKeep me."


def test_cancel_leaves_body_unchanged():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content="INT. ORIGINAL - DAY\n\nKeep me.")
    res = spp.apply_draft(db, pid, sid, spp.parse_draft_response(_DRAFT),
                          mode=spp.APPLY_CANCEL, confirmed=True)
    assert res.get("cancelled")
    assert db.get_scene_by_id(sid).content == "INT. ORIGINAL - DAY\n\nKeep me."


def test_append_preserves_existing_body():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content="INT. OPENING - DAY\n\nAn original opening beat.")
    res = spp.apply_draft(db, pid, sid, spp.parse_draft_response(_DRAFT),
                          mode=spp.APPLY_APPEND, confirmed=True)
    assert res["ok"]
    body = db.get_scene_by_id(sid).content
    assert "original opening beat" in body and "It ends now" in body


def test_apply_marks_dirty_and_refreshes():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content="")
    from logosforge.project_events import get_event_bus
    fired = []
    get_event_bus().project_data_changed.connect(lambda *a: fired.append(1))
    spp.apply_draft(db, pid, sid, spp.parse_draft_response(_DRAFT),
                    mode=spp.APPLY_TO_EMPTY, confirmed=True)
    assert fired     # project_data_changed drives the Manuscript refresh


def test_apply_preserves_outline_summary():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content="", summary="SUMMARY_KEPT")
    spp.apply_draft(db, pid, sid, spp.parse_draft_response(_DRAFT),
                    mode=spp.APPLY_TO_EMPTY, confirmed=True)
    assert db.get_scene_by_id(sid).summary == "SUMMARY_KEPT"


def test_apply_preserves_plans_timeline_psyke_notes():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content="", act="Act I", chapter="Chapter 1")
    spp.save_season_plan(db, pid, spp.SeasonArcPlan(act="Act I", premise="KEEP_S"))
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(chapter="Chapter 1",
                                                       a_story="KEEP_E"))
    db.add_timeline_event(pid, sid)
    db.create_psyke_entry(pid, "Maria", "character")
    db.create_note(pid, "n", "b")
    tl_before = db.get_timeline_event_ids(pid)
    psyke_before = len(db.get_all_psyke_entries(pid))
    notes_before = len(db.get_all_notes(pid))
    spp.apply_draft(db, pid, sid, spp.parse_draft_response(_DRAFT),
                    mode=spp.APPLY_TO_EMPTY, confirmed=True)
    assert spp.get_season_plan(db, pid, "Act I").premise == "KEEP_S"
    assert spp.get_episode_plan(db, pid, "Chapter 1").a_story == "KEEP_E"
    assert db.get_timeline_event_ids(pid) == tl_before
    assert len(db.get_all_psyke_entries(pid)) == psyke_before
    assert len(db.get_all_notes(pid)) == notes_before


# ==========================================================================
# 28-33  Validation
# ==========================================================================


def test_dialogue_without_character_warning():
    v = spp.validate_draft_series_script(spp.parse_draft_response(
        "INT. X - DAY\n\nA line with no speaker before it.\n\nAnother line."))
    # The Phase 1 validator's structural warnings flow through the draft validator.
    script = sbk.SeriesScript()
    sbk.add_block(script, sbk.BT_SCENE_HEADING, "INT. X - DAY")
    sbk.add_block(script, sbk.BT_DIALOGUE, "A line with no speaker.")
    v = spp.validate_draft_series_script(script)
    assert any("no preceding character" in w.lower() for w in v.warnings)


def test_missing_scene_heading_warning():
    v = spp.validate_draft_series_script(spp.parse_draft_response(
        "Maria opens the door.\n\nMARIA\nHi."))
    assert any("scene heading" in w.lower() for w in v.warnings)


def test_bad_act_break_placement_warning():
    v = spp.validate_draft_series_script(spp.parse_draft_response(
        "ACT BREAK\n\nINT. X - DAY\n\nAction."))
    assert any("act break" in w.lower() and "start" in w.lower() for w in v.warnings)


def test_bad_tag_placement_warning():
    script = sbk.SeriesScript()
    sbk.add_block(script, sbk.BT_TAG, "TAG")
    sbk.add_block(script, sbk.BT_SCENE_HEADING, "INT. X - DAY")
    sbk.add_block(script, sbk.BT_ACTION, "Action.")
    v = spp.validate_draft_series_script(script)
    assert any("tag" in w.lower() and "before" in w.lower() for w in v.warnings)


def test_abc_story_mismatch_warning():
    script = spp.parse_draft_response("INT. X - DAY\n\nA single beat.")
    plan = spp.EpisodeBeatPlan(chapter="Chapter 1", a_story="A", b_story="B",
                               c_story="C")
    v = spp.validate_draft_series_script(script, episode=plan)
    assert any("storyline" in w.lower() or "serve every" in w.lower()
               for w in v.warnings)


def test_corrupt_structure_blocks_apply():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content="INT. KEEP - DAY\n\nKeep.")
    res = spp.apply_draft(db, pid, sid, sbk.SeriesScript(),
                          mode=spp.APPLY_REPLACE, confirmed=True)
    assert res["ok"] is False and db.get_scene_by_id(sid).content == "INT. KEEP - DAY\n\nKeep."


# ==========================================================================
# 34-37  Export
# ==========================================================================


def test_applied_blocks_export_as_markdown():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content="")
    spp.apply_draft(db, pid, sid, spp.parse_draft_response(_DRAFT),
                    mode=spp.APPLY_TO_EMPTY, confirmed=True)
    md = sbk.export_scene_markdown(db, pid, sid)
    assert "MARIA" in md and "It ends now" in md


def test_project_export_canonical_order():
    db = Database()
    pid = _series(db)
    b = _scene(db, pid, content="INT. B - DAY\n\nBeta beat.", title="Beta",
               act="Act II", chapter="Chapter 2")
    a = _scene(db, pid, content="INT. A - DAY\n\nAlpha beat.", title="Alpha",
               act="Act I", chapter="Chapter 1")
    db.reorder_scenes(pid, [a, b])
    md = sbk.export_project_markdown(db, pid)
    assert md.index("Alpha beat") < md.index("Beta beat")


def test_export_uses_body_not_plan():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nA visible beat.", act="Act I",
           chapter="Chapter 1")
    spp.save_season_plan(db, pid, spp.SeasonArcPlan(act="Act I",
                                                    premise="PLAN_SENTINEL"))
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(chapter="Chapter 1",
                                                       a_story="EP_PLAN_SENTINEL"))
    md = sbk.export_project_markdown(db, pid)
    assert "A visible beat" in md
    assert "PLAN_SENTINEL" not in md and "EP_PLAN_SENTINEL" not in md


def test_export_excludes_api_keys():
    db = Database()
    from logosforge.settings import get_manager
    get_manager().set("ai_api_key", "SECRET_KEY_SENTINEL")
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nA beat.")
    assert "SECRET_KEY_SENTINEL" not in sbk.export_project_markdown(db, pid)


# ==========================================================================
# 38-42  Context / Logos
# ==========================================================================


def test_planning_context_identifies_mode_episode_scene():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content="INT. X - DAY\n\nA beat.", act="Act I",
                 chapter="Episode 2")
    assert spp.series_planning_context(db, pid, sid) == ""       # nothing yet
    spp.save_season_plan(db, pid, spp.SeasonArcPlan(act="Act I", premise="the spine"))
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(chapter="Episode 2",
                                                       a_story="the case"))
    ctx = spp.series_planning_context(db, pid, sid)
    assert "[Series Plan]" in ctx                                # identifies plan block
    assert "Act I" in ctx and "Episode 2" in ctx                 # season + episode
    assert "the spine" in ctx and "the case" in ctx              # both plans included


def test_planning_context_empty_for_non_series():
    db = Database()
    nv = db.create_project("N", narrative_engine="novel").id
    sid = _scene(db, nv, content="prose")
    assert spp.series_planning_context(db, nv, sid) == ""
    assert spp.series_planning_context(db, nv, None) == ""


def test_logos_dropdown_includes_series_planning_actions():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("SR", narrative_engine="series",
                      default_writing_format="series")
    man = [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="series")]
    out = [a.name for a in LogosController(db).available_actions(
        "Outline", writing_mode="series")]
    assert "series_draft_scene" in man
    assert {"series_episode_check", "series_abc_check"} <= set(man)
    assert {"series_season_plan", "series_episode_plan"} <= set(out)
    # Mode-gated: none leak into Novel.
    novel = [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="novel")]
    novel += [a.name for a in LogosController(db).available_actions(
        "Outline", writing_mode="novel")]
    assert not any(n.startswith("series_") for n in novel)


def test_logos_generative_action_does_not_auto_apply():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content="INT. KEEP - DAY\n\nKeep this body.")
    ctl = LogosController(db, provider_resolver=lambda: object(),
                         chat_fn=lambda m, p: "INT. NEW - DAY\n\nGenerated.")
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "series_draft_scene")
    assert res.ok
    assert db.get_scene_by_id(sid).content == "INT. KEEP - DAY\n\nKeep this body."


def test_logos_deterministic_checks_do_not_call_llm():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def _boom(*a, **k):
        raise AssertionError("deterministic action must not call the LLM")

    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content=_DRAFT, chapter="Chapter 1")
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(
        chapter="Chapter 1", a_story="A", b_story="B",
        teaser_or_cold_open="cold open", climax="the fall"))
    ctl = LogosController(db, provider_resolver=_boom, chat_fn=_boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    for action in ("series_episode_check", "series_abc_check"):
        res = ctl.run(ctx, action)
        assert res.ok and res.proposed_operations == []


def test_episode_check_reports_marker_coverage():
    db = Database()
    pid = _series(db)
    # Episode plan promises a teaser, an act break and a tag; the scene has none.
    sid = _scene(db, pid, content="INT. X - DAY\n\nJust action and nothing else.",
                 chapter="Chapter 1")
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(
        chapter="Chapter 1", teaser_or_cold_open="cold open",
        act_breaks=["end of act one"], tag_or_button="a button"))
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    ctl = LogosController(db)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "series_episode_check")
    low = res.message.lower()
    assert "teaser" in low and "act break" in low and "tag" in low


# ==========================================================================
# Regression guards (no image generation; mode isolation)
# ==========================================================================


def test_no_image_generation_in_pipeline():
    import os, tokenize
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(here, "logosforge", "series_pipeline.py")
    toks = []
    with open(src, "rb") as fh:
        for tok in tokenize.tokenize(fh.readline):
            name = tokenize.tok_name[tok.type]
            if tok.type == tokenize.COMMENT or name.endswith("STRING"):
                continue
            toks.append(tok.string.lower())
    skeleton = " ".join(toks)
    for banned in ("comfyui", "image generation", "image prompt", "lora",
                   "render", "stable diffusion", "img2img", "txt2img"):
        assert banned not in skeleton, banned


def test_series_planning_actions_absent_from_other_modes():
    from logosforge.logos.controller import LogosController
    db = Database()
    for engine in ("screenplay", "graphic_novel", "stage_script"):
        db.create_project(engine, narrative_engine=engine,
                          default_writing_format=engine)
        names = [a.name for a in LogosController(db).available_actions(
            "Manuscript", writing_mode=engine)]
        names += [a.name for a in LogosController(db).available_actions(
            "Outline", writing_mode=engine)]
        assert not any(n.startswith("series_") for n in names)
