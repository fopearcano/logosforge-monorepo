/**
 * The Screenplay TipTap extension — assembles the engine for the editor:
 *  - inference-driven formatting via a decorations plugin (Screenplay mode only);
 *  - keyboard (Tab autocomplete, Shift+Tab, Cmd/Ctrl+B/I/U);
 *  - a backward-compatible `sp` paragraph attribute (older saved docs may carry it).
 *
 * Whether to format is held in plugin state (set via a meta transaction by the
 * editor when the mode changes) — reliable, no DOM-timing race.
 */

import { Extension } from '@tiptap/core';
import { Plugin, PluginKey } from '@tiptap/pm/state';
import type { Editor } from '@tiptap/react';

import type { FountainType } from './fountainTypes';
import { classify } from './screenplayClassifier';
import { decorationsForDoc, docToFountainBlocks } from './screenplayFormatting';
import {
  handleShiftTab,
  handleTab,
  toggleCenterLine,
  wrapMarker,
  wrapNote,
  wrapOmit,
  type AutocompleteContext,
} from './screenplayKeyboard';

export type { AutocompleteContext };

export const fountainKey = new PluginKey('fountainMode');

export interface ScreenplayOptions {
  onAutocomplete?: (ctx: AutocompleteContext) => void;
}

/** The inferred screenplay element at the cursor (for the status indicator). */
export function currentFountainType(editor: Editor): FountainType | null {
  const types = classify(docToFountainBlocks(editor.state.doc));
  const idx = editor.state.selection.$from.index(0);
  return types[idx] ?? null;
}

export const ScreenplayEditing = Extension.create<ScreenplayOptions>({
  name: 'screenplayEditing',

  addOptions() {
    return { onAutocomplete: undefined };
  },

  addGlobalAttributes() {
    return [
      {
        types: ['paragraph'],
        attributes: {
          sp: {
            default: null,
            parseHTML: (el) => el.getAttribute('data-sp'),
            renderHTML: (attrs) => (attrs.sp ? { 'data-sp': attrs.sp } : {}),
          },
        },
      },
    ];
  },

  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: fountainKey,
        state: {
          init: () => ({ screenplay: false }),
          apply: (tr, value) => {
            const meta = tr.getMeta(fountainKey);
            return meta ? { screenplay: !!meta.screenplay } : value;
          },
        },
        props: {
          decorations(state) {
            return fountainKey.getState(state)?.screenplay ? decorationsForDoc(state.doc) : null;
          },
        },
      }),
    ];
  },

  addKeyboardShortcuts() {
    return {
      Tab: () => handleTab(this.editor, this.options.onAutocomplete),
      'Shift-Tab': () => handleShiftTab(this.editor),
      'Mod-b': () => wrapMarker(this.editor, '**'),
      'Mod-i': () => wrapMarker(this.editor, '*'),
      'Mod-u': () => wrapMarker(this.editor, '_'),
      'Mod-Alt-n': () => wrapNote(this.editor), // Note: [[ … ]] (Cmd/Ctrl+Y avoided — it is redo)
      'Mod-Alt-o': () => wrapOmit(this.editor), // Omit selected text into the boneyard /* … */
      'Mod-\\': () => toggleCenterLine(this.editor), // Center line: wrap/unwrap > … <
      // Enter is not bound — see screenplayKeyboard.ts. Cmd/Ctrl+K stays free for Logos.
    };
  },
});
