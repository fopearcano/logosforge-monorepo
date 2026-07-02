"""AI Orchestration — mode-aware PSYKE context composition.

Each orchestration mode customizes which PSYKE entries, temporal states,
and relations are included in the AI context, keeping prompts compact
and action-appropriate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from logosforge.context_builder import (
    _entry_matches_scene,
    _scene_searchable_text,
    _word_match,
    render_psyke_details,
)
from logosforge.temporal_psyke import TemporalGraph


@dataclass
class OrchestrationResult:
    """Result of orchestration: context string + metadata for debug."""

    mode: str
    psyke_context: str
    entries_included: list[str]
    temporal_used: bool
    relations_used: bool
    decisions: list[str]


# -- Mode constants ----------------------------------------------------------

MODE_REWRITE = "rewrite"
MODE_DIALOGUE = "dialogue"
MODE_EXPAND = "expand"
MODE_BRAINSTORM = "brainstorm"

_MODE_MAP: dict[str, str] = {
    "Rewrite": MODE_REWRITE,
    "Tighten": MODE_REWRITE,
    "Tension": MODE_REWRITE,
    "Pacing": MODE_REWRITE,
    "Dialogue": MODE_DIALOGUE,
    "Expand": MODE_EXPAND,
    "Next Beat": MODE_BRAINSTORM,
    "Brainstorm": MODE_BRAINSTORM,
    "Alternatives": MODE_BRAINSTORM,
    "Summarize": MODE_REWRITE,
}

_MAX_ENTRIES = {
    MODE_REWRITE: 4,
    MODE_DIALOGUE: 6,
    MODE_EXPAND: 6,
    MODE_BRAINSTORM: 8,
}

_MAX_NOTES = {
    MODE_REWRITE: 80,
    MODE_DIALOGUE: 100,
    MODE_EXPAND: 120,
    MODE_BRAINSTORM: 100,
}

_MAX_PROGRESSION = 60


def resolve_mode(action_key: str) -> str:
    return _MODE_MAP.get(action_key, MODE_REWRITE)


def orchestrate_psyke_context(
    db: Any,
    project_id: int,
    scene_id: int,
    mode: str,
    selected_text: str = "",
) -> OrchestrationResult:
    """Build mode-appropriate PSYKE context for an AI action."""

    entries = db.get_all_psyke_entries(project_id)
    if not entries:
        return OrchestrationResult(
            mode=mode, psyke_context="", entries_included=[],
            temporal_used=False, relations_used=False,
            decisions=["No PSYKE entries in project"],
        )

    scene = db.get_scene_by_id(scene_id)
    if scene is None:
        return OrchestrationResult(
            mode=mode, psyke_context="", entries_included=[],
            temporal_used=False, relations_used=False,
            decisions=["Scene not found"],
        )

    tg = TemporalGraph(db, project_id)
    all_scenes = db.get_all_scenes(project_id)
    scene_order_map = {s.id: s.sort_order for s in all_scenes}
    current_order = scene_order_map.get(scene_id, 0)

    if mode == MODE_REWRITE:
        return _orchestrate_rewrite(
            db, tg, entries, scene, current_order, selected_text,
        )
    elif mode == MODE_DIALOGUE:
        return _orchestrate_dialogue(
            db, tg, entries, scene, current_order, selected_text,
        )
    elif mode == MODE_EXPAND:
        return _orchestrate_expand(
            db, tg, entries, scene, current_order, selected_text,
        )
    elif mode == MODE_BRAINSTORM:
        return _orchestrate_brainstorm(
            db, tg, entries, scene, current_order, selected_text,
        )
    else:
        return _orchestrate_rewrite(
            db, tg, entries, scene, current_order, selected_text,
        )


def _orchestrate_rewrite(
    db, tg, entries, scene, current_order, selected_text,
) -> OrchestrationResult:
    """Rewrite: compact PSYKE, only entries mentioned in text."""
    decisions: list[str] = []
    scene_text = _scene_searchable_text(scene)
    match_text = f"{scene_text}\n{selected_text}" if selected_text else scene_text
    max_entries = _MAX_ENTRIES[MODE_REWRITE]
    max_notes = _MAX_NOTES[MODE_REWRITE]

    matched = []
    for e in entries:
        if e.is_global:
            continue
        if _entry_matches_scene(e, match_text):
            matched.append(e)
            if len(matched) >= max_entries:
                break

    if not matched:
        decisions.append("No entries matched selection/scene text")
        return OrchestrationResult(
            mode=MODE_REWRITE, psyke_context="", entries_included=[],
            temporal_used=False, relations_used=False, decisions=decisions,
        )

    lines = []
    temporal_used = False
    for e in matched:
        state = tg.get_entry_state_at(e.id, current_order)
        line = f"- {e.name} ({e.entry_type})"
        if e.notes:
            short = _truncate(e.notes.split("\n")[0], max_notes)
            line += f": {short}"
        if state and state.has_progression:
            prog = _truncate(state.progression_text, _MAX_PROGRESSION)
            line += f" | State: {prog}"
            temporal_used = True
        lines.append(line)
        lines.extend(render_psyke_details(e, per_field_max=max_notes * 2))

    decisions.append(f"Matched {len(matched)} entries to {'selection' if selected_text else 'scene'}")
    if temporal_used:
        decisions.append("Included latest progression for matched entries")

    ctx = "[PSYKE Context]\n\n" + "\n".join(lines)
    return OrchestrationResult(
        mode=MODE_REWRITE, psyke_context=ctx,
        entries_included=[e.name for e in matched],
        temporal_used=temporal_used, relations_used=False,
        decisions=decisions,
    )


def _orchestrate_dialogue(
    db, tg, entries, scene, current_order, selected_text: str = "",
) -> OrchestrationResult:
    """Dialogue: character-focused entries + one-hop character relations."""
    decisions: list[str] = []
    scene_text = _scene_searchable_text(scene)
    if selected_text:
        scene_text = f"{scene_text}\n{selected_text}"
    max_entries = _MAX_ENTRIES[MODE_DIALOGUE]
    max_notes = _MAX_NOTES[MODE_DIALOGUE]

    char_entries = []
    for e in entries:
        if e.is_global:
            continue
        if e.entry_type == "character" and _entry_matches_scene(e, scene_text):
            char_entries.append(e)
            if len(char_entries) >= max_entries:
                break

    if not char_entries:
        for e in entries:
            if e.is_global:
                continue
            if _entry_matches_scene(e, scene_text):
                char_entries.append(e)
                if len(char_entries) >= max_entries:
                    break
        decisions.append("No character entries matched; falling back to all matched entries")
    else:
        decisions.append(f"Found {len(char_entries)} character entries in scene")

    lines = []
    temporal_used = False
    relations_used = False
    seen_ids = {e.id for e in char_entries}

    for e in char_entries:
        state = tg.get_entry_state_at(e.id, current_order)
        line = f"- {e.name} ({e.entry_type})"
        if e.notes:
            short = _truncate(e.notes.split("\n")[0], max_notes)
            line += f": {short}"
        if state and state.has_progression:
            prog = _truncate(state.progression_text, _MAX_PROGRESSION)
            line += f" | State: {prog}"
            temporal_used = True
        lines.append(line)
        lines.extend(render_psyke_details(e, per_field_max=max_notes * 2))

    # One-hop character relations
    related_lines = []
    for e in char_entries:
        for rel in tg.get_active_related_entries(e.id, current_order):
            if rel.entry_id in seen_ids:
                continue
            if rel.entry_type != "character":
                continue
            if not rel.active:
                continue
            seen_ids.add(rel.entry_id)
            rline = f"- {rel.name} (related to {e.name})"
            if rel.state.has_progression:
                prog = _truncate(rel.state.progression_text, _MAX_PROGRESSION)
                rline += f" | State: {prog}"
            related_lines.append(rline)
            relations_used = True

    if relations_used:
        decisions.append(f"Included {len(related_lines)} related character(s)")
    if temporal_used:
        decisions.append("Included character progression states")

    if not lines and not related_lines:
        return OrchestrationResult(
            mode=MODE_DIALOGUE, psyke_context="", entries_included=[],
            temporal_used=False, relations_used=False,
            decisions=decisions + ["No applicable entries"],
        )

    parts = ["[PSYKE Context]", ""]
    if lines:
        parts.append("Characters:")
        parts.extend(lines)
    if related_lines:
        parts.append("")
        parts.append("Related:")
        parts.extend(related_lines)

    ctx = "\n".join(parts)
    return OrchestrationResult(
        mode=MODE_DIALOGUE, psyke_context=ctx,
        entries_included=[e.name for e in char_entries],
        temporal_used=temporal_used, relations_used=relations_used,
        decisions=decisions,
    )


def _orchestrate_expand(
    db, tg, entries, scene, current_order, selected_text: str = "",
) -> OrchestrationResult:
    """Expand: matched entries with moderate detail + conservative relations."""
    decisions: list[str] = []
    scene_text = _scene_searchable_text(scene)
    if selected_text:
        scene_text = f"{scene_text}\n{selected_text}"
    max_entries = _MAX_ENTRIES[MODE_EXPAND]
    max_notes = _MAX_NOTES[MODE_EXPAND]

    global_lines = []
    matched = []
    for e in entries:
        if e.is_global:
            short = _truncate(e.notes.split("\n")[0] if e.notes else "", 80)
            global_lines.append(f"- {e.name} ({e.entry_type}): {short}" if short else f"- {e.name} ({e.entry_type})")
            global_lines.extend(render_psyke_details(e, per_field_max=150))
        elif _entry_matches_scene(e, scene_text):
            matched.append(e)
            if len(matched) >= max_entries:
                break

    lines = []
    temporal_used = False
    relations_used = False
    seen_ids = {e.id for e in matched}

    for e in matched:
        state = tg.get_entry_state_at(e.id, current_order)
        line = f"- {e.name} ({e.entry_type})"
        if e.notes:
            short = _truncate(e.notes.split("\n")[0], max_notes)
            line += f": {short}"
        if state and state.has_progression:
            prog = _truncate(state.progression_text, _MAX_PROGRESSION)
            line += f" | State: {prog}"
            temporal_used = True
        lines.append(line)
        lines.extend(render_psyke_details(e, per_field_max=max_notes * 2))

    # Conservative one-hop relations
    related_lines = []
    for e in matched[:3]:
        for rel in tg.get_active_related_entries(e.id, current_order):
            if rel.entry_id in seen_ids:
                continue
            if not rel.active:
                continue
            seen_ids.add(rel.entry_id)
            related_lines.append(f"- {rel.name} ({rel.entry_type})")
            relations_used = True
            if len(related_lines) >= 3:
                break
        if len(related_lines) >= 3:
            break

    decisions.append(f"Matched {len(matched)} entries, {len(global_lines)} global")
    if temporal_used:
        decisions.append("Included progression states for continuity")
    if relations_used:
        decisions.append(f"Included {len(related_lines)} related entry names")

    if not lines and not global_lines:
        return OrchestrationResult(
            mode=MODE_EXPAND, psyke_context="", entries_included=[],
            temporal_used=False, relations_used=False, decisions=decisions,
        )

    parts = ["[PSYKE Context]"]
    if global_lines:
        parts.append("")
        parts.append("Global:")
        parts.extend(global_lines)
    if lines:
        parts.append("")
        parts.append("Relevant:")
        parts.extend(lines)
    if related_lines:
        parts.append("")
        parts.append("Related:")
        parts.extend(related_lines)

    ctx = "\n".join(parts)
    return OrchestrationResult(
        mode=MODE_EXPAND, psyke_context=ctx,
        entries_included=[e.name for e in matched],
        temporal_used=temporal_used, relations_used=relations_used,
        decisions=decisions,
    )


def _orchestrate_brainstorm(
    db, tg, entries, scene, current_order, selected_text: str = "",
) -> OrchestrationResult:
    """Brainstorm: global + active entities + temporal state."""
    decisions: list[str] = []
    scene_text = _scene_searchable_text(scene)
    if selected_text:
        scene_text = f"{scene_text}\n{selected_text}"
    max_entries = _MAX_ENTRIES[MODE_BRAINSTORM]

    global_lines = []
    active_lines = []
    active_entries = []
    temporal_used = False
    relations_used = False
    seen_ids: set[int] = set()

    for e in entries:
        if e.is_global:
            short = _truncate(e.notes.split("\n")[0] if e.notes else "", 80)
            line = f"- {e.name} ({e.entry_type})"
            if short:
                line += f": {short}"
            global_lines.append(line)
            global_lines.extend(render_psyke_details(e, per_field_max=150))
            seen_ids.add(e.id)

    for e in entries:
        if e.id in seen_ids:
            continue
        state = tg.get_entry_state_at(e.id, current_order)
        if state is None:
            continue
        is_relevant = _entry_matches_scene(e, scene_text) or state.has_progression
        if is_relevant and len(active_entries) < max_entries:
            seen_ids.add(e.id)
            active_entries.append(e)
            line = f"- {e.name} ({e.entry_type})"
            if state.has_progression:
                prog = _truncate(state.progression_text, _MAX_PROGRESSION)
                line += f" | State: {prog}"
                temporal_used = True
            active_lines.append(line)
            active_lines.extend(render_psyke_details(e, per_field_max=200))

    # One-hop relations for active entries
    related_lines = []
    for e in active_entries[:4]:
        for rel in tg.get_active_related_entries(e.id, current_order):
            if rel.entry_id in seen_ids:
                continue
            if not rel.active:
                continue
            seen_ids.add(rel.entry_id)
            rline = f"- {rel.name} ({rel.entry_type})"
            if rel.state.has_progression:
                prog = _truncate(rel.state.progression_text, _MAX_PROGRESSION)
                rline += f" | State: {prog}"
            related_lines.append(rline)
            relations_used = True
            if len(related_lines) >= 4:
                break
        if len(related_lines) >= 4:
            break

    decisions.append(f"{len(global_lines)} global, {len(active_lines)} active at scene order {current_order}")
    if temporal_used:
        decisions.append("Included temporal state for active entities")
    if relations_used:
        decisions.append(f"Included {len(related_lines)} related entries")

    if not global_lines and not active_lines:
        return OrchestrationResult(
            mode=MODE_BRAINSTORM, psyke_context="", entries_included=[],
            temporal_used=False, relations_used=False, decisions=decisions,
        )

    parts = ["[PSYKE Context]"]
    if global_lines:
        parts.append("")
        parts.append("Global:")
        parts.extend(global_lines)
    if active_lines:
        parts.append("")
        parts.append("Active:")
        parts.extend(active_lines)
    if related_lines:
        parts.append("")
        parts.append("Related:")
        parts.extend(related_lines)

    ctx = "\n".join(parts)
    return OrchestrationResult(
        mode=MODE_BRAINSTORM, psyke_context=ctx,
        entries_included=[e.name for e in active_entries],
        temporal_used=temporal_used, relations_used=relations_used,
        decisions=decisions,
    )


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] + "..."


def format_orchestration_debug(result: OrchestrationResult) -> str:
    """Format orchestration metadata for the context preview panel."""
    lines = [
        f"--- Orchestration ({result.mode}) ---",
        f"Entries: {', '.join(result.entries_included) or '(none)'}",
        f"Temporal: {'yes' if result.temporal_used else 'no'}",
        f"Relations: {'yes' if result.relations_used else 'no'}",
    ]
    for d in result.decisions:
        lines.append(f"  • {d}")
    return "\n".join(lines)
