import type { CSSProperties, ReactNode } from "react";
import type { WritingMode } from "@logosforge/ui-contracts";
import { useWritingMode } from "../../adapters/StudioProvider";
import { ShellStyles } from "./ShellStyles";
import { panelScopeVars, resolveMode } from "./shellVars";

/** Props every standalone Studio panel accepts. */
export interface PanelProps {
  /** Active writing mode → --accent. Falls back to <StudioProvider>, then screenplay. */
  writingMode?: WritingMode | string;
  /** Extra style for the panel scope (e.g. an explicit height when standalone). */
  style?: CSSProperties;
}

/**
 * Wraps a standalone panel in the shell theme scope: sets the full CSS-var
 * palette (incl. writingMode → --accent) and renders the shared keyframes/global
 * styles, so panels render correctly on their own AND when docked into the shell.
 */
export function PanelShell({ writingMode, style, children }: PanelProps & { children: ReactNode }) {
  const ctx = useWritingMode();
  const mode = resolveMode(writingMode ?? ctx);
  return (
    <div
      className="lf-shell"
      style={{ fontFamily: "'JetBrains Mono',monospace", color: "var(--txt)", height: "100%", ...panelScopeVars(mode), ...style }}
    >
      <ShellStyles />
      {children}
    </div>
  );
}

/** The crimson corner brackets every panel frame carries (top-left always; add `br` for bottom-right). */
export function Corners({ br = false }: { br?: boolean }) {
  return (
    <>
      <div style={{ position: "absolute", top: -1, left: -1, width: 14, height: 14, borderTop: "1px solid var(--crimson)", borderLeft: "1px solid var(--crimson)" }} />
      <div style={{ position: "absolute", top: 3, left: 3, width: 5, height: 5, background: "var(--crimson)", boxShadow: "0 0 6px var(--crimson)" }} />
      {br && <div style={{ position: "absolute", bottom: -1, right: -1, width: 14, height: 14, borderBottom: "1px solid var(--crimson)", borderRight: "1px solid var(--crimson)" }} />}
    </>
  );
}
