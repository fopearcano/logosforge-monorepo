"""Phase 10B — Screenplay block engine + Fountain/plain-text export hardening."""

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
# Block model
# ===========================================================================


def test_block_valid_element_types():
    from logosforge.screenplay_blocks import ScreenplayBlock
    import logosforge.screenplay as sp
    for et in sp.ELEMENT_KEYS:
        assert ScreenplayBlock(et, "x").element_type == et


def test_block_invalid_element_falls_back_to_action():
    from logosforge.screenplay_blocks import ScreenplayBlock, normalize_element_type
    assert ScreenplayBlock("nonsense", "x").element_type == "action"
    assert ScreenplayBlock("", "x").element_type == "action"
    assert normalize_element_type("floob") == "action"
    assert normalize_element_type("dialogue") == "dialogue"


def test_block_serialization_roundtrip_dict():
    from logosforge.screenplay_blocks import ScreenplayBlock
    b = ScreenplayBlock("character", "JOHN", scene_id=3, order_index=2,
                        metadata={"ext": "V.O."})
    d = b.to_dict()
    b2 = ScreenplayBlock.from_dict(d)
    assert b2.element_type == "character" and b2.text == "JOHN"
    assert b2.scene_id == 3 and b2.order_index == 2 and b2.metadata == {"ext": "V.O."}


# ===========================================================================
# Parser
# ===========================================================================


def test_parser_preserves_all_text():
    from logosforge.screenplay_blocks import parse_screenplay_text
    text = ("INT. BAR - NIGHT\n\nJohn enters.\n\nJOHN\nHello.\n\n"
            "They wait.")
    blocks = parse_screenplay_text(text)
    joined = " ".join(b.text for b in blocks)
    for fragment in ("INT. BAR - NIGHT", "John enters.", "JOHN", "Hello.", "They wait."):
        assert fragment in joined


def test_parser_detects_scene_heading():
    from logosforge.screenplay_blocks import parse_screenplay_text
    for prefix in ("INT.", "EXT.", "INT./EXT.", "EST."):
        blocks = parse_screenplay_text(f"{prefix} HOUSE - DAY")
        assert blocks[0].element_type == "scene_heading"


def test_parser_detects_transition():
    from logosforge.screenplay_blocks import parse_screenplay_text
    assert parse_screenplay_text("CUT TO:")[0].element_type == "transition"
    assert parse_screenplay_text("DISSOLVE TO:")[0].element_type == "transition"
    assert parse_screenplay_text("FADE OUT.")[0].element_type == "transition"


def test_parser_detects_character_dialogue_parenthetical():
    from logosforge.screenplay_blocks import parse_screenplay_text
    blocks = parse_screenplay_text("JOHN\n(quietly)\nWe need to talk.")
    kinds = [b.element_type for b in blocks]
    assert kinds == ["character", "parenthetical", "dialogue"]


def test_parser_defaults_uncertain_text_to_action():
    from logosforge.screenplay_blocks import parse_screenplay_text
    # Ordinary prose paragraph → action (no false character/transition).
    blocks = parse_screenplay_text("It was a quiet morning and the sun rose slowly.")
    assert len(blocks) == 1 and blocks[0].element_type == "action"
    # A lone uppercase short line without dialogue stays action (conservative).
    blocks2 = parse_screenplay_text("THE END")
    assert blocks2[0].element_type == "action"


def test_parser_scene_id_and_order():
    from logosforge.screenplay_blocks import parse_screenplay_text
    blocks = parse_screenplay_text("INT. X\n\nAction one.\n\nMore action.", scene_id=9)
    assert all(b.scene_id == 9 for b in blocks)
    assert [b.order_index for b in blocks] == list(range(len(blocks)))


# ===========================================================================
# Serializer
# ===========================================================================


def test_serializer_uppercases_caps_elements():
    from logosforge.screenplay_blocks import ScreenplayBlock, serialize_blocks
    blocks = [
        ScreenplayBlock("scene_heading", "int. bar - night"),
        ScreenplayBlock("character", "john"),
        ScreenplayBlock("dialogue", "Hello there."),
        ScreenplayBlock("transition", "cut to:"),
    ]
    out = serialize_blocks(blocks)
    assert "INT. BAR - NIGHT" in out
    assert "JOHN" in out
    assert "Hello there." in out      # dialogue not uppercased
    assert "CUT TO:" in out


def test_serializer_normalizes_parenthetical():
    from logosforge.screenplay_blocks import ScreenplayBlock, serialize_blocks
    out = serialize_blocks([ScreenplayBlock("parenthetical", "quietly")])
    assert "(quietly)" in out


def test_serializer_no_uppercase_option():
    from logosforge.screenplay_blocks import ScreenplayBlock, serialize_blocks
    out = serialize_blocks([ScreenplayBlock("character", "john")], uppercase=False)
    assert "john" in out


def test_roundtrip_parse_serialize_preserves_content():
    from logosforge.screenplay_blocks import parse_screenplay_text, serialize_blocks
    text = "INT. BAR - NIGHT\n\nJohn enters.\n\nJOHN\nHello.\n\nCUT TO:"
    out = serialize_blocks(parse_screenplay_text(text))
    for fragment in ("INT. BAR - NIGHT", "John enters.", "JOHN", "Hello.", "CUT TO:"):
        assert fragment in out


def test_character_cues_unique_and_uppercased():
    from logosforge.screenplay_blocks import parse_screenplay_text, character_cues
    text = "JOHN\nHi.\n\nMARY\nHello.\n\nJOHN (V.O.)\nLater."
    cues = character_cues(parse_screenplay_text(text))
    assert cues == ["JOHN", "MARY"]


# ===========================================================================
# Export hardening
# ===========================================================================


def _screenplay_with_dialogue(db):
    pid = db.create_project("Heist", narrative_engine="screenplay").id
    db.create_scene(
        pid, "The Vault",
        content="INT. VAULT - NIGHT\n\nThey crack the safe.\n\nJOHN\nGot it.",
        summary="x",
    )
    return pid


def test_screenplay_export_includes_writing_mode_and_classifies():
    from logosforge.export import export_screenplay
    db = Database()
    pid = _screenplay_with_dialogue(db)
    out = export_screenplay(db, pid)
    assert "Writing Mode: Screenplay" in out
    assert "They crack the safe." in out   # action preserved
    assert "JOHN" in out                    # character cue preserved
    assert "Got it." in out                 # dialogue preserved


def test_fountain_export_preserves_heading_action_dialogue():
    from logosforge.export import export_fountain
    db = Database()
    pid = _screenplay_with_dialogue(db)
    out = export_fountain(db, pid)
    assert "Title: Heist" in out
    assert "They crack the safe." in out
    assert "JOHN" in out
    assert "Got it." in out


def test_screenplay_export_does_not_break_novel_export():
    from logosforge.export import export_manuscript, export_json
    import json
    db = Database()
    pid = db.create_project("Book", narrative_engine="novel").id
    db.create_scene(pid, "Chapter One", content="It was a quiet morning.", summary="x")
    txt = export_manuscript(db, pid)
    assert "It was a quiet morning." in txt
    assert "Writing Mode: Screenplay" not in txt
    assert json.loads(export_json(db, pid))["project"]["writing_mode"] == "novel"


# ===========================================================================
# Logos actions (hardened set)
# ===========================================================================


def test_new_screenplay_actions_registered_and_restricted():
    from logosforge.logos import actions as A
    for name in ("sp_setup_payoff", "sp_overwritten_action", "sp_escalation"):
        act = A.get_action(name)
        assert act is not None and act.modes == ("screenplay",) and not act.destructive


def test_screenplay_actions_prioritized_in_screenplay_not_novel():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("S", narrative_engine="screenplay")
    ctl = LogosController(db)
    sp_names = [a.name for a in ctl.available_actions("Manuscript", writing_mode="screenplay")]
    assert sp_names[0].startswith("sp_")
    assert "sp_setup_payoff" in sp_names and "sp_overwritten_action" in sp_names
    novel = [a.name for a in ctl.available_actions("Manuscript", writing_mode="novel")]
    assert not any(n.startswith("sp_") for n in novel)


# ===========================================================================
# Assistant / LogosContext
# ===========================================================================


def test_assistant_context_includes_screenplay_scene_block():
    from logosforge.assistant_context_policy import gather_injected_context
    db = Database()
    pid = db.create_project("Film", narrative_engine="screenplay").id
    sid = db.create_scene(
        pid, "Vault",
        content="INT. VAULT - NIGHT\n\nThey enter.\n\nJOHN\nGo.\n\nMARY\nNow.",
        summary="x",
    ).id
    ctx = gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    assert "[Screenplay Scene]" in ctx
    assert "JOHN" in ctx and "MARY" in ctx


def test_screenplay_scene_block_absent_for_novel():
    from logosforge.assistant_context_policy import gather_injected_context
    db = Database()
    pid = db.create_project("Book", narrative_engine="novel").id
    sid = db.create_scene(pid, "Ch1", content="JOHN\nHello.", summary="x").id
    ctx = gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    assert "[Screenplay Scene]" not in ctx


def test_logos_context_can_carry_current_screenplay_element():
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay").id
    ctx = build_logos_context(db, pid, section_name="Manuscript",
                              active_block_type="dialogue")
    assert ctx.active_block_type == "dialogue"
    assert ctx.writing_mode == "screenplay"


# ===========================================================================
# Manuscript editor — current element accessor (no mode mutation)
# ===========================================================================


def test_writing_core_view_current_element_type():
    from logosforge.ui.writing_core_view import WritingCoreView
    from logosforge.writing_modes import get_project_writing_mode_by_id
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay").id
    db.create_scene(pid, "Open", content="INT. BAR - NIGHT", summary="x")
    view = WritingCoreView(db, pid)
    # No active editor yet → empty string, never raises.
    assert view.current_element_type() == ""
    # Reading the element must not change the project's writing mode.
    assert get_project_writing_mode_by_id(db, pid) == "screenplay"


# ===========================================================================
# Provider guard
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
