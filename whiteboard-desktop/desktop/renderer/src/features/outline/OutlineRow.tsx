/**
 * One outliner row — Dynalist-style, story-oriented.
 *
 * Main line: disclosure · checkbox · color dot · type · title · status badge ·
 * (when selected) quick actions. A subtle tag line + an optional details panel
 * (type / status / color / tags / Note body) sit under the row.
 *
 * The title is the only keyboard-driven field (its onKeyDown is owned by the
 * outliner); the other controls are mouse-only so they never fight the editor.
 */

import { useEffect, useRef, useState, type KeyboardEvent, type MouseEvent } from 'react';

import { Popover } from '../../components/Popover';
import {
  COLOR_LABELS,
  OUTLINE_COLORS,
  OUTLINE_STATUSES,
  OUTLINE_TYPES,
  STATUS_BADGE,
  STATUS_LABELS,
  TYPE_LABELS,
  type OutlineColor,
  type OutlineItemType,
  type OutlineStatus,
  type VisibleRow,
} from './outlineModel';
import type { OutlineStore } from './useOutline';

const INDENT_STEP = 14;
const BASE_PAD = 8;

interface Props {
  row: VisibleRow;
  store: OutlineStore;
  onKeyDown: (e: KeyboardEvent<HTMLInputElement>, atStart: boolean, atEnd: boolean) => void;
  onDelete: (id: string) => void;
}

export function OutlineRow({ row, store, onKeyDown, onDelete }: Props) {
  const { node, depth, hasChildren } = row;
  const selected = store.selectedId === node.id;
  const detailsOpen = store.detailsOpenId === node.id;
  const inputRef = useRef<HTMLInputElement>(null);
  const [tagDraft, setTagDraft] = useState('');

  // When this row becomes selected, focus the title and place the caret at end.
  useEffect(() => {
    if (selected && inputRef.current) {
      const el = inputRef.current;
      el.focus();
      const len = el.value.length;
      el.setSelectionRange(len, len);
    }
  }, [selected]);

  const pad = BASE_PAD + depth * INDENT_STEP;
  const isNote = node.type === 'note';

  const onDisclosureClick = (e: MouseEvent) => {
    if (e.altKey) store.collapseBranch(node.id, !node.collapsed); // recursive
    else store.toggleCollapse(node.id);
  };

  const commitTag = () => {
    const t = tagDraft.trim();
    if (t) store.addTag(node.id, t);
    setTagDraft('');
  };

  return (
    <li className="outline-node">
      <div
        className={`outline-row${selected ? ' is-selected' : ''}${node.completed ? ' is-completed' : ''}`}
        style={{ paddingLeft: pad }}
      >
        {hasChildren ? (
          <button
            type="button"
            className="outline-disclosure"
            aria-label={node.collapsed ? 'Expand' : 'Collapse'}
            aria-expanded={!node.collapsed}
            title={node.collapsed ? 'Expand (Alt+click: all)' : 'Collapse (Alt+click: all)'}
            onMouseDown={(e) => e.preventDefault()}
            onClick={onDisclosureClick}
          >
            {node.collapsed ? '▸' : '▾'}
          </button>
        ) : (
          <span className="outline-disclosure outline-disclosure-leaf" aria-hidden>
            •
          </span>
        )}

        <input
          type="checkbox"
          className="outline-check"
          checked={node.completed}
          title="Completed"
          aria-label="Completed"
          onMouseDown={(e) => e.stopPropagation()}
          onChange={() => store.toggleCompleted(node.id)}
        />

        {node.colorLabel !== 'none' && (
          <span
            className={`outline-color-dot outline-color-${node.colorLabel}`}
            title={COLOR_LABELS[node.colorLabel]}
            aria-hidden
          />
        )}

        <span
          className="outline-type"
          title={`${TYPE_LABELS[node.type]} — double-click to zoom in`}
          onDoubleClick={() => store.zoomInto(node.id)}
        >
          {TYPE_LABELS[node.type]}
        </span>

        {selected ? (
          <input
            ref={inputRef}
            className="outline-title-input"
            value={node.title}
            placeholder={isNote ? 'Note title' : 'Untitled'}
            spellCheck={false}
            onChange={(e) => store.rename(node.id, e.target.value)}
            onKeyDown={(e) => {
              const el = e.currentTarget;
              const atStart = el.selectionStart === 0 && el.selectionEnd === 0;
              const atEnd = el.selectionStart === el.value.length && el.selectionEnd === el.value.length;
              onKeyDown(e, atStart, atEnd);
            }}
          />
        ) : (
          <button
            type="button"
            className={`outline-title${node.title ? '' : ' is-untitled'}`}
            title={node.title || 'Untitled'}
            onClick={() => store.setSelectedId(node.id)}
          >
            {node.title || (isNote ? 'Untitled note' : 'Untitled')}
          </button>
        )}

        {node.status !== 'none' && (
          <span
            className={`outline-status outline-status-${node.status}`}
            title={STATUS_LABELS[node.status]}
          >
            {STATUS_BADGE[node.status]}
          </span>
        )}

        {selected && (
          <span className="outline-row-actions">
            <button
              type="button"
              className="outline-act"
              title="Add child (Ctrl/Cmd+Enter)"
              aria-label="Add child"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => store.addChild(node.id)}
            >
              +
            </button>
            <Popover label="⋯" title="Item actions" align="right">
              {(close) => (
                <div className="wb-menu outline-menu">
                  <button type="button" className="wb-menu-item" onClick={() => { store.addChild(node.id); close(); }}>
                    Add child
                  </button>
                  <button type="button" className="wb-menu-item" onClick={() => { store.setSelectedId(node.id); close(); }}>
                    Rename
                  </button>
                  <button
                    type="button"
                    className="wb-menu-item"
                    onClick={() => { store.setDetailsOpenId(detailsOpen ? null : node.id); close(); }}
                  >
                    {detailsOpen ? 'Hide details' : (isNote ? 'Edit note…' : 'Edit details…')}
                  </button>
                  <button type="button" className="wb-menu-item" onClick={() => { store.zoomInto(node.id); close(); }}>
                    Zoom into item
                  </button>
                  <button type="button" className="wb-menu-item" onClick={() => { store.toggleCompleted(node.id); close(); }}>
                    {node.completed ? 'Mark not done' : 'Mark done'}
                  </button>
                  <button type="button" className="wb-menu-item" onClick={() => { store.duplicate(node.id); close(); }}>
                    Duplicate
                  </button>
                  <button type="button" className="wb-menu-item is-danger" onClick={() => { onDelete(node.id); close(); }}>
                    Delete
                  </button>
                </div>
              )}
            </Popover>
          </span>
        )}
      </div>

      {node.tags.length > 0 && (
        <div className="outline-tags" style={{ paddingLeft: pad + INDENT_STEP }}>
          {node.tags.map((t) => (
            <button
              key={t}
              type="button"
              className="outline-tag-chip"
              title={`Filter by #${t}`}
              onClick={() => store.setFilter({ tag: t })}
            >
              #{t}
            </button>
          ))}
        </div>
      )}

      {detailsOpen && (
        <div className="outline-details" style={{ paddingLeft: pad + INDENT_STEP }}>
          <div className="outline-details-grid">
            <label className="outline-field">
              <span>Type</span>
              <select value={node.type} onChange={(e) => store.setType(node.id, e.target.value as OutlineItemType)}>
                {OUTLINE_TYPES.map((t) => (
                  <option key={t} value={t}>{TYPE_LABELS[t]}</option>
                ))}
              </select>
            </label>
            <label className="outline-field">
              <span>Status</span>
              <select value={node.status} onChange={(e) => store.setStatus(node.id, e.target.value as OutlineStatus)}>
                {OUTLINE_STATUSES.map((s) => (
                  <option key={s} value={s}>{STATUS_LABELS[s]}</option>
                ))}
              </select>
            </label>
            <label className="outline-field">
              <span>Color</span>
              <select value={node.colorLabel} onChange={(e) => store.setColorLabel(node.id, e.target.value as OutlineColor)}>
                {OUTLINE_COLORS.map((c) => (
                  <option key={c} value={c}>{COLOR_LABELS[c]}</option>
                ))}
              </select>
            </label>
          </div>

          <div className="outline-field-block">
            <span>Tags</span>
            <div className="outline-tag-edit">
              {node.tags.map((t) => (
                <button
                  key={t}
                  type="button"
                  className="outline-tag-chip is-removable"
                  title="Remove tag"
                  onClick={() => store.removeTag(node.id, t)}
                >
                  #{t} ×
                </button>
              ))}
              <input
                className="outline-tag-input"
                placeholder="add tag…"
                value={tagDraft}
                onChange={(e) => setTagDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    e.stopPropagation();
                    commitTag();
                  }
                }}
                onBlur={commitTag}
              />
            </div>
          </div>

          <label className="outline-field-block">
            <span>{isNote ? 'Note' : 'Notes'}</span>
            <textarea
              className="outline-notes"
              placeholder={isNote ? 'LogosForge Note body…' : 'Notes…'}
              value={node.notes}
              rows={3}
              onChange={(e) => store.setNotes(node.id, e.target.value)}
            />
          </label>

          <div className="outline-details-actions">
            <button type="button" className="outline-details-done" onClick={() => store.setDetailsOpenId(null)}>
              Done
            </button>
          </div>
        </div>
      )}
    </li>
  );
}
