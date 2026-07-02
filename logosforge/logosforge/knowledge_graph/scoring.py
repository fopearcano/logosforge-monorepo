"""Knowledge Graph scoring: orphans, centrality, weak links (Phase 10P).

Deterministic, capped, read-only. "Centrality" here is plain degree — explainable
and cheap; no eigenvector/PageRank pretence.
"""

from __future__ import annotations

from logosforge.knowledge_graph import provenance as P
from logosforge.knowledge_graph.models import KGEdge, KGNode, KnowledgeGraph

# Node types that are *expected* to be standalone / structural and so should not
# be reported as "orphans".
_NON_ORPHAN_TYPES = {P.NT_PROJECT}
# Node types we care about when looking for isolation.
_STORY_TYPES = {P.NT_SCENE, P.NT_CHARACTER, P.NT_PLACE, P.NT_OBJECT, P.NT_LORE,
                P.NT_THEME, P.NT_MOTIF, P.NT_PSYKE_ENTRY, P.NT_NOTE,
                P.NT_PLOT_BLOCK}


def orphan_nodes(graph: KnowledgeGraph, *, cap: int = 50) -> list[KGNode]:
    """Story nodes with no visible (non-inferred-or-inferred) connections.

    A node connected only to the project via a structural ``contains`` edge is
    still considered isolated for story purposes.
    """
    out: list[KGNode] = []
    for node in graph.nodes.values():
        if node.node_type in _NON_ORPHAN_TYPES or node.node_type not in _STORY_TYPES:
            continue
        meaningful = 0
        for e in graph.neighbors(node.key):
            other = e.target if e.source == node.key else e.source
            on = graph.get_node(other)
            if on is None:
                continue
            if on.node_type == P.NT_PROJECT and e.edge_type == P.ET_CONTAINS:
                continue  # project-membership doesn't count as a story connection
            meaningful += 1
        if meaningful == 0:
            out.append(node)
        if len(out) >= cap:
            break
    return out


def high_centrality_nodes(graph: KnowledgeGraph, *, top: int = 10,
                          ) -> list[tuple[KGNode, int]]:
    scored = [(n, graph.degree(n.key)) for n in graph.nodes.values()
              if n.node_type != P.NT_PROJECT]
    scored.sort(key=lambda t: t[1], reverse=True)
    return [(n, d) for n, d in scored[:top] if d > 0]


def weak_link_edges(graph: KnowledgeGraph, *, cap: int = 50) -> list[KGEdge]:
    """Inferred (possible/likely, not user-confirmed) edges that may need
    confirmation."""
    out = [e for e in graph.visible_edges() if e.is_inferred]
    out.sort(key=lambda e: P.confidence_rank(e.confidence), reverse=True)
    return out[:cap]


def scenes_without_psyke(graph: KnowledgeGraph, *, cap: int = 50) -> list[KGNode]:
    """Scene nodes with no PSYKE/character appearance edge."""
    psyke_types = {P.NT_PSYKE_ENTRY, P.NT_CHARACTER, P.NT_PLACE, P.NT_OBJECT,
                   P.NT_LORE, P.NT_THEME, P.NT_MOTIF}
    out: list[KGNode] = []
    for node in graph.nodes_of_type(P.NT_SCENE):
        has = False
        for e in graph.neighbors(node.key):
            other = e.target if e.source == node.key else e.source
            on = graph.get_node(other)
            if on is not None and on.node_type in psyke_types:
                has = True
                break
        if not has:
            out.append(node)
        if len(out) >= cap:
            break
    return out
