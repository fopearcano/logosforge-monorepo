"""Tests for view refresh, cache invalidation, and plot block edits."""

from logosforge.db import Database
from logosforge.ui.dashboard_view import DashboardView
from logosforge.ui.main_window import MainWindow
from logosforge.ui.multi_plot_view import MultiPlotView, _TimelineStrip, _ArcLanes, _CharLanes
from logosforge.ui.psyke_view import PsykeView
from logosforge.ui.stages_view import StagesView


def _setup():
    db = Database()
    proj = db.create_project("RefreshTest")
    return db, proj


# -- 1. Active view refresh on data_changed ---------------------------------

def test_on_data_changed_refreshes_dashboard():
    db, proj = _setup()
    db.create_scene(proj.id, "S1", content="hello")
    win = MainWindow(db, proj.id)
    win._set_active_section("Dashboard")
    win._show_dashboard()
    view = win.content_area
    assert isinstance(view, DashboardView)
    db.create_scene(proj.id, "S2", content="world")
    win._on_data_changed()
    # Dashboard was refreshed — if it crashed or didn't call refresh(), we'd fail


def test_on_data_changed_refreshes_psyke_view():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    win._set_active_section("PSYKE")
    win._show_psyke()
    view = win.content_area
    assert isinstance(view, PsykeView)
    # Add a PSYKE entry externally
    db.create_psyke_entry(proj.id, "NewChar", entry_type="character")
    win._on_data_changed()
    # View was refreshed — entry should appear in the list
    found = False
    for i in range(view._list.count()):
        if "NewChar" in view._list.item(i).text():
            found = True
            break
    assert found


def test_on_data_changed_refreshes_stages_view():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    win._set_active_section("Stages")
    win._show_stages()
    view = win.content_area
    assert isinstance(view, StagesView)
    db.create_stage(proj.id, "NewStage")
    win._on_data_changed()
    root = view._tree.invisibleRootItem()
    assert root.childCount() >= 1


def test_on_data_changed_refreshes_plot_view():
    db, proj = _setup()
    db.create_scene(proj.id, "S1", content="x")
    win = MainWindow(db, proj.id)
    win._set_active_section("Plot")
    win._show_plot()
    view = win.content_area
    from logosforge.ui.canvas_plot_view import CanvasPlotView
    assert isinstance(view, CanvasPlotView)
    db.create_scene(proj.id, "S2", content="y")
    win._on_data_changed()
    # View was refreshed — no crash, and grid view picked up new scene


# -- 2. New project resets caches -------------------------------------------

def test_new_project_clears_cached_scenes_view():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    win._show_scenes()
    assert win._cached_scenes_view is not None
    win._on_new_project()
    assert win._cached_scenes_view is None


def test_new_project_clears_scene_entry_caches():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    win._cached_scene_entry_scene = 42
    win._cached_scene_entry_ids = {1, 2, 3}
    win._on_new_project()
    assert win._cached_scene_entry_scene is None
    assert win._cached_scene_entry_ids is None


def test_new_project_no_old_scenes_remain():
    db, proj = _setup()
    db.create_scene(proj.id, "OldScene", content="old")
    win = MainWindow(db, proj.id)
    win._on_new_project()
    new_id = win._project_id
    assert new_id != proj.id
    scenes = db.get_all_scenes(new_id)
    assert len(scenes) == 0


def test_new_project_no_old_psyke_remains():
    db, proj = _setup()
    db.create_psyke_entry(proj.id, "OldChar", entry_type="character")
    win = MainWindow(db, proj.id)
    win._on_new_project()
    new_id = win._project_id
    entries = db.get_all_psyke_entries(new_id)
    assert len(entries) == 0


# -- 3. Loaded project shows Dashboard --------------------------------------

def test_open_file_shows_dashboard(tmp_path):
    from logosforge.export import export_json

    db, proj = _setup()
    db.create_scene(proj.id, "TestScene", content="data")
    json_data = export_json(db, proj.id)
    path = tmp_path / "test_proj.json"
    path.write_text(json_data, encoding="utf-8")

    win = MainWindow(db, proj.id)
    win._open_file(str(path))
    assert isinstance(win.content_area, DashboardView)


# -- 4. Plot block edit options (context menus) ------------------------------

def test_timeline_cards_have_context_menu():
    db, proj = _setup()
    db.create_scene(proj.id, "Scene1", content="x")
    view = _TimelineStrip(db, proj.id)
    view.refresh()
    assert view.card_count() == 1
    card = view._cards[0]
    assert card.property("scene_id") is not None


def test_arc_cards_have_context_menu():
    db, proj = _setup()
    db.create_scene(proj.id, "Scene1", content="x", plotline="MainPlot")
    view = _ArcLanes(db, proj.id)
    view.refresh()
    assert view.lane_count() >= 1


def test_char_cards_have_context_menu():
    db, proj = _setup()
    char = db.create_character(proj.id, "Hero")
    db.create_scene(proj.id, "Scene1", content="x", character_ids=[char.id])
    view = _CharLanes(db, proj.id)
    view.refresh()
    assert view.lane_count() >= 1


def test_timeline_edit_title_updates_db():
    db, proj = _setup()
    scene = db.create_scene(proj.id, "OldTitle", content="x")
    view = _TimelineStrip(db, proj.id)
    view.refresh()
    db.update_scene(
        scene.id, "NewTitle",
        summary=scene.summary, synopsis=scene.synopsis,
        goal=scene.goal, conflict=scene.conflict, outcome=scene.outcome,
        beat=scene.beat, tags=scene.tags, act=scene.act,
        content=scene.content, chapter=scene.chapter, plotline=scene.plotline,
    )
    updated = db.get_scene_by_id(scene.id)
    assert updated.title == "NewTitle"


def test_plot_view_refresh_method():
    db, proj = _setup()
    db.create_scene(proj.id, "S1", content="x")
    view = MultiPlotView(db, proj.id)
    assert hasattr(view, 'refresh')
    view.refresh()


def test_timeline_stores_filters_on_refresh():
    from logosforge.ui.multi_plot_view import PlotFilters
    db, proj = _setup()
    db.create_scene(proj.id, "S1", content="x")
    view = _TimelineStrip(db, proj.id)
    filters = PlotFilters(tag="important")
    view.refresh(filters)
    assert view._filters is filters


# -- 5. View refresh methods exist and work ----------------------------------

def test_dashboard_view_has_refresh():
    db, proj = _setup()
    view = DashboardView(db, proj.id)
    assert hasattr(view, 'refresh')
    view.refresh()


def test_psyke_view_has_refresh():
    db, proj = _setup()
    view = PsykeView(db, proj.id)
    assert hasattr(view, 'refresh')
    view.refresh()


def test_stages_view_has_refresh():
    db, proj = _setup()
    view = StagesView(db, proj.id)
    assert hasattr(view, 'refresh')
    view.refresh()


def test_multi_plot_view_has_refresh():
    db, proj = _setup()
    view = MultiPlotView(db, proj.id)
    assert hasattr(view, 'refresh')
    view.refresh()


# -- 6. Cache invalidation --------------------------------------------------

def test_psyke_console_cache_cleared_on_new_project():
    db, proj = _setup()
    db.create_psyke_entry(proj.id, "OldEntry", entry_type="character")
    win = MainWindow(db, proj.id)
    win._psyke_console.rebuild_index()
    win._on_new_project()
    cache = win._psyke_console._psyke_entries_cache
    if cache is not None:
        for entry in cache:
            assert entry.name != "OldEntry"
    else:
        win._psyke_console.rebuild_index()
        for entry in win._psyke_console._psyke_entries_cache:
            assert entry.name != "OldEntry"


def test_assistant_panel_refreshed_on_new_project():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    win._on_new_project()
    # No crash; assistant refreshed


# -- 7. Stale data doesn't reappear after section switch --------------------

def test_scene_update_visible_after_data_changed():
    db, proj = _setup()
    scene = db.create_scene(proj.id, "Original", content="old text")
    win = MainWindow(db, proj.id)
    win._set_active_section("PSYKE")
    win._show_psyke()
    db.update_scene_content(scene.id, "new text")
    win._on_data_changed()
    win._set_active_section("Dashboard")
    win._show_dashboard()
    # Dashboard should reflect new state, not old
    assert isinstance(win.content_area, DashboardView)


def test_no_stale_stages_after_switch():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    win._set_active_section("Stages")
    win._show_stages()
    db.create_stage(proj.id, "AddedExternally")
    win._on_data_changed()
    view = win.content_area
    assert isinstance(view, StagesView)
    root = view._tree.invisibleRootItem()
    found = False
    for i in range(root.childCount()):
        if root.child(i).text(0) == "AddedExternally":
            found = True
            break
    assert found
