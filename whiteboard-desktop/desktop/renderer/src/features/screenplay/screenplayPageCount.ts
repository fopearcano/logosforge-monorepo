/**
 * Rough screenplay page-count approximation (pure).
 *
 * NOT production pagination — a simple printed-line model (~55 lines/page) that
 * ignores notes/boneyard/outline elements and adds a page for the title page.
 * Final industry-accurate pagination (precise element spacing, MORE/CONT'D,
 * dialogue page-breaks, etc.) is a later task — see PRO_TODO / docs.
 */

import { detectBoneyard } from './screenplayBoneyard';
import { classify } from './screenplayClassifier';
import type { FountainBlock, FountainType } from './fountainTypes';
import { parseTitlePage } from './screenplayTitlePage';

const LINES_PER_PAGE = 55;

// Approximate printable column widths per element (Courier 12pt ≈ 60 cols).
const WIDTH: Partial<Record<FountainType, number>> = {
  scene_heading: 58,
  action: 58,
  character: 38,
  dialogue: 35,
  parenthetical: 32,
  transition: 58,
  centered: 58,
};

/** Approximate page count (0 for an empty document). */
export function approxPageCount(blocks: FountainBlock[]): number {
  const types = classify(blocks);
  const boneyard = detectBoneyard(blocks);
  const titleEnd = parseTitlePage(blocks).endIndex;

  let printedLines = 0;
  blocks.forEach((b, i) => {
    if (i < titleEnd || boneyard[i]) return;
    const t = types[i];
    if (t === 'empty') {
      printedLines += 1; // a blank line still occupies vertical space
      return;
    }
    if (t === 'note' || t === 'section' || t === 'synopsis' || t === 'page_break') return;
    const text = b.text.trim();
    if (!text) return;
    const width = WIDTH[t] ?? 58;
    printedLines += Math.max(1, Math.ceil(text.length / width)) + 1; // + element spacing
  });

  const body = printedLines === 0 ? 0 : Math.max(1, Math.round(printedLines / LINES_PER_PAGE));
  return (titleEnd > 0 ? 1 : 0) + body;
}
