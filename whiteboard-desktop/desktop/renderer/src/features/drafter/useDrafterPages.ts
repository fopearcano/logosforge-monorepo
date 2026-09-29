import { useCallback, useEffect, useRef, useState } from 'react';

import {
  persistPendingDocument,
  persistPendingDocumentOnUnload,
  retainPendingDocumentConflict,
} from '../../api/pendingDocumentPersistence';
import { isPersistenceRecoveryError } from '../../api/responseError';
import {
  captureDocumentIncarnation,
  getCurrentDocId,
  markPendingDocSave,
} from '../../state/currentDocument';
import { canStartDocumentMutationDuringClose } from '../whiteboard/documentOperationGuard';
import type { WhiteboardBlock } from '../whiteboard/types';
import { getDrafterPages } from './drafterApi';
import {
  createDrafterPage,
  removeDrafterPage,
  renameDrafterPage,
  replaceDrafterPageBlocks,
  validateDrafterPages,
} from './drafterModel';
import {
  claimDrafterConflict,
  drafterRevisionConflict,
  flushDrafterSnapshots,
  newestRetainedDrafterSnapshot,
  peekRetainedDrafterSnapshot,
  queueDrafterSnapshot,
} from './pendingDrafterRecovery';
import type { DrafterPage, DrafterSaveStatus } from './types';

const SAVE_DEBOUNCE_MS = 700;
const NO_PAGES: DrafterPage[] = [];
const CONFLICT_MESSAGE =
  'Drafter recovery required: these saved pages changed or are no longer writable. '
  + 'Your local pages remain open and were not overwritten.';

interface Options {
  baseUrl: string;
  ready: boolean;
  documentId: string | null;
  documentIncarnation: string | null;
}

export interface DrafterPagesStore {
  pages: DrafterPage[];
  /** True only after the pages for the exact current document generation loaded. */
  available: boolean;
  loading: boolean;
  error: string | null;
  saveStatus: DrafterSaveStatus;
  createPage: (title: string, blocks?: WhiteboardBlock[]) => DrafterPage | null;
  renamePage: (id: string, title: string) => void;
  deletePage: (id: string) => boolean;
  updatePageBlocks: (id: string, blocks: WhiteboardBlock[]) => void;
  replacePages: (pages: DrafterPage[]) => boolean;
  flush: () => Promise<boolean>;
  dismissError: () => void;
}

export function useDrafterPages({
  baseUrl,
  ready,
  documentId,
  documentIncarnation,
}: Options): DrafterPagesStore {
  const [pages, setPages] = useState<DrafterPage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<DrafterSaveStatus>('idle');
  const pagesRef = useRef(pages);
  pagesRef.current = pages;
  const baseUrlRef = useRef(baseUrl);
  baseUrlRef.current = baseUrl;
  const loadedRef = useRef<{ documentId: string; incarnation: string } | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const timerDocIdRef = useRef('');
  const loadSequenceRef = useRef(0);

  const flushDocument = useCallback(async (targetDocumentId: string): Promise<void> => {
    if (!targetDocumentId) return;
    if (timerRef.current && timerDocIdRef.current === targetDocumentId) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
      timerDocIdRef.current = '';
    }
    if (!peekRetainedDrafterSnapshot(targetDocumentId)) return;
    if (loadedRef.current?.documentId === targetDocumentId) {
      setSaveStatus(drafterRevisionConflict(targetDocumentId) ? 'conflict' : 'saving');
    }
    try {
      await flushDrafterSnapshots(targetDocumentId);
      if (loadedRef.current?.documentId === targetDocumentId) {
        setSaveStatus('saved');
        setError(null);
      }
    } catch (saveError) {
      if (loadedRef.current?.documentId === targetDocumentId) {
        if (isPersistenceRecoveryError(saveError)) {
          setSaveStatus('conflict');
          setError(CONFLICT_MESSAGE);
        } else {
          setSaveStatus('error');
          setError(`Drafter autosave stopped: ${saveError instanceof Error ? saveError.message : String(saveError)}`);
        }
      }
      throw saveError;
    }
  }, []);

  const scheduleSave = useCallback((next: DrafterPage[]): boolean => {
    if (!canStartDocumentMutationDuringClose()) return false;
    const loaded = loadedRef.current;
    if (!loaded || loaded.documentId !== getCurrentDocId()) return false;
    const incarnation = captureDocumentIncarnation(loaded.documentId);
    if (incarnation !== loaded.incarnation) return false;
    const queued = queueDrafterSnapshot(loaded.documentId, next, {
      incarnation,
      write: (targetDocumentId, snapshot, revision) => persistPendingDocument(
        baseUrlRef.current,
        'drafter',
        targetDocumentId,
        revision,
        { pages: snapshot },
        incarnation,
      ),
      writeOnUnload: (targetDocumentId, snapshot, revision) => {
        persistPendingDocumentOnUnload(
          baseUrlRef.current,
          'drafter',
          targetDocumentId,
          revision,
          { pages: snapshot },
          incarnation,
        );
      },
      retainConflict: (targetDocumentId, snapshot, revision, recovery) =>
        retainPendingDocumentConflict(
          'drafter',
          targetDocumentId,
          revision,
          { pages: snapshot },
          recovery,
          incarnation,
        ),
    });
    if (!queued) return false;
    markPendingDocSave();
    setSaveStatus(drafterRevisionConflict(loaded.documentId) ? 'conflict' : 'saving');
    if (timerRef.current) clearTimeout(timerRef.current);
    timerDocIdRef.current = loaded.documentId;
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      timerDocIdRef.current = '';
      void flushDocument(loaded.documentId).catch(() => {
        /* The retained queue owns the complete page snapshot for retry/recovery. */
      });
    }, SAVE_DEBOUNCE_MS);
    return true;
  }, [flushDocument]);

  const commit = useCallback((next: DrafterPage[]): boolean => {
    const validationError = validateDrafterPages(next);
    if (validationError) {
      setSaveStatus('error');
      setError(validationError);
      return false;
    }
    if (!scheduleSave(next)) return false;
    pagesRef.current = next;
    setPages(next);
    return true;
  }, [scheduleSave]);

  useEffect(() => {
    if (!ready || !documentId || !documentIncarnation) {
      loadedRef.current = null;
      pagesRef.current = [];
      setPages([]);
      setLoading(Boolean(documentId));
      return undefined;
    }
    const requestId = ++loadSequenceRef.current;
    const controller = new AbortController();
    const retainedBeforeLoad = claimDrafterConflict(documentId, documentIncarnation);
    loadedRef.current = null;
    setLoading(true);
    setError(null);
    setSaveStatus('idle');
    void getDrafterPages(baseUrl, documentId, documentIncarnation, controller.signal).then(
      (loaded) => {
        if (
          controller.signal.aborted
          || requestId !== loadSequenceRef.current
          || getCurrentDocId() !== documentId
          || captureDocumentIncarnation(documentId) !== documentIncarnation
        ) return;
        const retained = newestRetainedDrafterSnapshot(
          retainedBeforeLoad,
          peekRetainedDrafterSnapshot(documentId, documentIncarnation),
        );
        const next = (retained?.pages ?? loaded.pages) as DrafterPage[];
        loadedRef.current = { documentId, incarnation: documentIncarnation };
        pagesRef.current = next;
        setPages(next);
        setLoading(false);
        if (retained && drafterRevisionConflict(documentId)) {
          setSaveStatus('conflict');
          setError(CONFLICT_MESSAGE);
        } else if (retained) {
          scheduleSave(next);
        }
      },
      (loadError: unknown) => {
        if (controller.signal.aborted || requestId !== loadSequenceRef.current) return;
        setError(loadError instanceof Error ? loadError.message : String(loadError));
        setLoading(false);
      },
    );
    return () => controller.abort();
  }, [baseUrl, documentId, documentIncarnation, ready, scheduleSave]);

  useEffect(() => () => {
    loadSequenceRef.current += 1;
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = null;
    timerDocIdRef.current = '';
    const loaded = loadedRef.current;
    if (loaded && peekRetainedDrafterSnapshot(loaded.documentId, loaded.incarnation)) {
      void flushDocument(loaded.documentId).catch(() => {});
    }
  }, [flushDocument]);

  const createPage = useCallback((title: string, blocks?: WhiteboardBlock[]): DrafterPage | null => {
    const page = createDrafterPage(title, blocks);
    return commit([...pagesRef.current, page]) ? page : null;
  }, [commit]);

  const renamePage = useCallback((id: string, title: string) => {
    commit(renameDrafterPage(pagesRef.current, id, title));
  }, [commit]);

  const deletePage = useCallback((id: string) => {
    return commit(removeDrafterPage(pagesRef.current, id));
  }, [commit]);

  const updatePageBlocks = useCallback((id: string, blocks: WhiteboardBlock[]) => {
    commit(replaceDrafterPageBlocks(pagesRef.current, id, blocks));
  }, [commit]);

  const replacePages = useCallback((next: DrafterPage[]) => commit(next), [commit]);

  const flush = useCallback(async (): Promise<boolean> => {
    const loaded = loadedRef.current;
    if (!loaded) return true;
    try {
      await flushDocument(loaded.documentId);
      return true;
    } catch {
      return false;
    }
  }, [flushDocument]);

  const available = Boolean(
    documentId
    && documentIncarnation
    && loadedRef.current?.documentId === documentId
    && loadedRef.current.incarnation === documentIncarnation,
  );

  return {
    // Never expose the prior project's pages during the effect-sized handoff
    // between React receiving a new document id and its GET starting.
    pages: available ? pages : NO_PAGES,
    available,
    loading,
    error,
    saveStatus,
    createPage,
    renamePage,
    deletePage,
    updatePageBlocks,
    replacePages,
    flush,
    dismissError: () => setError(null),
  };
}
