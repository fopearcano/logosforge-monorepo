/**
 * The hideable Outline left-panel.
 *
 * Two views, toggled by a small segmented control (choice persisted locally):
 *   - "Outline" (default): the manual, editable, persisted story outliner.
 *   - "From Document": the read-only navigator derived from the current document
 *     (headings / scene-headings / synopses / notes) — click to scroll there.
 *
 * The panel stays exactly where it is (left side, lightweight, Whiteboard Free).
 */

import { useCallback, useMemo, useRef, useState } from 'react';

import { ConfirmDialog } from '../../components/ConfirmDialog';
import { Popover } from '../../components/Popover';
import { normalizeOutlineTitle } from './outlineColorStore';
import { OutlineOutliner } from './OutlineOutliner';
import { OutlineTemplatesDialog } from './OutlineTemplatesDialog';
import {
  COLOR_LABELS,
  OUTLINE_COLORS,
  OUTLINE_STATUSES,
  OUTLINE_TYPES,
  STATUS_LABELS,
  TYPE_LABELS,
  descendantIds,
  hasChildren,
  isFilterActive,
  isSelfOrAncestor,
  type OutlineColor,
  type OutlineItemType,
  type OutlineNode,
  type OutlineStatus,
} from './outlineModel';
import type { OutlineItem, OutlineKind } from './types';
import { useOutline } from './useOutline';

/** Confirmation state for a pending delete (single row or batch). */
interface DeletePrompt {
  title: string;
  message: string;
  onConfirm: () => void;
}

type View = 'manual' | 'document';

const VIEW_KEY = 'lf-outline-view';

function loadView(): View {
  try {
    return localStorage.getItem(VIEW_KEY) === 'document' ? 'document' : 'manual';
  } catch {
    return 'manual';
  }
}

const KIND_ORDER: OutlineKind[] = ['section', 'scene', 'synopsis', 'note'];
const KIND_LABELS: Record<OutlineKind, string> = {
  section: 'Sections',
  scene: 'Scenes',
  synopsis: 'Synopses',
  note: 'Notes',
};

function derivedIndent(item: OutlineItem): number {
  if (item.kind === 'section') return 10 + Math.max(0, item.level - 1) * 14;
  return 24; // scenes / synopses / notes sit nested under sections
}


interface Props {
  derivedItems: OutlineItem[];
  onNavigate?: (item: OutlineItem) => void;
  baseUrl: string;
  ready: boolean;
  mode: string;
}

const SAVE_LABEL: Record<string, string> = {
  saving: 'Saving…',
  saved: 'Saved',
  error: 'Save failed',
};

export function OutlinePanel({ derivedItems, onNavigate, baseUrl, ready, mode }: Props) {
  const [view, setView] = useState<View>(loadView);
  const store = useOutline({ baseUrl, ready, mode });

  const selectView = (next: View) => {
    setView(next);
    try {
      localStorage.setItem(VIEW_KEY, next);
    } catch {
      /* ignore storage failures */
    }
  };

  return (
    <aside className="outline-panel" aria-label="Outline">
      <div className="outline-header">
        <span className="outline-title-label">Outline</span>
        <div className="outline-view-toggle" role="group" aria-label="Outline view">
          <button
            type="button"
            className={`outline-view${view === 'manual' ? ' is-active' : ''}`}
            aria-pressed={view === 'manual'}
            onClick={() => selectView('manual')}
          >
            Outline
          </button>
          <button
            type="button"
            className={`outline-view${view === 'document' ? ' is-active' : ''}`}
            aria-pressed={view === 'document'}
            onClick={() => selectView('document')}
            title="Navigator derived from the current document"
          >
            From Document
          </button>
        </div>
      </div>

      {view === 'manual' ? (
        <ManualView store={store} derivedItems={derivedItems} onNavigate={onNavigate} />
      ) : (
        <DerivedView items={derivedItems} onNavigate={onNavigate} />
      )}
    </aside>
  );
}

function ManualView({
  store,
  derivedItems,
  onNavigate,
}: {
  store: ReturnType<typeof useOutline>;
  derivedItems: OutlineItem[];
  onNavigate?: (item: OutlineItem) => void;
}) {
  const saveLabel = SAVE_LABEL[store.saveState] ?? '';
  const [templatesOpen, setTemplatesOpen] = useState(false);
  const [deletePrompt, setDeletePrompt] = useState<DeletePrompt | null>(null);
  const filterOn = isFilterActive(store.filter);
  const multiCount = store.selectedIds.length;

  // Primary "+ Add": another item at the current level (sibling of the selection),
  // else a child of the zoom root, else a new top-level item. The ▾ menu adds a
  // specific type (auto-placed by rank) or opens the templates picker.
  const smartAdd = () => {
    const zoom = store.zoomRootId;
    const sel = store.selectedId;
    if (!zoom) {
      if (sel) store.addSibling(sel);
      else store.addRoot();
      return;
    }
    // Zoomed: only add a sibling when the selection is strictly inside the zoomed
    // subtree (a stale selection outside it would create the node off-screen);
    // otherwise add a child of the zoom root so it stays visible.
    const inside = !!sel && sel !== zoom && isSelfOrAncestor(store.items, zoom, sel);
    if (inside) store.addSibling(sel as string);
    else store.addChild(zoom);
  };

  // Delete routes through the in-app ConfirmDialog — window.confirm is unreliable
  // in the packaged Electron app, so parent deletes (the only path that confirms)
  // silently no-op'd. Leaf rows need no confirmation and delete immediately.
  const requestDelete = (id: string) => {
    const node = store.items.find((n) => n.id === id);
    if (!node) return;
    if (!hasChildren(store.items, id)) {
      store.remove(id);
      return;
    }
    const n = descendantIds(store.items, id).length;
    const label = node.title.trim() || TYPE_LABELS[node.type];
    setDeletePrompt({
      title: 'Delete item',
      message: `Delete “${label}” and its ${n} nested item${n === 1 ? '' : 's'}?`,
      onConfirm: () => {
        store.remove(id);
        setDeletePrompt(null);
      },
    });
  };

  // Reveal-in-editor: match a manual item's title to document heading(s)/scene(s).
  // Titles can collide (two "Chapter One" headings), so keep every match and
  // cycle through them on repeated reveals rather than always jumping to the first.
  const revealMap = useMemo(() => {
    const m = new Map<string, OutlineItem[]>();
    for (const it of derivedItems) {
      const k = normalizeOutlineTitle(it.label);
      if (!k) continue;
      const arr = m.get(k);
      if (arr) arr.push(it);
      else m.set(k, [it]);
    }
    return m;
  }, [derivedItems]);
  const revealIdx = useRef(new Map<string, number>());
  const canReveal = useCallback(
    (node: OutlineNode) => {
      const arr = revealMap.get(normalizeOutlineTitle(node.title));
      return !!node.title.trim() && !!arr && arr.length > 0;
    },
    [revealMap],
  );
  const onReveal = useCallback(
    (node: OutlineNode) => {
      const k = normalizeOutlineTitle(node.title);
      const arr = revealMap.get(k);
      if (!arr || arr.length === 0) return;
      const next = ((revealIdx.current.get(k) ?? -1) + 1) % arr.length;
      revealIdx.current.set(k, next);
      onNavigate?.(arr[next]);
    },
    [revealMap, onNavigate],
  );

  const deleteSelected = () => {
    setDeletePrompt({
      title: 'Delete selection',
      message: `Delete ${multiCount} selected items and all their children?`,
      onConfirm: () => {
        store.removeSelected();
        setDeletePrompt(null);
      },
    });
  };

  return (
    <>
      <div className="outline-toolbar">
        <div className="outline-add-split" role="group" aria-label="Add outline item">
          <button type="button" className="outline-tool outline-add-main" onClick={smartAdd} title="Add an item at the current level">
            + Add
          </button>
          <Popover
            align="left"
            triggerClassName="outline-tool outline-add-caret"
            label="▾"
            title="Add a specific type, or apply a structure template"
          >
            {(close) => (
              <div className="wb-menu outline-add-menu">
                <div className="wb-menu-label">Add item</div>
                {OUTLINE_TYPES.map((t) => (
                  <button
                    key={t}
                    type="button"
                    className="wb-menu-item"
                    onClick={() => {
                      store.addTyped(t);
                      close();
                    }}
                  >
                    {TYPE_LABELS[t]}
                  </button>
                ))}
                <div className="wb-menu-sep" role="separator" />
                <button
                  type="button"
                  className="wb-menu-item"
                  onClick={() => {
                    setTemplatesOpen(true);
                    close();
                  }}
                >
                  Structure templates…
                </button>
              </div>
            )}
          </Popover>
        </div>
        <button type="button" className="outline-tool" onClick={store.collapseAll} title="Collapse all">
          Collapse all
        </button>
        <button type="button" className="outline-tool" onClick={store.expandAll} title="Expand all">
          Expand all
        </button>
        <span className={`outline-save outline-save-${store.saveState}`} aria-live="polite">
          {saveLabel}
        </span>
      </div>

      <div className="outline-searchbar">
        <input
          className="outline-search"
          type="search"
          placeholder="Search title, #tag…"
          value={store.filter.query}
          onChange={(e) => store.setFilter({ query: e.target.value })}
        />
        <Popover label="⛃" title="Filter" align="right">
          {() => (
            <div className="wb-menu outline-filter-menu">
              <label className="outline-field">
                <span>Type</span>
                <select
                  value={store.filter.type}
                  onChange={(e) => store.setFilter({ type: e.target.value as OutlineItemType | 'all' })}
                >
                  <option value="all">Any type</option>
                  {OUTLINE_TYPES.map((t) => (
                    <option key={t} value={t}>{TYPE_LABELS[t]}</option>
                  ))}
                </select>
              </label>
              <label className="outline-field">
                <span>Status</span>
                <select
                  value={store.filter.status}
                  onChange={(e) => store.setFilter({ status: e.target.value as OutlineStatus | 'all' })}
                >
                  <option value="all">Any status</option>
                  {OUTLINE_STATUSES.filter((s) => s !== 'none').map((s) => (
                    <option key={s} value={s}>{STATUS_LABELS[s]}</option>
                  ))}
                </select>
              </label>
              <label className="outline-field">
                <span>Color</span>
                <select
                  value={store.filter.color}
                  onChange={(e) => store.setFilter({ color: e.target.value as OutlineColor | 'all' })}
                >
                  <option value="all">Any color</option>
                  {OUTLINE_COLORS.filter((c) => c !== 'none').map((c) => (
                    <option key={c} value={c}>{COLOR_LABELS[c]}</option>
                  ))}
                </select>
              </label>
              <button type="button" className="wb-menu-item" onClick={store.clearFilter}>
                Clear filters
              </button>
            </div>
          )}
        </Popover>
      </div>
      {filterOn && (
        <div className="outline-filter-active">
          Filtered{store.filter.tag ? ` · #${store.filter.tag}` : ''}
          <button type="button" className="outline-inline-link" onClick={store.clearFilter}>
            Clear
          </button>
        </div>
      )}

      {multiCount >= 2 && (
        <div className="outline-batchbar" role="group" aria-label="Batch actions">
          <span className="outline-batch-count">{multiCount} selected</span>
          <Popover label="Status" title="Set status for selected" align="left">
            {(close) => (
              <div className="wb-menu outline-pick-menu">
                {OUTLINE_STATUSES.map((s) => (
                  <button
                    key={s}
                    type="button"
                    className="wb-menu-item"
                    onClick={() => { store.setStatusSelected(s); close(); }}
                  >
                    {STATUS_LABELS[s]}
                  </button>
                ))}
              </div>
            )}
          </Popover>
          <Popover label="Colour" title="Set colour for selected" align="left">
            {(close) => (
              <div className="wb-menu outline-color-menu">
                {OUTLINE_COLORS.map((c) => (
                  <button
                    key={c}
                    type="button"
                    className={`outline-swatch outline-color-${c}${c === 'none' ? ' is-none' : ''}`}
                    title={COLOR_LABELS[c]}
                    aria-label={COLOR_LABELS[c]}
                    onClick={() => { store.setColorSelected(c); close(); }}
                  />
                ))}
              </div>
            )}
          </Popover>
          <button type="button" className="outline-tool" onClick={() => store.setCompletedSelected(true)}>
            Done
          </button>
          <button type="button" className="outline-tool outline-tool-danger" onClick={deleteSelected}>
            Delete
          </button>
          <button type="button" className="outline-inline-link" onClick={store.clearMulti}>
            Clear
          </button>
        </div>
      )}

      <div className="outline-body">
        {store.loading ? (
          <p className="outline-hint">Loading…</p>
        ) : store.error ? (
          <p className="outline-hint outline-error">Couldn’t load outline: {store.error}</p>
        ) : (
          <OutlineOutliner
            store={store}
            onReveal={onReveal}
            canReveal={canReveal}
            onDeleteRequest={requestDelete}
          />
        )}
      </div>

      <ConfirmDialog
        open={!!deletePrompt}
        title={deletePrompt?.title ?? ''}
        message={deletePrompt?.message ?? ''}
        confirmLabel="Delete"
        onConfirm={() => deletePrompt?.onConfirm()}
        onCancel={() => setDeletePrompt(null)}
      />
      <OutlineTemplatesDialog
        open={templatesOpen}
        hasExisting={store.items.length > 0}
        onApply={(tpl, replace) => {
          store.applyTemplate(tpl, replace);
          setTemplatesOpen(false);
        }}
        onClose={() => setTemplatesOpen(false)}
      />
    </>
  );
}

function DerivedView({
  items,
  onNavigate,
}: {
  items: OutlineItem[];
  onNavigate?: (item: OutlineItem) => void;
}) {
  const [hidden, setHidden] = useState<Set<OutlineKind>>(() => new Set());

  const kinds = useMemo(() => {
    const present = new Set(items.map((i) => i.kind));
    return KIND_ORDER.filter((k) => present.has(k));
  }, [items]);

  const visible = items.filter((i) => !hidden.has(i.kind));

  const toggle = (k: OutlineKind) =>
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });

  return (
    <>
      {kinds.length > 1 && (
        <div className="outline-filters" role="group" aria-label="Filter outline">
          {kinds.map((k) => (
            <button
              key={k}
              type="button"
              className={`outline-filter${hidden.has(k) ? '' : ' is-active'}`}
              aria-pressed={!hidden.has(k)}
              onClick={() => toggle(k)}
            >
              {KIND_LABELS[k]}
            </button>
          ))}
        </div>
      )}
      <div className="outline-body">
        {visible.length === 0 ? (
          <p className="outline-hint">
            {items.length === 0 ? 'No structure in the document yet.' : 'All hidden.'}
          </p>
        ) : (
          <ul className="outline-list">
            {visible.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className={`outline-item outline-${item.kind}`}
                  style={{ paddingLeft: derivedIndent(item) }}
                  onClick={() => onNavigate?.(item)}
                  title={item.label}
                >
                  {item.label}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}
