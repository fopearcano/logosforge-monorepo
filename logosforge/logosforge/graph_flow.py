"""Temporal narrative flow — story-order overlay for the graph view.

Given a project, produces an ordered list of FlowSegment objects that
connect scenes in their narrative order.  Four flow types:

  timeline  straight chronological chain through every scene
  acts      same chain, but a flag marks transitions across acts so
            the renderer can draw an act separator
  arc       same chain — the renderer reshapes it into a Freytag-style
            arching curve (rising → climax → falling)
  causal    only the segments where the source scene mentions the
            target scene via a [[link]] reference

Each scene is also tagged with a position band — beginning / middle /
ending — so the renderer can colour-drift the path from one end of the
story to the other.  The system is provider-neutral and pure-data; no
Qt imports here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from logosforge.db import Database


FLOW_TIMELINE = "timeline"
FLOW_ACTS = "acts"
FLOW_ARC = "arc"
FLOW_CAUSAL = "causal"

FLOW_TYPES: tuple[str, ...] = (FLOW_TIMELINE, FLOW_ACTS, FLOW_ARC, FLOW_CAUSAL)

BAND_BEGINNING = "beginning"
BAND_MIDDLE = "middle"
BAND_ENDING = "ending"

_BAND_COLORS = {
    BAND_BEGINNING: "#4ade80",  # green — fresh story start
    BAND_MIDDLE: "#f59e0b",     # gold — rising / midpoint
    BAND_ENDING: "#c084fc",     # violet — resolution
}


@dataclass(frozen=True)
class FlowSegment:
    from_scene_id: int
    to_scene_id: int
    band: str           # band of the *from* scene
    act_boundary: bool  # True when the two scenes belong to different acts


def position_band(idx: int, total: int) -> str:
    """Bucket a scene index into beginning / middle / ending."""
    if total <= 0:
        return BAND_MIDDLE
    pos = idx / max(total - 1, 1) if total > 1 else 0.0
    if pos <= 0.34:
        return BAND_BEGINNING
    if pos >= 0.67:
        return BAND_ENDING
    return BAND_MIDDLE


def band_color(band: str) -> str:
    return _BAND_COLORS.get(band, "#9e9e9e")


def compute_flow(
    db: "Database", project_id: int, flow_type: str = FLOW_TIMELINE,
) -> list[FlowSegment]:
    """Build the ordered list of FlowSegment for the requested flow type."""
    scenes = db.get_all_scenes(project_id)
    if len(scenes) < 2:
        return []
    total = len(scenes)

    if flow_type == FLOW_CAUSAL:
        return _causal_segments(scenes, total)

    segments: list[FlowSegment] = []
    for i in range(total - 1):
        cur = scenes[i]
        nxt = scenes[i + 1]
        cur_act = (cur.act or "").strip()
        nxt_act = (nxt.act or "").strip()
        segments.append(FlowSegment(
            from_scene_id=cur.id,
            to_scene_id=nxt.id,
            band=position_band(i, total),
            act_boundary=bool(cur_act and nxt_act and cur_act != nxt_act),
        ))
    return segments


def _causal_segments(scenes: list, total: int) -> list[FlowSegment]:
    """Segments only between scenes whose text mentions another scene's title."""
    title_to_id: dict[str, int] = {}
    for s in scenes:
        if s.title:
            title_to_id[s.title.lower()] = s.id
    if not title_to_id:
        return []

    link_pat = re.compile(r"\[\[(.+?)\]\]")
    scene_index = {s.id: i for i, s in enumerate(scenes)}
    scene_act = {s.id: (s.act or "").strip() for s in scenes}
    segments: list[FlowSegment] = []

    for s in scenes:
        text = " ".join([
            s.summary or "", s.synopsis or "", s.goal or "",
            s.conflict or "", s.outcome or "", s.content or "",
        ])
        if not text:
            continue
        seen_targets: set[int] = set()
        for m in link_pat.finditer(text):
            tgt_id = title_to_id.get(m.group(1).lower())
            if tgt_id is None or tgt_id == s.id or tgt_id in seen_targets:
                continue
            seen_targets.add(tgt_id)
            band = position_band(scene_index[s.id], total)
            segments.append(FlowSegment(
                from_scene_id=s.id,
                to_scene_id=tgt_id,
                band=band,
                act_boundary=(
                    scene_act[s.id] != scene_act.get(tgt_id, "")
                    and bool(scene_act[s.id]) and bool(scene_act.get(tgt_id, ""))
                ),
            ))
    return segments


def scene_bands(db: "Database", project_id: int) -> dict[int, str]:
    """Map scene_id → band for every scene in the project."""
    scenes = db.get_all_scenes(project_id)
    total = len(scenes)
    return {s.id: position_band(i, total) for i, s in enumerate(scenes)}
