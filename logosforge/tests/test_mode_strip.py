"""Tests for Adaptive AI UX — ModeStrip widget and integration."""

from logosforge.adaptive_mode import AIMode, ModeResult, StoryStage, HealthState
from logosforge.db import Database
from logosforge.ui import theme
from logosforge.ui.mode_strip import ModeStrip, _MODE_HINTS, _MODE_COLORS


def _make_project():
    db = Database()
    proj = db.create_project("StripTest")
    return db, proj


# -- ModeStrip basic ----------------------------------------------------------

def test_strip_construction():
    db, proj = _make_project()
    strip = ModeStrip(db, proj.id)
    assert strip.get_mode_result() is not None


def test_strip_default_mode_early():
    db, proj = _make_project()
    c = db.create_character(proj.id, "A")
    for i in range(3):
        db.create_scene(proj.id, f"S{i}", character_ids=[c.id])
    strip = ModeStrip(db, proj.id)
    assert strip.get_effective_mode() == AIMode.STRUCTURE


def test_strip_no_override_by_default():
    db, proj = _make_project()
    strip = ModeStrip(db, proj.id)
    assert strip.is_overridden() is False


# -- Override -----------------------------------------------------------------

def test_strip_override_mode():
    db, proj = _make_project()
    strip = ModeStrip(db, proj.id)
    strip._set_override(AIMode.REFINEMENT)
    assert strip.get_effective_mode() == AIMode.REFINEMENT
    assert strip.is_overridden() is True


def test_strip_reset_override():
    db, proj = _make_project()
    strip = ModeStrip(db, proj.id)
    strip._set_override(AIMode.BALANCE)
    assert strip.get_effective_mode() == AIMode.BALANCE
    strip._set_auto()
    assert strip.is_overridden() is False


def test_strip_override_callback():
    db, proj = _make_project()
    calls = []
    strip = ModeStrip(db, proj.id, on_mode_changed=lambda m: calls.append(m))
    strip._set_override(AIMode.BALANCE)
    assert calls == [AIMode.BALANCE]


def test_strip_auto_callback():
    db, proj = _make_project()
    calls = []
    strip = ModeStrip(db, proj.id, on_mode_changed=lambda m: calls.append(m))
    strip._set_override(AIMode.REFINEMENT)
    strip._set_auto()
    assert calls[-1] is None


# -- Refresh ------------------------------------------------------------------

def test_strip_refresh_updates():
    db, proj = _make_project()
    strip = ModeStrip(db, proj.id)
    # Initially early/structure
    assert strip.get_effective_mode() == AIMode.STRUCTURE
    # Add enough data to shift
    c1 = db.create_character(proj.id, "A")
    c2 = db.create_character(proj.id, "B")
    for i in range(21):
        act = "Act 1" if i < 7 else ("Act 2" if i < 14 else "Act 3")
        pl = "Main" if i % 2 == 0 else "Sub"
        db.create_scene(proj.id, f"S{i}", act=act, plotline=pl,
                        character_ids=[c1.id, c2.id])
    strip.refresh()
    assert strip.get_effective_mode() == AIMode.REFINEMENT


def test_strip_refresh_preserves_override():
    db, proj = _make_project()
    strip = ModeStrip(db, proj.id)
    strip._set_override(AIMode.BALANCE)
    strip.refresh()
    assert strip.get_effective_mode() == AIMode.BALANCE
    assert strip.is_overridden() is True


# -- Mode hints ---------------------------------------------------------------

def test_mode_hints_exist():
    assert AIMode.STRUCTURE in _MODE_HINTS
    assert AIMode.BALANCE in _MODE_HINTS
    assert AIMode.REFINEMENT in _MODE_HINTS


def test_mode_colors_exist():
    assert AIMode.STRUCTURE in _MODE_COLORS
    assert AIMode.BALANCE in _MODE_COLORS
    assert AIMode.REFINEMENT in _MODE_COLORS


# -- Integration with assistant build_messages --------------------------------

def test_mode_context_uses_override():
    from logosforge.adaptive_mode import mode_context_block, _MODE_DESCRIPTIONS
    db, proj = _make_project()
    c = db.create_character(proj.id, "A")
    for i in range(3):
        db.create_scene(proj.id, f"S{i}", character_ids=[c.id])
    strip = ModeStrip(db, proj.id)
    # Auto = Structure for early project
    assert strip.get_effective_mode() == AIMode.STRUCTURE

    # Override to Refinement
    strip._set_override(AIMode.REFINEMENT)
    mode_result = strip.get_mode_result()
    effective = strip.get_effective_mode()
    result = ModeResult(
        mode=effective,
        stage=mode_result.stage,
        health=mode_result.health,
        description=_MODE_DESCRIPTIONS[effective],
    )
    block = mode_context_block(result)
    assert "[AI Mode: Refinement]" in block


# -- Theme styles -------------------------------------------------------------

def test_theme_has_mode_strip():
    ss = theme.build_stylesheet()
    assert "#modeStrip" in ss


def test_theme_has_mode_strip_hint():
    ss = theme.build_stylesheet()
    assert "#modeStripHint" in ss


def test_theme_has_mode_strip_reset():
    ss = theme.build_stylesheet()
    assert "#modeStripReset" in ss
