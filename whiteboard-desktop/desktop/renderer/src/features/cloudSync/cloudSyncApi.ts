import {
  validateProjectBundleSnapshot,
  type ProjectBundleSnapshot,
} from '../../api/runtimeDtoValidation';
import type {
  CloudSyncRendererApi,
  RendererCloudActionReceipt,
  RendererCloudActionReceiptRequest,
} from '../../../../electron/cloud-sync-contract';
import type {
  CloudDocumentBinding,
  CloudProjectInventory,
  CloudSnapshotMetadata,
} from './cloudSyncModel';

export interface NativeCloudSyncState {
  enabled: boolean;
  automatic: boolean;
  folderPath: string | null;
  deviceId: string;
  lastSuccessfulSyncAt: string | null;
  lastError: string | null;
  outboxCount: number;
  folderAvailable?: boolean;
  warnings?: string[];
  retiredLocalDocuments?: Array<{
    localDocumentId: string;
    localIncarnation: string;
    expectedDigest: string | null;
  }>;
  actionReceipts: RendererCloudActionReceipt[];
  recoveredRemoteHeads: Array<{
    cloudProjectId: string;
    snapshotIds: string[];
  }>;
  bindings: CloudDocumentBinding[];
  ignoredCloudProjectIds: string[];
  projects: CloudProjectInventory[];
}

export interface CloudSnapshotEnvelope {
  format: 'logosforge-whiteboard-cloud-snapshot';
  version: '1.0';
  cloudProjectId: string;
  snapshot: CloudSnapshotMetadata;
  bundle: ProjectBundleSnapshot;
}

export interface CloudPublishRequest {
  localDocumentId: string;
  localIncarnation: string;
  bundle: ProjectBundleSnapshot;
  cloudProjectId?: string | null;
  parentSnapshotIds?: string[];
  createNewProject?: boolean;
  newCloudProjectId?: string | null;
}

export interface CloudPublishResult {
  binding: CloudDocumentBinding;
  snapshot: CloudSnapshotMetadata;
  queued: boolean;
}

export interface CloudBindingRequest {
  localDocumentId: string;
  localIncarnation: string;
  cloudProjectId: string;
  snapshotId: string;
  digest: string;
}

type CloudSyncBridge = Pick<CloudSyncRendererApi,
  | 'cloudSyncGetState'
  | 'cloudSyncChooseFolder'
  | 'cloudSyncDisable'
  | 'cloudSyncSetAutomatic'
  | 'cloudSyncDigest'
  | 'cloudSyncPublish'
  | 'cloudSyncReadSnapshot'
  | 'cloudSyncSetBinding'
  | 'cloudSyncMoveBinding'
  | 'cloudSyncForgetBinding'
  | 'cloudSyncSetRemoteIgnored'
  | 'cloudSyncSaveActionReceipt'
  | 'cloudSyncCompleteActionReceipt'
  | 'cloudSyncRecordRecoveredRemoteHeads'
  | 'cloudSyncClearRecoveredRemoteHeads'
  | 'cloudSyncRetryOutbox'
  | 'onCloudSyncChanged'
>;

function bridge(): CloudSyncBridge | null {
  const candidate = (window as unknown as { logosforge?: Partial<CloudSyncBridge> }).logosforge;
  if (
    !candidate
    || typeof candidate.cloudSyncGetState !== 'function'
    || typeof candidate.cloudSyncChooseFolder !== 'function'
    || typeof candidate.cloudSyncPublish !== 'function'
  ) return null;
  return candidate as CloudSyncBridge;
}

export function cloudSyncAvailable(): boolean {
  return bridge() !== null;
}

function requiredBridge(): CloudSyncBridge {
  const available = bridge();
  if (!available) {
    throw new Error('Cloud folder sync is available in the installed desktop app.');
  }
  return available;
}

export const cloudSyncGetState = (): Promise<NativeCloudSyncState> => (
  requiredBridge().cloudSyncGetState()
);
export const cloudSyncChooseFolder = (): Promise<NativeCloudSyncState> => (
  requiredBridge().cloudSyncChooseFolder()
);
export const cloudSyncDisable = (): Promise<NativeCloudSyncState> => (
  requiredBridge().cloudSyncDisable()
);
export const cloudSyncSetAutomatic = (automatic: boolean): Promise<NativeCloudSyncState> => (
  requiredBridge().cloudSyncSetAutomatic(automatic)
);
export const cloudSyncDigest = (bundle: ProjectBundleSnapshot): Promise<string> => (
  requiredBridge().cloudSyncDigest(bundle)
);
export const cloudSyncPublish = (request: CloudPublishRequest): Promise<CloudPublishResult> => (
  requiredBridge().cloudSyncPublish(request)
);
export const cloudSyncReadSnapshot = (
  cloudProjectId: string,
  snapshotId: string,
): Promise<CloudSnapshotEnvelope> => requiredBridge()
  .cloudSyncReadSnapshot(cloudProjectId, snapshotId)
  .then((envelope) => ({
    ...envelope,
    bundle: validateProjectBundleSnapshot(envelope.bundle),
  }));
export const cloudSyncSetBinding = (request: CloudBindingRequest): Promise<NativeCloudSyncState> => (
  requiredBridge().cloudSyncSetBinding(request)
);
export const cloudSyncMoveBinding = (
  oldLocalDocumentId: string,
  oldLocalIncarnation: string,
  next: CloudBindingRequest,
  expectedRetiredDigest?: string | null,
): Promise<NativeCloudSyncState> => (
  requiredBridge().cloudSyncMoveBinding(
    oldLocalDocumentId,
    oldLocalIncarnation,
    next,
    expectedRetiredDigest,
  )
);
export const cloudSyncForgetBinding = (
  localDocumentId: string,
  localIncarnation: string,
  ignoreRemote = true,
): Promise<NativeCloudSyncState> => (
  requiredBridge().cloudSyncForgetBinding(localDocumentId, localIncarnation, ignoreRemote)
);
export const cloudSyncRetryOutbox = (): Promise<NativeCloudSyncState> => (
  requiredBridge().cloudSyncRetryOutbox()
);
export const cloudSyncSetRemoteIgnored = (
  cloudProjectId: string,
  ignored: boolean,
): Promise<void> => requiredBridge().cloudSyncSetRemoteIgnored(cloudProjectId, ignored);
export const cloudSyncSaveActionReceipt = (
  request: RendererCloudActionReceiptRequest,
): Promise<NativeCloudSyncState> => requiredBridge().cloudSyncSaveActionReceipt(request);
export const cloudSyncCompleteActionReceipt = (
  actionId: string,
): Promise<NativeCloudSyncState> => requiredBridge().cloudSyncCompleteActionReceipt(actionId);
export const cloudSyncRecordRecoveredRemoteHeads = (
  cloudProjectId: string,
  snapshotIds: string[],
): Promise<NativeCloudSyncState> => (
  requiredBridge().cloudSyncRecordRecoveredRemoteHeads(cloudProjectId, snapshotIds)
);
export const cloudSyncClearRecoveredRemoteHeads = (
  cloudProjectId: string,
): Promise<NativeCloudSyncState> => (
  requiredBridge().cloudSyncClearRecoveredRemoteHeads(cloudProjectId)
);
export type CloudSyncActionReceipt = RendererCloudActionReceipt;
export type CloudSyncActionReceiptRequest = RendererCloudActionReceiptRequest;
export const onCloudSyncChanged = (callback: () => void): (() => void) => (
  bridge()?.onCloudSyncChanged?.(callback) ?? (() => {})
);
