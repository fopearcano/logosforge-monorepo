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
    psyke_identities_seen: set[tuple[str, str]] = set()
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
        # Core identity is exact (name, type): differently-cased names are
        # legal, distinct bible subjects and must survive a full round-trip.
        psyke_identities_seen.add((name, "character"))
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
        psyke_identities_seen.add((name, "place"))
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

    scene_id_by_source_order: dict[int, int] = {}
    for fallback_order, scene_data in enumerate(scenes, start=1):
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

        scene = db.create_scene(
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
        try:
            source_order = int(scene_data.get("order_index", fallback_order))
        except (TypeError, ValueError):
            source_order = fallback_order
        scene_id_by_source_order.setdefault(source_order, int(scene.id))

    # Create PSYKE entries and build name → id mapping
    psyke_id_by_name: dict[str, int] = {}
    psyke_raw = data.get("psyke_entries", [])
    for entry_data in psyke_raw:
        name = entry_data.get("name", "").strip()
        if not name:
            continue
        entry_type = entry_data.get("entry_type", "other")
        identity = (name, entry_type)
        if identity in psyke_identities_seen:
            for existing in db.get_all_psyke_entries(project_id):
                if (
                    existing.name == name
                    and existing.entry_type == entry_type
                ):
                    psyke_id_by_name.setdefault(name, existing.id)
                    break
            continue
        psyke_identities_seen.add(identity)
        details_raw = entry_data.get("details")
        details = details_raw if isinstance(details_raw, dict) else None
        entry = db.create_psyke_entry(
            project_id,
            name=name,
            entry_type=entry_type,
            aliases=entry_data.get("aliases", ""),
            notes=entry_data.get("notes", ""),
            is_global=entry_data.get("is_global", False),
            details=details,
        )
        psyke_id_by_name.setdefault(name, entry.id)

    psyke_id_by_identity = {
        (entry.name, entry.entry_type): int(entry.id)
        for entry in db.get_all_psyke_entries(project_id)
    }

    # Build scene title → id mapping for progression linking
    scene_id_by_title: dict[str, int] = {}
    for scene in db.get_all_scenes(project_id):
        scene_id_by_title[scene.title] = scene.id

    canonical_progressions = data.get("progression_tracks")
    has_canonical_progressions = canonical_progressions is not None
    if has_canonical_progressions and not isinstance(canonical_progressions, list):
        raise ValueError("progression_tracks must be a list")

    # Restore PSYKE relations and the legacy projection when no authoritative
    # canonical section is present (old exports remain import-compatible).
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

        if not has_canonical_progressions:
            for prog_data in entry_data.get("progressions", []):
                text = prog_data.get("text")
                if not isinstance(text, str):
                    continue
                scene_title = prog_data.get("scene_title", "")
                scene_id = scene_id_by_title.get(scene_title) if scene_title else None
                db.create_psyke_progression(entry_id, text, scene_id=scene_id)

    if has_canonical_progressions:
        def _subject_id(reference) -> int | None:
            if reference is None:
                return None
            if not isinstance(reference, dict):
                raise ValueError("Progression subject references must be objects")
            name = reference.get("name")
            entry_type = reference.get("entry_type")
            if not isinstance(name, str):
                raise ValueError("Progression subject references need a name")
            resolved = psyke_id_by_identity.get((name, entry_type))
            if resolved is None and entry_type is None:
                resolved = psyke_id_by_name.get(name)
            if resolved is None:
                raise ValueError(
                    f"Progression subject {name!r} ({entry_type!r}) was not imported"
                )
            return resolved

        def _progression_scene_id(reference) -> int | None:
            if reference is None:
                return None
            if not isinstance(reference, dict):
                raise ValueError("Progression scene references must be objects")
            raw_order = reference.get("source_order")
            if not isinstance(raw_order, bool):
                try:
                    resolved = scene_id_by_source_order.get(int(raw_order))
                except (TypeError, ValueError):
                    resolved = None
                if resolved is not None:
                    return resolved
            title = reference.get("source_title")
            if isinstance(title, str) and title:
                return scene_id_by_title.get(title)
            return None

        resolved_tracks = []
        for raw_track in sorted(
            canonical_progressions,
            key=lambda row: row.get("sort_order", 0) if isinstance(row, dict) else 0,
        ):
            if not isinstance(raw_track, dict):
                raise ValueError("Each progression track must be an object")
            legacy_compatibility = raw_track.get(
                "legacy_compatibility", False,
            )
            if not isinstance(legacy_compatibility, bool):
                raise ValueError(
                    "Progression legacy_compatibility must be a boolean"
                )
            primary_id = _subject_id(raw_track.get("primary_subject"))
            secondary_id = _subject_id(raw_track.get("secondary_subject"))
            raw_beats = raw_track.get("beats", [])
            if not isinstance(raw_beats, list):
                raise ValueError("Progression track beats must be a list")
            resolved_beats = []
            for raw_beat in sorted(
                raw_beats,
                key=lambda row: row.get("sort_order", 0) if isinstance(row, dict) else 0,
            ):
                if not isinstance(raw_beat, dict):
                    raise ValueError("Each progression beat must be an object")
                anchor_kind = raw_beat.get("anchor_kind", "unanchored")
                scene_id = (
                    _progression_scene_id(raw_beat.get("scene_anchor"))
                    if anchor_kind == "scene"
                    else None
                )
                resolved_beats.append({
                    "text": raw_beat.get("text"),
                    "anchor_kind": anchor_kind,
                    "scene_id": scene_id,
                    "anchor_ref": raw_beat.get("anchor_ref"),
                    "anchor_label": raw_beat.get("anchor_label", ""),
                })
            resolved_tracks.append({
                "kind": raw_track.get("kind"),
                "title": raw_track.get("title"),
                "description": raw_track.get("description", ""),
                "color_label": raw_track.get("color_label", ""),
                "primary_psyke_entry_id": primary_id,
                "secondary_psyke_entry_id": secondary_id,
                "legacy_psyke_entry_id": (
                    primary_id if legacy_compatibility else None
                ),
                "beats": resolved_beats,
            })
        db.restore_progression_tracks(project_id, resolved_tracks)

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

    def _timeline_scene_id(reference) -> int | None:
        """Resolve an exported, database-independent Timeline Scene reference."""
        if isinstance(reference, dict):
            raw_order = reference.get("source_order")
            if not isinstance(raw_order, bool):
                try:
                    resolved = scene_id_by_source_order.get(int(raw_order))
                except (TypeError, ValueError):
                    resolved = None
                if resolved is not None:
                    return resolved
            title = reference.get("source_title", "")
            return scene_id_by_title.get(title) if isinstance(title, str) else None
        if isinstance(reference, int) and not isinstance(reference, bool):
            return scene_id_by_source_order.get(reference)
        if isinstance(reference, str):
            return scene_id_by_title.get(reference)
        return None

    for lane in timeline.get("lanes", []):
        name = (lane.get("name") or "").strip()
        if not name:
            continue
        created_lane = db.create_timeline_lane(
            project_id, name,
            color_label=lane.get("color_label", ""),
            order_index=lane.get("order_index"),
        )
        if lane.get("collapsed"):
            db.set_timeline_lane_collapsed(created_lane.id, True)

    timeline_settings = {}
    if "explicit_events" in timeline:
        explicit_references = timeline.get("explicit_events")
        if not isinstance(explicit_references, list):
            explicit_references = []
        timeline_settings["timeline_event_ids"] = list(dict.fromkeys(
            scene_id
            for reference in explicit_references
            if (scene_id := _timeline_scene_id(reference)) is not None
        ))
    if "custom_order" in timeline:
        custom_references = timeline.get("custom_order")
        if not isinstance(custom_references, list):
            custom_references = []
        timeline_settings["timeline_order"] = list(dict.fromkeys(
            scene_id
            for reference in custom_references
            if (scene_id := _timeline_scene_id(reference)) is not None
        ))
    if timeline.get("order_mode") in {"structural", "custom"}:
        timeline_settings["timeline_order_mode"] = timeline["order_mode"]
    if timeline_settings:
        db.patch_project_settings(project_id, timeline_settings)

    for link in timeline.get("links", []):
        src = _timeline_scene_id({
            "source_order": link.get("source_order"),
            "source_title": link.get("source_title", ""),
        })
        tgt = _timeline_scene_id({
            "source_order": link.get("target_order"),
            "source_title": link.get("target_title", ""),
        })
        if src is None or tgt is None:
            continue
        db.add_timeline_link(
            project_id, src, tgt,
            color_label=link.get("color_label", "gray"),
            link_type=link.get("link_type", "custom"),
            label=link.get("label", ""),
        )

    return project_id
