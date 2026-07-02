"""Integration tests for cloud-safe save and conflict handling."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication

from logosforge.autosave import AutosaveManager
from logosforge.cloud_storage import LOCK_SUFFIX, current_lock_info
from logosforge.db import Database
from logosforge import recent_projects


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _project(db: Database):
    p = db.create_project("Novel")
    db.create_scene(p.id, "Opening", content="text")
    return p


# -- AutosaveManager uses atomic write --------------------------------------

def test_autosave_creates_file_atomically(tmp_path):
    db = Database()
    proj = _project(db)
    mgr = AutosaveManager(db, proj.id)
    target = tmp_path / "p.json"
    mgr.file_path = str(target)
    mgr.mark_dirty()
    mgr.save_now()
    assert target.exists()
    data = json.loads(target.read_text())
    assert isinstance(data, dict)
    # no leftover temp files
    assert list(tmp_path.glob("*.tmp")) == []


def test_autosave_overwrites_safely(tmp_path):
    db = Database()
    proj = _project(db)
    mgr = AutosaveManager(db, proj.id)
    target = tmp_path / "p.json"
    target.write_text('{"old": true}')
    mgr.file_path = str(target)
    mgr.save_now()
    # current content is the new export
    new = json.loads(target.read_text())
    assert "old" not in new


def test_autosave_refreshes_fingerprint_after_save(tmp_path):
    db = Database()
    proj = _project(db)
    mgr = AutosaveManager(db, proj.id)
    target = tmp_path / "p.json"
    mgr.file_path = str(target)
    mgr.save_now()
    # second save must not trip the external-change guard
    mgr.save_now()
    assert mgr.has_external_change() is False


# -- External-change detection -----------------------------------------------

def test_external_change_blocks_overwrite(tmp_path):
    db = Database()
    proj = _project(db)
    mgr = AutosaveManager(db, proj.id)
    target = tmp_path / "p.json"
    mgr.file_path = str(target)
    mgr.save_now()

    # simulate an external edit
    time.sleep(0.01)
    new_mtime = time.time() + 5
    target.write_text('{"changed": "externally"}')
    os.utime(target, (new_mtime, new_mtime))

    signals: list[str] = []
    mgr.external_change_detected.connect(lambda p: signals.append(p))

    ok = mgr.save_now()
    assert ok is False
    assert signals == [str(target)]
    # the external content is preserved
    assert json.loads(target.read_text())["changed"] == "externally"


def test_force_next_save_overwrites_external(tmp_path):
    db = Database()
    proj = _project(db)
    mgr = AutosaveManager(db, proj.id)
    target = tmp_path / "p.json"
    mgr.file_path = str(target)
    mgr.save_now()

    new_mtime = time.time() + 5
    target.write_text('{"changed": true}')
    os.utime(target, (new_mtime, new_mtime))

    mgr.force_next_save()
    ok = mgr.save_now()
    assert ok is True
    data = json.loads(target.read_text())
    assert "changed" not in data


def test_conflict_copy_written_beside_project(tmp_path):
    db = Database()
    proj = _project(db)
    mgr = AutosaveManager(db, proj.id)
    target = tmp_path / "p.json"
    mgr.file_path = str(target)
    mgr.save_now()

    dest = mgr.write_conflict_copy_now()
    assert dest is not None
    assert Path(dest).exists()
    assert Path(dest).parent == target.parent
    assert "conflict" in Path(dest).name


# -- Lock file lifecycle through file_path setter ----------------------------

def test_setting_file_path_refreshes_fingerprint(tmp_path):
    db = Database()
    proj = _project(db)
    mgr = AutosaveManager(db, proj.id)
    target = tmp_path / "p.json"
    target.write_text("{}")
    mgr.file_path = str(target)
    assert mgr._fingerprint is not None


def test_no_save_when_no_path(tmp_path):
    db = Database()
    proj = _project(db)
    mgr = AutosaveManager(db, proj.id)
    mgr.mark_dirty()
    assert mgr.save_now() is False


# -- recent_projects.rename and load_with_status ----------------------------

def test_recent_rename_preserves_other_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(
        recent_projects, "RECENT_FILE", tmp_path / "recent.json",
    )
    monkeypatch.setattr(recent_projects, "CONFIG_DIR", tmp_path)

    a = str(tmp_path / "a.json")
    b = str(tmp_path / "b.json")
    c = str(tmp_path / "c.json")
    for path in (a, b, c):
        Path(path).write_text("{}")
        recent_projects.add(path)

    new_b = str(tmp_path / "b_new.json")
    Path(new_b).write_text("{}")
    recent_projects.rename(b, new_b)

    paths = recent_projects.load()
    assert b not in paths
    assert new_b in paths
    assert a in paths
    assert c in paths


def test_load_with_status_marks_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        recent_projects, "RECENT_FILE", tmp_path / "recent.json",
    )
    monkeypatch.setattr(recent_projects, "CONFIG_DIR", tmp_path)

    real = tmp_path / "real.json"
    real.write_text("{}")
    recent_projects.add(str(real))
    recent_projects.add(str(tmp_path / "ghost.json"))

    statuses = recent_projects.load_with_status()
    seen = {Path(p).name: ok for p, ok in statuses}
    assert seen["real.json"] is True
    assert seen["ghost.json"] is False
    # load_with_status must NOT delete the missing entry
    assert recent_projects.load()  # still has both


# -- Full project save+open roundtrip in a "cloud-like" folder --------------

def test_roundtrip_through_cloud_like_folder(tmp_path):
    """Mimic Device A saves; Device B (same machine, fresh manager) opens."""
    cloud = tmp_path / "Dropbox" / "MyNovels"
    cloud.mkdir(parents=True)

    db_a = Database()
    proj_a = db_a.create_project("Roundtrip")
    db_a.create_scene(proj_a.id, "S1", content="Hello there")
    mgr_a = AutosaveManager(db_a, proj_a.id)
    target = cloud / "Roundtrip.json"
    mgr_a.file_path = str(target)
    mgr_a.save_now()

    # Device B reads it back
    raw = target.read_text()
    data = json.loads(raw)
    assert data["project"]["title"] == "Roundtrip"
    scenes = data.get("scenes") or []
    assert any("Hello there" in (s.get("content") or "") for s in scenes)


# -- Lock-acquisition through autosave/main_window flow (smoke) -------------

def test_lock_lifecycle_smoke(tmp_path):
    from logosforge.cloud_storage import (
        acquire_lock,
        current_lock_info,
        release_lock,
    )
    target = tmp_path / "x.json"
    target.write_text("{}")
    assert current_lock_info(target) is None
    acquire_lock(target)
    info = current_lock_info(target)
    assert info is not None
    assert info.is_same_machine() is True
    release_lock(target)
    assert current_lock_info(target) is None
