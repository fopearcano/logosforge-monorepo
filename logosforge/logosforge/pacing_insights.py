"""Pacing & Insight System — subtle story rhythm analysis.

Detects pacing issues: monotony, disappearances, stagnation, arc neglect, clustering.
Returns max 5 short insights sorted by severity.
"""

from __future__ import annotations

from dataclasses import dataclass

from logosforge.db import Database


@dataclass
class Insight:
    text: str
    severity: float  # 0.0–1.0, higher = more important
    category: str  # "disappearance", "monotony", "stagnation", "neglect", "clustering"


MIN_SCENES = 5


def generate_insights(db: Database, project_id: int) -> list[Insight]:
    """Analyze project pacing and return up to 5 insights."""
    scenes = db.get_all_scenes(project_id)
    if len(scenes) < MIN_SCENES:
        return []

    characters = db.get_all_characters(project_id)
    total = len(scenes)

    scene_char_map: dict[int, list[int]] = {}
    for i, scene in enumerate(scenes):
        char_ids = db.get_scene_character_ids(scene.id)
        scene_char_map[i] = char_ids

    insights: list[Insight] = []

    disappearance = _detect_disappearance(scenes, characters, scene_char_map, total)
    if disappearance:
        insights.append(disappearance)

    monotony = _detect_monotony(scenes, scene_char_map, total)
    if monotony:
        insights.append(monotony)

    stagnation = _detect_stagnation(scenes, scene_char_map, total)
    if stagnation:
        insights.append(stagnation)

    neglect = _detect_arc_neglect(scenes, total)
    if neglect:
        insights.append(neglect)

    clustering = _detect_clustering(scenes, characters, scene_char_map, total)
    if clustering:
        insights.append(clustering)

    insights.sort(key=lambda i: i.severity, reverse=True)
    return insights[:5]


def _detect_disappearance(scenes, characters, scene_char_map, total) -> Insight | None:
    """Character appears then vanishes for >40% of story."""
    threshold = 0.4
    worst_name = ""
    worst_gap = 0.0

    for char in characters:
        appearances = [i for i in range(total) if char.id in scene_char_map[i]]
        if len(appearances) < 2:
            continue
        max_gap = 0
        for j in range(1, len(appearances)):
            gap = appearances[j] - appearances[j - 1] - 1
            max_gap = max(max_gap, gap)

        gap_ratio = max_gap / total
        if gap_ratio > threshold and gap_ratio > worst_gap:
            worst_gap = gap_ratio
            worst_name = char.name

    if worst_name:
        severity = min(1.0, worst_gap / 0.8)
        gap_scenes = int(round(worst_gap * total))
        return Insight(
            text=(f"{worst_name} disappears for {gap_scenes} scenes in a row "
                  f"(~{int(worst_gap * 100)}% of the story)."),
            severity=severity,
            category="disappearance",
        )
    return None


def _detect_monotony(scenes, scene_char_map, total) -> Insight | None:
    """Consecutive scenes sharing same plotline or character set (4+)."""
    threshold = 4
    worst_run = 0
    worst_label = ""

    # Check plotline monotony
    run = 1
    for i in range(1, total):
        pl = scenes[i].plotline or ""
        prev_pl = scenes[i - 1].plotline or ""
        if pl and pl == prev_pl:
            run += 1
            if run > worst_run:
                worst_run = run
                worst_label = f"plotline \"{pl}\""
        else:
            run = 1

    # Check character-set monotony
    run = 1
    for i in range(1, total):
        curr = set(scene_char_map[i])
        prev = set(scene_char_map[i - 1])
        if curr and curr == prev:
            run += 1
            if run > worst_run:
                worst_run = run
                worst_label = "same character set"
        else:
            run = 1

    if worst_run >= threshold:
        severity = min(1.0, (worst_run - threshold + 1) / 4)
        return Insight(
            text=(f"{worst_run} consecutive scenes use {worst_label} "
                  f"(4+ in a row reads as repetitive)."),
            severity=severity,
            category="monotony",
        )
    return None


def _detect_stagnation(scenes, scene_char_map, total) -> Insight | None:
    """Middle third has less character/plotline variety than outer thirds."""
    if total < 6:
        return None

    third = total // 3
    start_scenes = scenes[:third]
    mid_scenes = scenes[third:2 * third]
    end_scenes = scenes[2 * third:]

    def diversity(scene_slice, offset):
        chars = set()
        plotlines = set()
        for j, s in enumerate(scene_slice):
            idx = offset + j
            chars.update(scene_char_map.get(idx, []))
            if s.plotline:
                plotlines.add(s.plotline)
        return len(chars) + len(plotlines)

    outer_diversity = (diversity(start_scenes, 0) + diversity(end_scenes, 2 * third)) / 2
    mid_diversity = diversity(mid_scenes, third)

    if outer_diversity > 0:
        ratio = mid_diversity / outer_diversity
        if ratio < 0.5:
            severity = min(1.0, (0.5 - ratio) / 0.4)
            return Insight(
                text=(f"Middle section has ~{int(ratio * 100)}% the variety "
                      f"of the opening and ending (target: 50%+)."),
                severity=severity,
                category="stagnation",
            )
    return None


def _detect_arc_neglect(scenes, total) -> Insight | None:
    """A plotline appears in only 1 act when 3+ acts exist."""
    arc_acts: dict[str, set[str]] = {}
    all_acts: set[str] = set()

    for scene in scenes:
        pl = scene.plotline or ""
        act = scene.act or ""
        if pl:
            if pl not in arc_acts:
                arc_acts[pl] = set()
            if act:
                arc_acts[pl].add(act)
        if act:
            all_acts.add(act)

    if len(all_acts) < 3:
        return None

    worst_pl = ""
    worst_score = 0.0

    for pl, acts in arc_acts.items():
        if len(acts) == 1:
            score = 0.7
            if score > worst_score:
                worst_score = score
                worst_pl = pl

    if worst_pl:
        return Insight(
            text=(f"Arc \"{worst_pl}\" appears in only 1 of "
                  f"{len(all_acts)} acts."),
            severity=worst_score,
            category="neglect",
        )
    return None


def _detect_clustering(scenes, characters, scene_char_map, total) -> Insight | None:
    """Character appears only in one tight cluster (all within 30% of story span)."""
    threshold = 0.3
    worst_name = ""
    worst_score = 0.0
    worst_span = 1.0

    for char in characters:
        appearances = [i for i in range(total) if char.id in scene_char_map[i]]
        if len(appearances) < 2:
            continue
        span = appearances[-1] - appearances[0] + 1
        span_ratio = span / total
        if span_ratio <= threshold and len(appearances) >= 2:
            score = min(1.0, (threshold - span_ratio) / 0.2 * 0.6 + 0.3)
            if score > worst_score:
                worst_score = score
                worst_name = char.name
                worst_span = span_ratio

    if worst_name:
        return Insight(
            text=(f"{worst_name} only appears within {int(worst_span * 100)}% "
                  f"of the story's span (a brief cluster)."),
            severity=worst_score,
            category="clustering",
        )
    return None


def insight_color(category: str) -> str:
    """Map each insight category to a DISTINCT indicator color, so the dot
    identifies the kind of issue at a glance (previously three categories
    shared the same amber, which was hard to tell apart)."""
    colors = {
        "disappearance": "#f59e0b",   # amber
        "monotony": "#a855f7",        # purple
        "stagnation": "#ef4444",      # red
        "neglect": "#0ea5e9",         # sky
        "clustering": "#6366f1",      # indigo
    }
    return colors.get(category, "#9ca3af")
