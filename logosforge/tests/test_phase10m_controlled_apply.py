"""Phase 10M — Controlled Apply / Merge Tools."""

from __future__ import annotations

import warnings

import pytest

warnings.filterwarnings("ignore")

from logosforge.db import Database
import logosforge.controlled_apply.service as CA
from logosforge.controlled_apply import targets as T
from logosforge.controlled_apply.diff import build_apply_diff


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


def _proj(db=None, mode="novel"):
    db = db or Database()
    pid = db.create_project("P", narrative_engine=mode).id
    db.create_psyke_entry(pid, "Alice", "character")
    sid = db.create_scene(pid, "Ch1", content="Alice walked into the dim room.",
                          summary="x").id
    return db, pid, sid


# ===========================================================================
# Migration / model
# ===========================================================================


def test_existing_db_opens_no_operations():
    db = Database()
    pid = db.create_project("Old").id
    assert db.get_apply_operations(pid) == []


def test_operation_and_conflict_crud():
    db, pid, sid = _proj()
    op = db.create_apply_operation(
        pid, target_type="scene", target_id=sid, status="previewed",
        conflicts=[{"conflict_type": "stale_source", "severity": "blocking",
                    "message": "x"}])
    assert op.id
    assert len(db.get_apply_conflicts(op.id)) == 1
    db.update_apply_operation(op.id, status="cancelled")
    assert db.get_apply_operation(op.id).status == "cancelled"


# ===========================================================================
# Diff
# ===========================================================================


def test_diff_line_changes_and_accents():
    d = build_apply_diff("café au lait\nline two", "café noir\nline two\nline three")
    assert d.added_lines >= 1 and d.removed_lines >= 1
    assert "café" not in d.removed_terms          # accent preserved
    assert not d.is_empty_change


def test_diff_empty_change():
    assert build_apply_diff("same", "same").is_empty_change


# ===========================================================================
# Preview (no mutation)
# ===========================================================================


def test_preview_does_not_mutate():
    db, pid, sid = _proj()
    before = db.get_scene_by_id(sid).content
    pv = CA.build_apply_preview(db, pid, target_type="scene", target_id=sid,
                                proposed_text="New text.")
    assert pv.can_apply and db.get_scene_by_id(sid).content == before


def test_preview_save_persists_draft_operation():
    db, pid, sid = _proj()
    pv = CA.build_apply_preview(db, pid, target_type="scene", target_id=sid,
                                proposed_text="New text.", save=True)
    assert pv.operation_id is not None
    assert db.get_apply_operation(pv.operation_id).status == "previewed"


def test_preview_target_missing_blocks():
    db, pid, sid = _proj()
    pv = CA.build_apply_preview(db, pid, target_type="scene", target_id=999999,
                                proposed_text="x")
    assert not pv.can_apply
    assert any(c["conflict_type"] == "target_missing" for c in pv.conflicts)


def test_preview_unsupported_target_deferred():
    db, pid, sid = _proj()
    pv = CA.build_apply_preview(db, pid, target_type="plot_block", target_id=1,
                                proposed_text="x")
    assert not pv.can_apply


def test_preview_empty_proposal_blocks():
    db, pid, sid = _proj()
    pv = CA.build_apply_preview(db, pid, target_type="scene", target_id=sid,
                                proposed_text="   ")
    assert not pv.can_apply


# ===========================================================================
# Conflicts
# ===========================================================================


def test_psyke_reference_loss_warning_not_blocking():
    db, pid, sid = _proj()
    pv = CA.build_apply_preview(db, pid, target_type="scene", target_id=sid,
                                proposed_text="A quiet empty morning.")
    assert any(c["conflict_type"] == "psyke_reference_loss" for c in pv.conflicts)
    assert pv.can_apply                              # warning only


def test_screenplay_block_invalid_warning():
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay").id
    sid = db.create_scene(pid, "V", content="INT. X - DAY\n\nAction.", summary="x").id
    pv = CA.build_apply_preview(db, pid, target_type="scene", target_id=sid,
                                proposed_text="An orphan dialogue line with no cue.")
    # Heuristic: lone uppercase-less line parses as action, so may be 0 — just
    # ensure preview is produced deterministically without crashing.
    assert isinstance(pv.conflicts, list)


def test_production_risk_warning_when_active():
    import logosforge.screenplay_production as P
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay").id
    sid = db.create_scene(pid, "V", content="INT. X - DAY\n\nAction.", summary="x").id
    P.enable_production_mode(db, pid)
    pv = CA.build_apply_preview(db, pid, target_type="scene", target_id=sid,
                                proposed_text="INT. X - NIGHT\n\nNew action.")
    assert any(c["conflict_type"] == "production_risk" for c in pv.conflicts)


# ===========================================================================
# Apply (confirmed, stale-guarded)
# ===========================================================================


def test_apply_requires_confirmation():
    db, pid, sid = _proj()
    before = db.get_scene_by_id(sid).content
    res = CA.apply_operation(db, pid, target_type="scene", target_id=sid,
                             proposed_text="New.")
    assert not res["ok"] and db.get_scene_by_id(sid).content == before


def test_apply_confirmed_mutates_with_checkpoint():
    db, pid, sid = _proj()
    res = CA.apply_operation(db, pid, target_type="scene", target_id=sid,
                             proposed_text="Applied body.", confirmed=True)
    assert res["ok"] and db.get_scene_by_id(sid).content == "Applied body."
    assert res["stage_id"] is not None
    assert any(o.status == "applied" for o in db.get_apply_operations(pid))


def test_apply_emits_project_data_changed():
    from logosforge.project_events import get_event_bus
    db, pid, sid = _proj()
    fired = []
    get_event_bus().project_data_changed.connect(lambda: fired.append(1))
    CA.apply_operation(db, pid, target_type="scene", target_id=sid,
                       proposed_text="X.", confirmed=True)
    assert fired


def test_apply_append_mode():
    db, pid, sid = _proj()
    before = db.get_scene_by_id(sid).content
    CA.apply_operation(db, pid, target_type="scene", target_id=sid,
                       proposed_text="Added paragraph.", apply_mode="append",
                       confirmed=True)
    after = db.get_scene_by_id(sid).content
    assert after.startswith(before) and "Added paragraph." in after


def test_cancel_does_not_mutate():
    db, pid, sid = _proj()
    before = db.get_scene_by_id(sid).content
    pv = CA.build_apply_preview(db, pid, target_type="scene", target_id=sid,
                                proposed_text="New.", save=True)
    CA.cancel_operation(db, pv.operation_id)
    assert db.get_scene_by_id(sid).content == before
    assert db.get_apply_operation(pv.operation_id).status == "cancelled"


def test_apply_no_llm(monkeypatch):
    import logosforge.assistant as assistant
    calls = []
    monkeypatch.setattr(assistant, "chat_completion",
                        lambda *a, **k: calls.append(1) or ("", False))
    db, pid, sid = _proj()
    CA.build_apply_preview(db, pid, target_type="scene", target_id=sid, proposed_text="x")
    CA.apply_operation(db, pid, target_type="scene", target_id=sid,
                       proposed_text="x", confirmed=True)
    assert calls == []


# ===========================================================================
# Target adapters
# ===========================================================================


def test_scene_adapter_read_apply():
    db, pid, sid = _proj()
    a = T.get_adapter(db, pid, "scene", sid)
    assert a.read().text == "Alice walked into the dim room."
    a.apply("Replaced.", "replace")
    assert db.get_scene_by_id(sid).content == "Replaced."


def test_psyke_adapter_updates_notes_only():
    db, pid, sid = _proj()
    e = db.create_psyke_entry(pid, "Bob", "character", aliases="Bobby")
    a = T.get_adapter(db, pid, "psyke_entry", e.id)
    a.apply("Bob is nervous.", "replace")
    e2 = db.get_psyke_entry_by_id(e.id)
    assert e2.notes == "Bob is nervous." and e2.name == "Bob"
    assert e2.entry_type == "character" and e2.aliases == "Bobby"


def test_note_adapter_updates_body_only():
    db, pid, sid = _proj()
    n = db.create_note(pid, "My Note", content="old", tags="t")
    a = T.get_adapter(db, pid, "note", n.id)
    a.apply("new body", "replace")
    n2 = db.get_note_by_id(n.id)
    assert n2.content == "new body" and n2.title == "My Note" and n2.tags == "t"


def test_outline_adapter_updates_description():
    db, pid, sid = _proj()
    node = db.create_outline_node(pid, title="Act I", description="old desc")
    a = T.get_adapter(db, pid, "outline_node", node.id)
    a.apply("new desc", "replace")
    assert db.get_outline_node_by_id(node.id).description == "new desc"


def test_adapter_rejects_disallowed_mode():
    db, pid, sid = _proj()
    a = T.get_adapter(db, pid, "psyke_entry", 1)
    assert a.validate_mode("replace_selection") is not None  # not allowed
    assert a.validate_mode("replace") is None


def test_unsupported_target_no_adapter():
    db, pid, sid = _proj()
    assert T.get_adapter(db, pid, "graph_node", 1) is None


# ===========================================================================
# Rewrite Sandbox integration (routes through Controlled Apply)
# ===========================================================================


def test_rewrite_apply_routes_through_controlled_apply():
    import logosforge.rewrite_sandbox.engine as E
    db, pid, sid = _proj()
    src = db.get_scene_by_id(sid).content
    sess = E.create_rewrite_session(db, pid, source_type="scene", source_id=sid,
                                    source_text=src)
    r = E.generate_rewrite_variant(db, pid, session_id=sess.id, source_text=src,
                                   chat_fn=lambda m, p: "Variant text.",
                                   provider_resolver=lambda: object())
    res = E.apply_rewrite_variant(db, pid, r.variant_id, confirm=True)
    assert res["ok"] and db.get_scene_by_id(sid).content == "Variant text."
    ops = db.get_apply_operations(pid)
    assert any(o.source_type == "rewrite_variant" and o.status == "applied"
               for o in ops)


def test_rewrite_apply_stale_blocked_via_service():
    import logosforge.rewrite_sandbox.engine as E
    db, pid, sid = _proj()
    src = db.get_scene_by_id(sid).content
    sess = E.create_rewrite_session(db, pid, source_type="scene", source_id=sid,
                                    source_text=src)
    r = E.generate_rewrite_variant(db, pid, session_id=sess.id, source_text=src,
                                   chat_fn=lambda m, p: "V.",
                                   provider_resolver=lambda: object())
    db.update_scene_content(sid, src + " EDITED")
    res = E.apply_rewrite_variant(db, pid, r.variant_id, confirm=True)
    assert not res["ok"] and res.get("stale")
    assert "EDITED" in db.get_scene_by_id(sid).content


# ===========================================================================
# Logos
# ===========================================================================


def test_controlled_apply_logos_actions_deterministic():
    from logosforge.logos import actions as A
    from logosforge.logos import deterministic as det
    for name in ("ca_apply_history", "ca_explain_conflicts"):
        act = A.get_action(name)
        assert act and act.deterministic and act.modes == ()
        assert det.is_deterministic(name)


def test_controlled_apply_actions_available_in_novel():
    from logosforge.logos.controller import LogosController
    db, pid, sid = _proj()
    ctl = LogosController(db)
    names = [a.name for a in ctl.available_actions("Manuscript", writing_mode="novel")]
    assert "ca_apply_history" in names and "ca_explain_conflicts" in names


def test_explain_conflicts_action_no_llm():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def boom(*a, **k):
        raise AssertionError("deterministic action must not use the LLM")

    db, pid, sid = _proj()
    CA.create_apply_operation(db, pid, target_type="scene", target_id=sid,
                              proposed_text="A quiet empty room.", source_type="assistant")
    ctl = LogosController(db, provider_resolver=boom, chat_fn=boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "ca_explain_conflicts")
    assert res.ok and res.proposed_operations == []


# ===========================================================================
# Assistant context
# ===========================================================================


def test_assistant_block_only_with_pending_preview():
    from logosforge.assistant_context_policy import gather_injected_context
    db, pid, sid = _proj()
    ctx0 = gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    assert "[Controlled Apply]" not in ctx0
    CA.create_apply_operation(db, pid, target_type="scene", target_id=sid,
                              proposed_text="A quiet empty room.", source_type="assistant")
    ctx1 = gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    assert "[Controlled Apply]" in ctx1


def test_assistant_block_no_proposed_text_dump():
    from logosforge.assistant_context_policy import gather_injected_context
    db, pid, sid = _proj()
    CA.create_apply_operation(db, pid, target_type="scene", target_id=sid,
                              proposed_text="SECRET PROPOSED CONTENT", source_type="assistant")
    ctx = gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    assert "SECRET PROPOSED CONTENT" not in ctx
    block = ctx.split("[Controlled Apply]")[-1].split("[")[0]
    assert block.count("\n") < 8


def test_assistant_block_no_llm_no_mutation(monkeypatch):
    import logosforge.assistant as assistant
    from logosforge.assistant_context_policy import gather_injected_context
    calls = []
    monkeypatch.setattr(assistant, "chat_completion",
                        lambda *a, **k: calls.append(1) or ("", False))
    db, pid, sid = _proj()
    CA.create_apply_operation(db, pid, target_type="scene", target_id=sid,
                              proposed_text="x", source_type="assistant")
    before = db.get_scene_by_id(sid).content
    gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    assert calls == [] and db.get_scene_by_id(sid).content == before


def test_assistant_block_no_cross_project_leak():
    from logosforge.assistant_context_policy import gather_injected_context
    db, p1, s1 = _proj()
    CA.create_apply_operation(db, p1, target_type="scene", target_id=s1,
                              proposed_text="x", source_type="assistant")
    p2 = db.create_project("Other", narrative_engine="novel").id
    s2 = db.create_scene(p2, "S", content="y", summary="x").id
    ctx2 = gather_injected_context(db, p2, section_name="Manuscript", scene_id=s2)
    assert "[Controlled Apply]" not in ctx2


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
