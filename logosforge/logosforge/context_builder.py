"""Context Builder — constructs structured prompts from project data."""

import re

from logosforge.db import Database

CONTENT_MAX_CHARS = 2000
RECENT_STATES_LIMIT = 2
DESCRIPTION_MAX_CHARS = 300
SURROUNDING_SUMMARY_MAX_CHARS = 200
PREVIOUS_SCENES_LIMIT = 2
STORY_ARC_SUMMARY_MAX_CHARS = 200
TOP_TAGS_LIMIT = 7

PSYKE_GLOBAL_NOTES_MAX = 100
PSYKE_RELEVANT_NOTES_MAX = 150
PSYKE_MAX_RELEVANT = 10
PSYKE_RELATION_DEPTH = 2

_LINK_RE = re.compile(r"\[\[(.+?)\]\]")


def _truncate(text: str, max_chars: int = CONTENT_MAX_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n[...truncated]"


def _find_scene_index(all_scenes: list, scene_id: int) -> int | None:
    for i, s in enumerate(all_scenes):
        if s.id == scene_id:
            return i
    return None


def _scene_summary_line(scene) -> str:
    if scene.synopsis:
        text = scene.synopsis
    elif scene.summary:
        text = scene.summary
    elif scene.content:
        text = _first_paragraph(scene.content)
    else:
        return ""
    if len(text) > SURROUNDING_SUMMARY_MAX_CHARS:
        truncated = text[:SURROUNDING_SUMMARY_MAX_CHARS].rsplit(" ", 1)[0]
        if not truncated:
            truncated = text[:SURROUNDING_SUMMARY_MAX_CHARS]
        return truncated + "..."
    return text


def _first_paragraph(content: str) -> str:
    for para in content.split("\n\n"):
        stripped = para.strip()
        if stripped:
            return stripped
    return content.strip()


def gather_scene_context(
    db: Database,
    project_id: int,
    scene_id: int,
) -> str:
    scene = db.get_scene_by_id(scene_id)
    if scene is None:
        return ""

    all_scenes = db.get_all_scenes(project_id)
    current_idx = _find_scene_index(all_scenes, scene_id)

    scene_section = _build_scene_section(scene)
    story_section = _build_story_context_section(all_scenes, current_idx)
    memory_section = _build_character_memory_section(db, project_id, scene_id)
    places_section = _build_places_section(db, project_id, scene_id)
    position_section = _build_position_section(all_scenes, current_idx)
    continuity_section = _build_continuity_section(db, scene_id)
    screenplay_section = _build_screenplay_context(db, project_id, scene_id)
    beat_plan_section = _build_beat_plan_section(db, project_id, scene_id)

    sections: list[str] = []
    if scene_section:
        sections.append(f"[Scene Context]\n{scene_section}")
    if story_section:
        sections.append(f"[Story Context]\n{story_section}")
    if memory_section:
        sections.append(f"[Character Memory]\n{memory_section}")
    if places_section:
        sections.append(f"[Places]\n{places_section}")
    if continuity_section:
        sections.append(f"[Continuity]\n{continuity_section}")
    if screenplay_section:
        sections.append(f"[Screenplay Analysis]\n{screenplay_section}")
    if beat_plan_section:
        # Already self-labelled "[Beat Plan]"; empty for non-screenplay/unplanned.
        sections.append(beat_plan_section)
    gn_section = _build_graphic_novel_section(db, project_id, scene_id)
    if gn_section:
        # Already self-labelled "[Graphic Novel Script]"; empty for other modes.
        sections.append(gn_section)
    gn_plan_section = _build_gn_plan_section(db, project_id, scene_id)
    if gn_plan_section:
        # Already self-labelled "[Graphic Novel Plan]"; empty without a plan.
        sections.append(gn_plan_section)
    if position_section:
        sections.append(f"[Story Position]\n{position_section}")

    return "\n\n".join(sections)


def _build_beat_plan_section(db: Database, project_id: int, scene_id: int) -> str:
    """Screenplay scene beat plan (Phase 2), if one exists. Read-only; empty for
    Novel projects or scenes without a plan."""
    try:
        from logosforge.screenplay_pipeline import beat_plan_context
        return beat_plan_context(db, project_id, scene_id)
    except Exception:
        return ""


def _build_graphic_novel_section(db: Database, project_id: int, scene_id: int) -> str:
    """Graphic Novel page/panel script summary (Phase 1), if any. Read-only; empty
    for non-graphic-novel projects or scenes without page/panel content."""
    try:
        from logosforge.graphic_novel_blocks import graphic_novel_context
        return graphic_novel_context(db, project_id, scene_id)
    except Exception:
        return ""


def _build_gn_plan_section(db: Database, project_id: int, scene_id: int) -> str:
    """Graphic Novel page breakdown / panel plan (Phase 2), if any. Read-only;
    empty for non-graphic-novel projects or scenes without a plan."""
    try:
        from logosforge.graphic_novel_pipeline import gn_planning_context
        return gn_planning_context(db, project_id, scene_id)
    except Exception:
        return ""


def _build_continuity_section(db: Database, scene_id: int) -> str:
    """Render screenplay continuity items for the scene."""
    items = db.get_continuity_for_scene(scene_id)
    if not items:
        return ""
    _LABELS = {
        "continuity_wound": "Wound",
        "continuity_prop": "Prop",
        "continuity_costume": "Costume",
        "continuity_emotional_state": "Emotional state",
        "continuity_knowledge_state": "Knowledge state",
    }
    lines: list[str] = []
    for it in items:
        label = _LABELS.get(it.memory_type, it.memory_type)
        target = f" — {it.target}" if it.target else ""
        lines.append(f"  {label}{target}: {it.value}")
    return "\n".join(lines)


def _build_screenplay_context(
    db: Database, project_id: int, scene_id: int,
) -> str:
    """Build screenplay-specific analysis context: duration, setup/payoff, subtext."""
    try:
        from logosforge.narrative_engines import engine_for_project
        project = db.get_project_by_id(project_id)
        engine = engine_for_project(project)
        if engine.name != "screenplay":
            return ""
    except Exception:
        return ""

    scene = db.get_scene_by_id(scene_id)
    if scene is None:
        return ""

    lines: list[str] = []

    # Duration estimate
    duration = getattr(scene, "estimated_duration_minutes", 0) or 0
    if duration:
        lines.append(f"Estimated duration: {duration} min")

    # Setup/payoff links from scene field
    setup_payoff = getattr(scene, "setup_payoff_links", "") or ""
    if setup_payoff:
        lines.append(f"Setup/payoff links: {setup_payoff}")

    # Typed PSYKE relations for characters in scene
    char_ids = db.get_scene_character_ids(scene_id)
    if char_ids:
        entries = db.get_all_psyke_entries(project_id)
        char_names = {c.name.lower(): c for c in db.get_all_characters(project_id)}
        entry_by_name: dict[str, int] = {}
        for e in entries:
            entry_by_name[e.name.lower()] = e.id

        typed_lines: list[str] = []
        seen_pairs: set[tuple[int, int]] = set()
        for cid in char_ids:
            char = db.get_character_by_id(cid)
            if char is None:
                continue
            eid = entry_by_name.get(char.name.lower())
            if eid is None:
                continue
            typed = db.get_typed_related_psyke_entries(eid)
            for related_entry, rel_type in typed:
                pair = (min(eid, related_entry.id), max(eid, related_entry.id))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                typed_lines.append(
                    f"  {char.name} —[{rel_type}]→ {related_entry.name}"
                )
        if typed_lines:
            lines.append("Typed relations:")
            lines.extend(typed_lines)

    # Montage group
    montage = getattr(scene, "montage_group", "") or ""
    if montage:
        lines.append(f"Montage group: {montage}")

    return "\n".join(lines)


def gather_outline_context(db: Database, project_id: int) -> str:
    scenes = db.get_all_scenes(project_id)
    if not scenes:
        return ""
    lines = ["[Story Outline]"]
    for i, s in enumerate(scenes, 1):
        line = f"  {i}. {s.title}"
        if s.chapter:
            line += f" [{s.chapter}]"
        if s.summary:
            line += f" — {s.summary[:80]}"
        lines.append(line)
    return "\n".join(lines)


def gather_story_memory(db: Database, project_id: int) -> str:
    notes = db.get_all_notes(project_id)
    note_by_title = {n.title.lower().strip(): n for n in notes}

    themes = _resolve_themes(db, project_id, note_by_title)
    motifs = _resolve_motifs(note_by_title)
    arc = _build_story_arc(db, project_id)

    sections: list[str] = []
    if themes:
        sections.append(f"Core Themes: {themes}")
    if motifs:
        sections.append(f"Recurring Motifs: {motifs}")
    if arc:
        sections.append("Story Arc:")
        sections.append(arc)

    if not sections:
        return ""
    return "[Global Story Memory]\n" + "\n".join(sections)


def _resolve_themes(
    db: Database, project_id: int, note_by_title: dict,
) -> str:
    note = note_by_title.get("themes")
    if note and note.content.strip():
        return _normalize_list(note.content)
    counts = _count_scene_tags(db, project_id)
    if not counts:
        return ""
    return ", ".join(tag for tag, _n in counts[:TOP_TAGS_LIMIT])


def _resolve_motifs(note_by_title: dict) -> str:
    note = note_by_title.get("motifs")
    if note and note.content.strip():
        return _normalize_list(note.content)
    return ""


def _normalize_list(text: str) -> str:
    items: list[str] = []
    for line in text.split("\n"):
        for raw in line.split(","):
            item = raw.strip(" \t-•*·")
            if item:
                items.append(item)
    return ", ".join(items[:TOP_TAGS_LIMIT])


def _count_scene_tags(db: Database, project_id: int) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for scene in db.get_all_scenes(project_id):
        if not scene.tags:
            continue
        for raw in scene.tags.split(","):
            tag = raw.strip()
            if tag:
                counts[tag] = counts.get(tag, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def _build_story_arc(db: Database, project_id: int) -> str:
    scenes = db.get_all_scenes(project_id)
    if not scenes:
        return ""

    lines: list[str] = []
    lines.append(f"  Beginning: {_arc_line(scenes[0])}")
    if len(scenes) >= 3:
        lines.append(f"  Midpoint: {_arc_line(scenes[len(scenes) // 2])}")
    if len(scenes) >= 2:
        lines.append(f"  Latest: {_arc_line(scenes[-1])}")
    return "\n".join(lines)


def _arc_line(scene) -> str:
    text = scene.title
    summary = scene.synopsis or scene.summary
    if summary:
        if len(summary) > STORY_ARC_SUMMARY_MAX_CHARS:
            summary = summary[:STORY_ARC_SUMMARY_MAX_CHARS] + "..."
        text += f" — {summary}"
    return text


def _build_scene_section(scene) -> str:
    parts: list[str] = []
    if scene.title:
        parts.append(f"Title: {scene.title}")
    if scene.act:
        parts.append(f"Act: {scene.act}")
    if scene.chapter:
        parts.append(f"Chapter: {scene.chapter}")
    if scene.plotline:
        parts.append(f"Plotline: {scene.plotline}")
    if scene.beat:
        parts.append(f"Beat: {scene.beat}")
    if scene.tags:
        parts.append(f"Tags: {scene.tags}")
    if scene.goal:
        parts.append(f"Goal: {scene.goal}")
    if scene.conflict:
        parts.append(f"Conflict: {scene.conflict}")
    if scene.outcome:
        parts.append(f"Outcome: {scene.outcome}")
    if scene.synopsis:
        parts.append(f"Synopsis: {scene.synopsis}")
    if scene.summary:
        parts.append(f"Summary: {scene.summary}")
    # -- Screenplay-engine fields (only emit when populated) -------------
    if getattr(scene, "slugline", ""):
        parts.append(f"Slugline: {scene.slugline}")
    if getattr(scene, "time_of_day", ""):
        parts.append(f"Time of day: {scene.time_of_day}")
    if getattr(scene, "visual_objective", ""):
        parts.append(f"Visual objective: {scene.visual_objective}")
    if getattr(scene, "dramatic_turn", ""):
        parts.append(f"Dramatic turn: {scene.dramatic_turn}")
    if getattr(scene, "subtext_notes", ""):
        parts.append(f"Subtext: {scene.subtext_notes}")
    if getattr(scene, "blocking_notes", ""):
        parts.append(f"Blocking: {scene.blocking_notes}")
    if getattr(scene, "cinematic_pacing", ""):
        parts.append(f"Cinematic pacing: {scene.cinematic_pacing}")
    if getattr(scene, "continuity_notes", ""):
        parts.append(f"Continuity notes: {scene.continuity_notes}")
    # -- Screenplay PSYKE extensions -------------------------------------
    if getattr(scene, "visible_conflict", ""):
        parts.append(f"Visible conflict: {scene.visible_conflict}")
    if getattr(scene, "hidden_conflict", ""):
        parts.append(f"Hidden conflict: {scene.hidden_conflict}")
    if getattr(scene, "emotional_turn", ""):
        parts.append(f"Emotional turn: {scene.emotional_turn}")
    if getattr(scene, "who_knows_what", ""):
        parts.append(f"Who knows what: {scene.who_knows_what}")
    if getattr(scene, "physical_action", ""):
        parts.append(f"Physical action: {scene.physical_action}")
    if getattr(scene, "visual_symbolism", ""):
        parts.append(f"Visual symbolism: {scene.visual_symbolism}")
    if scene.content:
        parts.append(f"\nScene Content:\n{_truncate(scene.content)}")
    return "\n".join(parts)


def _build_story_context_section(
    all_scenes: list, current_idx: int | None,
) -> str:
    if current_idx is None or len(all_scenes) < 2:
        return ""

    current_scene = all_scenes[current_idx]
    current_chapter = current_scene.chapter or ""

    prev_indices = _pick_previous_scenes(all_scenes, current_idx, current_chapter)
    next_idx = _pick_next_scene(all_scenes, current_idx, current_chapter)

    blocks: list[str] = []
    for i in prev_indices:
        s = all_scenes[i]
        lines = [f"Previous Scene: {s.title}"]
        summary = _scene_summary_line(s)
        if summary:
            lines.append(f"  Summary: {summary}")
        blocks.append("\n".join(lines))

    if next_idx is not None:
        s = all_scenes[next_idx]
        lines = [f"Next Scene: {s.title}"]
        summary = _scene_summary_line(s)
        if summary:
            lines.append(f"  Summary: {summary}")
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)


def _pick_previous_scenes(
    all_scenes: list, current_idx: int, current_chapter: str,
) -> list[int]:
    if current_idx == 0:
        return []
    if current_chapter:
        same_ch = [
            i for i in range(current_idx)
            if (all_scenes[i].chapter or "") == current_chapter
        ]
        if same_ch:
            return same_ch[-PREVIOUS_SCENES_LIMIT:]
    start = max(0, current_idx - PREVIOUS_SCENES_LIMIT)
    return list(range(start, current_idx))


def _pick_next_scene(
    all_scenes: list, current_idx: int, current_chapter: str,
) -> int | None:
    if current_idx >= len(all_scenes) - 1:
        return None
    if current_chapter:
        for i in range(current_idx + 1, len(all_scenes)):
            if (all_scenes[i].chapter or "") == current_chapter:
                return i
    return current_idx + 1


def _build_character_memory_section(
    db: Database, project_id: int, scene_id: int,
) -> str:
    char_ids = db.get_scene_character_ids(scene_id)
    if not char_ids:
        return ""

    char_map = {c.id: c for c in db.get_all_characters(project_id)}
    current_states = dict(db.get_scene_character_states(scene_id))

    all_arcs = _build_all_arcs(db, project_id, set(char_ids))

    blocks: list[str] = []
    for cid in char_ids:
        if cid not in char_map:
            continue
        char = char_map[cid]
        block = [char.name]
        if char.description:
            block.append(
                f"  Description: {char.description[:DESCRIPTION_MAX_CHARS]}"
            )
        current = current_states.get(cid)
        if current:
            block.append(f"  Current state: {current}")

        prior = _recent_prior_states(all_arcs.get(cid, []), scene_id)
        if prior:
            block.append(f"  Recent progression: {' → '.join(prior)}")

        blocks.append("\n".join(block))

    return "\n\n".join(blocks)


def _build_all_arcs(
    db: Database, project_id: int, char_ids: set[int],
) -> dict[int, list[tuple[int, str]]]:
    arcs: dict[int, list[tuple[int, str]]] = {}
    for scene in db.get_all_scenes(project_id):
        for cid, state in db.get_scene_character_states(scene.id):
            if cid in char_ids:
                arcs.setdefault(cid, []).append((scene.id, state))
    return arcs


def _recent_prior_states(
    arc: list[tuple[int, str]], scene_id: int,
) -> list[str]:
    current_idx = None
    for i, (sid, _state) in enumerate(arc):
        if sid == scene_id:
            current_idx = i
            break
    prior_entries = arc[:current_idx] if current_idx is not None else arc
    return [state for _sid, state in prior_entries[-RECENT_STATES_LIMIT:]]


def _build_places_section(
    db: Database, project_id: int, scene_id: int,
) -> str:
    place_ids = db.get_scene_place_ids(scene_id)
    if not place_ids:
        return ""
    place_map = {p.id: p for p in db.get_all_places(project_id)}
    names = [place_map[pid].name for pid in place_ids if pid in place_map]
    if not names:
        return ""
    return ", ".join(names)


def _build_position_section(
    all_scenes: list, current_idx: int | None,
) -> str:
    if current_idx is None or not all_scenes:
        return ""

    scene = all_scenes[current_idx]
    parts = [f"Scene {current_idx + 1} of {len(all_scenes)}"]

    if scene.chapter:
        parts.append(f"Chapter: {scene.chapter}")
    if scene.plotline:
        parts.append(f"Plotline: {scene.plotline}")

    return "\n".join(parts)


# -- PSYKE Context ----------------------------------------------------------

def gather_psyke_context(
    db: Database,
    project_id: int,
    scene_id: int | None = None,
    query_text: str = "",
) -> str:
    entries = db.get_all_psyke_entries(project_id)

    characters = db.get_all_characters(project_id)
    places = db.get_all_places(project_id)
    psyke_names = {e.name.lower() for e in entries}
    for char in characters:
        if char.name.lower() not in psyke_names:
            entries.append(_LegacyAsPsyke(
                char.id + 1_000_000, char.name, "character",
                char.description or "",
            ))
    for place in places:
        if place.name.lower() not in psyke_names:
            entries.append(_LegacyAsPsyke(
                place.id + 2_000_000, place.name, "place",
                place.description or "",
            ))

    if not entries:
        return ""

    if scene_id is None:
        return _gather_psyke_all(entries)

    scene = db.get_scene_by_id(scene_id)
    if scene is None:
        return _gather_psyke_all(entries)

    all_scenes = db.get_all_scenes(project_id)
    scene_order = {s.id: s.sort_order for s in all_scenes}
    current_order = scene_order.get(scene_id, 0)

    scene_text = _scene_searchable_text(scene)
    search_text = scene_text + "\n" + query_text if query_text else scene_text
    entry_by_id = {e.id: e for e in entries}

    global_lines: list[str] = []
    relevant_lines: list[str] = []
    relevant_ids: set[int] = set()

    for entry in entries:
        if entry.is_global:
            global_lines.append(_format_psyke_entry(
                entry, PSYKE_GLOBAL_NOTES_MAX,
            ))
        elif _entry_matches_scene(entry, search_text):
            if len(relevant_lines) < PSYKE_MAX_RELEVANT:
                prog = _latest_progression(db, entry.id, current_order, scene_order)
                relevant_lines.append(_format_psyke_entry(
                    entry, PSYKE_RELEVANT_NOTES_MAX, prog,
                ))
                relevant_ids.add(entry.id)

    related_lines: list[str] = []
    if relevant_ids:
        visited = set(relevant_ids)
        frontier = set(relevant_ids)
        for _ in range(PSYKE_RELATION_DEPTH):
            next_frontier: set[int] = set()
            for eid in frontier:
                for rel in db.get_related_psyke_entries(eid):
                    if rel.id not in visited and not rel.is_global:
                        visited.add(rel.id)
                        next_frontier.add(rel.id)
                        if rel.id in entry_by_id:
                            related_lines.append(_format_psyke_entry(
                                entry_by_id[rel.id], PSYKE_GLOBAL_NOTES_MAX,
                            ))
            frontier = next_frontier
            if not frontier:
                break

    if not global_lines and not relevant_lines:
        return _gather_psyke_all(entries)

    parts = ["[PSYKE Context]"]
    if global_lines:
        parts.append("")
        parts.append("Global:")
        parts.extend(global_lines)
    if relevant_lines:
        parts.append("")
        parts.append("Relevant:")
        parts.extend(relevant_lines)
    if related_lines:
        parts.append("")
        parts.append("Related:")
        parts.extend(related_lines)

    return "\n".join(parts)


class _LegacyAsPsyke:
    """Adapter so Character/Place records look like PsykeEntry for context."""

    def __init__(self, id_: int, name: str, entry_type: str, notes: str):
        self.id = id_
        self.name = name
        self.entry_type = entry_type
        self.notes = notes
        self.aliases = ""
        self.is_global = False
        self.details_json = ""


def _gather_psyke_all(entries: list) -> str:
    """Build PSYKE context without scene filtering. Globals are always included;
    other entries are capped at PSYKE_MAX_RELEVANT so this unfiltered fallback
    (no scene, or nothing matched the scene) never dumps the entire bible into
    the prompt."""
    global_lines: list[str] = []
    other_lines: list[str] = []
    for entry in entries:
        if entry.is_global:
            global_lines.append(_format_psyke_entry(entry, PSYKE_GLOBAL_NOTES_MAX))
        elif len(other_lines) < PSYKE_MAX_RELEVANT:
            other_lines.append(_format_psyke_entry(entry, PSYKE_GLOBAL_NOTES_MAX))
    omitted = sum(1 for e in entries if not e.is_global) - len(other_lines)

    if not global_lines and not other_lines:
        return ""

    parts = ["[PSYKE Context]"]
    if global_lines:
        parts.append("")
        parts.append("Global:")
        parts.extend(global_lines)
    if other_lines:
        parts.append("")
        parts.append("Entries:")
        parts.extend(other_lines)
        if omitted > 0:
            parts.append(
                f"(+{omitted} more entr{'y' if omitted == 1 else 'ies'} omitted)"
            )

    return "\n".join(parts)


def _scene_searchable_text(scene) -> str:
    fields = [
        scene.content or "",
        scene.summary or "",
        scene.synopsis or "",
        scene.goal or "",
        scene.conflict or "",
        scene.outcome or "",
    ]
    return "\n".join(fields)


def _entry_matches_scene(entry, scene_text: str) -> bool:
    for match in _LINK_RE.finditer(scene_text):
        if match.group(1).lower() == entry.name.lower():
            return True

    if _word_match(entry.name, scene_text):
        return True

    if entry.aliases:
        for alias in entry.aliases.split(","):
            alias = alias.strip()
            if alias and _word_match(alias, scene_text):
                return True

    return False


def _word_match(term: str, text: str) -> bool:
    pattern = re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE)
    return pattern.search(text) is not None


def _latest_progression(
    db: Database,
    entry_id: int,
    current_order: int,
    scene_order: dict[int, int],
) -> str:
    progs = db.get_psyke_progressions(entry_id)
    if not progs:
        return ""

    best = None
    for p in progs:
        if p.scene_id and p.scene_id in scene_order:
            if scene_order[p.scene_id] <= current_order:
                best = p
        elif best is None:
            best = p

    if best is None:
        best = progs[-1]

    return best.text


def render_psyke_details(entry, per_field_max: int = 200) -> list[str]:
    """Return the labeled detail lines (indented) for a PSYKE entry."""
    import json
    from logosforge.models.psyke_details import get_detail_schema

    try:
        details = json.loads(entry.details_json) if entry.details_json else {}
    except (json.JSONDecodeError, TypeError):
        return []
    if not details:
        return []

    schema = get_detail_schema(entry.entry_type)
    field_labels = {f.key: f.label for f in schema}
    field_order = [f.key for f in schema] or list(details.keys())

    lines: list[str] = []
    for key in field_order:
        val = details.get(key)
        if not val:
            continue
        label = field_labels.get(key, key.replace("_", " ").title())
        val_str = str(val).replace("\n", " ").strip()
        if len(val_str) > per_field_max:
            val_str = val_str[:per_field_max].rsplit(" ", 1)[0] + "..."
        lines.append(f"  {label}: {val_str}")
    return lines


def _format_psyke_entry(
    entry, max_notes: int, progression: str = "",
) -> str:
    header = f"- {entry.name} ({entry.entry_type})"
    if entry.notes:
        short = entry.notes.split("\n")[0]
        if len(short) > max_notes:
            short = short[:max_notes].rsplit(" ", 1)[0] + "..."
        header += f": {short}"

    lines = [header]
    lines.extend(render_psyke_details(entry, per_field_max=max(80, max_notes * 2)))

    if progression:
        prog_short = progression.replace("\n", " ").strip()
        if len(prog_short) > 120:
            prog_short = prog_short[:120].rsplit(" ", 1)[0] + "..."
        lines.append(f"  Latest progression: {prog_short}")

    return "\n".join(lines)


def find_psyke_scene_references(
    db: Database,
    project_id: int,
    entry_id: int,
) -> list[tuple[int, str]]:
    entry = db.get_psyke_entry_by_id(entry_id)
    if entry is None:
        return []

    results: list[tuple[int, str]] = []
    for scene in db.get_all_scenes(project_id):
        scene_text = _scene_searchable_text(scene)
        if _entry_matches_scene(entry, scene_text):
            results.append((scene.id, scene.title))

    return results


# -- Notes Context -----------------------------------------------------------

NOTES_MAX_RELEVANT = 12
NOTES_EXCERPT_MAX = 150


def gather_notes_context(
    db: Database,
    project_id: int,
    scene_id: int | None = None,
    query_text: str = "",
) -> str:
    notes = db.get_all_notes(project_id)
    if not notes:
        return ""

    entries = db.get_all_psyke_entries(project_id)
    psyke_names = {e.name.lower(): e.id for e in entries}
    for e in entries:
        if e.aliases:
            for alias in e.aliases.split(","):
                alias = alias.strip().lower()
                if alias:
                    psyke_names[alias] = e.id

    scene_relevant_psyke_ids: set[int] = set()
    scene_text = ""
    if scene_id is not None:
        scene = db.get_scene_by_id(scene_id)
        if scene is not None:
            scene_text = _scene_searchable_text(scene)
            for entry in entries:
                if _entry_matches_scene(entry, scene_text):
                    scene_relevant_psyke_ids.add(entry.id)

    scored: list[tuple[float, "Note", str]] = []

    for note in notes:
        score = 0.0
        reason = ""

        if note.pinned:
            score = max(score, 1.0)
            reason = "pinned"

        scene_links = set(db.get_note_scene_links(note.id))
        if scene_id is not None and scene_id in scene_links:
            score = max(score, 0.9)
            reason = reason or "linked to current scene"

        psyke_links = set(db.get_note_psyke_links(note.id))
        if psyke_links & scene_relevant_psyke_ids:
            score = max(score, 0.8)
            reason = reason or "linked to relevant PSYKE entry"

        if note.tags and scene_id is not None:
            note_tags = {t.strip().lower() for t in note.tags.split(",") if t.strip()}
            scene_tags = set()
            scene_obj = db.get_scene_by_id(scene_id) if scene_id else None
            if scene_obj and scene_obj.tags:
                scene_tags = {t.strip().lower() for t in scene_obj.tags.split(",") if t.strip()}
            if note_tags & scene_tags:
                matched = (note_tags & scene_tags).pop()
                score = max(score, 0.7)
                reason = reason or f"tag match: {matched}"
            else:
                search_text = scene_text + "\n" + query_text
                for tag in note_tags:
                    if tag and _word_match(tag, search_text):
                        score = max(score, 0.7)
                        reason = reason or f"tag match: {tag}"
                        break

        if scene_text and score < 0.7:
            combined = note.title + "\n" + note.content
            for name_lower, eid in psyke_names.items():
                if _word_match(name_lower, combined) and eid in scene_relevant_psyke_ids:
                    score = max(score, 0.5)
                    reason = reason or "mentions relevant entity"
                    break

        if score > 0:
            scored.append((score, note, reason))

    if not scored:
        return ""

    scored.sort(key=lambda t: -t[0])

    pinned = [(s, n, r) for s, n, r in scored if n.pinned]
    non_pinned = [(s, n, r) for s, n, r in scored if not n.pinned]
    selected = pinned + non_pinned[:NOTES_MAX_RELEVANT]

    lines = ["[Relevant Notes]"]
    for _score, note, reason in selected:
        excerpt = (note.content or "").replace("\n", " ").strip()
        if len(excerpt) > NOTES_EXCERPT_MAX:
            excerpt = excerpt[:NOTES_EXCERPT_MAX].rsplit(" ", 1)[0] + "..."
        line = f"- \"{note.title}\""
        if excerpt:
            line += f": {excerpt}"
        if reason:
            line += f" ({reason})"
        lines.append(line)

    return "\n".join(lines)


# -- Graph Context -----------------------------------------------------------

GRAPH_DIRECT_MAX = 8
GRAPH_HIGH_INFLUENCE_MAX = 3
GRAPH_ISOLATED_MAX = 3


def gather_graph_context(
    db: Database,
    project_id: int,
    scene_id: int,
) -> str:
    """Build [Graph Context] from narrative graph relationships."""
    from logosforge.ui.focus_graph_view import build_graph_data, get_neighborhood

    data = build_graph_data(db, project_id)
    if not data.nodes:
        return ""

    scene = db.get_scene_by_id(scene_id)
    if scene is None:
        return ""

    focal_id = f"Scene:{scene_id}"
    if focal_id not in data.nodes:
        return ""

    direct = get_neighborhood(data, focal_id, hops=1) - {focal_id}

    influence_ranked = sorted(
        data.nodes.keys(),
        key=lambda nid: len(data.adjacency.get(nid, set())),
        reverse=True,
    )

    isolated = [
        nid for nid in data.nodes
        if len(data.adjacency.get(nid, set())) <= 1 and nid != focal_id
    ]

    char_states: dict[int, str] = {}
    all_scenes = db.get_all_scenes(project_id)
    for s in all_scenes:
        if s.sort_order <= scene.sort_order:
            for cid, state in db.get_scene_character_states(s.id):
                char_states[cid] = state

    lines = ["[Graph Context]"]
    lines.append("")

    focal_node = data.nodes[focal_id]
    direct_names = []
    for nid in sorted(direct)[:GRAPH_DIRECT_MAX]:
        node = data.nodes[nid]
        label = f"{node.name} ({node.etype.lower()})"
        if node.etype == "Character":
            state = char_states.get(node.entity_id)
            if state:
                label += f" [{state}]"
        direct_names.append(label)

    lines.append(f"Current: {focal_node.name}")
    if direct_names:
        lines.append(f"Connected to: {', '.join(direct_names)}")

    already_shown = direct | {focal_id}
    high_influence = []
    for nid in influence_ranked:
        if nid in already_shown:
            continue
        node = data.nodes[nid]
        conn_count = len(data.adjacency.get(nid, set()))
        if conn_count < 2:
            break
        high_influence.append(f"{node.name} ({node.etype.lower()}, {conn_count} connections)")
        already_shown.add(nid)
        if len(high_influence) >= GRAPH_HIGH_INFLUENCE_MAX:
            break

    if high_influence:
        lines.append("")
        lines.append("High influence:")
        for item in high_influence:
            lines.append(f"  - {item}")

    iso_items = []
    for nid in isolated[:GRAPH_ISOLATED_MAX]:
        if nid in already_shown:
            continue
        node = data.nodes[nid]
        iso_items.append(f"{node.name} ({node.etype.lower()})")

    if iso_items:
        lines.append("")
        lines.append("Weakly connected:")
        for item in iso_items:
            lines.append(f"  - {item}")

    return "\n".join(lines)


def gather_graph_context_debug(
    db: Database,
    project_id: int,
    scene_id: int,
) -> list[dict[str, str]]:
    """Return debug info about which graph nodes were included and why."""
    from logosforge.ui.focus_graph_view import build_graph_data, get_neighborhood

    data = build_graph_data(db, project_id)
    if not data.nodes:
        return []

    focal_id = f"Scene:{scene_id}"
    if focal_id not in data.nodes:
        return []

    direct = get_neighborhood(data, focal_id, hops=1) - {focal_id}

    influence_ranked = sorted(
        data.nodes.keys(),
        key=lambda nid: len(data.adjacency.get(nid, set())),
        reverse=True,
    )

    isolated = [
        nid for nid in data.nodes
        if len(data.adjacency.get(nid, set())) <= 1 and nid != focal_id
    ]

    entries: list[dict[str, str]] = []
    entries.append({
        "node_id": focal_id,
        "name": data.nodes[focal_id].name,
        "reason": "focal (current scene)",
    })

    for nid in sorted(direct)[:GRAPH_DIRECT_MAX]:
        node = data.nodes[nid]
        entries.append({
            "node_id": nid,
            "name": node.name,
            "reason": "direct connection (1-hop)",
        })

    already_shown = direct | {focal_id}
    for nid in influence_ranked:
        if nid in already_shown:
            continue
        node = data.nodes[nid]
        conn_count = len(data.adjacency.get(nid, set()))
        if conn_count < 2:
            break
        entries.append({
            "node_id": nid,
            "name": node.name,
            "reason": f"high influence ({conn_count} connections)",
        })
        already_shown.add(nid)
        if len([e for e in entries if "high influence" in e["reason"]]) >= GRAPH_HIGH_INFLUENCE_MAX:
            break

    for nid in isolated[:GRAPH_ISOLATED_MAX]:
        if nid in already_shown:
            continue
        node = data.nodes[nid]
        entries.append({
            "node_id": nid,
            "name": node.name,
            "reason": "weakly connected (≤1 link)",
        })

    return entries
