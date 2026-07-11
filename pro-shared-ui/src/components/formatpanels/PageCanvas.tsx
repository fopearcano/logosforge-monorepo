import type { CSSProperties, ReactNode } from "react";
import { PanelShell, type PanelProps } from "../shell/PanelShell";

const panelBox: CSSProperties = {
  position: "relative",
  width: "100%",
  height: "100%",
  background: "linear-gradient(180deg,var(--panel2),var(--base))",
  border: "1px solid var(--gn-line)",
  boxShadow: "0 16px 60px rgba(0,0,0,.6)",
  overflow: "hidden",
  display: "flex",
};

const ACCENT = { ["--accent"]: "#ff7ac6", ["--gn"]: "#ff7ac6", ["--gn-line"]: "rgba(255,122,198,.3)" } as CSSProperties;

/** A small placeholder panel cell in the page mock (P2 / P3 / P4 reveal). */
function PanelCell({ label, labelColor, border, background }: { label: ReactNode; labelColor: string; border: string; background: string }) {
  return (
    <div style={{ flex: 1, border, background, position: "relative", display: "grid", placeItems: "center" }}>
      <div style={{ position: "absolute", top: 4, left: 5, fontSize: 7, color: labelColor }}>{label}</div>
      <div style={{ fontSize: 7, color: "var(--txt3)" }}>▦</div>
    </div>
  );
}

/** Section heading label above an inspector box. */
function FieldLabel({ children, mb = 4 }: { children: ReactNode; mb?: number }) {
  return <div style={{ fontSize: 7.5, letterSpacing: ".16em", color: "var(--txt3)", marginBottom: mb }}>{children}</div>;
}

export function PageCanvas(props: PanelProps) {
  return (
    <PanelShell {...props} style={ACCENT}>
      <div data-screen-label="GN Page Canvas" style={panelBox}>
        {/* pink corner bracket + dot */}
        <div style={{ position: "absolute", top: -1, left: -1, width: 14, height: 14, borderTop: "1px solid var(--gn)", borderLeft: "1px solid var(--gn)", zIndex: 3 }} />
        <div style={{ position: "absolute", top: 3, left: 3, width: 5, height: 5, background: "var(--gn)", zIndex: 3 }} />

        {/* page preview */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", borderRight: "1px solid var(--line2)", minWidth: 0 }}>
          <div style={{ height: 40, flex: "none", display: "flex", alignItems: "center", gap: 11, padding: "0 16px", borderBottom: "1px solid var(--gn-line)" }}>
            <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".1em", color: "var(--strong)" }}>PAGE CANVAS</span>
            <span style={{ fontSize: 9, color: "var(--gn)" }}>PAGE 4 / 32</span>
            <div style={{ flex: 1 }} />
            <span style={{ fontSize: 8, color: "var(--txt3)" }}>◂ ▸ · density: medium</span>
          </div>
          <div style={{ flex: 1, display: "grid", placeItems: "center", padding: 18 }}>
            <div style={{ width: 280, height: "100%", background: "var(--panel2)", border: "1px solid var(--gn-line)", padding: 9, display: "flex", flexDirection: "column", gap: 8, boxShadow: "0 0 24px rgba(255,122,198,.1)" }}>
              {/* splash panel */}
              <div style={{ flex: 2, border: "1px solid var(--gn)", background: "rgba(255,122,198,.05)", position: "relative", display: "grid", placeItems: "center" }}>
                <div style={{ position: "absolute", top: 5, left: 6, fontSize: 7, color: "var(--gn)" }}>P1 · SPLASH · wide</div>
                <div style={{ fontSize: 8, color: "var(--txt3)", textAlign: "center", lineHeight: 1.4 }}>▦<br />dead planet<br />fills the glass</div>
                <div style={{ position: "absolute", bottom: 5, left: 6, right: 6, fontSize: 7, color: "var(--txt2)", background: "rgba(0,0,0,.5)", padding: "2px 4px" }}>CAP: Nine years of silence.</div>
              </div>
              {/* row of 2 */}
              <div style={{ flex: 1, display: "flex", gap: 8 }}>
                <PanelCell label="P2" labelColor="var(--txt3)" border="1px solid var(--line2)" background="var(--tint2)" />
                <PanelCell label="P3 ◉" labelColor="var(--gn)" border="1px solid var(--gn)" background="rgba(255,122,198,.05)" />
              </div>
              {/* reveal panel */}
              <PanelCell label="P4 · ⟳ page-turn reveal" labelColor="var(--amber)" border="1px solid var(--line2)" background="var(--tint2)" />
            </div>
          </div>
        </div>

        {/* panel inspector */}
        <div style={{ width: 380, flex: "none", background: "var(--panel2)", display: "flex", flexDirection: "column", overflowY: "auto" }}>
          <div style={{ height: 40, flex: "none", display: "flex", alignItems: "center", gap: 8, padding: "0 14px", borderBottom: "1px solid var(--line2)" }}>
            <span style={{ fontSize: 9, letterSpacing: ".16em", color: "var(--gn)" }}>PANEL 3 INSPECTOR</span>
            <span style={{ marginLeft: "auto", fontSize: 8, color: "var(--txt3)" }}>shot: CU · cam: low</span>
          </div>
          <div style={{ padding: "13px 14px" }}>
            <FieldLabel>VISUAL</FieldLabel>
            <div style={{ fontSize: 10, color: "var(--txt2)", lineHeight: 1.4, border: "1px solid var(--line2)", padding: "7px 9px", marginBottom: 9 }}>Vesper's reflection in the dark glass — only her eyes lit.</div>
            <FieldLabel>DIALOGUE</FieldLabel>
            <div style={{ fontSize: 10, color: "var(--txt)", border: "1px solid var(--line2)", padding: "7px 9px", marginBottom: 9 }}><span style={{ color: "var(--cyan)" }}>VESPER:</span> He's counting heartbeats.</div>
            <div style={{ display: "flex", gap: 9, marginBottom: 11 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 7.5, color: "var(--txt3)", marginBottom: 3 }}>SFX</div>
                <div style={{ fontSize: 9, color: "var(--txt2)", border: "1px solid var(--line2)", padding: "5px 8px" }}>hmmmm</div>
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 7.5, color: "var(--txt3)", marginBottom: 3 }}>TRANSITION</div>
                <div style={{ fontSize: 9, color: "var(--txt2)", border: "1px solid var(--line2)", padding: "5px 8px" }}>cut</div>
              </div>
            </div>
            <div style={{ border: "1px solid var(--gn-line)", background: "rgba(255,122,198,.04)", padding: "10px 11px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 7 }}>
                <span style={{ fontSize: 8, letterSpacing: ".14em", color: "var(--gn)" }}>AI IMAGE-PROMPT EXPORT</span>
                <span style={{ marginLeft: "auto", fontSize: 7, color: "var(--amber)" }}>ComfyUI unavailable</span>
              </div>
              <div style={{ fontSize: 8.5, color: "var(--txt2)", lineHeight: 1.5, marginBottom: 7 }}>+ positive: CU reflection, single key light, cold palette, graphic-novel ink…<br />+ from PSYKE visual memory: VESPER silhouette, cool color-identity</div>
              <span style={{ fontSize: 8, color: "var(--gn)", border: "1px solid var(--gn-line)", padding: "4px 9px" }}>COPY PROMPT PACKAGE</span>
            </div>
          </div>
        </div>
      </div>
    </PanelShell>
  );
}
