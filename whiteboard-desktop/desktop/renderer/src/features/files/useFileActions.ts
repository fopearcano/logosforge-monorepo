/**
 * Desktop document file actions: current file path, dirty flag, save status, and
 * New / Open / Save / Save As. The native File menu and the in-app File dropdown
 * both call THIS one pathway. Backend autosave keeps the session; these write the
 * user-chosen file. A document stays dirty until an explicit file Save/Open/New.
 */

import { useCallback, useEffect, useRef, useSyncExternalStore } from 'react';

import { isModalDialogOpen } from '../../components/useModalDialog';
import { flushPendingDocSaves, getCurrentDocId } from '../../state/currentDocument';
import { isDocumentInteractionLocked } from '../whiteboard/documentOperationGuard';
import type { WhiteboardBlock } from '../whiteboard/types';
import { freshBlockIds } from '../whiteboard/blockIdentity';
import { fileApi, onMenuFile } from './fileApi';
import { baseName, blocksToText, suggestedFileName, textToBlocks } from './fileSerialize';
import {
  captureFileSession,
  completeFileSessionSave,
  getFileSessionState,
  isFileSessionContextCurrent,
  markFileSessionDirty,
  replaceFileSessionContext,
  runSerializedFileSave,
  setFileSessionStatusIfCurrent,
  subscribeFileSessionState,
  updateFileSessionState,
  waitForPendingFileSaves,
  type FileSessionToken,
} from './fileSessionStore';
import type { FileStatus } from './fileTypes';

const BLANK: WhiteboardBlock[] = [{ id: 'b0', type: 'paragraph', text: '' }];

interface Options {
  getBlocks: () => WhiteboardBlock[];
  loadBlocks: (blocks: WhiteboardBlock[]) => void;
  mode: string;
  /**
   * How "New" makes a blank slate. In the document-backed Whiteboard this creates
   * a fresh DOCUMENT (blank manuscript AND its own empty outline/comments) rather
   * than only blanking the editor — otherwise the current document's outline is
   * left orphaned against an empty manuscript. When omitted, New falls back to
   * blanking the editor in place (the file-only behaviour).
   */
  onNewDocument?: () => void | boolean | Promise<void | boolean>;
}

export interface FileActionsApi {
  filePath: string | null;
  fileName: string;
  dirty: boolean;
  status: FileStatus;
  /** Called by the editor on every user edit. */
  markDirty: () => void;
  newDocument: () => void;
  openDocument: () => void;
  saveDocument: () => void;
  /** Save the current live manuscript to a user-chosen file; false means canceled/failed. */
  saveDocumentAs: () => Promise<boolean>;
  /** Clear the disk-file association after switching backend documents. */
  resetForDocument: () => void;
  /**
   * Run the unsaved-changes guard (Save / Don't Save / Cancel) before a
   * destructive action like an import-replace. Resolves true to proceed, false
   * to abort. No-op (returns true) when the document is clean.
   */
  confirmProceedPastUnsavedChanges: (reason: string) => Promise<boolean>;
}

interface SaveRequest {
  allowInteractionLock?: boolean;
  expectedContext?: FileSessionToken;
  forceSaveAs?: boolean;
}

function isOperationCurrent(token: FileSessionToken, allowInteractionLock = false): boolean {
  return (
    isFileSessionContextCurrent(token, getCurrentDocId()) &&
    (allowInteractionLock || !isDocumentInteractionLocked())
  );
}

function isOperationUnchanged(token: FileSessionToken, allowInteractionLock = false): boolean {
  return (
    isOperationCurrent(token, allowInteractionLock) &&
    token.contentRevision === getFileSessionState().contentRevision
  );
}

export function useFileActions({ getBlocks, loadBlocks, mode, onNewDocument }: Options): FileActionsApi {
  const { filePath, dirty, status } = useSyncExternalStore(
    subscribeFileSessionState,
    getFileSessionState,
    getFileSessionState,
  );

  const getBlocksRef = useRef(getBlocks);
  getBlocksRef.current = getBlocks;
  const loadBlocksRef = useRef(loadBlocks);
  loadBlocksRef.current = loadBlocks;
  const modeRef = useRef(mode);
  modeRef.current = mode;
  const onNewDocumentRef = useRef(onNewDocument);
  onNewDocumentRef.current = onNewDocument;
  const suppressDirty = useRef(false);
  const updateStatus = useCallback((next: FileStatus) => {
    updateFileSessionState({ status: next });
  }, []);

  // Mirror dirty state to main (drives the close/quit save prompt).
  useEffect(() => {
    fileApi.setDirty(dirty);
  }, [dirty]);

  const markDirty = useCallback(() => {
    if (suppressDirty.current) return;
    markFileSessionDirty();
  }, []);

  const loadInto = useCallback((blocks: WhiteboardBlock[], path: string | null) => {
    suppressDirty.current = true;
    loadBlocksRef.current(blocks);
    replaceFileSessionContext(path);
    setTimeout(() => {
      suppressDirty.current = false;
    }, 0);
  }, []);

  const resetForDocument = useCallback(() => {
    replaceFileSessionContext(null);
  }, []);

  const runSave = useCallback(async (request: SaveRequest = {}): Promise<boolean> => {
    const allowInteractionLock = request.allowInteractionLock ?? false;
    const requestedContext = request.expectedContext ?? captureFileSession(getCurrentDocId());
    if (!isOperationCurrent(requestedContext, allowInteractionLock)) return false;

    return runSerializedFileSave(async () => {
      // The document or file context may have changed while this request waited
      // behind an earlier disk write. Never save or mutate the replacement.
      if (!isOperationCurrent(requestedContext, allowInteractionLock)) return false;

      const snapshot = captureFileSession(getCurrentDocId());
      const session = getFileSessionState();
      const saveAs = request.forceSaveAs || !session.filePath;
      const content = blocksToText(getBlocksRef.current());
      setFileSessionStatusIfCurrent(snapshot, getCurrentDocId(), 'saving');

      try {
        const result = saveAs
          ? await fileApi.saveAs(
              content,
              suggestedFileName(session.filePath, modeRef.current),
            )
          : await fileApi.saveToPath(session.filePath as string, content);

        // Save dialogs and IPC writes yield to document navigation. The write may
        // already have happened, but its response must never update a new context.
        if (!isFileSessionContextCurrent(snapshot, getCurrentDocId())) return false;
        if (!allowInteractionLock && isDocumentInteractionLocked()) {
          setFileSessionStatusIfCurrent(
            snapshot,
            getCurrentDocId(),
            getFileSessionState().dirty ? 'unsaved' : 'saved',
          );
          return false;
        }
        if (result.canceled) {
          setFileSessionStatusIfCurrent(
            snapshot,
            getCurrentDocId(),
            getFileSessionState().dirty ? 'unsaved' : 'saved',
          );
          return false;
        }
        if (!result.ok) {
          setFileSessionStatusIfCurrent(snapshot, getCurrentDocId(), 'error');
          return false;
        }
        if (saveAs && !result.filePath) {
          console.error('[files] saveAs succeeded without returning a file path');
          setFileSessionStatusIfCurrent(snapshot, getCurrentDocId(), 'error');
          return false;
        }

        const completion = completeFileSessionSave(
          snapshot,
          getCurrentDocId(),
          saveAs ? result.filePath : undefined,
        );
        // An edit made while the write was in flight remains dirty. Callers that
        // plan to discard/navigate must treat that as an incomplete save.
        return completion.currentContext && completion.clean;
      } catch (err) {
        console.error(saveAs ? '[files] saveAs failed:' : '[files] save failed:', err);
        if (isOperationCurrent(snapshot, allowInteractionLock)) {
          setFileSessionStatusIfCurrent(snapshot, getCurrentDocId(), 'error');
        }
        return false;
      }
    });
  }, []);

  const doSaveAs = useCallback(
    (request: Omit<SaveRequest, 'forceSaveAs'> = {}): Promise<boolean> =>
      runSave({ ...request, forceSaveAs: true }),
    [runSave],
  );

  const doSave = useCallback(
    (request: Omit<SaveRequest, 'forceSaveAs'> = {}): Promise<boolean> => runSave(request),
    [runSave],
  );

  // If there are unsaved changes, ask; returns false to abort the operation.
  const confirmProceed = useCallback(
    async (reason: string): Promise<boolean> => {
      const operation = captureFileSession(getCurrentDocId());
      if (!isOperationCurrent(operation)) return false;
      if (!getFileSessionState().dirty) return true;
      const choice = await fileApi.confirmSaveChanges(reason);
      if (!isOperationCurrent(operation)) return false;
      if (choice === 'cancel') return false;
      if (choice === 'save') {
        const saved = await doSave({ expectedContext: operation });
        return saved && isOperationCurrent(operation);
      }
      // "Don't Save" covers only the revision visible when the dialog opened.
      return isOperationUnchanged(operation);
    },
    [doSave],
  );

  const newDocument = useCallback(async () => {
    let operation = captureFileSession(getCurrentDocId());
    if (!isOperationCurrent(operation)) return;
    const createFresh = onNewDocumentRef.current;
    // In the document-backed app, an unassociated draft remains safely in the
    // library, so creating another document is not destructive. Ask only when
    // leaving an external disk file behind (or in file-only fallback mode).
    if (
      (!createFresh || getFileSessionState().filePath) &&
      !(await confirmProceed('Save changes before creating a new document?'))
    ) return;
    operation = captureFileSession(getCurrentDocId());
    if (!isOperationUnchanged(operation)) return;
    if (createFresh) {
      // Create a genuinely fresh document (blank manuscript + its own empty
      // outline/comments); the editor re-mounts on the new doc id. Reset the file
      // association so the new document starts as an unsaved, clean slate.
      const created = await createFresh();
      if (created === false) return;
      resetForDocument();
    } else {
      loadInto(BLANK, null);
    }
  }, [confirmProceed, loadInto, resetForDocument]);

  const openDocument = useCallback(async () => {
    let operation = captureFileSession(getCurrentDocId());
    if (!isOperationCurrent(operation)) return;
    if (!(await confirmProceed('Save changes before opening another document?'))) return;
    operation = captureFileSession(getCurrentDocId());
    if (!isOperationUnchanged(operation)) return;
    try {
      // Do not let an older Save-to-the-same-path finish after Open has read and
      // installed that file as a clean context.
      await waitForPendingFileSaves();
      if (!isOperationUnchanged(operation)) return;
      const res = await fileApi.open();
      if (!isOperationUnchanged(operation)) return;
      if (res.canceled) return;
      if (!res.ok) {
        updateStatus('error');
        return;
      }
      const parsed = textToBlocks(res.content ?? '');
      const ids = freshBlockIds(parsed.length);
      loadInto(parsed.map((block, index) => ({ ...block, id: ids[index] })), res.filePath ?? null);
    } catch (err) {
      console.error('[files] open failed:', err);
      if (isOperationCurrent(operation)) updateStatus('error');
    }
  }, [confirmProceed, loadInto, updateStatus]);

  // Native File-menu actions (mouse + accelerators).
  useEffect(() => {
    return onMenuFile((action) => {
      if (isModalDialogOpen() || isDocumentInteractionLocked()) return;
      if (action === 'new') void newDocument();
      else if (action === 'open') void openDocument();
      else if (action === 'save') void doSave();
      else if (action === 'save-as') void doSaveAs();
    });
  }, [newDocument, openDocument, doSave, doSaveAs]);

  // Main asks us to save during a window close / quit; reply with the result.
  useEffect(() => {
    const unsubscribe = fileApi.onSaveBeforeClose((requestId) => {
      void (async () => {
        try {
          // Capture edits made after the app-lifetime close drain but before
          // the external file snapshot is written.
          await flushPendingDocSaves();
          fileApi.sendCloseResult(
            requestId,
            await doSave({ allowInteractionLock: true }),
          );
        } catch (error) {
          console.error('[close] save-before-close failed:', error);
          fileApi.sendCloseResult(requestId, false);
        }
      })();
    });
    // Unlike document autosave readiness, this capability belongs to the
    // faultable App tree because doSave captures the mounted editor instance.
    fileApi.setExternalSaveHandshakeReady(true);
    return () => {
      fileApi.setExternalSaveHandshakeReady(false);
      unsubscribe();
    };
  }, [doSave]);

  return {
    filePath,
    fileName: filePath ? baseName(filePath) : 'Untitled',
    dirty,
    status,
    markDirty,
    newDocument: () => void newDocument(),
    openDocument: () => void openDocument(),
    saveDocument: () => void doSave(),
    saveDocumentAs: doSaveAs,
    resetForDocument,
    confirmProceedPastUnsavedChanges: confirmProceed,
  };
}
