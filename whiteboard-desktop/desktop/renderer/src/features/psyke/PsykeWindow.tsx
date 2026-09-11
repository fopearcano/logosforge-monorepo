/**
 * PSYKE Small: a compact, right-side, hideable panel — search → results → simple
 * detail (with edit + delete), plus minimal element creation (+ Add). No graph,
 * no Pro workspace.
 */

import { useEffect, useRef, useState } from 'react';

import { ConfirmDialog } from '../../components/ConfirmDialog';
import { getCurrentDocId, subscribeCurrentDoc } from '../../state/currentDocument';
import { PsykeCreateForm } from './PsykeCreateForm';
import { deletePsykeElement } from './psykeApi';
import { PsykeSearch } from './PsykeSearch';
import type { PsykeEntry } from './types';
import { usePsykeSearch } from './usePsykeSearch';

interface Props {
  baseUrl: string;
  initialQuery: string;
  onClose: () => void;
}

export function PsykeWindow({ baseUrl, initialQuery, onClose }: Props) {
  const { query, setQuery, results, loading, error, refresh } = usePsykeSearch({ baseUrl, initialQuery });
  const [selected, setSelected] = useState<PsykeEntry | null>(null);
  const [view, setView] = useState<'search' | 'create' | 'edit'>('search');
  const [added, setAdded] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<PsykeEntry | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const addButtonRef = useRef<HTMLButtonElement>(null);

  // Esc: leave the create/edit form first (back to search/detail), else close.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (pendingDelete) return; // the confirmation dialog owns Escape
      if (view === 'create' || view === 'edit') {
        e.stopPropagation();
        setView('search');
      } else {
        onClose();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, pendingDelete, view]);

  // Auto-dismiss the confirmation toast.
  useEffect(() => {
    if (!added) return;
    const t = setTimeout(() => setAdded(null), 2600);
    return () => clearTimeout(t);
  }, [added]);

  // The story bible is per-document — reset when the active document changes.
  useEffect(
    () =>
      subscribeCurrentDoc(() => {
        setSelected(null);
        setPendingDelete(null);
        setDeleting(false);
        setView('search');
        setActionError(null);
        setQuery('');
      }),
    [setQuery],
  );

  const trimmed = query.trim();

  const handleSaved = (element: PsykeEntry, wasEdit: boolean) => {
    setActionError(null);
    if (wasEdit) {
      setSelected(element); // keep the detail open, now showing the edits
      setView('search');
      refresh(); // the description/type may have changed in the result list
      setAdded(`Updated “${element.name}”.`);
    } else {
      setView('search');
      setSelected(null);
      setQuery(element.name); // re-run search so the new element shows immediately
      setAdded(`Added “${element.name}”.`);
    }
  };

  const handleDelete = async (entry: PsykeEntry) => {
    if (deleting) return;
    const operationDocId = getCurrentDocId();
    setDeleting(true);
    setActionError(null);
    try {
      await deletePsykeElement(baseUrl, entry.id);
      if (operationDocId !== getCurrentDocId()) return;
      setSelected(null);
      setView('search');
      refresh();
      setAdded(`Deleted “${entry.name}”.`);
    } catch (err) {
      if (operationDocId !== getCurrentDocId()) return;
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      if (operationDocId === getCurrentDocId()) setDeleting(false);
    }
  };

  return (
    <aside className="psyke-window" aria-label="PSYKE">
      <div className="psyke-header">
        <span className="psyke-title">PSYKE</span>
        <div className="psyke-header-actions">
          {view === 'search' && (
            <button
              ref={addButtonRef}
              type="button"
              className="psyke-add"
              onClick={() => {
                setSelected(null);
                setActionError(null);
                setView('create');
              }}
              title="Add a PSYKE element"
            >
              + Add
            </button>
          )}
          <button
            type="button"
            className="psyke-close"
            onClick={onClose}
            title="Close (Esc)"
            aria-label="Close PSYKE"
          >
            ×
          </button>
        </div>
      </div>

      {view === 'create' || view === 'edit' ? (
        <PsykeCreateForm
          baseUrl={baseUrl}
          seed={trimmed}
          entry={view === 'edit' ? (selected ?? undefined) : undefined}
          onSaved={(el) => handleSaved(el, view === 'edit')}
          onCancel={() => setView('search')}
        />
      ) : (
        <>
          <PsykeSearch
            query={query}
            onChange={(q) => {
              setQuery(q);
              setSelected(null);
              setActionError(null);
            }}
          />
          {added && <p className="psyke-added">{added}</p>}
          <div className="psyke-body">
            {selected ? (
              <div className="psyke-detail">
                <button type="button" className="psyke-back" onClick={() => setSelected(null)}>
                  ← Back to results
                </button>
                <h3 className="psyke-detail-name">{selected.name}</h3>
                <div className="psyke-detail-type">{selected.entry_type}</div>
                {selected.description ? <p className="psyke-detail-text">{selected.description}</p> : null}
                {selected.notes ? (
                  <div className="psyke-detail-aliases">
                    <span className="psyke-detail-label">Notes</span>
                    {selected.notes}
                  </div>
                ) : null}
                {selected.aliases.length > 0 && (
                  <div className="psyke-detail-aliases">
                    <span className="psyke-detail-label">Aliases</span>
                    {selected.aliases.join(', ')}
                  </div>
                )}
                {actionError && <p className="psyke-hint psyke-error">{actionError}</p>}
                <div className="psyke-detail-actions">
                  <button
                    type="button"
                    className="psyke-btn"
                    onClick={() => {
                      setActionError(null);
                      setView('edit');
                    }}
                    disabled={deleting}
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    className="psyke-btn psyke-btn-danger"
                    onClick={() => setPendingDelete(selected)}
                    disabled={deleting}
                  >
                    {deleting ? 'Deleting…' : 'Delete'}
                  </button>
                </div>
              </div>
            ) : !trimmed ? (
              <p className="psyke-hint">Type to search the story bible, or + Add a new element.</p>
            ) : loading ? (
              <p className="psyke-hint">Searching…</p>
            ) : error ? (
              <p className="psyke-hint psyke-error">{error}</p>
            ) : results.length === 0 ? (
              <div className="psyke-empty">
                <p className="psyke-hint">No entries match “{trimmed}”.</p>
                <button type="button" className="psyke-add-inline" onClick={() => setView('create')}>
                  + Add “{trimmed}”
                </button>
              </div>
            ) : (
              <ul className="psyke-results">
                {results.map((entry) => (
                  <li key={entry.id}>
                    <button type="button" className="psyke-result" onClick={() => setSelected(entry)}>
                      <span className="psyke-result-name">{entry.name}</span>
                      <span className="psyke-badge">{entry.entry_type}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete PSYKE element"
        message={`Delete “${pendingDelete?.name ?? ''}” from the story bible? This can’t be undone.`}
        confirmLabel="Delete"
        returnFocusFallbackRef={addButtonRef}
        onConfirm={() => {
          const target = pendingDelete;
          setPendingDelete(null);
          if (target) void handleDelete(target);
        }}
        onCancel={() => setPendingDelete(null)}
      />
    </aside>
  );
}
