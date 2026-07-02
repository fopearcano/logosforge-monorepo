"""Phase 10G — Fountain-first screenplay export + import pipeline."""

from __future__ import annotations

import json
import warnings

import pytest

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.screenplay_blocks import ScreenplayBlock
from logosforge import screenplay_fountain as sf


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


_STD_BLOCKS = [
    ScreenplayBlock("scene_heading", "INT. BAR - NIGHT"),
    ScreenplayBlock("action", "John enters slowly."),
    ScreenplayBlock("character", "JOHN"),
    ScreenplayBlock("parenthetical", "(quietly)"),
    ScreenplayBlock("dialogue", "We need to talk."),
    ScreenplayBlock("transition", "CUT TO:"),
]


def _ser(blocks, **opts):
    return sf.serialize_screenplay_to_fountain(
        blocks, options=sf.FountainExportOptions(**opts))


# ===========================================================================
# Serializer
# ===========================================================================


def test_serialize_scene_heading():
    out = _ser([ScreenplayBlock("scene_heading", "INT. BAR - NIGHT")]).text
    assert "INT. BAR - NIGHT" in out
    # Non-standard heading is forced with a leading dot.
    out2 = _ser([ScreenplayBlock("scene_heading", "THE VOID")]).text
    assert ".THE VOID" in out2


def test_serialize_action():
    assert "John enters slowly." in _ser([ScreenplayBlock("action", "John enters slowly.")]).text


def test_serialize_character_and_dialogue_grouped():
    out = _ser([ScreenplayBlock("character", "JOHN"),
                ScreenplayBlock("dialogue", "Hello.")]).text
    # Cue and dialogue are on consecutive lines (no blank line between).
    assert "JOHN\nHello." in out


def test_serialize_parenthetical():
    out = _ser([ScreenplayBlock("character", "JOHN"),
                ScreenplayBlock("parenthetical", "beat"),
                ScreenplayBlock("dialogue", "Hi.")]).text
    assert "(beat)" in out


def test_serialize_transition():
    assert "CUT TO:" in _ser([ScreenplayBlock("transition", "cut to:")]).text
    # Non-TO transition is forced with '>'.
    assert "> SMASH" in _ser([ScreenplayBlock("transition", "smash")]).text


def test_serialize_notes_included_or_excluded():
    incl = _ser([ScreenplayBlock("note", "fix this")], include_notes=True).text
    assert "[[fix this]]" in incl
    res = _ser([ScreenplayBlock("note", "fix this")], include_notes=False)
    assert "fix this" not in res.text
    assert any("omitted" in w for w in res.warnings)


def test_serialize_title_page():
    res = sf.serialize_screenplay_to_fountain(
        _STD_BLOCKS, title_page={"title": "My Film", "author": "Me"})
    assert "Title: My Film" in res.text and "Author: Me" in res.text


def test_ambiguous_uppercase_action_forced():
    res = _ser([ScreenplayBlock("action", "BANG")], force_ambiguous_elements=True)
    assert "!BANG" in res.text
    assert any("forced" in w.lower() for w in res.warnings)


def test_serialize_deterministic():
    a = _ser(_STD_BLOCKS).text
    b = _ser(_STD_BLOCKS).text
    assert a == b


def test_export_result_serializable():
    assert json.dumps(_ser(_STD_BLOCKS).to_dict())


# ===========================================================================
# Parser
# ===========================================================================


def test_parse_scene_heading_standard_and_forced():
    assert sf.parse_fountain_to_screenplay_blocks(
        "INT. BAR - NIGHT").blocks[0].element_type == "scene_heading"
    assert sf.parse_fountain_to_screenplay_blocks(
        ".THE VOID").blocks[0].element_type == "scene_heading"


def test_parse_action():
    b = sf.parse_fountain_to_screenplay_blocks("He walks across the room slowly.").blocks
    assert b[0].element_type == "action"


def test_parse_character_dialogue_parenthetical():
    b = sf.parse_fountain_to_screenplay_blocks("JOHN\n(quietly)\nWe need to talk.").blocks
    assert [x.element_type for x in b] == ["character", "parenthetical", "dialogue"]


def test_parse_forced_character():
    b = sf.parse_fountain_to_screenplay_blocks("@McKee\nHello.").blocks
    assert b[0].element_type == "character" and b[0].text == "McKee"
    assert b[1].element_type == "dialogue"


def test_parse_transition():
    assert sf.parse_fountain_to_screenplay_blocks(
        "CUT TO:").blocks[0].element_type == "transition"
    assert sf.parse_fountain_to_screenplay_blocks(
        "> SMASH").blocks[0].element_type == "transition"


def test_parse_title_page():
    res = sf.parse_fountain_to_screenplay_blocks(
        "Title: My Film\nAuthor: Me\n\nINT. X - DAY\n\nAction.")
    assert res.title_page["title"] == "My Film" and res.title_page["author"] == "Me"
    assert res.blocks[0].element_type == "scene_heading"


def test_parse_notes():
    b = sf.parse_fountain_to_screenplay_blocks("[[remember the key]]").blocks
    assert b[0].element_type == "note" and b[0].text == "remember the key"


def test_parse_ambiguous_degrades_to_action():
    # A lone uppercase non-cue line with no dialogue -> action (no false cue).
    b = sf.parse_fountain_to_screenplay_blocks("THE END").blocks
    assert b[0].element_type == "action"


def test_parse_sections_synopses_preserved_as_notes_with_warning():
    res = sf.parse_fountain_to_screenplay_blocks("# Act One\n\n= a synopsis\n\nAction.")
    types = [b.element_type for b in res.blocks]
    assert types.count("note") == 2 and "action" in types
    assert any("section" in w.lower() or "synopsis" in w.lower() for w in res.warnings)


def test_parse_boneyard_removed_with_warning():
    res = sf.parse_fountain_to_screenplay_blocks("Action.\n\n/* hidden */\n\nMore.")
    blob = " ".join(b.text for b in res.blocks)
    assert "hidden" not in blob
    assert any("boneyard" in w.lower() for w in res.warnings)


def test_parse_no_text_loss_for_standard():
    text = "INT. BAR - NIGHT\n\nJohn enters.\n\nJOHN\nHello."
    blocks = sf.parse_fountain_to_screenplay_blocks(text).blocks
    joined = " ".join(b.text for b in blocks)
    for frag in ("INT. BAR - NIGHT", "John enters.", "JOHN", "Hello."):
        assert frag in joined


# ===========================================================================
# Roundtrip
# ===========================================================================


def test_roundtrip_standard_elements():
    res = sf.serialize_screenplay_to_fountain(_STD_BLOCKS)
    parsed = sf.parse_fountain_to_screenplay_blocks(res.text)
    assert [b.element_type for b in parsed.blocks] == [
        "scene_heading", "action", "character", "parenthetical", "dialogue",
        "transition"]


def test_roundtrip_title_page():
    res = sf.serialize_screenplay_to_fountain(
        _STD_BLOCKS, title_page={"title": "T", "author": "A"})
    parsed = sf.parse_fountain_to_screenplay_blocks(res.text)
    assert parsed.title_page["title"] == "T" and parsed.title_page["author"] == "A"


def test_roundtrip_notes_when_included():
    blocks = _STD_BLOCKS + [ScreenplayBlock("note", "guard")]
    res = sf.serialize_screenplay_to_fountain(
        blocks, options=sf.FountainExportOptions(include_notes=True))
    parsed = sf.parse_fountain_to_screenplay_blocks(res.text)
    assert any(b.element_type == "note" and b.text == "guard" for b in parsed.blocks)


# ===========================================================================
# Validation
# ===========================================================================


def test_validate_empty():
    rep = sf.validate_fountain_export("")
    assert not rep.is_valid and rep.blocking_errors


def test_validate_missing_scene_heading_and_title():
    rep = sf.validate_fountain_export("Just action with no heading and no title page.")
    assert any("scene heading" in w for w in rep.warnings)
    assert any("title" in w.lower() for w in rep.warnings)
    assert rep.is_valid  # warnings don't block


def test_validate_report_serializable():
    assert json.dumps(sf.validate_fountain_export("INT. X\n\nAction.").to_dict())


# ===========================================================================
# Export service
# ===========================================================================


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


def test_export_screenplay_fountain_has_extension_and_title():
    from logosforge.export import export_screenplay_fountain_result
    db = Database()
    pid = _film(db)
    res = export_screenplay_fountain_result(db, pid)
    assert res.filename.endswith(".fountain")
    assert "Title: The Heist" in res.text
    assert "INT. VAULT - NIGHT" in res.text
    assert "ALICE\n(quietly)\nGot it." in res.text


def test_export_fountain_screenplay_uses_serializer_no_duplicate_heading():
    from logosforge.export import export_fountain
    db = Database()
    pid = _film(db)
    out = export_fountain(db, pid)
    assert out.count("VAULT - NIGHT") == 1   # no duplicate slug + heading


def test_notes_excluded_by_default_in_fountain():
    from logosforge.export import export_screenplay_fountain
    db = Database()
    pid = _film(db)
    assert "guard" not in export_screenplay_fountain(db, pid)


def test_generic_markdown_export_separate_and_unbroken():
    from logosforge.export import export_markdown, export_screenplay_fountain
    db = Database()
    pid = _film(db)
    md = export_markdown(db, pid)
    fountain = export_screenplay_fountain(db, pid)
    assert md != fountain                       # distinct serializers
    assert "# The Heist" in md or "# Heist" in md  # markdown heading style


def test_novel_export_unbroken():
    from logosforge.export import export_fountain, export_json
    db = Database()
    pid = db.create_project("Book", narrative_engine="novel").id
    db.create_scene(pid, "Opening", content="The dawn broke.", summary="x")
    out = export_fountain(db, pid)   # novel path unchanged
    assert ".OPENING" in out and "The dawn broke." in out
    assert json.loads(export_json(db, pid))["project"]["writing_mode"] == "novel"


def test_fountain_validation_json_export():
    from logosforge.export import export_fountain_validation_json
    db = Database()
    pid = _film(db)
    data = json.loads(export_fountain_validation_json(db, pid))
    assert data["schema_version"] == 1 and data["writing_mode"] == "screenplay"
    assert data["filename"].endswith(".fountain")
    assert "exported_at" in data


# ===========================================================================
# Logos
# ===========================================================================


def test_fountain_logos_actions_registered_deterministic_screenplay_only():
    from logosforge.logos import actions as A
    from logosforge.logos import deterministic as det
    for name in ("sp_validate_fountain_export", "sp_preview_fountain",
                 "sp_check_fountain_compatibility", "sp_find_ambiguous_fountain",
                 "sp_explain_fountain_warning", "sp_prepare_for_fountain"):
        act = A.get_action(name)
        assert act and act.modes == ("screenplay",) and act.deterministic
        assert det.is_deterministic(name)


def test_fountain_actions_do_not_dominate_novel():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("Book", narrative_engine="novel")
    ctl = LogosController(db)
    names = [a.name for a in ctl.available_actions("Manuscript", writing_mode="novel")]
    assert not any(n.startswith("sp_") for n in names)


def test_validate_fountain_action_no_llm():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def boom(*a, **k):
        raise AssertionError("deterministic Fountain action must not use the LLM")

    db = Database()
    pid = _film(db)
    ctl = LogosController(db, provider_resolver=boom, chat_fn=boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript")
    res = ctl.run(ctx, "sp_validate_fountain_export")
    assert res.ok and "Fountain" in res.message
    assert res.proposed_operations == []


# ===========================================================================
# Assistant context
# ===========================================================================


def test_assistant_fountain_export_block():
    from logosforge.assistant_context_policy import gather_injected_context
    db = Database()
    pid = _film(db)
    sid = db.get_all_scenes(pid)[0].id
    ctx = gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    assert "[Fountain Export Readiness]" in ctx
    assert "Export target: .fountain" in ctx
    # Exactly one export-readiness block (no duplicate generic one).
    assert ctx.count("Export Readiness]") == 1


def test_assistant_export_block_switches_for_non_fountain_target():
    from logosforge.assistant_context_policy import gather_injected_context
    from logosforge.screenplay_render import set_export_prefs
    db = Database()
    pid = _film(db)
    sid = db.get_all_scenes(pid)[0].id
    set_export_prefs(db, pid, {"export_target": "plain_text"})
    ctx = gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    assert "[Screenplay Export Readiness]" in ctx
    assert "[Fountain Export Readiness]" not in ctx


def test_fountain_context_no_llm_no_mutation(monkeypatch):
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


def test_fountain_context_absent_for_novel():
    from logosforge.assistant_context_policy import gather_injected_context
    db = Database()
    pid = db.create_project("Book", narrative_engine="novel").id
    sid = db.create_scene(pid, "S", content="Prose here.", summary="x").id
    ctx = gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    assert "[Fountain Export Readiness]" not in ctx


# ===========================================================================
# Health
# ===========================================================================


def test_health_fountain_categories_present_and_capped():
    from logosforge.logos.health import HealthEngine
    from logosforge.logos.health import metric as M
    db = Database()
    pid = _film(db)
    by = {m.category: m for m in HealthEngine(db, pid).generate_report().metrics}
    assert M.CAT_FOUNTAIN_READINESS in by and M.CAT_UNSUPPORTED_ELEMENTS in by
    for c in (M.CAT_FOUNTAIN_READINESS, M.CAT_UNSUPPORTED_ELEMENTS):
        assert by[c].status in (M.STATUS_STABLE, M.STATUS_WATCH, M.STATUS_UNKNOWN)


def test_novel_health_has_no_fountain_categories():
    from logosforge.logos.health import HealthEngine
    from logosforge.logos.health import metric as M
    db = Database()
    pid = db.create_project("Book", narrative_engine="novel").id
    db.create_scene(pid, "Ch1", content="A morning.", summary="x")
    cats = {m.category for m in HealthEngine(db, pid).generate_report().metrics}
    assert M.CAT_FOUNTAIN_READINESS not in cats


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
