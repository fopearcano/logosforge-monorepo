"""Knowledge Graph builder (Phase 10P).

Orchestrates the extractors into one in-memory :class:`KnowledgeGraph`, then
merges persisted **user-confirmed / hidden** edges back in so that confirmation
state survives a rebuild (inferred edges are always regenerated). Deterministic,
read-only by default, current-project-only, capped.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from logosforge.knowledge_graph import provenance as P
from logosforge.knowledge_graph.extractor_notes import extract_notes
from logosforge.knowledge_graph.extractor_psyke import extract_psyke
from logosforge.knowledge_graph.extractor_revision import (
    extract_apply,
    extract_revision,
    extract_rewrite,
)
from logosforge.knowledge_graph.extractor_structure import extract_structure
from logosforge.knowledge_graph.extractor_workflow import (
    extract_setup_payoff,
    extract_workflows,
)
from logosforge.knowledge_graph.models import KnowledgeGraph
from logosforge.knowledge_graph.scoring import (
    high_centrality_nodes,
    orphan_nodes,
)
from logosforge.db import KnowledgeGraphProjectNotFound
from logosforge.writing_modes import get_project_writing_mode_by_id


@dataclass
class KnowledgeGraphResult:
    graph: KnowledgeGraph
    undefined_terms: list[str] = field(default_factory=list)
    orphans: list = field(default_factory=list)   # list[KGNode]
    central: list = field(default_factory=list)    # list[(KGNode, degree)]

    @property
    def node_count(self) -> int:
        return self.graph.node_count

    @property
    def edge_count(self) -> int:
        return self.graph.edge_count

    @property
    def warning_count(self) -> int:
        return len(self.graph.warnings)

    def summary_line(self) -> str:
        g = self.graph
        return (f"Knowledge Graph: {g.node_count} nodes, {g.edge_count} edges, "
                f"{len(self.orphans)} orphan(s), {len(g.warnings)} warning(s).")


def build_knowledge_graph(db, project_id: int, *, options: dict | None = None,
                          ) -> KnowledgeGraphResult:
    options = options or {}
    mode = get_project_writing_mode_by_id(db, project_id)
    graph = KnowledgeGraph(project_id=project_id, writing_mode=mode)

    # Order matters only for node-existence; extractors are individually safe.
    extract_structure(db, project_id, graph)
    extract_psyke(db, project_id, graph)
    undefined = extract_notes(db, project_id, graph)
    if options.get("include_revision", True):
        extract_revision(db, project_id, graph)
    if options.get("include_rewrite", True):
        extract_rewrite(db, project_id, graph)
    if options.get("include_apply", True):
        extract_apply(db, project_id, graph)
    if options.get("include_workflows", True):
        extract_workflows(db, project_id, graph)
    if options.get("include_setup_payoff", True):
        extract_setup_payoff(db, project_id, graph)

    _merge_persisted_edges(db, project_id, graph)

    orphans = orphan_nodes(graph)
    central = high_centrality_nodes(graph)
    return KnowledgeGraphResult(graph=graph, undefined_terms=undefined,
                                orphans=orphans, central=central)


def _merge_persisted_edges(db, project_id: int, graph: KnowledgeGraph) -> None:
    """Apply persisted user-confirmed/hidden state to the freshly-built graph."""
    # This persisted layer now carries the optimistic-concurrency token for
    # edge review.  Reads must fail closed rather than advertise the empty
    # revision if storage is unavailable or corrupt.
    review = db.read_knowledge_graph_review_snapshot(project_id)
    if review is None:
        raise KnowledgeGraphProjectNotFound(project_id)
    node_rows = review.nodes
    rows = review.edges
    graph.revision = review.revision
    graph.persisted_hidden_edge_count = sum(
        1 for row in rows if row.is_hidden
    )
    # Persisted endpoint references make a confirmed or hidden review decision
    # discoverable even when its inferred basis later disappears.  They remain
    # references/summaries only; no manuscript text is copied here.
    if node_rows:
        import json

        from logosforge.knowledge_graph.models import KGNode

        for row in node_rows:
            metadata = {}
            try:
                decoded = json.loads(row.metadata_json or "{}")
                if isinstance(decoded, dict):
                    metadata = decoded
            except (json.JSONDecodeError, TypeError):
                pass
            graph.add_node(KGNode(
                key=row.node_key,
                node_type=row.node_type,
                source_type=row.source_type,
                source_id=row.source_id,
                label=row.label,
                summary=row.summary,
                metadata=metadata,
            ))
    index = {e.dedupe_key: e for e in graph.edges}
    for row in rows:
        # Very old hidden rows could predate endpoint persistence.  Keep their
        # project-scoped directional identity reviewable with reference-only
        # placeholder nodes; new commands always persist richer endpoints in
        # the same transaction.
        from logosforge.knowledge_graph.models import KGNode
        for key in (row.source_node_key, row.target_node_key):
            if key not in graph.nodes:
                parts = key.split(":", 2)
                graph.add_node(KGNode(
                    key=key,
                    node_type=(parts[0] if parts else "unknown"),
                    source_type=(parts[1] if len(parts) > 1 else "persisted"),
                    source_id=(parts[2] if len(parts) > 2 else None),
                    label=key,
                    summary="Persisted Knowledge Graph review endpoint.",
                ))
        dk = (row.source_node_key, row.target_node_key, row.edge_type)
        live = index.get(dk)
        if live is not None:
            if row.is_user_confirmed:
                live.is_user_confirmed = True
                live.confidence = P.CONF_CONFIRMED
            live.is_hidden = bool(row.is_hidden)
        elif row.is_user_confirmed or row.is_hidden:
            # A reviewed edge whose inferred basis disappeared remains
            # discoverable (including hidden rows so the user can restore it),
            # provided its persisted endpoint references are intact.
            if row.source_node_key in graph.nodes and row.target_node_key in graph.nodes:
                from logosforge.knowledge_graph.models import KGEdge
                graph.add_edge(KGEdge(
                    source=row.source_node_key, target=row.target_node_key,
                    edge_type=row.edge_type,
                    confidence=(
                        P.CONF_CONFIRMED
                        if row.is_user_confirmed else row.confidence
                    ),
                    provenance=(row.provenance or P.PROV_USER_GRAPH_LINK),
                    source_system=(row.source_system or P.SS_USER),
                    explanation=(
                        row.explanation
                        or (
                            "User-confirmed edge."
                            if row.is_user_confirmed
                            else "User-hidden edge."
                        )
                    ),
                    is_user_confirmed=bool(row.is_user_confirmed),
                    is_hidden=bool(row.is_hidden)))


def persist_snapshot(db, project_id: int, result: KnowledgeGraphResult):
    """Record a lightweight snapshot of a build (counts/summary). No content."""
    try:
        return db.create_kg_snapshot(
            project_id, summary=result.summary_line(),
            node_count=result.node_count, edge_count=result.edge_count,
            orphan_count=len(result.orphans),
            warning_count=result.warning_count)
    except Exception:
        return None
