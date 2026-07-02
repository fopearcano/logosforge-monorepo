"""Tests for Graphic Novel-aware Assistant: review checks + context."""

import pytest

from logosforge.db import Database
from logosforge.graphic_novel_plot import build_graphic_novel_context
from logosforge.graphic_novel_review import (
    GraphicNovelCheck,
    review_graphic_novel,
)
from logosforge.narrative_engines import GRAPHIC_NOVEL_ENGINE


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
# 1. Engine carries visual priorities + review checks (§1, §2)
# =========================================================================

def test_engine_priorities_visual():
    for pr in ("panel rhythm", "page turns", "visual reveal timing",
               "image/text balance", "symbolic recurrence"):
        assert pr in GRAPHIC_NOVEL_ENGINE.assistant_priorities


def test_engine_review_checks_present():
    checks = GRAPHIC_NOVEL_ENGINE.review_checks
    for c in ("panel readability", "exposition density", "page turn impact",
              "balloon overload"):
        assert c in checks


def test_engine_context_block_reaches_assistant_format():
    block = GRAPHIC_NOVEL_ENGINE.format_context_block()
    assert "[Narrative Engine: Graphic Novel]" in block
    assert "panel rhythm" in block


# =========================================================================
# 2. Review checks trigger correctly (§2, §4)
# =========================================================================

def test_too_much_dialogue_check():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id, density_level="medium")
    for _ in range(3):
        db.create_gn_panel(page.id, description="d", dialogue_refs=["a", "b", "c", "d"])
    checks = review_graphic_novel(db, p.id, page_id=page.id)
    assert "too_much_dialogue" in _types(checks)


def test_visual_clutter_check():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    for _ in range(10):
        db.create_gn_panel(page.id, description="d")
    assert "visual_clutter" in _types(review_graphic_novel(db, p.id, page_id=page.id))


def test_panel_flow_check():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    db.create_gn_panel(page.id, description="clear")
    db.create_gn_panel(page.id)  # empty: no description/action
    assert "panel_flow" in _types(review_graphic_novel(db, p.id, page_id=page.id))


def test_splash_unjustified_check():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id, density_level="light", splash_page=True)
    db.create_gn_panel(page.id, description="x")
    assert "splash_unjustified" in _types(review_graphic_novel(db, p.id, page_id=page.id))


def test_splash_justified_passes():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(
        p.id, density_level="explosive", splash_page=True,
        emotional_beat="climax",
    )
    db.create_gn_panel(page.id, description="hero lands")
    assert "splash_unjustified" not in _types(
        review_graphic_novel(db, p.id, page_id=page.id)
    )


def test_page_turn_effective_empty_reveal():
    db = Database()
    p = _gn(db)
    db.create_gn_page(p.id, reveal_type="cliffhanger")  # setup
    db.create_gn_page(p.id)  # reveal page, empty
    checks = review_graphic_novel(db, p.id)
    assert "page_turn_effective" in _types(checks)


def test_no_page_turns_flagged():
    db = Database()
    p = _gn(db)
    for _ in range(4):
        db.create_gn_page(p.id, density_level="medium")
    checks = review_graphic_novel(db, p.id)
    assert any(
        c.check_type == "page_turn_effective"
        and "not being leveraged" in c.message
        for c in checks
    )


def test_motif_recurrence_check():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    db.create_gn_panel(page.id, visual_motifs=["lonely_motif"])
    checks = review_graphic_novel(db, p.id)
    assert any(
        c.check_type == "motif_recurrence" and "lonely_motif" in c.message
        for c in checks
    )


def test_recurring_motif_not_flagged():
    db = Database()
    p = _gn(db)
    pg1 = db.create_gn_page(p.id)
    pg2 = db.create_gn_page(p.id)
    db.create_gn_panel(pg1.id, visual_motifs=["rain"])
    db.create_gn_panel(pg2.id, visual_motifs=["rain"])
    msgs = [c.message for c in review_graphic_novel(db, p.id)
            if c.check_type == "motif_recurrence"]
    assert not any("rain" in m for m in msgs)


def test_emotional_pacing_monotonous():
    db = Database()
    p = _gn(db)
    for _ in range(5):
        db.create_gn_page(p.id, density_level="medium")  # all same rhythm
    assert "emotional_pacing" in _types(review_graphic_novel(db, p.id))


def test_varied_pacing_not_flagged():
    db = Database()
    p = _gn(db)
    for d in ("silent", "light", "dense", "explosive"):
        db.create_gn_page(p.id, density_level=d)
    assert "emotional_pacing" not in _types(review_graphic_novel(db, p.id))


def test_check_is_typed():
    db = Database()
    p = _gn(db)
    db.create_gn_page(p.id, density_level="light", splash_page=True)
    checks = review_graphic_novel(db, p.id)
    assert all(isinstance(c, GraphicNovelCheck) for c in checks)


def test_empty_project_no_checks():
    db = Database()
    p = _gn(db)
    assert review_graphic_novel(db, p.id) == []


# =========================================================================
# 3. Graphic Novel context (§3)
# =========================================================================

def test_context_includes_rhythm_motifs_density():
    db = Database()
    p = _gn(db)
    pg1 = db.create_gn_page(p.id, density_level="silent")
    pg2 = db.create_gn_page(p.id, density_level="dense")
    db.create_gn_panel(pg2.id, visual_motifs=["rain"])
    db.create_gn_panel(pg1.id, visual_motifs=["rain"])
    ctx = build_graphic_novel_context(db, p.id)
    assert "[Graphic Novel Context]" in ctx
    assert "Page rhythm" in ctx
    assert "Panel density" in ctx
    assert "rain" in ctx  # recurring motif


def test_context_includes_continuity():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id, density_level="medium")
    item = db.create_gn_continuity_item(p.id, "Locket", item_type="prop")
    db.add_gn_continuity_appearance(item.id, page_id=page.id,
                                    continuity_status="changed")
    ctx = build_graphic_novel_context(db, p.id)
    assert "Continuity" in ctx
    assert "Locket" in ctx


def test_context_empty_project():
    db = Database()
    p = _gn(db)
    assert build_graphic_novel_context(db, p.id) == ""


# =========================================================================
# 4. Assistant sees GN feedback (§4)
# =========================================================================

def test_assistant_context_visual_for_gn():
    from logosforge.ui.assistant_view import AssistantPanel
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id, density_level="dense")
    db.create_gn_panel(page.id, visual_motifs=["rain"])
    db.create_scene(p.id, "PAGE ONE", content="x")

    panel = AssistantPanel(db, p.id)
    structural = panel._build_context()[8]
    # GN context block + the engine's visual priorities reach the prompt.
    assert "[Graphic Novel Context]" in structural
    assert "panel rhythm" in structural  # engine priority in format block


def test_assistant_context_not_visual_for_novel():
    from logosforge.ui.assistant_view import AssistantPanel
    db = Database()
    p = db.create_project("Novel")
    db.create_scene(p.id, "Chapter 1", content="x")
    panel = AssistantPanel(db, p.id)
    structural = panel._build_context()[8]
    assert "[Graphic Novel Context]" not in structural
