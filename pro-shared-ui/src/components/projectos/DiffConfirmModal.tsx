import type { CSSProperties, ReactNode } from "react";
import { PanelShell, type PanelProps } from "../shell/PanelShell";

const panelBox: CSSProperties = {
  position: "relative",
  width: "100%",
  height: "100%",
  background: "rgba(3,4,7,.96)",
  border: "1px solid var(--line)",
  boxShadow: "0 16px 60px rgba(0,0,0,.6)",
  overflow: "hidden",
};

const ctx = (t: string, mt = 0, mb = 0) => <div style={{ color: "var(--txt2)", opacity: 0.7, margin: `${mt}px 0 ${mb}px` }}>{t}</div>;
const cue = (t: string, mt: number) => <div style={{ textAlign: "center", color: "var(--txt2)", fontWeight: 700, marginTop: mt }}>{t}</div>;
const del = (t: string) => <div style={{ background: "rgba(255,82,96,.1)", borderLeft: "2px solid var(--blocking)", padding: "2px 8px", margin: "3px 0", color: "var(--txt2)" }}><span style={{ color: "var(--blocking)" }}>−</span> <span style={{ textDecoration: "line-through", textDecorationColor: "rgba(255,82,96,.5)" }}>{t}</span></div>;
const add = (t: ReactNode) => <div style={{ background: "rgba(98,217,154,.1)", borderLeft: "2px solid var(--green)", padding: "2px 8px", margin: "3px 0", color: "#eef1f6" }}><span style={{ color: "var(--green)" }}>+</span> {t}</div>;
const impactLabel = (t: string) => <div style={{ fontSize: 8, letterSpacing: ".16em", color: "var(--txt3)", marginBottom: 7 }}>{t}</div>;

export function DiffConfirmModal(props: PanelProps) {
  return (
    <PanelShell {...props}>
      <div data-screen-label="Diff Impact Confirm Modal" style={panelBox}>
        {/* faint underlying UI + dim */}
        <div style={{ position: "absolute", inset: 0, backgroundImage: "radial-gradient(circle,rgba(128,140,158,.05) 1px,transparent 1.4px)", backgroundSize: "30px 30px", opacity: 0.5 }} />
        <div style={{ position: "absolute", inset: 0, background: "rgba(2,3,6,.55)" }} />

        {/* MODAL DIALOG */}
        <div style={{ position: "absolute", top: 55, left: 70, right: 70, bottom: 55, background: "linear-gradient(180deg,#0b0e15,#070a0f)", border: "1px solid var(--crimson)", boxShadow: "0 30px 90px rgba(0,0,0,.8),0 0 0 1px rgba(232,68,58,.1)", display: "flex", flexDirection: "column" }}>
          <div style={{ position: "absolute", top: -1, left: -1, width: 15, height: 15, borderTop: "1px solid var(--crimson)", borderLeft: "1px solid var(--crimson)" }} />
          <div style={{ position: "absolute", top: 4, left: 4, width: 5, height: 5, background: "var(--crimson)", boxShadow: "0 0 6px var(--crimson)" }} />
          <div style={{ position: "absolute", bottom: -1, right: -1, width: 15, height: 15, borderBottom: "1px solid var(--crimson)", borderRight: "1px solid var(--crimson)" }} />

          {/* header */}
          <div style={{ flex: "none", padding: "13px 18px", borderBottom: "1px solid var(--line)", display: "flex", alignItems: "center", gap: 13 }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 16, letterSpacing: ".08em", color: "#fff" }}>CONTROLLED APPLY</span>
                <span style={{ fontSize: 9, color: "var(--cyan)", border: "1px solid var(--line-cy)", padding: "2px 8px", letterSpacing: ".1em" }}>REWRITE · SC.12</span>
              </div>
              <div style={{ fontSize: 8.5, color: "var(--txt3)", letterSpacing: ".16em", marginTop: 4 }}>PREVIEW → DIFF → IMPACT → CONFIRM · the single mutation gate</div>
            </div>
            <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8, fontSize: 8.5, color: "var(--green)", border: "1px solid rgba(98,217,154,.35)", padding: "4px 10px", letterSpacing: ".08em" }}><span style={{ width: 7, height: 7, background: "var(--green)", transform: "rotate(45deg)" }} />STAGE CHECKPOINT CREATED</div>
            <span style={{ fontSize: 13, color: "var(--txt3)" }}>✕</span>
          </div>

          {/* body */}
          <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
            {/* DIFF */}
            <div style={{ width: "60%", flex: "none", borderRight: "1px solid var(--line)", display: "flex", flexDirection: "column" }}>
              <div style={{ flex: "none", height: 32, display: "flex", alignItems: "center", gap: 11, padding: "0 15px", borderBottom: "1px solid var(--line2)" }}>
                <span style={{ fontSize: 9, letterSpacing: ".16em", color: "var(--txt2)" }}>DIFF · ORIGINAL → PROPOSED</span>
                <div style={{ flex: 1 }} />
                <span style={{ fontSize: 8, color: "var(--txt3)" }}>INLINE</span><span style={{ fontSize: 8, color: "var(--accent)", border: "1px solid var(--line-cy)", padding: "1px 6px" }}>SIDE-BY-SIDE</span>
                <span style={{ fontSize: 8, color: "var(--green)" }}>+12</span><span style={{ fontSize: 8, color: "var(--blocking)" }}>−7</span>
              </div>
              <div style={{ flex: 1, overflowY: "auto", padding: "14px 16px", fontFamily: "'Courier Prime'", fontSize: 13, lineHeight: 1.7 }}>
                <div style={{ color: "var(--txt3)" }}>12  INT. HELIOS-9 — OBSERVATION RING — NIGHT</div>
                {ctx("The corridor breathes. Marlow floats at the viewport.", 8, 8)}
                {cue("VESPER", 10)}
                {del("Neither should you. The Warden is counting heartbeats tonight.")}
                {add("Neither should you. He's counting heartbeats tonight.")}
                {add(<span style={{ background: "rgba(98,217,154,.18)" }}>Yours are loud.</span>)}
                {ctx("She lets the hatch seal. The static between them is old.", 10, 10)}
                {cue("MARLOW", 8)}
                {add("(quietly) Don't say his name.")}
                {ctx("SMASH CUT TO:", 10)}
              </div>
            </div>

            {/* CHANGE IMPACT MAP */}
            <div style={{ flex: 1, display: "flex", flexDirection: "column", background: "#06080c" }}>
              <div style={{ flex: "none", height: 32, display: "flex", alignItems: "center", padding: "0 15px", borderBottom: "1px solid var(--line2)" }}><span style={{ fontSize: 9, letterSpacing: ".16em", color: "var(--amber)" }}>CHANGE IMPACT MAP</span></div>
              <div style={{ flex: 1, overflowY: "auto", padding: "14px 15px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 7 }}><span style={{ fontSize: 8, letterSpacing: ".16em", color: "var(--txt3)" }}>IMPACT LEVEL</span><span style={{ marginLeft: "auto", fontSize: 8, color: "var(--txt3)" }}>conf <span style={{ color: "var(--green)" }}>HIGH</span></span></div>
                <div style={{ display: "flex", gap: 3, marginBottom: 5 }}>
                  <div style={{ flex: 1, height: 8, background: "var(--green)", opacity: 0.4 }} /><div style={{ flex: 1, height: 8, background: "var(--amber)", boxShadow: "0 0 8px var(--amber)" }} /><div style={{ flex: 1, height: 8, background: "rgba(255,255,255,.08)" }} /><div style={{ flex: 1, height: 8, background: "rgba(255,255,255,.08)" }} />
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 7, color: "var(--txt3)", marginBottom: 15, letterSpacing: ".06em" }}><span>LOW</span><span style={{ color: "var(--amber-b)" }}>● MEDIUM</span><span>HIGH</span><span>CRITICAL</span></div>

                {impactLabel("IMPACTED SCENES · 3")}
                <div style={{ display: "flex", flexDirection: "column", gap: 5, marginBottom: 14 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 9.5, color: "var(--txt)", borderLeft: "2px solid var(--cyan)", padding: "4px 9px", background: "rgba(11,14,21,.5)" }}><span style={{ color: "var(--cyan)" }}>SC.12</span><span style={{ color: "var(--txt3)", flex: 1 }}>direct edit</span></div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 9.5, color: "var(--txt2)", borderLeft: "2px solid var(--amber)", padding: "4px 9px", background: "rgba(11,14,21,.5)" }}><span style={{ color: "var(--amber)" }}>SC.21</span><span style={{ color: "var(--txt3)", flex: 1 }}>Warden reveal advanced</span></div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 9.5, color: "var(--txt2)", borderLeft: "2px solid var(--txt3)", padding: "4px 9px", background: "rgba(11,14,21,.5)" }}><span style={{ color: "var(--txt2)" }}>SC.14</span><span style={{ color: "var(--txt3)", flex: 1 }}>downstream · echo check</span></div>
                </div>

                {impactLabel("SETUP / PAYOFF")}
                <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 9, color: "var(--txt2)", marginBottom: 14 }}>
                  <div style={{ display: "flex", gap: 8 }}><span style={{ color: "var(--green)" }}>✓</span>“black box” setup — unaffected</div>
                  <div style={{ display: "flex", gap: 8 }}><span style={{ color: "var(--amber)" }}>△</span>Warden reveal — pulled earlier (track payoff)</div>
                </div>

                {impactLabel("PSYKE AFFECTED")}
                <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginBottom: 14 }}>
                  <span style={{ fontSize: 8, color: "var(--cyan)", border: "1px solid var(--line-cy)", padding: "2px 7px" }}>◆ VESPER +prog</span>
                  <span style={{ fontSize: 8, color: "var(--crimson)", border: "1px solid rgba(232,68,58,.3)", padding: "2px 7px" }}>◆ WARDEN revealed</span>
                </div>

                {impactLabel("CONTINUITY FINDINGS")}
                <div style={{ border: "1px solid rgba(255,180,84,.3)", background: "rgba(255,180,84,.05)", padding: "7px 9px", fontSize: 9, color: "var(--txt2)" }}><span style={{ color: "var(--warning)" }}>△ WARNING</span> · spatial — no travel cue before SC.14 <span style={{ color: "var(--txt3)" }}>· conf MED</span></div>
              </div>
            </div>
          </div>

          {/* footer */}
          <div style={{ flex: "none", borderTop: "1px solid var(--line)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 16, padding: "9px 18px", borderBottom: "1px solid var(--line2)", background: "rgba(6,8,12,.5)" }}>
              <span style={{ fontSize: 8, letterSpacing: ".16em", color: "var(--txt3)" }}>CONFLICTS</span>
              <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 9, color: "var(--txt2)" }}><span style={{ width: 8, height: 8, background: "var(--blocking)", display: "inline-grid", placeItems: "center", color: "#fff", fontSize: 6 }}>!</span>0 BLOCKING</span>
              <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 9, color: "var(--warning)" }}><span style={{ width: 7, height: 7, transform: "rotate(45deg)", background: "var(--warning)" }} />1 WARNING</span>
              <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 9, color: "var(--txt2)" }}>0 ERROR</span>
              <span style={{ fontSize: 8.5, color: "var(--txt3)", marginLeft: 6 }}>warnings allow apply · blocking would gate</span>
              <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6, fontSize: 8, color: "var(--green)" }}><span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--green)" }} />✓ logged to apply history</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 11, padding: "13px 18px" }}>
              <span style={{ fontSize: 8.5, color: "var(--txt3)", letterSpacing: ".04em" }}>↳ restore anytime from Stages · non-destructive</span>
              <div style={{ flex: 1 }} />
              <span style={{ fontSize: 10, letterSpacing: ".1em", color: "var(--txt2)", border: "1px solid var(--line2)", padding: "9px 18px" }}>CANCEL</span>
              <span style={{ fontSize: 10, letterSpacing: ".1em", color: "var(--amber)", border: "1px solid rgba(255,180,84,.35)", padding: "9px 18px", opacity: 0.5 }}>FORCE OVERRIDE</span>
              <span style={{ fontSize: 11, letterSpacing: ".1em", color: "#04060a", background: "var(--green)", padding: "10px 26px", fontWeight: 700, boxShadow: "0 0 18px rgba(98,217,154,.4)" }}>✓ APPLY (CONFIRMED)</span>
            </div>
          </div>
        </div>
      </div>
    </PanelShell>
  );
}
