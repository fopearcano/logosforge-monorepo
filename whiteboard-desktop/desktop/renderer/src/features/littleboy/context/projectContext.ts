/**
 * Project-awareness for the AI agents (pure, testable).
 *
 * The agents (Billy chat + Logos inline) used to see only the text around the
 * cursor — "project-blind". This builds a compact, bounded digest of the whole
 * document (its outline + cast) from the live editor blocks, which the caller
 * PREPENDS to the `nearby_context` field both agents already send. That field is
 * forwarded 1:1 by the wrapper and folded into the core's "Editor context:"
 * grounding — so no DTO / wrapper / core change is needed.
 */

import { deriveOutline } from '../../outline/deriveOutline';
import { extractCharacters } from '../../screenplay/screenplayClassifier';
import { toFountainBlocks } from '../../screenplay/screenplayExport';
import type { WhiteboardBlock } from '../../whiteboard/types';
import { clamp } from './selectionContext';

export const OUTLINE_MAX = 30;
export const CAST_MAX = 30;
export const PROJECT_MAX = 900; // stays well under the core's caps (chat 6000, inline ~600)

/** A short outline + cast digest of the current document, or '' when empty. */
export function buildProjectContext(blocks: WhiteboardBlock[], mode: string): string {
  const outline = deriveOutline(blocks, mode).filter((o) => o.kind === 'section' || o.kind === 'scene');
  const cast = extractCharacters(toFountainBlocks(blocks));

  const parts: string[] = [];
  if (cast.length) {
    const shown = cast.slice(0, CAST_MAX);
    const more = cast.length - shown.length;
    parts.push(`Cast: ${shown.join(', ')}${more > 0 ? ` (+${more} more)` : ''}`);
  }
  if (outline.length) {
    const shown = outline.slice(0, OUTLINE_MAX);
    const more = outline.length - shown.length;
    const rows = shown.map((o) =>
      o.kind === 'scene'
        ? `  - ${o.label}`
        : `${'  '.repeat(Math.max(0, (o.level ?? 1) - 1))}${o.label}`,
    );
    parts.push(`Outline:\n${rows.join('\n')}${more > 0 ? `\n  …(+${more} more)` : ''}`);
  }
  if (!parts.length) return '';
  return clamp(`Document so far (for reference) —\n${parts.join('\n')}`, PROJECT_MAX);
}

/** Put the project digest first, then the cursor's nearby text. */
export function prependProjectContext(project: string, nearby: string | undefined): string {
  const p = project.trim();
  const n = (nearby ?? '').trim();
  if (p && n) return `${p}\n\n${n}`;
  return p || n;
}
