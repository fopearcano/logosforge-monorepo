"""Phase 10A — Screenplay Mode foundation.

Covers the canonical element taxonomy, mode-aware Logos actions, Assistant
screenplay guidance, Strategy activation, Health/Diagnostics mode awareness, and
conservative screenplay text export. No provider/backend changes; no other
medium engines; per-block persistence + Shot/Note editor styling are 10B.
"""

from __future__ import annotations

import warnings

import pytest

warnings.filterwarnings("ignore")

from logosforge.db import Database


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


# ===========================================================================
# Element taxonomy
# ===========================================================================


def test_canonical_screenplay_elements_exist():
    import logosforge.screenplay as sp
    assert sp.ELEMENT_KEYS == (
        "scene_heading", "action", "character", "parenthetical",
        "dialogue", "transition", "shot", "note",
    )
    for key in sp.ELEMENT_KEYS:
        assert sp.is_valid_element(key)
        el = sp.get_element(key)
        assert el and el.label and el.role


def test_uppercase_and_dialogue_flags():
    import logosforge.screenplay as sp
    assert sp.is_uppercase_element("scene_heading")
    assert sp.is_uppercase_element("character")
    assert sp.is_uppercase_element("transition")
    assert not sp.is_uppercase_element("action")
    assert not sp.is_uppercase_element("dialogue")
    assert set(sp.dialogue_elements()) == {"character", "parenthetical", "dialogue"}
    assert "scene_heading" in sp.structural_elements()


def test_normalize_caps_only_uppercases_uppercase_elements():
    import logosforge.screenplay as sp
    assert sp.normalize_caps("character", "john") == "JOHN"
    assert sp.normalize_caps("scene_heading", "int. bar - night") == "INT. BAR - NIGHT"
    assert sp.normalize_caps("action", "John waits.") == "John waits."
    assert sp.normalize_caps("dialogue", "Hello.") == "Hello."
    assert sp.normalize_caps("character", "") == ""


def test_scene_heading_prefixes_present():
    import logosforge.screenplay as sp
    assert "INT." in sp.SCENE_HEADING_PREFIXES
    assert "EXT." in sp.SCENE_HEADING_PREFIXES


def test_character_suggestions_from_psyke_uppercased_and_filtered():
    import logosforge.screenplay as sp
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay").id
    db.create_psyke_entry(pid, "Alice", "character")
    db.create_psyke_entry(pid, "Bob", "character")
    db.create_psyke_entry(pid, "The Tower", "place")
    sug = sp.character_suggestions(db, pid)
    assert sug == ["ALICE", "BOB"]  # places excluded, uppercased, ordered


# ===========================================================================
# Manuscript / writing-format separation (no destructive change to the editor)
# ===========================================================================


def test_screenplay_editor_format_still_six_elements_unchanged():
    """Editor visual grammar is untouched; Shot/Note remain taxonomy-only (10B)."""
    from logosforge.writing_formats import SCREENPLAY
    names = [e.name for e in SCREENPLAY.elements]
    assert names == ["scene_heading", "action", "character",
                     "dialogue", "parenthetical", "transition"]


def test_novel_format_has_no_screenplay_only_elements():
    from logosforge.writing_formats import NOVEL
    novel_names = {e.name for e in NOVEL.elements}
    assert "scene_heading" not in novel_names
    assert "character" not in novel_names
    assert "dialogue" not in novel_names


def test_element_type_is_not_project_writing_mode():
    """Applying a screenplay element type must not change Project.writing_mode."""
    from logosforge.writing_modes import get_project_writing_mode_by_id
    import logosforge.screenplay as sp
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay").id
    # Choosing/normalizing an element type is pure UI/text state.
    sp.normalize_caps("character", "alice")
    assert get_project_writing_mode_by_id(db, pid) == "screenplay"


# ===========================================================================
# Logos actions — mode-aware
# ===========================================================================


def test_screenplay_logos_actions_registered_and_restricted():
    from logosforge.logos import actions as A
    for name in ("sp_visual_action", "sp_check_scene_turn", "sp_reduce_interiority",
                 "sp_clarify_objective", "sp_scene_economy",
                 "sp_sequence_logic", "sp_act_turn", "sp_central_question",
                 "sp_track_setup_payoff", "sp_causal_chain", "sp_visual_turn"):
        act = A.get_action(name)
        assert act is not None
        assert act.modes == ("screenplay",)
        assert act.destructive is False


def test_screenplay_actions_appear_in_screenplay_mode():
    from logosforge.logos import actions as A
    ms = [a.name for a in A.list_actions_for_section("Manuscript", writing_mode="screenplay")]
    assert "sp_visual_action" in ms
    # Mode-agnostic actions still present.
    assert "improve_dialogue" in ms


def test_screenplay_actions_hidden_in_novel_mode():
    from logosforge.logos import actions as A
    ms = [a.name for a in A.list_actions_for_section("Manuscript", writing_mode="novel")]
    assert "sp_visual_action" not in ms
    assert "sp_reduce_interiority" not in ms
    # Mode-agnostic actions are unaffected.
    assert "improve_dialogue" in ms


def test_unfiltered_listing_is_backward_compatible():
    """No writing_mode arg = original behavior (everything for the section)."""
    from logosforge.logos import actions as A
    ms = [a.name for a in A.list_actions_for_section("Manuscript")]
    assert "sp_visual_action" in ms and "improve_dialogue" in ms


def test_controller_orders_screenplay_actions_first():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("S", narrative_engine="screenplay")
    ctl = LogosController(db)
    names = [a.name for a in ctl.available_actions("Manuscript", writing_mode="screenplay")]
    assert names[0].startswith("sp_")  # screenplay-preferred surfaces first
    # In novel mode the screenplay-only ones are gone.
    novel_names = [a.name for a in ctl.available_actions("Manuscript", writing_mode="novel")]
    assert not any(n.startswith("sp_") for n in novel_names)


def test_screenplay_actions_run_through_preview_path():
    """A registered screenplay action executes via the controller (faked chat)."""
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay").id
    sid = db.create_scene(pid, "Open", content="Alice thinks about her past.",
                          summary="x").id
    ctx = build_logos_context(
        db, pid, section_name="Manuscript", current_scene_id=sid,
        selected_text="Alice thinks about her past.",
    )
    ctl = LogosController(db, chat_fn=lambda messages, provider: "- externalize as action")
    result = ctl.run(ctx, "sp_visual_action")
    assert result.ok


# ===========================================================================
# Assistant context — screenplay guidance
# ===========================================================================


def test_assistant_context_has_screenplay_guidance():
    from logosforge.assistant_context_policy import gather_injected_context
    db = Database()
    pid = db.create_project("Film", narrative_engine="screenplay").id
    ctx = gather_injected_context(db, pid, section_name="Manuscript")
    assert "Mode: Screenplay" in ctx
    assert "cinematically" in ctx.lower()
    assert "novelistic interior exposition" in ctx.lower()


def test_novel_context_has_no_screenplay_guidance():
    from logosforge.assistant_context_policy import gather_injected_context
    db = Database()
    pid = db.create_project("Book", narrative_engine="novel").id
    ctx = gather_injected_context(db, pid, section_name="Manuscript")
    assert "cinematically" not in ctx.lower()
    assert "novelistic interior exposition" not in ctx.lower()


# ===========================================================================
# Strategy / LogosContext / Health / Diagnostics
# ===========================================================================


def test_strategy_selects_screenplay_profile():
    from logosforge.logos.strategy.router import StrategyRouter
    from logosforge.settings import get_manager
    get_manager().set("strategy_enabled", True)
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay").id
    d = StrategyRouter(db, pid).decide("Manuscript")
    assert "screenplay" in d.active_strategies
    assert "screenplay" in d.explanation


def test_strategy_manual_override_still_wins():
    from logosforge.logos.strategy.router import StrategyRouter
    from logosforge.settings import get_manager
    get_manager().set("strategy_enabled", True)
    get_manager().set("strategy_user_mode_override", "novel")
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay").id
    d = StrategyRouter(db, pid).decide("Manuscript")
    assert "novel" in d.active_strategies  # override beats project mode


def test_logos_context_carries_screenplay_mode():
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay").id
    assert build_logos_context(db, pid, section_name="Manuscript").writing_mode == "screenplay"


def test_health_and_diagnostics_receive_screenplay_mode():
    from logosforge.logos.health import HealthEngine
    from logosforge.logos.diagnostics import DiagnosticsEngine
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay").id
    assert HealthEngine(db, pid).generate_report().writing_mode == "screenplay"
    assert DiagnosticsEngine(db, pid).writing_mode == "screenplay"


# ===========================================================================
# Export
# ===========================================================================


def test_screenplay_export_includes_writing_mode_and_slugs():
    from logosforge.export import export_screenplay
    db = Database()
    pid = db.create_project("Heist", narrative_engine="screenplay").id
    db.create_scene(pid, "The Vault", content="They crack the safe.", summary="x")
    out = export_screenplay(db, pid)
    assert "Writing Mode: Screenplay" in out
    assert "THE VAULT" in out  # slug line uppercased
    assert "They crack the safe." in out


def test_novel_export_unbroken_by_screenplay_changes():
    from logosforge.export import export_manuscript, export_json
    import json
    db = Database()
    pid = db.create_project("Book", narrative_engine="novel").id
    db.create_scene(pid, "Chapter One", content="It was a quiet morning.", summary="x")
    txt = export_manuscript(db, pid)
    assert "It was a quiet morning." in txt
    assert "Writing Mode: Screenplay" not in txt
    data = json.loads(export_json(db, pid))
    assert data["project"]["writing_mode"] == "novel"


def test_screenplay_export_robust_when_no_scenes():
    from logosforge.export import export_screenplay
    db = Database()
    pid = db.create_project("Empty", narrative_engine="screenplay").id
    out = export_screenplay(db, pid)  # must not raise
    assert "Writing Mode: Screenplay" in out


# ===========================================================================
# Guards: provider + prior phases
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
