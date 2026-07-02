"""Step 10 — versioning, backup, and restore safety."""

import json

import pytest

from logosforge.db import Database


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path, raising=False)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json",
                        raising=False)
    # Version snapshots live under VERSIONS_DIR (computed from CONFIG_DIR at
    # import) — redirect it to the temp dir so tests never touch real user data.
    import logosforge.version_manager as vm
    monkeypatch.setattr(vm, "VERSIONS_DIR", tmp_path / "versions", raising=False)
    yield
    settings._instance = None


def _project(db, title="P", mode="novel"):
    pid = db.create_project(title, narrative_engine=mode).id
    db.create_scene(pid, "Opening", content="Alice arrives.", act="Act I",
                    chapter="Ch1", summary="intro")
    db.create_psyke_entry(pid, "Alice", "character", notes="lead")
    db.create_note(pid, "Idea", "A note about Alice.")
    return pid


# ==========================================================================
# Versioning / snapshots
# ==========================================================================


def test_snapshot_creation():
    from logosforge.version_manager import VersionManager
    db = Database()
    pid = _project(db)
    vm = VersionManager(db, pid)
    path = vm.create_snapshot(reason="manual", label="checkpoint")
    assert path is not None and path.exists()
    versions = vm.list_versions()
    assert len(versions) == 1
    assert versions[0].reason == "manual"
    assert versions[0].label == "checkpoint"


def test_snapshot_metadata_readable():
    from logosforge.version_manager import VersionManager
    db = Database()
    pid = _project(db)
    vm = VersionManager(db, pid)
    vm.create_snapshot(reason="autosave")
    info = vm.list_versions()[0]
    assert info.display_time
    assert info.file_size_kb > 0


def test_snapshot_restore_creates_new_project_nondestructively():
    from logosforge.version_manager import VersionManager
    db = Database()
    pid = _project(db)
    vm = VersionManager(db, pid)
    path = vm.create_snapshot(reason="manual")
    before_scenes = [s.content for s in db.get_all_scenes(pid)]

    new_id = vm.restore_version(path)
    assert new_id is not None
    assert new_id != pid  # restore is non-destructive: a NEW project
    # Original project is untouched.
    assert [s.content for s in db.get_all_scenes(pid)] == before_scenes
    # Restored project has the snapshot's content.
    restored = db.get_all_scenes(new_id)
    assert any("Alice arrives" in (s.content or "") for s in restored)


def test_restore_takes_pre_restore_safety_snapshot():
    from logosforge.version_manager import VersionManager
    db = Database()
    pid = _project(db)
    vm = VersionManager(db, pid)
    path = vm.create_snapshot(reason="manual")
    vm.restore_version(path)
    reasons = [v.reason for v in vm.list_versions()]
    assert any("pre-restore" in r for r in reasons)


def test_restore_corrupt_file_returns_none_readable_error(tmp_path):
    from logosforge.version_manager import VersionManager
    db = Database()
    pid = _project(db)
    vm = VersionManager(db, pid)
    bad = tmp_path / "corrupt.json"
    bad.write_text("{ not valid json", encoding="utf-8")
    assert vm.load_version_data(bad) is None
    assert vm.restore_version(bad) is None  # surfaced as None -> UI shows error


def test_versions_are_per_project_no_leak():
    from logosforge.version_manager import VersionManager
    db = Database()
    pid_a = _project(db, "A")
    pid_b = _project(db, "B")
    vm = VersionManager(db, pid_a)
    vm.create_snapshot(reason="manual", label="A-snap")
    assert len(vm.list_versions()) == 1
    # Switching to project B shows B's (empty) history, not A's.
    vm.set_project(pid_b)
    assert vm.list_versions() == []


# ==========================================================================
# Backup / full export
# ==========================================================================


def test_backup_includes_all_story_data():
    from logosforge.data_export import build_full_export
    db = Database()
    pid = _project(db, mode="screenplay")
    data = build_full_export(db, pid)
    assert data.get("project")
    assert data.get("scenes")
    assert data.get("psyke_entries")
    assert data.get("notes")
    assert "outline" in data
    assert "plot" in data
    assert "timeline" in data


def test_backup_excludes_api_keys():
    from logosforge.data_export import build_full_export, to_json
    db = Database()
    pid = _project(db)
    blob = to_json(build_full_export(db, pid))
    lower = blob.lower()
    assert "api_key" not in lower
    assert "ai_api_key" not in lower
    assert "anthropic" not in lower and "sk-" not in blob


def test_backup_handles_empty_project_cleanly():
    from logosforge.data_export import build_full_export
    db = Database()
    pid = db.create_project("Empty", narrative_engine="novel").id
    data = build_full_export(db, pid)  # must not raise
    assert data.get("project")
    assert data.get("scenes") == []


# ==========================================================================
# Restore / import roundtrip
# ==========================================================================


def test_import_roundtrip_preserves_content():
    from logosforge.data_export import build_full_export
    from logosforge.import_data import import_json, validate_import_data
    db = Database()
    pid = _project(db)
    raw = json.dumps(build_full_export(db, pid))
    data, err = validate_import_data(raw)
    assert data is not None and err == ""
    new_id = import_json(db, data)
    assert new_id != pid
    assert any("Alice arrives" in (s.content or "")
               for s in db.get_all_scenes(new_id))
    assert any(e.name == "Alice" for e in db.get_all_psyke_entries(new_id))


def test_import_rejects_invalid_json():
    from logosforge.import_data import validate_import_data
    data, err = validate_import_data("}{ not json")
    assert data is None
    assert err  # readable error string


# ==========================================================================
# UI wiring: restore refreshes via project switch
# ==========================================================================


def test_main_window_restore_switches_project():
    import inspect
    from logosforge.ui.main_window import MainWindow
    src = inspect.getsource(MainWindow._on_version_history)
    # Restore must route through _switch_project so the whole UI refreshes and
    # no stale state from the previous project remains.
    assert "_switch_project" in src
    assert "restored_project_id" in src
