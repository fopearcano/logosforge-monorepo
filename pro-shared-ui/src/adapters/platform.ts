/**
 * Platform adapter — the boundary the apps inject so this package stays
 * platform-neutral. pro-desktop (Electron) and pro-web (browser) each provide
 * their own implementation; shared-ui components only call this interface, never
 * `electron`, Node, or browser-host APIs directly.
 */

export interface OpenFileResult {
  canceled: boolean;
  path?: string;
  /** text content if the host read it for us; else undefined. */
  content?: string;
  /** raw file bytes, base64-encoded — for binary imports (e.g. .docx) that a
   *  UTF-8 read would corrupt. Set by desktop alongside `content`. */
  contentBase64?: string;
}

export interface SaveFileResult {
  canceled: boolean;
  path?: string;
}

/**
 * Opaque, host-owned persistence used for command recovery records which must
 * outlive a browser origin. Browser hosts can omit this and use localStorage;
 * Electron supplies an app-owned userData implementation through its preload.
 */
export interface DurableRecoveryStorage {
  getItem(key: string): Promise<string | null> | string | null;
  setItem(key: string, value: string): Promise<void> | void;
  /**
   * Hosts with asynchronous storage should compare `expectedValue` before
   * removing so an old panel cannot erase a newer command for the same slot.
   */
  removeItem(key: string, expectedValue?: string): Promise<boolean | void> | boolean | void;
}

/** Immutable snapshot metadata discovered in a provider-managed cloud folder. */
export interface CloudSyncSnapshotMetadata {
  snapshotId: string;
  parentSnapshotIds: string[];
  generation: number;
  digest: string;
  createdAt: string;
  deviceId: string;
  title: string;
  queued: boolean;
}

export interface CloudSyncBinding {
  /** Device-local numeric Core id, serialized because host bindings are opaque. */
  localProjectId: string;
  /** Portable project identity carried by the canonical Core snapshot. */
  localIncarnation: string;
  cloudProjectId: string;
  lastSnapshotId: string;
  lastDigest: string;
}

export interface CloudSyncProjectInventory {
  cloudProjectId: string;
  title: string;
  snapshots: CloudSyncSnapshotMetadata[];
  headSnapshotIds: string[];
}

export type CloudSyncActionKind =
  | "pull"
  | "replace-cloud"
  | "keep-both"
  | "use-cloud"
  | "discover"
  | "remote-recovery";
export type CloudSyncActionPhase =
  | "prepared"
  | "local-forked"
  | "restored"
  | "binding-installed";

export interface CloudSyncActionReceipt {
  actionId: string;
  kind: CloudSyncActionKind;
  phase: CloudSyncActionPhase;
  sourceLocalProjectId: string;
  sourceLocalIncarnation: string;
  originalCloudProjectId: string;
  intendedCloudProjectId: string | null;
  snapshotId: string;
  snapshotDigest: string;
  parentSnapshotIds: string[];
  expectedSourceDigest: string;
  restoredLocalProjectId: string | null;
  restoredLocalIncarnation: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface CloudSyncState {
  enabled: boolean;
  automatic: boolean;
  folderPath: string | null;
  folderAvailable: boolean;
  warnings: string[];
  deviceId: string;
  lastSuccessfulSyncAt: string | null;
  lastError: string | null;
  outboxCount: number;
  syncing: boolean;
  bindings: CloudSyncBinding[];
  retiredLocalProjects: Array<{
    localProjectId: string;
    localIncarnation: string;
    expectedDigest: string | null;
  }>;
  actionReceipts: CloudSyncActionReceipt[];
  recoveredRemoteHeads: Array<{ cloudProjectId: string; snapshotIds: string[] }>;
  ignoredCloudProjectIds: string[];
  projects: CloudSyncProjectInventory[];
}

export interface CloudSyncBindingRequest {
  localProjectId: string;
  localIncarnation: string;
  cloudProjectId: string;
  snapshotId: string;
  digest: string;
}

export interface CloudSyncPublishRequest {
  localProjectId: string;
  localIncarnation: string;
  bundle: unknown;
  cloudProjectId?: string | null;
  parentSnapshotIds?: string[];
  createNewProject?: boolean;
  newCloudProjectId?: string | null;
}

export interface CloudSyncPublishResult {
  binding: CloudSyncBinding;
  snapshot: CloudSyncSnapshotMetadata;
  queued: boolean;
}

export interface CloudSyncSnapshotEnvelope {
  format: "logosforge-pro-cloud-snapshot";
  version: "1.0";
  cloudProjectId: string;
  snapshot: CloudSyncSnapshotMetadata;
  bundle: unknown;
}

export interface CloudSyncActionReceiptRequest {
  actionId: string;
  kind: CloudSyncActionKind;
  phase: CloudSyncActionPhase;
  sourceLocalProjectId: string;
  sourceLocalIncarnation: string;
  originalCloudProjectId: string;
  intendedCloudProjectId?: string | null;
  snapshotId: string;
  snapshotDigest: string;
  parentSnapshotIds: string[];
  expectedSourceDigest: string;
  restoredLocalProjectId?: string | null;
  restoredLocalIncarnation?: string | null;
}

/**
 * Desktop-owned provider-folder transport. It never receives provider tokens:
 * Google Drive, Dropbox, OneDrive, iCloud and Syncthing perform their ordinary
 * filesystem synchronization outside LogosForge.
 */
export interface CloudSyncHost {
  getState(): Promise<CloudSyncState>;
  chooseFolder(): Promise<CloudSyncState>;
  disable(): Promise<CloudSyncState>;
  setAutomatic(automatic: boolean): Promise<CloudSyncState>;
  digest(bundle: unknown): Promise<string>;
  publish(request: CloudSyncPublishRequest): Promise<CloudSyncPublishResult>;
  readSnapshot(cloudProjectId: string, snapshotId: string): Promise<CloudSyncSnapshotEnvelope>;
  setBinding(request: CloudSyncBindingRequest): Promise<CloudSyncState>;
  moveBinding(
    oldLocalProjectId: string,
    oldLocalIncarnation: string,
    next: CloudSyncBindingRequest,
    expectedRetiredDigest?: string | null,
  ): Promise<CloudSyncState>;
  forgetBinding(
    localProjectId: string,
    localIncarnation: string,
    ignoreRemote?: boolean,
  ): Promise<CloudSyncState>;
  setRemoteIgnored(cloudProjectId: string, ignored: boolean): Promise<CloudSyncState>;
  saveActionReceipt(request: CloudSyncActionReceiptRequest): Promise<CloudSyncState>;
  completeActionReceipt(actionId: string): Promise<CloudSyncState>;
  recordRecoveredRemoteHeads(cloudProjectId: string, snapshotIds: string[]): Promise<CloudSyncState>;
  clearRecoveredRemoteHeads(cloudProjectId: string): Promise<CloudSyncState>;
  removeRecoveredRemoteHead(cloudProjectId: string, snapshotId: string): Promise<CloudSyncState>;
  retryOutbox(): Promise<CloudSyncState>;
  onChanged(callback: () => void): () => void;
}

export interface PlatformAdapter {
  /**
   * Stable, non-secret identity for the backing Core/account used to scope
   * durable UI recovery records. Hosts serving multiple accounts or Cores from
   * one origin must provide distinct values.
   */
  readonly persistenceScope?: string;
  /** Stable command-recovery storage; desktop must not use origin localStorage. */
  readonly progressionCommandStorage?: DurableRecoveryStorage;
  /** Local file open (desktop) / file picker or import (web). */
  openFile(opts?: { filters?: { name: string; extensions: string[] }[] }): Promise<OpenFileResult>;
  /**
   * Local file save (desktop) / download (web). Pass `content` for text exports,
   * or `contentBase64` for binary ones (PDF/DOCX) — the host decodes the base64 and
   * writes raw bytes (a UTF-8 string write would corrupt binary). At least one of
   * `content` / `contentBase64` should be set.
   */
  saveFile(opts: { suggestedName?: string; content?: string; contentBase64?: string; mimeType?: string }): Promise<SaveFileResult>;
  /** Reveal/open a path or URL in the host (best-effort). */
  openExternal(target: string): Promise<void>;
  /** App-level navigation (router on web; window/section on desktop). */
  navigate?(to: string): void;
  /** Persist + restore opaque per-project UI layout (docking). */
  loadLayout?(projectId: number): Promise<unknown | null>;
  /** Optional prior generation, validated by shared UI before recovery. */
  loadLayoutBackup?(projectId: number): Promise<unknown | null>;
  saveLayout?(projectId: number, layout: unknown, options?: { preserveBackup?: boolean }): Promise<void>;
  /** Desktop-only complete-project cloud-folder transport. Browser hosts omit it. */
  readonly cloudSync?: CloudSyncHost;
  /** True on Electron desktop (enables local-only features like Dexter's Room). */
  readonly isDesktop: boolean;
}
