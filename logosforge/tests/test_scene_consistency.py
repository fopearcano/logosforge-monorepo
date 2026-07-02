"""Tests for scene consistency across views.

The Scenes section uses a cached ScenesView. When the project changes
(import, open-file), the cache must be invalidated so ScenesView loads
scenes from the new project — matching Manuscript, Timeline, Plot, and
Outline, which are always created fresh.
"""

from PySide6.QtCore import Qt

from logosforge.db import Database
from logosforge.ui.main_window import MainWindow

USER_ROLE = Qt.ItemDataRole.UserRole


def _make_window():
    db = Database()
    proj = db.create_project("Project A")
    win = MainWindow(db, proj.id)
    return win, db, proj


def _scene_ids_in_list(view):
    return [view._list.item(i).data(USER_ROLE) for i in range(view._list.count())]


# -- Cache invalidation on project switch ------------------------------------

def test_cache_reset_on_new_project():
    win, db, proj_a = _make_window()
    db.create_scene(proj_a.id, "Scene A1")
    win._show_scenes()
    assert win._cached_scenes_view is not None

    win._on_new_project()
    assert win._cached_scenes_view is None
    assert win._project_id != proj_a.id


def test_scenes_view_project_id_matches_window():
    win, db, proj_a = _make_window()
    db.create_scene(proj_a.id, "Scene A1")
    win._show_scenes()
    assert win._cached_scenes_view._project_id == proj_a.id

    win._on_new_project()
    win._show_scenes()
    assert win._cached_scenes_view._project_id == win._project_id


def test_new_project_shows_no_old_scenes():
    win, db, proj_a = _make_window()
    db.create_scene(proj_a.id, "Old Scene 1")
    db.create_scene(proj_a.id, "Old Scene 2")
    win._show_scenes()
    assert win._cached_scenes_view._list.count() == 2

    win._on_new_project()
    new_pid = win._project_id
    win._show_scenes()
    assert win._cached_scenes_view._list.count() == 0


def test_new_project_shows_only_new_scenes():
    win, db, proj_a = _make_window()
    db.create_scene(proj_a.id, "Old Scene")
    win._show_scenes()

    win._on_new_project()
    new_pid = win._project_id
    db.create_scene(new_pid, "New Scene 1")
    db.create_scene(new_pid, "New Scene 2")
    win._show_scenes()

    view = win._cached_scenes_view
    assert view._list.count() == 2
    expected = db.get_all_scenes(new_pid)
    assert _scene_ids_in_list(view) == [s.id for s in expected]


# -- Scene source of truth: all views see the same data ---------------------

def test_all_views_use_same_db_source():
    win, db, proj = _make_window()
    s1 = db.create_scene(proj.id, "Scene 1")
    s2 = db.create_scene(proj.id, "Scene 2")
    s3 = db.create_scene(proj.id, "Scene 3")

    expected = db.get_all_scenes(proj.id)
    expected_ids = [s.id for s in expected]

    win._show_scenes()
    view = win._cached_scenes_view
    assert view._list.count() == len(expected)
    assert _scene_ids_in_list(view) == expected_ids


def test_scene_ordering_after_reorder():
    win, db, proj = _make_window()
    s1 = db.create_scene(proj.id, "First")
    s2 = db.create_scene(proj.id, "Second")
    s3 = db.create_scene(proj.id, "Third")

    db.move_scene_up(s3.id)

    expected = db.get_all_scenes(proj.id)
    expected_ids = [s.id for s in expected]

    win._show_scenes()
    view = win._cached_scenes_view
    assert _scene_ids_in_list(view) == expected_ids


# -- External changes reflected via refresh ----------------------------------

def test_scene_creation_reflected_after_refresh():
    """Scenes created externally appear after a refresh cycle."""
    win, db, proj = _make_window()
    db.create_scene(proj.id, "Existing")
    win._show_scenes()
    view = win._cached_scenes_view
    assert view._list.count() == 1

    db.create_scene(proj.id, "New Scene")
    view._do_refresh()
    assert view._list.count() == 2


def test_scene_deletion_reflected_after_refresh():
    """Scenes deleted externally disappear after a refresh cycle."""
    win, db, proj = _make_window()
    s1 = db.create_scene(proj.id, "Keep")
    s2 = db.create_scene(proj.id, "Delete")
    win._show_scenes()
    view = win._cached_scenes_view
    assert view._list.count() == 2

    db.delete_scene(s2.id)
    view._do_refresh()
    assert view._list.count() == 1
    assert _scene_ids_in_list(view) == [s1.id]


def test_scene_rename_reflected_after_refresh():
    """Scene title changes appear after a refresh cycle."""
    win, db, proj = _make_window()
    s = db.create_scene(proj.id, "Original Title")
    win._show_scenes()
    view = win._cached_scenes_view
    assert "Original Title" in view._list.item(0).text()

    db.update_scene(s.id, title="Updated Title")
    view._do_refresh()
    assert "Updated Title" in view._list.item(0).text()


def test_reorder_reflected_after_refresh():
    """Reordering scenes externally is reflected after refresh."""
    win, db, proj = _make_window()
    s1 = db.create_scene(proj.id, "First")
    s2 = db.create_scene(proj.id, "Second")
    win._show_scenes()
    view = win._cached_scenes_view
    assert _scene_ids_in_list(view) == [s1.id, s2.id]

    db.move_scene_up(s2.id)
    view._do_refresh()
    assert _scene_ids_in_list(view) == [s2.id, s1.id]


# -- Identity mapping: scene IDs stable across operations -------------------

def test_scene_ids_stable_after_multiple_operations():
    """Scene IDs in the list match the DB after create/delete/reorder."""
    win, db, proj = _make_window()
    s1 = db.create_scene(proj.id, "A")
    s2 = db.create_scene(proj.id, "B")
    s3 = db.create_scene(proj.id, "C")
    db.move_scene_up(s3.id)
    db.delete_scene(s1.id)

    expected = db.get_all_scenes(proj.id)
    expected_ids = [s.id for s in expected]

    win._show_scenes()
    view = win._cached_scenes_view
    assert _scene_ids_in_list(view) == expected_ids
