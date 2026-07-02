"""Phase 10O — Guided Workflows / Project Operating System."""

from __future__ import annotations

import warnings

import pytest

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.guided_workflows import (
    advance_workflow_step,
    build_workflow_recommendations,
    cancel_workflow,
    complete_workflow_step,
    get_active_workflows,
    get_all_workflows,
    get_template,
    get_workflow_run_view,
    list_workflow_templates,
    pause_workflow,
    refresh_workflow_run,
    resume_workflow,
    skip_workflow_step,
    start_workflow,
    workflow_status_summary,
)
from logosforge.guided_workflows.models import KIND_CHECK, KIND_CREATIVE


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path, raising=False)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json",
                        raising=False)
    import logosforge.gomckee_bridge as gb
    monkeypatch.setattr(gb, "is_gomckee_enabled", lambda: False)
    yield
    settings._instance = None


def _novel():
    db = Database()
    pid = db.create_project("My Novel", narrative_engine="novel").id
    return db, pid


def _screenplay():
    db = Database()
    pid = db.create_project("My Script", narrative_engine="screenplay").id
    return db, pid


# ===========================================================================
# Templates + registry (mode awareness)
# ===========================================================================


def test_templates_a_to_h_present():
    ids = {t.id for t in list_workflow_templates(None)}
    expected = {
        "project_setup", "psyke_story_bible", "classical_outline",
        "scene_drafting", "rewrite", "screenplay_production_prep",
        "export_readiness", "decision_radar_fix",
    }
    assert expected <= ids


def test_production_prep_is_screenplay_only():
    novel_ids = {t.id for t in list_workflow_templates("novel")}
    sp_ids = {t.id for t in list_workflow_templates("screenplay")}
    assert "screenplay_production_prep" not in novel_ids
    assert "screenplay_production_prep" in sp_ids


def test_get_template_unknown_returns_none():
    assert get_template("nope") is None


def test_template_steps_serializable():
    tpl = get_template("project_setup")
    d = tpl.to_dict()
    assert d["id"] == "project_setup" and d["steps"]
    assert all("completion_check" in s for s in d["steps"])


# ===========================================================================
# Engine lifecycle
# ===========================================================================


def test_start_workflow_creates_state():
    db, pid = _novel()
    v = start_workflow(db, pid, "project_setup")
    assert v is not None
    assert v.run.status == "active"
    assert v.total_steps == 4
    assert v.current_step.step_id == "title"
    assert v.steps[0].status == "active"
    assert all(s.status == "pending" for s in v.steps[1:])


def test_start_unknown_template_returns_none():
    db, pid = _novel()
    assert start_workflow(db, pid, "does_not_exist") is None


def test_start_mode_excluded_template_returns_none():
    db, pid = _novel()  # novel
    assert start_workflow(db, pid, "screenplay_production_prep") is None


def test_screenplay_can_start_production_prep():
    db, pid = _screenplay()
    v = start_workflow(db, pid, "screenplay_production_prep")
    assert v is not None and v.run.writing_mode == "screenplay"


def test_complete_step_advances_pointer():
    db, pid = _novel()
    v = start_workflow(db, pid, "project_setup")
    rid = v.run.id
    v = complete_workflow_step(db, rid, "title", notes="done")
    assert v.completed_steps == 1
    # pointer moves to next open step
    assert v.current_step.step_id == "logline"


def test_skip_step_counts_as_resolved():
    db, pid = _novel()
    v = start_workflow(db, pid, "project_setup")
    v = skip_workflow_step(db, v.run.id, "logline")
    skipped = [s for s in v.steps if s.step_id == "logline"][0]
    assert skipped.status == "skipped"


def test_completing_all_steps_completes_run():
    db, pid = _novel()
    v = start_workflow(db, pid, "project_setup")
    rid = v.run.id
    for s in list(v.steps):
        v = complete_workflow_step(db, rid, s.step_id)
    assert v.run.status == "completed"
    assert v.is_complete
    assert v.run.completed_at is not None


def test_advance_without_completing():
    db, pid = _novel()
    v = start_workflow(db, pid, "scene_drafting")
    assert v.current_step.step_id == "draft"
    v = advance_workflow_step(db, v.run.id)
    # draft (creative) is not completed, just deferred; pointer moved on
    assert v.current_step.step_id != "draft"
    draft = [s for s in v.steps if s.step_id == "draft"][0]
    assert draft.status in ("pending", "active")


def test_pause_resume_cancel():
    db, pid = _novel()
    v = start_workflow(db, pid, "project_setup")
    rid = v.run.id
    v = pause_workflow(db, rid)
    assert v.run.status == "paused"
    assert len(get_active_workflows(db, pid)) == 1  # paused still "active-ish"
    v = resume_workflow(db, rid)
    assert v.run.status == "active"
    v = cancel_workflow(db, rid)
    assert v.run.status == "cancelled"
    assert len(get_active_workflows(db, pid)) == 0


def test_resume_completed_is_noop():
    db, pid = _novel()
    v = start_workflow(db, pid, "project_setup")
    rid = v.run.id
    for s in list(v.steps):
        complete_workflow_step(db, rid, s.step_id)
    v = resume_workflow(db, rid)
    assert v.run.status == "completed"


# ===========================================================================
# Deterministic completion checks (never auto-complete creative steps)
# ===========================================================================


def test_refresh_auto_completes_verifiable_step():
    db, pid = _novel()
    db.create_scene(pid, "S0", content="word " * 10, summary="x")
    v = start_workflow(db, pid, "project_setup")
    rid = v.run.id
    # title check should pass (project already titled) and first_scenes too
    v = refresh_workflow_run(db, rid)
    statuses = {s.step_id: s.status for s in v.steps}
    assert statuses["title"] == "completed"
    assert statuses["first_scenes"] == "completed"
    # 'mode' is a manual step with no check — must stay open
    assert statuses["mode"] in ("pending", "active")


def test_refresh_never_completes_creative_step():
    db, pid = _novel()
    db.create_scene(pid, "S0", content="word " * 10, summary="x")
    v = start_workflow(db, pid, "scene_drafting")
    rid = v.run.id
    v = refresh_workflow_run(db, rid)
    draft = [s for s in v.steps if s.step_id == "draft"][0]
    # 'draft' is creative — even with content present it is never auto-done
    assert draft.status in ("pending", "active")
    # but the 'summary' check step auto-completes (scene has a summary)
    summary = [s for s in v.steps if s.step_id == "summary"][0]
    assert summary.status == "completed"


def test_refresh_does_not_complete_when_check_fails():
    db, pid = _novel()
    db.create_scene(pid, "S0", content="word " * 10, summary="")  # no summary
    v = start_workflow(db, pid, "classical_outline")
    rid = v.run.id
    v = refresh_workflow_run(db, rid)
    summaries = [s for s in v.steps if s.step_id == "summaries"][0]
    assert summaries.status in ("pending", "active")


def test_check_step_completion_returns_none_for_creative():
    from logosforge.guided_workflows import check_step_completion
    from logosforge.project_intelligence import build_project_intelligence_report
    db, pid = _novel()
    v = start_workflow(db, pid, "scene_drafting")
    tpl = get_template("scene_drafting")
    report = build_project_intelligence_report(db, pid)
    draft = [s for s in v.steps if s.step_id == "draft"][0]
    assert check_step_completion(report, tpl, draft) is None


# ===========================================================================
# Recommendations (from Decision Radar, deterministic)
# ===========================================================================


def test_recommendations_for_empty_project():
    db, pid = _novel()
    recs = build_workflow_recommendations(db, pid)
    ids = [r.template_id for r in recs]
    assert "project_setup" in ids


def test_recommendations_only_offer_mode_valid_templates():
    db, pid = _novel()
    recs = build_workflow_recommendations(db, pid)
    assert "screenplay_production_prep" not in [r.template_id for r in recs]


def test_recommendations_capped():
    db, pid = _novel()
    recs = build_workflow_recommendations(db, pid, cap=2)
    assert len(recs) <= 2


# ===========================================================================
# Persistence / events / isolation
# ===========================================================================


def test_events_recorded():
    db, pid = _novel()
    v = start_workflow(db, pid, "project_setup")
    rid = v.run.id
    complete_workflow_step(db, rid, "title")
    events = db.get_workflow_events(rid)
    types = {e.event_type for e in events}
    assert "started" in types and "step_completed" in types


def test_runs_isolated_by_project():
    db, pid_a = _novel()
    pid_b = db.create_project("Other", narrative_engine="novel").id
    start_workflow(db, pid_a, "project_setup")
    assert len(get_active_workflows(db, pid_a)) == 1
    assert len(get_active_workflows(db, pid_b)) == 0


def test_get_all_workflows_includes_finished():
    db, pid = _novel()
    v = start_workflow(db, pid, "project_setup")
    cancel_workflow(db, v.run.id)
    assert len(get_all_workflows(db, pid)) == 1
    assert len(get_active_workflows(db, pid)) == 0


def test_status_summary_text():
    db, pid = _novel()
    assert workflow_status_summary(db, pid) == "No active guided workflows."
    start_workflow(db, pid, "project_setup")
    assert "Project Setup" in workflow_status_summary(db, pid)


# ===========================================================================
# Engine never mutates project content
# ===========================================================================


def test_engine_does_not_mutate_project_content():
    db, pid = _novel()
    db.create_scene(pid, "S0", content="hello world", summary="s")
    db.create_psyke_entry(pid, "Alice", "character")
    before = (
        [(s.content, s.summary) for s in db.get_all_scenes(pid)],
        len(db.get_all_psyke_entries(pid)),
    )
    v = start_workflow(db, pid, "scene_drafting")
    rid = v.run.id
    complete_workflow_step(db, rid, "draft")
    refresh_workflow_run(db, rid)
    skip_workflow_step(db, rid, "continuity")
    after = (
        [(s.content, s.summary) for s in db.get_all_scenes(pid)],
        len(db.get_all_psyke_entries(pid)),
    )
    assert before == after


# ===========================================================================
# Logos actions (deterministic, read-only)
# ===========================================================================


def test_logos_wf_actions_deterministic():
    from logosforge.logos.deterministic import is_deterministic
    assert is_deterministic("wf_active_workflows")
    assert is_deterministic("wf_recommend_workflows")


def test_logos_wf_active_workflows():
    from logosforge.logos.context import build_logos_context
    from logosforge.logos.deterministic import get_handler
    db, pid = _novel()
    start_workflow(db, pid, "classical_outline")
    ctx = build_logos_context(db, pid, section_name="Manuscript")
    res = get_handler("wf_active_workflows")(db, ctx)
    assert res.ok and "Classical Outline" in res.message


def test_logos_wf_active_workflows_empty():
    from logosforge.logos.context import build_logos_context
    from logosforge.logos.deterministic import get_handler
    db, pid = _novel()
    ctx = build_logos_context(db, pid, section_name="Manuscript")
    res = get_handler("wf_active_workflows")(db, ctx)
    assert res.ok and "No active" in res.message


def test_logos_wf_recommend():
    from logosforge.logos.context import build_logos_context
    from logosforge.logos.deterministic import get_handler
    db, pid = _novel()
    ctx = build_logos_context(db, pid, section_name="Manuscript")
    res = get_handler("wf_recommend_workflows")(db, ctx)
    assert res.ok


def test_logos_explain_step_is_generative():
    from logosforge.logos.actions import get_action
    act = get_action("wf_explain_next_step")
    assert act is not None and not act.deterministic


# ===========================================================================
# Assistant context block (gated, only when active)
# ===========================================================================


def test_assistant_block_absent_without_active_workflow():
    from logosforge.assistant_context_policy import _guided_workflow_block
    db, pid = _novel()
    assert _guided_workflow_block(db, pid) == ""


def test_assistant_block_present_when_active():
    from logosforge.assistant_context_policy import _guided_workflow_block
    db, pid = _novel()
    start_workflow(db, pid, "project_setup")
    block = _guided_workflow_block(db, pid)
    assert block.startswith("[Guided Workflow]")
    assert "Current step" in block
    assert "never mark steps done" in block


def test_assistant_block_respects_flag_off():
    from logosforge.assistant_context_policy import gather_injected_context
    from logosforge.settings import get_manager
    db, pid = _novel()
    start_workflow(db, pid, "project_setup")
    get_manager().set("include_guided_workflow_in_assistant_context", False)
    ctx = gather_injected_context(db, pid, section_name="Manuscript")
    assert "[Guided Workflow]" not in ctx
