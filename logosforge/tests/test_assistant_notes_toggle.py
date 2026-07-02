"""Tests for the Assistant 'Include Notes' context toggle.

Relevance filtering of notes is covered in test_notes_context.py. These
tests cover the new checkbox: default ON, persistence, and that notes
only influence the Assistant context when the toggle is enabled.
"""

import pytest

from logosforge.db import Database
from logosforge.ui.assistant_view import AssistantPanel


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    yield
    settings._instance = None


def _panel_with_note(pinned=True):
    db = Database()
    proj = db.create_project("P")
    note = db.create_note(proj.id, "SecretClue", content="The locket is fake.")
    if pinned:
        db.update_note(note.id, title="SecretClue",
                       content="The locket is fake.", tags="", pinned=True)
    panel = AssistantPanel(db, proj.id)
    return db, proj, note, panel


# The notes_ctx is index 5 in the _build_context tuple.
_NOTES_IDX = 5


# =========================================================================
# 1. Checkbox presence + default
# =========================================================================

def test_include_notes_checkbox_exists():
    db = Database()
    proj = db.create_project("P")
    panel = AssistantPanel(db, proj.id)
    assert hasattr(panel, "_notes_check")
    assert panel._notes_check.text() == "Include Notes"


def test_include_notes_default_on():
    """Default ON preserves the prior always-included behavior."""
    db = Database()
    proj = db.create_project("P")
    panel = AssistantPanel(db, proj.id)
    assert panel._notes_check.isChecked() is True


# =========================================================================
# 2. Gating: notes only included when enabled
# =========================================================================

def test_notes_included_when_enabled():
    db, proj, note, panel = _panel_with_note(pinned=True)
    panel._notes_check.setChecked(True)
    ctx = panel._build_context()
    notes_ctx = ctx[_NOTES_IDX]
    assert "SecretClue" in notes_ctx


def test_notes_excluded_when_disabled():
    db, proj, note, panel = _panel_with_note(pinned=True)
    panel._notes_check.setChecked(False)
    ctx = panel._build_context()
    notes_ctx = ctx[_NOTES_IDX]
    assert notes_ctx == ""


def test_toggle_off_then_on_round_trip():
    db, proj, note, panel = _panel_with_note(pinned=True)
    panel._notes_check.setChecked(False)
    assert panel._build_context()[_NOTES_IDX] == ""
    panel._notes_check.setChecked(True)
    assert "SecretClue" in panel._build_context()[_NOTES_IDX]


# =========================================================================
# 3. Persistence
# =========================================================================

def test_toggle_persists_immediately():
    from logosforge.settings import get_manager
    db = Database()
    proj = db.create_project("P")
    panel = AssistantPanel(db, proj.id)
    panel._notes_check.setChecked(False)
    assert get_manager().get("assistant_include_notes") is False
    panel._notes_check.setChecked(True)
    assert get_manager().get("assistant_include_notes") is True


def test_preference_restored_on_new_panel():
    from logosforge.settings import get_manager
    db = Database()
    proj = db.create_project("P")
    get_manager().set("assistant_include_notes", False)
    panel = AssistantPanel(db, proj.id)
    assert panel._notes_check.isChecked() is False


def test_preference_survives_restart():
    import logosforge.settings as settings
    db = Database()
    proj = db.create_project("P")
    panel = AssistantPanel(db, proj.id)
    panel._notes_check.setChecked(False)
    # Simulate restart.
    settings._instance = None
    panel2 = AssistantPanel(db, proj.id)
    assert panel2._notes_check.isChecked() is False


def test_save_settings_includes_notes_flag():
    from logosforge.settings import get_manager
    db = Database()
    proj = db.create_project("P")
    panel = AssistantPanel(db, proj.id)
    panel._notes_check.setChecked(False)
    panel.save_settings()
    assert get_manager().get("assistant_include_notes") is False


# =========================================================================
# 4. Freshness — context reflects note changes (no stale cache)
# =========================================================================

def test_context_reflects_new_notes_without_invalidation():
    db, proj, note, panel = _panel_with_note(pinned=True)
    panel._notes_check.setChecked(True)
    first = panel._build_context()[_NOTES_IDX]
    assert "SecretClue" in first

    # Add another pinned note; rebuilding context picks it up immediately.
    n2 = db.create_note(proj.id, "SecondClue", content="The map is upside down.")
    db.update_note(n2.id, title="SecondClue",
                   content="The map is upside down.", tags="", pinned=True)
    second = panel._build_context()[_NOTES_IDX]
    assert "SecondClue" in second
