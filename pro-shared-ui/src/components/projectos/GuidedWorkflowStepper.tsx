import type { CSSProperties, ReactNode } from "react";
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

function Dot({ kind }: { kind: "done" | "creative-done" | "current" | "todo" }) {
  if (kind === "done") return <span style={{ position: "relative", zIndex: 1, width: 20, height: 20, flex: "none", borderRadius: "50%", background: "var(--green)", display: "grid", placeItems: "center", color: "#04060a", fontSize: 10 }}>✓</span>;
  if (kind === "creative-done") return <span style={{ position: "relative", zIndex: 1, width: 20, height: 20, flex: "none", borderRadius: "50%", border: "1px solid var(--green)", background: "#0a0d12", display: "grid", placeItems: "center", color: "var(--green)", fontSize: 9 }}>✎</span>;
  if (kind === "current") return <span style={{ position: "relative", zIndex: 1, width: 20, height: 20, flex: "none", borderRadius: "50%", background: "var(--accent)", display: "grid", placeItems: "center", color: "#04060a", fontSize: 9, boxShadow: "0 0 12px var(--accent)" }}>✎</span>;
  return <span style={{ position: "relative", zIndex: 1, width: 20, height: 20, flex: "none", borderRadius: "50%", border: "1px solid var(--txt3)", background: "#0a0d12", display: "grid", placeItems: "center", color: "var(--txt3)", fontSize: 9 }}>○</span>;
}

function Step({ kind, title, tag, tagColor, dim = false, children }: { kind: "done" | "creative-done" | "current" | "todo"; title: string; tag?: string; tagColor?: string; dim?: boolean; children?: ReactNode }) {
  return (
    <div style={{ display: "flex", gap: 13, alignItems: "flex-start", marginBottom: 16, opacity: dim ? 0.5 : undefined }}>
      <Dot kind={kind} />
      {children ?? (
        <div>
          <div style={{ fontSize: 11, color: "var(--txt2)" }}>{title}</div>
          <div style={{ fontSize: 8, color: tagColor, letterSpacing: ".1em" }}>{tag}</div>
        </div>
      )}
    </div>
  );
}

const tmpl = (t: string) => <div style={{ fontSize: 9, color: "var(--txt2)", padding: "5px 8px", border: "1px solid var(--line2)" }}>{t}</div>;
const logRow = (time: string, color: string, text: string) => (
  <div style={{ display: "flex", gap: 8 }}><span style={{ color: "var(--txt3)" }}>{time}</span><span style={{ color }}>●</span>{text}</div>
);

export function GuidedWorkflowStepper(props: PanelProps) {
  return (
    <PanelShell {...props}>
      <div data-screen-label="Guided Workflow Stepper" style={panelBox}>
        <Corners />
        {/* runs + gallery */}
        <div style={{ width: 260, flex: "none", borderRight: "1px solid var(--line)", background: "#06080c", display: "flex", flexDirection: "column" }}>
          <div style={{ height: 38, display: "flex", alignItems: "center", padding: "0 13px", borderBottom: "1px solid var(--line2)", fontSize: 8.5, letterSpacing: ".18em", color: "var(--txt3)" }}>ACTIVE RUNS</div>
          <div style={{ padding: 10, display: "flex", flexDirection: "column", gap: 7 }}>
            <div style={{ border: "1px solid var(--line-cy)", background: "rgba(76,194,255,.07)", padding: "9px 10px" }}>
              <div style={{ fontSize: 10, color: "#fff", marginBottom: 5 }}>Rewrite Pass</div>
              <div style={{ height: 4, background: "rgba(255,255,255,.06)" }}><div style={{ width: "44%", height: "100%", background: "var(--accent)" }} /></div>
              <div style={{ fontSize: 7.5, color: "var(--txt3)", marginTop: 4 }}>4/9 · active</div>
            </div>
            <div style={{ border: "1px solid var(--line2)", background: "rgba(11,14,21,.4)", padding: "9px 10px" }}>
              <div style={{ fontSize: 10, color: "var(--txt2)", marginBottom: 5 }}>Export Readiness</div>
              <div style={{ height: 4, background: "rgba(255,255,255,.06)" }}><div style={{ width: "70%", height: "100%", background: "var(--txt3)" }} /></div>
              <div style={{ fontSize: 7.5, color: "var(--txt3)", marginTop: 4 }}>7/10 · paused</div>
            </div>
          </div>
          <div style={{ padding: "6px 13px", fontSize: 8.5, letterSpacing: ".18em", color: "var(--txt3)", borderTop: "1px solid var(--line2)" }}>TEMPLATES · 11</div>
          <div style={{ flex: 1, overflowY: "auto", padding: "6px 10px", display: "flex", flexDirection: "column", gap: 4 }}>
            {tmpl("A · Project Setup")}{tmpl("C · Classical Outline")}{tmpl("H · Decision Radar Fix")}{tmpl("J · Continuity Review")}
          </div>
          <div style={{ borderTop: "1px solid var(--line-cy)", background: "rgba(76,194,255,.05)", padding: "9px 11px" }}>
            <div style={{ fontSize: 7.5, letterSpacing: ".14em", color: "var(--cyan)", marginBottom: 4 }}>RECOMMENDED NEXT</div>
            <div style={{ fontSize: 9, color: "var(--txt)" }}>H · Decision Radar Fix → resolve blocking</div>
          </div>
        </div>
        {/* stepper */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
          <div style={{ height: 42, flex: "none", display: "flex", alignItems: "center", gap: 11, padding: "0 16px", borderBottom: "1px solid var(--line)" }}>
            <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".1em", color: "#fff" }}>REWRITE PASS</span>
            <span style={{ fontSize: 8, color: "var(--txt3)" }}>mode-aware · resumable</span>
            <div style={{ flex: 1 }} /><span style={{ fontSize: 8.5, color: "var(--txt2)" }}>⏸ PAUSE</span><span style={{ fontSize: 8.5, color: "var(--txt3)" }}>CANCEL</span>
          </div>
          <div style={{ flex: 1, overflowY: "auto", padding: "15px 18px", position: "relative" }}>
            <div style={{ position: "absolute", left: 32, top: 24, bottom: 80, width: 1, background: "var(--line2)" }} />
            <Step kind="done" title="Capture a STAGE checkpoint" tag="CHECK · auto-ticked" tagColor="var(--green)" />
            <Step kind="done" title="Run Decision Radar" tag="CHECK · auto-ticked" tagColor="var(--green)" />
            <Step kind="creative-done" title="Address blocking issue" tag="CREATIVE · done by you" tagColor="var(--txt3)" />
            <Step kind="current" title="">
              <div style={{ flex: 1, border: "1px solid var(--line-cy)", background: "rgba(76,194,255,.06)", padding: "10px 12px" }}>
                <div style={{ fontSize: 11.5, color: "#fff", marginBottom: 4 }}>Tighten Act II middle (SC.13–15)</div>
                <div style={{ fontSize: 8, color: "var(--accent)", letterSpacing: ".1em", marginBottom: 8 }}>CREATIVE · CURRENT STEP</div>
                <div style={{ display: "flex", gap: 7 }}>
                  <span style={{ fontSize: 8, color: "var(--cyan)", border: "1px solid var(--line-cy)", padding: "3px 9px" }}>GO TO MANUSCRIPT ▸</span>
                  <span style={{ fontSize: 8, color: "#04060a", background: "var(--accent)", padding: "3px 9px", fontWeight: 600 }}>RUN LOGOS: TIGHTEN</span>
                </div>
              </div>
            </Step>
            <Step kind="todo" title="Verify continuity" tag="CHECK · auto-verifies" tagColor="var(--txt3)" dim />
            <div style={{ display: "flex", gap: 13, alignItems: "flex-start", opacity: 0.5 }}>
              <Dot kind="todo" /><div><div style={{ fontSize: 11, color: "var(--txt2)" }}>Apply via Controlled Apply</div><div style={{ fontSize: 8, color: "var(--txt3)", letterSpacing: ".1em" }}>MANUAL · acknowledge</div></div>
            </div>
          </div>
          {/* quest log */}
          <div style={{ flex: "none", height: 96, borderTop: "1px solid var(--line)", padding: "9px 16px", background: "#06080c", overflowY: "auto" }}>
            <div style={{ fontSize: 7.5, letterSpacing: ".18em", color: "var(--txt3)", marginBottom: 7 }}>EVENT TIMELINE · quest log</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 8.5, color: "var(--txt2)" }}>
              {logRow("09:14", "var(--green)", "started · Rewrite Pass")}
              {logRow("09:15", "var(--green)", "step_completed · checkpoint")}
              {logRow("09:21", "var(--cyan)", "step_auto_completed · radar")}
            </div>
          </div>
        </div>
      </div>
    </PanelShell>
  );
}
