/**
 * One outliner row — Dynalist-style, story-oriented.
 *
 * Main line: indent guides · disclosure · checkbox · color · type · title ·
 * status · (on hover/selected) quick actions. Colour / status / type are inline
 * pickers, so common edits never need the details panel. A subtle tag line + an
 * optional details panel (type / status / color / tags) sit under the row.
 *
 * Drag-to-reorder: a row is draggable while it isn't being edited; dropping on
 * the top/bottom third makes a sibling, the middle third nests it as a child.
 *
 * The title is the only keyboard-driven field (its onKeyDown is owned by the
 * outliner); the other controls are mouse-only so they never fight the editor.
 */

import {
  useEffect,
  useRef,
  useState,
  type DragEvent,
  type KeyboardEvent,
  type MouseEvent,
} from 'react';

import { Popover } from '../../components/Popover';
import {
  COLOR_LABELS,
  dropZone,
  OUTLINE_COLORS,
  OUTLINE_STATUSES,
  OUTLINE_TYPES,
  STATUS_BADGE,
  STATUS_LABELS,
  TYPE_LABELS,
  type DropPosition,
  type OutlineColor,
  type OutlineItemType,
  type OutlineNode,
  type OutlineStatus,
  type VisibleRow,
} from './outlineModel';
import type { OutlineStore } from './useOutline';

const INDENT_STEP = 12;
const BASE_PAD = 8;

interface Props {
  row: VisibleRow;
  store: OutlineStore;
  onKeyDown: (e: KeyboardEvent<HTMLInputElement>, atStart: boolean, atEnd: boolean) => void;
  onDelete: (id: string) => void;
  /** Drag-to-reorder is disabled while a filter is active (order is ambiguous). */
  canDrag: boolean;
  onReveal?: (node: OutlineNode) => void;
  canReveal?: (node: OutlineNode) => boolean;
  /** This is the linked node the editor caret currently sits in ("you are here"). */
  active?: boolean;
  /** A manuscript caret is available to bind a link to. */
  canLink?: boolean;
  onLinkToCursor?: (id: string) => void;
  onNavigateBlock?: (blockIndex: number) => void;
}

function dropZoneFor(e: DragEvent<HTMLElement>): DropPosition {
  const rect = e.currentTarget.getBoundingClientRect();
  return dropZone(e.clientY - rect.top, rect.height);
}

export function OutlineRow({
  row,
  store,
  onKeyDown,
  onDelete,
  canDrag,
  onReveal,
  canReveal,
  active = false,
  canLink = false,
  onLinkToCursor,
  onNavigateBlock,
}: Props) {
  const { node, depth, hasChildren } = row;
  const selected = store.selectedId === node.id;
  const multi = store.selectedIds.includes(node.id);
  const detailsOpen = store.detailsOpenId === node.id;
  const inputRef = useRef<HTMLInputElement>(null);
  const [tagDraft, setTagDraft] = useState('');
  const [hovered, setHovered] = useState(false);
  const [dropZone, setDropZone] = useState<DropPosition | null>(null);
  const [dragging, setDragging] = useState(false);

  // When this row becomes selected, focus the title and place the caret at end.
  useEffect(() => {
    if (selected && inputRef.current) {
      const el = inputRef.current;
      el.focus();
      const len = el.value.length;
      el.setSelectionRange(len, len);
    }
  }, [selected]);

  const revealable = !!onReveal && (canReveal ? canReveal(node) : false);
  const showAffordances = selected || hovered;
  const pad = BASE_PAD + depth * INDENT_STEP;

  const onDisclosureClick = (e: MouseEvent) => {
    if (e.altKey) store.collapseBranch(node.id, !node.collapsed); // recursive
    else store.toggleCollapse(node.id);
  };

  const selectFromClick = (e: MouseEvent) => {
    if (e.shiftKey) store.selectRange(node.id);
    else if (e.metaKey || e.ctrlKey) store.toggleMulti(node.id);
    else store.selectOnly(node.id);
  };

  const commitTag = () => {
    const t = tagDraft.trim();
    if (t) store.addTag(node.id, t);
    setTagDraft('');
  };

  // --- drag & drop ---
  const onDragStart = (e: DragEvent<HTMLDivElement>) => {
    e.dataTransfer.setData('text/plain', node.id);
    e.dataTransfer.effectAllowed = 'move';
    setDragging(true);
  };
  const onDragEnd = () => {
    setDragging(false);
    setDropZone(null);
  };
  const onDragOver = (e: DragEvent<HTMLDivElement>) => {
    if (!canDrag) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    const z = dropZoneFor(e);
    setDropZone((prev) => (prev === z ? prev : z));
  };
  const onDragLeave = () => setDropZone(null);
  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    if (!canDrag) return;
    e.preventDefault();
    const dragId = e.dataTransfer.getData('text/plain');
    const z = dropZoneFor(e);
    setDropZone(null);
    if (dragId && dragId !== node.id) store.move(dragId, node.id, z);
  };

  const rowClass = [
    'outline-row',
    selected ? 'is-selected' : '',
    multi ? 'is-multi' : '',
    node.completed ? 'is-completed' : '',
    dragging ? 'is-dragging' : '',
    active ? 'is-linked-active' : '',
    dropZone ? `drop-${dropZone}` : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <li className="outline-node">
      <div
        className={rowClass}
        style={{ paddingLeft: BASE_PAD }}
        draggable={canDrag && !selected}
        onDragStart={onDragStart}
        onDragEnd={onDragEnd}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      >
        {depth > 0 && (
          <span className="outline-indent" aria-hidden>
            {Array.from({ length: depth }).map((_, i) => (
              <span key={i} className="outline-guide" />
            ))}
          </span>
        )}

        {hasChildren ? (
          <button
            type="button"
            className="outline-disclosure"
            aria-label={node.collapsed ? 'Expand' : 'Collapse'}
            aria-expanded={!node.collapsed}
            title={node.collapsed ? 'Expand (Alt+click: all)' : 'Collapse (Alt+click: all)'}
            draggable={false}
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
          draggable={false}
          onMouseDown={(e) => e.stopPropagation()}
          onChange={() => store.toggleCompleted(node.id)}
        />

        {(node.colorLabel !== 'none' || showAffordances) && (
          <Popover
            align="left"
            triggerClassName={`outline-color-trigger${
              node.colorLabel !== 'none' ? ` outline-color-${node.colorLabel}` : ' is-empty'
            }`}
            label={<span className="outline-a11y">Colour</span>}
            title={`Colour: ${COLOR_LABELS[node.colorLabel]}`}
          >
            {(close) => (
              <div className="wb-menu outline-color-menu">
                {OUTLINE_COLORS.map((c) => (
                  <button
                    key={c}
                    type="button"
                    className={`outline-swatch outline-color-${c}${c === 'none' ? ' is-none' : ''}${
                      node.colorLabel === c ? ' is-current' : ''
                    }`}
                    title={COLOR_LABELS[c]}
                    aria-label={COLOR_LABELS[c]}
                    onClick={() => {
                      store.setColorLabel(node.id, c);
                      close();
                    }}
                  />
                ))}
              </div>
            )}
          </Popover>
        )}

        <Popover
          align="left"
          triggerClassName="outline-type-trigger"
          label={TYPE_LABELS[node.type]}
          title={`Type: ${TYPE_LABELS[node.type]} — click to change`}
        >
          {(close) => (
            <div className="wb-menu outline-pick-menu">
              {OUTLINE_TYPES.map((t) => (
                <button
                  key={t}
                  type="button"
                  className={`wb-menu-item${node.type === t ? ' is-current' : ''}`}
                  onClick={() => {
                    store.setType(node.id, t);
                    close();
                  }}
                >
                  {TYPE_LABELS[t]}
                </button>
              ))}
            </div>
          )}
        </Popover>

        {node.link && (
          <button
            type="button"
            className="outline-link-badge"
            title="Go to linked passage"
            aria-label="Go to linked passage"
            draggable={false}
            onMouseDown={(e) => e.stopPropagation()}
            onClick={() => node.link && onNavigateBlock?.(node.link.blockIndex)}
          >
            ⚓
          </button>
        )}

        {selected ? (
          <input
            ref={inputRef}
            className="outline-title-input"
            value={node.title}
            placeholder="Untitled"
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
            draggable={false}
            onClick={selectFromClick}
          >
            {node.title || 'Untitled'}
          </button>
        )}

        {(node.status !== 'none' || showAffordances) && (
          <Popover
            align="right"
            triggerClassName={`outline-status-trigger${
              node.status !== 'none' ? ` outline-status-${node.status}` : ' is-empty'
            }`}
            label={node.status !== 'none' ? STATUS_BADGE[node.status] : ''}
            title={`Status: ${STATUS_LABELS[node.status]} — click to change`}
          >
            {(close) => (
              <div className="wb-menu outline-pick-menu">
                {OUTLINE_STATUSES.map((s) => (
                  <button
                    key={s}
                    type="button"
                    className={`wb-menu-item${node.status === s ? ' is-current' : ''}`}
                    onClick={() => {
                      store.setStatus(node.id, s);
                      close();
                    }}
                  >
                    {STATUS_LABELS[s]}
                  </button>
                ))}
              </div>
            )}
          </Popover>
        )}

        {showAffordances && (
          <span className="outline-row-actions">
            <Popover label="⋯" title="Item actions" align="right">
              {(close) => (
                <div className="wb-menu outline-menu">
                  {node.link ? (
                    <>
                      <button
                        type="button"
                        className="wb-menu-item"
                        onClick={() => { if (node.link) onNavigateBlock?.(node.link.blockIndex); close(); }}
                      >
                        Go to linked passage
                      </button>
                      <button
                        type="button"
                        className="wb-menu-item"
                        onClick={() => { store.unlink(node.id); close(); }}
                      >
                        Unlink from manuscript
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      className="wb-menu-item"
                      disabled={!canLink}
                      title={canLink
                        ? 'Bind this item to where your cursor is in the manuscript'
                        : 'Put your cursor on a manuscript line that has text'}
                      onClick={() => { onLinkToCursor?.(node.id); close(); }}
                    >
                      Link to cursor position
                    </button>
                  )}
                  <div className="wb-menu-sep" role="separator" />
                  <button type="button" className="wb-menu-item" onClick={() => { store.addChild(node.id); close(); }}>
                    Add child
                  </button>
                  <button type="button" className="wb-menu-item" onClick={() => { store.selectOnly(node.id); close(); }}>
                    Rename
                  </button>
                  <button
                    type="button"
                    className="wb-menu-item"
                    onClick={() => { store.setDetailsOpenId(detailsOpen ? null : node.id); close(); }}
                  >
                    {detailsOpen ? 'Hide details' : 'Edit details…'}
                  </button>
                  {revealable && (
                    <button type="button" className="wb-menu-item" onClick={() => { onReveal!(node); close(); }}>
                      Reveal in editor
                    </button>
                  )}
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
