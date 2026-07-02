"""Logos Phase 7 — Assistant Strategy Layer / medium-aware router."""

from __future__ import annotations

import json
import warnings

import pytest

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.logos.strategy import (
    StrategyRouter,
    gather_strategy_context,
    get_strategy,
    list_strategies,
)
from logosforge.logos.strategy import registry as reg
from logosforge.logos.strategy.conflicts import (
    resolve_causality,
    resolve_conflict_principle,
    template_forces_conflict,
)
from logosforge.logos.strategy.strategy import NarrativeStrategy, StrategyDecision


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path, raising=False)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json", raising=False)
    # Pin gomckee OFF by default — the plugin-manager singleton is process-global
    # and other suites may leave it enabled; tests that need it ON re-patch it.
    import logosforge.gomckee_bridge as gb
    monkeypatch.setattr(gb, "is_gomckee_enabled", lambda: False)
    yield
    settings._instance = None


def _project(engine="novel"):
    db = Database()
    pid = db.create_project("P", narrative_engine=engine).id
    return db, pid


# -- Serialization -----------------------------------------------------------


def test_strategy_serializable():
    s = NarrativeStrategy(id="x", name="X", applies_to_modes=("novel",))
    json.dumps(s.to_dict())
    assert s.applies_to("novel") and not s.applies_to("screenplay")


def test_decision_serializable():
    db, pid = _project()
    d = StrategyRouter(db, pid).decide("Manuscript")
    blob = json.dumps(d.to_dict())
    assert "api_key" not in blob.lower()
    assert d.to_dict()["dominant_strategy"]


# -- Registry ----------------------------------------------------------------


def test_registry_lists_default_strategies():
    ids = {s.id for s in list_strategies()}
    assert {
        reg.S_DEFAULT, reg.S_NOVEL, reg.S_SCREENPLAY, reg.S_GRAPHIC_NOVEL,
        reg.S_STAGE_SCRIPT, reg.S_SERIES, reg.S_GOMCKEE, reg.S_CONTROLLING_IDEA,
        reg.S_PSYKE_CONTINUITY, reg.S_NARRATIVE_HEALTH,
        reg.S_QUANTUM_CLASSICAL, reg.S_QUANTUM_LAMBDA,
    } <= ids


# -- Mode -> strategy --------------------------------------------------------


@pytest.mark.parametrize("engine,strategy_id", [
    ("novel", reg.S_NOVEL),
    ("screenplay", reg.S_SCREENPLAY),
    ("graphic_novel", reg.S_GRAPHIC_NOVEL),
    ("stage_script", reg.S_STAGE_SCRIPT),
    ("series", reg.S_SERIES),
])
def test_mode_activates_medium_strategy(engine, strategy_id):
    db, pid = _project(engine)
    d = StrategyRouter(db, pid).decide("Manuscript")
    assert d.dominant_strategy == strategy_id
    assert strategy_id in d.active_strategies


def test_missing_mode_defaults_to_novel():
    db = Database()
    pid = db.create_project("NoEngine").id  # legacy: no narrative_engine
    d = StrategyRouter(db, pid).decide("Manuscript")
    assert d.narrative_engine == "novel"
    assert d.dominant_strategy == reg.S_NOVEL


# -- Logos actions differ by mode --------------------------------------------


def test_logos_actions_differ_by_mode():
    db_s, pid_s = _project("screenplay")
    db_n, pid_n = _project("novel")
    sa = StrategyRouter(db_s, pid_s).recommended_logos_actions("Manuscript")
    na = StrategyRouter(db_n, pid_n).recommended_logos_actions("Manuscript")
    assert sa != na
    # Phase 10A/10C: screenplay surfaces its mode-specific actions first (the
    # deterministic scene-economy diagnostic leads); novel surfaces revision/voice
    # and never sees screenplay-only actions.
    assert sa[0] == "sp_diagnose_scene_economy"
    assert na[0] == "suggest_revision"
    assert not any(n.startswith("sp_") for n in na)


def test_recommended_actions_are_real():
    from logosforge.logos.actions import get_action
    db, pid = _project("screenplay")
    for action in StrategyRouter(db, pid).recommended_logos_actions("Manuscript"):
        assert get_action(action) is not None


# -- Go McKee only when enabled ----------------------------------------------


def test_gomckee_inactive_by_default():
    db, pid = _project("novel")
    d = StrategyRouter(db, pid).decide("Manuscript")
    assert reg.S_GOMCKEE not in d.active_strategies


def test_gomckee_active_when_enabled(monkeypatch):
    import logosforge.gomckee_bridge as gb
    monkeypatch.setattr(gb, "is_gomckee_enabled", lambda: True)
    db, pid = _project("novel")
    d = StrategyRouter(db, pid).decide("Manuscript")
    assert reg.S_GOMCKEE in d.active_strategies


# -- Template / conflict resolution ------------------------------------------


def test_template_forces_conflict_table():
    assert template_forces_conflict("save_the_cat")
    assert template_forces_conflict("three_act")
    assert not template_forces_conflict("story_circle")
    assert not template_forces_conflict("kishotenketsu")
    assert template_forces_conflict("")  # conservative default


def test_contrast_template_does_not_force_mckee_conflict(monkeypatch):
    import logosforge.gomckee_bridge as gb
    monkeypatch.setattr(gb, "is_gomckee_enabled", lambda: True)
    db, pid = _project("novel")
    db.save_project_settings(pid, {"outline_template": "story_circle"})
    d = StrategyRouter(db, pid).decide("Outline")
    # McKee is suppressed because the template is contrast-based.
    assert reg.S_GOMCKEE in d.suppressed_strategies


def test_conflict_forced_template_keeps_mckee(monkeypatch):
    import logosforge.gomckee_bridge as gb
    monkeypatch.setattr(gb, "is_gomckee_enabled", lambda: True)
    db, pid = _project("novel")
    db.save_project_settings(pid, {"outline_template": "save_the_cat"})
    d = StrategyRouter(db, pid).decide("Outline")
    assert reg.S_GOMCKEE not in d.suppressed_strategies


def test_resolve_conflict_principle_helper():
    stance, note = resolve_conflict_principle(
        "conflict", project_stance="emphasize", template_key="story_circle",
    )
    assert stance == "allow" and "contrast" in note
    stance2, _ = resolve_conflict_principle(
        "conflict", project_stance="emphasize", template_key="save_the_cat",
    )
    assert stance2 == "emphasize"


# -- Lambda / Classical ------------------------------------------------------


def test_classical_by_default():
    db, pid = _project("novel")
    d = StrategyRouter(db, pid).decide("Manuscript")
    assert reg.S_QUANTUM_CLASSICAL in d.active_strategies
    assert reg.S_QUANTUM_LAMBDA in d.suppressed_strategies


def test_lambda_overrides_classical():
    db, pid = _project("novel")
    from logosforge.quantum_outliner.state import OutlineMode, get_state
    get_state(pid).outline_mode = OutlineMode.LAMBDA
    d = StrategyRouter(db, pid).decide("Manuscript")
    assert reg.S_QUANTUM_LAMBDA in d.active_strategies
    assert reg.S_QUANTUM_CLASSICAL in d.suppressed_strategies
    assert any("Lambda" in n for n in d.reasoning_notes)


def test_resolve_causality_helper():
    stance, note = resolve_causality(lambda_on=True)
    assert stance == "allow" and "Lambda" in note
    stance2, _ = resolve_causality(lambda_on=False)
    assert stance2 == "emphasize"


# -- Context policy ----------------------------------------------------------


def test_context_policy_includes_only_relevant_blocks():
    db, pid = _project("screenplay")
    d = StrategyRouter(db, pid).decide("Manuscript")
    # Screenplay context is lean: scene + psyke + outline, no story_memory dump.
    assert "scene" in d.included_context_blocks
    assert "story_memory" not in d.included_context_blocks
    db2, pid2 = _project("novel")
    d2 = StrategyRouter(db2, pid2).decide("Manuscript")
    assert "story_memory" in d2.included_context_blocks  # novel includes it


# -- Explainability ----------------------------------------------------------


def test_explanation_contains_strategy_and_reason():
    db, pid = _project("screenplay")
    d = StrategyRouter(db, pid).decide("Manuscript")
    assert "Screenplay Strategy" in d.explanation
    assert "screenplay" in d.explanation
    assert "Manuscript" in d.explanation


# -- User override -----------------------------------------------------------


def test_user_override_beats_project_mode():
    import logosforge.settings as settings
    settings.get_manager().set("strategy_user_mode_override", "screenplay")
    db, pid = _project("novel")
    d = StrategyRouter(db, pid).decide("Manuscript")
    assert d.dominant_strategy == reg.S_SCREENPLAY


def test_strategy_disabled_uses_default():
    import logosforge.settings as settings
    settings.get_manager().set("strategy_enabled", False)
    db, pid = _project("screenplay")
    d = StrategyRouter(db, pid).decide("Manuscript")
    assert d.dominant_strategy == reg.S_DEFAULT


# -- PSYKE continuity for entity sections ------------------------------------


def test_psyke_section_adds_continuity_strategy():
    db, pid = _project("novel")
    d = StrategyRouter(db, pid).decide("PSYKE")
    assert reg.S_PSYKE_CONTINUITY in d.active_strategies


# -- Safety ------------------------------------------------------------------


def test_routing_does_not_mutate_db():
    db, pid = _project("novel")
    db.create_scene(pid, "S1", act="Act I", summary="x")
    before = (len(db.get_all_scenes(pid)), len(db.get_all_psyke_entries(pid)))
    StrategyRouter(db, pid).decide("Manuscript")
    StrategyRouter(db, pid).decide("PSYKE")
    after = (len(db.get_all_scenes(pid)), len(db.get_all_psyke_entries(pid)))
    assert before == after


def test_no_llm_calls_during_routing(monkeypatch):
    import logosforge.assistant as assistant
    calls = []
    monkeypatch.setattr(assistant, "chat_completion",
                        lambda *a, **k: calls.append(1) or ("", False))
    db, pid = _project("screenplay")
    StrategyRouter(db, pid).decide("Manuscript")
    gather_strategy_context(db, pid, "Manuscript")
    assert calls == []


def test_strategy_context_block_format():
    db, pid = _project("screenplay")
    text = gather_strategy_context(db, pid, "Manuscript")
    assert text.startswith("[Strategy]")
    assert "Screenplay Strategy" in text
