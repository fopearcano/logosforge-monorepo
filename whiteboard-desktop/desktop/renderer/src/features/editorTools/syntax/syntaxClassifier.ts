/**
 * Syntax classification (pure, testable) — the writer-oriented "syntax" layer.
 *
 * Produces a block-level token + a list of inline spans per block. The editor
 * tools extension turns these into `wb-syn-*` decorations, coloured by the
 * active theme. Screenplay reuses the Fountain classifier; prose/notes modes
 * classify Markdown-ish headings, bullets and checkboxes. Inline spans (emphasis,
 * notes, TODO/FIXME, tags, links, checkboxes) are shared across modes.
 */

import { parseEmphasis } from '../../screenplay/fountainParser';
import type { FountainBlock } from '../../screenplay/fountainTypes';
import { detectBoneyard } from '../../screenplay/screenplayBoneyard';
import { classify } from '../../screenplay/screenplayClassifier';
import { parseTitlePage } from '../../screenplay/screenplayTitlePage';
import { headingLevel } from '../folding/foldingModel';

export type BlockToken =
  | 'scene_heading'
  | 'action'
  | 'character'
  | 'dialogue'
  | 'parenthetical'
  | 'transition'
  | 'centered'
  | 'section'
  | 'synopsis'
  | 'note'
  | 'boneyard'
  | 'page_break'
  | 'title_field'
  | 'chapter'
  | 'heading'
  | 'subheading'
  | 'bullet'
  | 'checkbox'
  | 'plain';

export type InlineToken = 'emphasis' | 'note' | 'todo' | 'tag' | 'link' | 'checkbox' | 'psyke' | 'quote';

export interface InlineSpan {
  from: number;
  to: number;
  token: InlineToken;
}

export interface BlockSyntax {
  token: BlockToken;
  inline: InlineSpan[];
}

const TODO_RE = /\b(?:TODO|FIXME|XXX)\b/g;
const NOTE_RE = /\[\[[^\]]*?\]\]/g;
const LINK_MD_RE = /\[[^\]]+\]\([^)]+\)/g;
const URL_RE = /\bhttps?:\/\/[^\s)]+/g;
const CHECKBOX_RE = /\[[ xX]\]/g;
const TAG_RE = /(^|\s)([#@][A-Za-z][\w-]*)/g;
// Reserved: an inline PSYKE reference convention (foundation — see docs).
const PSYKE_RE = /@@[A-Za-z][\w -]*/g;
// Prose dialogue: a run of double-quoted speech ("…" straight or “…” curly).
const QUOTE_RE = /“[^”\n]*”|"[^"\n]*"/g;

function eachMatch(re: RegExp, text: string, fn: (m: RegExpExecArray) => void) {
  re.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    fn(m);
    if (m.index === re.lastIndex) re.lastIndex += 1; // zero-width guard
  }
}

/** Inline spans, de-overlapped by earliest-start / longest-wins priority. */
function scanInline(text: string, mode: string): InlineSpan[] {
  const spans: InlineSpan[] = [];
  const add = (from: number, to: number, token: InlineToken) => {
    if (to > from) spans.push({ from, to, token });
  };

  for (const r of parseEmphasis(text)) {
    if (r.className !== 'sp-emph-marker') add(r.from, r.to, 'emphasis');
  }
  eachMatch(NOTE_RE, text, (m) => add(m.index, m.index + m[0].length, 'note'));
  eachMatch(PSYKE_RE, text, (m) => add(m.index, m.index + m[0].length, 'psyke'));
  eachMatch(LINK_MD_RE, text, (m) => add(m.index, m.index + m[0].length, 'link'));
  eachMatch(URL_RE, text, (m) => add(m.index, m.index + m[0].length, 'link'));
  eachMatch(TODO_RE, text, (m) => add(m.index, m.index + m[0].length, 'todo'));
  if (mode !== 'screenplay') {
    eachMatch(QUOTE_RE, text, (m) => add(m.index, m.index + m[0].length, 'quote'));
    eachMatch(CHECKBOX_RE, text, (m) => add(m.index, m.index + m[0].length, 'checkbox'));
    eachMatch(TAG_RE, text, (m) => {
      const tag = m[2];
      const start = m.index + m[0].indexOf(tag);
      add(start, start + tag.length, 'tag');
    });
  }

  // Resolve overlaps: sort by start (longer first on ties), drop overlaps.
  spans.sort((a, b) => a.from - b.from || b.to - a.to);
  const out: InlineSpan[] = [];
  let lastEnd = -1;
  for (const s of spans) {
    if (s.from >= lastEnd) {
      out.push(s);
      lastEnd = s.to;
    }
  }
  return out;
}

const FOUNTAIN_TO_TOKEN: Record<string, BlockToken> = {
  scene_heading: 'scene_heading',
  action: 'action',
  character: 'character',
  dialogue: 'dialogue',
  parenthetical: 'parenthetical',
  transition: 'transition',
  centered: 'centered',
  section: 'section',
  synopsis: 'synopsis',
  note: 'note',
  page_break: 'page_break',
  empty: 'plain',
};

function proseBlockToken(b: FountainBlock): BlockToken {
  const level = headingLevel(b);
  if (level === 1) return 'chapter';
  if (level === 2) return 'heading';
  if (level >= 3) return 'subheading';
  const t = b.text.trimStart();
  if (/^[-*]\s\[[ xX]\]/.test(t)) return 'checkbox';
  if (/^[-*]\s/.test(t)) return 'bullet';
  return 'plain';
}

export function classifySyntax(blocks: FountainBlock[], mode: string): BlockSyntax[] {
  if (mode === 'screenplay') {
    const types = classify(blocks);
    const boneyard = detectBoneyard(blocks);
    const titleEnd = parseTitlePage(blocks).endIndex;
    return blocks.map((b, i) => {
      let token: BlockToken;
      if (i < titleEnd) token = 'title_field';
      else if (boneyard[i]) token = 'boneyard';
      else token = FOUNTAIN_TO_TOKEN[types[i]] ?? 'action';
      return { token, inline: scanInline(b.text, mode) };
    });
  }
  return blocks.map((b) => ({ token: proseBlockToken(b), inline: scanInline(b.text, mode) }));
}
