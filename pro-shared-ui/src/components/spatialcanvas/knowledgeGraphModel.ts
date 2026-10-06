import type {
  KnowledgeGraphEdgeDTO,
  KnowledgeGraphNodeDTO,
  KnowledgeGraphReadDTO,
} from "@logosforge/ui-contracts";

export type GraphConfidence = "unknown" | "possible" | "likely" | "confirmed";

export interface KnowledgeGraphFilters {
  hiddenNodeTypes: ReadonlySet<string>;
  confidenceMin: GraphConfidence;
  sourceSystem: string;
}

export interface KnowledgeGraphView {
  nodes: KnowledgeGraphNodeDTO[];
  edges: KnowledgeGraphEdgeDTO[];
  orphanNodes: KnowledgeGraphNodeDTO[];
  weakLinks: KnowledgeGraphEdgeDTO[];
  nodeByKey: Map<string, KnowledgeGraphNodeDTO>;
}

const CONFIDENCE_RANK: Record<string, number> = {
  unknown: 0,
  possible: 1,
  likely: 2,
  confirmed: 3,
};

export function confidenceRank(value: string): number {
  return CONFIDENCE_RANK[value] ?? -1;
}

export function edgePassesFilters(
  edge: KnowledgeGraphEdgeDTO,
  filters: Pick<KnowledgeGraphFilters, "confidenceMin" | "sourceSystem">,
): boolean {
  return confidenceRank(edge.confidence) >= confidenceRank(filters.confidenceMin)
    && (filters.sourceSystem === "all" || edge.source_system === filters.sourceSystem);
}

/**
 * Apply presentation-only filters to one core-owned graph page. Orphan and
 * weak-link membership always comes from the server's full filtered graph;
 * the UI never infers those diagnostics from a potentially truncated page.
 */
export function buildKnowledgeGraphView(
  graph: KnowledgeGraphReadDTO,
  filters: KnowledgeGraphFilters,
): KnowledgeGraphView {
  const nodes = graph.nodes.filter((node) => !filters.hiddenNodeTypes.has(node.node_type));
  const nodeByKey = new Map(nodes.map((node) => [node.key, node]));
  const edges = graph.edges.filter((edge) => (
    nodeByKey.has(edge.source)
    && nodeByKey.has(edge.target)
    && edgePassesFilters(edge, filters)
  ));
  const orphanSet = new Set(graph.orphan_keys);
  const orphanNodes = nodes.filter((node) => orphanSet.has(node.key));
  const weakLinks = graph.weak_links.filter((edge) => (
    nodeByKey.has(edge.source)
    && nodeByKey.has(edge.target)
    && edgePassesFilters(edge, filters)
  ));
  return { nodes, edges, orphanNodes, weakLinks, nodeByKey };
}

export interface GraphPosition {
  x: number;
  y: number;
}

/**
 * Stable, bounded layout: related types remain adjacent without a physics loop.
 * Small maps use a spacious orbit; larger maps switch to a density-aware grid
 * so keyboard/mouse hit areas never collapse onto the same ring coordinates.
 */
export function layoutKnowledgeGraph(
  nodes: readonly KnowledgeGraphNodeDTO[],
  width = 900,
  height = 560,
): Map<string, GraphPosition> {
  const ordered = [...nodes].sort((left, right) => (
    left.node_type.localeCompare(right.node_type)
    || right.degree - left.degree
    || left.key.localeCompare(right.key)
  ));
  const positions = new Map<string, GraphPosition>();
  const centerX = width / 2;
  const centerY = height / 2;

  if (ordered.length > 12) {
    const horizontalMargin = Math.min(60, width / 5);
    const topMargin = Math.min(48, height / 5);
    const bottomMargin = Math.min(72, height / 4);
    const aspectRatio = Math.max(1, width / Math.max(1, height));
    const columns = Math.max(2, Math.ceil(Math.sqrt(ordered.length * aspectRatio)));
    const rows = Math.ceil(ordered.length / columns);
    const columnGap = columns === 1 ? 0 : (width - horizontalMargin * 2) / (columns - 1);
    const rowGap = rows === 1 ? 0 : (height - topMargin - bottomMargin) / (rows - 1);

    ordered.forEach((node, index) => {
      const row = Math.floor(index / columns);
      const column = index % columns;
      const rowSize = Math.min(columns, ordered.length - row * columns);
      const rowWidth = Math.max(0, rowSize - 1) * columnGap;
      const rowStart = centerX - rowWidth / 2;
      const displayedColumn = row % 2 === 0 ? column : rowSize - column - 1;
      positions.set(node.key, {
        x: rowStart + displayedColumn * columnGap,
        y: rows === 1 ? centerY : topMargin + row * rowGap,
      });
    });
    return positions;
  }

  const radiusX = Math.max(0, width / 2 - 105);
  const radiusY = Math.max(0, height / 2 - 82);
  ordered.forEach((node, index) => {
    if (ordered.length === 1) {
      positions.set(node.key, { x: centerX, y: centerY });
      return;
    }
    const angle = (index / ordered.length) * Math.PI * 2 - Math.PI / 2;
    positions.set(node.key, {
      x: centerX + radiusX * Math.cos(angle),
      y: centerY + radiusY * Math.sin(angle),
    });
  });
  return positions;
}

export function graphEdgeKey(edge: KnowledgeGraphEdgeDTO): string {
  return [edge.source, edge.target, edge.edge_type, edge.source_system, edge.provenance].join("\u0000");
}
