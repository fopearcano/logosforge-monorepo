"""Lightweight continuity state tracking (Phase 10Q).

Builds ordered observation lists per subject from the extracted facts. Uses only
available data — ``unknown`` is acceptable, sparse projects never hard-fail.
"""

from __future__ import annotations

from logosforge.continuity import models as M
from logosforge.continuity.facts import ProjectFacts


def build_states(pf: ProjectFacts) -> list[M.ContinuityState]:
    states: list[M.ContinuityState] = []
    entry_label = {e.id: (getattr(e, "name", "") or "") for e in pf.entries}

    # Character/object presence states (spatial dimension: scene order presence).
    for entry_id, order_indices in pf.scene_appearances.items():
        obs = []
        for oi in order_indices:
            scene = pf.scenes[oi] if 0 <= oi < len(pf.scenes) else None
            sid = getattr(scene, "id", None) if scene else None
            loc = (getattr(scene, "location", "") or "") if scene else ""
            obs.append((oi, sid, loc or "present"))
        states.append(M.ContinuityState(
            subject_type="psyke", subject_id=entry_id, dimension=M.DIM_CHARACTER,
            label=entry_label.get(entry_id, ""), observations=obs))

    # Place state across scenes (which scenes occur at each location).
    by_location: dict[str, list] = {}
    for f in pf.facts:
        if f.fact_type == M.FT_LOCATION_STATE and f.value:
            by_location.setdefault(f.value, []).append((f.order_index, f.scene_id,
                                                         f.value))
    for loc, obs in by_location.items():
        states.append(M.ContinuityState(
            subject_type="place", subject_id=None, dimension=M.DIM_SPATIAL,
            label=loc, observations=sorted(obs)))

    return states


def character_appearance_span(pf: ProjectFacts, entry_id: int) -> tuple[int, int] | None:
    """(first_order_index, last_order_index) a character appears, or None."""
    idxs = pf.scene_appearances.get(entry_id)
    if not idxs:
        return None
    return (min(idxs), max(idxs))
