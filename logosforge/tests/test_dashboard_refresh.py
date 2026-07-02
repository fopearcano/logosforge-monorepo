"""Tests for Dashboard recompute on project load / change.

The Dashboard must recompute purely from the active project. Switching
A -> B (or any data-mutation event) must leave no metric from the old
project behind.
"""

import pytest
from PySide6.QtWidgets import QLabel

from logosforge.db import Database
from logosforge.project_events import (
    emit_project_created,
    emit_project_data_changed,
    emit_project_loaded,
    emit_scene_changed,
    get_event_bus,
)
from logosforge.ui.dashboard_view import DashboardView
from logosforge.ui.main_window import MainWindow


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    yield
    settings._instance = None


def _label_texts(view) -> str:
    """Concatenate every QLabel's text in the view for easy assertions."""
    return " | ".join(lbl.text() for lbl in view.findChildren(QLabel))


def _project_with_scenes(db, title, n):
    proj = db.create_project(title)
    for i in range(n):
        db.create_scene(proj.id, f"{title}-Scene{i + 1}", content="word " * 10)
    return proj


# ==========================================================================
# 1. set_project re-points and clears old state
# ==========================================================================

def test_set_project_repoints_dashboard():
    db = Database()
    a = _project_with_scenes(db, "Alpha", 2)
    b = _project_with_scenes(db, "Beta", 1)

    dash = DashboardView(db, a.id)
    assert dash._project_id == a.id

    dash.set_project(b.id)
    assert dash._project_id == b.id
    text = _label_texts(dash)
    assert "Beta" in text
    assert "Alpha" not in text


def test_set_project_leaves_no_old_metrics():
    db = Database()
    # Alpha has 5 scenes; Beta has 1. After switching, the scene count
    # must reflect Beta, never Alpha's 5.
    a = _project_with_scenes(db, "Alpha", 5)
    b = _project_with_scenes(db, "Beta", 1)

    dash = DashboardView(db, a.id)
    dash.set_project(b.id)

    # Beta's single scene → "Scenes" stat value should be "1", not "5".
    values = [lbl.text() for lbl in dash.findChildren(QLabel)]
    assert "5" not in values  # Alpha's scene count must not survive
    assert "1" in values


# ==========================================================================
# 2. Lifecycle signals trigger recompute
# ==========================================================================

def test_project_loaded_signal_repoints_dashboard():
    db = Database()
    a = _project_with_scenes(db, "Alpha", 2)
    b = _project_with_scenes(db, "Beta", 1)

    dash = DashboardView(db, a.id)
    emit_project_loaded(b.id)

    assert dash._project_id == b.id
    text = _label_texts(dash)
    assert "Beta" in text
    assert "Alpha" not in text


def test_project_created_signal_repoints_dashboard():
    db = Database()
    a = _project_with_scenes(db, "Alpha", 2)
    b = db.create_project("Gamma")

    dash = DashboardView(db, a.id)
    emit_project_created(b.id)

    assert dash._project_id == b.id
    text = _label_texts(dash)
    assert "Gamma" in text
    assert "Alpha" not in text


# ==========================================================================
# 3. Data-mutation signals recompute for the current project
# ==========================================================================

def test_project_data_changed_recomputes():
    db = Database()
    proj = _project_with_scenes(db, "Story", 1)
    dash = DashboardView(db, proj.id)

    # Add a scene directly, then announce the change.
    db.create_scene(proj.id, "Story-Scene2", content="x")
    emit_project_data_changed()

    # Scene count should now reflect 2 scenes.
    values = [lbl.text() for lbl in dash.findChildren(QLabel)]
    assert "2" in values


def test_scene_changed_recomputes():
    db = Database()
    proj = _project_with_scenes(db, "Story", 1)
    dash = DashboardView(db, proj.id)

    s = db.create_scene(proj.id, "Story-Scene2", content="y")
    emit_scene_changed(s.id)

    values = [lbl.text() for lbl in dash.findChildren(QLabel)]
    assert "2" in values


def test_dashboard_recomputes_word_count_after_change():
    db = Database()
    proj = db.create_project("WC")
    db.create_scene(proj.id, "S1", content="one two three")
    dash = DashboardView(db, proj.id)
    before = _label_texts(dash)
    assert "3" in [lbl.text() for lbl in dash.findChildren(QLabel)]

    db.create_scene(proj.id, "S2", content="four five six seven")
    emit_project_data_changed()
    # Total words now 7.
    values = [lbl.text() for lbl in dash.findChildren(QLabel)]
    assert "7" in values


# ==========================================================================
# 4. End-to-end via MainWindow: Project A -> Project B
# ==========================================================================

def test_main_window_switch_shows_b_only():
    db = Database()
    a = _project_with_scenes(db, "Alpha", 3)
    b = _project_with_scenes(db, "Beta", 1)

    win = MainWindow(db, a.id)
    win._set_active_section("Dashboard")
    win._show_dashboard()
    assert isinstance(win.content_area, DashboardView)
    text_a = _label_texts(win.content_area)
    assert "Alpha" in text_a

    # Switch to B.
    win._switch_project(b.id)
    dash_b = win.content_area
    assert isinstance(dash_b, DashboardView)
    assert dash_b._project_id == b.id
    text_b = _label_texts(dash_b)
    assert "Beta" in text_b
    assert "Alpha" not in text_b
    win.close()


def test_main_window_switch_no_old_word_count():
    db = Database()
    # Alpha: 4 scenes * 10 words = 40 words. Beta: 1 scene * 2 words.
    a = db.create_project("Alpha")
    for i in range(4):
        a_scene = db.create_scene(a.id, f"A{i}", content="word " * 10)
    b = db.create_project("Beta")
    db.create_scene(b.id, "B1", content="two words")

    win = MainWindow(db, a.id)
    win._set_active_section("Dashboard")
    win._show_dashboard()

    win._switch_project(b.id)
    values = [lbl.text() for lbl in win.content_area.findChildren(QLabel)]
    # Alpha's 40-word total must not appear; Beta has 2 words.
    assert "40" not in values
    assert "2" in values
    win.close()


def test_load_file_then_dashboard_shows_loaded_project(tmp_path):
    from logosforge.export import export_json

    db = Database()
    a = _project_with_scenes(db, "Alpha", 2)
    b = _project_with_scenes(db, "Beta", 1)
    path = tmp_path / "beta.json"
    path.write_text(export_json(db, b.id), encoding="utf-8")

    win = MainWindow(db, a.id)
    win._set_active_section("Dashboard")
    win._show_dashboard()

    # Loading the Beta file lands on its Dashboard with Beta's data.
    win._open_file(str(path))
    assert isinstance(win.content_area, DashboardView)
    text = _label_texts(win.content_area)
    assert "Beta" in text
    assert "Alpha" not in text
    win.close()


# ==========================================================================
# 5. Dead-dashboard guard
# ==========================================================================

def test_signal_after_replace_does_not_crash():
    """A dashboard that has been replaced must ignore late signals."""
    db = Database()
    a = _project_with_scenes(db, "Alpha", 1)
    b = _project_with_scenes(db, "Beta", 1)

    win = MainWindow(db, a.id)
    win._set_active_section("Dashboard")
    win._show_dashboard()
    old_dash = win.content_area

    # Replace the dashboard with a different section.
    win._set_active_section("Projects")
    win._show_projects()

    # Emitting must not raise even though old_dash is being torn down.
    emit_project_loaded(b.id)
    emit_project_data_changed()
    win.close()
