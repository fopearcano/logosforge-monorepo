/**
 * Nerd Mode editor tools — shared types + defaults.
 *
 * These are OPTIONAL editor aids (line numbers, folding, syntax highlighting,
 * typography overrides). Every default is off / "use the mode default", so the
 * Whiteboard stays clean and minimal until a writer opts in. Persisted in
 * localStorage (see useEditorTools) — independent of the backend document and of
 * the screenplay Document Settings.
 */

import {
  INSTALLED_FONT_FAMILY_MAX_LENGTH,
  normalizeInstalledFontFamily,
} from './installedFonts';

/** General editor typeface override ('default' = keep the per-mode typeface). */
export const EDITOR_TYPEFACES = [
  'default',
  'serif',
  'book',
  'classic',
  'transitional',
  'editorial',
  'slab',
  'sans',
  'system',
  'humanist',
  'geometric',
  'rounded',
  'mono',
  'coding',
  'courier-prime',
  'typewriter',
  'typewriter-modern',
  'handwritten',
  'handwritten-casual',
  'script',
  'chalkboard',
  'marker',
  'installed',
] as const;

export type EditorTypeface = (typeof EDITOR_TYPEFACES)[number];

/** How the manuscript is laid out: one continuous column, or framed as pages. */
export type EditorLayout = 'flow' | 'paged';

export interface EditorToolsState {
  lineNumbers: boolean;
  currentLineHighlight: boolean;
  folding: boolean;
  syntax: boolean;
  /** Font-size override in px (null = per-mode default). */
  fontSize: number | null;
  /** Line-height override, unitless (null = per-mode default). */
  lineHeight: number | null;
  /** General typeface override across all modes. */
  typeface: EditorTypeface;
  /** One locally installed OS font family. Used only when typeface=installed. */
  systemFontFamily: string | null;
  /** Optional manuscript ink override (#rrggbb); null follows the active theme. */
  textColor: string | null;
  /** 'flow' = continuous scroll (default); 'paged' = a page sheet with page breaks. */
  layout: EditorLayout;
}

export const DEFAULT_EDITOR_TOOLS: EditorToolsState = {
  lineNumbers: false,
  currentLineHighlight: false,
  folding: false,
  // Colour-coding ON by default (writers get visible structure: headings,
  // dialogue, tags). Toggle off in Editor → "Colour-code text" for plain B&W.
  syntax: true,
  fontSize: null,
  lineHeight: null,
  typeface: 'default',
  systemFontFamily: null,
  textColor: null,
  layout: 'flow',
};

/** Bounds for the typography overrides (kept reasonable for writing). */
export const FONT_SIZE_MIN = 12;
export const FONT_SIZE_MAX = 28;
export const LINE_HEIGHT_MIN = 1.2;
export const LINE_HEIGHT_MAX = 2.4;

export const SYSTEM_FONT_FAMILY_MAX_LENGTH = INSTALLED_FONT_FAMILY_MAX_LENGTH;

/**
 * Accept one font-family name, never a CSS expression or fallback list. The
 * renderer quotes the result before putting it in an inline custom property.
 */
export function normalizeSystemFontFamily(value: unknown): string | null {
  return normalizeInstalledFontFamily(value);
}
