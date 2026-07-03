/**
 * The manual story outliner — a Dynalist-style editable tree, with hoist/zoom
 * and search/filter. Rendering is a flat list of currently-visible rows
 * (collapsed subtrees skipped; when filtering, matches + ancestors are shown).
 *
 * Keyboard model (only while a row title is focused, so it never fights the
 * editor):
 *   Enter            new sibling below            Shift+Enter   edit details/notes
 *   Tab / Shift+Tab  indent / outdent             Ctrl/Cmd+Enter add child
 *   Arrow Up/Down    move selection               Ctrl/Cmd+Arrow Up/Down  move item
 *   Arrow Left       collapse, else select parent (only at caret start)
 *   Arrow Right      expand, else first child      (only at caret end)
 *   Ctrl/Cmd+]       zoom into item               Ctrl/Cmd+[    zoom out
 *   Backspace        delete when title empty (confirm if it has children)
 *   Escape           deselect (cancel edit)
 */

import { type KeyboardEvent } from 'react';

import {
  ancestorChain,
  buildRows,
  firstChildId,
  hasChildren,
  isFilterActive,
  TYPE_LABELS,
  type OutlineNode,
} from './outlineModel';
import { OutlineRow } from './OutlineRow';
import type { OutlineStore } from './useOutline';

interface Props {
  store: OutlineStore;
  onReveal?: (node: OutlineNode) => void;
  canReveal?: (node: OutlineNode) => boolean;
  /** Delete request — the panel confirms (in-app dialog) parents-with-children. */
  onDeleteRequest: (id: string) => void;
}

export function OutlineOutliner({ store, onReveal, canReveal, onDeleteRequest }: Props) {
  const rows = buildRows(store.items, store.zoomRootId, store.filter);
  const visibleIds = new Set(rows.map((r) => r.node.id));
  const filtering = isFilterActive(store.filter);
  const canDrag = !filtering; // order is ambiguous under an active filter
  const crumbs = store.zoomRootId ? ancestorChain(store.items, store.zoomRootId) : [];

  const handleKey = (e: KeyboardEvent<HTMLInputElement>, atStart: boolean, atEnd: boolean) => {
    const id = store.selectedId;
    if (!id) return;
    const node = store.items.find((n) => n.id === id);
    if (!node) return;
    const mod = e.metaKey || e.ctrlKey;

    // Zoom (hoist) — Ctrl/Cmd+] in, Ctrl/Cmd+[ out.
    if (mod && (e.code === 'BracketRight' || e.code === 'BracketLeft')) {
      e.preventDefault();
      e.stopPropagation();
      if (e.code === 'BracketRight') store.zoomInto(id);
      else store.zoomOut();
      return;
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      e.stopPropagation();
      if (e.shiftKey) store.setDetailsOpenId(store.detailsOpenId === id ? null : id);
      else if (mod) store.addChild(id);
      else store.addSibling(id);
      return;
    }
    if (e.key === 'Tab') {
      e.preventDefault();
      e.stopPropagation();
      if (e.shiftKey) store.outdent(id);
      else store.indent(id);
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      e.stopPropagation();
      if (mod) store.moveUp(id);
      else {
        const i = rows.findIndex((r) => r.node.id === id);
        if (i > 0) store.selectOnly(rows[i - 1].node.id);
      }
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      e.stopPropagation();
      if (mod) store.moveDown(id);
      else {
        const i = rows.findIndex((r) => r.node.id === id);
        if (i >= 0 && i < rows.length - 1) store.selectOnly(rows[i + 1].node.id);
      }
      return;
    }
    if (e.key === 'ArrowLeft' && atStart) {
      e.preventDefault();
      e.stopPropagation();
      if (hasChildren(store.items, id) && !node.collapsed) store.toggleCollapse(id);
      else if (node.parentId && visibleIds.has(node.parentId)) store.selectOnly(node.parentId);
      return;
    }
    if (e.key === 'ArrowRight' && atEnd) {
      const kids = hasChildren(store.items, id);
      if (!kids) return;
      e.preventDefault();
      e.stopPropagation();
      if (node.collapsed) store.toggleCollapse(id);
      else {
        const first = firstChildId(store.items, id);
        if (first) store.selectOnly(first);
      }
      return;
    }
    if ((e.key === 'Backspace' || e.key === 'Delete') && node.title.length === 0) {
      e.preventDefault();
      e.stopPropagation();
      onDeleteRequest(id);
      return;
    }
    if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      store.setSelectedId(null);
      store.clearMulti();
      e.currentTarget.blur();
    }
  };

  return (
    <>
      {crumbs.length > 0 && (
        <nav className="outline-breadcrumbs" aria-label="Outline zoom path">
          <button type="button" className="outline-crumb" onClick={() => store.setZoomRootId(null)}>
            Outline
          </button>
          {crumbs.map((n, i) => (
            <span key={n.id} className="outline-crumb-wrap">
              <span className="outline-crumb-sep">›</span>
              <button
                type="button"
                className="outline-crumb"
                disabled={i === crumbs.length - 1}
                onClick={() => store.setZoomRootId(n.id)}
              >
                {n.title || TYPE_LABELS[n.type]}
              </button>
            </span>
          ))}
        </nav>
      )}

      {rows.length === 0 ? (
        filtering ? (
          <p className="outline-hint">
            No matches.{' '}
            <button type="button" className="outline-inline-link" onClick={store.clearFilter}>
              Clear filter
            </button>
          </p>
        ) : store.zoomRootId ? (
          <p className="outline-hint">Empty — add an item under this one.</p>
        ) : (
          <p className="outline-hint">
            No outline yet. Use <strong>+ Add</strong> to start your story structure.
          </p>
        )
      ) : (
        <ul className="outline-tree">
          {rows.map((row) => (
            <OutlineRow
              key={row.node.id}
              row={row}
              store={store}
              onKeyDown={handleKey}
              onDelete={onDeleteRequest}
              canDrag={canDrag}
              onReveal={onReveal}
              canReveal={canReveal}
            />
          ))}
        </ul>
      )}
    </>
  );
}
