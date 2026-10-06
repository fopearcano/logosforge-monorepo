import type {
  KnowledgeGraphEdgeDTO,
  KnowledgeGraphNodeDTO,
  KnowledgeGraphReadDTO,
  KnowledgeGraphViewMode,
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

function placeGrid(
  nodes: readonly KnowledgeGraphNodeDTO[],
  positions: Map<string, GraphPosition>,
  bounds: { left: number; right: number; top: number; bottom: number },
): void {
  if (nodes.length === 0) return;
  const width = Math.max(1, bounds.right - bounds.left);
  const height = Math.max(1, bounds.bottom - bounds.top);
  const maxColumns = Math.max(1, Math.floor(width / 80) + 1);
  const maxRows = Math.max(1, Math.floor(height / 76) + 1);
  const preferredColumns = Math.ceil(Math.sqrt(nodes.length * Math.max(0.65, width / height)));
  const columns = Math.min(maxColumns, Math.max(1, preferredColumns, Math.ceil(nodes.length / maxRows)));
  const rows = Math.ceil(nodes.length / columns);
  const columnGap = columns === 1 ? 0 : width / (columns - 1);
  const rowGap = rows === 1 ? 0 : height / (rows - 1);
  nodes.forEach((node, index) => {
    const row = Math.floor(index / columns);
    const column = index % columns;
    const rowSize = Math.min(columns, nodes.length - row * columns);
    const rowWidth = Math.max(0, rowSize - 1) * columnGap;
    const rowStart = (bounds.left + bounds.right - rowWidth) / 2;
    positions.set(node.key, {
      x: rowStart + column * columnGap,
      y: rows === 1 ? (bounds.top + bounds.bottom) / 2 : bounds.top + row * rowGap,
    });
  });
}

function layoutStructure(
  nodes: readonly KnowledgeGraphNodeDTO[],
  edges: readonly KnowledgeGraphEdgeDTO[],
  width: number,
  height: number,
): Map<string, GraphPosition> {
  const rank: Record<string, number> = {
    project: 0,
    act: 1,
    chapter: 2,
    plot_block: 2,
    timeline_event: 3,
    scene: 3,
  };
  const nodeKeys = new Set(nodes.map((node) => node.key));
  const parentByChild = new Map<string, string>();
  for (const edge of [...edges].sort((left, right) => graphEdgeKey(left).localeCompare(graphEdgeKey(right)))) {
    if (!nodeKeys.has(edge.source) || !nodeKeys.has(edge.target)) continue;
    const parent = edge.edge_type === "contains"
      ? edge.source
      : edge.edge_type === "belongs_to"
        ? edge.target
        : null;
    const child = edge.edge_type === "contains"
      ? edge.target
      : edge.edge_type === "belongs_to"
        ? edge.source
        : null;
    if (parent && child && !parentByChild.has(child)) parentByChild.set(child, parent);
  }
  const hierarchyPath = (key: string): string => {
    const path = [key];
    const seen = new Set(path);
    let parent = parentByChild.get(key);
    while (parent && !seen.has(parent)) {
      path.unshift(parent);
      seen.add(parent);
      parent = parentByChild.get(parent);
    }
    return path.join("\u0000");
  };
  const sceneKeys = nodes.filter((node) => node.node_type === "scene").map((node) => node.key).sort();
  const sceneSet = new Set(sceneKeys);
  const nextScenes = new Map(sceneKeys.map((key) => [key, new Set<string>()]));
  const indegree = new Map(sceneKeys.map((key) => [key, 0]));
  for (const edge of edges) {
    const before = edge.edge_type === "precedes" ? edge.source : edge.edge_type === "follows" ? edge.target : null;
    const after = edge.edge_type === "precedes" ? edge.target : edge.edge_type === "follows" ? edge.source : null;
    if (!before || !after || before === after || !sceneSet.has(before) || !sceneSet.has(after)) continue;
    const targets = nextScenes.get(before)!;
    if (!targets.has(after)) {
      targets.add(after);
      indegree.set(after, (indegree.get(after) ?? 0) + 1);
    }
  }
  const available = sceneKeys.filter((key) => indegree.get(key) === 0);
  const sceneOrder: string[] = [];
  while (available.length > 0) {
    available.sort((left, right) => hierarchyPath(left).localeCompare(hierarchyPath(right)) || left.localeCompare(right));
    const key = available.shift()!;
    sceneOrder.push(key);
    for (const target of [...(nextScenes.get(key) ?? [])].sort()) {
      const nextDegree = (indegree.get(target) ?? 0) - 1;
      indegree.set(target, nextDegree);
      if (nextDegree === 0) available.push(target);
    }
  }
  for (const key of sceneKeys) if (!sceneOrder.includes(key)) sceneOrder.push(key);
  const sceneIndex = new Map(sceneOrder.map((key, index) => [key, index]));
  const ordered = [...nodes].sort((left, right) => (
    (rank[left.node_type] ?? 4) - (rank[right.node_type] ?? 4)
    || (left.node_type === "scene" && right.node_type === "scene"
      ? (sceneIndex.get(left.key) ?? Number.MAX_SAFE_INTEGER) - (sceneIndex.get(right.key) ?? Number.MAX_SAFE_INTEGER)
      : 0)
    || hierarchyPath(left.key).localeCompare(hierarchyPath(right.key))
    || left.node_type.localeCompare(right.node_type)
    || right.degree - left.degree
    || left.key.localeCompare(right.key)
  ));
  const maxColumns = Math.max(1, Math.floor((width - 100) / 88));
  const rows: KnowledgeGraphNodeDTO[][] = [];
  let cursor = 0;
  while (cursor < ordered.length) {
    const currentRank = rank[ordered[cursor]!.node_type] ?? 4;
    const layer: KnowledgeGraphNodeDTO[] = [];
    while (cursor < ordered.length && (rank[ordered[cursor]!.node_type] ?? 4) === currentRank) {
      layer.push(ordered[cursor]!);
      cursor += 1;
    }
    for (let index = 0; index < layer.length; index += maxColumns) {
      rows.push(layer.slice(index, index + maxColumns));
    }
  }
  const positions = new Map<string, GraphPosition>();
  const top = 48;
  const bottom = height - 68;
  const maxSafeRows = Math.max(1, Math.floor((bottom - top) / 76) + 1);
  if (rows.length > maxSafeRows) {
    placeGrid(ordered, positions, { left: 60, right: width - 60, top, bottom });
    return positions;
  }
  rows.forEach((row, rowIndex) => {
    const y = rows.length === 1 ? height / 2 : top + ((bottom - top) * rowIndex) / Math.max(1, rows.length - 1);
    const gap = row.length === 1 ? 0 : Math.min(100, (width - 120) / (row.length - 1));
    const rowWidth = gap * Math.max(0, row.length - 1);
    const start = width / 2 - rowWidth / 2;
    row.forEach((node, column) => positions.set(node.key, { x: start + column * gap, y }));
  });
  return positions;
}

function layoutEvidenceHubs(
  nodes: readonly KnowledgeGraphNodeDTO[],
  edges: readonly KnowledgeGraphEdgeDTO[],
  width: number,
  height: number,
  viewMode: KnowledgeGraphViewMode,
): Map<string, GraphPosition> {
  const nodeByKey = new Map(nodes.map((node) => [node.key, node]));
  const anchorKeys = new Set<string>();
  for (const edge of edges) {
    if (nodeByKey.has(edge.source)) anchorKeys.add(edge.source);
  }
  for (const node of nodes) {
    if (
      node.node_type === "revision_impact"
      || (viewMode === "recorded_risk" && node.node_type === "controlled_apply_operation")
    ) anchorKeys.add(node.key);
  }
  const byIdentity = (left: KnowledgeGraphNodeDTO, right: KnowledgeGraphNodeDTO) => (
    left.node_type.localeCompare(right.node_type)
    || right.degree - left.degree
    || left.key.localeCompare(right.key)
  );
  const anchors = nodes.filter((node) => anchorKeys.has(node.key)).sort(byIdentity);
  const targets = nodes.filter((node) => !anchorKeys.has(node.key)).sort(byIdentity);
  if (anchors.length === 0 || targets.length === 0) {
    return layoutKnowledgeGraph(nodes, width, height, "project_map", edges);
  }
  const positions = new Map<string, GraphPosition>();
  const anchorBounds = { left: 68, right: width * 0.43, top: 58, bottom: height - 76 };
  const targetBounds = { left: width * 0.57, right: width - 68, top: 42, bottom: height - 60 };
  const capacity = (bounds: { left: number; right: number; top: number; bottom: number }) => (
    (Math.floor((bounds.right - bounds.left) / 80) + 1)
    * (Math.floor((bounds.bottom - bounds.top) / 76) + 1)
  );
  if (anchors.length > capacity(anchorBounds) || targets.length > capacity(targetBounds)) {
    return layoutKnowledgeGraph(nodes, width, height, "project_map", edges);
  }
  placeGrid(anchors, positions, anchorBounds);
  placeGrid(targets, positions, targetBounds);
  return positions;
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
  viewMode: KnowledgeGraphViewMode = "project_map",
  edges: readonly KnowledgeGraphEdgeDTO[] = [],
): Map<string, GraphPosition> {
  if (viewMode === "structure") return layoutStructure(nodes, edges, width, height);
  if (viewMode === "recorded_risk" || viewMode === "revision_impact") {
    return layoutEvidenceHubs(nodes, edges, width, height, viewMode);
  }
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
