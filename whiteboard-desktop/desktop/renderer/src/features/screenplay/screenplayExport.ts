/**
 * Export foundation (pure). Notes ([[ … ]]) and boneyard (/* … *​/) are excluded
 * from preview/export — they stay in the document but are stripped here.
 *
 * This is a *foundation*, not a production exporter: it serializes to raw
 * Fountain / plain text. PDF, Final Draft (.fdx), and Print are declared as
 * future targets (see `EXPORT_TARGETS`) so the UI + callers have a stable
 * boundary to build on later.
 */

import type { WhiteboardBlock } from '../whiteboard/types';
import type { FountainBlock, FountainType } from './fountainTypes';
import { classify } from './screenplayClassifier';

const BONEYARD = /\/\*[\s\S]*?\*\//g;
const NOTE = /\[\[[\s\S]*?\]\]/g;

/** Remove notes + boneyard for preview/export (the editor keeps the raw text). */
export function stripForExport(text: string): string {
  return text.replace(BONEYARD, '').replace(NOTE, '');
}

/** WhiteboardBlock[] → FountainBlock[] (heading nodes are Fountain Sections). */
export function toFountainBlocks(blocks: WhiteboardBlock[]): FountainBlock[] {
  return blocks.map((b) => ({
    text: b.text,
    isHeading: b.type === 'heading',
    level: b.level ?? 1,
  }));
}

/**
 * Serialize the document to raw Fountain text (lossless — markers, notes and
 * boneyard are preserved). Heading nodes are written as Fountain Sections (`#`).
 */
export function blocksToFountainText(blocks: WhiteboardBlock[]): string {
  return blocks
    .map((b) =>
      b.type === 'heading' ? `${'#'.repeat(Math.max(1, b.level ?? 1))} ${b.text}`.trimEnd() : b.text,
    )
    .join('\n');
}

const XML_ESCAPE: Record<string, string> = {
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;',
};
function escapeXml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => XML_ESCAPE[c]);
}

/** Fountain element → Final Draft paragraph Type. */
const FDX_TYPE: Partial<Record<FountainType, string>> = {
  scene_heading: 'Scene Heading',
  action: 'Action',
  character: 'Character',
  dialogue: 'Dialogue',
  parenthetical: 'Parenthetical',
  transition: 'Transition',
};
/** Structural / non-content elements that have no Final Draft paragraph. */
const FDX_SKIP = new Set<FountainType>(['note', 'page_break', 'empty', 'section', 'synopsis']);

/**
 * Serialize the document to Final Draft (.fdx) XML — the inverse of parseFdx.
 * Each block is classified via Fountain inference and emitted as a typed
 * Paragraph; notes/boneyard are stripped, blank and structural lines dropped
 * (FDX has no blank/section paragraphs), and text is XML-escaped.
 */
export function blocksToFdx(blocks: WhiteboardBlock[]): string {
  const types = classify(toFountainBlocks(blocks));
  const paras: string[] = [];
  blocks.forEach((b, i) => {
    const type = types[i] ?? 'action';
    if (FDX_SKIP.has(type)) return;
    const text = stripForExport(b.text).trim();
    if (!text) return;
    paras.push(`    <Paragraph Type="${FDX_TYPE[type] ?? 'Action'}"><Text>${escapeXml(text)}</Text></Paragraph>`);
  });
  return [
    '<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
    '<FinalDraft DocumentType="Script" Template="No" Version="1">',
    '  <Content>',
    ...paras,
    '  </Content>',
    '</FinalDraft>',
    '',
  ].join('\n');
}

export interface ExportTarget {
  id: string;
  label: string;
  /** Implemented now vs. a declared future boundary. */
  available: boolean;
  note?: string;
}

/** What export can do now, plus the boundaries reserved for later. */
export const EXPORT_TARGETS: ExportTarget[] = [
  { id: 'fountain', label: 'Export Fountain (.fountain)', available: true },
  { id: 'copy-fountain', label: 'Copy Fountain text', available: true },
  { id: 'copy-preview', label: 'Copy formatted preview', available: true },
  { id: 'pdf', label: 'Export PDF…', available: true },
  { id: 'fdx', label: 'Export Final Draft (.fdx)…', available: true },
  { id: 'print', label: 'Print…', available: true },
];
