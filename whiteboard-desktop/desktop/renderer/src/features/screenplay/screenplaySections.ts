/** Section depth math (pure). Sections map to heading levels 1–3 (#, ##, ###). */

export const MAX_SECTION_LEVEL = 3;

/** Tab on a Section deepens it (adds a #), capped at level 3. */
export function sectionTabLevel(level: number): number {
  return Math.min(level + 1, MAX_SECTION_LEVEL);
}

/**
 * Shift+Tab on a Section shallows it (removes a #). Returns the new level, or 0
 * to mean "drop the section entirely" (convert to a normal paragraph).
 */
export function sectionShiftTabLevel(level: number): number {
  return level > 1 ? level - 1 : 0;
}
