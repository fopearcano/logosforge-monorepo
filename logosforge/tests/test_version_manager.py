"""Tests for VersionManager — snapshot storage, retention, and restore."""

import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from logosforge.db import Database
from logosforge.version_manager import (
    MAX_VERSIONS,
    VersionManager,
    _version_dir,
)


def _make_project():
    db = Database()
    proj = db.create_project("VersionTest")
    return db, proj


def _app():
    return QApplication.instance() or QApplication([])


def _with_tmp_versions(project_id):
    """Patch VERSIONS_DIR to a temp dir for test isolation."""
    tmp = Path(tempfile.mkdtemp())
    return patch("logosforge.version_manager.VERSIONS_DIR", tmp), tmp


# -- Snapshot creation ---------------------------------------------------------

def test_create_snapshot_returns_path():
    _app()
    db, proj = _make_project()
    patcher, tmp = _with_tmp_versions(proj.id)
    with patcher:
        vm = VersionManager(db, proj.id)
        path = vm.create_snapshot(reason="test")
    assert path is not None
    assert path.exists()
    assert path.suffix == ".json"
    shutil.rmtree(tmp, ignore_errors=True)


def test_create_snapshot_contains_project_data():
    _app()
    db, proj = _make_project()
    db.create_scene(proj.id, "Scene 1", act="Act 1")
    patcher, tmp = _with_tmp_versions(proj.id)
    with patcher:
        vm = VersionManager(db, proj.id)
        path = vm.create_snapshot(reason="manual", label="checkpoint")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["project"]["title"] == "VersionTest"
    assert len(data["scenes"]) == 1
    assert data["_version_meta"]["reason"] == "manual"
    assert data["_version_meta"]["label"] == "checkpoint"
    shutil.rmtree(tmp, ignore_errors=True)


def test_create_snapshot_clears_dirty_flag():
    _app()
    db, proj = _make_project()
    patcher, tmp = _with_tmp_versions(proj.id)
    with patcher:
        vm = VersionManager(db, proj.id)
        vm.mark_dirty()
        vm.create_snapshot()
    assert not vm._dirty_since_snapshot
    shutil.rmtree(tmp, ignore_errors=True)


# -- Listing -------------------------------------------------------------------

def test_list_versions_empty():
    _app()
    db, proj = _make_project()
    patcher, tmp = _with_tmp_versions(proj.id)
    with patcher:
        vm = VersionManager(db, proj.id)
        assert vm.list_versions() == []
    shutil.rmtree(tmp, ignore_errors=True)


def test_list_versions_returns_created_snapshots():
    _app()
    db, proj = _make_project()
    patcher, tmp = _with_tmp_versions(proj.id)
    with patcher:
        vm = VersionManager(db, proj.id)
        vm.create_snapshot(reason="first")
        vm.create_snapshot(reason="second")
        versions = vm.list_versions()
    assert len(versions) == 2
    assert versions[0].reason in ("first", "second")
    shutil.rmtree(tmp, ignore_errors=True)


def test_list_versions_sorted_newest_first():
    _app()
    db, proj = _make_project()
    patcher, tmp = _with_tmp_versions(proj.id)
    with patcher:
        vm = VersionManager(db, proj.id)
        import time
        vm.create_snapshot(reason="older")
        time.sleep(0.05)
        vm.create_snapshot(reason="newer")
        versions = vm.list_versions()
    assert versions[0].timestamp >= versions[1].timestamp
    shutil.rmtree(tmp, ignore_errors=True)


# -- Version info properties ---------------------------------------------------

def test_version_info_display_time():
    _app()
    db, proj = _make_project()
    patcher, tmp = _with_tmp_versions(proj.id)
    with patcher:
        vm = VersionManager(db, proj.id)
        vm.create_snapshot(reason="test")
        v = vm.list_versions()[0]
    assert len(v.display_time) == 19  # "YYYY-MM-DD HH:MM:SS"
    shutil.rmtree(tmp, ignore_errors=True)


def test_version_info_file_size():
    _app()
    db, proj = _make_project()
    patcher, tmp = _with_tmp_versions(proj.id)
    with patcher:
        vm = VersionManager(db, proj.id)
        vm.create_snapshot()
        v = vm.list_versions()[0]
    assert v.file_size_kb > 0
    shutil.rmtree(tmp, ignore_errors=True)


# -- Load version data ---------------------------------------------------------

def test_load_version_data_strips_meta():
    _app()
    db, proj = _make_project()
    patcher, tmp = _with_tmp_versions(proj.id)
    with patcher:
        vm = VersionManager(db, proj.id)
        path = vm.create_snapshot()
        data = vm.load_version_data(path)
    assert "_version_meta" not in data
    assert "project" in data
    shutil.rmtree(tmp, ignore_errors=True)


# -- Deletion ------------------------------------------------------------------

def test_delete_version():
    _app()
    db, proj = _make_project()
    patcher, tmp = _with_tmp_versions(proj.id)
    with patcher:
        vm = VersionManager(db, proj.id)
        path = vm.create_snapshot()
        assert path.exists()
        vm.delete_version(path)
        assert not path.exists()
    shutil.rmtree(tmp, ignore_errors=True)


# -- Retention -----------------------------------------------------------------

def test_retention_keeps_max_versions():
    _app()
    db, proj = _make_project()
    patcher, tmp = _with_tmp_versions(proj.id)
    with patcher:
        import time
        vm = VersionManager(db, proj.id)
        for i in range(MAX_VERSIONS + 5):
            vm.create_snapshot(reason=f"v{i}")
            time.sleep(0.01)
        versions = vm.list_versions()
    assert len(versions) <= MAX_VERSIONS
    shutil.rmtree(tmp, ignore_errors=True)


# -- Restore -------------------------------------------------------------------

def test_restore_creates_safety_snapshot():
    _app()
    db, proj = _make_project()
    db.create_scene(proj.id, "Original")
    patcher, tmp = _with_tmp_versions(proj.id)
    with patcher:
        vm = VersionManager(db, proj.id)
        path = vm.create_snapshot(reason="base")
        count_before = len(vm.list_versions())
        vm.restore_version(path)
        count_after = len(vm.list_versions())
    assert count_after == count_before + 1
    shutil.rmtree(tmp, ignore_errors=True)


def test_restore_returns_new_project_id():
    _app()
    db, proj = _make_project()
    db.create_scene(proj.id, "Original")
    patcher, tmp = _with_tmp_versions(proj.id)
    with patcher:
        vm = VersionManager(db, proj.id)
        path = vm.create_snapshot()
        new_id = vm.restore_version(path)
    assert new_id is not None
    assert new_id != proj.id
    shutil.rmtree(tmp, ignore_errors=True)


def test_restore_loads_data_correctly():
    _app()
    db, proj = _make_project()
    db.create_scene(proj.id, "SceneA", act="Act 1")
    patcher, tmp = _with_tmp_versions(proj.id)
    with patcher:
        vm = VersionManager(db, proj.id)
        path = vm.create_snapshot()
        new_id = vm.restore_version(path)
    scenes = db.get_all_scenes(new_id)
    assert len(scenes) == 1
    assert scenes[0].title == "SceneA"
    assert scenes[0].act == "Act 1"
    shutil.rmtree(tmp, ignore_errors=True)


def test_restore_invalid_path_returns_none():
    _app()
    db, proj = _make_project()
    patcher, tmp = _with_tmp_versions(proj.id)
    with patcher:
        vm = VersionManager(db, proj.id)
        result = vm.restore_version(Path("/nonexistent/file.json"))
    assert result is None
    shutil.rmtree(tmp, ignore_errors=True)


# -- Periodic timer ------------------------------------------------------------

def test_periodic_timer_interval():
    _app()
    db, proj = _make_project()
    vm = VersionManager(db, proj.id)
    from logosforge.version_manager import SNAPSHOT_INTERVAL_MS
    assert vm._interval_timer.interval() == SNAPSHOT_INTERVAL_MS


def test_start_activates_timer():
    _app()
    db, proj = _make_project()
    vm = VersionManager(db, proj.id)
    vm.start()
    assert vm._interval_timer.isActive()
    vm.stop()


def test_stop_deactivates_timer():
    _app()
    db, proj = _make_project()
    vm = VersionManager(db, proj.id)
    vm.start()
    vm.stop()
    assert not vm._interval_timer.isActive()


def test_interval_callback_snapshots_when_dirty():
    _app()
    db, proj = _make_project()
    patcher, tmp = _with_tmp_versions(proj.id)
    with patcher:
        vm = VersionManager(db, proj.id)
        vm.mark_dirty()
        vm._on_interval()
        versions = vm.list_versions()
    assert len(versions) == 1
    assert versions[0].reason == "periodic"
    shutil.rmtree(tmp, ignore_errors=True)


def test_interval_callback_skips_when_not_dirty():
    _app()
    db, proj = _make_project()
    patcher, tmp = _with_tmp_versions(proj.id)
    with patcher:
        vm = VersionManager(db, proj.id)
        vm._on_interval()
        assert vm.list_versions() == []
    shutil.rmtree(tmp, ignore_errors=True)
