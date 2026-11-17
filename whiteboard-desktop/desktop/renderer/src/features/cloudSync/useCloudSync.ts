import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { flushPendingDocSaves } from '../../state/currentDocument';
import type { ProjectBundleSnapshot } from '../../api/runtimeDtoValidation';
import { documentExists, listDocuments, type DocumentSummary } from '../whiteboard/documentsApi';
import { acquireTrackedDocumentOperation, lockDocumentInteraction } from '../whiteboard/documentOperationGuard';
import { getWhiteboardForDocument } from '../whiteboard/whiteboardApi';
import type { SaveStatus, WhiteboardDocument } from '../whiteboard/types';
import {
  cloudSyncAvailable,
  cloudSyncChooseFolder,
  cloudSyncCompleteActionReceipt,
  cloudSyncDigest,
  cloudSyncDisable,
  cloudSyncForgetBinding,
  cloudSyncGetState,
  cloudSyncMoveBinding,
  cloudSyncPublish,
  cloudSyncReadSnapshot,
  cloudSyncRecordRecoveredRemoteHeads,
  cloudSyncRetryOutbox,
  cloudSyncSaveActionReceipt,
  cloudSyncSetAutomatic,
  cloudSyncSetBinding,
  cloudSyncSetRemoteIgnored,
  onCloudSyncChanged,
  type CloudSyncActionReceipt,
  type CloudSyncActionReceiptRequest,
  type NativeCloudSyncState,
} from './cloudSyncApi';
import {
  isCloudRetireContentChanged,
  isCloudRestoreRetryStale,
  readCompleteProjectBundle,
  restoreCompleteProjectBundle,
  retireCloudProjectIfUnchanged,
} from './cloudSyncBackend';
import {
  cloudProjectHeads,
  decideCloudSync,
  deterministicCloudRecoveryUuid,
  newestCloudHead,
  planCloudPreservation,
  planRemoteRecovery,
  staleRestoreSuccessorActionId,
  type CloudDocumentBinding,
  type CloudProjectInventory,
  type CloudSnapshotMetadata,
} from './cloudSyncModel';
import { setCloudSyncUiState } from './cloudSyncStore';
import type { CloudSyncConflictSummary, CloudSyncControls, CloudSyncUiState } from './cloudSyncUi';

const AUTOMATIC_SYNC_INTERVAL_MS = 30_000;
const EDIT_QUIET_PERIOD_MS = 12_000;

interface BoundPendingReview {
  kind: 'bound';
  document: DocumentSummary;
  binding: CloudDocumentBinding;
  inventory: CloudProjectInventory;
  heads: CloudSnapshotMetadata[];
  localBundle: ProjectBundleSnapshot;
  localDigest: string;
  reason: string;
}

interface RemotePendingReview {
  kind: 'remote';
  inventory: CloudProjectInventory;
  heads: CloudSnapshotMetadata[];
  reason: string;
}

type PendingReview = BoundPendingReview | RemotePendingReview;

interface Options {
  baseUrl: string;
  ready: boolean;
  documentsLoaded: boolean;
  document: WhiteboardDocument | null;
  documents: DocumentSummary[];
  saveStatus: SaveStatus;
  restoreActiveDocument: (restore: () => Promise<WhiteboardDocument>) => Promise<WhiteboardDocument | null>;
  deleteLocalDocument: (id: string) => Promise<boolean>;
  refreshDocuments: () => Promise<void>;
}

interface Result {
  controls: CloudSyncControls;
  conflictOpen: boolean;
  conflictError: string | null;
  openConflict: () => void;
  closeConflict: () => void;
  keepBoth: () => Promise<void>;
  useCloudCopy: () => Promise<void>;
  replaceCloud: () => Promise<void>;
  recoverRemote: () => Promise<void>;
  forgetDeletedDocument: (document: DocumentSummary) => Promise<void>;
}

interface RestoredIdentity {
  id: string;
  incarnation: string;
  document: WhiteboardDocument | null;
}

const DISABLED: CloudSyncUiState = {
  enabled: false,
  automatic: false,
  folderPath: null,
  status: 'disabled',
  detail: 'Choose a provider-managed folder to sync complete projects across devices.',
  lastSuccessfulSyncAt: null,
  conflict: null,
  busy: false,
};

function actionId(prefix: string): string {
  return `${prefix}:${crypto.randomUUID()}`;
}

function cloudUuid(): string {
  return crypto.randomUUID();
}

function sortedHeads(inventory: CloudProjectInventory): CloudSnapshotMetadata[] {
  return cloudProjectHeads(inventory).sort((left, right) => left.snapshotId.localeCompare(right.snapshotId));
}

function reviewSummary(review: PendingReview, localDeviceId: string): CloudSyncConflictSummary {
  if (review.kind === 'remote') {
    const remote = newestCloudHead(review.heads);
    return {
      kind: 'remote-recovery',
      projectTitle: review.inventory.snapshots[0]?.title || 'Untitled',
      localDeviceLabel: 'No linked copy on this device',
      remoteDeviceLabel: `${review.heads.length} preserved cloud branches`,
      localChangedAt: null,
      remoteChangedAt: remote?.createdAt ?? null,
      branchCount: review.heads.length,
    };
  }
  const remote = newestCloudHead(review.heads);
  return {
    kind: 'bound-conflict',
    projectTitle: review.localBundle.project.title || review.document.title || 'Untitled',
    localDeviceLabel: `This device (${localDeviceId.slice(0, 8)})`,
    remoteDeviceLabel: remote ? `Device ${remote.deviceId.slice(0, 8)}` : 'Cloud history',
    localChangedAt: review.document.updated_at,
    remoteChangedAt: remote?.createdAt ?? null,
    branchCount: Math.max(2, review.heads.length + 1),
  };
}

function bindingForIdentity(
  state: NativeCloudSyncState,
  localDocumentId: string,
  localIncarnation: string,
): CloudDocumentBinding | null {
  return state.bindings.find((binding) => (
    binding.localDocumentId === localDocumentId && binding.localIncarnation === localIncarnation
  )) ?? null;
}

function bindingForDocument(
  state: NativeCloudSyncState,
  document: Pick<DocumentSummary, 'id' | 'incarnation'>,
): CloudDocumentBinding | null {
  return bindingForIdentity(state, document.id, document.incarnation);
}

function inventoryForBinding(
  state: NativeCloudSyncState,
  binding: CloudDocumentBinding | null,
): CloudProjectInventory | null {
  if (!binding) return null;
  return state.projects.find((project) => project.cloudProjectId === binding.cloudProjectId) ?? null;
}

function snapshotForReceipt(
  state: NativeCloudSyncState,
  receipt: CloudSyncActionReceipt,
): CloudSnapshotMetadata | null {
  return state.projects
    .find((candidate) => candidate.cloudProjectId === receipt.originalCloudProjectId)
    ?.snapshots.find((snapshot) => snapshot.snapshotId === receipt.snapshotId) ?? null;
}

function bindingSnapshotMatches(
  state: NativeCloudSyncState,
  binding: CloudDocumentBinding,
  receipt: CloudSyncActionReceipt,
): boolean {
  if (binding.cloudProjectId !== receipt.originalCloudProjectId || binding.lastDigest !== receipt.snapshotDigest) {
    return false;
  }
  const snapshot = inventoryForBinding(state, binding)?.snapshots.find((candidate) => (
    candidate.snapshotId === binding.lastSnapshotId
  ));
  if (!snapshot) return false;
  if (receipt.kind === 'discover' || receipt.kind === 'pull') return snapshot.snapshotId === receipt.snapshotId;
  const expectedParents = [...receipt.parentSnapshotIds].sort();
  const actualParents = [...snapshot.parentSnapshotIds].sort();
  return expectedParents.length === actualParents.length
    && expectedParents.every((id, index) => id === actualParents[index]);
}

function stateAfterNative(
  native: NativeCloudSyncState,
  review: PendingReview | null,
  busy = false,
): CloudSyncUiState {
  if (!native.enabled) return { ...DISABLED, automatic: native.automatic };
  if (review) {
    return {
      enabled: true,
      automatic: native.automatic,
      folderPath: native.folderPath,
      status: busy ? 'syncing' : 'attention',
      detail: review.reason,
      lastSuccessfulSyncAt: native.lastSuccessfulSyncAt,
      conflict: reviewSummary(review, native.deviceId),
      busy,
    };
  }
  if (native.lastError) {
    return {
      enabled: true,
      automatic: native.automatic,
      folderPath: native.folderPath,
      status: 'folder-unavailable',
      detail: native.lastError,
      lastSuccessfulSyncAt: native.lastSuccessfulSyncAt,
      conflict: null,
      busy,
    };
  }
  return {
    enabled: true,
    automatic: native.automatic,
    folderPath: native.folderPath,
    status: busy ? 'syncing' : (native.outboxCount > 0 ? 'attention' : 'up-to-date'),
    detail: native.outboxCount > 0
      ? `${native.outboxCount} snapshot${native.outboxCount === 1 ? '' : 's'} waiting for the cloud folder.`
      : 'Complete project snapshots are synchronized.',
    lastSuccessfulSyncAt: native.lastSuccessfulSyncAt,
    conflict: null,
    busy,
  };
}

function receiptRequest(
  receipt: CloudSyncActionReceipt,
  phase: CloudSyncActionReceipt['phase'],
  restored?: Pick<RestoredIdentity, 'id' | 'incarnation'> | null,
): CloudSyncActionReceiptRequest {
  return {
    actionId: receipt.actionId,
    kind: receipt.kind,
    phase,
    sourceLocalDocumentId: receipt.sourceLocalDocumentId,
    sourceLocalIncarnation: receipt.sourceLocalIncarnation,
    originalCloudProjectId: receipt.originalCloudProjectId,
    intendedCloudProjectId: receipt.intendedCloudProjectId,
    snapshotId: receipt.snapshotId,
    snapshotDigest: receipt.snapshotDigest,
    parentSnapshotIds: receipt.parentSnapshotIds,
    expectedSourceDigest: receipt.expectedSourceDigest,
    restoredLocalDocumentId: restored?.id ?? receipt.restoredLocalDocumentId,
    restoredLocalIncarnation: restored?.incarnation ?? receipt.restoredLocalIncarnation,
  };
}

export function useCloudSync({
  baseUrl,
  ready,
  documentsLoaded,
  document,
  documents: _documents,
  saveStatus,
  restoreActiveDocument,
  deleteLocalDocument: _deleteLocalDocument,
  refreshDocuments,
}: Options): Result {
  const available = cloudSyncAvailable();
  const [nativeState, setNativeState] = useState<NativeCloudSyncState | null>(null);
  const nativeStateRef = useRef(nativeState);
  nativeStateRef.current = nativeState;
  const activeDocumentRef = useRef(document);
  activeDocumentRef.current = document;
  const [pendingReview, setPendingReview] = useState<PendingReview | null>(null);
  const pendingReviewRef = useRef(pendingReview);
  pendingReviewRef.current = pendingReview;
  const [uiState, setUiState] = useState<CloudSyncUiState>(() => (
    available ? { ...DISABLED, status: 'checking', detail: 'Checking the cloud folder…' } : DISABLED
  ));
  const [conflictOpen, setConflictOpen] = useState(false);
  const [conflictError, setConflictError] = useState<string | null>(null);
  const syncingRef = useRef(false);
  const rerunRef = useRef(false);
  const syncCompletionRef = useRef<Promise<void> | null>(null);
  const resolveSyncCompletionRef = useRef<(() => void) | null>(null);
  const startupSyncKeyRef = useRef('');
  const mountedRef = useRef(true);

  const commitUi = useCallback((next: CloudSyncUiState) => {
    if (!mountedRef.current) return;
    setUiState(next);
    setCloudSyncUiState(next);
  }, []);

  const loadNativeState = useCallback(async (): Promise<NativeCloudSyncState | null> => {
    if (!available) {
      commitUi(DISABLED);
      return null;
    }
    try {
      const next = await cloudSyncGetState();
      if (!mountedRef.current) return next;
      nativeStateRef.current = next;
      setNativeState(next);
      commitUi(stateAfterNative(next, pendingReviewRef.current, syncingRef.current));
      return next;
    } catch (error) {
      commitUi({ ...DISABLED, status: 'error', detail: error instanceof Error ? error.message : String(error) });
      return null;
    }
  }, [available, commitUi]);

  const installBinding = useCallback(async (
    localDocument: Pick<WhiteboardDocument, 'id' | 'incarnation'>,
    cloudProjectId: string,
    snapshot: CloudSnapshotMetadata,
  ) => {
    await cloudSyncSetBinding({
      localDocumentId: localDocument.id,
      localIncarnation: localDocument.incarnation,
      cloudProjectId,
      snapshotId: snapshot.snapshotId,
      digest: snapshot.digest,
    });
  }, []);

  const saveReceiptPhase = useCallback(async (
    receipt: CloudSyncActionReceipt,
    phase: CloudSyncActionReceipt['phase'],
    restored?: Pick<RestoredIdentity, 'id' | 'incarnation'> | null,
  ): Promise<CloudSyncActionReceipt> => {
    const state = await cloudSyncSaveActionReceipt(receiptRequest(receipt, phase, restored));
    const saved = state.actionReceipts.find((candidate) => candidate.actionId === receipt.actionId);
    if (!saved) throw new Error('The cloud recovery receipt was not durably saved.');
    return saved;
  }, []);

  const createSuccessorReceipt = useCallback(async (
    receipt: CloudSyncActionReceipt,
  ): Promise<CloudSyncActionReceipt> => {
    // Save the successor first. A crash before retiring the old receipt leaves
    // both receipts, and replay deterministically discovers this same successor
    // before completing the stale one.
    const successorActionId = staleRestoreSuccessorActionId(receipt.actionId);
    const successorState = await cloudSyncSaveActionReceipt({
      actionId: successorActionId,
      kind: receipt.kind,
      phase: 'prepared',
      sourceLocalDocumentId: receipt.sourceLocalDocumentId,
      sourceLocalIncarnation: receipt.sourceLocalIncarnation,
      originalCloudProjectId: receipt.originalCloudProjectId,
      intendedCloudProjectId: receipt.intendedCloudProjectId,
      snapshotId: receipt.snapshotId,
      snapshotDigest: receipt.snapshotDigest,
      parentSnapshotIds: receipt.parentSnapshotIds,
      expectedSourceDigest: receipt.expectedSourceDigest,
    });
    const successor = successorState.actionReceipts.find((candidate) => (
      candidate.actionId === successorActionId
    ));
    if (!successor) throw new Error('The replacement cloud recovery receipt was not saved.');
    await cloudSyncCompleteActionReceipt(receipt.actionId);
    return successor;
  }, []);

  const ensureEditedRestoreDurable = useCallback(async (
    documentId: string,
    incarnation: string,
    bundle: ProjectBundleSnapshot,
    bundleDigest: string,
    cloudProjectId: string,
  ): Promise<void> => {
    let state = await cloudSyncGetState();
    let binding = bindingForIdentity(state, documentId, incarnation);
    let inventory = state.projects.find((project) => project.cloudProjectId === cloudProjectId) ?? null;
    const otherOwner = state.bindings.find((candidate) => (
      candidate.cloudProjectId === cloudProjectId
      && (candidate.localDocumentId !== documentId || candidate.localIncarnation !== incarnation)
    ));
    if (otherOwner) throw new Error('The edited restore preservation history is already owned by another project.');

    if (!inventory) {
      const preserved = await cloudSyncPublish({
        localDocumentId: documentId,
        localIncarnation: incarnation,
        bundle,
        createNewProject: true,
        newCloudProjectId: cloudProjectId,
      });
      if (
        preserved.binding.cloudProjectId !== cloudProjectId
        || preserved.snapshot.digest !== bundleDigest
      ) {
        throw new Error('The edited restore could not be durably preserved before retrying recovery.');
      }
      return;
    }

    if (!binding || binding.cloudProjectId !== cloudProjectId) {
      if (binding) await cloudSyncForgetBinding(documentId, incarnation, false);
      const head = newestCloudHead(cloudProjectHeads(inventory));
      if (!head) throw new Error('The edited restore preservation history has no readable head.');
      await installBinding({ id: documentId, incarnation }, cloudProjectId, head);
      state = await cloudSyncGetState();
      binding = bindingForIdentity(state, documentId, incarnation);
      inventory = state.projects.find((project) => project.cloudProjectId === cloudProjectId) ?? inventory;
    }
    if (!binding || binding.cloudProjectId !== cloudProjectId) {
      throw new Error('The edited restore could not be linked to its preservation history.');
    }

    const preservation = planCloudPreservation(inventory, bundleDigest);
    if (preservation.kind === 'reuse') {
      if (binding.lastSnapshotId !== preservation.snapshot.snapshotId) {
        await installBinding(
          { id: documentId, incarnation },
          cloudProjectId,
          preservation.snapshot,
        );
      }
      return;
    }
    if (preservation.parentSnapshotIds.length === 0) {
      throw new Error('The edited restore preservation history has no safe parent snapshot.');
    }
    const preserved = await cloudSyncPublish({
      localDocumentId: documentId,
      localIncarnation: incarnation,
      bundle,
      cloudProjectId,
      parentSnapshotIds: preservation.parentSnapshotIds,
    });
    if (preserved.snapshot.digest !== bundleDigest) {
      throw new Error('The latest edited restore bytes were not durably preserved.');
    }
  }, [installBinding]);

  const replanEditedRestore = useCallback(async (
    receipt: CloudSyncActionReceipt,
    documentId: string,
    incarnation: string,
  ): Promise<CloudSyncActionReceipt> => {
    const preservedCloudProjectId = await deterministicCloudRecoveryUuid(
      `logosforge-cloud-stale-restore:${receipt.actionId}:${documentId}:${incarnation}`,
    );
    const bundle = await readCompleteProjectBundle(baseUrl, documentId, incarnation);
    const bundleDigest = await cloudSyncDigest(bundle);
    const current = await cloudSyncGetState();
    const binding = bindingForIdentity(current, documentId, incarnation);
    const targetCloudProjectId = binding && binding.cloudProjectId !== receipt.originalCloudProjectId
      ? binding.cloudProjectId
      : preservedCloudProjectId;
    await ensureEditedRestoreDurable(
      documentId,
      incarnation,
      bundle,
      bundleDigest,
      targetCloudProjectId,
    );
    return createSuccessorReceipt(receipt);
  }, [baseUrl, createSuccessorReceipt, ensureEditedRestoreDurable]);

  const ensureRestored = useCallback(async (
    initialReceipt: CloudSyncActionReceipt,
  ): Promise<{ receipt: CloudSyncActionReceipt; restored: RestoredIdentity }> => {
    let receipt = initialReceipt;
    for (;;) {
      if (receipt.restoredLocalDocumentId && receipt.restoredLocalIncarnation) {
        if (await documentExists(baseUrl, receipt.restoredLocalDocumentId, receipt.restoredLocalIncarnation)) {
          return {
            receipt,
            restored: {
              id: receipt.restoredLocalDocumentId,
              incarnation: receipt.restoredLocalIncarnation,
              document: null,
            },
          };
        }
        // The restored copy was deliberately deleted (or its incarnation was
        // replaced) after the receipt was recorded. Remove any stale binding,
        // then move the semantic operation to a fresh restore id; mutating the
        // old receipt's immutable identity would make crash replay ambiguous.
        await cloudSyncForgetBinding(
          receipt.restoredLocalDocumentId,
          receipt.restoredLocalIncarnation,
          false,
        );
        receipt = await createSuccessorReceipt(receipt);
        continue;
      }
      const envelope = await cloudSyncReadSnapshot(receipt.originalCloudProjectId, receipt.snapshotId);
      const suffix = receipt.kind === 'remote-recovery'
        ? ` (Recovered ${receipt.snapshotId.slice(0, 8)})`
        : receipt.kind === 'keep-both' ? ' (Cloud copy)' : '';
      try {
        const restoredDocument = await restoreCompleteProjectBundle(
          baseUrl,
          envelope.bundle,
          `cloud-sync-action:${receipt.actionId}`,
          suffix,
        );
        const saved = await saveReceiptPhase(receipt, 'restored', restoredDocument);
        return {
          receipt: saved,
          restored: { id: restoredDocument.id, incarnation: restoredDocument.incarnation, document: restoredDocument },
        };
      } catch (error) {
        if (
          !isCloudRestoreRetryStale(error)
          || !error.documentId
          || !error.incarnation
          || receipt.restoredLocalDocumentId
        ) throw error;
        receipt = await replanEditedRestore(
          receipt,
          error.documentId,
          error.incarnation,
        );
      }
    }
  }, [baseUrl, createSuccessorReceipt, replanEditedRestore, saveReceiptPhase]);

  const preserveRetiredDocument = useCallback(async (
    localDocumentId: string,
    localIncarnation: string,
    intendedCloudProjectId: string,
  ): Promise<void> => {
    let state = await cloudSyncGetState();
    const alreadyBound = bindingForIdentity(state, localDocumentId, localIncarnation);
    if (alreadyBound && alreadyBound.cloudProjectId !== intendedCloudProjectId) {
      throw new Error('The edited superseded project is already linked to different cloud history.');
    }
    if (!alreadyBound) {
      // Clear a moveBinding tombstone before publishing the preservation fork.
      await cloudSyncForgetBinding(localDocumentId, localIncarnation, false);
    }
    const bundle = await readCompleteProjectBundle(baseUrl, localDocumentId, localIncarnation);
    const digest = await cloudSyncDigest(bundle);
    await ensureEditedRestoreDurable(
      localDocumentId,
      localIncarnation,
      bundle,
      digest,
      intendedCloudProjectId,
    );
    state = await cloudSyncGetState();
    const binding = bindingForIdentity(state, localDocumentId, localIncarnation);
    if (!binding || binding.cloudProjectId !== intendedCloudProjectId) {
      throw new Error('The edited superseded project could not be linked to its preserved history.');
    }
  }, [baseUrl, ensureEditedRestoreDurable]);

  const safelyRetireDocument = useCallback(async (
    localDocumentId: string,
    localIncarnation: string,
    expectedDigest: string | null,
    preserveCloudProjectId: string,
  ): Promise<void> => {
    if (!await documentExists(baseUrl, localDocumentId, localIncarnation)) {
      await cloudSyncForgetBinding(localDocumentId, localIncarnation, false);
      return;
    }
    const existingBinding = bindingForIdentity(
      await cloudSyncGetState(),
      localDocumentId,
      localIncarnation,
    );
    if (existingBinding) {
      if (existingBinding.cloudProjectId === preserveCloudProjectId) {
        await preserveRetiredDocument(localDocumentId, localIncarnation, preserveCloudProjectId);
        return;
      }
      throw new Error('The superseded project is linked to unexpected cloud history.');
    }
    const active = activeDocumentRef.current;
    if (!expectedDigest || (active?.id === localDocumentId && active.incarnation === localIncarnation)) {
      await preserveRetiredDocument(localDocumentId, localIncarnation, preserveCloudProjectId);
      return;
    }
    let finishOperation: (() => void) | null = null;
    let releaseInteraction: (() => void) | null = null;
    try {
      finishOperation = await acquireTrackedDocumentOperation();
      releaseInteraction = lockDocumentInteraction();
      await flushPendingDocSaves();
      const currentActive = activeDocumentRef.current;
      if (currentActive?.id === localDocumentId && currentActive.incarnation === localIncarnation) {
        await preserveRetiredDocument(localDocumentId, localIncarnation, preserveCloudProjectId);
        return;
      }
      const bundle = await readCompleteProjectBundle(baseUrl, localDocumentId, localIncarnation);
      const digest = await cloudSyncDigest(bundle);
      if (digest !== expectedDigest) {
        await preserveRetiredDocument(localDocumentId, localIncarnation, preserveCloudProjectId);
        return;
      }
      try {
        await retireCloudProjectIfUnchanged(
          baseUrl,
          { id: localDocumentId, incarnation: localIncarnation },
          expectedDigest,
          bundle,
        );
        await cloudSyncForgetBinding(localDocumentId, localIncarnation, false);
      } catch (error) {
        if (!isCloudRetireContentChanged(error)) throw error;
        await preserveRetiredDocument(localDocumentId, localIncarnation, preserveCloudProjectId);
      }
    } finally {
      releaseInteraction?.();
      finishOperation?.();
    }
  }, [baseUrl, preserveRetiredDocument]);

  const reconcileAction = useCallback(async (
    initialReceipt: CloudSyncActionReceipt,
    openRestoredOnCompletion = false,
  ): Promise<void> => {
    let receipt = initialReceipt;
    let state = await cloudSyncGetState();
    const sourceBinding = bindingForIdentity(state, receipt.sourceLocalDocumentId, receipt.sourceLocalIncarnation);
    if (receipt.kind === 'keep-both' || receipt.kind === 'use-cloud') {
      if (!receipt.intendedCloudProjectId) throw new Error('The cloud conflict receipt has no durable fork destination.');
      if (sourceBinding?.cloudProjectId !== receipt.intendedCloudProjectId) {
        if (sourceBinding && sourceBinding.cloudProjectId !== receipt.originalCloudProjectId) {
          throw new Error('The local project link changed while its conflict was pending.');
        }
        const localBundle = await readCompleteProjectBundle(
          baseUrl,
          receipt.sourceLocalDocumentId,
          receipt.sourceLocalIncarnation,
        );
        const localDigest = await cloudSyncDigest(localBundle);
        await ensureEditedRestoreDurable(
          receipt.sourceLocalDocumentId,
          receipt.sourceLocalIncarnation,
          localBundle,
          localDigest,
          receipt.intendedCloudProjectId,
        );
      }
      if (receipt.phase === 'prepared') {
        receipt = await saveReceiptPhase(receipt, 'local-forked');
      }
    }

    const ensured = await ensureRestored(receipt);
    receipt = ensured.receipt;
    const restored = ensured.restored;
    state = await cloudSyncGetState();
    let restoredBinding = bindingForIdentity(state, restored.id, restored.incarnation);

    if (receipt.kind === 'discover') {
      if (!restoredBinding) {
        const snapshot = snapshotForReceipt(state, receipt);
        if (!snapshot) throw new Error('The discovered cloud snapshot is no longer available.');
        await installBinding(restored, receipt.originalCloudProjectId, snapshot);
        state = await cloudSyncGetState();
        restoredBinding = bindingForIdentity(state, restored.id, restored.incarnation);
      }
      if (!restoredBinding || !bindingSnapshotMatches(state, restoredBinding, receipt)) {
        throw new Error('The discovered project could not be linked to its cloud snapshot.');
      }
      receipt = await saveReceiptPhase(receipt, 'binding-installed', restored);
      await cloudSyncCompleteActionReceipt(receipt.actionId);
      await refreshDocuments();
      return;
    }

    if (receipt.kind === 'remote-recovery') {
      if (!receipt.intendedCloudProjectId) throw new Error('The remote recovery receipt has no durable fork destination.');
      if (restoredBinding?.cloudProjectId !== receipt.intendedCloudProjectId) {
        if (restoredBinding) throw new Error('A recovered branch is linked to unexpected cloud history.');
        const bundle = await readCompleteProjectBundle(baseUrl, restored.id, restored.incarnation);
        const digest = await cloudSyncDigest(bundle);
        // This fork can already contain descendants if the device crashed
        // after its first binding. Reattach and extend/merge that immutable
        // history instead of requiring an empty one-root project on replay.
        await ensureEditedRestoreDurable(
          restored.id,
          restored.incarnation,
          bundle,
          digest,
          receipt.intendedCloudProjectId,
        );
      }
      await saveReceiptPhase(receipt, 'binding-installed', restored);
      await refreshDocuments();
      return;
    }

    if (receipt.kind === 'pull') {
      if (!restoredBinding || !bindingSnapshotMatches(state, restoredBinding, receipt)) {
        if (restoredBinding && restoredBinding.cloudProjectId !== receipt.originalCloudProjectId) {
          throw new Error('The restored pull target is linked to unexpected cloud history.');
        }
        const currentSourceBinding = bindingForIdentity(
          state,
          receipt.sourceLocalDocumentId,
          receipt.sourceLocalIncarnation,
        );
        if (currentSourceBinding?.cloudProjectId === receipt.originalCloudProjectId) {
          await cloudSyncMoveBinding(
            receipt.sourceLocalDocumentId,
            receipt.sourceLocalIncarnation,
            {
              localDocumentId: restored.id,
              localIncarnation: restored.incarnation,
              cloudProjectId: receipt.originalCloudProjectId,
              snapshotId: receipt.snapshotId,
              digest: receipt.snapshotDigest,
            },
            receipt.expectedSourceDigest,
          );
        } else {
          if (
            currentSourceBinding
            && currentSourceBinding.cloudProjectId !== receipt.intendedCloudProjectId
          ) {
            throw new Error('The pull source is linked to unexpected cloud history.');
          }
          const sourceStillExists = await documentExists(
            baseUrl,
            receipt.sourceLocalDocumentId,
            receipt.sourceLocalIncarnation,
          );
          if (sourceStillExists && !currentSourceBinding) {
            if (!receipt.intendedCloudProjectId) {
              throw new Error('The pull receipt has no preservation destination.');
            }
            // Binding ownership disappeared with the old restored copy. Fork
            // the still-live source first, then attach the clean restored copy
            // directly to the exact remote snapshot.
            await preserveRetiredDocument(
              receipt.sourceLocalDocumentId,
              receipt.sourceLocalIncarnation,
              receipt.intendedCloudProjectId,
            );
          }
          state = await cloudSyncGetState();
          const snapshot = snapshotForReceipt(state, receipt);
          if (!snapshot) throw new Error('The remote pull snapshot is no longer available.');
          await installBinding(restored, receipt.originalCloudProjectId, snapshot);
        }
        state = await cloudSyncGetState();
        restoredBinding = bindingForIdentity(state, restored.id, restored.incarnation);
      }
      if (!restoredBinding || !bindingSnapshotMatches(state, restoredBinding, receipt)) {
        throw new Error('The remote project was restored, but its cloud link could not be transferred safely.');
      }
      receipt = await saveReceiptPhase(receipt, 'binding-installed', restored);
      if (!receipt.intendedCloudProjectId) throw new Error('The pull receipt has no preservation destination.');
      await safelyRetireDocument(
        receipt.sourceLocalDocumentId,
        receipt.sourceLocalIncarnation,
        receipt.expectedSourceDigest,
        receipt.intendedCloudProjectId,
      );
      await cloudSyncCompleteActionReceipt(receipt.actionId);
      await refreshDocuments();
      return;
    }

    if (!restoredBinding || !bindingSnapshotMatches(state, restoredBinding, receipt)) {
      if (restoredBinding && restoredBinding.cloudProjectId !== receipt.originalCloudProjectId) {
        throw new Error('The restored cloud branch is linked to unexpected history.');
      }
      const envelope = await cloudSyncReadSnapshot(receipt.originalCloudProjectId, receipt.snapshotId);
      await cloudSyncPublish({
        localDocumentId: restored.id,
        localIncarnation: restored.incarnation,
        bundle: envelope.bundle,
        cloudProjectId: receipt.originalCloudProjectId,
        parentSnapshotIds: receipt.parentSnapshotIds,
      });
      state = await cloudSyncGetState();
      restoredBinding = bindingForIdentity(state, restored.id, restored.incarnation);
    }
    if (!restoredBinding || !bindingSnapshotMatches(state, restoredBinding, receipt)) {
      throw new Error('The chosen cloud branch was not durably resolved.');
    }
    receipt = await saveReceiptPhase(receipt, 'binding-installed', restored);
    await cloudSyncCompleteActionReceipt(receipt.actionId);
    await refreshDocuments();
    const active = activeDocumentRef.current;
    if (
      receipt.kind === 'use-cloud'
      && openRestoredOnCompletion
      && active?.id === receipt.sourceLocalDocumentId
      && active.incarnation === receipt.sourceLocalIncarnation
    ) {
      await restoreActiveDocument(async () => (
        restored.document ?? getWhiteboardForDocument(baseUrl, restored.id, undefined, restored.incarnation)
      ));
    }
  }, [
    baseUrl,
    ensureEditedRestoreDurable,
    ensureRestored,
    installBinding,
    preserveRetiredDocument,
    refreshDocuments,
    restoreActiveDocument,
    safelyRetireDocument,
    saveReceiptPhase,
  ]);

  const planRemoteRecoveryReceipt = useCallback(async (
    inventory: CloudProjectInventory,
    head: CloudSnapshotMetadata,
  ): Promise<void> => {
    const current = await cloudSyncGetState();
    if (current.actionReceipts.some((receipt) => (
      receipt.kind === 'remote-recovery'
      && receipt.originalCloudProjectId === inventory.cloudProjectId
      && receipt.snapshotId === head.snapshotId
    ))) return;
    await cloudSyncSaveActionReceipt({
      actionId: actionId('remote-recovery'),
      kind: 'remote-recovery',
      phase: 'prepared',
      sourceLocalDocumentId: `remote:${inventory.cloudProjectId}`,
      sourceLocalIncarnation: head.snapshotId,
      originalCloudProjectId: inventory.cloudProjectId,
      intendedCloudProjectId: cloudUuid(),
      snapshotId: head.snapshotId,
      snapshotDigest: head.digest,
      // This receipt recovers one immutable head. Keeping only that head here
      // avoids coupling recovery capacity to the transport's 32-parent merge
      // limit; group completeness comes from the durable recovered-head ledger.
      parentSnapshotIds: [head.snapshotId],
      expectedSourceDigest: head.digest,
    });
  }, []);

  const reconcilePendingActions = useCallback(async (): Promise<NativeCloudSyncState> => {
    let state = await cloudSyncGetState();
    const recoveryGroups = new Map<string, CloudSyncActionReceipt[]>();
    for (const receipt of state.actionReceipts) {
      if (receipt.kind !== 'remote-recovery') continue;
      const group = recoveryGroups.get(receipt.originalCloudProjectId) ?? [];
      group.push(receipt);
      recoveryGroups.set(receipt.originalCloudProjectId, group);
    }
    for (const [cloudProjectId, receipts] of recoveryGroups) {
      const inventory = state.projects.find((project) => project.cloudProjectId === cloudProjectId);
      if (!inventory) throw new Error('A pending remote recovery history is not available yet.');
      // The provider folder may receive another branch while recovery is in
      // progress. Re-read the current DAG heads and include every newly
      // observed head before the original multi-head UUID can be ignored.
      const recoveredHeadIds = state.recoveredRemoteHeads.find((entry) => (
        entry.cloudProjectId === cloudProjectId
      ))?.snapshotIds ?? [];
      const plan = planRemoteRecovery(inventory, receipts, recoveredHeadIds);
      for (const snapshotId of plan.missingHeadIds) {
        const head = inventory.snapshots.find((snapshot) => snapshot.snapshotId === snapshotId);
        if (!head) throw new Error('A preserved branch needed for recovery is not available yet.');
        await planRemoteRecoveryReceipt(inventory, head);
      }
      state = await cloudSyncGetState();
    }
    for (const plannedReceipt of [...state.actionReceipts].sort((left, right) => (
      left.createdAt.localeCompare(right.createdAt) || left.actionId.localeCompare(right.actionId)
    ))) {
      const receipt = state.actionReceipts.find((candidate) => (
        candidate.actionId === plannedReceipt.actionId
      ));
      if (!receipt) continue;
      await reconcileAction(receipt);
      state = await cloudSyncGetState();
    }
    const completedGroups = new Map<string, CloudSyncActionReceipt[]>();
    for (const receipt of state.actionReceipts) {
      if (receipt.kind !== 'remote-recovery') continue;
      const group = completedGroups.get(receipt.originalCloudProjectId) ?? [];
      group.push(receipt);
      completedGroups.set(receipt.originalCloudProjectId, group);
    }
    for (const [cloudProjectId, receipts] of completedGroups) {
      const inventory = state.projects.find((project) => project.cloudProjectId === cloudProjectId);
      if (!inventory) continue;
      const recoveredHeadIds = state.recoveredRemoteHeads.find((entry) => (
        entry.cloudProjectId === cloudProjectId
      ))?.snapshotIds ?? [];
      const completionPlan = planRemoteRecovery(inventory, receipts, recoveredHeadIds);
      if (!completionPlan.readyToIgnoreOriginal) continue;
      // Record the installed heads first. If the app exits after this write,
      // the replacement renderer can distinguish this recovered history from
      // a user-deleted remote project and resume when a new head appears.
      state = await cloudSyncRecordRecoveredRemoteHeads(
        cloudProjectId,
        completionPlan.currentHeadIds,
      );
      await cloudSyncSetRemoteIgnored(cloudProjectId, true);
      const verificationState = await cloudSyncGetState();
      const verificationInventory = verificationState.projects.find((project) => (
        project.cloudProjectId === cloudProjectId
      ));
      if (
        !verificationInventory
        || !planRemoteRecovery(
          verificationInventory,
          receipts,
          verificationState.recoveredRemoteHeads.find((entry) => (
            entry.cloudProjectId === cloudProjectId
          ))?.snapshotIds ?? [],
        ).readyToIgnoreOriginal
      ) {
        await cloudSyncSetRemoteIgnored(cloudProjectId, false);
        state = await cloudSyncGetState();
        continue;
      }
      for (const receipt of receipts) await cloudSyncCompleteActionReceipt(receipt.actionId);
      state = await cloudSyncGetState();
    }
    return state;
  }, [planRemoteRecoveryReceipt, reconcileAction]);

  const cleanupRetiredDocuments = useCallback(async (
    initialState: NativeCloudSyncState,
  ): Promise<NativeCloudSyncState> => {
    let state = initialState;
    for (const retired of state.retiredLocalDocuments ?? []) {
      if (!await documentExists(baseUrl, retired.localDocumentId, retired.localIncarnation)) {
        await cloudSyncForgetBinding(retired.localDocumentId, retired.localIncarnation, false);
        state = await cloudSyncGetState();
        continue;
      }
      await safelyRetireDocument(
        retired.localDocumentId,
        retired.localIncarnation,
        retired.expectedDigest,
        cloudUuid(),
      );
      state = await cloudSyncGetState();
    }
    return state;
  }, [baseUrl, safelyRetireDocument]);

  const performSync = useCallback(async (): Promise<void> => {
    if (!available || !ready || !documentsLoaded) return;
    if (syncingRef.current) {
      rerunRef.current = true;
      await syncCompletionRef.current;
      return;
    }
    syncingRef.current = true;
    syncCompletionRef.current = new Promise<void>((resolve) => { resolveSyncCompletionRef.current = resolve; });
    try {
      do {
        rerunRef.current = false;
        let state = await cloudSyncGetState();
        nativeStateRef.current = state;
        setNativeState(state);
        if (!state.enabled) {
          commitUi(stateAfterNative(state, null));
          return;
        }
        if (state.folderAvailable === false) {
          commitUi({
            ...stateAfterNative(state, null),
            status: 'folder-unavailable',
            detail: state.lastError || 'The selected cloud folder is unavailable. Local writing continues safely.',
          });
          return;
        }
        if ((state.warnings?.length ?? 0) > 0) {
          commitUi({
            ...stateAfterNative(state, null),
            status: 'attention',
            detail: state.warnings?.[0] || 'Some cloud snapshots could not be read safely.',
          });
          return;
        }
        commitUi({ ...stateAfterNative(state, pendingReviewRef.current, true), status: 'syncing' });
        state = await cloudSyncRetryOutbox();
        state = await reconcilePendingActions();
        state = await cleanupRetiredDocuments(state);
        await flushPendingDocSaves();

        let foundReview: PendingReview | null = null;
        let waitingForRemoteHistory = 0;
        const localDocuments = await listDocuments(baseUrl);
        for (const local of localDocuments) {
          if (state.retiredLocalDocuments?.some((retired) => (
            retired.localDocumentId === local.id && retired.localIncarnation === local.incarnation
          ))) continue;
          const bundle = await readCompleteProjectBundle(baseUrl, local.id, local.incarnation);
          const digest = await cloudSyncDigest(bundle);
          const binding = bindingForDocument(state, local);
          const inventory = inventoryForBinding(state, binding);
          const decision = decideCloudSync(binding, digest, inventory);
          if (decision.kind === 'seed') {
            await cloudSyncPublish({ localDocumentId: local.id, localIncarnation: local.incarnation, bundle, createNewProject: true });
          } else if (decision.kind === 'upload') {
            await cloudSyncPublish({
              localDocumentId: local.id,
              localIncarnation: local.incarnation,
              bundle,
              cloudProjectId: binding?.cloudProjectId,
              parentSnapshotIds: decision.parentSnapshotIds,
            });
          } else if (decision.kind === 'advance' && binding) {
            await installBinding(local, binding.cloudProjectId, decision.snapshot);
          } else if (decision.kind === 'merge-identical' && binding) {
            await cloudSyncPublish({
              localDocumentId: local.id,
              localIncarnation: local.incarnation,
              bundle,
              cloudProjectId: binding.cloudProjectId,
              parentSnapshotIds: decision.heads.map((head) => head.snapshotId),
            });
          } else if (decision.kind === 'pull' && binding) {
            const active = activeDocumentRef.current;
            if (active?.id === local.id && active.incarnation === local.incarnation) {
              if (!foundReview) {
                foundReview = {
                  kind: 'bound',
                  document: local,
                  binding,
                  inventory: inventory ?? {
                    cloudProjectId: binding.cloudProjectId,
                    snapshots: [decision.snapshot],
                    headSnapshotIds: [decision.snapshot.snapshotId],
                  },
                  heads: [decision.snapshot],
                  localBundle: bundle,
                  localDigest: digest,
                  reason: 'A newer cloud version is ready. Review it before replacing the open manuscript.',
                };
              }
            } else {
              const next = await cloudSyncSaveActionReceipt({
                actionId: actionId('pull'),
                kind: 'pull',
                phase: 'prepared',
                sourceLocalDocumentId: local.id,
                sourceLocalIncarnation: local.incarnation,
                originalCloudProjectId: binding.cloudProjectId,
                intendedCloudProjectId: cloudUuid(),
                snapshotId: decision.snapshot.snapshotId,
                snapshotDigest: decision.snapshot.digest,
                parentSnapshotIds: [decision.snapshot.snapshotId],
                expectedSourceDigest: digest,
              });
              const receipt = next.actionReceipts.find((candidate) => (
                candidate.kind === 'pull'
                && candidate.sourceLocalDocumentId === local.id
                && candidate.sourceLocalIncarnation === local.incarnation
                && candidate.snapshotId === decision.snapshot.snapshotId
              ));
              if (!receipt) throw new Error('The pull receipt could not be recovered.');
              await reconcileAction(receipt);
              state = await cloudSyncGetState();
            }
          } else if (decision.kind === 'conflict' && binding && inventory && !foundReview) {
            foundReview = {
              kind: 'bound', document: local, binding, inventory, heads: decision.heads,
              localBundle: bundle, localDigest: digest, reason: decision.reason,
            };
          } else if (decision.kind === 'wait') {
            waitingForRemoteHistory += 1;
          }
        }

        state = await cloudSyncGetState();
        const allBoundCloudIds = new Set(state.bindings.map((binding) => binding.cloudProjectId));
        for (const remote of state.projects) {
          if (allBoundCloudIds.has(remote.cloudProjectId)) continue;
          const heads = sortedHeads(remote);
          const recovered = state.recoveredRemoteHeads.find((entry) => (
            entry.cloudProjectId === remote.cloudProjectId
          ));
          const ignored = state.ignoredCloudProjectIds.includes(remote.cloudProjectId);
          if (recovered) {
            const ledgerPlan = planRemoteRecovery(remote, [], recovered.snapshotIds);
            if (ledgerPlan.missingHeadIds.length === 0) {
              // This is a completed replacement-device recovery, not a user
              // deletion. Restore its ignore marker after a crash between the
              // durable ledger write and the ignore write.
              if (!ignored) await cloudSyncSetRemoteIgnored(remote.cloudProjectId, true);
              continue;
            }
            // A provider delivered a new concurrent branch after the original
            // history was recovered. Reopen it automatically and fork only the
            // unseen heads; ledger-known branches are never imported twice.
            if (ignored) await cloudSyncSetRemoteIgnored(remote.cloudProjectId, false);
            for (const snapshotId of ledgerPlan.missingHeadIds) {
              const head = heads.find((candidate) => candidate.snapshotId === snapshotId);
              if (!head) throw new Error('A newly discovered recovery head is unavailable.');
              await planRemoteRecoveryReceipt(remote, head);
            }
            state = await reconcilePendingActions();
            continue;
          }
          // An ignored project without a recovered-head ledger represents an
          // intentional local deletion; do not resurrect it.
          if (ignored) continue;
          if (heads.length !== 1) {
            if (!foundReview) {
              foundReview = {
                kind: 'remote',
                inventory: remote,
                heads,
                reason: `${heads.length} preserved cloud versions need recovery on this device.`,
              };
            }
            continue;
          }
          const head = heads[0];
          const next = await cloudSyncSaveActionReceipt({
            actionId: actionId('discover'),
            kind: 'discover',
            phase: 'prepared',
            sourceLocalDocumentId: `remote:${remote.cloudProjectId}`,
            sourceLocalIncarnation: head.snapshotId,
            originalCloudProjectId: remote.cloudProjectId,
            snapshotId: head.snapshotId,
            snapshotDigest: head.digest,
            parentSnapshotIds: [head.snapshotId],
            expectedSourceDigest: head.digest,
          });
          const receipt = next.actionReceipts.find((candidate) => (
            candidate.kind === 'discover'
            && candidate.originalCloudProjectId === remote.cloudProjectId
            && candidate.snapshotId === head.snapshotId
          ));
          if (!receipt) throw new Error('The discovery receipt could not be recovered.');
          await reconcileAction(receipt);
          allBoundCloudIds.add(remote.cloudProjectId);
        }

        state = await cloudSyncGetState();
        nativeStateRef.current = state;
        setNativeState(state);
        pendingReviewRef.current = foundReview;
        setPendingReview(foundReview);
        const nextUi = stateAfterNative(state, foundReview);
        commitUi(!foundReview && waitingForRemoteHistory > 0
          ? {
            ...nextUi,
            status: 'attention',
            detail: `${waitingForRemoteHistory} linked project histor${waitingForRemoteHistory === 1 ? 'y is' : 'ies are'} not available in the selected folder yet. Sync is waiting safely.`,
          }
          : nextUi);
      } while (rerunRef.current);
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      const state = nativeStateRef.current;
      commitUi({
        enabled: state?.enabled ?? false,
        automatic: state?.automatic ?? false,
        folderPath: state?.folderPath ?? null,
        status: 'error',
        detail,
        lastSuccessfulSyncAt: state?.lastSuccessfulSyncAt ?? null,
        conflict: pendingReviewRef.current && state ? reviewSummary(pendingReviewRef.current, state.deviceId) : null,
        busy: false,
      });
    } finally {
      syncingRef.current = false;
      resolveSyncCompletionRef.current?.();
      resolveSyncCompletionRef.current = null;
      syncCompletionRef.current = null;
    }
  }, [available, baseUrl, cleanupRetiredDocuments, commitUi, documentsLoaded, installBinding, ready, reconcileAction, reconcilePendingActions]);

  const chooseFolder = useCallback(async () => {
    try {
      commitUi({ ...uiState, status: 'checking', busy: true, detail: 'Choosing a cloud folder…' });
      const state = await cloudSyncChooseFolder();
      nativeStateRef.current = state;
      setNativeState(state);
      commitUi(stateAfterNative(state, pendingReviewRef.current));
      if (state.enabled) await performSync();
    } catch (error) {
      commitUi({ ...uiState, status: 'error', busy: false, detail: error instanceof Error ? error.message : String(error) });
    }
  }, [commitUi, performSync, uiState]);

  const disable = useCallback(async () => {
    const state = await cloudSyncDisable();
    nativeStateRef.current = state;
    setNativeState(state);
    pendingReviewRef.current = null;
    setPendingReview(null);
    setConflictOpen(false);
    commitUi(stateAfterNative(state, null));
  }, [commitUi]);

  const setAutomatic = useCallback(async (automatic: boolean) => {
    const state = await cloudSyncSetAutomatic(automatic);
    nativeStateRef.current = state;
    setNativeState(state);
    commitUi(stateAfterNative(state, pendingReviewRef.current));
    if (automatic && state.enabled) await performSync();
  }, [commitUi, performSync]);

  const resolveBoundReview = useCallback(async (action: 'keep-both' | 'cloud' | 'device'): Promise<void> => {
    if (pendingReviewRef.current?.kind !== 'bound') return;
    while (syncingRef.current) await syncCompletionRef.current;
    syncingRef.current = true;
    syncCompletionRef.current = new Promise<void>((resolve) => { resolveSyncCompletionRef.current = resolve; });
    setConflictError(null);
    commitUi({ ...uiState, status: 'syncing', busy: true, detail: 'Resolving the preserved versions…' });
    let finishOperation: (() => void) | null = null;
    let releaseInteraction: (() => void) | null = null;
    let followup = false;
    try {
      finishOperation = await acquireTrackedDocumentOperation();
      releaseInteraction = lockDocumentInteraction();
      await flushPendingDocSaves();
      const original = pendingReviewRef.current;
      if (!original || original.kind !== 'bound') return;
      const currentDocument = (await listDocuments(baseUrl)).find((candidate) => (
        candidate.id === original.document.id && candidate.incarnation === original.document.incarnation
      ));
      if (!currentDocument) throw new Error('The local project changed identity; run sync again.');
      const currentState = await cloudSyncGetState();
      const currentBinding = bindingForDocument(currentState, currentDocument);
      const currentInventory = inventoryForBinding(currentState, currentBinding);
      if (!currentBinding || !currentInventory) throw new Error('The cloud project link changed; run sync again.');
      const currentBundle = await readCompleteProjectBundle(baseUrl, currentDocument.id, currentDocument.incarnation);
      const currentDigest = await cloudSyncDigest(currentBundle);
      const currentDecision = decideCloudSync(currentBinding, currentDigest, currentInventory);
      if (currentDecision.kind !== 'conflict' && currentDecision.kind !== 'pull') {
        pendingReviewRef.current = null;
        setPendingReview(null);
        setConflictOpen(false);
        followup = true;
        return;
      }
      const heads = currentDecision.kind === 'conflict' ? currentDecision.heads : [currentDecision.snapshot];
      const chosen = newestCloudHead(heads);
      if (!chosen) throw new Error('No readable cloud version is available.');
      if (action === 'device') {
        const resolution = await cloudSyncPublish({
          localDocumentId: currentDocument.id,
          localIncarnation: currentDocument.incarnation,
          bundle: currentBundle,
          cloudProjectId: currentBinding.cloudProjectId,
          parentSnapshotIds: heads.map((head) => head.snapshotId),
        });
        if (resolution.snapshot.digest !== currentDigest) {
          throw new Error('The cloud folder did not durably preserve the current local project.');
        }
      } else {
        const kind = action === 'cloud' ? 'use-cloud' : 'keep-both';
        const next = await cloudSyncSaveActionReceipt({
          actionId: actionId(kind),
          kind,
          phase: 'prepared',
          sourceLocalDocumentId: currentDocument.id,
          sourceLocalIncarnation: currentDocument.incarnation,
          originalCloudProjectId: currentBinding.cloudProjectId,
          intendedCloudProjectId: cloudUuid(),
          snapshotId: chosen.snapshotId,
          snapshotDigest: chosen.digest,
          parentSnapshotIds: heads.map((head) => head.snapshotId).sort(),
          expectedSourceDigest: currentDigest,
        });
        const receipt = next.actionReceipts.find((candidate) => (
          candidate.kind === kind
          && candidate.sourceLocalDocumentId === currentDocument.id
          && candidate.snapshotId === chosen.snapshotId
        ));
        if (!receipt) throw new Error('The conflict recovery receipt could not be recovered.');
        releaseInteraction?.();
        releaseInteraction = null;
        finishOperation?.();
        finishOperation = null;
        await reconcileAction(receipt, kind === 'use-cloud');
      }
      pendingReviewRef.current = null;
      setPendingReview(null);
      setConflictOpen(false);
      followup = true;
    } catch (error) {
      setConflictError(error instanceof Error ? error.message : String(error));
      const state = nativeStateRef.current;
      if (state) commitUi(stateAfterNative(state, pendingReviewRef.current));
    } finally {
      releaseInteraction?.();
      finishOperation?.();
      syncingRef.current = false;
      resolveSyncCompletionRef.current?.();
      resolveSyncCompletionRef.current = null;
      syncCompletionRef.current = null;
    }
    if (followup) await performSync();
  }, [baseUrl, commitUi, performSync, reconcileAction, uiState]);

  const recoverRemote = useCallback(async (): Promise<void> => {
    const review = pendingReviewRef.current;
    if (!review || review.kind !== 'remote') return;
    while (syncingRef.current) await syncCompletionRef.current;
    syncingRef.current = true;
    syncCompletionRef.current = new Promise<void>((resolve) => { resolveSyncCompletionRef.current = resolve; });
    setConflictError(null);
    commitUi({ ...uiState, status: 'syncing', busy: true, detail: 'Recovering every preserved cloud version…' });
    let followup = false;
    try {
      for (const head of review.heads) await planRemoteRecoveryReceipt(review.inventory, head);
      await reconcilePendingActions();
      pendingReviewRef.current = null;
      setPendingReview(null);
      setConflictOpen(false);
      followup = true;
    } catch (error) {
      setConflictError(error instanceof Error ? error.message : String(error));
      const state = nativeStateRef.current;
      if (state) commitUi(stateAfterNative(state, pendingReviewRef.current));
    } finally {
      syncingRef.current = false;
      resolveSyncCompletionRef.current?.();
      resolveSyncCompletionRef.current = null;
      syncCompletionRef.current = null;
    }
    if (followup) await performSync();
  }, [commitUi, performSync, planRemoteRecoveryReceipt, reconcilePendingActions, uiState]);

  const forgetDeletedDocument = useCallback(async (deleted: DocumentSummary) => {
    if (!available) return;
    try {
      const next = await cloudSyncForgetBinding(deleted.id, deleted.incarnation, true);
      nativeStateRef.current = next;
      setNativeState(next);
      commitUi(stateAfterNative(next, pendingReviewRef.current));
    } catch (error) {
      commitUi({
        ...uiState,
        status: 'error',
        detail: `The document was deleted locally, but its sync link could not be retired. ${error instanceof Error ? error.message : String(error)}`,
      });
    }
  }, [available, commitUi, uiState]);

  useEffect(() => {
    mountedRef.current = true;
    void loadNativeState();
    const unsubscribe = onCloudSyncChanged(() => { void loadNativeState(); });
    return () => {
      mountedRef.current = false;
      unsubscribe();
    };
  }, [loadNativeState]);

  useEffect(() => {
    if (!ready || !documentsLoaded || !nativeState?.enabled || !nativeState.automatic) return undefined;
    const timer = window.setInterval(() => { void performSync(); }, AUTOMATIC_SYNC_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [documentsLoaded, nativeState?.enabled, nativeState?.automatic, performSync, ready]);

  useEffect(() => {
    if (!ready || !documentsLoaded || !nativeState?.enabled || !nativeState.automatic) return;
    const key = `${nativeState.deviceId}:${nativeState.folderPath ?? ''}`;
    if (startupSyncKeyRef.current === key) return;
    startupSyncKeyRef.current = key;
    void performSync();
  }, [documentsLoaded, nativeState?.enabled, nativeState?.automatic, nativeState?.deviceId, nativeState?.folderPath, performSync, ready]);

  useEffect(() => {
    if (!documentsLoaded || saveStatus !== 'saved' || !nativeState?.enabled || !nativeState.automatic) return undefined;
    const timer = window.setTimeout(() => { void performSync(); }, EDIT_QUIET_PERIOD_MS);
    return () => window.clearTimeout(timer);
  }, [documentsLoaded, nativeState?.enabled, nativeState?.automatic, performSync, saveStatus]);

  const controls = useMemo<CloudSyncControls>(() => ({
    state: uiState,
    onChooseFolder: chooseFolder,
    onSyncNow: performSync,
    onRetry: async () => {
      await cloudSyncRetryOutbox();
      await performSync();
    },
    onDisable: disable,
    onAutomaticChange: setAutomatic,
    onReviewConflict: () => {
      setConflictError(null);
      setConflictOpen(true);
    },
  }), [chooseFolder, disable, performSync, setAutomatic, uiState]);

  return {
    controls,
    conflictOpen,
    conflictError,
    openConflict: () => {
      setConflictError(null);
      setConflictOpen(true);
    },
    closeConflict: () => {
      if (!uiState.busy) setConflictOpen(false);
    },
    keepBoth: () => resolveBoundReview('keep-both'),
    useCloudCopy: () => resolveBoundReview('cloud'),
    replaceCloud: () => resolveBoundReview('device'),
    recoverRemote,
    forgetDeletedDocument,
  };
}
