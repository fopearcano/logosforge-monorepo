/**
 * Graphic-novel element inference (frontend only, pure).
 *
 * Mirrors the Screenplay classifier but for comic-script structure: PAGE/PANEL
 * are native headings (h2/h3) OR terse plain-text headers ("PAGE ONE", "PANEL 1");
 * paragraphs are inferred as caption / sfx / cue → dialogue / parenthetical, with
 * the rest left as panel description. Conservative — only confident matches are
 * classified, so plain description prose is never mis-centered.
 *
 * Two comic conventions beyond the screenplay model are supported: plain-text
 * PAGE/PANEL markers, and inline dialogue ("MARA: It's keeping time.") where the
 * speaker and speech share one line.
 *
 * Inline spans (label / name / sound) are emitted for the deterministic cases:
 * the CAPTION/SFX prefix, a caption speaker "(Name)", the SFX sound text, and an
 * inline dialogue speaker "NAME:".
 */

import { isAllCapsName, looksLikeName } from '../screenplay/cueHeuristics';
import type { FountainBlock } from '../screenplay/fountainTypes';

export type GnType =
  | 'page'
  | 'panel'
  | 'cue'
  | 'paren'
  | 'dialogue'
  | 'caption'
  | 'sfx'
  | 'description'
  | 'empty';

// A real caption / SFX cue carries a delimiter ("CAPTION:", "CAPTION (Nan)",
// "SFX: BOOM") — a bare leading word ("Caption this moment", "Sound travels…")
// is ordinary prose and must NOT be boxed.
const CAPTION_RE = /^caption\s*[:(]/i;
const SFX_RE = /^(sfx|sound|fx)\s*:/i;

// A "PAGE …" / "PANEL …" header written as plain text (not a native heading).
const PAGE_LEAD = /^page\b/i;
const PANEL_LEAD = /^panel\b/i;

/**
 * A terse plain-text PAGE/PANEL marker: confident only when the line is short AND
 * either ALL-CAPS ("PAGE ONE", "PANEL 1") or numbered right after the keyword
 * ("Page 1", "Panel 2"). So prose that merely starts with the word — "Page after
 * page", "Panel discussions resumed", "Page one of two." — is never mistaken for
 * structure, and a PAGE/PANEL line can never be misread as a cue or dialogue.
 */
function isMarker(t: string, lead: RegExp): boolean {
  if (t.length > 48 || !lead.test(t)) return false;
  const caps = t === t.toUpperCase() && /[A-Z]/.test(t);
  const numbered = /^(?:page|panel)\b[\s.:#\-]*\d/i.test(t);
  return caps || numbered;
}

function isParen(t: string): boolean {
  return t.length > 1 && t.length <= 40 && t.startsWith('(') && t.endsWith(')');
}

/** The character name part of a possible cue (a trailing "(…)" is stripped). */
function cueName(t: string): string {
  return t.replace(/\s*\([^)]*\)\s*$/, '').trim();
}

/** A cue is a short, name-like line — never a Title-Case prose phrase. */
function looksLikeCue(t: string): boolean {
  return looksLikeName(cueName(t));
}

/** A strong cue (ALL-CAPS name) — used to start a NEW cue right after dialogue. */
function isStrongCue(t: string): boolean {
  return isAllCapsName(cueName(t)) && looksLikeCue(t);
}

/**
 * Inline comic dialogue "NAME: speech" (speaker + speech on one line). Returns the
 * speaker name, or null. The speaker must be a strong (ALL-CAPS) name that isn't a
 * known interstitial, so prose like "Note: remember this" or "CUT: to black" is
 * not mistaken for dialogue. CAPTION:/SFX: are matched earlier and never reach here.
 */
function inlineDialogueName(t: string): string | null {
  const idx = t.indexOf(':');
  if (idx < 1 || idx > 28) return null;
  if (!t.slice(idx + 1).trim()) return null; // must carry speech after the colon
  const nm = cueName(t.slice(0, idx));
  return isAllCapsName(nm) && looksLikeName(nm) ? nm : null;
}

export function classifyGn(blocks: FountainBlock[]): GnType[] {
  const out: GnType[] = [];
  let expectingDialogue = false; // set after a cue (or a parenthetical)

  blocks.forEach((b, i) => {
    if (b.isHeading) {
      out.push((b.level ?? 2) >= 3 ? 'panel' : 'page');
      expectingDialogue = false;
      return;
    }
    const t = b.text.trim();
    if (!t) {
      out.push('empty');
      expectingDialogue = false;
      return;
    }
    // Plain-text PAGE / PANEL headers — structural, never a cue/dialogue.
    if (isMarker(t, PANEL_LEAD)) {
      out.push('panel');
      expectingDialogue = false;
      return;
    }
    if (isMarker(t, PAGE_LEAD)) {
      out.push('page');
      expectingDialogue = false;
      return;
    }
    if (CAPTION_RE.test(t)) {
      out.push('caption');
      expectingDialogue = false;
      return;
    }
    if (SFX_RE.test(t)) {
      out.push('sfx');
      expectingDialogue = false;
      return;
    }
    if (isParen(t)) {
      // A parenthetical between a cue and its dialogue keeps the dialogue coming
      // (leave expectingDialogue as-is); a STANDALONE "(stage direction)" must NOT
      // start expecting dialogue, or it would steal the next character cue.
      out.push('paren');
      return;
    }
    // Inline dialogue: "MARA: It's keeping time." — a self-contained balloon.
    if (inlineDialogueName(t)) {
      out.push('dialogue');
      expectingDialogue = false;
      return;
    }
    // A cue must be followed by a real dialogue line (not a heading / caption /
    // sfx / page-panel marker).
    const next = blocks[i + 1];
    const nextText = next?.text.trim() ?? '';
    const hasDialogueAfter =
      !!next && !next.isHeading && nextText.length > 0 &&
      !CAPTION_RE.test(nextText) && !SFX_RE.test(nextText) &&
      !isMarker(nextText, PAGE_LEAD) && !isMarker(nextText, PANEL_LEAD);
    if (expectingDialogue) {
      // Continued speech — unless THIS line is itself a strong (ALL-CAPS) cue,
      // so a new speaker (or a false-positive recovery) starts a fresh balloon.
      if (hasDialogueAfter && isStrongCue(t)) {
        out.push('cue');
        expectingDialogue = true;
        return;
      }
      out.push('dialogue');
      expectingDialogue = false;
      return;
    }
    if (hasDialogueAfter && looksLikeCue(t)) {
      out.push('cue');
      expectingDialogue = true;
      return;
    }
    out.push('description');
    expectingDialogue = false;
  });
  return out;
}

export interface GnInlineRange {
  from: number;
  to: number;
  className: string;
}

/** Inline spans within a classified block (char offsets into the block text). */
export function gnInlineRanges(text: string, type: GnType): GnInlineRange[] {
  const out: GnInlineRange[] = [];
  if (type === 'caption') {
    const lab = /^caption:?/i.exec(text); // "CAPTION" or "CAPTION:"
    if (lab) out.push({ from: 0, to: lab[0].length, className: 'gn-label' });
    const name = /^caption\s*(\([^)]*\))/i.exec(text); // CAPTION (Speaker)
    if (name) {
      const start = text.indexOf(name[1]);
      out.push({ from: start, to: start + name[1].length, className: 'gn-name' });
    }
  } else if (type === 'sfx') {
    const lab = /^(sfx|sound|fx):?/i.exec(text);
    if (lab) out.push({ from: 0, to: lab[0].length, className: 'gn-label' });
    const colon = text.indexOf(':');
    if (colon >= 0 && colon < text.length - 1) {
      let s = colon + 1;
      while (s < text.length && /\s/.test(text[s])) s += 1;
      if (s < text.length) out.push({ from: s, to: text.length, className: 'gn-sound' });
    }
  } else if (type === 'dialogue') {
    // Inline dialogue "NAME: speech" — mark the "NAME:" speaker prefix.
    if (inlineDialogueName(text)) {
      out.push({ from: 0, to: text.indexOf(':') + 1, className: 'gn-name' });
    }
  }
  return out;
}
