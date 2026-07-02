"""Phase 10Q — Semantic Continuity Engine."""

from __future__ import annotations

import warnings

import pytest

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.continuity import (
    build_continuity_decision_cards,
    build_continuity_report,
    check_scene_continuity,
    get_continuity_issues,
    get_continuity_summary_for_assistant,
    persist_check_run,
    set_issue_status,
    validate_continuity_change,
)
from logosforge.continuity import models as M


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
    pid = db.create_project("Novel", narrative_engine="novel").id
    db.create_psyke_entry(pid, "Alice", "character")
    db.create_psyke_entry(pid, "Solo", "character")  # one appearance
    s1 = db.create_scene(pid, "Open", content="Alice stood in the Kitchen.",
                         location="Kitchen")
    s2 = db.create_scene(pid, "Next", content="Alice was at the Castle.",
                         location="Castle")
    s3 = db.create_scene(pid, "Solo bit", content="Solo waved.", location="Castle")
    return db, pid, s1.id, s2.id, s3.id


def _screenplay():
    db = Database()
    pid = db.create_project("Script", narrative_engine="screenplay").id
    db.create_scene(pid, "S1", content="Action happens.")  # missing slug/time
    return db, pid


# ===========================================================================
# Migration / persistence
# ===========================================================================


def test_tables_created_db_opens():
    db = Database()
    pid = db.create_project("E", narrative_engine="novel").id
    assert db.get_continuity_issues(pid) == []
    assert db.get_latest_continuity_check_run(pid) is None


def test_empty_project_no_crash():
    db = Database()
    pid = db.create_project("E", narrative_engine="novel").id
    rep = build_continuity_report(db, pid)
    assert rep.issues == []
    assert rep.summary_line()


def test_check_run_persisted():
    db, pid, *_ = _novel()
    rep = build_continuity_report(db, pid)
    run = persist_check_run(db, pid, rep)
    assert run is not None
    assert db.get_latest_continuity_check_run(pid).issue_count == len(rep.open_issues())


def test_dismissed_status_persists():
    db, pid, *_ = _novel()
    rep = build_continuity_report(db, pid)
    iss = rep.issues[0]
    set_issue_status(db, pid, iss, "dismissed")
    rep2 = build_continuity_report(db, pid)
    match = [i for i in rep2.issues if i.issue_key == iss.issue_key][0]
    assert match.status == "dismissed"
    assert iss.issue_key not in {i.issue_key for i in rep2.open_issues()}


def test_resolved_status_persists():
    db, pid, *_ = _novel()
    rep = build_continuity_report(db, pid)
    iss = rep.issues[0]
    set_issue_status(db, pid, iss, "resolved")
    assert db.get_continuity_issue_by_key(pid, iss.issue_key).status == "resolved"


def test_current_project_only():
    db, pid_a, *_ = _novel()
    pid_b = db.create_project("Other", narrative_engine="novel").id
    rep_b = build_continuity_report(db, pid_b)
    assert rep_b.issues == []


# ===========================================================================
# Fact extraction
# ===========================================================================


def test_facts_extracted():
    db, pid, s1, s2, s3 = _novel()
    rep = build_continuity_report(db, pid)
    types = {f.fact_type for f in rep.facts}
    assert M.FT_LOCATION_STATE in types
    assert M.FT_CHARACTER_STATE in types


def test_lore_fact_extracted():
    db = Database()
    pid = db.create_project("L", narrative_engine="novel").id
    db.create_psyke_entry(pid, "Magic Law", "lore", notes="No resurrection.")
    rep = build_continuity_report(db, pid)
    assert any(f.fact_type == M.FT_LORE_RULE for f in rep.facts)


def test_states_built():
    db, pid, s1, s2, s3 = _novel()
    rep = build_continuity_report(db, pid)
    dims = {s.dimension for s in rep.states}
    assert M.DIM_CHARACTER in dims or M.DIM_SPATIAL in dims


def test_deferred_systems_degrade_cleanly():
    db = Database()
    pid = db.create_project("GN", narrative_engine="graphic_novel").id
    rep = build_continuity_report(db, pid)
    assert "graphic_novel_continuity" in rep.unavailable


# ===========================================================================
# Contradiction / gap detection
# ===========================================================================


def test_dangling_setup_payoff_link_blocking():
    db = Database()
    pid = db.create_project("P", narrative_engine="novel").id
    s1 = db.create_scene(pid, "A", content="x")
    s2 = db.create_scene(pid, "B", content="y")
    db.update_scene(s2.id, s2.title, content=s2.content, setup_payoff_links="9999")
    rep = build_continuity_report(db, pid)
    gaps = [i for i in rep.issues if i.issue_type == M.IT_CONTINUITY_GAP
            and i.severity == M.SEV_BLOCKING]
    assert gaps and gaps[0].confidence == M.CONF_CONFIRMED


def test_no_hallucinated_contradictions_on_clean_project():
    db = Database()
    pid = db.create_project("Clean", narrative_engine="novel").id
    db.create_psyke_entry(pid, "Alice", "character")
    db.create_scene(pid, "S", content="Alice acts.", location="Home")
    rep = build_continuity_report(db, pid)
    assert all(i.severity != M.SEV_BLOCKING for i in rep.issues)


def test_no_fake_causality():
    db, pid, s1, s2, s3 = _novel()
    rep = build_continuity_report(db, pid)
    # the engine never emits a "causes"-style fabricated contradiction
    assert all(i.issue_type != "causes" for i in rep.issues)


# ===========================================================================
# Missing transitions
# ===========================================================================


def test_location_jump_detected():
    db, pid, s1, s2, s3 = _novel()
    rep = build_continuity_report(db, pid)
    jumps = [i for i in rep.issues if i.issue_type == M.IT_LOCATION_JUMP]
    assert jumps and jumps[0].dimension == M.DIM_SPATIAL
    assert jumps[0].severity == M.SEV_SUGGESTION  # never blocking


def test_travel_cue_suppresses_jump():
    db = Database()
    pid = db.create_project("T", narrative_engine="novel").id
    db.create_scene(pid, "A", content="Home life.", location="Home")
    db.create_scene(pid, "B", content="She travelled to the city and arrived.",
                    location="City")
    rep = build_continuity_report(db, pid)
    assert not any(i.issue_type == M.IT_LOCATION_JUMP for i in rep.issues)


# ===========================================================================
# State drift
# ===========================================================================


def test_single_appearance_character_flagged():
    db, pid, s1, s2, s3 = _novel()
    for i in range(3):
        db.create_scene(pid, f"F{i}", content="Alice waits.", location="Castle")
    rep = build_continuity_report(db, pid)
    drift = [i for i in rep.issues if i.issue_type == M.IT_STATE_DRIFT]
    assert any("Solo" in i.title for i in drift)


# ===========================================================================
# Writing-mode awareness
# ===========================================================================


def test_screenplay_production_risk():
    db, pid = _screenplay()
    rep = build_continuity_report(db, pid)
    prod = [i for i in rep.issues if i.issue_type == M.IT_PRODUCTION_RISK]
    assert prod and prod[0].dimension == M.DIM_PRODUCTION


def test_no_production_risk_in_novel():
    db, pid, s1, s2, s3 = _novel()
    rep = build_continuity_report(db, pid)
    assert not any(i.issue_type == M.IT_PRODUCTION_RISK for i in rep.issues)


def test_series_mode_deferred_clean():
    db = Database()
    pid = db.create_project("S", narrative_engine="series").id
    rep = build_continuity_report(db, pid)
    assert "series_continuity" in rep.unavailable


# ===========================================================================
# Rewrite / Controlled Apply validation
# ===========================================================================


def test_validate_removed_psyke_term():
    db = Database()
    pid = db.create_project("V", narrative_engine="novel").id
    db.create_psyke_entry(pid, "Alice", "character")
    v = validate_continuity_change(db, pid, "scene", 1,
                                   "Alice stood in the Kitchen.", "She stood there.")
    assert any("Alice" in w for w in v.warnings)
    assert "Alice" in v.related_psyke


def test_validate_screenplay_heading_removed():
    db = Database()
    pid = db.create_project("V", narrative_engine="screenplay").id
    v = validate_continuity_change(db, pid, "scene", 1,
                                   "INT. HOUSE - DAY\nAction.", "Just action.",
                                   writing_mode="screenplay")
    assert any("heading" in w.lower() for w in v.warnings)


def test_validate_no_mutation():
    db = Database()
    pid = db.create_project("V", narrative_engine="novel").id
    db.create_psyke_entry(pid, "Alice", "character")
    sc = db.create_scene(pid, "S", content="Alice here.")
    before = (len(db.get_all_scenes(pid)), len(db.get_continuity_issues(pid)))
    validate_continuity_change(db, pid, "scene", sc.id, "Alice here.", "Gone.")
    after = (len(db.get_all_scenes(pid)), len(db.get_continuity_issues(pid)))
    assert before == after


def test_validate_big_cut_warns():
    db = Database()
    pid = db.create_project("V", narrative_engine="novel").id
    v = validate_continuity_change(db, pid, "scene", 1, "x" * 100, "x" * 10)
    assert any("half" in w for w in v.warnings)


# ===========================================================================
# Scene-scoped check
# ===========================================================================


def test_check_scene_continuity_filters():
    db, pid, s1, s2, s3 = _novel()
    rep = check_scene_continuity(db, pid, s1)
    for i in rep.issues:
        if i.related_scene_ids:
            assert s1 in i.related_scene_ids or s2 in i.related_scene_ids


def test_queries_no_db_mutation():
    db, pid, s1, s2, s3 = _novel()
    before = (len(db.get_all_scenes(pid)), len(db.get_continuity_issues(pid)),
              len(db.get_continuity_check_runs(pid)))
    build_continuity_report(db, pid)
    check_scene_continuity(db, pid, s1)
    get_continuity_issues(db, pid)
    after = (len(db.get_all_scenes(pid)), len(db.get_continuity_issues(pid)),
             len(db.get_continuity_check_runs(pid)))
    assert before == after


def test_get_issues_filters():
    db, pid, s1, s2, s3 = _novel()
    spatial = get_continuity_issues(db, pid, dimension=M.DIM_SPATIAL)
    assert all(i.dimension == M.DIM_SPATIAL for i in spatial)


# ===========================================================================
# Decision cards
# ===========================================================================


def test_continuity_decision_cards():
    db, pid, s1, s2, s3 = _novel()
    cards = build_continuity_decision_cards(db, pid)
    assert cards and all(c.category == "continuity" for c in cards)


def test_decision_cards_traceable():
    db, pid, s1, s2, s3 = _novel()
    cards = build_continuity_decision_cards(db, pid)
    assert all(c.id.startswith("continuity_") for c in cards)


# ===========================================================================
# Logos
# ===========================================================================


def test_logos_continuity_actions_registered():
    from logosforge.logos.actions import get_action
    from logosforge.logos.deterministic import is_deterministic
    for name in ("ct_run_check", "ct_check_scene", "ct_show_issues",
                 "ct_decision_cards"):
        assert get_action(name) is not None
        assert is_deterministic(name)


def test_logos_explain_is_generative():
    from logosforge.logos.actions import get_action
    act = get_action("ct_explain_issue")
    assert act is not None and not act.deterministic


def test_logos_run_check_runs():
    from logosforge.logos.context import build_logos_context
    from logosforge.logos.deterministic import get_handler
    db, pid, s1, s2, s3 = _novel()
    ctx = build_logos_context(db, pid, section_name="Manuscript")
    res = get_handler("ct_run_check")(db, ctx)
    assert res.ok and "Continuity" in res.message


def test_logos_check_scene_needs_scene():
    from logosforge.logos.context import build_logos_context
    from logosforge.logos.deterministic import get_handler
    db, pid, s1, s2, s3 = _novel()
    ctx = build_logos_context(db, pid, section_name="Manuscript")
    assert "Open a scene" in get_handler("ct_check_scene")(db, ctx).message


# ===========================================================================
# Assistant context
# ===========================================================================


def test_assistant_block_present_with_issues():
    db, pid, s1, s2, s3 = _novel()
    block = get_continuity_summary_for_assistant(db, pid)
    assert block.startswith("[Continuity]")
    assert "never auto-fix" in block


def test_assistant_block_empty_when_clean():
    db = Database()
    pid = db.create_project("Clean", narrative_engine="novel").id
    db.create_scene(pid, "S", content="A quiet scene.")
    assert get_continuity_summary_for_assistant(db, pid) == ""


def test_assistant_block_respects_flag_off():
    from logosforge.assistant_context_policy import gather_injected_context
    from logosforge.settings import get_manager
    db, pid, s1, s2, s3 = _novel()
    get_manager().set("include_continuity_in_assistant_context", False)
    ctx = gather_injected_context(db, pid, section_name="Manuscript", scene_id=s1)
    assert "[Continuity]" not in ctx


def test_assistant_context_no_mutation():
    from logosforge.assistant_context_policy import gather_injected_context
    db, pid, s1, s2, s3 = _novel()
    before = (len(db.get_continuity_issues(pid)),
              len(db.get_continuity_check_runs(pid)))
    gather_injected_context(db, pid, section_name="Manuscript", scene_id=s1)
    after = (len(db.get_continuity_issues(pid)),
             len(db.get_continuity_check_runs(pid)))
    assert before == after


# ===========================================================================
# Guided Workflows integration
# ===========================================================================


def test_continuity_workflows_present():
    from logosforge.guided_workflows import list_workflow_templates
    novel = {t.id for t in list_workflow_templates("novel")}
    sp = {t.id for t in list_workflow_templates("screenplay")}
    assert "continuity_review" in novel
    assert "screenplay_continuity_pass" not in novel
    assert "screenplay_continuity_pass" in sp


def test_continuity_review_workflow_starts():
    from logosforge.guided_workflows import start_workflow
    db, pid, s1, s2, s3 = _novel()
    v = start_workflow(db, pid, "continuity_review")
    assert v is not None and v.total_steps >= 4
