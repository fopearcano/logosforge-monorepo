"""Step 7 — writing_mode is a reliable project-level source of truth.

Confirms writing_mode loads from the current project, persists, propagates on
project switch (including the long-lived Assistant mode strip), and that export /
Assistant / continuity all see the *current* mode with no stale state.
"""

import pytest

from logosforge.db import Database
from logosforge.writing_modes import (
    get_project_writing_mode_by_id,
    set_project_writing_mode,
)


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    import logosforge.gomckee_bridge as gb
    monkeypatch.setattr(gb, "is_gomckee_enabled", lambda: False, raising=False)
    yield
    settings._instance = None


# ==========================================================================
# Persistence + single source of truth
# ==========================================================================


def test_writing_mode_persists_after_reload():
    db = Database()
    pid = db.create_project("P", narrative_engine="novel").id
    set_project_writing_mode(db, pid, "screenplay")
    # Re-read from the DB (fresh object) — value must persist.
    assert get_project_writing_mode_by_id(db, pid) == "screenplay"


def test_invalid_mode_falls_back_to_novel():
    db = Database()
    pid = db.create_project("P", narrative_engine="novel").id
    stored = set_project_writing_mode(db, pid, "not-a-mode")
    assert stored == "novel"
    assert get_project_writing_mode_by_id(db, pid) == "novel"


def test_outline_and_manuscript_see_same_mode():
    db = Database()
    pid = db.create_project("Script", narrative_engine="screenplay").id
    # Both surfaces resolve through the same single source of truth.
    from logosforge.screenplay_production import _is_screenplay
    assert get_project_writing_mode_by_id(db, pid) == "screenplay"
    assert _is_screenplay(db, pid) is True


# ==========================================================================
# Export sees the current writing_mode
# ==========================================================================


def test_export_payload_uses_current_mode():
    from logosforge.writing_modes import get_project_writing_mode
    db = Database()
    pid = db.create_project("P", narrative_engine="novel").id
    db.create_scene(pid, "S", content="x")
    proj = db.get_project_by_id(pid)
    assert get_project_writing_mode(proj) == "novel"
    set_project_writing_mode(db, pid, "screenplay")
    proj2 = db.get_project_by_id(pid)
    assert get_project_writing_mode(proj2) == "screenplay"


def test_screenplay_gate_off_in_novel():
    from logosforge.screenplay_production import _is_screenplay
    db = Database()
    novel = db.create_project("N", narrative_engine="novel").id
    assert _is_screenplay(db, novel) is False


# ==========================================================================
# Assistant sees current writing_mode (context)
# ==========================================================================


def test_assistant_context_reflects_mode():
    from logosforge.assistant_context_policy import _project_mode_block
    db = Database()
    novel = db.create_project("N", narrative_engine="novel").id
    sp = db.create_project("S", narrative_engine="screenplay").id
    assert "Novel" in _project_mode_block(db, novel)
    assert "Screenplay" in _project_mode_block(db, sp)


def test_no_screenplay_only_warnings_in_novel_mode():
    from logosforge.continuity import build_continuity_report
    from logosforge.continuity import models as M
    db = Database()
    novel = db.create_project("N", narrative_engine="novel").id
    db.create_scene(novel, "S", content="Action without a slugline.")
    rep = build_continuity_report(db, novel)
    assert not any(i.issue_type == M.IT_PRODUCTION_RISK for i in rep.issues)


# ==========================================================================
# Project switch updates writing_mode everywhere (UI)
# ==========================================================================


def test_project_switch_updates_section_view_mode():
    from logosforge.ui.main_window import MainWindow
    db = Database()
    novel = db.create_project("Novel", narrative_engine="novel").id
    sp = db.create_project("Script", narrative_engine="screenplay").id
    from logosforge.ui.plan_view import PlanView
    win = MainWindow(db, novel)
    win.sidebar_buttons["Outline"].click()
    # Outline is the single structural section (PlanView) for all modes; its
    # engine reflects the active project.
    assert isinstance(win.content_area, PlanView)
    assert win.content_area._engine == "novel"
    win._switch_project(sp)
    win.sidebar_buttons["Outline"].click()
    assert isinstance(win.content_area, PlanView)
    assert win.content_area._engine == "screenplay"


def test_project_switch_repoints_assistant_mode_strip():
    from logosforge.ui.main_window import MainWindow
    db = Database()
    a = db.create_project("A", narrative_engine="novel").id
    b = db.create_project("B", narrative_engine="screenplay").id
    win = MainWindow(db, a)
    strip = win._assistant_panel._mode_strip
    assert strip._project_id == a
    # simulate a manual mode override on project A
    from logosforge.ui.mode_strip import AIMode
    strip._override = AIMode.BALANCE
    win._switch_project(b)
    # mode strip must re-point at B and drop the stale override
    assert strip._project_id == b
    assert strip._override is None


def test_mode_strip_set_project_resets_state():
    from logosforge.ui.mode_strip import AIMode, ModeStrip
    db = Database()
    a = db.create_project("A", narrative_engine="novel").id
    b = db.create_project("B", narrative_engine="screenplay").id
    strip = ModeStrip(db, a)
    strip._override = AIMode.STRUCTURE
    strip.set_project(b)
    assert strip._project_id == b
    assert strip._override is None
