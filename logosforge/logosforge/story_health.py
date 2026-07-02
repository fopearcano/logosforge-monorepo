"""Story Health — high-level narrative status indicators.

Computes four structural health signals and maps each to a simple
label + percentage for compact visual display.
"""

from __future__ import annotations

from dataclasses import dataclass

from logosforge.db import Database


@dataclass
class HealthSignal:
    label: str
    level: str  # "balanced", "sparse", "problematic"
    score: float  # 0.0 to 1.0


@dataclass
class StoryHealth:
    structure: HealthSignal
    characters: HealthSignal
    arcs: HealthSignal
    density: HealthSignal


def compute_health(db: Database, project_id: int) -> StoryHealth:
    """Compute all health signals for a project."""
    scenes = db.get_all_scenes(project_id)
    characters = db.get_all_characters(project_id)

    structure = _compute_structure(scenes)
    char_dist = _compute_character_distribution(db, scenes, characters)
    arcs = _compute_arc_coverage(scenes)
    density = _compute_density(scenes)

    return StoryHealth(
        structure=structure,
        characters=char_dist,
        arcs=arcs,
        density=density,
    )


def _compute_structure(scenes) -> HealthSignal:
    """Check if scenes have structural fields filled."""
    if not scenes:
        return HealthSignal("Empty", "problematic", 0.0)

    total = len(scenes)
    filled = 0
    for s in scenes:
        fields_filled = 0
        fields_total = 4
        if s.act:
            fields_filled += 1
        if s.chapter:
            fields_filled += 1
        if s.plotline:
            fields_filled += 1
        if s.beat:
            fields_filled += 1
        filled += fields_filled / fields_total

    score = filled / total

    if score >= 0.7:
        return HealthSignal("Complete", "balanced", score)
    elif score >= 0.4:
        return HealthSignal("Partial", "sparse", score)
    else:
        return HealthSignal("Thin", "problematic", score)


def _compute_character_distribution(db: Database, scenes, characters) -> HealthSignal:
    """Check if characters are evenly distributed across scenes."""
    if not scenes or not characters:
        return HealthSignal("No data", "sparse", 0.0)

    appearance_counts: dict[int, int] = {c.id: 0 for c in characters}
    for scene in scenes:
        char_ids = db.get_scene_character_ids(scene.id)
        for cid in char_ids:
            if cid in appearance_counts:
                appearance_counts[cid] += 1

    counts = list(appearance_counts.values())
    if not counts or max(counts) == 0:
        return HealthSignal("Unused", "problematic", 0.0)

    max_possible = len(scenes)
    avg = sum(counts) / len(counts)
    max_count = max(counts)
    min_count = min(counts)

    if max_count == 0:
        return HealthSignal("Unused", "problematic", 0.0)

    spread = (max_count - min_count) / max_possible if max_possible > 0 else 0
    coverage = avg / max_possible if max_possible > 0 else 0

    score = min(1.0, coverage * 1.5) * (1.0 - spread * 0.5)
    score = max(0.0, min(1.0, score))

    if spread <= 0.3 and coverage >= 0.3:
        return HealthSignal("Balanced", "balanced", score)
    elif spread <= 0.6 or coverage >= 0.2:
        return HealthSignal("Uneven", "sparse", score)
    else:
        return HealthSignal("Lopsided", "problematic", score)


def _compute_arc_coverage(scenes) -> HealthSignal:
    """Check if plotlines span beginning/middle/end."""
    if not scenes:
        return HealthSignal("Empty", "problematic", 0.0)

    plotlines: dict[str, list[int]] = {}
    for i, s in enumerate(scenes):
        pl = s.plotline or ""
        if pl:
            plotlines.setdefault(pl, []).append(i)

    if not plotlines:
        return HealthSignal("No arcs", "sparse", 0.0)

    total = len(scenes)
    third = total / 3.0
    covered_arcs = 0

    for pl, indices in plotlines.items():
        has_beginning = any(i < third for i in indices)
        has_middle = any(third <= i < 2 * third for i in indices)
        has_end = any(i >= 2 * third for i in indices)
        sections = sum([has_beginning, has_middle, has_end])
        if sections >= 2:
            covered_arcs += 1

    score = covered_arcs / len(plotlines)

    if score >= 0.7:
        return HealthSignal("Complete", "balanced", score)
    elif score >= 0.4:
        return HealthSignal("Partial", "sparse", score)
    else:
        return HealthSignal("Fragmented", "problematic", score)


def _compute_density(scenes) -> HealthSignal:
    """Check average content length per scene."""
    if not scenes:
        return HealthSignal("Empty", "problematic", 0.0)

    lengths = [len(s.content or "") for s in scenes]
    avg_length = sum(lengths) / len(lengths) if lengths else 0

    if avg_length >= 500:
        score = min(1.0, avg_length / 2000.0)
        if avg_length > 3000:
            return HealthSignal("Overloaded", "sparse", min(score, 0.6))
        return HealthSignal("Developed", "balanced", score)
    elif avg_length >= 100:
        score = avg_length / 500.0
        return HealthSignal("Sparse", "sparse", score)
    else:
        score = avg_length / 100.0
        return HealthSignal("Thin", "problematic", score)


def level_color(level: str) -> str:
    """Map health level to display color."""
    if level == "balanced":
        return "#4ade80"
    elif level == "sparse":
        return "#f59e0b"
    else:
        return "#ef4444"


# Plain-language explanation of every status label, keyed by (metric, label).
# The metric key disambiguates labels that recur with different meanings —
# notably "Thin" (Structure = missing structural metadata; Scene Density =
# very short scenes). The metric names match the bar titles in the view.
LABEL_HELP: dict[tuple[str, str], str] = {
    ("Structure", "Empty"): "No scenes yet.",
    ("Structure", "Complete"):
        "Most scenes have their structural fields (Act, Chapter, Plotline, "
        "Beat) filled.",
    ("Structure", "Partial"):
        "Many scenes are missing structural fields (Act, Chapter, Plotline, "
        "Beat).",
    ("Structure", "Thin"):
        "Few scenes have structural fields (Act, Chapter, Plotline, Beat) "
        "filled.",
    ("Characters", "No data"):
        "No scenes or characters yet to measure distribution.",
    ("Characters", "Unused"):
        "Characters exist but none are assigned to any scene.",
    ("Characters", "Balanced"):
        "Characters appear fairly evenly across scenes.",
    ("Characters", "Uneven"):
        "Some characters appear noticeably more than others.",
    ("Characters", "Lopsided"):
        "Scene presence is dominated by a few characters.",
    ("Arc Coverage", "Empty"): "No scenes yet.",
    ("Arc Coverage", "No arcs"): "No plotlines are assigned to scenes yet.",
    ("Arc Coverage", "Complete"):
        "Most plotlines span at least two of beginning / middle / end.",
    ("Arc Coverage", "Partial"):
        "Some plotlines are confined to one part of the story.",
    ("Arc Coverage", "Fragmented"):
        "Most plotlines appear in only one part of the story.",
    ("Scene Density", "Empty"): "No scenes yet.",
    ("Scene Density", "Overloaded"):
        "Scenes are very long on average — consider splitting them.",
    ("Scene Density", "Developed"): "Scenes have a healthy average length.",
    ("Scene Density", "Sparse"): "Scenes are fairly short on average.",
    ("Scene Density", "Thin"):
        "Scenes are very short on average (little written content).",
}


def signal_help(metric: str, label: str) -> str:
    """Plain-language explanation for a (metric, label) pair, or '' if none."""
    return LABEL_HELP.get((metric, label), "")
