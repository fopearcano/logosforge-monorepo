"""Phase 10L — Adaptive Rewrite Sandbox."""

from __future__ import annotations

import json
import warnings

import pytest

warnings.filterwarnings("ignore")

from logosforge.db import Database
import logosforge.rewrite_sandbox.engine as E
from logosforge.rewrite_sandbox import strategies as S
from logosforge.rewrite_sandbox.scoring import score_rewrite
from logosforge.rewrite_sandbox.prompt_builder import build_rewrite_prompt


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


_FAKE = lambda messages, provider: "Alice entered. The night clung to her."  # noqa: E731


def _proj(db=None, mode="novel"):
    db = db or Database()
    pid = db.create_project("P", narrative_engine=mode).id
    db.create_psyke_entry(pid, "Alice", "character")
    src = "Alice walked in. She remembered everything about that night."
    sid = db.create_scene(pid, "Ch1", content=src, summary="x").id
    return db, pid, sid, src


# ===========================================================================
# Migration / model
# ===========================================================================


def test_existing_db_opens_no_sessions():
    db = Database()
    pid = db.create_project("Old").id
    assert db.get_rewrite_sessions(pid) == []
    assert db.get_latest_rewrite_session(pid) is None


def test_session_variant_apply_crud():
    db, pid, sid, src = _proj()
    sess = db.create_rewrite_session(pid, source_type="scene", source_id=sid)
    v = db.create_rewrite_variant(pid, sess.id, label="V1", variant_text="x")
    rec = db.create_rewrite_apply_record(pid, sess.id, v.id, source_type="scene",
                                         source_id=sid)
    assert sess.id and v.id and rec.id
    assert len(db.get_rewrite_variants(sess.id)) == 1


# ===========================================================================
# Strategies
# ===========================================================================


def test_strategies_mode_aware():
    sp = {s.key for s in S.strategies_for_mode("screenplay")}
    nv = {s.key for s in S.strategies_for_mode("novel")}
    assert "dialogue_economy" in sp and "dialogue_economy" not in nv
    assert "interiority_increase" in nv and "interiority_increase" not in sp
    assert "clarify" in sp and "clarify" in nv          # general present in both


def test_strategy_validity():
    assert S.is_valid_for_mode("dialogue_economy", "screenplay")
    assert not S.is_valid_for_mode("dialogue_economy", "novel")
    assert S.get_strategy("compress") is not None


# ===========================================================================
# Prompt builder
# ===========================================================================


def test_prompt_includes_mode_and_source_no_dump():
    db, pid, sid, src = _proj()
    p = build_rewrite_prompt(db, pid, writing_mode="novel", source_type="scene",
                             source_text=src, strategy_key="compress",
                             user_instruction="tighten")
    assert "Novel" in p.system or "Novel" in p.constraints
    assert src in p.user                                  # source included
    assert "preserve the source language" in p.system.lower()
    # No full project dump: only the source text is present, not other scenes.
    assert "Compress" in " ".join(p.context_blocks)


def test_prompt_psyke_capped_and_optional():
    db, pid, sid, src = _proj()
    p = build_rewrite_prompt(db, pid, writing_mode="novel", source_type="scene",
                             source_text=src, include_psyke=True)
    assert any("PSYKE" in b for b in p.context_blocks)
    p2 = build_rewrite_prompt(db, pid, writing_mode="novel", source_type="scene",
                              source_text=src, include_psyke=False)
    assert not any("PSYKE" in b for b in p2.context_blocks)


# ===========================================================================
# Engine — generation (no canonical mutation)
# ===========================================================================


def test_create_session():
    db, pid, sid, src = _proj()
    sess = E.create_rewrite_session(db, pid, source_type="scene", source_id=sid,
                                    source_text=src)
    assert sess.status == "open" and sess.writing_mode == "novel"
    assert sess.source_text_hash


def test_generate_variant_no_canonical_mutation():
    db, pid, sid, src = _proj()
    sess = E.create_rewrite_session(db, pid, source_type="scene", source_id=sid,
                                    source_text=src)
    r = E.generate_rewrite_variant(db, pid, session_id=sess.id, source_text=src,
                                   strategy_key="compress", chat_fn=_FAKE,
                                   provider_resolver=lambda: object())
    assert r.ok and r.variant_id
    assert db.get_scene_by_id(sid).content == src        # canonical unchanged
    assert r.score and "length_delta" in r.score


def test_generate_empty_source_handled():
    db, pid, sid, src = _proj()
    sess = E.create_rewrite_session(db, pid, source_type="scene", source_id=sid)
    r = E.generate_rewrite_variant(db, pid, session_id=sess.id, source_text="",
                                   chat_fn=_FAKE, provider_resolver=lambda: object())
    assert not r.ok and "Empty" in r.error


def test_generate_empty_ai_output_handled():
    db, pid, sid, src = _proj()
    sess = E.create_rewrite_session(db, pid, source_type="scene", source_id=sid)
    r = E.generate_rewrite_variant(db, pid, session_id=sess.id, source_text=src,
                                   chat_fn=lambda m, p: "  ",
                                   provider_resolver=lambda: object())
    assert not r.ok and "empty" in r.error.lower()


def test_generate_timeout_handled():
    db, pid, sid, src = _proj()
    sess = E.create_rewrite_session(db, pid, source_type="scene", source_id=sid)

    def boom(m, p):
        raise TimeoutError("slow")

    r = E.generate_rewrite_variant(db, pid, session_id=sess.id, source_text=src,
                                   chat_fn=boom, provider_resolver=lambda: object())
    assert not r.ok and "failed" in r.error.lower()


def test_generate_multiple_variants():
    db, pid, sid, src = _proj()
    sess = E.create_rewrite_session(db, pid, source_type="scene", source_id=sid,
                                    source_text=src)
    results = E.generate_multiple_variants(
        db, pid, session_id=sess.id, source_text=src,
        strategies=["compress", "clarify", "intensify"], chat_fn=_FAKE,
        provider_resolver=lambda: object())
    assert all(r.ok for r in results)
    assert len(db.get_rewrite_variants(sess.id)) == 3


def test_generation_records_provider_metadata():
    db, pid, sid, src = _proj()
    sess = E.create_rewrite_session(db, pid, source_type="scene", source_id=sid,
                                    source_text=src)

    class P:
        name = "OpenAI"
        model = "gpt-4o"

    r = E.generate_rewrite_variant(db, pid, session_id=sess.id, source_text=src,
                                   chat_fn=_FAKE, provider_resolver=lambda: P())
    v = db.get_rewrite_variant(r.variant_id)
    assert v.model_provider == "OpenAI" and v.model_name == "gpt-4o"


# ===========================================================================
# Engine — apply (explicit, stale-guarded)
# ===========================================================================


def _gen(db, pid, sid, src):
    sess = E.create_rewrite_session(db, pid, source_type="scene", source_id=sid,
                                    source_text=src)
    r = E.generate_rewrite_variant(db, pid, session_id=sess.id, source_text=src,
                                   chat_fn=_FAKE, provider_resolver=lambda: object())
    return sess, r


def test_apply_requires_confirmation():
    db, pid, sid, src = _proj()
    _, r = _gen(db, pid, sid, src)
    res = E.apply_rewrite_variant(db, pid, r.variant_id)        # no confirm
    assert not res["ok"] and "confirmation" in res["error"].lower()
    assert db.get_scene_by_id(sid).content == src


def test_apply_confirmed_mutates_and_records():
    db, pid, sid, src = _proj()
    _, r = _gen(db, pid, sid, src)
    res = E.apply_rewrite_variant(db, pid, r.variant_id, confirm=True)
    assert res["ok"]
    assert db.get_scene_by_id(sid).content == r.variant_text
    assert db.get_rewrite_variant(r.variant_id).status == "applied"
    assert res.get("stage_id") is not None                      # checkpoint created


def test_apply_stale_source_blocked():
    db, pid, sid, src = _proj()
    sess, r = _gen(db, pid, sid, src)
    db.update_scene_content(sid, src + " EDITED")               # source drifts
    assert E.is_source_stale(db, sess.id)
    res = E.apply_rewrite_variant(db, pid, r.variant_id, confirm=True)
    assert not res["ok"] and res.get("stale")
    assert "EDITED" in db.get_scene_by_id(sid).content          # not overwritten
    # Force applies.
    res2 = E.apply_rewrite_variant(db, pid, r.variant_id, confirm=True, force=True)
    assert res2["ok"]


def test_apply_emits_project_data_changed():
    from logosforge.project_events import get_event_bus
    db, pid, sid, src = _proj()
    _, r = _gen(db, pid, sid, src)
    fired = []
    get_event_bus().project_data_changed.connect(lambda: fired.append(1))
    E.apply_rewrite_variant(db, pid, r.variant_id, confirm=True)
    assert fired


# ===========================================================================
# Scoring (deterministic)
# ===========================================================================


def test_scoring_length_and_psyke():
    db, pid, sid, src = _proj()
    score = score_rewrite(db, pid, "Alice ran fast and far across the field.",
                          "Alice ran.", writing_mode="novel")
    assert score["length_delta"] < 0
    assert "psyke_terms_preserved" in score and "summary" in score


def test_scoring_screenplay_warnings():
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay").id
    score = score_rewrite(db, pid, "INT. X\n\nA.", "Orphan dialogue line here.",
                          writing_mode="screenplay")
    assert "screenplay_format_warnings" in score


def test_scoring_no_llm(monkeypatch):
    import logosforge.assistant as assistant
    calls = []
    monkeypatch.setattr(assistant, "chat_completion",
                        lambda *a, **k: calls.append(1) or ("", False))
    db, pid, sid, src = _proj()
    score_rewrite(db, pid, src, "Short.", writing_mode="novel")
    assert calls == []


# ===========================================================================
# Revision Impact integration
# ===========================================================================


def test_variant_impact_map_via_10k():
    from logosforge.revision_intelligence.impact_map import build_revision_impact_map
    db, pid, sid, src = _proj()
    _, r = _gen(db, pid, sid, src)
    m = build_revision_impact_map(db, pid, scene_id=sid, before_text=src,
                                  after_text=r.variant_text)
    assert m.impact_level in ("low", "medium", "high", "critical")


# ===========================================================================
# Logos (writing-mode-aware: available in Novel too)
# ===========================================================================


def test_rewrite_logos_actions_registered():
    from logosforge.logos import actions as A
    from logosforge.logos import deterministic as det
    for name in ("rw_sandbox_status", "rw_explain_tradeoffs", "rw_score_variants",
                 "rw_check_psyke_preservation"):
        act = A.get_action(name)
        assert act and act.deterministic and act.modes == ()    # cross-mode
        assert det.is_deterministic(name)
    assert A.get_action("rw_suggest_strategy") is not None       # generative


def test_rewrite_actions_available_in_novel_mode():
    from logosforge.logos.controller import LogosController
    db, pid, sid, src = _proj()
    ctl = LogosController(db)
    names = [a.name for a in ctl.available_actions("Manuscript", writing_mode="novel")]
    assert "rw_sandbox_status" in names
    assert not any(n.startswith("sp_") for n in names)           # sp_ still hidden


def test_rewrite_status_action_no_llm():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def boom(*a, **k):
        raise AssertionError("deterministic rewrite action must not use the LLM")

    db, pid, sid, src = _proj()
    _gen(db, pid, sid, src)
    ctl = LogosController(db, provider_resolver=boom, chat_fn=boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "rw_sandbox_status")
    assert res.ok and res.proposed_operations == []


# ===========================================================================
# Assistant context
# ===========================================================================


def test_assistant_rewrite_block_only_with_open_session():
    from logosforge.assistant_context_policy import gather_injected_context
    db, pid, sid, src = _proj()
    ctx0 = gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    assert "[Rewrite Sandbox]" not in ctx0
    _gen(db, pid, sid, src)
    ctx1 = gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    assert "[Rewrite Sandbox]" in ctx1


def test_assistant_rewrite_block_capped_no_variant_dump():
    from logosforge.assistant_context_policy import gather_injected_context
    db, pid, sid, src = _proj()
    _gen(db, pid, sid, src)
    ctx = gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    block = ctx.split("[Rewrite Sandbox]")[-1].split("[")[0]
    assert block.count("\n") < 8
    assert "clung to her" not in ctx                              # no variant text


def test_assistant_rewrite_no_llm_no_mutation(monkeypatch):
    import logosforge.assistant as assistant
    from logosforge.assistant_context_policy import gather_injected_context
    calls = []
    monkeypatch.setattr(assistant, "chat_completion",
                        lambda *a, **k: calls.append(1) or ("", False))
    db, pid, sid, src = _proj()
    _gen(db, pid, sid, src)
    before = len(db.get_rewrite_sessions(pid))
    gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    assert calls == [] and len(db.get_rewrite_sessions(pid)) == before


def test_assistant_rewrite_no_stale_project_leak():
    from logosforge.assistant_context_policy import gather_injected_context
    db, p1, sid1, src1 = _proj()
    _gen(db, p1, sid1, src1)
    p2 = db.create_project("Other", narrative_engine="novel").id
    sid2 = db.create_scene(p2, "S", content="Different.", summary="x").id
    ctx2 = gather_injected_context(db, p2, section_name="Manuscript", scene_id=sid2)
    assert "[Rewrite Sandbox]" not in ctx2


# ===========================================================================
# Health (open variants only; never canonical)
# ===========================================================================


def test_rewrite_health_only_with_open_session():
    from logosforge.logos.health import HealthEngine
    from logosforge.logos.health import metric as M
    db, pid, sid, src = _proj()
    cats0 = {m.category for m in HealthEngine(db, pid).generate_report().metrics}
    assert M.CAT_REWRITE_CONTINUITY not in cats0
    _gen(db, pid, sid, src)
    cats1 = {m.category for m in HealthEngine(db, pid).generate_report().metrics}
    assert M.CAT_REWRITE_CONTINUITY in cats1


def test_rewrite_health_capped():
    from logosforge.logos.health import HealthEngine
    from logosforge.logos.health import metric as M
    db, pid, sid, src = _proj()
    _gen(db, pid, sid, src)
    by = {m.category: m for m in HealthEngine(db, pid).generate_report().metrics}
    for c in (M.CAT_REWRITE_CONTINUITY, M.CAT_PSYKE_PRESERVATION,
              M.CAT_SOURCE_STALENESS):
        assert by[c].status in (M.STATUS_STABLE, M.STATUS_WATCH, M.STATUS_UNKNOWN)


def test_applied_variant_clears_open_session_health():
    from logosforge.logos.health import HealthEngine
    from logosforge.logos.health import metric as M
    db, pid, sid, src = _proj()
    _, r = _gen(db, pid, sid, src)
    E.apply_rewrite_variant(db, pid, r.variant_id, confirm=True)  # session -> applied
    cats = {m.category for m in HealthEngine(db, pid).generate_report().metrics}
    assert M.CAT_REWRITE_CONTINUITY not in cats                   # no open session


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
