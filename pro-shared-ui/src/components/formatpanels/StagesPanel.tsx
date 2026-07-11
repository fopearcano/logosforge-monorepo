import type { CSSProperties, ReactNode } from "react";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";

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

const ACCENT = { ["--accent"]: "#4cc2ff", ["--blue"]: "#5a78ff" } as CSSProperties;

/** An absolutely-positioned round commit-tick dot on the git-graph timeline. */
function CommitTick({ left, top, size, color, glow = false }: { left: number; top: number; size: number; color: string; glow?: boolean }) {
  return (
    <div
      style={{
        position: "absolute",
        left,
        top,
        width: size,
        height: size,
        borderRadius: "50%",
        background: color,
        border: "2px solid var(--base)",
        boxShadow: glow ? `0 0 ${size >= 16 ? 10 : 8}px ${color}` : undefined,
      }}
    />
  );
}

/** A REASON legend row: a colored dot + label. */
function ReasonRow({ color, children }: { color: string; children: ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <span style={{ width: 8, height: 8, borderRadius: "50%", background: color }} />
      {children}
    </div>
  );
}

export function StagesPanel(props: PanelProps) {
  return (
    <PanelShell {...props} style={ACCENT}>
      <div data-screen-label="Stages" style={panelBox}>
        <Corners />

        {/* header */}
        <div style={{ height: 40, flex: "none", display: "flex", alignItems: "center", gap: 11, padding: "0 16px", borderBottom: "1px solid var(--line)" }}>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".1em", color: "var(--strong)" }}>STAGES</span>
          <span style={{ fontSize: 9, color: "var(--txt2)" }}>⟲ next autosave 2:41</span>
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 8, color: "var(--amber)" }}>↳ restore → NEW PROJECT · non-destructive</span>
        </div>

        {/* git-graph timeline */}
        <div style={{ height: 150, flex: "none", position: "relative", borderBottom: "1px solid var(--line2)", padding: "0 20px" }}>
          <svg viewBox="0 0 1140 150" style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}>
            {/* canon line */}
            <line x1="40" y1="60" x2="1100" y2="60" stroke="#2a3340" strokeWidth="2" />
            {/* branch */}
            <path d="M620,60 C 680,60 700,110 760,110 L 1000,110" fill="none" stroke="#3a2a40" strokeWidth="2" />
            {/* merge-ish dashed return */}
            <path d="M1000,110 C 1050,110 1060,60 1090,60" fill="none" stroke="#2a3340" strokeWidth="1" strokeDasharray="3 4" />
          </svg>
          {/* commit ticks */}
          <CommitTick left={34} top={54} size={13} color="var(--txt3)" />
          <CommitTick left={150} top={54} size={13} color="var(--blue)" />
          <CommitTick left={290} top={52} size={16} color="var(--cyan)" glow />
          <CommitTick left={440} top={55} size={11} color="var(--txt3)" />
          <CommitTick left={570} top={54} size={13} color="var(--amber)" />
          <CommitTick left={740} top={104} size={13} color="var(--violet)" glow />
          <CommitTick left={880} top={105} size={11} color="var(--violet)" />
          {/* labels */}
          <div style={{ position: "absolute", left: 270, top: 18, fontSize: 8, color: "var(--cyan)", textAlign: "center" }}>
            manual<br /><span style={{ color: "var(--txt3)" }}>“Act II locked”</span>
          </div>
          <div style={{ position: "absolute", left: 548, top: 18, fontSize: 8, color: "var(--amber)", textAlign: "center" }}>
            pre-restore<br /><span style={{ color: "var(--txt3)" }}>safety</span>
          </div>
          <div style={{ position: "absolute", left: 710, top: 124, fontSize: 8, color: "var(--violet)" }}>branch · Quantum collapse</div>
          <div style={{ position: "absolute", left: 34, top: 80, fontSize: 7, color: "var(--txt3)" }}>CANON</div>
        </div>

        {/* legend + selected diff */}
        <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
          {/* LEFT 300px legend */}
          <div style={{ width: 300, flex: "none", borderRight: "1px solid var(--line2)", padding: "12px 14px", overflowY: "auto" }}>
            <div style={{ fontSize: 7.5, letterSpacing: ".18em", color: "var(--txt3)", marginBottom: 8 }}>REASON</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 5, fontSize: 9, color: "var(--txt2)", marginBottom: 13 }}>
              <ReasonRow color="var(--txt3)">autosave</ReasonRow>
              <ReasonRow color="var(--blue)">periodic (5 min)</ReasonRow>
              <ReasonRow color="var(--cyan)">manual · labeled</ReasonRow>
              <ReasonRow color="var(--amber)">pre-restore safety</ReasonRow>
              <ReasonRow color="var(--violet)">branch</ReasonRow>
            </div>
            <div style={{ fontSize: 7.5, letterSpacing: ".18em", color: "var(--txt3)", marginBottom: 8 }}>APPLY HISTORY</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 8.5, color: "var(--txt2)" }}>
              <div>09:21 · rewrite SC.12 <span style={{ color: "var(--green)" }}>applied</span></div>
              <div>09:05 · outline gen <span style={{ color: "var(--green)" }}>applied</span></div>
              <div>08:47 · collapse B1 <span style={{ color: "var(--green)" }}>applied</span></div>
            </div>
          </div>

          {/* RIGHT selected-version diff */}
          <div style={{ flex: 1, padding: "12px 14px", overflowY: "auto" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 9 }}>
              <span style={{ fontSize: 8, letterSpacing: ".16em", color: "var(--cyan)" }}>SELECTED · “Act II locked” → vs current</span>
              <span style={{ fontSize: 7.5, color: "var(--txt3)" }}>142 KB · 09:14</span>
            </div>
            <div style={{ fontFamily: "'Courier Prime'", fontSize: 11, lineHeight: 1.6, marginBottom: 12 }}>
              <div style={{ background: "rgba(255,82,96,.1)", borderLeft: "2px solid var(--blocking,#ff5260)", padding: "1px 8px", color: "var(--txt3)" }}>− 6 scenes in Act II</div>
              <div style={{ background: "rgba(98,217,154,.1)", borderLeft: "2px solid var(--green)", padding: "1px 8px", color: "var(--txt)" }}>+ 8 scenes · +2,140 words</div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <span style={{ fontSize: 9, color: "var(--on-accent)", background: "var(--accent)", padding: "6px 13px", fontWeight: 600, letterSpacing: ".06em" }}>RESTORE → NEW PROJECT</span>
              <span style={{ fontSize: 9, color: "var(--txt2)", border: "1px solid var(--line2)", padding: "6px 13px" }}>DIFF</span>
              <span style={{ fontSize: 9, color: "var(--txt3)", border: "1px solid var(--line2)", padding: "6px 13px" }}>DELETE</span>
            </div>
            <div style={{ fontSize: 7.5, color: "var(--txt3)", marginTop: 8 }}>↳ a safety snapshot is taken first · the original is never overwritten</div>
          </div>
        </div>
      </div>
    </PanelShell>
  );
}
