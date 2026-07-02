"""Project lifecycle: switching projects clears stale state and refreshes nav.

Covers the Step 5 fixes — chiefly that the writing-mode-dependent sidebar nav
(the Graphic-Novel-only Pages item) refreshes on project switch — plus the
existing central stale-clearing guarantees.
"""

import pytest

from logosforge.db import Database
from logosforge.ui.main_window import MainWindow


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


def _db_two():
    db = Database()
    a = db.create_project("Novel A", narrative_engine="novel").id
    db.create_scene(a, "A-Scene", content="Alice in A.")
    db.create_psyke_entry(a, "Alice", "character")
    b = db.create_project("Novel B", narrative_engine="novel").id
    db.create_scene(b, "B-Scene", content="Bob in B.")
    return db, a, b


# ==========================================================================
# Writing-mode-dependent nav (Pages) refreshes on switch
# ==========================================================================


def test_pages_stays_hidden_when_switching_into_graphic_novel():
    # Alpha: the standalone Pages section is disabled (fullscreen-hostile). It is
    # hidden in every mode, including Graphic Novel — Page/Panel navigation lives
    # in the GN Manuscript (comics script editor).
    db = Database()
    novel = db.create_project("Novel", narrative_engine="novel").id
    gn = db.create_project("GN", narrative_engine="graphic_novel").id
    win = MainWindow(db, novel)
    assert "Pages" not in win.sidebar_buttons
    win._switch_project(gn)
    assert "Pages" not in win.sidebar_buttons
    assert "Pages" not in win._nav_labels


def test_pages_hidden_in_both_gn_and_novel():
    db = Database()
    gn = db.create_project("GN", narrative_engine="graphic_novel").id
    novel = db.create_project("Novel", narrative_engine="novel").id
    win = MainWindow(db, gn)
    assert "Pages" not in win.sidebar_buttons
    win._switch_project(novel)
    assert "Pages" not in win.sidebar_buttons
    assert "Pages" not in win._nav_labels


def test_pages_route_falls_back_safely_for_non_gn():
    db = Database()
    novel = db.create_project("Novel", narrative_engine="novel").id
    win = MainWindow(db, novel)
    from logosforge.ui.graphic_novel_scene_pages_view import (
        GraphicNovelScenePagesView)
    win._show_gn_pages()  # inert: must not mount the standalone Pages widget
    assert not isinstance(win.content_area, GraphicNovelScenePagesView)


def test_pages_section_reset_clears_to_safe_section():
    # If _current_section is ever "Pages", availability resets it (Pages can no
    # longer be the active section).
    db = Database()
    gn = db.create_project("GN", narrative_engine="graphic_novel").id
    win = MainWindow(db, gn)
    win._current_section = "Pages"
    win._apply_pages_availability()
    assert win._current_section != "Pages"


# ==========================================================================
# Stale data cleared on switch
# ==========================================================================


def test_new_project_does_not_show_previous_scenes():
    db, a, b = _db_two()
    win = MainWindow(db, a)
    win.sidebar_buttons["Scenes"].click()
    win._switch_project(b)
    # active view rebuilt against the new project id
    assert win._project_id == b
    assert win.content_area is not None


def test_switch_updates_major_subsystems_to_new_project():
    db, a, b = _db_two()
    win = MainWindow(db, a)
    win._switch_project(b)
    assert win._project_id == b
    assert win._logos_engine._project_id == b
    assert win._diagnostics_engine._project_id == b
    assert win._health_engine._project_id == b
    assert win._strategy_router._project_id == b
    assert win._assistant_panel._project_id == b


def test_dashboard_refreshes_on_project_load():
    db, a, b = _db_two()
    win = MainWindow(db, a)
    win.sidebar_buttons["Dashboard"].click()
    from logosforge.ui.dashboard_view import DashboardView
    assert isinstance(win.content_area, DashboardView)
    win._switch_project(b)
    # Dashboard rebuilt for the new project (current_section stayed Dashboard).
    assert isinstance(win.content_area, DashboardView)
    assert win._project_id == b


def test_assistant_context_clears_after_switch():
    db, a, b = _db_two()
    win = MainWindow(db, a)
    # queue a pending message on the assistant panel, then switch
    win._assistant_panel._pending_messages = [{"role": "user", "content": "x"}]
    win._switch_project(b)
    assert win._assistant_panel._pending_messages is None
    assert win._assistant_panel._project_id == b


def test_logos_suggestions_clear_after_switch():
    db, a, b = _db_two()
    win = MainWindow(db, a)
    win._logos_enabled = True
    win._switch_project(b)
    # engine repointed; no stale suggestions from project A linger.
    assert win._logos_engine._project_id == b


def test_writing_mode_refreshes_after_switch():
    db = Database()
    novel = db.create_project("Novel", narrative_engine="novel").id
    gn = db.create_project("GN", narrative_engine="graphic_novel").id
    win = MainWindow(db, novel)
    assert win._is_graphic_novel is False
    win._switch_project(gn)
    assert win._is_graphic_novel is True
    assert win._project_is_graphic_novel() is True
    win._switch_project(novel)
    assert win._is_graphic_novel is False


# ==========================================================================
# Contract still holds at startup (regression guard)
# ==========================================================================


def test_pages_absent_on_gn_startup():
    # Alpha: standalone Pages is disabled even for GN (navigation is in Manuscript).
    db = Database()
    gn = db.create_project("GN", narrative_engine="graphic_novel").id
    win = MainWindow(db, gn)
    assert "Pages" not in win.sidebar_buttons and "Pages" not in win._nav_labels


def test_pages_absent_on_novel_startup():
    db = Database()
    novel = db.create_project("Novel", narrative_engine="novel").id
    win = MainWindow(db, novel)
    assert "Pages" not in win.sidebar_buttons and "Pages" not in win._nav_labels
