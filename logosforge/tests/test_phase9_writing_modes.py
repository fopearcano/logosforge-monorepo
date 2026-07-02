"""Phase 9 — Project Writing Mode as project-level source of truth."""

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
# writing_modes module + data model
# ===========================================================================


def test_all_modes_and_default():
    import logosforge.writing_modes as wm
    assert wm.DEFAULT_MODE == "novel"
    assert wm.ALL_MODES == (
        "novel", "screenplay", "graphic_novel", "stage_script", "series",
    )


@pytest.mark.parametrize("mode", [
    "novel", "screenplay", "graphic_novel", "stage_script", "series",
])
def test_valid_modes(mode):
    import logosforge.writing_modes as wm
    assert wm.is_valid_mode(mode)
    assert wm.normalize_mode(mode) == mode


@pytest.mark.parametrize("bad", ["", None, "comic", "manga", "  ", "Novel"])
def test_invalid_mode_falls_back_to_novel(bad):
    import logosforge.writing_modes as wm
    assert wm.normalize_mode(bad) == "novel"
    assert wm.is_valid_mode(bad) is False


def test_project_model_has_writing_mode_via_field():
    """The project's writing mode IS the canonical narrative_engine field."""
    import logosforge.writing_modes as wm
    db = Database()
    proj = db.create_project("Saga", narrative_engine="screenplay")
    assert wm.get_project_writing_mode(proj) == "screenplay"
    assert wm.get_project_writing_mode_by_id(db, proj.id) == "screenplay"


def test_migration_legacy_project_defaults_to_novel():
    """A legacy project (no narrative_engine) resolves to novel."""
    import logosforge.writing_modes as wm
    db = Database()
    proj = db.create_project("Old")  # no engine specified
    assert wm.get_project_writing_mode(proj) == "novel"


def test_migration_is_idempotent_no_data_loss():
    import logosforge.writing_modes as wm
    db = Database()
    proj = db.create_project("Keep", narrative_engine="series")
    sid = db.create_scene(proj.id, "S1", content="x", summary="x").id
    # Re-running migration must not change mode or lose data.
    db._migrate()
    db._migrate()
    again = db.get_project_by_id(proj.id)
    assert wm.get_project_writing_mode(again) == "series"
    assert any(s.id == sid for s in db.get_all_scenes(proj.id))


def test_invalid_stored_mode_falls_back():
    import logosforge.writing_modes as wm
    db = Database()
    proj = db.create_project("Weird", narrative_engine="nonsense")
    # Unknown stored value resolves safely to novel.
    assert wm.get_project_writing_mode(proj) == "novel"


def test_set_project_writing_mode_normalizes_and_persists():
    import logosforge.writing_modes as wm
    db = Database()
    proj = db.create_project("P")
    stored = wm.set_project_writing_mode(db, proj.id, "graphic_novel")
    assert stored == "graphic_novel"
    assert wm.get_project_writing_mode_by_id(db, proj.id) == "graphic_novel"
    # Invalid input is normalized to novel.
    assert wm.set_project_writing_mode(db, proj.id, "garbage") == "novel"


def test_create_flow_saves_writing_mode():
    import logosforge.writing_modes as wm
    db = Database()
    proj = db.create_project("Stage", narrative_engine="stage_script")
    assert wm.get_project_writing_mode(proj) == "stage_script"


# ===========================================================================
# Structural vocabulary + medium constraints
# ===========================================================================


@pytest.mark.parametrize("mode,first,last", [
    ("novel", "Acts", "Scenes"),
    ("screenplay", "Acts", "Scenes"),
    ("graphic_novel", "Chapters", "Panels"),
    ("stage_script", "Acts", "Stage Directions"),
    ("series", "Seasons", "Scenes"),
])
def test_structural_vocabulary_per_mode(mode, first, last):
    import logosforge.writing_modes as wm
    units = wm.structural_units(mode)
    assert units[0] == first and units[-1] == last
    assert wm.structural_vocabulary(mode) == " / ".join(units)


def test_medium_constraints_distinct_and_nonempty():
    import logosforge.writing_modes as wm
    seen = {wm.medium_constraints(m) for m in wm.ALL_MODES}
    assert len(seen) == len(wm.ALL_MODES)  # all distinct
    assert all(s for s in seen)


def test_mode_context_block_shape():
    import logosforge.writing_modes as wm
    # Novel has no extra guidance line — the minimal 3-line shape.
    novel = wm.mode_context_block("novel")
    assert novel.startswith("[Project Mode]")
    assert "Mode: Novel" in novel
    assert "Primary constraints:" in novel
    assert novel.count("\n") == 2  # short — never a manual
    # Screenplay (Phase 10A) adds exactly one guidance line — still short.
    screen = wm.mode_context_block("screenplay")
    assert screen.startswith("[Project Mode]")
    assert "Mode: Screenplay" in screen
    assert screen.count("\n") == 3


# ===========================================================================
# Outline label adaptation (engine-driven, non-destructive)
# ===========================================================================


@pytest.mark.parametrize("engine,expected_top", [
    ("novel", "part"),
    ("screenplay", "act"),
    ("graphic_novel", "issue"),
    ("stage_script", "act"),
])
def test_outline_structural_units_adapt(engine, expected_top):
    from logosforge.outline_actions import engine_structural_units
    units = engine_structural_units(engine)
    assert units and units[0] == expected_top


def test_series_mode_does_not_crash_outline_model():
    from logosforge.outline_actions import (
        build_outline_generation_prompt,
        engine_structural_units,
    )
    units = engine_structural_units("series")
    assert units  # non-empty
    prompt = build_outline_generation_prompt("full", engine="series")
    assert isinstance(prompt, str) and prompt


# ===========================================================================
# Assistant context integration
# ===========================================================================


def test_assistant_context_includes_project_mode():
    from logosforge.assistant_context_policy import gather_injected_context
    db = Database()
    pid = db.create_project("Film", narrative_engine="screenplay").id
    ctx = gather_injected_context(db, pid, section_name="Manuscript")
    assert "[Project Mode]" in ctx
    assert "Mode: Screenplay" in ctx


def test_project_mode_block_can_be_disabled():
    from logosforge.assistant_context_policy import gather_injected_context
    from logosforge.settings import get_manager
    db = Database()
    pid = db.create_project("Film", narrative_engine="screenplay").id
    get_manager().set("include_project_mode_in_assistant_context", False)
    ctx = gather_injected_context(db, pid, section_name="Manuscript")
    assert "[Project Mode]" not in ctx


def test_project_mode_block_no_llm_no_db_mutation(monkeypatch):
    import logosforge.assistant as assistant
    from logosforge.assistant_context_policy import gather_injected_context
    calls = []
    monkeypatch.setattr(assistant, "chat_completion",
                        lambda *a, **k: calls.append(1) or ("", False))
    db = Database()
    pid = db.create_project("Film", narrative_engine="series").id
    db.create_scene(pid, "S", content="x", summary="x")
    before = len(db.get_all_scenes(pid))
    gather_injected_context(db, pid, section_name="Manuscript")
    assert calls == []
    assert len(db.get_all_scenes(pid)) == before


# ===========================================================================
# Logos context integration
# ===========================================================================


def test_logos_context_includes_writing_mode():
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = db.create_project("GN", narrative_engine="graphic_novel").id
    ctx = build_logos_context(db, pid, section_name="Manuscript")
    assert ctx.writing_mode == "graphic_novel"
    assert ctx.to_dict()["writing_mode"] == "graphic_novel"


def test_logos_context_writing_mode_defaults_novel():
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = db.create_project("Plain").id
    ctx = build_logos_context(db, pid)
    assert ctx.writing_mode == "novel"


# ===========================================================================
# Strategy Layer routing by mode
# ===========================================================================


@pytest.mark.parametrize("engine,expected", [
    ("novel", "novel"),
    ("screenplay", "screenplay"),
    ("graphic_novel", "graphic_novel"),
    ("stage_script", "stage_script"),
    ("series", "series"),
])
def test_strategy_activates_correct_medium_profile(engine, expected):
    from logosforge.logos.strategy.router import StrategyRouter
    from logosforge.settings import get_manager
    get_manager().set("strategy_enabled", True)
    db = Database()
    pid = db.create_project("S", narrative_engine=engine).id
    decision = StrategyRouter(db, pid).decide("Manuscript")
    # The medium strategy for the project's mode is active.
    assert expected in decision.active_strategies
    # Explanation mentions the project mode.
    assert engine in decision.explanation


def test_strategy_falls_back_to_novel_for_unknown_mode():
    from logosforge.logos.strategy.router import StrategyRouter
    from logosforge.settings import get_manager
    get_manager().set("strategy_enabled", True)
    db = Database()
    pid = db.create_project("U", narrative_engine="garbage").id
    decision = StrategyRouter(db, pid).decide("Manuscript")
    assert decision.dominant_strategy  # something resolved, no crash


# ===========================================================================
# Health / Diagnostics receive writing mode
# ===========================================================================


def test_health_engine_receives_writing_mode():
    from logosforge.logos.health import HealthEngine
    db = Database()
    pid = db.create_project("H", narrative_engine="screenplay").id
    report = HealthEngine(db, pid).generate_report()
    assert report.writing_mode == "screenplay"
    assert report.to_dict()["writing_mode"] == "screenplay"


def test_health_engine_explicit_writing_mode_override():
    from logosforge.logos.health import HealthEngine
    db = Database()
    pid = db.create_project("H").id  # novel
    report = HealthEngine(db, pid, writing_mode="series").generate_report()
    assert report.writing_mode == "series"


def test_diagnostics_engine_receives_writing_mode():
    from logosforge.logos.diagnostics import DiagnosticsEngine
    db = Database()
    pid = db.create_project("D", narrative_engine="stage_script").id
    engine = DiagnosticsEngine(db, pid)
    assert engine.writing_mode == "stage_script"
    # Still scans fine, no crash.
    engine.scan_project()


# ===========================================================================
# Export integration
# ===========================================================================


def test_export_json_includes_writing_mode():
    import json
    from logosforge.export import export_json
    db = Database()
    pid = db.create_project("E", narrative_engine="graphic_novel").id
    data = json.loads(export_json(db, pid))
    assert data["project"]["writing_mode"] == "graphic_novel"


def test_export_markdown_includes_writing_mode():
    from logosforge.export import export_markdown
    db = Database()
    pid = db.create_project("E", narrative_engine="stage_script").id
    md = export_markdown(db, pid)
    assert "Writing Mode: Stage Script" in md


def test_data_export_metadata_includes_writing_mode():
    from logosforge.data_export import _project_meta, ExportOptions
    db = Database()
    pid = db.create_project("E", narrative_engine="series").id
    meta = _project_meta(db, pid, ExportOptions())
    assert meta["writing_mode"] == "series"


# ===========================================================================
# Provider / Phase 8B guarantees unchanged
# ===========================================================================


def test_build_active_provider_untouched():
    from logosforge.providers import build_active_provider
    from logosforge.settings import get_manager
    mgr = get_manager()
    mgr.set("ai_provider", "OpenAI")
    mgr.set("ai_base_url", "https://api.openai.com/v1")
    mgr.set("ai_model", "gpt-4o")
    mgr.set("ai_api_key", "")
    p = build_active_provider(require_configured=True)
    assert p is not None and p.name == "OpenAI" and p.model == "gpt-4o"


def test_phase8b_injection_still_gated():
    """Phase 8B behavior intact: health still off by default, others on."""
    from logosforge.assistant_context_policy import gather_injected_context
    db = Database()
    pid = db.create_project("P", narrative_engine="novel").id
    db.create_psyke_entry(pid, "Alice", "character")
    db.create_scene(pid, "Open", content="Alice.", summary="Alice")
    ctx = gather_injected_context(db, pid, section_name="PSYKE")
    assert "[Strategy]" in ctx
    assert "[Diagnostics]" in ctx
    assert "[Narrative Health]" not in ctx
