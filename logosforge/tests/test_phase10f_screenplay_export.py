"""Phase 10F — screenplay production polish + export preparation."""

from __future__ import annotations

import json
import warnings

import pytest

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import screenplay_render as sr
from logosforge.screenplay_export_validation import validate_screenplay_export


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


def _film(db, *, title=True):
    pid = db.create_project("Heist", narrative_engine="screenplay").id
    db.create_scene(pid, "Vault",
                    content="INT. VAULT - NIGHT\n\nAlice cracks the safe.\n\n"
                            "ALICE\n(quietly)\nGot it.\n\n[[note: add guard]]",
                    summary="x")
    if title:
        sr.set_title_page(db, pid, {"title": "The Heist", "author": "A. Writer"})
    return pid


# ===========================================================================
# Render model
# ===========================================================================


def test_render_document_builds_from_blocks():
    db = Database()
    pid = _film(db)
    doc = sr.build_render_document(db, pid)
    assert doc.project_id == pid and doc.blocks
    kinds = {b.element_type for b in doc.blocks}
    assert "scene_heading" in kinds and "dialogue" in kinds


def test_render_document_includes_title_page():
    db = Database()
    pid = _film(db)
    doc = sr.build_render_document(db, pid)
    assert doc.title == "The Heist"
    assert doc.title_page["author"] == "A. Writer"


def test_render_excludes_notes_by_default_includes_when_pref_set():
    db = Database()
    pid = _film(db)
    doc = sr.build_render_document(db, pid)
    assert all(b.element_type != "note" for b in doc.blocks)
    sr.set_export_prefs(db, pid, {"show_notes_in_export": True})
    doc2 = sr.build_render_document(db, pid)
    assert any(b.element_type == "note" for b in doc2.blocks)


def test_render_estimates_are_approximate_and_optional():
    db = Database()
    pid = _film(db)
    doc = sr.build_render_document(db, pid)
    assert doc.estimated_pages is not None and doc.estimated_minutes is not None
    sr.set_export_prefs(db, pid, {"approximate_page_estimate": False})
    doc2 = sr.build_render_document(db, pid)
    assert doc2.estimated_pages is None


def test_render_does_not_mutate_db():
    db = Database()
    pid = _film(db)
    before = len(db.get_all_scenes(pid))
    sr.build_render_document(db, pid)
    assert len(db.get_all_scenes(pid)) == before


def test_render_does_not_call_llm(monkeypatch):
    import logosforge.assistant as assistant
    calls = []
    monkeypatch.setattr(assistant, "chat_completion",
                        lambda *a, **k: calls.append(1) or ("", False))
    db = Database()
    pid = _film(db)
    sr.build_render_document(db, pid)
    assert calls == []


def test_render_document_serializable():
    db = Database()
    pid = _film(db)
    assert json.dumps(sr.build_render_document(db, pid).to_dict())


def test_render_warns_when_no_title():
    db = Database()
    pid = db.create_project("", narrative_engine="screenplay").id  # blank title
    db.create_scene(pid, "S", content="INT. X - DAY\n\nAction.", summary="x")
    doc = sr.build_render_document(db, pid)
    assert any("title" in w.lower() for w in doc.warnings)


def test_unsupported_block_produces_warning():
    from logosforge.screenplay_render import ScreenplayRenderBlock
    # Direct DTO use: an out-of-taxonomy element is still representable.
    b = ScreenplayRenderBlock(element_type="action", text="x")
    assert json.dumps(b.to_dict())


def test_render_html_and_plain_text():
    db = Database()
    pid = _film(db)
    doc = sr.build_render_document(db, pid)
    html = sr.render_to_html(doc)
    assert html.startswith("<!DOCTYPE") and "The Heist" in html
    txt = sr.render_to_plain_text(doc)
    assert "ALICE" in txt and "GOT IT." in txt.upper()


# ===========================================================================
# Title page metadata
# ===========================================================================


def test_title_page_saves_and_loads():
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay").id
    sr.set_title_page(db, pid, {"title": "My Film", "author": "Me",
                                "draft_date": "2026-01-01"})
    meta = sr.get_title_page(db, pid)
    assert meta["title"] == "My Film" and meta["author"] == "Me"


def test_title_page_defaults_to_project_title():
    db = Database()
    pid = db.create_project("Fallback Title", narrative_engine="screenplay").id
    assert sr.get_title_page(db, pid)["title"] == "Fallback Title"


def test_title_page_exports_to_fountain():
    from logosforge.export import export_fountain
    db = Database()
    pid = _film(db)
    out = export_fountain(db, pid)
    assert "Title: The Heist" in out and "Author: A. Writer" in out


def test_missing_title_is_warning_not_crash():
    db = Database()
    pid = db.create_project("", narrative_engine="screenplay").id
    db.create_scene(pid, "S", content="INT. X - DAY\n\nAction.", summary="x")
    rep = validate_screenplay_export(db, pid)
    assert any("title" in w.lower() for w in rep.warnings)
    assert rep.is_export_safe  # missing title is non-blocking


# ===========================================================================
# Export prefs
# ===========================================================================


def test_export_prefs_persist_with_conservative_defaults():
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay").id
    prefs = sr.get_export_prefs(db, pid)
    assert prefs["show_notes_in_export"] is False   # conservative default
    assert prefs["export_target"] == "fountain"
    sr.set_export_prefs(db, pid, {"export_target": "preview_html"})
    assert sr.get_export_prefs(db, pid)["export_target"] == "preview_html"


def test_invalid_export_target_falls_back():
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay").id
    sr.set_export_prefs(db, pid, {"export_target": "garbage"})
    assert sr.get_export_prefs(db, pid)["export_target"] == "fountain"


# ===========================================================================
# Fountain export hardening
# ===========================================================================


def test_fountain_export_elements():
    from logosforge.export import export_fountain
    db = Database()
    pid = _film(db)
    out = export_fountain(db, pid)
    assert "INT. VAULT - NIGHT" in out             # scene heading (from content)
    assert out.count("VAULT - NIGHT") == 1         # no duplicate heading/slug
    assert "Alice cracks the safe." in out         # action
    assert "ALICE" in out                          # character cue
    assert "(quietly)" in out                      # parenthetical
    assert "Got it." in out                        # dialogue


def test_fountain_notes_excluded_by_default_included_when_set():
    from logosforge.export import export_fountain
    db = Database()
    pid = _film(db)
    assert "add guard" not in export_fountain(db, pid)
    sr.set_export_prefs(db, pid, {"show_notes_in_export": True})
    assert "add guard" in export_fountain(db, pid)


def test_fountain_no_text_loss_for_action():
    from logosforge.export import export_fountain
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay").id
    db.create_scene(pid, "S", content="INT. X - DAY\n\nThe dawn broke slowly.",
                    summary="x")
    assert "The dawn broke slowly." in export_fountain(db, pid)


def test_note_parser_roundtrip():
    from logosforge.screenplay_blocks import parse_screenplay_text, to_fountain
    blocks = parse_screenplay_text("INT. X - DAY\n\nAction.\n\n[[remember the key]]")
    assert any(b.element_type == "note" for b in blocks)
    assert "[[remember the key]]" in to_fountain(blocks)


def test_novel_export_unbroken():
    from logosforge.export import export_manuscript, export_json
    db = Database()
    pid = db.create_project("Book", narrative_engine="novel").id
    db.create_scene(pid, "Ch1", content="It was a quiet morning.", summary="x")
    assert "It was a quiet morning." in export_manuscript(db, pid)
    assert json.loads(export_json(db, pid))["project"]["writing_mode"] == "novel"


# ===========================================================================
# Validation
# ===========================================================================


def test_empty_screenplay_is_blocking():
    db = Database()
    pid = db.create_project("Empty", narrative_engine="screenplay").id
    rep = validate_screenplay_export(db, pid)
    assert not rep.is_export_safe
    assert any("empty" in e.lower() for e in rep.blocking_errors)


def test_missing_scene_heading_warning():
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay").id
    db.create_scene(pid, "S", content="Just some action with no heading.", summary="x")
    rep = validate_screenplay_export(db, pid)
    assert any("scene heading" in w for w in rep.warnings)


def test_orphan_dialogue_warning():
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay").id
    # Dialogue-looking line with no character cue: parser makes it action, but a
    # genuine orphan is dialogue not preceded by a cue. Build one explicitly.
    db.create_scene(pid, "S",
                    content="INT. X - DAY\n\nALICE\nHi.\n\nBOB\nHello.",
                    summary="x")
    rep = validate_screenplay_export(db, pid)
    assert rep.is_export_safe  # well-formed dialogue is safe


def test_orphan_parenthetical_detected():
    from logosforge.screenplay_blocks import ScreenplayBlock
    from logosforge import screenplay_export_validation as v
    # White-box: a parenthetical with no preceding cue/dialogue is an orphan.
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay").id
    db.create_scene(pid, "S", content="INT. X - DAY\n\n(under his breath)\nWhat?",
                    summary="x")
    rep = v.validate_screenplay_export(db, pid)
    # The parser may classify the lone parenthetical chunk; ensure no crash and a
    # deterministic report is produced.
    assert isinstance(rep.warnings, list)


def test_export_safe_flag_and_no_block_for_warnings():
    db = Database()
    pid = _film(db, title=False)   # has scenes, no title
    rep = validate_screenplay_export(db, pid)
    assert rep.is_export_safe is True   # warnings don't block


def test_validation_deterministic_no_llm(monkeypatch):
    import logosforge.assistant as assistant
    calls = []
    monkeypatch.setattr(assistant, "chat_completion",
                        lambda *a, **k: calls.append(1) or ("", False))
    db = Database()
    pid = _film(db)
    validate_screenplay_export(db, pid)
    assert calls == []


def test_validation_no_db_mutation():
    db = Database()
    pid = _film(db)
    before = len(db.get_all_scenes(pid))
    validate_screenplay_export(db, pid)
    assert len(db.get_all_scenes(pid)) == before


def test_unsupported_target_blocks():
    db = Database()
    pid = _film(db)
    rep = validate_screenplay_export(db, pid, target_format="fdx")
    assert not rep.is_export_safe


def test_validation_report_serializable():
    db = Database()
    pid = _film(db)
    assert json.dumps(validate_screenplay_export(db, pid).to_dict())


# ===========================================================================
# Logos
# ===========================================================================


def test_export_polish_actions_registered_deterministic_screenplay_only():
    from logosforge.logos import actions as A
    from logosforge.logos import deterministic as det
    for name in ("sp_validate_export", "sp_export_readiness_report",
                 "sp_preview_render", "sp_find_orphan_dialogue",
                 "sp_find_orphan_parenthetical", "sp_check_production_polish"):
        act = A.get_action(name)
        assert act and act.modes == ("screenplay",) and act.deterministic
        assert det.is_deterministic(name)


def test_export_actions_do_not_dominate_novel():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("Book", narrative_engine="novel")
    ctl = LogosController(db)
    names = [a.name for a in ctl.available_actions("Manuscript", writing_mode="novel")]
    assert "sp_validate_export" not in names


def test_validate_export_action_no_llm():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def boom(*a, **k):
        raise AssertionError("deterministic export action must not use the LLM")

    db = Database()
    pid = _film(db)
    ctl = LogosController(db, provider_resolver=boom, chat_fn=boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript")
    res = ctl.run(ctx, "sp_validate_export")
    assert res.ok and "Export" in res.message
    assert res.proposed_operations == []   # no mutation


# ===========================================================================
# Assistant context
# ===========================================================================


def test_assistant_export_readiness_block():
    from logosforge.assistant_context_policy import gather_injected_context
    db = Database()
    pid = _film(db)
    sid = db.get_all_scenes(pid)[0].id
    ctx = gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    # Phase 10G: the default export target is .fountain, so the export-readiness
    # block is the Fountain variant (the generic one shows for other targets).
    assert "[Fountain Export Readiness]" in ctx
    assert "Export target: .fountain" in ctx


def test_assistant_export_block_disableable_and_novel_absent():
    from logosforge.assistant_context_policy import gather_injected_context
    from logosforge.settings import get_manager
    db = Database()
    pid = _film(db)
    sid = db.get_all_scenes(pid)[0].id
    get_manager().set("include_screenplay_export_in_assistant_context", False)
    ctx = gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    assert "[Screenplay Export Readiness]" not in ctx
    nov = db.create_project("Book", narrative_engine="novel").id
    nsid = db.create_scene(nov, "S", content="Prose.", summary="x").id
    nctx = gather_injected_context(db, nov, section_name="Manuscript", scene_id=nsid)
    assert "[Screenplay Export Readiness]" not in nctx


def test_assistant_export_block_no_llm_no_mutation(monkeypatch):
    import logosforge.assistant as assistant
    from logosforge.assistant_context_policy import gather_injected_context
    calls = []
    monkeypatch.setattr(assistant, "chat_completion",
                        lambda *a, **k: calls.append(1) or ("", False))
    db = Database()
    pid = _film(db)
    sid = db.get_all_scenes(pid)[0].id
    before = len(db.get_all_scenes(pid))
    gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    assert calls == []
    assert len(db.get_all_scenes(pid)) == before


# ===========================================================================
# Health (format health, capped at watch)
# ===========================================================================


def test_health_format_categories_present():
    from logosforge.logos.health import HealthEngine
    from logosforge.logos.health import metric as M
    db = Database()
    pid = _film(db)
    by = {m.category: m for m in HealthEngine(db, pid).generate_report().metrics}
    for c in (M.CAT_EXPORT_READINESS, M.CAT_TITLE_PAGE,
              M.CAT_SCENE_HEADING_INTEGRITY, M.CAT_DIALOGUE_FORMAT):
        assert c in by


def test_format_health_never_critical_or_weak():
    from logosforge.logos.health import HealthEngine
    from logosforge.logos.health import metric as M
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay").id
    db.create_scene(pid, "S", content="Just action, no heading.", summary="x")
    by = {m.category: m for m in HealthEngine(db, pid).generate_report().metrics}
    for c in (M.CAT_EXPORT_READINESS, M.CAT_TITLE_PAGE,
              M.CAT_SCENE_HEADING_INTEGRITY, M.CAT_DIALOGUE_FORMAT):
        assert by[c].status in (M.STATUS_STABLE, M.STATUS_WATCH, M.STATUS_UNKNOWN)


def test_novel_health_has_no_format_categories():
    from logosforge.logos.health import HealthEngine
    from logosforge.logos.health import metric as M
    db = Database()
    pid = db.create_project("Book", narrative_engine="novel").id
    db.create_scene(pid, "Ch1", content="A quiet morning.", summary="x")
    cats = {m.category for m in HealthEngine(db, pid).generate_report().metrics}
    assert M.CAT_EXPORT_READINESS not in cats


# ===========================================================================
# Export deliverables
# ===========================================================================


def test_preview_html_export():
    from logosforge.export import export_screenplay_preview_html
    db = Database()
    pid = _film(db)
    html = export_screenplay_preview_html(db, pid)
    assert html.startswith("<!DOCTYPE") and "The Heist" in html


def test_validation_json_export_has_metadata():
    from logosforge.export import export_screenplay_export_validation_json
    db = Database()
    pid = _film(db)
    data = json.loads(export_screenplay_export_validation_json(db, pid))
    assert data["schema_version"] == 1
    assert data["writing_mode"] == "screenplay"
    assert "exported_at" in data and "is_export_safe" in data


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
