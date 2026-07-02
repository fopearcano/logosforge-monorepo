/** Autocomplete suggestion logic (pure, testable) — static slugs + doc-derived. */

import type { FountainBlock } from './fountainTypes';
import {
  extractCharacters,
  extractSceneHeadings,
  extractTransitions,
} from './screenplayClassifier';

export const STATIC_SUGGESTIONS = [
  'INT. ',
  'EXT. ',
  'INT./EXT. ',
  'EST. ',
  'CUT TO:',
  'FADE TO:',
  'FADE OUT:',
  'FADE IN:',
  'DISSOLVE TO:',
  'SMASH CUT:',
];

/**
 * Build the suggestion list from the document. When `charactersFirst` is true
 * (a character cue is plausible at the cursor — e.g. dialogue context), recently
 * used character names are prioritized.
 */
export function computeSuggestions(blocks: FountainBlock[], charactersFirst = false): string[] {
  const characters = extractCharacters(blocks);
  const scenes = extractSceneHeadings(blocks);
  const transitions = extractTransitions(blocks);
  const ordered = charactersFirst
    ? [...characters, ...STATIC_SUGGESTIONS, ...scenes, ...transitions]
    : [...STATIC_SUGGESTIONS, ...characters, ...scenes, ...transitions];
  return [...new Set(ordered.filter(Boolean))];
}

/** Filter suggestions by a typed query — prefix matches first, then substring. */
export function filterSuggestions(items: string[], query: string): string[] {
  const q = query.trim().toUpperCase();
  if (!q) return items;
  const prefix: string[] = [];
  const substr: string[] = [];
  for (const it of items) {
    const u = it.toUpperCase();
    if (u.startsWith(q)) prefix.push(it);
    else if (u.includes(q)) substr.push(it);
  }
  return [...prefix, ...substr];
}
