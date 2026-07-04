/**
 * Desktop document file actions: current file path, dirty flag, save status, and
 * New / Open / Save / Save As. The native File menu and the in-app File dropdown
 * both call THIS one pathway. Backend autosave keeps the session; these write the
 * user-chosen file. A document stays dirty until an explicit file Save/Open/New.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import type { WhiteboardBlock } from '../whiteboard/types';
import { fileApi, onMenuFile } from './fileApi';
import { baseName, blocksToText, suggestedFileName, textToBlocks } from './fileSerialize';
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
  onNewDocument?: () => void | Promise<void>;
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
  saveDocumentAs: () => void;
  /**
   * Run the unsaved-changes guard (Save / Don't Save / Cancel) before a
   * destructive action like an import-replace. Resolves true to proceed, false
   * to abort. No-op (returns true) when the document is clean.
   */
  confirmProceedPastUnsavedChanges: (reason: string) => Promise<boolean>;
}

export function useFileActions({ getBlocks, loadBlocks, mode, onNewDocument }: Options): FileActionsApi {
  const [filePath, setFilePath] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [status, setStatus] = useState<FileStatus>('saved');

  const getBlocksRef = useRef(getBlocks);
  getBlocksRef.current = getBlocks;
  const loadBlocksRef = useRef(loadBlocks);
  loadBlocksRef.current = loadBlocks;
  const modeRef = useRef(mode);
  modeRef.current = mode;
  const filePathRef = useRef(filePath);
  filePathRef.current = filePath;
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;
  const onNewDocumentRef = useRef(onNewDocument);
  onNewDocumentRef.current = onNewDocument;
  const suppressDirty = useRef(false);

  // Mirror dirty state to main (drives the close/quit save prompt).
  useEffect(() => {
    fileApi.setDirty(dirty);
  }, [dirty]);

  const markDirty = useCallback(() => {
    if (suppressDirty.current) return;
    setDirty(true);
    setStatus('unsaved');
  }, []);

  const loadInto = useCallback((blocks: WhiteboardBlock[], path: string | null) => {
    suppressDirty.current = true;
    loadBlocksRef.current(blocks);
    setFilePath(path);
    setDirty(false);
    setStatus('saved');
    setTimeout(() => {
      suppressDirty.current = false;
    }, 0);
  }, []);

  const doSaveAs = useCallback(async (): Promise<boolean> => {
    try {
      setStatus('saving');
      const res = await fileApi.saveAs(
        blocksToText(getBlocksRef.current()),
        suggestedFileName(filePathRef.current, modeRef.current),
      );
      if (res.canceled) {
        setStatus(dirtyRef.current ? 'unsaved' : 'saved');
        return false;
      }
      if (!res.ok) {
        setStatus('error');
        return false;
      }
      setFilePath(res.filePath ?? null);
      setDirty(false);
      setStatus('saved');
      return true;
    } catch (err) {
      console.error('[files] saveAs failed:', err);
      setStatus('error');
      return false;
    }
  }, []);

  const doSave = useCallback(async (): Promise<boolean> => {
    const path = filePathRef.current;
    if (!path) return doSaveAs();
    try {
      setStatus('saving');
      const res = await fileApi.saveToPath(path, blocksToText(getBlocksRef.current()));
      if (!res.ok) {
        setStatus('error');
        return false;
      }
      setDirty(false);
      setStatus('saved');
      return true;
    } catch (err) {
      console.error('[files] save failed:', err);
      setStatus('error');
      return false;
    }
  }, [doSaveAs]);

  // If there are unsaved changes, ask; returns false to abort the operation.
  const confirmProceed = useCallback(
    async (reason: string): Promise<boolean> => {
      if (!dirtyRef.current) return true;
      const choice = await fileApi.confirmSaveChanges(reason);
      if (choice === 'cancel') return false;
      if (choice === 'save') return doSave();
      return true; // dont-save
    },
    [doSave],
  );

  const newDocument = useCallback(async () => {
    if (!(await confirmProceed('Save changes before creating a new document?'))) return;
    const createFresh = onNewDocumentRef.current;
    if (createFresh) {
      // Create a genuinely fresh document (blank manuscript + its own empty
      // outline/comments); the editor re-mounts on the new doc id. Reset the file
      // association so the new document starts as an unsaved, clean slate.
      await createFresh();
      setFilePath(null);
      setDirty(false);
      setStatus('saved');
    } else {
      loadInto(BLANK, null);
    }
  }, [confirmProceed, loadInto]);

  const openDocument = useCallback(async () => {
    if (!(await confirmProceed('Save changes before opening another document?'))) return;
    try {
      const res = await fileApi.open();
      if (res.canceled) return;
      if (!res.ok) {
        setStatus('error');
        return;
      }
      loadInto(textToBlocks(res.content ?? ''), res.filePath ?? null);
    } catch (err) {
      console.error('[files] open failed:', err);
      setStatus('error');
    }
  }, [confirmProceed, loadInto]);

  // Native File-menu actions (mouse + accelerators).
  useEffect(() => {
    return onMenuFile((action) => {
      if (action === 'new') void newDocument();
      else if (action === 'open') void openDocument();
      else if (action === 'save') void doSave();
      else if (action === 'save-as') void doSaveAs();
    });
  }, [newDocument, openDocument, doSave, doSaveAs]);

  // Main asks us to save during a window close / quit; reply with the result.
  useEffect(
    () =>
      fileApi.onSaveBeforeClose(() => {
        void doSave().then((ok) => fileApi.sendCloseResult(ok));
      }),
    [doSave],
  );

  return {
    filePath,
    fileName: filePath ? baseName(filePath) : 'Untitled',
    dirty,
    status,
    markDirty,
    newDocument: () => void newDocument(),
    openDocument: () => void openDocument(),
    saveDocument: () => void doSave(),
    saveDocumentAs: () => void doSaveAs(),
    confirmProceedPastUnsavedChanges: confirmProceed,
  };
}
