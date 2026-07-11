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
  type AppearanceTheme,
} from "./shellVars";

export interface WorkspaceShellProps {
  /** Active writing mode → drives --accent + per-mode vocabulary. Falls back to
   *  the <StudioProvider> writingMode, then 'screenplay'. */
  writingMode?: WritingMode | string;
  /** 'cockpit' shows all docks; 'focus' hides nav/right/bottom (editor only). */
  layout?: ShellLayout;
  /** Visual theme: 'dark' | 'light' | 'warm'. Drives the whole surface palette. */
  theme?: AppearanceTheme;
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
  /** Show the slim PSYKE console bar under the editor (a design element). Off when
   *  a real app supplies its own input surfaces. Default true. */
  showConsole?: boolean;
  /** Open the app's command palette (the top-bar ⌘K omnibox). */
  onCommandPalette?: () => void;
  /** Toggle Focus ↔ Cockpit (Focus hides the rails for distraction-free writing). */
  onToggleFocus?: () => void;
}

const ambient = (s: CSSProperties): CSSProperties => ({ position: "absolute", inset: 0, pointerEvents: "none", ...s });

export function WorkspaceShell(props: WorkspaceShellProps) {
  const ctxMode = useWritingMode();
  const mode = resolveMode(props.writingMode ?? ctxMode);
  const layout: ShellLayout = props.layout ?? "cockpit";
  const theme: AppearanceTheme = props.theme ?? "dark";

  const showDocks = layout !== "focus";
  // A calm, clean surface (the old HUD grid/scanlines/rulers/brackets are gone).
  // On dark, a soft edge vignette adds depth; on light/warm it would muddy the
  // paper, so it's dark-only and gentle.
  const isDark = theme === "dark";

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
    ...shellThemeVars(mode, theme),
  };

  return (
    <div className="lf-shell" data-screen-label="Workspace Shell — Cockpit" style={root}>
      <ShellStyles />

      {/* a single soft edge vignette for depth — DARK only; on light/warm it would
          muddy the paper, so those stay clean. (The old HUD grid/scanlines/rulers/
          corner-brackets were removed — they added noise without meaning.) */}
      {isDark && <div style={ambient({ background: "radial-gradient(130% 120% at 50% 50%,transparent 66%,rgba(0,0,0,.42))", zIndex: 1 })} />}

      {/* top bar */}
      <TopBar formatBadge={MODE_FORMATS[mode]} layout={layout} countdown={countdown} onCommandPalette={props.onCommandPalette} onToggleFocus={props.onToggleFocus} />

      {/* body row */}
      <div style={{ position: "relative", zIndex: 20, display: "flex", flex: 1, minHeight: 0 }}>
        {showDocks && (props.navSlot ?? <Navigator projectTitle={projectTitle} modeName={MODE_NAMES[mode]} spineLabel={MODE_SPINES[mode]} />)}
        {/* center column: editor + PSYKE console */}
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
          <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
            {props.centerSlot ?? <ManuscriptRegion />}
          </div>
          {(props.showConsole ?? true) && <PsykeConsole />}
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
