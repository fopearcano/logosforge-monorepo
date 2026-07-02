"""Tests for the startup landing section.

The app must open on the Projects section — not Dashboard — and the
sidebar highlight must reflect that. Dashboard remains reachable when
the user selects it.
"""

import pytest

from logosforge.db import Database
from logosforge.ui.dashboard_view import DashboardView
from logosforge.ui.main_window import MainWindow
from logosforge.ui.projects_view import ProjectsView


def _setup():
    db = Database()
    proj = db.create_project("Test")
    return db, proj


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch, tmp_path):
    """Use an isolated settings file so tests don't pollute user state."""
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    yield
    settings._instance = None


# ==========================================================================
# 1. Default section is Projects (not Dashboard)
# ==========================================================================

def test_default_current_section_is_projects():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    assert win._current_section == "Projects"


# ==========================================================================
# 2. show_initial_section lands on Projects
# ==========================================================================

def test_show_initial_section_opens_projects_view():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    win.show_initial_section()
    assert isinstance(win.content_area, ProjectsView)
    assert win._current_section == "Projects"


def test_show_initial_section_highlights_projects_in_sidebar():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    win.show_initial_section()
    assert win.sidebar_buttons["Projects"].isChecked() is True
    assert win.sidebar_buttons["Dashboard"].isChecked() is False


# ==========================================================================
# 3. Dashboard is NOT the default landing
# ==========================================================================

def test_dashboard_not_active_at_startup():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    win.show_initial_section()
    assert not isinstance(win.content_area, DashboardView)


# ==========================================================================
# 4. Dashboard still works when explicitly selected
# ==========================================================================

def test_dashboard_reachable_after_initial_projects():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    win.show_initial_section()
    # User clicks Dashboard.
    win._set_active_section("Dashboard")
    win._show_dashboard()
    assert isinstance(win.content_area, DashboardView)
    assert win.sidebar_buttons["Dashboard"].isChecked() is True
    assert win.sidebar_buttons["Projects"].isChecked() is False


# ==========================================================================
# 5. Session restore still lands on Projects with fresh data
# ==========================================================================

def test_restore_then_initial_lands_on_projects(tmp_path):
    """Even when a session-restore navigated to Dashboard, the final
    startup navigation lands on Projects."""
    from logosforge.export import export_json

    db, proj = _setup()
    db.create_scene(proj.id, "Scene", content="x")
    path = tmp_path / "proj.json"
    path.write_text(export_json(db, proj.id), encoding="utf-8")

    win = MainWindow(db, proj.id)
    # Simulate the app.py startup order: restore session, then land.
    win.load_file_quiet(str(path))
    # load_file_quiet intentionally shows Dashboard mid-restore.
    assert isinstance(win.content_area, DashboardView)

    win.show_initial_section()
    # Final landing is Projects, with a freshly built view.
    assert isinstance(win.content_area, ProjectsView)
    assert win._current_section == "Projects"
    assert win.sidebar_buttons["Projects"].isChecked() is True


# ==========================================================================
# 6. Explicit open still goes to Dashboard (not a startup concern)
# ==========================================================================

def test_explicit_open_file_still_shows_dashboard(tmp_path):
    from logosforge.export import export_json

    db, proj = _setup()
    db.create_scene(proj.id, "Scene", content="x")
    path = tmp_path / "proj.json"
    path.write_text(export_json(db, proj.id), encoding="utf-8")

    win = MainWindow(db, proj.id)
    win.show_initial_section()
    # User explicitly opens a project file.
    win._open_file(str(path))
    assert isinstance(win.content_area, DashboardView)
