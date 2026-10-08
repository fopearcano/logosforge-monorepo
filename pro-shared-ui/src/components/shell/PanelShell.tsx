import type { CSSProperties, ReactNode } from "react";
import type { WritingMode } from "@logosforge/ui-contracts";
import { useWritingMode } from "../../adapters/StudioProvider";
import { ShellStyles } from "./ShellStyles";
import { resolveMode, shellSkinVars } from "./shellVars";
import { useSkin } from "./SkinContext";

/** Props every standalone Studio panel accepts. */
export interface PanelProps {
  /** Active writing mode → --accent. Falls back to <StudioProvider>, then screenplay. */
  writingMode?: WritingMode | string;
  /** Extra style for the panel scope (e.g. an explicit height when standalone). */
  style?: CSSProperties;
}

/**
 * Wraps a standalone panel in the active Skin scope, including the
 * writingMode → --accent contract, so panels render consistently on their own,
 * docked in the shell, and through portals.
 */
export function PanelShell({ writingMode, style, children }: PanelProps & { children: ReactNode }) {
  const ctx = useWritingMode();
  const mode = resolveMode(writingMode ?? ctx);
  const skin = useSkin();
  return (
    <div
      className="lf-shell"
      data-skin={skin}
      style={{ fontFamily: "var(--ui-font,'JetBrains Mono',monospace)", color: "var(--txt)", height: "100%", ...shellSkinVars(mode, skin), ...style }}
    >
      <ShellStyles />
      {children}
    </div>
  );
}

/** Forge ornament. Paper suppresses it through the shared skin stylesheet. */
export function Corners({ br = false }: { br?: boolean }) {
  return (
    <>
      <div className="lf-panel-corner lf-panel-corner-tl" style={{ position: "absolute", top: -1, left: -1, width: 14, height: 14, borderTop: "1px solid var(--crimson)", borderLeft: "1px solid var(--crimson)" }} />
      <div className="lf-panel-corner lf-panel-corner-signal" style={{ position: "absolute", top: 3, left: 3, width: 5, height: 5, background: "var(--crimson)", boxShadow: "0 0 6px var(--crimson)" }} />
      {br && <div className="lf-panel-corner lf-panel-corner-br" style={{ position: "absolute", bottom: -1, right: -1, width: 14, height: 14, borderBottom: "1px solid var(--crimson)", borderRight: "1px solid var(--crimson)" }} />}
    </>
  );
}
