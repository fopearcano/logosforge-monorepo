/**
 * Whiteboard theme tokens + application (RESTYLE v3).
 *
 * The whole UI reads CSS variables (`--bg`, `--panel`, `--paper`, `--ink`,
 * `--text`, `--accent`, …), so applying a theme = setting those variables on
 * <html>. `applyThemeVars` is the SINGLE writer of theme vars; it also computes
 * a few derived helpers (`--hover`, `--on-accent`, `--border-soft`, `--panel-2`,
 * `--error`, `--ok`) so app.css never has to branch light-vs-dark itself.
 *
 * Two text colours matter: UI text (`text`, on chrome) and editor ink
 * (`editorText`, on the writing sheet) — they differ in mixed themes.
 */

export type ThemeMode = 'light' | 'dark';

export interface WhiteboardTheme {
  id: string;
  name: string;
  /** Chrome luminance (panels/app) — drives hover/error/ok shades. */
  mode: ThemeMode;
  appBg: string; // → --bg
  panelBg: string; // → --panel
  editorBg: string; // → --paper (the writing sheet)
  text: string; // → --text (UI ink on chrome)
  mutedText: string; // → --muted
  editorText: string; // → --ink (page ink on the sheet)
  editorMuted: string; // → --paper-muted
  border: string;
  accent: string;
  accentSoft: string;
  selectionBg: string; // UI selection
  editorSelection: string; // editor text selection
  caret: string;
  shadow: string;
}

/** The minimal user-editable Custom theme fields (editor ink/muted are derived). */
export interface CustomThemeFields {
  appBg: string;
  editorBg: string;
  text: string;
  mutedText: string;
  accent: string;
  border: string;
}

// -- colour helpers ----------------------------------------------------------

function hexToRgb(hex: string): [number, number, number] {
  let h = hex.replace('#', '').trim();
  if (h.length === 3)
    h = h
      .split('')
      .map((c) => c + c)
      .join('');
  const n = parseInt(h.slice(0, 6), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function toHex(r: number, g: number, b: number): string {
  const c = (n: number) => Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, '0');
  return `#${c(r)}${c(g)}${c(b)}`;
}

/** Linear blend toward `b` by weight `t` (hex in, hex out). */
function mix(a: string, b: string, t: number): string {
  const [ar, ag, ab] = hexToRgb(a);
  const [br, bg, bb] = hexToRgb(b);
  return toHex(ar + (br - ar) * t, ag + (bg - ag) * t, ab + (bb - ab) * t);
}

/** WCAG relative luminance (0–1). */
function luminance(hex: string): number {
  const [r, g, b] = hexToRgb(hex).map((v) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** `rgba(...)` string from a hex colour + alpha (for selection/soft tints). */
export function rgba(hex: string, alpha: number): string {
  const [r, g, b] = hexToRgb(hex);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/** Is a hex colour dark (low relative luminance)? */
export function isDark(hex: string): boolean {
  return luminance(hex) < 0.5;
}

/**
 * Text-on-accent: design-chosen ink for text sitting on the accent fill, kept
 * out of the 17-field theme type so the contract is unchanged. Unknown ids fall
 * back to a luminance pick.
 */
const ON_ACCENT: Record<string, string> = {
  manuscript: '#ffffff',
  forge: '#1f0a06',
  deepdark: '#160d03',
  violet: '#160a2e',
  blueprint: '#0c2350',
};

function onAccentFor(theme: WhiteboardTheme): string {
  return ON_ACCENT[theme.id] ?? (luminance(theme.accent) > 0.42 ? '#13110e' : '#ffffff');
}

// -- application -------------------------------------------------------------

/**
 * Apply a theme by setting CSS variables on <html>. The single writer of theme
 * vars; also publishes derived helpers + `--lf-*` back-compat aliases.
 */
export function applyThemeVars(
  theme: WhiteboardTheme,
  root: HTMLElement = document.documentElement,
): void {
  const dark = theme.mode === 'dark';
  const set = (k: string, v: string) => root.style.setProperty(k, v);

  // — core contract —
  set('--bg', theme.appBg);
  set('--panel', theme.panelBg);
  set('--paper', theme.editorBg);
  set('--text', theme.text);
  set('--muted', theme.mutedText);
  set('--ink', theme.editorText);
  set('--paper-muted', theme.editorMuted);
  set('--border', theme.border);
  set('--accent', theme.accent);
  set('--accent-soft', theme.accentSoft);
  set('--selection', theme.selectionBg);
  set('--paper-selection', theme.editorSelection);
  set('--caret', theme.caret);
  set('--page-shadow', theme.shadow);

  // — derived helpers (computed where light/dark matters) —
  set('--hover', dark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.04)');
  set('--on-accent', onAccentFor(theme));
  set('--border-soft', mix(theme.border, theme.panelBg, 0.5));
  set('--panel-2', dark ? mix(theme.panelBg, theme.editorText, 0.07) : mix(theme.panelBg, '#ffffff', 0.6));
  set('--error', dark ? '#df5b4f' : '#c0473b');
  set('--ok', dark ? '#54b585' : '#3f8f63');

  // — back-compat aliases (kept so older --lf-* consumers don't break) —
  set('--lf-bg', theme.appBg);
  set('--lf-panel', theme.panelBg);
  set('--lf-paper', theme.editorBg);
  set('--lf-text', theme.text);
  set('--lf-muted', theme.mutedText);
  set('--lf-accent', theme.accent);
  set('--lf-border', theme.border);

  root.setAttribute('data-theme', theme.mode);
  root.setAttribute('data-theme-id', theme.id);
}

/**
 * Expand the 6 Custom fields into a full theme. Editor ink/muted are derived
 * from the editor background's luminance so the page stays readable regardless
 * of the chosen UI text colour.
 */
export function customToTheme(c: CustomThemeFields): WhiteboardTheme {
  const dark = luminance(c.editorBg) < 0.5;
  const editorText = dark ? mix(c.editorBg, '#ffffff', 0.86) : mix(c.editorBg, '#000000', 0.82);
  const editorMuted = dark ? mix(c.editorBg, '#ffffff', 0.42) : mix(c.editorBg, '#000000', 0.4);
  const mode: ThemeMode = luminance(c.appBg) < 0.5 ? 'dark' : 'light';
  return {
    id: 'custom',
    name: 'Custom',
    mode,
    appBg: c.appBg,
    panelBg: mode === 'dark' ? mix(c.appBg, '#ffffff', 0.05) : mix(c.appBg, '#ffffff', 0.45),
    editorBg: c.editorBg,
    text: c.text,
    mutedText: c.mutedText,
    editorText,
    editorMuted,
    border: c.border,
    accent: c.accent,
    accentSoft: rgba(c.accent, 0.16),
    selectionBg: rgba(c.accent, 0.18),
    editorSelection: rgba(c.accent, dark ? 0.18 : 0.14),
    caret: c.accent,
    shadow: dark ? '0 30px 70px -24px rgba(0,0,0,0.8)' : '0 30px 70px -30px rgba(40,38,34,0.3)',
  };
}
