"""Phase 10H — professional screenplay output layer (DOCX / PDF / FDX / preview)."""

from __future__ import annotations

import json
import warnings

import pytest

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import screenplay_output_styles as sos


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
                            "ALICE\n(quietly)\nGot it.\n\n[[guard]]",
                    summary="x")
    if title:
        from logosforge.screenplay_render import set_title_page
        set_title_page(db, pid, {"title": "The Heist", "author": "A. Writer"})
    return pid


def _render(db, pid):
    from logosforge.screenplay_render import build_render_document
    return build_render_document(db, pid)


# ===========================================================================
# Style model
# ===========================================================================


def test_default_style_exists():
    s = sos.get_style()
    assert s.name == "Standard Screenplay" and s.font_family in sos.FONT_FALLBACKS


def test_font_fallback():
    s = sos.get_style()
    font, fell = s.resolve_font(available={"Courier New", "Arial"})
    assert font == "Courier New" and fell is True
    font2, fell2 = s.resolve_font(available={"Arial"})
    assert font2 == "monospace" and fell2 is True
    font3, fell3 = s.resolve_font(available=None)
    assert font3 == sos.FONT_FALLBACKS[0] and fell3 is False


def test_element_styles_present():
    s = sos.get_style()
    for et in ("scene_heading", "action", "character", "parenthetical",
               "dialogue", "transition", "note"):
        assert s.style_for(et) is not None


def test_style_serializes():
    assert json.dumps(sos.get_style().to_dict())


def test_list_styles():
    assert "standard" in sos.list_styles()


# ===========================================================================
# DOCX export
# ===========================================================================


def test_docx_export_creates_document(tmp_path):
    from logosforge.export import export_screenplay_docx
    db = Database()
    pid = _film(db)
    path = str(tmp_path / "out.docx")
    res = export_screenplay_docx(db, pid, path)
    assert res.ok and res.file_path == path
    from docx import Document
    full = "\n".join(p.text for p in Document(path).paragraphs)
    assert "THE HEIST" in full              # title page
    assert "INT. VAULT - NIGHT" in full.upper()
    assert "ALICE" in full and "Got it." in full
    assert "guard" not in full              # notes excluded by default


def test_docx_no_db_mutation_no_llm(tmp_path, monkeypatch):
    import logosforge.assistant as assistant
    from logosforge.export import export_screenplay_docx
    calls = []
    monkeypatch.setattr(assistant, "chat_completion",
                        lambda *a, **k: calls.append(1) or ("", False))
    db = Database()
    pid = _film(db)
    before = len(db.get_all_scenes(pid))
    export_screenplay_docx(db, pid, str(tmp_path / "o.docx"))
    assert calls == [] and len(db.get_all_scenes(pid)) == before


def test_docx_missing_dependency_handled(monkeypatch, tmp_path):
    import logosforge.screenplay_docx_export as dx
    monkeypatch.setattr(dx, "docx_available", lambda: False)
    res = dx.export_screenplay_to_docx(_render(Database(), Database().create_project(
        "S", narrative_engine="screenplay").id), str(tmp_path / "x.docx"))
    assert not res.ok and any("python-docx" in w for w in res.warnings)


def test_docx_result_serializable(tmp_path):
    from logosforge.export import export_screenplay_docx
    db = Database()
    pid = _film(db)
    res = export_screenplay_docx(db, pid, str(tmp_path / "o.docx"))
    assert json.dumps(res.to_dict())


# ===========================================================================
# PDF / preview
# ===========================================================================


def test_pdf_export_writes_pdf(tmp_path):
    from logosforge.export import export_screenplay_pdf
    db = Database()
    pid = _film(db)
    path = str(tmp_path / "o.pdf")
    res = export_screenplay_pdf(db, pid, path)
    assert res["ok"]
    with open(path, "rb") as fh:
        assert fh.read(5) == b"%PDF-"
    assert any("approximate" in w.lower() for w in res["warnings"])


def test_preview_html_generated():
    from logosforge.export import export_professional_preview_html
    db = Database()
    pid = _film(db)
    html = export_professional_preview_html(db, pid)
    assert html.startswith("<!DOCTYPE")
    assert "The Heist" in html
    assert "INT. VAULT - NIGHT" in html.upper()
    assert "@media print" in html           # print CSS


def test_preview_dark_mode():
    from logosforge.screenplay_html_preview import build_screenplay_preview_html
    db = Database()
    pid = _film(db)
    html = build_screenplay_preview_html(_render(db, pid), dark=True)
    assert "#1e1e1e" in html


# ===========================================================================
# FDX (experimental)
# ===========================================================================


def test_fdx_gated_without_acknowledgement():
    from logosforge.export import export_screenplay_fdx_experimental
    db = Database()
    pid = _film(db)
    res = export_screenplay_fdx_experimental(db, pid)
    assert res.ok is False and res.experimental is True
    assert any("gated" in w.lower() for w in res.warnings)
    assert res.text == ""


def test_fdx_experimental_export_standard_elements():
    from logosforge.export import export_screenplay_fdx_experimental
    db = Database()
    pid = _film(db)
    res = export_screenplay_fdx_experimental(
        db, pid, options={"experimental_export_acknowledged": True})
    assert res.ok and res.experimental
    assert 'Type="Scene Heading"' in res.text
    assert 'Type="Character"' in res.text
    assert 'Type="Dialogue"' in res.text
    assert res.filename.endswith(".fdx")
    assert any("experimental" in w.lower() for w in res.warnings)


def test_fdx_notes_omitted_with_warning():
    from logosforge.export import export_screenplay_fdx_experimental
    db = Database()
    pid = _film(db)
    res = export_screenplay_fdx_experimental(
        db, pid, options={"experimental_export_acknowledged": True})
    assert "guard" not in res.text
    assert any("note" in w.lower() for w in res.warnings)


def test_fdx_result_serializable():
    from logosforge.export import export_screenplay_fdx_experimental
    db = Database()
    pid = _film(db)
    assert json.dumps(export_screenplay_fdx_experimental(db, pid).to_dict())


# ===========================================================================
# Output validation
# ===========================================================================


def test_validation_wrong_writing_mode():
    from logosforge.screenplay_output_validation import validate_professional_output
    db = Database()
    pid = db.create_project("Book", narrative_engine="novel").id
    db.create_scene(pid, "S", content="Prose.", summary="x")
    rep = validate_professional_output(db, pid, target_format="docx")
    assert any("screenplay mode" in w for w in rep.warnings)


def test_validation_empty_screenplay():
    from logosforge.screenplay_output_validation import validate_professional_output
    db = Database()
    pid = db.create_project("E", narrative_engine="screenplay").id
    rep = validate_professional_output(db, pid, target_format="docx")
    assert any("empty" in e.lower() for e in rep.blocking_errors) or not rep.is_export_safe \
        or rep.warnings  # empty content surfaces via the fountain validator


def test_validation_unsupported_target_blocks():
    from logosforge.screenplay_output_validation import validate_professional_output
    db = Database()
    pid = _film(db)
    rep = validate_professional_output(db, pid, target_format="xyz")
    assert not rep.is_export_safe


def test_validation_compatibility_levels():
    from logosforge.screenplay_output_validation import (
        validate_professional_output, LEVEL_STABLE, LEVEL_PREVIEW, LEVEL_EXPERIMENTAL,
    )
    db = Database()
    pid = _film(db)
    assert validate_professional_output(db, pid, target_format="docx").compatibility_level == LEVEL_STABLE
    assert validate_professional_output(db, pid, target_format="pdf").compatibility_level == LEVEL_PREVIEW
    assert validate_professional_output(db, pid, target_format="fdx").compatibility_level == LEVEL_EXPERIMENTAL


def test_validation_pdf_approximate_warning():
    from logosforge.screenplay_output_validation import validate_professional_output
    db = Database()
    pid = _film(db)
    rep = validate_professional_output(db, pid, target_format="pdf")
    assert any("approximate" in w.lower() for w in rep.warnings)


def test_validation_no_db_mutation_no_llm(monkeypatch):
    import logosforge.assistant as assistant
    from logosforge.screenplay_output_validation import validate_professional_output
    calls = []
    monkeypatch.setattr(assistant, "chat_completion",
                        lambda *a, **k: calls.append(1) or ("", False))
    db = Database()
    pid = _film(db)
    before = len(db.get_all_scenes(pid))
    validate_professional_output(db, pid, target_format="docx")
    assert calls == [] and len(db.get_all_scenes(pid)) == before


def test_validation_json_export():
    from logosforge.export import export_screenplay_output_validation_json
    db = Database()
    pid = _film(db)
    data = json.loads(export_screenplay_output_validation_json(db, pid))
    assert data["schema_version"] == 1 and data["writing_mode"] == "screenplay"
    assert "available_formats" in data and "compatibility_level" in data


# ===========================================================================
# Existing exports unbroken
# ===========================================================================


def test_fountain_and_markdown_still_separate_and_work():
    from logosforge.export import export_screenplay_fountain, export_markdown
    db = Database()
    pid = _film(db)
    assert "INT. VAULT - NIGHT" in export_screenplay_fountain(db, pid)
    assert export_markdown(db, pid) != export_screenplay_fountain(db, pid)


def test_novel_export_unbroken():
    from logosforge.export import export_fountain, export_json
    db = Database()
    pid = db.create_project("Book", narrative_engine="novel").id
    db.create_scene(pid, "Opening", content="The dawn broke.", summary="x")
    assert "The dawn broke." in export_fountain(db, pid)
    assert json.loads(export_json(db, pid))["project"]["writing_mode"] == "novel"


# ===========================================================================
# Logos
# ===========================================================================


def test_output_logos_actions_registered_deterministic_screenplay_only():
    from logosforge.logos import actions as A
    from logosforge.logos import deterministic as det
    for name in ("sp_validate_professional_output", "sp_output_readiness_report",
                 "sp_preview_output", "sp_check_pdf_readiness",
                 "sp_check_fdx_feasibility", "sp_explain_export_warnings",
                 "sp_prepare_professional_export"):
        act = A.get_action(name)
        assert act and act.modes == ("screenplay",) and act.deterministic
        assert det.is_deterministic(name)


def test_output_actions_do_not_dominate_novel():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("Book", narrative_engine="novel")
    ctl = LogosController(db)
    names = [a.name for a in ctl.available_actions("Manuscript", writing_mode="novel")]
    assert not any(n.startswith("sp_") for n in names)


def test_validate_output_action_no_llm():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def boom(*a, **k):
        raise AssertionError("deterministic output action must not use the LLM")

    db = Database()
    pid = _film(db)
    ctl = LogosController(db, provider_resolver=boom, chat_fn=boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript")
    res = ctl.run(ctx, "sp_validate_professional_output")
    assert res.ok and "format" in res.message.lower()
    assert res.proposed_operations == []


# ===========================================================================
# Assistant context
# ===========================================================================


def test_assistant_professional_block_opt_in():
    from logosforge.assistant_context_policy import gather_injected_context
    from logosforge.settings import get_manager
    db = Database()
    pid = _film(db)
    sid = db.get_all_scenes(pid)[0].id
    # Off by default — no professional block.
    ctx = gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    assert "[Professional Output Readiness]" not in ctx
    # Opt-in.
    get_manager().set("include_professional_output_in_assistant_context", True)
    ctx2 = gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    assert "[Professional Output Readiness]" in ctx2
    assert "Available formats:" in ctx2


def test_professional_block_no_llm_no_mutation(monkeypatch):
    import logosforge.assistant as assistant
    from logosforge.assistant_context_policy import gather_injected_context
    from logosforge.settings import get_manager
    calls = []
    monkeypatch.setattr(assistant, "chat_completion",
                        lambda *a, **k: calls.append(1) or ("", False))
    db = Database()
    pid = _film(db)
    sid = db.get_all_scenes(pid)[0].id
    get_manager().set("include_professional_output_in_assistant_context", True)
    before = len(db.get_all_scenes(pid))
    gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    assert calls == [] and len(db.get_all_scenes(pid)) == before


def test_professional_block_absent_for_novel():
    from logosforge.assistant_context_policy import gather_injected_context
    from logosforge.settings import get_manager
    db = Database()
    pid = db.create_project("Book", narrative_engine="novel").id
    sid = db.create_scene(pid, "S", content="Prose.", summary="x").id
    get_manager().set("include_professional_output_in_assistant_context", True)
    ctx = gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    assert "[Professional Output Readiness]" not in ctx


# ===========================================================================
# Health
# ===========================================================================


def test_health_output_categories_present_and_capped():
    from logosforge.logos.health import HealthEngine
    from logosforge.logos.health import metric as M
    db = Database()
    pid = _film(db)
    by = {m.category: m for m in HealthEngine(db, pid).generate_report().metrics}
    assert M.CAT_PRO_OUTPUT_READINESS in by and M.CAT_FDX_COMPAT_RISK in by
    for c in (M.CAT_PRO_OUTPUT_READINESS, M.CAT_FDX_COMPAT_RISK):
        assert by[c].status in (M.STATUS_STABLE, M.STATUS_WATCH, M.STATUS_UNKNOWN)


def test_fdx_risk_is_watch_not_failure():
    from logosforge.logos.health import HealthEngine
    from logosforge.logos.health import metric as M
    db = Database()
    pid = _film(db)
    by = {m.category: m for m in HealthEngine(db, pid).generate_report().metrics}
    assert by[M.CAT_FDX_COMPAT_RISK].status == M.STATUS_WATCH  # never weak/critical


def test_novel_health_has_no_output_categories():
    from logosforge.logos.health import HealthEngine
    from logosforge.logos.health import metric as M
    db = Database()
    pid = db.create_project("Book", narrative_engine="novel").id
    db.create_scene(pid, "Ch1", content="Morning.", summary="x")
    cats = {m.category for m in HealthEngine(db, pid).generate_report().metrics}
    assert M.CAT_PRO_OUTPUT_READINESS not in cats


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
