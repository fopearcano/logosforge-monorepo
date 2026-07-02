import type { CSSProperties, ReactNode } from "react";
import type { WritingMode } from "@logosforge/ui-contracts";
import { useWritingMode, useStudio } from "../../adapters/StudioProvider";
import { useProjects } from "../../hooks";
import { ShellStyles } from "./ShellStyles";
import { Navigator } from "./Navigator";
import { TopBar, PsykeConsole, StatusBar } from "./Chrome";
import { ManuscriptRegion, IntelligenceDock, BottomDock } from "./regions";
import {
  shellThemeVars,
  resolveMode,
  MODE_NAMES,
  MODE_SPINES,
  MODE_FORMATS,
  type ShellLayout,
  type CinematicLevel,
} from "./shellVars";

export interface WorkspaceShellProps {
  /** Active writing mode → drives --accent + per-mode vocabulary. Falls back to
   *  the <StudioProvider> writingMode, then 'screenplay'. */
  writingMode?: WritingMode | string;
  /** 'cockpit' shows all docks; 'focus' hides nav/right/bottom (editor only). */
  layout?: ShellLayout;
  /** Ambient HUD intensity: restrained < cinematic < full_hud. */
  cinematicLevel?: CinematicLevel;
  /** Active project name shown in the top-bar switcher. */
  projectTitle?: string;
  countdown?: string;
  sync?: string;
  statusCenter?: string;
  /** Dock slots — override the faithful defaults with real panels (T02/T03/T06). */
  navSlot?: ReactNode;
  centerSlot?: ReactNode;
  rightSlot?: ReactNode;
  bottomSlot?: ReactNode;
}

const ambient = (s: CSSProperties): CSSProperties => ({ position: "absolute", inset: 0, pointerEvents: "none", ...s });

export function WorkspaceShell(props: WorkspaceShellProps) {
  const ctxMode = useWritingMode();
  const mode = resolveMode(props.writingMode ?? ctxMode);
  const layout: ShellLayout = props.layout ?? "cockpit";
  const cine: CinematicLevel = props.cinematicLevel ?? "full_hud";

  const showDocks = layout !== "focus";
  const gridOn = cine !== "restrained";
  const scanOn = cine === "full_hud";

  // Real current-project title from the core (falls back to the prop, then a
  // neutral default — never the old "NULL HORIZON" mock).
  const { projectId } = useStudio();
  const { data: projects } = useProjects();
  const realTitle = projects?.find((p) => p.id === projectId)?.title;
  const projectTitle = props.projectTitle ?? realTitle ?? "Untitled Project";
  const countdown = props.countdown ?? "02:41";
  const sync = props.sync ?? "99.412";
  const statusCenter = props.statusCenter ?? "ACT II · SEQUENCE D · SCENE 12 · “OBSERVATION RING”";

  const root: CSSProperties = {
    position: "relative",
    width: "100%",
    height: "100%",
    minHeight: 0,
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
    background: "var(--void)",
    color: "var(--txt)",
    fontFamily: "'JetBrains Mono','SFMono-Regular',monospace",
    fontSize: 12,
    lineHeight: 1.45,
    letterSpacing: ".02em",
    ...shellThemeVars(mode),
  };

  const cornerBracket = (pos: CSSProperties, glow: string): CSSProperties => ({
    position: "absolute",
    width: 17,
    height: 17,
    pointerEvents: "none",
    zIndex: 58,
    boxShadow: glow,
    ...pos,
  });

  return (
    <div className="lf-shell" data-screen-label="Workspace Shell — Cockpit" style={root}>
      <ShellStyles />

      {/* ambient background layers */}
      {gridOn && <div style={ambient({ backgroundImage: "radial-gradient(circle,rgba(128,140,158,.07) 1px,transparent 1.4px)", backgroundSize: "30px 30px", zIndex: 0 })} />}
      <div style={ambient({ background: "radial-gradient(120% 90% at 50% -10%,rgba(232,68,58,.10),transparent 55%),radial-gradient(90% 70% at 80% 120%,rgba(76,194,255,.05),transparent 60%)", zIndex: 0 })} />
      <div style={ambient({ background: "radial-gradient(130% 120% at 50% 50%,transparent 62%,rgba(0,0,0,.72))", zIndex: 1 })} />
      {scanOn && <>
        <div style={ambient({ background: "repeating-linear-gradient(0deg,transparent 0 2px,rgba(255,255,255,.013) 2px 3px)", zIndex: 60 })} />
        <div style={{ position: "absolute", left: 0, right: 0, height: 140, top: 0, background: "linear-gradient(180deg,transparent,rgba(76,194,255,.05),transparent)", pointerEvents: "none", zIndex: 60, animation: "lf-scan 9s linear infinite" }} />
      </>}
      {/* perimeter tick rulers */}
      <div style={{ position: "absolute", top: 3, left: 120, right: 120, height: 5, backgroundImage: "repeating-linear-gradient(90deg,rgba(245,177,51,.5) 0 1px,transparent 1px 26px)", pointerEvents: "none", zIndex: 55 }} />
      <div style={{ position: "absolute", bottom: 2, left: 120, right: 120, height: 5, backgroundImage: "repeating-linear-gradient(90deg,rgba(245,177,51,.32) 0 1px,transparent 1px 26px)", pointerEvents: "none", zIndex: 55 }} />
      {/* corner frame brackets */}
      <div style={cornerBracket({ top: 6, left: 6, borderTop: "1px solid var(--crimson)", borderLeft: "1px solid var(--crimson)" }, "-1px -1px 8px rgba(232,68,58,.3)")} />
      <div style={cornerBracket({ top: 6, right: 6, borderTop: "1px solid var(--crimson)", borderRight: "1px solid var(--crimson)" }, "1px -1px 8px rgba(232,68,58,.3)")} />
      <div style={cornerBracket({ bottom: 6, left: 6, borderBottom: "1px solid var(--crimson)", borderLeft: "1px solid var(--crimson)" }, "-1px 1px 8px rgba(232,68,58,.3)")} />
      <div style={cornerBracket({ bottom: 6, right: 6, borderBottom: "1px solid var(--crimson)", borderRight: "1px solid var(--crimson)" }, "1px 1px 8px rgba(232,68,58,.3)")} />

      {/* top bar */}
      <TopBar formatBadge={MODE_FORMATS[mode]} layout={layout} countdown={countdown} />

      {/* body row */}
      <div style={{ position: "relative", zIndex: 20, display: "flex", flex: 1, minHeight: 0 }}>
        {showDocks && (props.navSlot ?? <Navigator projectTitle={projectTitle} modeName={MODE_NAMES[mode]} spineLabel={MODE_SPINES[mode]} />)}
        {/* center column: editor + PSYKE console */}
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
          <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
            {props.centerSlot ?? <ManuscriptRegion />}
          </div>
          <PsykeConsole />
        </div>
        {showDocks && (props.rightSlot ?? <IntelligenceDock />)}
      </div>

      {/* bottom analysis dock */}
      {showDocks && (props.bottomSlot ?? <BottomDock />)}

      {/* status bar */}
      <StatusBar countdown={countdown} sync={sync} statusCenter={statusCenter} />
    </div>
  );
}
