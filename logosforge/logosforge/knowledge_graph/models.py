"""In-memory Narrative Knowledge Graph dataclasses (Phase 10P).

The live graph is computed in-memory — these are the working objects. Persisted
``KnowledgeGraphNode``/``KnowledgeGraphEdge`` rows (user-confirmed/hidden edges)
are merged into this structure by the builder.

Pure data: no Qt, no LLM, no DB. References to existing entities only — a node
stores a label/summary, never a copy of manuscript text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from logosforge.knowledge_graph import provenance as P


def node_key(node_type: str, source_type: str, source_id) -> str:
    """Stable key for a node: ``"node_type:source_type:source_id"``."""
    return f"{node_type}:{source_type}:{'' if source_id is None else source_id}"


@dataclass
class KGNode:
    key: str
    node_type: str
    source_type: str = ""
    source_id: str | None = None
    label: str = ""
    summary: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "node_type": self.node_type,
            "source_type": self.source_type, "source_id": self.source_id,
            "label": self.label, "summary": self.summary,
            "metadata": dict(self.metadata),
        }


@dataclass
class KGEdge:
    source: str            # source node key
    target: str            # target node key
    edge_type: str
    confidence: str = P.CONF_POSSIBLE
    provenance: str = ""
    source_system: str = ""
    explanation: str = ""
    is_user_confirmed: bool = False
    is_hidden: bool = False
    metadata: dict = field(default_factory=dict)

    @property
    def dedupe_key(self) -> tuple[str, str, str]:
        return (self.source, self.target, self.edge_type)

    @property
    def is_inferred(self) -> bool:
        return not self.is_user_confirmed and self.confidence != P.CONF_CONFIRMED

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source, "target": self.target,
            "edge_type": self.edge_type, "confidence": self.confidence,
            "provenance": self.provenance, "source_system": self.source_system,
            "explanation": self.explanation,
            "is_user_confirmed": self.is_user_confirmed,
            "is_hidden": self.is_hidden, "metadata": dict(self.metadata),
        }


@dataclass
class KnowledgeGraph:
    project_id: int
    writing_mode: str = "novel"
    nodes: dict[str, KGNode] = field(default_factory=dict)
    edges: list[KGEdge] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unavailable: list[str] = field(default_factory=list)  # deferred source systems
    _edge_index: dict[tuple, KGEdge] = field(default_factory=dict, repr=False)

    # -- mutation (build-time only; never touches project content) ----------

    def add_node(self, node: KGNode) -> KGNode:
        existing = self.nodes.get(node.key)
        if existing is None:
            self.nodes[node.key] = node
            return node
        # Merge: keep first label/summary, union metadata.
        if not existing.label and node.label:
            existing.label = node.label
        if not existing.summary and node.summary:
            existing.summary = node.summary
        existing.metadata.update(node.metadata)
        return existing

    def add_edge(self, edge: KGEdge) -> KGEdge:
        prior = self._edge_index.get(edge.dedupe_key)
        if prior is None:
            self._edge_index[edge.dedupe_key] = edge
            self.edges.append(edge)
            return edge
        # Same (source,target,type): keep the strongest confidence + confirmation.
        prior.confidence = P.stronger_confidence(prior.confidence, edge.confidence)
        prior.is_user_confirmed = prior.is_user_confirmed or edge.is_user_confirmed
        if edge.is_user_confirmed:
            prior.is_hidden = edge.is_hidden
        if not prior.explanation and edge.explanation:
            prior.explanation = edge.explanation
        return prior

    # -- queries ------------------------------------------------------------

    def get_node(self, key: str) -> KGNode | None:
        return self.nodes.get(key)

    def visible_edges(self, *, include_inferred: bool = True) -> list[KGEdge]:
        out = []
        for e in self.edges:
            if e.is_hidden:
                continue
            if not include_inferred and e.is_inferred:
                continue
            out.append(e)
        return out

    def degree(self, key: str, *, include_inferred: bool = True) -> int:
        n = 0
        for e in self.visible_edges(include_inferred=include_inferred):
            if e.source == key or e.target == key:
                n += 1
        return n

    def neighbors(self, key: str, *, include_inferred: bool = True) -> list[KGEdge]:
        return [e for e in self.visible_edges(include_inferred=include_inferred)
                if e.source == key or e.target == key]

    def nodes_of_type(self, node_type: str) -> list[KGNode]:
        return [n for n in self.nodes.values() if n.node_type == node_type]

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len([e for e in self.edges if not e.is_hidden])

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id, "writing_mode": self.writing_mode,
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges if not e.is_hidden],
            "warnings": list(self.warnings),
            "unavailable": list(self.unavailable),
        }
