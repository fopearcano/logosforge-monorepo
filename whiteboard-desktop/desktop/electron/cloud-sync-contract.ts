/**
 * Pure context-bridge contract shared by Electron preload and the sandboxed
 * renderer. Keep this file free of Electron/Node imports so renderer typecheck
 * cannot accidentally pull main-process implementation libraries into its
 * compilation target.
 */

export interface RendererCloudSnapshotMetadata {
  snapshotId: string;
  parentSnapshotIds: string[];
  generation: number;
  digest: string;
  createdAt: string;
  deviceId: string;
  title: string;
}

export interface RendererCloudBinding {
  localDocumentId: string;
  localIncarnation: string;
  cloudProjectId: string;
  lastSnapshotId: string;
  lastDigest: string;
}

export type RendererCloudActionKind =
  | 'pull'
  | 'keep-both'
  | 'use-cloud'
  | 'discover'
  | 'remote-recovery';
export type RendererCloudActionPhase = 'prepared' | 'local-forked' | 'restored' | 'binding-installed';

export interface RendererCloudActionReceipt {
  actionId: string;
  kind: RendererCloudActionKind;
  phase: RendererCloudActionPhase;
  sourceLocalDocumentId: string;
  sourceLocalIncarnation: string;
  originalCloudProjectId: string;
  intendedCloudProjectId: string | null;
  snapshotId: string;
  snapshotDigest: string;
  parentSnapshotIds: string[];
  expectedSourceDigest: string;
  restoredLocalDocumentId: string | null;
  restoredLocalIncarnation: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface RendererCloudActionReceiptRequest {
  actionId: string;
  kind: RendererCloudActionKind;
  phase: RendererCloudActionPhase;
  sourceLocalDocumentId: string;
  sourceLocalIncarnation: string;
  originalCloudProjectId: string;
  intendedCloudProjectId?: string | null;
  snapshotId: string;
  snapshotDigest: string;
  parentSnapshotIds: string[];
  expectedSourceDigest: string;
  restoredLocalDocumentId?: string | null;
  restoredLocalIncarnation?: string | null;
}

export interface RendererCloudRecoveredRemoteHeads {
  cloudProjectId: string;
  snapshotIds: string[];
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
  bindings: RendererCloudBinding[];
  retiredLocalDocuments: Array<{
    localDocumentId: string;
    localIncarnation: string;
    /** Null means a legacy tombstone whose bytes were never fingerprinted. */
    expectedDigest: string | null;
  }>;
  actionReceipts: RendererCloudActionReceipt[];
  recoveredRemoteHeads: RendererCloudRecoveredRemoteHeads[];
  ignoredCloudProjectIds: string[];
  projects: Array<{
    cloudProjectId: string;
    snapshots: RendererCloudSnapshotMetadata[];
    headSnapshotIds: string[];
  }>;
}

export interface RendererCloudBindingRequest {
  localDocumentId: string;
  localIncarnation: string;
  cloudProjectId: string;
  snapshotId: string;
  digest: string;
}

export interface RendererCloudPublishRequest {
  localDocumentId: string;
  localIncarnation: string;
  bundle: unknown;
  cloudProjectId?: string | null;
  parentSnapshotIds?: string[];
  createNewProject?: boolean;
  newCloudProjectId?: string | null;
}

export interface RendererCloudSnapshotEnvelope {
  format: 'logosforge-whiteboard-cloud-snapshot';
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
    oldLocalDocumentId: string,
    oldLocalIncarnation: string,
    next: RendererCloudBindingRequest,
    expectedRetiredDigest?: string | null,
  ): Promise<RendererCloudState>;
  cloudSyncForgetBinding(
    localDocumentId: string,
    localIncarnation: string,
    ignoreRemote?: boolean,
  ): Promise<RendererCloudState>;
  cloudSyncSetRemoteIgnored(cloudProjectId: string, ignored: boolean): Promise<void>;
  cloudSyncSaveActionReceipt(
    request: RendererCloudActionReceiptRequest,
  ): Promise<RendererCloudState>;
  cloudSyncCompleteActionReceipt(actionId: string): Promise<RendererCloudState>;
  cloudSyncRecordRecoveredRemoteHeads(
    cloudProjectId: string,
    snapshotIds: string[],
  ): Promise<RendererCloudState>;
  cloudSyncClearRecoveredRemoteHeads(cloudProjectId: string): Promise<RendererCloudState>;
  cloudSyncRetryOutbox(): Promise<RendererCloudState>;
  onCloudSyncChanged(callback: () => void): () => void;
}
