"""Phase 10C — deterministic screenplay diagnostics + scene economy engine."""

from __future__ import annotations

import json
import warnings

import pytest

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.screenplay_blocks import parse_screenplay_text
from logosforge.screenplay_diagnostics import analyze_scene


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
    return analyze_scene(parse_screenplay_text(text), **kw)


# ===========================================================================
# Scene diagnostics — structural
# ===========================================================================


def test_empty_scene_handled_safely():
    r = analyze_scene([])
    assert r.block_count == 0
    assert r.economy_label == "sparse"
    assert r.issues == []
    assert "Empty scene" in r.summary


def test_scene_without_heading_flagged():
    r = _report("John walks in.\n\nJOHN\nHello.")
    assert any(i.id == "missing_scene_heading" for i in r.issues)


def test_scene_heading_detected_no_missing_flag():
    r = _report("INT. BAR - NIGHT\n\nJohn walks in.", scene_heading="INT. BAR - NIGHT")
    assert not any(i.id == "missing_scene_heading" for i in r.issues)


def test_clear_character_cue_count_and_unique_characters():
    r = _report("JOHN\nHi.\n\nMARY\nHello.\n\nJOHN (V.O.)\nLater.")
    assert r.character_cue_count == 3
    assert r.unique_characters == ["JOHN", "MARY"]


def test_unknown_blocks_handled_safely():
    from logosforge.screenplay_blocks import ScreenplayBlock
    bad = [ScreenplayBlock("not_a_type", "x")]  # normalizes to action
    r = analyze_scene(bad)
    assert r.block_count == 1
    assert r.action_block_count == 1  # invalid -> action


# ===========================================================================
# Scene economy
# ===========================================================================


def test_dialogue_heavy_scene_flagged():
    text = ("INT. ROOM - DAY\n\nJOHN\nLine one.\n\nMARY\nLine two.\n\n"
            "JOHN\nLine three.\n\nMARY\nLine four.\n\nJOHN\nLine five.")
    r = _report(text, scene_heading="INT. ROOM - DAY")
    assert r.economy_label == "dialogue-heavy"
    assert any(i.id == "dialogue_heavy" for i in r.issues)


def test_action_heavy_scene_flagged():
    text = "\n\n".join(["He walks." for _ in range(8)])
    r = _report(text)
    assert r.economy_label == "action-heavy"
    assert any(i.id == "no_dialogue" for i in r.issues)


def test_only_notes_scene_flagged():
    from logosforge.screenplay_blocks import ScreenplayBlock
    r = analyze_scene([ScreenplayBlock("note", "remember to fix this")])
    assert any(i.id == "only_notes" for i in r.issues)


# ===========================================================================
# Dialogue economy
# ===========================================================================


def test_excessive_parentheticals_flagged():
    text = ("JOHN\n(quietly)\nHi.\n\nMARY\n(angrily)\nNo.")
    r = _report(text)
    assert any(i.id == "parenthetical_overuse" for i in r.issues)


def test_long_dialogue_flagged():
    long_line = " ".join(["word"] * 60)
    r = _report(f"JOHN\n{long_line}")
    assert any(i.id.startswith("long_dialogue") for i in r.issues)


# ===========================================================================
# Visual action
# ===========================================================================


def test_internal_prose_action_flagged():
    text = "INT. X - DAY\n\nJohn thinks about it and remembers and feels and realizes."
    r = _report(text, scene_heading="INT. X - DAY")
    issue = next((i for i in r.issues if i.id.startswith("internal_action")), None)
    assert issue is not None
    assert "internal prose" in issue.suggested_action.lower()
    assert issue.logos_action_id == "sp_visual_action"


def test_overwritten_action_flagged():
    big = " ".join(["walks"] * 70)
    r = _report(f"INT. X - DAY\n\n{big}", scene_heading="INT. X - DAY")
    assert any(i.id.startswith("overwritten_action") for i in r.issues)


# ===========================================================================
# Transition / shot overuse
# ===========================================================================


def test_transition_overuse_flagged():
    text = ("INT. X - DAY\n\nAction.\n\nCUT TO:\n\nMore.\n\nDISSOLVE TO:\n\n"
            "Even more.\n\nSMASH CUT TO:")
    r = _report(text, scene_heading="INT. X - DAY")
    assert any(i.id == "transition_overuse" for i in r.issues)


# ===========================================================================
# Scene turn — confidence-aware
# ===========================================================================


def test_uncertain_scene_turn_low_confidence_warning():
    r = _report("INT. X - DAY\n\nHe sits. He waits.", scene_heading="INT. X - DAY")
    turn = next((i for i in r.issues if i.id == "scene_turn_unclear"), None)
    assert turn is not None
    assert turn.label == "Scene turn unclear"   # never "no turn"
    assert turn.confidence < 0.5                 # honest low confidence


def test_turn_marker_suppresses_unclear_turn():
    r = _report("INT. X - DAY\n\nHe waits, but then everything changes suddenly.",
                scene_heading="INT. X - DAY")
    assert not any(i.id == "scene_turn_unclear" for i in r.issues)


# ===========================================================================
# Character objective + PSYKE integration
# ===========================================================================


def test_objective_unclear_lower_confidence_without_psyke():
    r = _report("INT. X - DAY\n\nJOHN\nHello there friend.",
                scene_heading="INT. X - DAY", psyke_characters=None)
    obj = next((i for i in r.issues if i.id == "objective_unclear"), None)
    assert obj is not None
    assert obj.confidence <= 0.35  # no PSYKE data -> lower confidence, not a failure


def test_objective_clear_when_psyke_has_goal():
    r = _report("INT. X - DAY\n\nJOHN\nHello there friend.",
                scene_heading="INT. X - DAY",
                psyke_characters={"JOHN": True})
    assert not any(i.id == "objective_unclear" for i in r.issues)


def test_objective_markers_suppress_issue():
    r = _report("INT. X - DAY\n\nJOHN\nI want the money and I need to leave.",
                scene_heading="INT. X - DAY")
    assert not any(i.id == "objective_unclear" for i in r.issues)


def test_db_adapter_uses_psyke_objective(monkeypatch):
    from logosforge.screenplay_diagnostics import _psyke_character_map
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay").id
    e = db.create_psyke_entry(pid, "Alice", "character")
    db.create_psyke_entry(pid, "Tower", "place")
    monkeypatch.setattr(db, "get_psyke_entry_details",
                        lambda eid: {"goal": "escape"} if eid == e.id else {})
    m = _psyke_character_map(db, pid)
    assert m == {"ALICE": True}  # place excluded; goal detected


# ===========================================================================
# Setup/payoff hooks
# ===========================================================================


def test_setup_candidate_is_cautious():
    r = _report("INT. X - DAY\n\nJOHN\nRemember the gun. I promise I'll be back.")
    setup = next((i for i in r.issues if i.id.startswith("setup_candidate")), None)
    assert setup is not None
    assert setup.label == "Possible setup"      # cautious wording
    assert setup.severity == "info"


# ===========================================================================
# Serialization
# ===========================================================================


def test_report_serializable():
    r = _report("INT. X - DAY\n\nJOHN\nHi.")
    d = r.to_dict()
    assert json.dumps(d)  # no exceptions
    assert d["economy_label"] and "issues" in d


# ===========================================================================
# Logos integration
# ===========================================================================


def test_screenplay_diagnostic_action_registered_and_deterministic():
    from logosforge.logos import actions as A
    from logosforge.logos import deterministic as det
    act = A.get_action("sp_diagnose_scene_economy")
    assert act is not None and act.deterministic and act.modes == ("screenplay",)
    assert det.is_deterministic("sp_diagnose_scene_economy")


def test_diagnostic_action_appears_in_screenplay_not_novel():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("S", narrative_engine="screenplay")
    ctl = LogosController(db)
    sp = [a.name for a in ctl.available_actions("Manuscript", writing_mode="screenplay")]
    assert "sp_diagnose_scene_economy" in sp
    assert sp[0] == "sp_diagnose_scene_economy"   # prioritized first
    novel = [a.name for a in ctl.available_actions("Manuscript", writing_mode="novel")]
    assert "sp_diagnose_scene_economy" not in novel


def test_deterministic_action_does_not_call_llm():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def _boom(*a, **k):
        raise AssertionError("LLM/provider must not be used for deterministic actions")

    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay").id
    sid = db.create_scene(pid, "Open", content="INT. X - DAY\n\nJOHN\nHi.",
                          summary="x").id
    ctl = LogosController(db, provider_resolver=_boom, chat_fn=_boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "sp_diagnose_scene_economy")
    assert res.ok and "Scene economy" in res.message
    assert res.proposed_operations == []  # diagnostic only — no mutation


def test_rewrite_action_calls_llm_only_when_invoked():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    calls = []
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay").id
    sid = db.create_scene(pid, "Open", content="INT. X - DAY\n\nJohn waits.",
                          summary="x").id
    ctl = LogosController(
        db, provider_resolver=lambda: object(),
        chat_fn=lambda m, p: calls.append(1) or "- suggestion",
    )
    ctx = build_logos_context(db, pid, section_name="Manuscript",
                              current_scene_id=sid, selected_text="John waits.")
    # No call until explicitly invoked.
    assert calls == []
    res = ctl.run(ctx, "sp_suggest_visual_beat")
    assert res.ok and calls == [1]


# ===========================================================================
# Assistant context
# ===========================================================================


def test_assistant_context_includes_screenplay_diagnostics():
    from logosforge.assistant_context_policy import gather_injected_context
    db = Database()
    pid = db.create_project("Film", narrative_engine="screenplay").id
    sid = db.create_scene(
        pid, "Open",
        content="John thinks and remembers and feels everything deeply inside.",
        summary="x",
    ).id
    ctx = gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    assert "[Screenplay Diagnostics]" in ctx
    assert "Scene economy:" in ctx
    # Capped at 3 numbered issues.
    assert ctx.count("\n1.") <= 1


def test_screenplay_diagnostics_can_be_disabled():
    from logosforge.assistant_context_policy import gather_injected_context
    from logosforge.settings import get_manager
    db = Database()
    pid = db.create_project("Film", narrative_engine="screenplay").id
    sid = db.create_scene(pid, "Open", content="John waits.", summary="x").id
    get_manager().set("include_screenplay_diagnostics_in_assistant_context", False)
    ctx = gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    assert "[Screenplay Diagnostics]" not in ctx


def test_diagnostics_absent_for_novel():
    from logosforge.assistant_context_policy import gather_injected_context
    db = Database()
    pid = db.create_project("Book", narrative_engine="novel").id
    sid = db.create_scene(pid, "Ch1", content="John thinks and remembers.", summary="x").id
    ctx = gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    assert "[Screenplay Diagnostics]" not in ctx


def test_assistant_assembly_no_db_mutation_no_llm(monkeypatch):
    import logosforge.assistant as assistant
    from logosforge.assistant_context_policy import gather_injected_context
    calls = []
    monkeypatch.setattr(assistant, "chat_completion",
                        lambda *a, **k: calls.append(1) or ("", False))
    db = Database()
    pid = db.create_project("Film", narrative_engine="screenplay").id
    sid = db.create_scene(pid, "Open", content="INT. X - DAY\n\nJOHN\nHi.", summary="x").id
    before = len(db.get_all_scenes(pid))
    gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    assert calls == []
    assert len(db.get_all_scenes(pid)) == before


# ===========================================================================
# Health integration
# ===========================================================================


def test_health_includes_screenplay_categories():
    from logosforge.logos.health import HealthEngine
    from logosforge.logos.health import metric as M
    db = Database()
    pid = db.create_project("Film", narrative_engine="screenplay").id
    db.create_scene(
        pid, "Open",
        content="John thinks and remembers and feels and realizes everything.",
        summary="x",
    )
    report = HealthEngine(db, pid).generate_report()
    cats = {m.category for m in report.metrics}
    for c in (M.CAT_SCENE_ECONOMY, M.CAT_VISUAL_ACTION, M.CAT_DIALOGUE_ECONOMY,
              M.CAT_SCENE_TURN, M.CAT_CHARACTER_OBJECTIVE):
        assert c in cats


def test_health_defers_unsupported_categories():
    from logosforge.logos.health import HealthEngine
    from logosforge.logos.health import metric as M
    db = Database()
    pid = db.create_project("Film", narrative_engine="screenplay").id
    db.create_scene(pid, "Open", content="INT. X - DAY\n\nJohn waits.", summary="x")
    report = HealthEngine(db, pid).generate_report()
    by_cat = {m.category: m for m in report.metrics}
    # Cinematic Continuity stays deferred (Subtext is now populated in Phase 10D).
    assert by_cat[M.CAT_CINEMATIC_CONTINUITY].status == M.STATUS_UNKNOWN


def test_novel_health_has_no_screenplay_categories():
    from logosforge.logos.health import HealthEngine
    from logosforge.logos.health import metric as M
    db = Database()
    pid = db.create_project("Book", narrative_engine="novel").id
    db.create_scene(pid, "Ch1", content="It was a quiet morning.", summary="x")
    report = HealthEngine(db, pid).generate_report()
    cats = {m.category for m in report.metrics}
    assert M.CAT_SCENE_ECONOMY not in cats


# ===========================================================================
# Export
# ===========================================================================


def test_screenplay_diagnostics_json_export():
    from logosforge.export import export_screenplay_diagnostics_json
    db = Database()
    pid = db.create_project("Film", narrative_engine="screenplay").id
    db.create_scene(pid, "Open", content="INT. X - DAY\n\nJOHN\nHi.", summary="x")
    data = json.loads(export_screenplay_diagnostics_json(db, pid))
    assert data["project"]["writing_mode"] == "screenplay"
    assert len(data["scenes"]) == 1
    assert "economy_label" in data["scenes"][0]


def test_existing_exports_unbroken():
    from logosforge.export import export_json, export_screenplay
    db = Database()
    pid = db.create_project("Film", narrative_engine="screenplay").id
    db.create_scene(pid, "Open", content="INT. X - DAY\n\nJohn waits.", summary="x")
    assert json.loads(export_json(db, pid))["project"]["writing_mode"] == "screenplay"
    assert "Writing Mode: Screenplay" in export_screenplay(db, pid)


# ===========================================================================
# Strategy + provider guards
# ===========================================================================


def test_strategy_screenplay_profile_active():
    from logosforge.logos.strategy.router import StrategyRouter
    from logosforge.settings import get_manager
    get_manager().set("strategy_enabled", True)
    db = Database()
    pid = db.create_project("Film", narrative_engine="screenplay").id
    d = StrategyRouter(db, pid).decide("Manuscript")
    assert "screenplay" in d.active_strategies


def test_build_active_provider_unchanged():
    from logosforge.providers import build_active_provider
    from logosforge.settings import get_manager
    mgr = get_manager()
    mgr.set("ai_provider", "OpenAI")
    mgr.set("ai_base_url", "https://api.openai.com/v1")
    mgr.set("ai_model", "gpt-4o")
    p = build_active_provider(require_configured=True)
    assert p is not None and p.name == "OpenAI"
