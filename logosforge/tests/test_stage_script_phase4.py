"""Stage Script Mode — Phase 4 acceptance suite.

Counterpart / Reflection: a deterministic, multi-perspective (audience / actor /
director / dramaturg) scene reflection that produces feedback and revision
questions — never a rewrite, never a mutation. Builds on Phase 3 diagnostics +
Phase 2 beat/blocking plans + PSYKE; optionally AI-enhanced; optionally savable
as a scene-linked Note.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge import stage_script_pipeline as ssp
from logosforge import stage_script_reflection as ssr


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


def _scene(db, pid, content, *, summary="", title="S"):
    return ss.create_scene(db, pid, act="Act I", chapter="Chapter 1", title=title,
                           content=content, summary=summary).id


def _build(body, *, summary="", beat=None, blocking=None):
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, body, summary=summary)
    if beat is not None:
        beat.scene_id = sid
        ssp.save_beat_plan(db, pid, beat)
    if blocking is not None:
        blocking.scene_id = sid
        ssp.save_blocking_plan(db, pid, blocking)
    return db, pid, sid, ssr.build_scene_reflection(db, pid, sid)


_RICH = (
    "SCENE: The Throne Room\n\n"
    "STAGE: A bare hall. Maria crosses to the window but stops suddenly.\n\n"
    "CHARACTER: MARIA\nI won't leave. I need to know the truth.\n\n"
    "CHARACTER: JOHN\nNo. You must go now.\n\n"
    "ENTER: A guard enters from the left.\n\n"
    "LIGHT: Lights dim to a cold blue.\n\n"
    "SOUND: A distant bell tolls."
)


# ==========================================================================
# 1-11  Reflection core + sections + no mutation
# ==========================================================================


def test_report_can_be_generated():
    db, pid, sid, rep = _build(_RICH, summary="Maria confronts John")
    assert rep.scene_id == sid and rep.snapshot


def test_report_includes_snapshot_and_audience_actor():
    _, _, _, rep = _build(_RICH)
    t = rep.to_text()
    assert ssr.SEC_SNAPSHOT in t and ssr.SEC_AUDIENCE in t and ssr.SEC_ACTOR in t


def test_report_includes_director_and_dramaturg():
    _, _, _, rep = _build(_RICH)
    t = rep.to_text()
    assert ssr.SEC_DIRECTOR in t and ssr.SEC_DRAMATURG in t


def test_report_includes_dialogue_stage_cue_notes():
    _, _, _, rep = _build(_RICH)
    t = rep.to_text()
    assert ssr.SEC_DIALOGUE in t and ssr.SEC_STAGE_ACTION in t and ssr.SEC_CUE in t


def test_report_includes_alignment_and_psyke_sections():
    _, _, _, rep = _build(_RICH)
    t = rep.to_text()
    assert ssr.SEC_BEAT_ALIGN in t and ssr.SEC_BLOCKING_ALIGN in t and ssr.SEC_PSYKE in t


def test_report_includes_revision_questions():
    _, _, _, rep = _build(_RICH)
    assert rep.questions and ssr.SEC_QUESTIONS in rep.to_text()
    assert any("audience" in q.lower() or "physically" in q.lower()
               for q in rep.questions)


def test_report_does_not_mutate_body():
    db, pid, sid, _ = _build(_RICH, summary="keep")
    before = (db.get_scene_by_id(sid).content, db.get_scene_by_id(sid).summary)
    ssr.build_scene_reflection(db, pid, sid)
    after = (db.get_scene_by_id(sid).content, db.get_scene_by_id(sid).summary)
    assert before == after


def test_report_serializes_to_dict():
    import json
    _, _, sid, rep = _build(_RICH)
    d = rep.to_dict()
    assert json.dumps(d) and d["scene_id"] == sid and "metrics" in d


# ==========================================================================
# 12-15  Audience perspective
# ==========================================================================


def test_detects_unclear_audience_understanding():
    _, _, _, rep = _build("CHARACTER: MARIA\nHello there.\n\nCHARACTER: JOHN\nGoodbye now.")
    assert rep.audience


def test_detects_exposition_heavy():
    _, _, _, rep = _build("CHARACTER: MARIA\nHello there.\n\nCHARACTER: JOHN\nGoodbye now.")
    assert any("exposition" in i.title.lower() for i in rep.audience)


def test_detects_emotional_shift_stated_not_staged():
    _, _, _, rep = _build("CHARACTER: MARIA\nI feel so abandoned and alone now.")
    assert any("stated" in i.title.lower() for i in rep.audience)


def test_detects_weak_ending():
    _, _, _, rep = _build("STAGE: A calm room.\n\nCHARACTER: MARIA\nI am content today.")
    assert any("ends without" in i.title.lower() or "turn" in i.title.lower()
               for i in rep.audience)


# ==========================================================================
# 16-19  Actor perspective
# ==========================================================================


def test_character_blocks_detected():
    _, _, _, rep = _build(_RICH)
    assert {c.name for c in rep.actor} == {"MARIA", "JOHN"}


def test_unlinked_characters_reported():
    _, _, _, rep = _build(_RICH)
    maria = next(c for c in rep.actor if c.name == "MARIA")
    assert maria.linked is False and any("unlinked" in n.lower() for n in maria.notes)


def test_character_objective_warning_when_unclear():
    _, _, _, rep = _build("CHARACTER: BOB\nHello there friend, nice weather today.")
    bob = next(c for c in rep.actor if c.name == "BOB")
    assert bob.wants == "unclear"


def test_parenthetical_over_direction_warning():
    body = ("CHARACTER: MARIA\n(softly)\nHi.\n(angrily)\nNo.\n(sadly)\nWhy.")
    _, _, _, rep = _build(body)
    assert any("over-direct" in i.title.lower() for i in rep.dialogue_subtext)


# ==========================================================================
# 20-23  Director / Blocking perspective
# ==========================================================================


def test_missing_movement_warning():
    _, _, _, rep = _build("CHARACTER: MARIA\nHi.\n\nCHARACTER: JOHN\nBye.")
    assert any("stage direction" in i.title.lower() or "action" in i.title.lower()
               for i in rep.director)


def test_entrance_exit_plan_mismatch():
    bk = ssp.BlockingCuePlan(entrance_exit_plan=["Maria enters from left"])
    _, _, _, rep = _build("STAGE: A room.\n\nCHARACTER: MARIA\nHi.", blocking=bk)
    assert any("entrances/exits" in i.title.lower() or "moves" in i.title.lower()
               for i in rep.blocking_alignment)


def test_cue_clarity_warning():
    _, _, _, rep = _build("STAGE: A room.\n\nLIGHT: dim")
    assert any("vague" in i.title.lower() or "cue" in i.title.lower()
               for i in rep.cue_production)


def test_playability_warning_for_internal_state():
    _, _, _, rep = _build("STAGE: She feels abandoned and remembers everything.")
    assert any("interiority" in i.title.lower() or "playable" in i.title.lower()
               or "unplayable" in i.title.lower() for i in rep.stage_action)


# ==========================================================================
# 24-27  Dramaturg / Story
# ==========================================================================


def test_missing_conflict_warning():
    _, _, _, rep = _build("STAGE: A calm room.\n\nCHARACTER: MARIA\nI am happy today.")
    assert any("conflict" in i.title.lower() for i in rep.dramaturg)


def test_missing_turning_point_warning():
    _, _, _, rep = _build("STAGE: A calm room.\n\nCHARACTER: MARIA\nI am happy today.")
    assert any("turn" in i.title.lower() for i in rep.dramaturg)


def test_beat_plan_mismatch_included():
    beat = ssp.StageBeatPlan(conflict="a dragon besieges the castle gates")
    _, _, _, rep = _build("STAGE: A quiet room.\n\nCHARACTER: MARIA\nHi.", beat=beat)
    assert any("beat" in i.title.lower() or "plan" in i.title.lower()
               for i in rep.beat_alignment)


def test_blocking_plan_mismatch_included():
    bk = ssp.BlockingCuePlan(sound_cues=["a thunderclap"])
    _, _, _, rep = _build("STAGE: A quiet room.\n\nCHARACTER: MARIA\nHi.", blocking=bk)
    assert any("sound" in i.title.lower() or "plan" in i.title.lower()
               for i in rep.blocking_alignment)


# ==========================================================================
# 28-30  Deterministic vs AI
# ==========================================================================


def test_deterministic_report_works_without_provider():
    _, _, _, rep = _build(_RICH)
    assert rep.to_text() and not rep.ai_enhanced


def test_reflection_and_messages_do_not_mutate():
    db = Database()
    pid = _stage(db)
    db.create_psyke_entry(pid, "Maria", "character")
    sid = _scene(db, pid, _RICH, summary="keep")
    body_before = db.get_scene_by_id(sid).content
    psyke_before = len(db.get_all_psyke_entries(pid))
    notes_before = len(db.get_all_notes(pid))
    rep = ssr.build_scene_reflection(db, pid, sid)
    ssr.build_reflection_messages(rep, scene_context="[Scene]")
    assert db.get_scene_by_id(sid).content == body_before
    assert len(db.get_all_psyke_entries(pid)) == psyke_before
    assert len(db.get_all_notes(pid)) == notes_before


def test_ai_messages_are_structured_and_grounded():
    _, _, _, rep = _build(_RICH)
    msgs = ssr.build_reflection_messages(rep, scene_context="[Scene Context]")
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system" and "COUNTERPART" in msgs[0]["content"]
    assert msgs[1]["role"] == "user" and ssr.SEC_SNAPSHOT in msgs[1]["content"]
    assert "do not produce replacement script" in msgs[1]["content"].lower() \
        or "do not rewrite" in msgs[1]["content"].lower()


# ==========================================================================
# 31-37  Logos / Assistant
# ==========================================================================


def test_logos_dropdown_contains_stage_reflection():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("ST", narrative_engine="stage_script",
                      default_writing_format="stage_script")
    names = [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="stage_script")]
    assert "stage_reflection" in names
    novel = [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="novel")]
    assert "stage_reflection" not in novel


def test_action_is_readable():
    from logosforge.logos import actions as A
    act = A.get_action("stage_reflection")
    assert act and act.label == "Stage Script Reflection"
    assert act.deterministic and not act.needs_selection
    assert act.modes == ("stage_script",)


def test_action_runs_without_selection_and_no_llm():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def _boom(*a, **k):
        raise AssertionError("deterministic reflection must not call the LLM")

    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, _RICH)
    ctl = LogosController(db, provider_resolver=_boom, chat_fn=_boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "stage_reflection")
    assert res.ok and res.title == "Stage Script Reflection"
    assert ssr.SEC_AUDIENCE in res.message and ssr.SEC_DRAMATURG in res.message
    assert res.proposed_operations == []


def test_selected_text_actions_still_require_selection():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, _RICH)
    ctl = LogosController(db, provider_resolver=lambda: object(),
                          chat_fn=lambda m, p: "x")
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "explain_selection")
    assert not res.ok and "Select" in (res.error or "")


def test_assistant_reflection_seam_works():
    _, _, _, rep = _build(_RICH)
    msgs = ssr.build_reflection_messages(rep)
    assert isinstance(msgs, list) and msgs and msgs[0]["role"] == "system"


def test_report_message_is_copyable_text():
    from logosforge.logos.deterministic import get_handler
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, _RICH)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = get_handler("stage_reflection")(db, ctx)
    assert isinstance(res.message, str) and res.message
    assert isinstance(res.suggestions, list)


def test_no_scene_open_is_graceful():
    from logosforge.logos.deterministic import get_handler
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = _stage(db)
    ctx = build_logos_context(db, pid, section_name="Manuscript")
    res = get_handler("stage_reflection")(db, ctx)
    assert res.ok and "Open a Stage Script scene" in res.message


# ==========================================================================
# 38-40  Optional Notes integration
# ==========================================================================


def test_save_reflection_as_note_requires_confirmation():
    db, pid, sid, rep = _build(_RICH)
    res = ssr.save_reflection_as_note(db, pid, sid, rep, confirmed=False)
    assert res["ok"] is False and len(db.get_all_notes(pid)) == 0


def test_saved_note_links_to_scene():
    db, pid, sid, rep = _build(_RICH)
    res = ssr.save_reflection_as_note(db, pid, sid, rep, confirmed=True)
    assert res["ok"] and res["note_id"]
    assert res["note_id"] in db.get_scene_note_links(sid)


def test_cancel_save_note_does_not_mutate_notes():
    db, pid, sid, rep = _build(_RICH)
    before = len(db.get_all_notes(pid))
    ssr.save_reflection_as_note(db, pid, sid, rep, confirmed=False)
    assert len(db.get_all_notes(pid)) == before


# ==========================================================================
# Isolation + no image generation + mode safety
# ==========================================================================


def test_reflection_isolated_across_projects(tmp_path):
    db = Database(str(tmp_path / "st.db"))
    a = _stage(db, "A")
    db.create_psyke_entry(a, "Alice", "character")
    b = _stage(db, "B")
    sid_b = _scene(db, b, "CHARACTER: BOB\nHi there.")
    rep_b = ssr.build_scene_reflection(db, b, sid_b)
    risk = " ".join(i.title + " " + i.detail for i in rep_b.continuity_risks)
    assert "ALICE" not in risk.upper()


def test_no_image_generation_code_or_actions():
    import os, tokenize
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(here, "logosforge", "stage_script_reflection.py")
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


def test_scene_not_found_is_graceful():
    db = Database()
    pid = _stage(db)
    rep = ssr.build_scene_reflection(db, pid, 999999)
    assert rep.snapshot == "Scene not found."
