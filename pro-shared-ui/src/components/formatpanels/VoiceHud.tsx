import type { CSSProperties } from "react";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";

const panelBox: CSSProperties = {
  position: "relative",
  width: "100%",
  height: "100%",
  background: "radial-gradient(70% 80% at 50% 0%,#0a0e16,#040609)",
  border: "1px solid var(--line)",
  boxShadow: "0 16px 60px rgba(0,0,0,.6)",
  overflow: "hidden",
  display: "flex",
  flexDirection: "column",
};

const ACCENT = { ["--accent"]: "#4cc2ff" } as CSSProperties;

/** One animated waveform bar — height % and per-bar animation duration from the design. */
function WaveBar({ height, dur }: { height: string; dur: string }) {
  return (
    <div
      style={{
        flex: 1,
        height,
        background: "linear-gradient(180deg,var(--cyan),rgba(76,194,255,.2))",
        animation: `lf-bars ${dur} ease-in-out infinite`,
      }}
    />
  );
}

const WAVE: { height: string; dur: string }[] = [
  { height: "60%", dur: "0.9s" },
  { height: "85%", dur: "0.7s" },
  { height: "40%", dur: "1.1s" },
  { height: "95%", dur: "0.6s" },
  { height: "55%", dur: "0.85s" },
  { height: "75%", dur: "0.95s" },
  { height: "35%", dur: "1.2s" },
  { height: "88%", dur: "0.75s" },
  { height: "50%", dur: "1.05s" },
  { height: "70%", dur: "0.8s" },
  { height: "45%", dur: "1.15s" },
  { height: "80%", dur: "0.65s" },
];

/** A COMMIT TARGET row. `active` = cyan highlighted, `dim` = disabled/dimmed. */
function Target({
  active = false,
  dim = false,
  dot,
  label,
  trailing,
}: {
  active?: boolean;
  dim?: boolean;
  dot?: boolean;
  label: string;
  trailing?: string;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        border: active ? "1px solid var(--line-cy)" : "1px solid var(--line2)",
        background: active ? "rgba(76,194,255,.07)" : undefined,
        padding: "6px 9px",
        fontSize: 9,
        color: active ? "#fff" : dim ? "var(--txt3)" : "var(--txt2)",
        opacity: dim ? 0.55 : undefined,
      }}
    >
      {dot && <span style={{ color: "var(--cyan)" }}>●</span>}
      {label}
      {trailing && <span style={{ marginLeft: "auto", fontSize: 7 }}>{trailing}</span>}
    </div>
  );
}

export function VoiceHud(props: PanelProps) {
  return (
    <PanelShell {...props} style={ACCENT}>
      <div data-screen-label="Dexters Room Voice" style={panelBox}>
        <Corners />

        {/* header */}
        <div style={{ height: 40, flex: "none", display: "flex", alignItems: "center", gap: 11, padding: "0 16px", borderBottom: "1px solid var(--line)" }}>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".1em", color: "#fff" }}>DEXTER&apos;S ROOM</span>
          <span style={{ fontSize: 8, color: "var(--txt3)", border: "1px solid var(--line2)", padding: "2px 7px", letterSpacing: ".1em" }}>DESKTOP ONLY</span>
          <div style={{ flex: 1 }} />
          <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 8, color: "var(--green)" }}>
            <span style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--green)" }} />
            LOCAL · audio never leaves device
          </span>
        </div>

        {/* waveform + state */}
        <div style={{ height: 108, flex: "none", display: "flex", alignItems: "center", gap: 16, padding: "0 18px", borderBottom: "1px solid var(--line2)" }}>
          <div style={{ position: "relative", width: 56, height: 56, flex: "none" }}>
            <div style={{ position: "absolute", inset: 0, borderRadius: "50%", border: "1px solid var(--cyan)", animation: "lf-ring 2s ease-in-out infinite" }} />
            <div style={{ position: "absolute", inset: 7, borderRadius: "50%", border: "2px solid var(--cyan)", display: "grid", placeItems: "center", color: "var(--cyan)", fontSize: 8, letterSpacing: ".1em", boxShadow: "0 0 18px rgba(76,194,255,.3) inset" }}>REC</div>
          </div>
          <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 2, height: 56 }}>
            {WAVE.map((b, i) => <WaveBar key={i} height={b.height} dur={b.dur} />)}
          </div>
          <div style={{ flex: "none", textAlign: "right" }}>
            <div style={{ fontFamily: "'Chakra Petch'", fontSize: 13, color: "var(--cyan)" }}>LISTENING</div>
            <div style={{ fontSize: 8, color: "var(--txt3)" }}>state 4 / 14</div>
          </div>
        </div>

        {/* mode rail + context */}
        <div style={{ flex: "none", display: "flex", alignItems: "center", gap: 9, padding: "9px 16px", borderBottom: "1px solid var(--line2)" }}>
          <div style={{ display: "flex", border: "1px solid var(--line2)", fontSize: 8, letterSpacing: ".08em" }}>
            <span style={{ padding: "4px 9px", color: "#04060a", background: "var(--cyan)", fontWeight: 600 }}>DICTATION</span>
            <span style={{ padding: "4px 9px", color: "var(--txt3)", borderLeft: "1px solid var(--line2)" }}>INTENT</span>
            <span style={{ padding: "4px 9px", color: "var(--txt3)", borderLeft: "1px solid var(--line2)" }}>ASK BILLY</span>
            <span style={{ padding: "4px 9px", color: "var(--txt3)", borderLeft: "1px solid var(--line2)" }}>EDIT W/ BILLY</span>
          </div>
          <span style={{ fontSize: 8, color: "var(--txt3)", marginLeft: "auto" }}>project · screenplay · cursor @ SC.12 · text selected</span>
        </div>

        {/* transcript + commit */}
        <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
          {/* transcript */}
          <div style={{ flex: 1, borderRight: "1px solid var(--line2)", padding: "11px 14px", overflowY: "auto" }}>
            <div style={{ fontSize: 7.5, letterSpacing: ".18em", color: "var(--txt3)", marginBottom: 8 }}>TRANSCRIPT · session-only</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, borderLeft: "2px solid var(--green)", padding: "5px 9px", background: "rgba(11,14,21,.4)" }}>
                <span style={{ fontSize: 7, color: "var(--green)" }}>COMMITTED</span>
                <span style={{ fontSize: 9.5, color: "var(--txt2)", flex: 1 }}>She lets the hatch seal behind her.</span>
                <span style={{ fontSize: 7, color: "var(--txt3)" }}>2.1s</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, borderLeft: "2px solid var(--cyan)", padding: "5px 9px", background: "rgba(76,194,255,.06)" }}>
                <span style={{ fontSize: 7, color: "var(--cyan)" }}>PENDING</span>
                <span style={{ fontSize: 9.5, color: "#fff", flex: 1 }}>The static between them is older than the station.</span>
                <span style={{ fontSize: 7, color: "var(--amber)" }}>0.91</span>
              </div>
            </div>
            <div style={{ marginTop: 11, border: "1px solid var(--line-cy)", background: "rgba(76,194,255,.04)", padding: "9px 10px" }}>
              <div style={{ fontSize: 7.5, letterSpacing: ".14em", color: "var(--cyan)", marginBottom: 5 }}>INTENT PREVIEW · cleanup (no mutation)</div>
              <div style={{ fontSize: 9, color: "var(--txt2)" }}><span style={{ color: "var(--txt3)" }}>before:</span> the static between them is older than the station</div>
              <div style={{ fontSize: 9, color: "#eef1f6" }}><span style={{ color: "var(--txt3)" }}>after:</span> The static between them is older than the station.</div>
            </div>
          </div>

          {/* commit target */}
          <div style={{ width: 300, flex: "none", padding: "11px 14px", background: "#06080c" }}>
            <div style={{ fontSize: 7.5, letterSpacing: ".18em", color: "var(--txt3)", marginBottom: 8 }}>COMMIT TARGET · explicit only</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              <Target active dot label="Active cursor @ SC.12" />
              <Target label="Note" />
              <Target label="PSYKE draft entry" />
              <Target dim label="Manuscript append" trailing="disabled · safety" />
            </div>
            <div style={{ display: "flex", gap: 7, marginTop: 11 }}>
              <span style={{ fontSize: 9, color: "#04060a", background: "var(--green)", padding: "6px 11px", fontWeight: 600 }}>COMMIT</span>
              <span style={{ fontSize: 9, color: "var(--txt2)", border: "1px solid var(--line2)", padding: "6px 11px" }}>⟲ UNDO LAST</span>
            </div>
            <div style={{ display: "flex", gap: 9, marginTop: 12, alignItems: "center", justifyContent: "center", fontSize: 9, color: "var(--txt2)" }}>
              <span style={{ width: 30, height: 30, borderRadius: "50%", border: "1px solid var(--blocking,#ff5260)", display: "grid", placeItems: "center", color: "var(--blocking,#ff5260)" }}>■</span>
              <span style={{ width: 30, height: 30, borderRadius: "50%", border: "1px solid var(--cyan)", display: "grid", placeItems: "center", color: "var(--cyan)" }}>▮▮</span>
              <span style={{ fontSize: 8, color: "var(--txt3)" }}>stop · pause</span>
            </div>
          </div>
        </div>
      </div>
    </PanelShell>
  );
}
