"""Phase 10J — screenplay production draft layer."""

from __future__ import annotations

import warnings

import pytest

warnings.filterwarnings("ignore")

from logosforge.db import Database
import logosforge.screenplay_production as P


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


def _film(db=None, n=3):
    db = db or Database()
    pid = db.create_project("Heist", narrative_engine="screenplay").id
    sids = []
    for i in range(n):
        sids.append(db.create_scene(
            pid, f"S{i+1}", content=f"INT. PLACE{i} - DAY\n\nAction {i}.",
            summary="x").id)
    return db, pid, sids


# ===========================================================================
# Migration / model safety
# ===========================================================================


def test_existing_db_opens_and_no_drafts():
    db = Database()
    pid = db.create_project("Old").id
    assert db.get_production_drafts(pid) == []
    assert db.get_active_production_draft(pid) is None


def test_migration_idempotent():
    db = Database()
    db._migrate()  # must not raise; production tables already exist via create_all
    pid = db.create_project("X", narrative_engine="screenplay").id
    P.enable_production_mode(db, pid)
    assert db.get_active_production_draft(pid) is not None


def test_production_mode_screenplay_only():
    db = Database()
    pid = db.create_project("Book", narrative_engine="novel").id
    assert P.enable_production_mode(db, pid) is None
    assert not P.is_production_mode(db, pid)


def test_validation_does_not_mutate_db():
    db, pid, _ = _film()
    P.enable_production_mode(db, pid)
    P.assign_scene_numbers(db, pid)
    before = len(db.get_production_scene_numbers(db.get_active_production_draft(pid).id))
    P.validate_production_draft(db, pid)
    P.validate_scene_numbers(db, pid)
    after = len(db.get_production_scene_numbers(db.get_active_production_draft(pid).id))
    assert before == after


# ===========================================================================
# Scene numbering
# ===========================================================================


def test_initial_numbering_sequential():
    db, pid, sids = _film()
    nums = P.assign_scene_numbers(db, pid)
    assert [nums[s] for s in sids] == ["1", "2", "3"]


def test_no_duplicate_numbers():
    db, pid, _ = _film()
    P.assign_scene_numbers(db, pid)
    assert P.validate_scene_numbers(db, pid) == []


def test_numbering_preserved_on_reassign():
    db, pid, sids = _film()
    P.assign_scene_numbers(db, pid)
    # Add a scene and renumber — existing numbers preserved, new one numbered.
    s4 = db.create_scene(pid, "S4", content="INT. NEW - DAY\n\nX.", summary="x").id
    nums = P.assign_scene_numbers(db, pid)
    assert nums[sids[0]] == "1" and nums[s4] == "4"


def test_omitted_scene_preserves_number_and_not_reused():
    db, pid, sids = _film()
    P.assign_scene_numbers(db, pid)
    P.omit_scene(db, pid, sids[1])
    m = P.scene_number_map(db, pid)
    assert m[sids[1]]["omitted"] is True and m[sids[1]]["number"] == "2"
    # Re-running numbering must not reuse '2'.
    s4 = db.create_scene(pid, "S4", content="INT. NEW - DAY\n\nX.", summary="x").id
    nums = P.assign_scene_numbers(db, pid)
    assert nums[s4] != "2"


def test_restore_omitted_scene():
    db, pid, sids = _film()
    P.assign_scene_numbers(db, pid)
    P.omit_scene(db, pid, sids[1])
    P.restore_scene(db, pid, sids[1])
    assert P.scene_number_map(db, pid)[sids[1]]["omitted"] is False


def test_insert_scene_number_convention():
    assert P.insert_scene_number("10") == "10A"
    assert P.insert_scene_number("10A") == "10B"
    assert P.insert_scene_number("A11") == "A11A"


def test_duplicate_number_detected_as_problem():
    db, pid, sids = _film()
    P.assign_scene_numbers(db, pid)
    draft = db.get_active_production_draft(pid)
    db.set_production_scene_number(pid, draft.id, sids[1], scene_number="1")  # force dupe
    assert any("Duplicate" in p for p in P.validate_scene_numbers(db, pid))


# ===========================================================================
# Revision sets
# ===========================================================================


def test_revision_color_sequence():
    db, pid, _ = _film()
    P.enable_production_mode(db, pid)
    r1 = P.create_revision_set(db, pid)
    r2 = P.create_revision_set(db, pid)
    r3 = P.create_revision_set(db, pid)
    assert (r1.color_name, r2.color_name, r3.color_name) == ("White", "Blue", "Pink")


def test_revision_change_detection_via_hash():
    db, pid, sids = _film()
    P.enable_production_mode(db, pid)
    P.create_revision_set(db, pid)            # baseline (all 'added')
    db.update_scene_content(sids[0], "INT. PLACE0 - DAY\n\nAction CHANGED.")
    assert P.changed_scenes_since_last_revision(db, pid) == [sids[0]]
    P.create_revision_set(db, pid)            # records 'modified' for sids[0]
    draft = db.get_active_production_draft(pid)
    changes = db.get_revision_changes(draft.id)
    mods = [c for c in changes if c.change_type == "modified"]
    assert any(c.scene_id == sids[0] for c in mods)


def test_no_auto_revision_on_edit():
    """Editing a scene does not create a revision set by itself."""
    db, pid, sids = _film()
    P.enable_production_mode(db, pid)
    db.update_scene_content(sids[0], "INT. PLACE0 - DAY\n\nEdited.")
    draft = db.get_active_production_draft(pid)
    assert db.get_revision_sets(draft.id) == []


def test_revision_set_status_update():
    db, pid, _ = _film()
    P.enable_production_mode(db, pid)
    rs = P.create_revision_set(db, pid)
    db.update_revision_set(rs.id, status="issued")
    assert db.get_revision_sets(db.get_active_production_draft(pid).id)[0].status == "issued"


# ===========================================================================
# Page locking (no fake locking)
# ===========================================================================


def test_page_locking_status_is_approximate_not_stable():
    db, pid, _ = _film()
    draft = P.enable_production_mode(db, pid)
    assert draft.page_locking_status in ("approximate", "disabled", "unsupported")
    assert draft.page_locking_status != "stable"


def test_validation_warns_page_locking_approximate():
    db, pid, _ = _film()
    P.enable_production_mode(db, pid)
    P.assign_scene_numbers(db, pid)
    rep = P.validate_production_draft(db, pid)
    assert any("approximate" in w.lower() for w in rep.warnings)


# ===========================================================================
# Validation readiness levels
# ===========================================================================


def test_readiness_spec_when_not_enabled():
    db, pid, _ = _film()
    assert P.validate_production_draft(db, pid).readiness_level == P.LEVEL_SPEC


def test_readiness_numbered_then_revised():
    db, pid, _ = _film()
    P.enable_production_mode(db, pid)
    P.assign_scene_numbers(db, pid)
    assert P.validate_production_draft(db, pid).readiness_level == P.LEVEL_NUMBERED
    P.create_revision_set(db, pid)
    assert P.validate_production_draft(db, pid).readiness_level == P.LEVEL_REVISED


def test_readiness_unsupported_for_novel():
    db = Database()
    pid = db.create_project("Book", narrative_engine="novel").id
    rep = P.validate_production_draft(db, pid)
    assert rep.readiness_level == P.LEVEL_UNSUPPORTED and rep.blocking_errors


def test_duplicate_numbers_block_production():
    db, pid, sids = _film()
    P.enable_production_mode(db, pid)
    P.assign_scene_numbers(db, pid)
    draft = db.get_active_production_draft(pid)
    db.set_production_scene_number(pid, draft.id, sids[1], scene_number="1")
    rep = P.validate_production_draft(db, pid)
    assert any("Duplicate" in e for e in rep.blocking_errors)


# ===========================================================================
# Production exports
# ===========================================================================


def test_production_fountain_scene_numbers_and_omitted():
    from logosforge.export import export_production_fountain
    db, pid, sids = _film()
    P.enable_production_mode(db, pid)
    P.assign_scene_numbers(db, pid)
    P.omit_scene(db, pid, sids[1])
    out = export_production_fountain(db, pid)
    assert "#1#" in out and "#3#" in out
    assert "OMITTED" in out


def test_production_fountain_omitted_excluded_when_off():
    from logosforge.export import export_production_fountain
    db, pid, sids = _film()
    P.enable_production_mode(db, pid)
    P.assign_scene_numbers(db, pid)
    P.omit_scene(db, pid, sids[1])
    out = export_production_fountain(db, pid, include_omitted=False)
    assert "OMITTED" not in out


def test_default_fountain_unchanged_without_production_numbers():
    from logosforge.export import export_screenplay_fountain
    db, pid, _ = _film()
    out = export_screenplay_fountain(db, pid)
    assert "#1#" not in out  # default export carries no production numbers


def test_production_export_not_markdown():
    from logosforge.export import export_production_fountain, export_markdown
    db, pid, _ = _film()
    P.enable_production_mode(db, pid)
    P.assign_scene_numbers(db, pid)
    assert export_production_fountain(db, pid) != export_markdown(db, pid)


# ===========================================================================
# Logos
# ===========================================================================


def test_production_logos_actions_deterministic_screenplay_only():
    from logosforge.logos import actions as A
    from logosforge.logos import deterministic as det
    for name in ("sp_production_status", "sp_validate_production",
                 "sp_check_duplicate_scene_numbers", "sp_summarize_revision_set",
                 "sp_explain_page_locking", "sp_check_fountain_production_export",
                 "sp_prepare_production_export"):
        act = A.get_action(name)
        assert act and act.modes == ("screenplay",) and act.deterministic
        assert det.is_deterministic(name)


def test_production_actions_hidden_in_novel():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("Book", narrative_engine="novel")
    ctl = LogosController(db)
    names = [a.name for a in ctl.available_actions("Manuscript", writing_mode="novel")]
    assert not any(n.startswith("sp_") for n in names)


def test_production_status_action_no_llm():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def boom(*a, **k):
        raise AssertionError("deterministic production action must not use the LLM")

    db, pid, _ = _film()
    P.enable_production_mode(db, pid)
    ctl = LogosController(db, provider_resolver=boom, chat_fn=boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript")
    res = ctl.run(ctx, "sp_production_status")
    assert res.ok and res.proposed_operations == []


# ===========================================================================
# Assistant context
# ===========================================================================


def test_assistant_production_block_only_when_active():
    from logosforge.assistant_context_policy import gather_injected_context
    db, pid, sids = _film()
    # Spec draft: no production block.
    ctx = gather_injected_context(db, pid, section_name="Manuscript", scene_id=sids[0])
    assert "[Production Draft Status]" not in ctx
    # Enable production: block appears.
    P.enable_production_mode(db, pid)
    P.assign_scene_numbers(db, pid)
    ctx2 = gather_injected_context(db, pid, section_name="Manuscript", scene_id=sids[0])
    assert "[Production Draft Status]" in ctx2
    assert "Mode: production" in ctx2


def test_assistant_production_block_capped_no_dump():
    from logosforge.assistant_context_policy import gather_injected_context
    db, pid, sids = _film()
    P.enable_production_mode(db, pid)
    P.assign_scene_numbers(db, pid)
    ctx = gather_injected_context(db, pid, section_name="Manuscript", scene_id=sids[0])
    block = ctx.split("[Production Draft Status]")[-1].split("[")[0]
    assert block.count("\n") < 10           # concise
    assert "Action 0." not in ctx           # no scene-body dump


def test_assistant_production_no_stale_leak():
    from logosforge.assistant_context_policy import gather_injected_context
    db, p1, _ = _film()
    P.enable_production_mode(db, p1)
    P.assign_scene_numbers(db, p1)
    # Second screenplay project with no production mode.
    p2 = db.create_project("Other", narrative_engine="screenplay").id
    s2 = db.create_scene(p2, "X", content="INT. Y - DAY\n\nZ.", summary="x").id
    ctx2 = gather_injected_context(db, p2, section_name="Manuscript", scene_id=s2)
    assert "[Production Draft Status]" not in ctx2


def test_assistant_production_no_llm_no_mutation(monkeypatch):
    import logosforge.assistant as assistant
    from logosforge.assistant_context_policy import gather_injected_context
    calls = []
    monkeypatch.setattr(assistant, "chat_completion",
                        lambda *a, **k: calls.append(1) or ("", False))
    db, pid, sids = _film()
    P.enable_production_mode(db, pid)
    P.assign_scene_numbers(db, pid)
    before = len(db.get_all_scenes(pid))
    gather_injected_context(db, pid, section_name="Manuscript", scene_id=sids[0])
    assert calls == [] and len(db.get_all_scenes(pid)) == before


# ===========================================================================
# Health
# ===========================================================================


def test_production_health_only_when_active():
    from logosforge.logos.health import HealthEngine
    from logosforge.logos.health import metric as M
    db, pid, _ = _film()
    cats_before = {m.category for m in HealthEngine(db, pid).generate_report().metrics}
    assert M.CAT_PRODUCTION_READINESS not in cats_before
    P.enable_production_mode(db, pid)
    P.assign_scene_numbers(db, pid)
    cats_after = {m.category for m in HealthEngine(db, pid).generate_report().metrics}
    assert M.CAT_PRODUCTION_READINESS in cats_after


def test_production_health_capped_not_narrative_failure():
    from logosforge.logos.health import HealthEngine
    from logosforge.logos.health import metric as M
    db, pid, sids = _film()
    P.enable_production_mode(db, pid)
    P.assign_scene_numbers(db, pid)
    draft = db.get_active_production_draft(pid)
    db.set_production_scene_number(pid, draft.id, sids[1], scene_number="1")  # dupe
    by = {m.category: m for m in HealthEngine(db, pid).generate_report().metrics}
    # Duplicate is a production blocker (validator) but health stays capped.
    assert by[M.CAT_SCENE_NUMBERING].status in (M.STATUS_WATCH, M.STATUS_STABLE)


def test_novel_health_has_no_production_categories():
    from logosforge.logos.health import HealthEngine
    from logosforge.logos.health import metric as M
    db = Database()
    pid = db.create_project("Book", narrative_engine="novel").id
    db.create_scene(pid, "Ch1", content="Morning.", summary="x")
    cats = {m.category for m in HealthEngine(db, pid).generate_report().metrics}
    assert M.CAT_PRODUCTION_READINESS not in cats


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
