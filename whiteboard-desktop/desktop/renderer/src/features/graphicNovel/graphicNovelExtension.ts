/**
 * The Graphic-Novel TipTap extension — a decorations-only plugin that applies
 * comic-script formatting (gn-* classes) when the writing mode is graphic_novel.
 * Like the Screenplay engine, the on/off flag lives in plugin state (set via a
 * meta transaction by the editor on mode change) — reliable, no DOM-timing race.
 *
 * Decorations only: no keyboard bindings (GN has no Fountain Tab cycling), so it
 * composes cleanly alongside the Screenplay extension.
 */

import { Extension } from '@tiptap/core';
import { Plugin, PluginKey } from '@tiptap/pm/state';

import { buildGnDecorations } from './graphicNovelFormatting';

export const gnKey = new PluginKey('graphicNovelMode');

export const GraphicNovelEditing = Extension.create({
  name: 'graphicNovelEditing',

  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: gnKey,
        state: {
          init: () => ({ gn: false }),
          apply: (tr, value) => {
            const meta = tr.getMeta(gnKey);
            return meta ? { gn: !!meta.gn } : value;
          },
        },
        props: {
          decorations(state) {
            return gnKey.getState(state)?.gn ? buildGnDecorations(state.doc) : null;
          },
        },
      }),
    ];
  },
});
