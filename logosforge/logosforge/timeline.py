"""Pure helpers for the canonical, scene-backed Timeline board.

The Timeline is a projection over Scene rows plus project-scoped lane and
settings state.  It deliberately owns its *display* order: structural mode
follows the canonical manuscript, while custom mode uses ``timeline_order``
without changing ``Scene.sort_order``.

This module has no database dependency.  Keeping normalization and revision
calculation pure lets both atomic read and write transactions derive exactly
the same board state from rows already loaded in one SQLite snapshot.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from logosforge import story_structure


TIMELINE_ORDER_MODES = frozenset({"structural", "custom"})


def _unique_ints(value: Any, *, allowed: set[int] | None = None) -> tuple[int, ...]:
    """Return ordered, unique integer ids from legacy JSON settings."""
    if not isinstance(value, list):
        return ()
    result: list[int] = []
    seen: set[int] = set()
    for raw in value:
        if isinstance(raw, bool):
            continue
        try:
            item = int(raw)
        except (TypeError, ValueError):
            continue
        if item in seen or (allowed is not None and item not in allowed):
            continue
        seen.add(item)
        result.append(item)
    return tuple(result)


def parse_project_settings(raw: str | None) -> dict[str, Any]:
    """Decode ``Project.settings_json`` defensively as an object."""
    try:
        value = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    return dict(value) if isinstance(value, dict) else {}


@dataclass(frozen=True)
class TimelineProjection:
    """Normalized membership and effective ordering for one board snapshot."""

    order_mode: str
    explicit_event_ids: tuple[int, ...]
    stored_custom_order: tuple[int, ...]
    event_ids: tuple[int, ...]
    effective_order: tuple[int, ...]
    off_timeline_ids: tuple[int, ...]


def project_timeline(
    scenes: Sequence[Any], settings: Mapping[str, Any],
) -> TimelineProjection:
    """Project loaded Scene rows and settings into canonical Timeline state.

    ``scenes`` must be in persisted manuscript order (``sort_order``, then id),
    matching the input contract of ``build_structure_tree_from_scenes``.
    """
    valid_ids = {int(scene.id) for scene in scenes}
    explicit = _unique_ints(settings.get("timeline_event_ids", []), allowed=valid_ids)
    explicit_set = set(explicit)
    event_set = {
        int(scene.id)
        for scene in scenes
        if (getattr(scene, "plotline", "") or "").strip()
        or int(scene.id) in explicit_set
    }

    tree = story_structure.build_structure_tree_from_scenes(scenes)
    structural_order, _ = story_structure.flatten_tree_to_order(tree)
    structural_events = [scene_id for scene_id in structural_order if scene_id in event_set]

    mode = str(settings.get("timeline_order_mode", "structural") or "structural")
    if mode not in TIMELINE_ORDER_MODES:
        mode = "structural"
    custom = _unique_ints(settings.get("timeline_order", []), allowed=event_set)
    if mode == "custom":
        effective = list(custom)
        seen = set(effective)
        effective.extend(
            scene_id for scene_id in structural_events if scene_id not in seen
        )
    else:
        effective = structural_events

    return TimelineProjection(
        order_mode=mode,
        explicit_event_ids=tuple(sorted(explicit_set)),
        stored_custom_order=custom,
        event_ids=tuple(structural_events),
        effective_order=tuple(effective),
        off_timeline_ids=tuple(
            scene_id for scene_id in structural_order if scene_id not in event_set
        ),
    )


def timeline_revision(
    project: Any,
    scenes: Sequence[Any],
    lanes: Sequence[Any],
    settings: Mapping[str, Any],
) -> str:
    """Content-address the board topology used by guarded Timeline commands.

    Prose and chronology metadata are intentionally excluded: editing a Scene's
    body, title, location, or time must not make an otherwise safe lane drag
    stale.  Every field that changes membership, lane placement, structural
    order/numbers, or custom Timeline order participates.
    """
    projection = project_timeline(scenes, settings)
    payload = {
        "project_id": int(getattr(project, "id", 0) or 0),
        "narrative_engine": str(
            getattr(project, "narrative_engine", "")
            or getattr(project, "format_mode", "")
            or "novel"
        ),
        "scenes": [
            [
                int(scene.id),
                (getattr(scene, "act", "") or "").strip(),
                (getattr(scene, "chapter", "") or "").strip(),
                (
                    int(scene.episode_id)
                    if getattr(scene, "episode_id", None) is not None
                    else None
                ),
                int(getattr(scene, "sort_order", 0) or 0),
                (getattr(scene, "plotline", "") or "").strip(),
                getattr(scene, "color_label", "") or "",
            ]
            for scene in scenes
        ],
        "lanes": [
            [
                int(lane.id),
                lane.name or "",
                lane.color_label or "",
                int(lane.order_index or 0),
                bool(lane.collapsed),
            ]
            for lane in lanes
        ],
        "order_mode": projection.order_mode,
        "event_ids": list(projection.explicit_event_ids),
        "custom_order": list(projection.stored_custom_order),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalized_lane_rows(lanes: Iterable[Any]) -> list[Any]:
    """Return lane objects in stable persisted order."""
    return sorted(
        lanes,
        key=lambda lane: (int(lane.order_index or 0), int(lane.id or 0)),
    )
