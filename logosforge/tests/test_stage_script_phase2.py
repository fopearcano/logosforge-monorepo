"""Stage Script Mode — Phase 2 acceptance suite.

Planning pipeline: Outline summary -> Stage Beat Plan -> Blocking/Cue Plan ->
stage-script draft preview -> confirmed apply. Plans are stored separately from
the body; the AI never overwrites the Manuscript — apply requires confirmation,
touches only Scene.content, and preserves Outline/plans/Timeline/PSYKE/Notes.
No image generation.
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


def _scene(db, pid, content="", *, title="S", summary="s", act="Act I",
           chapter="Chapter 1"):
    return ss.create_scene(db, pid, act=act, chapter=chapter, title=title,
                           content=content, summary=summary).id


_DRAFT = (
    "SCENE: The Throne Room\n\n"
    "STAGE: A bare room. Evening light fades.\n\n"
    "CHARACTER: MARIA\n(softly)\nIt ends now.\n\n"
    "ENTER: John enters from stage left.\n\n"
    "LIGHT: Lights dim to blue."
)


# ==========================================================================
# 1-6  Stage Beat Plan
# ==========================================================================


def test_beat_plan_prompt_uses_summary():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, summary="Maria confronts the king")
    prompt = ssp.build_beat_plan_prompt(db, pid, sid)
    assert "Maria confronts the king" in prompt


def test_beat_plan_stored_separately_from_body():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, content="", summary="intent")
    ssp.save_beat_plan(db, pid, ssp.StageBeatPlan(scene_id=sid, objective="win"))
    assert db.get_scene_by_id(sid).content == ""          # body untouched
    assert ssp.get_beat_plan(db, pid, sid).objective == "win"


def test_accept_beat_plan_stores_it():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    plan = ssp.parse_beat_plan_response(
        "Objective: stop the duel\nConflict: pride vs love\n"
        "Dialogue Beats:\n- the plea\n- the refusal", scene_id=sid)
    ssp.save_beat_plan(db, pid, plan)
    got = ssp.get_beat_plan(db, pid, sid)
    assert got.objective == "stop the duel" and len(got.dialogue_beats) == 2


def test_discard_beat_plan_changes_nothing():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    ssp.parse_beat_plan_response("Objective: x", scene_id=sid)   # not saved
    assert ssp.get_beat_plan(db, pid, sid) is None
    assert ssp.has_beat_plan(db, pid, sid) is False


def test_beat_plan_project_bound():
    db = Database()
    a = _stage(db, "A")
    sid_a = _scene(db, a)
    b = _stage(db, "B")
    sid_b = _scene(db, b)
    ssp.save_beat_plan(db, a, ssp.StageBeatPlan(scene_id=sid_a, objective="A only"))
    assert ssp.get_beat_plan(db, a, sid_a).objective == "A only"
    assert ssp.get_beat_plan(db, b, sid_b) is None


def test_beat_plan_isolation_across_projects(tmp_path):
    db = Database(str(tmp_path / "st.db"))
    a = _stage(db, "A")
    sid_a = _scene(db, a)
    ssp.save_beat_plan(db, a, ssp.StageBeatPlan(scene_id=sid_a,
                                                objective="SENTINEL_A"))
    b = _stage(db, "B")
    assert ssp.get_beat_plan(db, b, sid_a) is None        # no leak by scene id


# ==========================================================================
# 7-11  Blocking / Cue Plan
# ==========================================================================


def test_blocking_prompt_uses_beat_plan():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    ssp.save_beat_plan(db, pid, ssp.StageBeatPlan(scene_id=sid,
                                                  objective="seize the crown"))
    prompt = ssp.build_blocking_plan_prompt(db, pid, sid)
    assert "seize the crown" in prompt


def test_blocking_plan_stored_separately_from_body():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, content="")
    ssp.save_blocking_plan(db, pid, ssp.BlockingCuePlan(
        scene_id=sid, lighting_cues=["dim to blue"]))
    assert db.get_scene_by_id(sid).content == ""
    assert ssp.get_blocking_plan(db, pid, sid).lighting_cues == ["dim to blue"]


def test_accept_blocking_plan_stores_it():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    plan = ssp.parse_blocking_plan_response(
        "Staging Area: thrust stage\nLighting Cues:\n- spotlight up\n- fade",
        scene_id=sid)
    ssp.save_blocking_plan(db, pid, plan)
    got = ssp.get_blocking_plan(db, pid, sid)
    assert got.staging_area_notes == "thrust stage" and len(got.lighting_cues) == 2


def test_discard_blocking_plan_changes_nothing():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    ssp.parse_blocking_plan_response("Staging Area: x", scene_id=sid)   # not saved
    assert ssp.get_blocking_plan(db, pid, sid) is None


def test_blocking_plan_project_bound():
    db = Database()
    a = _stage(db, "A")
    sid_a = _scene(db, a)
    b = _stage(db, "B")
    ssp.save_blocking_plan(db, a, ssp.BlockingCuePlan(scene_id=sid_a,
                                                      set_notes="A set"))
    assert ssp.get_blocking_plan(db, a, sid_a).set_notes == "A set"
    assert ssp.get_blocking_plan(db, b, sid_a) is None


# ==========================================================================
# 12-16  Draft preview
# ==========================================================================


def test_draft_returns_valid_block_list():
    script = ssp.parse_draft_response(_DRAFT)
    kinds = {b.block_type for b in script.blocks}
    assert {ssb.BT_SCENE_HEADING, ssb.BT_STAGE_DIRECTION, ssb.BT_CHARACTER,
            ssb.BT_DIALOGUE, ssb.BT_ENTRANCE, ssb.BT_LIGHTING_CUE} <= kinds
    assert ssp.validate_draft_script(script).is_valid


def test_draft_preview_does_not_auto_apply():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, content="")
    script = ssp.parse_draft_response(_DRAFT)
    prev = ssp.preview_draft_apply(db, pid, sid, script, mode=ssp.APPLY_TO_EMPTY)
    assert prev is not None
    assert db.get_scene_by_id(sid).content == ""          # preview only


def test_invalid_draft_is_rejected():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, content="")
    empty = ssp.parse_draft_response("")
    assert ssp.validate_draft_script(empty).is_valid is False
    res = ssp.apply_draft(db, pid, sid, empty, mode=ssp.APPLY_TO_EMPTY,
                          confirmed=True)
    assert res["ok"] is False and db.get_scene_by_id(sid).content == ""


def test_provider_error_does_not_mutate():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, content="STAGE: existing.")
    # Simulate a failed/empty generation: empty draft -> invalid -> apply blocked.
    res = ssp.apply_draft(db, pid, sid, ssp.parse_draft_response(""),
                          mode=ssp.APPLY_REPLACE, confirmed=True)
    assert res["ok"] is False
    assert db.get_scene_by_id(sid).content == "STAGE: existing."


def test_markdown_fences_are_cleaned():
    script = ssp.parse_draft_response("```\nSCENE: Room\n\nSTAGE: A chair.\n```")
    v = ssp.validate_draft_script(script)
    assert v.is_valid
    assert "```" not in ssb.serialize_stage_script(script)


def test_system_prompt_leakage_is_rejected():
    script = ssp.parse_draft_response(
        "STAGE: As an AI language model, here is the script you requested.")
    assert ssp.validate_draft_script(script).is_valid is False


# ==========================================================================
# 17-26  Controlled apply
# ==========================================================================


def test_apply_to_empty_writes_blocks():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, content="")
    res = ssp.apply_draft(db, pid, sid, ssp.parse_draft_response(_DRAFT),
                          mode=ssp.APPLY_TO_EMPTY, confirmed=True)
    assert res["ok"]
    body = db.get_scene_by_id(sid).content
    assert "Throne Room" in body and "It ends now" in body


def test_replace_requires_confirmation():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, content="STAGE: original room.")
    res = ssp.apply_draft(db, pid, sid, ssp.parse_draft_response(_DRAFT),
                          mode=ssp.APPLY_REPLACE, confirmed=False)
    assert res["ok"] is False
    assert db.get_scene_by_id(sid).content == "STAGE: original room."


def test_cancel_leaves_body_unchanged():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, content="STAGE: original room.")
    res = ssp.apply_draft(db, pid, sid, ssp.parse_draft_response(_DRAFT),
                          mode=ssp.APPLY_CANCEL, confirmed=True)
    assert res.get("cancelled")
    assert db.get_scene_by_id(sid).content == "STAGE: original room."


def test_append_preserves_existing_body():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, content="STAGE: An original opening room.")
    res = ssp.apply_draft(db, pid, sid, ssp.parse_draft_response(_DRAFT),
                          mode=ssp.APPLY_APPEND, confirmed=True)
    assert res["ok"]
    body = db.get_scene_by_id(sid).content
    assert "original opening room" in body and "Throne Room" in body


def test_apply_marks_project_dirty():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, content="")
    from logosforge.project_events import get_event_bus
    fired = []
    get_event_bus().project_data_changed.connect(lambda *a: fired.append(1))
    ssp.apply_draft(db, pid, sid, ssp.parse_draft_response(_DRAFT),
                    mode=ssp.APPLY_TO_EMPTY, confirmed=True)
    assert fired


def test_apply_preserves_outline_summary():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, content="", summary="SUMMARY_KEPT")
    ssp.apply_draft(db, pid, sid, ssp.parse_draft_response(_DRAFT),
                    mode=ssp.APPLY_TO_EMPTY, confirmed=True)
    assert db.get_scene_by_id(sid).summary == "SUMMARY_KEPT"


def test_apply_preserves_plans_timeline_psyke_notes():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, content="")
    ssp.save_beat_plan(db, pid, ssp.StageBeatPlan(scene_id=sid, objective="KEEP"))
    db.add_timeline_event(pid, sid)
    db.create_psyke_entry(pid, "Maria", "character")
    db.create_note(pid, "n", "b")
    tl_before = db.get_timeline_event_ids(pid)
    psyke_before = len(db.get_all_psyke_entries(pid))
    notes_before = len(db.get_all_notes(pid))
    ssp.apply_draft(db, pid, sid, ssp.parse_draft_response(_DRAFT),
                    mode=ssp.APPLY_TO_EMPTY, confirmed=True)
    assert ssp.get_beat_plan(db, pid, sid).objective == "KEEP"
    assert db.get_timeline_event_ids(pid) == tl_before
    assert len(db.get_all_psyke_entries(pid)) == psyke_before
    assert len(db.get_all_notes(pid)) == notes_before


# ==========================================================================
# 27-31  Validation
# ==========================================================================


def test_dialogue_without_character_warning():
    v = ssp.validate_draft_script(ssp.parse_draft_response(
        "STAGE: A room.\n\nDIALOGUE: A line with no speaker."))
    assert any("no preceding character" in w.lower() for w in v.warnings)


def test_entrance_without_character_warning():
    v = ssp.validate_draft_script(ssp.parse_draft_response(
        "STAGE: A room.\n\nENTER:"))
    assert any("movement" in w.lower() or "character" in w.lower()
               for w in v.warnings)


def test_empty_cue_warning():
    v = ssp.validate_draft_script(ssp.parse_draft_response(
        "STAGE: A room.\n\nLIGHT:"))
    assert any("cue text" in w.lower() for w in v.warnings)


def test_too_many_dialogue_blocks_warning():
    body = ("CHARACTER: MARIA\n" + "\n".join(f"Line {i}." for i in range(1, 7)))
    v = ssp.validate_draft_script(ssp.parse_draft_response(body))
    assert any("row" in w.lower() for w in v.warnings)


def test_corrupt_structure_blocks_apply():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, content="STAGE: keep.")
    # An empty/corrupt draft fails validation and never reaches the body.
    res = ssp.apply_draft(db, pid, sid, ssb.StageScript(),
                          mode=ssp.APPLY_REPLACE, confirmed=True)
    assert res["ok"] is False and db.get_scene_by_id(sid).content == "STAGE: keep."


# ==========================================================================
# 32-35  Export
# ==========================================================================


def test_applied_blocks_export_as_markdown():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, content="")
    ssp.apply_draft(db, pid, sid, ssp.parse_draft_response(_DRAFT),
                    mode=ssp.APPLY_TO_EMPTY, confirmed=True)
    md = ssb.export_scene_markdown(db, pid, sid)
    assert "MARIA" in md and "It ends now" in md


def test_project_export_canonical_order():
    db = Database()
    pid = _stage(db)
    b = _scene(db, pid, content="STAGE: Beta room.", title="Beta",
               act="Act II", chapter="Chapter 2")
    a = _scene(db, pid, content="STAGE: Alpha room.", title="Alpha",
               act="Act I", chapter="Chapter 1")
    db.reorder_scenes(pid, [a, b])
    md = ssb.export_project_markdown(db, pid)
    assert md.index("Alpha room") < md.index("Beta room")


def test_export_uses_body_not_plan():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, content="STAGE: A room.")
    ssp.save_beat_plan(db, pid, ssp.StageBeatPlan(
        scene_id=sid, objective="PLAN_SENTINEL_OBJECTIVE"))
    md = ssb.export_project_markdown(db, pid)
    assert "A room" in md and "PLAN_SENTINEL_OBJECTIVE" not in md


def test_export_excludes_api_keys():
    db = Database()
    from logosforge.settings import get_manager
    get_manager().set("ai_api_key", "SECRET_KEY_SENTINEL")
    pid = _stage(db)
    _scene(db, pid, content="STAGE: A room.")
    assert "SECRET_KEY_SENTINEL" not in ssb.export_project_markdown(db, pid)


# ==========================================================================
# 36-39  Context / Logos
# ==========================================================================


def test_assistant_context_identifies_stage_and_scene():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, content="CHARACTER: MARIA\nHello.\n\nSTAGE: She waits.")
    assert "[Stage Script]" in ssb.stage_script_context(db, pid, sid)
    assert ssb.stage_script_context(db, pid, None) == ""        # needs a scene


def test_planning_context_includes_plans():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    assert ssp.stage_planning_context(db, pid, sid) == ""       # nothing yet
    ssp.save_beat_plan(db, pid, ssp.StageBeatPlan(scene_id=sid, objective="reach X"))
    ctx = ssp.stage_planning_context(db, pid, sid)
    assert "[Stage Plan]" in ctx and "reach X" in ctx


def test_logos_dropdown_includes_stage_planning_actions():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("ST", narrative_engine="stage_script",
                      default_writing_format="stage_script")
    names = [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="stage_script")]
    assert {"stage_beat_plan", "stage_blocking_plan", "stage_draft_scene"} <= set(names)
    novel = [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="novel")]
    assert not any(n.startswith("stage_") for n in novel)


def test_logos_generative_action_does_not_auto_apply():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, content="STAGE: keep this body.")
    ctl = LogosController(db, provider_resolver=lambda: object(),
                         chat_fn=lambda m, p: "Objective: do the thing")
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "stage_beat_plan")
    assert res.ok
    assert db.get_scene_by_id(sid).content == "STAGE: keep this body."


def test_logos_does_not_break_on_stage_blocks():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, content=_DRAFT)
    ctl = LogosController(db, provider_resolver=lambda: object(),
                         chat_fn=lambda m, p: "x")
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "stage_check")
    assert res.ok and res.proposed_operations == []
