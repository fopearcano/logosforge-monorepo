"""Graph analysis — narrative interpretation of the project's graph.

Two analysis layers:

  Per node      analyze_node(db, project_id, data, node_id) returns a
                NodeAnalysis with themes, relations, scenes, plotline arcs
                and Controlling-Idea alignment relevant to a single node.

  Global        explain_structure, find_disconnected_nodes,
                suggest_missing_relations, find_weak_thematic_clusters
                each return list[GraphInsight] suitable for the Insights
                panel or for the Assistant.

Both layers are pure data — no Qt imports — and can be sent to the
Assistant as plain text via compose_assistant_context().
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from logosforge.db import Database
    from logosforge.ui.focus_graph_view import GraphData


SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"


@dataclass
class NodeAnalysis:
    """Per-node narrative summary."""
    node_id: str
    name: str
    kind: str
    themes: list[str] = field(default_factory=list)
    relations: list[str] = field(default_factory=list)
    scenes: list[str] = field(default_factory=list)
    arcs: list[str] = field(default_factory=list)
    ci_alignment: str = ""                  # supports / opposes / tests / transforms / ""
    ci_aligned_neighbours: list[str] = field(default_factory=list)


@dataclass
class GraphInsight:
    """A single global finding the Assistant or panel can show."""
    title: str
    severity: str
    message: str
    node_ids: list[str] = field(default_factory=list)


# -- Per-node analysis -------------------------------------------------------

def analyze_node(
    db: "Database", project_id: int, data: "GraphData", node_id: str,
) -> NodeAnalysis | None:
    if not data or node_id not in data.nodes:
        return None
    node = data.nodes[node_id]
    from logosforge.ui.focus_graph_view import node_kind
    kind = node_kind(node)

    themes: list[str] = []
    relations: list[str] = []
    scenes: list[str] = []
    arcs: list[str] = []

    # Walk the adjacency to bucket neighbours.
    neighbours = data.adjacency.get(node_id, set())
    for nid in neighbours:
        nb = data.nodes.get(nid)
        if nb is None:
            continue
        nb_kind = node_kind(nb)
        if nb_kind == "theme":
            themes.append(nb.name)
        elif nb.etype == "Scene":
            scenes.append(nb.name)
        else:
            relations.append(f"{nb.name} ({nb_kind})")

    # Arcs (plotlines): pull from the scenes this node touches.
    if node.etype == "Character":
        all_scenes = db.get_all_scenes(project_id)
        for s in all_scenes:
            if node.entity_id in db.get_scene_character_ids(s.id):
                pl = (s.plotline or "").strip()
                if pl and pl not in arcs:
                    arcs.append(pl)
    elif node.etype == "Scene":
        sc = db.get_scene_by_id(node.entity_id)
        if sc and (sc.plotline or "").strip():
            arcs.append(sc.plotline.strip())

    # Controlling Idea alignment.
    ci_alignment = ""
    ci_aligned_neighbours: list[str] = []
    try:
        from logosforge.controlling_idea import load as load_ci
        ci = load_ci(db, project_id)
        if ci.is_defined():
            if node.etype == "Scene":
                ci_alignment = ci.scene_alignment.get(str(node.entity_id), "")
            elif node.etype == "PSYKE":
                ci_alignment = ci.psyke_alignment.get(str(node.entity_id), "")
            # Neighbours with their own CI alignment.
            for nid in neighbours:
                nb = data.nodes.get(nid)
                if nb is None:
                    continue
                if nb.etype == "Scene":
                    al = ci.scene_alignment.get(str(nb.entity_id), "")
                elif nb.etype == "PSYKE":
                    al = ci.psyke_alignment.get(str(nb.entity_id), "")
                else:
                    al = ""
                if al:
                    ci_aligned_neighbours.append(f"{nb.name} ({al})")
    except Exception:
        pass

    return NodeAnalysis(
        node_id=node_id,
        name=node.name,
        kind=kind,
        themes=sorted(set(themes)),
        relations=sorted(set(relations)),
        scenes=scenes,
        arcs=arcs,
        ci_alignment=ci_alignment,
        ci_aligned_neighbours=sorted(set(ci_aligned_neighbours)),
    )


# -- Global analyses ---------------------------------------------------------

def explain_structure(
    db: "Database", project_id: int, data: "GraphData",
) -> str:
    """Short prose summary of the graph: counts + density + most-connected node."""
    if not data or not data.nodes:
        return "The graph is empty — no characters, places, or PSYKE entries yet."

    by_kind: dict[str, int] = defaultdict(int)
    from logosforge.ui.focus_graph_view import node_kind
    for node in data.nodes.values():
        by_kind[node_kind(node)] += 1

    parts = [
        f"{by_kind.get(k, 0)} {label}"
        for label, k in (
            ("characters", "character"), ("places", "place"),
            ("themes", "theme"), ("lore", "lore"), ("objects", "object"),
            ("scenes", "scene"), ("acts", "act"),
        )
        if by_kind.get(k, 0) > 0
    ]
    summary = "Graph: " + ", ".join(parts) + "."

    # Most-connected node.
    if data.adjacency:
        most = max(
            ((nid, len(neighbours)) for nid, neighbours in data.adjacency.items()),
            key=lambda kv: kv[1],
        )
        if most[1] > 0:
            name = data.nodes[most[0]].name if most[0] in data.nodes else most[0]
            summary += f" Most connected: {name} ({most[1]} neighbours)."

    return summary


def find_disconnected_nodes(data: "GraphData") -> list[GraphInsight]:
    """Nodes with no neighbours at all."""
    if not data:
        return []
    isolated: list[str] = []
    for nid, neighbours in data.adjacency.items():
        if not neighbours and nid in data.nodes:
            # Acts with no scenes are uninteresting; skip.
            if data.nodes[nid].etype == "Act":
                continue
            isolated.append(nid)
    if not isolated:
        return []
    names = ", ".join(data.nodes[nid].name for nid in isolated[:6])
    msg = (
        f"{len(isolated)} disconnected node"
        f"{'s' if len(isolated) != 1 else ''}: {names}"
    )
    if len(isolated) > 6:
        msg += f" (and {len(isolated) - 6} more)"
    return [GraphInsight(
        title="Disconnected nodes",
        severity=SEVERITY_WARNING,
        message=msg,
        node_ids=isolated,
    )]


def suggest_missing_relations(
    db: "Database", project_id: int, data: "GraphData",
) -> list[GraphInsight]:
    """Characters who share many scenes but lack a PSYKE relation."""
    if not data:
        return []
    insights: list[GraphInsight] = []

    # Build char_id → set of scene IDs they appear in.
    scenes = db.get_all_scenes(project_id)
    char_scenes: dict[int, set[int]] = defaultdict(set)
    for s in scenes:
        for cid in db.get_scene_character_ids(s.id):
            char_scenes[cid].add(s.id)

    # Existing PSYKE-relation pairs among character PSYKE entries.
    psyke_pair: set[tuple[int, int]] = set()
    name_to_psyke_id: dict[str, int] = {}
    for n in data.nodes.values():
        if n.etype == "PSYKE":
            name_to_psyke_id[n.name.lower()] = n.entity_id
    for n in data.nodes.values():
        if n.etype != "PSYKE":
            continue
        related = db.get_related_psyke_entries(n.entity_id)
        for r in related:
            a, b = sorted((n.entity_id, r.id))
            psyke_pair.add((a, b))

    # Map character name → PSYKE entry id (for character-typed PSYKE entries).
    chars = {c.id: c for c in db.get_all_characters(project_id)}
    char_to_psyke: dict[int, int] = {}
    for cid, char in chars.items():
        pid = name_to_psyke_id.get(char.name.lower())
        if pid is not None:
            char_to_psyke[cid] = pid

    pairs_seen: set[tuple[int, int]] = set()
    suggestions: list[str] = []
    for cid_a, scenes_a in char_scenes.items():
        for cid_b, scenes_b in char_scenes.items():
            if cid_a >= cid_b:
                continue
            shared = len(scenes_a & scenes_b)
            if shared < 2:
                continue
            pair_key = (cid_a, cid_b)
            if pair_key in pairs_seen:
                continue
            pairs_seen.add(pair_key)
            pa = char_to_psyke.get(cid_a)
            pb = char_to_psyke.get(cid_b)
            if pa is None or pb is None:
                continue
            if tuple(sorted((pa, pb))) in psyke_pair:
                continue
            suggestions.append(
                f"{chars[cid_a].name} and {chars[cid_b].name} share {shared}"
                f" scene{'s' if shared != 1 else ''} but have no PSYKE relation."
            )

    for line in suggestions[:5]:
        insights.append(GraphInsight(
            title="Missing PSYKE relation",
            severity=SEVERITY_INFO,
            message=line,
        ))
    return insights


def find_weak_thematic_clusters(
    db: "Database", project_id: int, data: "GraphData",
) -> list[GraphInsight]:
    """Themes whose presence (via scenes mentioning them) drops sharply across acts."""
    if not data:
        return []
    from logosforge.ui.focus_graph_view import node_kind

    theme_nodes = [
        n for n in data.nodes.values()
        if n.etype == "PSYKE" and node_kind(n) == "theme"
    ]
    if not theme_nodes:
        return []

    scenes = db.get_all_scenes(project_id)
    if not scenes:
        return []
    scenes_by_act: dict[str, list[int]] = defaultdict(list)
    for s in scenes:
        act = (s.act or "").strip() or "(unassigned)"
        scenes_by_act[act].append(s.id)
    acts_in_order: list[str] = []
    seen_acts: set[str] = set()
    for s in scenes:
        act = (s.act or "").strip() or "(unassigned)"
        if act not in seen_acts:
            seen_acts.add(act)
            acts_in_order.append(act)

    if len(acts_in_order) < 2:
        return []

    insights: list[GraphInsight] = []

    # Build scene_id → text blob once.
    scene_text: dict[int, str] = {}
    for s in scenes:
        scene_text[s.id] = " ".join([
            s.summary or "", s.synopsis or "", s.goal or "",
            s.conflict or "", s.outcome or "", s.content or "",
        ]).lower()

    for theme in theme_nodes:
        token = theme.name.lower()
        if not token:
            continue
        per_act_hits: dict[str, int] = {}
        for act in acts_in_order:
            hits = 0
            for sid in scenes_by_act.get(act, []):
                if token in scene_text.get(sid, ""):
                    hits += 1
            per_act_hits[act] = hits

        total = sum(per_act_hits.values())
        if total < 2:
            continue  # too rare to draw conclusions

        max_act = max(per_act_hits, key=per_act_hits.get)
        max_hits = per_act_hits[max_act]
        zero_acts = [a for a in acts_in_order if per_act_hits[a] == 0]
        # "Strong in one act, absent in another" heuristic.
        if max_hits >= 2 and zero_acts:
            missing = ", ".join(zero_acts[:3])
            insights.append(GraphInsight(
                title=f"Theme '{theme.name}' is uneven across acts",
                severity=SEVERITY_WARNING,
                message=(
                    f"'{theme.name}' appears strongly in {max_act}"
                    f" ({max_hits} scene{'s' if max_hits != 1 else ''})"
                    f" but is absent in {missing}."
                ),
                node_ids=[f"PSYKE:{theme.entity_id}"],
            ))

    return insights


# -- Composition -------------------------------------------------------------

def compose_assistant_context(payload) -> str:
    """Render a NodeAnalysis or list[GraphInsight] as an Assistant prompt block."""
    if isinstance(payload, NodeAnalysis):
        return _format_node(payload)
    if isinstance(payload, list):
        return _format_insights(payload)
    return ""


def _format_node(a: NodeAnalysis) -> str:
    lines = [f"[Graph Analysis: {a.name}]", f"Kind: {a.kind}"]
    if a.themes:
        lines.append(f"Themes: {', '.join(a.themes)}")
    if a.relations:
        lines.append(f"Relations: {', '.join(a.relations[:10])}")
    if a.scenes:
        lines.append(f"Appears in: {', '.join(a.scenes[:10])}")
    if a.arcs:
        lines.append(f"Plotlines / arcs: {', '.join(a.arcs)}")
    if a.ci_alignment:
        lines.append(f"Controlling Idea alignment: {a.ci_alignment}")
    if a.ci_aligned_neighbours:
        lines.append(
            "Neighbours with CI alignment: "
            + ", ".join(a.ci_aligned_neighbours[:6])
        )
    return "\n".join(lines)


def _format_insights(insights: list[GraphInsight]) -> str:
    if not insights:
        return "[Graph Insights]\nNo issues detected."
    lines = ["[Graph Insights]"]
    for ins in insights[:12]:
        tag = "!" if ins.severity == SEVERITY_WARNING else "-"
        lines.append(f"{tag} {ins.title}: {ins.message}")
    return "\n".join(lines)
