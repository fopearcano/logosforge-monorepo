/**
 * Builds ProseMirror decorations for Graphic-Novel mode: block element classes
 * (gn-page / gn-panel / gn-cue / gn-dialogue / gn-caption / gn-sfx / gn-paren) from
 * the classifier, plus inline label/name/sound spans. Non-destructive — the
 * document stays plain text. PAGE/PANEL are styled whether written as native h2/h3
 * headings (via heading CSS) or as plain-text markers (gn-page / gn-panel here).
 */

import { Decoration, DecorationSet } from '@tiptap/pm/view';

import { docToFountainBlocks } from '../screenplay/screenplayFormatting';
import { classifyGn, gnInlineRanges, type GnType } from './graphicNovelClassifier';

const BLOCK_CLASS: Partial<Record<GnType, string>> = {
  page: 'gn-page',
  panel: 'gn-panel',
  cue: 'gn-cue',
  paren: 'gn-paren',
  dialogue: 'gn-dialogue',
  caption: 'gn-caption',
  sfx: 'gn-sfx',
};

export function buildGnDecorations(doc: any): DecorationSet {
  const blocks = docToFountainBlocks(doc);
  const types = classifyGn(blocks);
  const decos: Decoration[] = [];

  doc.forEach((node: any, offset: number, index: number) => {
    if (node.type.name !== 'paragraph') return;
    const type = types[index];
    const cls = type ? BLOCK_CLASS[type] : undefined;
    if (cls) decos.push(Decoration.node(offset, offset + node.nodeSize, { class: cls }));

    // Paragraphs contain only text, so a char index maps directly to a position.
    const base = offset + 1;
    for (const r of gnInlineRanges(node.textContent, type)) {
      if (r.to > r.from) {
        decos.push(Decoration.inline(base + r.from, base + r.to, { class: r.className }));
      }
    }
  });
  return DecorationSet.create(doc, decos);
}
