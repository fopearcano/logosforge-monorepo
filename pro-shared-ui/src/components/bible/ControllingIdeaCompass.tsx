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
  flexDirection: "column",
};

const seg = (flex: number, bg: string, op = 0.7) => <div style={{ flex, background: bg, opacity: op }} />;

function Coverage({ value, color, label }: { value: string; color: string; label: string }) {
  return (
    <div style={{ border: "1px solid var(--line2)", padding: 10, textAlign: "center" }}>
      <div style={{ fontFamily: "'Chakra Petch'", fontSize: 22, color }}>{value}</div>
      <div style={{ fontSize: 7.5, letterSpacing: ".1em", color: "var(--txt3)" }}>{label}</div>
    </div>
  );
}

export function ControllingIdeaCompass(props: PanelProps) {
  return (
    <PanelShell {...props}>
      <div data-screen-label="Controlling-Idea Compass" style={panelBox}>
        <Corners />
        <div style={{ height: 38, flex: "none", display: "flex", alignItems: "center", gap: 9, padding: "0 14px", borderBottom: "1px solid var(--line)" }}>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".1em", color: "#fff" }}>CONTROLLING IDEA</span>
          <span style={{ fontSize: 8, color: "var(--violet)", border: "1px solid rgba(176,124,255,.3)", padding: "2px 6px" }}>/idea</span>
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 8, color: "var(--txt3)" }}>→ theme entry auto-linked</span>
        </div>
        <div style={{ flex: 1, overflowY: "auto", padding: 16 }}>
          <div style={{ display: "flex", gap: 16, alignItems: "center", marginBottom: 18 }}>
            {/* charge compass */}
            <div style={{ flex: "none", position: "relative", width: 120, height: 120 }}>
              <div style={{ position: "absolute", inset: 0, borderRadius: "50%", background: "conic-gradient(var(--green) 0 33%,var(--amber) 33% 66%,var(--blocking) 66% 100%)", opacity: 0.25 }} />
              <div style={{ position: "absolute", inset: 9, borderRadius: "50%", background: "#070a0f", border: "1px solid var(--line2)" }} />
              <div style={{ position: "absolute", left: "50%", top: "50%", width: 2, height: 44, background: "var(--green)", transformOrigin: "bottom center", transform: "translate(-50%,-100%) rotate(-52deg)", boxShadow: "0 0 8px var(--green)" }} />
              <div style={{ position: "absolute", left: "50%", top: "50%", width: 8, height: 8, borderRadius: "50%", background: "var(--green)", transform: "translate(-50%,-50%)", boxShadow: "0 0 8px var(--green)" }} />
              <div style={{ position: "absolute", left: 0, right: 0, bottom: 8, textAlign: "center", fontSize: 8, letterSpacing: ".16em", color: "var(--green)" }}>POSITIVE</div>
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 8, letterSpacing: ".2em", color: "var(--txt3)", marginBottom: 6 }}>VALUE + CAUSE</div>
              <div style={{ fontFamily: "'Chakra Petch'", fontSize: 16, lineHeight: 1.35, color: "#fff" }}><span style={{ color: "var(--green)" }}>JUSTICE</span> prevails <span style={{ color: "var(--txt2)" }}>when</span> the powerless break their silence.</div>
              <div style={{ marginTop: 10, fontSize: 8, letterSpacing: ".2em", color: "var(--txt3)", marginBottom: 4 }}>COUNTER-IDEA</div>
              <div style={{ fontFamily: "'Chakra Petch'", fontSize: 13, lineHeight: 1.35, color: "var(--txt2)" }}><span style={{ color: "var(--blocking)" }}>TYRANNY</span> wins when fear is rewarded.</div>
            </div>
          </div>
          {/* alignment ribbon */}
          <div style={{ fontSize: 8, letterSpacing: ".2em", color: "var(--txt3)", marginBottom: 7 }}>SCENE ALIGNMENT · 24 scenes</div>
          <div style={{ display: "flex", gap: 2, height: 22, marginBottom: 8 }}>
            {seg(2, "var(--green)")}{seg(1, "var(--amber)")}{seg(3, "var(--green)")}{seg(1, "var(--blocking)")}{seg(2, "var(--amber)")}{seg(1, "var(--violet)")}{seg(2, "var(--green)")}{seg(1, "rgba(255,255,255,.08)", 1)}{seg(1, "var(--violet)")}
          </div>
          <div style={{ display: "flex", gap: 13, fontSize: 8, color: "var(--txt3)", marginBottom: 18 }}>
            <span><span style={{ color: "var(--green)" }}>■</span> supports</span><span><span style={{ color: "var(--blocking)" }}>■</span> opposes</span><span><span style={{ color: "var(--amber)" }}>■</span> tests</span><span><span style={{ color: "var(--violet)" }}>■</span> transforms</span>
          </div>
          {/* coverage HUD */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 9 }}>
            <Coverage value="18" color="var(--green)" label="/24 ENGAGE" />
            <Coverage value="3" color="var(--blocking)" label="OPPOSE" />
            <Coverage value="2" color="var(--violet)" label="TRANSFORM" />
          </div>
        </div>
      </div>
    </PanelShell>
  );
}
