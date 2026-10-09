import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron';

import type { CoreStatus, RendererLiveContextPayload } from './core-manager';
import type {
  DesktopSessionState,
  DialogFilter,
  LayoutSaveOptions,
  OpenFileResult,
  SaveFileResult,
} from './file-manager';
import type {
  NativePanelWindowChannels,
  NativePanelWindowBounds,
  NativePanelWindowEvent,
  NativePanelWindowFramePrefix,
} from './native-panel-windows';

// Keep runtime values inline: sandboxed Electron preloads cannot require local
// CommonJS modules unless the preload is first bundled into one file.
const NATIVE_PANEL_WINDOW_CHANNELS = {
  event: 'native-panel:event',
  show: 'native-panel:show',
  focus: 'native-panel:focus',
  minimize: 'native-panel:minimize',
  restore: 'native-panel:restore',
  close: 'native-panel:close',
  bounds: 'native-panel:bounds',
} as const satisfies NativePanelWindowChannels;

const NATIVE_PANEL_WINDOW_FRAME_PREFIX: NativePanelWindowFramePrefix = 'logosforge-panel:';
const nativePanelWindowFrameName = (panelId: string, token: string): string => (
  `${NATIVE_PANEL_WINDOW_FRAME_PREFIX}${panelId}:${token}`
);

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
  publishLiveContext(context: RendererLiveContextPayload): Promise<void>;
  clearLiveContext(): Promise<void>;

  openFile(filters?: DialogFilter[]): Promise<OpenFileResult>;
  saveFile(payload: { suggestedName?: string; content?: string; contentBase64?: string; mimeType?: string }): Promise<SaveFileResult>;
  openExternal(target: string): Promise<void>;
  loadLayout(projectId: number): Promise<unknown | null>;
  loadLayoutBackup(projectId: number): Promise<unknown | null>;
  saveLayout(projectId: number, layout: unknown, options?: LayoutSaveOptions): Promise<void>;
  loadDesktopSessionState(): Promise<DesktopSessionState | null>;
  saveLastActiveProjectId(projectId: number | null): Promise<void>;
  loadProgressionCommandRecovery(storageKey: string): Promise<string | null>;
  saveProgressionCommandRecovery(storageKey: string, value: string): Promise<void>;
  removeProgressionCommandRecovery(storageKey: string, expectedValue: string): Promise<boolean>;
  onSaveBeforeClose(cb: (attemptId: number) => void): () => void;
  onCloseCancelled(cb: () => void): () => void;
  sendCloseResult(attemptId: number, saved: boolean): void;

  /** Acquisition-specific frame name; main validates both id and token. */
  nativePanelWindowFrameName(panelId: string, token: string): string;
  /** Reveal only after the renderer has installed the portal and adopted styles. */
  showNativePanelWindow(panelId: string, token: string, activate?: boolean): Promise<boolean>;
  focusNativePanelWindow(panelId: string, token: string): Promise<boolean>;
  minimizeNativePanelWindow(panelId: string, token: string): Promise<boolean>;
  restoreNativePanelWindow(panelId: string, token: string): Promise<boolean>;
  /** Authorize destruction after the renderer has committed its layout update. */
  closeNativePanelWindow(panelId: string, token: string): Promise<boolean>;
  getNativePanelWindowBounds(panelId: string, token: string): Promise<NativePanelWindowBounds | null>;
  onNativePanelWindowEvent(cb: (event: NativePanelWindowEvent) => void): () => void;

  /** Menu → renderer commands (see electron/menu.ts for the grammar). */
  onMenuCommand(cb: (command: string) => void): () => void;
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
  publishLiveContext: (context) => ipcRenderer.invoke('live-context:publish', context),
  clearLiveContext: () => ipcRenderer.invoke('live-context:clear'),

  openFile: (filters) => ipcRenderer.invoke('file:open', { filters }),
  saveFile: (payload) => ipcRenderer.invoke('file:save', payload),
  openExternal: (target) => ipcRenderer.invoke('shell:open-external', { target }),
  loadLayout: (projectId) => ipcRenderer.invoke('layout:load', { projectId }),
  loadLayoutBackup: (projectId) => ipcRenderer.invoke('layout:load-backup', { projectId }),
  saveLayout: (projectId, layout, options) => ipcRenderer.invoke('layout:save', {
    projectId,
    layout,
    preserveBackup: options?.preserveBackup === true,
  }),
  loadDesktopSessionState: () => ipcRenderer.invoke('session:load'),
  saveLastActiveProjectId: (projectId) => ipcRenderer.invoke('session:save-last-project', { projectId }),
  loadProgressionCommandRecovery: (storageKey) => ipcRenderer.invoke(
    'progression-command:load',
    { storageKey },
  ),
  saveProgressionCommandRecovery: (storageKey, value) => ipcRenderer.invoke(
    'progression-command:save',
    { storageKey, value },
  ),
  removeProgressionCommandRecovery: (storageKey, expectedValue) => ipcRenderer.invoke(
    'progression-command:remove',
    { storageKey, expectedValue },
  ),
  onSaveBeforeClose: (cb) => subscribe<number>('app:save-before-close', cb),
  onCloseCancelled: (cb) => subscribe<void>('app:close-cancelled', () => cb()),
  sendCloseResult: (attemptId, saved) => ipcRenderer.send('app:close-result', attemptId, saved),

  nativePanelWindowFrameName,
  showNativePanelWindow: (panelId, token, activate = false) => ipcRenderer.invoke(
    NATIVE_PANEL_WINDOW_CHANNELS.show,
    { panelId, token, activate },
  ),
  focusNativePanelWindow: (panelId, token) => ipcRenderer.invoke(
    NATIVE_PANEL_WINDOW_CHANNELS.focus,
    { panelId, token },
  ),
  minimizeNativePanelWindow: (panelId, token) => ipcRenderer.invoke(
    NATIVE_PANEL_WINDOW_CHANNELS.minimize,
    { panelId, token },
  ),
  restoreNativePanelWindow: (panelId, token) => ipcRenderer.invoke(
    NATIVE_PANEL_WINDOW_CHANNELS.restore,
    { panelId, token },
  ),
  closeNativePanelWindow: (panelId, token) => ipcRenderer.invoke(
    NATIVE_PANEL_WINDOW_CHANNELS.close,
    { panelId, token },
  ),
  getNativePanelWindowBounds: (panelId, token) => ipcRenderer.invoke(
    NATIVE_PANEL_WINDOW_CHANNELS.bounds,
    { panelId, token },
  ),
  onNativePanelWindowEvent: (cb) => subscribe<NativePanelWindowEvent>(NATIVE_PANEL_WINDOW_CHANNELS.event, cb),

  onMenuCommand: (cb) => subscribe<string>('menu:command', cb),
};

contextBridge.exposeInMainWorld('logosforge', api);
console.log('[preload] window.logosforge exposed:', Object.keys(api));
