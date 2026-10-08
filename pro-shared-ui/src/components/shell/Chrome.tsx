import { useCallback, useEffect, useRef, useState } from "react";
import type { AdaptDTO } from "@logosforge/ui-contracts";
import type { ShellLayout } from "./shellVars";
import { useStudio, useNavigate } from "../../adapters/StudioProvider";
import { createLatestRequestGate } from "../../hooks/latestRequest";
import type { WorkspaceCoreState, WorkspaceStatusModel, WorkspaceStatusTone } from "../../status/workspaceStatus";
export { PsykeConsole } from "./PsykeConsole";

/** Top-bar omnibox — opens the app's command palette. */
export function CommandPalette({ onOpen }: { onOpen?: () => void }) {
  const available = typeof onOpen === "function";
  return (
    <div className="lf-topbar-command" style={{ flex: 1, display: "flex", justifyContent: "center" }}>
      <button
        type="button"
        onClick={onOpen}
        disabled={!available}
        aria-label={available ? "Open command palette" : "Command palette is available in the desktop host"}
        title={available ? "Open command palette" : "The browser preview does not host desktop commands"}
        className="lf-cmd"
        style={{ display: "flex", alignItems: "center", gap: 10, width: "100%", maxWidth: 560, minWidth: 0, height: 30, padding: "0 12px", background: "var(--tint)", border: "1px solid var(--line2)", borderRadius: "var(--control-radius)", color: "var(--txt3)", transition: ".15s", cursor: available ? "text" : "not-allowed", font: "inherit", textAlign: "left", opacity: available ? 1 : 0.62 }}
      >
        <span className="lf-topbar-command-shortcut" style={{ display: "grid", placeItems: "center", minWidth: 46, height: 16, border: "1px solid var(--line2)", fontSize: 8, color: "var(--txt2)", whiteSpace: "nowrap" }}>Ctrl/⌘ K</span>
        <span style={{ color: "var(--accent)" }}>❯</span>
        <span className="lf-topbar-command-copy" style={{ fontSize: 11, letterSpacing: ".04em", flex: 1 }}>{available ? "Run a command · jump to a section · open an AI tool…" : "Command palette is hosted by the desktop app"}</span>
        <span style={{ fontSize: 8, letterSpacing: ".2em", color: "var(--txt3)", border: "1px solid var(--line2)", padding: "1px 5px" }}>{available ? "PALETTE" : "DESKTOP"}</span>
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
  const requests = useRef(createLatestRequestGate()).current;
  useEffect(() => { requests.open(); return () => requests.close(); }, [requests]);
  const projectIdRef = useRef(projectId);
  projectIdRef.current = projectId;
  const [adapt, setAdapt] = useState<AdaptDTO | null>(null);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [error, setError] = useState("");
  const loadAdapt = useCallback(async (preserveError = false) => {
    if (projectId == null) { setAdapt(null); return; }
    const token = requests.begin("adapt");
    try {
      const value = await api.getAdapt(projectId);
      if (requests.isCurrent(token)) { setAdapt(value); if (!preserveError) setError(""); }
    } catch (loadError) {
      if (requests.isCurrent(token)) setError(loadError instanceof Error ? loadError.message : String(loadError));
    }
  }, [api, projectId, requests]);
  useEffect(() => {
    requests.invalidate("adapt");
    busyRef.current = false;
    setBusy(false); setAdapt(null); setError("");
    void loadAdapt(false);
    return () => requests.invalidate("adapt");
  }, [loadAdapt, requests]);
  useEffect(() => {
    if (projectId == null || typeof api.subscribe !== "function") return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const unsubscribe = api.subscribe(projectId, (event) => {
      if (["connected", "scene_changed", "scenes_changed", "psyke_changed", "outline_changed", "project_data_changed"].includes(event.event)) {
        if (timer) clearTimeout(timer);
        timer = setTimeout(() => { void loadAdapt(false); }, 180);
      }
    });
    return () => { if (timer) clearTimeout(timer); unsubscribe?.(); };
  }, [api, projectId, loadAdapt]);

  const mode = adapt?.mode ?? "—";
  const col = MODE_COLOR[adapt?.mode ?? ""] ?? "var(--amber-b)";
  const override = adapt?.override ?? "";
  const setOverride = async (v: string) => {
    if (projectId == null || busyRef.current) return;
    const ownerProjectId = projectId;
    busyRef.current = true;
    setBusy(true); setError("");
    try {
      await api.patchAiBehavior(ownerProjectId, { adaptive_override: v });
      if (projectIdRef.current === ownerProjectId) await loadAdapt(false);
    } catch (saveError) {
      if (projectIdRef.current === ownerProjectId) {
        setError(saveError instanceof Error ? saveError.message : String(saveError));
        await loadAdapt(true);
      }
    } finally {
      if (projectIdRef.current === ownerProjectId) {
        busyRef.current = false;
        setBusy(false);
      }
    }
  };
  const tip = adapt
    ? `Adaptive AI coaching mode — ${override ? `forced to ${override}` : `auto: ${adapt.mode} (from stage ${adapt.stage} × health ${adapt.health})`}. ${adapt.description}`
    : "Adaptive AI coaching mode — auto from stage × health, or override it.";
  return (
    <div className="lf-topbar-adaptive" title={error ? `Adaptive mode failed: ${error}` : tip} style={{ display: "flex", alignItems: "center", gap: 7, height: 26, padding: "0 8px", border: `1px solid ${error ? "var(--blocking)" : "var(--line2)"}`, borderRadius: "var(--control-radius)", background: "var(--tint)" }}>
      <span style={{ fontSize: 8, letterSpacing: ".2em", color: "var(--txt3)" }}>ADAPTIVE</span>
      <span style={{ width: 7, height: 7, borderRadius: "50%", background: col, boxShadow: "var(--signal-glow)", color: col, animation: "lf-pulse 2.6s ease-in-out infinite" }} />
      <select
        value={override || "Auto"}
        disabled={busy || adapt == null}
        aria-label="Adaptive AI coaching mode"
        onChange={(e) => { void setOverride(e.target.value === "Auto" ? "" : e.target.value); }}
        title="Override the coaching mode (Auto = derived from stage × health)"
        style={{ background: "transparent", border: "none", color: col, font: "inherit", fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 11, letterSpacing: ".08em", cursor: "pointer", outline: "none" }}
      >
        <option value="Auto">{override ? "AUTO" : `AUTO · ${String(mode).toUpperCase()}`}</option>
        <option value="Structure">STRUCTURE</option>
        <option value="Balance">BALANCE</option>
        <option value="Refinement">REFINEMENT</option>
      </select>
      {error && <button type="button" role="alert" disabled={busy} aria-label="Retry Adaptive mode" title={`Retry: ${error}`} onClick={() => { void loadAdapt(false); }} style={{ color: "var(--blocking)", fontSize: 9, border: "none", background: "transparent", cursor: busy ? "default" : "pointer", padding: 0 }}>⚠</button>}
      <span style={{ width: 1, height: 14, background: "var(--line2)" }} />
      <button type="button" onClick={() => navigate("Adapt")} title="Open the Adapt panel" style={{ background: "transparent", border: "none", color: "var(--txt3)", font: "inherit", fontSize: 8, letterSpacing: ".14em", cursor: "pointer", padding: 0 }}>ADAPT ›</button>
    </div>
  );
}

function FocusToggle({ layout, onToggle }: { layout: ShellLayout; onToggle?: () => void }) {
  const seg = (label: string, on: boolean, target: ShellLayout) => (
    <button type="button"
      aria-pressed={on}
      onClick={onToggle && layout !== target ? onToggle : undefined}
      style={{
        display: "grid", placeItems: "center", padding: "0 11px", font: "inherit", letterSpacing: ".16em", border: "none",
        background: on ? "var(--accent)" : "transparent", color: on ? "var(--on-accent)" : "var(--txt2)", fontWeight: on ? 700 : 400,
        boxShadow: on ? "0 0 12px rgba(76,194,255,.4)" : undefined, cursor: onToggle && !on ? "pointer" : "default",
      }}
    >{label}</button>
  );
  return (
    <div className="lf-topbar-layout" role="group" aria-label="Workspace mode" style={{ display: "flex", height: 26, border: "1px solid var(--line2)", fontSize: 9 }} title="Focus mode hides the rails; Cockpit shows everything">
      {seg("FOCUS", layout === "focus", "focus")}
      {seg("COCKPIT", layout === "cockpit", "cockpit")}
    </div>
  );
}

const STATUS_COLOR: Record<WorkspaceStatusTone, string> = {
  neutral: "var(--txt2)",
  info: "var(--accent)",
  success: "var(--green)",
  warning: "var(--amber)",
  danger: "var(--crimson)",
};

const UNKNOWN_STATUS: WorkspaceStatusModel = {
  kind: "ready",
  priority: 0,
  tone: "neutral",
  copy: "LOCAL STATUS UNKNOWN",
  detail: "No runtime persistence status was supplied by this host.",
  storage: "local",
  storageCopy: "LOCAL",
  dirty: false,
  inFlightCount: 0,
  lastSavedAt: null,
};

function SyncHud({ status = UNKNOWN_STATUS }: { status?: WorkspaceStatusModel }) {
  const color = STATUS_COLOR[status.tone];
  const saved = status.lastSavedAt == null ? "No completed save in this session" : `Last local save ${new Date(status.lastSavedAt).toLocaleTimeString()}`;
  return (
    <>
      <span role="status" aria-live="polite" aria-atomic="true" style={{ position: "absolute", width: 1, height: 1, padding: 0, margin: -1, overflow: "hidden", clip: "rect(0,0,0,0)", whiteSpace: "nowrap", border: 0 }}>
        {status.copy}. {status.detail}
      </span>
      <details className="lf-topbar-status" style={{ position: "relative", height: 26 }}>
        <summary className="lf-topbar-status-summary" aria-label={`Workspace status: ${status.copy}`} style={{ listStyle: "none", display: "flex", alignItems: "center", gap: 9, height: 26, padding: "0 11px", border: `1px solid color-mix(in srgb, ${color} 38%, transparent)`, borderRadius: "var(--control-radius)", background: "var(--tint)", cursor: "pointer" }}>
          <span className="lf-topbar-status-dot" aria-hidden="true" style={{ width: 7, height: 7, borderRadius: "50%", background: color, boxShadow: "var(--signal-glow)", color }} />
          <span className="lf-topbar-status-copy" style={{ fontSize: 9, letterSpacing: ".13em", color }}>{status.copy}</span>
          <span className="lf-topbar-status-separator" aria-hidden="true" style={{ width: 1, height: 13, background: "var(--line2)" }} />
          <span className="lf-topbar-status-storage" style={{ fontSize: 8, color: "var(--txt3)", letterSpacing: ".12em" }}>{status.storageCopy}</span>
        </summary>
        <div className="lf-topbar-status-popover" style={{ position: "absolute", top: 32, right: 0, zIndex: 70, width: 320, padding: "11px 12px", border: "1px solid var(--line)", borderTop: `2px solid ${color}`, borderRadius: "var(--control-radius)", background: "var(--raised)", boxShadow: "var(--chrome-shadow)", fontSize: 9, lineHeight: 1.5 }}>
          <div style={{ color, letterSpacing: ".14em", marginBottom: 5 }}>{status.copy}</div>
          <div style={{ color: "var(--txt2)" }}>{status.detail}</div>
          <div style={{ color: "var(--txt3)", marginTop: 7 }}>{saved} · storage: this device</div>
        </div>
      </details>
    </>
  );
}

export function TopBar({
  formatBadge,
  layout,
  runtimeStatus,
  onCommandPalette,
  onToggleFocus,
}: {
  formatBadge: string;
  layout: ShellLayout;
  runtimeStatus?: WorkspaceStatusModel;
  onCommandPalette?: () => void;
  onToggleFocus?: () => void;
}) {
  return (
    <div className="lf-topbar">
      {/* brand */}
      <div className="lf-topbar-brand" style={{ display: "flex", alignItems: "center", gap: 9, paddingRight: 14, borderRight: "1px solid var(--line2)" }}>
        <div className="lf-brand-mark" style={{ position: "relative", width: 22, height: 22, display: "grid", placeItems: "center", border: "1px solid var(--crimson)", boxShadow: "var(--signal-glow)", color: "var(--crimson)", borderRadius: "var(--control-radius)" }}>
          <div className="lf-brand-mark-core" style={{ width: 8, height: 8, background: "var(--crimson)", boxShadow: "var(--signal-glow)" }} />
          <div className="lf-brand-corner" style={{ position: "absolute", top: -1, left: -1, width: 5, height: 5, borderTop: "1px solid var(--crimson)", borderLeft: "1px solid var(--crimson)" }} />
          <div className="lf-brand-corner" style={{ position: "absolute", bottom: -1, right: -1, width: 5, height: 5, borderBottom: "1px solid var(--crimson)", borderRight: "1px solid var(--crimson)" }} />
        </div>
        <div style={{ lineHeight: 1 }}>
          <div className="lf-brand-wordmark" style={{ fontFamily: "var(--display-font)", fontWeight: 700, fontSize: 15, letterSpacing: "var(--brand-tracking)", color: "var(--strong)" }}>LOGOSFORGE</div>
          <div className="lf-brand-subtitle" style={{ fontFamily: "var(--ui-font)", fontSize: 8, letterSpacing: ".5em", color: "var(--crimson)", marginTop: 2 }}>STUDIO · PRO</div>
        </div>
      </div>

      {/* active writing format */}
      <div className="lf-topbar-format" style={{ display: "flex", alignItems: "center", gap: 6, height: 20, padding: "0 9px", border: "1px solid var(--accent)", borderRadius: "var(--control-radius)", background: "color-mix(in srgb,var(--accent) 9%,transparent)", color: "var(--accent)", fontSize: 9.5, letterSpacing: ".18em", boxShadow: "var(--signal-glow)" }}>
        <span className="lf-topbar-format-dot" style={{ width: 5, height: 5, background: "var(--accent)", boxShadow: "var(--signal-glow)" }} />{formatBadge}
      </div>

      <CommandPalette onOpen={onCommandPalette} />
      <ModeStrip />
      <FocusToggle layout={layout} onToggle={onToggleFocus} />
      <SyncHud status={runtimeStatus} />
    </div>
  );
}

export function StatusBar({ runtimeStatus = UNKNOWN_STATUS, coreState = "connecting", statusCenter }: { runtimeStatus?: WorkspaceStatusModel; coreState?: WorkspaceCoreState; statusCenter: string }) {
  const color = STATUS_COLOR[runtimeStatus.tone];
  const coreColor = coreState === "connected" ? "var(--green)" : coreState === "error" ? "var(--crimson)" : "var(--amber)";
  return (
    <div style={{ position: "relative", zIndex: 30, height: 26, flex: "none", display: "flex", alignItems: "center", gap: 14, padding: "0 14px", background: "var(--base)", borderTop: "1px solid var(--line)", fontSize: 9, letterSpacing: ".06em", color: "var(--txt3)" }}>
      <span style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--txt2)" }}>
        <span style={{ width: 6, height: 6, borderRadius: "50%", background: coreColor, boxShadow: `0 0 6px ${coreColor}`, animation: coreState === "connecting" ? "lf-pulse 2.4s ease-in-out infinite" : undefined }} />CORE · {coreState.toUpperCase()}
      </span>
      <span style={{ display: "flex", alignItems: "center", gap: 6, color, border: `1px solid color-mix(in srgb, ${color} 30%, transparent)`, padding: "1px 8px", letterSpacing: ".12em" }}>{runtimeStatus.copy}</span>
      <div style={{ flex: 1, textAlign: "center", color: "var(--txt2)", letterSpacing: ".12em" }}>{statusCenter}</div>
      <span style={{ color: "var(--txt2)" }}>UTF-8</span>
      <span style={{ color: "var(--txt2)" }}>{runtimeStatus.storageCopy} DATA</span>
    </div>
  );
}
