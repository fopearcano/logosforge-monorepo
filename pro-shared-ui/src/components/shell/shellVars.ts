/**
 * Studio shell Skins + per-mode vocabulary. Forge preserves the original design
 * handoff; Paper and Lamplit swap semantic visual tokens without changing
 * workspace structure or the writingMode → --accent contract.
 */
import type { CSSProperties } from "react";
import { WRITING_MODES, type WritingMode } from "@logosforge/ui-contracts";
import { accentForMode } from "../../theme/accent";

export type ShellLayout = "cockpit" | "focus";
/** Stable, user-facing workspace skins. */
export const SKIN_IDS = ["forge", "paper", "lamplit"] as const;
export type SkinId = (typeof SKIN_IDS)[number];

export interface SkinOption {
  id: SkinId;
  label: string;
  description: string;
}

export const SKIN_OPTIONS: readonly SkinOption[] = [
  { id: "forge", label: "Forge", description: "The original cinematic LogosForge cockpit." },
  { id: "paper", label: "Paper", description: "A quiet, neutral writing room inspired by Whiteboard." },
  { id: "lamplit", label: "Lamplit", description: "A warm, dark study with amber surfaces." },
] as const;

/** @deprecated Legacy persisted values accepted during the Skins migration. */
export type AppearanceTheme = "dark" | "light" | "warm";
/** @deprecated kept for source compatibility with early shell consumers. */
export type CinematicLevel = AppearanceTheme;

const LEGACY_SKIN_MAP: Record<AppearanceTheme, SkinId> = {
  dark: "forge",
  light: "paper",
  warm: "lamplit",
};

/** Resolve current ids and legacy appearance values without throwing. */
export function resolveSkin(value: unknown): SkinId {
  if (typeof value !== "string") return "forge";
  if ((SKIN_IDS as readonly string[]).includes(value)) return value as SkinId;
  return LEGACY_SKIN_MAP[value as AppearanceTheme] ?? "forge";
}

/**
 * Per-skin surface, typography, shape, and effect tokens. Accents, severity and
 * entity colours remain writing-mode driven and therefore stable across skins.
 */
const SKIN_SURFACES: Record<SkinId, Record<string, string>> = {
  forge: {
    "--void": "#000000", "--base": "#04060a", "--panel": "#080a0f", "--panel2": "#0b0e15", "--raised": "#11151e",
    "--tint": "rgba(11,14,21,.5)", "--tint2": "rgba(255,255,255,.04)",
    "--txt": "#e4e8ef", "--txt2": "#8b95a5", "--txt3": "#525c6b", "--strong": "#ffffff",
    "--line": "rgba(232,68,58,.28)", "--line2": "rgba(150,162,180,.10)", "--line-cy": "rgba(76,194,255,.30)",
    "--on-accent": "#04060a", "--page-shadow": "0 16px 60px rgba(0,0,0,.6)",
    "--ui-font": "'JetBrains Mono','SFMono-Regular',monospace", "--display-font": "'Chakra Petch',sans-serif",
    "--ui-tracking": ".02em", "--brand-tracking": ".16em", "--control-radius": "2px", "--panel-radius": "0px",
    "--chrome-shadow": "0 12px 36px rgba(0,0,0,.48)", "--signal-glow": "0 0 8px currentColor",
  },
  paper: {
    "--void": "#e7e6e1", "--base": "#f2f2f0", "--panel": "#f8f8f6", "--panel2": "#ffffff", "--raised": "#ffffff",
    "--tint": "rgba(43,42,46,.035)", "--tint2": "rgba(43,42,46,.055)",
    "--txt": "#36353a", "--txt2": "#706e69", "--txt3": "#99968e", "--strong": "#242328",
    "--line": "rgba(176,101,63,.25)", "--line2": "rgba(54,53,58,.12)", "--line-cy": "rgba(81,129,168,.34)",
    "--on-accent": "#ffffff", "--page-shadow": "0 24px 60px -30px rgba(40,38,34,.30)",
    "--ui-font": "system-ui,-apple-system,'Segoe UI',sans-serif", "--display-font": "Georgia,'Times New Roman',serif",
    "--ui-tracking": "0", "--brand-tracking": ".08em", "--control-radius": "6px", "--panel-radius": "8px",
    "--chrome-shadow": "0 12px 34px rgba(40,38,34,.16)", "--signal-glow": "none",
    // Contrast-safe signal variants for a light surface. Their semantics stay
    // identical to Forge; only luminance changes.
    "--crimson": "#b44339", "--crimson-d": "#7c211c", "--amber": "#8a5f18", "--amber-b": "#8a5f18",
    "--cyan": "#276f9d", "--green": "#28734c", "--violet": "#7046a3", "--pink": "#9b3c72",
    "--blocking": "#b72f3c", "--warning": "#8a5f18", "--suggestion": "#276f9d", "--opportunity": "#28734c", "--info": "#59636f",
    "--c-char": "#276f9d", "--c-place": "#8a5f18", "--c-obj": "#7046a3", "--c-lore": "#28734c", "--c-theme": "#9b3c72",
  },
  // Lamplit study: dark aged wood, warm cream ink, and amber hairlines.
  lamplit: {
    "--void": "#140f08", "--base": "#1d1610", "--panel": "#241b12", "--panel2": "#2b2016", "--raised": "#362819",
    "--tint": "rgba(247,224,168,.06)", "--tint2": "rgba(247,224,168,.035)",
    "--txt": "#f0e3c8", "--txt2": "#c8b087", "--txt3": "#9c8760", "--strong": "#fdf4dc",
    "--line": "rgba(201,150,80,.30)", "--line2": "rgba(240,226,198,.11)", "--line-cy": "rgba(120,160,205,.32)",
    "--on-accent": "#1d1610", "--page-shadow": "0 16px 50px rgba(0,0,0,.5)",
    "--ui-font": "'JetBrains Mono','SFMono-Regular',monospace", "--display-font": "'Chakra Petch',sans-serif",
    "--ui-tracking": ".02em", "--brand-tracking": ".14em", "--control-radius": "3px", "--panel-radius": "2px",
    "--chrome-shadow": "0 12px 36px rgba(0,0,0,.44)", "--signal-glow": "0 0 7px currentColor",
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
// Default signal / severity / entity colours. Paper replaces these with darker
// contrast-safe variants while keeping their semantic roles stable.
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

const PAPER_MODE_ACCENTS: Record<WritingMode, string> = {
  novel: "#80632d",
  screenplay: "#276f9d",
  graphic_novel: "#9b3c72",
  stage_script: "#8a5f18",
  series: "#28734c",
};

/** The full outer-shell scope: selected skin + signals + writing-mode accent. */
export function shellSkinVars(mode: WritingMode, skin: SkinId | AppearanceTheme = "forge"): CSSProperties {
  const resolved = resolveSkin(skin);
  const accent = resolved === "paper" ? PAPER_MODE_ACCENTS[mode] : accentForMode(mode);
  return {
    ...SIGNAL_VARS,
    ...SKIN_SURFACES[resolved],
    "--accent": accent,
    "--accent-soft": accent + "22",
  } as CSSProperties;
}

/** @deprecated Use shellSkinVars. Accepts old values for source compatibility. */
export function shellThemeVars(mode: WritingMode, theme: AppearanceTheme = "dark"): CSSProperties {
  return shellSkinVars(mode, theme);
}

/** The scope for a docked/standalone panel: signals + accent only. Surfaces come
 * from the skin-aware outer shell / :root, so panels never pin themselves to a
 * particular skin. */
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
