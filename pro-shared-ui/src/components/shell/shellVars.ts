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
export type CinematicLevel = "restrained" | "cinematic" | "full_hud";

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
export function shellThemeVars(mode: WritingMode): CSSProperties {
  const accent = accentForMode(mode);
  const vars: Record<string, string> = {
    "--void": "#000000",
    "--base": "#04060a",
    "--panel": "#080a0f",
    "--panel2": "#0b0e15",
    "--raised": "#11151e",
    "--line": "rgba(232,68,58,.28)",
    "--line2": "rgba(150,162,180,.10)",
    "--line-cy": "rgba(76,194,255,.30)",
    "--crimson": "#e8443a",
    "--crimson-d": "#7c211c",
    "--amber": "#f5b133",
    "--amber-b": "#ffcf4a",
    "--cyan": "#4cc2ff",
    "--green": "#62d99a",
    "--violet": "#b07cff",
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
    "--txt": "#e4e8ef",
    "--txt2": "#8b95a5",
    "--txt3": "#525c6b",
    "--accent": accent,
    "--accent-soft": accent + "22",
  };
  return vars as CSSProperties;
}

/** Coerce an arbitrary writing-mode string to a known mode (default screenplay). */
export function resolveMode(m: WritingMode | string | undefined): WritingMode {
  return (WRITING_MODES as readonly string[]).includes(m ?? "") ? (m as WritingMode) : "screenplay";
}
