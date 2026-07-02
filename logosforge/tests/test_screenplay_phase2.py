"""Screenplay Mode — Phase 2 acceptance suite (scene planning pipeline).

Covers the deterministic core of:

    Outline scene summary → Beat Plan → screenplay draft preview → confirmed apply

The safety contract is the point of these tests: the beat plan is a *separate*
artifact (never the body or the summary), generation only ever previews, and the
draft reaches ``Scene.content`` **only** through Controlled Apply with explicit
confirmation. The AI never auto-overwrites the Manuscript body.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge import context_builder as cb
from logosforge import screenplay_pipeline as spp
from logosforge.screenplay_blocks import ScreenplayBlock, serialize_blocks


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


def _screenplay(db):
    return db.create_project("S", narrative_engine="screenplay",
                             default_writing_format="screenplay").id


def _novel(db):
    return db.create_project("N", narrative_engine="novel").id


def _scene(db, pid, *, summary="", content=""):
    return ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="S",
                           summary=summary, content=content).id


_SAMPLE_PLAN_TEXT = (
    "Objective: get the truth\n"
    "Dramatic Question: will she confess?\n"
    "Conflict: mentor stonewalls\n"
    "Turning Point: a slip reveals the lie\n"
    "Emotional Shift: hope to dread\n"
    "Visual Beats:\n- she places the photo on the table\n- he refuses to look\n"
    "Dialogue Intentions:\n- corner him without accusing\n"
    "Continuity Notes: callback to the locket"
)

_GOOD_DRAFT = (
    "INT. KITCHEN - NIGHT\n\n"
    "She places the photo on the table.\n\n"
    "MENTOR\n(quietly)\nI have nothing to say.\n\n"
    "CUT TO:"
)


# ==========================================================================
# 1  Beat plan model
# ==========================================================================


def test_beat_plan_is_empty_and_roundtrips():
    assert spp.ScreenplayBeatPlan().is_empty()
    plan = spp.parse_beat_plan_response(_SAMPLE_PLAN_TEXT, scene_id=7)
    assert not plan.is_empty()
    back = spp.ScreenplayBeatPlan.from_dict(plan.to_dict())
    assert back.objective == "get the truth"
    assert back.visual_beats == ["she places the photo on the table",
                                 "he refuses to look"]
    assert back.dialogue_intentions == ["corner him without accusing"]
    assert back.scene_id == 7


def test_beat_plan_to_text_omits_empty_fields():
    plan = spp.ScreenplayBeatPlan(objective="x")
    text = plan.to_text()
    assert text == "Objective: x"


# ==========================================================================
# 2  Settings storage — separate from body & summary, isolated per project
# ==========================================================================


def test_save_get_clear_beat_plan_separate_from_body_and_summary():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, summary="OUTLINE SUMMARY", content="REAL BODY")
    plan = spp.parse_beat_plan_response(_SAMPLE_PLAN_TEXT, scene_id=sid)
    spp.save_beat_plan(db, pid, plan)

    got = spp.get_beat_plan(db, pid, sid)
    assert got is not None and got.objective == "get the truth"
    # The beat plan must NOT touch body or summary.
    after = db.get_scene_by_id(sid)
    assert after.content == "REAL BODY"
    assert after.summary == "OUTLINE SUMMARY"
    assert spp.has_beat_plan(db, pid, sid)

    assert spp.clear_beat_plan(db, pid, sid) is True
    assert spp.get_beat_plan(db, pid, sid) is None
    assert spp.has_beat_plan(db, pid, sid) is False


def test_save_preserves_created_at_and_bumps_updated_at():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, summary="s")
    p1 = spp.save_beat_plan(
        db, pid, spp.ScreenplayBeatPlan(scene_id=sid, objective="a"))
    p2 = spp.save_beat_plan(
        db, pid, spp.ScreenplayBeatPlan(scene_id=sid, objective="b"))
    assert p2.created_at == p1.created_at      # stable
    assert p2.updated_at >= p1.updated_at      # advances (>= for fast clocks)


def test_beat_plans_do_not_leak_across_projects(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    a = _screenplay(db)
    sid_a = _scene(db, a, summary="s")
    spp.save_beat_plan(db, a, spp.ScreenplayBeatPlan(scene_id=sid_a, objective="A-ONLY"))
    b = _screenplay(db)
    assert spp.all_beat_plans(db, b) == {}
    assert spp.get_beat_plan(db, b, sid_a) is None


# ==========================================================================
# 3  Prompt builders — deterministic, grounded in summary/plan
# ==========================================================================


def test_beat_plan_prompt_uses_summary_and_template():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, summary="Hero confronts mentor")
    prompt = spp.build_beat_plan_prompt(db, pid, sid)
    assert "Hero confronts mentor" in prompt
    assert "Objective:" in prompt                 # labelled template requested
    assert "Screenplay" in prompt                 # mode block present


def test_draft_prompt_uses_beat_plan():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, summary="s")
    spp.save_beat_plan(db, pid, spp.parse_beat_plan_response(_SAMPLE_PLAN_TEXT, sid))
    prompt = spp.build_draft_prompt(db, pid, sid)
    assert "get the truth" in prompt              # plan carried into the prompt
    assert "screenplay" in prompt.lower()


# ==========================================================================
# 4  Parsers — tolerant beat plan, conservative draft, fence-stripping
# ==========================================================================


def test_parse_beat_plan_handles_bullets_and_fences():
    text = "```\nObjective: win\nVisual Beats:\n* a\n* b\n```"
    plan = spp.parse_beat_plan_response(text)
    assert plan.objective == "win"
    assert plan.visual_beats == ["a", "b"]


def test_parse_beat_plan_ignores_unlabelled_prose():
    plan = spp.parse_beat_plan_response("Just some rambling with no labels.")
    assert plan.is_empty()


def test_parse_draft_strips_fountain_fence_and_classifies():
    blocks = spp.parse_draft_blocks("```fountain\n" + _GOOD_DRAFT + "\n```")
    kinds = [b.element_type for b in blocks]
    assert kinds == ["scene_heading", "action", "character",
                     "parenthetical", "dialogue", "transition"]


# ==========================================================================
# 5  Deterministic validation — errors block, warnings allow
# ==========================================================================


def test_validation_passes_clean_draft():
    v = spp.validate_draft_blocks(spp.parse_draft_blocks(_GOOD_DRAFT))
    assert v.is_valid and not v.errors


def test_validation_blocks_empty():
    assert not spp.validate_draft_blocks([]).is_valid


def test_validation_blocks_leaked_beat_plan():
    v = spp.validate_draft_blocks([ScreenplayBlock("action", "Objective: get the truth")])
    assert not v.is_valid
    assert any("beat plan" in e.lower() for e in v.errors)


def test_validation_blocks_markdown_and_commentary():
    fence = spp.validate_draft_blocks([ScreenplayBlock("action", "```")])
    assert not fence.is_valid
    chat = spp.validate_draft_blocks(
        [ScreenplayBlock("action", "Sure, here is the screenplay you asked for.")])
    assert not chat.is_valid


def test_validation_warns_but_allows_orphans_and_missing_heading():
    # Dialogue with no heading and no character cue: warnings, still valid.
    blocks = [ScreenplayBlock("dialogue", "Hello there.")]
    v = spp.validate_draft_blocks(blocks)
    assert v.is_valid
    assert v.warnings
    # Opt-in hard requirement turns the missing heading into an error.
    strict = spp.validate_draft_blocks(blocks, require_scene_heading=True)
    assert not strict.is_valid


# ==========================================================================
# 6  Apply-mode gate
# ==========================================================================


def test_resolve_apply_mode_empty_body():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, content="")
    assert spp.resolve_apply_mode(db, pid, sid, spp.APPLY_TO_EMPTY) == ("replace", False, "")
    assert spp.resolve_apply_mode(db, pid, sid, spp.APPLY_REPLACE) == ("replace", False, "")
    assert spp.resolve_apply_mode(db, pid, sid, spp.APPLY_APPEND) == ("append", False, "")


def test_resolve_apply_mode_non_empty_body():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, content="EXISTING")
    mode, confirm, err = spp.resolve_apply_mode(db, pid, sid, spp.APPLY_TO_EMPTY)
    assert mode == "" and err and "not empty" in err          # refused
    mode, confirm, err = spp.resolve_apply_mode(db, pid, sid, spp.APPLY_REPLACE)
    assert mode == "replace" and confirm is True and not err   # replace needs confirm
    mode, confirm, err = spp.resolve_apply_mode(db, pid, sid, spp.APPLY_APPEND)
    assert mode == "append" and not err


# ==========================================================================
# 7  Preview — no mutation
# ==========================================================================


def test_preview_draft_apply_does_not_mutate():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, content="ORIGINAL")
    blocks = spp.parse_draft_blocks(_GOOD_DRAFT)
    preview = spp.preview_draft_apply(db, pid, sid, blocks, mode=spp.APPLY_REPLACE)
    assert preview is not None
    assert "KITCHEN" in preview.after_text          # diff computed
    assert db.get_scene_by_id(sid).content == "ORIGINAL"   # but body untouched


# ==========================================================================
# 8  Apply — AI never auto-overwrites; confirm required; modes behave
# ==========================================================================


def test_apply_draft_refused_without_confirmation():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, content="")
    blocks = spp.parse_draft_blocks(_GOOD_DRAFT)
    res = spp.apply_draft(db, pid, sid, blocks, mode=spp.APPLY_REPLACE, confirmed=False)
    assert res["ok"] is False                         # AI cannot apply on its own
    assert db.get_scene_by_id(sid).content == ""      # body never written


def test_apply_draft_to_empty_writes_body_on_confirm():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, content="")
    blocks = spp.parse_draft_blocks(_GOOD_DRAFT)
    res = spp.apply_draft(db, pid, sid, blocks, mode=spp.APPLY_TO_EMPTY, confirmed=True)
    assert res["ok"] is True
    assert "KITCHEN" in db.get_scene_by_id(sid).content


def test_apply_to_empty_refuses_non_empty_body():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, content="REAL BODY")
    blocks = spp.parse_draft_blocks(_GOOD_DRAFT)
    res = spp.apply_draft(db, pid, sid, blocks, mode=spp.APPLY_TO_EMPTY, confirmed=True)
    assert res["ok"] is False
    assert db.get_scene_by_id(sid).content == "REAL BODY"   # protected


def test_apply_replace_overwrites_only_on_confirm():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, content="OLD BODY")
    blocks = spp.parse_draft_blocks(_GOOD_DRAFT)
    res = spp.apply_draft(db, pid, sid, blocks, mode=spp.APPLY_REPLACE, confirmed=True)
    assert res["ok"] is True
    body = db.get_scene_by_id(sid).content
    assert "KITCHEN" in body and "OLD BODY" not in body


def test_apply_append_keeps_existing_body():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, content="KEEP ME")
    blocks = spp.parse_draft_blocks(_GOOD_DRAFT)
    res = spp.apply_draft(db, pid, sid, blocks, mode=spp.APPLY_APPEND, confirmed=True)
    assert res["ok"] is True
    body = db.get_scene_by_id(sid).content
    assert body.startswith("KEEP ME") and "KITCHEN" in body


def test_apply_cancel_is_noop():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, content="BODY")
    res = spp.apply_draft(db, pid, sid, spp.parse_draft_blocks(_GOOD_DRAFT),
                          mode=spp.APPLY_CANCEL, confirmed=True)
    assert res["ok"] is False and res.get("cancelled")
    assert db.get_scene_by_id(sid).content == "BODY"


def test_apply_invalid_draft_is_blocked():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, content="")
    bad = [ScreenplayBlock("action", "Objective: leaked plan")]
    res = spp.apply_draft(db, pid, sid, bad, mode=spp.APPLY_TO_EMPTY, confirmed=True)
    assert res["ok"] is False and "validation" in res
    assert db.get_scene_by_id(sid).content == ""


# ==========================================================================
# 9  Assistant / Logos context
# ==========================================================================


def test_beat_plan_context_only_for_screenplay_with_plan():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, summary="s")
    assert spp.beat_plan_context(db, pid, sid) == ""        # no plan yet
    spp.save_beat_plan(db, pid, spp.ScreenplayBeatPlan(scene_id=sid, objective="WIN"))
    ctx = spp.beat_plan_context(db, pid, sid)
    assert "[Beat Plan]" in ctx and "WIN" in ctx


def test_beat_plan_context_empty_for_novel():
    db = Database()
    pid = _novel(db)
    sid = _scene(db, pid, content="x")
    # Even if a plan dict somehow existed, novel mode yields no beat-plan block.
    spp.save_beat_plan(db, pid, spp.ScreenplayBeatPlan(scene_id=sid, objective="X"))
    assert spp.beat_plan_context(db, pid, sid) == ""


def test_scene_context_includes_beat_plan_for_screenplay():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, summary="intent", content="body")
    spp.save_beat_plan(db, pid, spp.ScreenplayBeatPlan(scene_id=sid, objective="WIN THE DUEL"))
    ctx = cb.gather_scene_context(db, pid, sid)
    assert "[Beat Plan]" in ctx and "WIN THE DUEL" in ctx


def test_scene_context_no_beat_plan_for_novel():
    db = Database()
    pid = _novel(db)
    sid = _scene(db, pid, content="body")
    ctx = cb.gather_scene_context(db, pid, sid)
    assert "[Beat Plan]" not in ctx


# ==========================================================================
# 10  Preview/confirm dialogs (no mutation; correct gating)
# ==========================================================================


def test_beat_plan_dialog_returns_edited_text_on_save():
    from logosforge.ui.screenplay_pipeline_dialogs import BeatPlanPreviewDialog
    dlg = BeatPlanPreviewDialog("Objective: x", title="S")
    dlg._on_save()
    assert dlg.result_text() == "Objective: x"


def test_beat_plan_dialog_rejects_empty():
    from logosforge.ui.screenplay_pipeline_dialogs import BeatPlanPreviewDialog
    dlg = BeatPlanPreviewDialog("   ")
    dlg._on_save()                     # empty -> no result, dialog stays open
    assert dlg.result_text() is None


def test_draft_dialog_apply_to_empty_gated_by_body():
    from logosforge.ui.screenplay_pipeline_dialogs import DraftPreviewDialog
    v = spp.validate_draft_blocks(spp.parse_draft_blocks(_GOOD_DRAFT))
    empty = DraftPreviewDialog(_GOOD_DRAFT, v, body_is_empty=True)
    assert empty._apply_empty_btn.isEnabled() is True
    nonempty = DraftPreviewDialog(_GOOD_DRAFT, v, body_is_empty=False)
    assert nonempty._apply_empty_btn.isEnabled() is False


def test_draft_dialog_disables_apply_on_invalid():
    from logosforge.ui.screenplay_pipeline_dialogs import DraftPreviewDialog
    bad = spp.validate_draft_blocks([])
    dlg = DraftPreviewDialog("", bad, body_is_empty=True)
    assert not dlg._append_btn.isEnabled()
    assert not dlg._replace_btn.isEnabled()
    assert not dlg._apply_empty_btn.isEnabled()


def test_draft_dialog_returns_mode_and_text():
    from logosforge.ui.screenplay_pipeline_dialogs import DraftPreviewDialog
    v = spp.validate_draft_blocks(spp.parse_draft_blocks(_GOOD_DRAFT))
    dlg = DraftPreviewDialog(_GOOD_DRAFT, v, body_is_empty=True)
    dlg._choose(spp.APPLY_APPEND)
    assert dlg.chosen_mode() == spp.APPLY_APPEND
    assert "KITCHEN" in dlg.draft_text()


# ==========================================================================
# 11  UI hook points are mode-gated (no rewrite of Manuscript/Outline)
# ==========================================================================


def test_plan_view_screenplay_mode_flag(tmp_path):
    from logosforge.ui.plan_view import PlanView
    db = Database(str(tmp_path / "sp.db"))
    pid = _screenplay(db)
    _scene(db, pid, summary="s")
    view = PlanView(db, pid)
    assert view._is_screenplay_mode() is True
    assert hasattr(view, "_generate_beat_plan")


def test_plan_view_novel_mode_flag(tmp_path):
    from logosforge.ui.plan_view import PlanView
    db = Database(str(tmp_path / "n.db"))
    pid = _novel(db)
    _scene(db, pid, content="x")
    assert PlanView(db, pid)._is_screenplay_mode() is False


def test_manuscript_editor_screenplay_flag_set(tmp_path):
    from logosforge.ui.writing_core_view import WritingCoreView
    db = Database(str(tmp_path / "sp.db"))
    pid = _screenplay(db)
    _scene(db, pid, content="INT. X - DAY\n\nAction.")
    view = WritingCoreView(db, pid, structured_list=True)
    assert view._is_screenplay_mode() is True
    editor = next(iter(view._editors.values()))
    assert editor._screenplay_mode is True
    assert editor._on_draft_from_beat_plan is not None


def test_manuscript_editor_no_draft_hook_in_novel(tmp_path):
    from logosforge.ui.writing_core_view import WritingCoreView
    db = Database(str(tmp_path / "n.db"))
    pid = _novel(db)
    _scene(db, pid, content="prose body")
    view = WritingCoreView(db, pid, structured_list=True)
    assert view._is_screenplay_mode() is False
    editor = next(iter(view._editors.values()))
    assert editor._screenplay_mode is False
