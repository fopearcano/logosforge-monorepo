"""Adaptive AI Behavior — mode-specific suggestion generators.

Produces deterministic suggestions tailored to the current AI mode:
- Structure: what's missing from the skeleton
- Balance: what's uneven in distribution
- Refinement: what could be better in existing content
"""

from __future__ import annotations

from dataclasses import dataclass

from logosforge.adaptive_mode import AIMode, compute_mode, ModeResult
from logosforge.db import Database


@dataclass
class ModeSuggestion:
    text: str
    category: str  # "structure", "balance", "refinement"


MAX_SUGGESTIONS = 5


def generate_mode_suggestions(db: Database, project_id: int) -> tuple[ModeResult, list[ModeSuggestion]]:
    """Generate suggestions appropriate to the current AI mode."""
    mode_result = compute_mode(db, project_id)

    if mode_result.mode == AIMode.STRUCTURE:
        suggestions = _structure_suggestions(db, project_id)
    elif mode_result.mode == AIMode.BALANCE:
        suggestions = _balance_suggestions(db, project_id)
    else:
        suggestions = _refinement_suggestions(db, project_id)

    return mode_result, suggestions[:MAX_SUGGESTIONS]


def _structure_suggestions(db: Database, project_id: int) -> list[ModeSuggestion]:
    """Structure mode: identify what's missing from the story skeleton."""
    scenes = db.get_all_scenes(project_id)
    characters = db.get_all_characters(project_id)
    suggestions: list[ModeSuggestion] = []

    if not scenes:
        suggestions.append(ModeSuggestion(
            "Start by creating your first scene to establish the world.",
            "structure",
        ))
        return suggestions

    total = len(scenes)

    # Missing acts
    acts = {s.act for s in scenes if s.act}
    if len(acts) == 0:
        suggestions.append(ModeSuggestion(
            "Define act structure — assign scenes to acts for narrative shape.",
            "structure",
        ))
    elif len(acts) == 1:
        suggestions.append(ModeSuggestion(
            "Story has only one act — consider adding a second act for progression.",
            "structure",
        ))

    # Missing plotlines
    plotlines = {s.plotline for s in scenes if s.plotline}
    if len(plotlines) == 0:
        suggestions.append(ModeSuggestion(
            "Assign plotlines to scenes — this creates narrative threads to follow.",
            "structure",
        ))
    elif len(plotlines) == 1 and total >= 5:
        suggestions.append(ModeSuggestion(
            "Consider a subplot to add depth and contrast to the main storyline.",
            "structure",
        ))

    # Unlinked characters
    unlinked = []
    for char in characters:
        scene_char_map = db.get_scene_character_ids
        has_scene = False
        for scene in scenes:
            if char.id in db.get_scene_character_ids(scene.id):
                has_scene = True
                break
        if not has_scene:
            unlinked.append(char.name)

    if unlinked:
        name = unlinked[0]
        suggestions.append(ModeSuggestion(
            f"Character \"{name}\" has no scenes — add a scene to introduce them.",
            "structure",
        ))

    # Missing conflict
    scenes_without_conflict = [s for s in scenes if not s.conflict and not s.goal]
    ratio = len(scenes_without_conflict) / total if total > 0 else 0
    if ratio > 0.7 and total >= 3:
        suggestions.append(ModeSuggestion(
            "Most scenes lack defined goals or conflicts — add dramatic questions.",
            "structure",
        ))

    # Low scene count for characters
    if len(characters) >= 2 and total < len(characters) * 2:
        suggestions.append(ModeSuggestion(
            "More scenes needed — characters need room to develop relationships.",
            "structure",
        ))

    return suggestions


def _balance_suggestions(db: Database, project_id: int) -> list[ModeSuggestion]:
    """Balance mode: identify distribution problems."""
    from logosforge.character_balance import compute_balance

    scenes = db.get_all_scenes(project_id)
    characters = db.get_all_characters(project_id)
    balance = compute_balance(db, project_id)
    suggestions: list[ModeSuggestion] = []
    total = len(scenes)

    if total == 0:
        return suggestions

    # Dominant characters
    for p in balance.characters:
        if p.flag == "dominant":
            suggestions.append(ModeSuggestion(
                f"\"{p.name}\" dominates — shift focus to other characters in upcoming scenes.",
                "balance",
            ))
            break

    # Underused characters
    underused = [p for p in balance.characters if p.flag == "underused"]
    if underused:
        name = underused[0].name
        suggestions.append(ModeSuggestion(
            f"Reintroduce \"{name}\" — they've been absent too long.",
            "balance",
        ))

    # Thin arcs
    for arc in balance.arcs:
        if arc.flag == "thin":
            suggestions.append(ModeSuggestion(
                f"Arc \"{arc.plotline}\" needs development — add scenes to sustain it.",
                "balance",
            ))
            break

    # Pacing monotony — consecutive same plotline
    run = 1
    max_run = 1
    max_pl = ""
    for i in range(1, total):
        pl = scenes[i].plotline or ""
        prev = scenes[i - 1].plotline or ""
        if pl and pl == prev:
            run += 1
            if run > max_run:
                max_run = run
                max_pl = pl
        else:
            run = 1

    if max_run >= 4:
        suggestions.append(ModeSuggestion(
            f"Break up the {max_run}-scene streak in \"{max_pl}\" with a different thread.",
            "balance",
        ))

    # Act imbalance
    act_counts: dict[str, int] = {}
    for s in scenes:
        if s.act:
            act_counts[s.act] = act_counts.get(s.act, 0) + 1
    if len(act_counts) >= 2:
        max_act_count = max(act_counts.values())
        min_act_count = min(act_counts.values())
        if max_act_count > min_act_count * 3:
            short_act = min(act_counts, key=act_counts.get)
            suggestions.append(ModeSuggestion(
                f"\"{short_act}\" is very short compared to others — expand it for better pacing.",
                "balance",
            ))

    return suggestions


def _refinement_suggestions(db: Database, project_id: int) -> list[ModeSuggestion]:
    """Refinement mode: subtle quality improvements for mature stories."""
    scenes = db.get_all_scenes(project_id)
    characters = db.get_all_characters(project_id)
    suggestions: list[ModeSuggestion] = []
    total = len(scenes)

    if total == 0:
        return suggestions

    # Dialogue density — scenes with content but no dialogue markers
    scenes_with_content = [s for s in scenes if len(s.content or "") > 200]
    no_dialogue = []
    for s in scenes_with_content:
        content = s.content or ""
        has_quotes = '"' in content or '\u201c' in content or '\u2014' in content
        if not has_quotes:
            no_dialogue.append(s)

    if no_dialogue and len(no_dialogue) >= 2:
        suggestions.append(ModeSuggestion(
            "Several scenes lack dialogue — consider adding character voices.",
            "refinement",
        ))
    elif no_dialogue:
        suggestions.append(ModeSuggestion(
            f"\"{no_dialogue[0].title}\" has no dialogue — could benefit from character interaction.",
            "refinement",
        ))

    # Short scenes that could be expanded
    short_scenes = [s for s in scenes if 50 < len(s.content or "") < 200]
    if short_scenes:
        s = short_scenes[0]
        suggestions.append(ModeSuggestion(
            f"\"{s.title}\" is thin — add sensory detail or emotional depth.",
            "refinement",
        ))

    # Stagnant character states — same state repeated
    for char in characters[:3]:
        states = []
        for scene in scenes:
            scene_states = db.get_scene_character_states(scene.id)
            for cid, state in scene_states:
                if cid == char.id and state:
                    states.append(state)
        if len(states) >= 3:
            unique = set(states)
            if len(unique) == 1:
                suggestions.append(ModeSuggestion(
                    f"\"{char.name}\" stays in \"{states[0]}\" state — show internal evolution.",
                    "refinement",
                ))
                break

    # Scenes without emotional contrast to neighbors
    for i in range(1, total - 1):
        prev_len = len(scenes[i - 1].content or "")
        curr_len = len(scenes[i].content or "")
        next_len = len(scenes[i + 1].content or "")
        if prev_len > 500 and curr_len > 500 and next_len > 500:
            suggestions.append(ModeSuggestion(
                "Consider varying scene intensity — consecutive dense scenes reduce impact.",
                "refinement",
            ))
            break

    # Summary/synopsis quality
    scenes_missing_summary = [s for s in scenes if not s.summary and not s.synopsis]
    if scenes_missing_summary and len(scenes_missing_summary) <= total * 0.3:
        suggestions.append(ModeSuggestion(
            f"\"{scenes_missing_summary[0].title}\" lacks a summary — add one for outline clarity.",
            "refinement",
        ))

    return suggestions
