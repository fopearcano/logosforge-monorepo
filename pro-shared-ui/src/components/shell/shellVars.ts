/**
 * Studio shell palette + per-mode vocabulary — ported verbatim from the Claude
 * Design handoff (`Workspace Shell.dc.html`, the `renderVals()` block). The
 * per-mode accent map is identical to `theme/tokens.color.mode`, so the shell's
 * writingMode → --accent mechanism is exactly our scaffold convention.
 */
import type { CSSProperties } from "react";
import { WRITING_MODES, type WritingMode } from "@logosforge/ui-contracts";
import { accentForMode } from "../../theme/accent";

export type ShellLayout = "cockpit" | "focus";
/** Visual theme (replaces the old HUD-intensity levels). */
export type AppearanceTheme = "dark" | "light" | "warm";
/** @deprecated kept for prop compatibility; the app now passes an AppearanceTheme. */
export type CinematicLevel = AppearanceTheme;

/**
 * Per-theme SURFACE + text + line palette. Accents, severity and entity colours
 * are theme-independent (they read on any surface) and live in shellThemeVars.
 *   - dark  → the original cinematic near-black surface
 *   - light → clean cool light
 *   - warm  → cream / paper (ref: manuscript-syntax-cheatsheet.html light palette)
 */
const THEME_SURFACES: Record<AppearanceTheme, Record<string, string>> = {
  dark: {
    "--void": "#000000", "--base": "#04060a", "--panel": "#080a0f", "--panel2": "#0b0e15", "--raised": "#11151e",
    "--tint": "rgba(11,14,21,.5)", "--tint2": "rgba(255,255,255,.04)",
    "--txt": "#e4e8ef", "--txt2": "#8b95a5", "--txt3": "#525c6b", "--strong": "#ffffff",
    "--line": "rgba(232,68,58,.28)", "--line2": "rgba(150,162,180,.10)", "--line-cy": "rgba(76,194,255,.30)",
    "--on-accent": "#04060a", "--page-shadow": "0 16px 60px rgba(0,0,0,.6)",
  },
  light: {
    "--void": "#dce1e8", "--base": "#eaeef3", "--panel": "#f7f9fc", "--panel2": "#eef2f7", "--raised": "#ffffff",
    "--tint": "rgba(30,42,60,.05)", "--tint2": "rgba(30,42,60,.03)",
    "--txt": "#1a222c", "--txt2": "#54606f", "--txt3": "#8b97a6", "--strong": "#0d141c",
    "--line": "rgba(30,42,60,.16)", "--line2": "rgba(30,42,60,.09)", "--line-cy": "rgba(40,120,190,.35)",
    "--on-accent": "#0a0f16", "--page-shadow": "0 10px 30px -14px rgba(30,42,60,.35)",
  },
  // warm = "lamplit study": DARK aged wood — deep walnut surfaces, warm cream
  // ink, amber hairlines. A cosy dark theme (not a paper theme): dark enough that
  // the rail's cream text reads with high contrast, warm enough to feel like
  // lamplight on old wood rather than the cool near-black Dark theme.
  warm: {
    "--void": "#140f08", "--base": "#1d1610", "--panel": "#241b12", "--panel2": "#2b2016", "--raised": "#362819",
    "--tint": "rgba(247,224,168,.06)", "--tint2": "rgba(247,224,168,.035)",
    "--txt": "#f0e3c8", "--txt2": "#c8b087", "--txt3": "#9c8760", "--strong": "#fdf4dc",
    "--line": "rgba(201,150,80,.30)", "--line2": "rgba(240,226,198,.11)", "--line-cy": "rgba(120,160,205,.32)",
    "--on-accent": "#1d1610", "--page-shadow": "0 16px 50px rgba(0,0,0,.5)",
  },
};

export const MODE_NAMES: Record<WritingMode, string> = {
  novel: "NOVEL",
  screenplay: "SCREENPLAY",
  graphic_novel: "GRAPHIC NOVEL",
  stage_script: "STAGE SCRIPT",
  series: "SERIES",
};

export const MODE_SPINES: Record<WritingMode, string> = {
  novel: "ACT · CHAPTER · SCENE",
  screenplay: "ACT · SEQUENCE · SCENE · BEAT",
  graphic_novel: "ACT · PAGE · SCENE · PANEL",
  stage_script: "ACT · SCENE · BEAT",
  series: "SEASON · EPISODE · ACT · SCENE",
};

export const MODE_FORMATS: Record<WritingMode, string> = {
  novel: "NOVEL · PROSE",
  screenplay: "SCREENPLAY · FEATURE",
  graphic_novel: "GRAPHIC NOVEL · SCRIPT",
  stage_script: "STAGE · TWO-ACT",
  series: "SERIES · TELEPLAY",
};

/**
 * The full shell CSS-variable scope, with `--accent` (+ `--accent-soft`) derived
 * from the active writing mode. Spread onto the shell root; every descendant
 * reads `var(--accent)`, `var(--txt)`, the severity vars, etc.
 */
// Signal / severity / entity colours — theme-INDEPENDENT (saturated, read on any
// surface). Identical across themes so the design language is stable. Also
// includes --pink (used by a couple of panels).
const SIGNAL_VARS: Record<string, string> = {
  "--crimson": "#e8443a",
  "--crimson-d": "#7c211c",
  "--amber": "#f5b133",
  "--amber-b": "#ffcf4a",
  "--cyan": "#4cc2ff",
  "--green": "#62d99a",
  "--violet": "#b07cff",
  "--pink": "#ff7ac6",
  "--blocking": "#ff5260",
  "--warning": "#ffb454",
  "--suggestion": "#4cc2ff",
  "--opportunity": "#62d99a",
  "--info": "#7a8694",
  "--c-char": "#4cc2ff",
  "--c-place": "#f5b133",
  "--c-obj": "#b07cff",
  "--c-lore": "#62d99a",
  "--c-theme": "#ff7ac6",
};

/** The FULL scope for the outer shell root: theme surfaces + signals + accent. */
export function shellThemeVars(mode: WritingMode, theme: AppearanceTheme = "dark"): CSSProperties {
  const accent = accentForMode(mode);
  return {
    ...(THEME_SURFACES[theme] ?? THEME_SURFACES.dark),
    ...SIGNAL_VARS,
    "--accent": accent,
    "--accent-soft": accent + "22",
  } as CSSProperties;
}

/** The scope for a docked/standalone PANEL: ONLY signals + accent (NOT the theme
 * surfaces/text/lines). Surfaces come from the theme-aware outer shell / :root so
 * a panel never pins itself to one theme — the light/warm bug fix. */
export function panelScopeVars(mode: WritingMode): CSSProperties {
  const accent = accentForMode(mode);
  return {
    ...SIGNAL_VARS,
    "--accent": accent,
    "--accent-soft": accent + "22",
  } as CSSProperties;
}

/** Coerce an arbitrary writing-mode string to a known mode (default screenplay). */
export function resolveMode(m: WritingMode | string | undefined): WritingMode {
  return (WRITING_MODES as readonly string[]).includes(m ?? "") ? (m as WritingMode) : "screenplay";
}
