"""Phase 8B — provider consolidation + controlled Assistant context injection."""

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
# Provider consolidation
# ===========================================================================


def _set_provider(name, base_url="", model="", key=""):
    from logosforge.settings import get_manager
    mgr = get_manager()
    mgr.set("ai_provider", name)
    mgr.set("ai_base_url", base_url)
    mgr.set("ai_model", model)
    mgr.set("ai_api_key", key)


def test_central_builder_default_returns_config():
    from logosforge.providers import build_active_provider
    _set_provider("", "")  # nothing configured
    p = build_active_provider()  # default mode -> always a config
    assert p is not None and p.name == "LM Studio"


def test_central_builder_require_configured_none_when_empty():
    from logosforge.providers import build_active_provider
    _set_provider("", "")
    assert build_active_provider(require_configured=True) is None


@pytest.mark.parametrize("name,base_url", [
    ("OpenAI", "https://api.openai.com/v1"),
    ("Anthropic", "https://api.anthropic.com"),
    ("OpenRouter", "https://openrouter.ai/api/v1"),
    ("LM Studio", "http://localhost:1234/v1"),
    ("Ollama", "http://localhost:11434/v1"),
])
def test_all_providers_resolve(name, base_url):
    from logosforge.providers import build_active_provider
    _set_provider(name, base_url, model="m", key="k")
    p = build_active_provider(require_configured=True)
    assert p is not None
    assert p.name == name and p.base_url == base_url and p.model == "m"


def test_wrappers_delegate_to_central_builder():
    """The consolidated wrappers all return what the central builder returns."""
    _set_provider("Anthropic", "https://api.anthropic.com", model="claude-opus-4-8")
    from logosforge.providers import build_active_provider
    central = build_active_provider()

    import logosforge.paragraph_energy as pe
    import logosforge.style_analysis as sa
    import logosforge.psyke_intent_llm as pil
    import logosforge.quantum_outliner.possibilities as poss
    import logosforge.quantum_outliner.llm_evaluator as lev
    import logosforge.quantum_outliner.relativity as rel
    import logosforge.api.routes.assistant as api_assist

    for mod in (pe, sa, pil, poss, lev, rel, api_assist):
        got = mod._build_provider()
        assert got.name == central.name == "Anthropic"
        assert got.model == "claude-opus-4-8"


def test_ui_wrappers_delegate_require_configured():
    from logosforge.ui.outline_ai import build_provider
    _set_provider("", "")
    assert build_provider() is None
    _set_provider("OpenAI", "https://api.openai.com/v1", model="gpt-4o")
    p = build_provider()
    assert p is not None and p.model == "gpt-4o"


def test_central_builder_never_logs_key(capsys):
    from logosforge.providers import build_active_provider
    _set_provider("OpenAI", "https://api.openai.com/v1", key="sk-secret-123")
    build_active_provider()
    out = capsys.readouterr()
    assert "sk-secret-123" not in out.out
    assert "sk-secret-123" not in out.err


def test_central_builder_does_not_mutate_settings():
    from logosforge.providers import build_active_provider
    from logosforge.settings import get_manager
    _set_provider("OpenAI", "https://api.openai.com/v1")
    before = dict(get_manager()._data)
    build_active_provider()
    assert get_manager()._data == before


# ===========================================================================
# Controlled Assistant context injection
# ===========================================================================


def _project():
    db = Database()
    pid = db.create_project("Saga", narrative_engine="screenplay").id
    db.create_psyke_entry(pid, "Alice", "character")  # detail-less -> diagnostic
    sid = db.create_scene(pid, "Opening", content="Alice.", summary="Alice").id
    return db, pid, sid


def test_default_injection_strategy_and_diagnostics_no_health():
    from logosforge.assistant_context_policy import gather_injected_context
    db, pid, sid = _project()
    ctx = gather_injected_context(db, pid, section_name="PSYKE", scene_id=sid)
    assert "[Strategy]" in ctx                # default ON
    assert "[Diagnostics]" in ctx             # default ON
    assert "[Narrative Health]" not in ctx    # default OFF


def test_strategy_omitted_when_disabled():
    from logosforge.assistant_context_policy import gather_injected_context
    from logosforge.settings import get_manager
    db, pid, sid = _project()
    get_manager().set("include_strategy_in_assistant_context", False)
    ctx = gather_injected_context(db, pid, section_name="PSYKE", scene_id=sid)
    assert "[Strategy]" not in ctx


def test_health_included_when_enabled_and_capped():
    from logosforge.assistant_context_policy import gather_injected_context
    from logosforge.settings import get_manager
    db, pid, sid = _project()
    get_manager().set("include_health_in_assistant_context", True)
    get_manager().set("max_health_risks_in_context", 2)
    ctx = gather_injected_context(db, pid, section_name="PSYKE", scene_id=sid)
    assert "[Narrative Health]" in ctx
    # The health block lists at most max_health_risks risk bullets.
    health_part = ctx.split("[Narrative Health]")[-1]
    # Stop at the next labelled block if present.
    for label in ("[Strategy]", "[Diagnostics]"):
        health_part = health_part.split(label)[0]
    assert health_part.count("\n- ") <= 2


def test_diagnostics_respect_max_limit():
    from logosforge.assistant_context_policy import gather_injected_context
    from logosforge.settings import get_manager
    db = Database()
    pid = db.create_project("Big", narrative_engine="novel").id
    for i in range(8):
        db.create_psyke_entry(pid, f"Char{i}", "character")  # 8 detail-less
        db.create_scene(pid, f"S{i}", content=f"Char{i} acts", summary=f"Char{i}")
    get_manager().set("max_diagnostics_in_context", 3)
    ctx = gather_injected_context(db, pid, section_name="PSYKE")
    diag_part = ctx.split("[Diagnostics]")[-1] if "[Diagnostics]" in ctx else ""
    assert diag_part.count("\n- ") <= 3


def test_all_off_yields_empty():
    from logosforge.assistant_context_policy import gather_injected_context
    from logosforge.settings import get_manager
    db, pid, sid = _project()
    for k in ("include_project_mode_in_assistant_context",  # Phase 9 block
              "include_screenplay_diagnostics_in_assistant_context",  # Phase 10C
              "include_screenplay_tracking_in_assistant_context",      # Phase 10D
              "include_screenplay_links_in_assistant_context",         # Phase 10E
              "include_screenplay_export_in_assistant_context",        # Phase 10F
              "include_professional_output_in_assistant_context",      # Phase 10H
              "include_production_draft_in_assistant_context",         # Phase 10J
              "include_revision_impact_in_assistant_context",          # Phase 10K
              "include_rewrite_sandbox_in_assistant_context",          # Phase 10L
              "include_controlled_apply_in_assistant_context",         # Phase 10M
              "include_project_intelligence_in_assistant_context",     # Phase 10N
              "include_guided_workflow_in_assistant_context",          # Phase 10O
              "include_knowledge_graph_in_assistant_context",          # Phase 10P
              "include_continuity_in_assistant_context",               # Phase 10Q
              "include_strategy_in_assistant_context",
              "include_health_in_assistant_context",
              "include_diagnostics_in_assistant_context"):
        get_manager().set(k, False)
    assert gather_injected_context(db, pid, section_name="PSYKE", scene_id=sid) == ""


def test_injection_does_not_mutate_db():
    from logosforge.assistant_context_policy import gather_injected_context
    db, pid, sid = _project()
    before = (len(db.get_all_scenes(pid)), len(db.get_all_psyke_entries(pid)))
    gather_injected_context(db, pid, section_name="PSYKE", scene_id=sid)
    after = (len(db.get_all_scenes(pid)), len(db.get_all_psyke_entries(pid)))
    assert before == after


def test_injection_does_not_call_llm(monkeypatch):
    import logosforge.assistant as assistant
    from logosforge.assistant_context_policy import gather_injected_context
    calls = []
    monkeypatch.setattr(assistant, "chat_completion",
                        lambda *a, **k: calls.append(1) or ("", False))
    db, pid, sid = _project()
    gather_injected_context(db, pid, section_name="PSYKE", scene_id=sid)
    assert calls == []


def test_injection_reads_current_project_no_leak():
    """Switching the project_id arg yields that project's context, not a cache."""
    from logosforge.assistant_context_policy import gather_injected_context
    db = Database()
    p1 = db.create_project("P1", narrative_engine="novel").id
    db.create_psyke_entry(p1, "Alice", "character")
    db.create_scene(p1, "S1", content="Alice", summary="Alice")
    p2 = db.create_project("P2", narrative_engine="novel").id  # empty
    from logosforge.settings import get_manager
    get_manager().set("include_health_in_assistant_context", True)
    ctx1 = gather_injected_context(db, p1, section_name="PSYKE")
    ctx2 = gather_injected_context(db, p2, section_name="PSYKE")
    # P1 has diagnostics; empty P2 has none of P1's findings.
    assert "Alice" in ctx1
    assert "Alice" not in ctx2


# ===========================================================================
# Event compatibility
# ===========================================================================


def test_conceptual_event_map_documents_real_signals():
    from logosforge.project_events import CONCEPTUAL_EVENT_MAP
    assert CONCEPTUAL_EVENT_MAP["manuscript_changed"] == ("scene_changed", "project_data_changed")
    for concept in ("timeline_changed", "graph_changed", "strategy_changed",
                    "health_report_changed", "assistant_settings_changed"):
        assert "project_data_changed" in CONCEPTUAL_EVENT_MAP[concept]


def test_emit_conceptual_raises_real_signals():
    from logosforge.project_events import emit_conceptual, get_event_bus
    bus = get_event_bus()
    fired = {"scene": [], "data": 0}
    bus.scene_changed.connect(lambda sid: fired["scene"].append(sid))
    bus.project_data_changed.connect(lambda: fired.__setitem__("data", fired["data"] + 1))
    emit_conceptual("manuscript_changed", scene_id=7)
    assert fired["scene"] == [7] and fired["data"] >= 1
    # Unknown concept falls back to project_data_changed (no crash).
    emit_conceptual("nonexistent_event")
    assert fired["data"] >= 2
