"""Knowledge Graph → text serializers (Phase 10P).

Concise, capped summaries for the Assistant context block and Logos messages.
Deterministic; no LLM; no DB write.
"""

from __future__ import annotations

from logosforge.knowledge_graph import provenance as P
from logosforge.knowledge_graph.builder import build_knowledge_graph
from logosforge.knowledge_graph.models import KnowledgeGraph
from logosforge.knowledge_graph.queries import (
    get_scene_context_graph,
    neighborhood,
)


def _label(graph: KnowledgeGraph, key: str) -> str:
    n = graph.get_node(key)
    return n.label if (n and n.label) else key


def explain_node(graph: KnowledgeGraph, key: str, *, cap: int = 8) -> str:
    node = graph.get_node(key)
    if node is None:
        return "Node not found."
    lines = [f"{node.node_type}: {node.label or key}"]
    if node.summary:
        lines.append(node.summary)
    nbrs = graph.neighbors(key)[:cap]
    if nbrs:
        lines.append(f"Connections ({len(graph.neighbors(key))}):")
        for e in nbrs:
            other = e.target if e.source == key else e.source
            lines.append(f"- {e.edge_type} → {_label(graph, other)} "
                         f"[{e.confidence}]")
    return "\n".join(lines)


def explain_edge(graph: KnowledgeGraph, edge) -> str:
    return (f"{_label(graph, edge.source)} —{edge.edge_type}→ "
            f"{_label(graph, edge.target)}\n"
            f"Confidence: {edge.confidence}; source: {edge.source_system}; "
            f"provenance: {edge.provenance}.\n"
            f"{edge.explanation}"
            + ("\n(User-confirmed.)" if edge.is_user_confirmed else ""))


def get_graph_summary_for_assistant(db, project_id: int, *,
                                    section_name: str | None = None,
                                    scene_id: int | None = None,
                                    graph: KnowledgeGraph | None = None) -> str:
    """Concise ``[Narrative Knowledge Graph]`` block — only when relevant.

    Prefers the current scene's neighborhood; otherwise a tiny project summary.
    Capped; deterministic; no LLM/DB write.
    """
    result = None
    if graph is None:
        result = build_knowledge_graph(db, project_id)
        graph = result.graph
    if graph.node_count == 0:
        return ""

    lines = ["[Narrative Knowledge Graph]"]
    if scene_id is not None:
        res = get_scene_context_graph(db, project_id, scene_id, graph=graph)
        if res.nodes:
            from logosforge.knowledge_graph.models import node_key
            skey = node_key(P.NT_SCENE, "scene", scene_id)
            psyke_types = {P.NT_PSYKE_ENTRY, P.NT_CHARACTER, P.NT_PLACE,
                           P.NT_OBJECT, P.NT_LORE, P.NT_THEME, P.NT_MOTIF}
            related_psyke, related_scenes, risks = [], [], []
            for e in res.edges:
                other = e.target if e.source == skey else e.source
                on = graph.get_node(other)
                if on is None:
                    continue
                if on.node_type in psyke_types and on.label not in related_psyke:
                    related_psyke.append(on.label)
                elif on.node_type == P.NT_SCENE and other != skey \
                        and on.label not in related_scenes:
                    related_scenes.append(on.label)
                elif e.edge_type in (P.ET_RISKS, P.ET_CONTRADICTS):
                    risks.append(on.label or other)
            if related_psyke:
                lines.append("Related PSYKE: " + ", ".join(related_psyke[:3]))
            if related_scenes:
                lines.append("Connected scenes: " + ", ".join(related_scenes[:3]))
            if risks:
                lines.append("Risks: " + ", ".join(risks[:3]))
    if len(lines) == 1:
        # No scene context — give a tiny project-level summary instead.
        if result is None:
            result = build_knowledge_graph(db, project_id)
        lines.append(result.summary_line())
        if result.undefined_terms:
            lines.append(f"Undefined note terms: "
                         f"{', '.join(result.undefined_terms[:3])}")
    if graph.warnings:
        lines.append("Note: " + graph.warnings[0])
    return "\n".join(lines) if len(lines) > 1 else ""
