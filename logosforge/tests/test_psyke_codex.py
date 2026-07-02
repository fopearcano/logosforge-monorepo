"""Tests for PSYKE Codex parity features (STEP 1)."""

import json

from logosforge.db import Database
from logosforge.context_builder import gather_psyke_context
from logosforge.models.psyke_details import FieldSpec, get_detail_schema


# -- Detail schema -----------------------------------------------------------

def test_get_detail_schema_character():
    schema = get_detail_schema("character")
    assert len(schema) >= 20
    keys = [f.key for f in schema]
    assert "full_name" in keys
    assert "personality" in keys
    assert "arc" in keys
    assert "appearance" in keys
    for f in schema:
        assert isinstance(f, FieldSpec)
        assert f.widget in ("line", "multiline", "combo")
        assert f.max_chars > 0 or f.widget == "combo"


def test_get_detail_schema_place():
    schema = get_detail_schema("place")
    assert len(schema) >= 15
    keys = [f.key for f in schema]
    assert "climate" in keys
    assert "atmosphere" in keys
    assert "history" in keys


def test_get_detail_schema_object():
    schema = get_detail_schema("object")
    assert len(schema) >= 10
    keys = [f.key for f in schema]
    assert "appearance" in keys
    assert "function" in keys


def test_get_detail_schema_lore():
    schema = get_detail_schema("lore")
    assert len(schema) >= 10
    keys = [f.key for f in schema]
    assert "summary" in keys
    assert "rules" in keys


def test_get_detail_schema_theme():
    schema = get_detail_schema("theme")
    assert len(schema) >= 8
    assert schema[0].key == "statement"


def test_get_detail_schema_other():
    schema = get_detail_schema("other")
    assert len(schema) >= 3


def test_get_detail_schema_unknown():
    assert get_detail_schema("nonexistent") == []


# -- details_json round trip -------------------------------------------------

def test_details_json_create_and_read():
    db = Database()
    proj = db.create_project("Test")
    details = {"appearance": "Tall and dark", "voice": "Deep baritone"}
    entry = db.create_psyke_entry(
        proj.id, "Gandalf", entry_type="character", details=details,
    )
    loaded = db.get_psyke_entry_details(entry.id)
    assert loaded == details


def test_details_json_update():
    db = Database()
    proj = db.create_project("Test")
    entry = db.create_psyke_entry(proj.id, "Rivendell", entry_type="place")
    assert db.get_psyke_entry_details(entry.id) == {}

    new_details = {"climate": "Temperate", "atmosphere": "Serene and ancient"}
    db.update_psyke_entry(
        entry.id, "Rivendell", entry_type="place", details=new_details,
    )
    assert db.get_psyke_entry_details(entry.id) == new_details


def test_details_json_none_on_update_preserves():
    db = Database()
    proj = db.create_project("Test")
    details = {"summary": "Ancient magic system"}
    entry = db.create_psyke_entry(
        proj.id, "The Source", entry_type="lore", details=details,
    )
    db.update_psyke_entry(entry.id, "The Source", entry_type="lore", notes="updated")
    assert db.get_psyke_entry_details(entry.id) == details


def test_details_json_empty_string_returns_empty_dict():
    db = Database()
    proj = db.create_project("Test")
    entry = db.create_psyke_entry(proj.id, "Plain", entry_type="other")
    assert db.get_psyke_entry_details(entry.id) == {}


def test_details_json_invalid_json_returns_empty_dict():
    db = Database()
    proj = db.create_project("Test")
    entry = db.create_psyke_entry(proj.id, "Broken", entry_type="other")
    from sqlmodel import Session
    from logosforge.models import PsykeEntry
    with Session(db._engine) as session:
        row = session.get(PsykeEntry, entry.id)
        row.details_json = "not valid json{{"
        session.commit()
    assert db.get_psyke_entry_details(entry.id) == {}


def test_details_json_nonexistent_entry():
    db = Database()
    assert db.get_psyke_entry_details(9999) == {}


# -- details_json in export/import ------------------------------------------

def test_details_export_import_roundtrip():
    db = Database()
    proj = db.create_project("Test")
    details = {"appearance": "Silver hair", "goals": "Defeat Sauron"}
    db.create_psyke_entry(
        proj.id, "Gandalf", entry_type="character", details=details,
    )

    from logosforge.export import export_json
    from logosforge.import_data import import_json, validate_import_data

    exported = export_json(db, proj.id)
    data, err = validate_import_data(exported)
    assert data is not None, err

    new_pid = import_json(db, data)
    entries = db.get_all_psyke_entries(new_pid)
    assert len(entries) == 1
    loaded = db.get_psyke_entry_details(entries[0].id)
    assert loaded == details


# -- Relation cascade --------------------------------------------------------

def _setup_relation_graph(db, project_id):
    """Creates: A -related- B -related- C -related- D (chain of 3 hops)."""
    a = db.create_psyke_entry(project_id, "Alpha", entry_type="character")
    b = db.create_psyke_entry(project_id, "Bravo", entry_type="character")
    c = db.create_psyke_entry(project_id, "Charlie", entry_type="character")
    d = db.create_psyke_entry(project_id, "Delta", entry_type="character")
    db.add_psyke_relation(a.id, b.id)
    db.add_psyke_relation(b.id, c.id)
    db.add_psyke_relation(c.id, d.id)
    return a, b, c, d


def test_relation_cascade_depth_cap():
    db = Database()
    proj = db.create_project("Test")
    a, b, c, d = _setup_relation_graph(db, proj.id)

    scene = db.create_scene(proj.id, "Test Scene", content=f"Alpha is here.")

    ctx = gather_psyke_context(db, proj.id, scene.id)
    assert "Alpha" in ctx
    # B is depth 1 from Alpha, C is depth 2 — both should appear as related
    assert "Bravo" in ctx
    assert "Charlie" in ctx
    # D is depth 3 — should NOT appear (depth cap is 2)
    assert "Delta" not in ctx


def test_relation_cascade_cycles():
    db = Database()
    proj = db.create_project("Test")
    a = db.create_psyke_entry(proj.id, "Yin", entry_type="character")
    b = db.create_psyke_entry(proj.id, "Yang", entry_type="character")
    db.add_psyke_relation(a.id, b.id)
    # Both directions already stored, so this is a cycle (A↔B)

    scene = db.create_scene(proj.id, "Test Scene", content="Yin appears here.")
    ctx = gather_psyke_context(db, proj.id, scene.id)
    assert "Yin" in ctx
    assert "Yang" in ctx


def test_relation_cascade_no_progression_for_related():
    db = Database()
    proj = db.create_project("Test")
    a = db.create_psyke_entry(proj.id, "Hero", entry_type="character")
    b = db.create_psyke_entry(proj.id, "Mentor", entry_type="character", notes="Wise elder")
    db.add_psyke_relation(a.id, b.id)
    db.create_psyke_progression(b.id, "Mentor dies tragically")

    scene = db.create_scene(proj.id, "Test Scene", content="Hero walks in.")
    ctx = gather_psyke_context(db, proj.id, scene.id)
    assert "Mentor" in ctx
    # Related entries should NOT have progression text
    assert "dies tragically" not in ctx


def test_related_section_label():
    db = Database()
    proj = db.create_project("Test")
    a = db.create_psyke_entry(proj.id, "Frodo", entry_type="character")
    b = db.create_psyke_entry(proj.id, "Sam", entry_type="character")
    db.add_psyke_relation(a.id, b.id)

    scene = db.create_scene(proj.id, "Test", content="Frodo is here.")
    ctx = gather_psyke_context(db, proj.id, scene.id)
    assert "Relevant:" in ctx
    assert "Related:" in ctx


def test_globals_not_duplicated_in_related():
    db = Database()
    proj = db.create_project("Test")
    a = db.create_psyke_entry(proj.id, "Hero", entry_type="character")
    g = db.create_psyke_entry(proj.id, "WorldRule", entry_type="lore", is_global=True)
    db.add_psyke_relation(a.id, g.id)

    scene = db.create_scene(proj.id, "Test", content="Hero enters.")
    ctx = gather_psyke_context(db, proj.id, scene.id)
    assert ctx.count("WorldRule") == 1


# -- Details in AI context ---------------------------------------------------

def test_details_appear_in_context():
    db = Database()
    proj = db.create_project("Test")
    details = {"appearance": "Silver hair", "voice": "Deep and calm"}
    db.create_psyke_entry(
        proj.id, "Wizard", entry_type="character", details=details,
    )
    scene = db.create_scene(proj.id, "Scene 1", content="The Wizard appeared.")
    ctx = gather_psyke_context(db, proj.id, scene.id)
    assert "Silver hair" in ctx
    assert "Deep and calm" in ctx


# -- Migration ---------------------------------------------------------------

def test_migration_idempotent():
    db = Database()
    # Running _migrate again should not fail
    db._migrate()
    db._migrate()
    proj = db.create_project("Test")
    entry = db.create_psyke_entry(proj.id, "Test", details={"key": "val"})
    assert db.get_psyke_entry_details(entry.id) == {"key": "val"}


# -- Highlighter regex -------------------------------------------------------

def test_highlighter_pattern_compilation():
    """Verify PsykeHighlighter compiles patterns without error."""
    from logosforge.ui.psyke_highlighter import PsykeHighlighter
    from PySide6.QtGui import QTextDocument

    doc = QTextDocument()
    hl = PsykeHighlighter(doc)
    hl.refresh_patterns(["Gandalf", "Frodo Baggins", "The One Ring"])
    assert hl._pattern is not None
    assert hl._pattern.search("Gandalf was here")
    assert hl._pattern.search("Frodo Baggins walked")
    assert not hl._pattern.search("Gandalfx")

    hl.refresh_patterns([])
    assert hl._pattern is None
