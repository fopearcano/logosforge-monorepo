"""Story Flow Layer — tension, pacing, and scene type analysis.

Computes lightweight flow indicators from existing scene data without
requiring schema changes. Tension is inferred from beat type, conflict
presence, and content word analysis (with manual override via tags).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


_BEAT_TENSION: dict[str, int] = {
    "opening": 2,
    "inciting incident": 5,
    "first plot point": 6,
    "midpoint": 7,
    "all is lost": 8,
    "dark night": 8,
    "climax": 9,
    "resolution": 3,
    "denouement": 2,
    "pinch point": 6,
    "second plot point": 7,
    "break into two": 5,
    "break into three": 7,
    "fun and games": 4,
    "debate": 4,
}

_CONFLICT_WORDS = frozenset({
    "fought", "argued", "screamed", "attacked", "refused", "clash",
    "struggle", "battle", "confronted", "threat", "danger", "risk",
    "tension", "afraid", "fear", "rage", "fury", "desperate",
    "betrayed", "lied", "deceived", "trapped", "enemy", "killed",
})

_DIALOGUE_MARKERS = frozenset({'"', "\u201c", "\u201d", "\u2018", "\u2019"})

_ACTION_WORDS = frozenset({
    "ran", "jumped", "fell", "grabbed", "slammed", "sprinted",
    "crashed", "exploded", "chased", "dodged", "struck", "threw",
    "kicked", "punched", "fired", "shot", "fled", "escaped",
})


@dataclass
class SceneTension:
    """Computed tension value for a scene."""

    scene_id: int
    value: int  # 0-10
    source: str  # "beat", "conflict", "content", "manual", "default"


@dataclass
class SceneType:
    """Inferred scene type from content analysis."""

    scene_id: int
    primary: str  # "dialogue", "action", "exposition", "mixed"
    dialogue_ratio: float
    action_ratio: float


@dataclass
class PacingWarning:
    """Pacing imbalance detected in a sequence of scenes."""

    start_scene_id: int
    end_scene_id: int
    scene_ids: list[int]
    reason: str  # "monotone_low", "monotone_high", "no_variation"


@dataclass
class FlowAnalysis:
    """Complete flow analysis for a project."""

    tensions: dict[int, SceneTension]
    scene_types: dict[int, SceneType]
    pacing_warnings: list[PacingWarning]


def compute_tension(scene) -> SceneTension:
    """Compute tension for a single scene from its data."""
    tags = scene.tags or ""
    for part in tags.split(","):
        part = part.strip().lower()
        if part.startswith("tension:"):
            try:
                val = int(part.split(":")[1])
                return SceneTension(
                    scene_id=scene.id,
                    value=max(0, min(10, val)),
                    source="manual",
                )
            except (ValueError, IndexError):
                pass

    beat = (scene.beat or "").strip().lower()
    if beat in _BEAT_TENSION:
        return SceneTension(
            scene_id=scene.id,
            value=_BEAT_TENSION[beat],
            source="beat",
        )

    conflict = (scene.conflict or "").strip()
    if conflict:
        base = 5
        content = (scene.content or "").lower()
        conflict_hits = sum(1 for w in content.split() if w in _CONFLICT_WORDS)
        boost = min(conflict_hits // 3, 3)
        return SceneTension(
            scene_id=scene.id,
            value=min(base + boost, 10),
            source="conflict",
        )

    content = (scene.content or "").lower()
    words = content.split()
    if words:
        conflict_hits = sum(1 for w in words if w in _CONFLICT_WORDS)
        ratio = conflict_hits / len(words)
        if ratio > 0.03:
            return SceneTension(scene_id=scene.id, value=6, source="content")
        elif ratio > 0.01:
            return SceneTension(scene_id=scene.id, value=4, source="content")

    return SceneTension(scene_id=scene.id, value=2, source="default")


def classify_scene_type(scene) -> SceneType:
    """Classify a scene as dialogue, action, or exposition."""
    content = scene.content or ""
    if not content.strip():
        return SceneType(
            scene_id=scene.id, primary="exposition",
            dialogue_ratio=0.0, action_ratio=0.0,
        )

    lines = content.split("\n")
    dialogue_lines = 0
    for line in lines:
        stripped = line.strip()
        if any(stripped.startswith(m) or stripped.endswith(m) for m in _DIALOGUE_MARKERS):
            dialogue_lines += 1

    total_lines = max(len(lines), 1)
    dialogue_ratio = dialogue_lines / total_lines

    words = content.lower().split()
    action_hits = sum(1 for w in words if w in _ACTION_WORDS)
    action_ratio = action_hits / max(len(words), 1)

    if dialogue_ratio >= 0.4:
        primary = "dialogue"
    elif action_ratio >= 0.03:
        primary = "action"
    elif dialogue_ratio >= 0.2 and action_ratio >= 0.01:
        primary = "mixed"
    else:
        primary = "exposition"

    return SceneType(
        scene_id=scene.id,
        primary=primary,
        dialogue_ratio=round(dialogue_ratio, 2),
        action_ratio=round(action_ratio, 2),
    )


def detect_pacing_warnings(tensions: list[SceneTension]) -> list[PacingWarning]:
    """Detect monotonous pacing stretches."""
    warnings: list[PacingWarning] = []
    if len(tensions) < 4:
        return warnings

    window = 4
    for i in range(len(tensions) - window + 1):
        chunk = tensions[i:i + window]
        values = [t.value for t in chunk]

        if all(v <= 3 for v in values):
            warnings.append(PacingWarning(
                start_scene_id=chunk[0].scene_id,
                end_scene_id=chunk[-1].scene_id,
                scene_ids=[t.scene_id for t in chunk],
                reason="monotone_low",
            ))
        elif all(v >= 7 for v in values):
            warnings.append(PacingWarning(
                start_scene_id=chunk[0].scene_id,
                end_scene_id=chunk[-1].scene_id,
                scene_ids=[t.scene_id for t in chunk],
                reason="monotone_high",
            ))
        elif max(values) - min(values) <= 1 and len(set(values)) == 1:
            warnings.append(PacingWarning(
                start_scene_id=chunk[0].scene_id,
                end_scene_id=chunk[-1].scene_id,
                scene_ids=[t.scene_id for t in chunk],
                reason="no_variation",
            ))

    seen: set[tuple[int, ...]] = set()
    deduped: list[PacingWarning] = []
    for w in warnings:
        key = tuple(w.scene_ids)
        if key not in seen:
            seen.add(key)
            deduped.append(w)
    return deduped


def analyze_flow(db: Any, project_id: int) -> FlowAnalysis:
    """Run full flow analysis for a project."""
    scenes = db.get_all_scenes(project_id)

    tensions: dict[int, SceneTension] = {}
    scene_types: dict[int, SceneType] = {}
    tension_list: list[SceneTension] = []

    for scene in scenes:
        t = compute_tension(scene)
        tensions[scene.id] = t
        tension_list.append(t)
        scene_types[scene.id] = classify_scene_type(scene)

    pacing_warnings = detect_pacing_warnings(tension_list)

    return FlowAnalysis(
        tensions=tensions,
        scene_types=scene_types,
        pacing_warnings=pacing_warnings,
    )


def tension_color(value: int) -> str:
    """Return a color for a tension value (0-10)."""
    if value <= 2:
        return "#4ade80"  # green - calm
    elif value <= 4:
        return "#a3e635"  # lime - low
    elif value <= 6:
        return "#facc15"  # amber - medium
    elif value <= 8:
        return "#fb923c"  # orange - high
    else:
        return "#f87171"  # red - intense


_SCENE_TYPE_ICONS: dict[str, str] = {
    "dialogue": "\U0001F4AC",
    "action": "\u26A1",
    "exposition": "\U0001F4D6",
    "mixed": "\u2726",
}


def scene_type_icon(primary: str) -> str:
    """Return a small icon character for a scene type."""
    return _SCENE_TYPE_ICONS.get(primary, "")
