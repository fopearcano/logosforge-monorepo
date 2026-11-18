/**
 * Context-bridge-safe Cloud Folder Sync contract. This module deliberately has
 * no Electron or Node imports so the sandboxed renderer may typecheck it.
 */

export interface RendererCloudSnapshotMetadata {
  snapshotId: string;
  parentSnapshotIds: string[];
  generation: number;
  digest: string;
  createdAt: string;
  deviceId: string;
  title: string;
  queued: boolean;
}

export interface RendererCloudBinding {
  localProjectId: string;
  localIncarnation: string;
  cloudProjectId: string;
  lastSnapshotId: string;
  lastDigest: string;
}

export type RendererCloudActionKind =
  | 'pull'
  | 'replace-cloud'
  | 'keep-both'
  | 'use-cloud'
  | 'discover'
  | 'remote-recovery';

export type RendererCloudActionPhase =
  | 'prepared'
  | 'local-forked'
  | 'restored'
  | 'binding-installed';

export interface RendererCloudActionReceipt {
  actionId: string;
  kind: RendererCloudActionKind;
  phase: RendererCloudActionPhase;
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

export interface RendererCloudActionReceiptRequest {
  actionId: string;
  kind: RendererCloudActionKind;
  phase: RendererCloudActionPhase;
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

export interface RendererCloudRecoveredRemoteHeads {
  cloudProjectId: string;
  snapshotIds: string[];
}

export interface RendererCloudProjectInventory {
  cloudProjectId: string;
  title: string;
  snapshots: RendererCloudSnapshotMetadata[];
  headSnapshotIds: string[];
}

export interface RendererCloudState {
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
  bindings: RendererCloudBinding[];
  retiredLocalProjects: Array<{
    localProjectId: string;
    localIncarnation: string;
    /** Null is a migrated tombstone without a safe retirement fingerprint. */
    expectedDigest: string | null;
  }>;
  actionReceipts: RendererCloudActionReceipt[];
  recoveredRemoteHeads: RendererCloudRecoveredRemoteHeads[];
  ignoredCloudProjectIds: string[];
  projects: RendererCloudProjectInventory[];
}

export interface RendererCloudBindingRequest {
  localProjectId: string;
  localIncarnation: string;
  cloudProjectId: string;
  snapshotId: string;
  digest: string;
}

export interface RendererCloudPublishRequest {
  localProjectId: string;
  localIncarnation: string;
  bundle: unknown;
  cloudProjectId?: string | null;
  parentSnapshotIds?: string[];
  createNewProject?: boolean;
  /** Persist this UUID in an action receipt before requesting a fork. */
  newCloudProjectId?: string | null;
}

export interface RendererCloudSnapshotEnvelope {
  format: 'logosforge-pro-cloud-snapshot';
  version: '1.0';
  cloudProjectId: string;
  snapshot: RendererCloudSnapshotMetadata;
  bundle: unknown;
}

export interface RendererCloudPublishResult {
  binding: RendererCloudBinding;
  snapshot: RendererCloudSnapshotMetadata;
  queued: boolean;
}

export interface CloudSyncRendererApi {
  getState(): Promise<RendererCloudState>;
  chooseFolder(): Promise<RendererCloudState>;
  disable(): Promise<RendererCloudState>;
  setAutomatic(automatic: boolean): Promise<RendererCloudState>;
  digest(bundle: unknown): Promise<string>;
  publish(request: RendererCloudPublishRequest): Promise<RendererCloudPublishResult>;
  readSnapshot(cloudProjectId: string, snapshotId: string): Promise<RendererCloudSnapshotEnvelope>;
  setBinding(request: RendererCloudBindingRequest): Promise<RendererCloudState>;
  moveBinding(
    oldLocalProjectId: string,
    oldLocalIncarnation: string,
    next: RendererCloudBindingRequest,
    expectedRetiredDigest?: string | null,
  ): Promise<RendererCloudState>;
  forgetBinding(
    localProjectId: string,
    localIncarnation: string,
    ignoreRemote?: boolean,
  ): Promise<RendererCloudState>;
  setRemoteIgnored(cloudProjectId: string, ignored: boolean): Promise<RendererCloudState>;
  saveActionReceipt(request: RendererCloudActionReceiptRequest): Promise<RendererCloudState>;
  completeActionReceipt(actionId: string): Promise<RendererCloudState>;
  recordRecoveredRemoteHeads(
    cloudProjectId: string,
    snapshotIds: string[],
  ): Promise<RendererCloudState>;
  clearRecoveredRemoteHeads(cloudProjectId: string): Promise<RendererCloudState>;
  removeRecoveredRemoteHead(
    cloudProjectId: string,
    snapshotId: string,
  ): Promise<RendererCloudState>;
  retryOutbox(): Promise<RendererCloudState>;
  onChanged(callback: () => void): () => void;
}
