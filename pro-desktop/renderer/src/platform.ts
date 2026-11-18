import type { PlatformAdapter } from '@logosforge/pro-shared-ui';
import type {
  CloudSyncRendererApi,
  RendererCloudActionReceiptRequest,
  RendererCloudBindingRequest,
  RendererCloudPublishRequest,
  RendererCloudPublishResult,
  RendererCloudSnapshotEnvelope,
  RendererCloudState,
} from '../../electron/cloud-sync-contract';
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
  cloudSyncGetState(): Promise<RendererCloudState>;
  cloudSyncChooseFolder(): Promise<RendererCloudState>;
  cloudSyncDisable(): Promise<RendererCloudState>;
  cloudSyncSetAutomatic(automatic: boolean): Promise<RendererCloudState>;
  cloudSyncDigest(bundle: unknown): Promise<string>;
  cloudSyncPublish(request: RendererCloudPublishRequest): Promise<RendererCloudPublishResult>;
  cloudSyncReadSnapshot(
    cloudProjectId: string,
    snapshotId: string,
  ): Promise<RendererCloudSnapshotEnvelope>;
  cloudSyncSetBinding(request: RendererCloudBindingRequest): Promise<RendererCloudState>;
  cloudSyncMoveBinding(
    oldLocalProjectId: string,
    oldLocalIncarnation: string,
    next: RendererCloudBindingRequest,
    expectedRetiredDigest?: string | null,
  ): Promise<RendererCloudState>;
  cloudSyncForgetBinding(
    localProjectId: string,
    localIncarnation: string,
    ignoreRemote?: boolean,
  ): Promise<RendererCloudState>;
  cloudSyncSetRemoteIgnored(cloudProjectId: string, ignored: boolean): Promise<RendererCloudState>;
  cloudSyncSaveActionReceipt(request: RendererCloudActionReceiptRequest): Promise<RendererCloudState>;
  cloudSyncCompleteActionReceipt(actionId: string): Promise<RendererCloudState>;
  cloudSyncRecordRecoveredRemoteHeads(
    cloudProjectId: string,
    snapshotIds: string[],
  ): Promise<RendererCloudState>;
  cloudSyncClearRecoveredRemoteHeads(cloudProjectId: string): Promise<RendererCloudState>;
  cloudSyncRemoveRecoveredRemoteHead(
    cloudProjectId: string,
    snapshotId: string,
  ): Promise<RendererCloudState>;
  cloudSyncRetryOutbox(): Promise<RendererCloudState>;
  onCloudSyncChanged(cb: () => void): () => void;
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

const cloudSync: CloudSyncRendererApi | undefined = desktop ? {
  getState: () => desktop.cloudSyncGetState(),
  chooseFolder: () => desktop.cloudSyncChooseFolder(),
  disable: () => desktop.cloudSyncDisable(),
  setAutomatic: (automatic) => desktop.cloudSyncSetAutomatic(automatic),
  digest: (bundle) => desktop.cloudSyncDigest(bundle),
  publish: (request) => desktop.cloudSyncPublish(request),
  readSnapshot: (cloudProjectId, snapshotId) => (
    desktop.cloudSyncReadSnapshot(cloudProjectId, snapshotId)
  ),
  setBinding: (request) => desktop.cloudSyncSetBinding(request),
  moveBinding: (oldLocalProjectId, oldLocalIncarnation, next, expectedRetiredDigest) => (
    desktop.cloudSyncMoveBinding(
      oldLocalProjectId,
      oldLocalIncarnation,
      next,
      expectedRetiredDigest,
    )
  ),
  forgetBinding: (localProjectId, localIncarnation, ignoreRemote) => (
    desktop.cloudSyncForgetBinding(localProjectId, localIncarnation, ignoreRemote)
  ),
  setRemoteIgnored: (cloudProjectId, ignored) => (
    desktop.cloudSyncSetRemoteIgnored(cloudProjectId, ignored)
  ),
  saveActionReceipt: (request) => desktop.cloudSyncSaveActionReceipt(request),
  completeActionReceipt: (actionId) => desktop.cloudSyncCompleteActionReceipt(actionId),
  recordRecoveredRemoteHeads: (cloudProjectId, snapshotIds) => (
    desktop.cloudSyncRecordRecoveredRemoteHeads(cloudProjectId, snapshotIds)
  ),
  clearRecoveredRemoteHeads: (cloudProjectId) => (
    desktop.cloudSyncClearRecoveredRemoteHeads(cloudProjectId)
  ),
  removeRecoveredRemoteHead: (cloudProjectId, snapshotId) => (
    desktop.cloudSyncRemoveRecoveredRemoteHead(cloudProjectId, snapshotId)
  ),
  retryOutbox: () => desktop.cloudSyncRetryOutbox(),
  onChanged: (callback) => desktop.onCloudSyncChanged(callback),
} : undefined;

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
  cloudSync,
};
