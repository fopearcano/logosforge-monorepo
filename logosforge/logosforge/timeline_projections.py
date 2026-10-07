"""Pure mode-specific read projections for the canonical Timeline.

The functions in this module consume rows already captured by the caller's
SQLite read transaction.  They never open a database session and never affect
the Timeline command revision: these projections are presentation data, not
editable Timeline topology.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from itertools import pairwise
from typing import Any

from logosforge.project_compat import get_project_narrative_engine

_DENSITIES = frozenset({"silent", "light", "medium", "dense", "explosive"})
_DENSITY_TO_RHYTHM = {
    "silent": "held",
    "light": "slow",
    "medium": "steady",
    "dense": "fast",
    "explosive": "chaotic",
    "unset": "steady",
}
_STAGE_MOVES = frozenset({"entrance", "exit"})
_STAGE_CUES = frozenset({"light", "sound", "music", "prop", "movement", "other"})
_ARC_SCOPES = frozenset(
    {
        "series",
        "season",
        "episode",
        "character",
        "relationship",
        "mystery",
    }
)
_ARC_STATUSES = frozenset({"active", "resolved", "abandoned", "delayed"})
_MAX_ROOT_ITEMS = 10_000
_MAX_NESTED_ITEMS = 1_000


def _text(value: Any, *, limit: int = 4096) -> str:
    """Normalize persisted free text without letting malformed rows break DTOs."""
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _label(value: Any) -> str:
    return _text(value, limit=256)


def _nonnegative(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def _csv_count(value: Any) -> int:
    return len([part for part in str(value or "").split(",") if part.strip()])


def _screenplay_projection(
    event_scenes: Sequence[Any],
    settings: Mapping[str, Any],
) -> dict[str, Any]:
    raw_plans = settings.get("screenplay_beat_plans", {})
    plans = raw_plans if isinstance(raw_plans, dict) else {}
    rows: list[dict[str, Any]] = []
    for scene in event_scenes:
        raw = plans.get(str(int(scene.id)), {})
        plan = raw if isinstance(raw, dict) else {}
        visual_beats = plan.get("visual_beats", [])
        if not isinstance(visual_beats, list):
            visual_beats = []
        rows.append(
            {
                "scene_id": int(scene.id),
                "interior_exterior": _label(getattr(scene, "interior_exterior", "")),
                "cinematic_pacing": _label(getattr(scene, "cinematic_pacing", "")),
                "dramatic_turn": _text(getattr(scene, "dramatic_turn", "")),
                "emotional_turn": _text(getattr(scene, "emotional_turn", "")),
                "objective": _text(plan.get("objective", "")),
                "conflict": _text(plan.get("conflict", "")),
                "turning_point": _text(plan.get("turning_point", "")),
                "emotional_shift": _text(plan.get("emotional_shift", "")),
                "visual_beat_count": len(visual_beats),
            }
        )
    return {"kind": "screenplay", "scenes": rows}


def _graphic_novel_projection(
    issues: Sequence[Any],
    sequences: Sequence[Any],
    pages: Sequence[Any],
    panels: Sequence[Any],
) -> dict[str, Any]:
    issue_by_id = {int(row.id): row for row in issues}
    sequence_by_id = {int(row.id): row for row in sequences}
    owned_page_ids = {int(row.id) for row in pages}
    panels_by_page: dict[int, list[Any]] = defaultdict(list)
    for panel in panels:
        page_id = int(panel.page_id)
        if page_id in owned_page_ids:
            panels_by_page[page_id].append(panel)
    for group in panels_by_page.values():
        group.sort(
            key=lambda row: (
                int(getattr(row, "panel_number", 0) or 0),
                int(getattr(row, "sort_order", 0) or 0),
                int(row.id),
            )
        )

    ordered_pages = sorted(
        pages,
        key=lambda row: (
            int(getattr(row, "page_number", 0) or 0),
            int(getattr(row, "sort_order", 0) or 0),
            int(row.id),
        ),
    )[:_MAX_ROOT_ITEMS]
    page_rows: list[dict[str, Any]] = []
    for page in ordered_pages:
        page_id = int(page.id)
        page_panels = panels_by_page.get(page_id, [])
        density_raw = _label(getattr(page, "density_level", "")).lower()
        density = density_raw if density_raw in _DENSITIES else "unset"
        reveal = _label(getattr(page, "reveal_type", ""))
        panel_count = len(page_panels)
        action_count = sum(
            1 for panel in page_panels if _text(getattr(panel, "action", ""))
        )
        action_density = round(
            action_count / panel_count if panel_count else 0.0,
            4,
        )
        text_load = sum(
            _csv_count(getattr(panel, "dialogue_refs", "")) for panel in page_panels
        )
        if bool(getattr(page, "splash_page", False)) or density == "explosive":
            pacing = "explosive"
        elif panel_count and text_load >= 2 * panel_count:
            pacing = "exposition-heavy"
        elif reveal and reveal.lower() != "none":
            pacing = "cinematic"
        elif density == "dense":
            pacing = "dense"
        else:
            pacing = "quiet"

        issue_id = getattr(page, "issue_id", None)
        issue = issue_by_id.get(int(issue_id)) if issue_id is not None else None
        sequence_id = getattr(page, "sequence_id", None)
        sequence = (
            sequence_by_id.get(int(sequence_id)) if sequence_id is not None else None
        )
        page_rows.append(
            {
                "page_id": page_id,
                "page_number": _nonnegative(getattr(page, "page_number", 0)),
                "sequence_id": int(sequence.id) if sequence is not None else None,
                "issue_id": int(issue.id) if issue is not None else None,
                "issue_title": _label(getattr(issue, "title", "")),
                "density": density,
                "rhythm": _DENSITY_TO_RHYTHM[density],
                "reveal_timing": reveal,
                "splash_page": bool(getattr(page, "splash_page", False)),
                "panel_count": panel_count,
                "action_density": action_density,
                "text_load": text_load,
                "pacing": pacing,
                "is_silence": density in {"silent", "light"},
                "is_action": density in {"dense", "explosive"},
            }
        )

    turns: list[dict[str, Any]] = []
    for setup, reveal in pairwise(page_rows):
        reveal_type = _text(setup["reveal_timing"])
        if reveal_type and reveal_type.lower() != "none":
            turns.append(
                {
                    "setup_page_id": setup["page_id"],
                    "setup_page_number": setup["page_number"],
                    "reveal_page_id": reveal["page_id"],
                    "reveal_page_number": reveal["page_number"],
                    "reveal_type": reveal_type,
                }
            )
    return {"kind": "graphic_novel", "pages": page_rows, "page_turns": turns}


def _stage_projection(
    event_scenes: Sequence[Any],
    entrances: Sequence[Any],
    cues: Sequence[Any],
    business: Sequence[Any],
    character_names: Mapping[int, str],
    psyke_names: Mapping[int, str],
) -> dict[str, Any]:
    scene_ids = {int(scene.id) for scene in event_scenes}
    entrances_by_scene: dict[int, list[Any]] = defaultdict(list)
    for row in entrances:
        if int(row.scene_id) in scene_ids:
            entrances_by_scene[int(row.scene_id)].append(row)
    cues_by_scene: dict[int, list[Any]] = defaultdict(list)
    for row in cues:
        if int(row.scene_id) in scene_ids:
            cues_by_scene[int(row.scene_id)].append(row)
    business_by_scene: dict[int, list[Any]] = defaultdict(list)
    for row in business:
        if int(row.scene_id) in scene_ids:
            business_by_scene[int(row.scene_id)].append(row)
    for groups in (entrances_by_scene, cues_by_scene, business_by_scene):
        for group in groups.values():
            group.sort(
                key=lambda row: (
                    int(getattr(row, "moment_order", 0) or 0),
                    int(row.id),
                )
            )

    result: list[dict[str, Any]] = []
    for order_index, scene in enumerate(event_scenes, start=1):
        scene_id = int(scene.id)
        movement_rows: list[dict[str, Any]] = []
        for row in entrances_by_scene.get(scene_id, []):
            character_id = getattr(row, "character_id", None)
            if character_id is not None and int(character_id) not in character_names:
                continue
            move_type = _label(getattr(row, "type", "")).lower()
            if move_type not in _STAGE_MOVES:
                move_type = "entrance"
            movement_rows.append(
                {
                    "character": (
                        _label(character_names.get(int(character_id), ""))
                        if character_id is not None
                        else ""
                    ),
                    "type": move_type,
                    "moment_order": _nonnegative(getattr(row, "moment_order", 0)),
                    "cue_text": _text(getattr(row, "cue_text", "")),
                }
            )
            if len(movement_rows) == _MAX_NESTED_ITEMS:
                break

        cue_rows: list[dict[str, Any]] = []
        for row in cues_by_scene.get(scene_id, [])[:_MAX_NESTED_ITEMS]:
            cue_type = _label(getattr(row, "cue_type", "")).lower()
            if cue_type not in _STAGE_CUES:
                cue_type = "other"
            cue_rows.append(
                {
                    "type": cue_type,
                    "text": _text(getattr(row, "cue_text", "")),
                    "moment_order": _nonnegative(getattr(row, "moment_order", 0)),
                }
            )

        props: list[str] = []
        for row in business_by_scene.get(scene_id, []):
            prop_id = getattr(row, "prop_psyke_entry_id", None)
            if prop_id is None:
                continue
            name = _label(psyke_names.get(int(prop_id), ""))
            if name and name not in props:
                props.append(name)
                if len(props) == _MAX_NESTED_ITEMS:
                    break
        prop_notes = _label(getattr(scene, "prop_notes", ""))
        if not props and prop_notes:
            props.append(prop_notes)

        if _text(getattr(scene, "dramatic_turn", "")):
            pressure = "turn"
        elif _text(getattr(scene, "conflict", "")):
            pressure = "conflict"
        elif _text(getattr(scene, "scene_objective", "")):
            pressure = "pursuit"
        else:
            pressure = "flat"
        offstage = _text(getattr(scene, "offstage_events", ""))
        result.append(
            {
                "scene_id": scene_id,
                "order_index": order_index,
                "act": _label(getattr(scene, "act", "")),
                "title": _label(getattr(scene, "title", "")),
                "entrances_exits": movement_rows,
                "cues": cue_rows,
                "offstage_events": offstage,
                "has_offstage_events": bool(offstage),
                "props": props,
                "emotional_pressure": pressure,
            }
        )
    return {"kind": "stage_script", "scenes": result}


def _series_projection(
    event_scenes: Sequence[Any],
    seasons: Sequence[Any],
    episodes: Sequence[Any],
    arcs: Sequence[Any],
) -> dict[str, Any]:
    season_by_id = {int(row.id): row for row in seasons}
    ordered_seasons = sorted(
        seasons,
        key=lambda row: (
            int(getattr(row, "order_index", 0) or 0),
            int(row.id),
        ),
    )
    episodes_by_season: dict[int, list[Any]] = defaultdict(list)
    orphaned: list[Any] = []
    for episode in episodes:
        season_id = int(episode.season_id)
        if season_id in season_by_id:
            episodes_by_season[season_id].append(episode)
        else:
            orphaned.append(episode)
    for group in episodes_by_season.values():
        group.sort(
            key=lambda row: (
                int(getattr(row, "episode_number", 0) or 0),
                int(getattr(row, "order_index", 0) or 0),
                int(row.id),
            )
        )
    orphaned.sort(
        key=lambda row: (
            int(getattr(row, "order_index", 0) or 0),
            int(row.id),
        )
    )
    all_ordered_episodes: list[Any] = []
    for season in ordered_seasons:
        all_ordered_episodes.extend(episodes_by_season.get(int(season.id), []))
    all_ordered_episodes.extend(orphaned)
    canonical_order_by_id = {
        int(row.id): index
        for index, row in enumerate(all_ordered_episodes, start=1)
    }

    # Native Series metadata remains bounded when it is independent of the
    # active Timeline, but every project-owned Episode referenced by an active
    # event must be present so a real assignment is never reported as
    # "unassigned" merely because its Episode fell beyond the display cap.
    owned_episode_ids = {int(row.id) for row in all_ordered_episodes}
    referenced_episode_ids = {
        int(episode_id)
        for scene in event_scenes
        if (episode_id := getattr(scene, "episode_id", None)) is not None
        and int(episode_id) in owned_episode_ids
    }
    selected_episode_ids = set(referenced_episode_ids)
    remaining_slots = max(0, _MAX_ROOT_ITEMS - len(selected_episode_ids))
    if remaining_slots:
        for episode in all_ordered_episodes:
            episode_id = int(episode.id)
            if episode_id in selected_episode_ids:
                continue
            selected_episode_ids.add(episode_id)
            remaining_slots -= 1
            if remaining_slots == 0:
                break
    ordered_episodes = [
        episode
        for episode in all_ordered_episodes
        if int(episode.id) in selected_episode_ids
    ]
    episode_by_id = {int(row.id): row for row in ordered_episodes}
    order_by_id = {
        int(row.id): index for index, row in enumerate(ordered_episodes, start=1)
    }

    normalized_arcs: list[tuple[Any, str, str, int | None, int | None]] = []
    for arc in sorted(arcs, key=lambda row: int(row.id))[:_MAX_ROOT_ITEMS]:
        scope_raw = _label(getattr(arc, "scope", "")).lower()
        status_raw = _label(getattr(arc, "status", "")).lower()
        scope = scope_raw if scope_raw in _ARC_SCOPES else "series"
        status = status_raw if status_raw in _ARC_STATUSES else "active"
        setup_raw = getattr(arc, "setup_episode_id", None)
        payoff_raw = getattr(arc, "payoff_episode_id", None)
        setup_id = (
            int(setup_raw)
            if setup_raw is not None and int(setup_raw) in owned_episode_ids
            else None
        )
        payoff_id = (
            int(payoff_raw)
            if payoff_raw is not None and int(payoff_raw) in owned_episode_ids
            else None
        )
        normalized_arcs.append((arc, scope, status, setup_id, payoff_id))

    event_ids_by_episode: dict[int, list[int]] = defaultdict(list)
    unassigned: list[int] = []
    for scene in event_scenes:
        episode_id = getattr(scene, "episode_id", None)
        if episode_id is None or int(episode_id) not in episode_by_id:
            unassigned.append(int(scene.id))
        else:
            event_ids_by_episode[int(episode_id)].append(int(scene.id))

    episode_rows: list[dict[str, Any]] = []
    for episode in ordered_episodes:
        episode_id = int(episode.id)
        order_index = order_by_id[episode_id]
        season = season_by_id.get(int(episode.season_id))
        active_arcs: list[dict[str, Any]] = []
        setup_arc_ids: list[int] = []
        payoff_arc_ids: list[int] = []
        for arc, scope, status, setup_id, payoff_id in normalized_arcs:
            arc_id = int(arc.id)
            if setup_id == episode_id:
                setup_arc_ids.append(arc_id)
            if payoff_id == episode_id:
                payoff_arc_ids.append(arc_id)
            episode_position = canonical_order_by_id[episode_id]
            start = (
                canonical_order_by_id.get(setup_id)
                if setup_id is not None
                else None
            )
            end = (
                canonical_order_by_id.get(payoff_id)
                if payoff_id is not None
                else None
            )
            is_active = status in {"active", "delayed"}
            if start is not None and episode_position < start:
                is_active = False
            if end is not None and episode_position > end:
                is_active = False
            if is_active and len(active_arcs) < _MAX_NESTED_ITEMS:
                active_arcs.append(
                    {
                        "arc_id": arc_id,
                        "title": _label(getattr(arc, "title", "")),
                        "scope": scope,
                        "status": status,
                    }
                )
        setup_arc_ids = setup_arc_ids[:_MAX_NESTED_ITEMS]
        payoff_arc_ids = payoff_arc_ids[:_MAX_NESTED_ITEMS]
        episode_rows.append(
            {
                "episode_id": episode_id,
                "order_index": order_index,
                "season_id": int(season.id) if season is not None else None,
                "season": (
                    _label(getattr(season, "title", ""))
                    or (
                        f"Season {_nonnegative(getattr(season, 'season_number', 0))}"
                        if season is not None
                        else ""
                    )
                ),
                "episode_number": _nonnegative(getattr(episode, "episode_number", 0)),
                "title": (
                    _label(getattr(episode, "title", ""))
                    or f"Episode {_nonnegative(getattr(episode, 'episode_number', 0))}"
                ),
                "cliffhanger": _text(getattr(episode, "cliffhanger", "")),
                "scene_ids": event_ids_by_episode.get(episode_id, []),
                "active_arcs": active_arcs,
                "setup_arc_ids": setup_arc_ids,
                "payoff_arc_ids": payoff_arc_ids,
            }
        )

    chains = [
        {
            "arc_id": int(arc.id),
            "title": _label(getattr(arc, "title", "")),
            "scope": scope,
            "setup_episode_id": setup_id,
            "payoff_episode_id": payoff_id,
            "setup_order_index": order_by_id.get(setup_id),
            "payoff_order_index": order_by_id.get(payoff_id),
        }
        for arc, scope, _status, setup_id, payoff_id in normalized_arcs
        if setup_id in order_by_id and payoff_id in order_by_id
    ][:_MAX_ROOT_ITEMS]
    return {
        "kind": "series",
        "episodes": episode_rows,
        "arc_chains": chains,
        "unassigned_scene_ids": unassigned,
    }


def build_timeline_mode_projection(
    project: Any,
    event_scenes: Sequence[Any],
    settings: Mapping[str, Any],
    *,
    graphic_novel_issues: Sequence[Any] = (),
    graphic_novel_sequences: Sequence[Any] = (),
    graphic_novel_pages: Sequence[Any] = (),
    graphic_novel_panels: Sequence[Any] = (),
    stage_entrances: Sequence[Any] = (),
    stage_cues: Sequence[Any] = (),
    stage_business: Sequence[Any] = (),
    character_names_by_id: Mapping[int, str] | None = None,
    psyke_names_by_id: Mapping[int, str] | None = None,
    seasons: Sequence[Any] = (),
    episodes: Sequence[Any] = (),
    series_arcs: Sequence[Any] = (),
) -> dict[str, Any]:
    """Build the engine-discriminated Timeline projection from captured rows."""
    engine = get_project_narrative_engine(project)
    if engine == "screenplay":
        return _screenplay_projection(event_scenes, settings)
    if engine == "graphic_novel":
        return _graphic_novel_projection(
            graphic_novel_issues,
            graphic_novel_sequences,
            graphic_novel_pages,
            graphic_novel_panels,
        )
    if engine == "stage_script":
        return _stage_projection(
            event_scenes,
            stage_entrances,
            stage_cues,
            stage_business,
            character_names_by_id or {},
            psyke_names_by_id or {},
        )
    if engine == "series":
        return _series_projection(event_scenes, seasons, episodes, series_arcs)
    return {"kind": "novel"}
