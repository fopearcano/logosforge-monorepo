"""Knowledge Graph query API (Phase 10P).

Deterministic, capped, read-only, current-project-only. Builds the graph then
answers structured questions over it. Callers that already have a built result
can pass it via ``graph=`` to avoid a rebuild.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from logosforge.knowledge_graph import provenance as P
from logosforge.knowledge_graph import scoring
from logosforge.knowledge_graph.builder import build_knowledge_graph
from logosforge.knowledge_graph.models import KGEdge, KGNode, KnowledgeGraph, node_key


@dataclass
class GraphQuery:
    node_type: str | None = None
    node_id: str | int | None = None
    edge_type: str | None = None
    confidence_min: str | None = None       # keep edges at least this strong
    source_system: str | None = None
    depth: int = 1
    limit: int = 100
    include_inferred: bool = True
    include_deferred: bool = True


@dataclass
class GraphQueryResult:
    nodes: list[KGNode] = field(default_factory=list)
    edges: list[KGEdge] = field(default_factory=list)
    explanation: str = ""

    def to_dict(self) -> dict:
        return {"nodes": [n.to_dict() for n in self.nodes],
                "edges": [e.to_dict() for e in self.edges],
                "explanation": self.explanation}


def _graph(db, project_id: int, graph: KnowledgeGraph | None):
    if graph is not None:
        return graph
    return build_knowledge_graph(db, project_id).graph


def _edge_ok(edge: KGEdge, q: GraphQuery) -> bool:
    if not q.include_inferred and edge.is_inferred:
        return False
    if q.edge_type and edge.edge_type != q.edge_type:
        return False
    if q.source_system and edge.source_system != q.source_system:
        return False
    if q.confidence_min and (P.confidence_rank(edge.confidence)
                             > P.confidence_rank(q.confidence_min)):
        return False
    return True


def neighborhood(graph: KnowledgeGraph, start_key: str, *, depth: int = 1,
                 include_inferred: bool = True, limit: int = 100,
                 ) -> GraphQueryResult:
    if start_key not in graph.nodes:
        return GraphQueryResult(explanation="Node not found.")
    frontier = {start_key}
    seen_nodes = {start_key}
    seen_edges: list[KGEdge] = []
    edge_keys = set()
    for _ in range(max(1, depth)):
        nxt = set()
        for key in frontier:
            for e in graph.neighbors(key, include_inferred=include_inferred):
                if e.dedupe_key not in edge_keys:
                    edge_keys.add(e.dedupe_key)
                    seen_edges.append(e)
                    if len(seen_edges) >= limit:
                        break
                other = e.target if e.source == key else e.source
                if other not in seen_nodes:
                    seen_nodes.add(other)
                    nxt.add(other)
            if len(seen_edges) >= limit:
                break
        frontier = nxt
        if not frontier or len(seen_edges) >= limit:
            break
    nodes = [graph.nodes[k] for k in seen_nodes if k in graph.nodes]
    return GraphQueryResult(nodes=nodes, edges=seen_edges,
                            explanation=f"{len(nodes)} node(s), {len(seen_edges)} edge(s).")


def query_knowledge_graph(db, project_id: int, query: GraphQuery, *,
                          graph: KnowledgeGraph | None = None) -> GraphQueryResult:
    g = _graph(db, project_id, graph)
    if query.node_type and query.node_id is not None:
        start = node_key(query.node_type, _src_for(query.node_type), query.node_id)
        # fall back to scanning for a matching key suffix if the source_type guess is off
        if start not in g.nodes:
            start = _find_key(g, query.node_type, query.node_id) or start
        res = neighborhood(g, start, depth=query.depth,
                           include_inferred=query.include_inferred,
                           limit=query.limit)
        res.edges = [e for e in res.edges if _edge_ok(e, query)]
        return res
    # No anchor: return filtered edge set (capped).
    edges = [e for e in g.visible_edges(include_inferred=query.include_inferred)
             if _edge_ok(e, query)][:query.limit]
    keys = {e.source for e in edges} | {e.target for e in edges}
    nodes = [g.nodes[k] for k in keys if k in g.nodes]
    return GraphQueryResult(nodes=nodes, edges=edges,
                            explanation=f"{len(nodes)} node(s), {len(edges)} edge(s).")


_SRC_GUESS = {P.NT_SCENE: "scene", P.NT_NOTE: "note", P.NT_PROJECT: "project",
              P.NT_PSYKE_ENTRY: "psyke", P.NT_CHARACTER: "psyke",
              P.NT_PLACE: "psyke", P.NT_OBJECT: "psyke", P.NT_THEME: "psyke",
              P.NT_MOTIF: "psyke", P.NT_LORE: "psyke"}


def _src_for(node_type: str) -> str:
    return _SRC_GUESS.get(node_type, node_type)


def _find_key(graph: KnowledgeGraph, node_type: str, node_id) -> str | None:
    suffix = f":{node_id}"
    for k, n in graph.nodes.items():
        if n.node_type == node_type and k.endswith(suffix):
            return k
    return None


# -- Convenience query helpers (used by Logos / Assistant / Dashboard) ------

def get_node_neighborhood(db, project_id: int, node_type: str, node_id,
                          depth: int = 1, *, graph=None) -> GraphQueryResult:
    g = _graph(db, project_id, graph)
    key = _find_key(g, node_type, node_id) or node_key(node_type,
                                                       _src_for(node_type), node_id)
    return neighborhood(g, key, depth=depth)


def get_scene_context_graph(db, project_id: int, scene_id: int, *, depth: int = 1,
                            graph=None) -> GraphQueryResult:
    return get_node_neighborhood(db, project_id, P.NT_SCENE, scene_id, depth,
                                 graph=graph)


def get_psyke_entry_context_graph(db, project_id: int, entry_id: int, *,
                                  depth: int = 1, graph=None) -> GraphQueryResult:
    g = _graph(db, project_id, graph)
    # PSYKE entries map to several node types; find by source id suffix.
    suffix = f":psyke:{entry_id}"
    key = next((k for k in g.nodes if k.endswith(suffix)), None)
    if key is None:
        return GraphQueryResult(explanation="PSYKE node not found.")
    return neighborhood(g, key, depth=depth)


def get_orphan_nodes(db, project_id: int, *, graph=None) -> list[KGNode]:
    return scoring.orphan_nodes(_graph(db, project_id, graph))


def get_high_centrality_nodes(db, project_id: int, *, graph=None):
    return scoring.high_centrality_nodes(_graph(db, project_id, graph))


def get_weak_links(db, project_id: int, *, graph=None) -> list[KGEdge]:
    return scoring.weak_link_edges(_graph(db, project_id, graph))


def get_scenes_without_psyke(db, project_id: int, *, graph=None) -> list[KGNode]:
    return scoring.scenes_without_psyke(_graph(db, project_id, graph))
