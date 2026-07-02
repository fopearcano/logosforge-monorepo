/**
 * Stage-script element inference (frontend only, pure).
 *
 * Mirrors the Graphic-Novel classifier but for theatre scripts, emitting the
 * SAME sp-* classes the screenplay engine uses — the stage CSS
 * (data-writing-mode="stage_script" .sp-*) re-styles them: centered character
 * cues, centered dialogue, centered parentheticals, italic action.
 *
 * Conservative: only confident cues are detected, so plain stage-direction prose
 * is never mis-centered. ACT/SCENE-style lines are scene headings; a short
 * name-like line followed by a real line is a character cue -> the next line is
 * dialogue; parentheticals are stage directions; everything else is action.
 */

import { isAllCapsName, looksLikeName } from '../screenplay/cueHeuristics';
import type { FountainBlock } from '../screenplay/fountainTypes';

export type StageType =
  | 'scene_heading'
  | 'character'
  | 'parenthetical'
  | 'dialogue'
  | 'action'
  | 'empty';

const SCENE_RE = /^(act|scene|prologue|epilogue|intermission|interval|curtain)\b/i;

function isParen(t: string): boolean {
  return t.length > 1 && t.startsWith('(') && t.endsWith(')');
}

/** The character name part of a possible cue (trailing "(…)" and ":" stripped). */
function cueName(t: string): string {
  return t.replace(/\s*\([^)]*\)\s*$/, '').replace(/:\s*$/, '').trim();
}

/** A cue is a short, name-like line — never a Title-Case prose phrase. */
function looksLikeCue(t: string): boolean {
  return looksLikeName(cueName(t));
}

/** A strong cue (ALL-CAPS name) — used to start a NEW cue right after dialogue. */
function isStrongCue(t: string): boolean {
  return isAllCapsName(cueName(t)) && looksLikeCue(t);
}

export function classifyStage(blocks: FountainBlock[]): StageType[] {
  const out: StageType[] = [];
  let expectingDialogue = false; // set after a character cue

  blocks.forEach((b, i) => {
    if (b.isHeading) {
      out.push('scene_heading');
      expectingDialogue = false;
      return;
    }
    const t = b.text.trim();
    if (!t) {
      out.push('empty');
      expectingDialogue = false;
      return;
    }
    if (SCENE_RE.test(t)) {
      out.push('scene_heading');
      expectingDialogue = false;
      return;
    }
    if (isParen(t)) {
      // A parenthetical between a cue and dialogue keeps the dialogue coming;
      // a standalone "(stage direction)" leaves the state untouched.
      out.push('parenthetical');
      return;
    }
    const next = blocks[i + 1];
    const nextText = next?.text.trim() ?? '';
    const hasDialogueAfter =
      !!next && !next.isHeading && nextText.length > 0 && !SCENE_RE.test(nextText);
    if (expectingDialogue) {
      // Continued speech — unless THIS line is itself a strong (ALL-CAPS) cue,
      // in which case a new character is speaking (a missing blank line, or the
      // previous "cue" was a false positive). Never flip on Title-Case dialogue.
      if (hasDialogueAfter && isStrongCue(t)) {
        out.push('character');
        expectingDialogue = true;
        return;
      }
      out.push('dialogue');
      expectingDialogue = false;
      return;
    }
    if (hasDialogueAfter && looksLikeCue(t)) {
      out.push('character');
      expectingDialogue = true;
      return;
    }
    out.push('action');
    expectingDialogue = false;
  });
  return out;
}
