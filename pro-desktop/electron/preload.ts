import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron';

import type { CoreStatus } from './core-manager';
import type { DialogFilter, OpenFileResult, SaveFileResult } from './file-manager';

/**
 * The `window.logosforge` surface exposed to the renderer. Every method is FLAT
 * (not nested) — contextBridge reliably exposes top-level functions in the
 * sandboxed renderer. The renderer's platform.ts re-composes these into the
 * pro-shared-ui `PlatformAdapter`.
 */
export interface LogosForgeDesktop {
  /** Base URL of the core HTTP API (e.g. http://127.0.0.1:8765) — pass to createHttpApiClient. */
  coreBaseUrl(): Promise<string>;
  getCoreStatus(): Promise<CoreStatus>;
  onCoreStatus(cb: (status: CoreStatus) => void): () => void;

  openFile(filters?: DialogFilter[]): Promise<OpenFileResult>;
  saveFile(payload: { suggestedName?: string; content?: string; contentBase64?: string; mimeType?: string }): Promise<SaveFileResult>;
  openExternal(target: string): Promise<void>;
  loadLayout(projectId: number): Promise<unknown | null>;
  saveLayout(projectId: number, layout: unknown): Promise<void>;
}

function subscribe<T>(channel: string, cb: (payload: T) => void): () => void {
  const listener = (_e: IpcRendererEvent, payload: T) => cb(payload);
  ipcRenderer.on(channel, listener);
  return () => ipcRenderer.removeListener(channel, listener);
}

const api: LogosForgeDesktop = {
  coreBaseUrl: () => ipcRenderer.invoke('core:base-url'),
  getCoreStatus: () => ipcRenderer.invoke('core:get-status'),
  onCoreStatus: (cb) => subscribe<CoreStatus>('core:status', cb),

  openFile: (filters) => ipcRenderer.invoke('file:open', { filters }),
  saveFile: (payload) => ipcRenderer.invoke('file:save', payload),
  openExternal: (target) => ipcRenderer.invoke('shell:open-external', { target }),
  loadLayout: (projectId) => ipcRenderer.invoke('layout:load', { projectId }),
  saveLayout: (projectId, layout) => ipcRenderer.invoke('layout:save', { projectId, layout }),
};

contextBridge.exposeInMainWorld('logosforge', api);
console.log('[preload] window.logosforge exposed:', Object.keys(api));
