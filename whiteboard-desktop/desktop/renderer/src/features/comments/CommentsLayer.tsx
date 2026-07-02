/**
 * The comments UI layer: a floating "Comment" affordance over a selection, the
 * anchored edit/delete popover for the active comment, and the side panel. Sits
 * next to the editor in WhiteboardPage (which owns the marks → editor highlights).
 */

import { useEffect, useReducer, useRef, useState } from 'react';

import type { Editor } from '@tiptap/react';

import { selectionToDraft } from './commentsAnchor';
import { CommentPopover } from './CommentPopover';
import {
  useCommentsPanelOpen,
  setCommentsPanelOpen,
  useResolvedHidden,
  toggleResolvedHidden,
} from './commentsPanelStore';
import { CommentsWindow } from './CommentsWindow';
import type { CommentsApi } from './useComments';

interface Props {
  editor: Editor | null;
  api: CommentsApi;
  activeId: string | null;
  setActiveId: (id: string | null) => void;
}

/** Absolute ProseMirror position for a (blockIndex, charOffset) anchor. */
function absPos(editor: Editor, blockIndex: number, charOffset: number): number | null {
  let pos: number | null = null;
  let i = 0;
  editor.state.doc.forEach((node, offset) => {
    if (i === blockIndex) {
      const max = offset + node.nodeSize - 1;
      pos = Math.max(offset + 1, Math.min(offset + 1 + charOffset, max));
    }
    i += 1;
  });
  return pos;
}

export function CommentsLayer({ editor, api, activeId, setActiveId }: Props) {
  const panelOpen = useCommentsPanelOpen();
  const hideResolved = useResolvedHidden();
  const [selRect, setSelRect] = useState<{ top: number; left: number } | null>(null);
  const [, reflow] = useReducer((n: number) => n + 1, 0); // re-place the popover on scroll/resize

  // Track the editor selection → show the floating "Comment" button above it, and
  // keep both it and the open popover pinned to the text as the page scrolls or
  // the window resizes (their positions are viewport coords from coordsAtPos).
  useEffect(() => {
    if (!editor) return undefined;
    const update = () => {
      const { from, to, empty } = editor.state.selection;
      if (empty || to <= from || !editor.isFocused) {
        setSelRect(null);
        return;
      }
      try {
        const a = editor.view.coordsAtPos(from);
        const b = editor.view.coordsAtPos(to);
        const top = Math.max(6, Math.min(a.top, b.top) - 38); // never above the viewport
        const left = Math.max(8, Math.min((a.left + b.left) / 2, window.innerWidth - 120));
        setSelRect({ top, left });
      } catch {
        setSelRect(null);
      }
    };
    const clear = () => setTimeout(() => setSelRect(null), 150);
    const onScrollResize = () => {
      update(); // re-place the FAB
      reflow(); // re-place the open popover (its position is derived in render)
    };
    editor.on('selectionUpdate', update);
    editor.on('blur', clear);
    window.addEventListener('scroll', onScrollResize, true); // capture: catches the editor's scroller
    window.addEventListener('resize', onScrollResize);
    return () => {
      editor.off('selectionUpdate', update);
      editor.off('blur', clear);
      window.removeEventListener('scroll', onScrollResize, true);
      window.removeEventListener('resize', onScrollResize);
    };
  }, [editor]);

  const addFromSelection = async () => {
    if (!editor) return;
    const draft = selectionToDraft(editor);
    if (!draft) return;
    setSelRect(null);
    const created = await api.add(draft);
    if (created) {
      setCommentsPanelOpen(true);
      setActiveId(created.id);
    }
  };

  const jumpTo = (id: string) => {
    const c = api.comments.find((x) => x.id === id);
    if (editor && c) {
      const pos = absPos(editor, c.anchor.block_index, c.anchor.from_offset);
      if (pos != null) editor.chain().focus().setTextSelection(pos).scrollIntoView().run();
    }
    setActiveId(id);
  };

  // Keyboard nav: Alt+↓ / Alt+↑ jump to the next / previous UNRESOLVED comment in
  // document order (scroll + open its popover) — the review-and-resolve flow. Wraps
  // around. Ref-backed so the listener stays stable while reading the latest state.
  const navRef = useRef<(dir: 1 | -1) => void>(() => {});
  navRef.current = (dir) => {
    const list = api.comments
      .filter((c) => !c.resolved)
      .sort(
        (a, b) =>
          a.anchor.block_index - b.anchor.block_index || a.anchor.from_offset - b.anchor.from_offset,
      );
    if (!list.length) return;
    const cur = list.findIndex((c) => c.id === activeId);
    const idx = cur === -1 ? (dir === 1 ? 0 : list.length - 1) : (cur + dir + list.length) % list.length;
    jumpTo(list[idx].id);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        navRef.current(1);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        navRef.current(-1);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const active = api.comments.find((c) => c.id === activeId) ?? null;
  let popoverPos: { top: number; left: number } | null = null;
  if (editor && active) {
    const pos = absPos(editor, active.anchor.block_index, active.anchor.from_offset);
    if (pos != null) {
      try {
        const c = editor.view.coordsAtPos(pos);
        popoverPos = { top: c.bottom + 6, left: Math.max(8, Math.min(c.left, window.innerWidth - 332)) };
      } catch {
        popoverPos = null;
      }
    }
  }

  return (
    <>
      {selRect && (
        <button
          type="button"
          className="comment-add-fab"
          style={{ top: selRect.top, left: selRect.left }}
          onMouseDown={(e) => e.preventDefault()}
          onClick={addFromSelection}
          title="Comment on the selected text"
          aria-label="Add a comment on the selected text"
        >
          + Comment
        </button>
      )}

      {active && popoverPos && (
        <CommentPopover
          comment={active}
          top={popoverPos.top}
          left={popoverPos.left}
          onSave={(body) => api.edit(active.id, { body })}
          onReply={(body) => void api.addReply(active.id, body)}
          onDeleteReply={(replyId) => void api.removeReply(active.id, replyId)}
          onToggleResolved={() => api.edit(active.id, { resolved: !active.resolved })}
          onDelete={() => {
            void api.remove(active.id);
            setActiveId(null);
          }}
          onClose={() => setActiveId(null)}
        />
      )}

      {panelOpen && (
        <CommentsWindow
          comments={api.comments}
          hideResolved={hideResolved}
          onToggleHideResolved={toggleResolvedHidden}
          onSelect={jumpTo}
          onToggleResolved={(id) => {
            const c = api.comments.find((x) => x.id === id);
            if (c) void api.edit(id, { resolved: !c.resolved });
          }}
          onDelete={(id) => {
            void api.remove(id);
            if (activeId === id) setActiveId(null);
          }}
          onClose={() => setCommentsPanelOpen(false)}
        />
      )}

      {api.error && (
        <div className="wb-toast wb-toast-error" role="alert">
          {api.error}
        </div>
      )}
    </>
  );
}
