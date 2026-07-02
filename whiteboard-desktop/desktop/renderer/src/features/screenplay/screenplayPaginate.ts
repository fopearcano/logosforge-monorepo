/**
 * Industry-standard screenplay pagination (pure, testable).
 *
 * Lays a classified Fountain document out into US-Letter pages in 12pt Courier
 * (10 chars/inch, 6 lines/inch). Page text area = 6in × 9in = 60 cols × 54 rows,
 * inside a 1in top / 1in bottom / 1in right / 1.5in LEFT margin. Elements sit at
 * their conventional columns (measured from the text-area left edge, i.e. after
 * the 1.5in margin):
 *
 *   Scene heading / Action  col 0   width 60
 *   Dialogue                col 10  width 35
 *   Parenthetical           col 16  width 25
 *   Character (cue)         col 22
 *   Transition              right-aligned to col 60
 *
 * Dialogue that crosses a page boundary gets a "(MORE)" at the foot and the cue
 * repeated as "NAME (CONT'D)" at the top of the next page. Page numbers (added by
 * the renderer) start on page 2.
 */

import { classify } from './screenplayClassifier';
import type { FountainBlock, FountainType } from './fountainTypes';

export interface PageLine {
  text: string;
  col: number;
  align?: 'right';
}
export interface ScreenplayPage {
  number: number;
  /** null = a blank spacer row */
  lines: (PageLine | null)[];
}

export const LINES_PER_PAGE = 54;
const PAGE_COLS = 60;
const COL = { character: 22, parenthetical: 16, dialogue: 10 } as const;
const WIDTH = { action: 60, parenthetical: 25, dialogue: 35 } as const;

/** Greedy word-wrap to `width` columns (hard-breaks any over-long word). */
export function wrapText(text: string, width: number): string[] {
  const words = text.split(/\s+/).filter(Boolean);
  if (!words.length) return [''];
  const out: string[] = [];
  let line = '';
  for (const word of words) {
    if (word.length > width) {
      if (line) {
        out.push(line);
        line = '';
      }
      let w = word;
      while (w.length > width) {
        out.push(w.slice(0, width));
        w = w.slice(width);
      }
      line = w;
    } else if (!line) {
      line = word;
    } else if (line.length + 1 + word.length <= width) {
      line += ` ${word}`;
    } else {
      out.push(line);
      line = word;
    }
  }
  if (line) out.push(line);
  return out.length ? out : [''];
}

interface El {
  type: FountainType;
  character?: string; // speaking character (for CONT'D)
  blankBefore: number;
  lines: PageLine[];
  keepWithNext: boolean; // scene heading / cue must not be orphaned at a page foot
}

function buildElements(blocks: FountainBlock[]): El[] {
  const types = classify(blocks);
  const els: El[] = [];
  let currentChar = '';
  blocks.forEach((b, i) => {
    const type = types[i];
    const text = b.text.trim();
    if (!text || type === 'empty' || type === 'page_break') return;

    if (type === 'character') {
      currentChar = text.toUpperCase();
      els.push({ type, character: currentChar, blankBefore: 1, keepWithNext: true,
        lines: [{ text: currentChar, col: COL.character }] });
    } else if (type === 'parenthetical') {
      els.push({ type, character: currentChar, blankBefore: 0, keepWithNext: true,
        lines: wrapText(text, WIDTH.parenthetical).map((t) => ({ text: t, col: COL.parenthetical })) });
    } else if (type === 'dialogue') {
      els.push({ type, character: currentChar, blankBefore: 0, keepWithNext: false,
        lines: wrapText(text, WIDTH.dialogue).map((t) => ({ text: t, col: COL.dialogue })) });
    } else if (type === 'transition') {
      els.push({ type, blankBefore: 1, keepWithNext: false,
        lines: [{ text: text.toUpperCase(), col: 0, align: 'right' }] });
    } else if (type === 'scene_heading') {
      els.push({ type, blankBefore: 2, keepWithNext: true,
        lines: wrapText(text.toUpperCase(), PAGE_COLS).map((t) => ({ text: t, col: 0 })) });
    } else {
      // action (and section/synopsis/note/centered fall back to action)
      els.push({ type: 'action', blankBefore: 1, keepWithNext: false,
        lines: wrapText(text, WIDTH.action).map((t) => ({ text: t, col: 0 })) });
    }
  });
  return els;
}

export function paginateScreenplay(blocks: FountainBlock[]): ScreenplayPage[] {
  const els = buildElements(blocks);
  const pages: ScreenplayPage[] = [];
  let lines: (PageLine | null)[] = [];
  let used = 0;
  let pageNo = 1;

  const flush = () => {
    pages.push({ number: pageNo, lines });
    pageNo += 1;
    lines = [];
    used = 0;
  };
  const push = (l: PageLine | null) => {
    lines.push(l);
    used += 1;
  };
  const contdCue = (name?: string) => {
    if (name) push({ text: `${name} (CONT'D)`, col: COL.character });
  };

  for (const el of els) {
    const blank = used === 0 ? 0 : el.blankBefore;

    // Orphan control: don't strand a scene heading / cue at the page foot.
    if (el.keepWithNext && used > 0 && used + blank + el.lines.length + 1 > LINES_PER_PAGE) {
      flush();
    }
    const lead = used === 0 ? 0 : el.blankBefore;
    for (let k = 0; k < lead; k += 1) push(null);

    if (el.type === 'dialogue' || el.type === 'action') {
      const isDialogue = el.type === 'dialogue';
      let idx = 0;
      while (idx < el.lines.length) {
        let room = LINES_PER_PAGE - used;
        if (room <= 0) {
          flush();
          if (isDialogue) contdCue(el.character);
          room = LINES_PER_PAGE - used;
        }
        const remaining = el.lines.length - idx;
        if (isDialogue && remaining > room) {
          // Split with (MORE)/(CONT'D); keep ≥1 line + the (MORE) on this page.
          const place = room - 1;
          if (place < 1) {
            flush();
            contdCue(el.character);
            continue;
          }
          for (let n = 0; n < place; n += 1) push(el.lines[idx++]);
          push({ text: '(MORE)', col: COL.parenthetical });
          flush();
          contdCue(el.character);
        } else {
          const place = Math.min(remaining, room);
          for (let n = 0; n < place; n += 1) push(el.lines[idx++]);
          if (idx < el.lines.length) flush();
        }
      }
    } else {
      // Short atomic element (scene heading / character / parenthetical / transition).
      if (used + el.lines.length > LINES_PER_PAGE) flush();
      el.lines.forEach(push);
    }
  }
  if (lines.length) flush();
  return pages;
}
