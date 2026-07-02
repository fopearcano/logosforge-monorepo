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

import { useMemo, useState } from 'react';

import { Popover } from '../../components/Popover';
import { OutlineOutliner } from './OutlineOutliner';
import {
  COLOR_LABELS,
  OUTLINE_COLORS,
  OUTLINE_STATUSES,
  OUTLINE_TYPES,
  STATUS_LABELS,
  TYPE_LABELS,
  isFilterActive,
  type OutlineColor,
  type OutlineItemType,
  type OutlineStatus,
} from './outlineModel';
import type { OutlineItem, OutlineKind } from './types';
import { useOutline } from './useOutline';

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
        <ManualView store={store} />
      ) : (
        <DerivedView items={derivedItems} onNavigate={onNavigate} />
      )}
    </aside>
  );
}

function ManualView({ store }: { store: ReturnType<typeof useOutline> }) {
  const saveLabel = SAVE_LABEL[store.saveState] ?? '';
  // When zoomed in, "+ Add" adds a child of the zoom root (not a new top-level).
  const add = () => (store.zoomRootId ? store.addChild(store.zoomRootId) : store.addRoot());
  const filterOn = isFilterActive(store.filter);
  return (
    <>
      <div className="outline-toolbar">
        <button type="button" className="outline-tool" onClick={add}>
          + Add
        </button>
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
          placeholder="Search title, note, #tag…"
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

      <div className="outline-body">
        {store.loading ? (
          <p className="outline-hint">Loading…</p>
        ) : store.error ? (
          <p className="outline-hint outline-error">Couldn’t load outline: {store.error}</p>
        ) : (
          <OutlineOutliner store={store} />
        )}
      </div>
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
