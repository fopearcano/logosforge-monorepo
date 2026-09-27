import { useRef, type KeyboardEvent } from 'react';

import { Popover } from '../../components/Popover';
import {
  nextTabIndex,
  writingSurfaceTabDomId,
  writingSurfaceTabId,
} from './drafterModel';
import type { DrafterPage, DrafterSaveStatus, WritingSurface } from './types';

interface Props {
  pages: DrafterPage[];
  active: WritingSurface;
  saveStatus: DrafterSaveStatus;
  disabled?: boolean;
  canCreate?: boolean;
  onSelect: (surface: WritingSurface) => void;
  onCreate: () => void;
  onImport: () => void;
  onRename: (page: DrafterPage) => void;
  onDelete: (page: DrafterPage) => void;
}

const STATUS_LABEL: Record<DrafterSaveStatus, string> = {
  idle: '',
  saving: 'Saving draft…',
  saved: 'Draft saved',
  error: 'Draft save stopped',
  conflict: 'Draft conflict',
};

export function DrafterTabs({
  pages,
  active,
  saveStatus,
  disabled = false,
  canCreate = true,
  onSelect,
  onCreate,
  onImport,
  onRename,
  onDelete,
}: Props) {
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const activeId = writingSurfaceTabId(active);
  const manuscriptSurface: WritingSurface = { kind: 'manuscript' };
  const surfaces: WritingSurface[] = [
    { kind: 'manuscript' },
    ...pages.map((page): WritingSurface => ({ kind: 'draft', pageId: page.id })),
  ];

  const handleKey = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const next = nextTabIndex(index, event.key, surfaces.length);
    if (next === null) return;
    event.preventDefault();
    const surface = surfaces[next];
    tabRefs.current[next]?.focus({ preventScroll: true });
    onSelect(surface);
  };

  return (
    <div className="drafter-tabs-row">
      <div className="drafter-tabs" role="tablist" aria-label="Writing pages">
        <button
          ref={(element) => { tabRefs.current[0] = element; }}
          type="button"
          id={writingSurfaceTabDomId(manuscriptSurface)}
          className={`drafter-tab${activeId === writingSurfaceTabId(manuscriptSurface) ? ' is-active' : ''}`}
          role="tab"
          aria-selected={activeId === writingSurfaceTabId(manuscriptSurface)}
          aria-controls="writing-panel-active"
          tabIndex={activeId === writingSurfaceTabId(manuscriptSurface) ? 0 : -1}
          disabled={disabled}
          onClick={() => onSelect({ kind: 'manuscript' })}
          onKeyDown={(event) => handleKey(event, 0)}
        >
          Manuscript
        </button>
        {pages.map((page, index) => {
          const surface: WritingSurface = { kind: 'draft', pageId: page.id };
          const selected = activeId === writingSurfaceTabId(surface);
          return (
            <button
              key={page.id}
              ref={(element) => { tabRefs.current[index + 1] = element; }}
              type="button"
              id={writingSurfaceTabDomId(surface)}
              className={`drafter-tab${selected ? ' is-active' : ''}`}
              role="tab"
              aria-selected={selected}
              aria-controls="writing-panel-active"
              tabIndex={selected ? 0 : -1}
              disabled={disabled}
              title={page.title}
              onClick={() => onSelect(surface)}
              onKeyDown={(event) => handleKey(event, index + 1)}
            >
              {page.title}
            </button>
          );
        })}
      </div>
      <button
        type="button"
        className="drafter-add"
        aria-label="New Drafter page"
        title="New Drafter page (Ctrl/Cmd+Shift+N)"
        disabled={disabled || !canCreate}
        onClick={onCreate}
      >
        +
      </button>
      {disabled ? (
        <button type="button" className="drafter-manage" disabled aria-label="Manage Drafter pages">
          Drafter
        </button>
      ) : (
        <Popover label="Drafter" title="Manage Drafter pages" align="right" triggerClassName="drafter-manage">
          {(close) => (
          <div className="wb-menu wb-menu-scroll drafter-menu">
            <button
              type="button"
              className="wb-menu-item wb-menu-strong"
              disabled={!canCreate}
              onClick={() => { close(); onCreate(); }}
            >
              + New page
            </button>
            <button
              type="button"
              className="wb-menu-item"
              disabled={!canCreate}
              onClick={() => { close(); onImport(); }}
            >
              Import file as page…
            </button>
            {pages.length > 0 && <div className="wb-menu-sep" role="separator" />}
            {pages.map((page) => (
              <div key={page.id} className="drafter-menu-page">
                <button
                  type="button"
                  className="wb-menu-item drafter-menu-open"
                  onClick={() => { close({ restoreFocus: false }); onSelect({ kind: 'draft', pageId: page.id }); }}
                >
                  {page.title}
                </button>
                <button
                  type="button"
                  className="drafter-menu-action"
                  aria-label={`Rename ${page.title}`}
                  onClick={() => { close({ restoreFocus: true }); onRename(page); }}
                >
                  Rename
                </button>
                <button
                  type="button"
                  className="drafter-menu-action is-danger"
                  aria-label={`Delete ${page.title}`}
                  onClick={() => { close({ restoreFocus: true }); onDelete(page); }}
                >
                  Delete
                </button>
              </div>
            ))}
          </div>
          )}
        </Popover>
      )}
      <span className={`drafter-save drafter-save-${saveStatus}`} role="status" aria-live="polite">
        {STATUS_LABEL[saveStatus]}
      </span>
    </div>
  );
}
