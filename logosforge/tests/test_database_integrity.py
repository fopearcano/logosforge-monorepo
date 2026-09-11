"""Versioned SQLite startup, durable migration backup, and FK enforcement."""
from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from logosforge.db import Database
from logosforge.db.database import (
    DB_SCHEMA_VERSION,
    SQLITE_BUSY_TIMEOUT_MS,
    UnsupportedDatabaseVersionError,
    _prepare_migration_backup,
)


def _pragma(db: Database, statement: str):
    with db._engine.connect() as conn:
        return conn.execute(text(statement)).fetchone()[0]


def test_every_connection_enables_fk_and_busy_timeout() -> None:
    db = Database()
    assert _pragma(db, "PRAGMA foreign_keys") == 1
    assert _pragma(db, "PRAGMA busy_timeout") >= SQLITE_BUSY_TIMEOUT_MS


def test_first_versioned_upgrade_preserves_exact_pre_migration_copy(tmp_path: Path) -> None:
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE legacy_marker (value TEXT)")
        conn.execute("INSERT INTO legacy_marker VALUES ('before migration')")
        conn.commit()
    db = Database(str(path))
    backup = path.with_name(path.name + f".pre-v{DB_SCHEMA_VERSION}.bak")

    with sqlite3.connect(backup) as snapshot:
        assert snapshot.execute("SELECT value FROM legacy_marker").fetchone()[0] == "before migration"
        assert snapshot.execute("PRAGMA user_version").fetchone()[0] == 0
    assert _pragma(db, "PRAGMA user_version") == DB_SCHEMA_VERSION
    assert str(_pragma(db, "PRAGMA journal_mode")).lower() == "wal"
    db._engine.dispose()

    # A normal reopen must never overwrite the original pre-migration safety copy.
    original_backup = backup.read_bytes()
    Database(str(path))._engine.dispose()
    assert backup.read_bytes() == original_backup


def test_future_database_version_is_rejected_without_touching_bytes(
    tmp_path: Path,
) -> None:
    path = tmp_path / "future.db"
    future_version = DB_SCHEMA_VERSION + 1
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE future_marker (value TEXT)")
        conn.execute("INSERT INTO future_marker VALUES ('leave untouched')")
        conn.execute(f"PRAGMA user_version = {future_version}")
        conn.commit()
    original = path.read_bytes()

    with pytest.raises(UnsupportedDatabaseVersionError) as caught:
        Database(str(path))

    assert caught.value.found == future_version
    assert caught.value.supported == DB_SCHEMA_VERSION
    assert path.read_bytes() == original
    assert not list(tmp_path.glob("future.db.pre-v*.bak"))


def test_v2_repairs_legacy_character_psyke_fk_and_detaches_orphans(
    tmp_path: Path,
) -> None:
    path = tmp_path / "legacy-character.db"
    seed = Database(str(path))
    project = seed.create_project("FK repair")
    entry = seed.create_psyke_entry(project.id, "Linked", "character")
    linked = seed.create_character(project.id, "Linked")
    orphan = seed.create_character(project.id, "Orphan")
    seed.set_character_psyke_entry(linked.id, entry.id)
    seed._engine.dispose()

    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.executescript(
            f"""
            BEGIN;
            CREATE TABLE character_legacy (
                id INTEGER NOT NULL,
                project_id INTEGER NOT NULL,
                name VARCHAR NOT NULL,
                description VARCHAR NOT NULL,
                color VARCHAR NOT NULL,
                created_at DATETIME NOT NULL,
                psyke_entry_id INTEGER,
                PRIMARY KEY (id),
                FOREIGN KEY(project_id) REFERENCES project (id)
            );
            INSERT INTO character_legacy (
                id, project_id, name, description, color, created_at, psyke_entry_id
            )
            SELECT
                id, project_id, name, description, color, created_at, psyke_entry_id
            FROM character;
            DROP TABLE character;
            ALTER TABLE character_legacy RENAME TO character;
            UPDATE character SET psyke_entry_id = 999999 WHERE id = {orphan.id};
            PRAGMA user_version = {DB_SCHEMA_VERSION - 1};
            COMMIT;
            """
        )

    upgraded = Database(str(path))
    assert upgraded.get_character_by_id(linked.id).psyke_entry_id == entry.id
    assert upgraded.get_character_by_id(orphan.id).psyke_entry_id is None
    with upgraded._engine.connect() as conn:
        character_fks = {
            (row[2], row[3], row[4])
            for row in conn.execute(text("PRAGMA foreign_key_list(character)"))
        }
        assert ("psykeentry", "psyke_entry_id", "id") in character_fks
        assert conn.execute(text("PRAGMA foreign_key_check")).fetchall() == []
    upgraded._engine.dispose()


def test_failed_character_fk_rebuild_rolls_back_and_can_retry(
    tmp_path: Path,
) -> None:
    path = tmp_path / "legacy-character-invalid.db"
    seed = Database(str(path))
    project = seed.create_project("Retry repair")
    character = seed.create_character(project.id, "Incomplete")
    seed._engine.dispose()

    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.executescript(
            f"""
            BEGIN;
            CREATE TABLE character_legacy (
                id INTEGER NOT NULL,
                project_id INTEGER NOT NULL,
                name VARCHAR NOT NULL,
                description VARCHAR,
                color VARCHAR NOT NULL,
                created_at DATETIME NOT NULL,
                psyke_entry_id INTEGER,
                PRIMARY KEY (id),
                FOREIGN KEY(project_id) REFERENCES project (id)
            );
            INSERT INTO character_legacy (
                id, project_id, name, description, color, created_at, psyke_entry_id
            )
            SELECT
                id, project_id, name, NULL, color, created_at, psyke_entry_id
            FROM character;
            DROP TABLE character;
            ALTER TABLE character_legacy RENAME TO character;
            PRAGMA user_version = {DB_SCHEMA_VERSION - 1};
            COMMIT;
            """
        )

    with pytest.raises(IntegrityError):
        Database(str(path))

    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == DB_SCHEMA_VERSION - 1
        assert conn.execute(
            "SELECT description FROM character WHERE id = ?", (character.id,)
        ).fetchone()[0] is None
        assert conn.execute(
            "SELECT 1 FROM sqlite_master"
            " WHERE type='table' AND name='character__logosforge_v2'"
        ).fetchone() is None
        conn.execute(
            "UPDATE character SET description = '' WHERE id = ?", (character.id,)
        )
        conn.commit()

    retried = Database(str(path))
    assert retried.get_character_by_id(character.id).description == ""
    with retried._engine.connect() as conn:
        character_fks = {
            (row[2], row[3], row[4])
            for row in conn.execute(text("PRAGMA foreign_key_list(character)"))
        }
        assert ("psykeentry", "psyke_entry_id", "id") in character_fks
        assert conn.execute(text("PRAGMA foreign_key_check")).fetchall() == []
    retried._engine.dispose()


def test_concurrent_backup_creation_is_first_writer_wins(tmp_path: Path) -> None:
    path = tmp_path / "legacy-race.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE legacy_marker (value TEXT)")
        conn.execute("INSERT INTO legacy_marker VALUES ('one durable snapshot')")
        conn.commit()

    workers = 8
    barrier = threading.Barrier(workers)

    def prepare():
        barrier.wait()
        return _prepare_migration_backup(path)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda _index: prepare(), range(workers)))

    backup = path.with_name(path.name + f".pre-v{DB_SCHEMA_VERSION}.bak")
    assert results == [backup] * workers
    with sqlite3.connect(backup) as snapshot:
        assert snapshot.execute("SELECT value FROM legacy_marker").fetchone()[0] == "one durable snapshot"
    assert not list(tmp_path.glob(f".{backup.name}.*.tmp"))


def test_concurrent_backup_fallback_never_exposes_a_partial_file(
    tmp_path: Path, monkeypatch,
) -> None:
    """Filesystems without hard links still get one atomically-installed copy."""
    path = tmp_path / "legacy-no-links.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE legacy_marker (value TEXT)")
        conn.execute("INSERT INTO legacy_marker VALUES ('fallback snapshot')")
        conn.commit()

    def links_unsupported(*_args, **_kwargs):
        raise OSError("hard links unavailable")

    monkeypatch.setattr("logosforge.db.database.os.link", links_unsupported)
    workers = 8
    barrier = threading.Barrier(workers)

    def prepare():
        barrier.wait()
        return _prepare_migration_backup(path)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda _index: prepare(), range(workers)))

    backup = path.with_name(path.name + f".pre-v{DB_SCHEMA_VERSION}.bak")
    assert results == [backup] * workers
    with sqlite3.connect(backup) as snapshot:
        assert snapshot.execute("SELECT value FROM legacy_marker").fetchone()[0] == "fallback snapshot"
    assert not backup.with_name(f".{backup.name}.installing").exists()
    assert not list(tmp_path.glob(f".{backup.name}.*.tmp"))


def test_project_delete_leaves_no_foreign_key_violations() -> None:
    db = Database()
    project = db.create_project("FK project")
    character = db.create_character(project.id, "Mara")
    place = db.create_place(project.id, "Harbour")
    db.create_scene(
        project.id,
        "Opening",
        character_ids=[character.id],
        place_ids=[place.id],
    )

    db.delete_project(project.id)

    with db._engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_key_check")).fetchall() == []
    assert db.get_project_by_id(project.id) is None


def test_scene_delete_cascades_owned_rows_and_detaches_optional_anchors() -> None:
    db = Database()
    project = db.create_project("Scene cascade")
    entry = db.create_psyke_entry(project.id, "Mara", "character")
    scene = db.create_scene(project.id, "Opening")
    entrance = db.create_stage_entrance_exit(scene.id)
    cue = db.create_stage_cue(scene.id)
    business = db.create_stage_business(scene.id)
    progression = db.create_psyke_progression(entry.id, "Changes", scene_id=scene.id)
    db.add_memory(project.id, scene.id, "continuity_prop", "key", "held")

    db.delete_scene(scene.id)

    assert db.get_scene_by_id(scene.id) is None
    assert db.get_stage_entrance_exit_by_id(entrance.id) is None
    assert db.get_stage_cue_by_id(cue.id) is None
    assert db.get_stage_business_by_id(business.id) is None
    assert db.get_psyke_progression_by_id(progression.id).scene_id is None
    with db._engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_key_check")).fetchall() == []


def test_character_and_psyke_deletes_detach_optional_references() -> None:
    db = Database()
    project = db.create_project("Reference cleanup")
    entry = db.create_psyke_entry(project.id, "Mara", "character")
    character = db.create_character(project.id, "Mara")
    db.set_character_psyke_entry(character.id, entry.id)
    scene = db.create_scene(project.id, "Opening", character_ids=[character.id])
    entrance = db.create_stage_entrance_exit(scene.id, character_id=character.id)
    business = db.create_stage_business(
        scene.id,
        character_id=character.id,
        prop_psyke_entry_id=entry.id,
    )
    db.create_voice_profile(character.id)
    item = db.create_gn_continuity_item(
        project.id,
        "Coat",
        linked_psyke_entry_id=entry.id,
    )

    db.delete_character(character.id)
    assert db.get_character_by_id(character.id) is None
    assert db.get_stage_entrance_exit_by_id(entrance.id).character_id is None
    assert db.get_stage_business_by_id(business.id).character_id is None

    db.delete_psyke_entry(entry.id)
    assert db.get_psyke_entry_by_id(entry.id) is None
    assert db.get_stage_business_by_id(business.id).prop_psyke_entry_id is None
    assert db.get_gn_continuity_item_by_id(item.id).linked_psyke_entry_id is None
    with db._engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_key_check")).fetchall() == []


def test_gn_page_delete_removes_panels_and_their_appearances() -> None:
    db = Database()
    project = db.create_project("GN cleanup")
    page = db.create_gn_page(project.id)
    panel = db.create_gn_panel(page.id, project_id=project.id)
    item = db.create_gn_continuity_item(project.id, "Watch")
    appearance = db.add_gn_continuity_appearance(
        item.id,
        page_id=page.id,
        panel_id=panel.id,
    )

    db.delete_gn_page(page.id)

    assert db.get_gn_page_by_id(page.id) is None
    assert db.get_gn_panel_by_id(panel.id) is None
    assert db.get_gn_continuity_appearance_by_id(appearance.id) is None


def test_episode_delete_preserves_arc_but_clears_episode_anchors() -> None:
    db = Database()
    project = db.create_project("Series cleanup")
    season = db.create_season(project.id)
    episode = db.create_episode(season.id, project_id=project.id)
    plotline = db.create_episode_plotline(episode.id, title="A story")
    arc = db.create_series_arc(
        project.id,
        title="Mystery",
        setup_episode_id=episode.id,
        payoff_episode_id=episode.id,
    )

    db.delete_episode(episode.id)

    assert db.get_episode_by_id(episode.id) is None
    assert db.get_episode_plotline_by_id(plotline.id) is None
    kept_arc = db.get_series_arc_by_id(arc.id)
    assert kept_arc is not None
    assert kept_arc.setup_episode_id is None
    assert kept_arc.payoff_episode_id is None
