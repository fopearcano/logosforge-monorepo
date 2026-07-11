import type { CSSProperties, ReactNode } from "react";
import type { NarrativeDashboardDTO, StoryHealthDTO, HealthSignalDTO, PacingInsightDTO, SceneTensionDTO, ActSegmentDTO, CharacterPresenceDTO, ThemePresenceDTO } from "@logosforge/ui-contracts";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import { useDashboard, useStoryHealth, usePacing } from "../../hooks";

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

function Tile({ span = 1, label, right, accent = false, children }: { span?: number; label: string; right?: ReactNode; accent?: boolean; children: ReactNode }) {
  return (
    <div style={{ gridColumn: `span ${span}`, border: accent ? "1px solid rgba(255,180,84,.25)" : "1px solid var(--line2)", background: accent ? "rgba(255,180,84,.04)" : "var(--tint)", padding: 12 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 9 }}>
        <span style={{ fontSize: 7.5, letterSpacing: ".18em", color: "var(--txt3)" }}>{label}</span>{right}
      </div>
      {children}
    </div>
  );
}

const miniGauge = (color: string, pct: number, label: string) => (
  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
    <div style={{ width: 22, height: 22, borderRadius: "50%", background: `conic-gradient(${color} 0 ${pct}%,var(--tint2) ${pct}%)`, display: "grid", placeItems: "center" }}><div style={{ width: 15, height: 15, borderRadius: "50%", background: "var(--raised)" }} /></div>
    <span style={{ fontSize: 8, color: "var(--txt2)" }}>{label}</span>
  </div>
);

const loopStep = (label: string, color: string, active = false) => active
  ? <span style={{ padding: "0 18px", color: "var(--on-accent)", background: "var(--accent)", height: "100%", display: "flex", alignItems: "center", fontWeight: 700 }}>{label}</span>
  : <span style={{ padding: "0 18px", color }}>{label}</span>;
const sep = <span style={{ color: "var(--txt3)" }}>›</span>;

const pacingRow = (color: string, text: string) => (
  <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 9, color: "var(--txt2)" }}><span style={{ width: 6, height: 6, background: color }} />{text}</div>
);

/** Story-health level → gauge color (balanced → green, sparse → amber, problematic → red). */
const healthColor = (level: string) => (level === "balanced" ? "var(--green)" : level === "sparse" ? "var(--amber)" : "var(--blocking)");

/** Pacing category → dot color. */
const pacingColor = (category: string): string => {
  switch (category) {
    case "monotony":
    case "stagnation":
      return "var(--blocking)";
    case "clustering":
      return "var(--amber)";
    case "neglect":
    case "disappearance":
      return "var(--cyan)";
    default:
      return "var(--txt3)";
  }
};

/** Build the tension sparkline points across the SVG box (580 × 78) from scores (0–100). */
function tensionPolyline(points: SceneTensionDTO[]): { line: string; peak: { x: number; y: number } | null } {
  const W = 580;
  const H = 78;
  if (points.length === 0) return { line: "", peak: null };
  const stepX = points.length === 1 ? 0 : W / (points.length - 1);
  const toY = (score: number) => H - 4 - (Math.max(0, Math.min(100, score)) / 100) * (H - 8);
  let peakIdx = 0;
  for (let i = 1; i < points.length; i++) {
    const p = points[i];
    const best = points[peakIdx];
    if (p && best && p.score > best.score) peakIdx = i;
  }
  const coords = points.map((p, i) => `${(i * stepX).toFixed(1)},${toY(p.score).toFixed(1)}`);
  const peakPt = points[peakIdx];
  return {
    line: coords.join(" "),
    peak: peakPt ? { x: peakIdx * stepX, y: toY(peakPt.score) } : null,
  };
}

const message = (text: string) => (
  <div style={{ gridColumn: "1 / -1", padding: "34px 0", textAlign: "center", fontSize: 11, color: "var(--txt3)", letterSpacing: ".04em" }}>{text}</div>
);

const gauges = (h: StoryHealthDTO) => {
  const g = (signal: HealthSignalDTO) => miniGauge(healthColor(signal.level), Math.round(signal.score * 100), signal.label);
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 7 }}>
      {g(h.structure)}{g(h.characters)}{g(h.arcs)}{g(h.density)}
    </div>
  );
};

const num = (n: number) => n.toLocaleString();

export function NarrativeDashboard(props: PanelProps) {
  const dashboard = useDashboard();
  const health = useStoryHealth();
  const pacing = usePacing();

  const dash: NarrativeDashboardDTO | undefined = dashboard.data;
  const loading = dashboard.loading && !dashboard.data;

  // Derived overview counts (structure is the source of truth for scenes/words).
  const structure = dash?.structure;
  const characters: CharacterPresenceDTO[] = dash?.characters ?? [];
  const themes: ThemePresenceDTO[] = dash?.themes ?? [];
  const segments: ActSegmentDTO[] = structure?.segments ?? [];
  const tensionPoints: SceneTensionDTO[] = dash?.tension.points ?? [];
  const tensionFlags: string[] = dash?.tension.flags ?? [];
  const { line: tensionLine, peak } = tensionPolyline(tensionPoints);

  const totalScenes = structure?.total_scenes ?? 0;
  const totalWords = structure?.total_words ?? 0;
  const actCount = segments.length;
  const charCount = characters.length;

  // peak scene label, if any
  let peakIdx = 0;
  for (let i = 1; i < tensionPoints.length; i++) {
    const p = tensionPoints[i];
    const best = tensionPoints[peakIdx];
    if (p && best && p.score > best.score) peakIdx = i;
  }
  const peakScene = tensionPoints[peakIdx];

  // structure bar scaling (relative to the widest segment by word_count)
  const maxSegWords = segments.reduce((m, s) => Math.max(m, s.word_count), 0);

  const healthData = health.data;
  const pacingList: PacingInsightDTO[] = pacing.data ?? [];

  return (
    <PanelShell {...props}>
      <div data-screen-label="Narrative Dashboard" style={panelBox}>
        <Corners />
        {/* OS loop ribbon */}
        <div style={{ flex: "none", display: "flex", alignItems: "stretch", height: 42, borderBottom: "1px solid var(--line)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "0 18px", fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".1em", color: "var(--strong)", borderRight: "1px solid var(--line2)" }}>PROJECT OS</div>
          <div style={{ flex: 1, display: "flex", alignItems: "center", fontSize: 9, letterSpacing: ".14em" }}>
            {loopStep("UNDERSTAND", "var(--green)")}{sep}{loopStep("DECIDE", "", true)}{sep}{loopStep("ACT", "var(--txt2)")}{sep}{loopStep("VERIFY", "var(--txt2)")}{sep}{loopStep("APPLY", "var(--txt2)")}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 7, padding: "0 16px", fontSize: 8, color: "var(--txt3)", letterSpacing: ".1em" }}>light recompute · 0.2s</div>
        </div>
        {/* tile grid */}
        <div style={{ flex: 1, overflowY: "auto", padding: 13, display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 11, gridAutoRows: "min-content" }}>
          {loading
            ? message("Loading dashboard…")
            : dashboard.error
              ? message(`Couldn't load dashboard — ${dashboard.error}`)
              : !dash
                ? message("No dashboard data yet — write a few scenes to populate it")
                : (
            <>
              <Tile label="OVERVIEW">
                <div style={{ fontFamily: "'Chakra Petch'", fontSize: 26, color: "var(--strong)", lineHeight: 1 }}>{num(totalWords)}</div>
                <div style={{ fontSize: 8, color: "var(--txt3)", marginBottom: 9 }}>words{structure?.inferred ? " · acts inferred" : ""}</div>
                <div style={{ display: "flex", gap: 11, fontSize: 9, color: "var(--txt2)" }}><span>{totalScenes} sc</span><span>{charCount} ch</span><span>{actCount} act</span></div>
              </Tile>
              <Tile span={2} label="TENSION CURVE · scrubbable" right={peakScene ? <span style={{ fontSize: 8, color: "var(--blocking)" }}>▲ peak SC.{peakScene.scene_order}</span> : undefined}>
                {tensionPoints.length === 0 ? (
                  <div style={{ height: 78, display: "grid", placeItems: "center", fontSize: 9, color: "var(--txt3)" }}>No tension data</div>
                ) : (
                  <svg viewBox="0 0 580 78" style={{ width: "100%", height: 78, display: "block" }}>
                    <line x1="0" y1="39" x2="580" y2="39" stroke="var(--tint2)" />
                    <polyline points={tensionLine} fill="none" stroke="var(--amber)" strokeWidth="1.6" style={{ filter: "drop-shadow(0 0 3px rgba(245,177,51,.6))" }} />
                    {peak && <circle cx={peak.x} cy={peak.y} r="3" fill="var(--blocking)" />}
                  </svg>
                )}
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 7, color: "var(--txt3)", marginTop: 2, gap: 8, flexWrap: "wrap" }}>
                  {tensionFlags.length > 0
                    ? tensionFlags.map((f, i) => <span key={i} style={{ color: "var(--amber)" }}>{f}</span>)
                    : <><span>{tensionPoints[0] ? `SC.${tensionPoints[0].scene_order}` : ""}</span><span>{peakScene ? <span style={{ color: "var(--accent)" }}>▮ SC.{peakScene.scene_order}</span> : null}</span><span>{tensionPoints.length > 1 ? `SC.${tensionPoints[tensionPoints.length - 1]!.scene_order}` : ""}</span></>}
                </div>
              </Tile>
              <Tile label="STORY HEALTH">
                {health.loading && !healthData
                  ? <div style={{ fontSize: 9, color: "var(--txt3)" }}>Loading…</div>
                  : health.error
                    ? <div style={{ fontSize: 9, color: "var(--blocking)" }}>{health.error}</div>
                    : healthData
                      ? gauges(healthData)
                      : <div style={{ fontSize: 9, color: "var(--txt3)" }}>No health data</div>}
              </Tile>
              <Tile span={2} label="PACING INSIGHTS">
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {pacing.loading && !pacing.data
                    ? <div style={{ fontSize: 9, color: "var(--txt3)" }}>Loading…</div>
                    : pacing.error
                      ? <div style={{ fontSize: 9, color: "var(--blocking)" }}>{pacing.error}</div>
                      : pacingList.length === 0
                        ? <div style={{ fontSize: 9, color: "var(--txt3)" }}>No pacing issues detected</div>
                        : pacingList.map((p, i) => <div key={i}>{pacingRow(pacingColor(p.category), p.text)}</div>)}
                </div>
              </Tile>
              <Tile span={2} label="STRUCTURE DISTRIBUTION">
                {segments.length === 0 ? (
                  <div style={{ fontSize: 9, color: "var(--txt3)" }}>No acts yet</div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
                    {segments.map((s, i) => (
                      <div key={i} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontSize: 8, color: "var(--txt2)", width: 64, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{s.label}</span>
                        <div style={{ flex: 1, height: 6, background: "var(--tint2)" }}>
                          <div style={{ width: `${maxSegWords > 0 ? Math.round((s.word_count / maxSegWords) * 100) : 0}%`, height: "100%", background: "var(--accent)" }} />
                        </div>
                        <span style={{ fontSize: 8, color: "var(--txt3)", width: 70, textAlign: "right", whiteSpace: "nowrap" }}>{s.scene_count} sc · {num(s.word_count)}w</span>
                      </div>
                    ))}
                  </div>
                )}
              </Tile>
              <Tile span={2} label={`CHARACTER PRESENCE · ${charCount}`}>
                {characters.length === 0 ? (
                  <div style={{ fontSize: 9, color: "var(--txt3)" }}>No characters tracked</div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {characters.slice(0, 6).map((c) => presenceRow(c))}
                  </div>
                )}
              </Tile>
              <Tile span={2} label={`THEME PRESENCE · ${themes.length}`}>
                {themes.length === 0 ? (
                  <div style={{ fontSize: 9, color: "var(--txt3)" }}>No themes tracked</div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {themes.slice(0, 6).map((t) => presenceRow(t))}
                  </div>
                )}
              </Tile>
            </>
          )}
        </div>
        {/* summary line */}
        <div style={{ flex: "none", height: 24, borderTop: "1px solid var(--line2)", display: "flex", alignItems: "center", gap: 14, padding: "0 16px", background: "var(--base)", fontSize: 8, letterSpacing: ".1em", color: "var(--txt3)" }}>
          <span style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--green)" }}><span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--green)" }} />DETERMINISTIC · ADVISORY ONLY</span>
          <span style={{ marginLeft: "auto", color: "var(--txt2)" }}>{totalScenes} scenes · {charCount} characters · {pacingList.length} pacing insights</span>
        </div>
      </div>
    </PanelShell>
  );
}

/** Shared presence row used for both characters and themes (name + n/total scenes + bar). */
function presenceRow(item: CharacterPresenceDTO | ThemePresenceDTO) {
  const present = item.present_scenes.length;
  const total = item.total_scenes;
  const pct = total > 0 ? Math.round((present / total) * 100) : 0;
  const thin = item.flags.length > 0;
  // Themes carry a presence_source: be honest about whether a count is a prose
  // heuristic (≈) or backed by Controlling-Idea scene alignment (◆). Characters
  // (link-backed) have no such marker.
  const source = "presence_source" in item ? item.presence_source : undefined;
  const mark = source === "controlling_idea"
    ? { sym: "◆", color: "var(--cyan)", title: "Includes Controlling-Idea scene alignment (structural)" }
    : source
      ? { sym: "≈", color: "var(--txt3)", title: "Presence inferred from prose name/alias mentions (heuristic)" }
      : null;
  return (
    <div key={item.entry_id} style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <span style={{ fontSize: 9, color: "var(--txt2)", width: 78, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{item.name}</span>
      <div style={{ flex: 1, height: 5, background: "var(--tint2)" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: thin ? "var(--amber)" : "var(--cyan)" }} />
      </div>
      {mark && <span title={mark.title} style={{ fontSize: 8, color: mark.color, width: 8, textAlign: "center", cursor: "help" }}>{mark.sym}</span>}
      <span style={{ fontSize: 8, color: "var(--txt3)", width: 44, textAlign: "right" }}>{present}/{total}</span>
    </div>
  );
}
