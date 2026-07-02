/**
 * Derive the outline from the document, client-side.
 *
 * - Screenplay (Fountain): Sections (#), Scene Headings, Synopses (=), Notes ([[ ]]).
 * - Prose modes: Markdown-style headings.
 *
 * Pure (no editor/DOM imports) so it is unit-testable.
 */

import type { FountainBlock } from '../screenplay/fountainTypes';
import { classify } from '../screenplay/screenplayClassifier';
import { modeBehavior } from '../whiteboard/modes';
import type { WhiteboardBlock } from '../whiteboard/types';
import type { OutlineItem } from './types';

function toFountain(blocks: WhiteboardBlock[]): FountainBlock[] {
  return blocks.map((b) => ({
    text: b.text,
    isHeading: b.type === 'heading',
    level: b.level ?? 1,
  }));
}

function sectionLevel(text: string): number {
  const m = text.match(/^#+/);
  return m ? Math.min(m[0].length, 6) : 1;
}

export function deriveOutline(blocks: WhiteboardBlock[], mode: string): OutlineItem[] {
  return modeBehavior(mode).outline === 'fountain'
    ? deriveFountain(blocks)
    : deriveHeadings(blocks);
}

function deriveHeadings(blocks: WhiteboardBlock[]): OutlineItem[] {
  const items: OutlineItem[] = [];
  blocks.forEach((b, i) => {
    if (b.type === 'heading') {
      items.push({
        id: `o${i}`,
        label: b.text.trim() || '(untitled)',
        kind: 'section',
        level: b.level ?? 1,
        blockIndex: i,
      });
    }
  });
  return items;
}

function deriveFountain(blocks: WhiteboardBlock[]): OutlineItem[] {
  const types = classify(toFountain(blocks));
  const items: OutlineItem[] = [];
  blocks.forEach((b, i) => {
    const text = b.text.trim();
    if (b.type === 'heading') {
      items.push({ id: `o${i}`, label: text || '(untitled)', kind: 'section', level: b.level ?? 1, blockIndex: i });
      return;
    }
    switch (types[i]) {
      case 'section':
        items.push({ id: `o${i}`, label: text.replace(/^#+\s*/, '') || '(untitled)', kind: 'section', level: sectionLevel(text), blockIndex: i });
        break;
      case 'scene_heading':
        items.push({ id: `o${i}`, label: text.replace(/^\./, ''), kind: 'scene', level: 0, blockIndex: i });
        break;
      case 'synopsis':
        items.push({ id: `o${i}`, label: text.replace(/^=+\s*/, ''), kind: 'synopsis', level: 0, blockIndex: i });
        break;
      case 'note':
        items.push({
          id: `o${i}`,
          label: text.replace(/^\[\[\s*/, '').replace(/\s*\]\]$/, ''),
          kind: 'note',
          level: 0,
          blockIndex: i,
        });
        break;
      default:
        break;
    }
  });
  return items;
}
