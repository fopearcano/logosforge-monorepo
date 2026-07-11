import type { CSSProperties } from "react";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";

const panelBox: CSSProperties = {
  position: "relative",
  width: "100%",
  height: "100%",
  background: "radial-gradient(80% 70% at 42% 42%,var(--raised),var(--base) 75%)",
  border: "1px solid var(--line)",
  boxShadow: "0 16px 60px rgba(0,0,0,.6)",
  overflow: "hidden",
};

interface NodeDef {
  left: number; top: number; size: number; border: string; bg: string; shadow?: string;
  icon: string; iconColor?: string; iconSize: number; label: string; labelColor?: string; labelSize: number;
  halo?: boolean; focus?: boolean; dim?: boolean; borderWidth?: number;
}

const NODES: NodeDef[] = [
  { left: 360, top: 290, size: 64, border: "var(--cyan)", bg: "radial-gradient(circle,rgba(76,194,255,.25),rgba(76,194,255,.04))", shadow: "0 0 22px rgba(76,194,255,.3)", icon: "◆", iconSize: 20, label: "MARLOW", labelColor: "var(--strong)", labelSize: 12 },
  { left: 560, top: 460, size: 72, border: "var(--cyan)", bg: "radial-gradient(circle,rgba(76,194,255,.3),rgba(76,194,255,.05))", shadow: "0 0 30px rgba(76,194,255,.5)", icon: "◆", iconColor: "var(--strong)", iconSize: 22, label: "VESPER", labelColor: "var(--strong)", labelSize: 13, halo: true, focus: true },
  { left: 620, top: 680, size: 54, border: "var(--crimson)", bg: "radial-gradient(circle,rgba(232,68,58,.25),rgba(232,68,58,.04))", shadow: "0 0 18px rgba(232,68,58,.35)", icon: "◆", iconSize: 17, label: "THE WARDEN", labelColor: "var(--strong)", labelSize: 11 },
  { left: 250, top: 580, size: 46, border: "var(--amber)", bg: "radial-gradient(circle,rgba(245,177,51,.2),transparent)", icon: "▲", iconSize: 15, label: "HELIOS-9", labelSize: 10 },
  { left: 840, top: 340, size: 44, border: "var(--violet)", bg: "radial-gradient(circle,rgba(176,124,255,.2),transparent)", icon: "◇", iconSize: 14, label: "BLACK BOX", labelSize: 10 },
  { left: 880, top: 580, size: 42, border: "#ff7ac6", bg: "radial-gradient(circle,rgba(255,122,198,.18),transparent)", icon: "✦", iconSize: 14, label: "STATIC", labelSize: 10 },
  { left: 720, top: 190, size: 40, border: "var(--green)", bg: "radial-gradient(circle,rgba(98,217,154,.18),transparent)", icon: "⬢", iconSize: 13, label: "KESSLER BURN", labelSize: 10 },
  { left: 220, top: 320, size: 34, border: "var(--cyan)", bg: "rgba(76,194,255,.06)", icon: "◆", iconSize: 11, label: "ARI", labelColor: "var(--txt2)", labelSize: 9, dim: true, borderWidth: 1 },
];

function Node(n: NodeDef) {
  const mt = n.size >= 54 ? 5 : n.size >= 40 ? 4 : 3;
  return (
    <div style={{ position: "absolute", left: n.left, top: n.top, transform: "translate(-50%,-50%)", zIndex: 3, textAlign: "center", opacity: n.dim ? 0.7 : undefined }}>
      {n.halo && <div style={{ position: "absolute", inset: -10, borderRadius: "50%", border: "1px solid var(--cyan)", animation: "lf-halo 2.8s ease-in-out infinite" }} />}
      <div style={{ width: n.size, height: n.size, borderRadius: "50%", border: `${n.borderWidth ?? 2}px solid ${n.border}`, background: n.bg, display: "grid", placeItems: "center", color: n.iconColor ?? n.border, fontSize: n.iconSize, boxShadow: n.shadow }}>{n.icon}</div>
      <div style={{ fontFamily: "'Chakra Petch'", fontSize: n.labelSize, color: n.labelColor ?? "var(--txt)", marginTop: mt, letterSpacing: ".04em" }}>{n.label}</div>
      {n.focus && <div style={{ fontSize: 7, color: "var(--accent)", letterSpacing: ".16em" }}>◉ FOCUS</div>}
    </div>
  );
}

const edgeLabel = (left: number, top: number, color: string, text: string) => (
  <div style={{ position: "absolute", left, top, fontSize: 8, color, background: "var(--tint)", padding: "1px 5px", zIndex: 2 }}>{text}</div>
);

export function RelationGraph(props: PanelProps) {
  return (
    <PanelShell {...props}>
      <div data-screen-label="Relation Graph" style={panelBox}>
        <div style={{ position: "absolute", top: -1, left: -1, width: 14, height: 14, borderTop: "1px solid var(--crimson)", borderLeft: "1px solid var(--crimson)", zIndex: 5 }} />
        <div style={{ position: "absolute", top: 3, left: 3, width: 5, height: 5, background: "var(--crimson)", zIndex: 5 }} />
        {/* toolbar */}
        <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 40, display: "flex", alignItems: "center", gap: 12, padding: "0 14px", borderBottom: "1px solid var(--line)", background: "var(--tint)", zIndex: 4 }}>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".12em", color: "var(--strong)" }}>RELATION GRAPH</span>
          <span style={{ fontSize: 9, color: "var(--txt3)" }}>⌕ focus…</span>
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 8.5, color: "var(--txt2)", letterSpacing: ".1em" }}>LAYOUT FORCE ▾</span>
          <span style={{ fontSize: 8.5, color: "var(--accent)", letterSpacing: ".1em" }}>⊹ GRAVITY</span>
          <span style={{ fontSize: 8.5, color: "var(--txt2)", letterSpacing: ".1em" }}>FIT</span>
        </div>

        {/* edges */}
        <svg viewBox="0 0 1240 820" style={{ position: "absolute", left: 0, top: 40, width: "100%", height: 820, zIndex: 1 }}>
          <defs>
            <marker id="ar-cy" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6" fill="none" stroke="#4cc2ff" strokeWidth="1" /></marker>
            <marker id="ar-cr" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6" fill="none" stroke="#e8443a" strokeWidth="1" /></marker>
            <marker id="ar-am" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6" fill="none" stroke="#f5b133" strokeWidth="1" /></marker>
          </defs>
          <line x1="360" y1="250" x2="560" y2="420" stroke="#4cc2ff" strokeWidth="2" opacity=".85" />
          <line x1="360" y1="250" x2="620" y2="640" stroke="#e8443a" strokeWidth="1.6" markerEnd="url(#ar-cr)" opacity=".8" />
          <line x1="560" y1="420" x2="720" y2="150" stroke="#f5b133" strokeWidth="1.6" markerEnd="url(#ar-am)" opacity=".8" />
          <line x1="720" y1="150" x2="840" y2="300" stroke="#62d99a" strokeWidth="1.4" strokeDasharray="5 4" markerEnd="url(#ar-cy)" opacity=".7" style={{ animation: "lf-dash 1.4s linear infinite" }} />
          <line x1="880" y1="540" x2="560" y2="420" stroke="#ff7ac6" strokeWidth="1.3" strokeDasharray="3 4" opacity=".6" />
          <line x1="880" y1="540" x2="360" y2="250" stroke="#ff7ac6" strokeWidth="1.3" strokeDasharray="3 4" opacity=".5" />
          <line x1="360" y1="250" x2="250" y2="540" stroke="#8b95a5" strokeWidth="1.2" opacity=".4" />
          <line x1="220" y1="280" x2="360" y2="250" stroke="#4cc2ff" strokeWidth="1.3" opacity=".55" />
          <line x1="620" y1="640" x2="250" y2="540" stroke="#e8443a" strokeWidth="1.3" markerEnd="url(#ar-cr)" opacity=".5" />
        </svg>
        {edgeLabel(430, 360, "var(--cyan)", "confides")}
        {edgeLabel(470, 495, "var(--crimson)", "opposes ⚔")}
        {edgeLabel(650, 290, "var(--amber)", "sets up →")}
        {edgeLabel(790, 240, "var(--green)", "pays off →")}

        {NODES.map((n) => <Node key={n.label} {...n} />)}

        {/* legend */}
        <div style={{ position: "absolute", left: 14, bottom: 12, background: "var(--tint)", border: "1px solid var(--line2)", padding: "9px 11px", zIndex: 4 }}>
          <div style={{ fontSize: 7.5, letterSpacing: ".18em", color: "var(--txt3)", marginBottom: 6 }}>EDGE TYPES</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 8.5, color: "var(--txt2)" }}>
            <span><span style={{ color: "var(--cyan)" }}>━</span> associated</span>
            <span><span style={{ color: "var(--crimson)" }}>━▸</span> subtext opposition</span>
            <span><span style={{ color: "var(--amber)" }}>━▸</span> sets up</span>
            <span><span style={{ color: "var(--green)" }}>┅▸</span> pays off · inferred</span>
            <span><span style={{ color: "#ff7ac6" }}>┄</span> thematic echo</span>
          </div>
        </div>
        <div style={{ position: "absolute", right: 14, bottom: 12, display: "flex", alignItems: "center", gap: 7, background: "var(--tint)", border: "1px solid rgba(98,217,154,.25)", padding: "6px 10px", zIndex: 4, fontSize: 8, letterSpacing: ".12em", color: "var(--green)" }}>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--green)", boxShadow: "0 0 6px var(--green)" }} />DETERMINISTIC · TRACEABLE · NODE SIZE = PRESENCE
        </div>
      </div>
    </PanelShell>
  );
}
