"""Integration tests for cross-system coordination audit fixes."""

from logosforge.autosave import AutosaveManager
from logosforge.db import Database
from logosforge.ui.assistant_view import AssistantPanel
from logosforge.ui.characters_view import CharactersView
from logosforge.ui.dashboard_view import DashboardView
from logosforge.ui.graph_view import GraphView
from logosforge.ui.main_window import MainWindow
from logosforge.ui.multi_plot_view import MultiPlotView
from logosforge.ui.notes_view import NotesView
from logosforge.ui.outline_view import OutlineView
from logosforge.ui.places_view import PlacesView
from logosforge.ui.psyke_view import PsykeView
from logosforge.ui.scenes_view import ScenesView
from logosforge.ui.stages_view import StagesView
from logosforge.ui.story_grid_view import StoryGridView
from logosforge.ui.structure_view import StructureView
from logosforge.ui.timeline_view import TimelineView
from logosforge.version_manager import VersionManager


def _setup():
    db = Database()
    proj = db.create_project("TestProject")
    return db, proj


# ==========================================================================
# 1. Project-switch coordination
# ==========================================================================

def test_autosave_set_project():
    db, proj = _setup()
    auto = AutosaveManager(db, proj.id)
    proj2 = db.create_project("Proj2")
    auto.set_project(proj2.id)
    assert auto._project_id == proj2.id
    assert auto._dirty is False


def test_version_manager_set_project():
    db, proj = _setup()
    vm = VersionManager(db, proj.id)
    proj2 = db.create_project("Proj2")
    vm.set_project(proj2.id)
    assert vm._project_id == proj2.id
    assert vm._dirty_since_snapshot is False


def test_switch_project_updates_autosave():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    proj2 = db.create_project("Proj2")
    win._switch_project(proj2.id)
    assert win._autosave._project_id == proj2.id


def test_switch_project_updates_versions():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    proj2 = db.create_project("Proj2")
    win._switch_project(proj2.id)
    assert win._versions._project_id == proj2.id


def test_switch_project_updates_assistant():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    proj2 = db.create_project("Proj2")
    win._switch_project(proj2.id)
    assert win._assistant_panel._project_id == proj2.id


def test_switch_project_updates_commands():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    proj2 = db.create_project("Proj2")
    win._switch_project(proj2.id)
    assert win._system_command_handlers._project_id == proj2.id


def test_new_project_uses_switch():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    win._on_new_project()
    new_id = win._project_id
    assert new_id != proj.id
    assert win._autosave._project_id == new_id
    assert win._versions._project_id == new_id
    assert win._assistant_panel._project_id == new_id
    assert win._system_command_handlers._project_id == new_id


def test_open_file_uses_switch(tmp_path):
    from logosforge.export import export_json
    db, proj = _setup()
    db.create_scene(proj.id, "S1", content="test")
    json_data = export_json(db, proj.id)
    path = tmp_path / "test.json"
    path.write_text(json_data, encoding="utf-8")

    win = MainWindow(db, proj.id)
    win._open_file(str(path))
    new_id = win._project_id
    assert new_id != proj.id
    assert win._autosave._project_id == new_id
    assert win._versions._project_id == new_id
    assert win._assistant_panel._project_id == new_id


def test_import_uses_switch(tmp_path):
    from logosforge.export import export_json
    from logosforge.import_data import validate_import_data, import_json

    db, proj = _setup()
    db.create_scene(proj.id, "S1", content="x")
    json_data = export_json(db, proj.id)
    path = tmp_path / "import.json"
    path.write_text(json_data, encoding="utf-8")

    db2, proj2 = _setup()
    win = MainWindow(db2, proj2.id)

    with open(str(path), "r") as f:
        raw = f.read()
    data, _ = validate_import_data(raw)
    new_id = import_json(db2, data)
    win._switch_project(new_id)

    assert win._autosave._project_id == new_id
    assert win._versions._project_id == new_id
    assert win._assistant_panel._project_id == new_id


def test_load_file_quiet_uses_switch(tmp_path):
    from logosforge.export import export_json
    db, proj = _setup()
    db.create_scene(proj.id, "S1", content="test")
    json_data = export_json(db, proj.id)
    path = tmp_path / "quiet.json"
    path.write_text(json_data, encoding="utf-8")

    win = MainWindow(db, proj.id)
    result = win.load_file_quiet(str(path))
    assert result is True
    new_id = win._project_id
    assert new_id != proj.id
    assert win._autosave._project_id == new_id
    assert win._versions._project_id == new_id
    assert isinstance(win.content_area, DashboardView)


# ==========================================================================
# 2. Story grid drag-drop preserves scene data
# ==========================================================================

def test_grid_drop_preserves_scene_content():
    db, proj = _setup()
    scene = db.create_scene(
        proj.id, "MyScene",
        content="Important content",
        summary="My summary",
        synopsis="My synopsis",
        act="Act I",
    )

    view = StoryGridView(db, proj.id)
    view._group_by = "act"
    view._on_scene_dropped(scene.id, "Act II", 0)

    updated = db.get_scene_by_id(scene.id)
    assert updated.act == "Act II"
    assert updated.content == "Important content"
    assert updated.summary == "My summary"
    assert updated.synopsis == "My synopsis"


def test_grid_drop_chapter_preserves_data():
    db, proj = _setup()
    scene = db.create_scene(
        proj.id, "MyScene",
        content="Keep this",
        act="Act I",
        chapter="Ch1",
    )

    view = StoryGridView(db, proj.id)
    view._group_by = "chapter"
    view._on_scene_dropped(scene.id, "Ch2", 0)

    updated = db.get_scene_by_id(scene.id)
    assert updated.chapter == "Ch2"
    assert updated.content == "Keep this"
    assert updated.act == "Act I"


# ==========================================================================
# 3. Views have refresh() methods
# ==========================================================================

def test_characters_view_has_refresh():
    db, proj = _setup()
    view = CharactersView(db, proj.id)
    assert hasattr(view, "refresh")
    view.refresh()


def test_places_view_has_refresh():
    db, proj = _setup()
    view = PlacesView(db, proj.id)
    assert hasattr(view, "refresh")
    view.refresh()


def test_outline_view_has_refresh():
    db, proj = _setup()
    view = OutlineView(db, proj.id)
    assert hasattr(view, "refresh")
    view.refresh()


def test_timeline_view_has_refresh():
    db, proj = _setup()
    db.create_scene(proj.id, "S1", content="x")
    view = TimelineView(db, proj.id)
    assert hasattr(view, "refresh")
    view.refresh()


def test_structure_view_has_refresh():
    db, proj = _setup()
    view = StructureView(db, proj.id)
    assert hasattr(view, "refresh")
    view.refresh()


def test_graph_view_has_refresh():
    db, proj = _setup()
    view = GraphView(db, proj.id)
    assert hasattr(view, "refresh")
    view.refresh()


# ==========================================================================
# 4. Missing on_data_changed calls
# ==========================================================================

def test_plan_act_summary_notifies():
    db, proj = _setup()
    db.create_scene(proj.id, "S1", content="x", act="Act I")
    notified = []
    from logosforge.ui.plan_view import PlanView
    view = PlanView(db, proj.id, on_data_changed=lambda: notified.append(True))
    view._save_act_summary("Act I", "This is act one.")
    assert len(notified) == 1


def test_plan_chapter_summary_notifies():
    db, proj = _setup()
    db.create_scene(proj.id, "S1", content="x", chapter="Ch1")
    notified = []
    from logosforge.ui.plan_view import PlanView
    view = PlanView(db, proj.id, on_data_changed=lambda: notified.append(True))
    view._save_chapter_summary("Ch1", "Chapter one summary.")
    assert len(notified) == 1


# ==========================================================================
# 5. Act naming consistency
# ==========================================================================

def test_grid_first_scene_uses_roman_numeral():
    db, proj = _setup()
    view = StoryGridView(db, proj.id)
    view._group_by = "act"
    view._create_first_scene()
    scenes = db.get_all_scenes(proj.id)
    assert any(s.act == "Act I" for s in scenes)


# ==========================================================================
# 6. Multi-plot filter refresh
# ==========================================================================

def test_multi_plot_refresh_updates_filters():
    db, proj = _setup()
    db.create_scene(proj.id, "S1", content="x", plotline="PlotA")
    view = MultiPlotView(db, proj.id)

    db.create_scene(proj.id, "S2", content="y", plotline="PlotB")
    view.refresh()

    arcs = [view._arc_filter.itemText(i) for i in range(view._arc_filter.count())]
    assert "PlotB" in arcs


# ==========================================================================
# 7. Create scene visible across views
# ==========================================================================

def test_scene_visible_in_grid_after_create():
    db, proj = _setup()
    db.create_scene(proj.id, "NewScene", content="test", act="Act I")
    grid = StoryGridView(db, proj.id)
    grid.refresh()
    assert grid.total_cards() >= 1


def test_scene_visible_in_timeline_after_create():
    db, proj = _setup()
    db.create_scene(proj.id, "NewScene", content="test")
    from logosforge.ui.multi_plot_view import _TimelineStrip
    ts = _TimelineStrip(db, proj.id)
    ts.refresh()
    assert ts.card_count() >= 1


# ==========================================================================
# 8. PSYKE entry appears in console after create
# ==========================================================================

def test_psyke_entry_searchable_after_create():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    db.create_psyke_entry(proj.id, "Gandalf", entry_type="character")
    win._on_data_changed()
    assert win._psyke_console._index_dirty is True


# ==========================================================================
# 9. Dashboard refreshes after project load
# ==========================================================================

def test_dashboard_after_new_project():
    db, proj = _setup()
    db.create_scene(proj.id, "OldScene", content="old")
    win = MainWindow(db, proj.id)
    win._on_new_project()
    assert isinstance(win.content_area, DashboardView)


# ==========================================================================
# 10. Autosave triggers after data changes
# ==========================================================================

def test_data_changed_marks_autosave_dirty():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    win._autosave._dirty = False
    win._on_data_changed()
    assert win._autosave._dirty is True


def test_data_changed_marks_versions_dirty():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    win._versions._dirty_since_snapshot = False
    win._on_data_changed()
    assert win._versions._dirty_since_snapshot is True


# ==========================================================================
# 11. Stages write paths trigger on_data_changed
# ==========================================================================

def test_stages_new_stage_notifies():
    db, proj = _setup()
    notified = []
    view = StagesView(db, proj.id, on_data_changed=lambda: notified.append(True))
    stage = db.create_stage(proj.id, "TestStage", scope_type="project")
    view._reload_tree()
    view._select_stage(stage.id)
    old_count = len(notified)
    view._on_status_change()
    assert len(notified) > old_count


# ==========================================================================
# 12. Open scene in editor passes on_open_psyke_entry
# ==========================================================================

def test_open_scene_in_editor_has_psyke_callback():
    db, proj = _setup()
    scene = db.create_scene(proj.id, "S1", content="x")
    win = MainWindow(db, proj.id)
    win._open_scene_in_editor(scene.id)
    assert win._cached_scenes_view._on_open_psyke_entry is not None
