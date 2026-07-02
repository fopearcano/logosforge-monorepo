"""Narrative Knowledge Graph (Phase 10P).

A traceable semantic map of a project: PSYKE entries, scenes, chapters, acts,
notes, plot blocks, timeline order, graph links, setup/payoff, and
revision/rewrite/apply findings — connected by typed edges that each carry a
confidence level, provenance and source system. Confirmed (explicit / user)
edges are distinguished from inferred ones, and inferred links never masquerade
as canonical.

The live graph is computed in-memory each build (deterministic, read-only); only
user-confirmed / hidden edges are persisted, so confirmation survives rebuilds
while inferred edges are regenerated. No LLM, no autonomous mutation, no cloud,
no external graph DB.
"""

from __future__ import annotations

from logosforge.knowledge_graph.builder import (
    KnowledgeGraphResult,
    build_knowledge_graph,
    persist_snapshot,
)
from logosforge.knowledge_graph.collector import (
    confirm_edge,
    convert_edge_to_psyke_relation,
    create_psyke_entry_from_term,
    hide_edge,
    unhide_edge,
)
from logosforge.knowledge_graph.decision_cards import build_graph_decision_cards
from logosforge.knowledge_graph.models import (
    KGEdge,
    KGNode,
    KnowledgeGraph,
    node_key,
)
from logosforge.knowledge_graph.queries import (
    GraphQuery,
    GraphQueryResult,
    get_high_centrality_nodes,
    get_node_neighborhood,
    get_orphan_nodes,
    get_psyke_entry_context_graph,
    get_scene_context_graph,
    get_scenes_without_psyke,
    get_weak_links,
    query_knowledge_graph,
)
from logosforge.knowledge_graph.serializers import (
    explain_edge,
    explain_node,
    get_graph_summary_for_assistant,
)

__all__ = [
    "KnowledgeGraph",
    "KnowledgeGraphResult",
    "KGNode",
    "KGEdge",
    "GraphQuery",
    "GraphQueryResult",
    "node_key",
    "build_knowledge_graph",
    "persist_snapshot",
    "query_knowledge_graph",
    "get_node_neighborhood",
    "get_scene_context_graph",
    "get_psyke_entry_context_graph",
    "get_orphan_nodes",
    "get_high_centrality_nodes",
    "get_weak_links",
    "get_scenes_without_psyke",
    "get_graph_summary_for_assistant",
    "explain_node",
    "explain_edge",
    "build_graph_decision_cards",
    "confirm_edge",
    "hide_edge",
    "unhide_edge",
    "convert_edge_to_psyke_relation",
    "create_psyke_entry_from_term",
]
