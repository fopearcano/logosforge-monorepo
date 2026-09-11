"""Upgrade real, sanitized Whiteboard and Pro databases as immutable goldens."""
from __future__ import annotations

import hashlib
import shutil
import sqlite3
from pathlib import Path

import pytest
from sqlmodel import SQLModel

from logosforge.db import Database
from logosforge.db.database import DB_SCHEMA_VERSION


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "database_upgrades"
GOLDEN_DATABASES = (
    (
        "whiteboard-released-unversioned.sqlite3",
        "3C7860ACEB884552B116A209923337F0684AFD77F231E4181B2FF1BFA0FC3491",
        8,
        0,
        "Whiteboard Golden Project 01",
    ),
    (
        "pro-previous-unversioned.sqlite3",
        "514EB6EF3A1E230AFB464F3005C5245AD8234021E0F86687FAE479644EA4B984",
        1,
        1,
        "Pro Golden Project 01",
    ),
)


def _readonly_connection(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.resolve().as_posix()}?mode=ro&immutable=1"
    return sqlite3.connect(uri, uri=True)


def _logical_dump(path: Path) -> list[str]:
    with _readonly_connection(path) as conn:
        return list(conn.iterdump())


def _model_foreign_keys() -> set[tuple[str, str, str, str]]:
    return {
        (
            table.name,
            foreign_key.parent.name,
            foreign_key.column.table.name,
            foreign_key.column.name,
        )
        for table in SQLModel.metadata.tables.values()
        for foreign_key in table.foreign_keys
    }


def _database_foreign_keys(conn: sqlite3.Connection) -> set[tuple[str, str, str, str]]:
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master"
            " WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    ]
    found: set[tuple[str, str, str, str]] = set()
    for table in tables:
        quoted = '"' + table.replace('"', '""') + '"'
        found.update(
            (table, row[3], row[2], row[4])
            for row in conn.execute(f"PRAGMA foreign_key_list({quoted})")
        )
    return found


@pytest.mark.parametrize(
    ("filename", "sha256", "project_count", "scene_count", "first_title"),
    GOLDEN_DATABASES,
)
def test_real_database_golden_upgrades_without_data_loss(
    tmp_path: Path,
    filename: str,
    sha256: str,
    project_count: int,
    scene_count: int,
    first_title: str,
) -> None:
    fixture = FIXTURE_DIR / filename
    fixture_bytes = fixture.read_bytes()
    assert hashlib.sha256(fixture_bytes).hexdigest().upper() == sha256
    with _readonly_connection(fixture) as source:
        assert source.execute("PRAGMA user_version").fetchone()[0] == 0
        assert source.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert source.execute("PRAGMA foreign_key_check").fetchall() == []
        assert source.execute("SELECT COUNT(*) FROM project").fetchone()[0] == project_count
        assert source.execute("SELECT COUNT(*) FROM scene").fetchone()[0] == scene_count

    target = tmp_path / filename
    shutil.copyfile(fixture, target)
    db = Database(str(target))
    projects = db.get_all_projects()
    assert len(projects) == project_count
    assert projects[0].title == first_title
    scenes = [
        scene
        for project in projects
        for scene in db.get_all_scenes(project.id)
    ]
    assert len(scenes) == scene_count
    if scenes:
        assert scenes[0].title == "Golden Scene"
        assert scenes[0].content == "Golden fixture manuscript."

    smoke_project = db.create_project("Post-upgrade smoke")
    smoke_scene = db.create_scene(smoke_project.id, "Writable scene")
    assert db.get_scene_by_id(smoke_scene.id).title == "Writable scene"
    db._engine.dispose()

    backup = target.with_name(target.name + f".pre-v{DB_SCHEMA_VERSION}.bak")
    assert backup.exists()
    assert _logical_dump(backup) == _logical_dump(fixture)
    with _readonly_connection(backup) as snapshot:
        assert snapshot.execute("PRAGMA user_version").fetchone()[0] == 0

    with sqlite3.connect(target) as upgraded:
        assert upgraded.execute("PRAGMA user_version").fetchone()[0] == DB_SCHEMA_VERSION
        assert upgraded.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert upgraded.execute("PRAGMA foreign_key_check").fetchall() == []
        assert _database_foreign_keys(upgraded) == _model_foreign_keys()

    backup_bytes = backup.read_bytes()
    Database(str(target))._engine.dispose()
    assert backup.read_bytes() == backup_bytes
    assert fixture.read_bytes() == fixture_bytes
