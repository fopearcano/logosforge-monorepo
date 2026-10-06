import { MessagePort } from "node:worker_threads";
import { act, create, type ReactTestInstance, type ReactTestRenderer } from "react-test-renderer";
import type {
  EventMessage,
  KnowledgeGraphCommandDTO,
  KnowledgeGraphCommandResultDTO,
  KnowledgeGraphEdgeDTO,
  KnowledgeGraphQueryDTO,
  KnowledgeGraphReadDTO,
} from "@logosforge/ui-contracts";
import type { ApiClient } from "../src/adapters/api";
import { useSelection } from "../src/adapters/selection";
import { StudioProvider } from "../src/adapters/StudioProvider";
import { ApiRequestError, ApiRequestTimeoutError, createHttpApiClient } from "../src/adapters/httpApiClient";
import {
  validateKnowledgeGraphCommandReceiptDTOForRequest,
  validateKnowledgeGraphCommandResultDTOForRequest,
  validateKnowledgeGraphHiddenEdgePageDTOForRequest,
  validateKnowledgeGraphReadDTOForRequest,
} from "../src/adapters/runtimeDtoValidation";
import { KnowledgeGraph } from "../src/components/spatialcanvas/KnowledgeGraph";
import {
  buildKnowledgeGraphView,
  layoutKnowledgeGraph,
} from "../src/components/spatialcanvas/knowledgeGraphModel";
import { planKnowledgeGraphCommand } from "../src/components/spatialcanvas/knowledgeGraphTransactions";
import { useKnowledgeGraph } from "../src/hooks/resources";
import type { PlatformAdapter } from "../src/adapters/platform";

let assertions = 0;
const REVISION_A = "1".repeat(64);
const REVISION_B = "2".repeat(64);
const REVISION_C = "3".repeat(64);
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
  is_hidden: false,
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
  is_hidden: false,
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
    revision: REVISION_A,
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
    hidden_edges: [],
    hidden_edge_count: 0,
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
    is_hidden: false,
    metadata: {},
  }));
  return {
    project_id: projectId,
    revision: REVISION_A,
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
    hidden_edges: [],
    hidden_edge_count: 0,
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

const hiddenInferredEdge: KnowledgeGraphEdgeDTO = { ...inferredEdge, is_hidden: true };
const hiddenGraph = graphFixture(7, {}, {
  edges: [confirmedEdge],
  edge_count: 1,
  returned_edge_count: 1,
  weak_links: [],
  weak_link_count: 0,
  hidden_edges: [hiddenInferredEdge],
  hidden_edge_count: 1,
});
check(
  validateKnowledgeGraphReadDTOForRequest(hiddenGraph, 7).hidden_edges[0]?.is_hidden === true,
  "runtime validation must accept an endpoint-complete hidden-edge review collection",
);
const confirmPlan = planKnowledgeGraphCommand(valid, {
  kind: "confirm_edge",
  source: inferredEdge.source,
  target: inferredEdge.target,
  edge_type: inferredEdge.edge_type,
});
check(confirmPlan.command?.expected_revision === REVISION_A, "confirmation planning must bind the exact fresh review-layer revision");
check(
  planKnowledgeGraphCommand(valid, { kind: "hide_edge", source: confirmedEdge.source, target: confirmedEdge.target, edge_type: confirmedEdge.edge_type }).error?.includes("unconfirmed inferred") === true,
  "hiding must be rejected for explicit or already-confirmed edges to match Core eligibility",
);
check(
  planKnowledgeGraphCommand(hiddenGraph, { kind: "unhide_edge", source: hiddenInferredEdge.source, target: hiddenInferredEdge.target, edge_type: hiddenInferredEdge.edge_type }).command?.kind === "unhide_edge",
  "restore planning must target only the authoritative hidden-edge collection",
);
const command = confirmPlan.command!;
const concurrentResult: KnowledgeGraphCommandResultDTO = {
  knowledge_graph: graphFixture(7, {}, { revision: REVISION_C }),
  changed: true,
  affected_edge: { source: command.source, target: command.target, edge_type: command.edge_type },
  replayed: false,
  applied_revision: REVISION_B,
};
check(
  validateKnowledgeGraphCommandResultDTOForRequest(concurrentResult, 7, command).applied_revision === REVISION_B,
  "command validation must allow the returned map to advance after the command's truthful applied revision",
);
validationMessage = "";
try {
  validateKnowledgeGraphCommandResultDTOForRequest({
    ...concurrentResult,
    changed: false,
    applied_revision: command.expected_revision,
  }, 7, command);
} catch (error) {
  validationMessage = error instanceof Error ? error.message : String(error);
}
check(validationMessage.includes("$.changed"), "runtime validation must reject a fresh graph command response that falsely reports a no-op");
check(
  validateKnowledgeGraphCommandReceiptDTOForRequest({
    project_id: 7,
    request_digest: "a".repeat(64),
    command_kind: command.kind,
    expected_revision: command.expected_revision,
    applied_revision: REVISION_B,
    original_changed: true,
    original_affected_edge: { source: command.source, target: command.target, edge_type: command.edge_type },
    committed_at: "2026-10-06T10:00:00Z",
  }, 7, command).original_changed,
  "receipt validation must bind the project, command, edge identity, and changed revision",
);
check(
  validateKnowledgeGraphHiddenEdgePageDTOForRequest({
    project_id: 7,
    revision: REVISION_B,
    offset: 0,
    limit: 25,
    hidden_edge_count: 1,
    returned_edge_count: 1,
    nodes: valid.nodes.filter((node) => node.key === hiddenInferredEdge.source || node.key === hiddenInferredEdge.target),
    edges: [hiddenInferredEdge],
  }, 7, 0, 25).nodes.length === 2,
  "hidden-edge page validation must require a dense page with its exact endpoint-node set",
);
validationMessage = "";
try {
  validateKnowledgeGraphHiddenEdgePageDTOForRequest({
    project_id: 7,
    revision: REVISION_B,
    offset: 0,
    limit: 25,
    hidden_edge_count: 2,
    returned_edge_count: 1,
    nodes: valid.nodes.filter((node) => node.key === hiddenInferredEdge.source || node.key === hiddenInferredEdge.target),
    edges: [hiddenInferredEdge],
  }, 7, 0, 25);
} catch (error) {
  validationMessage = error instanceof Error ? error.message : String(error);
}
check(validationMessage.includes("$.edges"), "hidden-edge page validation must reject short middle pages that could strand later restore decisions");

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

try {
  const requests: Array<{ url: string; method: string; headers: Headers; body: string }> = [];
  globalThis.fetch = async (input, init) => {
    const url = String(input);
    requests.push({
      url,
      method: init?.method ?? "GET",
      headers: new Headers(init?.headers),
      body: typeof init?.body === "string" ? init.body : "",
    });
    if (url.includes("command-receipt")) {
      return new Response(JSON.stringify({
        project_id: 7,
        request_digest: "a".repeat(64),
        command_kind: command.kind,
        expected_revision: command.expected_revision,
        applied_revision: REVISION_B,
        original_changed: true,
        original_affected_edge: { source: command.source, target: command.target, edge_type: command.edge_type },
        committed_at: "2026-10-06T10:00:00Z",
      }), { status: 200, headers: { "content-type": "application/json" } });
    }
    if (url.includes("hidden-edges")) {
      return new Response(JSON.stringify({
        project_id: 7,
        revision: REVISION_B,
        offset: 0,
        limit: 25,
        hidden_edge_count: 1,
        returned_edge_count: 1,
        nodes: valid.nodes.filter((node) => node.key === hiddenInferredEdge.source || node.key === hiddenInferredEdge.target),
        edges: [hiddenInferredEdge],
      }), { status: 200, headers: { "content-type": "application/json" } });
    }
    return new Response(JSON.stringify(concurrentResult), { status: 200, headers: { "content-type": "application/json" } });
  };
  const http = createHttpApiClient("");
  await http.executeKnowledgeGraphCommand(7, command, "kg-ui-1234567890123456");
  await http.getKnowledgeGraphCommandReceipt(7, "kg-ui-1234567890123456", command);
  await http.getKnowledgeGraphHiddenEdges(7, 0, 25);
  check(requests[0]?.url === "/api/projects/7/knowledge-graph/commands" && requests[0]?.method === "POST", "graph commands must use the dedicated POST route");
  check(requests[0]?.headers.get("Idempotency-Key") === "kg-ui-1234567890123456" && !requests[0]?.url.includes("kg-ui"), "graph command capability keys must travel only in the Idempotency-Key header");
  check(requests[0]?.body === JSON.stringify(command), "graph command transport must preserve the exact revision-guarded command body");
  check(requests[1]?.headers.get("Idempotency-Key") === "kg-ui-1234567890123456" && requests[1]?.headers.get("Cache-Control") === "no-store", "receipt recovery must use the same header-only key and bypass caches");
  check(requests[2]?.url === "/api/projects/7/knowledge-graph/hidden-edges?offset=0&limit=25", "hidden restore review must use the complete paged queue route");
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
act(() => liveListener?.({ id: 1, event: "knowledge_graph_changed", project_id: 7, data: { source: inferredEdge.source, target: inferredEdge.target, edge_type: inferredEdge.edge_type }, ts: Date.now() }));
await act(async () => {
  await new Promise((resolve) => setTimeout(resolve, 140));
  await Promise.resolve();
});
check(readInvalidations === 1 && liveRequests.length === 2, "a knowledge_graph_changed event must invalidate pending GET coalescing before refetching");
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
check(text(panelRenderer.root.findByProps({ role: "status" })).includes("DIAGNOSTIC CAP · Core returned 1 of 3 orphan keys, 1 of 2 weak links, and 0 of 0 hidden edges"), "diagnostic-only caps must announce Core-returned and query-total orphan, weak-link, and hidden-edge counts");
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

let mutationConfirmed = false;
const submittedGraphCommands: Array<{ command: KnowledgeGraphCommandDTO; key: string }> = [];
const mutableConfirmationGraph = (projectId: number, query: KnowledgeGraphQueryDTO): KnowledgeGraphReadDTO => {
  const base = graphFixture(projectId, query);
  if (!mutationConfirmed) return base;
  const confirmedInference = { ...inferredEdge, is_user_confirmed: true, confidence: "confirmed" as const };
  return {
    ...base,
    revision: REVISION_B,
    edges: [base.edges[0]!, confirmedInference],
    weak_links: [confirmedInference],
  };
};
const mutationApi = {
  getKnowledgeGraph: async (projectId: number, query: KnowledgeGraphQueryDTO) => mutableConfirmationGraph(projectId, query),
  executeKnowledgeGraphCommand: async (projectId: number, nextCommand: KnowledgeGraphCommandDTO, key: string): Promise<KnowledgeGraphCommandResultDTO> => {
    submittedGraphCommands.push({ command: structuredClone(nextCommand), key });
    mutationConfirmed = true;
    return {
      knowledge_graph: mutableConfirmationGraph(projectId, {}),
      changed: true,
      affected_edge: { source: nextCommand.source, target: nextCommand.target, edge_type: nextCommand.edge_type },
      replayed: false,
      applied_revision: REVISION_B,
    };
  },
  getKnowledgeGraphCommandReceipt: async () => { throw new Error("receipt lookup should not run for a successful write"); },
  subscribe: () => () => {},
  invalidatePendingReads: () => {},
} as unknown as ApiClient;
await act(async () => {
  panelRenderer = create(panelTree(7, mutationApi));
  await flush();
});
const reviewConfirmButton = panelRenderer.root.findByProps({ "aria-label": "Review confirmation of Scene One to Marlow mentions edge" });
check(panelRenderer.root.findByProps({ "aria-label": "Review hiding Scene One to Marlow mentions edge" }), "eligible inferred edges must expose both confirm and hide review actions");
act(() => reviewConfirmButton.props.onClick({ currentTarget: reviewConfirmButton }));
const reviewDialog = panelRenderer.root.findByProps({ "data-knowledge-graph-edge-review": "confirm_edge" });
check(submittedGraphCommands.length === 0, "opening an edge review must not mutate graph state");
check(
  reviewDialog.props.role === "dialog"
    && text(reviewDialog).includes("Nothing changes until you apply this reviewed decision")
    && text(reviewDialog).includes("PROVENANCE · scene text match"),
  "edge review must expose a keyboard-focusable, traceable confirmation step before mutation",
);
await act(async () => {
  reviewDialog.findByProps({ "aria-label": "Apply reviewed confirm edge" }).props.onClick();
  await flush();
});
check(
  submittedGraphCommands.length === 1
    && submittedGraphCommands[0]?.command.kind === "confirm_edge"
    && submittedGraphCommands[0]?.command.expected_revision === REVISION_A
    && submittedGraphCommands[0]!.key.length >= 16,
  "confirmation must submit one fresh-revision command with a capability-sized Idempotency-Key",
);
check(text(panelRenderer.root).includes("Knowledge Graph edge decision saved"), "successful graph review must announce its committed outcome");
check(panelRenderer.root.findAllByProps({ "aria-label": "Review confirmation of Scene One to Marlow mentions edge" }).length === 0, "confirmed edges must stop offering an ineligible confirmation action after refresh");
act(() => panelRenderer.unmount());

let ambiguousAttempt = 0;
const ambiguousSubmissions: Array<{ command: KnowledgeGraphCommandDTO; key: string }> = [];
const ambiguousApi = {
  getKnowledgeGraph: async (projectId: number, query: KnowledgeGraphQueryDTO) => graphFixture(projectId, query, ambiguousAttempt >= 2 ? { revision: REVISION_B } : {}),
  executeKnowledgeGraphCommand: async (projectId: number, nextCommand: KnowledgeGraphCommandDTO, key: string): Promise<KnowledgeGraphCommandResultDTO> => {
    ambiguousAttempt += 1;
    ambiguousSubmissions.push({ command: structuredClone(nextCommand), key });
    if (ambiguousAttempt === 1) throw new ApiRequestTimeoutError("POST", `/api/projects/${projectId}/knowledge-graph/commands`, 50);
    return {
      knowledge_graph: graphFixture(projectId, {}, { revision: REVISION_B }),
      changed: true,
      affected_edge: { source: nextCommand.source, target: nextCommand.target, edge_type: nextCommand.edge_type },
      replayed: false,
      applied_revision: REVISION_B,
    };
  },
  getKnowledgeGraphCommandReceipt: async () => {
    throw new ApiRequestError("GET", "/api/projects/7/knowledge-graph/command-receipt", 404, "not found", "knowledge_graph_receipt_not_found");
  },
  subscribe: () => () => {},
  invalidatePendingReads: () => {},
} as unknown as ApiClient;
await act(async () => {
  panelRenderer = create(panelTree(7, ambiguousApi));
  await flush();
});
act(() => panelRenderer.root.findByProps({ "aria-label": "Review confirmation of Scene One to Marlow mentions edge" }).props.onClick({ currentTarget: null }));
await act(async () => {
  panelRenderer.root.findByProps({ "aria-label": "Apply reviewed confirm edge" }).props.onClick();
  await flush();
});
check(text(panelRenderer.root).includes("No committed receipt is available yet"), "ambiguous command delivery without a receipt must explain the unresolved outcome");
const retryButton = panelRenderer.root.findByProps({ "aria-label": "Retry same reviewed confirm edge proposal" });
await act(async () => {
  retryButton.props.onClick();
  await flush();
});
check(
  ambiguousSubmissions.length === 2
    && ambiguousSubmissions[0]?.key === ambiguousSubmissions[1]?.key
    && JSON.stringify(ambiguousSubmissions[0]?.command) === JSON.stringify(ambiguousSubmissions[1]?.command),
  "ambiguous retry must reuse the exact reviewed command and Idempotency-Key",
);
act(() => panelRenderer.unmount());

const staleMutationResult = deferred<KnowledgeGraphCommandResultDTO>();
let staleSubmittedCommand: KnowledgeGraphCommandDTO | null = null;
const staleMutationApi = {
  getKnowledgeGraph: async (projectId: number, query: KnowledgeGraphQueryDTO) => graphFixture(projectId, query),
  executeKnowledgeGraphCommand: async (_projectId: number, nextCommand: KnowledgeGraphCommandDTO) => {
    staleSubmittedCommand = structuredClone(nextCommand);
    return staleMutationResult.promise;
  },
  getKnowledgeGraphCommandReceipt: async () => { throw new Error("receipt lookup should not run"); },
  subscribe: () => () => {},
  invalidatePendingReads: () => {},
} as unknown as ApiClient;
await act(async () => {
  panelRenderer = create(panelTree(7, staleMutationApi));
  await flush();
});
const staleReviewButton = panelRenderer.root.findByProps({ "aria-label": "Review confirmation of Scene One to Marlow mentions edge" });
act(() => staleReviewButton.props.onClick({ currentTarget: staleReviewButton }));
await act(async () => {
  panelRenderer.root.findByProps({ "aria-label": "Apply reviewed confirm edge" }).props.onClick();
  await flush();
});
check(staleSubmittedCommand?.kind === "confirm_edge", "stale-response coverage must hold a real in-flight graph command");
await act(async () => {
  panelRenderer.update(panelTree(8, staleMutationApi));
  await flush();
});
await act(async () => {
  const nextCommand = staleSubmittedCommand!;
  staleMutationResult.resolve({
    knowledge_graph: graphFixture(7, {}, { revision: REVISION_B }),
    changed: true,
    affected_edge: { source: nextCommand.source, target: nextCommand.target, edge_type: nextCommand.edge_type },
    replayed: false,
    applied_revision: REVISION_B,
  });
  await flush();
});
check(
  panelRenderer.root.findByProps({ "data-knowledge-graph-canvas": "true" }).props["data-project-id"] === 8
    && !text(panelRenderer.root).includes("Knowledge Graph edge decision saved"),
  "a delayed old-project command response must not repopulate or announce state in the new project",
);
act(() => panelRenderer.unmount());

let hiddenQueueRevision = REVISION_B;
let hiddenQueueEdges = Array.from({ length: 26 }, (_, index): KnowledgeGraphEdgeDTO => ({
  ...hiddenInferredEdge,
  edge_type: `hidden_type_${index}`,
}));
const hiddenQueueNodes = valid.nodes.filter((node) => node.key === hiddenInferredEdge.source || node.key === hiddenInferredEdge.target);
const hiddenQueueMap = (projectId: number, query: KnowledgeGraphQueryDTO): KnowledgeGraphReadDTO => {
  const base = graphFixture(projectId, query);
  const embedded = hiddenQueueEdges.slice(0, Math.min(query.limit ?? 100, 25));
  return {
    ...base,
    revision: hiddenQueueRevision,
    edges: [base.edges[0]!],
    edge_count: 1,
    returned_edge_count: 1,
    weak_links: [],
    weak_link_count: 0,
    hidden_edges: embedded,
    hidden_edge_count: hiddenQueueEdges.length,
    truncated: embedded.length < hiddenQueueEdges.length,
  };
};
const nextHiddenPage = deferred<{
  project_id: number;
  revision: string;
  offset: number;
  limit: number;
  hidden_edge_count: number;
  returned_edge_count: number;
  nodes: typeof hiddenQueueNodes;
  edges: KnowledgeGraphEdgeDTO[];
}>();
let nextHiddenPageReleased = false;
const hiddenCommands: KnowledgeGraphCommandDTO[] = [];
const hiddenQueueApi = {
  getKnowledgeGraph: async (projectId: number, query: KnowledgeGraphQueryDTO) => hiddenQueueMap(projectId, query),
  getKnowledgeGraphHiddenEdges: async (projectId: number, offset = 0, limit = 25) => {
    if (offset === 25 && !nextHiddenPageReleased) return nextHiddenPage.promise;
    const edges = hiddenQueueEdges.slice(offset, offset + limit);
    return {
      project_id: projectId,
      revision: hiddenQueueRevision,
      offset,
      limit,
      hidden_edge_count: hiddenQueueEdges.length,
      returned_edge_count: edges.length,
      nodes: edges.length > 0 ? structuredClone(hiddenQueueNodes) : [],
      edges: structuredClone(edges),
    };
  },
  executeKnowledgeGraphCommand: async (projectId: number, nextCommand: KnowledgeGraphCommandDTO): Promise<KnowledgeGraphCommandResultDTO> => {
    hiddenCommands.push(structuredClone(nextCommand));
    hiddenQueueEdges = hiddenQueueEdges.filter((edge) => edge.edge_type !== nextCommand.edge_type);
    hiddenQueueRevision = REVISION_C;
    return {
      knowledge_graph: hiddenQueueMap(projectId, {}),
      changed: true,
      affected_edge: { source: nextCommand.source, target: nextCommand.target, edge_type: nextCommand.edge_type },
      replayed: false,
      applied_revision: REVISION_C,
    };
  },
  getKnowledgeGraphCommandReceipt: async () => { throw new Error("receipt lookup should not run for a successful restore"); },
  subscribe: () => () => {},
  invalidatePendingReads: () => {},
} as unknown as ApiClient;
await act(async () => {
  panelRenderer = create(panelTree(7, hiddenQueueApi));
  await flush();
});
check(text(panelRenderer.root).includes("The bounded map includes 25 of 26 hidden edges"), "bounded hidden diagnostics must point to the complete restore queue");
await act(async () => {
  panelRenderer.root.findByProps({ "aria-label": "Open the complete hidden edge review queue" }).props.onClick();
  await flush();
});
check(text(panelRenderer.root).includes("Queue rows 1–25 of 26"), "the hidden review queue must expose its exact page range and total");
act(() => panelRenderer.root.findByProps({ "aria-label": "Show all 25 returned hidden edges" }).props.onClick());
check(panelRenderer.root.findAllByProps({ "data-hidden-graph-edge": "true" }).length === 25, "hidden review expansion must expose every decision on the current page");
act(() => panelRenderer.root.findByProps({ "aria-label": "Next hidden edge review page" }).props.onClick());
check(panelRenderer.root.findAllByProps({ "data-hidden-graph-edge": "true" }).length === 0, "an offset change must synchronously clear stale hidden-page rows before the next response arrives");
nextHiddenPageReleased = true;
await act(async () => {
  const edges = hiddenQueueEdges.slice(25, 50);
  nextHiddenPage.resolve({
    project_id: 7,
    revision: hiddenQueueRevision,
    offset: 25,
    limit: 25,
    hidden_edge_count: hiddenQueueEdges.length,
    returned_edge_count: edges.length,
    nodes: structuredClone(hiddenQueueNodes),
    edges: structuredClone(edges),
  });
  await flush();
});
check(text(panelRenderer.root).includes("Queue rows 26–26 of 26"), "the final hidden page must remain reachable after a delayed page response");
const restoreReviewButton = panelRenderer.root.findByProps({ "aria-label": "Review restoring Scene One to Marlow hidden type 25 edge" });
act(() => restoreReviewButton.props.onClick({ currentTarget: restoreReviewButton }));
await act(async () => {
  panelRenderer.root.findByProps({ "aria-label": "Apply reviewed restore edge" }).props.onClick();
  await flush();
});
check(
  hiddenCommands.length === 1
    && hiddenCommands[0]?.kind === "unhide_edge"
    && hiddenCommands[0]?.edge_type === "hidden_type_25"
    && hiddenCommands[0]?.expected_revision === REVISION_B,
  "restore must preflight the same complete hidden page and submit its fresh page revision",
);
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
