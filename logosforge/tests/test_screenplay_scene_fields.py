"""Tests for the screenplay-specific Scene fields and their persistence."""

from __future__ import annotations

import json

from logosforge.db import Database
from logosforge.export import _gather_project_data, export_json
from logosforge.import_data import import_json


# -- Defaults preserve backward compatibility -------------------------------

def test_scene_created_without_screenplay_fields_has_safe_defaults():
    db = Database()
    proj = db.create_project("Old project")
    scene = db.create_scene(proj.id, "Opening")
    assert scene.slugline == ""
    assert scene.location == ""
    assert scene.interior_exterior == ""
    assert scene.time_of_day == ""
    assert scene.estimated_duration_minutes == 0
    assert scene.visual_objective == ""
    assert scene.dramatic_turn == ""
    assert scene.blocking_notes == ""
    assert scene.subtext_notes == ""
    assert scene.setup_payoff_links == ""
    assert scene.montage_group == ""
    assert scene.cinematic_pacing == ""
    assert scene.continuity_notes == ""


def test_create_scene_accepts_screenplay_fields():
    db = Database()
    proj = db.create_project("Film", format_mode="screenplay")
    scene = db.create_scene(
        proj.id, "OPENING",
        slugline="INT. CAFE - DAY",
        location="CAFE",
        interior_exterior="INT",
        time_of_day="DAY",
        estimated_duration_minutes=3,
        visual_objective="Establish the loneliness of the protagonist.",
        dramatic_turn="Recognition that he's been forgotten.",
        blocking_notes="JOE alone by the window; rain outside.",
        subtext_notes="He hopes she'll come — and dreads it.",
        setup_payoff_links="42,57",
        montage_group="opening_montage",
        cinematic_pacing="slow",
        continuity_notes="Same coat as scene 12.",
    )
    assert scene.slugline == "INT. CAFE - DAY"
    assert scene.location == "CAFE"
    assert scene.interior_exterior == "INT"
    assert scene.time_of_day == "DAY"
    assert scene.estimated_duration_minutes == 3
    assert scene.dramatic_turn.startswith("Recognition")
    assert scene.cinematic_pacing == "slow"


def test_update_scene_preserves_unspecified_screenplay_fields():
    """Passing None for a field leaves it unchanged (matches color_label)."""
    db = Database()
    proj = db.create_project("Film", format_mode="screenplay")
    scene = db.create_scene(
        proj.id, "INT. ROOM - NIGHT",
        slugline="INT. ROOM - NIGHT",
        cinematic_pacing="fast",
    )
    # Touch only the title — screenplay fields should survive.
    db.update_scene(scene.id, title="INT. ROOM - LATE NIGHT")
    refreshed = db.get_scene_by_id(scene.id)
    assert refreshed.slugline == "INT. ROOM - NIGHT"
    assert refreshed.cinematic_pacing == "fast"


def test_update_scene_can_overwrite_screenplay_fields():
    db = Database()
    proj = db.create_project("Film", format_mode="screenplay")
    scene = db.create_scene(proj.id, "Pivot", cinematic_pacing="slow")
    db.update_scene(scene.id, title="Pivot", cinematic_pacing="fast")
    refreshed = db.get_scene_by_id(scene.id)
    assert refreshed.cinematic_pacing == "fast"


# -- Switch project to Screenplay -------------------------------------------

def test_switch_project_to_screenplay():
    db = Database()
    proj = db.create_project("Hybrid")  # starts as novel
    db.update_project_format(proj.id, "screenplay")
    refreshed = db.get_project_by_id(proj.id)
    assert refreshed.format_mode == "screenplay"


def test_existing_scene_still_editable_after_switch():
    db = Database()
    proj = db.create_project("Hybrid")
    scene = db.create_scene(proj.id, "Chapter One")
    db.update_project_format(proj.id, "screenplay")
    # Edit the scene under the new mode — add screenplay fields.
    db.update_scene(scene.id, title="OPENING", slugline="INT. DAWN - DAY")
    refreshed = db.get_scene_by_id(scene.id)
    assert refreshed.title == "OPENING"
    assert refreshed.slugline == "INT. DAWN - DAY"


# -- Old projects still load ------------------------------------------------

def test_legacy_export_without_screenplay_fields_imports_cleanly():
    """JSON files written before the screenplay fields existed must still load."""
    legacy_payload = {
        "project": {"title": "Legacy", "description": "", "format_mode": "novel"},
        "characters": [],
        "places": [],
        "notes": [],
        "scenes": [{
            "title": "S1",
            "summary": "", "synopsis": "", "goal": "", "conflict": "",
            "outcome": "", "content": "", "beat": "",
            "tags": [], "order_index": 1,
            "act": "", "chapter": "", "plotline": "",
            "characters": [], "places": [], "character_states": [],
        }],
        "psyke_entries": [],
        "outline": [],
    }
    db = Database()
    new_pid = import_json(db, legacy_payload)
    assert new_pid > 0
    scenes = db.get_all_scenes(new_pid)
    assert len(scenes) == 1
    assert scenes[0].slugline == ""  # defaulted, not None or missing


# -- Roundtrip preserves screenplay fields ----------------------------------

def test_roundtrip_preserves_screenplay_fields():
    db = Database()
    proj = db.create_project("Film", format_mode="screenplay")
    db.create_scene(
        proj.id, "OPENING",
        slugline="EXT. STREET - NIGHT",
        location="STREET",
        interior_exterior="EXT",
        time_of_day="NIGHT",
        estimated_duration_minutes=5,
        visual_objective="Set tone.",
        dramatic_turn="The detective sees the body.",
        blocking_notes="Detective in foreground; lamp post DR.",
        subtext_notes="He already knows the victim.",
        setup_payoff_links="2",
        montage_group="",
        cinematic_pacing="medium",
        continuity_notes="Coat collar up.",
    )
    payload_str = export_json(db, proj.id)
    payload = json.loads(payload_str)
    db2 = Database()
    db2_pid = import_json(db2, payload)
    scenes = db2.get_all_scenes(db2_pid)
    assert len(scenes) == 1
    s = scenes[0]
    assert s.slugline == "EXT. STREET - NIGHT"
    assert s.interior_exterior == "EXT"
    assert s.time_of_day == "NIGHT"
    assert s.estimated_duration_minutes == 5
    assert s.dramatic_turn == "The detective sees the body."
    assert s.setup_payoff_links == "2"
    assert s.cinematic_pacing == "medium"
    assert s.continuity_notes == "Coat collar up."


def test_export_emits_screenplay_fields_in_json():
    db = Database()
    proj = db.create_project("Film", format_mode="screenplay")
    db.create_scene(
        proj.id, "OPENING",
        slugline="INT. CAFE - DAY",
        time_of_day="DAY",
        estimated_duration_minutes=2,
    )
    data = _gather_project_data(db, proj.id)
    scene = data["scenes"][0]
    assert scene["slugline"] == "INT. CAFE - DAY"
    assert scene["time_of_day"] == "DAY"
    assert scene["estimated_duration_minutes"] == 2


# -- Assistant context block exposes screenplay engine ---------------------

def test_assistant_context_block_for_screenplay_project():
    from logosforge.narrative_engines import engine_for_project
    db = Database()
    proj = db.create_project("Film", format_mode="screenplay")
    block = engine_for_project(proj).format_context_block()
    assert "[Narrative Engine: Screenplay]" in block
    assert "Plot block: scene" in block
    assert "Timeline: screen_time" in block


def test_assistant_context_block_for_novel_project():
    from logosforge.narrative_engines import engine_for_project
    db = Database()
    proj = db.create_project("Book")  # default novel
    block = engine_for_project(proj).format_context_block()
    assert "[Narrative Engine: Novel]" in block
    assert "Plot block: chapter" in block
    assert "interiority" in block
