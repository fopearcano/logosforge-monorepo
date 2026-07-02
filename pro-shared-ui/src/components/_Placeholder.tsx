import type { ReactNode } from "react";
import { tokens } from "../theme/tokens";
import { accent } from "../theme/accent";

/**
 * Scaffold placeholder. Every Studio panel is stubbed with this until its design
 * is approved in Claude Design and recoded. Two scaffold-wide conventions live
 * here so every panel inherits them for free:
 *   - `data-screen-label` — the stable screen id, matching the Figma frame label,
 *     so design comments map to code.
 *   - the accent rail uses `accent()` (var(--accent)) — the writingMode → --accent
 *     pattern, never a hardcoded color.
 */
export function Placeholder({
  name,
  screenLabel,
  ticket,
  children,
}: {
  name: string;
  /** Stable screen id; mirrors the design's frame label for comment ↔ code mapping. */
  screenLabel: string;
  ticket?: string;
  children?: ReactNode;
}) {
  return (
    <div
      data-screen-label={screenLabel}
      style={{
        background: tokens.color.bg.panel,
        color: tokens.color.text.secondary,
        border: `1px solid ${tokens.color.bg.grid}`,
        borderLeft: `2px solid ${accent()}`,
        borderRadius: tokens.radius.md,
        padding: tokens.space.lg,
        fontFamily: tokens.font.ui,
        fontSize: tokens.font.sizePx.md,
      }}
    >
      <div style={{ color: tokens.color.text.primary, fontWeight: 600 }}>{name}</div>
      <div style={{ color: tokens.color.text.muted, fontSize: tokens.font.sizePx.xs, marginTop: tokens.space.xs }}>
        Studio panel — design in Claude Design{ticket ? ` (ticket ${ticket})` : ""}, then wire to the injected ApiClient.
      </div>
      {children}
    </div>
  );
}
