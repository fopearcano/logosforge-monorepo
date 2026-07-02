/**
 * Fountain inline emphasis parser (pure, testable).
 *
 * Recognizes ***bold italic***, **bold**, *italic*, _underline_. Returns the
 * marker ranges (so they can be dimmed) and the content ranges (so the inner
 * text can be styled). Simple, non-nested — a clean foundation.
 */

import type { EmphasisRange } from './fountainTypes';

// Order matters: try the longest markers first.
const EMPHASIS =
  /(\*\*\*)([^*]+?)(\*\*\*)|(\*\*)([^*]+?)(\*\*)|(\*)([^*]+?)(\*)|(_)([^_]+?)(_)/g;

export function parseEmphasis(text: string): EmphasisRange[] {
  const ranges: EmphasisRange[] = [];
  EMPHASIS.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = EMPHASIS.exec(text)) !== null) {
    let markerLen: number;
    let contentClass: string;
    if (m[1]) {
      markerLen = 3;
      contentClass = 'sp-bold-italic';
    } else if (m[4]) {
      markerLen = 2;
      contentClass = 'sp-bold';
    } else if (m[7]) {
      markerLen = 1;
      contentClass = 'sp-italic';
    } else {
      markerLen = 1;
      contentClass = 'sp-underline';
    }
    const start = m.index;
    const end = m.index + m[0].length;
    ranges.push({ from: start, to: start + markerLen, className: 'sp-emph-marker' });
    ranges.push({ from: start + markerLen, to: end - markerLen, className: contentClass });
    ranges.push({ from: end - markerLen, to: end, className: 'sp-emph-marker' });
    if (m.index === EMPHASIS.lastIndex) EMPHASIS.lastIndex += 1; // guard
  }
  return ranges;
}
