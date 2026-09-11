/**
 * Multi-document lifecycle + autosave for the Whiteboard.
 *
 * Owns the active document (blocks/title/mode), the document-library list, and
 * the debounced backend autosave. On launch it loads the last-used document (or
 * the most recent) — startup is now persistent, not blank. Switching flushes
 * pending saves to the OLD document on both sides of target preparation, so an
 * in-flight autosave or a keystroke made during loading can never land on the
 * new doc; every doc-scoped call is scoped to the active id by `withDoc`.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import {
  blockDocumentMutations,
  captureDocumentIncarnation,
  discardDocumentMutations,
  discardPendingDocSaves,
  getCurrentDocId,
  markPendingDocSave,
  prepareDocumentHandoff,
  registerDocDiscarder,
  registerDocFlusher,
  resumeDocumentMutations,
  setCurrentDocumentIdentity,
  waitForPendingDocWrites,
} from '../../state/currentDocument';
import {
  persistPendingDocument,
  persistPendingDocumentOnUnload,
  deleteDocumentWithNativePersistenceFence,
  waitForPendingDocumentPersistence,
} from '../../api/pendingDocumentPersistence';
import {
  createDocument,
  deleteDocument as deleteDocumentApi,
  documentExists,
  listDocuments,
  type DocumentSummary,
} from './documentsApi';
import type { SaveStatus, WhiteboardBlock, WhiteboardDocument, WhiteboardUpdate } from './types';
import { getWhiteboardForDocument } from './whiteboardApi';
import {
  blockWhiteboardWrites,
  applyRetainedWhiteboardPatch,
  discardRetainedWhiteboardPatch,
  flushWhiteboardPatches,
  newestRetainedWhiteboardPatch,
  peekRetainedWhiteboardPatch,
  queueWhiteboardPatch,
  resumeWhiteboardWrites,
  type WhiteboardPatchReceipt,
  waitForWhiteboardWrites,
} from './pendingWhiteboardRecovery';
import {
  blockOutlineWrites,
  discardRetainedOutlineSnapshot,
  flushOutlineSnapshots,
  resumeOutlineWrites,
  waitForOutlineWrites,
} from '../outline/pendingOutlineRecovery';
import { loadInitialDocumentOnce } from './documentBootstrap';
import {
  acquireTrackedDocumentOperation,
  activateDocumentOperationOwner,
  canStartDocumentMutationDuringClose,
  createDocumentOperationOwner,
  DocumentCloseInProgressError,
  isActiveDocumentOperationOwner,
  lockDocumentInteraction,
  releaseDocumentOperationOwner,
} from './documentOperationGuard';

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
  dismissError: () => void;
  saveStatus: SaveStatus;
  onChangeBlocks: (blocks: WhiteboardBlock[]) => WhiteboardPatchReceipt | null;
  onChangeSettings: (settings: object) => void;
  setMode: (mode: string) => Promise<boolean>;
  selectDocument: (id: string) => Promise<boolean>;
  newDocument: (title?: string, mode?: string) => Promise<boolean>;
  deleteDocument: (id: string) => Promise<boolean>;
  renameDocument: (title: string) => void;
}

export function useWhiteboardDocument({ baseUrl, ready, onSaved }: Options): Result {
  const lifecycleOwnerRef = useRef<symbol | null>(null);
  if (lifecycleOwnerRef.current === null) {
    lifecycleOwnerRef.current = createDocumentOperationOwner();
  }
  const lifecycleOwner = lifecycleOwnerRef.current;
  const onSavedRef = useRef(onSaved);
  onSavedRef.current = onSaved;

  const [doc, setDoc] = useState<WhiteboardDocument | null>(null);
  const [docList, setDocList] = useState<DocumentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');

  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const timerDocId = useRef('');
  const navigationBusy = useRef(false);
  const switchSeq = useRef(0); // bumped per document switch; guards against out-of-order loads

  useEffect(() => {
    activateDocumentOperationOwner(lifecycleOwner);
    return () => releaseDocumentOperationOwner(lifecycleOwner);
  }, [lifecycleOwner]);

  const refreshList = useCallback(async () => {
    try {
      setDocList(await listDocuments(baseUrl));
    } catch {
      /* keep the last good list */
    }
  }, [baseUrl]);

  const queuePatch = useCallback(
    (documentId: string, patch: WhiteboardUpdate) => {
      const incarnation = captureDocumentIncarnation(documentId);
      return queueWhiteboardPatch(documentId, patch, {
        write: (targetDocumentId, queuedPatch, revision) => persistPendingDocument(
          baseUrl,
          'whiteboard',
          targetDocumentId,
          revision,
          queuedPatch,
          incarnation,
        ),
        writeOnUnload: (targetDocumentId, queuedPatch, revision) => {
          persistPendingDocumentOnUnload(
            baseUrl,
            'whiteboard',
            targetDocumentId,
            revision,
            queuedPatch,
            incarnation,
          );
        },
      });
    },
    [baseUrl],
  );

  // -- serialize manuscript + document-settings patches by immutable doc id --
  const flushDocument = useCallback((documentId: string): Promise<void> => {
    if (!documentId) return Promise.resolve();
    if (timer.current && timerDocId.current === documentId) {
      clearTimeout(timer.current);
      timer.current = null;
      timerDocId.current = '';
    }
    if (!peekRetainedWhiteboardPatch(documentId)) return Promise.resolve();
    if (getCurrentDocId() === documentId) setSaveStatus('saving');
    return flushWhiteboardPatches(documentId).then(
      () => {
        if (getCurrentDocId() !== documentId) return;
        setSaveStatus('saved');
        setLoadError(null);
        onSavedRef.current?.();
      },
      (error: unknown) => {
        if (getCurrentDocId() === documentId) {
          setSaveStatus('error');
          setLoadError(`Autosave stopped: ${error instanceof Error ? error.message : String(error)}`);
        }
        throw error;
      },
    );
  }, [baseUrl]);

  const flush = useCallback(
    (): Promise<void> => flushDocument(getCurrentDocId()),
    [flushDocument],
  );

  // Register so a document switch can drain a pending save into the OLD doc first.
  useEffect(() => registerDocFlusher(flush), [flush]);

  // A successful deletion intentionally invalidates every queued/in-flight
  // snapshot for that document. Generation stamping prevents a late rejection
  // from restoring deleted content into the next document's save queue.
  useEffect(
    () =>
      registerDocDiscarder(() => {
        discardRetainedWhiteboardPatch(getCurrentDocId());
        if (timer.current) clearTimeout(timer.current);
        timer.current = null;
        timerDocId.current = '';
      }),
    [],
  );

  const schedulePatch = useCallback(
    (patch: WhiteboardUpdate): WhiteboardPatchReceipt | null => {
      if (!canStartDocumentMutationDuringClose()) return null;
      const documentId = getCurrentDocId();
      const receipt = queuePatch(documentId, patch);
      if (!receipt) return null;
      markPendingDocSave();
      setSaveStatus('saving');
      if (timer.current) clearTimeout(timer.current);
      timerDocId.current = documentId;
      timer.current = setTimeout(() => {
        timer.current = null;
        timerDocId.current = '';
        void flushDocument(documentId).catch(() => {
          /* the hook exposes the error and the shared queue retains the patch */
        });
      }, SAVE_DEBOUNCE_MS);
      return receipt;
    },
    [flushDocument, queuePatch],
  );

  const onChangeBlocks = useCallback(
    (blocks: WhiteboardBlock[]) => schedulePatch({ blocks }),
    [schedulePatch],
  );

  const onChangeSettings = useCallback(
    (settings: object) => {
      setDoc((current) => current ? { ...current, settings } : current);
      schedulePatch({ settings });
    },
    [schedulePatch],
  );

  // -- initial load: the last-used (or most-recent) document, not a blank one --
  useEffect(() => {
    if (!ready) return undefined;
    let cancelled = false;
    const seq = (switchSeq.current += 1);
    navigationBusy.current = true;
    let finishOperation: (() => void) | null = null;
    void (async () => {
      setLoading(true);
      setLoadError(null);
      try {
        // A root-boundary replacement serializes behind retiring operations and
        // remains resumable if a failed close attempt temporarily blocks startup.
        finishOperation = await acquireTrackedDocumentOperation({ waitForCloseBarrier: true });
        if (
          cancelled
          || seq !== switchSeq.current
          || !isActiveDocumentOperationOwner(lifecycleOwner)
        ) return;
        await waitForPendingDocWrites();
        const recoveringDocumentId = getCurrentDocId();
        const loadDocument = async () => {
          await waitForPendingDocumentPersistence();
          let list = await listDocuments(baseUrl);
          let createdDocument: WhiteboardDocument | null = null;
          if (!list.length) {
            createdDocument = await createDocument(baseUrl, {});
            list = [{
              id: createdDocument.id,
              incarnation: createdDocument.incarnation,
              title: createdDocument.title,
              mode: createdDocument.mode,
              updated_at: createdDocument.updated_at,
            }];
          }
          const lastUsed = loadLastDocId();
          const pick = (
            recoveringDocumentId
              ? list.find((candidate) => candidate.id === recoveringDocumentId)
              : undefined
          ) ?? list.find((candidate) => candidate.id === lastUsed) ?? list[0];
          // Capture before the GET as well as after it. A retiring hook can finish
          // its PUT (and acknowledge the outbox) while this GET is in flight; the
          // pre-request snapshot prevents that race from displaying stale text.
          const retainedBeforeLoad = peekRetainedWhiteboardPatch(pick.id);
          const full = createdDocument?.id === pick.id
            ? createdDocument
            : await getWhiteboardForDocument(baseUrl, pick.id, undefined, pick.incarnation);
          const retained = newestRetainedWhiteboardPatch(
            retainedBeforeLoad,
            peekRetainedWhiteboardPatch(pick.id),
          );
          return { list, pick, full, retained };
        };
        // On root-boundary recovery, the shared queue already owns ordering and
        // an explicit document id. Load immediately and overlay its snapshot so
        // a temporary network failure cannot strand the replacement UI blank.
        const loadInitialDocument = () => loadInitialDocumentOnce(baseUrl, loadDocument);
        const prepared = recoveringDocumentId
          ? await loadInitialDocument()
          : await prepareDocumentHandoff(loadInitialDocument);
        if (
          cancelled
          || seq !== switchSeq.current
          || !isActiveDocumentOperationOwner(lifecycleOwner)
        ) return;
        setDoc(applyRetainedWhiteboardPatch(prepared.full, prepared.retained));
        setCurrentDocumentIdentity(prepared.pick.id, prepared.full.incarnation);
        saveLastDocId(prepared.pick.id);
        setDocList(prepared.list.map((summary) => (
          summary.id === prepared.pick.id && prepared.retained
            ? {
              ...summary,
              ...(prepared.retained.patch.title !== undefined
                ? { title: prepared.retained.patch.title }
                : {}),
              ...(prepared.retained.patch.mode !== undefined
                ? { mode: prepared.retained.patch.mode }
                : {}),
            }
            : summary
        )));
        if (prepared.retained) schedulePatch(prepared.retained.patch);
        else setSaveStatus('idle');
        setLoading(false);
      } catch (err) {
        if (cancelled || seq !== switchSeq.current) return;
        setLoadError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      } finally {
        finishOperation?.();
        if (seq === switchSeq.current) navigationBusy.current = false;
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [ready, baseUrl, lifecycleOwner, schedulePatch]);

  // -- switch / create / delete / rename --
  const selectDocument = useCallback(
    async (id: string) => {
      if (!id || navigationBusy.current) return false;
      if (id === getCurrentDocId()) return true;
      navigationBusy.current = true;
      const seq = (switchSeq.current += 1);
      let finishOperation: (() => void) | null = null;
      let releaseInteraction: (() => void) | null = null;
      try {
        finishOperation = await acquireTrackedDocumentOperation();
        releaseInteraction = lockDocumentInteraction();
        if (!isActiveDocumentOperationOwner(lifecycleOwner)) return false;
        // Keep the old id active while loading the target. The writer can still
        // type during this request, so drain once before and once after it.
        const targetIncarnation = docList.find((candidate) => candidate.id === id)?.incarnation;
        if (!targetIncarnation) throw new Error('The document identity is stale; refresh and try again.');
        const full = await prepareDocumentHandoff(() =>
          getWhiteboardForDocument(baseUrl, id, undefined, targetIncarnation),
        );
        if (
          seq !== switchSeq.current
          || !isActiveDocumentOperationOwner(lifecycleOwner)
        ) return false;

        // No await between the final drain and this state handoff: a browser input
        // event cannot queue old-document blocks under the new active id.
        setDoc(full);
        setCurrentDocumentIdentity(id, full.incarnation);
        saveLastDocId(id);
        setSaveStatus('idle');
        setLoadError(null);
        return true;
      } catch (err) {
        if (seq !== switchSeq.current) return false;
        if (err instanceof DocumentCloseInProgressError) return false;
        setLoadError(
          `Document switch stopped; your current document is still open. ${
            err instanceof Error ? err.message : String(err)
          }`,
        );
        return false;
      } finally {
        releaseInteraction?.();
        finishOperation?.();
        if (seq === switchSeq.current) navigationBusy.current = false;
      }
    },
    [baseUrl, docList, lifecycleOwner],
  );

  const newDocument = useCallback(
    async (title?: string, mode?: string) => {
      if (navigationBusy.current) return false;
      navigationBusy.current = true;
      const seq = (switchSeq.current += 1);
      let finishOperation: (() => void) | null = null;
      let releaseInteraction: (() => void) | null = null;
      try {
        finishOperation = await acquireTrackedDocumentOperation();
        releaseInteraction = lockDocumentInteraction();
        if (!isActiveDocumentOperationOwner(lifecycleOwner)) return false;
        const createdDocument = await prepareDocumentHandoff(() =>
          createDocument(baseUrl, { title, mode }),
        );
        if (
          seq !== switchSeq.current
          || !isActiveDocumentOperationOwner(lifecycleOwner)
        ) return false;
        setDoc(createdDocument);
        setCurrentDocumentIdentity(createdDocument.id, createdDocument.incarnation);
        saveLastDocId(createdDocument.id);
        setSaveStatus('idle');
        setLoadError(null);
        await refreshList();
        return true;
      } catch (err) {
        if (seq !== switchSeq.current) return false;
        if (err instanceof DocumentCloseInProgressError) return false;
        // The create request may have succeeded before the second safety drain
        // failed. Refresh so that recoverable blank document remains visible.
        await refreshList();
        setLoadError(
          `New document stopped; your current document is still open. ${
            err instanceof Error ? err.message : String(err)
          }`,
        );
        return false;
      } finally {
        releaseInteraction?.();
        finishOperation?.();
        if (seq === switchSeq.current) navigationBusy.current = false;
      }
    },
    [baseUrl, lifecycleOwner, refreshList],
  );

  const deleteDocument = useCallback(
    async (id: string) => {
      if (!id || navigationBusy.current) return false;
      navigationBusy.current = true;
      const seq = (switchSeq.current += 1);
      let wasCurrent = false;
      let replacement: WhiteboardDocument | null = null;
      let finishOperation: (() => void) | null = null;
      let releaseInteraction: (() => void) | null = null;
      let writesBlocked = false;
      let backendDeleted = false;
      try {
        finishOperation = await acquireTrackedDocumentOperation();
        releaseInteraction = lockDocumentInteraction();
        if (!isActiveDocumentOperationOwner(lifecycleOwner)) return false;
        wasCurrent = id === getCurrentDocId();
        const deletingIncarnation = wasCurrent
          ? captureDocumentIncarnation(id)
          : docList.find((candidate) => candidate.id === id)?.incarnation ?? '';
        if (!deletingIncarnation) {
          throw new Error('The document identity is stale; refresh the library and try again.');
        }
        if (wasCurrent) {
          replacement = await prepareDocumentHandoff(async () => {
            const latest = await listDocuments(baseUrl);
            const existing = latest.find((candidate) => candidate.id !== id);
            return existing
              ? getWhiteboardForDocument(baseUrl, existing.id, undefined, existing.incarnation)
              : createDocument(baseUrl, {});
          });
        }

        // Tombstone renderer queues before draining them, then establish the
        // matching main-process fence. This closes both halves of the window in
        // which an already-copied unload PUT could otherwise follow DELETE.
        blockWhiteboardWrites(id);
        blockOutlineWrites(id);
        blockDocumentMutations(id);
        writesBlocked = true;
        await Promise.allSettled([
          waitForWhiteboardWrites(id),
          waitForOutlineWrites(id),
        ]);
        await waitForPendingDocWrites();
        const mainOwned = await deleteDocumentWithNativePersistenceFence(
          id,
          deletingIncarnation,
        );
        if (!mainOwned) {
          // Browser-preview fallback. Electron main owns this entire transaction
          // so it can finish after renderer loss; direct Vite preview still uses
          // bounded idempotent requests plus authoritative reconciliation.
          try {
            await deleteDocumentApi(baseUrl, id, deletingIncarnation);
          } catch (firstDeleteError) {
            try {
              await deleteDocumentApi(baseUrl, id, deletingIncarnation);
            } catch (retryDeleteError) {
              let stillExists: boolean | null = null;
              try {
                stillExists = await documentExists(baseUrl, id, deletingIncarnation);
              } catch {
                /* backend unavailable: preserve queues and surface the failure */
              }
              if (stillExists !== false) {
                console.error(
                  '[documents] delete and retry both failed:',
                  firstDeleteError,
                  retryDeleteError,
                );
                throw new Error('The document delete could not be confirmed.');
              }
            }
          }
        }
        backendDeleted = true;
        discardRetainedWhiteboardPatch(id);
        discardRetainedOutlineSnapshot(id);
        discardDocumentMutations(id);
        writesBlocked = false;
        if (
          seq !== switchSeq.current
          || !isActiveDocumentOperationOwner(lifecycleOwner)
        ) return false;
        if (wasCurrent && replacement) {
          discardPendingDocSaves();
          setDoc(replacement);
          setCurrentDocumentIdentity(replacement.id, replacement.incarnation);
          saveLastDocId(replacement.id);
          setSaveStatus('idle');
        }

        await refreshList();
        setLoadError(null);
        return true;
      } catch (err) {
        if (writesBlocked && !backendDeleted) {
          resumeWhiteboardWrites(id);
          resumeOutlineWrites(id);
          resumeDocumentMutations(id);
          writesBlocked = false;
          // DELETE failed, so edits made during it still belong to this live
          // document. Restart both retained queues before returning control.
          await Promise.allSettled([
            flushWhiteboardPatches(id),
            flushOutlineSnapshots(id),
          ]);
        }
        if (seq !== switchSeq.current) return false;
        if (err instanceof DocumentCloseInProgressError) return false;
        await refreshList();
        setLoadError(
          `Delete stopped. ${err instanceof Error ? err.message : String(err)}`,
        );
        return false;
      } finally {
        if (writesBlocked) {
          if (backendDeleted) {
            discardRetainedWhiteboardPatch(id);
            discardRetainedOutlineSnapshot(id);
            discardDocumentMutations(id);
          } else {
            resumeWhiteboardWrites(id);
            resumeOutlineWrites(id);
            resumeDocumentMutations(id);
          }
        }
        releaseInteraction?.();
        finishOperation?.();
        if (seq === switchSeq.current) navigationBusy.current = false;
      }
    },
    [baseUrl, docList, lifecycleOwner, refreshList],
  );

  const renameDocument = useCallback(
    async (title: string) => {
      if (!canStartDocumentMutationDuringClose()) return;
      const next = title.trim() || 'Untitled';
      const operationDocId = getCurrentDocId();
      setDoc((prev) => (prev ? { ...prev, title: next } : prev));
      queuePatch(operationDocId, { title: next });
      markPendingDocSave();
      try {
        await flushDocument(operationDocId);
        if (
          operationDocId !== getCurrentDocId()
          || !isActiveDocumentOperationOwner(lifecycleOwner)
        ) return;
        setLoadError(null);
        await refreshList();
      } catch (err) {
        if (
          operationDocId !== getCurrentDocId()
          || !isActiveDocumentOperationOwner(lifecycleOwner)
        ) return;
        // The shared outbox already retains the newest title. Keep the writer's
        // latest intent visible and retryable instead of overwriting it with an
        // older optimistic rollback from another in-flight rename.
        setLoadError(`Rename stopped: ${err instanceof Error ? err.message : String(err)}`);
      }
    },
    [flushDocument, lifecycleOwner, queuePatch, refreshList],
  );

  const dismissError = useCallback(() => setLoadError(null), []);

  // -- writing mode (active document) --
  const setMode = useCallback(
    async (requested: string) => {
      if (!canStartDocumentMutationDuringClose()) return false;
      // `series` is not a Whiteboard mode — normalize it to `novel`.
      const mode = requested === 'series' ? 'novel' : requested;
      const operationDocId = getCurrentDocId();
      setDoc((prev) => (prev ? { ...prev, mode } : prev));
      queuePatch(operationDocId, { mode });
      markPendingDocSave();
      try {
        await flushDocument(operationDocId);
        if (
          operationDocId !== getCurrentDocId()
          || !isActiveDocumentOperationOwner(lifecycleOwner)
        ) return false;
        setSaveStatus('saved');
        setLoadError(null);
        onSavedRef.current?.();
        await refreshList();
        return true;
      } catch (err) {
        if (
          operationDocId !== getCurrentDocId()
          || !isActiveDocumentOperationOwner(lifecycleOwner)
        ) return false;
        // Retain the latest requested mode in both UI and outbox. Rolling back
        // here can race a newer request and replace it with a value that was
        // never actually persisted.
        setSaveStatus('error');
        setLoadError(`Mode save stopped: ${err instanceof Error ? err.message : String(err)}`);
        return false;
      }
    },
    [flushDocument, lifecycleOwner, queuePatch, refreshList],
  );

  // A root render fallback can unmount this hook. Start the pending save now;
  // the renderer-memory outbox above remains available if the request fails or
  // races the replacement hook's reload.
  useEffect(
    () => () => {
      const documentId = timerDocId.current || getCurrentDocId();
      if (timer.current) clearTimeout(timer.current);
      timer.current = null;
      timerDocId.current = '';
      if (peekRetainedWhiteboardPatch(documentId)) {
        void flushDocument(documentId).catch(() => {});
      }
    },
    [flushDocument],
  );

  return {
    doc,
    docList,
    loading,
    loadError,
    dismissError,
    saveStatus,
    onChangeBlocks,
    onChangeSettings,
    setMode,
    selectDocument,
    newDocument,
    deleteDocument,
    renameDocument,
  };
}
