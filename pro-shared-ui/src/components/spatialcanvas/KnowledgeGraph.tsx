import { useCallback, useEffect, useId, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import type {
  KnowledgeGraphCommandDTO,
  KnowledgeGraphEdgeDTO,
  KnowledgeGraphNodeDTO,
  KnowledgeGraphQueryDTO,
  KnowledgeGraphReadDTO,
  KnowledgeGraphViewMode,
} from "@logosforge/ui-contracts";
import { useSelection } from "../../adapters/selection";
import { useStudio } from "../../adapters/StudioProvider";
import { ApiRequestError, ApiRequestTimeoutError } from "../../adapters/httpApiClient";
import { flushPendingProjectSaves } from "../../adapters/projectSaveCoordinator";
import { useKnowledgeGraph, useKnowledgeGraphHiddenEdges, useMountedRef } from "../../hooks";
import { PanelShell, type PanelProps } from "../shell/PanelShell";
import {
  buildKnowledgeGraphView,
  graphEdgeKey,
  knowledgeGraphNodeSize,
  layoutKnowledgeGraph,
  storyOrderFlowPath,
  storyOrderFlowSegments,
  type GraphConfidence,
  type GraphNodeSizing,
  type StoryOrderBand,
} from "./knowledgeGraphModel";
import {
  createKnowledgeGraphIdempotencyKey,
  describeKnowledgeGraphAction,
  planKnowledgeGraphCommand,
  type KnowledgeGraphEdgeAction,
  type KnowledgeGraphEdgeIntent,
} from "./knowledgeGraphTransactions";

// Keep the default project page dense enough to be useful while preserving
// distinct keyboard/pointer hit areas. Larger graphs remain reachable through
// the server-backed focus-neighborhood control.
const PAGE_LIMIT = 48;
const HIDDEN_EDGE_PAGE_LIMIT = 25;
const CW = 900;
const CH = 560;

interface GraphViewMeta {
  title: string;
  shortLabel: string;
  description: string;
  empty: string;
}

const GRAPH_VIEW_META: Record<KnowledgeGraphViewMode, GraphViewMeta> = {
  project_map: {
    title: "PROJECT MAP",
    shortLabel: "Project Map",
    description: "The bounded canonical story graph across every available source system.",
    empty: "No narrative knowledge has been derived yet. Add manuscript structure, PSYKE entries, notes, or workflows to begin the map.",
  },
  structure: {
    title: "STRUCTURE",
    shortLabel: "Structure",
    description: "Recorded hierarchy and manuscript-order evidence. Inferred order disappears in Confirmed only scope.",
    empty: "No structural relationships match this evidence scope. Add or link acts, chapters, scenes, plot blocks, or timeline evidence.",
  },
  recorded_risk: {
    title: "RECORDED RISK",
    shortLabel: "Recorded Risk",
    description: "Only saved risk and contradiction evidence from Core—not a prediction or a low-confidence guess.",
    empty: "No saved risk or contradiction evidence matches this scope. This does not prove that the manuscript is risk-free.",
  },
  revision_impact: {
    title: "SAVED REVISION IMPACT",
    shortLabel: "Saved Revision Impact",
    description: "Saved revision-intelligence reports and the exact story elements they revise or flag.",
    empty: "No saved revision-impact evidence matches this scope. Run and save a revision-impact analysis to populate this view.",
  },
};

const panelBox: CSSProperties = {
  position: "relative",
  width: "100%",
  height: "100%",
  background: "radial-gradient(70% 60% at 40% 45%,var(--raised),var(--base) 78%)",
  border: "1px solid var(--line)",
  boxShadow: "0 16px 60px rgba(0,0,0,.6)",
  overflow: "hidden",
  display: "flex",
  flexDirection: "column",
};

const control: CSSProperties = {
  border: "1px solid var(--line2)",
  background: "var(--tint)",
  color: "var(--txt2)",
  font: "inherit",
  fontSize: 8,
  letterSpacing: ".06em",
  padding: "4px 7px",
};

const activeControl: CSSProperties = {
  ...control,
  borderColor: "var(--line-cy)",
  color: "var(--accent)",
  cursor: "pointer",
};

interface NodeMeta {
  icon: string;
  color: string;
  label: string;
}

const TYPE_META: Record<string, NodeMeta> = {
  project: { icon: "◉", color: "var(--accent)", label: "Project" },
  act: { icon: "Ⅰ", color: "var(--amber)", label: "Act" },
  chapter: { icon: "§", color: "var(--amber)", label: "Chapter" },
  scene: { icon: "▤", color: "var(--cyan)", label: "Scene" },
  screenplay_block: { icon: "▥", color: "var(--cyan)", label: "Screenplay block" },
  psyke_entry: { icon: "◆", color: "var(--c-char)", label: "PSYKE entry" },
  character: { icon: "◆", color: "var(--c-char)", label: "Character" },
  place: { icon: "▲", color: "var(--c-place)", label: "Place" },
  object: { icon: "◇", color: "var(--c-obj)", label: "Object" },
  lore: { icon: "⬢", color: "var(--c-lore)", label: "Lore" },
  theme: { icon: "✦", color: "var(--c-theme)", label: "Theme" },
  motif: { icon: "✧", color: "var(--c-theme)", label: "Motif" },
  note: { icon: "▧", color: "var(--green)", label: "Note" },
  plot_block: { icon: "▰", color: "var(--amber)", label: "Plot block" },
  timeline_event: { icon: "◆", color: "var(--cyan)", label: "Timeline event" },
  setup: { icon: "↗", color: "var(--suggestion)", label: "Setup" },
  payoff: { icon: "◎", color: "var(--green)", label: "Payoff" },
  revision_impact: { icon: "△", color: "var(--warning)", label: "Revision impact" },
  rewrite_variant: { icon: "≈", color: "var(--suggestion)", label: "Rewrite" },
  controlled_apply_operation: { icon: "✓", color: "var(--green)", label: "Controlled apply" },
  decision_card: { icon: "!", color: "var(--warning)", label: "Decision" },
  workflow_run: { icon: "▷", color: "var(--cyan)", label: "Workflow" },
};

const FALLBACK_META: NodeMeta = { icon: "▣", color: "var(--txt2)", label: "Other" };
const metaOf = (nodeType: string): NodeMeta => TYPE_META[nodeType] ?? {
  ...FALLBACK_META,
  label: nodeType.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase()),
};

const STORY_ORDER_COLORS: Record<StoryOrderBand, string> = {
  beginning: "var(--green)",
  middle: "var(--amber)",
  ending: "var(--c-theme)",
};

function Message({ children, role }: { children: ReactNode; role?: "alert" | "status" }) {
  return (
    <div role={role} aria-live={role ? "polite" : undefined} style={{ flex: 1, display: "grid", placeItems: "center", padding: 24, textAlign: "center", fontSize: 11, color: role === "alert" ? "var(--blocking)" : "var(--txt3)", letterSpacing: ".04em" }}>
      {children}
    </div>
  );
}

function InsightCard({
  label,
  tone,
  children,
  onClick,
  ariaLabel,
  disabled = false,
}: {
  label: string;
  tone: string;
  children: ReactNode;
  onClick?: () => void;
  ariaLabel?: string;
  disabled?: boolean;
}) {
  const content = (
    <>
      <span style={{ display: "block", fontSize: 7.5, letterSpacing: ".14em", color: tone, marginBottom: 4 }}>{label}</span>
      <span style={{ display: "block", color: "var(--txt)", fontSize: 9.5, lineHeight: 1.4, overflowWrap: "anywhere" }}>{children}</span>
    </>
  );
  return onClick ? (
    <button type="button" aria-label={ariaLabel} disabled={disabled} onClick={onClick} style={{ width: "100%", textAlign: "left", border: "1px solid var(--line2)", background: "var(--tint)", padding: "8px 9px", marginBottom: 6, font: "inherit", cursor: disabled ? "default" : "pointer", opacity: disabled ? 0.55 : 1 }}>{content}</button>
  ) : (
    <div style={{ border: "1px solid var(--line2)", background: "var(--tint)", padding: "8px 9px", marginBottom: 6 }}>{content}</div>
  );
}

function edgeTitle(edge: KnowledgeGraphEdgeDTO, nodes: Map<string, KnowledgeGraphNodeDTO>): string {
  const source = nodes.get(edge.source)?.label || edge.source;
  const target = nodes.get(edge.target)?.label || edge.target;
  return `${source} —${edge.edge_type.replaceAll("_", " ")}→ ${target} · ${edge.confidence} · ${edge.source_system}`;
}

function edgeInspectionLabel(
  edge: KnowledgeGraphEdgeDTO,
  selectedKey: string,
  nodes: Map<string, KnowledgeGraphNodeDTO>,
): string {
  const outgoing = edge.source === selectedKey;
  const otherKey = outgoing ? edge.target : edge.source;
  const other = nodes.get(otherKey)?.label || otherKey;
  return [
    `${outgoing ? "Outgoing to" : "Incoming from"} ${other}`,
    `Type ${edge.edge_type.replaceAll("_", " ")}`,
    `Confidence ${edge.confidence}`,
    `Source system ${edge.source_system.replaceAll("_", " ")}`,
    `Provenance ${edge.provenance || "not provided"}`,
    `Explanation ${edge.explanation || "not provided"}`,
  ].join(". ");
}

type NormalizedKnowledgeGraphQuery = Required<KnowledgeGraphQueryDTO>;

interface EdgeReviewProposal {
  ownerProjectId: number;
  query: NormalizedKnowledgeGraphQuery;
  intent: KnowledgeGraphEdgeIntent;
  edge: KnowledgeGraphEdgeDTO;
  idempotencyKey: string;
  command: KnowledgeGraphCommandDTO | null;
  retryReady: boolean;
  hiddenPageOffset: number | null;
}

function queryMatches(
  left: NormalizedKnowledgeGraphQuery,
  right: NormalizedKnowledgeGraphQuery,
): boolean {
  return left.focus_key === right.focus_key
    && left.depth === right.depth
    && left.limit === right.limit
    && left.view_mode === right.view_mode
    && left.include_inferred === right.include_inferred;
}

function actionLabel(action: KnowledgeGraphEdgeAction): string {
  if (action === "confirm_edge") return "CONFIRM EDGE";
  if (action === "hide_edge") return "HIDE EDGE";
  return "RESTORE EDGE";
}

function actionEffect(action: KnowledgeGraphEdgeAction): string {
  if (action === "confirm_edge") {
    return "Persists this inferred relationship as user-confirmed graph metadata. It does not change manuscript or PSYKE content.";
  }
  if (action === "hide_edge") {
    return "Hides this relationship from the live graph while preserving any confirmation state. The decision is reversible from Hidden edge review.";
  }
  return "Restores this hidden relationship to the live graph using its prior traceable evidence.";
}

export function KnowledgeGraph(props: PanelProps) {
  const { api, projectId } = useStudio();
  const { setSelection } = useSelection();
  const markerPrefix = `knowledge-graph-${useId().replaceAll(":", "")}`;
  const mounted = useMountedRef();
  const projectIdRef = useRef(projectId);
  projectIdRef.current = projectId;
  const apiRef = useRef(api);
  apiRef.current = api;
  const requestRef = useRef<object | null>(null);
  const reviewRef = useRef<EdgeReviewProposal | null>(null);
  const reviewDialogRef = useRef<HTMLElement | null>(null);
  const reviewTriggerRef = useRef<HTMLButtonElement | null>(null);
  const [focusKey, setFocusKey] = useState<string | null>(null);
  const [depth, setDepth] = useState(1);
  const [viewMode, setViewMode] = useState<KnowledgeGraphViewMode>("project_map");
  const [includeInferred, setIncludeInferred] = useState(true);
  const [nodeSizing, setNodeSizing] = useState<GraphNodeSizing>("story_gravity");
  const [storyOrderFlow, setStoryOrderFlow] = useState(false);
  const [hiddenNodeTypes, setHiddenNodeTypes] = useState<Set<string>>(new Set());
  const [confidenceMin, setConfidenceMin] = useState<GraphConfidence>("unknown");
  const [sourceSystem, setSourceSystem] = useState("all");
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [connectionsExpanded, setConnectionsExpanded] = useState(false);
  const [orphansExpanded, setOrphansExpanded] = useState(false);
  const [weakLinksExpanded, setWeakLinksExpanded] = useState(false);
  const [hiddenEdgesExpanded, setHiddenEdgesExpanded] = useState(false);
  const [hiddenReviewOpen, setHiddenReviewOpen] = useState(false);
  const [hiddenReviewOffset, setHiddenReviewOffset] = useState(0);
  const [commandSnapshot, setCommandSnapshot] = useState<KnowledgeGraphReadDTO | null>(null);
  const [review, setReview] = useState<EdgeReviewProposal | null>(null);
  const [busy, setBusy] = useState("");
  const [mutationError, setMutationError] = useState("");
  const [mutationStatus, setMutationStatus] = useState("");

  const replaceReview = useCallback((next: EdgeReviewProposal | null) => {
    reviewRef.current = next;
    setReview(next);
  }, []);

  useEffect(() => {
    setFocusKey(null);
    setDepth(1);
    setViewMode("project_map");
    setIncludeInferred(true);
    setNodeSizing("story_gravity");
    setStoryOrderFlow(false);
    setHiddenNodeTypes(new Set());
    setConfidenceMin("unknown");
    setSourceSystem("all");
    setSelectedKey(null);
    setConnectionsExpanded(false);
    setOrphansExpanded(false);
    setWeakLinksExpanded(false);
    setHiddenEdgesExpanded(false);
    setHiddenReviewOpen(false);
    setHiddenReviewOffset(0);
    setCommandSnapshot(null);
    requestRef.current = null;
    replaceReview(null);
    setBusy("");
    setMutationError("");
    setMutationStatus("");
  }, [api, projectId, replaceReview]);

  const query = useMemo<NormalizedKnowledgeGraphQuery>(() => ({
    focus_key: focusKey,
    depth,
    limit: PAGE_LIMIT,
    view_mode: viewMode,
    include_inferred: includeInferred,
  }), [depth, focusKey, includeInferred, viewMode]);
  const queryRef = useRef(query);
  queryRef.current = query;
  const { data, loading, error, refetch } = useKnowledgeGraph(query);
  const hiddenReviewResource = useKnowledgeGraphHiddenEdges(
    hiddenReviewOffset,
    HIDDEN_EDGE_PAGE_LIMIT,
    hiddenReviewOpen,
  );
  useEffect(() => {
    if (
      data
      && data.project_id === projectId
      && data.focus_key === query.focus_key
      && data.depth === query.depth
      && data.view_mode === query.view_mode
      && data.include_inferred === query.include_inferred
    ) setCommandSnapshot(data);
  }, [data, projectId, query.depth, query.focus_key, query.include_inferred, query.view_mode]);

  useEffect(() => {
    requestRef.current = null;
    setCommandSnapshot(null);
    replaceReview(null);
    setBusy("");
    setMutationError("");
    setMutationStatus("");
  }, [depth, focusKey, includeInferred, projectId, replaceReview, viewMode]);
  // useResource clears on project changes in an effect. This synchronous guard
  // prevents even one render of the prior project's graph in the new workspace.
  const matchesActiveQuery = (candidate: KnowledgeGraphReadDTO | null | undefined) => (
    candidate != null
    && candidate.project_id === projectId
    && candidate.focus_key === focusKey
    && candidate.depth === depth
    && candidate.view_mode === viewMode
    && candidate.include_inferred === includeInferred
  );
  const graph = matchesActiveQuery(commandSnapshot)
    ? commandSnapshot ?? undefined
    : matchesActiveQuery(data)
      ? data
      : undefined;
  const view = useMemo(() => graph ? buildKnowledgeGraphView(graph, {
    hiddenNodeTypes,
    confidenceMin,
    sourceSystem,
  }) : null, [confidenceMin, graph, hiddenNodeTypes, sourceSystem]);

  useEffect(() => {
    if (selectedKey && view && !view.nodeByKey.has(selectedKey)) {
      setSelectedKey(null);
      setSelection({ sceneId: null, text: "", section: "Knowledge Graph", nodeId: null });
    }
  }, [selectedKey, setSelection, view]);

  const nodeTypes = useMemo(() => {
    const counts = new Map<string, number>();
    for (const node of graph?.nodes ?? []) counts.set(node.node_type, (counts.get(node.node_type) ?? 0) + 1);
    return [...counts].sort(([left], [right]) => left.localeCompare(right));
  }, [graph]);
  const sourceSystems = useMemo(() => {
    const values = new Set((graph?.edges ?? []).map((edge) => edge.source_system).filter(Boolean));
    if (sourceSystem !== "all") values.add(sourceSystem);
    return [...values].sort();
  }, [graph, sourceSystem]);

  const selected = view?.nodeByKey.get(selectedKey ?? "")
    ?? (graph?.focus_key ? view?.nodeByKey.get(graph.focus_key) : undefined)
    ?? [...(view?.nodes ?? [])].sort((left, right) => right.degree - left.degree || left.key.localeCompare(right.key))[0];
  const positions = useMemo(
    () => layoutKnowledgeGraph(view?.nodes ?? [], CW, CH, viewMode, view?.edges ?? []),
    [view?.edges, view?.nodes, viewMode],
  );
  const visibleDegree = useMemo(() => {
    const degree = new Map<string, number>((view?.nodes ?? []).map((node) => [node.key, 0]));
    for (const edge of view?.edges ?? []) {
      degree.set(edge.source, (degree.get(edge.source) ?? 0) + 1);
      degree.set(edge.target, (degree.get(edge.target) ?? 0) + 1);
    }
    return degree;
  }, [view]);
  const selectedEdges = selected ? (view?.edges ?? []).filter((edge) => edge.source === selected.key || edge.target === selected.key) : [];
  const displayedConnections = connectionsExpanded ? selectedEdges : selectedEdges.slice(0, 12);
  const orphanNodes = view?.orphanNodes ?? [];
  const displayedOrphans = orphansExpanded ? orphanNodes : orphanNodes.slice(0, 8);
  const weakLinks = view?.weakLinks ?? [];
  const displayedWeakLinks = weakLinksExpanded ? weakLinks : weakLinks.slice(0, 8);
  const hiddenPageCandidate = hiddenReviewResource.data;
  const hiddenReviewPage = hiddenPageCandidate != null
    && hiddenPageCandidate.project_id === projectId
    && hiddenPageCandidate.offset === hiddenReviewOffset
    && hiddenPageCandidate.limit === HIDDEN_EDGE_PAGE_LIMIT
    ? hiddenPageCandidate
    : undefined;
  const hiddenEdges = hiddenReviewOpen
    ? hiddenReviewPage?.edges ?? []
    : graph?.hidden_edges ?? [];
  const displayedHiddenEdges = hiddenEdgesExpanded ? hiddenEdges : hiddenEdges.slice(0, 8);
  const graphNodeByKey = new Map((graph?.nodes ?? []).map((node) => [node.key, node]));
  const hiddenReviewNodeByKey = new Map((hiddenReviewPage?.nodes ?? []).map((node) => [node.key, node]));
  const maxDegree = Math.max(1, ...(view?.nodes ?? []).map((node) => node.degree));
  const effectiveNodeSizing: GraphNodeSizing = nodeSizing === "story_gravity" && graph?.story_gravity_available
    ? "story_gravity"
    : "view_links";
  const gravityMappedNodeCount = effectiveNodeSizing === "story_gravity"
    ? (view?.nodes ?? []).filter((node) => node.story_gravity !== null).length
    : 0;
  const flowSegments = useMemo(
    () => storyOrderFlow ? storyOrderFlowSegments(view?.edges ?? []) : [],
    [storyOrderFlow, view?.edges],
  );
  const flowGapCount = flowSegments.filter((segment) => segment.gapBefore).length;
  const mapCapped = Boolean(graph && (
    graph.returned_node_count < graph.node_count
    || graph.returned_edge_count < graph.edge_count
  ));
  const diagnosticsCapped = Boolean(graph?.story_diagnostics_available && (
    graph.orphan_keys.length < graph.orphan_count
    || graph.weak_links.length < graph.weak_link_count
    || graph.hidden_edges.length < graph.hidden_edge_count
  ));

  useEffect(() => {
    setConnectionsExpanded(false);
  }, [confidenceMin, focusKey, includeInferred, selected?.key, sourceSystem, viewMode]);

  useEffect(() => {
    setOrphansExpanded(false);
    setWeakLinksExpanded(false);
    setHiddenEdgesExpanded(false);
  }, [confidenceMin, focusKey, hiddenNodeTypes, includeInferred, sourceSystem, viewMode]);

  useEffect(() => {
    if (!hiddenReviewOpen || !hiddenReviewPage || hiddenReviewOffset === 0) return;
    if (hiddenReviewPage.returned_edge_count > 0 || hiddenReviewOffset < hiddenReviewPage.hidden_edge_count) return;
    const lastOffset = hiddenReviewPage.hidden_edge_count === 0
      ? 0
      : Math.floor((hiddenReviewPage.hidden_edge_count - 1) / HIDDEN_EDGE_PAGE_LIMIT) * HIDDEN_EDGE_PAGE_LIMIT;
    setHiddenReviewOffset(lastOffset);
  }, [hiddenReviewOffset, hiddenReviewOpen, hiddenReviewPage]);

  const chooseNode = (node: KnowledgeGraphNodeDTO) => {
    setSelectedKey(node.key);
    setSelection({
      sceneId: node.node_type === "scene" && /^\d+$/.test(node.source_id ?? "") ? Number(node.source_id) : null,
      text: [node.label, node.summary].filter(Boolean).join(" — "),
      section: "Knowledge Graph",
      nodeId: node.key,
    });
  };

  const toggleNodeType = (nodeType: string) => setHiddenNodeTypes((current) => {
    const next = new Set(current);
    if (next.has(nodeType)) next.delete(nodeType);
    else next.add(nodeType);
    return next;
  });

  const beginEdgeReview = (
    action: KnowledgeGraphEdgeAction,
    edge: KnowledgeGraphEdgeDTO,
    trigger: HTMLButtonElement,
    hiddenPageOffset: number | null = null,
  ) => {
    if (projectId == null || busy) return;
    reviewTriggerRef.current = trigger;
    setMutationError("");
    setMutationStatus("");
    replaceReview({
      ownerProjectId: projectId,
      query: { ...query },
      intent: {
        kind: action,
        source: edge.source,
        target: edge.target,
        edge_type: edge.edge_type,
      },
      edge: { ...edge, metadata: { ...edge.metadata } },
      idempotencyKey: createKnowledgeGraphIdempotencyKey(),
      command: null,
      retryReady: false,
      hiddenPageOffset,
    });
  };

  const cancelEdgeReview = () => {
    if (busy) return;
    replaceReview(null);
    setMutationError("");
    setMutationStatus("");
    const trigger = reviewTriggerRef.current;
    reviewTriggerRef.current = null;
    if (typeof trigger?.focus === "function") trigger.focus();
  };

  useEffect(() => {
    if (review && !busy) reviewDialogRef.current?.focus();
  }, [busy, review]);

  const runReviewedEdgeAction = useCallback(async () => {
    const initialProposal = reviewRef.current;
    if (!initialProposal || requestRef.current != null) return;
    const ownerApi = api;
    const ownerProjectId = initialProposal.ownerProjectId;
    const proposalKey = initialProposal.idempotencyKey;
    const token = {};
    requestRef.current = token;
    setBusy(initialProposal.intent.kind);
    setMutationError("");
    setMutationStatus("Refreshing graph review state…");

    const ownsRequest = () => mounted.current
      && requestRef.current === token
      && projectIdRef.current === ownerProjectId
      && apiRef.current === ownerApi;
    const ownsProposal = () => ownsRequest()
      && reviewRef.current?.idempotencyKey === proposalKey
      && queryMatches(queryRef.current, initialProposal.query);

    const refreshCurrentQuery = async (successMessage: string) => {
      api.invalidatePendingReads?.();
      try {
        const refreshed = await api.getKnowledgeGraph(ownerProjectId, initialProposal.query);
        if (!ownsRequest() || !queryMatches(queryRef.current, initialProposal.query)) return;
        setCommandSnapshot(refreshed);
        setMutationError("");
        setMutationStatus(successMessage);
        if (hiddenReviewOpen) hiddenReviewResource.refetch();
      } catch (refreshFailure) {
        if (!ownsRequest()) return;
        setMutationStatus("");
        setMutationError(`The edge decision was committed, but the active graph view could not refresh — ${refreshFailure instanceof Error ? refreshFailure.message : String(refreshFailure)}. Reload the view; do not repeat the decision as a new proposal.`);
      } finally {
        if (ownsRequest()) refetch();
      }
    };

    let command = initialProposal.command;
    try {
      if (!command) {
        await flushPendingProjectSaves({ commitActiveField: true });
        if (!ownsProposal()) return;
        api.invalidatePendingReads?.();
        const latest = await api.getKnowledgeGraph(ownerProjectId, initialProposal.query);
        if (!ownsProposal()) return;
        setCommandSnapshot(latest);
        let planningGraph = latest;
        if (initialProposal.intent.kind === "unhide_edge") {
          if (initialProposal.hiddenPageOffset == null) {
            replaceReview(null);
            setMutationStatus("");
            setMutationError("Open the complete hidden-edge review queue and review that edge again before restoring it.");
            return;
          }
          const hiddenPage = await api.getKnowledgeGraphHiddenEdges(
            ownerProjectId,
            initialProposal.hiddenPageOffset,
            HIDDEN_EDGE_PAGE_LIMIT,
          );
          if (!ownsProposal()) return;
          planningGraph = {
            ...latest,
            revision: hiddenPage.revision,
            hidden_edges: hiddenPage.edges,
            hidden_edge_count: hiddenPage.hidden_edge_count,
          };
        }
        const planned = planKnowledgeGraphCommand(planningGraph, initialProposal.intent);
        if (!planned.command) {
          replaceReview(null);
          setMutationStatus("");
          setMutationError(planned.error);
          refetch();
          return;
        }
        command = planned.command;
        replaceReview({ ...initialProposal, edge: planned.edge, command, retryReady: false });
      }

      if (!ownsProposal()) return;
      setMutationStatus(`Saving reviewed decision to ${describeKnowledgeGraphAction(command.kind)}…`);
      try {
        const result = await api.executeKnowledgeGraphCommand(
          ownerProjectId,
          command,
          proposalKey,
        );
        if (!ownsProposal()) return;
        replaceReview(null);
        reviewTriggerRef.current = null;
        await refreshCurrentQuery(result.replayed
          ? "Recovered the previously committed edge decision."
          : result.changed
            ? "Knowledge Graph edge decision saved."
            : "The Knowledge Graph already matched that edge decision.");
      } catch (failure) {
        if (!ownsProposal()) return;
        const ambiguousTransport = failure instanceof ApiRequestTimeoutError
          ? failure.outcomeUnknown
          : failure instanceof ApiRequestError
            ? failure.status >= 500 || failure.status === 408 || failure.status === 429
            : true;
        if (ambiguousTransport) {
          setMutationStatus("The write response was interrupted. Checking its durable receipt…");
          try {
            const receipt = await api.getKnowledgeGraphCommandReceipt(
              ownerProjectId,
              proposalKey,
              command,
            );
            if (!ownsProposal()) return;
            replaceReview(null);
            reviewTriggerRef.current = null;
            await refreshCurrentQuery(receipt.original_changed
              ? "Recovered the committed edge decision from its durable receipt."
              : "The durable receipt confirms that the graph already matched this decision.");
            return;
          } catch (receiptFailure) {
            if (!ownsProposal()) return;
            const next = { ...(reviewRef.current ?? initialProposal), command, retryReady: true };
            replaceReview(next);
            setMutationStatus("");
            setMutationError(
              receiptFailure instanceof ApiRequestError
                && receiptFailure.code === "knowledge_graph_receipt_not_found"
                ? "No committed receipt is available yet. Retry will reuse the exact reviewed proposal and Idempotency-Key."
                : `The write outcome could not be verified — ${receiptFailure instanceof Error ? receiptFailure.message : String(receiptFailure)}. Retry will reuse the exact reviewed proposal and Idempotency-Key.`,
            );
            refetch();
            return;
          }
        }
        throw failure;
      }
    } catch (failure) {
      if (!ownsRequest()) return;
      const keyConflict = failure instanceof ApiRequestError && failure.code === "idempotency_key_conflict";
      const conflict = failure instanceof ApiRequestError
        && !keyConflict
        && (failure.code === "knowledge_graph_conflict" || failure.status === 409);
      const missing = failure instanceof ApiRequestError && failure.status === 404;
      const definiteClientFailure = failure instanceof ApiRequestError
        && failure.status >= 400
        && failure.status < 500
        && failure.status !== 408
        && failure.status !== 429;
      if (conflict || missing || keyConflict || definiteClientFailure) {
        replaceReview(null);
      } else {
        replaceReview({ ...(reviewRef.current ?? initialProposal), command, retryReady: true });
      }
      setMutationStatus("");
      setMutationError(
        conflict
          ? "The graph review state changed before this decision could be saved. The map was refreshed; review the edge again."
            : missing
              ? "That edge is no longer available. The map was refreshed."
            : keyConflict
              ? "This proposal key was already used for a different graph decision. Review the edge again to create a new proposal."
              : definiteClientFailure
                ? `Core rejected the edge decision — ${failure.message}. The map was refreshed; review the edge again.`
                : `Couldn’t save the edge decision — ${failure instanceof Error ? failure.message : String(failure)}.`,
      );
      refetch();
    } finally {
      if (requestRef.current === token) {
        requestRef.current = null;
        if (mounted.current && projectIdRef.current === ownerProjectId) setBusy("");
      }
    }
  }, [api, hiddenReviewOpen, hiddenReviewResource, mounted, refetch, replaceReview]);

  const interactionLocked = Boolean(busy) || review != null;
  const clearProjectionContext = (resetManualFilters: boolean) => {
    setFocusKey(null);
    setDepth(1);
    setSelectedKey(null);
    setSelection({ sceneId: null, text: "", section: "Knowledge Graph", nodeId: null });
    setConnectionsExpanded(false);
    setOrphansExpanded(false);
    setWeakLinksExpanded(false);
    setHiddenEdgesExpanded(false);
    setHiddenReviewOpen(false);
    setHiddenReviewOffset(0);
    setCommandSnapshot(null);
    replaceReview(null);
    reviewTriggerRef.current = null;
    setMutationError("");
    setMutationStatus("");
    if (resetManualFilters) {
      setHiddenNodeTypes(new Set());
      setConfidenceMin("unknown");
      setSourceSystem("all");
    }
  };
  const changeViewMode = (next: KnowledgeGraphViewMode) => {
    if (interactionLocked || next === viewMode) return;
    clearProjectionContext(true);
    setViewMode(next);
  };
  const changeEvidenceScope = (nextIncludeInferred: boolean) => {
    if (interactionLocked || nextIncludeInferred === includeInferred) return;
    clearProjectionContext(false);
    setIncludeInferred(nextIncludeInferred);
  };
  const reviewSourceLabel = review
    ? hiddenReviewNodeByKey.get(review.edge.source)?.label || graphNodeByKey.get(review.edge.source)?.label || review.edge.source
    : "";
  const reviewTargetLabel = review
    ? hiddenReviewNodeByKey.get(review.edge.target)?.label || graphNodeByKey.get(review.edge.target)?.label || review.edge.target
    : "";
  const selectedSizing = selected
    ? knowledgeGraphNodeSize(selected, nodeSizing, Boolean(graph?.story_gravity_available), maxDegree)
    : null;

  return (
    <PanelShell {...props}>
      <div data-screen-label="Knowledge Graph" style={panelBox}>
        <div style={{ position: "absolute", top: -1, left: -1, width: 14, height: 14, borderTop: "1px solid var(--crimson)", borderLeft: "1px solid var(--crimson)", zIndex: 9 }} />
        <div style={{ position: "absolute", top: 3, left: 3, width: 5, height: 5, background: "var(--crimson)", zIndex: 9 }} />

        <div style={{ minHeight: 44, flex: "none", display: "flex", flexWrap: "wrap", alignItems: "center", gap: 9, padding: "5px 16px", borderBottom: "1px solid var(--line)", background: "var(--tint)", zIndex: 5 }}>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 14, letterSpacing: ".12em", color: "var(--strong)" }}>{GRAPH_VIEW_META[viewMode].title}</span>
          <span style={{ fontSize: 7.5, color: "var(--accent)", border: "1px solid var(--line-cy)", padding: "2px 7px", letterSpacing: ".12em" }}>CANONICAL NARRATIVE GRAPH</span>
          {graph?.focus_key && <span style={{ maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: 8, color: "var(--amber)" }}>FOCUS · {graph.nodes.find((node) => node.key === graph.focus_key)?.label ?? graph.focus_key}</span>}
          <div style={{ flex: 1 }} />
          <label style={{ display: "flex", alignItems: "center", gap: 5, color: "var(--txt2)", fontSize: 8 }}>
            VIEW
            <select aria-label="Knowledge Graph view mode" value={viewMode} disabled={interactionLocked} onChange={(event) => changeViewMode(event.currentTarget.value as KnowledgeGraphViewMode)} style={{ ...control, opacity: interactionLocked ? 0.55 : 1 }}>
              <option value="project_map">Project Map</option>
              <option value="structure">Structure</option>
              <option value="recorded_risk">Recorded Risk</option>
              <option value="revision_impact">Saved Revision Impact</option>
            </select>
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 5, color: "var(--txt2)", fontSize: 8 }}>
            EVIDENCE
            <select aria-label="Knowledge Graph evidence scope" value={includeInferred ? "inferred_and_confirmed" : "confirmed_only"} disabled={interactionLocked} onChange={(event) => changeEvidenceScope(event.currentTarget.value === "inferred_and_confirmed")} style={{ ...control, opacity: interactionLocked ? 0.55 : 1 }}>
              <option value="confirmed_only">Confirmed only</option>
              <option value="inferred_and_confirmed">Inferred + Confirmed</option>
            </select>
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 5, color: "var(--txt2)", fontSize: 8 }}>
            DEPTH
            <select aria-label="Knowledge Graph focus depth" value={depth} disabled={interactionLocked} onChange={(event) => setDepth(Number(event.currentTarget.value))} style={{ ...control, opacity: interactionLocked ? 0.55 : 1 }}>
              <option value={1}>1 hop</option>
              <option value={2}>2 hops</option>
            </select>
          </label>
          {focusKey ? (
            <button type="button" disabled={interactionLocked} aria-label={`Return to full ${GRAPH_VIEW_META[viewMode].shortLabel} view`} onClick={() => setFocusKey(null)} style={{ ...activeControl, opacity: interactionLocked ? 0.55 : 1 }}>SHOW FULL {GRAPH_VIEW_META[viewMode].title}</button>
          ) : (
            <button type="button" disabled={!selected || interactionLocked} aria-label={selected ? `Focus graph on ${selected.label || selected.key}` : "Focus graph on selected node"} onClick={() => selected && setFocusKey(selected.key)} style={{ ...activeControl, opacity: selected && !interactionLocked ? 1 : 0.45, cursor: selected && !interactionLocked ? "pointer" : "default" }}>FOCUS NEIGHBORHOOD</button>
          )}
        </div>

        {graph && (graph.truncated || diagnosticsCapped || graph.warnings.length > 0 || graph.unavailable.length > 0) && (
          <div role="status" aria-live="polite" style={{ flex: "none", padding: "5px 14px", borderBottom: "1px solid var(--line2)", color: graph.truncated || diagnosticsCapped ? "var(--warning)" : "var(--txt2)", background: "var(--tint2)", fontSize: 8, lineHeight: 1.45, overflowWrap: "anywhere" }}>
            {mapCapped && <span>SIZE CAP · Showing an interaction-safe page of {graph.returned_node_count} of {graph.node_count} nodes and {graph.returned_edge_count} of {graph.edge_count} edges (up to {PAGE_LIMIT} nodes). Focus a node to inspect its bounded neighborhood. </span>}
            {diagnosticsCapped && <span>DIAGNOSTIC CAP · Core returned {graph.orphan_keys.length} of {graph.orphan_count} orphan keys, {graph.weak_links.length} of {graph.weak_link_count} weak links, and {graph.hidden_edges.length} of {graph.hidden_edge_count} hidden edges. </span>}
            {graph.truncated && !mapCapped && !diagnosticsCapped && <span>BOUNDED RESPONSE · Core indicated additional graph data was omitted. </span>}
            {graph.warnings.map((warning) => <span key={warning}>WARNING · {warning} </span>)}
            {graph.unavailable.length > 0 && <span>DEFERRED SOURCES · {graph.unavailable.join(", ")}</span>}
          </div>
        )}

        {(mutationStatus || mutationError) && (
          <div
            role={mutationError ? "alert" : "status"}
            aria-live="polite"
            style={{ flex: "none", display: "flex", alignItems: "center", gap: 8, padding: "6px 14px", borderBottom: "1px solid var(--line2)", color: mutationError ? "var(--blocking)" : "var(--green)", background: "var(--tint2)", fontSize: 8.5, lineHeight: 1.45, overflowWrap: "anywhere" }}
          >
            <span>{mutationError || mutationStatus}</span>
            {mutationError && !busy && (
              <button type="button" onClick={() => setMutationError("")} style={{ ...activeControl, marginLeft: "auto", flex: "none" }}>DISMISS MESSAGE</button>
            )}
          </div>
        )}

        {review && (
          <section
            ref={reviewDialogRef}
            role="dialog"
            aria-modal="false"
            aria-labelledby="knowledge-graph-edge-review-title"
            aria-describedby="knowledge-graph-edge-review-effect"
            aria-busy={Boolean(busy)}
            data-knowledge-graph-edge-review={review.intent.kind}
            tabIndex={-1}
            onKeyDown={(event) => {
              if (event.key === "Escape" && !busy) {
                event.preventDefault();
                cancelEdgeReview();
              }
            }}
            style={{ flex: "none", borderBottom: "1px solid var(--line-cy)", background: "var(--panel2)", padding: "10px 14px", color: "var(--txt2)", fontSize: 9, lineHeight: 1.45, overflowWrap: "anywhere", outline: "none" }}
          >
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: 8 }}>
              <strong id="knowledge-graph-edge-review-title" style={{ color: "var(--strong)", fontFamily: "'Chakra Petch'", letterSpacing: ".12em" }}>REVIEW · {actionLabel(review.intent.kind)}</strong>
              <span style={{ color: "var(--accent)" }}>{reviewSourceLabel} → {reviewTargetLabel}</span>
              <span style={{ color: "var(--txt3)" }}>TYPE · {review.edge.edge_type.replaceAll("_", " ")} · CONFIDENCE · {review.edge.confidence}</span>
            </div>
            <div style={{ marginTop: 4 }}>
              <span style={{ color: "var(--txt3)" }}>SOURCE SYSTEM · {review.edge.source_system.replaceAll("_", " ")} · PROVENANCE · {review.edge.provenance || "not provided"}</span>
              <span style={{ display: "block" }}>EXPLANATION · {review.edge.explanation || "not provided"}</span>
              <span style={{ display: "block" }}>CURRENT REVIEW STATE · {review.edge.is_hidden ? "hidden" : "visible"} · {review.edge.is_user_confirmed ? "user-confirmed" : "not user-confirmed"}</span>
            </div>
            <p id="knowledge-graph-edge-review-effect" style={{ margin: "6px 0", color: "var(--warning)" }}>{actionEffect(review.intent.kind)} Nothing changes until you apply this reviewed decision.</p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
              <button type="button" disabled={Boolean(busy)} onClick={cancelEdgeReview} style={{ ...control, cursor: busy ? "default" : "pointer", opacity: busy ? 0.55 : 1 }}>CANCEL</button>
              <button
                type="button"
                disabled={Boolean(busy)}
                aria-label={review.retryReady ? `Retry same reviewed ${actionLabel(review.intent.kind).toLowerCase()} proposal` : `Apply reviewed ${actionLabel(review.intent.kind).toLowerCase()}`}
                onClick={() => void runReviewedEdgeAction()}
                style={{ ...activeControl, opacity: busy ? 0.55 : 1, cursor: busy ? "default" : "pointer" }}
              >
                {busy ? "WORKING…" : review.retryReady ? "RETRY SAME PROPOSAL" : `APPLY ${actionLabel(review.intent.kind)}`}
              </button>
              {review.retryReady && review.command && <span role="status" style={{ alignSelf: "center", color: "var(--txt3)" }}>Retry preserves the exact reviewed command and Idempotency-Key.</span>}
            </div>
          </section>
        )}

        <div
          data-knowledge-graph-scroll-region="true"
          role="region"
          tabIndex={0}
          aria-label="Scrollable Knowledge Graph workspace"
          style={{ flex: 1, minHeight: 0, overflowX: "auto", overflowY: "hidden" }}
        >
          <div style={{ display: "flex", width: "100%", minWidth: 920, height: "100%", minHeight: 0 }}>
          <aside aria-label="Knowledge Graph filters" style={{ width: 196, flex: "none", borderRight: "1px solid var(--line)", background: "var(--panel2)", overflowY: "auto", padding: "12px 11px" }}>
            <div data-graph-view-description={viewMode} style={{ border: "1px solid var(--line2)", background: "var(--tint)", padding: "8px 9px", marginBottom: 13 }}>
              <span style={{ display: "block", color: "var(--accent)", fontSize: 7.5, letterSpacing: ".14em" }}>{GRAPH_VIEW_META[viewMode].shortLabel.toUpperCase()}</span>
              <span style={{ display: "block", marginTop: 4, color: "var(--txt2)", fontSize: 8.5, lineHeight: 1.4 }}>{GRAPH_VIEW_META[viewMode].description}</span>
              <span style={{ display: "block", marginTop: 5, color: includeInferred ? "var(--warning)" : "var(--green)", fontSize: 7.5 }}>{includeInferred ? "INFERRED + CONFIRMED EVIDENCE" : "CONFIRMED EVIDENCE ONLY"}</span>
            </div>
            <fieldset disabled={interactionLocked} style={{ border: 0, padding: 0, margin: 0, opacity: interactionLocked ? 0.55 : 1 }}>
              <legend style={{ fontSize: 7.5, letterSpacing: ".2em", color: "var(--txt3)", marginBottom: 8 }}>NODE TYPES</legend>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {nodeTypes.length === 0 && <span style={{ fontSize: 8.5, color: "var(--txt3)" }}>No node types loaded</span>}
                {nodeTypes.map(([nodeType, count]) => {
                  const meta = metaOf(nodeType);
                  const visible = !hiddenNodeTypes.has(nodeType);
                  return (
                    <button key={nodeType} type="button" aria-pressed={visible} aria-label={`${visible ? "Hide" : "Show"} ${meta.label} nodes`} onClick={() => toggleNodeType(nodeType)} style={{ width: "100%", border: 0, background: "transparent", padding: "2px 0", color: visible ? "var(--txt)" : "var(--txt3)", font: "inherit", fontSize: 9, display: "flex", alignItems: "center", gap: 7, cursor: "pointer" }}>
                      <span aria-hidden="true" style={{ width: 9, height: 9, border: `1px solid ${meta.color}`, background: visible ? meta.color : "transparent" }} />
                      <span aria-hidden="true" style={{ color: meta.color }}>{meta.icon}</span>
                      <span>{meta.label}</span><span style={{ marginLeft: "auto", color: "var(--txt3)" }}>{count}</span>
                    </button>
                  );
                })}
              </div>
            </fieldset>

            <fieldset disabled={interactionLocked} style={{ border: 0, padding: 0, margin: "15px 0 0", opacity: interactionLocked ? 0.55 : 1 }}>
              <legend style={{ fontSize: 7.5, letterSpacing: ".2em", color: "var(--txt3)", marginBottom: 8 }}>EDGE FILTERS</legend>
              <label style={{ display: "flex", flexDirection: "column", gap: 4, color: "var(--txt2)", fontSize: 8, marginBottom: 9 }}>
                MINIMUM CONFIDENCE
                <select aria-label="Minimum edge confidence" value={confidenceMin} onChange={(event) => setConfidenceMin(event.currentTarget.value as GraphConfidence)} style={{ ...control, width: "100%" }}>
                  <option value="unknown">All confidence</option>
                  <option value="possible">Possible+</option>
                  <option value="likely">Likely+</option>
                  <option value="confirmed">Confirmed confidence</option>
                </select>
              </label>
              <label style={{ display: "flex", flexDirection: "column", gap: 4, color: "var(--txt2)", fontSize: 8, marginBottom: 9 }}>
                SOURCE SYSTEM
                <select aria-label="Edge source system" value={sourceSystem} onChange={(event) => setSourceSystem(event.currentTarget.value)} style={{ ...control, width: "100%" }}>
                  <option value="all">All sources</option>
                  {sourceSystems.map((source) => <option key={source} value={source}>{source.replaceAll("_", " ")}</option>)}
                </select>
              </label>
            </fieldset>

            <fieldset disabled={interactionLocked} style={{ border: 0, borderTop: "1px solid var(--line2)", padding: "13px 0 0", margin: "15px 0 0", opacity: interactionLocked ? 0.55 : 1 }}>
              <legend style={{ fontSize: 7.5, letterSpacing: ".2em", color: "var(--txt3)", marginBottom: 8 }}>VISUAL OVERLAYS</legend>
              <span style={{ display: "block", color: "var(--txt2)", fontSize: 8, marginBottom: 5 }}>NODE SIZING</span>
              <div role="group" aria-label="Knowledge Graph node sizing" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4 }}>
                <button
                  type="button"
                  disabled={interactionLocked}
                  aria-pressed={nodeSizing === "story_gravity"}
                  aria-label="Size Knowledge Graph nodes by Story Gravity"
                  onClick={() => setNodeSizing("story_gravity")}
                  style={{ ...(nodeSizing === "story_gravity" ? activeControl : control), cursor: interactionLocked ? "default" : "pointer", padding: "5px 3px" }}
                >
                  STORY GRAVITY
                </button>
                <button
                  type="button"
                  disabled={interactionLocked}
                  aria-pressed={nodeSizing === "view_links"}
                  aria-label="Size Knowledge Graph nodes by view links"
                  onClick={() => setNodeSizing("view_links")}
                  style={{ ...(nodeSizing === "view_links" ? activeControl : control), cursor: interactionLocked ? "default" : "pointer", padding: "5px 3px" }}
                >
                  VIEW LINKS
                </button>
              </div>
              <span style={{ display: "block", minHeight: 24, marginTop: 5, color: nodeSizing === "story_gravity" && graph && !graph.story_gravity_available ? "var(--warning)" : "var(--txt3)", fontSize: 7.5, lineHeight: 1.4 }}>
                {nodeSizing === "story_gravity"
                  ? graph
                    ? graph.story_gravity_available
                      ? `${gravityMappedNodeCount} of ${view?.nodes.length ?? 0} visible nodes have project-wide Story Gravity.`
                      : "Story Gravity is unavailable; node size falls back to view-scoped links."
                    : "Story Gravity waits for the active graph view."
                  : "Node size reflects links in the complete selected view."}
              </span>
              <button
                type="button"
                disabled={interactionLocked}
                aria-pressed={storyOrderFlow}
                aria-label={`${storyOrderFlow ? "Hide" : "Show"} returned story-order flow`}
                onClick={() => setStoryOrderFlow((current) => !current)}
                style={{ ...(storyOrderFlow ? activeControl : control), width: "100%", marginTop: 8, cursor: interactionLocked ? "default" : "pointer" }}
              >
                STORY-ORDER FLOW · {storyOrderFlow ? "ON" : "OFF"}
              </button>
              {storyOrderFlow && (
                <span role="status" aria-live="polite" style={{ display: "block", marginTop: 5, color: flowSegments.length > 0 ? "var(--txt3)" : "var(--warning)", fontSize: 7.5, lineHeight: 1.4 }}>
                  {flowSegments.length > 0
                    ? `${flowSegments.length} returned active-scope order segment${flowSegments.length === 1 ? "" : "s"}${flowGapCount > 0 ? ` · ${flowGapCount} visible gap${flowGapCount === 1 ? "" : "s"}` : ""}. Manuscript order, not causality.`
                    : graph
                      ? "No returned story-order segments match this view, evidence scope, focus, and manual filters."
                      : "Story-order flow waits for the active graph view."}
                </span>
              )}
            </fieldset>
          </aside>

          <main aria-label="Narrative Knowledge Graph canvas" style={{ flex: 1, minWidth: 0, position: "relative", overflow: "auto", display: "grid", placeItems: "center" }}>
            {projectId == null ? (
              <Message>Open a project to build its narrative map.</Message>
            ) : loading && !graph ? (
              <Message role="status">Building the canonical {GRAPH_VIEW_META[viewMode].shortLabel} view…</Message>
            ) : error ? (
              <Message role="alert">
                <div>
                  <div>Couldn&apos;t load the {GRAPH_VIEW_META[viewMode].shortLabel} view — {error}</div>
                  <button type="button" onClick={refetch} style={{ ...activeControl, marginTop: 10 }}>RETRY LOAD</button>
                </div>
              </Message>
            ) : !graph ? (
              <Message>{GRAPH_VIEW_META[viewMode].shortLabel} view unavailable.</Message>
            ) : graph.nodes.length === 0 ? (
              <Message>{GRAPH_VIEW_META[viewMode].empty}</Message>
            ) : !view || view.nodes.length === 0 ? (
              <Message>No nodes in this {GRAPH_VIEW_META[viewMode].shortLabel} view match the manual filters.</Message>
            ) : (
              <div data-knowledge-graph-canvas="true" data-project-id={graph.project_id} data-focus-key={graph.focus_key ?? ""} data-view-mode={graph.view_mode} data-evidence-scope={graph.include_inferred ? "inferred_and_confirmed" : "confirmed_only"} data-node-sizing={effectiveNodeSizing} data-story-order-flow={storyOrderFlow ? "on" : "off"} style={{ position: "relative", width: CW, height: CH, flex: "none" }}>
                <svg aria-hidden="true" viewBox={`0 0 ${CW} ${CH}`} width={CW} height={CH} style={{ position: "absolute", inset: 0, zIndex: 1 }}>
                  <defs>
                    <marker id={`${markerPrefix}-evidence-arrow`} markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6" fill="none" stroke="var(--txt3)" strokeWidth="1.1" /></marker>
                    {(Object.entries(STORY_ORDER_COLORS) as Array<[StoryOrderBand, string]>).map(([band, color]) => (
                      <marker key={band} id={`${markerPrefix}-story-order-${band}`} markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 Z" fill={color} /></marker>
                    ))}
                  </defs>
                  {storyOrderFlow && flowSegments.length > 0 && (
                    <g data-story-order-flow-overlay="true">
                      {flowSegments.map((segment) => {
                        const from = positions.get(segment.source);
                        const to = positions.get(segment.target);
                        if (!from || !to) return null;
                        const sourceLabel = view.nodeByKey.get(segment.source)?.label || segment.source;
                        const targetLabel = view.nodeByKey.get(segment.target)?.label || segment.target;
                        const color = STORY_ORDER_COLORS[segment.band];
                        const dash = segment.actBoundary && segment.gapBefore
                          ? "10 3 2 3"
                          : segment.actBoundary
                            ? "10 4"
                            : segment.gapBefore
                              ? "2 5"
                              : undefined;
                        return (
                          <path
                            key={`story-order-${graphEdgeKey(segment.edge)}`}
                            data-story-order-segment={segment.orderIndex}
                            data-story-order-band={segment.band}
                            data-act-boundary={segment.actBoundary ? "true" : "false"}
                            data-flow-gap-before={segment.gapBefore ? "true" : "false"}
                            d={storyOrderFlowPath(from, to, segment.orderIndex)}
                            fill="none"
                            stroke={color}
                            strokeWidth={segment.actBoundary ? 3.2 : 2.5}
                            strokeDasharray={dash}
                            opacity={0.72}
                            markerEnd={`url(#${markerPrefix}-story-order-${segment.band})`}
                          >
                            <title>{`${sourceLabel} → ${targetLabel} · manuscript order ${segment.orderIndex + 1} of ${segment.orderTotal - 1} · ${segment.band}${segment.actBoundary ? " · act boundary" : ""}${segment.gapBefore ? " · preceding returned gap" : ""}`}</title>
                          </path>
                        );
                      })}
                    </g>
                  )}
                  {view.edges.map((edge) => {
                    const from = positions.get(edge.source);
                    const to = positions.get(edge.target);
                    if (!from || !to) return null;
                    const hot = selected && (edge.source === selected.key || edge.target === selected.key);
                    const weak = edge.is_inferred || edge.confidence === "possible" || edge.confidence === "unknown";
                    const edgeColor = edge.edge_type === "contradicts"
                      ? "var(--blocking)"
                      : edge.edge_type === "risks"
                        ? "var(--warning)"
                        : weak
                          ? "var(--warning)"
                          : "var(--txt3)";
                    return (
                      <g key={graphEdgeKey(edge)} opacity={hot ? 1 : 0.48}>
                        <title>{edgeTitle(edge, view.nodeByKey)}</title>
                        <line x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke={hot ? "var(--accent)" : edgeColor} strokeWidth={hot ? 1.8 : 1.1} strokeDasharray={weak ? "5 4" : undefined} markerEnd={`url(#${markerPrefix}-evidence-arrow)`} />
                        {hot && <text x={(from.x + to.x) / 2} y={(from.y + to.y) / 2 - 4} textAnchor="middle" fontSize="8" fill="var(--accent)">{edge.edge_type.replaceAll("_", " ")}</text>}
                      </g>
                    );
                  })}
                </svg>
                {view.nodes.map((node) => {
                  const position = positions.get(node.key) ?? { x: CW / 2, y: CH / 2 };
                  const meta = metaOf(node.node_type);
                  const selectedNode = selected?.key === node.key;
                  const focusedNode = graph.focus_key === node.key;
                  const sizing = knowledgeGraphNodeSize(
                    node,
                    nodeSizing,
                    graph.story_gravity_available,
                    maxDegree,
                  );
                  const size = sizing.size;
                  const gravityHalo = sizing.basis === "story_gravity"
                    && sizing.gravity !== null
                    && sizing.gravity >= 0.55;
                  const sizeBasisLabel = sizing.basis === "story_gravity"
                    ? sizing.gravity === null
                      ? "Story Gravity not mapped, neutral size"
                      : `Story Gravity ${Math.round(sizing.gravity * 100)} percent`
                    : nodeSizing === "story_gravity"
                      ? `${node.degree} view-scoped links, Story Gravity unavailable`
                      : `${node.degree} view-scoped links`;
                  return (
                    <button
                      key={node.key}
                      type="button"
                      data-graph-node-key={node.key}
                      data-node-size-basis={sizing.basis}
                      data-story-gravity={sizing.gravity ?? ""}
                      aria-pressed={selectedNode}
                      disabled={interactionLocked}
                      aria-label={`Select ${node.label || node.key}, ${meta.label}, ${node.degree} connections, node size by ${sizeBasisLabel}`}
                      onClick={() => chooseNode(node)}
                      style={{ position: "absolute", left: position.x, top: position.y, transform: "translate(-50%,-50%)", zIndex: selectedNode ? 4 : 3, width: 80, minHeight: 76, border: 0, background: "transparent", padding: 0, color: "var(--txt)", font: "inherit", textAlign: "center", cursor: interactionLocked ? "default" : "pointer", opacity: interactionLocked && !selectedNode ? 0.65 : 1 }}
                    >
                      {gravityHalo && <span data-story-gravity-halo="true" aria-hidden="true" style={{ position: "absolute", pointerEvents: "none", left: "50%", top: size / 2, transform: "translate(-50%,-50%)", width: size + 12, height: size + 12, borderRadius: "50%", background: meta.color, opacity: Math.min(0.28, 0.1 + ((sizing.gravity ?? 0) - 0.55) * 0.4), boxShadow: `0 0 18px ${meta.color}` }} />}
                      {(selectedNode || focusedNode) && <span aria-hidden="true" style={{ position: "absolute", pointerEvents: "none", left: "50%", top: size / 2, transform: "translate(-50%,-50%)", width: size + 16, height: size + 16, borderRadius: "50%", border: `1px solid ${meta.color}`, boxShadow: `0 0 16px ${meta.color}` }} />}
                      <span aria-hidden="true" style={{ position: "relative", margin: "0 auto", width: size, height: size, borderRadius: "50%", border: `${selectedNode ? 2.5 : 1.5}px solid ${meta.color}`, background: "var(--tint)", display: "grid", placeItems: "center", color: meta.color, fontSize: Math.max(13, Math.round(size * 0.33)) }}>{meta.icon}</span>
                      <span style={{ display: "block", marginTop: 4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontFamily: "'Chakra Petch'", fontSize: selectedNode ? 11 : 9.5, color: selectedNode ? "var(--strong)" : "var(--txt)" }}>{node.label || node.key}</span>
                      <span style={{ display: "block", fontSize: 6.5, color: focusedNode ? "var(--accent)" : "var(--txt3)", letterSpacing: ".08em" }}>{focusedNode ? "FOCUS · " : ""}{node.degree} LINK{node.degree === 1 ? "" : "S"}</span>
                    </button>
                  );
                })}
                <div aria-label="Knowledge Graph visual legend" style={{ position: "absolute", left: 8, bottom: 8, zIndex: 4, display: "flex", flexWrap: "wrap", gap: "4px 10px", maxWidth: "calc(100% - 16px)", border: "1px solid var(--line2)", background: "var(--tint)", padding: "6px 9px", color: "var(--txt2)", fontSize: 7.5 }}>
                  <span>──▸ confirmed evidence</span><span style={{ color: "var(--warning)" }}>┄▸ inferred evidence</span>
                  <span style={{ color: "var(--accent)" }}>
                    {effectiveNodeSizing === "story_gravity"
                      ? `node size = project-wide Story Gravity · ${gravityMappedNodeCount}/${view.nodes.length} mapped · halo ≥ 55%`
                      : nodeSizing === "story_gravity"
                        ? "node size = view-scoped links · Story Gravity unavailable"
                        : "node size = view-scoped links"}
                  </span>
                  {storyOrderFlow && <span style={{ color: "var(--green)" }}>curved arrows = returned manuscript order, not causality · {flowSegments.length} segment{flowSegments.length === 1 ? "" : "s"}</span>}
                </div>
              </div>
            )}
          </main>

          <aside aria-label="Knowledge Graph inspector and diagnostics" style={{ width: 332, flex: "none", borderLeft: "1px solid var(--line)", background: "var(--panel2)", display: "flex", flexDirection: "column", overflow: "hidden" }}>
            <div style={{ flex: "none", minHeight: 30, display: "flex", alignItems: "center", padding: "5px 12px", borderBottom: "1px solid var(--line)", color: "var(--accent)", fontSize: 8.5, letterSpacing: ".18em" }}>INSPECTOR · TRACEABLE SOURCES</div>
            {selected ? (
              <section aria-label={`Selected graph node ${selected.label || selected.key}`} style={{ flex: "none", maxHeight: "46%", overflow: "auto", overflowWrap: "anywhere", padding: 12, borderBottom: "1px solid var(--line2)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
                  <span aria-hidden="true" style={{ width: 30, height: 30, display: "grid", placeItems: "center", border: `1px solid ${metaOf(selected.node_type).color}`, color: metaOf(selected.node_type).color }}>{metaOf(selected.node_type).icon}</span>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ color: "var(--strong)", fontFamily: "'Chakra Petch'", fontSize: 14, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{selected.label || selected.key}</div>
                    <div style={{ color: "var(--txt3)", fontSize: 7.5, letterSpacing: ".08em" }}>{metaOf(selected.node_type).label.toUpperCase()} · {selected.degree} VIEW-SCOPED LINKS</div>
                  </div>
                </div>
                {selected.summary && <p style={{ margin: "9px 0", color: "var(--txt2)", fontSize: 9.5, lineHeight: 1.45 }}>{selected.summary}</p>}
                <div style={{ display: "flex", flexWrap: "wrap", gap: 5, margin: "9px 0" }}>
                  <span style={{ ...control, padding: "2px 5px" }}>SOURCE · {selected.source_type || "derived"}</span>
                  <span style={{ ...control, padding: "2px 5px" }}>VISIBLE · {visibleDegree.get(selected.key) ?? 0}</span>
                  <span data-selected-node-size-basis={selectedSizing?.basis} style={{ ...control, padding: "2px 5px", color: "var(--accent)" }}>
                    NODE SIZE · {selectedSizing?.basis === "story_gravity" ? "STORY GRAVITY" : nodeSizing === "story_gravity" ? "VIEW LINKS · GRAVITY FALLBACK" : "VIEW LINKS"}
                  </span>
                  {graph?.story_gravity_available && (
                    <span data-selected-story-gravity={selected.story_gravity ?? ""} style={{ ...control, padding: "2px 5px", color: selected.story_gravity === null ? "var(--txt3)" : "var(--green)" }}>
                      STORY GRAVITY · {selected.story_gravity === null
                        ? selectedSizing?.basis === "story_gravity"
                          ? "NOT MAPPED · NEUTRAL SIZE"
                          : "NOT MAPPED"
                        : `${Math.round(selected.story_gravity * 100)}%`}
                    </span>
                  )}
                </div>
                {graph?.focus_key === selected.key ? (
                  <div role="status" style={{ ...control, width: "100%", boxSizing: "border-box", color: "var(--accent)", textAlign: "center" }}>FOCUS ROOT · {depth}-HOP NEIGHBORHOOD</div>
                ) : (
                  <button type="button" disabled={interactionLocked} aria-label={`Focus graph on ${selected.label || selected.key}`} onClick={() => setFocusKey(selected.key)} style={{ ...activeControl, width: "100%", opacity: interactionLocked ? 0.55 : 1 }}>FOCUS {depth}-HOP NEIGHBORHOOD</button>
                )}
                <div style={{ marginTop: 10, color: "var(--txt3)", fontSize: 7.5, letterSpacing: ".14em" }}>VISIBLE CONNECTIONS · SHOWING {displayedConnections.length} OF {selectedEdges.length}</div>
                {selectedEdges.length === 0 ? <p style={{ color: "var(--txt3)", fontSize: 9 }}>None under the current edge filters.</p> : displayedConnections.map((edge) => {
                  const otherKey = edge.source === selected.key ? edge.target : edge.source;
                  const other = view?.nodeByKey.get(otherKey);
                  const outgoing = edge.source === selected.key;
                  const direction = outgoing ? "OUTGOING TO" : "INCOMING FROM";
                  const description = edgeInspectionLabel(edge, selected.key, view?.nodeByKey ?? new Map<string, KnowledgeGraphNodeDTO>());
                  const sourceLabel = graphNodeByKey.get(edge.source)?.label || edge.source;
                  const targetLabel = graphNodeByKey.get(edge.target)?.label || edge.target;
                  const edgeActionLabel = `${sourceLabel} to ${targetLabel} ${edge.edge_type.replaceAll("_", " ")} edge`;
                  return (
                    <div data-graph-connection="true" key={graphEdgeKey(edge)} aria-label={description} style={{ width: "100%", boxSizing: "border-box", border: "1px solid var(--line2)", background: "var(--tint)", padding: "6px 7px", marginTop: 5, color: "var(--txt2)", fontSize: 8.5, overflowWrap: "anywhere" }}>
                      <span style={{ display: "block", color: "var(--strong)", fontSize: 9 }}>{outgoing ? "→" : "←"} {direction} · {other?.label || otherKey}</span>
                      <span style={{ display: "block", marginTop: 3, color: "var(--accent)" }}>TYPE · {edge.edge_type.replaceAll("_", " ")} · CONFIDENCE · {edge.confidence}</span>
                      <span style={{ display: "block", color: "var(--txt3)" }}>SOURCE SYSTEM · {edge.source_system.replaceAll("_", " ")}</span>
                      <span style={{ display: "block", color: "var(--txt3)" }}>PROVENANCE · {edge.provenance || "not provided"}</span>
                      <span style={{ display: "block", color: "var(--txt2)" }}>EXPLANATION · {edge.explanation || "not provided"}</span>
                      <span style={{ display: "block", color: edge.is_user_confirmed ? "var(--green)" : "var(--txt3)" }}>REVIEW STATE · {edge.is_user_confirmed ? "USER-CONFIRMED" : edge.is_inferred ? "INFERRED" : "SOURCE-DERIVED"}</span>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 6 }}>
                        {other && <button type="button" disabled={interactionLocked} aria-label={`${description}. Select connected node.`} onClick={() => chooseNode(other)} style={{ ...control, cursor: interactionLocked ? "default" : "pointer", opacity: interactionLocked ? 0.55 : 1 }}>SELECT NODE</button>}
                        {edge.is_inferred && !edge.is_user_confirmed && (
                          <button type="button" disabled={interactionLocked} aria-label={`Review confirmation of ${edgeActionLabel}`} onClick={(event) => beginEdgeReview("confirm_edge", edge, event.currentTarget)} style={{ ...activeControl, opacity: interactionLocked ? 0.55 : 1 }}>REVIEW CONFIRM</button>
                        )}
                        {edge.is_inferred && !edge.is_user_confirmed && (
                          <button type="button" disabled={interactionLocked} aria-label={`Review hiding ${edgeActionLabel}`} onClick={(event) => beginEdgeReview("hide_edge", edge, event.currentTarget)} style={{ ...activeControl, borderColor: "var(--warning)", color: "var(--warning)", opacity: interactionLocked ? 0.55 : 1 }}>REVIEW HIDE</button>
                        )}
                      </div>
                    </div>
                  );
                })}
                {selectedEdges.length > 12 && (
                  <button type="button" disabled={interactionLocked} aria-expanded={connectionsExpanded} aria-label={connectionsExpanded ? "Show fewer visible connections" : `Show all ${selectedEdges.length} visible connections`} onClick={() => setConnectionsExpanded((current) => !current)} style={{ ...activeControl, width: "100%", marginTop: 6, opacity: interactionLocked ? 0.55 : 1 }}>
                    {connectionsExpanded ? "SHOW FEWER CONNECTIONS" : `SHOW ALL ${selectedEdges.length} CONNECTIONS`}
                  </button>
                )}
              </section>
            ) : <Message>Select a node to inspect its neighborhood.</Message>}

            <section aria-label="Graph diagnostics" style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: 12 }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 7, marginBottom: 8 }}><span style={{ fontFamily: "'Chakra Petch'", color: "var(--strong)", fontSize: 11, letterSpacing: ".1em" }}>DIAGNOSTICS</span><span style={{ marginLeft: "auto", color: "var(--txt3)", fontSize: 7 }}>CORE-DERIVED</span></div>
              {!graph ? (
                <InsightCard label="WAITING" tone="var(--txt3)">Diagnostics become available after the active graph view finishes loading.</InsightCard>
              ) : graph.story_diagnostics_available ? (
                <>
              {(graph?.orphan_count ?? 0) === 0 && (graph?.weak_link_count ?? 0) === 0 && (graph?.hidden_edge_count ?? 0) === 0 ? (
                <InsightCard label="CONNECTED" tone="var(--green)">No orphan, weak-link, or hidden-edge diagnostics in this graph view.</InsightCard>
              ) : null}
              {(graph?.orphan_count ?? 0) > 0 && (
                <div style={{ marginBottom: 9 }}>
                  <div style={{ color: "var(--warning)", fontSize: 7.5, letterSpacing: ".14em", marginBottom: 5 }}>ORPHANS · SHOWING {displayedOrphans.length} OF {orphanNodes.length} MATCHING · {graph?.orphan_keys.length ?? 0} CORE RETURNED · {graph?.orphan_count} QUERY TOTAL</div>
                  {displayedOrphans.map((node) => (
                    <InsightCard key={node.key} label={metaOf(node.node_type).label.toUpperCase()} tone="var(--warning)" ariaLabel={`Select orphan node ${node.label || node.key}`} disabled={interactionLocked} onClick={() => chooseNode(node)}>{node.label || node.key}</InsightCard>
                  ))}
                  {orphanNodes.length === 0 && <div style={{ color: "var(--txt3)", fontSize: 8 }}>No returned orphan nodes match the active node-type filters.</div>}
                  {orphanNodes.length > 8 && (
                    <button type="button" disabled={interactionLocked} aria-expanded={orphansExpanded} aria-label={orphansExpanded ? "Show fewer matching orphan nodes" : `Show all ${orphanNodes.length} matching orphan nodes`} onClick={() => setOrphansExpanded((current) => !current)} style={{ ...activeControl, width: "100%", marginBottom: 5, opacity: interactionLocked ? 0.55 : 1 }}>
                      {orphansExpanded ? "SHOW FEWER ORPHANS" : `SHOW ALL ${orphanNodes.length} ORPHANS`}
                    </button>
                  )}
                  {graph && graph.orphan_keys.length > orphanNodes.length && <div style={{ color: "var(--txt3)", fontSize: 8 }}>{orphanNodes.length} of {graph.orphan_keys.length} Core-returned orphan nodes match the active node-type filters.</div>}
                  {graph && graph.orphan_count > graph.orphan_keys.length && <div style={{ color: "var(--txt3)", fontSize: 8 }}>Core returned {graph.orphan_keys.length} of {graph.orphan_count} orphan keys for this bounded query.</div>}
                </div>
              )}
              {(graph?.weak_link_count ?? 0) > 0 && (
                <div style={{ marginBottom: 9 }}>
                  <div style={{ color: "var(--warning)", fontSize: 7.5, letterSpacing: ".14em", marginBottom: 5 }}>WEAK LINKS · SHOWING {displayedWeakLinks.length} OF {weakLinks.length} MATCHING · {graph?.weak_links.length ?? 0} CORE RETURNED · {graph?.weak_link_count} QUERY TOTAL</div>
                  {displayedWeakLinks.map((edge) => {
                    const source = view?.nodeByKey.get(edge.source);
                    const target = view?.nodeByKey.get(edge.target);
                    const sourceLabel = source?.label || edge.source;
                    const targetLabel = target?.label || edge.target;
                    return (
                      <InsightCard key={`weak-${graphEdgeKey(edge)}`} label={`${edge.confidence.toUpperCase()} · ${edge.source_system.replaceAll("_", " ").toUpperCase()}`} tone="var(--warning)" ariaLabel={`Weak link from ${sourceLabel} to ${targetLabel}. Type ${edge.edge_type.replaceAll("_", " ")}. Confidence ${edge.confidence}. Source system ${edge.source_system.replaceAll("_", " ")}. Provenance ${edge.provenance || "not provided"}. Explanation ${edge.explanation || "not provided"}. Select source node.`} disabled={interactionLocked} onClick={() => source && chooseNode(source)}>
                        <span style={{ display: "block" }}>{sourceLabel} → {targetLabel}</span>
                        <span style={{ display: "block", color: "var(--txt3)" }}>TYPE · {edge.edge_type.replaceAll("_", " ")} · CONFIDENCE · {edge.confidence}</span>
                        <span style={{ display: "block", color: "var(--txt3)" }}>SOURCE SYSTEM · {edge.source_system.replaceAll("_", " ")}</span>
                        <span style={{ display: "block", color: "var(--txt3)" }}>PROVENANCE · {edge.provenance || "not provided"}</span>
                        <span style={{ display: "block", color: "var(--txt2)" }}>EXPLANATION · {edge.explanation || "not provided"}</span>
                      </InsightCard>
                    );
                  })}
                  {weakLinks.length === 0 && <div style={{ color: "var(--txt3)", fontSize: 8 }}>No returned weak links match the active edge filters.</div>}
                  {weakLinks.length > 8 && (
                    <button type="button" disabled={interactionLocked} aria-expanded={weakLinksExpanded} aria-label={weakLinksExpanded ? "Show fewer matching weak links" : `Show all ${weakLinks.length} matching weak links`} onClick={() => setWeakLinksExpanded((current) => !current)} style={{ ...activeControl, width: "100%", marginTop: 1, opacity: interactionLocked ? 0.55 : 1 }}>
                      {weakLinksExpanded ? "SHOW FEWER WEAK LINKS" : `SHOW ALL ${weakLinks.length} WEAK LINKS`}
                    </button>
                  )}
                  {graph && graph.weak_links.length > weakLinks.length && <div style={{ color: "var(--txt3)", fontSize: 8, marginTop: 5 }}>{weakLinks.length} of {graph.weak_links.length} Core-returned weak links match the active edge filters.</div>}
                  {graph && graph.weak_link_count > graph.weak_links.length && <div style={{ color: "var(--txt3)", fontSize: 8, marginTop: 5 }}>Core returned {graph.weak_links.length} of {graph.weak_link_count} weak links for this bounded query.</div>}
                </div>
              )}
                </>
              ) : (
                <InsightCard label="VIEW-SCOPED" tone="var(--accent)">Orphan and weak-link diagnostics belong to Project Map. This specialized view reports only its traceable evidence; zero rows must not be read as “connected” or “risk-free.”</InsightCard>
              )}
              {((graph?.hidden_edge_count ?? 0) > 0 || (hiddenReviewPage?.hidden_edge_count ?? 0) > 0) && (
                <div>
                  <div style={{ color: "var(--warning)", fontSize: 7.5, letterSpacing: ".14em", marginBottom: 5 }}>HIDDEN EDGES · SHOWING {displayedHiddenEdges.length} OF {hiddenEdges.length} {hiddenReviewOpen ? "ON THIS QUEUE PAGE" : "CORE RETURNED"} · {hiddenReviewPage?.hidden_edge_count ?? graph?.hidden_edge_count} PROJECT TOTAL</div>
                  {!hiddenReviewOpen ? (
                    <button type="button" disabled={interactionLocked} aria-label="Open the complete hidden edge review queue" onClick={() => { setHiddenReviewOffset(0); setHiddenReviewOpen(true); }} style={{ ...activeControl, width: "100%", marginBottom: 6, opacity: interactionLocked ? 0.55 : 1 }}>OPEN COMPLETE HIDDEN REVIEW QUEUE</button>
                  ) : (
                    <button type="button" disabled={interactionLocked} aria-label="Close the complete hidden edge review queue" onClick={() => { setHiddenReviewOpen(false); setHiddenReviewOffset(0); }} style={{ ...control, width: "100%", marginBottom: 6, cursor: interactionLocked ? "default" : "pointer", opacity: interactionLocked ? 0.55 : 1 }}>CLOSE HIDDEN REVIEW QUEUE</button>
                  )}
                  {hiddenReviewOpen && hiddenReviewResource.loading && !hiddenReviewPage && <div role="status" aria-live="polite" style={{ color: "var(--txt3)", fontSize: 8, marginBottom: 6 }}>Loading hidden edge review queue…</div>}
                  {hiddenReviewOpen && hiddenReviewResource.error && <div role="alert" style={{ color: "var(--blocking)", fontSize: 8, marginBottom: 6 }}>Couldn&apos;t load hidden edge reviews — {hiddenReviewResource.error} <button type="button" disabled={interactionLocked} onClick={hiddenReviewResource.refetch} style={{ ...activeControl, marginLeft: 5 }}>RETRY QUEUE</button></div>}
                  {displayedHiddenEdges.map((edge) => {
                    const sourceLabel = hiddenReviewNodeByKey.get(edge.source)?.label || graphNodeByKey.get(edge.source)?.label || edge.source;
                    const targetLabel = hiddenReviewNodeByKey.get(edge.target)?.label || graphNodeByKey.get(edge.target)?.label || edge.target;
                    const readableType = edge.edge_type.replaceAll("_", " ");
                    return (
                      <div key={`hidden-${graphEdgeKey(edge)}`} data-hidden-graph-edge="true" style={{ border: "1px solid var(--line2)", background: "var(--tint)", padding: "8px 9px", marginBottom: 6, color: "var(--txt2)", fontSize: 8.5, lineHeight: 1.4, overflowWrap: "anywhere" }}>
                        <span style={{ display: "block", color: "var(--strong)", fontSize: 9 }}>{sourceLabel} → {targetLabel}</span>
                        <span style={{ display: "block", color: "var(--accent)" }}>TYPE · {readableType} · CONFIDENCE · {edge.confidence}</span>
                        <span style={{ display: "block", color: "var(--txt3)" }}>SOURCE SYSTEM · {edge.source_system.replaceAll("_", " ")}</span>
                        <span style={{ display: "block", color: "var(--txt3)" }}>PROVENANCE · {edge.provenance || "not provided"}</span>
                        <span style={{ display: "block" }}>EXPLANATION · {edge.explanation || "not provided"}</span>
                        <span style={{ display: "block", color: edge.is_user_confirmed ? "var(--green)" : "var(--txt3)" }}>PRESERVED REVIEW STATE · {edge.is_user_confirmed ? "USER-CONFIRMED" : "NOT USER-CONFIRMED"}</span>
                        {hiddenReviewOpen && hiddenReviewPage ? (
                          <button type="button" disabled={interactionLocked} aria-label={`Review restoring ${sourceLabel} to ${targetLabel} ${readableType} edge`} onClick={(event) => beginEdgeReview("unhide_edge", edge, event.currentTarget, hiddenReviewOffset)} style={{ ...activeControl, width: "100%", marginTop: 6, opacity: interactionLocked ? 0.55 : 1 }}>REVIEW RESTORE</button>
                        ) : (
                          <span style={{ display: "block", marginTop: 5, color: "var(--txt3)" }}>Open the complete queue to review restoration against a fresh page revision.</span>
                        )}
                      </div>
                    );
                  })}
                  {hiddenEdges.length === 0 && <div style={{ color: "var(--txt3)", fontSize: 8 }}>{hiddenReviewOpen ? "No hidden edges are present on this queue page." : "Core reports hidden edges, but none fit this bounded map response. Open the complete queue to review them."}</div>}
                  {hiddenEdges.length > 8 && (
                    <button type="button" disabled={interactionLocked} aria-expanded={hiddenEdgesExpanded} aria-label={hiddenEdgesExpanded ? "Show fewer hidden edges" : `Show all ${hiddenEdges.length} returned hidden edges`} onClick={() => setHiddenEdgesExpanded((current) => !current)} style={{ ...activeControl, width: "100%", marginTop: 1, opacity: interactionLocked ? 0.55 : 1 }}>
                      {hiddenEdgesExpanded ? "SHOW FEWER HIDDEN EDGES" : `SHOW ALL ${hiddenEdges.length} HIDDEN EDGES`}
                    </button>
                  )}
                  {hiddenReviewOpen && hiddenReviewPage && (
                    <div style={{ display: "flex", gap: 5, marginTop: 5 }}>
                      <button type="button" disabled={interactionLocked || hiddenReviewOffset === 0} aria-label="Previous hidden edge review page" onClick={() => setHiddenReviewOffset((current) => Math.max(0, current - HIDDEN_EDGE_PAGE_LIMIT))} style={{ ...activeControl, flex: 1, opacity: interactionLocked || hiddenReviewOffset === 0 ? 0.45 : 1 }}>PREVIOUS</button>
                      <button type="button" disabled={interactionLocked || hiddenReviewOffset + hiddenReviewPage.returned_edge_count >= hiddenReviewPage.hidden_edge_count} aria-label="Next hidden edge review page" onClick={() => setHiddenReviewOffset((current) => current + HIDDEN_EDGE_PAGE_LIMIT)} style={{ ...activeControl, flex: 1, opacity: interactionLocked || hiddenReviewOffset + hiddenReviewPage.returned_edge_count >= hiddenReviewPage.hidden_edge_count ? 0.45 : 1 }}>NEXT</button>
                    </div>
                  )}
                  {hiddenReviewOpen && hiddenReviewPage && <div role="status" style={{ color: "var(--txt3)", fontSize: 8, marginTop: 5 }}>Queue rows {hiddenReviewPage.returned_edge_count === 0 ? 0 : hiddenReviewPage.offset + 1}–{hiddenReviewPage.offset + hiddenReviewPage.returned_edge_count} of {hiddenReviewPage.hidden_edge_count}.</div>}
                  {!hiddenReviewOpen && graph && graph.hidden_edge_count > graph.hidden_edges.length && <div style={{ color: "var(--txt3)", fontSize: 8, marginTop: 5 }}>The active view embeds {graph.hidden_edges.length} of {graph.hidden_edge_count} project-wide hidden edges; the complete paged queue reaches every restore decision.</div>}
                </div>
              )}
            </section>
          </aside>
          </div>
        </div>

        <div style={{ minHeight: 24, flex: "none", borderTop: "1px solid var(--line2)", display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12, padding: "3px 16px", background: "var(--base)", color: "var(--txt3)", fontSize: 8, letterSpacing: ".08em" }}>
          <span style={{ color: "var(--green)" }}>● DETERMINISTIC · REVIEWABLE · TRACEABLE</span>
          <span>{view?.nodes.length ?? 0} / {graph?.node_count ?? 0} NODES</span>
          <span>{view?.edges.length ?? 0} / {graph?.edge_count ?? 0} EDGES</span>
          {!graph
            ? <span style={{ color: "var(--txt3)" }}>DIAGNOSTICS · WAITING FOR ACTIVE VIEW</span>
            : graph.story_diagnostics_available
              ? <span style={{ color: "var(--warning)" }}>{graph.orphan_count} ORPHANS · {graph.weak_link_count} WEAK LINKS · {graph.hidden_edge_count} HIDDEN EDGES</span>
              : <span style={{ color: "var(--txt3)" }}>STORY DIAGNOSTICS · PROJECT MAP ONLY · {graph.hidden_edge_count} HIDDEN EDGES</span>}
          {hiddenNodeTypes.size > 0 && <span>{hiddenNodeTypes.size} NODE TYPE{hiddenNodeTypes.size === 1 ? "" : "S"} HIDDEN</span>}
          <span style={{ marginLeft: "auto", color: "var(--txt2)" }}>{GRAPH_VIEW_META[viewMode].shortLabel} · {includeInferred ? "Inferred + Confirmed" : "Confirmed only"} · {graph?.writing_mode ?? "current project"}</span>
        </div>
      </div>
    </PanelShell>
  );
}
