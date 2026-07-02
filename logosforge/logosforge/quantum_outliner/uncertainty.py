"""Uncertainty Engine — find weak/predictable scenes worth re-exploring.

Uses lightweight heuristics (no LLM call). High-uncertainty zones are
the inverse: scenes where the story can still surprise.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from logosforge.db import Database


@dataclass(frozen=True)
class WeakScene:
    """A scene flagged for re-exploration."""

    scene_id: int
    title: str
    weakness: float
    reasons: tuple[str, ...]


_TENSION_KEYWORDS = (
    "but", "however", "suddenly", "fight", "argued", "shouted",
    "cried", "betray", "lie", "secret", "fear", "afraid", "danger",
    "must", "cannot", "refused", "demanded",
)

_FILLER_KEYWORDS = (
    "then", "and then", "after that", "next", "anyway",
)


def score_scene(content: str) -> tuple[float, tuple[str, ...]]:
    """Heuristic weakness score. 0.0 = strong, 1.0 = weak.

    Reasons describe why the scene was flagged.
    """
    text = content.strip()
    if not text:
        return 1.0, ("scene is empty",)

    word_count = len(text.split())
    reasons: list[str] = []
    score = 0.0

    if word_count < 80:
        score += 0.4
        reasons.append(f"very short ({word_count} words)")
    elif word_count < 200:
        score += 0.15
        reasons.append(f"short ({word_count} words)")

    lower = text.lower()
    tension_hits = sum(1 for kw in _TENSION_KEYWORDS if kw in lower)
    if tension_hits == 0:
        score += 0.3
        reasons.append("no tension or conflict markers")
    elif tension_hits == 1:
        score += 0.15
        reasons.append("low tension density")

    filler_hits = sum(lower.count(kw) for kw in _FILLER_KEYWORDS)
    if word_count > 0 and filler_hits / max(word_count / 100, 1) > 2:
        score += 0.2
        reasons.append("heavy filler transitions")

    dialogue_lines = len(re.findall(r'"[^"]+"', text))
    paragraphs = max(text.count("\n\n") + 1, 1)
    if dialogue_lines == 0 and paragraphs > 2:
        score += 0.15
        reasons.append("no dialogue")

    score = min(score, 1.0)
    if not reasons:
        reasons.append("no weaknesses detected")
    return score, tuple(reasons)


def find_uncertainty_zones(
    db: "Database",
    project_id: int,
    *,
    threshold: float = 0.4,
    max_results: int = 10,
) -> list[WeakScene]:
    """Return scenes scoring above the weakness threshold."""
    scenes = db.get_all_scenes(project_id)
    weak: list[WeakScene] = []
    for sc in scenes:
        content = getattr(sc, "content", "") or ""
        score, reasons = score_scene(content)
        if score >= threshold:
            title = getattr(sc, "title", "") or f"Scene {sc.id}"
            weak.append(WeakScene(
                scene_id=sc.id,
                title=title,
                weakness=score,
                reasons=reasons,
            ))

    weak.sort(key=lambda w: w.weakness, reverse=True)
    return weak[:max_results]
