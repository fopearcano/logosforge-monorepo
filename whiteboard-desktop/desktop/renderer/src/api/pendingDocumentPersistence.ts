import { backendFetch, withDocumentIncarnation } from './backendAuth';
import { requestRecoveryNoticeCheck } from './recoverySignal';
import {
  PersistenceRecoveryError,
  responseError,
  RevisionConflictError,
} from './responseError';
import type {
  LogosForgeBridge,
  PendingDocumentConflictReceipt,
  PendingDocumentConflictRecovery,
  PendingDocumentWrite,
  PendingDocumentWriteResult,
} from './backend';
import { captureDocumentIncarnation } from '../state/currentDocument';
import {
  advanceResourceRevision,
  requireResourceRevision,
  resourceEtag,
  validateResourceRevisionResponse,
} from './resourceRevision';
import {
  claimWhiteboardConflict,
  discardWhiteboardConflictRecovery,
  restoreWhiteboardConflict,
} from '../features/whiteboard/pendingWhiteboardRecovery';
import {
  claimOutlineConflict,
  discardOutlineConflictRecovery,
  restoreOutlineConflict,
} from '../features/outline/pendingOutlineRecovery';
import {
  coordinateRecoveryAbandonment,
  reconcilePendingDocumentRecoveries,
  samePendingDocumentConflict,
} from './pendingRecoveryPolicy';

const sessionId = typeof globalThis.crypto?.randomUUID === 'function'
  ? globalThis.crypto.randomUUID()
  : `renderer_${Date.now()}_${Math.random().toString(36).slice(2)}`;

let publishedRecoveries: readonly PendingDocumentConflictRecovery[] = [];
const recoveryListeners = new Set<() => void>();
let publicationGeneration = 0;
const recoveryMutationGeneration = new Map<string, number>();
let recoveryRefresh: Promise<PendingDocumentConflictRecovery[]> | null = null;
let recoveryReloadExemption: PendingDocumentConflictReceipt | null = null;

function replacePublishedRecoveries(
  recoveries: PendingDocumentConflictRecovery[],
  forcedMutationIds: readonly string[] = [],
): void {
  const previous = new Map(publishedRecoveries.map((item) => [item.conflictId, item]));
  const next = new Map(recoveries.map((item) => [item.conflictId, item]));
  const changed = new Set(forcedMutationIds);
  for (const conflictId of new Set([...previous.keys(), ...next.keys()])) {
    const before = previous.get(conflictId);
    const after = next.get(conflictId);
    if (!before || !after || before.version !== after.version) changed.add(conflictId);
  }
  publishedRecoveries = recoveries;
  if (changed.size) {
    publicationGeneration += 1;
    for (const conflictId of changed) {
      recoveryMutationGeneration.set(conflictId, publicationGeneration);
    }
  }
  for (const listener of recoveryListeners) listener();
}

function mergePublishedRecovery(recovery: PendingDocumentConflictRecovery): void {
  const existing = publishedRecoveries.find((item) => item.conflictId === recovery.conflictId);
  if (existing && existing.version >= recovery.version) return;
  const next = publishedRecoveries.filter((item) => item.conflictId !== recovery.conflictId);
  replacePublishedRecoveries([...next, recovery], [recovery.conflictId]);
}

function publishAuthoritativeRecoveries(
  recoveries: PendingDocumentConflictRecovery[],
  requestGeneration: number,
): PendingDocumentConflictRecovery[] {
  const next = reconcilePendingDocumentRecoveries(
    publishedRecoveries,
    recoveries,
    requestGeneration,
    recoveryMutationGeneration,
  );
  replacePublishedRecoveries(next);
  return next;
}

export function pendingDocumentRecoveriesSnapshot(): readonly PendingDocumentConflictRecovery[] {
  return publishedRecoveries;
}

export function subscribePendingDocumentRecoveries(listener: () => void): () => void {
  recoveryListeners.add(listener);
  return () => recoveryListeners.delete(listener);
}

function nativeBridge(): LogosForgeBridge | null {
  if (typeof window === 'undefined') return null;
  const candidate = window.logosforge;
  return candidate && typeof candidate.persistPendingDocument === 'function' ? candidate : null;
}

function request(
  kind: PendingDocumentWrite['kind'],
  documentId: string,
  revision: number,
  payload: object,
  incarnation: string,
  resourceRevision: string,
): PendingDocumentWrite {
  return { kind, documentId, incarnation, resourceRevision, revision, sessionId, payload };
}

function endpoint(baseUrl: string, kind: PendingDocumentWrite['kind'], documentId: string): string {
  const route = kind === 'whiteboard' ? '/api/whiteboard' : '/api/outline/items';
  return `${baseUrl}${route}?doc=${encodeURIComponent(documentId)}`;
}

/** Electron uses the main-owned FIFO; the direct branch is Vite-browser development only. */
export async function persistPendingDocument(
  baseUrl: string,
  kind: PendingDocumentWrite['kind'],
  documentId: string,
  revision: number,
  payload: object,
  incarnation: string = captureDocumentIncarnation(documentId),
): Promise<{ ok: true; resourceRevision: string }> {
  const expectedRevision = requireResourceRevision(kind, documentId, incarnation);
  const pending = request(
    kind,
    documentId,
    revision,
    payload,
    incarnation,
    expectedRevision,
  );
  const native = nativeBridge();
  if (native) {
    const result = await native.persistPendingDocument(pending);
    if (!result.ok) {
      mergePublishedRecovery({
        ...result.recovery,
        write: pending,
        error: {
          code: result.code,
          status: result.status,
          message: result.message,
          ...(result.currentRevision ? { currentRevision: result.currentRevision } : {}),
          ...(result.currentEtag ? { currentEtag: result.currentEtag } : {}),
        },
      });
      if (
        result.code === 'revision_conflict'
        && typeof result.currentRevision === 'string'
        && typeof result.currentEtag === 'string'
      ) {
        throw new RevisionConflictError(
          result.message,
          result.currentRevision,
          result.currentEtag,
          result.recovery,
        );
      }
      throw new PersistenceRecoveryError(
        result.message,
        result.status,
        result.code,
        result.recovery,
      );
    }
    advanceResourceRevision(
      kind,
      documentId,
      incarnation,
      expectedRevision,
      result.resourceRevision,
    );
    requestRecoveryNoticeCheck();
    return result;
  }
  const response = await backendFetch(endpoint(baseUrl, kind, documentId), {
    method: 'PUT',
    headers: withDocumentIncarnation(incarnation, {
      'Content-Type': 'application/json',
      'If-Match': resourceEtag(kind, incarnation, expectedRevision),
      'X-LogosForge-Mutation-Id': `${sessionId}_${revision}`,
    }),
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw await responseError(response, `Could not save ${kind}`);
  const data = await response.json() as { revision?: unknown };
  const nextRevision = validateResourceRevisionResponse(
    kind,
    incarnation,
    data.revision,
    response.headers.get('ETag'),
  );
  const result: PendingDocumentWriteResult = { ok: true, resourceRevision: nextRevision };
  advanceResourceRevision(
    kind,
    documentId,
    incarnation,
    expectedRevision,
    result.resourceRevision,
  );
  return result;
}

/**
 * `sendSync` returns only after main has validated and copied the snapshot. The
 * main handler queues HTTP asynchronously, so pagehide never waits on network.
 */
export function persistPendingDocumentOnUnload(
  baseUrl: string,
  kind: PendingDocumentWrite['kind'],
  documentId: string,
  revision: number,
  payload: object,
  incarnation: string = captureDocumentIncarnation(documentId),
): void {
  const resourceRevision = requireResourceRevision(kind, documentId, incarnation);
  const pending = request(
    kind,
    documentId,
    revision,
    payload,
    incarnation,
    resourceRevision,
  );
  const native = nativeBridge();
  if (native) {
    if (!native.persistPendingDocumentOnUnload(pending)) {
      console.error(`[persistence] main process rejected ${kind} unload snapshot`);
    }
    return;
  }
  // Browser-only preview fallback. Packaged Electron never relies on Chromium's
  // aggregate keepalive quota or bypasses the main serializer.
  void backendFetch(endpoint(baseUrl, kind, documentId), {
    method: 'PUT',
    headers: withDocumentIncarnation(incarnation, {
      'Content-Type': 'application/json',
      'If-Match': resourceEtag(kind, incarnation, resourceRevision),
      'X-LogosForge-Mutation-Id': `${sessionId}_${revision}`,
    }),
    body: JSON.stringify(payload),
    keepalive: true,
  }).catch(() => {});
}

export function retainPendingDocumentConflict(
  kind: PendingDocumentWrite['kind'],
  documentId: string,
  revision: number,
  payload: object,
  recovery: PendingDocumentConflictReceipt,
  incarnation: string = captureDocumentIncarnation(documentId),
): PendingDocumentConflictReceipt | null {
  const native = nativeBridge();
  if (!native) return null;
  const resourceRevision = requireResourceRevision(kind, documentId, incarnation);
  const result = native.retainPendingDocumentConflict(
    recovery,
    request(kind, documentId, revision, payload, incarnation, resourceRevision),
  );
  if (!result.ok || !result.recovery) return null;
  const existing = publishedRecoveries.find((item) => item.conflictId === recovery.conflictId);
  if (existing) {
    mergePublishedRecovery({
      ...existing,
      ...result.recovery,
      write: {
        ...existing.write,
        ...request(kind, documentId, revision, payload, incarnation, resourceRevision),
        payload: kind === 'whiteboard'
          ? { ...existing.write.payload, ...payload }
          : payload,
      },
    });
  }
  return result.recovery;
}

function recoveryError(recovery: PendingDocumentConflictRecovery): PersistenceRecoveryError {
  if (
    recovery.error.code === 'revision_conflict'
    && typeof recovery.error.currentRevision === 'string'
    && typeof recovery.error.currentEtag === 'string'
  ) {
    return new RevisionConflictError(
      recovery.error.message,
      recovery.error.currentRevision,
      recovery.error.currentEtag,
      recovery,
    );
  }
  return new PersistenceRecoveryError(
    recovery.error.message,
    recovery.error.status,
    recovery.error.code,
    recovery,
  );
}

function hydratePendingDocumentConflicts(
  recoveries: PendingDocumentConflictRecovery[],
): void {
  for (const recovery of recoveries) {
    const error = recoveryError(recovery);
    if (recovery.kind === 'whiteboard') restoreWhiteboardConflict(recovery, error);
    else if (recovery.kind === 'outline') restoreOutlineConflict(recovery, error);
  }
}

/** Hydrate, but do not acknowledge, main-owned rescue entries after renderer loss. */
export async function recoverPendingDocumentPersistence(): Promise<PendingDocumentConflictRecovery[]> {
  if (recoveryRefresh) return recoveryRefresh;
  const requestGeneration = publicationGeneration;
  const refresh = (async () => {
    const recoveries = await (
      nativeBridge()?.waitForPendingDocumentPersistence() ?? Promise.resolve([])
    );
    const published = publishAuthoritativeRecoveries(recoveries, requestGeneration);
    hydratePendingDocumentConflicts(published);
    return published;
  })();
  recoveryRefresh = refresh;
  try {
    return await refresh;
  } finally {
    if (recoveryRefresh === refresh) recoveryRefresh = null;
  }
}

/** Close gate: unresolved recoveries remain unsafe until an explicit resolution. */
export async function waitForPendingDocumentPersistence(): Promise<void> {
  const recoveries = await recoverPendingDocumentPersistence();
  const blocking = recoveryReloadExemption
    ? recoveries.filter((recovery) => !samePendingDocumentConflict(
      recovery,
      recoveryReloadExemption as PendingDocumentConflictReceipt,
    ))
    : recoveries;
  if (blocking.length) throw recoveryError(blocking[0]);
}

export function acknowledgePendingDocumentConflict(
  recovery: PendingDocumentConflictReceipt | undefined,
): Promise<boolean> {
  if (!recovery) return Promise.resolve(true);
  const acknowledgment = nativeBridge()?.acknowledgePendingDocumentConflict(recovery)
    ?? Promise.resolve(false);
  return acknowledgment.then((acknowledged) => {
    if (acknowledged) {
      replacePublishedRecoveries(
        publishedRecoveries.filter((item) => item.conflictId !== recovery.conflictId),
        [recovery.conflictId],
      );
    }
    return acknowledged;
  });
}

/**
 * Active-editor abandonment is a reload transaction, not a raw page refresh.
 * Main retains the exact recovery until every other renderer store and any
 * external-file prompt succeeds, then acknowledges it only after reload starts.
 */
export async function abandonPendingDocumentRecoveryAndReload(
  recovery: PendingDocumentConflictRecovery,
  flushOtherState: () => Promise<void>,
): Promise<boolean> {
  const native = nativeBridge();
  if (!native) throw new Error('A coordinated desktop reload is unavailable.');
  return coordinateRecoveryAbandonment({
    discardTarget: () => recovery.kind === 'whiteboard'
      ? discardWhiteboardConflictRecovery(recovery)
      : discardOutlineConflictRecovery(recovery),
    flushOtherState,
    requestCoordinatedReload: async () => {
      recoveryReloadExemption = recovery;
      try {
        const reloading = await native.reloadAfterAbandoningPendingDocumentConflict(recovery);
        if (!reloading) recoveryReloadExemption = null;
        return reloading;
      } catch (error) {
        recoveryReloadExemption = null;
        throw error;
      }
    },
    restoreTarget: async () => {
      recoveryReloadExemption = null;
      const error = recoveryError(recovery);
      if (recovery.kind === 'whiteboard') {
        restoreWhiteboardConflict(recovery, error);
        claimWhiteboardConflict(recovery.documentId, recovery.incarnation);
      } else {
        restoreOutlineConflict(recovery, error);
        claimOutlineConflict(recovery.documentId, recovery.incarnation);
      }
      // The captured complete snapshot is already safe locally. A separate
      // uncertain main write must not make rollback depend on drain success.
      await recoverPendingDocumentPersistence().catch(() => {});
    },
  });
}

export async function discardPendingDocumentRecovery(
  recovery: PendingDocumentConflictRecovery,
): Promise<boolean> {
  const discarded = recovery.kind === 'whiteboard'
    ? discardWhiteboardConflictRecovery(recovery)
    : discardOutlineConflictRecovery(recovery);
  if (!discarded) {
    await recoverPendingDocumentPersistence();
    return false;
  }
  try {
    const acknowledged = await acknowledgePendingDocumentConflict(recovery);
    if (!acknowledged) await recoverPendingDocumentPersistence();
    return acknowledged;
  } catch (error) {
    await recoverPendingDocumentPersistence().catch(() => {});
    throw error;
  }
}

/**
 * Let main own the complete fence -> DELETE -> reconcile -> commit transaction.
 * The operation therefore survives renderer reload/crash after DELETE succeeds.
 * Plain-browser development returns false and uses the direct API fallback.
 */
export async function deleteDocumentWithNativePersistenceFence(
  documentId: string,
  incarnation: string,
): Promise<boolean> {
  const native = nativeBridge();
  if (!native) return false;
  await native.deleteDocumentWithPersistenceFence(documentId, incarnation);
  return true;
}
