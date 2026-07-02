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

function InboxCard({ kind, kindColor, title, ignore = false }: { kind: string; kindColor: string; title: string; ignore?: boolean }) {
  return (
    <div style={{ border: "1px solid var(--line2)", borderLeft: `2px solid ${kindColor}`, background: "rgba(11,14,21,.4)", padding: "8px 10px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 4 }}>
        <span style={{ fontSize: 7.5, letterSpacing: ".12em", color: kindColor }}>{kind}</span>
        <span style={{ fontSize: 10, color: "#fff", flex: 1 }}>{title}</span>
      </div>
      <div style={{ display: "flex", gap: 6 }}>
        <span style={{ fontSize: 8, color: "#04060a", background: kindColor, padding: "3px 9px", fontWeight: 600 }}>ACCEPT</span>
        <span style={{ fontSize: 8, color: "var(--txt2)", border: "1px solid var(--line2)", padding: "3px 9px" }}>DISMISS</span>
        {ignore && <span style={{ marginLeft: "auto", fontSize: 7.5, color: "var(--txt3)", alignSelf: "center" }}>+ ignore-list</span>}
      </div>
    </div>
  );
}

export function PsykeConsoleInbox(props: PanelProps) {
  return (
    <PanelShell {...props}>
      <div data-screen-label="PSYKE Console + Auto-Link Inbox" style={panelBox}>
        <Corners />
        {/* console (open) */}
        <div style={{ padding: 13, borderBottom: "1px solid var(--line)" }}>
          <div style={{ fontSize: 8, letterSpacing: ".2em", color: "var(--txt3)", marginBottom: 9 }}>PSYKE CONSOLE · OPEN</div>
          <div style={{ border: "1px solid var(--line-cy)", background: "#0a0d14", boxShadow: "0 0 22px rgba(76,194,255,.12)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 9, padding: "10px 12px", borderBottom: "1px solid var(--line2)" }}>
              <span style={{ fontFamily: "'Chakra Petch'", color: "var(--accent)", fontSize: 13 }}>ψ</span>
              <span style={{ fontSize: 12, color: "#fff" }}>make vesper colder<span style={{ display: "inline-block", width: 2, height: 14, background: "var(--accent)", verticalAlign: -2, marginLeft: 1, animation: "lf-blink 1.1s step-end infinite" }} /></span>
              <span style={{ marginLeft: "auto", fontSize: 7.5, color: "var(--txt3)" }}>ENTITY · VESPER › action</span>
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 9, padding: "8px 12px", background: "rgba(76,194,255,.08)", borderLeft: "2px solid var(--accent)" }}>
                <span style={{ color: "var(--amber)" }}>⚡</span><span style={{ fontSize: 11, color: "#fff", flex: 1 }}>Rewrite — colder register</span>
                <span style={{ fontSize: 7.5, color: "var(--txt3)" }}>intent · conf <span style={{ color: "var(--green)" }}>0.82</span></span><span style={{ fontSize: 8, color: "var(--accent)" }}>⏎</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 9, padding: "8px 12px" }}>
                <span style={{ color: "var(--cyan)" }}>◆</span><span style={{ fontSize: 11, color: "var(--txt)", flex: 1 }}>Open <span style={{ color: "#fff" }}>VESPER</span></span><span style={{ fontSize: 7.5, color: "var(--txt3)" }}>entity · scene-boosted</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 9, padding: "8px 12px" }}>
                <span style={{ color: "var(--txt2)" }}>⌘</span><span style={{ fontSize: 11, color: "var(--txt)", flex: 1 }}>/go scene 12</span><span style={{ fontSize: 7.5, color: "var(--txt3)" }}>command</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 9, padding: "8px 12px" }}>
                <span style={{ color: "var(--txt2)" }}>⌘</span><span style={{ fontSize: 11, color: "var(--txt)", flex: 1 }}>/link vesper → warden</span><span style={{ fontSize: 7.5, color: "var(--txt3)" }}>command</span>
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 12px", borderTop: "1px solid var(--line2)", fontSize: 7.5, color: "var(--txt3)", letterSpacing: ".06em" }}>
              <span>↑↓ navigate</span><span>⏎ run</span><span>esc close</span><span style={{ marginLeft: "auto", color: "var(--amber)" }}>⤷ CONFIRM inline · no modal</span>
            </div>
          </div>
        </div>
        {/* auto-link inbox */}
        <div style={{ flex: 1, overflowY: "auto", padding: 13 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 10 }}>
            <span style={{ fontSize: 8, letterSpacing: ".2em", color: "var(--txt3)" }}>AUTO-LINK INBOX</span>
            <span style={{ fontSize: 7.5, color: "#04060a", background: "var(--amber)", padding: "1px 6px", borderRadius: 6, fontWeight: 600 }}>4 PENDING</span>
            <span style={{ marginLeft: "auto", fontSize: 7.5, color: "var(--txt3)" }}>engine proposes · you commit</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <InboxCard kind="CREATE" kindColor="var(--green)" title={"“Ari” — 4 occurrences"} />
            <InboxCard kind="RELATION" kindColor="var(--cyan)" title="MARLOW × VESPER · co-occur ×6" />
            <InboxCard kind="MEMORY" kindColor="var(--amber)" title={"Vesper “vowed” → progression"} ignore />
          </div>
        </div>
      </div>
    </PanelShell>
  );
}
