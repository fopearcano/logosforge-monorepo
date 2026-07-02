"""Graph data model — the headless, Qt-free core of the knowledge graph.

This module owns the *data* side of the graph: the semantic node/edge kind
constants, the lightweight ``GraphNode`` / ``GraphEdge`` / ``GraphData``
dataclasses, and ``build_graph_data`` — which assembles a project's graph from
the DB link graph + PSYKE relations + scene participation + Act clusters.

It deliberately imports **no Qt**, so server / headless deployments (the API's
``remote`` mode) can build and analyse the graph without a display stack. The
Qt view in ``logosforge.ui.focus_graph_view`` re-exports these names and layers
rendering (colors, shapes, styles) + the screenplay/GN/stage/series edge
enrichers on top.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from logosforge.db import Database

# -- Semantic node kinds (subtype-aware) --------------------------------------
# Each kind maps (in the view) to a distinct shape + color so types are
# recognizable at a glance. The strings themselves are the headless contract.

NODE_KIND_CHARACTER = "character"
NODE_KIND_PLACE = "place"
NODE_KIND_OBJECT = "object"
NODE_KIND_THEME = "theme"
NODE_KIND_LORE = "lore"
NODE_KIND_SCENE = "scene"
NODE_KIND_ACT = "act"
NODE_KIND_NOTE = "note"
NODE_KIND_OTHER = "other"

# -- Graphic Novel node kinds -------------------------------------------------
NODE_KIND_PAGE = "page"
NODE_KIND_PANEL = "panel"
NODE_KIND_MOTIF = "motif"
NODE_KIND_GN_OBJECT = "gn_object"

# -- Stage Script node kinds --------------------------------------------------
# Characters / scenes / set-locations / props reuse the existing character /
# scene / place / object kinds. Cues and offstage events are new.
NODE_KIND_CUE = "cue"
NODE_KIND_OFFSTAGE = "offstage"

# -- Series node kinds --------------------------------------------------------
# Characters / scenes reuse the existing kinds. Seasons, episodes, arcs,
# mysteries and A/B/C plotlines are the new long-form structural nodes.
NODE_KIND_SEASON = "season"
NODE_KIND_EPISODE = "episode"
NODE_KIND_ARC = "arc"
NODE_KIND_MYSTERY = "mystery"
NODE_KIND_PLOTLINE = "plotline"

# -- Quantum node kinds -------------------------------------------------------
NODE_KIND_WAVEFUNCTION = "wavefunction"
NODE_KIND_BRANCH = "branch"

# -- Semantic edge kinds ------------------------------------------------------

EDGE_LINK = "link"                  # generic / unknown
EDGE_MENTION = "mention"            # [[text-link]] reference
EDGE_PSYKE_RELATION = "psyke_relation"   # PSYKE entry ↔ related entry
EDGE_PARTICIPATION = "participation"     # scene ↔ character / place
EDGE_CONTAINMENT = "containment"         # Act → Scene
EDGE_QUANTUM = "quantum_branch"          # wavefunction → branch (in Quantum mode)

# -- Screenplay-specific edge kinds ------------------------------------------
EDGE_CAUSALITY = "causality"             # consecutive scenes sharing characters
EDGE_SETUP_PAYOFF = "setup_payoff"       # PSYKE supports_setup / payoff relation
EDGE_KNOWLEDGE = "knowledge"             # scenes sharing who_knows_what characters
EDGE_SUBTEXT = "subtext"                 # PSYKE subtext_opposition relation
EDGE_VISUAL_MOTIF = "visual_motif"       # PSYKE visual_motif relation
EDGE_CONTINUITY = "continuity"           # continuity tracking across scenes

# -- Graphic Novel-specific edge kinds ---------------------------------------
EDGE_GN_CONTAINS = "gn_contains"             # page → panel
EDGE_GN_PAGE_FLOW = "gn_page_flow"           # page → next page (reading order)
EDGE_GN_PANEL_CAUSALITY = "gn_panel_causality"  # panel → next panel
EDGE_GN_MOTIF = "gn_motif"                   # motif ↔ page it appears on
EDGE_GN_SYMBOL_ECHO = "gn_symbol_echo"       # page ↔ page sharing a motif
EDGE_GN_OBJECT_CONTINUITY = "gn_object_continuity"  # object ↔ page it appears on
EDGE_GN_CHARACTER_PRESENT = "gn_character_present"   # character ↔ page (appears_in)
EDGE_GN_PSYKE_MOTIF = "gn_psyke_motif"               # motif ↔ PSYKE theme/object entry

# -- Stage Script-specific edge kinds ----------------------------------------
EDGE_SS_PRESSURE = "ss_pressure"           # pressures/confronts/dominates...
EDGE_SS_SUBTEXT = "ss_subtext"             # subtext_opposition / avoids
EDGE_SS_ENTRANCE_EXIT = "ss_entrance_exit"  # character ↔ scene (enter/exit)
EDGE_SS_USES_PROP = "ss_uses_prop"         # character → prop, prop → scene
EDGE_SS_BLOCKING = "ss_blocking"           # scene ↔ set location
EDGE_SS_CUE = "ss_cue"                      # scene → cue
EDGE_SS_OFFSTAGE = "ss_offstage"           # character/scene ↔ offstage event

# -- Series-specific edge kinds ----------------------------------------------
EDGE_SR_CONTAINS = "sr_contains"           # season → episode, episode → plotline
EDGE_SR_CONTINUES = "sr_continues"         # episode → next episode (dependency)
EDGE_SR_SETS_UP = "sr_sets_up"             # setup episode → arc
EDGE_SR_PAYS_OFF = "sr_pays_off"           # payoff episode → arc (active)
EDGE_SR_RESOLVES = "sr_resolves"           # payoff episode → arc (resolved)
EDGE_SR_DELAYS = "sr_delays"               # payoff episode → arc (delayed)
EDGE_SR_ESCALATES = "sr_escalates"         # mid-span episode → arc
EDGE_SR_ECHOES = "sr_echoes"               # character → episode (progression/callback)
EDGE_SR_CONTRADICTS = "sr_contradicts"     # character → episode (continuity risk)

# PSYKE entry_type → semantic node kind.
_PSYKE_SUBTYPE_MAP = {
    "character": NODE_KIND_CHARACTER,
    "place": NODE_KIND_PLACE,
    "object": NODE_KIND_OBJECT,
    "theme": NODE_KIND_THEME,
    "lore": NODE_KIND_LORE,
    "other": NODE_KIND_OTHER,
}


@dataclass
class GraphNode:
    """A node in the graph."""

    node_id: str  # "type:id" e.g. "Character:5"
    etype: str
    entity_id: int
    name: str
    subtype: str = ""  # e.g. "theme", "lore", "object" for PSYKE entries


@dataclass
class GraphEdge:
    """A connection between two nodes."""

    source_id: str
    target_id: str
    edge_type: str = EDGE_LINK


@dataclass
class GraphData:
    """Full graph data for a project."""

    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)
    adjacency: dict[str, set[str]] = field(default_factory=dict)


def build_graph_data(db: Database, project_id: int) -> GraphData:
    """Build structured graph data from DB link graph + PSYKE relations,
    enriched with subtypes, Act clusters, and semantic edge types."""
    raw_nodes, raw_edges = db.build_link_graph(project_id)

    data = GraphData()

    for etype, eid, name in raw_nodes:
        node_id = f"{etype}:{eid}"
        data.nodes[node_id] = GraphNode(node_id, etype, eid, name)
        data.adjacency.setdefault(node_id, set())

    psyke_entries = db.get_all_psyke_entries(project_id)
    for entry in psyke_entries:
        node_id = f"PSYKE:{entry.id}"
        sub = _PSYKE_SUBTYPE_MAP.get((entry.entry_type or "").lower(), NODE_KIND_OTHER)
        if node_id not in data.nodes:
            data.nodes[node_id] = GraphNode(
                node_id, "PSYKE", entry.id, entry.name, subtype=sub,
            )
            data.adjacency.setdefault(node_id, set())
        else:
            data.nodes[node_id].subtype = sub

        related = db.get_related_psyke_entries(entry.id)
        for rel in related:
            rel_id = f"PSYKE:{rel.id}"
            rel_sub = _PSYKE_SUBTYPE_MAP.get((rel.entry_type or "").lower(), NODE_KIND_OTHER)
            if rel_id not in data.nodes:
                data.nodes[rel_id] = GraphNode(
                    rel_id, "PSYKE", rel.id, rel.name, subtype=rel_sub,
                )
                data.adjacency.setdefault(rel_id, set())
            data.edges.append(GraphEdge(node_id, rel_id, edge_type=EDGE_PSYKE_RELATION))
            data.adjacency.setdefault(node_id, set()).add(rel_id)
            data.adjacency.setdefault(rel_id, set()).add(node_id)

    name_to_id: dict[str, str] = {}
    for nid, node in data.nodes.items():
        name_to_id[node.name.lower()] = nid

    for src_name, tgt_name in raw_edges:
        src_id = name_to_id.get(src_name.lower())
        tgt_id = name_to_id.get(tgt_name.lower())
        if src_id and tgt_id:
            data.edges.append(GraphEdge(src_id, tgt_id, edge_type=EDGE_MENTION))
            data.adjacency.setdefault(src_id, set()).add(tgt_id)
            data.adjacency.setdefault(tgt_id, set()).add(src_id)

    # Participation: scene ↔ character / place from the junction tables.
    # To avoid polluting the graph with isolated scenes (no participants, no
    # mentions, no act), we only ADD a scene node here if it has at least one
    # participant, place, or act assignment. Scenes already in data.nodes
    # (because they were referenced via [[link]]) are kept as-is.
    char_name_by_id = {c.id: c.name for c in db.get_all_characters(project_id)}
    place_name_by_id = {p.id: p.name for p in db.get_all_places(project_id)}
    scenes = db.get_all_scenes(project_id)
    for scene in scenes:
        scene_id = f"Scene:{scene.id}"
        char_ids = db.get_scene_character_ids(scene.id)
        place_ids = db.get_scene_place_ids(scene.id)
        has_act = bool((scene.act or "").strip())
        has_participants = bool(char_ids) or bool(place_ids) or has_act
        already_in_graph = scene_id in data.nodes
        if not already_in_graph and not has_participants:
            continue
        if not already_in_graph:
            data.nodes[scene_id] = GraphNode(scene_id, "Scene", scene.id, scene.title)
            data.adjacency.setdefault(scene_id, set())
        for cid in char_ids:
            char_id = f"Character:{cid}"
            if char_id not in data.nodes:
                name = char_name_by_id.get(cid, f"Character {cid}")
                data.nodes[char_id] = GraphNode(char_id, "Character", cid, name)
                data.adjacency.setdefault(char_id, set())
            data.edges.append(GraphEdge(scene_id, char_id, edge_type=EDGE_PARTICIPATION))
            data.adjacency.setdefault(scene_id, set()).add(char_id)
            data.adjacency.setdefault(char_id, set()).add(scene_id)
        for pid in place_ids:
            place_id = f"Place:{pid}"
            if place_id not in data.nodes:
                name = place_name_by_id.get(pid, f"Place {pid}")
                data.nodes[place_id] = GraphNode(place_id, "Place", pid, name)
                data.adjacency.setdefault(place_id, set())
            data.edges.append(GraphEdge(scene_id, place_id, edge_type=EDGE_PARTICIPATION))
            data.adjacency.setdefault(scene_id, set()).add(place_id)
            data.adjacency.setdefault(place_id, set()).add(scene_id)

    # Act cluster nodes — one per distinct non-empty scene.act.  We only emit
    # an act node if at least one scene with that act ended up in the graph.
    act_order: dict[str, int] = {}
    for scene in scenes:
        scene_id = f"Scene:{scene.id}"
        if scene_id not in data.nodes:
            continue
        act = (scene.act or "").strip()
        if act and act not in act_order:
            act_order[act] = len(act_order) + 1
    for act, idx in act_order.items():
        act_id = f"Act:{idx}"
        data.nodes[act_id] = GraphNode(act_id, "Act", idx, act, subtype=NODE_KIND_ACT)
        data.adjacency.setdefault(act_id, set())
    for scene in scenes:
        scene_id = f"Scene:{scene.id}"
        if scene_id not in data.nodes:
            continue
        act = (scene.act or "").strip()
        if not act:
            continue
        act_id = f"Act:{act_order[act]}"
        data.edges.append(GraphEdge(act_id, scene_id, edge_type=EDGE_CONTAINMENT))
        data.adjacency[act_id].add(scene_id)
        data.adjacency.setdefault(scene_id, set()).add(act_id)

    return data
