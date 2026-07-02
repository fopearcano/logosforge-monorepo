/**
 * Fountain boneyard / omitted text detection (pure).
 *
 * Boneyard is wrapped in /* ... *\/ and may span multiple blocks. Returns, for
 * each block, whether it lies inside (or opens/closes) a boneyard region. The
 * text is kept — it is only rendered subdued and excluded from export.
 */

import type { FountainBlock } from './fountainTypes';

export function detectBoneyard(blocks: FountainBlock[]): boolean[] {
  const out: boolean[] = [];
  let inside = false;

  for (const b of blocks) {
    const t = b.text;
    const open = t.indexOf('/*');
    const close = t.indexOf('*/');

    if (inside) {
      out.push(true);
      if (close !== -1) inside = false;
    } else if (open !== -1) {
      out.push(true);
      // Open and close on the same block keeps us closed; otherwise we enter.
      if (!(close !== -1 && close > open)) inside = true;
    } else {
      out.push(false);
    }
  }
  return out;
}
