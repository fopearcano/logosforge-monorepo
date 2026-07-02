/**
 * Maps the editor-tools state to the `data-*` attributes + CSS custom properties
 * applied on the writing surface. Keeping this here (pure) keeps WhiteboardPage
 * clean and the CSS gating in one obvious place.
 */

import type { EditorToolsState } from './editorToolTypes';

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
  return a;
}

/** CSS custom properties for the typography overrides. Syntax COLOURS come from
 * the active app theme's `--syn-*` palette (applySyntaxVars), so colour-coding
 * always tracks the chosen theme — no separate, conflicting syntax palette. */
export function editorToolsVars(tools: EditorToolsState): Record<string, string> {
  const v: Record<string, string> = {};
  if (tools.fontSize != null) v['--wb-font-px'] = `${tools.fontSize}px`;
  if (tools.lineHeight != null) v['--wb-line-height'] = String(tools.lineHeight);
  return v;
}
