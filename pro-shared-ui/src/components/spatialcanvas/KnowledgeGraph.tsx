import { useEffect, useMemo, useState, type CSSProperties, type ReactNode } from "react";
import type { KnowledgeGraphEdgeDTO, KnowledgeGraphNodeDTO } from "@logosforge/ui-contracts";
import { useSelection } from "../../adapters/selection";
import { useProjectId } from "../../adapters/StudioProvider";
import { useKnowledgeGraph } from "../../hooks";
import { PanelShell, type PanelProps } from "../shell/PanelShell";
import {
  buildKnowledgeGraphView,
  graphEdgeKey,
  layoutKnowledgeGraph,
  type GraphConfidence,
} from "./knowledgeGraphModel";

// Keep the default project page dense enough to be useful while preserving
// distinct keyboard/pointer hit areas. Larger graphs remain reachable through
// the server-backed focus-neighborhood control.
const PAGE_LIMIT = 48;
const CW = 900;
const CH = 560;

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
}: {
  label: string;
  tone: string;
  children: ReactNode;
  onClick?: () => void;
  ariaLabel?: string;
}) {
  const content = (
    <>
      <span style={{ display: "block", fontSize: 7.5, letterSpacing: ".14em", color: tone, marginBottom: 4 }}>{label}</span>
      <span style={{ display: "block", color: "var(--txt)", fontSize: 9.5, lineHeight: 1.4, overflowWrap: "anywhere" }}>{children}</span>
    </>
  );
  return onClick ? (
    <button type="button" aria-label={ariaLabel} onClick={onClick} style={{ width: "100%", textAlign: "left", border: "1px solid var(--line2)", background: "var(--tint)", padding: "8px 9px", marginBottom: 6, font: "inherit", cursor: "pointer" }}>{content}</button>
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

export function KnowledgeGraph(props: PanelProps) {
  const projectId = useProjectId();
  const { setSelection } = useSelection();
  const [focusKey, setFocusKey] = useState<string | null>(null);
  const [depth, setDepth] = useState(1);
  const [includeInferred, setIncludeInferred] = useState(true);
  const [hiddenNodeTypes, setHiddenNodeTypes] = useState<Set<string>>(new Set());
  const [confidenceMin, setConfidenceMin] = useState<GraphConfidence>("unknown");
  const [sourceSystem, setSourceSystem] = useState("all");
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [connectionsExpanded, setConnectionsExpanded] = useState(false);
  const [orphansExpanded, setOrphansExpanded] = useState(false);
  const [weakLinksExpanded, setWeakLinksExpanded] = useState(false);

  useEffect(() => {
    setFocusKey(null);
    setDepth(1);
    setIncludeInferred(true);
    setHiddenNodeTypes(new Set());
    setConfidenceMin("unknown");
    setSourceSystem("all");
    setSelectedKey(null);
    setConnectionsExpanded(false);
    setOrphansExpanded(false);
    setWeakLinksExpanded(false);
  }, [projectId]);

  const query = useMemo(() => ({
    focus_key: focusKey,
    depth,
    limit: PAGE_LIMIT,
    include_inferred: includeInferred,
  }), [depth, focusKey, includeInferred]);
  const { data, loading, error, refetch } = useKnowledgeGraph(query);
  // useResource clears on project changes in an effect. This synchronous guard
  // prevents even one render of the prior project's graph in the new workspace.
  const graph = data && data.project_id === projectId
    && data.focus_key === focusKey
    && data.depth === depth
    && data.include_inferred === includeInferred
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
  const positions = useMemo(() => layoutKnowledgeGraph(view?.nodes ?? [], CW, CH), [view?.nodes]);
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
  const maxDegree = Math.max(1, ...(view?.nodes ?? []).map((node) => node.degree));
  const mapCapped = Boolean(graph && (
    graph.returned_node_count < graph.node_count
    || graph.returned_edge_count < graph.edge_count
  ));
  const diagnosticsCapped = Boolean(graph && (
    graph.orphan_keys.length < graph.orphan_count
    || graph.weak_links.length < graph.weak_link_count
  ));

  useEffect(() => {
    setConnectionsExpanded(false);
  }, [confidenceMin, focusKey, includeInferred, selected?.key, sourceSystem]);

  useEffect(() => {
    setOrphansExpanded(false);
    setWeakLinksExpanded(false);
  }, [confidenceMin, focusKey, hiddenNodeTypes, includeInferred, sourceSystem]);

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

  return (
    <PanelShell {...props}>
      <div data-screen-label="Knowledge Graph" style={panelBox}>
        <div style={{ position: "absolute", top: -1, left: -1, width: 14, height: 14, borderTop: "1px solid var(--crimson)", borderLeft: "1px solid var(--crimson)", zIndex: 9 }} />
        <div style={{ position: "absolute", top: 3, left: 3, width: 5, height: 5, background: "var(--crimson)", zIndex: 9 }} />

        <div style={{ minHeight: 44, flex: "none", display: "flex", flexWrap: "wrap", alignItems: "center", gap: 9, padding: "5px 16px", borderBottom: "1px solid var(--line)", background: "var(--tint)", zIndex: 5 }}>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 14, letterSpacing: ".12em", color: "var(--strong)" }}>PROJECT MAP</span>
          <span style={{ fontSize: 7.5, color: "var(--accent)", border: "1px solid var(--line-cy)", padding: "2px 7px", letterSpacing: ".12em" }}>CANONICAL NARRATIVE GRAPH</span>
          {graph?.focus_key && <span style={{ maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: 8, color: "var(--amber)" }}>FOCUS · {graph.nodes.find((node) => node.key === graph.focus_key)?.label ?? graph.focus_key}</span>}
          <div style={{ flex: 1 }} />
          <label style={{ display: "flex", alignItems: "center", gap: 5, color: "var(--txt2)", fontSize: 8 }}>
            DEPTH
            <select aria-label="Knowledge Graph focus depth" value={depth} onChange={(event) => setDepth(Number(event.currentTarget.value))} style={control}>
              <option value={1}>1 hop</option>
              <option value={2}>2 hops</option>
            </select>
          </label>
          {focusKey ? (
            <button type="button" aria-label="Return to full Project Map" onClick={() => setFocusKey(null)} style={activeControl}>SHOW PROJECT MAP</button>
          ) : (
            <button type="button" disabled={!selected} aria-label={selected ? `Focus graph on ${selected.label || selected.key}` : "Focus graph on selected node"} onClick={() => selected && setFocusKey(selected.key)} style={{ ...activeControl, opacity: selected ? 1 : 0.45, cursor: selected ? "pointer" : "default" }}>FOCUS NEIGHBORHOOD</button>
          )}
        </div>

        {graph && (graph.truncated || diagnosticsCapped || graph.warnings.length > 0 || graph.unavailable.length > 0) && (
          <div role="status" aria-live="polite" style={{ flex: "none", padding: "5px 14px", borderBottom: "1px solid var(--line2)", color: graph.truncated || diagnosticsCapped ? "var(--warning)" : "var(--txt2)", background: "var(--tint2)", fontSize: 8, lineHeight: 1.45, overflowWrap: "anywhere" }}>
            {mapCapped && <span>SIZE CAP · Showing an interaction-safe page of {graph.returned_node_count} of {graph.node_count} nodes and {graph.returned_edge_count} of {graph.edge_count} edges (up to {PAGE_LIMIT} nodes). Focus a node to inspect its bounded neighborhood. </span>}
            {diagnosticsCapped && <span>DIAGNOSTIC CAP · Core returned {graph.orphan_keys.length} of {graph.orphan_count} orphan keys and {graph.weak_links.length} of {graph.weak_link_count} weak links. </span>}
            {graph.truncated && !mapCapped && !diagnosticsCapped && <span>BOUNDED RESPONSE · Core indicated additional graph data was omitted. </span>}
            {graph.warnings.map((warning) => <span key={warning}>WARNING · {warning} </span>)}
            {graph.unavailable.length > 0 && <span>DEFERRED SOURCES · {graph.unavailable.join(", ")}</span>}
          </div>
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
            <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
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

            <fieldset style={{ border: 0, padding: 0, margin: "15px 0 0" }}>
              <legend style={{ fontSize: 7.5, letterSpacing: ".2em", color: "var(--txt3)", marginBottom: 8 }}>EDGE FILTERS</legend>
              <label style={{ display: "flex", flexDirection: "column", gap: 4, color: "var(--txt2)", fontSize: 8, marginBottom: 9 }}>
                MINIMUM CONFIDENCE
                <select aria-label="Minimum edge confidence" value={confidenceMin} onChange={(event) => setConfidenceMin(event.currentTarget.value as GraphConfidence)} style={{ ...control, width: "100%" }}>
                  <option value="unknown">All confidence</option>
                  <option value="possible">Possible+</option>
                  <option value="likely">Likely+</option>
                  <option value="confirmed">Confirmed only</option>
                </select>
              </label>
              <label style={{ display: "flex", flexDirection: "column", gap: 4, color: "var(--txt2)", fontSize: 8, marginBottom: 9 }}>
                SOURCE SYSTEM
                <select aria-label="Edge source system" value={sourceSystem} onChange={(event) => setSourceSystem(event.currentTarget.value)} style={{ ...control, width: "100%" }}>
                  <option value="all">All sources</option>
                  {sourceSystems.map((source) => <option key={source} value={source}>{source.replaceAll("_", " ")}</option>)}
                </select>
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: 7, color: "var(--txt2)", fontSize: 8.5 }}>
                <input type="checkbox" checked={includeInferred} onChange={(event) => setIncludeInferred(event.currentTarget.checked)} />
                INCLUDE INFERRED
              </label>
            </fieldset>
          </aside>

          <main aria-label="Narrative Knowledge Graph canvas" style={{ flex: 1, minWidth: 0, position: "relative", overflow: "auto", display: "grid", placeItems: "center" }}>
            {projectId == null ? (
              <Message>Open a project to build its narrative map.</Message>
            ) : loading && !graph ? (
              <Message role="status">Building the canonical Project Map…</Message>
            ) : error ? (
              <Message role="alert">
                <div>
                  <div>Couldn&apos;t load the Project Map — {error}</div>
                  <button type="button" onClick={refetch} style={{ ...activeControl, marginTop: 10 }}>RETRY LOAD</button>
                </div>
              </Message>
            ) : !graph ? (
              <Message>Project Map unavailable.</Message>
            ) : graph.nodes.length === 0 ? (
              <Message>No narrative knowledge has been derived yet. Add manuscript structure, PSYKE entries, notes, or workflows to begin the map.</Message>
            ) : !view || view.nodes.length === 0 ? (
              <Message>No nodes match the current filters.</Message>
            ) : (
              <div data-knowledge-graph-canvas="true" data-project-id={graph.project_id} data-focus-key={graph.focus_key ?? ""} style={{ position: "relative", width: CW, height: CH, flex: "none" }}>
                <svg aria-hidden="true" viewBox={`0 0 ${CW} ${CH}`} width={CW} height={CH} style={{ position: "absolute", inset: 0, zIndex: 1 }}>
                  <defs>
                    <marker id="project-map-arrow" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6" fill="none" stroke="var(--txt3)" strokeWidth="1.1" /></marker>
                  </defs>
                  {view.edges.map((edge) => {
                    const from = positions.get(edge.source);
                    const to = positions.get(edge.target);
                    if (!from || !to) return null;
                    const hot = selected && (edge.source === selected.key || edge.target === selected.key);
                    const weak = edge.is_inferred || edge.confidence === "possible" || edge.confidence === "unknown";
                    return (
                      <g key={graphEdgeKey(edge)} opacity={hot ? 1 : 0.48}>
                        <title>{edgeTitle(edge, view.nodeByKey)}</title>
                        <line x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke={hot ? "var(--accent)" : weak ? "var(--warning)" : "var(--txt3)"} strokeWidth={hot ? 1.8 : 1.1} strokeDasharray={weak ? "5 4" : undefined} markerEnd="url(#project-map-arrow)" />
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
                  const size = 30 + Math.min(18, Math.sqrt(Math.max(0, node.degree) / maxDegree) * 18);
                  return (
                    <button
                      key={node.key}
                      type="button"
                      data-graph-node-key={node.key}
                      aria-pressed={selectedNode}
                      aria-label={`Select ${node.label || node.key}, ${meta.label}, ${node.degree} connections`}
                      onClick={() => chooseNode(node)}
                      style={{ position: "absolute", left: position.x, top: position.y, transform: "translate(-50%,-50%)", zIndex: selectedNode ? 4 : 3, width: 80, minHeight: 76, border: 0, background: "transparent", padding: 0, color: "var(--txt)", font: "inherit", textAlign: "center", cursor: "pointer" }}
                    >
                      {(selectedNode || focusedNode) && <span aria-hidden="true" style={{ position: "absolute", pointerEvents: "none", left: "50%", top: size / 2, transform: "translate(-50%,-50%)", width: size + 16, height: size + 16, borderRadius: "50%", border: `1px solid ${meta.color}`, boxShadow: `0 0 16px ${meta.color}` }} />}
                      <span aria-hidden="true" style={{ position: "relative", margin: "0 auto", width: size, height: size, borderRadius: "50%", border: `${selectedNode ? 2.5 : 1.5}px solid ${meta.color}`, background: "var(--tint)", display: "grid", placeItems: "center", color: meta.color, fontSize: Math.max(13, Math.round(size * 0.33)) }}>{meta.icon}</span>
                      <span style={{ display: "block", marginTop: 4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontFamily: "'Chakra Petch'", fontSize: selectedNode ? 11 : 9.5, color: selectedNode ? "var(--strong)" : "var(--txt)" }}>{node.label || node.key}</span>
                      <span style={{ display: "block", fontSize: 6.5, color: focusedNode ? "var(--accent)" : "var(--txt3)", letterSpacing: ".08em" }}>{focusedNode ? "FOCUS · " : ""}{node.degree} LINK{node.degree === 1 ? "" : "S"}</span>
                    </button>
                  );
                })}
                <div style={{ position: "absolute", left: 8, bottom: 8, zIndex: 4, border: "1px solid var(--line2)", background: "var(--tint)", padding: "6px 9px", color: "var(--txt2)", fontSize: 7.5 }}>
                  <span style={{ marginRight: 10 }}>──▸ relation</span><span style={{ color: "var(--warning)", marginRight: 10 }}>┄▸ weak / inferred</span><span style={{ color: "var(--accent)" }}>node size = full-graph degree</span>
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
                    <div style={{ color: "var(--txt3)", fontSize: 7.5, letterSpacing: ".08em" }}>{metaOf(selected.node_type).label.toUpperCase()} · {selected.degree} FULL-GRAPH LINKS</div>
                  </div>
                </div>
                {selected.summary && <p style={{ margin: "9px 0", color: "var(--txt2)", fontSize: 9.5, lineHeight: 1.45 }}>{selected.summary}</p>}
                <div style={{ display: "flex", flexWrap: "wrap", gap: 5, margin: "9px 0" }}>
                  <span style={{ ...control, padding: "2px 5px" }}>SOURCE · {selected.source_type || "derived"}</span>
                  <span style={{ ...control, padding: "2px 5px" }}>VISIBLE · {visibleDegree.get(selected.key) ?? 0}</span>
                </div>
                {graph?.focus_key === selected.key ? (
                  <div role="status" style={{ ...control, width: "100%", boxSizing: "border-box", color: "var(--accent)", textAlign: "center" }}>FOCUS ROOT · {depth}-HOP NEIGHBORHOOD</div>
                ) : (
                  <button type="button" aria-label={`Focus graph on ${selected.label || selected.key}`} onClick={() => setFocusKey(selected.key)} style={{ ...activeControl, width: "100%" }}>FOCUS {depth}-HOP NEIGHBORHOOD</button>
                )}
                <div style={{ marginTop: 10, color: "var(--txt3)", fontSize: 7.5, letterSpacing: ".14em" }}>VISIBLE CONNECTIONS · SHOWING {displayedConnections.length} OF {selectedEdges.length}</div>
                {selectedEdges.length === 0 ? <p style={{ color: "var(--txt3)", fontSize: 9 }}>None under the current edge filters.</p> : displayedConnections.map((edge) => {
                  const otherKey = edge.source === selected.key ? edge.target : edge.source;
                  const other = view?.nodeByKey.get(otherKey);
                  const outgoing = edge.source === selected.key;
                  const direction = outgoing ? "OUTGOING TO" : "INCOMING FROM";
                  const description = edgeInspectionLabel(edge, selected.key, view?.nodeByKey ?? new Map<string, KnowledgeGraphNodeDTO>());
                  return (
                    <button data-graph-connection="true" key={graphEdgeKey(edge)} type="button" aria-label={`${description}. Select connected node.`} onClick={() => other && chooseNode(other)} style={{ width: "100%", border: "1px solid var(--line2)", background: "var(--tint)", padding: "6px 7px", marginTop: 5, color: "var(--txt2)", font: "inherit", fontSize: 8.5, display: "block", textAlign: "left", cursor: other ? "pointer" : "default", overflowWrap: "anywhere" }}>
                      <span style={{ display: "block", color: "var(--strong)", fontSize: 9 }}>{outgoing ? "→" : "←"} {direction} · {other?.label || otherKey}</span>
                      <span style={{ display: "block", marginTop: 3, color: "var(--accent)" }}>TYPE · {edge.edge_type.replaceAll("_", " ")} · CONFIDENCE · {edge.confidence}</span>
                      <span style={{ display: "block", color: "var(--txt3)" }}>SOURCE SYSTEM · {edge.source_system.replaceAll("_", " ")}</span>
                      <span style={{ display: "block", color: "var(--txt3)" }}>PROVENANCE · {edge.provenance || "not provided"}</span>
                      <span style={{ display: "block", color: "var(--txt2)" }}>EXPLANATION · {edge.explanation || "not provided"}</span>
                    </button>
                  );
                })}
                {selectedEdges.length > 12 && (
                  <button type="button" aria-expanded={connectionsExpanded} aria-label={connectionsExpanded ? "Show fewer visible connections" : `Show all ${selectedEdges.length} visible connections`} onClick={() => setConnectionsExpanded((current) => !current)} style={{ ...activeControl, width: "100%", marginTop: 6 }}>
                    {connectionsExpanded ? "SHOW FEWER CONNECTIONS" : `SHOW ALL ${selectedEdges.length} CONNECTIONS`}
                  </button>
                )}
              </section>
            ) : <Message>Select a node to inspect its neighborhood.</Message>}

            <section aria-label="Graph diagnostics" style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: 12 }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 7, marginBottom: 8 }}><span style={{ fontFamily: "'Chakra Petch'", color: "var(--strong)", fontSize: 11, letterSpacing: ".1em" }}>DIAGNOSTICS</span><span style={{ marginLeft: "auto", color: "var(--txt3)", fontSize: 7 }}>CORE-DERIVED</span></div>
              {(graph?.orphan_count ?? 0) === 0 && (graph?.weak_link_count ?? 0) === 0 ? (
                <InsightCard label="CONNECTED" tone="var(--green)">No orphan or weak-link diagnostics in this graph view.</InsightCard>
              ) : null}
              {(graph?.orphan_count ?? 0) > 0 && (
                <div style={{ marginBottom: 9 }}>
                  <div style={{ color: "var(--warning)", fontSize: 7.5, letterSpacing: ".14em", marginBottom: 5 }}>ORPHANS · SHOWING {displayedOrphans.length} OF {orphanNodes.length} MATCHING · {graph?.orphan_keys.length ?? 0} CORE RETURNED · {graph?.orphan_count} QUERY TOTAL</div>
                  {displayedOrphans.map((node) => (
                    <InsightCard key={node.key} label={metaOf(node.node_type).label.toUpperCase()} tone="var(--warning)" ariaLabel={`Select orphan node ${node.label || node.key}`} onClick={() => chooseNode(node)}>{node.label || node.key}</InsightCard>
                  ))}
                  {orphanNodes.length === 0 && <div style={{ color: "var(--txt3)", fontSize: 8 }}>No returned orphan nodes match the active node-type filters.</div>}
                  {orphanNodes.length > 8 && (
                    <button type="button" aria-expanded={orphansExpanded} aria-label={orphansExpanded ? "Show fewer matching orphan nodes" : `Show all ${orphanNodes.length} matching orphan nodes`} onClick={() => setOrphansExpanded((current) => !current)} style={{ ...activeControl, width: "100%", marginBottom: 5 }}>
                      {orphansExpanded ? "SHOW FEWER ORPHANS" : `SHOW ALL ${orphanNodes.length} ORPHANS`}
                    </button>
                  )}
                  {graph && graph.orphan_keys.length > orphanNodes.length && <div style={{ color: "var(--txt3)", fontSize: 8 }}>{orphanNodes.length} of {graph.orphan_keys.length} Core-returned orphan nodes match the active node-type filters.</div>}
                  {graph && graph.orphan_count > graph.orphan_keys.length && <div style={{ color: "var(--txt3)", fontSize: 8 }}>Core returned {graph.orphan_keys.length} of {graph.orphan_count} orphan keys for this bounded query.</div>}
                </div>
              )}
              {(graph?.weak_link_count ?? 0) > 0 && (
                <div>
                  <div style={{ color: "var(--warning)", fontSize: 7.5, letterSpacing: ".14em", marginBottom: 5 }}>WEAK LINKS · SHOWING {displayedWeakLinks.length} OF {weakLinks.length} MATCHING · {graph?.weak_links.length ?? 0} CORE RETURNED · {graph?.weak_link_count} QUERY TOTAL</div>
                  {displayedWeakLinks.map((edge) => {
                    const source = view?.nodeByKey.get(edge.source);
                    const target = view?.nodeByKey.get(edge.target);
                    const sourceLabel = source?.label || edge.source;
                    const targetLabel = target?.label || edge.target;
                    return (
                      <InsightCard key={`weak-${graphEdgeKey(edge)}`} label={`${edge.confidence.toUpperCase()} · ${edge.source_system.replaceAll("_", " ").toUpperCase()}`} tone="var(--warning)" ariaLabel={`Weak link from ${sourceLabel} to ${targetLabel}. Type ${edge.edge_type.replaceAll("_", " ")}. Confidence ${edge.confidence}. Source system ${edge.source_system.replaceAll("_", " ")}. Provenance ${edge.provenance || "not provided"}. Explanation ${edge.explanation || "not provided"}. Select source node.`} onClick={() => source && chooseNode(source)}>
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
                    <button type="button" aria-expanded={weakLinksExpanded} aria-label={weakLinksExpanded ? "Show fewer matching weak links" : `Show all ${weakLinks.length} matching weak links`} onClick={() => setWeakLinksExpanded((current) => !current)} style={{ ...activeControl, width: "100%", marginTop: 1 }}>
                      {weakLinksExpanded ? "SHOW FEWER WEAK LINKS" : `SHOW ALL ${weakLinks.length} WEAK LINKS`}
                    </button>
                  )}
                  {graph && graph.weak_links.length > weakLinks.length && <div style={{ color: "var(--txt3)", fontSize: 8, marginTop: 5 }}>{weakLinks.length} of {graph.weak_links.length} Core-returned weak links match the active edge filters.</div>}
                  {graph && graph.weak_link_count > graph.weak_links.length && <div style={{ color: "var(--txt3)", fontSize: 8, marginTop: 5 }}>Core returned {graph.weak_links.length} of {graph.weak_link_count} weak links for this bounded query.</div>}
                </div>
              )}
            </section>
          </aside>
          </div>
        </div>

        <div style={{ minHeight: 24, flex: "none", borderTop: "1px solid var(--line2)", display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12, padding: "3px 16px", background: "var(--base)", color: "var(--txt3)", fontSize: 8, letterSpacing: ".08em" }}>
          <span style={{ color: "var(--green)" }}>● DETERMINISTIC · READ ONLY · TRACEABLE</span>
          <span>{view?.nodes.length ?? 0} / {graph?.node_count ?? 0} NODES</span>
          <span>{view?.edges.length ?? 0} / {graph?.edge_count ?? 0} EDGES</span>
          <span style={{ color: "var(--warning)" }}>{graph?.orphan_count ?? 0} ORPHANS · {graph?.weak_link_count ?? 0} WEAK LINKS</span>
          {hiddenNodeTypes.size > 0 && <span>{hiddenNodeTypes.size} NODE TYPE{hiddenNodeTypes.size === 1 ? "" : "S"} HIDDEN</span>}
          <span style={{ marginLeft: "auto", color: "var(--txt2)" }}>{graph?.writing_mode ?? "current project"}</span>
        </div>
      </div>
    </PanelShell>
  );
}
