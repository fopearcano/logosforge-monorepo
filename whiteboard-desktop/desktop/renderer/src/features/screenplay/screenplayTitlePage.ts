/**
 * Fountain title-page parsing foundation (pure).
 *
 * Recognizes leading "Key: value" metadata (Title, Credit, Author(s), Source,
 * Draft date, Contact, Copyright, …) with indented multi-line continuations,
 * up to the first blank line. Returns the parsed fields and how many leading
 * blocks the title page spans (so the editor can render them subtly).
 *
 * Plain text is preserved; this does not transform the document.
 */

import type { FountainBlock } from './fountainTypes';

const KEYS = new Set([
  'title',
  'credit',
  'author',
  'authors',
  'source',
  'draft date',
  'date',
  'contact',
  'copyright',
  'notes',
  'revision',
]);

const KEY_RE = /^([A-Za-z][A-Za-z ]*?):\s*(.*)$/;

export interface TitlePage {
  fields: Record<string, string>;
  /** Number of leading blocks the title page occupies (0 if none). */
  endIndex: number;
}

export function parseTitlePage(blocks: FountainBlock[]): TitlePage {
  const fields: Record<string, string> = {};
  let i = 0;
  let lastKey: string | null = null;

  for (; i < blocks.length; i += 1) {
    const raw = blocks[i].text;
    if (blocks[i].isHeading) break;

    if (raw.trim() === '') {
      if (Object.keys(fields).length > 0) i += 1; // consume the terminating blank
      break;
    }

    const m = raw.match(KEY_RE);
    const indented = /^\s+\S/.test(raw);

    if (m && KEYS.has(m[1].trim().toLowerCase())) {
      lastKey = m[1].trim().toLowerCase();
      fields[lastKey] = m[2].trim();
    } else if (indented && lastKey) {
      fields[lastKey] = (fields[lastKey] ? `${fields[lastKey]}\n` : '') + raw.trim();
    } else {
      break; // not a title-page line
    }
  }

  return { fields, endIndex: Object.keys(fields).length ? i : 0 };
}
