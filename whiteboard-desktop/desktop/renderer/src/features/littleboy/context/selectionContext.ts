/**
 * Pure selection/context helpers (no editor/DOM imports) — unit-testable.
 *
 * Keeps AI context bounded (Part 8): never send the whole document by default.
 */

export const NEARBY_LIMIT = 1500;
export const PREVIEW_LIMIT = 160;

/** Truncate to `max` characters with a trailing ellipsis when clipped. */
export function clamp(text: string, max: number): string {
  const t = text ?? '';
  if (t.length <= max) return t;
  return t.slice(0, Math.max(0, max - 1)).trimEnd() + '…';
}

/** Collapse runs of blank lines / trailing whitespace and bound the length. */
export function boundedContext(text: string, max: number = NEARBY_LIMIT): string {
  const cleaned = (text ?? '').replace(/\n{3,}/g, '\n\n').trim();
  return clamp(cleaned, max);
}

/** A short, single-line preview for the Logos context header. */
export function contextPreview(selection: string, block: string, max: number = PREVIEW_LIMIT): string {
  const source = (selection && selection.trim()) || (block && block.trim()) || '';
  return clamp(source.replace(/\s+/g, ' ').trim(), max);
}
