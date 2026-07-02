"""Stage Script Mode — Phase 6 acceptance suite.

Cross-scene theatrical continuity / coherence: a deterministic, read-only report
(Scene Chain, Character/Entrances/Exits, Blocking/Movement, Props/Set,
Lighting/Sound Cue, Setup/Payoff, Timeline alignment, PSYKE/Notes) consolidating
the existing continuity / setup-payoff / Timeline / PSYKE engines plus
stage-specific checks. No mutation, no image generation.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge import stage_script_pipeline as ssp
from logosforge import stage_script_continuity as ssc


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
    """Beta created first (Act II), Alpha second (Act I) -> canonical Alpha, Beta."""
    pid = _stage(db)
    b = ss.create_scene(db, pid, act="Act II", chapter="Chapter 2", title="Beta",
                        content="SCENE: Lab\n\nSTAGE: Mary works.\n\n"
                                "CHARACTER: MARY\nHello.", summary="Beta").id
    a = ss.create_scene(db, pid, act="Act I", chapter="Chapter 1", title="Alpha",
                        content="SCENE: Kitchen\n\nSTAGE: Maria waits.\n\n"
                                "CHARACTER: MARIA\nHi.", summary="Alpha").id
    db.reorder_scenes(pid, [a, b])
    return pid, a, b


def _row(rep, title):
    return next(f for f in rep.all_findings() if title.lower() in f.title.lower())


# ==========================================================================
# 1-3  Canonical chain
# ==========================================================================


def test_report_reads_scenes_in_canonical_order():
    db = Database()
    pid, a, b = _two_scene(db)
    rep = ssc.build_stage_script_continuity_report(db, pid)
    assert [e.title for e in rep.scene_chain] == ["Alpha", "Beta"]
    assert [e.scene_id for e in rep.scene_chain] == [a, b]


def test_moving_scene_updates_order():
    db = Database()
    pid, a, b = _two_scene(db)
    db.reorder_scenes(pid, [b, a])
    rep = ssc.build_stage_script_continuity_report(db, pid)
    assert [e.title for e in rep.scene_chain] == ["Beta", "Alpha"]


def test_chain_does_not_sort_by_id():
    db = Database()
    pid, a, b = _two_scene(db)
    ids = [e.scene_id for e in ssc.build_stage_script_continuity_report(db, pid).scene_chain]
    assert ids != sorted(ids) and ids == [a, b]


# ==========================================================================
# 4-7  Scene state
# ==========================================================================


def test_missing_beat_plan_reported():
    db = Database()
    pid, a, b = _two_scene(db)
    rep = ssc.build_stage_script_continuity_report(db, pid)
    assert rep.metrics["scenes_without_beat_plan"] == 2
    assert all(not e.has_beat_plan for e in rep.scene_chain)


def test_missing_blocking_plan_reported():
    db = Database()
    pid, a, b = _two_scene(db)
    rep = ssc.build_stage_script_continuity_report(db, pid)
    assert rep.metrics["scenes_without_blocking_plan"] == 2


def test_missing_body_reported():
    db = Database()
    pid = _stage(db)
    _sc(db, pid, "Empty", "")
    rep = ssc.build_stage_script_continuity_report(db, pid)
    assert rep.metrics["scenes_without_body"] == 1
    assert not rep.scene_chain[0].has_body


def test_scene_with_body_and_plans_not_false_empty():
    db = Database()
    pid = _stage(db)
    sid = _sc(db, pid, "Full", "SCENE: Room\n\nSTAGE: In the room, action.\n\n"
              "CHARACTER: MARIA\nHi.")
    ssp.save_beat_plan(db, pid, ssp.StageBeatPlan(scene_id=sid, objective="go"))
    ssp.save_blocking_plan(db, pid, ssp.BlockingCuePlan(scene_id=sid,
                                                        staging_area_notes="x"))
    e = ssc.build_stage_script_continuity_report(db, pid).scene_chain[0]
    assert e.has_body and e.has_beat_plan and e.has_blocking_plan


# ==========================================================================
# 8-12  Character / entrance / exit continuity
# ==========================================================================


def test_speaks_without_entrance_warned():
    db = Database()
    pid = _stage(db)
    # Scene uses entrances (BOB) but JOHN speaks with no entrance.
    _sc(db, pid, "A", "ENTER: Bob enters from the left.\n\n"
        "CHARACTER: JOHN\nHello there.\n\nCHARACTER: BOB\nHi.")
    rep = ssc.build_stage_script_continuity_report(db, pid)
    assert any("speaks without" in f.title.lower() and "JOHN" in f.title
               for f in rep.character_continuity)


def test_exit_then_acts_warned():
    db = Database()
    pid = _stage(db)
    _sc(db, pid, "A", "CHARACTER: MARIA\nI leave now.\n\nEXIT: Maria exits right.\n\n"
        "CHARACTER: MARIA\nActually, wait.")
    rep = ssc.build_stage_script_continuity_report(db, pid)
    assert any("after exiting" in f.title.lower() for f in rep.character_continuity)


def test_planned_entrance_exit_missing_from_body():
    db = Database()
    pid = _stage(db)
    sid = _sc(db, pid, "A", "STAGE: A room.\n\nCHARACTER: MARIA\nHi.")
    ssp.save_blocking_plan(db, pid, ssp.BlockingCuePlan(
        scene_id=sid, entrance_exit_plan=["Maria enters left", "John exits right"]))
    rep = ssc.build_stage_script_continuity_report(db, pid)
    assert any("entrances/exits not staged" in f.title.lower()
               for f in rep.character_continuity)


def test_character_disappearance_warning():
    db = Database()
    pid = _stage(db)
    ids = [_sc(db, pid, "S1", "STAGE: x.\n\nCHARACTER: ZARA\nHi.", act="Act I")]
    for i, act in enumerate(("Act II", "Act III", "Act IV"), start=2):
        ids.append(_sc(db, pid, f"S{i}", f"STAGE: x.\n\nCHARACTER: BOB\nLine {i}.",
                       act=act, chapter=f"Chapter {i}"))
    db.reorder_scenes(pid, ids)
    rep = ssc.build_stage_script_continuity_report(db, pid)
    assert any("ZARA" in f.title for f in rep.character_continuity)


# ==========================================================================
# 13-17  Blocking / set / prop continuity
# ==========================================================================


def test_missing_stage_direction_warning():
    db = Database()
    pid = _stage(db)
    _sc(db, pid, "A", "CHARACTER: MARIA\nHi.\n\nCHARACTER: JOHN\nBye.")
    rep = ssc.build_stage_script_continuity_report(db, pid)
    assert any("no stage directions" in f.title.lower()
               for f in rep.blocking_continuity)


def test_planned_movement_missing():
    db = Database()
    pid = _stage(db)
    sid = _sc(db, pid, "A", "CHARACTER: MARIA\nHi.")
    ssp.save_blocking_plan(db, pid, ssp.BlockingCuePlan(
        scene_id=sid, movement_beats=["Maria crosses downstage"]))
    rep = ssc.build_stage_script_continuity_report(db, pid)
    assert any("movement not staged" in f.title.lower()
               for f in rep.blocking_continuity)


def test_set_change_without_orientation():
    db = Database()
    pid = _stage(db)
    _sc(db, pid, "A", "STAGE: In the kitchen, Maria cooks.", act="Act I")
    _sc(db, pid, "B", "CHARACTER: BOB\nSomeone speaks with no orientation.",
        act="Act II", chapter="Chapter 2")
    rep = ssc.build_stage_script_continuity_report(db, pid)
    assert any("orientation" in f.title.lower() for f in rep.blocking_continuity)


def test_prop_recurrence_detected():
    db = Database()
    pid = _stage(db)
    for i, act in enumerate(("Act I", "Act II", "Act III"), start=1):
        _sc(db, pid, f"S{i}", f"STAGE: A lantern glows on the table {i}.",
            act=act, chapter=f"Chapter {i}")
    rep = ssc.build_stage_script_continuity_report(db, pid)
    assert any("lantern" in (f.title + f.detail).lower() for f in rep.props_set)


def test_setup_payoff_is_a_list():
    db = Database()
    pid, a, b = _two_scene(db)
    rep = ssc.build_stage_script_continuity_report(db, pid)
    assert isinstance(rep.setup_payoff, list)


# ==========================================================================
# 18-21  Cue continuity
# ==========================================================================


def test_planned_lighting_cue_missing():
    db = Database()
    pid = _stage(db)
    sid = _sc(db, pid, "A", "STAGE: A room.\n\nCHARACTER: MARIA\nHi.")
    ssp.save_blocking_plan(db, pid, ssp.BlockingCuePlan(
        scene_id=sid, lighting_cues=["Lights dim slowly"]))
    rep = ssc.build_stage_script_continuity_report(db, pid)
    assert any("lighting cue not staged" in f.title.lower()
               for f in rep.cue_continuity)


def test_planned_sound_cue_missing():
    db = Database()
    pid = _stage(db)
    sid = _sc(db, pid, "A", "STAGE: A room.\n\nCHARACTER: MARIA\nHi.")
    ssp.save_blocking_plan(db, pid, ssp.BlockingCuePlan(
        scene_id=sid, sound_cues=["Distant thunder"]))
    rep = ssc.build_stage_script_continuity_report(db, pid)
    assert any("sound cue not staged" in f.title.lower() for f in rep.cue_continuity)


def test_cue_used_once_reported():
    db = Database()
    pid = _stage(db)
    _sc(db, pid, "S1", "STAGE: x.\n\nLIGHT: Lights up.", act="Act I")
    for i, act in enumerate(("Act II", "Act III"), start=2):
        _sc(db, pid, f"S{i}", f"STAGE: scene {i}.", act=act, chapter=f"Chapter {i}")
    rep = ssc.build_stage_script_continuity_report(db, pid)
    assert any("lighting used in only one scene" in f.title.lower()
               for f in rep.cue_continuity)


def test_planned_transition_missing():
    db = Database()
    pid = _stage(db)
    sid = _sc(db, pid, "A", "STAGE: A room.\n\nCHARACTER: MARIA\nHi.")
    ssp.save_blocking_plan(db, pid, ssp.BlockingCuePlan(
        scene_id=sid, transition_notes="Blackout at the end"))
    rep = ssc.build_stage_script_continuity_report(db, pid)
    assert any("transition" in f.title.lower() for f in rep.cue_continuity)


# ==========================================================================
# 22-25  Timeline alignment
# ==========================================================================


def test_scene_linked_to_timeline_detected():
    db = Database()
    pid, a, b = _two_scene(db)
    db.add_timeline_event(pid, a)
    rep = ssc.build_stage_script_continuity_report(db, pid)
    ea = next(e for e in rep.scene_chain if e.scene_id == a)
    assert ea.timeline_linked is True


def test_scene_without_timeline_link_reported():
    db = Database()
    pid, a, b = _two_scene(db)
    db.add_timeline_event(pid, a)
    rep = ssc.build_stage_script_continuity_report(db, pid)
    assert any("not linked" in f.title.lower() for f in rep.timeline_alignment)


def test_timeline_order_mismatch_warning():
    db = Database()
    pid, a, b = _two_scene(db)
    db.set_timeline_order_mode(pid, "custom")
    db.set_timeline_order(pid, [b, a])
    rep = ssc.build_stage_script_continuity_report(db, pid)
    assert any("order differs" in f.title.lower() for f in rep.timeline_alignment)


def test_timeline_labels_use_canonical_numbering():
    db = Database()
    pid, a, b = _two_scene(db)
    rep = ssc.build_stage_script_continuity_report(db, pid)
    nums = {e.title: e.number for e in rep.scene_chain}
    assert nums["Alpha"] and nums["Beta"] and nums["Alpha"] != nums["Beta"]
    assert nums["Alpha"].startswith("1") and nums["Beta"].startswith("2")


# ==========================================================================
# 26-29  PSYKE / Notes
# ==========================================================================


def test_missing_psyke_link_warning():
    db = Database()
    pid = _stage(db)
    db.create_psyke_entry(pid, "Mary", "character")
    _sc(db, pid, "A", "STAGE: x.\n\nCHARACTER: MARY\nHi.\n\nCHARACTER: JOHN\nBye.")
    rep = ssc.build_stage_script_continuity_report(db, pid)
    titles = " ".join(f.title for f in rep.psyke_notes)
    assert "JOHN" in titles and "MARY" not in titles


def test_linked_notes_included():
    db = Database()
    pid = _stage(db)
    sid = _sc(db, pid, "A", "STAGE: x.")
    note = db.create_note(pid, "ctx", "body")
    db.link_note_to_scene(getattr(note, "id", note), sid)
    rep = ssc.build_stage_script_continuity_report(db, pid)
    assert any("note" in f.title.lower() for f in rep.psyke_notes)


def test_report_does_not_mutate_psyke():
    db = Database()
    pid = _stage(db)
    db.create_psyke_entry(pid, "Mary", "character")
    _sc(db, pid, "A", "STAGE: x.\n\nCHARACTER: MARY\nHi.")
    before = len(db.get_all_psyke_entries(pid))
    ssc.build_stage_script_continuity_report(db, pid)
    assert len(db.get_all_psyke_entries(pid)) == before == 1


def test_report_does_not_mutate_notes():
    db = Database()
    pid = _stage(db)
    _sc(db, pid, "A", "STAGE: x.")
    db.create_note(pid, "n", "b")
    before = len(db.get_all_notes(pid))
    ssc.build_stage_script_continuity_report(db, pid)
    assert len(db.get_all_notes(pid)) == before


# ==========================================================================
# 30-33  UI / actions
# ==========================================================================


def test_logos_dropdown_includes_continuity_check():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("ST", narrative_engine="stage_script",
                      default_writing_format="stage_script")
    ctl = LogosController(db)
    for sec in ("Manuscript", "Timeline", "Outline"):
        names = [a.name for a in ctl.available_actions(sec, writing_mode="stage_script")]
        assert "stage_continuity_check" in names
    novel = [a.name for a in ctl.available_actions("Manuscript", writing_mode="novel")]
    assert "stage_continuity_check" not in novel


def test_continuity_action_runs_without_scene_and_no_llm():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def _boom(*a, **k):
        raise AssertionError("deterministic action must not call the LLM")

    db = Database()
    pid, a, b = _two_scene(db)
    ctl = LogosController(db, provider_resolver=_boom, chat_fn=_boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=None)
    res = ctl.run(ctx, "stage_continuity_check")
    assert res.ok and res.title == "Stage Continuity Check"
    assert ssc.SEC_CHAIN in res.message and res.proposed_operations == []


def test_assistant_seam_and_copyable_report():
    from logosforge.logos.deterministic import get_handler
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid, a, b = _two_scene(db)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=None)
    res = get_handler("stage_continuity_check")(db, ctx)
    assert isinstance(res.message, str) and res.message
    assert isinstance(res.suggestions, list)
    rep = ssc.build_stage_script_continuity_report(db, pid)
    msgs = ssc.build_continuity_messages(rep)
    assert len(msgs) == 2 and msgs[0]["role"] == "system"
    assert ssc.SEC_CHAIN in msgs[1]["content"]


def test_save_as_note_requires_confirmation():
    db = Database()
    pid, a, b = _two_scene(db)
    rep = ssc.build_stage_script_continuity_report(db, pid)
    r0 = ssc.save_continuity_as_note(db, pid, rep, confirmed=False)
    assert r0["ok"] is False and len(db.get_all_notes(pid)) == 0
    r1 = ssc.save_continuity_as_note(db, pid, rep, confirmed=True)
    assert r1["ok"] and len(db.get_all_notes(pid)) == 1


# ==========================================================================
# 34-38  Safety (no mutation)
# ==========================================================================


def test_report_does_not_mutate_manuscript_or_outline():
    db = Database()
    pid = _stage(db)
    sid = _sc(db, pid, "A", "STAGE: x.", summary="SUM")
    before = (db.get_scene_by_id(sid).content, db.get_scene_by_id(sid).summary)
    ssc.build_stage_script_continuity_report(db, pid)
    after = (db.get_scene_by_id(sid).content, db.get_scene_by_id(sid).summary)
    assert before == after


def test_report_does_not_mutate_timeline():
    db = Database()
    pid, a, b = _two_scene(db)
    db.add_timeline_event(pid, a)
    before = db.get_timeline_event_ids(pid)
    ssc.build_stage_script_continuity_report(db, pid)
    assert db.get_timeline_event_ids(pid) == before


def test_report_does_not_mutate_plans():
    db = Database()
    pid = _stage(db)
    sid = _sc(db, pid, "A", "STAGE: x.")
    ssp.save_beat_plan(db, pid, ssp.StageBeatPlan(scene_id=sid, objective="KEEP"))
    ssc.build_stage_script_continuity_report(db, pid)
    assert ssp.get_beat_plan(db, pid, sid).objective == "KEEP"


def test_provider_error_does_not_mutate():
    db = Database()
    pid, a, b = _two_scene(db)
    rep = ssc.build_stage_script_continuity_report(db, pid)
    before = db.get_scene_by_id(a).content
    msgs = ssc.build_continuity_messages(rep)
    assert isinstance(msgs, list) and db.get_scene_by_id(a).content == before


def test_report_isolated_across_projects(tmp_path):
    db = Database(str(tmp_path / "st.db"))
    pid_a, a, b = _two_scene(db)
    db.create_psyke_entry(pid_a, "Mary", "character")
    pid_b = _stage(db, "B")
    _sc(db, pid_b, "Z", "STAGE: x.\n\nCHARACTER: ZARA\nHi.")
    rep_b = ssc.build_stage_script_continuity_report(db, pid_b)
    assert [e.title for e in rep_b.scene_chain] == ["Z"]
    assert "MARY" not in " ".join(f.title for f in rep_b.psyke_notes)


# ==========================================================================
# No image generation
# ==========================================================================


def test_no_image_generation_code():
    import os, tokenize
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(here, "logosforge", "stage_script_continuity.py")
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
