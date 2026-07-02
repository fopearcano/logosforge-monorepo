"""Plot and Timeline behavior for the Stage Script Engine.

Deterministic, pure helpers that make Plot and Timeline theatre-aware:
scenes grouped by acts as plot blocks, a performance-order timeline with
entrances/exits, cues, offstage events, prop continuity and emotional
pressure, plus compact entrance/exit and cue markers.

No UI / Tauri / filesystem / provider imports — the views consume these.
"""

from __future__ import annotations

from typing import Any


def _character_names(db: Any, project_id: int) -> dict[int, str]:
    try:
        return {c.id: c.name for c in db.get_all_characters(project_id)}
    except Exception:
        return {}


def _psyke_names(db: Any, project_id: int) -> dict[int, str]:
    try:
        return {e.id: e.name for e in db.get_all_psyke_entries(project_id)}
    except Exception:
        return {}


def _characters_on_stage(db: Any, scene_id: int, names: dict[int, str]) -> list[str]:
    try:
        cids = db.get_scene_character_ids(scene_id)
    except Exception:
        cids = []
    return [names.get(cid, f"#{cid}") for cid in cids]


def _important_props(db: Any, scene: Any, psyke_names: dict[int, str]) -> list[str]:
    props: list[str] = []
    try:
        for biz in db.get_stage_business(scene.id):
            name = psyke_names.get(biz.prop_psyke_entry_id)
            if name and name not in props:
                props.append(name)
    except Exception:
        pass
    if not props and (getattr(scene, "prop_notes", "") or "").strip():
        props.append(scene.prop_notes.strip())
    return props


def _emotional_pressure(scene: Any) -> str:
    """Compact pressure read for a scene."""
    if (getattr(scene, "dramatic_turn", "") or "").strip():
        return "turn"
    if (getattr(scene, "conflict", "") or "").strip():
        return "conflict"
    if (getattr(scene, "scene_objective", "") or "").strip():
        return "pursuit"
    return "flat"


# ---------------------------------------------------------------------------
# Plot grid (§1):  Scenes grouped by Acts
# ---------------------------------------------------------------------------

def _scene_block(db: Any, scene: Any, names: dict, psyke_names: dict) -> dict:
    ee = db.get_stage_entrances_exits(scene.id)
    return {
        "id": scene.id,
        "title": scene.title,
        "act": (scene.act or "").strip(),
        "scene_objective": getattr(scene, "scene_objective", "") or "",
        "dramatic_turn": getattr(scene, "dramatic_turn", "") or "",
        "characters_on_stage": _characters_on_stage(db, scene.id, names),
        "entrance_exit_count": len(ee),
        "important_props": _important_props(db, scene, psyke_names),
        "estimated_duration": getattr(scene, "performance_duration_minutes", 0) or 0,
    }


def get_stage_plot_blocks(db: Any, project_id: int) -> list[dict]:
    """One block per scene (with theatre metadata), in reading order."""
    names = _character_names(db, project_id)
    psyke_names = _psyke_names(db, project_id)
    return [
        _scene_block(db, s, names, psyke_names)
        for s in db.get_all_scenes(project_id)
    ]


def get_stage_plot_acts(db: Any, project_id: int) -> list[dict]:
    """Scenes grouped by act, preserving act + scene order.

    Returns [{act, scenes:[block, ...]}] with an act label (empty acts
    grouped under "")."""
    groups: list[dict] = []
    index: dict[str, dict] = {}
    for block in get_stage_plot_blocks(db, project_id):
        act = block["act"]
        if act not in index:
            grp = {"act": act, "scenes": []}
            index[act] = grp
            groups.append(grp)
        index[act]["scenes"].append(block)
    return groups


# ---------------------------------------------------------------------------
# Timeline (§2):  performance order with entrances/exits, cues, etc.
# ---------------------------------------------------------------------------

def get_stage_timeline(db: Any, project_id: int) -> list[dict]:
    """Ordered performance rows, one per scene."""
    names = _character_names(db, project_id)
    rows: list[dict] = []
    for idx, scene in enumerate(db.get_all_scenes(project_id), start=1):
        ee = db.get_stage_entrances_exits(scene.id)
        cues = db.get_stage_cues(scene.id)
        rows.append({
            "scene_id": scene.id,
            "order": idx,
            "act": (scene.act or "").strip(),
            "title": scene.title,
            "entrances_exits": [
                {"character": names.get(e.character_id, ""), "type": e.type}
                for e in ee
            ],
            "entrance_exit_count": len(ee),
            "cues": [{"type": c.cue_type, "text": c.cue_text} for c in cues],
            "cue_count": len(cues),
            "offstage_events": getattr(scene, "offstage_events", "") or "",
            "prop_continuity": _important_props(
                db, scene, _psyke_names(db, project_id),
            ),
            "emotional_pressure": _emotional_pressure(scene),
        })
    return rows


def get_act_progression(db: Any, project_id: int) -> list[str]:
    """Act labels in performance order (deduped, preserving first-seen)."""
    seen: list[str] = []
    for scene in db.get_all_scenes(project_id):
        act = (scene.act or "").strip()
        if act and act not in seen:
            seen.append(act)
    return seen


# ---------------------------------------------------------------------------
# Entrance/Exit display (§3) + Cue display (§4)
# ---------------------------------------------------------------------------

def get_entrance_exit_markers(db: Any, project_id: int, scene_id: int) -> list[dict]:
    """Compact entrance/exit markers for a scene (+ offstage flag)."""
    names = _character_names(db, project_id)
    markers = [
        {
            "character": names.get(e.character_id, ""),
            "type": e.type,                 # entrance | exit
            "moment_order": e.moment_order,
            "cue_text": e.cue_text,
        }
        for e in db.get_stage_entrances_exits(scene_id)
    ]
    scene = db.get_scene_by_id(scene_id)
    if scene is not None and (getattr(scene, "offstage_events", "") or "").strip():
        markers.append({
            "character": "",
            "type": "offstage",
            "moment_order": 9999,
            "cue_text": scene.offstage_events,
        })
    return markers


def get_cue_markers(db: Any, scene_id: int) -> list[dict]:
    """Compact cue markers for a scene (light/sound/music/movement/prop)."""
    return [
        {
            "cue_type": c.cue_type,
            "text": c.cue_text,
            "moment_order": c.moment_order,
        }
        for c in db.get_stage_cues(scene_id)
    ]


# ---------------------------------------------------------------------------
# Assistant context (§3):  scene objective / entrances-exits / blocking /
# stage layout / props / subtext / offstage knowledge
# ---------------------------------------------------------------------------

def _scene_place_layouts(db: Any, project_id: int, scene_id: int) -> list[str]:
    """Stage layouts for the scene's places, via matching PSYKE place
    entries' theatre memory."""
    try:
        place_ids = db.get_scene_place_ids(scene_id)
        place_names = {p.id: p.name for p in db.get_all_places(project_id)}
        wanted = {place_names.get(pid, "").lower() for pid in place_ids}
    except Exception:
        wanted = set()
    layouts: list[str] = []
    for e in db.get_all_psyke_entries(project_id):
        if (e.entry_type or "").lower() != "place":
            continue
        if wanted and e.name.lower() not in wanted:
            continue
        tm = db.get_psyke_theatre_memory(e.id)
        if tm.get("stage_layout"):
            layouts.append(f"{e.name}: {tm['stage_layout']}")
    return layouts


def build_stage_script_context(
    db: Any, project_id: int, scene_id: int | None = None,
) -> str:
    """Compact ``[Stage Script Context]`` block for the Assistant (§3).

    Scene-focused when *scene_id* is given. Returns "" when there is no
    scene to describe.
    """
    scene = None
    if scene_id is not None:
        scene = db.get_scene_by_id(scene_id)
    if scene is None:
        scenes = db.get_all_scenes(project_id)
        scene = scenes[0] if scenes else None
    if scene is None:
        return ""

    names = _character_names(db, project_id)
    psyke_names = _psyke_names(db, project_id)
    lines = ["[Stage Script Context]", f"Scene: {scene.title}"]

    if (getattr(scene, "scene_objective", "") or "").strip():
        lines.append(f"Objective: {scene.scene_objective}")
    if (getattr(scene, "blocking_notes", "") or "").strip():
        lines.append(f"Blocking: {scene.blocking_notes}")

    ee = get_entrance_exit_markers(db, project_id, scene.id)
    movers = [
        f"{m['character'] or '?'} {m['type']}"
        for m in ee if m["type"] in ("entrance", "exit")
    ]
    if movers:
        lines.append("Entrances/Exits: " + ", ".join(movers))

    layouts = _scene_place_layouts(db, project_id, scene.id)
    if layouts:
        lines.append("Stage layout: " + "; ".join(layouts))

    props = _important_props(db, scene, psyke_names)
    if props:
        lines.append("Props: " + ", ".join(props))

    if (getattr(scene, "subtext_notes", "") or "").strip():
        lines.append(f"Subtext: {scene.subtext_notes}")
    if (getattr(scene, "offstage_events", "") or "").strip():
        lines.append(f"Offstage: {scene.offstage_events}")

    # Offstage knowledge of the characters on stage.
    on_stage = _characters_on_stage(db, scene.id, names)
    name_to_entry = {
        e.name: e for e in db.get_all_psyke_entries(project_id)
        if (e.entry_type or "").lower() == "character"
    }
    knowledge: list[str] = []
    for cname in on_stage:
        entry = name_to_entry.get(cname)
        if entry is None:
            continue
        tm = db.get_psyke_theatre_memory(entry.id)
        if tm.get("offstage_knowledge"):
            knowledge.append(f"{cname}: {tm['offstage_knowledge']}")
    if knowledge:
        lines.append("Offstage knowledge: " + "; ".join(knowledge))

    if len(lines) <= 2:  # only header + scene title → nothing meaningful
        return ""
    return "\n".join(lines)
