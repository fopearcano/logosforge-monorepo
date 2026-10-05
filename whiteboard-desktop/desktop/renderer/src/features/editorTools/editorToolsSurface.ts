/**
 * Maps the editor-tools state to the `data-*` attributes + CSS custom properties
 * applied on the writing surface. Keeping this here (pure) keeps WhiteboardPage
 * clean and the CSS gating in one obvious place.
 */

import type { EditorToolsState } from './editorToolTypes';

/** Offline-safe stacks. Bundled faces lead where available; platform faces add
 * several distinct book, handwriting and typewriter voices without networking. */
export const EDITOR_TYPEFACE_STACKS: Record<Exclude<EditorToolsState['typeface'], 'default'>, string> = {
  serif: "'Spectral', 'Iowan Old Style', Georgia, serif",
  book: "'Palatino Linotype', 'Book Antiqua', Palatino, 'URW Palladio L', serif",
  classic: "Georgia, 'Times New Roman', 'Liberation Serif', serif",
  sans: "'IBM Plex Sans', system-ui, -apple-system, 'Segoe UI', sans-serif",
  system: "system-ui, -apple-system, 'Segoe UI', sans-serif",
  mono: "'IBM Plex Mono', ui-monospace, 'SF Mono', Menlo, Consolas, monospace",
  'courier-prime': "'Courier Prime', 'Courier New', 'Liberation Mono', monospace",
  typewriter: "'American Typewriter', 'Lucida Console', Monaco, 'URW Typewriter L', 'DejaVu Sans Mono', monospace",
  handwritten: "'Segoe Print', 'Bradley Hand', 'Comic Sans MS', 'Comic Sans', 'Comic Neue', Chilanka, cursive",
  script: "'Segoe Script', 'Snell Roundhand', 'Brush Script MT', cursive",
  chalkboard: "'Chalkboard SE', Chalkboard, Noteworthy, 'Kristen ITC', 'Comic Sans MS', 'Comic Sans', 'URW Chancery L', cursive",
};

/** Gating attributes for the writing surface (only the active tools appear). */
export function editorToolsAttrs(tools: EditorToolsState): Record<string, string> {
  const a: Record<string, string> = {};
  if (tools.lineNumbers) a['data-linenumbers'] = 'on';
  if (tools.folding) a['data-folding'] = 'on';
  if (tools.syntax) a['data-syntax'] = 'on';
  if (tools.currentLineHighlight) a['data-currentline'] = 'on';
  if (tools.fontSize != null) a['data-editor-font'] = 'on';
  if (tools.lineHeight != null) a['data-editor-lh'] = 'on';
  if (tools.typeface !== 'default') a['data-editor-typeface'] = tools.typeface;
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
  if (tools.typeface !== 'default') v['--wb-editor-typeface'] = EDITOR_TYPEFACE_STACKS[tools.typeface];
  if (tools.textColor) v['--wb-editor-ink'] = tools.textColor;
  return v;
}
