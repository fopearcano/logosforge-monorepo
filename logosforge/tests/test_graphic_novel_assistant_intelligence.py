"""Tests for Slice 5 — Graphic Novel Assistant intelligence."""

import pytest

from logosforge.db import Database
from logosforge.graphic_novel_plot import build_graphic_novel_context
from logosforge.graphic_novel_review import (
    GN_COMMANDS,
    detect_missing_visual_action,
    detect_text_heavy_page,
    format_gn_command,
    review_gn_page,
    review_gn_panel,
    suggest_page_turn,
    suggest_panel_rewrite,
)


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    yield
    settings._instance = None


def _gn(db):
    return db.create_project(
        "GN", narrative_engine="graphic_novel",
        default_writing_format="graphic_novel",
    )


def _types(checks):
    return {c.check_type for c in checks}


# =========================================================================
# 1. Assistant context includes page/panel data (§2)
# =========================================================================

def test_gn_context_has_page_and_panel_data():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id, density_level="medium")
    db.create_gn_panel(page.id, description="x")
    db.create_gn_panel(page.id, description="y")
    ctx = build_graphic_novel_context(db, p.id)
    assert "[Graphic Novel Context]" in ctx
    assert "Page rhythm" in ctx
    assert "Panel density" in ctx
    assert "p1:2" in ctx   # two panels on page 1


def test_assistant_panel_sees_gn_context():
    from logosforge.ui.assistant_view import AssistantPanel
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id, density_level="dense")
    db.create_gn_panel(page.id, description="x")
    db.create_scene(p.id, "PAGE ONE", content="x")
    panel = AssistantPanel(db, p.id)
    structural = panel._build_context()[8]
    assert "[Graphic Novel Context]" in structural
    assert "panel rhythm" in structural  # engine priority in format block


# =========================================================================
# 2. Page review — text-heavy detection (§3, §8)
# =========================================================================

def test_detect_text_heavy_balloon_overload():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    db.create_gn_panel(page.id, dialogue_refs=["a", "b", "c", "d"])  # 4 balloons / 1 panel
    assert detect_text_heavy_page(db, page.id) is True


def test_detect_text_heavy_by_ratio():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    db.create_gn_panel(page.id, dialogue_refs=["hi"])
    db.create_gn_panel(page.id, dialogue_refs=["yo"])
    db.create_gn_panel(page.id, description="silent")  # 2/3 have dialogue
    assert detect_text_heavy_page(db, page.id) is True


def test_quiet_page_not_text_heavy():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    db.create_gn_panel(page.id, description="a")
    db.create_gn_panel(page.id, description="b", dialogue_refs=["one"])
    assert detect_text_heavy_page(db, page.id) is False


def test_review_gn_page_flags_text_heavy():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id, emotional_beat="dread")
    db.create_gn_panel(page.id, description="x", shot_type="wide",
                       dialogue_refs=["a", "b", "c"])
    assert "text_heavy" in _types(review_gn_page(db, page.id))


# =========================================================================
# 3. Panel review — missing drawable action (§3, §8)
# =========================================================================

def test_detect_missing_visual_action():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    panel = db.create_gn_panel(page.id, description="He realizes the truth")
    assert detect_missing_visual_action(db, panel.id) is True


def test_action_present_is_drawable():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    panel = db.create_gn_panel(
        page.id, description="He realizes the truth", action="slams the door",
    )
    assert detect_missing_visual_action(db, panel.id) is False


def test_review_gn_panel_flags_drawable_action():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    panel = db.create_gn_panel(page.id, description="She remembers her mother",
                               shot_type="close_up")
    assert "drawable_action" in _types(review_gn_panel(db, panel.id))


def test_review_gn_panel_flags_unreadable_and_shot():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    blank = db.create_gn_panel(page.id)  # no desc/action
    assert "panel_readable" in _types(review_gn_panel(db, blank.id))
    noshot = db.create_gn_panel(page.id, description="a wide vista")
    assert "shot_clarity" in _types(review_gn_panel(db, noshot.id))


def test_review_gn_panel_dialogue_overflow():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    long_line = "This is an extremely long monologue " * 5
    panel = db.create_gn_panel(page.id, description="x", shot_type="wide",
                               dialogue_refs=[long_line])
    assert "dialogue_overflow" in _types(review_gn_panel(db, panel.id))


def test_suggest_panel_rewrite_uses_gn_vocab():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    panel = db.create_gn_panel(page.id, description="He realizes the truth")
    out = suggest_panel_rewrite(db, panel.id)
    assert "drawable action" in out.lower()
    # Not generic novel advice.
    assert "develop the character" not in out.lower()


# =========================================================================
# 4. Page-turn review — missing reveal pressure (§3)
# =========================================================================

def test_page_turn_missing_reveal_pressure():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)  # no reveal_type
    db.create_gn_panel(page.id, description="x")
    assert "page_turn_pressure" in _types(suggest_page_turn(db, page.id))


def test_page_turn_with_reveal_has_pressure():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id, reveal_type="cliffhanger")
    nxt = db.create_gn_page(p.id)
    db.create_gn_panel(nxt.id, description="the reveal")
    assert "page_turn_pressure" not in _types(suggest_page_turn(db, page.id))


def test_page_turn_reveal_with_empty_next_page():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id, reveal_type="page_turn")
    db.create_gn_page(p.id)  # next page empty
    checks = suggest_page_turn(db, page.id)
    assert any(c.severity == "warning" for c in checks)


# =========================================================================
# 5. Motif / continuity review uses PSYKE visual memory (§7)
# =========================================================================

def test_gn_continuity_flags_missing_visual_identity():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    db.create_gn_panel(page.id, characters_present=["Zampano"])
    db.create_psyke_entry(p.id, "Zampano", entry_type="character")  # no visual
    out = format_gn_command(db, p.id, "continuity")
    assert "Zampano" in out
    assert "visual identity" in out.lower()


def test_gn_continuity_clean_when_identity_present():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    db.create_gn_panel(page.id, characters_present=["Zampano"])
    z = db.create_psyke_entry(p.id, "Zampano", entry_type="character")
    db.set_psyke_visual_memory(z.id, {"silhouette": "small fluffy Maltese"})
    out = format_gn_command(db, p.id, "continuity")
    assert "no issues found" in out.lower()


# =========================================================================
# 6. /gn commands — compact grouped output (§5, §6)
# =========================================================================

def test_gn_check_grouped_format():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    db.create_gn_panel(page.id, description="He realizes the truth")
    out = format_gn_command(db, p.id, "check")
    assert out.startswith("Graphic Novel Review")
    assert "Panel Readability:" in out
    assert "- issue:" in out
    assert "fix:" in out


def test_gn_commands_constant():
    for c in ("check", "page", "panel", "rhythm", "page-turn", "motifs",
              "continuity"):
        assert c in GN_COMMANDS


def test_gn_command_unknown():
    db = Database()
    p = _gn(db)
    db.create_gn_page(p.id)
    out = format_gn_command(db, p.id, "bogus")
    assert "Unknown /gn command" in out


def test_gn_command_no_pages():
    db = Database()
    p = _gn(db)
    out = format_gn_command(db, p.id, "check")
    assert "No graphic-novel pages" in out


# =========================================================================
# 7. chat_view integration + engine gating (§5, §10)
# =========================================================================

def test_chat_view_gn_command_integration():
    from logosforge.ui.chat_view import ChatView
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    db.create_gn_panel(page.id, description="He realizes the truth")
    view = ChatView(db, p.id)
    assert view._handle_slash_command("/gn check") is True
    msgs = db.get_chat_messages(p.id)
    assert any("Graphic Novel Review" in m.content
               for m in msgs if m.role == "system")


def test_chat_view_gn_command_rejected_for_novel():
    from logosforge.ui.chat_view import ChatView
    db = Database()
    p = db.create_project("Novel")
    view = ChatView(db, p.id)
    assert view._handle_slash_command("/gn check") is True
    msgs = db.get_chat_messages(p.id)
    assert any("only available for Graphic Novel" in m.content
               for m in msgs if m.role == "system")


# =========================================================================
# 8. Non-GN projects get no GN review behavior (§10)
# =========================================================================

def test_non_gn_project_no_gn_context():
    from logosforge.ui.assistant_view import AssistantPanel
    db = Database()
    p = db.create_project("Novel")
    db.create_scene(p.id, "Chapter 1", content="prose")
    panel = AssistantPanel(db, p.id)
    assert "[Graphic Novel Context]" not in panel._build_context()[8]
