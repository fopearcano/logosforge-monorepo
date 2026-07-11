import { useState, type CSSProperties, type ReactNode } from "react";
import type { PsykeRelationDTO } from "@logosforge/ui-contracts";
import { PanelShell, type PanelProps } from "../shell/PanelShell";
import { usePsykeEntries, usePsykeRelations, useGraphGravity } from "../../hooks";

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

type Meta = { icon: string; color: string; label: string };
const OTHER: Meta = { icon: "▣", color: "var(--txt3)", label: "Other" };
const TYPE: Record<string, Meta> = {
  character: { icon: "◆", color: "var(--c-char)", label: "Character" },
  place: { icon: "▲", color: "var(--c-place)", label: "Place" },
  object: { icon: "◇", color: "var(--c-obj)", label: "Object" },
  lore: { icon: "⬢", color: "var(--c-lore)", label: "Lore" },
  theme: { icon: "✦", color: "var(--c-theme)", label: "Theme" },
  other: OTHER,
};
const metaOf = (t: string): Meta => TYPE[t] ?? OTHER;
const LAYER_TYPES = ["character", "place", "object", "lore", "theme", "other"];

// virtual canvas — nodes laid on an ellipse (deterministic, no DTO positions)
const CW = 900, CH = 540, CX = CW / 2, CY = CH / 2, RX = 330, RY = 210;

const check = (label: string, on: boolean) => (
  <label style={{ display: "flex", alignItems: "center", gap: 7 }}><span style={{ width: 10, height: 10, border: on ? "1px solid var(--line-cy)" : "1px solid var(--line2)", background: on ? "var(--accent)" : undefined }} />{label}</label>
);
const gbar = (label: string, color: string, pct: number) => (
  <div style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 8.5, color: "var(--txt2)" }}><span style={{ width: 62 }}>{label}</span><div style={{ flex: 1, height: 4, background: "var(--tint2)" }}><div style={{ width: `${pct}%`, height: "100%", background: color }} /></div></div>
);
function Insight({ icon, label, labelColor, text, border, bg }: { icon: ReactNode; label: string; labelColor: string; text: string; border: string; bg: string }) {
  return (
    <div style={{ border: `1px solid ${border}`, background: bg, padding: "9px 10px", marginBottom: 7 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>{icon}<span style={{ fontSize: 7.5, letterSpacing: ".14em", color: labelColor }}>{label}</span></div>
      <div style={{ fontSize: 10, color: "var(--txt)", lineHeight: 1.4 }}>{text}</div>
    </div>
  );
}
const message = (text: string) => (
  <div style={{ flex: 1, display: "grid", placeItems: "center", fontSize: 11, color: "var(--txt3)", letterSpacing: ".04em" }}>{text}</div>
);

export function KnowledgeGraph(props: PanelProps) {
  const { data: entriesData, loading, error } = usePsykeEntries();
  const { data: relData } = usePsykeRelations();
  const { data: gravity } = useGraphGravity();
  const entries = entriesData ?? [];
  const relations = relData ?? [];

  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [selId, setSelId] = useState<number | null>(null);
  const [gravityOn, setGravityOn] = useState(false);
  const toggleType = (t: string) => setHidden((h) => { const n = new Set(h); n.has(t) ? n.delete(t) : n.add(t); return n; });

  const visible = entries.filter((e) => !hidden.has(e.type));
  const visibleIds = new Set(visible.map((e) => e.id));
  const edges = relations.filter((r) => visibleIds.has(r.source_id) && visibleIds.has(r.target_id));

  const degree = new Map<number, number>();
  for (const e of visible) degree.set(e.id, 0);
  for (const r of edges) { degree.set(r.source_id, (degree.get(r.source_id) ?? 0) + 1); degree.set(r.target_id, (degree.get(r.target_id) ?? 0) + 1); }
  const deg = (id: number) => degree.get(id) ?? 0;
  const maxDeg = Math.max(1, ...[...degree.values()]);

  // order by type cluster, then degree desc — so related types sit near each other
  const ordered = [...visible].sort((a, b) => (a.type === b.type ? deg(b.id) - deg(a.id) : a.type.localeCompare(b.type)));
  const N = ordered.length;
  const pos = new Map<number, { x: number; y: number }>();
  ordered.forEach((e, i) => {
    if (N <= 1) { pos.set(e.id, { x: CX, y: CY }); return; }
    const ang = (i / N) * Math.PI * 2 - Math.PI / 2;
    pos.set(e.id, { x: CX + RX * Math.cos(ang), y: CY + RY * Math.sin(ang) });
  });
  const xy = (id: number) => pos.get(id) ?? { x: CX, y: CY };

  let hubId: number | null = null, hubDeg = -1;
  for (const e of visible) { if (deg(e.id) > hubDeg) { hubDeg = deg(e.id); hubId = e.id; } }
  const selected = visible.find((e) => e.id === selId) ?? visible.find((e) => e.id === hubId) ?? visible[0];

  const neighbors = selected
    ? edges.filter((r) => r.source_id === selected.id || r.target_id === selected.id).map((r) => {
        const out = r.source_id === selected.id;
        return { id: out ? r.target_id : r.source_id, name: out ? r.target : r.source, rel: r.relation_type, out };
      })
    : [];
  const orphans = visible.filter((e) => deg(e.id) === 0);

  // story-gravity overlay — each PSYKE entry maps to graph node "PSYKE:<id>"
  const gravMap = new Map((gravity?.nodes ?? []).map((n) => [n.node_id, n]));
  const gravOf = (id: number) => gravMap.get(`PSYKE:${id}`);
  const gravAvailable = !!gravity?.available && gravMap.size > 0;
  const glowThreshold = gravity?.glow_threshold ?? 0.55;
  const useGrav = gravityOn && gravAvailable;
  const sizeOf = (id: number) =>
    useGrav ? 30 + (gravOf(id)?.total ?? 0) * 40 : 30 + (deg(id) / maxDeg) * 34;
  const empty = !loading && !error && entries.length === 0;

  return (
    <PanelShell {...props}>
      <div data-screen-label="Knowledge Graph" style={panelBox}>
        <div style={{ position: "absolute", top: -1, left: -1, width: 14, height: 14, borderTop: "1px solid var(--crimson)", borderLeft: "1px solid var(--crimson)", zIndex: 9 }} />
        <div style={{ position: "absolute", top: 3, left: 3, width: 5, height: 5, background: "var(--crimson)", zIndex: 9 }} />
        {/* toolbar */}
        <div style={{ height: 44, flex: "none", display: "flex", alignItems: "center", gap: 13, padding: "0 16px", borderBottom: "1px solid var(--line)", background: "var(--tint)", zIndex: 5 }}>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 14, letterSpacing: ".12em", color: "var(--strong)" }}>KNOWLEDGE GRAPH</span>
          <span style={{ fontSize: 7.5, color: "var(--txt3)", border: "1px solid var(--line2)", padding: "2px 7px", letterSpacing: ".12em" }}>DERIVED FROM PSYKE</span>
          <div style={{ flex: 1 }} />
          <span
            onClick={() => gravAvailable && setGravityOn((v) => !v)}
            title={gravAvailable ? "Size nodes by story gravity" : "Gravity unavailable for this project"}
            style={{ fontSize: 9, color: useGrav ? "var(--on-accent)" : gravAvailable ? "var(--accent)" : "var(--txt3)", background: useGrav ? "var(--accent)" : undefined, padding: useGrav ? "3px 7px" : undefined, letterSpacing: ".1em", cursor: gravAvailable ? "pointer" : "default" }}
          >⊹ GRAVITY</span>
        </div>

        <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
          {/* LAYERS / FILTERS */}
          <div style={{ width: 198, flex: "none", borderRight: "1px solid var(--line)", background: "var(--panel2)", overflowY: "auto", padding: "12px 11px" }}>
            <div style={{ fontSize: 7.5, letterSpacing: ".22em", color: "var(--txt3)", marginBottom: 8 }}>LAYERS · NODE TYPES</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 5, fontSize: 9.5 }}>
              {LAYER_TYPES.map((t) => {
                const m = metaOf(t);
                const count = entries.filter((e) => e.type === t).length;
                const on = !hidden.has(t);
                return (
                  <label key={t} onClick={() => toggleType(t)} style={{ display: "flex", alignItems: "center", gap: 8, color: on ? "var(--txt)" : "var(--txt3)", cursor: "pointer", opacity: count === 0 ? 0.4 : 1 }}>
                    <span style={{ width: 10, height: 10, background: on ? m.color : undefined, border: on ? undefined : "1px solid var(--txt3)" }} /><span style={{ color: m.color }}>{m.icon}</span>{m.label}<span style={{ marginLeft: "auto", color: "var(--txt3)" }}>{count}</span>
                  </label>
                );
              })}
            </div>
            <div style={{ fontSize: 7.5, letterSpacing: ".22em", color: "var(--txt3)", margin: "14px 0 8px" }}>VIEW</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 9, color: "var(--txt2)" }}>
              {check("skeleton only", false)}{check("hide isolated", false)}{check("mention edges", false)}{check("2-hop expand", true)}
            </div>
            <div style={{ fontSize: 7.5, letterSpacing: ".22em", color: "var(--txt3)", margin: "14px 0 8px" }}>PHASE-10P</div>
            <div style={{ fontSize: 8.5, color: "var(--txt2)", marginBottom: 5 }}>confidence_min</div>
            <div style={{ height: 5, background: "var(--tint2)", marginBottom: 4, position: "relative" }}><div style={{ width: "55%", height: "100%", background: "var(--green)" }} /><div style={{ position: "absolute", left: "55%", top: -3, width: 3, height: 11, background: "var(--strong)" }} /></div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 7, color: "var(--txt3)" }}><span>possible</span><span style={{ color: "var(--green)" }}>likely</span><span>confirmed</span></div>
          </div>

          {/* GRAPH CANVAS */}
          <div style={{ flex: 1, minWidth: 0, position: "relative", overflow: "hidden", display: "grid", placeItems: "center" }}>
            {loading ? message("Building graph…") : error ? message(`Couldn't load graph — ${error}`) : empty ? message("No PSYKE entities yet — the graph builds from your story bible") : (
              <div style={{ position: "relative", width: CW, height: CH, maxWidth: "100%", maxHeight: "100%" }}>
                {/* edges */}
                <svg viewBox={`0 0 ${CW} ${CH}`} preserveAspectRatio="xMidYMid meet" style={{ position: "absolute", inset: 0, width: "100%", height: "100%", zIndex: 1 }}>
                  <defs>
                    <marker id="kg-arrow" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6" fill="none" stroke="#8b95a5" strokeWidth="1.1" /></marker>
                  </defs>
                  {edges.map((r: PsykeRelationDTO) => {
                    const a = xy(r.source_id), b = xy(r.target_id);
                    const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
                    const hot = selected && (r.source_id === selected.id || r.target_id === selected.id);
                    return (
                      <g key={r.id} opacity={hot ? 1 : 0.5}>
                        <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={hot ? "var(--accent)" : "#8b95a5"} strokeWidth={hot ? 1.8 : 1.2} markerEnd="url(#kg-arrow)" />
                        <text x={mx} y={my - 3} textAnchor="middle" fontSize="8" fill={hot ? "#cfe8ff" : "#8b95a5"} style={{ pointerEvents: "none" }}>{r.relation_type}</text>
                      </g>
                    );
                  })}
                </svg>
                {/* nodes */}
                {ordered.map((e) => {
                  const m = metaOf(e.type);
                  const p = xy(e.id);
                  const size = sizeOf(e.id);
                  const isHub = e.id === hubId && hubDeg > 0;
                  const isSel = selected?.id === e.id;
                  const highGrav = useGrav && (gravOf(e.id)?.total ?? 0) >= glowThreshold;
                  return (
                    <div key={e.id} onClick={() => setSelId(e.id)} style={{ position: "absolute", left: p.x, top: p.y, transform: "translate(-50%,-50%)", zIndex: isSel ? 4 : 3, textAlign: "center", cursor: "pointer" }}>
                      {highGrav && <div style={{ position: "absolute", left: "50%", top: size / 2, transform: "translate(-50%,-50%)", width: size + 48, height: size + 48, borderRadius: "50%", background: `radial-gradient(circle, ${m.color}40, transparent 68%)`, pointerEvents: "none", zIndex: 0 }} />}
                      {(isHub || isSel) && <div style={{ position: "absolute", left: "50%", top: size / 2, transform: "translate(-50%,-50%)", width: size + 30, height: size + 30, borderRadius: "50%", border: `1px solid ${m.color}`, animation: "lf-halo 3s ease-in-out infinite" }} />}
                      <div style={{ width: size, height: size, borderRadius: "50%", border: `${isSel ? 2.5 : 2}px solid ${m.color}`, background: "var(--tint)", display: "grid", placeItems: "center", color: m.color, fontSize: Math.round(size * 0.34), boxShadow: isSel || isHub ? `0 0 20px ${m.color}` : undefined }}>{m.icon}</div>
                      <div style={{ fontFamily: "'Chakra Petch'", fontSize: size >= 50 ? 12 : 9.5, color: isSel ? "var(--strong)" : "var(--txt)", marginTop: 4, letterSpacing: ".04em", whiteSpace: "nowrap" }}>{e.name}</div>
                      {isHub && <div style={{ fontSize: 7, color: "var(--accent)", letterSpacing: ".16em" }}>◉ MOST CONNECTED</div>}
                    </div>
                  );
                })}
                {/* legend */}
                <div style={{ position: "absolute", left: 8, bottom: 8, background: "var(--tint)", border: "1px solid var(--line2)", padding: "7px 10px", zIndex: 4, fontSize: 8, color: "var(--txt2)" }}>
                  <div style={{ display: "flex", gap: 11 }}><span><span style={{ color: "#8b95a5" }}>──▸</span> relation</span><span><span style={{ color: "var(--accent)" }}>──</span> selected</span></div>
                  <div style={{ marginTop: 3, color: useGrav ? "var(--accent)" : "var(--txt3)" }}>node size = {useGrav ? "story gravity ⊹" : "relation degree"}</div>
                </div>
              </div>
            )}
          </div>

          {/* INSPECTOR + INSIGHTS */}
          <div style={{ width: 372, flex: "none", borderLeft: "1px solid var(--line)", background: "var(--panel2)", display: "flex", flexDirection: "column", overflow: "hidden" }}>
            <div style={{ flex: "none", height: 30, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 13px", borderBottom: "1px solid var(--line)", background: "rgba(76,194,255,.04)" }}>
              <span style={{ fontSize: 8.5, letterSpacing: ".22em", color: "var(--accent)" }}>INSPECTOR · explain_node</span><span style={{ fontSize: 8, color: "var(--txt3)" }}>⠿</span>
            </div>
            {selected ? (
              <div style={{ flex: "none", padding: 13, borderBottom: "1px solid var(--line2)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
                  <span style={{ width: 30, height: 30, display: "grid", placeItems: "center", border: `1px solid ${metaOf(selected.type).color}`, color: metaOf(selected.type).color, fontSize: 14 }}>{metaOf(selected.type).icon}</span>
                  <div style={{ minWidth: 0 }}><div style={{ fontFamily: "'Chakra Petch'", fontSize: 15, color: "var(--strong)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{selected.name}</div><div style={{ fontSize: 8, color: "var(--txt3)", letterSpacing: ".1em" }}>{metaOf(selected.type).label.toUpperCase()} · {neighbors.length} RELATION{neighbors.length === 1 ? "" : "S"}</div></div>
                  {selected.is_global && <span style={{ marginLeft: "auto", fontSize: 7, color: "var(--c-place)", border: "1px solid rgba(245,177,51,.35)", padding: "2px 6px", letterSpacing: ".06em" }}>GLOBAL</span>}
                </div>
                <div style={{ fontSize: 7.5, letterSpacing: ".18em", color: "var(--txt3)", marginBottom: 6 }}>CENTRALITY · {(deg(selected.id) / maxDeg).toFixed(2)}</div>
                <div style={{ marginBottom: 11 }}>{gbar("degree", "var(--cyan)", (deg(selected.id) / maxDeg) * 100)}</div>
                {gravAvailable && gravOf(selected.id) && (
                  <>
                    <div style={{ fontSize: 7.5, letterSpacing: ".18em", color: "var(--accent)", marginBottom: 6 }}>STORY GRAVITY · {gravOf(selected.id)!.total.toFixed(2)}</div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 11 }}>
                      {gbar("narrative", "var(--c-char)", gravOf(selected.id)!.narrative * 100)}
                      {gbar("thematic", "var(--c-theme)", gravOf(selected.id)!.thematic * 100)}
                      {gbar("structural", "var(--c-place)", gravOf(selected.id)!.structural * 100)}
                    </div>
                  </>
                )}
                <div style={{ fontSize: 7.5, letterSpacing: ".18em", color: "var(--txt3)", marginBottom: 6 }}>CONNECTED TO</div>
                {neighbors.length === 0 ? (
                  <div style={{ fontSize: 9.5, color: "var(--txt3)", fontStyle: "italic" }}>No relations — this node is isolated.</div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                    {neighbors.map((n, i) => (
                      <div key={`${n.id}-${i}`} style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 9.5, color: "var(--txt2)", cursor: "pointer" }} onClick={() => setSelId(n.id)}>
                        <span style={{ color: "var(--txt3)" }}>{n.out ? "→" : "←"}</span><span style={{ color: "var(--strong)" }}>{n.name}</span><span style={{ color: "var(--accent)" }}>{n.rel}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : null}
            <div style={{ flex: 1, overflowY: "auto", padding: 13 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                <div style={{ position: "relative", width: 20, height: 20, borderRadius: "50%", border: "1px solid var(--line)", overflow: "hidden" }}><div style={{ position: "absolute", inset: 0, background: "conic-gradient(from 0deg,rgba(232,68,58,.5),transparent 30%)", animation: "lf-pulse 2.6s infinite" }} /></div>
                <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 12, letterSpacing: ".1em", color: "var(--strong)" }}>INSIGHTS</span>
                <span style={{ marginLeft: "auto", fontSize: 8, color: "var(--txt3)" }}>DERIVED</span>
              </div>
              {hubId != null && hubDeg > 0 && (
                <Insight border="var(--line2)" bg="var(--tint)" labelColor="var(--txt2)" icon={<span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--info)" }} />} label="CENTRAL" text={`${visible.find((e) => e.id === hubId)?.name ?? ""} is the most connected — ${hubDeg} relations. Rewrites carry risk.`} />
              )}
              {orphans.length > 0 && (
                <Insight border="var(--line2)" bg="var(--tint)" labelColor="var(--warning)" icon={<span style={{ width: 8, height: 8, transform: "rotate(45deg)", background: "var(--warning)" }} />} label="ORPHANS" text={`${orphans.length} isolated: ${orphans.slice(0, 4).map((e) => e.name).join(", ")}${orphans.length > 4 ? "…" : ""}.`} />
              )}
              {edges.length === 0 && visible.length > 0 && (
                <Insight border="var(--line-cy)" bg="rgba(76,194,255,.05)" labelColor="var(--cyan)" icon={<span style={{ width: 7, height: 7, borderRadius: "50%", border: "2px solid var(--suggestion)" }} />} label="SUGGESTION" text="No relations yet — add some in PSYKE to weave the web." />
              )}
            </div>
          </div>
        </div>

        {/* provenance status */}
        <div style={{ height: 24, flex: "none", borderTop: "1px solid var(--line2)", display: "flex", alignItems: "center", gap: 14, padding: "0 16px", background: "var(--base)", fontSize: 8, letterSpacing: ".1em", color: "var(--txt3)" }}>
          <span style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--green)" }}><span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--green)", boxShadow: "0 0 6px var(--green)" }} />DETERMINISTIC · NO AI · REBUILT LIVE</span>
          <span>{visible.length} NODES</span><span>{edges.length} EDGES</span><span style={{ color: "var(--warning)" }}>{orphans.length} ORPHANS</span>
          {hidden.size > 0 && <span style={{ color: "var(--txt2)" }}>{hidden.size} LAYER{hidden.size === 1 ? "" : "S"} HIDDEN</span>}
          <span style={{ marginLeft: "auto", color: "var(--txt2)" }}>current project only</span>
        </div>
      </div>
    </PanelShell>
  );
}
