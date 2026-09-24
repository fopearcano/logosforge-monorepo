import type { WhiteboardDocument, WhiteboardUpdate } from './types';
import { mergeWhiteboardPatch, restoreWhiteboardPatch } from './whiteboardPatch';
import type {
  PendingDocumentConflictReceipt,
  PendingDocumentConflictRecovery,
} from '../../api/backend';
import { isPersistenceRecoveryError } from '../../api/responseError';
import {
  getCurrentDocId,
  registerDocDiscarder,
  registerDocFlusher,
  registerUnloadFlush,
} from '../../state/currentDocument';

/**
 * A document-keyed renderer-memory save queue that survives React remounts.
 * One queue owns write ordering for each document even when an error boundary
 * briefly leaves an old and replacement hook alive at the same time.
 */
export interface WhiteboardPatchReceipt {
  documentId: string;
  incarnation?: string;
  /** Identifies this in-memory queue even if SQLite later reuses the document id. */
  queueEpoch: number;
  revision: number;
}

export interface RetainedWhiteboardPatch extends WhiteboardPatchReceipt {
  patch: WhiteboardUpdate;
  mainRecovery?: PendingDocumentConflictReceipt;
}

interface SaveQueue {
  incarnation: string | null;
  epoch: number;
  generation: number;
  revision: number;
  persistedRevision: number;
  latest: WhiteboardUpdate;
  pending: WhiteboardUpdate | null;
  running: Promise<void> | null;
  transport: WhiteboardPatchTransport | null;
  conflict: Error | null;
  mainRecovery: PendingDocumentConflictReceipt | null;
}

export type WhiteboardPatchWriter = (
  documentId: string,
  patch: WhiteboardUpdate,
  revision: number,
) => Promise<unknown>;

export interface WhiteboardPatchTransport {
  incarnation?: string;
  write: WhiteboardPatchWriter;
  writeOnUnload?: (documentId: string, patch: WhiteboardUpdate, revision: number) => void;
  retainConflict?: (
    documentId: string,
    patch: WhiteboardUpdate,
    revision: number,
    recovery: PendingDocumentConflictReceipt,
  ) => PendingDocumentConflictReceipt | null;
}

const queues = new Map<string, SaveQueue>();
const snapshotBases = new Map<string, WhiteboardUpdate>();
const stagedConflicts = new Map<string, {
  recovery: PendingDocumentConflictRecovery;
  error: Error;
}>();
const blockedDocumentIds = new Set<string>();
let nextRevision = 0;
let nextQueueEpoch = 0;

export function queueWhiteboardPatch(
  documentId: string,
  patch: WhiteboardUpdate,
  transport?: WhiteboardPatchTransport,
): RetainedWhiteboardPatch | null {
  if (!documentId || Object.keys(patch).length === 0) return null;
  let current = queues.get(documentId);
  if (
    current
    && transport?.incarnation
    && current.incarnation
    && current.incarnation !== transport.incarnation
  ) {
    queues.delete(documentId);
    snapshotBases.delete(documentId);
    current = undefined;
  }
  const queue: SaveQueue = current ?? {
    incarnation: transport?.incarnation ?? null,
    epoch: ++nextQueueEpoch,
    generation: 0,
    revision: 0,
    persistedRevision: 0,
    latest: {},
    pending: null,
    running: null,
    transport: null,
    conflict: null,
    mainRecovery: null,
  };
  if (!queue.incarnation && transport?.incarnation) queue.incarnation = transport.incarnation;
  queue.revision = ++nextRevision;
  const completeSnapshot = mergeWhiteboardPatch(snapshotBases.get(documentId) ?? null, patch);
  snapshotBases.set(documentId, completeSnapshot);
  queue.latest = mergeWhiteboardPatch(queue.latest, completeSnapshot);
  queue.pending = mergeWhiteboardPatch(queue.pending, completeSnapshot);
  if (transport) {
    queue.transport = queue.transport
      ? {
        ...queue.transport,
        ...transport,
        writeOnUnload: transport.writeOnUnload ?? queue.transport.writeOnUnload,
        retainConflict: transport.retainConflict ?? queue.transport.retainConflict,
      }
      : transport;
  }
  queues.set(documentId, queue);
  if (queue.conflict && queue.mainRecovery && queue.transport?.retainConflict) {
    const recovery = queue.transport.retainConflict(
      documentId,
      queue.latest,
      queue.revision,
      queue.mainRecovery,
    );
    if (recovery) queue.mainRecovery = recovery;
  }
  return {
    documentId,
    ...(queue.incarnation ? { incarnation: queue.incarnation } : {}),
    queueEpoch: queue.epoch,
    revision: queue.revision,
    patch: queue.latest,
    ...(queue.mainRecovery ? { mainRecovery: queue.mainRecovery } : {}),
  };
}

/** Seed the next mutation with the complete local view, without marking it dirty. */
export function seedWhiteboardRecoverySnapshot(document: WhiteboardDocument): void {
  const base: WhiteboardUpdate = {
    title: document.title,
    mode: document.mode,
    blocks: document.blocks,
    settings: document.settings,
  };
  let queue = queues.get(document.id);
  if (queue?.incarnation && queue.incarnation !== document.incarnation) {
    queues.delete(document.id);
    snapshotBases.delete(document.id);
    queue = undefined;
  }
  if (queue && !queue.incarnation) queue.incarnation = document.incarnation;
  snapshotBases.set(document.id, base);
  const stagedKey = `${document.id}:${document.incarnation}`;
  const staged = stagedConflicts.get(stagedKey);
  if (staged) {
    stagedConflicts.delete(stagedKey);
    installWhiteboardConflict(staged.recovery, staged.error);
    queue = queues.get(document.id);
  }
  if (!queue || Object.keys(queue.latest).length === 0) {
    snapshotBases.set(document.id, base);
    return;
  }
  const complete = mergeWhiteboardPatch(base, queue.latest);
  snapshotBases.set(document.id, complete);
  queue.latest = complete;
  if (queue.pending) queue.pending = mergeWhiteboardPatch(base, queue.pending);
}

function installWhiteboardConflict(
  recovery: PendingDocumentConflictRecovery,
  error: Error,
): RetainedWhiteboardPatch | null {
  const patch = recovery.write.payload as WhiteboardUpdate;
  const current = queues.get(recovery.documentId);
  if (
    current?.mainRecovery
    && current.mainRecovery.conflictId === recovery.conflictId
    && current.mainRecovery.version >= recovery.version
  ) return peekRetainedWhiteboardPatch(recovery.documentId, recovery.incarnation);

  const queue: SaveQueue = current ?? {
    incarnation: recovery.incarnation,
    epoch: ++nextQueueEpoch,
    generation: 0,
    revision: 0,
    persistedRevision: 0,
    latest: {},
    pending: null,
    running: null,
    transport: null,
    conflict: null,
    mainRecovery: null,
  };
  queue.incarnation = recovery.incarnation;
  queue.revision = ++nextRevision;
  queue.latest = mergeWhiteboardPatch(patch, queue.latest);
  queue.pending = queue.latest;
  queue.conflict = error;
  queue.mainRecovery = {
    conflictId: recovery.conflictId,
    version: recovery.version,
    kind: recovery.kind,
    documentId: recovery.documentId,
    incarnation: recovery.incarnation,
  };
  snapshotBases.set(recovery.documentId, queue.latest);
  queues.set(recovery.documentId, queue);
  return peekRetainedWhiteboardPatch(recovery.documentId, recovery.incarnation);
}

/** Restore a main-owned rescue without acknowledging it or retrying the PUT. */
export function restoreWhiteboardConflict(
  recovery: PendingDocumentConflictRecovery,
  error: Error,
): RetainedWhiteboardPatch | null {
  if (recovery.kind !== 'whiteboard' || recovery.write.kind !== 'whiteboard') return null;
  const current = queues.get(recovery.documentId);
  if (!current || (current.incarnation && current.incarnation !== recovery.incarnation)) {
    const key = `${recovery.documentId}:${recovery.incarnation}`;
    const staged = stagedConflicts.get(key);
    if (!staged || staged.recovery.version < recovery.version) {
      stagedConflicts.set(key, { recovery, error });
    }
    return null;
  }
  return installWhiteboardConflict(recovery, error);
}

/** Claim a staged main rescue once the caller has proven the active incarnation. */
export function claimWhiteboardConflict(
  documentId: string,
  incarnation: string,
): RetainedWhiteboardPatch | null {
  const current = queues.get(documentId);
  if (current?.incarnation && current.incarnation !== incarnation) {
    queues.delete(documentId);
    snapshotBases.delete(documentId);
  }
  const key = `${documentId}:${incarnation}`;
  const staged = stagedConflicts.get(key);
  if (staged) {
    stagedConflicts.delete(key);
    installWhiteboardConflict(staged.recovery, staged.error);
  }
  const queue = queues.get(documentId);
  if (queue && !queue.incarnation) queue.incarnation = incarnation;
  return peekRetainedWhiteboardPatch(documentId, incarnation);
}

export function peekRetainedWhiteboardPatch(
  documentId: string,
  incarnation?: string,
): RetainedWhiteboardPatch | null {
  const queue = queues.get(documentId);
  if (
    !queue
    || (incarnation && queue.incarnation && queue.incarnation !== incarnation)
    || Object.keys(queue.latest).length === 0
  ) return null;
  return {
    documentId,
    ...(queue.incarnation ? { incarnation: queue.incarnation } : {}),
    queueEpoch: queue.epoch,
    revision: queue.revision,
    patch: queue.latest,
    ...(queue.mainRecovery ? { mainRecovery: queue.mainRecovery } : {}),
  };
}

export function newestRetainedWhiteboardPatch(
  first: RetainedWhiteboardPatch | null,
  second: RetainedWhiteboardPatch | null,
): RetainedWhiteboardPatch | null {
  if (!first) return second;
  if (!second) return first;
  return first.revision >= second.revision ? first : second;
}

/**
 * Serialize saves for one immutable document id across old and replacement
 * React trees. A navigation cannot redirect a retiring writer into a new doc.
 */
export function flushWhiteboardPatches(
  documentId: string,
  write?: WhiteboardPatchWriter,
): Promise<void> {
  const queue = queues.get(documentId);
  if (!queue) return Promise.resolve();
  if (queue.running) return queue.running;
  if (blockedDocumentIds.has(documentId)) return Promise.resolve();
  if (queue.conflict) return Promise.reject(queue.conflict);
  if (!queue.pending) return Promise.resolve();
  const writer = write ?? queue.transport?.write;
  if (!writer) return Promise.reject(new Error(`No save transport for document ${documentId}`));

  const generation = queue.generation;
  const run = async (): Promise<void> => {
    while (
      queue.pending
      && queues.get(documentId) === queue
      && queue.generation === generation
      && !blockedDocumentIds.has(documentId)
    ) {
      const patch = queue.pending;
      const savedRevision = queue.revision;
      queue.pending = null;
      try {
        await writer(documentId, patch, savedRevision);
      } catch (error) {
        if (queues.get(documentId) === queue && queue.generation === generation) {
          queue.pending = restoreWhiteboardPatch(patch, queue.pending);
          if (isPersistenceRecoveryError(error)) {
            queue.conflict = error instanceof Error ? error : new Error(String(error));
            queue.mainRecovery = error.recovery ?? null;
            if (queue.mainRecovery && queue.transport?.retainConflict) {
              queue.mainRecovery = queue.transport.retainConflict(
                documentId,
                queue.latest,
                queue.revision,
                queue.mainRecovery,
              ) ?? queue.mainRecovery;
            }
          }
        }
        throw error;
      }
      if (queues.get(documentId) === queue && queue.generation === generation) {
        queue.persistedRevision = Math.max(queue.persistedRevision, savedRevision);
      }
      if (
        queues.get(documentId) === queue
        && queue.generation === generation
        && queue.revision === savedRevision
      ) {
        queue.latest = {};
      }
    }
  };

  const tracked = run().finally(() => {
    if (queues.get(documentId) === queue && queue.running === tracked) {
      queue.running = null;
    }
  });
  queue.running = tracked;
  return tracked;
}

/**
 * Flush and acknowledge one exact queued snapshot (or a newer merged snapshot).
 * `false` means the queue was blocked, discarded, or replaced; a transport
 * failure rejects. Callers may therefore gate destructive derived cleanup on a
 * durable manuscript revision without confusing elapsed debounce time for save
 * success.
 */
export async function flushWhiteboardPatchThrough(
  receipt: WhiteboardPatchReceipt,
): Promise<boolean> {
  const queue = queues.get(receipt.documentId);
  if (!queue || queue.epoch !== receipt.queueEpoch) return false;
  await flushWhiteboardPatches(receipt.documentId);
  return (
    queues.get(receipt.documentId) === queue
    && queue.epoch === receipt.queueEpoch
    && queue.persistedRevision >= receipt.revision
  );
}

/** Hold new snapshots in memory while DELETE is in flight. */
export function blockWhiteboardWrites(documentId: string): void {
  if (documentId) blockedDocumentIds.add(documentId);
}

/** Re-enable persistence after a failed DELETE; retained snapshots can retry. */
export function resumeWhiteboardWrites(documentId: string): void {
  blockedDocumentIds.delete(documentId);
}

export function discardRetainedWhiteboardPatch(documentId: string): void {
  const queue = queues.get(documentId);
  if (queue) queue.generation += 1;
  queues.delete(documentId);
  snapshotBases.delete(documentId);
  blockedDocumentIds.delete(documentId);
}

export function discardWhiteboardConflictRecovery(
  recovery: PendingDocumentConflictReceipt,
): boolean {
  if (recovery.kind !== 'whiteboard') return false;
  const stagedKey = `${recovery.documentId}:${recovery.incarnation}`;
  const staged = stagedConflicts.get(stagedKey);
  if (
    staged
    && staged.recovery.conflictId === recovery.conflictId
    && staged.recovery.version === recovery.version
  ) {
    stagedConflicts.delete(stagedKey);
    return true;
  }
  const queue = queues.get(recovery.documentId);
  if (
    !queue
    || queue.mainRecovery?.conflictId !== recovery.conflictId
    || queue.mainRecovery.version !== recovery.version
    || queue.running
  ) return false;
  queue.generation += 1;
  queues.delete(recovery.documentId);
  snapshotBases.delete(recovery.documentId);
  blockedDocumentIds.delete(recovery.documentId);
  return true;
}

/**
 * Discard one conflicted draft only if no edit arrived while its replacement
 * snapshot was being fetched. This is the commit point for explicit reload.
 */
export function discardConflictedWhiteboardPatch(
  retained: RetainedWhiteboardPatch,
): boolean {
  const queue = queues.get(retained.documentId);
  if (
    !queue
    || !queue.conflict
    || queue.epoch !== retained.queueEpoch
    || queue.revision !== retained.revision
    || queue.running
    || (
      retained.mainRecovery
      && (
        queue.mainRecovery?.conflictId !== retained.mainRecovery.conflictId
        || queue.mainRecovery.version !== retained.mainRecovery.version
      )
    )
  ) return false;
  queue.generation += 1;
  queues.delete(retained.documentId);
  snapshotBases.delete(retained.documentId);
  blockedDocumentIds.delete(retained.documentId);
  return true;
}

export function waitForWhiteboardWrites(documentId: string): Promise<void> {
  return queues.get(documentId)?.running ?? Promise.resolve();
}

export function whiteboardRevisionConflict(documentId: string): Error | null {
  return queues.get(documentId)?.conflict ?? null;
}

export function applyRetainedWhiteboardPatch(
  document: WhiteboardDocument,
  retained: RetainedWhiteboardPatch | null,
): WhiteboardDocument {
  if (
    !retained
    || retained.documentId !== document.id
    || (retained.incarnation && retained.incarnation !== document.incarnation)
  ) return document;
  return { ...document, ...retained.patch };
}

// App-lifetime coordination keeps root-boundary recovery and graceful pagehide safety
// alive even while every hook below the boundary is temporarily unmounted.
registerDocFlusher(() => flushWhiteboardPatches(getCurrentDocId()));
registerDocDiscarder(() => discardRetainedWhiteboardPatch(getCurrentDocId()));
registerUnloadFlush(() => {
  const documentId = getCurrentDocId();
  if (blockedDocumentIds.has(documentId)) return;
  const queue = queues.get(documentId);
  if (!queue || Object.keys(queue.latest).length === 0) return;
  queue.transport?.writeOnUnload?.(documentId, queue.latest, queue.revision);
});
