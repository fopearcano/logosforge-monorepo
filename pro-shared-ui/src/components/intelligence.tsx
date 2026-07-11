import type { CSSProperties, ReactNode } from "react";
import type {
  StoryHealthDTO,
  HealthSignalDTO,
  PacingInsightDTO,
  BalanceDataDTO,
  CharacterBalanceDTO,
  ArcBalanceDTO,
  StructuralAnalysisDTO,
  StructuralIssueDTO,
} from "@logosforge/ui-contracts";
import { PanelShell, Corners, type PanelProps } from "./shell/PanelShell";
import { useStoryHealth, usePacing, useBalance, useStructureAnalysis } from "../hooks";

/**
 * Narrative intelligence HUDs. The Narrative Dashboard (mission control) is
 * re-exported from ./projectos; the four focused HUDs below are wired to the
 * core's deterministic-analysis endpoints (health / pacing / balance /
 * structure-analysis) — advisory, read-only views over the live project.
 */
export { NarrativeDashboard, ProjectsPanel, AdaptView, ReviewDashboard, PluginsPanel, SeriesNavigator, AiSettingsPanel, ConnectorPanel } from "./projectos";

/* ---------- shared frame + state helpers ---------- */

const frame: CSSProperties = {
  position: "relative", width: "100%", height: "100%",
  background: "linear-gradient(180deg,var(--panel),var(--base))", border: "1px solid var(--line)",
  boxShadow: "0 16px 60px rgba(0,0,0,.6)", overflow: "hidden", display: "flex", flexDirection: "column",
};
const headCss: CSSProperties = { flex: "none", height: 40, display: "flex", alignItems: "center", gap: 10, padding: "0 16px", borderBottom: "1px solid var(--line)" };
const titleCss: CSSProperties = { fontFamily: "'Chakra Petch',sans-serif", fontWeight: 600, fontSize: 12.5, letterSpacing: ".14em", color: "var(--strong)" };
const bodyCss: CSSProperties = { flex: 1, overflowY: "auto", padding: 14 };
const footCss: CSSProperties = { flex: "none", height: 22, borderTop: "1px solid var(--line2)", display: "flex", alignItems: "center", gap: 10, padding: "0 14px", background: "var(--base)", fontSize: 8, letterSpacing: ".1em", color: "var(--txt3)" };

interface Res<T> { data: T | null | undefined; loading: boolean; error: string | null }

const centered = (text: string, color = "var(--txt3)"): ReactNode => (
  <div style={{ padding: "44px 0", textAlign: "center", fontSize: 11, color, letterSpacing: ".04em" }}>{text}</div>
);

function stateView<T>(res: Res<T>, emptyText: string, isEmpty: (d: T) => boolean, render: (d: T) => ReactNode): ReactNode {
  if (res.loading && !res.data) return centered("Loading…");
  if (res.error) return centered(res.error, "var(--blocking)");
  if (res.data == null || isEmpty(res.data)) return centered(emptyText);
  return render(res.data);
}

function Frame({ panelProps, screen, title, footer, children }: { panelProps: PanelProps; screen: string; title: string; footer?: ReactNode; children: ReactNode }) {
  return (
    <PanelShell {...panelProps}>
      <div data-screen-label={screen} style={frame}>
        <Corners />
        <div style={headCss}>
          <span style={{ width: 6, height: 6, background: "var(--accent)", boxShadow: "0 0 6px var(--accent)" }} />
          <span style={titleCss}>{title}</span>
        </div>
        <div style={bodyCss}>{children}</div>
        <div style={footCss}>
          <span style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--green)" }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--green)" }} />DETERMINISTIC · ADVISORY ONLY
          </span>
          {footer && <span style={{ marginLeft: "auto", color: "var(--txt2)" }}>{footer}</span>}
        </div>
      </div>
    </PanelShell>
  );
}

const pct01 = (n: number) => Math.max(0, Math.min(100, Math.round(n * 100)));
const barTrack: CSSProperties = { flex: 1, height: 6, background: "var(--tint2)", borderRadius: 2, overflow: "hidden" };

/* ---------- colour maps (shared vocabulary with the dashboard) ---------- */

const healthColor = (level: string) => (level === "balanced" ? "var(--green)" : level === "sparse" ? "var(--amber)" : "var(--blocking)");
const pacingColor = (category: string): string => {
  switch (category) {
    case "monotony": case "stagnation": return "var(--blocking)";
    case "clustering": return "var(--amber)";
    case "neglect": case "disappearance": return "var(--cyan)";
    default: return "var(--txt3)";
  }
};
const sevColor = (s: number) => (s >= 0.66 ? "var(--blocking)" : s >= 0.33 ? "var(--amber)" : "var(--txt3)");
const flagColor = (flag: string) => (flag === "dominant" ? "var(--amber)" : flag === "underused" || flag === "thin" ? "var(--cyan)" : "var(--txt3)");

const chip = (text: string, color: string): ReactNode => (
  <span style={{ fontSize: 7.5, letterSpacing: ".14em", textTransform: "uppercase", color, border: `1px solid ${color}`, borderRadius: 2, padding: "1px 5px", whiteSpace: "nowrap" }}>{text}</span>
);

/* ======================= 1 · STORY HEALTH ======================= */

const HEALTH_ORDER: Array<{ key: keyof StoryHealthDTO; label: string }> = [
  { key: "structure", label: "STRUCTURE" },
  { key: "characters", label: "CHARACTERS" },
  { key: "arcs", label: "ARCS" },
  { key: "density", label: "DENSITY" },
];

function healthGauge(signal: HealthSignalDTO, label: string) {
  const color = healthColor(signal.level);
  const p = pct01(signal.score);
  return (
    <div key={label} style={{ border: "1px solid var(--line2)", background: "var(--tint)", padding: 14, display: "flex", alignItems: "center", gap: 14 }}>
      <div style={{ width: 58, height: 58, borderRadius: "50%", flex: "none", background: `conic-gradient(${color} 0 ${p}%,var(--tint2) ${p}%)`, display: "grid", placeItems: "center" }}>
        <div style={{ width: 42, height: 42, borderRadius: "50%", background: "var(--raised)", display: "grid", placeItems: "center", fontFamily: "'Chakra Petch'", fontSize: 15, color: "var(--strong)" }}>{p}</div>
      </div>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 8, letterSpacing: ".18em", color: "var(--txt3)" }}>{label}</div>
        <div style={{ fontSize: 11, color: "var(--txt)", margin: "3px 0" }}>{signal.label}</div>
        <div style={{ fontSize: 8.5, letterSpacing: ".12em", textTransform: "uppercase", color }}>{signal.level}</div>
      </div>
    </div>
  );
}

export function StoryHealthHud(props: PanelProps) {
  const health = useStoryHealth() as Res<StoryHealthDTO>;
  return (
    <Frame panelProps={props} screen="story-health-hud" title="STORY HEALTH">
      {stateView(health, "No health signals yet — write a few scenes to populate them", () => false, (h) => (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 11 }}>
          {HEALTH_ORDER.map(({ key, label }) => healthGauge(h[key], label))}
        </div>
      ))}
    </Frame>
  );
}

/* ======================= 2 · PACING INSIGHTS ======================= */

export function PacingInsights(props: PanelProps) {
  const pacing = usePacing() as Res<PacingInsightDTO[]>;
  const count = pacing.data?.length ?? 0;
  return (
    <Frame panelProps={props} screen="pacing-insights" title="PACING INSIGHTS" footer={count > 0 ? `${count} insight${count === 1 ? "" : "s"}` : undefined}>
      {stateView(pacing, "No pacing issues detected — rhythm looks balanced", (d) => d.length === 0, (list) => (
        <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
          {[...list].sort((a, b) => b.severity - a.severity).map((p, i) => (
            <div key={i} style={{ border: "1px solid var(--line2)", background: "var(--tint)", padding: "10px 12px", display: "flex", flexDirection: "column", gap: 7 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ width: 7, height: 7, background: pacingColor(p.category), flex: "none" }} />
                {chip(p.category, pacingColor(p.category))}
                <div style={{ ...barTrack, maxWidth: 120, marginLeft: "auto" }}>
                  <div style={{ width: `${pct01(p.severity)}%`, height: "100%", background: sevColor(p.severity) }} />
                </div>
              </div>
              <div style={{ fontSize: 10.5, color: "var(--txt)", lineHeight: 1.5 }}>{p.text}</div>
            </div>
          ))}
        </div>
      ))}
    </Frame>
  );
}

/* ======================= 3 · CHARACTER & ARC BALANCE ======================= */

function balanceRow(name: string, count: number, total: number, flag: string) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0;
  return (
    <div key={name} style={{ display: "flex", alignItems: "center", gap: 9 }}>
      <span style={{ fontSize: 10, color: "var(--txt2)", width: 96, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{name}</span>
      <div style={barTrack}>
        <div style={{ width: `${pct}%`, height: "100%", background: flag ? flagColor(flag) : "var(--accent)" }} />
      </div>
      <span style={{ fontSize: 8.5, color: "var(--txt3)", width: 54, textAlign: "right", whiteSpace: "nowrap" }}>{count}/{total}</span>
      <span style={{ width: 74, textAlign: "right" }}>{flag ? chip(flag, flagColor(flag)) : null}</span>
    </div>
  );
}

const sectionLabel: CSSProperties = { fontSize: 8, letterSpacing: ".2em", color: "var(--txt3)", margin: "2px 0 10px" };

export function CharacterBalance(props: PanelProps) {
  const balance = useBalance() as Res<BalanceDataDTO>;
  return (
    <Frame
      panelProps={props}
      screen="character-balance"
      title="CHARACTER & ARC BALANCE"
      footer={balance.data ? `${balance.data.total_scenes} scenes` : undefined}
    >
      {stateView(
        balance,
        "No cast or arcs tracked yet — add characters and plotlines to your scenes",
        (d) => d.characters.length === 0 && d.arcs.length === 0,
        (d) => (
          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            <div>
              <div style={sectionLabel}>CHARACTER PRESENCE · {d.characters.length}</div>
              {d.characters.length === 0
                ? <div style={{ fontSize: 9, color: "var(--txt3)" }}>No characters tracked</div>
                : <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {[...d.characters].sort((a: CharacterBalanceDTO, b: CharacterBalanceDTO) => b.scene_count - a.scene_count)
                      .map((c) => balanceRow(c.name, c.scene_count, c.total_scenes, c.flag))}
                  </div>}
            </div>
            <div>
              <div style={sectionLabel}>ARC BALANCE · {d.arcs.length}</div>
              {d.arcs.length === 0
                ? <div style={{ fontSize: 9, color: "var(--txt3)" }}>No plotlines tracked — set a plotline on your scenes</div>
                : <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {[...d.arcs].sort((a: ArcBalanceDTO, b: ArcBalanceDTO) => b.scene_count - a.scene_count)
                      .map((a) => balanceRow(a.plotline || "—", a.scene_count, d.total_scenes, a.flag))}
                  </div>}
            </div>
          </div>
        ),
      )}
    </Frame>
  );
}

/* ======================= 4 · STRUCTURE ANALYSIS (coverage) ======================= */

export function CoverageAnalysis(props: PanelProps) {
  const analysis = useStructureAnalysis() as Res<StructuralAnalysisDTO>;
  const issueCount = analysis.data?.issues.length ?? 0;
  return (
    <Frame
      panelProps={props}
      screen="structure-analysis"
      title="STRUCTURE ANALYSIS"
      footer={analysis.data ? `${issueCount} issue${issueCount === 1 ? "" : "s"}` : undefined}
    >
      {stateView(
        analysis,
        "No structural issues found — the spine looks sound",
        (d) => d.issues.length === 0 && d.suggestions.length === 0,
        (d) => (
          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            <div>
              <div style={sectionLabel}>ISSUES · {d.issues.length}</div>
              {d.issues.length === 0
                ? <div style={{ fontSize: 9, color: "var(--txt3)" }}>No issues flagged</div>
                : <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
                    {[...d.issues].sort((a: StructuralIssueDTO, b: StructuralIssueDTO) => b.severity - a.severity).map((it, i) => (
                      <div key={i} style={{ border: "1px solid var(--line2)", borderLeft: `2px solid ${sevColor(it.severity)}`, background: "var(--tint)", padding: "10px 12px", display: "flex", flexDirection: "column", gap: 6 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          {chip(it.category || it.issue_type, sevColor(it.severity))}
                          <span style={{ fontSize: 8, color: "var(--txt3)", marginLeft: "auto" }}>sev {pct01(it.severity)}</span>
                        </div>
                        <div style={{ fontSize: 10.5, color: "var(--txt)", lineHeight: 1.5 }}>{it.message}</div>
                        {it.suggestion && <div style={{ fontSize: 9.5, color: "var(--cyan)", lineHeight: 1.5 }}>↳ {it.suggestion}</div>}
                      </div>
                    ))}
                  </div>}
            </div>
            {d.suggestions.length > 0 && (
              <div>
                <div style={sectionLabel}>SUGGESTIONS · {d.suggestions.length}</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {d.suggestions.map((s, i) => (
                    <div key={i} style={{ display: "flex", gap: 8, fontSize: 10, color: "var(--txt2)", lineHeight: 1.5 }}>
                      <span style={{ color: "var(--accent)" }}>›</span>{s}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ),
      )}
    </Frame>
  );
}
