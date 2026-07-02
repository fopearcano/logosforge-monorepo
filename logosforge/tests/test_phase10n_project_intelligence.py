"""Phase 10N — Project Intelligence Dashboard + Decision Radar."""

from __future__ import annotations

import json
import warnings

import pytest

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.project_intelligence import build_project_intelligence_report as build


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


def _novel(db=None):
    db = db or Database()
    pid = db.create_project("My Novel", narrative_engine="novel").id
    db.create_psyke_entry(pid, "Alice", "character")  # empty notes
    for i in range(3):
        db.create_scene(pid, f"S{i}", content="word " * 20,
                        summary=("sum" if i == 0 else ""))
    return db, pid


# ===========================================================================
# Service
# ===========================================================================


def test_report_empty_project():
    db = Database()
    pid = db.create_project("", narrative_engine="novel").id
    rep = build(db, pid)
    assert rep.overview["total_scenes"] == 0
    assert any(c.id == "missing_title" for c in rep.radar)


def test_report_with_content():
    db, pid = _novel()
    rep = build(db, pid)
    assert rep.overview["total_scenes"] == 3 and rep.overview["total_words"] == 60
    assert rep.writing_mode == "novel"
    assert rep.psyke["total"] == 1 and rep.psyke["empty_notes"] == 1
    assert rep.structure["scenes_without_summary"] == 2


def test_report_no_db_mutation():
    db, pid = _novel()
    before = (len(db.get_all_scenes(pid)), len(db.get_all_psyke_entries(pid)))
    build(db, pid)
    after = (len(db.get_all_scenes(pid)), len(db.get_all_psyke_entries(pid)))
    assert before == after


def test_report_no_llm(monkeypatch):
    import logosforge.assistant as assistant
    calls = []
    monkeypatch.setattr(assistant, "chat_completion",
                        lambda *a, **k: calls.append(1) or ("", False))
    db, pid = _novel()
    build(db, pid)
    assert calls == []


def test_report_serializable():
    db, pid = _novel()
    assert json.dumps(build(db, pid).to_dict())


def test_light_mode_skips_health():
    db, pid = _novel()
    assert build(db, pid, light=True).health == {}
    assert build(db, pid, light=False).health.get("available") is not None


def test_current_project_only():
    db, p1 = _novel()
    p2 = db.create_project("Other", narrative_engine="novel").id
    rep = build(db, p2)
    assert rep.overview["total_scenes"] == 0   # p1 content not leaked


# ===========================================================================
# Decision Radar
# ===========================================================================


def test_missing_summary_card():
    db, pid = _novel()
    rep = build(db, pid)
    assert any(c.id == "scenes_no_summary" for c in rep.radar)


def test_empty_psyke_card():
    db, pid = _novel()
    rep = build(db, pid)
    assert any(c.id == "psyke_empty" for c in rep.radar)


def test_cards_ranked_blocking_first():
    db = Database()
    pid = db.create_project("Film", narrative_engine="screenplay").id
    # No scenes -> empty screenplay -> export blocking.
    rep = build(db, pid)
    sevs = [c.severity for c in rep.radar]
    rank = {"blocking": 0, "warning": 1, "suggestion": 2, "opportunity": 3, "info": 4}
    assert sevs == sorted(sevs, key=lambda s: rank.get(s, 5))


def test_cards_capped():
    db, pid = _novel()
    rep = build(db, pid)
    assert len(rep.radar) <= 10


def test_cards_have_confidence_and_traceable_section():
    db, pid = _novel()
    for c in build(db, pid).radar:
        assert c.confidence in ("confirmed", "likely", "possible", "unknown")
        assert c.category and c.severity


# ===========================================================================
# Workflow integration (rewrite / apply / revision)
# ===========================================================================


def test_pending_rewrite_preferred_card():
    import logosforge.rewrite_sandbox.engine as E
    db, pid = _novel()
    sid = db.get_all_scenes(pid)[0].id
    sess = E.create_rewrite_session(db, pid, source_type="scene", source_id=sid,
                                    source_text="x")
    r = E.generate_rewrite_variant(db, pid, session_id=sess.id, source_text="x",
                                   chat_fn=lambda m, p: "variant",
                                   provider_resolver=lambda: object())
    db.update_rewrite_variant(r.variant_id, status="preferred")
    rep = build(db, pid)
    assert any(c.id == "rewrite_preferred" for c in rep.radar)


def test_pending_controlled_apply_card():
    import logosforge.controlled_apply.service as CA
    db, pid = _novel()
    sid = db.get_all_scenes(pid)[0].id
    CA.create_apply_operation(db, pid, target_type="scene", target_id=sid,
                              proposed_text="New text.", source_type="assistant")
    rep = build(db, pid)
    assert any(c.id == "apply_pending" for c in rep.radar)


# ===========================================================================
# Writing mode awareness
# ===========================================================================


def test_novel_radar_has_no_production_cards():
    db, pid = _novel()
    cats = {c.category for c in build(db, pid).radar}
    assert "production" not in cats


def test_screenplay_export_card():
    db = Database()
    pid = db.create_project("Film", narrative_engine="screenplay").id
    db.create_scene(pid, "V", content="INT. X - DAY\n\nAction.", summary="x")
    rep = build(db, pid)
    assert rep.export.get("mode") == "screenplay" and rep.export.get("checked")


def test_screenplay_production_card_when_active():
    import logosforge.screenplay_production as P
    db = Database()
    pid = db.create_project("Film", narrative_engine="screenplay").id
    db.create_scene(pid, "V", content="INT. X - DAY\n\nAction.", summary="x")
    P.enable_production_mode(db, pid)
    rep = build(db, pid)
    assert any(c.category == "production" for c in rep.radar)


# ===========================================================================
# Logos
# ===========================================================================


def test_pi_logos_actions_registered():
    from logosforge.logos import actions as A
    from logosforge.logos import deterministic as det
    for name in ("pi_dashboard_status", "pi_decision_radar"):
        act = A.get_action(name)
        assert act and act.deterministic and act.modes == ()
        assert det.is_deterministic(name)
    assert A.get_action("pi_explain_dashboard") is not None  # generative


def test_pi_actions_available_in_novel():
    from logosforge.logos.controller import LogosController
    db, pid = _novel()
    ctl = LogosController(db)
    names = [a.name for a in ctl.available_actions("Manuscript", writing_mode="novel")]
    assert "pi_dashboard_status" in names and "pi_decision_radar" in names


def test_pi_status_action_no_llm():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def boom(*a, **k):
        raise AssertionError("deterministic dashboard action must not use the LLM")

    db, pid = _novel()
    ctl = LogosController(db, provider_resolver=boom, chat_fn=boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript")
    res = ctl.run(ctx, "pi_decision_radar")
    assert res.ok and res.proposed_operations == []


# ===========================================================================
# Assistant context
# ===========================================================================


def test_assistant_pi_block_present_and_capped():
    from logosforge.assistant_context_policy import gather_injected_context
    db, pid = _novel()
    sid = db.get_all_scenes(pid)[0].id
    ctx = gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    assert "[Project Intelligence]" in ctx
    block = ctx.split("[Project Intelligence]")[-1].split("[")[0]
    assert block.count("\n") < 8


def test_assistant_pi_block_no_llm_no_mutation(monkeypatch):
    import logosforge.assistant as assistant
    from logosforge.assistant_context_policy import gather_injected_context
    calls = []
    monkeypatch.setattr(assistant, "chat_completion",
                        lambda *a, **k: calls.append(1) or ("", False))
    db, pid = _novel()
    sid = db.get_all_scenes(pid)[0].id
    before = len(db.get_all_scenes(pid))
    gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    assert calls == [] and len(db.get_all_scenes(pid)) == before


def test_assistant_pi_block_no_cross_project_leak():
    from logosforge.assistant_context_policy import gather_injected_context
    db, p1 = _novel()
    p2 = db.create_project("Other", narrative_engine="novel").id
    s2 = db.create_scene(p2, "S", content="y", summary="x").id
    ctx2 = gather_injected_context(db, p2, section_name="Manuscript", scene_id=s2)
    assert "Alice" not in ctx2 and "My Novel" not in ctx2


def test_assistant_pi_block_disableable():
    from logosforge.assistant_context_policy import gather_injected_context
    from logosforge.settings import get_manager
    db, pid = _novel()
    sid = db.get_all_scenes(pid)[0].id
    get_manager().set("include_project_intelligence_in_assistant_context", False)
    ctx = gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    assert "[Project Intelligence]" not in ctx


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
