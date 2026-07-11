import { useCallback, useEffect, useState } from "react";
import type { AdaptDTO } from "@logosforge/ui-contracts";
import type { ShellLayout } from "./shellVars";
import { useStudio, useNavigate } from "../../adapters/StudioProvider";

/** Top-bar omnibox — opens the app's command palette. */
export function CommandPalette({ onOpen }: { onOpen?: () => void }) {
  return (
    <div style={{ flex: 1, display: "flex", justifyContent: "center" }}>
      <button type="button" onClick={onOpen} className="lf-cmd" style={{ display: "flex", alignItems: "center", gap: 10, width: 560, height: 30, padding: "0 12px", background: "var(--tint)", border: "1px solid var(--line2)", borderRadius: 2, color: "var(--txt3)", transition: ".15s", cursor: onOpen ? "text" : "default", font: "inherit", textAlign: "left" }}>
        <span style={{ display: "grid", placeItems: "center", width: 18, height: 16, border: "1px solid var(--line2)", fontSize: 9, color: "var(--txt2)" }}>⌘K</span>
        <span style={{ color: "var(--accent)" }}>❯</span>
        <span style={{ fontSize: 11, letterSpacing: ".04em", flex: 1 }}>Run a command · jump to a section · open an AI tool…</span>
        <span style={{ fontSize: 8, letterSpacing: ".2em", color: "var(--txt3)", border: "1px solid var(--line2)", padding: "1px 5px" }}>PALETTE</span>
      </button>
    </div>
  );
}

// Colour the mode by what the core's adaptive engine is coaching toward.
const MODE_COLOR: Record<string, string> = {
  Structure: "var(--accent)",   // scaffolding phase
  Balance: "var(--amber-b)",    // even-out phase
  Refinement: "var(--green)",   // polish phase
};

/**
 * Adaptive-AI mode strip — the core's coaching mode (Structure / Balance /
 * Refinement). By default it's DERIVED from the project's stage × health
 * (`adaptive_mode.py`), but the dropdown lets the writer OVERRIDE it (Auto = let
 * the engine decide). The override persists via `/ai/behavior` and flows into
 * Billy's prompts + the Adapt suggestions. "ADAPT ›" opens the full read-out.
 */
export function ModeStrip() {
  const { api, projectId } = useStudio();
  const navigate = useNavigate();
  const [adapt, setAdapt] = useState<AdaptDTO | null>(null);
  const refetch = useCallback(() => {
    if (projectId == null) { setAdapt(null); return; }
    api.getAdapt(projectId).then(setAdapt).catch(() => setAdapt(null));
  }, [api, projectId]);
  useEffect(() => {
    if (projectId == null) { setAdapt(null); return; }
    let alive = true;
    api.getAdapt(projectId).then((a) => { if (alive) setAdapt(a); }).catch(() => { if (alive) setAdapt(null); });
    return () => { alive = false; };
  }, [api, projectId]);

  const mode = adapt?.mode ?? "—";
  const col = MODE_COLOR[adapt?.mode ?? ""] ?? "var(--amber-b)";
  const override = adapt?.override ?? "";
  const setOverride = (v: string) => {
    if (projectId == null) return;
    api.patchAiBehavior(projectId, { adaptive_override: v }).then(() => refetch()).catch(() => {});
  };
  const tip = adapt
    ? `Adaptive AI coaching mode — ${override ? `forced to ${override}` : `auto: ${adapt.mode} (from stage ${adapt.stage} × health ${adapt.health})`}. ${adapt.description}`
    : "Adaptive AI coaching mode — auto from stage × health, or override it.";
  return (
    <div title={tip} style={{ display: "flex", alignItems: "center", gap: 7, height: 26, padding: "0 8px", border: "1px solid var(--line2)", background: "var(--tint)" }}>
      <span style={{ fontSize: 8, letterSpacing: ".2em", color: "var(--txt3)" }}>ADAPTIVE</span>
      <span style={{ width: 7, height: 7, borderRadius: "50%", background: col, boxShadow: `0 0 8px ${col}`, animation: "lf-pulse 2.6s ease-in-out infinite" }} />
      <select
        value={override || "Auto"}
        onChange={(e) => setOverride(e.target.value === "Auto" ? "" : e.target.value)}
        title="Override the coaching mode (Auto = derived from stage × health)"
        style={{ background: "transparent", border: "none", color: col, font: "inherit", fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 11, letterSpacing: ".08em", cursor: "pointer", outline: "none" }}
      >
        <option value="Auto">{override ? "AUTO" : `AUTO · ${String(mode).toUpperCase()}`}</option>
        <option value="Structure">STRUCTURE</option>
        <option value="Balance">BALANCE</option>
        <option value="Refinement">REFINEMENT</option>
      </select>
      <span style={{ width: 1, height: 14, background: "var(--line2)" }} />
      <button type="button" onClick={() => navigate("Adapt")} title="Open the Adapt panel" style={{ background: "transparent", border: "none", color: "var(--txt3)", font: "inherit", fontSize: 8, letterSpacing: ".14em", cursor: "pointer", padding: 0 }}>ADAPT ›</button>
    </div>
  );
}

function FocusToggle({ layout, onToggle }: { layout: ShellLayout; onToggle?: () => void }) {
  const seg = (label: string, on: boolean, target: ShellLayout) => (
    <button
      type="button"
      onClick={onToggle && layout !== target ? onToggle : undefined}
      style={{
        display: "grid", placeItems: "center", padding: "0 11px", font: "inherit", letterSpacing: ".16em", border: "none",
        background: on ? "var(--accent)" : "transparent", color: on ? "var(--on-accent)" : "var(--txt2)", fontWeight: on ? 700 : 400,
        boxShadow: on ? "0 0 12px rgba(76,194,255,.4)" : undefined, cursor: onToggle && !on ? "pointer" : "default",
      }}
    >{label}</button>
  );
  return (
    <div style={{ display: "flex", height: 26, border: "1px solid var(--line2)", fontSize: 9 }} title="Focus mode hides the rails; Cockpit shows everything">
      {seg("FOCUS", layout === "focus", "focus")}
      {seg("COCKPIT", layout === "cockpit", "cockpit")}
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
  onCommandPalette,
  onToggleFocus,
}: {
  formatBadge: string;
  layout: ShellLayout;
  countdown: string;
  onCommandPalette?: () => void;
  onToggleFocus?: () => void;
}) {
  return (
    <div style={{ position: "relative", zIndex: 30, height: 46, flex: "none", display: "flex", alignItems: "center", gap: 14, padding: "0 14px", background: "linear-gradient(180deg,var(--raised),var(--panel2))", borderBottom: "1px solid var(--line)" }}>
      {/* brand */}
      <div style={{ display: "flex", alignItems: "center", gap: 9, paddingRight: 14, borderRight: "1px solid var(--line2)" }}>
        <div style={{ position: "relative", width: 22, height: 22, display: "grid", placeItems: "center", border: "1px solid var(--crimson)", boxShadow: "0 0 10px rgba(232,68,58,.5) inset,0 0 8px rgba(232,68,58,.35)" }}>
          <div style={{ width: 8, height: 8, background: "var(--crimson)", boxShadow: "0 0 8px var(--crimson)" }} />
          <div style={{ position: "absolute", top: -1, left: -1, width: 5, height: 5, borderTop: "1px solid var(--crimson)", borderLeft: "1px solid var(--crimson)" }} />
          <div style={{ position: "absolute", bottom: -1, right: -1, width: 5, height: 5, borderBottom: "1px solid var(--crimson)", borderRight: "1px solid var(--crimson)" }} />
        </div>
        <div style={{ lineHeight: 1 }}>
          <div style={{ fontFamily: "'Chakra Petch',sans-serif", fontWeight: 700, fontSize: 15, letterSpacing: ".16em", color: "var(--strong)" }}>LOGOSFORGE</div>
          <div style={{ fontFamily: "'JetBrains Mono'", fontSize: 8, letterSpacing: ".5em", color: "var(--crimson)", marginTop: 2 }}>STUDIO · PRO</div>
        </div>
      </div>

      {/* active writing format */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, height: 20, padding: "0 9px", border: "1px solid var(--accent)", background: "linear-gradient(180deg,rgba(76,194,255,.10),transparent)", color: "var(--accent)", fontSize: 9.5, letterSpacing: ".18em", boxShadow: "0 0 10px rgba(76,194,255,.18)" }}>
        <span style={{ width: 5, height: 5, background: "var(--accent)", boxShadow: "0 0 6px var(--accent)" }} />{formatBadge}
      </div>

      <CommandPalette onOpen={onCommandPalette} />
      <ModeStrip />
      <FocusToggle layout={layout} onToggle={onToggleFocus} />
      <SyncHud countdown={countdown} />
    </div>
  );
}

/** PSYKE console slim bar (omni-input surface 2), pinned under the editor. */
export function PsykeConsole() {
  return (
    <div style={{ height: 30, flex: "none", display: "flex", alignItems: "center", gap: 10, padding: "0 14px", background: "var(--panel2)", borderTop: "1px solid var(--line)", position: "relative" }}>
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
  void sync;
  return (
    <div style={{ position: "relative", zIndex: 30, height: 26, flex: "none", display: "flex", alignItems: "center", gap: 14, padding: "0 14px", background: "var(--base)", borderTop: "1px solid var(--line)", fontSize: 9, letterSpacing: ".06em", color: "var(--txt3)" }}>
      <span style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--txt2)" }}>
        <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--green)", boxShadow: "0 0 6px var(--green)", animation: "lf-pulse 2.4s ease-in-out infinite" }} />CORE · CONNECTED
      </span>
      <span style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--green)", border: "1px solid rgba(98,217,154,.28)", padding: "1px 8px", letterSpacing: ".14em" }}>LOCAL-FIRST</span>
      <div style={{ flex: 1, textAlign: "center", color: "var(--txt2)", letterSpacing: ".12em" }}>{statusCenter}</div>
      <span style={{ color: "var(--txt2)" }}>UTF-8</span>
      <span style={{ color: "var(--txt2)" }}>⟲ {countdown}</span>
      <span style={{ color: "var(--txt2)" }}>LOCAL</span>
    </div>
  );
}
