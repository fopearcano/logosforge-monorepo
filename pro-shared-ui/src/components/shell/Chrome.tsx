import type { ShellLayout } from "./shellVars";

/** Top-bar omnibox (Command Palette surface 1). */
export function CommandPalette() {
  return (
    <div style={{ flex: 1, display: "flex", justifyContent: "center" }}>
      <div className="lf-cmd" style={{ display: "flex", alignItems: "center", gap: 10, width: 560, height: 30, padding: "0 12px", background: "rgba(8,11,17,.9)", border: "1px solid var(--line2)", borderRadius: 2, color: "var(--txt3)", transition: ".15s" }}>
        <span style={{ display: "grid", placeItems: "center", width: 18, height: 16, border: "1px solid var(--line2)", fontSize: 9, color: "var(--txt2)" }}>⌘K</span>
        <span style={{ color: "var(--accent)" }}>❯</span>
        <span style={{ fontSize: 11, letterSpacing: ".04em", flex: 1 }}>Run a command · jump to a scene · ask Billy…</span>
        <span style={{ fontSize: 8, letterSpacing: ".2em", color: "var(--txt3)", border: "1px solid var(--line2)", padding: "1px 5px" }}>PALETTE</span>
      </div>
    </div>
  );
}

/** Adaptive-AI mode strip (the AI behaviour mode, distinct from writing mode). */
export function ModeStrip({ aiMode = "BALANCE" }: { aiMode?: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, height: 26, padding: "0 10px", border: "1px solid var(--line2)", background: "rgba(11,14,21,.7)" }}>
      <span style={{ fontSize: 8, letterSpacing: ".22em", color: "var(--txt3)" }}>ADAPTIVE</span>
      <span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--amber)", boxShadow: "0 0 8px var(--amber)", animation: "lf-pulse 2.6s ease-in-out infinite" }} />
      <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 11, letterSpacing: ".12em", color: "var(--amber-b)" }}>{aiMode}</span>
      <span style={{ color: "var(--txt3)", fontSize: 9 }}>▾</span>
      <span style={{ width: 1, height: 14, background: "var(--line2)" }} />
      <span style={{ fontSize: 8, letterSpacing: ".14em", color: "var(--txt3)" }}>RESET</span>
    </div>
  );
}

function FocusToggle({ layout }: { layout: ShellLayout }) {
  const seg = (label: string, on: boolean) =>
    on ? (
      <div style={{ display: "grid", placeItems: "center", padding: "0 11px", background: "var(--accent)", color: "#04060a", fontWeight: 700, boxShadow: "0 0 12px rgba(76,194,255,.4)" }}>{label}</div>
    ) : (
      <div style={{ display: "grid", placeItems: "center", padding: "0 11px", color: "var(--txt2)" }}>{label}</div>
    );
  return (
    <div style={{ display: "flex", height: 26, border: "1px solid var(--line2)", fontSize: 9, letterSpacing: ".16em" }}>
      {seg("FOCUS", layout === "focus")}
      {seg("COCKPIT", layout === "cockpit")}
    </div>
  );
}

function SyncHud({ countdown }: { countdown: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 9, height: 26, padding: "0 11px", border: "1px solid rgba(98,217,154,.35)", background: "rgba(98,217,154,.06)" }}>
      <span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--green)", boxShadow: "0 0 8px var(--green)" }} />
      <span style={{ fontSize: 9, letterSpacing: ".16em", color: "var(--green)" }}>SYNCED</span>
      <span style={{ width: 1, height: 13, background: "var(--line2)" }} />
      <span style={{ fontSize: 9, color: "var(--txt2)", letterSpacing: ".08em" }}>⟲ AUTOSAVE {countdown}</span>
      <span style={{ width: 1, height: 13, background: "var(--line2)" }} />
      <span style={{ fontSize: 9, color: "var(--txt3)", letterSpacing: ".12em" }}>LOCAL</span>
    </div>
  );
}

export function TopBar({
  formatBadge,
  layout,
  countdown,
}: {
  formatBadge: string;
  layout: ShellLayout;
  countdown: string;
}) {
  return (
    <div style={{ position: "relative", zIndex: 30, height: 46, flex: "none", display: "flex", alignItems: "center", gap: 14, padding: "0 14px", background: "linear-gradient(180deg,#0a0d13,#06080c)", borderBottom: "1px solid var(--line)" }}>
      {/* brand */}
      <div style={{ display: "flex", alignItems: "center", gap: 9, paddingRight: 14, borderRight: "1px solid var(--line2)" }}>
        <div style={{ position: "relative", width: 22, height: 22, display: "grid", placeItems: "center", border: "1px solid var(--crimson)", boxShadow: "0 0 10px rgba(232,68,58,.5) inset,0 0 8px rgba(232,68,58,.35)" }}>
          <div style={{ width: 8, height: 8, background: "var(--crimson)", boxShadow: "0 0 8px var(--crimson)" }} />
          <div style={{ position: "absolute", top: -1, left: -1, width: 5, height: 5, borderTop: "1px solid var(--crimson)", borderLeft: "1px solid var(--crimson)" }} />
          <div style={{ position: "absolute", bottom: -1, right: -1, width: 5, height: 5, borderBottom: "1px solid var(--crimson)", borderRight: "1px solid var(--crimson)" }} />
        </div>
        <div style={{ lineHeight: 1 }}>
          <div style={{ fontFamily: "'Chakra Petch',sans-serif", fontWeight: 700, fontSize: 15, letterSpacing: ".16em", color: "#fff" }}>LOGOSFORGE</div>
          <div style={{ fontFamily: "'JetBrains Mono'", fontSize: 8, letterSpacing: ".5em", color: "var(--crimson)", marginTop: 2 }}>STUDIO · PRO</div>
        </div>
      </div>

      {/* active writing format */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, height: 20, padding: "0 9px", border: "1px solid var(--accent)", background: "linear-gradient(180deg,rgba(76,194,255,.10),transparent)", color: "var(--accent)", fontSize: 9.5, letterSpacing: ".18em", boxShadow: "0 0 10px rgba(76,194,255,.18)" }}>
        <span style={{ width: 5, height: 5, background: "var(--accent)", boxShadow: "0 0 6px var(--accent)" }} />{formatBadge}
      </div>

      <CommandPalette />
      <ModeStrip />
      <FocusToggle layout={layout} />
      <SyncHud countdown={countdown} />
    </div>
  );
}

/** PSYKE console slim bar (omni-input surface 2), pinned under the editor. */
export function PsykeConsole() {
  return (
    <div style={{ height: 30, flex: "none", display: "flex", alignItems: "center", gap: 10, padding: "0 14px", background: "#06080c", borderTop: "1px solid var(--line)", position: "relative" }}>
      <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 2, background: "var(--accent)", boxShadow: "0 0 10px var(--accent)" }} />
      <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 700, color: "var(--accent)", fontSize: 12 }}>ψ</span>
      <span style={{ color: "var(--accent)" }}>❯</span>
      <span style={{ flex: 1, fontSize: 11, color: "var(--txt3)", letterSpacing: ".03em" }}>
        Search the bible or type <span style={{ color: "var(--txt2)" }}>/</span> for commands — <span style={{ color: "var(--txt2)" }}>/create  /open  /go  /ai  /idea</span>
      </span>
      <span style={{ fontSize: 8, letterSpacing: ".22em", color: "var(--txt3)", border: "1px solid var(--line2)", padding: "2px 6px" }}>PSYKE CONSOLE</span>
      <span style={{ fontSize: 8, letterSpacing: ".2em", color: "var(--txt3)" }}>⌘⏎</span>
    </div>
  );
}

export function StatusBar({ countdown, sync, statusCenter }: { countdown: string; sync: string; statusCenter: string }) {
  return (
    <div style={{ position: "relative", zIndex: 30, height: 26, flex: "none", display: "flex", alignItems: "center", gap: 14, padding: "0 14px", background: "#05070b", borderTop: "1px solid var(--line)", fontSize: 9, letterSpacing: ".06em", color: "var(--txt3)" }}>
      <span style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--txt2)" }}>
        <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--green)", boxShadow: "0 0 6px var(--green)", animation: "lf-pulse 2.4s ease-in-out infinite" }} />EVENT · scene_changed → Scene 12 · 0.3s
      </span>
      <span style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--green)", border: "1px solid rgba(98,217,154,.28)", padding: "1px 8px", letterSpacing: ".14em" }}>DETERMINISTIC · NO AI · REBUILT LIVE</span>
      <div style={{ flex: 1, textAlign: "center", color: "var(--txt2)", letterSpacing: ".12em" }}>{statusCenter}</div>
      <span>LN 14 · COL 32</span>
      <span style={{ color: "var(--txt2)" }}>UTF-8</span>
      <span style={{ color: "var(--txt2)" }}>⟲ {countdown}</span>
      <span style={{ color: "var(--txt2)" }}>LOCAL · NO LOCK</span>
      <span style={{ color: "var(--accent)" }}>SYNC {sync}%</span>
      <span style={{ color: "var(--txt2)" }}>100%</span>
    </div>
  );
}
