/**
 * Collect bounded editor context for an AI request (selection + current block +
 * nearby text + caret coords). Uses the pure helpers to keep context limited.
 */

import type { Editor } from '@tiptap/react';

import { boundedContext } from './selectionContext';
import type { EditorContext } from '../littleboyTypes';

const NEARBY_RADIUS = 800; // ProseMirror positions either side of the selection

interface Options {
  mode: string;
  documentTitle?: string;
  screenplayElement?: string | null;
}

export function collectEditorContext(editor: Editor, opts: Options): EditorContext {
  const { from, to } = editor.state.selection;
  const doc = editor.state.doc;
  const selection = from !== to ? doc.textBetween(from, to, '\n', ' ') : '';
  const block = editor.state.selection.$from.parent.textContent;

  const size = doc.content.size;
  const start = Math.max(0, from - NEARBY_RADIUS);
  const end = Math.min(size, to + NEARBY_RADIUS);
  const nearby = boundedContext(doc.textBetween(start, end, '\n', ' '));

  let coords = { left: 0, top: 0, bottom: 0 };
  try {
    const c = editor.view.coordsAtPos(from);
    coords = { left: c.left, top: c.top, bottom: c.bottom };
  } catch {
    /* coords are best-effort (e.g. when the editor isn't laid out yet) */
  }

  return {
    selection,
    block,
    nearby,
    from,
    to,
    mode: opts.mode,
    screenplayElement: opts.screenplayElement ?? null,
    documentTitle: opts.documentTitle,
    coords,
  };
}
