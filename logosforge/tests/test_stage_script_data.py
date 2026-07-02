"""Tests for Stage Script data structures (scene fields, entrances/exits,
cues, stage business)."""

import pytest

from logosforge.db import Database
from logosforge.models import (
    Scene,
    StageBusiness,
    StageCue,
    StageEntranceExit,
)


def _play(db):
    return db.create_project(
        "Play", narrative_engine="stage_script",
        default_writing_format="stage_script",
    )


# =========================================================================
# 1. Scene model extensions (§1)
# =========================================================================

def test_scene_has_stage_fields():
    fields = Scene.model_fields
    for f in (
        "stage_location", "set_description", "scene_objective",
        "entrance_exit_notes", "prop_notes", "cue_notes",
        "offstage_events", "audience_visibility_notes",
        "performance_duration_minutes",
    ):
        assert f in fields


def test_stage_fields_persist():
    db = Database()
    p = _play(db)
    s = db.create_scene(
        p.id, "Act 1",
        stage_location="Elsinore", set_description="fog and torchlight",
        scene_objective="warn the prince", entrance_exit_notes="guards enter",
        prop_notes="skull on plinth", cue_notes="thunder before line 3",
        offstage_events="the king dies offstage",
        audience_visibility_notes="ghost hidden until reveal",
        performance_duration_minutes=12,
    )
    loaded = db.get_scene_by_id(s.id)
    assert loaded.stage_location == "Elsinore"
    assert loaded.set_description == "fog and torchlight"
    assert loaded.scene_objective == "warn the prince"
    assert loaded.entrance_exit_notes == "guards enter"
    assert loaded.prop_notes == "skull on plinth"
    assert loaded.cue_notes == "thunder before line 3"
    assert loaded.offstage_events == "the king dies offstage"
    assert loaded.audience_visibility_notes == "ghost hidden until reveal"
    assert loaded.performance_duration_minutes == 12


def test_stage_fields_default_empty():
    db = Database()
    p = _play(db)
    s = db.create_scene(p.id, "Plain")
    loaded = db.get_scene_by_id(s.id)
    assert loaded.stage_location == ""
    assert loaded.performance_duration_minutes == 0


def test_update_scene_stage_fields():
    db = Database()
    p = _play(db)
    s = db.create_scene(p.id, "Act 1")
    db.update_scene(s.id, "Act 1", scene_objective="seize the throne",
                    performance_duration_minutes=8)
    loaded = db.get_scene_by_id(s.id)
    assert loaded.scene_objective == "seize the throne"
    assert loaded.performance_duration_minutes == 8


def test_update_scene_leaves_stage_fields_unchanged_when_none():
    db = Database()
    p = _play(db)
    s = db.create_scene(p.id, "Act 1", stage_location="Elsinore")
    db.update_scene(s.id, "Act 1")  # stage_location not passed → unchanged
    assert db.get_scene_by_id(s.id).stage_location == "Elsinore"


# =========================================================================
# 2. Entrance / Exit (§2)
# =========================================================================

def test_entrance_exit_persists():
    db = Database()
    p = _play(db)
    c = db.create_character(p.id, "HAMLET")
    s = db.create_scene(p.id, "Act 1")
    ee = db.create_stage_entrance_exit(
        s.id, character_id=c.id, type="entrance", cue_text="thunder",
        notes="from stage left",
    )
    rows = db.get_stage_entrances_exits(s.id)
    assert len(rows) == 1
    assert rows[0].type == "entrance"
    assert rows[0].character_id == c.id
    assert rows[0].cue_text == "thunder"


def test_entrance_exit_ordering():
    db = Database()
    p = _play(db)
    s = db.create_scene(p.id, "Act 1")
    db.create_stage_entrance_exit(s.id, type="entrance")
    db.create_stage_entrance_exit(s.id, type="exit")
    db.create_stage_entrance_exit(s.id, type="entrance")
    rows = db.get_stage_entrances_exits(s.id)
    assert [r.moment_order for r in rows] == [0, 1, 2]
    assert [r.type for r in rows] == ["entrance", "exit", "entrance"]


def test_delete_entrance_exit():
    db = Database()
    p = _play(db)
    s = db.create_scene(p.id, "Act 1")
    a = db.create_stage_entrance_exit(s.id, type="entrance")
    db.create_stage_entrance_exit(s.id, type="exit")
    db.delete_stage_entrance_exit(a.id)
    rows = db.get_stage_entrances_exits(s.id)
    assert [r.type for r in rows] == ["exit"]


# =========================================================================
# 3. Cues (§3)
# =========================================================================

def test_cue_persists():
    db = Database()
    p = _play(db)
    s = db.create_scene(p.id, "Act 1")
    db.create_stage_cue(s.id, cue_type="light", cue_text="dim to blue",
                        notes="slow fade")
    rows = db.get_stage_cues(s.id)
    assert len(rows) == 1
    assert rows[0].cue_type == "light"
    assert rows[0].cue_text == "dim to blue"


def test_cues_ordered():
    db = Database()
    p = _play(db)
    s = db.create_scene(p.id, "Act 1")
    for t in ("light", "sound", "music", "movement"):
        db.create_stage_cue(s.id, cue_type=t)
    rows = db.get_stage_cues(s.id)
    assert [r.cue_type for r in rows] == ["light", "sound", "music", "movement"]
    assert [r.moment_order for r in rows] == [0, 1, 2, 3]


# =========================================================================
# 4. Stage business — references a PSYKE object (§4)
# =========================================================================

def test_stage_business_uses_psyke_object():
    db = Database()
    p = _play(db)
    c = db.create_character(p.id, "HAMLET")
    prop = db.create_psyke_entry(p.id, "Skull", entry_type="object")
    s = db.create_scene(p.id, "Act 5")
    biz = db.create_stage_business(
        s.id, prop_psyke_entry_id=prop.id, character_id=c.id,
        stage_action="lifts the skull", continuity_note="held in right hand",
    )
    rows = db.get_stage_business(s.id)
    assert len(rows) == 1
    assert rows[0].prop_psyke_entry_id == prop.id   # PSYKE object, not duplicated
    assert rows[0].character_id == c.id
    assert rows[0].stage_action == "lifts the skull"
    assert rows[0].continuity_note == "held in right hand"


def test_stage_business_ordered():
    db = Database()
    p = _play(db)
    s = db.create_scene(p.id, "Act 1")
    db.create_stage_business(s.id, stage_action="a")
    db.create_stage_business(s.id, stage_action="b")
    rows = db.get_stage_business(s.id)
    assert [r.stage_action for r in rows] == ["a", "b"]


# =========================================================================
# 5. Reload + backward compatibility (§5)
# =========================================================================

def test_reload_from_disk(tmp_path):
    path = str(tmp_path / "play.db")
    db = Database(path)
    p = _play(db)
    c = db.create_character(p.id, "HAMLET")
    prop = db.create_psyke_entry(p.id, "Skull", entry_type="object")
    s = db.create_scene(p.id, "Act 5", stage_location="graveyard",
                        performance_duration_minutes=15)
    db.create_stage_entrance_exit(s.id, character_id=c.id, type="entrance")
    db.create_stage_cue(s.id, cue_type="sound", cue_text="bell tolls")
    db.create_stage_business(s.id, prop_psyke_entry_id=prop.id,
                             stage_action="lifts skull")
    sid = s.id

    # Reopen with a fresh Database instance.
    db2 = Database(path)
    loaded = db2.get_scene_by_id(sid)
    assert loaded.stage_location == "graveyard"
    assert loaded.performance_duration_minutes == 15
    assert len(db2.get_stage_entrances_exits(sid)) == 1
    assert len(db2.get_stage_cues(sid)) == 1
    assert db2.get_stage_business(sid)[0].stage_action == "lifts skull"


def test_old_project_loads_with_empty_stage_data(tmp_path):
    path = str(tmp_path / "novel.db")
    db = Database(path)
    p = db.create_project("Novel")  # default novel engine
    s = db.create_scene(p.id, "Chapter 1", content="prose")
    db2 = Database(path)
    loaded = db2.get_scene_by_id(s.id)
    # Stage fields default-safe; collections empty.
    assert loaded.stage_location == ""
    assert db2.get_stage_entrances_exits(s.id) == []
    assert db2.get_stage_cues(s.id) == []
    assert db2.get_stage_business(s.id) == []


def test_scene_reload_retains_all_metadata(tmp_path):
    path = str(tmp_path / "play2.db")
    db = Database(path)
    p = _play(db)
    s = db.create_scene(
        p.id, "Act 2",
        stage_location="hall", set_description="grand",
        scene_objective="confess", cue_notes="music swells",
        offstage_events="a scream", audience_visibility_notes="masked",
        performance_duration_minutes=9,
    )
    sid = s.id
    db2 = Database(path)
    loaded = db2.get_scene_by_id(sid)
    for field, value in (
        ("stage_location", "hall"), ("set_description", "grand"),
        ("scene_objective", "confess"), ("cue_notes", "music swells"),
        ("offstage_events", "a scream"),
        ("audience_visibility_notes", "masked"),
        ("performance_duration_minutes", 9),
    ):
        assert getattr(loaded, field) == value
