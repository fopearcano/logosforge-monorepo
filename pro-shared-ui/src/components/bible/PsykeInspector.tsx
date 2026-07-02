import type { CSSProperties } from "react";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";

const panelBox: CSSProperties = {
  position: "relative",
  width: "100%",
  height: "100%",
  background: "linear-gradient(180deg,#080a0f,#05070b)",
  border: "1px solid var(--line)",
  boxShadow: "0 16px 60px rgba(0,0,0,.6)",
  overflow: "hidden",
  display: "flex",
};

interface Seg { left: string; width: string; bg: string; border: string }

function Lane({ name, nameColor, segs, right, rightColor }: { name: string; nameColor: string; segs: Seg[]; right: string; rightColor: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <span style={{ width: 68, flex: "none", fontSize: 9, color: nameColor, textAlign: "right" }}>{name}</span>
      <div style={{ flex: 1, height: 18, position: "relative", background: "rgba(255,255,255,.02)" }}>
        {segs.map((s, i) => (
          <div key={i} style={{ position: "absolute", left: s.left, width: s.width, top: 2, bottom: 2, background: s.bg, borderLeft: `2px solid ${s.border}` }} />
        ))}
      </div>
      <span style={{ width: 104, flex: "none", fontSize: 8, color: rightColor }}>{right}</span>
    </div>
  );
}

function Prog({ sc, scColor, text, textColor, dotColor, dotSize = 7, dotGlow = false, dim = false, last = false }: { sc: string; scColor: string; text: string; textColor: string; dotColor: string; dotSize?: number; dotGlow?: boolean; dim?: boolean; last?: boolean }) {
  return (
    <div style={{ position: "relative", padding: last ? 0 : "0 0 11px", opacity: dim ? 0.6 : undefined }}>
      <span style={{ position: "absolute", left: -14, top: 2, width: dotSize, height: dotSize, borderRadius: "50%", background: dotColor, boxShadow: dotGlow ? `0 0 ${dotSize}px ${dotColor}` : undefined }} />
      <div style={{ fontSize: 8, color: scColor }}>{sc}</div>
      <div style={{ fontSize: 10, color: textColor }}>{text}</div>
    </div>
  );
}

export function PsykeInspector(props: PanelProps) {
  return (
    <PanelShell {...props}>
      <div data-screen-label="Temporal Scrubber + Inspector" style={panelBox}>
        <div style={{ position: "absolute", top: -1, left: -1, width: 14, height: 14, borderTop: "1px solid var(--crimson)", borderLeft: "1px solid var(--crimson)", zIndex: 3 }} />
        <div style={{ position: "absolute", top: 3, left: 3, width: 5, height: 5, background: "var(--crimson)", zIndex: 3 }} />

        {/* temporal piano-roll */}
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", borderRight: "1px solid var(--line)" }}>
          <div style={{ height: 36, display: "flex", alignItems: "center", gap: 11, padding: "0 14px", borderBottom: "1px solid var(--line2)" }}>
            <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 12, letterSpacing: ".1em", color: "#fff" }}>STATE-AT-SCENE SCRUBBER</span>
            <span style={{ fontSize: 8, color: "var(--txt3)" }}>get_entry_state_at() · sort_order</span>
            <div style={{ flex: 1 }} />
            <span style={{ fontSize: 9, color: "var(--accent)" }}>▮ PLAYHEAD @ SC.12</span>
          </div>
          <div style={{ flex: 1, position: "relative", padding: "10px 16px 14px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 7, color: "var(--txt3)", letterSpacing: ".05em", borderBottom: "1px solid var(--line2)", paddingBottom: 4, marginBottom: 10, paddingLeft: 78 }}>
              <span>01</span><span>04</span><span>07</span><span>10</span><span style={{ color: "var(--accent)" }}>12</span><span>15</span><span>18</span><span>21</span><span>24</span>
            </div>
            <div style={{ position: "absolute", left: "calc(78px + 49%)", top: 34, bottom: 14, width: 1, background: "var(--accent)", boxShadow: "0 0 8px var(--accent)", zIndex: 4 }} />
            <div style={{ position: "absolute", left: "calc(78px + 49% - 5px)", top: 30, width: 11, height: 8, background: "var(--accent)", zIndex: 4, clipPath: "polygon(0 0,100% 0,50% 100%)" }} />
            <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
              <Lane name="◆ MARLOW" nameColor="var(--cyan)" right="→ guarded · grief" rightColor="var(--amber-b)" segs={[
                { left: "2%", width: "30%", bg: "rgba(76,194,255,.18)", border: "var(--cyan)" },
                { left: "33%", width: "28%", bg: "rgba(245,177,51,.16)", border: "var(--amber)" },
                { left: "62%", width: "36%", bg: "rgba(255,82,96,.16)", border: "var(--blocking)" },
              ]} />
              <Lane name="◆ VESPER" nameColor="var(--cyan)" right="→ confessing (partial)" rightColor="var(--amber-b)" segs={[
                { left: "8%", width: "40%", bg: "rgba(98,217,154,.16)", border: "var(--green)" },
                { left: "48%", width: "30%", bg: "rgba(245,177,51,.16)", border: "var(--amber)" },
                { left: "78%", width: "20%", bg: "rgba(255,82,96,.18)", border: "var(--blocking)" },
              ]} />
              <Lane name="◆ WARDEN" nameColor="var(--crimson)" right="→ counting · active" rightColor="var(--txt2)" segs={[
                { left: "25%", width: "35%", bg: "rgba(232,68,58,.12)", border: "var(--crimson)" },
                { left: "60%", width: "38%", bg: "rgba(232,68,58,.22)", border: "var(--crimson)" },
              ]} />
            </div>
            <div style={{ marginTop: 11, paddingLeft: 78, fontSize: 8, color: "var(--txt3)" }}>ACTIVE RELATED @ SC.12 · <span style={{ color: "var(--cyan)" }}>MARLOW ◉</span> · <span style={{ color: "var(--green)" }}>KESSLER BURN ◉</span> · <span style={{ color: "var(--txt3)" }}>THE WARDEN ○ (offscreen)</span></div>
          </div>
        </div>

        {/* docked inspector */}
        <div style={{ width: 440, flex: "none", display: "flex", flexDirection: "column", background: "#06080c" }}>
          <div style={{ height: 36, display: "flex", alignItems: "center", gap: 8, padding: "0 13px", borderBottom: "1px solid var(--line2)" }}>
            <span style={{ color: "var(--txt3)" }}>⠿</span><span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 12, letterSpacing: ".1em", color: "#fff" }}>INSPECTOR · VESPER</span>
            <div style={{ flex: 1 }} />
            <span style={{ fontSize: 8, color: "var(--accent)" }}>QUICK EDIT ✎</span>
          </div>
          <div style={{ flex: 1, overflowY: "auto", padding: "12px 13px" }}>
            <div style={{ fontSize: 7.5, letterSpacing: ".2em", color: "var(--txt3)", marginBottom: 8 }}>PROGRESSIONS · pinned to scenes</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 0, position: "relative", paddingLeft: 14 }}>
              <div style={{ position: "absolute", left: 3, top: 4, bottom: 4, width: 1, background: "var(--line2)" }} />
              <Prog sc="SC.02" scColor="var(--green)" text="Recognizes the looping voice." textColor="var(--txt)" dotColor="var(--green)" dotGlow />
              <Prog sc="SC.08" scColor="var(--amber)" text="Starts deflecting with logistics." textColor="var(--txt)" dotColor="var(--amber)" />
              <Prog sc="SC.12 · NOW" scColor="var(--accent)" text="Confesses, but only half of it." textColor="#fff" dotColor="var(--accent)" dotSize={8} dotGlow />
              <Prog sc="SC.21 · future" scColor="var(--blocking)" text="Goes silent. Pays off the motif." textColor="var(--txt2)" dotColor="var(--blocking)" dim last />
            </div>
            <div style={{ marginTop: 13, display: "flex", gap: 7 }}>
              <span style={{ fontSize: 8, color: "var(--accent)", border: "1px solid var(--line-cy)", padding: "4px 9px", letterSpacing: ".08em" }}>＋ PROGRESSION</span>
              <span style={{ fontSize: 8, color: "var(--txt2)", border: "1px solid var(--line2)", padding: "4px 9px", letterSpacing: ".08em" }}>＋ RELATION</span>
            </div>
          </div>
        </div>
      </div>
    </PanelShell>
  );
}
