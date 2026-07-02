"""Tests for AutosaveManager — debounced project saves."""

import json
import tempfile
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from logosforge.autosave import AutosaveManager, _DEBOUNCE_MS
from logosforge.db import Database


def _make_project():
    db = Database()
    proj = db.create_project("AutosaveTest")
    return db, proj


def _app():
    return QApplication.instance() or QApplication([])


# -- Basic state ---------------------------------------------------------------

def test_autosave_initially_not_dirty():
    _app()
    db, proj = _make_project()
    mgr = AutosaveManager(db, proj.id)
    assert not mgr.dirty


def test_mark_dirty_sets_flag():
    _app()
    db, proj = _make_project()
    mgr = AutosaveManager(db, proj.id)
    mgr.mark_dirty()
    assert mgr.dirty


def test_mark_clean_clears_flag():
    _app()
    db, proj = _make_project()
    mgr = AutosaveManager(db, proj.id)
    mgr.mark_dirty()
    mgr.mark_clean()
    assert not mgr.dirty


# -- File path -----------------------------------------------------------------

def test_file_path_default_none():
    _app()
    db, proj = _make_project()
    mgr = AutosaveManager(db, proj.id)
    assert mgr.file_path is None


def test_file_path_setter():
    _app()
    db, proj = _make_project()
    mgr = AutosaveManager(db, proj.id)
    mgr.file_path = "/tmp/test.json"
    assert mgr.file_path == "/tmp/test.json"


# -- Immediate save ------------------------------------------------------------

def test_save_now_without_file_returns_false():
    _app()
    db, proj = _make_project()
    mgr = AutosaveManager(db, proj.id)
    mgr.mark_dirty()
    assert mgr.save_now() is False


def test_save_now_writes_valid_json():
    _app()
    db, proj = _make_project()
    db.create_scene(proj.id, "Scene 1", act="Act 1")

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name

    mgr = AutosaveManager(db, proj.id)
    mgr.file_path = path
    mgr.mark_dirty()
    assert mgr.save_now() is True
    assert not mgr.dirty

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    assert data["project"]["title"] == "AutosaveTest"
    assert len(data["scenes"]) == 1

    Path(path).unlink(missing_ok=True)


def test_save_now_clears_dirty():
    _app()
    db, proj = _make_project()
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name

    mgr = AutosaveManager(db, proj.id)
    mgr.file_path = path
    mgr.mark_dirty()
    mgr.save_now()
    assert not mgr.dirty

    Path(path).unlink(missing_ok=True)


# -- Status signal -------------------------------------------------------------

def test_save_emits_saved_status():
    _app()
    db, proj = _make_project()
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name

    mgr = AutosaveManager(db, proj.id)
    mgr.file_path = path
    statuses: list[str] = []
    mgr.status_changed.connect(statuses.append)
    mgr.mark_dirty()
    mgr.save_now()
    assert "Saving…" in statuses
    assert "Saved" in statuses

    Path(path).unlink(missing_ok=True)


def test_save_emits_failed_on_bad_path(tmp_path):
    # Atomic save auto-creates missing parents, so we need a genuinely
    # unwritable path.  Use a path whose parent is a regular file — the
    # mkdir() inside atomic_write_text will fail with NotADirectoryError.
    _app()
    db, proj = _make_project()
    mgr = AutosaveManager(db, proj.id)
    blocker = tmp_path / "blocker"
    blocker.write_text("not a dir")
    mgr.file_path = str(blocker / "file.json")
    statuses: list[str] = []
    mgr.status_changed.connect(statuses.append)
    mgr.mark_dirty()
    mgr.save_now()
    assert "Save failed" in statuses


# -- Debounce ------------------------------------------------------------------

def test_debounce_interval():
    _app()
    db, proj = _make_project()
    mgr = AutosaveManager(db, proj.id)
    assert mgr._debounce.interval() == _DEBOUNCE_MS


def test_debounce_timer_starts_on_mark_dirty_with_file():
    _app()
    db, proj = _make_project()
    mgr = AutosaveManager(db, proj.id)
    mgr.file_path = "/tmp/test.json"
    mgr.mark_dirty()
    assert mgr._debounce.isActive()


def test_debounce_timer_not_started_without_file():
    _app()
    db, proj = _make_project()
    mgr = AutosaveManager(db, proj.id)
    mgr.mark_dirty()
    assert not mgr._debounce.isActive()


# -- Concurrent save protection ------------------------------------------------

def test_no_concurrent_saves():
    _app()
    db, proj = _make_project()
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name

    mgr = AutosaveManager(db, proj.id)
    mgr.file_path = path
    mgr._saving = True
    mgr.mark_dirty()
    result = mgr._do_save()
    assert result is False
    assert mgr._queued is True

    mgr._saving = False
    Path(path).unlink(missing_ok=True)


# -- gather_data ---------------------------------------------------------------

def test_gather_data_returns_project_dict():
    _app()
    db, proj = _make_project()
    db.create_scene(proj.id, "S1")
    mgr = AutosaveManager(db, proj.id)
    data = mgr.gather_data()
    assert data["project"]["title"] == "AutosaveTest"
    assert len(data["scenes"]) == 1
