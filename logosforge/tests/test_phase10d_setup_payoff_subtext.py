"""Phase 10D — screenplay setup/payoff + subtext tracking."""

from __future__ import annotations

import json
import warnings

import pytest

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.screenplay_blocks import parse_screenplay_text, ScreenplayBlock
from logosforge import screenplay_setup_payoff as spx
from logosforge import screenplay_subtext as sub


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


def _cands(text, **kw):
    return spx.scene_candidates(parse_screenplay_text(text), **kw)


# ===========================================================================
# Setup/payoff — single-scene candidates
# ===========================================================================


def test_detects_promise_candidate():
    cands = _cands("JOHN\nI promise I will fix this.")
    assert any(c.candidate_type == spx.T_PROMISE for c in cands)


def test_detects_threat_candidate():
    cands = _cands("JOHN\nIf you ever come back, you'll regret it.")
    assert any(c.candidate_type == spx.T_THREAT for c in cands)


def test_detects_object_candidate():
    cands = _cands("INT. ROOM - DAY\n\nA gun sits on the table.")
    obj = [c for c in cands if c.candidate_type == spx.T_OBJECT]
    assert any("gun" in c.label for c in obj)


def test_uncertain_candidate_has_modest_confidence():
    cands = _cands("INT. ROOM - DAY\n\nA gun sits on the table.")
    obj = next(c for c in cands if "gun" in c.label)
    assert 0.0 < obj.confidence <= 0.6  # never fake-certain


def test_empty_scene_handled_safely():
    assert _cands("") == []


def test_invalid_blocks_handled_safely():
    cands = spx.scene_candidates([ScreenplayBlock("bogus", "a gun lies here")])
    # invalid -> action; still scannable, no crash
    assert isinstance(cands, list)


def test_candidate_serializable():
    c = _cands("JOHN\nI promise.")[0]
    assert json.dumps(c.to_dict())


# ===========================================================================
# Setup/payoff — project-level recurrence
# ===========================================================================


def _project_with_gun(db):
    pid = db.create_project("Film", narrative_engine="screenplay").id
    db.create_scene(pid, "Setup", content="INT. BAR - NIGHT\n\nA gun on the table.",
                    summary="x")
    db.create_scene(pid, "Payoff", content="EXT. ALLEY - DAY\n\nHe grabs the gun.",
                    summary="x")
    return pid


def test_recurring_object_becomes_payoff_and_motif():
    db = Database()
    pid = _project_with_gun(db)
    rep = spx.analyze_setup_payoff(db, pid)
    assert any("gun" in c.label for c in rep.possible_payoffs)
    assert any("gun" in c.label for c in rep.recurring_motifs)
    # payoff links back to the earlier scene (graph hook suggestion).
    payoff = next(c for c in rep.possible_payoffs if "gun" in c.label)
    assert payoff.linked_scene_id is not None


def test_unresolved_setup_when_object_appears_once():
    db = Database()
    pid = db.create_project("Film", narrative_engine="screenplay").id
    db.create_scene(pid, "Only", content="INT. X - DAY\n\nA mysterious letter arrives.",
                    summary="x")
    rep = spx.analyze_setup_payoff(db, pid)
    assert any("letter" in c.label for c in rep.unresolved_setups)


def test_characters_not_tracked_as_motifs():
    db = Database()
    pid = db.create_project("Film", narrative_engine="screenplay").id
    db.create_psyke_entry(pid, "Alice", "character")
    db.create_scene(pid, "S1", content="INT. X - DAY\n\nAlice waits.", summary="x")
    db.create_scene(pid, "S2", content="EXT. Y - DAY\n\nAlice runs.", summary="x")
    rep = spx.analyze_setup_payoff(db, pid)
    assert not any("alice" in c.label.lower() for c in rep.recurring_motifs)


def test_psyke_object_referenced_links_entry():
    db = Database()
    pid = db.create_project("Film", narrative_engine="screenplay").id
    e = db.create_psyke_entry(pid, "Excalibur", "object")
    db.create_scene(pid, "S1", content="INT. X - DAY\n\nExcalibur gleams.", summary="x")
    rep = spx.analyze_setup_payoff(db, pid)
    linked = [c for c in rep.candidates if c.linked_psyke_entry_id == e.id]
    assert linked


# ===========================================================================
# Subtext
# ===========================================================================


def _sub(text, **kw):
    return sub.analyze_subtext_scene(parse_screenplay_text(text), **kw)


def test_detects_on_the_nose_emotion():
    r = _sub("JOHN\nI feel so angry and I hate you right now.")
    assert any(s.signal_type == sub.S_ON_THE_NOSE_RISK for s in r.signals)


def test_detects_exposition_heavy_dialogue():
    r = _sub("JOHN\nAs you know, years ago everything changed for our family.")
    assert any(s.signal_type == sub.S_EXPOSITION_RISK for s in r.signals)


def test_detects_avoidance_and_indirect_answer():
    r = _sub("MARY\nWhat happened?\n\nJOHN\nIt's nothing. I'm fine.")
    types = {s.signal_type for s in r.signals}
    assert sub.S_AVOIDANCE in types


def test_objective_gap_low_confidence_without_psyke():
    r = _sub("JOHN\nThe weather is pleasant today, isn't it.", psyke_objectives=None)
    gap = next((s for s in r.signals if s.signal_type == sub.S_OBJECTIVE_GAP), None)
    assert gap is not None and gap.confidence <= 0.3


def test_objective_gap_suppressed_when_psyke_has_goal():
    r = _sub("JOHN\nThe weather is pleasant today.",
             psyke_objectives={"JOHN": True})
    assert not any(s.signal_type == sub.S_OBJECTIVE_GAP for s in r.signals)


def test_subtext_report_serializable_and_no_signals_safe():
    r = _sub("INT. X - DAY\n\nHe walks across the room and out the door quietly today.")
    assert json.dumps(r.to_dict())


def test_subtext_does_not_mutate_psyke(monkeypatch):
    db = Database()
    pid = db.create_project("Film", narrative_engine="screenplay").id
    db.create_psyke_entry(pid, "Alice", "character")
    sid = db.create_scene(pid, "S", content="ALICE\nI'm fine.", summary="x").id
    before = len(db.get_all_psyke_entries(pid))
    sub.analyze_subtext_by_id(db, pid, sid)
    assert len(db.get_all_psyke_entries(pid)) == before


def test_subtext_db_adapter_uses_psyke_objective(monkeypatch):
    db = Database()
    pid = db.create_project("Film", narrative_engine="screenplay").id
    e = db.create_psyke_entry(pid, "Alice", "character")
    monkeypatch.setattr(db, "get_psyke_entry_details",
                        lambda eid: {"objective": "survive"} if eid == e.id else {})
    m = sub._psyke_objective_map(db, pid)
    assert m == {"ALICE": True}


# ===========================================================================
# Logos integration
# ===========================================================================


def test_setup_payoff_and_subtext_actions_registered_screenplay_only():
    from logosforge.logos import actions as A
    from logosforge.logos import deterministic as det
    for name in ("sp_detect_setup_payoff", "sp_track_unresolved_setups",
                 "sp_find_possible_payoffs", "sp_check_subtext", "sp_find_exposition"):
        act = A.get_action(name)
        assert act and act.modes == ("screenplay",) and act.deterministic
        assert det.is_deterministic(name)
    for name in ("sp_reduce_on_the_nose", "sp_objective_gap",
                 "sp_action_beat_subtext", "sp_emotion_to_behavior"):
        act = A.get_action(name)
        assert act and act.modes == ("screenplay",) and not act.deterministic


def test_actions_do_not_dominate_novel_mode():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("Book", narrative_engine="novel")
    ctl = LogosController(db)
    names = [a.name for a in ctl.available_actions("Manuscript", writing_mode="novel")]
    assert not any(n.startswith("sp_") for n in names)


def test_deterministic_setup_payoff_action_no_llm():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def boom(*a, **k):
        raise AssertionError("deterministic action must not use the LLM/provider")

    db = Database()
    pid = _project_with_gun(db)
    ctl = LogosController(db, provider_resolver=boom, chat_fn=boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript")
    res = ctl.run(ctx, "sp_detect_setup_payoff")
    assert res.ok and "candidate" in res.message.lower()
    assert res.proposed_operations == []


def test_deterministic_subtext_action_no_llm():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def boom(*a, **k):
        raise AssertionError("deterministic action must not use the LLM/provider")

    db = Database()
    pid = db.create_project("Film", narrative_engine="screenplay").id
    sid = db.create_scene(pid, "S", content="JOHN\nI feel so angry.", summary="x").id
    ctl = LogosController(db, provider_resolver=boom, chat_fn=boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "sp_check_subtext")
    assert res.ok and "subtext" in res.message.lower()


def test_subtext_rewrite_calls_llm_only_when_invoked():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    calls = []
    db = Database()
    pid = db.create_project("Film", narrative_engine="screenplay").id
    sid = db.create_scene(pid, "S", content="JOHN\nI feel so angry.", summary="x").id
    ctl = LogosController(db, provider_resolver=lambda: object(),
                          chat_fn=lambda m, p: calls.append(1) or "- show it")
    ctx = build_logos_context(db, pid, section_name="Manuscript",
                              current_scene_id=sid, selected_text="I feel so angry.")
    assert calls == []
    res = ctl.run(ctx, "sp_emotion_to_behavior")
    assert res.ok and calls == [1]


# ===========================================================================
# Assistant context
# ===========================================================================


def test_assistant_context_includes_setup_payoff_and_subtext():
    from logosforge.assistant_context_policy import gather_injected_context
    db = Database()
    pid = _project_with_gun(db)
    scenes = db.get_all_scenes(pid)
    sid = scenes[-1].id
    ctx = gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    assert "[Screenplay Setup/Payoff]" in ctx


def test_assistant_subtext_block_present_and_capped():
    from logosforge.assistant_context_policy import gather_injected_context
    db = Database()
    pid = db.create_project("Film", narrative_engine="screenplay").id
    sid = db.create_scene(
        pid, "S",
        content="JOHN\nI feel so angry. As you know, years ago it all changed.",
        summary="x",
    ).id
    ctx = gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    assert "[Screenplay Subtext]" in ctx
    # Isolate just the subtext block (stop at the next block header) — later
    # Assistant blocks may follow it in the gather order.
    block = ctx.split("[Screenplay Subtext]")[-1].split("\n[")[0]
    assert block.count("\n- ") <= 3   # capped at 3 signals


def test_tracking_blocks_can_be_disabled():
    from logosforge.assistant_context_policy import gather_injected_context
    from logosforge.settings import get_manager
    db = Database()
    pid = _project_with_gun(db)
    sid = db.get_all_scenes(pid)[-1].id
    get_manager().set("include_screenplay_tracking_in_assistant_context", False)
    ctx = gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    assert "[Screenplay Setup/Payoff]" not in ctx
    assert "[Screenplay Subtext]" not in ctx


def test_tracking_blocks_absent_for_novel():
    from logosforge.assistant_context_policy import gather_injected_context
    db = Database()
    pid = db.create_project("Book", narrative_engine="novel").id
    sid = db.create_scene(pid, "S", content="A gun. I promise.", summary="x").id
    ctx = gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    assert "[Screenplay Setup/Payoff]" not in ctx
    assert "[Screenplay Subtext]" not in ctx


def test_assistant_assembly_no_llm_no_db_mutation(monkeypatch):
    import logosforge.assistant as assistant
    from logosforge.assistant_context_policy import gather_injected_context
    calls = []
    monkeypatch.setattr(assistant, "chat_completion",
                        lambda *a, **k: calls.append(1) or ("", False))
    db = Database()
    pid = _project_with_gun(db)
    sid = db.get_all_scenes(pid)[-1].id
    before = len(db.get_all_scenes(pid))
    gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    assert calls == []
    assert len(db.get_all_scenes(pid)) == before


def test_no_stale_project_leak():
    from logosforge.assistant_context_policy import gather_injected_context
    db = Database()
    p1 = _project_with_gun(db)
    p2 = db.create_project("P2", narrative_engine="screenplay").id
    db.create_scene(p2, "Empty", content="INT. X - DAY\n\nNothing notable here today.",
                    summary="x")
    s2 = db.get_all_scenes(p2)[-1].id
    ctx2 = gather_injected_context(db, p2, section_name="Manuscript", scene_id=s2)
    assert "gun" not in ctx2.lower()


# ===========================================================================
# Health integration
# ===========================================================================


def test_health_populates_subtext_and_setup_payoff():
    from logosforge.logos.health import HealthEngine
    from logosforge.logos.health import metric as M
    db = Database()
    pid = db.create_project("Film", narrative_engine="screenplay").id
    db.create_scene(pid, "S", content="A gun.\n\nJOHN\nI feel so angry. I'm fine.",
                    summary="x")
    report = HealthEngine(db, pid).generate_report()
    by = {m.category: m for m in report.metrics}
    assert by[M.CAT_SUBTEXT].status != M.STATUS_UNKNOWN   # now populated
    assert M.CAT_SP_SETUP_PAYOFF in by
    assert M.CAT_MOTIF_RECURRENCE in by
    assert M.CAT_ON_THE_NOSE in by


def test_health_cinematic_continuity_deferred():
    from logosforge.logos.health import HealthEngine
    from logosforge.logos.health import metric as M
    db = Database()
    pid = db.create_project("Film", narrative_engine="screenplay").id
    db.create_scene(pid, "S", content="INT. X - DAY\n\nJohn waits.", summary="x")
    report = HealthEngine(db, pid).generate_report()
    by = {m.category: m for m in report.metrics}
    assert by[M.CAT_CINEMATIC_CONTINUITY].status == M.STATUS_UNKNOWN


def test_novel_health_unchanged_by_10d():
    from logosforge.logos.health import HealthEngine
    from logosforge.logos.health import metric as M
    db = Database()
    pid = db.create_project("Book", narrative_engine="novel").id
    db.create_scene(pid, "Ch1", content="It was a quiet morning.", summary="x")
    cats = {m.category for m in HealthEngine(db, pid).generate_report().metrics}
    assert M.CAT_SP_SETUP_PAYOFF not in cats
    assert M.CAT_ON_THE_NOSE not in cats


# ===========================================================================
# Export
# ===========================================================================


def test_setup_payoff_report_export():
    from logosforge.export import export_setup_payoff_report_json
    db = Database()
    pid = _project_with_gun(db)
    data = json.loads(export_setup_payoff_report_json(db, pid))
    assert data["project"]["writing_mode"] == "screenplay"
    assert "setup_payoff" in data
    assert "possible_payoffs" in data["setup_payoff"]


def test_subtext_report_export():
    from logosforge.export import export_subtext_report_json
    db = Database()
    pid = db.create_project("Film", narrative_engine="screenplay").id
    db.create_scene(pid, "S", content="JOHN\nI feel so angry.", summary="x")
    data = json.loads(export_subtext_report_json(db, pid))
    assert data["project"]["writing_mode"] == "screenplay"
    assert len(data["scenes"]) == 1


def test_existing_exports_unbroken():
    from logosforge.export import export_json, export_screenplay
    db = Database()
    pid = _project_with_gun(db)
    assert json.loads(export_json(db, pid))["project"]["writing_mode"] == "screenplay"
    assert "Writing Mode: Screenplay" in export_screenplay(db, pid)


# ===========================================================================
# Guards
# ===========================================================================


def test_build_active_provider_unchanged():
    from logosforge.providers import build_active_provider
    from logosforge.settings import get_manager
    mgr = get_manager()
    mgr.set("ai_provider", "OpenAI")
    mgr.set("ai_base_url", "https://api.openai.com/v1")
    mgr.set("ai_model", "gpt-4o")
    p = build_active_provider(require_configured=True)
    assert p is not None and p.name == "OpenAI"


def test_strategy_screenplay_active():
    from logosforge.logos.strategy.router import StrategyRouter
    from logosforge.settings import get_manager
    get_manager().set("strategy_enabled", True)
    db = Database()
    pid = db.create_project("Film", narrative_engine="screenplay").id
    assert "screenplay" in StrategyRouter(db, pid).decide("Manuscript").active_strategies
