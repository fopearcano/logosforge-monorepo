"""Tests for StagesView UI: nav, tree rendering, action flow."""

from logosforge.db import Database
from logosforge.stages import capture_scope, save_snapshot
from logosforge.ui.main_window import MainWindow
from logosforge.ui.stages_view import StagesView


def _setup():
    db = Database()
    proj = db.create_project("StagesUITest")
    return db, proj


# -- Navigation --------------------------------------------------------------

def test_stages_button_in_sidebar():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    assert "Stages" in win.sidebar_buttons


def test_stages_in_nav_labels():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    assert "Stages" in win._nav_labels


def test_show_stages_swaps_central_view():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    win._show_stages()
    assert isinstance(win.content_area, StagesView)


# -- Tree rendering ---------------------------------------------------------

def test_tree_lists_existing_stages():
    db, proj = _setup()
    db.create_stage(proj.id, "Draft 1")
    db.create_stage(proj.id, "Draft 2")
    view = StagesView(db, proj.id)
    # 2 root items expected
    root = view._tree.invisibleRootItem()
    assert root.childCount() == 2


def test_empty_state_guides_first_stage():
    db, proj = _setup()
    view = StagesView(db, proj.id)                       # no stages
    assert view._detail_label.text() == "No stages yet"
    assert "New Stage" in view._meta_label.text()


def test_non_empty_unselected_state_is_neutral():
    db, proj = _setup()
    db.create_stage(proj.id, "Draft 1")
    view = StagesView(db, proj.id)                       # stages exist, none picked
    assert view._detail_label.text() == "Select a stage to see its details."


def test_canonical_change_reports_demotion():
    # Setting a project stage canonical silently demotes the other canonical
    # project stage — the UI must surface that.
    db, proj = _setup()
    a = db.create_stage(proj.id, "A", scope_type="project", status="canonical")
    b = db.create_stage(proj.id, "B", scope_type="project")
    view = StagesView(db, proj.id)
    view._select_stage(b.id)
    view._status_combo.setCurrentIndex(view._status_combo.findData("canonical"))
    assert db.get_stage(a.id).status == "alternate"     # A demoted
    assert db.get_stage(b.id).status == "canonical"
    assert "demoted 1" in view._restore_status.text()


def test_canonical_change_no_peers_no_demotion_text():
    db, proj = _setup()
    s = db.create_stage(proj.id, "Solo", scope_type="project")
    view = StagesView(db, proj.id)
    view._select_stage(s.id)
    view._status_combo.setCurrentIndex(view._status_combo.findData("canonical"))
    assert "demoted" not in view._restore_status.text()
    assert "canonical" in view._restore_status.text().lower()


def test_scope_labels_cover_all_scopes_and_round_trip():
    from logosforge.ui.stages_view import (
        _SCOPE_LABELS,
        _USER_SCOPES,
        _scope_from_label,
    )
    for scope in _USER_SCOPES:
        assert scope in _SCOPE_LABELS
        assert _scope_from_label(_SCOPE_LABELS[scope]) == scope
    assert _scope_from_label("nonsense") == "project"    # safe default


def test_tree_nests_child_stages():
    db, proj = _setup()
    parent = db.create_stage(proj.id, "Parent")
    db.create_stage(proj.id, "Child", parent_stage_id=parent.id)
    view = StagesView(db, proj.id)
    root = view._tree.invisibleRootItem()
    parent_item = root.child(0)
    assert parent_item.childCount() == 1
    assert parent_item.child(0).text(0) == "Child"


# -- Snapshot action --------------------------------------------------------

def test_snapshot_action_creates_snapshot():
    db, proj = _setup()
    scene = db.create_scene(proj.id, "S1", content="hello")
    stage = db.create_stage(
        proj.id, "St", scope_type="scene", scope_id=scene.id,
    )
    view = StagesView(db, proj.id)
    view._selected_stage_id = stage.id
    view._on_take_snapshot()
    assert len(db.get_stage_snapshots(stage.id)) == 1


def test_reload_tree_preserves_selection():
    # A rebuild (fired by every data-changed refresh) must not drop the
    # selected stage — otherwise the next action says "select a stage first".
    db, proj = _setup()
    stage = db.create_stage(proj.id, "Keep")
    view = StagesView(db, proj.id)
    view._select_stage(stage.id)
    assert view._selected_stage_id == stage.id
    view._reload_tree()
    assert view._selected_stage_id == stage.id           # preserved
    assert view._detail_label.text() == "Keep"           # detail still shown


def test_snapshot_via_mainwindow_keeps_selection_and_shows_snapshot():
    # End-to-end: taking a snapshot triggers _on_data_changed → refresh →
    # _reload_tree; the stage must stay selected and the snapshot must appear.
    db, proj = _setup()
    db.create_scene(proj.id, "S1", content="hello")
    stage = db.create_stage(proj.id, "St")
    win = MainWindow(db, proj.id)
    win._show_stages()
    view = win.content_area
    view._select_stage(stage.id)
    view._on_take_snapshot()
    assert view._selected_stage_id == stage.id           # not deselected
    assert view._snapshot_list.count() == 1              # snapshot visible


def test_snapshot_label_not_derived_from_stage_time():
    # The old label "Snap {stage.created_at}" gave every snapshot the same,
    # misleading time. Now the row shows a distinct id-based label + the real
    # snapshot timestamp — never the stage's creation time as a prefix.
    db, proj = _setup()
    stage = db.create_stage(proj.id, "St")
    view = StagesView(db, proj.id)
    view._select_stage(stage.id)
    view._on_take_snapshot()
    snap = db.get_stage_snapshots(stage.id)[0]
    assert snap.label == ""                              # no stage-time prefix
    assert f"Snapshot {snap.id}" in view._snapshot_list.item(0).text()


def test_snapshot_without_selection_shows_message():
    db, proj = _setup()
    view = StagesView(db, proj.id)
    view._selected_stage_id = None
    view._on_take_snapshot()
    assert "Select" in view._restore_status.text()


# -- Restore confirmation flow ----------------------------------------------

def test_restore_requires_two_clicks():
    db, proj = _setup()
    scene = db.create_scene(proj.id, "S1", content="original")
    stage = db.create_stage(
        proj.id, "St", scope_type="scene", scope_id=scene.id,
    )
    snap = save_snapshot(
        db, stage.id, capture_scope(db, proj.id, "scene", scene.id),
    )
    db.update_scene_content(scene.id, "edited")
    view = StagesView(db, proj.id)
    view._selected_stage_id = stage.id
    view._selected_snapshot_id = snap.id

    view._on_restore()
    # First click: scene unchanged, confirm button visible
    assert db.get_scene_by_id(scene.id).content == "edited"
    assert view._confirm_btn.isVisible() or view._pending_restore_snapshot_id == snap.id

    view._on_confirm_restore()
    # After confirm: scene restored
    assert db.get_scene_by_id(scene.id).content == "original"


def test_restore_creates_safety_snapshot():
    db, proj = _setup()
    scene = db.create_scene(proj.id, "S1", content="original")
    stage = db.create_stage(
        proj.id, "St", scope_type="scene", scope_id=scene.id,
    )
    snap = save_snapshot(
        db, stage.id, capture_scope(db, proj.id, "scene", scene.id),
    )
    db.update_scene_content(scene.id, "current state")
    view = StagesView(db, proj.id)
    view._selected_stage_id = stage.id
    view._selected_snapshot_id = snap.id
    view._on_restore()
    view._on_confirm_restore()
    safety_stages = [
        s for s in db.get_all_stages(proj.id) if s.name == "Safety (auto)"
    ]
    assert len(safety_stages) == 1
    safety_snaps = db.get_stage_snapshots(safety_stages[0].id)
    assert len(safety_snaps) == 1
    assert "current state" in safety_snaps[0].data_json


# -- Compare action ---------------------------------------------------------

def test_compare_action_renders_diff():
    db, proj = _setup()
    scene = db.create_scene(proj.id, "S1", content="version 1")
    stage = db.create_stage(
        proj.id, "St", scope_type="scene", scope_id=scene.id,
    )
    snap = save_snapshot(
        db, stage.id, capture_scope(db, proj.id, "scene", scene.id),
    )
    db.update_scene_content(scene.id, "version 2")
    view = StagesView(db, proj.id)
    view._selected_stage_id = stage.id
    view._selected_snapshot_id = snap.id
    view._on_compare()
    diff_text = view._diff_view.toPlainText()
    assert "version 1" in diff_text
    assert "version 2" in diff_text


# -- Status change ----------------------------------------------------------

def test_status_change_persists():
    db, proj = _setup()
    stage = db.create_stage(proj.id, "X", scope_type="project", status="alternate")
    view = StagesView(db, proj.id)
    # select that stage
    view._selected_stage_id = stage.id
    idx = view._status_combo.findData("canonical")
    view._status_combo.setCurrentIndex(idx)
    # currentIndexChanged triggered _on_status_change
    fetched = db.get_stage(stage.id)
    assert fetched.status == "canonical"


# -- Reload from new view -----------------------------------------------------

def test_stages_persist_across_view_recreation():
    db, proj = _setup()
    db.create_stage(proj.id, "Persisted")
    view1 = StagesView(db, proj.id)
    assert view1._tree.invisibleRootItem().childCount() == 1
    view2 = StagesView(db, proj.id)
    assert view2._tree.invisibleRootItem().childCount() == 1
