/**
 * Document <-> plain-text serialization for disk files (pure, testable).
 *
 * Files are plain text / Fountain: one document block per line, with heading
 * blocks written as Markdown/Fountain Sections (`#`). This round-trips with the
 * editor's block model and stays compatible with .fountain / .md / .txt.
 */

import { blocksToFountainText } from '../screenplay/screenplayExport';
import type { WhiteboardBlock } from '../whiteboard/types';

export type DocExt = 'fountain' | 'md' | 'txt' | 'logosforge';

/** Blocks -> file text (lossless: markers/notes/boneyard preserved). */
export function blocksToText(blocks: WhiteboardBlock[]): string {
  return blocksToFountainText(blocks);
}

/** File text -> blocks. `#`/`##`/`###` lines become heading blocks. */
export function textToBlocks(text: string): WhiteboardBlock[] {
  const lines = text.replace(/\r\n?/g, '\n').split('\n');
  // A trailing newline (common in text files) yields one empty trailing line.
  if (lines.length > 1 && lines[lines.length - 1] === '') lines.pop();

  const blocks = lines.map((line, i): WhiteboardBlock => {
    const m = line.match(/^(#{1,3})\s+(.*)$/);
    if (m) return { id: `b${i}`, type: 'heading', text: m[2], level: m[1].length };
    return { id: `b${i}`, type: 'paragraph', text: line };
  });
  return blocks.length ? blocks : [{ id: 'b0', type: 'paragraph', text: '' }];
}

/** Default file extension for a writing mode (Save As default). */
export function defaultExtForMode(mode: string): DocExt {
  if (mode === 'screenplay') return 'fountain';
  if (['novel', 'notes', 'scene', 'graphic_novel'].includes(mode)) return 'md';
  return 'txt';
}

export function baseName(p: string): string {
  return p.replace(/^.*[\\/]/, '');
}

/** Suggested filename for the Save As dialog. */
export function suggestedFileName(currentPath: string | null, mode: string): string {
  if (currentPath) return baseName(currentPath);
  return `untitled.${defaultExtForMode(mode)}`;
}
