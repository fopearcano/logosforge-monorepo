import type { CSSProperties, ReactNode } from "react";
import type { TimelineEventDTO } from "@logosforge/ui-contracts";
import { PanelShell, type PanelProps } from "../shell/PanelShell";
import { useTimeline } from "../../hooks";

const panelBox: CSSProperties = {
  position: "relative",
  width: "100%",
  height: "100%",
  background: "linear-gradient(180deg,#080a0f,#05070b)",
  border: "1px solid var(--line)",
  boxShadow: "0 16px 60px rgba(0,0,0,.6)",
  overflow: "hidden",
  display: "flex",
  flexDirection: "column",
};

const STEP = 172; // horizontal px per order_index unit
const LABEL_W = 132;
const CARD_W = 154;

// lane palette — one (color, faint-bg) per act, cycled
const LANES = [
  { color: "var(--cyan)", bg: "rgba(76,194,255,.05)" },
  { color: "var(--green)", bg: "rgba(98,217,154,.05)" },
  { color: "var(--crimson)", bg: "rgba(232,68,58,.05)" },
  { color: "var(--violet)", bg: "rgba(176,124,255,.05)" },
  { color: "var(--amber)", bg: "rgba(245,177,51,.05)" },
  { color: "var(--pink)", bg: "rgba(255,122,198,.06)" },
];
const laneOf = (i: number) => LANES[i % LANES.length] ?? LANES[0]!;

function Lane({ height, color, label, labelBg, sub, children }: { height: number; color: string; label: string; labelBg: string; sub?: string; children: ReactNode }) {
  return (
    <div style={{ display: "flex", height, borderBottom: "1px solid var(--line2)" }}>
      <div style={{ width: LABEL_W, flex: "none", borderRight: "1px solid var(--line2)", padding: "9px 10px", background: labelBg }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}><span style={{ width: 7, height: 7, background: color }} /><span style={{ fontSize: 9, color, fontFamily: "'Chakra Petch'", letterSpacing: ".06em", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{label}</span></div>
        {sub && <div style={{ fontSize: 7, color: "var(--txt3)", marginTop: 4 }}>{sub}</div>}
      </div>
      <div style={{ flex: 1, position: "relative" }}>{children}</div>
    </div>
  );
}

function TCard({ left, width, height = 60, border, bg, children }: { left: number; width: number; height?: number; border: string; bg: string; children: ReactNode }) {
  return <div style={{ position: "absolute", left, top: 12, width, height, border: `1px solid ${border}`, background: bg, padding: "6px 8px", overflow: "hidden" }}>{children}</div>;
}
const chip = (t: string, color: string, border?: string) => <span style={{ fontSize: 6.5, color, border: border ? `1px solid ${border}` : undefined, padding: border ? "0 4px" : undefined, whiteSpace: "nowrap" }}>{t}</span>;

const message = (text: string) => (
  <div style={{ flex: 1, display: "grid", placeItems: "center", padding: "34px 0", textAlign: "center", fontSize: 11, color: "var(--txt3)", letterSpacing: ".04em" }}>{text}</div>
);

/** Group events by `act`, keeping acts in first-seen order; empty-act events go to `unassigned`. */
function byAct(events: TimelineEventDTO[]): { acts: { act: string; events: TimelineEventDTO[] }[]; unassigned: TimelineEventDTO[] } {
  const order: string[] = [];
  const groups = new Map<string, TimelineEventDTO[]>();
  const unassigned: TimelineEventDTO[] = [];
  for (const e of events) {
    if (!e.act) { unassigned.push(e); continue; }
    let bucket = groups.get(e.act);
    if (!bucket) { bucket = []; groups.set(e.act, bucket); order.push(e.act); }
    bucket.push(e);
  }
  return { acts: order.map((act) => ({ act, events: groups.get(act) ?? [] })), unassigned };
}

export function TimelinePanel(props: PanelProps) {
  const { data, loading, error } = useTimeline();
  const events = (data ?? []).slice().sort((a, b) => a.order_index - b.order_index);
  const { acts, unassigned } = byAct(events);
  const maxOrder = events.reduce((m, e) => Math.max(m, e.order_index), 1);
  const board = LABEL_W + maxOrder * STEP + 90;
  const xOf = (e: TimelineEventDTO) => (e.order_index - 1) * STEP + 8;

  return (
    <PanelShell {...props}>
      <div data-screen-label="Plot-Lane Timeline" style={panelBox}>
        <div style={{ position: "absolute", top: -1, left: -1, width: 14, height: 14, borderTop: "1px solid var(--crimson)", borderLeft: "1px solid var(--crimson)", zIndex: 9 }} />
        <div style={{ position: "absolute", top: 3, left: 3, width: 5, height: 5, background: "var(--crimson)", zIndex: 9 }} />
        {/* toolbar */}
        <div style={{ height: 40, flex: "none", display: "flex", alignItems: "center", gap: 14, padding: "0 16px", borderBottom: "1px solid var(--line)" }}>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".12em", color: "#fff" }}>PLOT · TIMELINE</span>
          <span style={{ fontSize: 8, color: "var(--accent)", border: "1px solid var(--line-cy)", padding: "2px 7px", letterSpacing: ".1em" }}>{events.length} EVENTS · {acts.length} ACTS</span>
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 7.5, color: "var(--txt3)", border: "1px solid var(--line2)", padding: "2px 7px", letterSpacing: ".12em" }}>DERIVED FROM STRUCTURE</span>
        </div>

        {/* horizontally-scrollable board */}
        {loading
          ? message("Loading timeline…")
          : error
            ? message(`Couldn't load timeline — ${error}`)
            : events.length === 0
              ? message("No timeline yet — events derive from your scenes")
              : (
                <div style={{ flex: 1, overflow: "auto" }}>
                  <div style={{ width: board, minWidth: board }}>
                    {/* ruler — gridline per order_index step */}
                    <div style={{ height: 20, display: "flex", alignItems: "center", borderBottom: "1px solid var(--line2)", backgroundImage: `repeating-linear-gradient(90deg,transparent 0 ${STEP - 1}px,rgba(245,177,51,.35) ${STEP - 1}px ${STEP}px)`, backgroundPosition: `${LABEL_W}px 0`, paddingLeft: 14 }}>
                      <span style={{ fontSize: 7, letterSpacing: ".16em", color: "var(--txt3)" }}>ORDER →</span>
                    </div>
                    {/* act lanes */}
                    {acts.map(({ act, events: evs }, i) => {
                      const lane = laneOf(i);
                      return (
                        <Lane key={act} height={84} color={lane.color} label={act} labelBg={lane.bg} sub={`${evs.length} ev`}>
                          {evs.map((e) => (
                            <TCard key={e.id} left={xOf(e)} width={CARD_W} border={lane.color} bg={lane.bg}>
                              <div title={e.title} style={{ fontSize: 8, color: "#fff", lineHeight: 1.25, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{e.title}</div>
                              <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 4 }}>
                                {e.chapter && chip(`▸ ${e.chapter}`, "var(--txt3)")}
                                {e.time_of_day && chip(e.time_of_day, "var(--amber)", "rgba(245,177,51,.3)")}
                                {e.duration_minutes > 0 && chip(`${e.duration_minutes}m`, "var(--txt3)")}
                              </div>
                              {e.character_states.length > 0 && (
                                <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 4 }}>
                                  {e.character_states.slice(0, 2).map((cs) => (
                                    <span key={cs.character} title={`${cs.character}: ${cs.state}`} style={{ fontSize: 6.5, color: lane.color, border: `1px solid ${lane.color}`, padding: "0 4px", whiteSpace: "nowrap" }}>{cs.character}</span>
                                  ))}
                                  {e.character_states.length > 2 && chip(`+${e.character_states.length - 2}`, "var(--txt3)")}
                                </div>
                              )}
                            </TCard>
                          ))}
                        </Lane>
                      );
                    })}
                    {/* unassigned — events with no act */}
                    {unassigned.length > 0 && (
                      <Lane height={84} color="var(--txt3)" label="UNASSIGNED" labelBg="rgba(255,255,255,.02)" sub={`${unassigned.length} ev · no act`}>
                        {unassigned.map((e, i) => (
                          <TCard key={e.id} left={i * STEP + 8} width={CARD_W} border="var(--line2)" bg="rgba(255,255,255,.02)">
                            <div title={e.title} style={{ fontSize: 8, color: "var(--txt2)", lineHeight: 1.25, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{e.title}</div>
                            <div style={{ fontSize: 6.5, color: "var(--txt3)", marginTop: 4 }}>off timeline</div>
                          </TCard>
                        ))}
                      </Lane>
                    )}
                  </div>
                </div>
              )}
      </div>
    </PanelShell>
  );
}
