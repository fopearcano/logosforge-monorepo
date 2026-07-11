import type { CSSProperties, ReactNode } from "react";
import type { DecisionCardDTO } from "@logosforge/ui-contracts";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import { useNavigate } from "../../adapters/StudioProvider";
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

type Action = { text: string; color: string; border: string; nav?: string };

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

/** Build the chip row: the suggested action (navigable when a section is set) + an optional ref tag. */
function cardActions(card: DecisionCardDTO, sev: SevStyle): Action[] {
  const actions: Action[] = [];
  if (card.suggested_action) actions.push({ text: card.suggested_action, color: sev.color, border: sev.border, nav: card.related_section || undefined });
  const ref = refTag(card);
  if (ref) actions.push({ text: ref, color: "var(--txt2)", border: "var(--line2)" });
  return actions;
}

function RadarCard({ severity, label, icon, conf, title, desc, actions, onNavigate, glow = false }: { severity: string; label: string; icon: ReactNode; conf: string; title: string; desc?: string; actions: Action[]; onNavigate: (section: string) => void; glow?: boolean }) {
  return (
    <div style={{ position: "relative", border: glow ? "1px solid rgba(255,82,96,.4)" : "1px solid var(--line2)", background: glow ? "linear-gradient(180deg,rgba(255,82,96,.07),transparent)" : "var(--tint)", padding: "11px 12px", marginBottom: 9, animation: glow ? "lf-glow 2.6s ease-in-out infinite" : undefined }}>
      <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 2, background: severity }} />
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 8, letterSpacing: ".16em", color: severity }}>{icon}{label}</span>
        <span style={{ fontSize: 7.5, color: "var(--txt3)" }}>{conf}</span>
      </div>
      <div style={{ fontSize: 11.5, color: glow ? "var(--strong)" : "var(--txt)", lineHeight: 1.4, marginBottom: desc ? 5 : 6 }}>{title}</div>
      {desc && <div style={{ fontSize: 9, color: "var(--txt2)", lineHeight: 1.4, marginBottom: 8 }}>{desc}</div>}
      <div style={{ display: "flex", gap: 6 }}>
        {actions.map((a, i) =>
          a.nav
            ? (
              <button
                key={i}
                type="button"
                onClick={() => onNavigate(a.nav!)}
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
  const radar = data?.radar ?? [];
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
