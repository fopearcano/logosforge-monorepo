"""Tests for the PSYKE theatre/performance-memory layer (Stage Script)."""

import pytest

from logosforge.db import Database
from logosforge.models import THEATRE_RELATION_TYPES
from logosforge.psyke_theatre import (
    CHARACTER_THEATRE_FIELDS,
    PROP_MEMORY_FIELDS,
    SET_MEMORY_FIELDS,
    build_theatre_memory_context,
    get_theatre_memory,
    set_theatre_memory,
    theatre_fields_for_type,
)


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    yield
    settings._instance = None


def _play(db):
    return db.create_project(
        "Play", narrative_engine="stage_script",
        default_writing_format="stage_script",
    )


# =========================================================================
# 1. Field schemas (§1, §2, §3)
# =========================================================================

def test_character_theatre_fields():
    for f in (
        "stage_objective", "spoken_strategy", "subtext_strategy",
        "physical_business", "gesture_vocabulary", "stage_presence",
        "relationship_pressure", "offstage_knowledge",
    ):
        assert f in CHARACTER_THEATRE_FIELDS


def test_set_memory_fields():
    for f in (
        "stage_layout", "entrances", "exits", "levels",
        "props_available", "audience_visibility", "spatial_constraints",
    ):
        assert f in SET_MEMORY_FIELDS


def test_prop_memory_fields():
    for f in (
        "prop_status", "owner_character_id", "first_appearance",
        "use_in_scene", "continuity_notes",
    ):
        assert f in PROP_MEMORY_FIELDS


def test_fields_for_type():
    assert theatre_fields_for_type("character") == CHARACTER_THEATRE_FIELDS
    assert theatre_fields_for_type("place") == SET_MEMORY_FIELDS
    assert theatre_fields_for_type("object") == PROP_MEMORY_FIELDS
    assert theatre_fields_for_type("theme") == ()


# =========================================================================
# 2. Character theatre memory persists (§1, §6)
# =========================================================================

def test_character_theatre_memory_persists():
    db = Database()
    p = _play(db)
    e = db.create_psyke_entry(p.id, "Hamlet", entry_type="character")
    set_theatre_memory(db, e.id, stage_objective="expose the king",
                       spoken_strategy="feign madness")
    tm = get_theatre_memory(db, e.id)
    assert tm["stage_objective"] == "expose the king"
    assert tm["spoken_strategy"] == "feign madness"


def test_theatre_memory_merges():
    db = Database()
    p = _play(db)
    e = db.create_psyke_entry(p.id, "Hamlet", entry_type="character")
    set_theatre_memory(db, e.id, stage_objective="x")
    set_theatre_memory(db, e.id, offstage_knowledge="knows the truth")
    tm = get_theatre_memory(db, e.id)
    assert tm["stage_objective"] == "x"
    assert tm["offstage_knowledge"] == "knows the truth"


def test_theatre_does_not_clobber_visual_or_details():
    db = Database()
    p = _play(db)
    e = db.create_psyke_entry(
        p.id, "Hamlet", entry_type="character", details={"role": "lead"},
    )
    db.set_psyke_visual_memory(e.id, {"silhouette": "lean"})
    set_theatre_memory(db, e.id, stage_objective="x")
    details = db.get_psyke_entry_details(e.id)
    assert details["role"] == "lead"
    assert details["visual"]["silhouette"] == "lean"
    assert details["theatre"]["stage_objective"] == "x"


def test_empty_clears_key():
    db = Database()
    p = _play(db)
    e = db.create_psyke_entry(p.id, "Hamlet", entry_type="character")
    set_theatre_memory(db, e.id, stage_objective="x")
    set_theatre_memory(db, e.id, stage_objective="")
    assert "stage_objective" not in get_theatre_memory(db, e.id)


# =========================================================================
# 3. Set memory + prop continuity persist (§2, §3, §6)
# =========================================================================

def test_set_memory_persists():
    db = Database()
    p = _play(db)
    e = db.create_psyke_entry(p.id, "Throne Room", entry_type="place")
    set_theatre_memory(db, e.id, stage_layout="raised dais",
                       spatial_constraints="no upstage exit")
    tm = get_theatre_memory(db, e.id)
    assert tm["stage_layout"] == "raised dais"
    assert tm["spatial_constraints"] == "no upstage exit"


def test_prop_continuity_persists():
    db = Database()
    p = _play(db)
    hamlet = db.create_psyke_entry(p.id, "Hamlet", entry_type="character")
    skull = db.create_psyke_entry(p.id, "Skull", entry_type="object")
    set_theatre_memory(db, skull.id, prop_status="clean",
                       owner_character_id=hamlet.id,
                       continuity_notes="cracked in Act 5")
    tm = get_theatre_memory(db, skull.id)
    assert tm["prop_status"] == "clean"
    assert tm["owner_character_id"] == hamlet.id
    assert tm["continuity_notes"] == "cracked in Act 5"


def test_theatre_memory_reloads_from_disk(tmp_path):
    path = str(tmp_path / "play.db")
    db = Database(path)
    p = _play(db)
    e = db.create_psyke_entry(p.id, "Hamlet", entry_type="character")
    set_theatre_memory(db, e.id, stage_objective="revenge",
                       physical_business="toys with a dagger")
    eid = e.id
    db2 = Database(path)
    tm = get_theatre_memory(db2, eid)
    assert tm["stage_objective"] == "revenge"
    assert tm["physical_business"] == "toys with a dagger"


# =========================================================================
# 4. Relation extensions (§4)
# =========================================================================

def test_theatre_relation_types_defined():
    for t in ("pressures", "confronts", "avoids", "dominates",
              "submits", "deceives", "overhears", "interrupts"):
        assert t in THEATRE_RELATION_TYPES


def test_dominates_submits_inverse():
    db = Database()
    p = _play(db)
    a = db.create_psyke_entry(p.id, "King", entry_type="character")
    b = db.create_psyke_entry(p.id, "Servant", entry_type="character")
    db.add_psyke_relation(a.id, b.id, relation_type="dominates")
    a_rel = dict((e.name, t) for e, t in db.get_typed_related_psyke_entries(a.id))
    b_rel = dict((e.name, t) for e, t in db.get_typed_related_psyke_entries(b.id))
    assert a_rel["Servant"] == "dominates"
    assert b_rel["King"] == "submits"


def test_directional_relation_stored():
    db = Database()
    p = _play(db)
    a = db.create_psyke_entry(p.id, "A", entry_type="character")
    b = db.create_psyke_entry(p.id, "B", entry_type="character")
    db.add_psyke_relation(a.id, b.id, relation_type="overhears")
    rels = dict((e.name, t) for e, t in db.get_typed_related_psyke_entries(a.id))
    assert rels["B"] == "overhears"


# =========================================================================
# 5. Assistant context (§5)
# =========================================================================

def _populated(db):
    p = _play(db)
    hamlet = db.create_psyke_entry(p.id, "Hamlet", entry_type="character")
    claudius = db.create_psyke_entry(p.id, "Claudius", entry_type="character")
    hall = db.create_psyke_entry(p.id, "Throne Room", entry_type="place")
    skull = db.create_psyke_entry(p.id, "Skull", entry_type="object")
    ch = db.create_character(p.id, "Hamlet")
    set_theatre_memory(db, hamlet.id, stage_objective="expose the king",
                       offstage_knowledge="the ghost spoke truth")
    set_theatre_memory(db, hall.id, spatial_constraints="no upstage exit")
    set_theatre_memory(db, skull.id, prop_status="clean",
                       owner_character_id=hamlet.id)
    db.add_psyke_relation(hamlet.id, claudius.id, relation_type="confronts")
    s = db.create_scene(p.id, "Act 5",
                        audience_visibility_notes="grave hidden behind set")
    db.create_stage_entrance_exit(s.id, character_id=ch.id, type="entrance")
    return p


def test_context_includes_all_facets():
    db = Database()
    p = _populated(db)
    ctx = build_theatre_memory_context(db, p.id)
    assert ctx.startswith("[Theatre Memory]")
    assert "Who wants what" in ctx and "expose the king" in ctx
    assert "Who pressures whom" in ctx and "confronts" in ctx
    assert "Who knows what" in ctx and "ghost spoke truth" in ctx
    assert "Who enters/exits" in ctx
    assert "Props that matter" in ctx and "Skull" in ctx
    assert "Staging concerns" in ctx and "grave hidden" in ctx


def test_context_empty_when_no_theatre_data():
    db = Database()
    p = _play(db)
    db.create_psyke_entry(p.id, "Bare", entry_type="character")
    assert build_theatre_memory_context(db, p.id) == ""


def test_pressure_dedup():
    db = Database()
    p = _play(db)
    a = db.create_psyke_entry(p.id, "A", entry_type="character")
    b = db.create_psyke_entry(p.id, "B", entry_type="character")
    db.add_psyke_relation(a.id, b.id, relation_type="deceives")
    ctx = build_theatre_memory_context(db, p.id)
    # The deceives relation is reported once, not once per direction.
    assert ctx.count("deceives") == 1


# =========================================================================
# 6. Assistant integration (§5, §6)
# =========================================================================

def test_assistant_context_sees_theatre_metadata():
    from logosforge.ui.assistant_view import AssistantPanel
    db = Database()
    p = _populated(db)
    db.create_scene(p.id, "Scene", content="x")
    panel = AssistantPanel(db, p.id)
    structural = panel._build_context()[8]
    assert "[Theatre Memory]" in structural
    assert "expose the king" in structural


def test_novel_project_no_theatre_context():
    from logosforge.ui.assistant_view import AssistantPanel
    db = Database()
    p = db.create_project("Novel")
    e = db.create_psyke_entry(p.id, "X", entry_type="character")
    set_theatre_memory(db, e.id, stage_objective="y")
    db.create_scene(p.id, "Chapter 1", content="x")
    panel = AssistantPanel(db, p.id)
    assert "[Theatre Memory]" not in panel._build_context()[8]
