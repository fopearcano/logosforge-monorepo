"""Tests for cloud-safe project storage primitives."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from logosforge.cloud_storage import (
    CloudFolder,
    FileFingerprint,
    LockInfo,
    LOCK_SUFFIX,
    acquire_lock,
    atomic_write_text,
    classify_path,
    conflict_copy_path,
    current_lock_info,
    detect_cloud_folders,
    hash_file,
    release_lock,
    write_conflict_copy,
)


# -- atomic_write_text -------------------------------------------------------

class TestAtomicWrite:
    def test_creates_file(self, tmp_path):
        target = tmp_path / "out.json"
        atomic_write_text(target, '{"a": 1}')
        assert target.read_text() == '{"a": 1}'

    def test_overwrites_existing(self, tmp_path):
        target = tmp_path / "out.json"
        target.write_text("OLD")
        atomic_write_text(target, "NEW")
        assert target.read_text() == "NEW"

    def test_creates_parent_dirs(self, tmp_path):
        target = tmp_path / "deep" / "nested" / "out.json"
        atomic_write_text(target, "data")
        assert target.read_text() == "data"

    def test_leaves_no_temp_file_on_success(self, tmp_path):
        target = tmp_path / "out.json"
        atomic_write_text(target, "data")
        leftover = list(tmp_path.glob("*.tmp"))
        assert leftover == []

    def test_cleans_up_temp_on_failure(self, tmp_path, monkeypatch):
        target = tmp_path / "out.json"
        target.write_text("ORIGINAL")

        def explode(*_a, **_kw):
            raise RuntimeError("simulated")

        monkeypatch.setattr(os, "replace", explode)
        with pytest.raises(RuntimeError):
            atomic_write_text(target, "NEW")
        # original is untouched, no .tmp leftovers
        assert target.read_text() == "ORIGINAL"
        leftover = list(tmp_path.glob("*.tmp"))
        assert leftover == []

    def test_atomic_against_partial_read(self, tmp_path):
        """If we crash mid-write, the previous content must still be intact.

        Simulated by inspecting what os.replace receives — the tmp file must
        be fully written and closed before replace is called.
        """
        target = tmp_path / "out.json"
        target.write_text("OK_OLD")

        seen_tmp_contents: list[str] = []
        orig_replace = os.replace

        def spy_replace(src, dst):
            seen_tmp_contents.append(Path(src).read_text())
            return orig_replace(src, dst)

        with patch("logosforge.cloud_storage.os.replace", side_effect=spy_replace):
            atomic_write_text(target, "FULL_NEW_CONTENT")
        assert seen_tmp_contents == ["FULL_NEW_CONTENT"]
        assert target.read_text() == "FULL_NEW_CONTENT"


# -- FileFingerprint ---------------------------------------------------------

class TestFingerprint:
    def test_of_missing_file_returns_none(self, tmp_path):
        assert FileFingerprint.of(tmp_path / "nope") is None

    def test_matches_after_no_change(self, tmp_path):
        p = tmp_path / "a.json"
        p.write_text("x")
        f1 = FileFingerprint.of(p)
        f2 = FileFingerprint.of(p)
        assert f1.matches(f2)

    def test_differs_after_external_change(self, tmp_path):
        p = tmp_path / "a.json"
        p.write_text("x")
        f1 = FileFingerprint.of(p)
        time.sleep(0.01)
        new_ns = f1.mtime_ns + 10_000_000
        os.utime(p, ns=(new_ns, new_ns))
        p.write_text("y")
        f2 = FileFingerprint.of(p)
        assert not f1.matches(f2)


def test_hash_file(tmp_path):
    p = tmp_path / "a"
    p.write_bytes(b"hello")
    assert hash_file(p) == (
        "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    )


def test_hash_missing_file(tmp_path):
    assert hash_file(tmp_path / "nope") is None


# -- Lock file ---------------------------------------------------------------

class TestLockFile:
    def test_acquire_creates_lock(self, tmp_path):
        project = tmp_path / "proj.json"
        project.write_text("{}")
        info = acquire_lock(project)
        lock_file = project.with_name(project.name + LOCK_SUFFIX)
        assert lock_file.exists()
        data = json.loads(lock_file.read_text())
        assert data["pid"] == os.getpid()
        assert info.pid == os.getpid()

    def test_release_removes_lock(self, tmp_path):
        project = tmp_path / "proj.json"
        project.write_text("{}")
        acquire_lock(project)
        release_lock(project)
        lock_file = project.with_name(project.name + LOCK_SUFFIX)
        assert not lock_file.exists()

    def test_release_when_missing_is_safe(self, tmp_path):
        project = tmp_path / "proj.json"
        release_lock(project)  # must not raise

    def test_current_lock_info_reads_back(self, tmp_path):
        project = tmp_path / "proj.json"
        project.write_text("{}")
        acquire_lock(project)
        info = current_lock_info(project)
        assert info is not None
        assert info.pid == os.getpid()

    def test_current_lock_info_none_when_missing(self, tmp_path):
        project = tmp_path / "proj.json"
        assert current_lock_info(project) is None

    def test_corrupt_lock_returns_none(self, tmp_path):
        project = tmp_path / "proj.json"
        lock = project.with_name(project.name + LOCK_SUFFIX)
        lock.write_text("not json")
        assert current_lock_info(project) is None

    def test_same_machine_detection(self, tmp_path):
        project = tmp_path / "proj.json"
        acquire_lock(project)
        info = current_lock_info(project)
        assert info.is_same_machine() is True

    def test_foreign_machine_not_same(self, tmp_path):
        info = LockInfo(
            device="other-host",
            user="other-user",
            timestamp=time.time(),
            app_version="1.0",
            pid=99999,
        )
        assert info.is_same_machine() is False

    def test_stale_when_pid_dead_on_same_machine(self, tmp_path):
        project = tmp_path / "proj.json"
        acquire_lock(project)
        info = current_lock_info(project)
        info.pid = 1  # init/PID 1 still alive — use a known-dead pid instead
        # Use an unlikely large pid
        info.pid = 999_999_999
        assert info.is_stale() is True

    def test_stale_when_very_old(self):
        info = LockInfo(
            device="other-host",
            user="other-user",
            timestamp=time.time() - 30 * 24 * 60 * 60,
            app_version="1.0",
            pid=12345,
        )
        assert info.is_stale() is True

    def test_fresh_foreign_lock_not_stale(self):
        info = LockInfo(
            device="other-host",
            user="other-user",
            timestamp=time.time(),
            app_version="1.0",
            pid=12345,
        )
        assert info.is_stale() is False


# -- Conflict copies ---------------------------------------------------------

class TestConflictCopy:
    def test_path_shape(self, tmp_path):
        p = tmp_path / "novel.json"
        cp = conflict_copy_path(p, when=0)
        assert cp.parent == p.parent
        assert cp.name.startswith("novel_conflict_")
        assert cp.suffix == ".json"

    def test_write_creates_sibling_file(self, tmp_path):
        p = tmp_path / "novel.json"
        p.write_text("{}")
        dest = write_conflict_copy(p, '{"conflict": true}')
        assert dest.exists()
        assert dest.parent == p.parent
        assert dest.read_text() == '{"conflict": true}'
        assert dest != p


# -- Cloud detection ---------------------------------------------------------

class TestCloudDetection:
    def test_detect_returns_list(self):
        result = detect_cloud_folders()
        assert isinstance(result, list)
        for entry in result:
            assert isinstance(entry, CloudFolder)
            assert entry.path.is_dir()

    def test_classify_local_path(self, tmp_path):
        # tmp_path is some unique temp dir — should not match any cloud provider
        with patch(
            "logosforge.cloud_storage.detect_cloud_folders", return_value=[],
        ):
            assert classify_path(tmp_path / "x.json") == "Local"

    def test_classify_inside_cloud_folder(self, tmp_path):
        cloud_root = tmp_path / "MyDropbox"
        cloud_root.mkdir()
        with patch(
            "logosforge.cloud_storage.detect_cloud_folders",
            return_value=[CloudFolder(provider="Dropbox", path=cloud_root)],
        ):
            assert classify_path(cloud_root / "project.json") == "Dropbox"

    def test_classify_path_name_heuristic_dropbox(self, tmp_path):
        with patch(
            "logosforge.cloud_storage.detect_cloud_folders", return_value=[],
        ):
            dbox = tmp_path / "Dropbox" / "p.json"
            dbox.parent.mkdir()
            assert classify_path(dbox) == "Dropbox"

    def test_classify_path_name_heuristic_onedrive(self, tmp_path):
        with patch(
            "logosforge.cloud_storage.detect_cloud_folders", return_value=[],
        ):
            od = tmp_path / "OneDrive-Personal" / "p.json"
            od.parent.mkdir()
            assert classify_path(od) == "OneDrive"
