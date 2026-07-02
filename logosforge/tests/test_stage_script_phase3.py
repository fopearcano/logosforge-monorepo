"""Stage Script Mode — Phase 3 acceptance suite.

Deterministic stage-script intelligence: metrics, format/block-order, stage
action & blocking, theatrical playability, dialogue/actor clarity, cues, dramatic
function, plan alignment, PSYKE continuity, and the 'Stage Script Check' Logos
action. Read-only, report-only — no mutation, no LLM, no image generation.
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


def _scene(db, pid, content, *, title="S", summary="", act="Act I",
           chapter="Chapter 1"):
    return ss.create_scene(db, pid, act=act, chapter=chapter, title=title,
                           content=content, summary=summary).id


def _report(body, **kw):
    return ssd.analyze_scene(ssb.parse_stage_script_text(body), **kw)


def _ids(report):
    return [i.id for i in report.issues]


_RICH = (
    "SCENE: Room\n\n"
    "STAGE: A bare room. Maria crosses to the window.\n\n"
    "CHARACTER: MARIA\nHello there friend, how are you doing today.\n\n"
    "CHARACTER: JOHN\nGo away now please.\n\n"
    "ENTER: Bob enters.\n\n"
    "EXIT: Bob exits.\n\n"
    "LIGHT: Lights dim.\n\n"
    "SOUND: Thunder.\n\n"
    "SET: A chair."
)


# ==========================================================================
# 1-10  Metrics
# ==========================================================================


def test_counts_total_blocks():
    assert _report(_RICH).total_blocks == 11


def test_counts_character_blocks():
    assert _report(_RICH).character_count == 2


def test_counts_dialogue_blocks():
    assert _report(_RICH).dialogue_count == 2


def test_counts_stage_directions():
    assert _report(_RICH).stage_direction_count == 1


def test_counts_entrance_exit():
    rep = _report(_RICH)
    assert rep.entrance_count == 1 and rep.exit_count == 1


def test_counts_lighting_sound_cues():
    rep = _report(_RICH)
    assert rep.lighting_count == 1 and rep.sound_count == 1


def test_dialogue_stage_ratio():
    assert _report(_RICH).dialogue_stage_ratio == 2.0


def test_counts_empty_blocks():
    rep = _report("STAGE: A room.\n\nLIGHT:")
    assert rep.empty_block_count >= 1


def test_longest_dialogue_block():
    rep = _report("CHARACTER: MARIA\n" + " ".join(["word"] * 12) + "\nShort.")
    assert rep.longest_dialogue_words == 12


def test_consecutive_dialogue_run():
    body = "CHARACTER: MARIA\n" + "\n".join(f"Line {i}." for i in range(1, 5))
    assert _report(body).max_consecutive_dialogue == 4


# ==========================================================================
# 11-16  Format / block order
# ==========================================================================


def test_dialogue_without_character():
    assert any(i.startswith("dialogue_no_character") for i in
               _ids(_report("DIALOGUE: A line with no speaker.")))


def test_character_without_dialogue():
    assert any(i.startswith("character_no_dialogue") for i in
               _ids(_report("CHARACTER: MARIA\n\nSTAGE: She leaves.")))


def test_parenthetical_misuse():
    assert any(i.startswith("parenthetical_misuse") for i in
               _ids(_report("(angry)")))


def test_empty_cue():
    assert any(i.startswith("empty_cue") for i in
               _ids(_report("STAGE: A room.\n\nLIGHT:")))


def test_entrance_without_name():
    assert any(i.startswith("entrance_no_name") for i in
               _ids(_report("STAGE: A room.\n\nENTER:")))


def test_unknown_block_degrades_safely():
    rep = _report("FOOBAR: an unrecognized label here.")
    assert rep.total_blocks == 1            # absorbed as stage direction, no crash
    assert rep.summary


# ==========================================================================
# 17-21  Stage action / playability
# ==========================================================================


def test_no_stage_direction_warning():
    assert "no_stage_direction" in _ids(_report("CHARACTER: MARIA\nHello there."))


def test_internal_feeling_warning():
    assert any(i.startswith("internal_feeling") for i in
               _ids(_report("STAGE: She feels abandoned and remembers the past.")))


def test_too_many_dialogue_warning():
    body = "CHARACTER: MARIA\n" + "\n".join(f"Line {i}." for i in range(1, 7))
    assert "too_many_dialogue" in _ids(_report(body))


def test_no_visible_action_warning():
    body = "CHARACTER: MARIA\nHi there.\n\nCHARACTER: JOHN\nGoodbye now."
    assert "no_visible_action" in _ids(_report(body))


def test_clear_playable_action_not_flagged():
    body = ("STAGE: Maria crosses to the window.\n\nCHARACTER: MARIA\n"
            "I see them coming.")
    ids = _ids(_report(body))
    assert not any(i.startswith(("internal_feeling", "too_literary",
                                 "overloaded_direction")) for i in ids)


# ==========================================================================
# 22-26  Blocking / Cue plan alignment
# ==========================================================================


def test_planned_entrance_missing_from_body():
    bk = ssp.BlockingCuePlan(scene_id=1, entrance_exit_plan=["Maria enters left"])
    rep = _report("STAGE: A room.\n\nCHARACTER: MARIA\nHi.", blocking_plan=bk)
    assert "blocking_moves_missing" in _ids(rep)


def test_planned_exit_missing_from_body():
    bk = ssp.BlockingCuePlan(scene_id=1, entrance_exit_plan=["John exits right"])
    rep = _report("STAGE: A room.\n\nCHARACTER: JOHN\nBye.", blocking_plan=bk)
    assert "blocking_moves_missing" in _ids(rep)


def test_planned_lighting_cue_missing():
    bk = ssp.BlockingCuePlan(scene_id=1, lighting_cues=["Lights dim slowly"])
    rep = _report("STAGE: A room.\n\nCHARACTER: MARIA\nHi.", blocking_plan=bk)
    assert "blocking_light_missing" in _ids(rep)


def test_planned_sound_cue_missing():
    bk = ssp.BlockingCuePlan(scene_id=1, sound_cues=["Distant thunder"])
    rep = _report("STAGE: A room.\n\nCHARACTER: MARIA\nHi.", blocking_plan=bk)
    assert "blocking_sound_missing" in _ids(rep)


def test_check_does_not_mutate_plans():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, "STAGE: A room.\n\nCHARACTER: MARIA\nHi.")
    ssp.save_beat_plan(db, pid, ssp.StageBeatPlan(scene_id=sid, conflict="KEEP_C"))
    ssp.save_blocking_plan(db, pid, ssp.BlockingCuePlan(scene_id=sid,
                                                        lighting_cues=["KEEP_L"]))
    ssd.analyze_scene_by_id(db, pid, sid)
    assert ssp.get_beat_plan(db, pid, sid).conflict == "KEEP_C"
    assert ssp.get_blocking_plan(db, pid, sid).lighting_cues == ["KEEP_L"]


# ==========================================================================
# 27-29  Dramatic function
# ==========================================================================


def test_objective_unclear_warning():
    assert "objective_unclear" in _ids(_report("CHARACTER: MARIA\nHello."))


def test_conflict_unclear_warning():
    body = "STAGE: A calm room.\n\nCHARACTER: MARIA\nI am happy today."
    assert "conflict_unclear" in _ids(_report(body))


def test_turn_unclear_warning():
    body = "STAGE: A calm room.\n\nCHARACTER: MARIA\nI am happy today."
    assert "turn_unclear" in _ids(_report(body))


# ==========================================================================
# 30-32  Continuity / PSYKE
# ==========================================================================


def test_character_not_in_psyke():
    rep = _report("CHARACTER: JOHN\nHi there.",
                  psyke_characters={"MARIA": True})
    assert "character_not_in_psyke_JOHN" in _ids(rep)


def test_psyke_isolated_across_projects(tmp_path):
    db = Database(str(tmp_path / "st.db"))
    a = _stage(db, "A")
    db.create_psyke_entry(a, "Alice", "character")
    b = _stage(db, "B")
    sid_b = _scene(db, b, "CHARACTER: BOB\nHi there.")
    rep_b = ssd.analyze_scene_by_id(db, b, sid_b)
    # Project B has no Story Bible -> no "not in Story Bible" flags from A.
    assert not any(i.id.startswith("character_not_in_psyke") for i in rep_b.issues)


def test_check_does_not_mutate_psyke():
    db = Database()
    pid = _stage(db)
    db.create_psyke_entry(pid, "Maria", "character")
    sid = _scene(db, pid, "CHARACTER: MARIA\nHi.\n\nCHARACTER: JOHN\nBye.")
    before = len(db.get_all_psyke_entries(pid))
    ssd.analyze_scene_by_id(db, pid, sid)
    assert len(db.get_all_psyke_entries(pid)) == before == 1


# ==========================================================================
# 33-38  Logos / Assistant
# ==========================================================================


def test_logos_dropdown_includes_stage_check():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("ST", narrative_engine="stage_script",
                      default_writing_format="stage_script")
    names = [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="stage_script")]
    assert "stage_check" in names
    novel = [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="novel")]
    assert "stage_check" not in novel


def test_action_is_readable():
    from logosforge.logos import actions as A
    act = A.get_action("stage_check")
    assert act and act.label == "Stage Script Check"
    assert act.deterministic and not act.needs_selection
    assert act.modes == ("stage_script",)


def test_action_runs_without_selection_and_no_llm():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def _boom(*a, **k):
        raise AssertionError("deterministic action must not call the LLM")

    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, _RICH)
    ctl = LogosController(db, provider_resolver=_boom, chat_fn=_boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "stage_check")
    assert res.ok and res.title == "Stage Script Check"
    assert res.proposed_operations == []
    assert ssd.CAT_FORMAT in res.message or "Metrics" in res.message


def test_selected_text_actions_still_require_selection():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, _RICH)
    ctl = LogosController(db, provider_resolver=lambda: object(),
                          chat_fn=lambda m, p: "x")
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "explain_selection")          # needs_selection
    assert not res.ok and "Select" in (res.error or "")


def test_check_message_is_copyable_text():
    from logosforge.logos.deterministic import get_handler
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, _RICH)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = get_handler("stage_check")(db, ctx)
    assert isinstance(res.message, str) and res.message
    assert isinstance(res.suggestions, list)


def test_no_scene_open_is_graceful():
    from logosforge.logos.deterministic import get_handler
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = _stage(db)
    ctx = build_logos_context(db, pid, section_name="Manuscript")
    res = get_handler("stage_check")(db, ctx)
    assert res.ok and "Open a Stage Script scene" in res.message


# ==========================================================================
# Serialization, empty scene, no image generation, mode safety
# ==========================================================================


def test_report_serializes_to_dict():
    import json
    d = _report(_RICH).to_dict()
    assert json.dumps(d) and "total_blocks" in d and "issues" in d


def test_empty_scene_handled():
    rep = _report("")
    assert rep.total_blocks == 0 and "Empty scene" in rep.summary


def test_no_image_generation_code_or_actions():
    import os, tokenize
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(here, "logosforge", "stage_script_diagnostics.py")
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
    from logosforge.logos import actions as A
    names = " ".join(a.name + " " + a.label for a in A.list_actions()).lower()
    for banned in ("comfyui", "image gen", "generate image", "image prompt"):
        assert banned not in names


def test_novel_and_screenplay_unaffected():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("N", narrative_engine="novel")
    nov = [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="novel")]
    scr = [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="screenplay")]
    assert "stage_check" not in nov and "stage_check" not in scr
