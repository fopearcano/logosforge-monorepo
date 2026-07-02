"""Knowledge Graph persistence + confirmable mutations (Phase 10P).

Two kinds of writes, both explicit (never automatic):

1. **Graph-metadata writes** — confirm / hide an edge. These touch only the
   knowledge-graph tables, never project content.
2. **Content writes** — convert a confirmed edge into a PSYKE relation, or create
   a PSYKE entry from an undefined term. These mutate PSYKE and so must be called
   explicitly by a user action (the engine never calls them on its own).
"""

from __future__ import annotations

from logosforge.knowledge_graph import provenance as P
from logosforge.knowledge_graph.models import KGEdge, KnowledgeGraph


def _persist_endpoints(db, project_id: int, graph: KnowledgeGraph, edge: KGEdge):
    for key in (edge.source, edge.target):
        n = graph.get_node(key)
        if n is not None:
            db.upsert_kg_node(project_id, key, node_type=n.node_type,
                              source_type=n.source_type, source_id=n.source_id,
                              label=n.label, summary=n.summary)


def confirm_edge(db, project_id: int, edge: KGEdge, *, graph: KnowledgeGraph | None = None):
    """Mark an inferred edge user-confirmed (graph metadata only)."""
    if graph is not None:
        _persist_endpoints(db, project_id, graph, edge)
        edge.is_user_confirmed = True
        edge.confidence = P.CONF_CONFIRMED
    return db.upsert_kg_edge(
        project_id, edge.source, edge.target, edge.edge_type,
        confidence=P.CONF_CONFIRMED, provenance=edge.provenance,
        source_system=edge.source_system, explanation=edge.explanation,
        is_user_confirmed=True, is_hidden=False)


def hide_edge(db, project_id: int, edge: KGEdge):
    """Hide an inferred edge (graph metadata only; reversible)."""
    return db.upsert_kg_edge(
        project_id, edge.source, edge.target, edge.edge_type,
        confidence=edge.confidence, provenance=edge.provenance,
        source_system=edge.source_system, explanation=edge.explanation,
        is_user_confirmed=False, is_hidden=True)


def unhide_edge(db, project_id: int, edge: KGEdge):
    return db.upsert_kg_edge(
        project_id, edge.source, edge.target, edge.edge_type,
        is_hidden=False)


def _psyke_id_from_key(key: str) -> int | None:
    # key = "node_type:psyke:<id>"
    parts = key.split(":")
    if len(parts) == 3 and parts[1] == "psyke" and parts[2].isdigit():
        return int(parts[2])
    return None


def convert_edge_to_psyke_relation(db, edge: KGEdge, *, relation_type: str = "") -> bool:
    """Create a PSYKE relation from a confirmed PSYKE↔PSYKE edge.

    CONTENT MUTATION — call only on an explicit, confirmed user action. Returns
    True if a relation was created. No-op unless both endpoints are PSYKE entries.
    """
    a = _psyke_id_from_key(edge.source)
    b = _psyke_id_from_key(edge.target)
    if a is None or b is None or a == b:
        return False
    db.add_psyke_relation(a, b, relation_type or "related")
    return True


def create_psyke_entry_from_term(db, project_id: int, term: str, *,
                                 entry_type: str = "other"):
    """Create a PSYKE entry from an undefined note term.

    CONTENT MUTATION — call only on an explicit, confirmed user action.
    """
    term = (term or "").strip()
    if not term:
        return None
    return db.create_psyke_entry(project_id, term, entry_type)
