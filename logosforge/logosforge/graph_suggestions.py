"""Graph-Driven Narrative Suggestions — structural story direction from graph.

Generates suggestions purely from graph relationships, PSYKE state, and
temporal progression. No AI call needed — all logic is deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from logosforge.db import Database
from logosforge.ui.focus_graph_view import build_graph_data, get_neighborhood


_STATE_ESCALATION = {
    "calm": "tense",
    "happy": "conflicted",
    "hopeful": "anxious",
    "peaceful": "tense",
    "content": "restless",
    "tense": "desperate",
    "anxious": "broken",
    "conflicted": "shattered",
    "angry": "destructive",
    "frustrated": "explosive",
    "broken": "acceptance",
    "desperate": "reckless",
    "resolved": "tested",
}

_STATE_REVERSAL = {
    "calm": "shaken",
    "tense": "relieved",
    "broken": "sparked",
    "desperate": "grounded",
    "happy": "betrayed",
    "anxious": "confronted",
    "hopeful": "disillusioned",
    "angry": "humbled",
    "resolved": "challenged",
}


@dataclass
class GraphSuggestion:
    category: str
    text: str
    reason: str
    trace_nodes: list[str] = field(default_factory=list)


@dataclass
class GraphSuggestions:
    suggestions: list[GraphSuggestion] = field(default_factory=list)
    debug_info: list[str] = field(default_factory=list)


def generate_graph_suggestions(
    db: Database,
    project_id: int,
    scene_id: int,
) -> GraphSuggestions:
    """Generate narrative suggestions from graph structure."""
    result = GraphSuggestions()

    scene = db.get_scene_by_id(scene_id)
    if scene is None:
        return result

    all_scenes = db.get_all_scenes(project_id)
    scene_order = {s.id: s.sort_order for s in all_scenes}
    current_order = scene_order.get(scene_id, 0)

    data = build_graph_data(db, project_id)
    if not data.nodes:
        result.debug_info.append("No graph data available")
        return result

    focal_id = f"Scene:{scene_id}"
    if focal_id not in data.nodes:
        result.debug_info.append(f"Scene {scene_id} not in graph")
        return result

    neighbors_1hop = get_neighborhood(data, focal_id, hops=1) - {focal_id}
    neighbors_2hop = get_neighborhood(data, focal_id, hops=2) - {focal_id} - neighbors_1hop

    char_states: dict[int, str] = {}
    char_state_counts: dict[tuple[int, str], int] = {}
    for s in all_scenes:
        if s.sort_order <= current_order:
            for cid, state in db.get_scene_character_states(s.id):
                char_states[cid] = state
                key = (cid, state.lower())
                char_state_counts[key] = char_state_counts.get(key, 0) + 1

    scene_chars = db.get_scene_character_ids(scene_id)

    char_nodes = {
        nid: data.nodes[nid] for nid in data.nodes
        if data.nodes[nid].etype == "Character"
    }

    adjacency_counts = {
        nid: len(data.adjacency.get(nid, set()))
        for nid in data.nodes
    }

    char_scene_pairs: dict[tuple[int, int], bool] = {}
    for s in all_scenes:
        s_chars = db.get_scene_character_ids(s.id)
        for i, c1 in enumerate(s_chars):
            for c2 in s_chars[i + 1:]:
                pair = (min(c1, c2), max(c1, c2))
                char_scene_pairs[pair] = True

    escalation = _suggest_escalation(
        scene_chars, char_states, char_nodes, adjacency_counts, data,
    )
    if escalation:
        result.suggestions.append(escalation)
        result.debug_info.append(f"Escalation: {escalation.reason}")

    reversal = _suggest_reversal(
        scene_chars, char_states, char_nodes, all_scenes, scene_id,
    )
    if reversal:
        result.suggestions.append(reversal)
        result.debug_info.append(f"Reversal: {reversal.reason}")

    expansion = _suggest_expansion(
        scene_chars, char_nodes, char_scene_pairs, neighbors_2hop, data,
    )
    if expansion:
        result.suggestions.append(expansion)
        result.debug_info.append(f"Expansion: {expansion.reason}")

    internal = _suggest_internal_shift(
        scene_chars, char_states, char_nodes, char_state_counts,
    )
    if internal:
        result.suggestions.append(internal)
        result.debug_info.append(f"Internal: {internal.reason}")

    return result


def _suggest_escalation(
    scene_chars: list[int],
    char_states: dict[int, str],
    char_nodes: dict[str, object],
    adjacency_counts: dict[str, int],
    data,
) -> GraphSuggestion | None:
    """Suggest escalation based on dominant/central character."""
    dominant_char_id = None
    max_conn = 0
    for cid in scene_chars:
        nid = f"Character:{cid}"
        conn = adjacency_counts.get(nid, 0)
        if conn > max_conn:
            max_conn = conn
            dominant_char_id = cid

    if dominant_char_id is None and scene_chars:
        dominant_char_id = scene_chars[0]

    if dominant_char_id is None:
        return None

    char_name = _char_name(dominant_char_id, char_nodes)
    current_state = char_states.get(dominant_char_id, "")
    next_state = _STATE_ESCALATION.get(current_state.lower(), "challenged")

    trace = [f"Character:{dominant_char_id}"]

    if current_state:
        text = f"{char_name}'s {current_state} state escalates to {next_state}"
        reason = f"dominant character ({max_conn} connections), state: {current_state}"
    else:
        text = f"{char_name} faces direct consequence of their central role"
        reason = f"dominant character ({max_conn} connections), no tracked state"

    return GraphSuggestion("Escalation", text, reason, trace)


def _suggest_reversal(
    scene_chars: list[int],
    char_states: dict[int, str],
    char_nodes: dict[str, object],
    all_scenes: list,
    scene_id: int,
) -> GraphSuggestion | None:
    """Suggest reversal based on current emotional trajectory."""
    for cid in scene_chars:
        state = char_states.get(cid, "")
        if not state:
            continue
        reversal_state = _STATE_REVERSAL.get(state.lower())
        if reversal_state:
            char_name = _char_name(cid, char_nodes)
            text = f"{char_name}'s {state} is disrupted \u2014 shifts to {reversal_state}"
            reason = f"state reversal from {state}"
            trace = [f"Character:{cid}"]
            return GraphSuggestion("Reversal", text, reason, trace)

    if scene_chars:
        char_name = _char_name(scene_chars[0], char_nodes)
        text = f"An unexpected revelation upends {char_name}'s assumptions"
        reason = "no tracked state for reversal, generic suggestion"
        trace = [f"Character:{scene_chars[0]}"]
        return GraphSuggestion("Reversal", text, reason, trace)

    return None


def _suggest_expansion(
    scene_chars: list[int],
    char_nodes: dict[str, object],
    char_scene_pairs: dict[tuple[int, int], bool],
    neighbors_2hop: set[str],
    data,
) -> GraphSuggestion | None:
    """Suggest expansion: missing interactions or isolated reintegration."""
    for nid in neighbors_2hop:
        node = data.nodes.get(nid)
        if node and node.etype == "Character":
            for cid in scene_chars:
                pair = (min(cid, node.entity_id), max(cid, node.entity_id))
                if pair not in char_scene_pairs:
                    char_name = _char_name(cid, char_nodes)
                    text = (
                        f"{char_name} and {node.name} are connected in the "
                        f"narrative web but have never shared a scene"
                    )
                    reason = f"missing interaction: 2-hop neighbor, no shared scene"
                    trace = [f"Character:{cid}", nid]
                    return GraphSuggestion("Expansion", text, reason, trace)

    isolated = [
        nid for nid, node in data.nodes.items()
        if node.etype == "Character"
        and len(data.adjacency.get(nid, set())) <= 1
        and node.entity_id not in scene_chars
    ]
    if isolated:
        node = data.nodes[isolated[0]]
        text = f"{node.name} has been isolated \u2014 bring them into the current thread"
        reason = f"isolated character (\u22641 connection)"
        trace = [isolated[0]]
        return GraphSuggestion("Expansion", text, reason, trace)

    return None


def _suggest_internal_shift(
    scene_chars: list[int],
    char_states: dict[int, str],
    char_nodes: dict[str, object],
    char_state_counts: dict[tuple[int, str], int],
) -> GraphSuggestion | None:
    """Suggest internal character development moment."""
    stagnant_chars = []
    for cid in scene_chars:
        state = char_states.get(cid, "")
        if not state:
            stagnant_chars.append(cid)
            continue

        count = char_state_counts.get((cid, state.lower()), 0)
        if count >= 2:
            stagnant_chars.append(cid)

    if stagnant_chars:
        cid = stagnant_chars[0]
        char_name = _char_name(cid, char_nodes)
        state = char_states.get(cid, "")
        trace = [f"Character:{cid}"]
        if state:
            text = (
                f"{char_name} has been {state} for multiple scenes "
                f"\u2014 force an internal reckoning or quiet realization"
            )
            reason = f"stagnant state ({state} repeated)"
        else:
            text = f"{char_name} lacks emotional arc \u2014 introduce a moment of self-awareness"
            reason = "no tracked state progression"
        return GraphSuggestion("Internal shift", text, reason, trace)

    if scene_chars:
        cid = scene_chars[0]
        char_name = _char_name(cid, char_nodes)
        state = char_states.get(cid, "unknown")
        text = f"{char_name} pauses to process what {state} means for their path forward"
        reason = "character reflection opportunity"
        trace = [f"Character:{cid}"]
        return GraphSuggestion("Internal shift", text, reason, trace)

    return None


def _char_name(char_id: int, char_nodes: dict[str, object]) -> str:
    nid = f"Character:{char_id}"
    node = char_nodes.get(nid)
    if node:
        return node.name
    return f"Character #{char_id}"


def format_suggestions(suggestions: GraphSuggestions) -> str:
    """Format suggestions into readable text block."""
    if not suggestions.suggestions:
        return ""

    lines = ["Next Narrative Possibilities:", ""]
    for i, s in enumerate(suggestions.suggestions, 1):
        lines.append(f"{i}. {s.category}")
        lines.append(f"   \u2192 {s.text}")
        lines.append("")

    return "\n".join(lines).rstrip()


def format_suggestions_debug(suggestions: GraphSuggestions) -> str:
    """Format debug info about suggestion reasoning."""
    if not suggestions.debug_info:
        return ""
    lines = ["[Suggestion Debug]"]
    for info in suggestions.debug_info:
        lines.append(f"  - {info}")
    return "\n".join(lines)
