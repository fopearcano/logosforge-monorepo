/**
 * Maps the editor-tools state to the `data-*` attributes + CSS custom properties
 * applied on the writing surface. Keeping this here (pure) keeps WhiteboardPage
 * clean and the CSS gating in one obvious place.
 */

import type { EditorToolsState } from './editorToolTypes';
import { installedFontCssStack } from './installedFonts';

/** Offline-safe stacks. Bundled faces lead where available; platform faces add
 * several distinct book, handwriting and typewriter voices without networking. */
type PresetTypeface = Exclude<EditorToolsState['typeface'], 'default' | 'installed'>;

export const EDITOR_TYPEFACE_STACKS: Record<PresetTypeface, string> = {
  serif: "'Spectral', 'Iowan Old Style', Georgia, serif",
  book: "'Palatino Linotype', 'Book Antiqua', Palatino, 'URW Palladio L', serif",
  classic: "Georgia, 'Times New Roman', 'Liberation Serif', serif",
  transitional: "Charter, 'Bitstream Charter', Cambria, 'Noto Serif', serif",
  editorial: "Didot, 'Bodoni 72', Bodoni, 'Bodoni MT', 'Times New Roman', serif",
  slab: "Rockwell, 'Roboto Slab', 'DejaVu Serif', Georgia, serif",
  sans: "'IBM Plex Sans', system-ui, -apple-system, 'Segoe UI', sans-serif",
  system: "system-ui, -apple-system, 'Segoe UI', sans-serif",
  humanist: "Optima, Candara, 'Trebuchet MS', 'Segoe UI', sans-serif",
  geometric: "Futura, 'Avenir Next', Avenir, 'Century Gothic', Montserrat, sans-serif",
  rounded: "'Arial Rounded MT Bold', 'SF Pro Rounded', Quicksand, Nunito, system-ui, sans-serif",
  mono: "'IBM Plex Mono', ui-monospace, 'SF Mono', Menlo, Consolas, monospace",
  coding: "'Cascadia Code', 'JetBrains Mono', 'SFMono-Regular', Menlo, Consolas, monospace",
  'courier-prime': "'Courier Prime', 'Courier New', 'Liberation Mono', monospace",
  typewriter: "'American Typewriter', 'Lucida Console', Monaco, 'URW Typewriter L', 'DejaVu Sans Mono', monospace",
  'typewriter-modern': "'Special Elite', 'Courier New', 'Nimbus Mono PS', 'Liberation Mono', monospace",
  handwritten: "'Segoe Print', 'Bradley Hand', 'Comic Sans MS', 'Comic Sans', 'Comic Neue', Chilanka, cursive",
  'handwritten-casual': "'Bradley Hand', 'Segoe Print', 'Comic Sans MS', 'Comic Sans', Chilanka, cursive",
  script: "'Segoe Script', 'Snell Roundhand', 'Brush Script MT', cursive",
  chalkboard: "'Chalkboard SE', Chalkboard, Noteworthy, 'Kristen ITC', 'Comic Sans MS', 'Comic Sans', 'URW Chancery L', cursive",
  marker: "'Marker Felt', 'Comic Sans MS', 'Comic Sans', 'Segoe Print', cursive",
};

/** A safe, quoted stack for a single user-named OS font. */
export function installedTypefaceStack(value: unknown): string | null {
  return installedFontCssStack(value);
}

/** Gating attributes for the writing surface (only the active tools appear). */
export function editorToolsAttrs(tools: EditorToolsState): Record<string, string> {
  const a: Record<string, string> = {};
  if (tools.lineNumbers) a['data-linenumbers'] = 'on';
  if (tools.folding) a['data-folding'] = 'on';
  if (tools.syntax) a['data-syntax'] = 'on';
  if (tools.currentLineHighlight) a['data-currentline'] = 'on';
  if (tools.fontSize != null) a['data-editor-font'] = 'on';
  if (tools.lineHeight != null) a['data-editor-lh'] = 'on';
  if (
    tools.typeface !== 'default'
    && (tools.typeface !== 'installed' || installedTypefaceStack(tools.systemFontFamily))
  ) a['data-editor-typeface'] = tools.typeface;
  if (tools.layout === 'paged') a['data-layout'] = 'paged';
  return a;
}

/** CSS custom properties for the typography overrides. Syntax COLOURS come from
 * the active app theme's `--syn-*` palette (applySyntaxVars), so colour-coding
 * always tracks the chosen theme — no separate, conflicting syntax palette. */
export function editorToolsVars(tools: EditorToolsState): Record<string, string> {
  const v: Record<string, string> = {};
  if (tools.fontSize != null) v['--wb-font-px'] = `${tools.fontSize}px`;
  if (tools.lineHeight != null) v['--wb-line-height'] = String(tools.lineHeight);
  if (tools.typeface === 'installed') {
    const stack = installedTypefaceStack(tools.systemFontFamily);
    if (stack) v['--wb-editor-typeface'] = stack;
  } else if (tools.typeface !== 'default') {
    v['--wb-editor-typeface'] = EDITOR_TYPEFACE_STACKS[tools.typeface];
  }
  if (tools.textColor) v['--wb-editor-ink'] = tools.textColor;
  return v;
}
