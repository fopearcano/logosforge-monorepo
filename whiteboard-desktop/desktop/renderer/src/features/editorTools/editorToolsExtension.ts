/**
 * The Nerd Mode editor tools, as a single TipTap/ProseMirror extension.
 *
 * Keeps all the view logic out of the main editor component. Tool state (which
 * tools are on, the mode, the folded heads) is held in plugin state and pushed
 * in via a meta transaction (no DOM-timing races). The extension renders, all as
 * non-destructive decorations:
 *   - line numbers  (node deco `data-ln` + CSS gutter ::before),
 *   - current line  (node deco `wb-current-line`),
 *   - folding       (node deco `wb-folded-hidden` to hide bodies, `wb-fold-*`
 *                    on heads, + a clickable gutter widget toggle),
 *   - syntax        (node + inline `wb-syn-*` classes, coloured by the theme).
 *
 * Folding never edits the document, so hidden text is always saved/restored.
 */

import { Extension } from '@tiptap/core';
import { Plugin, PluginKey, type EditorState } from '@tiptap/pm/state';
import { Decoration, DecorationSet } from '@tiptap/pm/view';

import { docToFountainBlocks } from '../screenplay/screenplayFormatting';
import type { EditorToolsState } from './editorToolTypes';
import { findFoldableRegions, hiddenBlocks } from './folding/foldingModel';
import { classifySyntax } from './syntax/syntaxClassifier';

export interface EditorToolsPluginState {
  lineNumbers: boolean;
  currentLineHighlight: boolean;
  folding: boolean;
  syntax: boolean;
  mode: string;
  folds: number[];
}

const INITIAL: EditorToolsPluginState = {
  lineNumbers: false,
  currentLineHighlight: false,
  folding: false,
  syntax: false,
  mode: 'novel',
  folds: [],
};

export const editorToolsKey = new PluginKey<EditorToolsPluginState>('editorTools');

export interface EditorToolsOptions {
  onToggleFold?: (index: number) => void;
}

/** Build the meta payload pushed into the plugin when settings/folds change. */
export function editorToolsMeta(
  tools: EditorToolsState,
  mode: string,
  folds: ReadonlySet<number>,
): EditorToolsPluginState {
  return {
    lineNumbers: tools.lineNumbers,
    currentLineHighlight: tools.currentLineHighlight,
    folding: tools.folding,
    syntax: tools.syntax,
    mode,
    folds: [...folds],
  };
}

function foldToggleDOM(collapsed: boolean, onClick: () => void): HTMLElement {
  const el = document.createElement('span');
  el.className = 'wb-fold-toggle';
  el.textContent = collapsed ? '▸' : '▾';
  el.setAttribute('contenteditable', 'false');
  el.setAttribute('role', 'button');
  el.setAttribute('aria-label', collapsed ? 'Expand block' : 'Collapse block');
  // mousedown before click: don't let the editor steal focus / move the caret.
  el.addEventListener('mousedown', (e) => {
    e.preventDefault();
    e.stopPropagation();
  });
  el.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    onClick();
  });
  return el;
}

function build(
  state: EditorState,
  s: EditorToolsPluginState,
  onToggleFold: (index: number) => void,
): DecorationSet {
  const { doc } = state;
  const blocks = docToFountainBlocks(doc);
  const regions = s.folding ? findFoldableRegions(blocks, s.mode) : [];
  const folded = new Set(s.folds);
  const hidden = s.folding ? hiddenBlocks(regions, folded) : new Set<number>();
  const heads = new Set(regions.map((r) => r.head));
  const syntax = s.syntax ? classifySyntax(blocks, s.mode) : null;
  const currentBlock = s.currentLineHighlight ? state.selection.$from.index(0) : -1;

  const decos: Decoration[] = [];
  let index = 0;
  doc.forEach((node, offset) => {
    const from = offset;
    const to = offset + node.nodeSize;
    const classes: string[] = [];
    const attrs: Record<string, string> = {};

    if (s.lineNumbers) {
      classes.push('wb-ln');
      attrs['data-ln'] = String(index + 1);
    }
    if (index === currentBlock) classes.push('wb-current-line');
    if (s.folding) {
      if (hidden.has(index)) classes.push('wb-folded-hidden');
      if (heads.has(index)) {
        classes.push('wb-fold-head');
        if (folded.has(index)) classes.push('wb-fold-collapsed');
      }
    }
    if (syntax) classes.push(`wb-syn-${syntax[index].token}`);

    if (classes.length) {
      decos.push(Decoration.node(from, to, { ...attrs, class: classes.join(' ') }));
    }

    if (s.folding && heads.has(index) && !hidden.has(index)) {
      const collapsed = folded.has(index);
      const headIndex = index;
      decos.push(
        Decoration.widget(from + 1, () => foldToggleDOM(collapsed, () => onToggleFold(headIndex)), {
          side: -1,
          key: `fold-${headIndex}-${collapsed ? 'c' : 'e'}`,
        }),
      );
    }

    if (syntax && !hidden.has(index)) {
      const base = from + 1; // first text position inside the block
      for (const span of syntax[index].inline) {
        if (span.to > span.from) {
          decos.push(Decoration.inline(base + span.from, base + span.to, { class: `wb-syn-${span.token}` }));
        }
      }
    }
    index += 1;
  });

  return DecorationSet.create(doc, decos);
}

export const EditorTools = Extension.create<EditorToolsOptions>({
  name: 'editorTools',

  addOptions() {
    return { onToggleFold: undefined };
  },

  addProseMirrorPlugins() {
    const onToggleFold = (i: number) => this.options.onToggleFold?.(i);
    return [
      new Plugin<EditorToolsPluginState>({
        key: editorToolsKey,
        state: {
          init: () => INITIAL,
          apply: (tr, value) => {
            const meta = tr.getMeta(editorToolsKey) as Partial<EditorToolsPluginState> | undefined;
            return meta ? { ...value, ...meta } : value;
          },
        },
        props: {
          decorations(state) {
            const s = editorToolsKey.getState(state);
            if (!s) return null;
            if (!s.lineNumbers && !s.currentLineHighlight && !s.folding && !s.syntax) return null;
            return build(state, s, onToggleFold);
          },
        },
      }),
    ];
  },
});
