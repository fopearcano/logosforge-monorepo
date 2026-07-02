/**
 * Line-number helpers (pure, testable).
 *
 * The document is block-based, so each top-level block (paragraph / heading)
 * gets one number — the standard behaviour for writing apps (a wrapped block
 * keeps a single number at its first visual line). Rendering happens in the
 * editor-tools ProseMirror extension via a node decoration + CSS gutter.
 */

/** [1, 2, … count]. */
export function lineNumbersForCount(count: number): number[] {
  const out: number[] = [];
  for (let i = 1; i <= count; i += 1) out.push(i);
  return out;
}

/** Digits needed for the widest number — used to size the gutter. */
export function gutterDigits(count: number): number {
  return String(Math.max(1, count)).length;
}
