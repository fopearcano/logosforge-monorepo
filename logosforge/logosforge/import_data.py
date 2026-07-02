"""Import project data from a JSON file (matching the app's export format)."""

import json

from logosforge.db import Database

REQUIRED_KEYS = {"project", "characters", "places", "notes", "scenes"}


def validate_import_data(raw: str) -> tuple[dict | None, str]:
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None, "Invalid JSON file."

    if not isinstance(data, dict):
        return None, "Invalid story plan format: expected a JSON object."

    missing = REQUIRED_KEYS - set(data.keys())
    if missing:
        return None, f"Invalid story plan format: missing {', '.join(sorted(missing))}."

    return data, ""


def import_json(db: Database, data: dict) -> int:
    project_info = data.get("project", {})
    title = project_info.get("title", "Imported Project")
    format_mode = project_info.get("format_mode", "novel")
    project = db.create_project(
        title,
        format_mode=format_mode,
        narrative_engine=project_info.get("narrative_engine", ""),
        default_writing_format=project_info.get("default_writing_format", ""),
    )
    project_id = project.id

    # Create characters and build name → id mapping
    char_id_by_name: dict[str, int] = {}
    psyke_names_seen: set[str] = set()
    for char_data in data.get("characters", []):
        name = char_data.get("name", "").strip()
        if not name:
            continue
        char = db.create_character(
            project_id,
            name=name,
            description=char_data.get("description", ""),
        )
        char_id_by_name[name] = char.id
        psyke_names_seen.add(name.lower())
        entry = db.create_psyke_entry(
            project_id,
            name=name,
            entry_type="character",
            notes=char_data.get("description", ""),
        )
        # Born linked: the Character and its bible entry are the same person.
        db.set_character_psyke_entry(char.id, entry.id)

    # Create places and build name → id mapping
    place_id_by_name: dict[str, int] = {}
    for place_data in data.get("places", []):
        name = place_data.get("name", "").strip()
        if not name:
            continue
        place = db.create_place(
            project_id,
            name=name,
            description=place_data.get("description", ""),
        )
        place_id_by_name[name] = place.id
        psyke_names_seen.add(name.lower())
        db.create_psyke_entry(
            project_id,
            name=name,
            entry_type="place",
            notes=place_data.get("description", ""),
        )

    # Create notes and store deferred link info
    note_link_deferred: list[tuple[int, list[str], list[str]]] = []
    for note_data in data.get("notes", []):
        title = note_data.get("title", "").strip()
        if not title:
            continue
        note = db.create_note(
            project_id,
            title=title,
            content=note_data.get("content", ""),
            tags=note_data.get("tags", ""),
            pinned=note_data.get("pinned", False),
        )
        psyke_link_names = note_data.get("psyke_links", [])
        scene_link_titles = note_data.get("scene_links", [])
        if psyke_link_names or scene_link_titles:
            note_link_deferred.append((note.id, psyke_link_names, scene_link_titles))

    # Create scenes in order, resolving character/place names to IDs
    scenes = data.get("scenes", [])
    scenes.sort(key=lambda s: s.get("order_index", 0))

    for scene_data in scenes:
        scene_title = scene_data.get("title", "").strip()
        if not scene_title:
            continue

        char_names = scene_data.get("characters", [])
        place_names = scene_data.get("places", [])

        character_ids = [
            char_id_by_name[name]
            for name in char_names
            if name in char_id_by_name
        ]
        place_ids = [
            place_id_by_name[name]
            for name in place_names
            if name in place_id_by_name
        ]

        character_states = None
        raw_states = scene_data.get("character_states", [])
        if raw_states:
            character_states = []
            for cs in raw_states:
                char_name = cs.get("character", "")
                state = cs.get("state", "")
                if char_name in char_id_by_name and state:
                    character_states.append((char_id_by_name[char_name], state))

        db.create_scene(
            project_id,
            title=scene_title,
            summary=scene_data.get("summary", ""),
            synopsis=scene_data.get("synopsis", ""),
            goal=scene_data.get("goal", ""),
            conflict=scene_data.get("conflict", ""),
            outcome=scene_data.get("outcome", ""),
            beat=scene_data.get("beat", ""),
            tags=", ".join(scene_data.get("tags", [])),
            act=scene_data.get("act", ""),
            content=scene_data.get("content", ""),
            chapter=scene_data.get("chapter", ""),
            plotline=scene_data.get("plotline", ""),
            color_label=scene_data.get("color_label", ""),
            # -- Screenplay-engine fields (silently absent in legacy JSONs) --
            slugline=scene_data.get("slugline", ""),
            location=scene_data.get("location", ""),
            interior_exterior=scene_data.get("interior_exterior", ""),
            time_of_day=scene_data.get("time_of_day", ""),
            estimated_duration_minutes=int(
                scene_data.get("estimated_duration_minutes") or 0,
            ),
            visual_objective=scene_data.get("visual_objective", ""),
            dramatic_turn=scene_data.get("dramatic_turn", ""),
            blocking_notes=scene_data.get("blocking_notes", ""),
            subtext_notes=scene_data.get("subtext_notes", ""),
            setup_payoff_links=scene_data.get("setup_payoff_links", ""),
            montage_group=scene_data.get("montage_group", ""),
            cinematic_pacing=scene_data.get("cinematic_pacing", ""),
            continuity_notes=scene_data.get("continuity_notes", ""),
            # -- Screenplay PSYKE extensions (absent in legacy JSON) ----
            visible_conflict=scene_data.get("visible_conflict", ""),
            hidden_conflict=scene_data.get("hidden_conflict", ""),
            emotional_turn=scene_data.get("emotional_turn", ""),
            who_knows_what=scene_data.get("who_knows_what", ""),
            physical_action=scene_data.get("physical_action", ""),
            visual_symbolism=scene_data.get("visual_symbolism", ""),
            character_ids=character_ids,
            place_ids=place_ids,
            character_states=character_states,
        )

    # Create PSYKE entries and build name → id mapping
    psyke_id_by_name: dict[str, int] = {}
    psyke_raw = data.get("psyke_entries", [])
    for entry_data in psyke_raw:
        name = entry_data.get("name", "").strip()
        if not name:
            continue
        if name.lower() in psyke_names_seen:
            for existing in db.get_all_psyke_entries(project_id):
                if existing.name.lower() == name.lower():
                    psyke_id_by_name[name] = existing.id
                    break
            continue
        psyke_names_seen.add(name.lower())
        details_raw = entry_data.get("details")
        details = details_raw if isinstance(details_raw, dict) else None
        entry = db.create_psyke_entry(
            project_id,
            name=name,
            entry_type=entry_data.get("entry_type", "other"),
            aliases=entry_data.get("aliases", ""),
            notes=entry_data.get("notes", ""),
            is_global=entry_data.get("is_global", False),
            details=details,
        )
        psyke_id_by_name[name] = entry.id

    # Build scene title → id mapping for progression linking
    scene_id_by_title: dict[str, int] = {}
    for scene in db.get_all_scenes(project_id):
        scene_id_by_title[scene.title] = scene.id

    # Restore PSYKE relations and progressions
    for entry_data in psyke_raw:
        name = entry_data.get("name", "").strip()
        if name not in psyke_id_by_name:
            continue
        entry_id = psyke_id_by_name[name]

        typed = entry_data.get("typed_relations") or []
        if typed:
            for rel_data in typed:
                rname = rel_data.get("name", "")
                rtype = rel_data.get("relation_type", "")
                if rname in psyke_id_by_name:
                    db.add_psyke_relation(
                        entry_id, psyke_id_by_name[rname], relation_type=rtype,
                    )
        else:
            for related_name in entry_data.get("related_entries", []):
                if related_name in psyke_id_by_name:
                    db.add_psyke_relation(
                        entry_id, psyke_id_by_name[related_name],
                    )

        for prog_data in entry_data.get("progressions", []):
            text = prog_data.get("text", "").strip()
            if not text:
                continue
            scene_title = prog_data.get("scene_title", "")
            scene_id = scene_id_by_title.get(scene_title) if scene_title else None
            db.create_psyke_progression(entry_id, text, scene_id=scene_id)

    # Restore outline nodes (optional — absent in older exports)
    outline_data = data.get("outline", [])
    if outline_data:
        def _create_outline_nodes(items: list, parent_id: int | None) -> None:
            for i, item in enumerate(items):
                node = db.create_outline_node(
                    project_id,
                    title=item.get("title", ""),
                    description=item.get("description", ""),
                    parent_id=parent_id,
                    sort_order=i,
                )
                children = item.get("children", [])
                if children:
                    _create_outline_nodes(children, node.id)

        _create_outline_nodes(outline_data, None)

    quantum_data = data.get("quantum_state")
    if quantum_data and isinstance(quantum_data, dict):
        from logosforge.quantum_outliner.persistence import import_quantum_state
        import_quantum_state(db, project_id, quantum_data)

    # Restore note → PSYKE and note → scene links
    for note_id, psyke_names, scene_titles in note_link_deferred:
        for pname in psyke_names:
            if pname in psyke_id_by_name:
                db.link_note_to_psyke(note_id, psyke_id_by_name[pname])
        for stitle in scene_titles:
            if stitle in scene_id_by_title:
                db.link_note_to_scene(note_id, scene_id_by_title[stitle])

    # Restore continuity items (screenplay PSYKE extension; absent in legacy)
    for item in data.get("continuity", []):
        stitle = item.get("scene_title", "")
        sid = scene_id_by_title.get(stitle)
        if sid is None:
            continue
        memory_type = item.get("memory_type", "")
        target = item.get("target", "")
        value = item.get("value", "")
        if not memory_type or not value:
            continue
        db.add_memory(project_id, sid, memory_type, target, value)

    # Restore Chapters (Novel primary unit; optional, absent in older exports).
    for ch in data.get("chapters", []):
        title = (ch.get("title") or "").strip()
        if not title and not (ch.get("content") or "").strip():
            continue
        db.create_chapter(
            project_id,
            title=title or "Untitled chapter",
            summary=ch.get("summary", ""),
            content=ch.get("content", ""),
            act=ch.get("act", ""),
            order_index=ch.get("order_index"),
        )

    # Restore Timeline lanes + event links (optional; absent in older exports).
    # Note: a distinct "plot_timeline" key avoids colliding with the separate
    # Interchange exporter's "timeline" (a list of events).
    timeline = data.get("plot_timeline", {}) or {}
    if not isinstance(timeline, dict):
        timeline = {}
    for lane in timeline.get("lanes", []):
        name = (lane.get("name") or "").strip()
        if not name:
            continue
        db.create_timeline_lane(
            project_id, name,
            color_label=lane.get("color_label", ""),
            order_index=lane.get("order_index"),
        )
    for link in timeline.get("links", []):
        src = scene_id_by_title.get(link.get("source_title", ""))
        tgt = scene_id_by_title.get(link.get("target_title", ""))
        if src is None or tgt is None:
            continue
        db.add_timeline_link(
            project_id, src, tgt,
            color_label=link.get("color_label", "gray"),
            link_type=link.get("link_type", "custom"),
            label=link.get("label", ""),
        )

    return project_id
