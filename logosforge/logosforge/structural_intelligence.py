"""Structural Intelligence — PSYKE-driven narrative structure analysis.

Analyzes story structure using PSYKE entries, scenes, outline, and temporal
state to detect structural weaknesses and suggest improvements.  All
computation is read-only; nothing is written to the database.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from logosforge.db import Database
from logosforge.narrative_dashboard import (
    CharacterPresence,
    NarrativeDashboardData,
    StructureDistribution,
    TensionCurve,
    ThemePresence,
    compute_dashboard,
)
from logosforge.story_structure import BEAT_ORDER
from logosforge.temporal_psyke import TemporalGraph


# -- Data types ---------------------------------------------------------------

@dataclass(frozen=True)
class StructuralIssue:
    issue_type: str
    category: str
    severity: float
    message: str
    suggestion: str
    data: dict = field(default_factory=dict)


@dataclass
class StructuralAnalysis:
    issues: list[StructuralIssue]
    suggestions: list[str]
    computed_at: float = 0.0


# -- Beat position expectations (fraction of total scenes) -------------------

_BEAT_POSITIONS: dict[str, tuple[float, float]] = {
    "Opening Image": (0.0, 0.05),
    "Setup": (0.0, 0.15),
    "Catalyst": (0.08, 0.20),
    "Debate": (0.12, 0.25),
    "Break into Two": (0.20, 0.30),
    "Midpoint": (0.40, 0.60),
    "Bad Guys Close In": (0.50, 0.75),
    "All Is Lost": (0.65, 0.80),
    "Break into Three": (0.70, 0.85),
    "Finale": (0.80, 1.0),
    "Final Image": (0.90, 1.0),
}

_MAX_ISSUES = 5
_MIN_SCENES = 4


# -- Main entry point ---------------------------------------------------------

def compute_structural_analysis(
    db: Database,
    project_id: int,
    temporal_graph: TemporalGraph | None = None,
) -> StructuralAnalysis:
    scenes = db.get_all_scenes(project_id)
    if len(scenes) < _MIN_SCENES:
        return StructuralAnalysis(issues=[], suggestions=[], computed_at=time.monotonic())

    dashboard = compute_dashboard(db, project_id)

    if temporal_graph is None:
        temporal_graph = TemporalGraph(db, project_id)

    issues: list[StructuralIssue] = []
    issues.extend(_detect_act_balance(dashboard.structure))
    issues.extend(_detect_arc_completion(temporal_graph, scenes))
    issues.extend(_detect_climax_preparation(dashboard.tension))
    issues.extend(_detect_tension_curve(dashboard.tension))
    issues.extend(_detect_theme_continuity(dashboard.themes, len(scenes)))
    issues.extend(_detect_character_presence(dashboard.characters, len(scenes)))
    issues.extend(_detect_beat_placement(scenes))

    issues.sort(key=lambda i: i.severity, reverse=True)
    issues = issues[:_MAX_ISSUES]

    suggestions = [i.suggestion for i in issues if i.suggestion]

    return StructuralAnalysis(
        issues=issues,
        suggestions=suggestions,
        computed_at=time.monotonic(),
    )


# -- A. Act Balance -----------------------------------------------------------

def _detect_act_balance(structure: StructureDistribution) -> list[StructuralIssue]:
    issues: list[StructuralIssue] = []
    segments = structure.segments
    if len(segments) < 2:
        return issues

    word_counts = [seg.word_count for seg in segments]
    avg = sum(word_counts) / len(word_counts) if word_counts else 0
    if avg == 0:
        return issues

    for seg in segments:
        ratio = seg.word_count / avg
        if ratio < 0.3:
            severity = min(1.0, (0.3 - ratio) / 0.25)
            issues.append(StructuralIssue(
                issue_type="weak_act",
                category="act_balance",
                severity=severity,
                message=f"{seg.label} appears underdeveloped ({seg.word_count} words).",
                suggestion=f"Expand {seg.label} with rising-stakes scenes or deeper character moments.",
                data={"act": seg.label, "words": seg.word_count, "avg": int(avg)},
            ))

    if len(segments) >= 3:
        mid_idx = len(segments) // 2
        mid = segments[mid_idx]
        others = [s.word_count for i, s in enumerate(segments) if i != mid_idx]
        others_avg = sum(others) / len(others) if others else 0
        if others_avg > 0 and mid.word_count < others_avg * 0.4:
            severity = min(1.0, (0.4 - mid.word_count / others_avg) / 0.3)
            issues.append(StructuralIssue(
                issue_type="weak_middle",
                category="act_balance",
                severity=max(severity, 0.6),
                message=f"Middle section ({mid.label}) is thin compared to outer acts.",
                suggestion="The middle carries the story's complications — add subplots, reversals, or deeper conflict.",
                data={"mid_act": mid.label, "mid_words": mid.word_count, "others_avg": int(others_avg)},
            ))

    return issues


# -- B. Arc Completion --------------------------------------------------------

def _detect_arc_completion(
    tg: TemporalGraph, scenes: list,
) -> list[StructuralIssue]:
    issues: list[StructuralIssue] = []
    if not scenes:
        return issues

    total = len(scenes)
    cutoff_order = scenes[int(total * 0.6)].sort_order if total > 1 else 0

    for entry_id, entry in tg._entries.items():
        if entry.is_global:
            continue
        if entry.entry_type not in ("character", "theme"):
            continue

        progs = tg._progressions.get(entry_id, [])
        if not progs:
            issues.append(StructuralIssue(
                issue_type="static_arc",
                category="arc_completion",
                severity=0.5,
                message=f"{entry.name} has no progression — static arc.",
                suggestion=f"Add progression milestones for {entry.name} to show growth or change.",
                data={"entry_id": entry_id, "entry_name": entry.name},
            ))
            continue

        anchored = [p for p in progs if p.scene_sort_order is not None]
        if not anchored:
            continue

        last_prog_order = max(p.scene_sort_order for p in anchored)
        if last_prog_order <= cutoff_order:
            last_scene_order = scenes[-1].sort_order
            if last_scene_order > 0:
                fraction = last_prog_order / last_scene_order
                severity = min(1.0, (0.6 - fraction) / 0.4) if fraction < 0.6 else 0.3
                issues.append(StructuralIssue(
                    issue_type="abandoned_arc",
                    category="arc_completion",
                    severity=max(severity, 0.35),
                    message=f"{entry.name}'s arc stops at {int(fraction * 100)}% of the story.",
                    suggestion=f"Continue {entry.name}'s progression into the final act — resolve or transform their arc.",
                    data={"entry_id": entry_id, "entry_name": entry.name, "last_at": fraction},
                ))

    return issues


# -- C. Climax Preparation ----------------------------------------------------

def _detect_climax_preparation(tension: TensionCurve) -> list[StructuralIssue]:
    issues: list[StructuralIssue] = []
    points = tension.points
    if len(points) < 5:
        return issues

    scores = [p.score for p in points]
    overall_avg = sum(scores) / len(scores)

    peak_idx = max(range(len(scores)), key=lambda i: scores[i])
    peak_score = scores[peak_idx]
    total = len(points)

    last_third_start = int(total * 0.7)
    if peak_idx >= last_third_start and peak_idx >= 3:
        preceding = scores[peak_idx - 3:peak_idx]
        if preceding and sum(preceding) / len(preceding) < overall_avg * 0.7:
            severity = 0.65
            issues.append(StructuralIssue(
                issue_type="unprepared_climax",
                category="climax_preparation",
                severity=severity,
                message="Climax scene lacks buildup — preceding scenes have low tension.",
                suggestion="Add escalation before the climax: raise stakes, increase obstacles, or tighten pacing.",
                data={"peak_scene": points[peak_idx].scene_id, "peak_score": peak_score},
            ))

    first_third_end = max(1, total // 3)
    first_avg = sum(scores[:first_third_end]) / first_third_end
    last_third_scores = scores[last_third_start:]
    if last_third_scores:
        last_max = max(last_third_scores)
        threshold = max(first_avg * 1.5, overall_avg * 1.2)
        if last_max < threshold and overall_avg > 5:
            issues.append(StructuralIssue(
                issue_type="weak_climax_build",
                category="climax_preparation",
                severity=0.55,
                message="No clear escalation toward the climax in the final third.",
                suggestion="The ending should peak — bring conflicts to a head and force decisive action.",
                data={"last_max": last_max, "threshold": threshold},
            ))

    return issues


# -- D. Tension Curve ---------------------------------------------------------

def _detect_tension_curve(tension: TensionCurve) -> list[StructuralIssue]:
    issues: list[StructuralIssue] = []
    points = tension.points
    if len(points) < 5:
        return issues

    scores = [p.score for p in points]
    n = len(scores)
    mean = sum(scores) / n

    if mean > 0:
        variance = sum((s - mean) ** 2 for s in scores) / n
        std = variance ** 0.5
        cv = std / mean
        if cv < 0.2:
            issues.append(StructuralIssue(
                issue_type="flat_pacing",
                category="tension_curve",
                severity=0.5,
                message="Tension is flat — scenes have similar intensity throughout.",
                suggestion="Vary the pacing: alternate high-tension and reflective scenes.",
                data={"cv": round(cv, 3), "mean": round(mean, 1)},
            ))

    slope = _linear_slope(scores)
    if slope <= 0 and mean > 5:
        issues.append(StructuralIssue(
            issue_type="no_rising_stakes",
            category="tension_curve",
            severity=0.45,
            message="No rising stakes — tension doesn't increase across the story.",
            suggestion="Introduce escalating obstacles: each act should raise the pressure on your protagonist.",
            data={"slope": round(slope, 4)},
        ))

    return issues


def _linear_slope(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    if denominator == 0:
        return 0.0
    return numerator / denominator


# -- E. Theme Continuity ------------------------------------------------------

def _detect_theme_continuity(
    themes: list[ThemePresence], total_scenes: int,
) -> list[StructuralIssue]:
    issues: list[StructuralIssue] = []
    if total_scenes < _MIN_SCENES:
        return issues

    third = total_scenes // 3

    for theme in themes:
        present = set(theme.present_scenes)

        if total_scenes > 0 and len(present) < total_scenes * 0.15:
            issues.append(StructuralIssue(
                issue_type="theme_underused",
                category="theme_continuity",
                severity=0.4,
                message=f"Theme \"{theme.name}\" appears in very few scenes.",
                suggestion=f"Weave \"{theme.name}\" more consistently — reference it in dialogue, imagery, or character decisions.",
                data={"entry_id": theme.entry_id, "present_count": len(present), "total": total_scenes},
            ))

        if present and third > 0:
            first_third = set(range(third))
            last_third = set(range(total_scenes - third, total_scenes))
            in_first = bool(present & first_third)
            in_last = bool(present & last_third)
            if in_first and not in_last:
                issues.append(StructuralIssue(
                    issue_type="theme_abandoned",
                    category="theme_continuity",
                    severity=0.5,
                    message=f"Theme \"{theme.name}\" is introduced early but disappears in the final act.",
                    suggestion=f"Revisit \"{theme.name}\" in the conclusion — themes should echo at the end.",
                    data={"entry_id": theme.entry_id, "name": theme.name},
                ))

    return issues


# -- F. Character Presence ----------------------------------------------------

def _detect_character_presence(
    characters: list[CharacterPresence], total_scenes: int,
) -> list[StructuralIssue]:
    issues: list[StructuralIssue] = []
    if total_scenes < _MIN_SCENES:
        return issues

    for char in characters:
        present = char.present_scenes
        if not present:
            continue

        gap_threshold = max(3, int(total_scenes * 0.3))

        if len(present) >= 3:
            max_gap = _max_consecutive_gap(present, total_scenes)
            if max_gap >= gap_threshold:
                issues.append(StructuralIssue(
                    issue_type="key_character_missing",
                    category="character_presence",
                    severity=min(0.6, 0.3 + max_gap / total_scenes),
                    message=f"{char.name} disappears for {max_gap} consecutive scenes.",
                    suggestion=f"Reference {char.name} during the gap — even a mention keeps them alive in the reader's mind.",
                    data={"entry_id": char.entry_id, "name": char.name, "gap": max_gap},
                ))

    return issues


def _max_consecutive_gap(present_orders: list[int], total: int) -> int:
    if not present_orders:
        return 0
    present_set = set(present_orders)
    max_gap = 0
    current = 0
    for i in range(total):
        if i in present_set:
            current = 0
        else:
            current += 1
            max_gap = max(max_gap, current)
    return max_gap


# -- Beat Placement (optional template awareness) -----------------------------

def _detect_beat_placement(scenes: list) -> list[StructuralIssue]:
    issues: list[StructuralIssue] = []
    total = len(scenes)
    if total < _MIN_SCENES:
        return issues

    beat_scenes: dict[str, list[int]] = {}
    for i, scene in enumerate(scenes):
        if scene.beat:
            beat_scenes.setdefault(scene.beat, []).append(i)

    has_any_known = any(b in BEAT_ORDER for b in beat_scenes)
    if not has_any_known:
        return issues

    assigned_known = [b for b in BEAT_ORDER if b in beat_scenes]
    missing = [b for b in BEAT_ORDER if b not in beat_scenes]

    if missing and len(assigned_known) >= 3:
        top_missing = missing[:3]
        issues.append(StructuralIssue(
            issue_type="missing_beats",
            category="beat_placement",
            severity=0.35,
            message=f"Missing beats: {', '.join(top_missing)}.",
            suggestion=f"Consider adding scenes for {top_missing[0]} to strengthen your structure.",
            data={"missing": missing},
        ))

    for beat_name, indices in beat_scenes.items():
        if beat_name not in _BEAT_POSITIONS:
            continue
        expected_lo, expected_hi = _BEAT_POSITIONS[beat_name]
        for idx in indices:
            position = idx / total
            if position < expected_lo - 0.1 or position > expected_hi + 0.1:
                issues.append(StructuralIssue(
                    issue_type="misplaced_beat",
                    category="beat_placement",
                    severity=0.3,
                    message=f"\"{beat_name}\" is at {int(position * 100)}% — expected around {int((expected_lo + expected_hi) / 2 * 100)}%.",
                    suggestion=f"Consider moving \"{beat_name}\" or adding scenes around it to shift its position.",
                    data={"beat": beat_name, "actual": round(position, 2), "expected": (expected_lo, expected_hi)},
                ))
                break

    return issues


# -- Context for assistant integration ----------------------------------------

def gather_structural_context(
    db: Database, project_id: int,
    temporal_graph: TemporalGraph | None = None,
) -> str:
    analysis = compute_structural_analysis(db, project_id, temporal_graph)
    if not analysis.issues:
        return ""

    lines = ["[Structural Analysis]"]
    lines.append("")
    for issue in analysis.issues[:3]:
        lines.append(f"- {issue.message}")
        if issue.suggestion:
            lines.append(f"  Suggestion: {issue.suggestion}")
    return "\n".join(lines)


# -- Cache wrapper for UI integration ----------------------------------------

_CACHE_TTL = 30.0


class StructuralCache:
    """Caches structural analysis results with a TTL."""

    def __init__(self) -> None:
        self._result: StructuralAnalysis | None = None
        self._dirty = True

    def mark_dirty(self) -> None:
        self._dirty = True

    def get(
        self, db: Database, project_id: int,
        temporal_graph: TemporalGraph | None = None,
    ) -> StructuralAnalysis:
        now = time.monotonic()
        if (
            self._result is not None
            and not self._dirty
            and now - self._result.computed_at < _CACHE_TTL
        ):
            return self._result

        self._result = compute_structural_analysis(db, project_id, temporal_graph)
        self._dirty = False
        return self._result

    def invalidate(self) -> None:
        self._result = None
        self._dirty = True
