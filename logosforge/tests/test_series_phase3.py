"""Series Mode — Phase 3 acceptance suite.

Deterministic Series intelligence: scene health (format / block order, scene
function, dialogue-action balance, plan alignment, PSYKE), episode structure,
season/arc alignment, transparent metrics, and Logos check actions. Everything is
report-only — no mutation, no auto-apply, no LLM, no image generation. Canonical
Act -> Chapter -> Scene is preserved (Chapter shown as Episode).
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
from logosforge import series_diagnostics as sd


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


def _script(*pairs):
    s = sbk.SeriesScript()
    for bt, text in pairs:
        sbk.add_block(s, bt, text)
    return s


# ==========================================================================
# 1-12  Metrics
# ==========================================================================


def test_metrics_total_blocks():
    s = _script((sbk.BT_SCENE_HEADING, "INT. X - DAY"), (sbk.BT_ACTION, "A."))
    assert sd.compute_metrics(s).total_blocks == 2


def test_metrics_scene_heading_count():
    s = _script((sbk.BT_SCENE_HEADING, "INT. X - DAY"),
                (sbk.BT_SCENE_HEADING, "INT. Y - DAY"), (sbk.BT_ACTION, "A."))
    assert sd.compute_metrics(s).scene_heading_count == 2


def test_metrics_action_count():
    s = _script((sbk.BT_ACTION, "A."), (sbk.BT_ACTION, "B."), (sbk.BT_DIALOGUE, "x"))
    assert sd.compute_metrics(s).action_count == 2


def test_metrics_character_count():
    s = _script((sbk.BT_CHARACTER, "MARIA"), (sbk.BT_DIALOGUE, "Hi."),
                (sbk.BT_CHARACTER, "JOHN"), (sbk.BT_DIALOGUE, "Bye."))
    assert sd.compute_metrics(s).character_count == 2


def test_metrics_dialogue_count():
    s = _script((sbk.BT_CHARACTER, "MARIA"), (sbk.BT_DIALOGUE, "a"),
                (sbk.BT_DIALOGUE, "b"))
    assert sd.compute_metrics(s).dialogue_count == 2


def test_metrics_act_break_count():
    s = _script((sbk.BT_SCENE_HEADING, "INT. X - DAY"), (sbk.BT_ACT_BREAK, "ACT BREAK"))
    assert sd.compute_metrics(s).act_break_count == 1


def test_metrics_teaser_count():
    s = _script((sbk.BT_TEASER, "COLD OPEN"), (sbk.BT_SCENE_HEADING, "INT. X - DAY"))
    assert sd.compute_metrics(s).teaser_count == 1


def test_metrics_tag_count():
    s = _script((sbk.BT_SCENE_HEADING, "INT. X - DAY"), (sbk.BT_TAG, "TAG"))
    assert sd.compute_metrics(s).tag_count == 1


def test_metrics_dialogue_action_ratio():
    s = _script((sbk.BT_ACTION, "A."), (sbk.BT_ACTION, "B."),
                (sbk.BT_CHARACTER, "MARIA"), (sbk.BT_DIALOGUE, "1"),
                (sbk.BT_DIALOGUE, "2"), (sbk.BT_DIALOGUE, "3"), (sbk.BT_DIALOGUE, "4"))
    assert sd.compute_metrics(s).dialogue_action_ratio == 2.0   # 4 dialogue / 2 action


def test_metrics_empty_block_count():
    s = _script((sbk.BT_SCENE_HEADING, "INT. X - DAY"), (sbk.BT_ACTION, ""))
    assert sd.compute_metrics(s).empty_block_count == 1


def test_metrics_longest_dialogue():
    s = _script((sbk.BT_CHARACTER, "MARIA"), (sbk.BT_DIALOGUE, "one two"),
                (sbk.BT_DIALOGUE, "one two three four five"))
    assert sd.compute_metrics(s).longest_dialogue_words == 5


def test_metrics_consecutive_dialogue_run():
    s = _script((sbk.BT_SCENE_HEADING, "INT. X - DAY"), (sbk.BT_CHARACTER, "MARIA"),
                (sbk.BT_DIALOGUE, "a"), (sbk.BT_DIALOGUE, "b"),
                (sbk.BT_DIALOGUE, "c"), (sbk.BT_DIALOGUE, "d"))
    assert sd.compute_metrics(s).max_consecutive_dialogue == 4


# ==========================================================================
# 13-18  Format / block order
# ==========================================================================


def test_detects_missing_scene_heading():
    r = sd.analyze_scene(_script((sbk.BT_ACTION, "A."), (sbk.BT_CHARACTER, "MARIA"),
                                 (sbk.BT_DIALOGUE, "Hi.")))
    assert any(i.id == "no_scene_heading" for i in r.issues)


def test_detects_dialogue_without_character():
    r = sd.analyze_scene(_script((sbk.BT_SCENE_HEADING, "INT. X - DAY"),
                                 (sbk.BT_DIALOGUE, "No speaker.")))
    assert any(i.id.startswith("dialogue_no_character") for i in r.issues)


def test_detects_character_without_dialogue():
    r = sd.analyze_scene(_script((sbk.BT_SCENE_HEADING, "INT. X - DAY"),
                                 (sbk.BT_CHARACTER, "MARIA"), (sbk.BT_ACTION, "She leaves.")))
    assert any(i.id.startswith("character_no_dialogue") for i in r.issues)


def test_detects_parenthetical_misuse():
    r = sd.analyze_scene(_script((sbk.BT_SCENE_HEADING, "INT. X - DAY"),
                                 (sbk.BT_PARENTHETICAL, "(beat)")))
    assert any(i.id.startswith("parenthetical_misuse") for i in r.issues)


def test_detects_empty_block():
    r = sd.analyze_scene(_script((sbk.BT_SCENE_HEADING, "INT. X - DAY"),
                                 (sbk.BT_ACTION, "")))
    assert any(i.id.startswith("empty_block") for i in r.issues)


def test_handles_unknown_block_type_safely():
    s = _script((sbk.BT_SCENE_HEADING, "INT. X - DAY"))
    b = sbk.SeriesBlock(sbk.BT_ACTION, "weird")
    b.block_type = "weirdo"          # force an invalid type past normalization
    s.blocks.append(b)
    r = sd.analyze_scene(s)          # must not crash
    assert any(i.id.startswith("unknown_type") for i in r.issues)


# ==========================================================================
# 19-23  Scene function
# ==========================================================================


def test_warns_objective_unclear():
    r = sd.analyze_scene(_script((sbk.BT_SCENE_HEADING, "INT. X - DAY"),
                                 (sbk.BT_ACTION, "Maria stands by the window.")),
                         outline_summary="")
    assert any(i.id == "objective_unclear" for i in r.issues)


def test_warns_does_not_advance_episode_objective():
    plan = spp.EpisodeBeatPlan(chapter="Episode 1",
                               episode_objective="overthrow the empire")
    r = sd.analyze_scene(_script((sbk.BT_SCENE_HEADING, "INT. X - DAY"),
                                 (sbk.BT_ACTION, "Maria waters her plants.")),
                         outline_summary="", episode_plan=plan)
    assert any(i.id == "not_advance_objective" for i in r.issues)


def test_warns_not_connected_to_abc_story():
    plan = spp.EpisodeBeatPlan(chapter="Episode 1", a_story="the heist downtown",
                               b_story="the office romance")
    r = sd.analyze_scene(_script((sbk.BT_SCENE_HEADING, "INT. X - DAY"),
                                 (sbk.BT_ACTION, "Maria waters her plants.")),
                         outline_summary="", episode_plan=plan)
    assert any(i.id == "no_abc_connection" for i in r.issues)


def test_warns_no_visible_turn():
    r = sd.analyze_scene(_script((sbk.BT_SCENE_HEADING, "INT. X - DAY"),
                                 (sbk.BT_ACTION, "Maria waters her plants.")))
    assert any(i.id == "turn_unclear" for i in r.issues)


def test_functional_scene_not_flagged():
    plan = spp.EpisodeBeatPlan(chapter="Episode 1",
                               episode_objective="escape the prison",
                               a_story="the prison escape")
    s = _script((sbk.BT_SCENE_HEADING, "INT. PRISON - NIGHT"),
                (sbk.BT_ACTION, "Maria wants to escape the prison."),
                (sbk.BT_CHARACTER, "MARIA"),
                (sbk.BT_DIALOGUE, "But the guard blocks it, then suddenly we run."))
    r = sd.analyze_scene(s, outline_summary="Maria escapes the prison.",
                         episode_plan=plan)
    assert not r.issues_in(sd.CAT_FUNCTION)


# ==========================================================================
# 24-29  Episode structure
# ==========================================================================


def test_episode_warns_missing_beat_plan():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nA beat.", chapter="Episode 1")
    r = sd.analyze_episode(db, pid, "Episode 1")
    assert any(i.id == "episode_no_plan" for i in r.issues)


def test_episode_warns_missing_cold_open():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nA beat.", chapter="Episode 1")
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(
        chapter="Episode 1", teaser_or_cold_open="a cold open", climax="the fall"))
    r = sd.analyze_episode(db, pid, "Episode 1")
    assert any(i.id == "teaser_expected_missing" for i in r.issues)


def test_episode_warns_missing_act_break():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nA beat.", chapter="Episode 1")
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(
        chapter="Episode 1", act_breaks=["end of act one"], climax="the fall"))
    r = sd.analyze_episode(db, pid, "Episode 1")
    assert any(i.id == "act_break_expected_missing" for i in r.issues)


def test_episode_warns_missing_tag():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nA beat.", chapter="Episode 1")
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(
        chapter="Episode 1", tag_or_button="a button", climax="the fall"))
    r = sd.analyze_episode(db, pid, "Episode 1")
    assert any(i.id == "tag_expected_missing" for i in r.issues)


def test_episode_warns_missing_climax():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nA beat.", chapter="Episode 1")
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(
        chapter="Episode 1", episode_premise="a premise"))   # no climax/turns
    r = sd.analyze_episode(db, pid, "Episode 1")
    assert any(i.id == "climax_missing" for i in r.issues)


def test_episode_warns_weak_abc_coverage():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nA beat.", chapter="Episode 1")
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(
        chapter="Episode 1", a_story="A", b_story="B", c_story="C", climax="x"))
    r = sd.analyze_episode(db, pid, "Episode 1")   # 1 scene, 3 stories
    assert any(i.id == "abc_weak" for i in r.issues)


# ==========================================================================
# 30-33  Season / Arc alignment
# ==========================================================================


def test_episode_warns_missing_season_plan():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nA beat.", chapter="Episode 1")
    r = sd.analyze_episode(db, pid, "Episode 1")
    assert any(i.id == "no_season_plan" for i in r.issues)


def test_episode_warns_not_connected_to_arc():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nMaria waters plants.",
           act="Act I", chapter="Episode 1", summary="watering")
    spp.save_season_plan(db, pid, spp.SeasonArcPlan(
        act="Act I", arc_question="who murdered the senator"))
    r = sd.analyze_episode(db, pid, "Episode 1")
    assert any(i.id == "arc_question_unsupported" for i in r.issues)


def test_episode_warns_setup_payoff_unsupported():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nMaria waters plants.",
           act="Act I", chapter="Episode 1", summary="watering")
    spp.save_season_plan(db, pid, spp.SeasonArcPlan(
        act="Act I", setup_payoff_notes="the hidden treasure vault"))
    r = sd.analyze_episode(db, pid, "Episode 1")
    assert any(i.id == "setup_payoff_unsupported" for i in r.issues)


def test_episode_check_does_not_mutate_season_plan():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nA beat.", act="Act I", chapter="Episode 1")
    spp.save_season_plan(db, pid, spp.SeasonArcPlan(act="Act I", premise="KEEP"))
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(chapter="Episode 1",
                                                       a_story="KEEP_E"))
    sd.analyze_episode(db, pid, "Episode 1")
    assert spp.get_season_plan(db, pid, "Act I").premise == "KEEP"
    assert spp.get_episode_plan(db, pid, "Episode 1").a_story == "KEEP_E"


# ==========================================================================
# 34-38  Timeline / PSYKE
# ==========================================================================


def test_timeline_order_mismatch_warning():
    db = Database()
    pid = _series(db)
    b = _scene(db, pid, content="INT. B - DAY\n\nb.", title="B", chapter="Episode 1")
    a = _scene(db, pid, content="INT. A - DAY\n\na.", title="A", chapter="Episode 1")
    db.reorder_scenes(pid, [a, b])
    db.add_timeline_event(pid, a)
    db.add_timeline_event(pid, b)
    db.set_timeline_order_mode(pid, "custom")
    db.set_timeline_order(pid, [b, a])      # reversed vs canonical [a, b]
    r = sd.analyze_episode(db, pid, "Episode 1")
    assert any(i.id == "timeline_order_mismatch" for i in r.issues)


def test_timeline_linked_labels_use_canonical_numbering():
    db = Database()
    pid = _series(db)
    a = _scene(db, pid, content="INT. A - DAY\n\na.", title="A", chapter="Episode 1")
    _scene(db, pid, content="INT. B - DAY\n\nb.", title="B", chapter="Episode 1")
    db.add_timeline_event(pid, a)
    tree = ss.build_structure_tree(db, pid)
    nums = ss.compute_structural_numbers(tree, ss.is_novel_project(db, pid))
    expected = nums["scenes"].get(a)
    r = sd.analyze_episode(db, pid, "Episode 1")
    assert r.timeline_linked_labels == [expected]
    assert expected and expected != str(a)   # canonical number, not the raw id


def test_character_not_in_psyke_warning():
    db = Database()
    pid = _series(db)
    db.create_psyke_entry(pid, "Maria", "character")
    sid = _scene(db, pid, content="INT. X - DAY\n\nJOHN\nHello.")
    r = sd.analyze_scene_by_id(db, pid, sid)
    assert any(i.id.startswith("character_not_in_psyke") and "JOHN" in i.id
               for i in r.issues)


def test_psyke_not_leaked_across_projects(tmp_path):
    db = Database(str(tmp_path / "sr.db"))
    a = _series(db, "A")
    db.create_psyke_entry(a, "Maria", "character")
    b = _series(db, "B")
    sid = _scene(db, b, content="INT. X - DAY\n\nMARIA\nHello.")
    r = sd.analyze_scene_by_id(db, b, sid)   # B has no Story Bible -> no PSYKE flags
    assert not r.issues_in(sd.CAT_CONTINUITY)


def test_check_does_not_mutate_psyke():
    db = Database()
    pid = _series(db)
    db.create_psyke_entry(pid, "Maria", "character")
    sid = _scene(db, pid, content="INT. X - DAY\n\nMARIA\nHello.")
    before = len(db.get_all_psyke_entries(pid))
    sd.analyze_scene_by_id(db, pid, sid)
    assert len(db.get_all_psyke_entries(pid)) == before == 1


# ==========================================================================
# 39-46  UI / actions
# ==========================================================================


def _series_actions(db, section="Manuscript"):
    from logosforge.logos.controller import LogosController
    return [a for a in LogosController(db).available_actions(
        section, writing_mode="series")]


def test_logos_dropdown_includes_scene_check():
    db = Database()
    _series(db)
    names = [a.name for a in _series_actions(db)]
    assert "series_check" in names


def test_logos_dropdown_includes_episode_check():
    db = Database()
    _series(db)
    names = [a.name for a in _series_actions(db)]
    assert "series_episode_check" in names


def test_series_check_actions_are_readable():
    db = Database()
    _series(db)
    checks = {a.name: a for a in _series_actions(db)
              if a.name in ("series_check", "series_episode_check", "series_abc_check",
                            "series_act_break_check", "series_cold_open_tag_check",
                            "series_dialogue_balance", "series_arc_alignment")}
    assert len(checks) == 7
    for a in checks.values():
        assert len(a.label) >= 5 and a.description     # human-readable, not a tiny button


def test_series_checks_run_without_selection_and_are_deterministic():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def _boom(*a, **k):
        raise AssertionError("deterministic action must not call the LLM")

    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content=(
        "COLD OPEN\n\nINT. X - NIGHT\n\nMaria waters plants.\n\n"
        "MARIA\nHello.\n\nACT BREAK\n\nTAG"), chapter="Episode 1")
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(
        chapter="Episode 1", a_story="A", b_story="B", climax="x"))
    spp.save_season_plan(db, pid, spp.SeasonArcPlan(act="Act I", arc_question="why"))
    ctl = LogosController(db, provider_resolver=_boom, chat_fn=_boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    assert ctx.selected_text == ""          # no selection
    for action in ("series_check", "series_episode_check", "series_abc_check",
                   "series_act_break_check", "series_cold_open_tag_check",
                   "series_dialogue_balance", "series_arc_alignment"):
        res = ctl.run(ctx, action)
        assert res.ok and res.proposed_operations == [] and res.message  # output present


def test_series_check_actions_do_not_require_selection():
    db = Database()
    _series(db)
    for a in _series_actions(db):
        if a.name.startswith("series_") and a.deterministic:
            assert a.needs_selection is False   # full-scene / episode checks


def test_episode_check_runs_from_scene_context():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content="INT. X - DAY\n\nA beat.", chapter="Episode 1")
    ctl = LogosController(db)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "series_episode_check")
    assert res.ok and "Episode" in res.message


# ==========================================================================
# Regression guards
# ==========================================================================


def test_no_image_generation_in_diagnostics():
    import os, tokenize
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(here, "logosforge", "series_diagnostics.py")
    toks = []
    with open(src, "rb") as fh:
        for tok in tokenize.tokenize(fh.readline):
            name = tokenize.tok_name[tok.type]
            if tok.type == tokenize.COMMENT or name.endswith("STRING"):
                continue
            toks.append(tok.string.lower())
    skeleton = " ".join(toks)
    for banned in ("comfyui", "image generation", "image prompt", "lora",
                   "stable diffusion", "img2img", "txt2img"):
        assert banned not in skeleton, banned


def test_series_checks_absent_from_other_modes():
    from logosforge.logos.controller import LogosController
    db = Database()
    for engine in ("novel", "screenplay", "graphic_novel", "stage_script"):
        db.create_project(engine, narrative_engine=engine,
                          default_writing_format=engine)
        names = [a.name for a in LogosController(db).available_actions(
            "Manuscript", writing_mode=engine)]
        assert not any(n.startswith("series_") for n in names)
