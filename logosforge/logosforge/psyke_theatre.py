"""PSYKE theatre/performance-memory layer for the Stage Script Engine.

Stores performance-aware metadata on PSYKE entries (under
details_json["theatre"]) and derives a compact theatrical context from
PSYKE + the stage entrance/exit and scene tables — without duplicating
PSYKE or props.

Pure core/app logic: no UI / Tauri / filesystem / provider imports.
"""

from __future__ import annotations

from typing import Any

from logosforge.models import THEATRE_RELATION_TYPES


# Theatre fields for a character PSYKE entry (entry_type == "character").
CHARACTER_THEATRE_FIELDS: tuple[str, ...] = (
    "stage_objective",
    "spoken_strategy",
    "subtext_strategy",
    "physical_business",
    "gesture_vocabulary",
    "stage_presence",
    "relationship_pressure",
    "offstage_knowledge",
)

# Theatre fields for a place/set PSYKE entry (entry_type == "place").
SET_MEMORY_FIELDS: tuple[str, ...] = (
    "stage_layout",
    "entrances",
    "exits",
    "levels",
    "props_available",
    "audience_visibility",
    "spatial_constraints",
)

# Theatre fields for an object/prop PSYKE entry (entry_type == "object").
PROP_MEMORY_FIELDS: tuple[str, ...] = (
    "prop_status",
    "owner_character_id",
    "first_appearance",
    "use_in_scene",
    "continuity_notes",
)

# Relation types that mean "who pressures whom" for the context summary.
_PRESSURE_RELATIONS = frozenset({
    "pressures", "confronts", "dominates", "deceives", "interrupts",
})


def theatre_fields_for_type(entry_type: str) -> tuple[str, ...]:
    et = (entry_type or "").lower()
    if et == "character":
        return CHARACTER_THEATRE_FIELDS
    if et == "place":
        return SET_MEMORY_FIELDS
    if et == "object":
        return PROP_MEMORY_FIELDS
    return ()


def get_theatre_memory(db: Any, entry_id: int) -> dict:
    return db.get_psyke_theatre_memory(entry_id)


def set_theatre_memory(db: Any, entry_id: int, **fields: Any) -> None:
    """Merge theatre metadata onto a PSYKE entry. Empty values clear a key."""
    db.set_psyke_theatre_memory(entry_id, dict(fields))


# ---------------------------------------------------------------------------
# Assistant context (§5)
# ---------------------------------------------------------------------------

_MAX_ROWS = 8


def _entries_by_type(db: Any, project_id: int) -> dict[str, list]:
    out: dict[str, list] = {}
    for e in db.get_all_psyke_entries(project_id):
        out.setdefault((e.entry_type or "other").lower(), []).append(e)
    return out


def build_theatre_memory_context(db: Any, project_id: int) -> str:
    """Compact ``[Theatre Memory]`` block for the Assistant (§5).

    Surfaces who wants what, who pressures whom, who knows what, who
    enters/exits, what props matter, and what cannot be staged clearly.
    Returns "" when there is nothing theatrical to report.
    """
    by_type = _entries_by_type(db, project_id)
    name_by_id = {e.id: e.name for e in db.get_all_psyke_entries(project_id)}
    lines: list[str] = []

    # Who wants what — character stage objectives.
    objectives: list[str] = []
    for e in by_type.get("character", []):
        tm = db.get_psyke_theatre_memory(e.id)
        if tm.get("stage_objective"):
            objectives.append(f"{e.name}: {tm['stage_objective']}")
    if objectives:
        lines.append("Who wants what: " + "; ".join(objectives[:_MAX_ROWS]))

    # Who pressures whom — directional theatrical relations.
    pressures: list[str] = []
    seen_pairs: set[tuple[frozenset, str]] = set()
    for e in by_type.get("character", []):
        try:
            typed = db.get_typed_related_psyke_entries(e.id)
        except Exception:
            typed = []
        for rel_entry, rel_type in typed:
            if rel_type in _PRESSURE_RELATIONS:
                key = (frozenset({e.id, rel_entry.id}), rel_type)
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                pressures.append(f"{e.name} {rel_type} {rel_entry.name}")
    if pressures:
        lines.append("Who pressures whom: " + "; ".join(pressures[:_MAX_ROWS]))

    # Who knows what — offstage knowledge.
    knows: list[str] = []
    for e in by_type.get("character", []):
        tm = db.get_psyke_theatre_memory(e.id)
        if tm.get("offstage_knowledge"):
            knows.append(f"{e.name}: {tm['offstage_knowledge']}")
    if knows:
        lines.append("Who knows what: " + "; ".join(knows[:_MAX_ROWS]))

    # Who enters/exits — from the stage entrance/exit table.
    movements: list[str] = []
    try:
        scenes = db.get_all_scenes(project_id)
    except Exception:
        scenes = []
    char_table_names = {}
    try:
        char_table_names = {c.id: c.name for c in db.get_all_characters(project_id)}
    except Exception:
        char_table_names = {}
    for scene in scenes:
        for ee in db.get_stage_entrances_exits(scene.id):
            who = char_table_names.get(ee.character_id, "")
            movements.append(f"{who or '?'} {ee.type}".strip())
            if len(movements) >= _MAX_ROWS:
                break
        if len(movements) >= _MAX_ROWS:
            break
    if movements:
        lines.append("Who enters/exits: " + ", ".join(movements))

    # What props matter — object entries with theatre prop memory.
    props: list[str] = []
    for e in by_type.get("object", []):
        tm = db.get_psyke_theatre_memory(e.id)
        if not tm:
            continue
        owner_id = tm.get("owner_character_id")
        owner = name_by_id.get(owner_id) or char_table_names.get(owner_id)
        status = tm.get("prop_status", "")
        bit = e.name
        if status:
            bit += f" ({status})"
        if owner:
            bit += f" — {owner}"
        props.append(bit)
    if props:
        lines.append("Props that matter: " + "; ".join(props[:_MAX_ROWS]))

    # What cannot be staged clearly — scene audience-visibility flags + set
    # spatial constraints.
    staging: list[str] = []
    for scene in scenes:
        note = getattr(scene, "audience_visibility_notes", "") or ""
        if note:
            staging.append(f"{scene.title}: {note}")
    for e in by_type.get("place", []):
        tm = db.get_psyke_theatre_memory(e.id)
        if tm.get("spatial_constraints"):
            staging.append(f"{e.name}: {tm['spatial_constraints']}")
    if staging:
        lines.append("Staging concerns: " + "; ".join(staging[:_MAX_ROWS]))

    if not lines:
        return ""
    return "[Theatre Memory]\n" + "\n".join(lines)
