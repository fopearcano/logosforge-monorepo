"""Tests for PSYKE screenplay extensions — cinematic + performative data."""

from __future__ import annotations

import json

from logosforge.db import Database
from logosforge.db.database import CONTINUITY_MEMORY_TYPES
from logosforge.models.psyke_details import get_detail_schema
from logosforge.models.models import PSYKE_RELATION_TYPES
from logosforge.export import _gather_project_data, export_json
from logosforge.import_data import import_json


# =========================================================================
# 1. CHARACTER SCREENPLAY DATA — extends PSYKE character schema
# =========================================================================

def test_character_schema_has_screenplay_section():
    schema = get_detail_schema("character")
    sections = {f.section for f in schema}
    assert "Screenplay" in sections


def test_character_schema_includes_all_screenplay_fields():
    schema = get_detail_schema("character")
    keys = {f.key for f in schema if f.section == "Screenplay"}
    assert keys == {
        "spoken_voice",
        "gesture_vocabulary",
        "silence_pattern",
        "performance_mask",
        "subtext_strategy",
        "physical_behavior",
    }


def test_character_screenplay_fields_persist_in_details_json():
    db = Database()
    proj = db.create_project("Film", format_mode="screenplay")
    entry = db.create_psyke_entry(
        proj.id,
        name="JOE",
        entry_type="character",
        details={
            "spoken_voice": "Clipped, monotone; never explains himself.",
            "gesture_vocabulary": "Hands in pockets; only one shoulder shrugs.",
            "silence_pattern": "Goes quiet when asked about his sister.",
            "performance_mask": "Plays it tough; eyes give it away.",
            "subtext_strategy": "Talks about coffee when he means grief.",
            "physical_behavior": "Stutters slightly under stress.",
        },
    )
    details = db.get_psyke_entry_details(entry.id)
    assert details["spoken_voice"].startswith("Clipped")
    assert details["gesture_vocabulary"].startswith("Hands")
    assert details["silence_pattern"].startswith("Goes quiet")
    assert details["performance_mask"].startswith("Plays it tough")
    assert details["subtext_strategy"].startswith("Talks about coffee")
    assert details["physical_behavior"].startswith("Stutters")


def test_character_legacy_fields_still_work():
    """Adding Screenplay section must not break existing character schema."""
    schema = get_detail_schema("character")
    keys = {f.key for f in schema}
    for legacy in ("personality", "voice", "arc", "background"):
        assert legacy in keys


# =========================================================================
# 2. SCENE SCREENPLAY DATA — 6 new fields on the Scene model
# =========================================================================

def test_scene_defaults_include_new_screenplay_fields():
    db = Database()
    proj = db.create_project("Old project")
    scene = db.create_scene(proj.id, "Opening")
    assert scene.visible_conflict == ""
    assert scene.hidden_conflict == ""
    assert scene.emotional_turn == ""
    assert scene.who_knows_what == ""
    assert scene.physical_action == ""
    assert scene.visual_symbolism == ""


def test_create_scene_accepts_new_screenplay_fields():
    db = Database()
    proj = db.create_project("Film", format_mode="screenplay")
    scene = db.create_scene(
        proj.id, "Confrontation",
        visible_conflict="Joe demands the letter.",
        hidden_conflict="Joe is testing whether she still loves him.",
        emotional_turn="From hope to certainty of loss.",
        who_knows_what="She knows about the affair; he doesn't.",
        physical_action="He pulls the chair between them.",
        visual_symbolism="The unopened letter; a closed door.",
    )
    assert scene.visible_conflict.startswith("Joe demands")
    assert scene.hidden_conflict.startswith("Joe is testing")
    assert scene.emotional_turn == "From hope to certainty of loss."
    assert scene.who_knows_what.startswith("She knows")
    assert scene.physical_action.startswith("He pulls")
    assert scene.visual_symbolism.startswith("The unopened letter")


def test_update_scene_preserves_screenplay_extension_fields():
    db = Database()
    proj = db.create_project("Film", format_mode="screenplay")
    scene = db.create_scene(
        proj.id, "Opening",
        visible_conflict="The argument starts.",
        emotional_turn="Hope dies.",
    )
    db.update_scene(scene.id, title="Opening (rev)")
    refreshed = db.get_scene_by_id(scene.id)
    assert refreshed.visible_conflict == "The argument starts."
    assert refreshed.emotional_turn == "Hope dies."


def test_update_scene_can_overwrite_screenplay_extension_fields():
    db = Database()
    proj = db.create_project("Film", format_mode="screenplay")
    scene = db.create_scene(proj.id, "S1", visible_conflict="A")
    db.update_scene(scene.id, title="S1", visible_conflict="B")
    refreshed = db.get_scene_by_id(scene.id)
    assert refreshed.visible_conflict == "B"


# =========================================================================
# 3. CONTINUITY TRACKING — wounds, props, costumes, emotional, knowledge
# =========================================================================

def test_continuity_memory_types_constant():
    assert "continuity_wound" in CONTINUITY_MEMORY_TYPES
    assert "continuity_prop" in CONTINUITY_MEMORY_TYPES
    assert "continuity_costume" in CONTINUITY_MEMORY_TYPES
    assert "continuity_emotional_state" in CONTINUITY_MEMORY_TYPES
    assert "continuity_knowledge_state" in CONTINUITY_MEMORY_TYPES


def test_add_continuity_item_creates_memory_row():
    db = Database()
    proj = db.create_project("Film", format_mode="screenplay")
    scene = db.create_scene(proj.id, "Fight")
    item = db.add_continuity_item(
        proj.id, scene.id, "wound", "JOE", "Cut above left eye.",
    )
    assert item.memory_type == "continuity_wound"
    assert item.target == "JOE"
    assert item.value == "Cut above left eye."


def test_add_continuity_item_rejects_unknown_category():
    db = Database()
    proj = db.create_project("Film")
    scene = db.create_scene(proj.id, "S1")
    try:
        db.add_continuity_item(
            proj.id, scene.id, "made_up_category", "X", "Y",
        )
    except ValueError as e:
        assert "Unknown continuity category" in str(e)
    else:
        raise AssertionError("Expected ValueError for unknown category")


def test_get_continuity_for_scene_returns_only_continuity_rows():
    db = Database()
    proj = db.create_project("Film", format_mode="screenplay")
    s1 = db.create_scene(proj.id, "S1")
    db.add_continuity_item(proj.id, s1.id, "wound", "JOE", "Cut on cheek.")
    db.add_continuity_item(proj.id, s1.id, "prop", "JOE", "Locket in pocket.")
    db.add_continuity_item(proj.id, s1.id, "costume", "JOE", "Bloodied shirt.")
    # Unrelated memory_type — must not leak in
    db.add_memory(proj.id, s1.id, "character_state", "JOE", "Angry.")
    items = db.get_continuity_for_scene(s1.id)
    types = {i.memory_type for i in items}
    assert "continuity_wound" in types
    assert "continuity_prop" in types
    assert "continuity_costume" in types
    assert "character_state" not in types
    assert len(items) == 3


def test_get_continuity_by_category():
    db = Database()
    proj = db.create_project("Film", format_mode="screenplay")
    s1 = db.create_scene(proj.id, "S1")
    s2 = db.create_scene(proj.id, "S2")
    db.add_continuity_item(proj.id, s1.id, "wound", "JOE", "Cut.")
    db.add_continuity_item(proj.id, s2.id, "wound", "JOE", "Healing.")
    db.add_continuity_item(proj.id, s1.id, "prop", "JOE", "Knife.")
    wounds = db.get_continuity_by_category(proj.id, "wound")
    assert len(wounds) == 2
    assert all(w.memory_type == "continuity_wound" for w in wounds)


def test_continuity_survives_export_reload():
    """Tracked continuity must survive JSON export/import roundtrip."""
    db = Database()
    proj = db.create_project("Film", format_mode="screenplay")
    s1 = db.create_scene(proj.id, "Confrontation")
    db.add_continuity_item(proj.id, s1.id, "wound", "JOE", "Cut on left brow.")
    db.add_continuity_item(proj.id, s1.id, "prop", "JOE", "Locket — open.")
    db.add_continuity_item(
        proj.id, s1.id, "knowledge_state", "ANNA",
        "Anna does not yet know about the affair.",
    )

    payload = json.loads(export_json(db, proj.id))
    assert "continuity" in payload
    assert len(payload["continuity"]) == 3

    db2 = Database()
    new_pid = import_json(db2, payload)
    scenes = db2.get_all_scenes(new_pid)
    assert len(scenes) == 1
    items = db2.get_continuity_for_scene(scenes[0].id)
    types = {i.memory_type for i in items}
    assert "continuity_wound" in types
    assert "continuity_prop" in types
    assert "continuity_knowledge_state" in types
    wound = next(i for i in items if i.memory_type == "continuity_wound")
    assert wound.target == "JOE"
    assert wound.value.startswith("Cut")


# =========================================================================
# 4. PSYKE RELATION EXTENSIONS — typed relations
# =========================================================================

def test_relation_types_constant_includes_screenplay_types():
    assert "supports_setup" in PSYKE_RELATION_TYPES
    assert "payoff" in PSYKE_RELATION_TYPES
    assert "thematic_echo" in PSYKE_RELATION_TYPES
    assert "visual_motif" in PSYKE_RELATION_TYPES
    assert "subtext_opposition" in PSYKE_RELATION_TYPES
    assert "" in PSYKE_RELATION_TYPES  # generic


def test_add_relation_with_type_stores_relation_type():
    db = Database()
    proj = db.create_project("Film", format_mode="screenplay")
    a = db.create_psyke_entry(proj.id, "Locket", "object")
    b = db.create_psyke_entry(proj.id, "Final reveal", "other")
    db.add_psyke_relation(a.id, b.id, relation_type="supports_setup")
    assert db.get_psyke_relation_type(a.id, b.id) == "supports_setup"
    # Inverse is payoff (direction preserved across the symmetric link)
    assert db.get_psyke_relation_type(b.id, a.id) == "payoff"


def test_symmetric_relation_types_have_same_inverse():
    db = Database()
    proj = db.create_project("Film", format_mode="screenplay")
    a = db.create_psyke_entry(proj.id, "Anna", "character")
    b = db.create_psyke_entry(proj.id, "Joe", "character")
    db.add_psyke_relation(a.id, b.id, relation_type="thematic_echo")
    assert db.get_psyke_relation_type(a.id, b.id) == "thematic_echo"
    assert db.get_psyke_relation_type(b.id, a.id) == "thematic_echo"


def test_generic_relation_still_works():
    """Untyped relations remain valid (backward compatibility)."""
    db = Database()
    proj = db.create_project("Book")
    a = db.create_psyke_entry(proj.id, "Hero", "character")
    b = db.create_psyke_entry(proj.id, "Mentor", "character")
    db.add_psyke_relation(a.id, b.id)
    assert db.get_psyke_relation_type(a.id, b.id) == ""
    related = db.get_related_psyke_entries(a.id)
    assert any(r.id == b.id for r in related)


def test_get_typed_related_psyke_entries():
    db = Database()
    proj = db.create_project("Film", format_mode="screenplay")
    locket = db.create_psyke_entry(proj.id, "Locket", "object")
    reveal = db.create_psyke_entry(proj.id, "Reveal", "other")
    motif = db.create_psyke_entry(proj.id, "Rain", "other")
    db.add_psyke_relation(locket.id, reveal.id, relation_type="supports_setup")
    db.add_psyke_relation(locket.id, motif.id, relation_type="visual_motif")
    typed = db.get_typed_related_psyke_entries(locket.id)
    by_name = {r.name: rtype for r, rtype in typed}
    assert by_name["Reveal"] == "supports_setup"
    assert by_name["Rain"] == "visual_motif"


def test_typed_relations_survive_export_reload():
    db = Database()
    proj = db.create_project("Film", format_mode="screenplay")
    setup = db.create_psyke_entry(proj.id, "Setup", "other")
    payoff = db.create_psyke_entry(proj.id, "Payoff", "other")
    db.add_psyke_relation(setup.id, payoff.id, relation_type="supports_setup")

    payload = json.loads(export_json(db, proj.id))
    db2 = Database()
    new_pid = import_json(db2, payload)
    entries = {e.name: e for e in db2.get_all_psyke_entries(new_pid)}
    assert "Setup" in entries
    assert "Payoff" in entries
    assert db2.get_psyke_relation_type(
        entries["Setup"].id, entries["Payoff"].id,
    ) == "supports_setup"
    assert db2.get_psyke_relation_type(
        entries["Payoff"].id, entries["Setup"].id,
    ) == "payoff"


def test_legacy_related_entries_still_importable():
    """Legacy JSON (no typed_relations) imports without crash."""
    legacy_payload = {
        "project": {"title": "Old", "description": "", "format_mode": "novel"},
        "characters": [],
        "places": [],
        "notes": [],
        "scenes": [],
        "psyke_entries": [
            {"name": "A", "entry_type": "character", "related_entries": ["B"]},
            {"name": "B", "entry_type": "character", "related_entries": ["A"]},
        ],
        "outline": [],
    }
    db = Database()
    new_pid = import_json(db, legacy_payload)
    entries = {e.name: e for e in db.get_all_psyke_entries(new_pid)}
    assert "A" in entries and "B" in entries
    # Generic (untyped) relation
    assert db.get_psyke_relation_type(entries["A"].id, entries["B"].id) == ""


# =========================================================================
# 5. EXPORT FORMAT — new fields land in JSON
# =========================================================================

def test_export_includes_screenplay_extension_scene_fields():
    db = Database()
    proj = db.create_project("Film", format_mode="screenplay")
    db.create_scene(
        proj.id, "S1",
        visible_conflict="Visible.",
        hidden_conflict="Hidden.",
        emotional_turn="Turn.",
        who_knows_what="Knowledge.",
        physical_action="Action.",
        visual_symbolism="Symbol.",
    )
    data = _gather_project_data(db, proj.id)
    s = data["scenes"][0]
    assert s["visible_conflict"] == "Visible."
    assert s["hidden_conflict"] == "Hidden."
    assert s["emotional_turn"] == "Turn."
    assert s["who_knows_what"] == "Knowledge."
    assert s["physical_action"] == "Action."
    assert s["visual_symbolism"] == "Symbol."


def test_export_includes_continuity_block():
    db = Database()
    proj = db.create_project("Film", format_mode="screenplay")
    s = db.create_scene(proj.id, "S1")
    db.add_continuity_item(proj.id, s.id, "wound", "JOE", "Cut.")
    data = _gather_project_data(db, proj.id)
    assert "continuity" in data
    assert len(data["continuity"]) == 1
    assert data["continuity"][0]["memory_type"] == "continuity_wound"


def test_export_includes_typed_relations():
    db = Database()
    proj = db.create_project("Film", format_mode="screenplay")
    a = db.create_psyke_entry(proj.id, "A", "character")
    b = db.create_psyke_entry(proj.id, "B", "character")
    db.add_psyke_relation(a.id, b.id, relation_type="thematic_echo")
    data = _gather_project_data(db, proj.id)
    a_entry = next(e for e in data["psyke_entries"] if e["name"] == "A")
    typed = a_entry.get("typed_relations", [])
    assert any(t["name"] == "B" and t["relation_type"] == "thematic_echo" for t in typed)


def test_roundtrip_preserves_screenplay_extension_fields():
    db = Database()
    proj = db.create_project("Film", format_mode="screenplay")
    db.create_scene(
        proj.id, "S1",
        visible_conflict="V",
        hidden_conflict="H",
        emotional_turn="T",
        who_knows_what="K",
        physical_action="P",
        visual_symbolism="S",
    )
    payload = json.loads(export_json(db, proj.id))
    db2 = Database()
    new_pid = import_json(db2, payload)
    scenes = db2.get_all_scenes(new_pid)
    assert scenes[0].visible_conflict == "V"
    assert scenes[0].hidden_conflict == "H"
    assert scenes[0].emotional_turn == "T"
    assert scenes[0].who_knows_what == "K"
    assert scenes[0].physical_action == "P"
    assert scenes[0].visual_symbolism == "S"


# =========================================================================
# 6. ASSISTANT CONTEXT — sees screenplay fields and continuity
# =========================================================================

def test_assistant_sees_screenplay_scene_fields():
    from logosforge.context_builder import gather_scene_context
    db = Database()
    proj = db.create_project("Film", format_mode="screenplay")
    scene = db.create_scene(
        proj.id, "Confrontation",
        visible_conflict="They argue about the letter.",
        hidden_conflict="He's testing her loyalty.",
        emotional_turn="From hope to certainty of loss.",
        who_knows_what="She knows about the affair.",
        visual_symbolism="The locked door.",
    )
    ctx = gather_scene_context(db, proj.id, scene.id)
    assert "Visible conflict: They argue about the letter." in ctx
    assert "Hidden conflict: He's testing her loyalty." in ctx
    assert "Emotional turn: From hope to certainty of loss." in ctx
    assert "Who knows what: She knows about the affair." in ctx
    assert "Visual symbolism: The locked door." in ctx


def test_assistant_sees_continuity_section():
    from logosforge.context_builder import gather_scene_context
    db = Database()
    proj = db.create_project("Film", format_mode="screenplay")
    scene = db.create_scene(proj.id, "S1")
    db.add_continuity_item(proj.id, scene.id, "wound", "JOE", "Cut on cheek.")
    db.add_continuity_item(proj.id, scene.id, "costume", "JOE", "Bloody shirt.")
    ctx = gather_scene_context(db, proj.id, scene.id)
    assert "[Continuity]" in ctx
    assert "Wound — JOE: Cut on cheek." in ctx
    assert "Costume — JOE: Bloody shirt." in ctx


def test_assistant_sees_character_screenplay_details():
    """PSYKE detail rendering surfaces the new screenplay character fields."""
    from logosforge.context_builder import render_psyke_details
    db = Database()
    proj = db.create_project("Film", format_mode="screenplay")
    entry = db.create_psyke_entry(
        proj.id,
        name="JOE",
        entry_type="character",
        details={
            "spoken_voice": "Clipped, evasive.",
            "gesture_vocabulary": "Hands in pockets.",
            "performance_mask": "Plays it tough.",
        },
    )
    lines = render_psyke_details(entry)
    joined = "\n".join(lines)
    assert "Spoken Voice: Clipped, evasive." in joined
    assert "Gesture Vocabulary: Hands in pockets." in joined
    assert "Performance Mask: Plays it tough." in joined


def test_assistant_does_not_surface_empty_screenplay_fields():
    """Don't pollute the prompt with empty/default values."""
    from logosforge.context_builder import gather_scene_context
    db = Database()
    proj = db.create_project("Book")  # novel — extensions left blank
    scene = db.create_scene(proj.id, "Chapter One", summary="Hi.")
    ctx = gather_scene_context(db, proj.id, scene.id)
    assert "Visible conflict:" not in ctx
    assert "Hidden conflict:" not in ctx
    assert "Visual symbolism:" not in ctx
    assert "[Continuity]" not in ctx
