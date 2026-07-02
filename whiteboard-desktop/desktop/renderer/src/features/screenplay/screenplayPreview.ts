/**
 * Build a readable screenplay Preview from the document (pure, testable).
 *
 * Applies final-output-ish formatting:
 *  - title-page fields are separated out;
 *  - notes ([[ … ]]) and boneyard (/* … *​/) are excluded;
 *  - Sections/Synopses are excluded unless `settings.includeOutline`;
 *  - structural markers (leading ., #, =, >) are stripped;
 *  - inline emphasis markers are removed but the styling is preserved via
 *    `previewSegments`.
 *
 * NOT paginated — a clean, readable foundation.
 */

import type { DocumentSettings } from '../whiteboard/documentSettings';
import { parseEmphasis } from './fountainParser';
import { detectBoneyard } from './screenplayBoneyard';
import { classify } from './screenplayClassifier';
import { stripForExport } from './screenplayExport';
import type { FountainBlock, FountainType } from './fountainTypes';
import { parseTitlePage } from './screenplayTitlePage';

export interface PreviewLine {
  type: FountainType;
  text: string;
}

export interface Preview {
  titlePage: Record<string, string>;
  lines: PreviewLine[];
}

const OUTLINE_TYPES = new Set<FountainType>(['section', 'synopsis']);

function cleanText(type: FountainType, raw: string): string {
  let t = raw.trim();
  switch (type) {
    case 'scene_heading':
      t = t.replace(/^\.(?!\.)/, ''); // drop the forced-scene dot
      break;
    case 'section':
      t = t.replace(/^#+\s*/, '');
      break;
    case 'synopsis':
      t = t.replace(/^=\s*/, '');
      break;
    case 'transition':
      t = t.replace(/^>\s*/, '');
      break;
    case 'centered':
      t = t.replace(/^>\s*/, '').replace(/\s*<$/, '');
      break;
    default:
      break;
  }
  // Drop any inline notes / boneyard, then tidy whitespace.
  return stripForExport(t).replace(/\s{2,}/g, ' ').trim();
}

export function buildPreview(blocks: FountainBlock[], settings: DocumentSettings): Preview {
  const { fields, endIndex } = parseTitlePage(blocks);
  const types = classify(blocks);
  const boneyard = detectBoneyard(blocks);
  const lines: PreviewLine[] = [];

  blocks.forEach((b, i) => {
    if (i < endIndex || boneyard[i]) return; // title page + omitted text excluded
    const type = types[i];
    if (type === 'empty' || type === 'note') return; // blanks + notes excluded
    if (OUTLINE_TYPES.has(type) && !settings.includeOutline) return;
    const text = cleanText(type, b.text);
    if (text === '' && type !== 'page_break') return;
    lines.push({ type, text });
  });

  return { titlePage: fields, lines };
}

// -- dual dialogue ----------------------------------------------------------
//
// Fountain marks the second of two simultaneous speakers with a trailing "^" on
// the character cue. We pair that block with the immediately-preceding dialogue
// block into a two-column group; everything else stays a single line.

export type PreviewItem =
  | { kind: 'line'; line: PreviewLine }
  | { kind: 'block'; lines: PreviewLine[] } // a normal character dialogue block
  | { kind: 'dual'; left: PreviewLine[]; right: PreviewLine[] };

const DIALOGUE_TYPES = new Set<FountainType>(['parenthetical', 'dialogue']);
const DUAL_RE = /\s*\^\s*$/;

function stripCaret(lines: PreviewLine[]): PreviewLine[] {
  return lines.map((l, i) =>
    i === 0 && l.type === 'character' ? { ...l, text: l.text.replace(DUAL_RE, '').trim() } : l,
  );
}

export function groupPreviewItems(lines: PreviewLine[]): PreviewItem[] {
  // Pass A: gather each character cue + its parenthetical/dialogue into a block;
  // every other line stays standalone.
  type Seg =
    | { kind: 'block'; lines: PreviewLine[]; dual: boolean }
    | { kind: 'line'; line: PreviewLine };
  const segs: Seg[] = [];
  for (let i = 0; i < lines.length; ) {
    const l = lines[i];
    if (l.type === 'character') {
      const group = [l];
      let j = i + 1;
      while (j < lines.length && DIALOGUE_TYPES.has(lines[j].type)) {
        group.push(lines[j]);
        j += 1;
      }
      segs.push({ kind: 'block', lines: group, dual: DUAL_RE.test(l.text) });
      i = j;
    } else {
      segs.push({ kind: 'line', line: l });
      i += 1;
    }
  }

  // Pass B: a "^" block pairs with the preceding character block (two columns).
  const items: PreviewItem[] = [];
  for (const s of segs) {
    if (s.kind === 'block' && s.dual && items.length && items[items.length - 1].kind === 'block') {
      const prev = items.pop() as { kind: 'block'; lines: PreviewLine[] };
      items.push({ kind: 'dual', left: prev.lines, right: stripCaret(s.lines) });
    } else if (s.kind === 'block') {
      items.push({ kind: 'block', lines: stripCaret(s.lines) });
    } else {
      items.push({ kind: 'line', line: s.line });
    }
  }
  return items;
}

export interface Segment {
  text: string;
  /** Emphasis class, or null for plain text. */
  cls: string | null;
}

/** Split a line into styled segments with the emphasis markers removed. */
export function previewSegments(text: string): Segment[] {
  const ranges = parseEmphasis(text);
  if (ranges.length === 0) return text ? [{ text, cls: null }] : [];

  const isMarker = new Array<boolean>(text.length).fill(false);
  const clsAt = new Array<string | null>(text.length).fill(null);
  for (const r of ranges) {
    if (r.className === 'sp-emph-marker') {
      for (let i = r.from; i < r.to; i += 1) isMarker[i] = true;
    } else {
      for (let i = r.from; i < r.to; i += 1) clsAt[i] = r.className;
    }
  }

  const segs: Segment[] = [];
  let cur = '';
  let curCls: string | null = null;
  const flush = () => {
    if (cur) segs.push({ text: cur, cls: curCls });
    cur = '';
  };
  for (let i = 0; i < text.length; i += 1) {
    if (isMarker[i]) continue; // hide markers in the preview
    if (clsAt[i] !== curCls) {
      flush();
      curCls = clsAt[i];
    }
    cur += text[i];
  }
  flush();
  return segs;
}

/** Render the Preview as plain formatted text (markers stripped) — for copying. */
export function previewToPlainText(preview: Preview): string {
  const out: string[] = [];
  for (const key of Object.keys(preview.titlePage)) {
    const label = key.charAt(0).toUpperCase() + key.slice(1);
    out.push(`${label}: ${preview.titlePage[key]}`);
  }
  if (out.length) out.push('');
  for (const line of preview.lines) {
    out.push(previewSegments(line.text).map((s) => s.text).join(''));
  }
  return out.join('\n');
}
