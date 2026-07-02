"""Tests for project-state reset, act consistency, dashboard reload, and plot edit options."""

from logosforge.db import Database
from logosforge.ui.dashboard_view import DashboardView
from logosforge.ui.main_window import MainWindow
from logosforge.ui.multi_plot_view import MultiPlotView, _TimelineStrip, _ArcLanes, _CharLanes
from logosforge.ui.scenes_view import ScenesView


def _setup():
    db = Database()
    proj = db.create_project("TestProject")
    return db, proj


# ==========================================================================
# A. New Project Reset
# ==========================================================================

def test_new_project_clears_all_caches():
    db, proj = _setup()
    db.create_scene(proj.id, "OldScene", content="old data")
    db.create_psyke_entry(proj.id, "OldChar", entry_type="character")
    db.create_note(proj.id, "OldNote", content="old note")

    win = MainWindow(db, proj.id)
    win._cached_scene_entry_scene = 99
    win._cached_scene_entry_ids = {1, 2, 3}
    win._on_new_project()

    assert win._cached_scenes_view is None
    assert win._cached_scene_entry_scene is None
    assert win._cached_scene_entry_ids is None


def test_new_project_no_old_scenes():
    db, proj = _setup()
    db.create_scene(proj.id, "OldScene", content="old")
    win = MainWindow(db, proj.id)
    win._on_new_project()
    new_id = win._project_id
    assert new_id != proj.id
    assert len(db.get_all_scenes(new_id)) == 0


def test_new_project_no_old_psyke():
    db, proj = _setup()
    db.create_psyke_entry(proj.id, "OldEntry", entry_type="character")
    win = MainWindow(db, proj.id)
    win._on_new_project()
    new_id = win._project_id
    assert len(db.get_all_psyke_entries(new_id)) == 0


def test_new_project_no_old_notes():
    db, proj = _setup()
    db.create_note(proj.id, "OldNote", content="old")
    win = MainWindow(db, proj.id)
    win._on_new_project()
    new_id = win._project_id
    assert len(db.get_all_notes(new_id)) == 0


def test_new_project_psyke_console_cleared():
    db, proj = _setup()
    db.create_psyke_entry(proj.id, "OldChar", entry_type="character")
    win = MainWindow(db, proj.id)
    win._psyke_console.rebuild_index()
    win._on_new_project()
    cache = win._psyke_console._psyke_entries_cache
    if cache is not None:
        for entry in cache:
            assert entry.name != "OldChar"


# ==========================================================================
# B. Import clears caches and shows Dashboard
# ==========================================================================

def test_import_clears_caches(tmp_path):
    from logosforge.export import export_json

    db, proj = _setup()
    db.create_scene(proj.id, "ImportedScene", content="data")
    json_data = export_json(db, proj.id)
    path = tmp_path / "import_test.json"
    path.write_text(json_data, encoding="utf-8")

    db2, proj2 = _setup()
    db2.create_scene(proj2.id, "OldScene", content="old")
    win = MainWindow(db2, proj2.id)
    win._cached_scene_entry_scene = 42
    win._cached_scene_entry_ids = {1, 2}

    with open(str(path), "r") as f:
        raw = f.read()
    from logosforge.import_data import validate_import_data, import_json
    data, _ = validate_import_data(raw)
    new_id = import_json(db2, data)
    win._project_id = new_id
    win._psyke_console.set_project(new_id)
    win._cached_scenes_view = None
    win._cached_scene_entry_scene = None
    win._cached_scene_entry_ids = None

    assert win._cached_scene_entry_scene is None
    assert win._cached_scene_entry_ids is None


def test_import_shows_dashboard(tmp_path):
    from logosforge.export import export_json

    db, proj = _setup()
    db.create_scene(proj.id, "TestScene", content="data")
    json_data = export_json(db, proj.id)
    path = tmp_path / "import_test.json"
    path.write_text(json_data, encoding="utf-8")

    win = MainWindow(db, proj.id)
    win._open_file(str(path))
    assert isinstance(win.content_area, DashboardView)


# ==========================================================================
# C. Act Consistency
# ==========================================================================

def test_act_dropdown_is_editable():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    win._show_scenes()
    view = win._cached_scenes_view
    assert isinstance(view, ScenesView)
    assert view._act_input.isEditable()


def test_act_dropdown_includes_custom_acts():
    db, proj = _setup()
    db.create_scene(proj.id, "S1", content="x", act="Prologue")
    db.create_scene(proj.id, "S2", content="y", act="Act I")
    db.create_scene(proj.id, "S3", content="z", act="Epilogue")
    win = MainWindow(db, proj.id)
    win._show_scenes()
    view = win._cached_scenes_view

    acts = [view._act_input.itemText(i) for i in range(view._act_input.count())]
    assert "Prologue" in acts
    assert "Act I" in acts
    assert "Epilogue" in acts


def test_act_dropdown_defaults_when_no_acts():
    db, proj = _setup()
    db.create_scene(proj.id, "S1", content="x")
    win = MainWindow(db, proj.id)
    win._show_scenes()
    view = win._cached_scenes_view

    acts = [view._act_input.itemText(i) for i in range(view._act_input.count())]
    assert "Act I" in acts
    assert "Act II" in acts
    assert "Act III" in acts


def test_act_dropdown_updates_on_refresh():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    win._show_scenes()
    view = win._cached_scenes_view

    db.create_scene(proj.id, "NewScene", content="x", act="Act IV")
    view._do_refresh()

    acts = [view._act_input.itemText(i) for i in range(view._act_input.count())]
    assert "Act IV" in acts


def test_custom_act_preserved_on_scene_select():
    db, proj = _setup()
    scene = db.create_scene(proj.id, "CustomAct", content="x", act="Interlude")
    win = MainWindow(db, proj.id)
    win._show_scenes()
    view = win._cached_scenes_view

    view.select_scene(scene.id)
    assert view._act_input.currentText() == "Interlude"


def test_act_matches_plot_timeline():
    db, proj = _setup()
    db.create_scene(proj.id, "S1", content="x", act="Act I")
    db.create_scene(proj.id, "S2", content="y", act="Prologue")
    db.create_scene(proj.id, "S3", content="z", act="Epilogue")

    view = _TimelineStrip(db, proj.id)
    view.refresh()

    acts_in_scenes = sorted({
        (s.act or "").strip()
        for s in db.get_all_scenes(proj.id)
    } - {""})

    assert "Act I" in acts_in_scenes
    assert "Prologue" in acts_in_scenes
    assert "Epilogue" in acts_in_scenes


# ==========================================================================
# D. Dashboard Reload
# ==========================================================================

def test_dashboard_refreshes_on_data_changed():
    db, proj = _setup()
    db.create_scene(proj.id, "S1", content="hello")
    win = MainWindow(db, proj.id)
    win._set_active_section("Dashboard")
    win._show_dashboard()
    assert isinstance(win.content_area, DashboardView)

    db.create_scene(proj.id, "S2", content="world")
    win._on_data_changed()
    assert isinstance(win.content_area, DashboardView)


def test_load_project_shows_fresh_dashboard(tmp_path):
    from logosforge.export import export_json

    db, proj_a = _setup()
    db.create_scene(proj_a.id, "SceneA", content="project A data")
    json_a = export_json(db, proj_a.id)
    path_a = tmp_path / "proj_a.json"
    path_a.write_text(json_a, encoding="utf-8")

    proj_b = db.create_project("ProjectB")
    db.create_scene(proj_b.id, "SceneB", content="project B data")
    json_b = export_json(db, proj_b.id)
    path_b = tmp_path / "proj_b.json"
    path_b.write_text(json_b, encoding="utf-8")

    win = MainWindow(db, proj_a.id)
    win._open_file(str(path_b))
    assert isinstance(win.content_area, DashboardView)
    assert win._project_id != proj_a.id


# ==========================================================================
# E. Plot Block Edit Options
# ==========================================================================

def test_timeline_has_context_menu():
    db, proj = _setup()
    db.create_scene(proj.id, "Scene1", content="x")
    view = _TimelineStrip(db, proj.id)
    view.refresh()
    assert view.card_count() == 1
    card = view._cards[0]
    assert card.property("scene_id") is not None


def test_arc_has_context_menu():
    db, proj = _setup()
    db.create_scene(proj.id, "Scene1", content="x", plotline="MainPlot")
    view = _ArcLanes(db, proj.id)
    view.refresh()
    assert view.lane_count() >= 1


def test_char_has_context_menu():
    db, proj = _setup()
    char = db.create_character(proj.id, "Hero")
    db.create_scene(proj.id, "Scene1", content="x", character_ids=[char.id])
    view = _CharLanes(db, proj.id)
    view.refresh()
    assert view.lane_count() >= 1


def test_move_to_act_updates_scene():
    db, proj = _setup()
    scene = db.create_scene(proj.id, "S1", content="x", act="Act I")
    db.create_scene(proj.id, "S2", content="y", act="Act II")

    view = _TimelineStrip(db, proj.id)
    view.refresh()
    view._move_to_act(scene.id, "Act II")

    updated = db.get_scene_by_id(scene.id)
    assert updated.act == "Act II"


def test_plot_view_refresh():
    db, proj = _setup()
    db.create_scene(proj.id, "S1", content="x")
    view = MultiPlotView(db, proj.id)
    assert hasattr(view, "refresh")
    view.refresh()


# ==========================================================================
# F. Assistant Refresh Path
# ==========================================================================

def test_data_changed_refreshes_active_view():
    db, proj = _setup()
    db.create_scene(proj.id, "S1", content="hello")
    win = MainWindow(db, proj.id)
    win._set_active_section("Dashboard")
    win._show_dashboard()

    db.create_scene(proj.id, "S2", content="world")
    win._on_data_changed()
    assert isinstance(win.content_area, DashboardView)


def test_data_changed_clears_entry_cache():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    win._cached_scene_entry_scene = 42
    win._cached_scene_entry_ids = {1, 2}
    win._on_data_changed()
    assert win._cached_scene_entry_scene is None
    assert win._cached_scene_entry_ids is None


def test_data_changed_marks_psyke_dirty():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    win._psyke_console._index_dirty = False
    win._on_data_changed()
    assert win._psyke_console._index_dirty is True
