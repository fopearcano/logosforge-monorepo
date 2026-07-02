/**
 * Fountain-style screenplay line classifier (pure, testable). Classifies a
 * sequence of document blocks into screenplay element types using simple
 * patterns + neighbour context.
 *
 * Already handled elsewhere: title pages + the boneyard (parseTitlePage /
 * detectBoneyard → subdued decorations in screenplayFormatting), notes ([[…]]),
 * and the dual-dialogue caret (stripped from the cue name). Genuinely unimplemented
 * Fountain niceties: side-by-side dual-dialogue LAYOUT, lyrics (~ lines), and hiding
 * the forced-element markers (. @ !) from the rendered view.
 */

import { NOT_A_CUE } from './cueHeuristics';
import type { FountainBlock, FountainType } from './fountainTypes';

const SCENE_PREFIXES = ['INT./EXT.', 'INT/EXT.', 'I/E.', 'INT.', 'EXT.', 'EST.'];

function isSceneHeading(t: string): boolean {
  if (/^\.[A-Za-z]/.test(t)) return true; // forced ".HEADING" — but not ".45" / ".."
  const up = t.toUpperCase();
  return SCENE_PREFIXES.some((p) => up.startsWith(p));
}

function isAllCaps(t: string): boolean {
  return /[A-Za-z]/.test(t) && t === t.toUpperCase() && !/[a-z]/.test(t);
}

function isTransition(t: string): boolean {
  if (t.startsWith('>') && !t.endsWith('<')) return true; // forced
  // A short line ending in "TO:" (any case) — "CUT TO:", "Dissolve to:".
  return t.split(/\s+/).length <= 4 && /\bTO:$/.test(t.toUpperCase());
}

const isParenthetical = (t: string) => t.startsWith('(') && t.endsWith(')');
const isNote = (t: string) => t.startsWith('[[') && t.endsWith(']]');
const isCentered = (t: string) => t.startsWith('>') && t.endsWith('<');
const isPageBreak = (t: string) => /^=+$/.test(t) && t.length >= 3;
const isSynopsis = (t: string) => t.startsWith('=') && !isPageBreak(t);
const isLyrics = (t: string) => t.startsWith('~');

function hasContentAfter(blocks: FountainBlock[], i: number): boolean {
  const next = blocks[i + 1];
  if (!next || next.isHeading) return false;
  return next.text.trim() !== '';
}

/**
 * A line that reads as a fresh character cue rather than a continuation of the
 * previous speech: short and name-like (a trailing (V.O.)/(CONT'D) is ignored),
 * with no sentence punctuation. Used to start a NEW cue directly after dialogue
 * even without the Fountain blank line, so single-spaced scripts still format.
 */
function looksLikeCharacterCue(t: string): boolean {
  const name = t.replace(/\s*\([^)]*\)\s*$/, '').trim();
  if (!name) return false;
  if (/[.!?,:;]/.test(name)) return false;
  if (NOT_A_CUE.has(name.toLowerCase())) return false; // SUDDENLY, THE END, CUT…
  return name.split(/\s+/).length <= 3;
}

/** Classify every block; index-aligned with the input. */
export function classify(blocks: FountainBlock[]): FountainType[] {
  const out: FountainType[] = [];
  let prev: FountainType = 'empty';

  for (let i = 0; i < blocks.length; i += 1) {
    const b = blocks[i];
    const t = b.text.trim();
    let type: FountainType;

    if (b.isHeading) type = 'section';
    else if (t === '') type = 'empty';
    else if (isPageBreak(t)) type = 'page_break';
    else if (t.startsWith('#')) type = 'section';
    else if (isSynopsis(t)) type = 'synopsis';
    else if (isNote(t)) type = 'note';
    else if (isCentered(t)) type = 'centered';
    else if (isTransition(t)) type = 'transition';
    else if (isSceneHeading(t)) type = 'scene_heading';
    else if (t.startsWith('!')) type = 'action'; // forced action
    else if (t.startsWith('@')) type = 'character'; // forced character
    else if (isLyrics(t)) type = 'lyrics'; // forced lyric (~)
    else if (
      isParenthetical(t) &&
      (prev === 'character' || prev === 'parenthetical' || prev === 'dialogue')
    )
      // A parenthetical is dialogue-context only when it actually follows a cue /
      // parenthetical / dialogue. A standalone "(aside)" inside action is action.
      type = 'parenthetical';
    else if (prev === 'character')
      type = 'dialogue'; // the speech directly under a cue
    else if (prev === 'parenthetical' || prev === 'dialogue')
      // continued speech — unless this line is clearly a NEW all-caps cue (so a
      // single-spaced script, or a new cue after a standalone stage-direction
      // parenthetical, still formats correctly).
      type =
        isAllCaps(t) && looksLikeCharacterCue(t) && hasContentAfter(blocks, i)
          ? 'character'
          : 'dialogue';
    else if (isAllCaps(t) && looksLikeCharacterCue(t) && hasContentAfter(blocks, i))
      // A bare ALL-CAPS cue (start of a block / after action). Guard with
      // looksLikeCharacterCue so "WHAT IS THIS?", "NO ENTRY", "SUDDENLY" and
      // other emphatic all-caps action lines are NOT mistaken for speakers.
      type = 'character';
    else type = 'action';

    out.push(type);
    prev = type;
  }
  return out;
}

const LABELS: Record<string, string> = {
  scene_heading: 'Scene Heading',
  action: 'Action',
  character: 'Character',
  dialogue: 'Dialogue',
  parenthetical: 'Parenthetical',
  transition: 'Transition',
  section: 'Section',
  synopsis: 'Synopsis',
  note: 'Note',
  centered: 'Centered',
  lyrics: 'Lyric',
  page_break: 'Page Break',
  empty: 'Action',
};

export function screenplayLabel(type: FountainType | null | undefined): string {
  return type ? LABELS[type] ?? 'Action' : 'Action';
}

function cleanCharacter(t: string): string {
  return t
    .replace(/^@/, '')
    .replace(/\s*\^\s*$/, '') // strip the dual-dialogue caret (CHARACTER ^)
    .replace(/\(.*\)\s*$/, '') // strip trailing (V.O.) etc.
    .trim()
    .toUpperCase();
}

/** Distinct character cues in document order (for autocomplete). */
export function extractCharacters(blocks: FountainBlock[]): string[] {
  const types = classify(blocks);
  const seen = new Set<string>();
  blocks.forEach((b, i) => {
    if (types[i] === 'character') {
      const name = cleanCharacter(b.text.trim());
      if (name) seen.add(name);
    }
  });
  return [...seen];
}

/** Distinct scene headings (for autocomplete). */
export function extractSceneHeadings(blocks: FountainBlock[]): string[] {
  const types = classify(blocks);
  const seen = new Set<string>();
  blocks.forEach((b, i) => {
    if (types[i] === 'scene_heading') {
      const s = b.text.trim().replace(/^\./, '');
      if (s) seen.add(s.toUpperCase());
    }
  });
  return [...seen];
}

/** Distinct transitions used (for autocomplete). */
export function extractTransitions(blocks: FountainBlock[]): string[] {
  const types = classify(blocks);
  const seen = new Set<string>();
  blocks.forEach((b, i) => {
    if (types[i] === 'transition') {
      const s = b.text.trim().replace(/^>/, '').trim();
      if (s) seen.add(s.toUpperCase());
    }
  });
  return [...seen];
}
