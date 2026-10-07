import type { CSSProperties, ReactNode } from "react";
import type { DecisionCardDTO, DecisionEvidenceDTO, DecisionRadarDTO } from "@logosforge/ui-contracts";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import { useNavigate, type StudioNavigationOptions } from "../../adapters/StudioProvider";
import { useDecisionRadar } from "../../hooks";

const panelBox: CSSProperties = {
  position: "relative",
  width: "100%",
  height: "100%",
  background: "linear-gradient(180deg,var(--panel),var(--base))",
  border: "1px solid var(--line)",
  boxShadow: "0 16px 60px rgba(0,0,0,.6)",
  overflow: "hidden",
  display: "flex",
  flexDirection: "column",
};

type Action = {
  text: string;
  color: string;
  border: string;
  nav?: string;
  options?: StudioNavigationOptions;
};

const DISPLAY_CAP = 10;
const SEVERITY_RANK: Record<string, number> = {
  blocking: 0,
  warning: 1,
  suggestion: 2,
  opportunity: 3,
  info: 4,
};

/** Preserve the established feed, add canonical graph cards, then rank once. */
export function mergeDecisionRadarCards(data: DecisionRadarDTO | null | undefined): DecisionCardDTO[] {
  if (!data) return [];
  const hasCanonicalIsolation = data.knowledge_graph_cards.some((card) => card.id.startsWith("kg_isolated_"));
  const base = hasCanonicalIsolation
    ? data.radar.filter((card) => card.id !== "graph_isolated")
    : data.radar;
  const unique = new Map<string, { card: DecisionCardDTO; order: number }>();
  [...base, ...data.knowledge_graph_cards, ...data.continuity_cards].forEach((card, order) => {
    if (!unique.has(card.id)) unique.set(card.id, { card, order });
  });
  return [...unique.values()]
    .sort((left, right) => (
      (SEVERITY_RANK[left.card.severity] ?? 5) - (SEVERITY_RANK[right.card.severity] ?? 5)
      || left.order - right.order
    ))
    .slice(0, DISPLAY_CAP)
    .map(({ card }) => card);
}

/** Per-severity visual treatment: color token, label, icon glyph + a soft border for chips. */
type SevStyle = { color: string; label: string; border: string; icon: ReactNode };

const SEV: Record<string, SevStyle> = {
  blocking: {
    color: "var(--blocking)",
    label: "BLOCKING",
    border: "rgba(255,82,96,.4)",
    icon: <span style={{ width: 10, height: 10, background: "var(--blocking)", display: "inline-grid", placeItems: "center", color: "var(--strong)", fontSize: 7 }}>!</span>,
  },
  warning: {
    color: "var(--warning)",
    label: "WARNING",
    border: "rgba(255,180,84,.4)",
    icon: <span style={{ width: 8, height: 8, transform: "rotate(45deg)", background: "var(--warning)" }} />,
  },
  suggestion: {
    color: "var(--suggestion)",
    label: "SUGGESTION",
    border: "var(--line-cy)",
    icon: <span style={{ width: 8, height: 8, borderRadius: "50%", border: "2px solid var(--suggestion)" }} />,
  },
  opportunity: {
    color: "var(--opportunity)",
    label: "OPPORTUNITY",
    border: "rgba(98,217,154,.4)",
    icon: <span style={{ width: 8, height: 8, background: "var(--opportunity)", clipPath: "polygon(50% 0,100% 100%,0 100%)" }} />,
  },
  info: {
    color: "var(--info)",
    label: "INFO",
    border: "var(--line2)",
    icon: <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--info)" }} />,
  },
};

const sevStyle = (severity: string): SevStyle => SEV[severity] ?? SEV.info!;

/** confirmed→HIGH, likely→MED, possible→LOW (else the raw value, uppercased). */
const CONF: Record<string, string> = { confirmed: "HIGH", likely: "MED", possible: "LOW" };
const confLabel = (confidence: string) => `conf ${CONF[confidence] ?? confidence.toUpperCase()}`;

/** A small ref tag: scene targets read as 'SC.{id}', otherwise the section / target type. */
function refTag(card: DecisionCardDTO): string | null {
  if (card.related_target_type === "scene" && card.related_target_id != null) return `SC.${card.related_target_id}`;
  if (card.related_section) return card.related_section;
  if (card.related_target_type && card.related_target_id != null) return `${card.related_target_type} ${card.related_target_id}`;
  return null;
}

function remediationOptions(card: DecisionCardDTO): StudioNavigationOptions | undefined {
  if (card.related_target_type === "continuity_issue" && card.related_target_key) {
    return { continuityIssueKey: card.related_target_key };
  }
  if (card.related_target_id == null) return undefined;
  if (card.related_target_type === "scene") return { sceneId: card.related_target_id };
  if (card.related_target_type === "psyke" || card.related_target_type === "psyke_entry") {
    return { psykeEntryId: card.related_target_id };
  }
  if (card.related_target_type === "note") return { noteId: card.related_target_id };
  if (card.related_target_type === "comment") return { commentId: card.related_target_id };
  return undefined;
}

function graphOptions(card: DecisionCardDTO, focusKey = card.graph_focus_key): StudioNavigationOptions | undefined {
  if (!focusKey || !card.graph_view_mode) return undefined;
  return {
    graphFocusKey: focusKey,
    graphViewMode: card.graph_view_mode,
    graphIncludeInferred: card.graph_include_inferred,
    graphDepth: card.graph_depth,
  };
}

function evidenceDestination(card: DecisionCardDTO, item: DecisionEvidenceDTO): {
  panel: string;
  options: StudioNavigationOptions;
  label: string;
} | undefined {
  const graph = graphOptions(card, item.graph_focus_key);
  if (graph) return { panel: "Graph", options: graph, label: "FOCUS THIS EVIDENCE" };
  if (item.related_target_type === "scene" && item.related_target_id != null) {
    return {
      panel: item.related_section || "Manuscript",
      options: { sceneId: item.related_target_id },
      label: "OPEN SCENE EVIDENCE",
    };
  }
  if (item.related_target_type === "continuity_issue" && item.related_target_key) {
    return {
      panel: item.related_section || "Continuity",
      options: { continuityIssueKey: item.related_target_key },
      label: "FOCUS THIS EVIDENCE",
    };
  }
  return undefined;
}

/** Build the chip row: the suggested action (navigable when a section is set) + an optional ref tag. */
function cardActions(card: DecisionCardDTO, sev: SevStyle): Action[] {
  const actions: Action[] = [];
  if (card.suggested_action) actions.push({
    text: card.suggested_action,
    color: sev.color,
    border: sev.border,
    nav: card.related_section || undefined,
    options: remediationOptions(card),
  });
  const exactGraphOptions = graphOptions(card);
  if (exactGraphOptions) actions.push({
    text: "OPEN GRAPH EVIDENCE",
    color: "var(--accent)",
    border: "var(--line-cy)",
    nav: "Graph",
    options: exactGraphOptions,
  });
  if (card.created_from === "semantic_continuity" && card.related_target_key) actions.push({
    text: "OPEN CONTINUITY ISSUE",
    color: "var(--cyan)",
    border: "var(--line-cy)",
    nav: "Continuity",
    options: { continuityIssueKey: card.related_target_key },
  });
  const ref = refTag(card);
  if (ref) actions.push({ text: ref, color: "var(--txt2)", border: "var(--line2)" });
  return actions;
}

function EvidenceRows({ card, onNavigate }: {
  card: DecisionCardDTO;
  onNavigate: (section: string, options?: StudioNavigationOptions) => void;
}) {
  if (card.evidence_total === 0) return null;
  return (
    <details data-decision-evidence={card.id} style={{ margin: "7px 0 8px", borderTop: "1px solid var(--line2)", paddingTop: 6 }}>
      <summary style={{ cursor: "pointer", color: "var(--txt3)", fontSize: 7.5, letterSpacing: ".12em" }}>
        TRACEABLE EVIDENCE · {card.evidence.length === card.evidence_total ? card.evidence_total : `${card.evidence.length} OF ${card.evidence_total}`}
      </summary>
      <div style={{ display: "grid", gap: 5, marginTop: 6 }}>
        {card.evidence.map((item: DecisionEvidenceDTO, index) => {
          const destination = evidenceDestination(card, item);
          const meta = [
            item.edge_type && `TYPE ${item.edge_type.replaceAll("_", " ")}`,
            item.confidence && `CONF ${item.confidence}`,
            item.source_system && `SOURCE ${item.source_system.replaceAll("_", " ")}`,
            item.provenance && `PROVENANCE ${item.provenance}`,
            item.related_target_type === "scene" && item.related_target_id != null && `SCENE ${item.related_target_id}`,
            item.related_target_type === "continuity_issue" && item.related_target_key && `ISSUE ${item.related_target_key}`,
          ].filter(Boolean).join(" · ");
          return (
            <div key={`${item.kind}:${item.source_key}:${item.target_key}:${item.graph_focus_key}:${index}`} style={{ borderLeft: "2px solid var(--line-cy)", background: "var(--tint2)", padding: "6px 7px" }}>
              <div style={{ color: "var(--txt)", fontSize: 8.5, lineHeight: 1.35 }}>{item.label}</div>
              {item.detail && <div style={{ color: "var(--txt2)", fontSize: 8, lineHeight: 1.35, marginTop: 2 }}>{item.detail}</div>}
              {meta && <div style={{ color: "var(--txt3)", fontSize: 7, lineHeight: 1.35, marginTop: 3, overflowWrap: "anywhere" }}>{meta}</div>}
              {destination && (
                <button type="button" aria-label={`Open evidence for ${item.label}`} onClick={() => onNavigate(destination.panel, destination.options)} style={{ marginTop: 5, border: "1px solid var(--line2)", background: "transparent", color: "var(--accent)", padding: "2px 6px", font: "inherit", fontSize: 7.5, cursor: "pointer" }}>
                  {destination.label}
                </button>
              )}
            </div>
          );
        })}
      </div>
    </details>
  );
}

function RadarCard({ card, severity, label, icon, conf, title, desc, actions, onNavigate, glow = false }: { card: DecisionCardDTO; severity: string; label: string; icon: ReactNode; conf: string; title: string; desc?: string; actions: Action[]; onNavigate: (section: string, options?: StudioNavigationOptions) => void; glow?: boolean }) {
  return (
    <div data-decision-card-id={card.id} style={{ position: "relative", border: glow ? "1px solid rgba(255,82,96,.4)" : "1px solid var(--line2)", background: glow ? "linear-gradient(180deg,rgba(255,82,96,.07),transparent)" : "var(--tint)", padding: "11px 12px", marginBottom: 9, animation: glow ? "lf-glow 2.6s ease-in-out infinite" : undefined }}>
      <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 2, background: severity }} />
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 8, letterSpacing: ".16em", color: severity }}>{icon}{label}</span>
        <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 7.5, color: "var(--txt3)" }}>
          {card.created_from === "knowledge_graph" && <span style={{ color: "var(--accent)", border: "1px solid var(--line-cy)", padding: "1px 4px" }}>KNOWLEDGE GRAPH</span>}
          {card.created_from === "semantic_continuity" && <span style={{ color: "var(--cyan)", border: "1px solid var(--line-cy)", padding: "1px 4px" }}>SEMANTIC CONTINUITY</span>}
          {conf}
        </span>
      </div>
      <div style={{ fontSize: 11.5, color: glow ? "var(--strong)" : "var(--txt)", lineHeight: 1.4, marginBottom: desc ? 5 : 6 }}>{title}</div>
      {desc && <div style={{ fontSize: 9, color: "var(--txt2)", lineHeight: 1.4, marginBottom: 8 }}>{desc}</div>}
      <EvidenceRows card={card} onNavigate={onNavigate} />
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {actions.map((a, i) =>
          a.nav
            ? (
              <button type="button"
                key={i}
                onClick={() => onNavigate(a.nav!, a.options)}
                style={{ fontSize: 8, color: a.color, background: "transparent", border: `1px solid ${a.border}`, padding: "3px 8px", cursor: "pointer", font: "inherit", lineHeight: 1.4, transition: "background .15s ease" }}
                onMouseEnter={(e) => { e.currentTarget.style.background = "var(--tint2)"; }}
                onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
              >
                {a.text}
              </button>
            )
            : <span key={i} style={{ fontSize: 8, color: a.color, border: `1px solid ${a.border}`, padding: "3px 8px" }}>{a.text}</span>,
        )}
      </div>
    </div>
  );
}

const message = (text: string) => (
  <div style={{ padding: "34px 0", textAlign: "center", fontSize: 11, color: "var(--txt3)", letterSpacing: ".04em" }}>{text}</div>
);

export function DecisionRadar(props: PanelProps) {
  const { data, loading, error } = useDecisionRadar();
  const navigate = useNavigate();
  const radar = mergeDecisionRadarCards(data);
  const tally = (severity: string) => radar.filter((c) => c.severity === severity).length;

  return (
    <PanelShell {...props}>
      <div data-screen-label="Decision Radar" style={panelBox}>
        <Corners />
        <div style={{ flex: "none", height: 46, display: "flex", alignItems: "center", gap: 11, padding: "0 14px", borderBottom: "1px solid var(--line)" }}>
          <div style={{ position: "relative", width: 26, height: 26, borderRadius: "50%", border: "1px solid var(--line)", overflow: "hidden" }}>
            <div style={{ position: "absolute", inset: 0, background: "conic-gradient(from 0deg,rgba(232,68,58,.55),transparent 28%)", animation: "lf-sweep 3.4s linear infinite" }} />
            <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", color: "var(--crimson)", fontSize: 10 }}>◎</div>
          </div>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 14, letterSpacing: ".1em", color: "var(--strong)" }}>DECISION RADAR</span>
          {data?.summary_line && <span style={{ fontSize: 8.5, color: "var(--txt3)", letterSpacing: ".04em", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 240 }}>{data.summary_line}</span>}
          <div style={{ flex: 1 }} />
          <div style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 8 }}>
            {data && <span style={{ color: data.knowledge_graph_available ? "var(--green)" : "var(--warning)", border: "1px solid var(--line2)", padding: "2px 5px" }}>{data.knowledge_graph_available ? "GRAPH ONLINE" : "GRAPH UNAVAILABLE"}</span>}
            {data && <span style={{ color: data.continuity_available ? "var(--green)" : "var(--warning)", border: "1px solid var(--line2)", padding: "2px 5px" }}>{data.continuity_available ? "CONTINUITY ONLINE" : "CONTINUITY UNAVAILABLE"}</span>}
            <span style={{ color: "var(--blocking)" }}>●{tally("blocking")}</span><span style={{ color: "var(--warning)" }}>●{tally("warning")}</span><span style={{ color: "var(--suggestion)" }}>●{tally("suggestion")}</span><span style={{ color: "var(--opportunity)" }}>●{tally("opportunity")}</span>
          </div>
        </div>
        <div style={{ flex: 1, overflowY: "auto", padding: 12 }}>
          {loading
            ? message("Scanning for decisions…")
            : error
              ? message(`Couldn't load decision radar — ${error}`)
              : radar.length === 0
                ? message("No decisions flagged — the story reads clean")
                : radar.map((card) => {
                    const sev = sevStyle(card.severity);
                    return (
                      <RadarCard
                        key={card.id}
                        card={card}
                        glow={card.severity === "blocking"}
                        severity={sev.color}
                        label={sev.label}
                        icon={sev.icon}
                        conf={confLabel(card.confidence)}
                        title={card.title}
                        desc={card.explanation || undefined}
                        actions={cardActions(card, sev)}
                        onNavigate={navigate}
                      />
                    );
                  })}
        </div>
        <div style={{ flex: "none", height: 26, display: "flex", alignItems: "center", justifyContent: "center", borderTop: "1px solid var(--line2)", fontSize: 8, letterSpacing: ".1em", color: "var(--txt3)" }}>ADVISORY ONLY · ROUTES THROUGH CONTROLLED APPLY</div>
      </div>
    </PanelShell>
  );
}
