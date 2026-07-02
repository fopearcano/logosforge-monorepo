"""Graph Meaning Layer — narrative insight from graph structure.

Computes per-node meaning metrics: character emotional state, scene importance,
arc grouping, dead zone detection, and PSYKE influence. All results are pure
data — the UI layer applies subtle visual adjustments.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from logosforge.db import Database


_STATE_WARMTH: dict[str, str] = {
    "calm": "cool",
    "happy": "cool",
    "hopeful": "cool",
    "peaceful": "cool",
    "content": "cool",
    "resolved": "cool",
    "tense": "warm",
    "anxious": "warm",
    "conflicted": "warm",
    "angry": "warm",
    "suspicious": "warm",
    "frustrated": "warm",
    "broken": "hot",
    "lost": "hot",
    "desperate": "hot",
    "grief": "hot",
    "shattered": "hot",
    "defeated": "hot",
}

_WARMTH_COLORS = {
    "cool": "#4ade80",
    "warm": "#f59e0b",
    "hot": "#ef4444",
    "neutral": "#9ca3af",
}


@dataclass
class NodeMeaning:
    importance: float = 0.0
    state_warmth: str = "neutral"
    is_dead_zone: bool = False
    psyke_glow: bool = False
    arc_group: str = ""


@dataclass
class ArcLink:
    source_id: str
    target_id: str
    plotline: str


@dataclass
class MeaningData:
    node_meanings: dict[str, NodeMeaning] = field(default_factory=dict)
    arc_links: list[ArcLink] = field(default_factory=list)
    flow_pairs: list[tuple[str, str]] = field(default_factory=list)


def compute_meaning(db: Database, project_id: int, node_ids: set[str]) -> MeaningData:
    """Compute meaning metrics for the given visible nodes."""
    result = MeaningData()

    scenes = db.get_all_scenes(project_id)
    scene_map = {s.id: s for s in scenes}
    scene_order = {s.id: s.sort_order for s in scenes}

    char_latest_state: dict[int, str] = {}
    for scene in scenes:
        for cid, state in db.get_scene_character_states(scene.id):
            char_latest_state[cid] = state

    scene_char_counts: dict[int, int] = {}
    for scene in scenes:
        scene_char_counts[scene.id] = len(db.get_scene_character_ids(scene.id))

    plotline_scenes: dict[str, list[int]] = {}
    for scene in scenes:
        pl = scene.plotline or "(unassigned)"
        plotline_scenes.setdefault(pl, []).append(scene.id)

    adjacency_counts: dict[str, int] = {}
    for nid in node_ids:
        adjacency_counts[nid] = 0

    from logosforge.ui.focus_graph_view import build_graph_data
    graph_data = build_graph_data(db, project_id)
    for nid in node_ids:
        adjacency_counts[nid] = len(graph_data.adjacency.get(nid, set()))

    for nid in node_ids:
        meaning = NodeMeaning()
        parts = nid.split(":", 1)
        if len(parts) != 2:
            result.node_meanings[nid] = meaning
            continue
        etype, eid_str = parts
        try:
            eid = int(eid_str)
        except ValueError:
            result.node_meanings[nid] = meaning
            continue

        if etype == "Character":
            state = char_latest_state.get(eid, "")
            warmth = _STATE_WARMTH.get(state.lower(), "neutral")
            meaning.state_warmth = warmth

        elif etype == "Scene":
            scene = scene_map.get(eid)
            if scene:
                score = scene_char_counts.get(eid, 0) * 2
                if scene.beat:
                    score += 3
                if scene.tags:
                    score += len(scene.tags.split(","))
                meaning.importance = min(score / 10.0, 1.0)
                meaning.arc_group = scene.plotline or ""

        elif etype == "PSYKE":
            conn_count = adjacency_counts.get(nid, 0)
            if conn_count >= 3:
                meaning.psyke_glow = True

        conn_count = adjacency_counts.get(nid, 0)
        if conn_count <= 1:
            meaning.is_dead_zone = True

        result.node_meanings[nid] = meaning

    for pl, scene_ids in plotline_scenes.items():
        ordered = sorted(scene_ids, key=lambda sid: scene_order.get(sid, 0))
        for i in range(len(ordered) - 1):
            src = f"Scene:{ordered[i]}"
            tgt = f"Scene:{ordered[i + 1]}"
            if src in node_ids and tgt in node_ids:
                result.arc_links.append(ArcLink(src, tgt, pl))

    scene_node_ids = sorted(
        [nid for nid in node_ids if nid.startswith("Scene:")],
        key=lambda nid: scene_order.get(int(nid.split(":")[1]), 0),
    )
    for i in range(len(scene_node_ids) - 1):
        result.flow_pairs.append((scene_node_ids[i], scene_node_ids[i + 1]))

    return result


def state_color(warmth: str) -> str:
    return _WARMTH_COLORS.get(warmth, _WARMTH_COLORS["neutral"])


def importance_radius_delta(importance: float) -> float:
    return importance * 6.0


def warmth_from_state(state: str) -> str:
    return _STATE_WARMTH.get(state.lower(), "neutral")
