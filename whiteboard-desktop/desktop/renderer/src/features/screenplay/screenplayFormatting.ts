/**
 * Builds ProseMirror decorations for Screenplay mode:
 *  - title-page metadata (subdued) at the top of the document;
 *  - boneyard / omitted text (subdued) wherever it appears;
 *  - block element classes (sp-scene_heading, sp-character, …) from the classifier;
 *  - inline emphasis (bold/italic/underline) + dimmed markers from the parser.
 *
 * Non-destructive: the document stays plain Fountain-compatible text.
 * `decorationsForDoc` memoizes by doc identity so selection-only state updates
 * don't reclassify (the plugin's decorations prop runs on every view update).
 */

import { Decoration, DecorationSet } from '@tiptap/pm/view';

import { parseEmphasis } from './fountainParser';
import { detectBoneyard } from './screenplayBoneyard';
import { classify } from './screenplayClassifier';
import { parseTitlePage } from './screenplayTitlePage';
import type { FountainBlock, FountainType } from './fountainTypes';

/** Length of a leading forcing marker to hide for a forced element (else 0). */
function forcedMarkerLen(type: FountainType, text: string): number {
  switch (type) {
    case 'scene_heading':
      return /^\.[A-Za-z]/.test(text) ? 1 : 0; // forced ".HEADING" (not ".." / ".5")
    case 'character':
      return text.startsWith('@') ? 1 : 0;
    case 'action':
      return text.startsWith('!') ? 1 : 0;
    case 'lyrics':
      return text.startsWith('~') ? 1 : 0;
    case 'transition':
      return text.startsWith('>') ? 1 : 0;
    default:
      return 0;
  }
}

export function docToFountainBlocks(doc: any): FountainBlock[] {
  const blocks: FountainBlock[] = [];
  doc.forEach((node: any) => {
    blocks.push({
      text: node.textContent,
      isHeading: node.type.name === 'heading',
      level: node.attrs?.level,
    });
  });
  return blocks;
}

export function buildDecorations(doc: any): DecorationSet {
  const blocks = docToFountainBlocks(doc);
  const types = classify(blocks);
  const boneyard = detectBoneyard(blocks);
  const titleEnd = parseTitlePage(blocks).endIndex;

  // Dual dialogue: a character cue ending in "^" floats its speech beside the
  // preceding cue's. Mark the left group, the right (dual) group, the blank
  // between them (collapsed), and a clear on the block after.
  const dual: (string | null)[] = new Array(blocks.length).fill(null);
  const isSpeech = (k: number) =>
    types[k] === 'dialogue' || types[k] === 'parenthetical' || types[k] === 'lyrics';
  for (let i = 0; i < blocks.length; i += 1) {
    if (types[i] !== 'character' || !/\^\s*$/.test(blocks[i].text.trim())) continue;
    let leftCue = -1;
    for (let k = i - 1; k >= 0; k -= 1) {
      if (types[k] === 'character') { leftCue = k; break; }
      if (types[k] === 'scene_heading' || types[k] === 'section' || types[k] === 'transition') break;
    }
    if (leftCue < 0) continue; // no partner cue in this scene → render normally
    let lEnd = leftCue;
    for (let k = leftCue + 1; k < i && isSpeech(k); k += 1) lEnd = k;
    let rEnd = i;
    for (let k = i + 1; k < blocks.length && isSpeech(k); k += 1) rEnd = k;
    for (let k = leftCue; k <= lEnd; k += 1) dual[k] = 'sp-dual-left';
    for (let k = lEnd + 1; k < i; k += 1) dual[k] = 'sp-dual-gap';
    for (let k = i; k <= rEnd; k += 1) dual[k] = 'sp-dual-right';
    if (rEnd + 1 < blocks.length && dual[rEnd + 1] == null) dual[rEnd + 1] = 'sp-dual-after';
  }

  const decos: Decoration[] = [];

  doc.forEach((node: any, offset: number, index: number) => {
    if (node.type.name !== 'paragraph') return;
    const from = offset;
    const to = offset + node.nodeSize;

    // Title page + boneyard are rendered subdued and skip element/emphasis.
    if (index < titleEnd) {
      decos.push(Decoration.node(from, to, { class: 'sp-title-page' }));
      return;
    }
    if (boneyard[index]) {
      decos.push(Decoration.node(from, to, { class: 'sp-boneyard' }));
      return;
    }

    // Block element formatting + dual-dialogue float class.
    const type = types[index];
    if (type && type !== 'action' && type !== 'empty') {
      decos.push(Decoration.node(from, to, { class: `sp-${type}` }));
    }
    if (dual[index]) {
      decos.push(Decoration.node(from, to, { class: dual[index] as string }));
    }

    // Inline emphasis + hidden forcing markers (paragraphs are plain text, so a
    // char index maps directly to a document position).
    const text: string = node.textContent;
    const base = offset + 1;

    const lead = type ? forcedMarkerLen(type, text) : 0;
    if (lead > 0) decos.push(Decoration.inline(base, base + lead, { class: 'sp-marker' }));
    if (type === 'character') {
      const caret = text.match(/(\s*\^\s*)$/); // trailing dual-dialogue caret
      if (caret) {
        decos.push(Decoration.inline(base + text.length - caret[1].length, base + text.length, { class: 'sp-marker' }));
      }
    }

    for (const r of parseEmphasis(text)) {
      if (r.to > r.from) {
        decos.push(Decoration.inline(base + r.from, base + r.to, { class: r.className }));
      }
    }
  });
  return DecorationSet.create(doc, decos);
}

// Memoize by doc identity. ProseMirror docs are immutable, so an unchanged `doc`
// object means unchanged content — a selection-only state update reuses the cached
// DecorationSet instead of reclassifying the whole screenplay each render.
let memoDoc: unknown = null;
let memoSet: DecorationSet | null = null;

export function decorationsForDoc(doc: any): DecorationSet {
  if (doc === memoDoc && memoSet) return memoSet;
  memoDoc = doc;
  memoSet = buildDecorations(doc);
  return memoSet;
}
