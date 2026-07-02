"""Creative Layer — context-aware hints, rhythm analysis, and review metrics.

Analyzes scenes to produce lightweight, non-intrusive writing feedback:
- Context hints (missing conflict, absent characters, etc.)
- Paragraph rhythm (length variation indicators)
- Review metrics (word distribution, pacing balance)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SceneHint:
    """A single non-intrusive hint about a scene."""

    scene_id: int
    hint_type: str
    message: str


@dataclass
class RhythmDot:
    """A single paragraph length indicator."""

    length: str  # "short", "medium", "long"
    word_count: int


@dataclass
class SceneRhythm:
    """Paragraph rhythm analysis for a scene."""

    scene_id: int
    dots: list[RhythmDot]
    variation_score: float  # 0.0 = uniform, 1.0 = maximum variation


@dataclass
class ReviewMetrics:
    """Lightweight review metrics for the manuscript."""

    total_words: int
    total_scenes: int
    avg_scene_words: int
    shortest_scene: tuple[int, int]  # (scene_id, word_count)
    longest_scene: tuple[int, int]
    pacing_balance: dict[str, int]  # {"short": n, "medium": n, "long": n}
    flagged_scenes: list[SceneHint]


_SHORT_THRESHOLD = 40
_LONG_THRESHOLD = 120

_PARA_SHORT = 30
_PARA_LONG = 80


def analyze_paragraph_rhythm(text: str, scene_id: int) -> SceneRhythm:
    """Analyze paragraph lengths and return rhythm dots."""
    if not text or not text.strip():
        return SceneRhythm(scene_id=scene_id, dots=[], variation_score=0.0)

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    dots: list[RhythmDot] = []

    for para in paragraphs:
        wc = len(para.split())
        if wc <= _PARA_SHORT:
            dots.append(RhythmDot(length="short", word_count=wc))
        elif wc >= _PARA_LONG:
            dots.append(RhythmDot(length="long", word_count=wc))
        else:
            dots.append(RhythmDot(length="medium", word_count=wc))

    if len(dots) < 2:
        return SceneRhythm(scene_id=scene_id, dots=dots, variation_score=0.0)

    lengths = [d.word_count for d in dots]
    mean = sum(lengths) / len(lengths)
    if mean == 0:
        return SceneRhythm(scene_id=scene_id, dots=dots, variation_score=0.0)

    variance = sum((l - mean) ** 2 for l in lengths) / len(lengths)
    std = variance ** 0.5
    cv = min(std / mean, 1.0)

    return SceneRhythm(scene_id=scene_id, dots=dots, variation_score=round(cv, 2))


def generate_scene_hints(
    db: Any, project_id: int, scene_id: int,
) -> list[SceneHint]:
    """Generate context-aware hints for a single scene."""
    hints: list[SceneHint] = []

    scene = db.get_scene_by_id(scene_id)
    if scene is None:
        return hints

    content = scene.content or ""
    words = content.split()
    word_count = len(words)

    if word_count == 0:
        hints.append(SceneHint(
            scene_id=scene_id,
            hint_type="empty",
            message="This scene is empty",
        ))
        return hints

    if not scene.conflict and not scene.goal:
        text_lower = content.lower()
        conflict_words = {"but", "however", "against", "refused", "fought", "argued", "clash"}
        has_conflict_signal = any(w in text_lower for w in conflict_words)
        if not has_conflict_signal and word_count > _SHORT_THRESHOLD:
            hints.append(SceneHint(
                scene_id=scene_id,
                hint_type="no_conflict",
                message="This scene has no conflict or goal defined",
            ))

    if word_count > _LONG_THRESHOLD * 3:
        hints.append(SceneHint(
            scene_id=scene_id,
            hint_type="long_scene",
            message=f"Long scene ({word_count} words) — consider splitting",
        ))

    if word_count < _SHORT_THRESHOLD and word_count > 0:
        hints.append(SceneHint(
            scene_id=scene_id,
            hint_type="short_scene",
            message="Very short scene — placeholder?",
        ))

    characters = db.get_all_psyke_entries(project_id)
    char_entries = [e for e in characters if e.entry_type == "character" and not e.is_global]
    text_lower = content.lower()

    for entry in char_entries:
        name_lower = entry.name.lower()
        if name_lower in text_lower:
            continue
        aliases = (entry.aliases or "").lower().split(",")
        if any(a.strip() and a.strip() in text_lower for a in aliases):
            continue

        scenes = db.get_all_scenes(project_id)
        scene_idx = None
        last_seen_idx = None
        for i, s in enumerate(scenes):
            if s.id == scene_id:
                scene_idx = i
            s_text = (s.content or "").lower()
            if name_lower in s_text:
                last_seen_idx = i

        if scene_idx is not None and last_seen_idx is not None:
            gap = scene_idx - last_seen_idx
            if 3 <= gap <= 8:
                hints.append(SceneHint(
                    scene_id=scene_id,
                    hint_type="absent_character",
                    message=f"{entry.name} hasn't appeared in {gap} scenes",
                ))

    # Screenplay-specific checks
    try:
        from logosforge.narrative_engines import engine_for_project
        project = db.get_project_by_id(project_id)
        engine = engine_for_project(project)
        if engine.name == "screenplay":
            hints.extend(_screenplay_scene_hints(db, project_id, scene_id, scene, content))
    except Exception:
        pass

    return hints


def _screenplay_scene_hints(
    db: Any, project_id: int, scene_id: int,
    scene: Any, content: str,
) -> list[SceneHint]:
    """Screenplay-specific scene hints: turn, visible conflict, dialogue, blocking."""
    hints: list[SceneHint] = []
    words = content.split()
    word_count = len(words)

    # Scene doesn't turn — no emotional_turn defined on a non-trivial scene
    if word_count > _SHORT_THRESHOLD:
        emotional_turn = getattr(scene, "emotional_turn", "") or ""
        if not emotional_turn:
            hints.append(SceneHint(
                scene_id=scene_id,
                hint_type="no_turn",
                message="Scene has no emotional turn defined",
            ))

    # No visible conflict
    if word_count > _SHORT_THRESHOLD:
        visible = getattr(scene, "visible_conflict", "") or ""
        if not visible and not scene.conflict:
            hints.append(SceneHint(
                scene_id=scene_id,
                hint_type="no_visible_conflict",
                message="No visible conflict — nothing the camera can film",
            ))

    # Dialogue economy — detect exposition-heavy passages
    if word_count > _LONG_THRESHOLD:
        lines = content.split("\n")
        dialogue_lines = sum(1 for l in lines if l.strip().startswith('"') or l.strip().startswith('“'))
        total_lines = max(sum(1 for l in lines if l.strip()), 1)
        if dialogue_lines > 0 and dialogue_lines / total_lines > 0.7:
            hints.append(SceneHint(
                scene_id=scene_id,
                hint_type="dialogue_heavy",
                message="Scene is >70% dialogue — check for exposition",
            ))

    # Static blocking — no physical_action defined
    if word_count > _SHORT_THRESHOLD:
        physical = getattr(scene, "physical_action", "") or ""
        blocking = getattr(scene, "blocking_notes", "") or ""
        if not physical and not blocking:
            hints.append(SceneHint(
                scene_id=scene_id,
                hint_type="static_blocking",
                message="No blocking or physical action defined",
            ))

    # No subtext
    if word_count > _SHORT_THRESHOLD:
        hidden = getattr(scene, "hidden_conflict", "") or ""
        subtext = getattr(scene, "subtext_notes", "") or ""
        if not hidden and not subtext:
            hints.append(SceneHint(
                scene_id=scene_id,
                hint_type="no_subtext",
                message="No subtext or hidden conflict defined",
            ))

    # Continuity check — scene has characters but no continuity items tracked
    if word_count > _SHORT_THRESHOLD:
        char_ids = db.get_scene_character_ids(scene_id)
        if char_ids:
            cont_items = db.get_continuity_for_scene(scene_id)
            if not cont_items:
                hints.append(SceneHint(
                    scene_id=scene_id,
                    hint_type="no_continuity",
                    message="Characters present but no continuity items tracked",
                ))

    # Duration missing
    duration = getattr(scene, "estimated_duration_minutes", 0) or 0
    if word_count > _SHORT_THRESHOLD and not duration:
        hints.append(SceneHint(
            scene_id=scene_id,
            hint_type="no_duration",
            message="No estimated duration — hard to evaluate pacing",
        ))

    return hints


def compute_review_metrics(db: Any, project_id: int) -> ReviewMetrics:
    """Compute lightweight review metrics for the entire manuscript."""
    scenes = db.get_all_scenes(project_id)
    if not scenes:
        return ReviewMetrics(
            total_words=0, total_scenes=0, avg_scene_words=0,
            shortest_scene=(0, 0), longest_scene=(0, 0),
            pacing_balance={"short": 0, "medium": 0, "long": 0},
            flagged_scenes=[],
        )

    scene_words: list[tuple[int, int]] = []
    for s in scenes:
        wc = len((s.content or "").split()) if (s.content or "").strip() else 0
        scene_words.append((s.id, wc))

    total = sum(wc for _, wc in scene_words)
    shortest = min(scene_words, key=lambda x: x[1])
    longest = max(scene_words, key=lambda x: x[1])
    avg = total // len(scenes) if scenes else 0

    pacing = {"short": 0, "medium": 0, "long": 0}
    for _, wc in scene_words:
        if wc <= _SHORT_THRESHOLD:
            pacing["short"] += 1
        elif wc >= _LONG_THRESHOLD:
            pacing["long"] += 1
        else:
            pacing["medium"] += 1

    flagged: list[SceneHint] = []
    for s in scenes:
        hints = generate_scene_hints(db, project_id, s.id)
        flagged.extend(hints)

    return ReviewMetrics(
        total_words=total,
        total_scenes=len(scenes),
        avg_scene_words=avg,
        shortest_scene=shortest,
        longest_scene=longest,
        pacing_balance=pacing,
        flagged_scenes=flagged,
    )
