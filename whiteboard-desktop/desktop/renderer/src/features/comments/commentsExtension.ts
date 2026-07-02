/**
 * Inline comments as ProseMirror decorations (mirrors editorToolsExtension).
 *
 * Holds the active comment "marks" (id + block index + char span) in plugin
 * state via a meta transaction, paints a highlight over each span, and routes a
 * click on a highlight to onCommentClick(id). Marks are reconciled to the live
 * text in the React layer (reconcileMarks) before being pushed in.
 */

import { Extension } from '@tiptap/core';
import { Plugin, PluginKey, type EditorState } from '@tiptap/pm/state';
import { Decoration, DecorationSet } from '@tiptap/pm/view';

export interface CommentMark {
  id: string;
  blockIndex: number;
  from: number; // char offset within the block's text
  to: number; // exclusive
  resolved: boolean;
}

export interface CommentsPluginState {
  marks: CommentMark[];
  activeId: string | null; // the comment whose popover is open (emphasised)
}

const INITIAL: CommentsPluginState = { marks: [], activeId: null };

export const commentsKey = new PluginKey<CommentsPluginState>('comments');

export function commentsMeta(marks: CommentMark[], activeId: string | null): CommentsPluginState {
  return { marks, activeId };
}

function build(state: EditorState, s: CommentsPluginState): DecorationSet {
  if (!s.marks.length) return DecorationSet.empty;
  const byBlock = new Map<number, CommentMark[]>();
  for (const m of s.marks) {
    const list = byBlock.get(m.blockIndex);
    if (list) list.push(m);
    else byBlock.set(m.blockIndex, [m]);
  }
  const decos: Decoration[] = [];
  let index = 0;
  state.doc.forEach((node, offset) => {
    const marks = byBlock.get(index);
    if (marks) {
      const base = offset + 1; // first text position inside the block
      const max = offset + node.nodeSize - 1; // last text position
      for (const m of marks) {
        const from = Math.max(base, Math.min(base + m.from, max));
        const to = Math.max(base, Math.min(base + m.to, max));
        if (to > from) {
          const cls = [
            'comment-mark',
            m.resolved ? 'comment-mark-resolved' : '',
            m.id === s.activeId ? 'comment-mark-active' : '',
          ]
            .filter(Boolean)
            .join(' ');
          decos.push(Decoration.inline(from, to, { class: cls, 'data-comment-id': m.id }));
        }
      }
    }
    index += 1;
  });
  return DecorationSet.create(state.doc, decos);
}

export interface CommentsOptions {
  onCommentClick?: (id: string) => void;
}

export const CommentsExtension = Extension.create<CommentsOptions>({
  name: 'comments',

  addOptions() {
    return { onCommentClick: undefined };
  },

  addProseMirrorPlugins() {
    const onCommentClick = this.options.onCommentClick;
    return [
      new Plugin<CommentsPluginState>({
        key: commentsKey,
        state: {
          init: () => INITIAL,
          apply: (tr, value) => {
            const meta = tr.getMeta(commentsKey) as CommentsPluginState | undefined;
            return meta ?? value;
          },
        },
        props: {
          decorations(state) {
            const s = commentsKey.getState(state);
            return s ? build(state, s) : null;
          },
          handleClick(_view, _pos, event) {
            const el = (event.target as HTMLElement)?.closest?.('[data-comment-id]') as
              | HTMLElement
              | null;
            const id = el?.getAttribute('data-comment-id');
            if (id) {
              onCommentClick?.(id);
              return true;
            }
            return false;
          },
        },
      }),
    ];
  },
});
