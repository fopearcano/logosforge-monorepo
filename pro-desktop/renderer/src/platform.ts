import type { PlatformAdapter } from '@logosforge/pro-shared-ui';
import type {
  NativePanelWindowBounds as HostNativePanelWindowBounds,
  NativePanelWindowEvent as HostNativePanelWindowEvent,
} from '../../electron/native-panel-windows';

export type CoreStatus = {
  state: 'connecting' | 'connected' | 'error';
  baseUrl: string;
  managed: boolean;
  detail?: string;
  authToken?: string;
};

export type LiveContextPayload = {
  projectId: number | null;
  activePanelId: string | null;
  activeSceneId: number | null;
  selectionSection: string | null;
  selection: string;
};

export type DesktopSessionState = {
  version: number;
  lastActiveProjectId: number | null;
};

/** Absolute outer-window screen bounds in Electron device-independent pixels (DIP). */
export type NativePanelWindowBounds = HostNativePanelWindowBounds;
export type NativePanelWindowEvent = HostNativePanelWindowEvent;

/** The flat `window.logosforge` surface exposed by the Electron preload. */
export interface DesktopBridge {
  coreBaseUrl(): Promise<string>;
  getCoreStatus(): Promise<CoreStatus>;
  onCoreStatus(cb: (s: CoreStatus) => void): () => void;
  publishLiveContext(context: LiveContextPayload): Promise<void>;
  clearLiveContext(): Promise<void>;
  openFile(filters?: { name: string; extensions: string[] }[]): Promise<{ canceled: boolean; path?: string; content?: string; contentBase64?: string }>;
  saveFile(p: { suggestedName?: string; content?: string; contentBase64?: string; mimeType?: string }): Promise<{ canceled: boolean; path?: string }>;
  openExternal(target: string): Promise<void>;
  loadLayout(projectId: number): Promise<unknown | null>;
  loadLayoutBackup(projectId: number): Promise<unknown | null>;
  saveLayout(projectId: number, layout: unknown, options?: { preserveBackup?: boolean }): Promise<void>;
  loadDesktopSessionState(): Promise<DesktopSessionState | null>;
  saveLastActiveProjectId(projectId: number | null): Promise<void>;
  loadProgressionCommandRecovery(storageKey: string): Promise<string | null>;
  saveProgressionCommandRecovery(storageKey: string, value: string): Promise<void>;
  removeProgressionCommandRecovery(storageKey: string, expectedValue: string): Promise<boolean>;
  onSaveBeforeClose(cb: (attemptId: number) => void): () => void;
  onCloseCancelled(cb: () => void): () => void;
  sendCloseResult(attemptId: number, saved: boolean): void;
  nativePanelWindowFrameName(panelId: string, token: string): string;
  showNativePanelWindow(panelId: string, token: string, activate?: boolean): Promise<boolean>;
  focusNativePanelWindow(panelId: string, token: string): Promise<boolean>;
  minimizeNativePanelWindow(panelId: string, token: string): Promise<boolean>;
  restoreNativePanelWindow(panelId: string, token: string): Promise<boolean>;
  closeNativePanelWindow(panelId: string, token: string): Promise<boolean>;
  getNativePanelWindowBounds(panelId: string, token: string): Promise<NativePanelWindowBounds | null>;
  onNativePanelWindowEvent(cb: (event: NativePanelWindowEvent) => void): () => void;
  onMenuCommand(cb: (command: string) => void): () => void;
}

declare global {
  interface Window {
    logosforge?: DesktopBridge;
  }
}

/** Present only when running inside the Electron shell (preload exposed it). */
export const desktop: DesktopBridge | undefined = window.logosforge;

/** The pro-shared-ui PlatformAdapter, backed by the Electron host. */
export const platform: PlatformAdapter = {
  isDesktop: true,
  persistenceScope: 'logosforge-pro-desktop-local-core',
  progressionCommandStorage: {
    getItem: (storageKey) => desktop!.loadProgressionCommandRecovery(storageKey),
    setItem: (storageKey, value) => desktop!.saveProgressionCommandRecovery(storageKey, value),
    removeItem: (storageKey, expectedValue) => {
      if (expectedValue == null) return Promise.resolve(false);
      return desktop!.removeProgressionCommandRecovery(storageKey, expectedValue);
    },
  },
  openFile: (opts) => desktop!.openFile(opts?.filters),
  saveFile: (opts) => desktop!.saveFile(opts),
  openExternal: (target) => desktop!.openExternal(target),
  loadLayout: (projectId) => desktop!.loadLayout(projectId),
  loadLayoutBackup: (projectId) => desktop!.loadLayoutBackup(projectId),
  saveLayout: (projectId, layout, options) => desktop!.saveLayout(projectId, layout, options),
};
