"""Screenplay Mode — Phase 3 acceptance suite.

Deterministic screenplay intelligence checks: metrics, format/visual/dialogue/
dramatic diagnostics, beat-plan alignment, PSYKE continuity warnings, and the
Logos "Screenplay Check" / "Beat Plan Alignment" actions.

These build on the existing Phase 10C diagnostics engine (extended in Phase 3);
everything is read-only and preview-only — no mutation, and no LLM is required.
"""

from __future__ import annotations

import json
import warnings

import pytest

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge import screenplay_pipeline as spp
from logosforge import screenplay_diagnostics as sd
from logosforge.screenplay_blocks import ScreenplayBlock, parse_screenplay_text


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path, raising=False)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json", raising=False)
    import logosforge.gomckee_bridge as gb
    monkeypatch.setattr(gb, "is_gomckee_enabled", lambda: False)
    yield
    settings._instance = None


def _report(text, **kw):
    return sd.analyze_scene(parse_screenplay_text(text), **kw)


def _ids(report):
    return [i.id for i in report.issues]


# ==========================================================================
# Metrics (1-7)
# ==========================================================================


def test_counts_screenplay_blocks_correctly():
    # heading + action + (JOHN, Hi) + (MARY, Hello) = 6 blocks.
    r = _report("INT. X - DAY\n\nHe walks.\n\nJOHN\nHi.\n\nMARY\nHello.")
    assert r.block_count == 6
    assert r.action_block_count == 1
    assert r.dialogue_block_count == 2
    assert r.character_cue_count == 2


def test_computes_dialogue_action_ratio():
    r = _report("INT. X - DAY\n\nHe walks.\n\nHe sits.\n\nJOHN\nHi.")
    assert r.action_dialogue_ratio == 2.0     # 2 action / 1 dialogue


def test_detects_missing_scene_heading():
    r = _report("John walks in.\n\nJOHN\nHello.")
    assert any(i.id == "missing_scene_heading" for i in r.issues)


def test_detects_dialogue_without_character():
    r = sd.analyze_scene([ScreenplayBlock("action", "Beat."),
                          ScreenplayBlock("dialogue", "Orphan line.")])
    assert any(i.id.startswith("dialogue_without_character") for i in r.issues)


def test_detects_parenthetical_misuse():
    r = sd.analyze_scene([ScreenplayBlock("action", "Beat."),
                          ScreenplayBlock("parenthetical", "(softly)")])
    assert any(i.id.startswith("parenthetical_without_dialogue") for i in r.issues)


def test_detects_long_dialogue_block():
    long_line = " ".join(["word"] * 60)
    r = _report(f"JOHN\n{long_line}")
    assert any(i.id.startswith("long_dialogue") for i in r.issues)
    assert r.longest_dialogue_words >= 60


def test_detects_empty_blocks():
    r = sd.analyze_scene([ScreenplayBlock("action", "  "),
                          ScreenplayBlock("action", "He walks.")])
    assert r.empty_block_count == 1
    assert any(i.id == "empty_blocks" for i in r.issues)


# ==========================================================================
# Visual writing (8-10)
# ==========================================================================


def test_detects_internal_state_phrases():
    text = "INT. X - DAY\n\nJohn thinks and remembers and feels and realizes it all."
    r = _report(text, scene_heading="INT. X - DAY")
    assert r.internal_state_phrase_count >= 2
    assert any(i.id.startswith("internal_action") for i in r.issues)


def test_flags_action_heavy_low_dialogue():
    text = "\n\n".join(["He walks." for _ in range(8)])
    r = _report(text)
    assert r.economy_label == "action-heavy"
    assert any(i.id == "no_dialogue" for i in r.issues)


def test_does_not_flag_concrete_action_as_internal():
    text = "INT. X - DAY\n\nJohn opens the door and crosses the room to the window."
    r = _report(text, scene_heading="INT. X - DAY")
    assert not any(i.id.startswith("internal_action") for i in r.issues)
    assert r.internal_state_phrase_count == 0


# ==========================================================================
# Dramatic function (11-13)
# ==========================================================================


def test_warns_when_no_turn_detected():
    r = _report("INT. X - DAY\n\nHe sits. He waits.", scene_heading="INT. X - DAY")
    turn = next((i for i in r.issues if i.id == "scene_turn_unclear"), None)
    assert turn is not None and turn.confidence < 0.5      # honest low confidence


def test_warns_when_objective_unclear():
    r = _report("INT. X - DAY\n\nJOHN\nNice weather we are having today.",
                scene_heading="INT. X - DAY")
    assert any(i.id == "objective_unclear" for i in r.issues)


def test_warns_beat_plan_objective_missing_from_body():
    plan = spp.ScreenplayBeatPlan(objective="escape the burning warehouse")
    body = parse_screenplay_text("INT. ROOM - DAY\n\nThey chat about gardening.")
    issues = sd.analyze_beat_plan_alignment(body, plan)
    assert any(i.id == "align_objective_missing" for i in issues)


# ==========================================================================
# Beat plan alignment (14-16)
# ==========================================================================


def test_compares_beat_plan_conflict_with_body():
    plan = spp.ScreenplayBeatPlan(conflict="mentor stonewalls the detective")
    missing = sd.analyze_beat_plan_alignment(
        parse_screenplay_text("INT. ROOM - DAY\n\nThey share a quiet coffee."), plan)
    present = sd.analyze_beat_plan_alignment(
        parse_screenplay_text("INT. ROOM - DAY\n\nThe mentor stonewalls her."), plan)
    assert any(i.id == "align_conflict_missing" for i in missing)
    assert not any(i.id == "align_conflict_missing" for i in present)


def test_compares_emotional_shift_with_body():
    plan = spp.ScreenplayBeatPlan(emotional_shift="triumph collapses into despair")
    missing = sd.analyze_beat_plan_alignment(
        parse_screenplay_text("INT. ROOM - DAY\n\nThey discuss the budget."), plan)
    present = sd.analyze_beat_plan_alignment(
        parse_screenplay_text("INT. ROOM - DAY\n\nHer triumph collapses to despair."),
        plan)
    assert any(i.id == "align_emotional_shift_missing" for i in missing)
    assert not any(i.id == "align_emotional_shift_missing" for i in present)


def test_alignment_does_not_mutate_beat_plan_or_body():
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay").id
    sid = ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="S",
                          content="INT. ROOM - DAY\n\nThey chat.", summary="x").id
    spp.save_beat_plan(db, pid, spp.ScreenplayBeatPlan(scene_id=sid, conflict="duel"))
    before_body = db.get_scene_by_id(sid).content
    before_plan = spp.get_beat_plan(db, pid, sid).to_dict()
    sd.analyze_scene_by_id(db, pid, sid)
    assert db.get_scene_by_id(sid).content == before_body
    assert spp.get_beat_plan(db, pid, sid).to_dict() == before_plan


def test_empty_beat_plan_yields_no_alignment_issues():
    issues = sd.analyze_beat_plan_alignment(
        parse_screenplay_text("INT. X - DAY\n\nAction."), spp.ScreenplayBeatPlan())
    assert issues == []


# ==========================================================================
# PSYKE / continuity (17-19)
# ==========================================================================


def test_character_mention_warning_when_psyke_link_missing():
    r = _report("INT. X - DAY\n\nJOHN\nHi.\n\nMARY\nHello.",
                scene_heading="INT. X - DAY", psyke_characters={"JOHN": True})
    assert "character_not_in_psyke_MARY" in _ids(r)
    assert "character_not_in_psyke_JOHN" not in _ids(r)


def test_no_psyke_warning_without_a_psyke_map():
    # No Story Bible to compare against -> never assert a character is "missing".
    r = _report("INT. X - DAY\n\nJOHN\nHi.", scene_heading="INT. X - DAY")
    assert not any(i.id.startswith("character_not_in_psyke") for i in r.issues)


def test_psyke_continuity_does_not_leak_between_projects(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    a = db.create_project("A", narrative_engine="screenplay").id
    db.create_psyke_entry(a, "Alice", "character")
    sid_a = ss.create_scene(db, a, act="Act I", chapter="Seq 1", title="S",
                            content="INT. X - DAY\n\nALICE\nHi.", summary="x").id
    b = db.create_project("B", narrative_engine="screenplay").id
    # Project B has no PSYKE; analyzing B's scene must not see A's Alice.
    sid_b = ss.create_scene(db, b, act="Act I", chapter="Seq 1", title="S",
                            content="INT. X - DAY\n\nBOB\nHi.", summary="x").id
    rep_b = sd.analyze_scene_by_id(db, b, sid_b)
    # No PSYKE in B -> no continuity warnings at all (and certainly not "ALICE").
    assert not any(i.id.startswith("character_not_in_psyke") for i in rep_b.issues)
    # And project A still sees its own entry as linked.
    rep_a = sd.analyze_scene_by_id(db, a, sid_a)
    assert "character_not_in_psyke_ALICE" not in _ids(rep_a)


def test_analysis_does_not_mutate_psyke():
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay").id
    db.create_psyke_entry(pid, "Alice", "character")
    before = len(db.get_all_psyke_entries(pid))
    sid = ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="S",
                          content="INT. X - DAY\n\nBOB\nHi.", summary="x").id
    sd.analyze_scene_by_id(db, pid, sid)
    assert len(db.get_all_psyke_entries(pid)) == before


# ==========================================================================
# UI / actions (20-25)
# ==========================================================================


def test_logos_dropdown_includes_screenplay_check():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("S", narrative_engine="screenplay")
    names = [a.name for a in
             LogosController(db).available_actions("Manuscript", writing_mode="screenplay")]
    assert "sp_scene_health" in names
    assert "sp_beat_plan_alignment" in names
    assert "sp_scene_health" not in [
        a.name for a in LogosController(db).available_actions("Manuscript", writing_mode="novel")]


def test_screenplay_check_action_is_readable():
    from logosforge.logos import actions as A
    act = A.get_action("sp_scene_health")
    assert act is not None
    assert act.label == "Screenplay Check"
    assert act.deterministic and not act.needs_selection
    assert act.modes == ("screenplay",)


def test_screenplay_check_runs_without_selection_and_no_llm():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def _boom(*a, **k):
        raise AssertionError("deterministic action must not call the LLM")

    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay").id
    sid = db.create_scene(pid, "Open", content="INT. X - DAY\n\nJOHN\nHi.",
                          summary="x").id
    ctl = LogosController(db, provider_resolver=_boom, chat_fn=_boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "sp_scene_health")             # no selected_text
    assert res.ok and res.title == "Screenplay Check"
    assert "Metrics" in res.message
    assert res.proposed_operations == []              # diagnostic only


def test_selected_text_actions_still_require_selection():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay").id
    sid = db.create_scene(pid, "Open", content="INT. X - DAY\n\nJohn waits.",
                          summary="x").id
    ctl = LogosController(db, provider_resolver=lambda: object(),
                          chat_fn=lambda m, p: "x")
    ctx = build_logos_context(db, pid, section_name="Manuscript",
                              current_scene_id=sid)           # no selection
    res = ctl.run(ctx, "sp_visual_action")           # needs_selection=True
    assert not res.ok and "Select some text" in (res.error or "")


def test_beat_plan_alignment_action_runs_deterministically():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay").id
    sid = ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="S",
                          content="INT. ROOM - DAY\n\nThey chat about gardening.",
                          summary="x").id
    spp.save_beat_plan(db, pid, spp.ScreenplayBeatPlan(
        scene_id=sid, conflict="a deadly interrogation"))
    ctl = LogosController(db, provider_resolver=lambda: (_ for _ in ()).throw(
        AssertionError("no LLM")), chat_fn=None)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "sp_beat_plan_alignment")
    assert res.ok and res.title == "Beat Plan Alignment"
    assert "Planned conflict" in res.message            # mismatch surfaced
    assert res.proposed_operations == []


def test_beat_plan_alignment_action_prompts_when_no_plan():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay").id
    sid = db.create_scene(pid, "Open", content="INT. X - DAY\n\nJohn waits.",
                          summary="x").id
    ctl = LogosController(db)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "sp_beat_plan_alignment")
    assert res.ok and "no beat plan" in res.message.lower()


def test_check_output_appears_in_result_message_area():
    # The result carries a human-readable message + suggestions (the UI renders
    # these in the existing Logos/Assistant response area).
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay").id
    sid = db.create_scene(
        pid, "Open",
        content="John thinks and remembers and feels and realizes everything.",
        summary="x").id
    from logosforge.logos.deterministic import get_handler
    from logosforge.logos.context import build_logos_context
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = get_handler("sp_scene_health")(db, ctx)
    assert res.message and isinstance(res.suggestions, list)
    assert "Visual Writing:" in res.message            # grouped, readable output


# ==========================================================================
# Assistant context + serialization
# ==========================================================================


def test_assistant_context_includes_beat_plan_alignment_when_misaligned():
    from logosforge.assistant_context_policy import gather_injected_context
    db = Database()
    pid = db.create_project("Film", narrative_engine="screenplay").id
    sid = db.create_scene(pid, "Open",
                          content="INT. ROOM - DAY\n\nThey chat about gardening.",
                          summary="x").id
    spp.save_beat_plan(db, pid, spp.ScreenplayBeatPlan(
        scene_id=sid, conflict="a deadly interrogation"))
    ctx = gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    assert "[Screenplay Diagnostics]" in ctx
    # The diagnostics block reflects the new alignment finding (top issues).
    assert "Planned conflict" in ctx or "alignment" in ctx.lower()


def test_extended_report_is_serializable():
    r = _report("INT. X - DAY\n\nJOHN\nHi.")
    d = r.to_dict()
    assert json.dumps(d)
    for k in ("parenthetical_block_count", "empty_block_count",
              "average_dialogue_words", "longest_dialogue_words",
              "action_dialogue_ratio", "internal_state_phrase_count",
              "repeated_character_turns", "beat_plan_aligned"):
        assert k in d


def test_novel_mode_unaffected_by_phase3_actions():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("Book", narrative_engine="novel")
    names = [a.name for a in
             LogosController(db).available_actions("Manuscript", writing_mode="novel")]
    assert not any(n in names for n in ("sp_scene_health", "sp_beat_plan_alignment"))
