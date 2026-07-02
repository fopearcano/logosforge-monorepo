"""Stored Character <-> PSYKE foreign key: additive migration on legacy DBs,
idempotent backfill, the setter, and the dashboard preferring the stored link.
See memory ``logosforge-pro-writer-qa``."""

import sqlite3

from logosforge.db import Database
from logosforge.narrative_dashboard import compute_dashboard


def test_legacy_db_gains_psyke_entry_id_column(tmp_path):
    """A pre-existing character table (no psyke_entry_id) gets the nullable column
    added on open, with existing rows preserved."""
    path = str(tmp_path / "legacy.db")
    c = sqlite3.connect(path)
    c.execute(
        "CREATE TABLE character (id INTEGER PRIMARY KEY, project_id INTEGER, "
        "name TEXT, description TEXT, color TEXT, created_at TEXT)"
    )
    c.execute("INSERT INTO character (id, project_id, name) VALUES (1, 1, 'Legacy')")
    c.commit()
    c.close()

    Database(path)  # _migrate() runs on open

    c = sqlite3.connect(path)
    cols = {r[1] for r in c.execute("PRAGMA table_info(character)").fetchall()}
    assert "psyke_entry_id" in cols
    assert c.execute("SELECT name FROM character WHERE id=1").fetchone()[0] == "Legacy"
    c.close()


def test_backfill_links_and_is_idempotent():
    db = Database()
    p = db.create_project("T", narrative_engine="screenplay")
    e = db.create_psyke_entry(p.id, "Mara Voss", entry_type="character")
    db.create_character(p.id, "Mara")
    assert db.get_all_characters(p.id)[0].psyke_entry_id is None
    assert db.backfill_character_psyke_links(p.id) == 1
    assert db.get_all_characters(p.id)[0].psyke_entry_id == e.id
    assert db.backfill_character_psyke_links(p.id) == 0  # idempotent: nothing new

    # A character with no matching bible entry stays NULL (no false-merge).
    db.create_character(p.id, "Zander")
    assert db.backfill_character_psyke_links(p.id) == 0
    zander = next(c for c in db.get_all_characters(p.id) if c.name == "Zander")
    assert zander.psyke_entry_id is None


def test_setter_sets_and_clears():
    db = Database()
    p = db.create_project("T")
    e = db.create_psyke_entry(p.id, "Mara Voss", entry_type="character")
    ch = db.create_character(p.id, "Mara")
    db.set_character_psyke_entry(ch.id, e.id)
    assert db.get_all_characters(p.id)[0].psyke_entry_id == e.id
    db.set_character_psyke_entry(ch.id, None)
    assert db.get_all_characters(p.id)[0].psyke_entry_id is None


def test_deleting_psyke_entry_unlinks_character():
    """Deleting a bible entry must UNLINK (not delete) any bound Character, leaving
    no dangling psyke_entry_id."""
    db = Database()
    p = db.create_project("T")
    e = db.create_psyke_entry(p.id, "Mara Voss", entry_type="character")
    ch = db.create_character(p.id, "Mara")
    db.set_character_psyke_entry(ch.id, e.id)
    db.delete_psyke_entry(e.id)
    chars = db.get_all_characters(p.id)
    assert len(chars) == 1                 # the Character survives the entry deletion
    assert chars[0].psyke_entry_id is None  # and is cleanly unlinked (no dangling FK)


def test_dashboard_prefers_stored_link():
    db = Database()
    p = db.create_project("T", narrative_engine="screenplay")
    db.create_psyke_entry(p.id, "Mara Voss", entry_type="character")  # no alias
    ch = db.create_character(p.id, "Mara")
    for i in range(3):  # linked but never NAMED in prose
        db.create_scene(
            p.id, f"INT. ROOM {i} - NIGHT", content="A room.", character_ids=[ch.id],
        )
    dash = compute_dashboard(db, p.id)  # lazy backfill + stored-link fold
    mv = next(c for c in dash.characters if c.name == "Mara Voss")
    assert len(mv.present_scenes) == 3
    # the lazy backfill on first dashboard open should have written the link
    assert db.get_all_characters(p.id)[0].psyke_entry_id is not None
