/**
 * Five Whiteboard palettes (RESTYLE v3):
 *   Manuscript (light, default) · Forge (ember-red) · Deepdark (Luxcium) ·
 *   Violet (Tokyo-Night) · Blueprint (cyanotype).
 *
 * Array order === ThemeSelector .theme-grid order === cycle order; Manuscript
 * is first/default. Mixed themes keep UI text and editor ink separate so both
 * stay readable.
 */

import { customToTheme, type CustomThemeFields, type WhiteboardTheme } from './themeTokens';

export const MANUSCRIPT: WhiteboardTheme = {
  id: 'manuscript',
  name: 'Manuscript',
  mode: 'light',
  appBg: '#f2f2f0',
  panelBg: '#f8f8f6',
  editorBg: '#ffffff',
  text: '#36353a',
  mutedText: '#9b988f',
  editorText: '#2b2a2e',
  editorMuted: '#a3a098',
  border: '#e6e5e0',
  accent: '#b0653f',
  accentSoft: 'rgba(176,101,63,0.13)',
  selectionBg: 'rgba(176,101,63,0.16)',
  editorSelection: 'rgba(176,101,63,0.14)',
  caret: '#b0653f',
  shadow: '0 30px 70px -30px rgba(40,38,34,0.30)',
};

export const CHROMA: WhiteboardTheme = {
  id: 'chroma',
  name: 'Chroma',
  mode: 'light',
  appBg: '#eef0f3',
  panelBg: '#f7f8fa',
  editorBg: '#ffffff',
  text: '#2a2d34',
  mutedText: '#868c99',
  editorText: '#1f2329',
  editorMuted: '#9aa0ad',
  border: '#e3e6ea',
  accent: '#1d4ed8',
  accentSoft: 'rgba(29,78,216,0.12)',
  selectionBg: 'rgba(29,78,216,0.14)',
  editorSelection: 'rgba(29,78,216,0.12)',
  caret: '#1d4ed8',
  shadow: '0 30px 70px -30px rgba(30,40,70,0.28)',
};

export const FORGE: WhiteboardTheme = {
  id: 'forge',
  name: 'Forge',
  mode: 'dark',
  appBg: '#15100f',
  panelBg: '#1c1614',
  editorBg: '#181110',
  text: '#cfc7c2',
  mutedText: '#7d726b',
  editorText: '#ddd4cd',
  editorMuted: '#766960',
  border: '#2f2421',
  accent: '#e44a35',
  accentSoft: 'rgba(228,74,53,0.16)',
  selectionBg: 'rgba(228,74,53,0.18)',
  editorSelection: 'rgba(228,74,53,0.16)',
  caret: '#e44a35',
  shadow: '0 30px 70px -26px rgba(0,0,0,0.72)',
};

export const DEEPDARK: WhiteboardTheme = {
  id: 'deepdark',
  name: 'Deepdark',
  mode: 'dark',
  appBg: '#0c0c0c',
  panelBg: '#0a0a0a',
  editorBg: '#060606',
  text: '#e4e4e4',
  mutedText: '#707070',
  editorText: '#f2f2f2',
  editorMuted: '#6a6a6a',
  border: '#222222',
  accent: '#e8913a',
  accentSoft: 'rgba(232,145,58,0.16)',
  selectionBg: 'rgba(232,145,58,0.18)',
  editorSelection: 'rgba(255,255,255,0.06)',
  caret: '#e8913a',
  shadow: '0 30px 70px -22px rgba(0,0,0,0.92)',
};

export const VIOLET: WhiteboardTheme = {
  id: 'violet',
  name: 'Violet',
  mode: 'dark',
  // Darker + more violet than Tokyo-Night navy, for higher contrast: the page is
  // a deep purple-black instead of blue-grey, so the lavender ink and the syntax
  // colour-coding pop harder.
  appBg: '#0f0a18',
  panelBg: '#140d1f',
  editorBg: '#18112c',
  text: '#c4b8e8',
  mutedText: '#6f5f96',
  editorText: '#d6cdf2',
  editorMuted: '#6f5f96',
  border: '#2c2146',
  accent: '#c4a7ff',
  accentSoft: 'rgba(196,167,255,0.18)',
  selectionBg: 'rgba(196,167,255,0.22)',
  editorSelection: 'rgba(150,120,240,0.14)',
  caret: '#c4a7ff',
  shadow: '0 30px 70px -22px rgba(16,6,34,0.92)',
};

export const BLUEPRINT: WhiteboardTheme = {
  id: 'blueprint',
  name: 'Blueprint',
  mode: 'dark',
  appBg: '#0f2a63',
  panelBg: '#143474',
  editorBg: '#1a4194',
  text: '#dbe6ff',
  mutedText: '#8aa0d8',
  editorText: '#ffffff',
  editorMuted: '#9fb4e6',
  border: '#345aa6',
  accent: '#7fb1ff',
  accentSoft: 'rgba(127,177,255,0.20)',
  selectionBg: 'rgba(127,177,255,0.22)',
  editorSelection: 'rgba(127,177,255,0.16)',
  caret: '#7fb1ff',
  shadow: '0 30px 70px -24px rgba(8,20,60,0.80)',
};

export const PREDEFINED_THEMES: WhiteboardTheme[] = [
  MANUSCRIPT,
  CHROMA,
  FORGE,
  DEEPDARK,
  VIOLET,
  BLUEPRINT,
];

export const DEFAULT_THEME_ID = MANUSCRIPT.id;

export function getPredefinedTheme(id: string): WhiteboardTheme | undefined {
  return PREDEFINED_THEMES.find((t) => t.id === id);
}

/** Resolve a theme id (+ custom fields) into a full theme. */
export function resolveTheme(themeId: string, customFields: CustomThemeFields): WhiteboardTheme {
  if (themeId === 'custom') return customToTheme(customFields);
  return getPredefinedTheme(themeId) ?? PREDEFINED_THEMES[0];
}

/** Starting point for the Custom theme (a clean warm-paper look). */
export const DEFAULT_CUSTOM_FIELDS: CustomThemeFields = {
  appBg: '#1b2330',
  editorBg: '#fbf7ee',
  text: '#dde4ee',
  mutedText: '#8b94a6',
  accent: '#3b6fd4',
  border: '#2c3647',
};
