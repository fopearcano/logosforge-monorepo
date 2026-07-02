/**
 * Builds ProseMirror decorations for Stage-Script mode: block element classes
 * (sp-scene_heading / sp-character / sp-parenthetical / sp-dialogue / sp-action)
 * from the classifier. The stage CSS re-styles these sp-* classes (centered cues
 * and dialogue, italic action). Non-destructive — the document stays plain text;
 * ACT/SCENE typed as headings stay native h2/h3 (centered via the stage CSS).
 */

import { Decoration, DecorationSet } from '@tiptap/pm/view';

import { docToFountainBlocks } from '../screenplay/screenplayFormatting';
import { classifyStage, type StageType } from './stageClassifier';

const BLOCK_CLASS: Record<StageType, string | undefined> = {
  scene_heading: 'sp-scene_heading',
  character: 'sp-character',
  parenthetical: 'sp-parenthetical',
  dialogue: 'sp-dialogue',
  action: 'sp-action',
  empty: undefined,
};

export function buildStageDecorations(doc: any): DecorationSet {
  const blocks = docToFountainBlocks(doc);
  const types = classifyStage(blocks);
  const decos: Decoration[] = [];

  doc.forEach((node: any, offset: number, index: number) => {
    if (node.type.name !== 'paragraph') return;
    const cls = BLOCK_CLASS[types[index]];
    if (cls) decos.push(Decoration.node(offset, offset + node.nodeSize, { class: cls }));
  });
  return DecorationSet.create(doc, decos);
}
