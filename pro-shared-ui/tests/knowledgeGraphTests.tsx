import { MessagePort } from "node:worker_threads";
import { act, create, type ReactTestInstance, type ReactTestRenderer } from "react-test-renderer";
import type {
  EventMessage,
  KnowledgeGraphEdgeDTO,
  KnowledgeGraphQueryDTO,
  KnowledgeGraphReadDTO,
} from "@logosforge/ui-contracts";
import type { ApiClient } from "../src/adapters/api";
import { useSelection } from "../src/adapters/selection";
import { StudioProvider } from "../src/adapters/StudioProvider";
import { createHttpApiClient } from "../src/adapters/httpApiClient";
import { validateKnowledgeGraphReadDTOForRequest } from "../src/adapters/runtimeDtoValidation";
import { KnowledgeGraph } from "../src/components/spatialcanvas/KnowledgeGraph";
import {
  buildKnowledgeGraphView,
  layoutKnowledgeGraph,
} from "../src/components/spatialcanvas/knowledgeGraphModel";
import { useKnowledgeGraph } from "../src/hooks/resources";
import type { PlatformAdapter } from "../src/adapters/platform";

let assertions = 0;
function check(value: unknown, message: string): asserts value {
  assertions += 1;
  if (!value) throw new Error(message);
}

function text(node: ReactTestInstance): string {
  return node.children.map((child) => typeof child === "string" ? child : text(child)).join("");
}

interface Deferred<T> {
  promise: Promise<T>;
  resolve(value: T): void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((next) => { resolve = next; });
  return { promise, resolve };
}

const confirmedEdge: KnowledgeGraphEdgeDTO = {
  source: "project:project:7",
  target: "scene:scene:2",
  edge_type: "contains",
  confidence: "confirmed",
  provenance: "project structure",
  source_system: "structure",
  explanation: "The Scene belongs to this project.",
  is_user_confirmed: true,
  is_inferred: false,
  metadata: {},
};

const inferredEdge: KnowledgeGraphEdgeDTO = {
  source: "scene:scene:2",
  target: "character:psyke:3",
  edge_type: "mentions",
  confidence: "possible",
  provenance: "scene text match",
  source_system: "manuscript",
  explanation: "The character name appears in the Scene.",
  is_user_confirmed: false,
  is_inferred: true,
  metadata: {},
};

function graphFixture(
  projectId = 7,
  query: KnowledgeGraphQueryDTO = {},
  overrides: Partial<KnowledgeGraphReadDTO> = {},
): KnowledgeGraphReadDTO {
  const projectKey = `project:project:${projectId}`;
  const remap = (edge: KnowledgeGraphEdgeDTO): KnowledgeGraphEdgeDTO => ({
    ...edge,
    source: edge.source.startsWith("project:project:") ? projectKey : edge.source,
  });
  const includeInferred = query.include_inferred ?? true;
  const edges = [remap(confirmedEdge), remap(inferredEdge)].filter((edge) => includeInferred || !edge.is_inferred);
  const nodes = [
    { key: projectKey, node_type: "project", source_type: "project", source_id: String(projectId), label: `Project ${projectId}`, summary: "", metadata: {}, degree: 1 },
    { key: "scene:scene:2", node_type: "scene", source_type: "scene", source_id: "2", label: "Scene One", summary: "An opening signal.", metadata: {}, degree: includeInferred ? 2 : 1 },
    { key: "character:psyke:3", node_type: "character", source_type: "psyke", source_id: "3", label: "Marlow", summary: "A reluctant observer.", metadata: {}, degree: includeInferred ? 1 : 0 },
    { key: "theme:psyke:9", node_type: "theme", source_type: "psyke", source_id: "9", label: "Static", summary: "An isolated motif.", metadata: {}, degree: 0 },
  ];
  const focusKey = query.focus_key ?? null;
  return {
    project_id: projectId,
    writing_mode: "novel",
    focus_key: focusKey,
    depth: query.depth ?? 1,
    include_inferred: includeInferred,
    nodes,
    edges,
    node_count: nodes.length,
    edge_count: edges.length,
    returned_node_count: nodes.length,
    returned_edge_count: edges.length,
    truncated: false,
    orphan_keys: ["theme:psyke:9"],
    orphan_count: 1,
    weak_links: includeInferred ? [remap(inferredEdge)] : [],
    weak_link_count: includeInferred ? 1 : 0,
    warnings: [],
    unavailable: [],
    ...overrides,
  };
}

function diagnosticFixture(projectId: number, query: KnowledgeGraphQueryDTO): KnowledgeGraphReadDTO {
  const centerKey = "scene:scene:100";
  const connected = Array.from({ length: 14 }, (_, index) => ({
    key: `character:psyke:${index + 1}`,
    node_type: "character",
    source_type: "psyke",
    source_id: String(index + 1),
    label: `Connected character ${index + 1}`,
    summary: `Connection target ${index + 1}`,
    metadata: {},
    degree: 1,
  }));
  const orphans = Array.from({ length: 10 }, (_, index) => ({
    key: `theme:psyke:${index + 101}`,
    node_type: "theme",
    source_type: "psyke",
    source_id: String(index + 101),
    label: `Orphan theme ${index + 1}`,
    summary: "",
    metadata: {},
    degree: 0,
  }));
  const nodes = [
    { key: centerKey, node_type: "scene", source_type: "scene", source_id: "100", label: "Connection hub", summary: "A highly connected scene.", metadata: {}, degree: connected.length },
    ...connected,
    ...orphans,
  ];
  const edges: KnowledgeGraphEdgeDTO[] = connected.map((node, index) => ({
    source: centerKey,
    target: node.key,
    edge_type: "mentions",
    confidence: "possible",
    provenance: `diagnostic source ${index + 1}`,
    source_system: "manuscript",
    explanation: `Diagnostic explanation ${index + 1}.`,
    is_user_confirmed: false,
    is_inferred: true,
    metadata: {},
  }));
  return {
    project_id: projectId,
    writing_mode: "novel",
    focus_key: query.focus_key ?? null,
    depth: query.depth ?? 1,
    include_inferred: query.include_inferred ?? true,
    nodes,
    edges,
    node_count: nodes.length,
    edge_count: edges.length,
    returned_node_count: nodes.length,
    returned_edge_count: edges.length,
    truncated: false,
    orphan_keys: orphans.map((node) => node.key),
    orphan_count: orphans.length,
    weak_links: edges,
    weak_link_count: edges.length,
    warnings: [],
    unavailable: [],
  };
}

const valid = graphFixture(7, { depth: 2, limit: 20, include_inferred: true });
check(
  validateKnowledgeGraphReadDTOForRequest(valid, 7, { depth: 2, limit: 20, include_inferred: true }).nodes.length === 4,
  "runtime validation must accept a coherent bounded graph response",
);
let validationMessage = "";
try {
  validateKnowledgeGraphReadDTOForRequest({ ...valid, project_id: 8 }, 7, { depth: 2, limit: 20, include_inferred: true });
} catch (error) {
  validationMessage = error instanceof Error ? error.message : String(error);
}
check(validationMessage.includes("$.project_id"), "runtime validation must bind a graph response to the requested project");
validationMessage = "";
try {
  validateKnowledgeGraphReadDTOForRequest({
    ...valid,
    weak_links: [{ ...inferredEdge, target: "character:psyke:missing" }],
  }, 7, { depth: 2, limit: 20, include_inferred: true });
} catch (error) {
  validationMessage = error instanceof Error ? error.message : String(error);
}
check(validationMessage.includes("$.weak_links[0].target"), "runtime validation must reject weak links whose endpoint was not returned");
validationMessage = "";
try {
  validateKnowledgeGraphReadDTOForRequest({ ...valid, returned_node_count: 99 }, 7, { depth: 2, limit: 20, include_inferred: true });
} catch (error) {
  validationMessage = error instanceof Error ? error.message : String(error);
}
check(validationMessage.includes("$.returned_node_count"), "runtime validation must bind returned counts to the actual arrays");

const independentlyCappedDiagnostics: KnowledgeGraphReadDTO = {
  ...valid,
  edges: [valid.edges[0]!],
  edge_count: 1,
  returned_edge_count: 1,
  weak_links: [inferredEdge],
  weak_link_count: 2,
  truncated: true,
};
check(
  validateKnowledgeGraphReadDTOForRequest(
    independentlyCappedDiagnostics,
    7,
    { depth: 2, limit: 20, include_inferred: true },
  ).weak_links.length === 1,
  "runtime validation must accept independently bounded weak-link diagnostics and their truncation state",
);
validationMessage = "";
try {
  const excessiveWeakLinks = Array.from({ length: 26 }, (_, index) => ({
    ...inferredEdge,
    edge_type: `weak-${index}`,
  }));
  validateKnowledgeGraphReadDTOForRequest({
    ...valid,
    weak_links: excessiveWeakLinks,
    weak_link_count: excessiveWeakLinks.length,
  }, 7, { depth: 2, limit: 100, include_inferred: true });
} catch (error) {
  validationMessage = error instanceof Error ? error.message : String(error);
}
check(validationMessage.includes("$.weak_links"), "runtime validation must enforce the Core weak-link diagnostic cap of 25");

const filtered = buildKnowledgeGraphView(valid, {
  hiddenNodeTypes: new Set(["character"]),
  confidenceMin: "likely",
  sourceSystem: "structure",
});
check(filtered.nodes.length === 3, "node-type filters must remove only the selected canonical type");
check(filtered.edges.length === 1 && filtered.edges[0]?.edge_type === "contains", "confidence and source filters must compose over edges");
check(filtered.orphanNodes.map((node) => node.key).join() === "theme:psyke:9", "orphan cards must use server-provided keys, not filtered degree");
check(filtered.weakLinks.length === 0, "weak-link cards must honor active confidence and source filters");
const firstLayout = layoutKnowledgeGraph(valid.nodes);
const secondLayout = layoutKnowledgeGraph([...valid.nodes].reverse());
check(
  [...firstLayout].every(([key, position]) => JSON.stringify(position) === JSON.stringify(secondLayout.get(key))),
  "graph layout must be deterministic regardless of response insertion order",
);
const denseNodes = Array.from({ length: 48 }, (_, index) => ({
  ...valid.nodes[index % valid.nodes.length]!,
  key: `dense:${index.toString().padStart(2, "0")}`,
  label: `Dense node ${index + 1}`,
  degree: index % 9,
}));
const denseLayout = layoutKnowledgeGraph(denseNodes);
const densePositions = [...denseLayout.values()];
check(
  densePositions.every(({ x, y }) => x >= 0 && x <= 900 && y >= 0 && y <= 560),
  "dense graph layout must keep every interaction target inside the bounded canvas",
);
check(
  densePositions.every((left, index) => densePositions.slice(index + 1).every((right) => (
    Math.abs(left.x - right.x) >= 80 || Math.abs(left.y - right.y) >= 76
  ))),
  "the 48-node interaction-safe page must not overlap its 80 by 76 pixel node hit areas",
);

const originalFetch = globalThis.fetch;
try {
  let requestedUrl = "";
  globalThis.fetch = async (input) => {
    requestedUrl = String(input);
    return new Response(JSON.stringify(graphFixture(7, {
      focus_key: "scene:scene:2", depth: 2, limit: 99, include_inferred: true,
    })), { status: 200, headers: { "content-type": "application/json" } });
  };
  const http = createHttpApiClient("");
  const response = await http.getKnowledgeGraph(7, {
    focus_key: "scene:scene:2", depth: 2, limit: 99, include_inferred: true,
  });
  check(
    requestedUrl === "/api/projects/7/knowledge-graph?focus_key=scene%3Ascene%3A2&depth=2&limit=99&include_inferred=true",
    `HTTP graph query must preserve and encode every bounded read option: ${requestedUrl}`,
  );
  check(response.focus_key === "scene:scene:2" && response.depth === 2, "HTTP graph reads must validate and return the requested neighborhood");
} finally {
  globalThis.fetch = originalFetch;
}

const platform: PlatformAdapter = {
  isDesktop: false,
  openFile: async () => ({ canceled: true }),
  saveFile: async () => ({ canceled: true }),
  openExternal: async () => undefined,
};

const pending = new Map<string, Deferred<KnowledgeGraphReadDTO>>();
const pendingKey = (projectId: number, query: KnowledgeGraphQueryDTO) => `${projectId}:${query.focus_key ?? "map"}`;
const hookApi = {
  getKnowledgeGraph: (projectId: number, query: KnowledgeGraphQueryDTO) => {
    const wait = deferred<KnowledgeGraphReadDTO>();
    pending.set(pendingKey(projectId, query), wait);
    return wait.promise;
  },
  subscribe: () => () => {},
} as unknown as ApiClient;

function GraphResourceProbe({ query }: { query: KnowledgeGraphQueryDTO }) {
  const result = useKnowledgeGraph(query);
  return <output data-project={result.data?.project_id ?? ""} data-focus={result.data?.focus_key ?? ""} data-loading={String(result.loading)}>{result.data?.nodes[0]?.label ?? ""}</output>;
}

function resourceTree(projectId: number, query: KnowledgeGraphQueryDTO) {
  return <StudioProvider services={{ api: hookApi, platform }} projectId={projectId}><GraphResourceProbe query={query} /></StudioProvider>;
}

const queryA = { focus_key: "scene:scene:2", depth: 1, limit: 10, include_inferred: true };
const queryB = { focus_key: "character:psyke:3", depth: 1, limit: 10, include_inferred: true };
let hookRenderer!: ReactTestRenderer;
await act(async () => {
  hookRenderer = create(resourceTree(7, queryA));
  await Promise.resolve();
});
await act(async () => {
  hookRenderer.update(resourceTree(8, queryB));
  await Promise.resolve();
});
await act(async () => {
  pending.get("7:scene:scene:2")?.resolve(graphFixture(7, queryA));
  await Promise.resolve();
  await Promise.resolve();
});
check(hookRenderer.root.findByType("output").props["data-project"] === "", "a delayed old-project graph response must never repopulate the new workspace");
await act(async () => {
  pending.get("8:character:psyke:3")?.resolve(graphFixture(8, queryB));
  await Promise.resolve();
  await Promise.resolve();
});
check(hookRenderer.root.findByType("output").props["data-project"] === 8, "the current project graph response must become visible");

await act(async () => {
  hookRenderer.update(resourceTree(8, queryA));
  await Promise.resolve();
});
await act(async () => {
  hookRenderer.update(resourceTree(8, queryB));
  await Promise.resolve();
});
await act(async () => {
  pending.get("8:scene:scene:2")?.resolve(graphFixture(8, queryA));
  await Promise.resolve();
  await Promise.resolve();
});
check(hookRenderer.root.findByType("output").props["data-focus"] !== "scene:scene:2", "a delayed superseded focus response must remain invisible");
await act(async () => {
  pending.get("8:character:psyke:3")?.resolve(graphFixture(8, queryB));
  await Promise.resolve();
  await Promise.resolve();
});
check(hookRenderer.root.findByType("output").props["data-focus"] === "character:psyke:3", "the latest focus response must win");
act(() => hookRenderer.unmount());

const liveRequests: Array<Deferred<KnowledgeGraphReadDTO>> = [];
let liveListener: ((event: EventMessage) => void) | undefined;
let readInvalidations = 0;
const liveApi = {
  getKnowledgeGraph: () => {
    const request = deferred<KnowledgeGraphReadDTO>();
    liveRequests.push(request);
    return request.promise;
  },
  invalidatePendingReads: () => { readInvalidations += 1; },
  subscribe: (_projectId: number, listener: (event: EventMessage) => void) => {
    liveListener = listener;
    return () => { liveListener = undefined; };
  },
} as unknown as ApiClient;
await act(async () => {
  hookRenderer = create(<StudioProvider services={{ api: liveApi, platform }} projectId={7}><GraphResourceProbe query={{}} /></StudioProvider>);
  await Promise.resolve();
});
check(liveRequests.length === 1, "graph resource must begin with one canonical read");
act(() => liveListener?.({ id: 1, event: "scene_changed", project_id: 7, data: { scene_id: 2 }, ts: Date.now() }));
await act(async () => {
  await new Promise((resolve) => setTimeout(resolve, 140));
  await Promise.resolve();
});
check(readInvalidations === 1 && liveRequests.length === 2, "a live graph event must invalidate pending GET coalescing before refetching");
await act(async () => {
  const stale = graphFixture(7);
  stale.nodes = stale.nodes.map((node, index) => index === 0 ? { ...node, label: "STALE GRAPH" } : node);
  liveRequests[0]!.resolve(stale);
  await Promise.resolve();
  await Promise.resolve();
});
check(!text(hookRenderer.root.findByType("output")).includes("STALE GRAPH"), "a pre-event graph response must not publish into the post-event generation");
await act(async () => {
  const fresh = graphFixture(7);
  fresh.nodes = fresh.nodes.map((node, index) => index === 0 ? { ...node, label: "FRESH GRAPH" } : node);
  liveRequests[1]!.resolve(fresh);
  await Promise.resolve();
  await Promise.resolve();
});
check(text(hookRenderer.root.findByType("output")).includes("FRESH GRAPH"), "the force-fresh post-event graph response must publish");
act(() => hookRenderer.unmount());

const graphRequests: Array<{ projectId: number; query: KnowledgeGraphQueryDTO }> = [];
const listeners = new Set<(event: EventMessage) => void>();
const panelApi = {
  getKnowledgeGraph: async (projectId: number, query: KnowledgeGraphQueryDTO) => {
    graphRequests.push({ projectId, query: { ...query } });
    const base = graphFixture(projectId, query);
    return query.focus_key ? base : {
      ...base,
      node_count: 9,
      edge_count: 5,
      truncated: true,
      orphan_count: 3,
      weak_link_count: 2,
      warnings: ["One optional extractor was unavailable."],
      unavailable: ["rewrite_sandbox"],
    };
  },
  subscribe: (_projectId: number, listener: (event: EventMessage) => void) => {
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  },
} as unknown as ApiClient;

function SelectionProbe() {
  const { selection } = useSelection();
  return <output data-section={selection.section ?? ""} data-node={selection.nodeId ?? ""} data-scene={selection.sceneId ?? ""}>{selection.text}</output>;
}

function panelTree(projectId: number, api: ApiClient = panelApi) {
  return <StudioProvider services={{ api, platform }} projectId={projectId}><KnowledgeGraph /><SelectionProbe /></StudioProvider>;
}

async function flush() {
  for (let index = 0; index < 8; index += 1) await Promise.resolve();
}

let panelRenderer!: ReactTestRenderer;
await act(async () => {
  panelRenderer = create(panelTree(7));
  await flush();
});
check(panelRenderer.root.findByProps({ "data-knowledge-graph-canvas": "true" }).props["data-project-id"] === 7, "Project Map must render the active project's canonical response");
check(text(panelRenderer.root.findByProps({ role: "status" })).includes("SIZE CAP"), "truncated graph responses must announce the size cap");
check(text(panelRenderer.root.findByProps({ role: "status" })).includes("DIAGNOSTIC CAP · Core returned 1 of 3 orphan keys and 1 of 2 weak links"), "diagnostic-only caps must announce Core-returned and query-total orphan and weak-link counts");
check(panelRenderer.root.findByProps({ "aria-label": "Narrative Knowledge Graph canvas" }), "graph canvas must have an accessible landmark name");
const scrollRegion = panelRenderer.root.findByProps({ "data-knowledge-graph-scroll-region": "true" });
check(scrollRegion.props.tabIndex === 0 && scrollRegion.props.style.overflowX === "auto", "narrow docks must expose a keyboard-reachable horizontal workspace instead of clipping fixed rails");
check(panelRenderer.root.findByType("svg").props["aria-hidden"] === "true", "graph SVG geometry must be decorative to assistive technology");
check(panelRenderer.root.findByProps({ "aria-label": "Minimum edge confidence" }), "confidence filter must have a stable accessible name");
check(panelRenderer.root.findByProps({ "aria-label": "Edge source system" }), "source-system filter must have a stable accessible name");
check(panelRenderer.root.findByProps({ "aria-label": "Select Scene One, Scene, 2 connections" }).props["aria-pressed"] === true, "nodes must expose a named keyboard button and non-color selected state");

act(() => panelRenderer.root.findByProps({ "aria-label": "Select Scene One, Scene, 2 connections" }).props.onClick());
const panelSelection = panelRenderer.root.findAllByType("output").at(-1)!;
check(panelSelection.props["data-section"] === "Knowledge Graph" && panelSelection.props["data-node"] === "scene:scene:2" && panelSelection.props["data-scene"] === 2, "node selection must publish graph and Scene context to Studio tools");
check(panelRenderer.root.findByProps({ "aria-label": "Select Scene One, Scene, 2 connections" }).props["aria-pressed"] === true, "selected graph nodes must expose aria-pressed");
const inspectedConnections = panelRenderer.root.findAllByProps({ "data-graph-connection": "true" });
check(inspectedConnections.length === 2, "the selected-node inspector must expose every returned visible connection");
const outgoingConnectionText = inspectedConnections.map(text).find((value) => value.includes("OUTGOING TO")) ?? "";
check(
  outgoingConnectionText.includes("TYPE · mentions")
    && outgoingConnectionText.includes("CONFIDENCE · possible")
    && outgoingConnectionText.includes("SOURCE SYSTEM · manuscript")
    && outgoingConnectionText.includes("PROVENANCE · scene text match")
    && outgoingConnectionText.includes("EXPLANATION · The character name appears in the Scene."),
  "connection inspection must expose direction, type, confidence, source system, provenance, and explanation as DOM text",
);

const initialLines = panelRenderer.root.findAllByType("line").length;
act(() => panelRenderer.root.findByProps({ "aria-label": "Minimum edge confidence" }).props.onChange({ currentTarget: { value: "likely" } }));
check(panelRenderer.root.findAllByType("line").length === initialLines - 1, "confidence controls must actually filter weaker edges");
act(() => panelRenderer.root.findByProps({ "aria-label": "Edge source system" }).props.onChange({ currentTarget: { value: "manuscript" } }));
check(panelRenderer.root.findAllByType("line").length === 0, "source controls must compose with confidence filters rather than act as inert labels");
act(() => panelRenderer.root.findByProps({ "aria-label": "Minimum edge confidence" }).props.onChange({ currentTarget: { value: "unknown" } }));
check(panelRenderer.root.findAllByType("line").length === 1, "lowering confidence must restore matching source edges");

act(() => panelRenderer.root.findAllByProps({ "aria-label": "Focus graph on Scene One" })[0]!.props.onClick());
await act(async () => { await flush(); });
check(graphRequests.at(-1)?.query.focus_key === "scene:scene:2", "focus action must request the selected canonical node neighborhood");
check(panelRenderer.root.findByProps({ "data-knowledge-graph-canvas": "true" }).props["data-focus-key"] === "scene:scene:2", "focused response must replace the Project Map only after it arrives");
check(panelRenderer.root.findByProps({ "aria-label": "Return to full Project Map" }), "focused mode must provide an accessible route back to the Project Map");
check(panelRenderer.root.findAllByProps({ "aria-label": "Focus graph on Scene One" }).length === 0 && text(panelRenderer.root).includes("FOCUS ROOT"), "a selected focus root must expose status instead of an inert same-focus action");

await act(async () => {
  panelRenderer.update(panelTree(8));
  await flush();
});
check(panelRenderer.root.findByProps({ "data-knowledge-graph-canvas": "true" }).props["data-project-id"] === 8, "project switching must clear and replace the prior graph");
const switchedSelection = panelRenderer.root.findAllByType("output").at(-1)!;
check(switchedSelection.props["data-node"] === "", "project switching must clear graph selection context");
act(() => panelRenderer.unmount());
check(listeners.size === 0, "unmount must release Knowledge Graph live-event subscriptions");

const diagnosticApi = {
  getKnowledgeGraph: async (projectId: number, query: KnowledgeGraphQueryDTO) => diagnosticFixture(projectId, query),
  subscribe: () => () => {},
} as unknown as ApiClient;
await act(async () => {
  panelRenderer = create(panelTree(7, diagnosticApi));
  await flush();
});
check(panelRenderer.root.findAllByProps({ "data-graph-connection": "true" }).length === 12, "long connection lists must report and initially render their 12-item preview cap");
check(text(panelRenderer.root).includes("VISIBLE CONNECTIONS · SHOWING 12 OF 14"), "connection preview headings must state the exact displayed and available counts");
act(() => panelRenderer.root.findByProps({ "aria-label": "Show all 14 visible connections" }).props.onClick());
check(panelRenderer.root.findAllByProps({ "data-graph-connection": "true" }).length === 14, "connection expansion must make every returned selected-node connection reachable");

check(text(panelRenderer.root).includes("ORPHANS · SHOWING 8 OF 10 MATCHING · 10 CORE RETURNED · 10 QUERY TOTAL"), "orphan diagnostics must report preview, post-filter match, Core-returned, and query-total counts separately");
act(() => panelRenderer.root.findByProps({ "aria-label": "Show all 10 matching orphan nodes" }).props.onClick());
check(panelRenderer.root.findAll((node) => typeof node.props["aria-label"] === "string" && node.props["aria-label"].startsWith("Select orphan node ")).length === 10, "orphan expansion must make every matching returned orphan reachable");

check(text(panelRenderer.root).includes("WEAK LINKS · SHOWING 8 OF 14 MATCHING · 14 CORE RETURNED · 14 QUERY TOTAL"), "weak-link diagnostics must report preview, post-filter match, Core-returned, and query-total counts separately");
act(() => panelRenderer.root.findByProps({ "aria-label": "Show all 14 matching weak links" }).props.onClick());
const expandedWeakLinks = panelRenderer.root.findAll((node) => typeof node.props["aria-label"] === "string" && node.props["aria-label"].startsWith("Weak link from "));
check(expandedWeakLinks.length === 14, "weak-link expansion must make every matching returned diagnostic reachable");
check(text(expandedWeakLinks[0]!).includes("PROVENANCE · diagnostic source 1") && text(expandedWeakLinks[0]!).includes("EXPLANATION · Diagnostic explanation 1."), "weak-link cards must expose traceable provenance and explanation as DOM text");
act(() => panelRenderer.unmount());

const loadingGraph = deferred<KnowledgeGraphReadDTO>();
const loadingApi = {
  getKnowledgeGraph: async () => loadingGraph.promise,
  subscribe: () => () => {},
} as unknown as ApiClient;
let stateRenderer!: ReactTestRenderer;
await act(async () => {
  stateRenderer = create(panelTree(7, loadingApi));
  await Promise.resolve();
});
check(text(stateRenderer.root.findByProps({ role: "status" })).includes("Building the canonical Project Map"), "initial graph loading must be announced as a live status");
await act(async () => {
  loadingGraph.resolve(graphFixture(7, { focus_key: null, depth: 1, limit: 48, include_inferred: true }));
  await flush();
});
act(() => stateRenderer.unmount());

const emptyApi = {
  getKnowledgeGraph: async (projectId: number, query: KnowledgeGraphQueryDTO) => graphFixture(projectId, query, {
    nodes: [], edges: [], node_count: 0, edge_count: 0, returned_node_count: 0, returned_edge_count: 0,
    orphan_keys: [], orphan_count: 0, weak_links: [], weak_link_count: 0,
  }),
  subscribe: () => () => {},
} as unknown as ApiClient;
await act(async () => {
  stateRenderer = create(panelTree(7, emptyApi));
  await flush();
});
check(text(stateRenderer.root).includes("No narrative knowledge has been derived yet"), "empty graph state must explain how to populate the map");
act(() => stateRenderer.unmount());

let failLoads = true;
const errorApi = {
  getKnowledgeGraph: async (projectId: number, query: KnowledgeGraphQueryDTO) => {
    if (failLoads) throw new Error("core offline");
    return graphFixture(projectId, query);
  },
  subscribe: () => () => {},
} as unknown as ApiClient;
await act(async () => {
  stateRenderer = create(panelTree(7, errorApi));
  await flush();
});
check(text(stateRenderer.root.findByProps({ role: "alert" })).includes("core offline"), "graph load errors must be announced");
failLoads = false;
await act(async () => {
  stateRenderer.root.findAllByType("button").find((button) => text(button) === "RETRY LOAD")!.props.onClick();
  await flush();
});
check(stateRenderer.root.findByProps({ "data-knowledge-graph-canvas": "true" }), "graph retry must recover from a transient load error");
act(() => stateRenderer.unmount());

console.log(`${assertions} Knowledge Graph assertions passed.`);

for (const handle of process._getActiveHandles()) {
  if (handle instanceof MessagePort) handle.unref();
}
