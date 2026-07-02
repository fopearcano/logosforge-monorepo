"""Phase 10K — screenplay revision intelligence + change impact map."""

from __future__ import annotations

import warnings

import pytest

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.revision_intelligence.diff import create_scene_diff
from logosforge.revision_intelligence.impact_map import build_revision_impact_map


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


def _film(db=None):
    db = db or Database()
    pid = db.create_project("Heist", narrative_engine="screenplay").id
    db.create_psyke_entry(pid, "Alice", "character")
    db.create_psyke_entry(pid, "Bob", "character")
    s1 = db.create_scene(pid, "Vault",
                         content="INT. VAULT - NIGHT\n\nAlice hides the gun.\n\n"
                                 "ALICE\nKeep it safe.", summary="x").id
    s2 = db.create_scene(pid, "Alley",
                         content="EXT. ALLEY - DAY\n\nAlice grabs the gun.\n\n"
                                 "ALICE\nGo.", summary="x").id
    return db, pid, s1, s2


# ===========================================================================
# Diff layer
# ===========================================================================


def test_diff_added_removed_terms():
    d = create_scene_diff("Alice waits.", "Bob waits with a gun.")
    assert "bob" in d.added_terms and "gun" in d.added_terms
    assert "alice" in d.removed_terms


def test_diff_empty_change():
    d = create_scene_diff("Same text.", "Same text.")
    assert d.is_empty_change and d.before_hash == d.after_hash


def test_diff_hashes_stable():
    a = create_scene_diff("X", "Y").after_hash
    b = create_scene_diff("Z", "Y").after_hash
    assert a == b  # same after-text -> same hash


def test_diff_accented_characters_preserved():
    d = create_scene_diff("café", "café au lait — 3€")
    assert "café" not in d.removed_terms       # café still present
    assert "lait" in d.added_terms


def test_diff_long_text_truncated():
    big = "word " * 2000
    d = create_scene_diff("", big)
    assert len(d.after_excerpt) <= 281


def test_diff_changed_lines_and_serializable():
    import json
    d = create_scene_diff("line1\nline2", "line1\nCHANGED")
    assert d.changed_lines >= 1
    assert json.dumps(d.to_dict())


# ===========================================================================
# PSYKE impact
# ===========================================================================


def test_psyke_direct_match_confirmed():
    from logosforge.revision_intelligence.psyke_impact import detect_psyke_impact
    db, pid, s1, s2 = _film()
    impacts = detect_psyke_impact(db, pid, "Bob waits.", "Alice waits.")
    by = {i.name: i for i in impacts}
    assert by["Alice"].impact_kind == "added" and by["Alice"].confidence == "confirmed"
    assert by["Bob"].impact_kind == "removed"


def test_psyke_changed_when_mentioned_both():
    from logosforge.revision_intelligence.psyke_impact import detect_psyke_impact
    db, pid, s1, s2 = _film()
    impacts = detect_psyke_impact(db, pid, "Alice runs.", "Alice walks.")
    assert any(i.name == "Alice" and i.impact_kind == "changed" for i in impacts)


def test_psyke_relations_marked_likely():
    from logosforge.revision_intelligence.psyke_impact import detect_psyke_impact
    db, pid, s1, s2 = _film()
    a = next(e for e in db.get_all_psyke_entries(pid) if e.name == "Alice")
    b = next(e for e in db.get_all_psyke_entries(pid) if e.name == "Bob")
    if hasattr(db, "create_psyke_relation"):
        db.create_psyke_relation(a.id, b.id, "ally")
        impacts = detect_psyke_impact(db, pid, "", "Alice waits.")
        bob = next((i for i in impacts if i.name == "Bob"), None)
        assert bob is not None and bob.confidence == "likely"


def test_psyke_no_stale_leak():
    from logosforge.revision_intelligence.psyke_impact import detect_psyke_impact
    db, p1, _, _ = _film()
    p2 = db.create_project("Other", narrative_engine="screenplay").id
    db.create_psyke_entry(p2, "Zara", "character")
    impacts = detect_psyke_impact(db, p2, "", "Zara enters.")
    assert all(i.name != "Alice" for i in impacts)


# ===========================================================================
# Scene dependency
# ===========================================================================


def test_scene_dep_confirmed_story_link():
    from logosforge.revision_intelligence.scene_impact import detect_scene_impacts
    from logosforge.screenplay_graph import confirm_candidate
    db, pid, s1, s2 = _film()
    confirm_candidate(db, pid, link_type="setup_to_payoff", label="gun",
                      source_type="scene", source_id=str(s1),
                      target_type="scene", target_id=str(s2),
                      source_scene_id=s1, target_scene_id=s2)
    impacts = detect_scene_impacts(db, pid, s1)
    dep = next((i for i in impacts if i.scene_id == s2), None)
    assert dep is not None and dep.confidence == "confirmed"


def test_scene_dep_shared_character_likely():
    from logosforge.revision_intelligence.scene_impact import detect_scene_impacts
    db, pid, s1, s2 = _film()  # both scenes feature ALICE
    impacts = detect_scene_impacts(db, pid, s1)
    assert any(i.scene_id == s2 for i in impacts)


def test_scene_dep_capped():
    from logosforge.revision_intelligence.scene_impact import (
        detect_scene_impacts, _MAX_SCENES,
    )
    db = Database()
    pid = db.create_project("Big", narrative_engine="screenplay").id
    sids = [db.create_scene(pid, f"S{i}", content=f"INT. P{i} - DAY\n\nALICE\nHi.",
                            summary="x").id for i in range(40)]
    assert len(detect_scene_impacts(db, pid, sids[0])) <= _MAX_SCENES


# ===========================================================================
# Impact map builder
# ===========================================================================


def test_impact_map_with_before_after():
    db, pid, s1, s2 = _film()
    m = build_revision_impact_map(db, pid, scene_id=s1,
                                  before_text="INT. VAULT - NIGHT\n\nAlice hides a letter.",
                                  after_text="INT. VAULT - NIGHT\n\nAlice hides the gun.")
    assert m.scene_id == s1 and m.impact_level in ("low", "medium", "high", "critical")
    assert m.confidence in ("confirmed", "likely", "possible", "unknown")
    assert m.impacted_psyke_entries


def test_impact_map_without_before_is_partial():
    db, pid, s1, s2 = _film()
    m = build_revision_impact_map(db, pid, scene_id=s1)
    assert any("previous snapshot" in lim.lower() for lim in m.limitations)


def test_impact_map_no_db_mutation_unless_saved():
    db, pid, s1, s2 = _film()
    before = len(db.get_revision_impact_reports(pid))
    build_revision_impact_map(db, pid, scene_id=s1)
    assert len(db.get_revision_impact_reports(pid)) == before


def test_impact_map_save_creates_report_and_items():
    db, pid, s1, s2 = _film()
    m = build_revision_impact_map(db, pid, scene_id=s1, save_report=True)
    assert m.created_report_id is not None
    reports = db.get_revision_impact_reports(pid)
    assert len(reports) == 1
    assert len(db.get_revision_impact_items(m.created_report_id)) >= 1


def test_impact_map_no_llm(monkeypatch):
    import logosforge.assistant as assistant
    calls = []
    monkeypatch.setattr(assistant, "chat_completion",
                        lambda *a, **k: calls.append(1) or ("", False))
    db, pid, s1, s2 = _film()
    build_revision_impact_map(db, pid, scene_id=s1, save_report=True)
    assert calls == []


def test_impact_map_serializable():
    import json
    db, pid, s1, s2 = _film()
    assert json.dumps(build_revision_impact_map(db, pid, scene_id=s1).to_dict())


# ===========================================================================
# Production integration
# ===========================================================================


def test_impact_map_includes_production_when_active():
    import logosforge.screenplay_production as P
    db, pid, s1, s2 = _film()
    P.enable_production_mode(db, pid)
    P.assign_scene_numbers(db, pid)
    m = build_revision_impact_map(db, pid, scene_id=s1)
    assert m.production_impacts and m.draft_id is not None


def test_impact_map_production_inactive_handled():
    db, pid, s1, s2 = _film()
    m = build_revision_impact_map(db, pid, scene_id=s1)
    assert m.production_impacts == []


# ===========================================================================
# Logos
# ===========================================================================


def test_revision_logos_actions_deterministic_screenplay_only():
    from logosforge.logos import actions as A
    from logosforge.logos import deterministic as det
    for name in ("sp_revision_impact", "sp_check_psyke_impact",
                 "sp_check_setup_payoff_impact", "sp_check_continuity_impact",
                 "sp_check_impacted_scenes", "sp_prepare_revision_followup"):
        act = A.get_action(name)
        assert act and act.modes == ("screenplay",) and act.deterministic
        assert det.is_deterministic(name)


def test_revision_actions_hidden_in_novel():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("Book", narrative_engine="novel")
    ctl = LogosController(db)
    names = [a.name for a in ctl.available_actions("Manuscript", writing_mode="novel")]
    assert not any(n.startswith("sp_") for n in names)


def test_revision_impact_action_no_llm():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def boom(*a, **k):
        raise AssertionError("deterministic revision action must not use the LLM")

    db, pid, s1, s2 = _film()
    ctl = LogosController(db, provider_resolver=boom, chat_fn=boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=s1)
    res = ctl.run(ctx, "sp_revision_impact")
    assert res.ok and "Impact" in res.message
    assert res.proposed_operations == []


# ===========================================================================
# Assistant context
# ===========================================================================


def test_assistant_revision_block_only_after_saved_report():
    from logosforge.assistant_context_policy import gather_injected_context
    db, pid, s1, s2 = _film()
    # No saved report -> no block.
    ctx = gather_injected_context(db, pid, section_name="Manuscript", scene_id=s1)
    assert "[Revision Impact]" not in ctx
    build_revision_impact_map(db, pid, scene_id=s1, save_report=True)
    ctx2 = gather_injected_context(db, pid, section_name="Manuscript", scene_id=s1)
    assert "[Revision Impact]" in ctx2


def test_assistant_revision_block_capped_no_dump():
    from logosforge.assistant_context_policy import gather_injected_context
    db, pid, s1, s2 = _film()
    build_revision_impact_map(db, pid, scene_id=s1, save_report=True)
    ctx = gather_injected_context(db, pid, section_name="Manuscript", scene_id=s1)
    block = ctx.split("[Revision Impact]")[-1].split("[")[0]
    assert block.count("\n") < 8
    assert "Keep it safe." not in ctx        # no scene-body dump


def test_assistant_revision_block_no_llm_no_mutation(monkeypatch):
    import logosforge.assistant as assistant
    from logosforge.assistant_context_policy import gather_injected_context
    db, pid, s1, s2 = _film()
    build_revision_impact_map(db, pid, scene_id=s1, save_report=True)
    calls = []
    monkeypatch.setattr(assistant, "chat_completion",
                        lambda *a, **k: calls.append(1) or ("", False))
    before = len(db.get_revision_impact_reports(pid))
    gather_injected_context(db, pid, section_name="Manuscript", scene_id=s1)
    assert calls == [] and len(db.get_revision_impact_reports(pid)) == before


def test_assistant_revision_block_no_stale_leak():
    from logosforge.assistant_context_policy import gather_injected_context
    db, p1, s1, s2 = _film()
    build_revision_impact_map(db, p1, scene_id=s1, save_report=True)
    p2 = db.create_project("Other", narrative_engine="screenplay").id
    sp2 = db.create_scene(p2, "X", content="INT. Y - DAY\n\nZ.", summary="x").id
    ctx2 = gather_injected_context(db, p2, section_name="Manuscript", scene_id=sp2)
    assert "[Revision Impact]" not in ctx2


# ===========================================================================
# Health
# ===========================================================================


def test_health_revision_categories_only_after_report():
    from logosforge.logos.health import HealthEngine
    from logosforge.logos.health import metric as M
    db, pid, s1, s2 = _film()
    cats0 = {m.category for m in HealthEngine(db, pid).generate_report().metrics}
    assert M.CAT_REVISION_CAUSALITY not in cats0
    build_revision_impact_map(db, pid, scene_id=s1, save_report=True)
    cats1 = {m.category for m in HealthEngine(db, pid).generate_report().metrics}
    assert M.CAT_REVISION_CAUSALITY in cats1 and M.CAT_CONTINUITY_REVISION in cats1


def test_health_revision_capped():
    from logosforge.logos.health import HealthEngine
    from logosforge.logos.health import metric as M
    db, pid, s1, s2 = _film()
    build_revision_impact_map(db, pid, scene_id=s1, save_report=True)
    by = {m.category: m for m in HealthEngine(db, pid).generate_report().metrics}
    for c in (M.CAT_REVISION_CAUSALITY, M.CAT_CONTINUITY_REVISION):
        assert by[c].status in (M.STATUS_STABLE, M.STATUS_WATCH, M.STATUS_UNKNOWN)


def test_novel_health_has_no_revision_categories():
    from logosforge.logos.health import HealthEngine
    from logosforge.logos.health import metric as M
    db = Database()
    pid = db.create_project("Book", narrative_engine="novel").id
    db.create_scene(pid, "Ch1", content="Morning.", summary="x")
    cats = {m.category for m in HealthEngine(db, pid).generate_report().metrics}
    assert M.CAT_REVISION_CAUSALITY not in cats


# ===========================================================================
# Migration / guards
# ===========================================================================


def test_existing_db_opens_no_reports():
    db = Database()
    pid = db.create_project("Old").id
    assert db.get_revision_impact_reports(pid) == []
    assert db.get_latest_revision_impact_report(pid) is None


def test_build_active_provider_unchanged():
    from logosforge.providers import build_active_provider
    from logosforge.settings import get_manager
    mgr = get_manager()
    mgr.set("ai_provider", "OpenAI")
    mgr.set("ai_base_url", "https://api.openai.com/v1")
    mgr.set("ai_model", "gpt-4o")
    p = build_active_provider(require_configured=True)
    assert p is not None and p.name == "OpenAI"
