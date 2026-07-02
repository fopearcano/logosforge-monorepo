/**
 * A tiny shared store of the manual outline's colour labels, keyed by normalized
 * title. The Outline store (`useOutline`) publishes it whenever its items change;
 * the bottom Story Map subscribes (via useSyncExternalStore) so each node can be
 * tinted with the colour of the outline item it corresponds to — matched by
 * title, the same way Reveal-in-editor matches a manual item to a document
 * heading. Nodes with no matching coloured outline item stay neutral.
 *
 * Mirrors the module-store pattern used by littleBoyControl / documentMenu.
 */

import type { OutlineColor } from './outlineModel';

export interface OutlineColorEntry {
  title: string;
  colorLabel: OutlineColor;
}

let colorMap: Map<string, OutlineColor> = new Map();
const subs = new Set<() => void>();

/** Normalize a title the way Reveal matches (trim + lowercase + collapse spaces). */
export function normalizeOutlineTitle(s: string): string {
  return s.trim().toLowerCase().replace(/\s+/g, ' ');
}

function mapsEqual(a: Map<string, OutlineColor>, b: Map<string, OutlineColor>): boolean {
  if (a.size !== b.size) return false;
  for (const [k, v] of a) if (b.get(k) !== v) return false;
  return true;
}

/** Rebuild the title→colour map from the outline items (coloured items only). */
export function publishOutlineColors(items: OutlineColorEntry[]): void {
  const next = new Map<string, OutlineColor>();
  for (const it of items) {
    if (it.colorLabel && it.colorLabel !== 'none') {
      const k = normalizeOutlineTitle(it.title);
      if (k && !next.has(k)) next.set(k, it.colorLabel);
    }
  }
  if (mapsEqual(colorMap, next)) return; // keep the ref stable so subscribers don't churn
  colorMap = next;
  subs.forEach((s) => s());
}

export function getOutlineColorSnapshot(): Map<string, OutlineColor> {
  return colorMap;
}

export function subscribeOutlineColors(cb: () => void): () => void {
  subs.add(cb);
  return () => {
    subs.delete(cb);
  };
}
