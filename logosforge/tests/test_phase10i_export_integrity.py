"""Phase 10I — export compatibility audit + roundtrip integrity."""

from __future__ import annotations

import json
import os
import warnings

import pytest

warnings.filterwarnings("ignore")

from logosforge.db import Database
from tests.helpers.screenplay_export_fixtures import (
    build_screenplay_fixture, REQUIRED_TOKENS, CUE_EXTENSION,
    fountain_text, fountain_parsed_text, docx_text, html_text, fdx_text,
    assert_tokens_present,
)


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
# No-text-loss across formats
# ===========================================================================


def test_fountain_no_text_loss_and_cue_extension():
    db, pid = build_screenplay_fixture()
    ft = fountain_text(db, pid)
    assert assert_tokens_present(ft) == []
    assert CUE_EXTENSION in ft                       # (V.O.) preserved on cue
    assert "!THE LIGHTS DIE" in ft                   # ambiguous caps forced
    assert "MARÍA" in ft                             # accent preserved


def test_fountain_roundtrip_no_text_loss():
    db, pid = build_screenplay_fixture()
    parsed = fountain_parsed_text(fountain_text(db, pid))
    assert assert_tokens_present(parsed) == []


def test_fountain_roundtrip_preserves_standard_element_types():
    from logosforge.export import export_screenplay_fountain
    from logosforge.screenplay_fountain import parse_fountain_to_screenplay_blocks
    db, pid = build_screenplay_fixture()
    blocks = parse_fountain_to_screenplay_blocks(
        export_screenplay_fountain(db, pid)).blocks
    types = {b.element_type for b in blocks}
    for t in ("scene_heading", "action", "character", "parenthetical",
              "dialogue", "transition"):
        assert t in types


def test_docx_no_text_loss(tmp_path):
    from logosforge.export import export_screenplay_docx
    db, pid = build_screenplay_fixture()
    path = str(tmp_path / "out.docx")
    res = export_screenplay_docx(db, pid, path)
    assert res.ok
    text = docx_text(path)
    # Notes excluded by default; everything else must survive.
    assert assert_tokens_present(text) == []
    assert CUE_EXTENSION in text


def test_html_no_text_loss_and_no_remote_assets():
    from logosforge.export import export_professional_preview_html
    db, pid = build_screenplay_fixture()
    html = export_professional_preview_html(db, pid)
    assert assert_tokens_present(html_text(html)) == []
    assert "http://" not in html and "https://" not in html
    assert "@media print" in html


def test_fdx_no_text_loss_when_acknowledged():
    from logosforge.export import export_screenplay_fdx_experimental
    db, pid = build_screenplay_fixture()
    res = export_screenplay_fdx_experimental(
        db, pid, options={"experimental_export_acknowledged": True})
    assert res.ok
    text = fdx_text(res.text)
    # Notes omitted in FDX; the rest survives.
    assert assert_tokens_present(text) == []


def test_pdf_file_created_and_valid_header(tmp_path):
    from logosforge.export import export_screenplay_pdf
    db, pid = build_screenplay_fixture()
    path = str(tmp_path / "out.pdf")
    res = export_screenplay_pdf(db, pid, path)
    assert res["ok"] and os.path.getsize(path) > 0
    with open(path, "rb") as fh:
        assert fh.read(5) == b"%PDF-"


# ===========================================================================
# Render-model heading consistency (Phase 10I fix)
# ===========================================================================


def test_render_exports_inject_scene_heading_when_missing():
    from logosforge.screenplay_render import build_render_document
    db = Database()
    pid = db.create_project("T", narrative_engine="screenplay").id
    db.create_scene(pid, "Opening", content="The dawn broke.", summary="x")
    doc = build_render_document(db, pid)
    assert doc.blocks[0].element_type == "scene_heading"
    assert doc.blocks[0].text == "Opening"


def test_render_exports_no_duplicate_heading_when_present():
    from logosforge.screenplay_render import build_render_document
    db = Database()
    pid = db.create_project("T", narrative_engine="screenplay").id
    db.create_scene(pid, "X", content="INT. BAR - DAY\n\nAction.", summary="x")
    headings = [b.text for b in build_render_document(db, pid).blocks
                if b.element_type == "scene_heading"]
    assert headings == ["INT. BAR - DAY"]


def test_docx_includes_heading_for_headingless_scene(tmp_path):
    from logosforge.export import export_screenplay_docx
    db = Database()
    pid = db.create_project("T", narrative_engine="screenplay").id
    db.create_scene(pid, "Opening", content="The dawn broke.", summary="x")
    path = str(tmp_path / "o.docx")
    export_screenplay_docx(db, pid, path)
    assert "OPENING" in docx_text(path).upper()


# ===========================================================================
# Fountain vs Markdown separation + extensions
# ===========================================================================


def test_fountain_and_markdown_are_separate():
    from logosforge.export import export_screenplay_fountain, export_markdown
    db, pid = build_screenplay_fixture()
    fountain = export_screenplay_fountain(db, pid)
    md = export_markdown(db, pid)
    assert fountain != md
    # Fountain title page uses key:value; Markdown uses '#'/'*'.
    assert fountain.startswith("Title:")
    assert "Title:" not in md.split("\n")[0]


def test_fountain_filename_extension():
    from logosforge.export import export_screenplay_fountain_result
    db, pid = build_screenplay_fixture()
    assert export_screenplay_fountain_result(db, pid).filename.endswith(".fountain")


def test_fdx_filename_extension():
    from logosforge.export import export_screenplay_fdx_experimental
    db, pid = build_screenplay_fixture()
    res = export_screenplay_fdx_experimental(
        db, pid, options={"experimental_export_acknowledged": True})
    assert res.filename.endswith(".fdx")


def test_screenplay_text_export_not_markdown():
    """The plain-text screenplay export is not routed through Markdown."""
    from logosforge.export import export_screenplay, export_markdown
    db, pid = build_screenplay_fixture()
    assert export_screenplay(db, pid) != export_markdown(db, pid)


# ===========================================================================
# Writing-mode visibility (screenplay exports/actions don't leak to other modes)
# ===========================================================================


@pytest.mark.parametrize("engine", ["novel", "graphic_novel", "stage_script", "series"])
def test_screenplay_logos_actions_hidden_in_other_modes(engine):
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("P", narrative_engine=engine)
    ctl = LogosController(db)
    names = [a.name for a in ctl.available_actions("Manuscript", writing_mode=engine)]
    assert not any(n.startswith("sp_") for n in names)


def test_screenplay_export_actions_present_in_screenplay():
    from logosforge.logos.controller import LogosController
    db, pid = build_screenplay_fixture()
    ctl = LogosController(db)
    names = [a.name for a in ctl.available_actions("Manuscript", writing_mode="screenplay")]
    for n in ("sp_validate_fountain_export", "sp_validate_professional_output"):
        assert n in names


def test_novel_export_unaffected():
    from logosforge.export import export_fountain, export_json, export_manuscript
    db = Database()
    pid = db.create_project("Book", narrative_engine="novel").id
    db.create_scene(pid, "Opening", content="The dawn broke.", summary="x")
    assert "The dawn broke." in export_fountain(db, pid)
    assert "The dawn broke." in export_manuscript(db, pid)
    assert json.loads(export_json(db, pid))["project"]["writing_mode"] == "novel"


# ===========================================================================
# Exports are read-only (no DB mutation, no LLM)
# ===========================================================================


def test_all_exports_no_db_mutation_no_llm(tmp_path, monkeypatch):
    import logosforge.assistant as assistant
    from logosforge.export import (
        export_screenplay_fountain, export_screenplay_docx, export_screenplay_pdf,
        export_screenplay_fdx_experimental, export_professional_preview_html,
        export_markdown, export_json,
    )
    calls = []
    monkeypatch.setattr(assistant, "chat_completion",
                        lambda *a, **k: calls.append(1) or ("", False))
    db, pid = build_screenplay_fixture()
    before = (len(db.get_all_scenes(pid)), len(db.get_story_links(pid)))
    export_screenplay_fountain(db, pid)
    export_screenplay_docx(db, pid, str(tmp_path / "a.docx"))
    export_screenplay_pdf(db, pid, str(tmp_path / "a.pdf"))
    export_screenplay_fdx_experimental(db, pid, options={"experimental_export_acknowledged": True})
    export_professional_preview_html(db, pid)
    export_markdown(db, pid)
    export_json(db, pid)
    after = (len(db.get_all_scenes(pid)), len(db.get_story_links(pid)))
    assert calls == [] and before == after


# ===========================================================================
# Assistant export-context: capped, no full dump, no stale leak
# ===========================================================================


def test_assistant_export_context_capped_no_full_dump():
    from logosforge.assistant_context_policy import gather_injected_context
    db, pid = build_screenplay_fixture()
    sid = db.get_all_scenes(pid)[0].id
    ctx = gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    # The full scene body must not be dumped into context.
    assert "Rain hammers the tin roof." not in ctx
    # Cumulative screenplay context stays bounded.
    assert len(ctx) < 4000


def test_assistant_export_context_no_stale_leak():
    from logosforge.assistant_context_policy import gather_injected_context
    db, p1 = build_screenplay_fixture()
    p2 = db.create_project("Other", narrative_engine="screenplay").id
    db.create_scene(p2, "Solo", content="INT. ROOM - DAY\n\nNothing of note.", summary="x")
    s2 = db.get_all_scenes(p2)[0].id
    ctx2 = gather_injected_context(db, p2, section_name="Manuscript", scene_id=s2)
    assert "WAREHOUSE" not in ctx2 and "MARÍA" not in ctx2


def test_assistant_export_context_no_llm_no_mutation(monkeypatch):
    import logosforge.assistant as assistant
    from logosforge.assistant_context_policy import gather_injected_context
    calls = []
    monkeypatch.setattr(assistant, "chat_completion",
                        lambda *a, **k: calls.append(1) or ("", False))
    db, pid = build_screenplay_fixture()
    sid = db.get_all_scenes(pid)[0].id
    before = len(db.get_all_scenes(pid))
    gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    assert calls == [] and len(db.get_all_scenes(pid)) == before


# ===========================================================================
# FDX safety
# ===========================================================================


def test_fdx_gated_and_valid_xml():
    import xml.etree.ElementTree as ET
    from logosforge.export import export_screenplay_fdx_experimental
    db, pid = build_screenplay_fixture()
    gated = export_screenplay_fdx_experimental(db, pid)
    assert not gated.ok and gated.experimental
    res = export_screenplay_fdx_experimental(
        db, pid, options={"experimental_export_acknowledged": True})
    ET.fromstring(res.text)   # valid XML, no exception
    assert any("experimental" in w.lower() for w in res.warnings)


# ===========================================================================
# Health: output-format health separate from narrative
# ===========================================================================


def test_output_format_health_capped_not_narrative_failure():
    from logosforge.logos.health import HealthEngine
    from logosforge.logos.health import metric as M
    db, pid = build_screenplay_fixture()
    report = HealthEngine(db, pid).generate_report()
    fmt_cats = {M.CAT_FOUNTAIN_READINESS, M.CAT_PRO_OUTPUT_READINESS,
                M.CAT_FDX_COMPAT_RISK, M.CAT_EXPORT_READINESS}
    for m in report.metrics:
        if m.category in fmt_cats:
            assert m.status in (M.STATUS_STABLE, M.STATUS_WATCH, M.STATUS_UNKNOWN)


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
