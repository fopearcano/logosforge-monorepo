import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron';

import type { BackendStatus } from './backend-manager';
import type {
  DialogFilter,
  ImportMode,
  OpenResult,
  SaveChoice,
  SaveResult,
} from './file-manager';

/**
 * IMPORTANT: every method is exposed at the TOP LEVEL (flat), not nested under a
 * `files` object. A nested object was being dropped by contextBridge in the
 * sandboxed renderer (top-level functions came through, the nested object did
 * not), which is why Open/Save/Save As silently no-op'd. Flat functions are
 * reliably exposed — the renderer re-composes them into a `files` façade.
 */
export interface LogosForgeApi {
  getBackendStatus(): Promise<BackendStatus>;
  onBackendStatus(cb: (status: BackendStatus) => void): () => void;

  fileOpen(): Promise<OpenResult>;
  fileSaveAs(content: string, suggestedName: string): Promise<SaveResult>;
  fileSaveToPath(filePath: string, content: string): Promise<SaveResult>;
  fileConfirmSaveChanges(reason?: string): Promise<SaveChoice>;
  fileSetDirty(dirty: boolean): void;
  fileOnSaveBeforeClose(cb: () => void): () => void;
  fileSendCloseResult(ok: boolean): void;

  importOpen(filters: DialogFilter[]): Promise<OpenResult>;
  importConfirmMode(): Promise<ImportMode>;
  exportSave(content: string, suggestedName: string, filters: DialogFilter[]): Promise<SaveResult>;

  onMenuFile(cb: (action: string) => void): () => void;
  onMenuView(cb: (action: string) => void): () => void;
}

function subscribe<T>(channel: string, cb: (payload: T) => void): () => void {
  const listener = (_event: IpcRendererEvent, payload: T) => cb(payload);
  ipcRenderer.on(channel, listener);
  return () => ipcRenderer.removeListener(channel, listener);
}

const api: LogosForgeApi = {
  getBackendStatus: () => ipcRenderer.invoke('backend:get-status'),
  onBackendStatus: (cb) => subscribe<BackendStatus>('backend:status', cb),

  fileOpen: () => ipcRenderer.invoke('file:open-dialog'),
  fileSaveAs: (content, suggestedName) =>
    ipcRenderer.invoke('file:save-dialog', { content, currentPath: null, suggestedName }),
  fileSaveToPath: (filePath, content) => ipcRenderer.invoke('file:save-to-path', { filePath, content }),
  fileConfirmSaveChanges: (reason) => ipcRenderer.invoke('file:confirm-save-changes', { reason }),
  fileSetDirty: (dirty) => ipcRenderer.send('file:set-dirty', dirty),
  fileOnSaveBeforeClose: (cb) => subscribe<void>('app:save-before-close', () => cb()),
  fileSendCloseResult: (ok) => ipcRenderer.send('app:close-result', ok),

  importOpen: (filters) => ipcRenderer.invoke('import:open-dialog', { filters }),
  importConfirmMode: () => ipcRenderer.invoke('import:confirm-mode'),
  exportSave: (content, suggestedName, filters) =>
    ipcRenderer.invoke('export:save-dialog', { content, suggestedName, filters }),

  onMenuFile: (cb) => subscribe<string>('menu:file', cb),
  onMenuView: (cb) => subscribe<string>('menu:view', cb),
};

contextBridge.exposeInMainWorld('logosforge', api);
console.log('[preload] logosforge exposed (flat) keys:', Object.keys(api));
