/**
 * The Stage-Script TipTap extension — a decorations-only plugin that applies
 * theatre-script formatting (sp-* classes, re-styled by the stage CSS) when the
 * writing mode is stage_script. The on/off flag lives in plugin state (set via a
 * meta transaction by the editor on mode change) — reliable, no DOM-timing race.
 *
 * Decorations only: no keyboard bindings, so it composes cleanly alongside the
 * Screenplay and Graphic-Novel extensions.
 */

import { Extension } from '@tiptap/core';
import { Plugin, PluginKey } from '@tiptap/pm/state';

import { buildStageDecorations } from './stageFormatting';

export const stageKey = new PluginKey('stageMode');

export const StageEditing = Extension.create({
  name: 'stageEditing',

  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: stageKey,
        state: {
          init: () => ({ stage: false }),
          apply: (tr, value) => {
            const meta = tr.getMeta(stageKey);
            return meta ? { stage: !!meta.stage } : value;
          },
        },
        props: {
          decorations(state) {
            return stageKey.getState(state)?.stage ? buildStageDecorations(state.doc) : null;
          },
        },
      }),
    ];
  },
});
