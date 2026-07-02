/**
 * writingMode → --accent — the generalized accent pattern for all of Studio.
 *
 * The shell (or the StudioProvider) scopes a single CSS custom property,
 * `--accent`, to the active writing mode. Every panel reads `var(--accent)`
 * (via `accent()`) instead of hardcoding an accent color, so re-skinning the
 * workspace by writing mode is one variable, set in one place.
 */
import type { CSSProperties } from "react";
import type { WritingMode } from "@logosforge/ui-contracts";
import { tokens } from "./tokens";

/** The one custom property every Studio surface reads for its accent. */
export const ACCENT_VAR = "--accent";

const MODE_ACCENTS = tokens.color.mode;

/** The accent color for a writing mode (falls back to the cyan signal). */
export function accentForMode(mode?: WritingMode | string | null): string {
  if (mode && mode in MODE_ACCENTS) return MODE_ACCENTS[mode as WritingMode];
  return tokens.color.accent.primary;
}

/**
 * Style object that scopes `--accent` to a writing mode. Spread onto a container
 * (the shell, the provider, a single docked panel); descendants inherit it.
 */
export function accentVars(mode?: WritingMode | string | null): CSSProperties {
  return { [ACCENT_VAR]: accentForMode(mode) } as CSSProperties;
}

/**
 * Reference the scoped accent in any style, with a token fallback for when a
 * panel is rendered outside an accent scope. Use this everywhere instead of a
 * literal color: `borderColor: accent()`.
 */
export function accent(fallback: string = tokens.color.accent.primary): string {
  return `var(${ACCENT_VAR}, ${fallback})`;
}
