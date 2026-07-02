/**
 * Multi-document lifecycle + autosave for the Whiteboard.
 *
 * Owns the active document (blocks/title/mode), the document-library list, and
 * the debounced backend autosave. On launch it loads the last-used document (or
 * the most recent) — startup is now persistent, not blank. Switching flushes
 * pending saves to the OLD document first (registerDocFlusher +
 * flushPendingDocSaves) so an in-flight autosave can never land on the new doc;
 * every doc-scoped call is scoped to the active id by `withDoc` in the clients.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import {
  flushPendingDocSaves,
  getCurrentDocId,
  registerDocFlusher,
  registerUnloadFlush,
  setCurrentDocId,
  withDoc,
} from '../../state/currentDocument';
import { emitOutlineRefresh } from '../outline/outlineApi';
import {
  createDocument,
  deleteDocument as deleteDocumentApi,
  listDocuments,
  type DocumentSummary,
} from './documentsApi';
import type { SaveStatus, WhiteboardBlock, WhiteboardDocument } from './types';
import { getWhiteboard, updateWhiteboard } from './whiteboardApi';

const SAVE_DEBOUNCE_MS = 700;
const LAST_DOC_KEY = 'lf-last-doc';

function loadLastDocId(): string | null {
  try {
    return localStorage.getItem(LAST_DOC_KEY) || null;
  } catch {
    return null;
  }
}
function saveLastDocId(id: string): void {
  try {
    localStorage.setItem(LAST_DOC_KEY, id);
  } catch {
    /* ignore */
  }
}

interface Options {
  baseUrl: string;
  ready: boolean;
  /** Called after each successful save (lets the outline/derived views refresh). */
  onSaved?: () => void;
}

interface Result {
  doc: WhiteboardDocument | null;
  docList: DocumentSummary[];
  loading: boolean;
  loadError: string | null;
  saveStatus: SaveStatus;
  onChangeBlocks: (blocks: WhiteboardBlock[]) => void;
  setMode: (mode: string) => void;
  selectDocument: (id: string) => void;
  newDocument: (title?: string, mode?: string) => void;
  deleteDocument: (id: string) => void;
  renameDocument: (title: string) => void;
}

export function useWhiteboardDocument({ baseUrl, ready, onSaved }: Options): Result {
  const onSavedRef = useRef(onSaved);
  onSavedRef.current = onSaved;

  const [doc, setDoc] = useState<WhiteboardDocument | null>(null);
  const [docList, setDocList] = useState<DocumentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');

  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pending = useRef<WhiteboardBlock[] | null>(null);
  const switchSeq = useRef(0); // bumped per document switch; guards against out-of-order loads

  const refreshList = useCallback(async () => {
    try {
      setDocList(await listDocuments(baseUrl));
    } catch {
      /* keep the last good list */
    }
  }, [baseUrl]);

  // -- autosave the active document's blocks (scoped to the active id via withDoc) --
  const flush = useCallback(async () => {
    const blocks = pending.current;
    if (!blocks) return;
    pending.current = null;
    setSaveStatus('saving');
    try {
      await updateWhiteboard(baseUrl, { blocks });
      setSaveStatus('saved');
      onSavedRef.current?.();
    } catch {
      setSaveStatus('error');
    }
  }, [baseUrl]);

  // Register so a document switch can drain a pending save into the OLD doc first.
  useEffect(() => registerDocFlusher(flush), [flush]);

  // Crash recovery: on an unclean exit, flush the pending blocks with a keepalive
  // PUT to the active document (survives page teardown; the normal autosave debounce
  // may not have fired yet).
  useEffect(
    () =>
      registerUnloadFlush(() => {
        const blocks = pending.current;
        if (!blocks) return;
        fetch(withDoc(`${baseUrl}/api/whiteboard`), {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ blocks }),
          keepalive: true,
        });
      }),
    [baseUrl],
  );

  const onChangeBlocks = useCallback(
    (blocks: WhiteboardBlock[]) => {
      pending.current = blocks;
      setSaveStatus('saving');
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => void flush(), SAVE_DEBOUNCE_MS);
    },
    [flush],
  );

  // -- initial load: the last-used (or most-recent) document, not a blank one --
  useEffect(() => {
    if (!ready) return undefined;
    let cancelled = false;
    void (async () => {
      setLoading(true);
      setLoadError(null);
      try {
        let list = await listDocuments(baseUrl);
        if (!list.length) {
          const created = await createDocument(baseUrl, {});
          list = [{ id: created.id, title: created.title, mode: created.mode, updated_at: created.updated_at }];
        }
        const lastUsed = loadLastDocId();
        const pick = list.find((d) => d.id === lastUsed) ?? list[0];
        setCurrentDocId(pick.id);
        saveLastDocId(pick.id);
        const full = await getWhiteboard(baseUrl);
        if (cancelled) return;
        setDocList(list);
        setDoc(full);
        setLoading(false);
      } catch (err) {
        if (cancelled) return;
        setLoadError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [ready, baseUrl]);

  // -- switch / create / delete / rename --
  const selectDocument = useCallback(
    async (id: string) => {
      if (!id || id === getCurrentDocId()) return;
      const seq = (switchSeq.current += 1);
      await flushPendingDocSaves(); // drain old-doc autosaves before the id changes
      setCurrentDocId(id);
      saveLastDocId(id);
      setSaveStatus('idle');
      try {
        const full = await getWhiteboard(baseUrl);
        // A faster subsequent switch may have superseded this load — dropping it
        // keeps the displayed doc (and its mode) matching the active document id.
        if (seq !== switchSeq.current) return;
        setDoc(full);
        emitOutlineRefresh(); // reload the outline for the new document
      } catch (err) {
        if (seq !== switchSeq.current) return;
        setLoadError(err instanceof Error ? err.message : String(err));
      }
    },
    [baseUrl],
  );

  const newDocument = useCallback(
    async (title?: string, mode?: string) => {
      await flushPendingDocSaves();
      try {
        const created = await createDocument(baseUrl, { title, mode });
        setCurrentDocId(created.id);
        saveLastDocId(created.id);
        setSaveStatus('idle');
        setDoc(created);
        emitOutlineRefresh(); // a fresh document has an empty outline
        await refreshList();
      } catch (err) {
        setLoadError(err instanceof Error ? err.message : String(err));
      }
    },
    [baseUrl, refreshList],
  );

  const deleteDocument = useCallback(
    async (id: string) => {
      const wasCurrent = id === getCurrentDocId();
      try {
        await deleteDocumentApi(baseUrl, id);
      } catch (err) {
        setLoadError(err instanceof Error ? err.message : String(err));
        return;
      }
      const list = await listDocuments(baseUrl);
      setDocList(list);
      if (wasCurrent) {
        if (list.length) await selectDocument(list[0].id);
        else await newDocument();
      }
    },
    [baseUrl, selectDocument, newDocument],
  );

  const renameDocument = useCallback(
    async (title: string) => {
      const next = title.trim() || 'Untitled';
      setDoc((prev) => (prev ? { ...prev, title: next } : prev));
      try {
        await updateWhiteboard(baseUrl, { title: next });
        await refreshList();
      } catch {
        /* the local title still updated */
      }
    },
    [baseUrl, refreshList],
  );

  // -- writing mode (active document) --
  const setMode = useCallback(
    async (requested: string) => {
      // `series` is not a Whiteboard mode — normalize it to `novel`.
      const mode = requested === 'series' ? 'novel' : requested;
      setDoc((prev) => (prev ? { ...prev, mode } : prev));
      setSaveStatus('saving');
      try {
        await updateWhiteboard(baseUrl, { mode });
        setSaveStatus('saved');
        onSavedRef.current?.();
        await refreshList();
      } catch {
        setSaveStatus('error');
      }
    },
    [baseUrl, refreshList],
  );

  // Clear any pending debounce on unmount.
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  return {
    doc,
    docList,
    loading,
    loadError,
    saveStatus,
    onChangeBlocks,
    setMode,
    selectDocument,
    newDocument,
    deleteDocument,
    renameDocument,
  };
}
