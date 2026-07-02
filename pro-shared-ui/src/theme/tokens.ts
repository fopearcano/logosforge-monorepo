/**
 * Studio design tokens — dark-first, cinematic, "minimal-cyber / terminal".
 * Distinct from the Whiteboard (Free) identity. These are starting values for
 * Claude Design to refine; the design owns the final palette. Severity and
 * confidence grammar is shared across HUD surfaces (Decision Radar, Continuity,
 * Knowledge Graph). Per-mode bands re-skin the workspace by writing mode.
 */
export const tokens = {
  color: {
    bg: {
      base: "#0b0e14",
      panel: "#11151d",
      raised: "#161b25",
      overlay: "rgba(6, 8, 12, 0.72)",
      grid: "#1c2430",
    },
    text: {
      primary: "#e6edf3",
      secondary: "#9aa7b6",
      muted: "#5c6b7a",
      inverse: "#0b0e14",
    },
    accent: {
      primary: "#4cc2ff", // cyan signal
      focus: "#7aa2ff",
      cinematic: "#b07cff", // for quantum / graph dramatic surfaces
    },
    /** Decision Radar / issue severity grammar (highest → lowest). */
    severity: {
      blocking: "#ff5c6c",
      warning: "#ffb454",
      suggestion: "#4cc2ff",
      opportunity: "#62d99a",
      info: "#7a8694",
    },
    /** Confidence ranking for derived facts (Knowledge Graph, Continuity). */
    confidence: {
      high: "#62d99a",
      medium: "#ffb454",
      low: "#7a8694",
    },
    /** Per-writing-mode accent bands (workspace re-skin). */
    mode: {
      novel: "#c8a96a",
      screenplay: "#4cc2ff",
      graphic_novel: "#ff7ac6",
      stage_script: "#ffb454",
      series: "#62d99a",
    },
  },
  space: { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 },
  radius: { sm: 4, md: 8, lg: 12, pill: 999 },
  font: {
    ui: "'Inter', system-ui, sans-serif",
    mono: "'JetBrains Mono', ui-monospace, monospace",
    prose: "'Iowan Old Style', Georgia, serif",
    sizePx: { xs: 11, sm: 12, md: 13, lg: 15, xl: 18, display: 24 },
  },
  z: { base: 0, dock: 10, overlay: 100, palette: 200, modal: 300, toast: 400 },
} as const;

export type Tokens = typeof tokens;
