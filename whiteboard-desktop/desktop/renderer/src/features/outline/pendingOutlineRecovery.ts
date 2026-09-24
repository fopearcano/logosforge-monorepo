import type { OutlineNode } from './outlineModel';
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

export interface RetainedOutlineSnapshot {
  documentId: string;
  incarnation?: string;
  revision: number;
  items: OutlineNode[];
  mainRecovery?: PendingDocumentConflictReceipt;
}

interface OutlineQueue {
  incarnation: string | null;
  generation: number;
  revision: number;
  latest: OutlineNode[];
  pending: OutlineNode[] | null;
  running: Promise<void> | null;
  transport: OutlineSnapshotTransport | null;
  conflict: Error | null;
  mainRecovery: PendingDocumentConflictReceipt | null;
}

export type OutlineSnapshotWriter = (
  documentId: string,
  items: OutlineNode[],
  revision: number,
) => Promise<unknown>;

export interface OutlineSnapshotTransport {
  incarnation?: string;
  write: OutlineSnapshotWriter;
  writeOnUnload?: (documentId: string, items: OutlineNode[], revision: number) => void;
  retainConflict?: (
    documentId: string,
    items: OutlineNode[],
    revision: number,
    recovery: PendingDocumentConflictReceipt,
  ) => PendingDocumentConflictReceipt | null;
}

const queues = new Map<string, OutlineQueue>();
const stagedConflicts = new Map<string, {
  recovery: PendingDocumentConflictRecovery;
  error: Error;
}>();
const blockedDocumentIds = new Set<string>();
let nextRevision = 0;

/** Queue a complete outline snapshot under the document that owns it. */
export function queueOutlineSnapshot(
  documentId: string,
  items: OutlineNode[],
  transport?: OutlineSnapshotTransport,
): RetainedOutlineSnapshot | null {
  if (!documentId) return null;
  let current = queues.get(documentId);
  if (
    current
    && transport?.incarnation
    && current.incarnation
    && current.incarnation !== transport.incarnation
  ) {
    queues.delete(documentId);
    current = undefined;
  }
  const queue: OutlineQueue = current ?? {
    incarnation: transport?.incarnation ?? null,
    generation: 0,
    revision: 0,
    latest: items,
    pending: null,
    running: null,
    transport: null,
    conflict: null,
    mainRecovery: null,
  };
  if (!queue.incarnation && transport?.incarnation) queue.incarnation = transport.incarnation;
  queue.revision = ++nextRevision;
  queue.latest = items;
  queue.pending = items;
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
      items,
      queue.revision,
      queue.mainRecovery,
    );
    if (recovery) queue.mainRecovery = recovery;
  }
  return {
    documentId,
    ...(queue.incarnation ? { incarnation: queue.incarnation } : {}),
    revision: queue.revision,
    items,
    ...(queue.mainRecovery ? { mainRecovery: queue.mainRecovery } : {}),
  };
}

function installOutlineConflict(
  recovery: PendingDocumentConflictRecovery,
  error: Error,
): RetainedOutlineSnapshot | null {
  const items = (recovery.write.payload as { items?: unknown }).items;
  if (!Array.isArray(items)) return null;
  const current = queues.get(recovery.documentId);
  if (
    current?.mainRecovery
    && current.mainRecovery.conflictId === recovery.conflictId
    && current.mainRecovery.version >= recovery.version
  ) return peekRetainedOutlineSnapshot(recovery.documentId, recovery.incarnation);

  const queue: OutlineQueue = current ?? {
    incarnation: recovery.incarnation,
    generation: 0,
    revision: 0,
    latest: items as OutlineNode[],
    pending: null,
    running: null,
    transport: null,
    conflict: null,
    mainRecovery: null,
  };
  queue.incarnation = recovery.incarnation;
  queue.revision = ++nextRevision;
  if (!current) queue.latest = items as OutlineNode[];
  queue.pending = queue.latest;
  queue.conflict = error;
  queue.mainRecovery = {
    conflictId: recovery.conflictId,
    version: recovery.version,
    kind: recovery.kind,
    documentId: recovery.documentId,
    incarnation: recovery.incarnation,
  };
  queues.set(recovery.documentId, queue);
  return peekRetainedOutlineSnapshot(recovery.documentId, recovery.incarnation);
}

/** Restore a main-owned full outline snapshot without retrying its stale PUT. */
export function restoreOutlineConflict(
  recovery: PendingDocumentConflictRecovery,
  error: Error,
): RetainedOutlineSnapshot | null {
  if (recovery.kind !== 'outline' || recovery.write.kind !== 'outline') return null;
  const current = queues.get(recovery.documentId);
  if (!current || (current.incarnation && current.incarnation !== recovery.incarnation)) {
    const key = `${recovery.documentId}:${recovery.incarnation}`;
    const staged = stagedConflicts.get(key);
    if (!staged || staged.recovery.version < recovery.version) {
      stagedConflicts.set(key, { recovery, error });
    }
    return null;
  }
  return installOutlineConflict(recovery, error);
}

export function claimOutlineConflict(
  documentId: string,
  incarnation: string,
): RetainedOutlineSnapshot | null {
  const current = queues.get(documentId);
  if (current?.incarnation && current.incarnation !== incarnation) queues.delete(documentId);
  const key = `${documentId}:${incarnation}`;
  const staged = stagedConflicts.get(key);
  if (staged) {
    stagedConflicts.delete(key);
    installOutlineConflict(staged.recovery, staged.error);
  }
  const queue = queues.get(documentId);
  if (queue && !queue.incarnation) queue.incarnation = incarnation;
  return peekRetainedOutlineSnapshot(documentId, incarnation);
}

export function peekRetainedOutlineSnapshot(
  documentId: string,
  incarnation?: string,
): RetainedOutlineSnapshot | null {
  const queue = queues.get(documentId);
  if (!queue || (incarnation && queue.incarnation && queue.incarnation !== incarnation)) return null;
  return {
    documentId,
    ...(queue.incarnation ? { incarnation: queue.incarnation } : {}),
    revision: queue.revision,
    items: queue.latest,
    ...(queue.mainRecovery ? { mainRecovery: queue.mainRecovery } : {}),
  };
}

export function newestRetainedOutlineSnapshot(
  first: RetainedOutlineSnapshot | null,
  second: RetainedOutlineSnapshot | null,
): RetainedOutlineSnapshot | null {
  if (!first) return second;
  if (!second) return first;
  return first.revision >= second.revision ? first : second;
}

/** Serialize all complete-snapshot writes for one immutable document id. */
export function flushOutlineSnapshots(
  documentId: string,
  write?: OutlineSnapshotWriter,
): Promise<void> {
  const queue = queues.get(documentId);
  if (!queue) return Promise.resolve();
  if (queue.running) return queue.running;
  if (blockedDocumentIds.has(documentId)) return Promise.resolve();
  if (queue.conflict) return Promise.reject(queue.conflict);
  if (!queue.pending) return Promise.resolve();
  const writer = write ?? queue.transport?.write;
  if (!writer) return Promise.reject(new Error(`No save transport for outline ${documentId}`));

  const generation = queue.generation;
  const run = async (): Promise<void> => {
    while (
      queue.pending
      && queues.get(documentId) === queue
      && queue.generation === generation
      && !blockedDocumentIds.has(documentId)
    ) {
      const items = queue.pending;
      const savedRevision = queue.revision;
      queue.pending = null;
      try {
        await writer(documentId, items, savedRevision);
      } catch (error) {
        if (queues.get(documentId) === queue && queue.generation === generation) {
          // Each outline update is a complete snapshot; a newer pending snapshot
          // already includes the failed one's intended history and must win.
          queue.pending ??= items;
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
      if (
        queues.get(documentId) === queue
        && queue.generation === generation
        && queue.revision === savedRevision
      ) {
        queues.delete(documentId);
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

/** Hold new snapshots in memory while DELETE is in flight. */
export function blockOutlineWrites(documentId: string): void {
  if (documentId) blockedDocumentIds.add(documentId);
}

/** Re-enable persistence after a failed DELETE; retained snapshots can retry. */
export function resumeOutlineWrites(documentId: string): void {
  blockedDocumentIds.delete(documentId);
}

export function discardRetainedOutlineSnapshot(documentId: string): void {
  const queue = queues.get(documentId);
  if (queue) queue.generation += 1;
  queues.delete(documentId);
  blockedDocumentIds.delete(documentId);
}

export function discardOutlineConflictRecovery(
  recovery: PendingDocumentConflictReceipt,
): boolean {
  if (recovery.kind !== 'outline') return false;
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
  blockedDocumentIds.delete(recovery.documentId);
  return true;
}

/** Commit an explicit conflict reload only when its captured local snapshot is unchanged. */
export function discardConflictedOutlineSnapshot(
  retained: RetainedOutlineSnapshot,
): boolean {
  const queue = queues.get(retained.documentId);
  if (
    !queue
    || !queue.conflict
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
  blockedDocumentIds.delete(retained.documentId);
  return true;
}

export function waitForOutlineWrites(documentId: string): Promise<void> {
  return queues.get(documentId)?.running ?? Promise.resolve();
}

export function outlineRevisionConflict(documentId: string): Error | null {
  return queues.get(documentId)?.conflict ?? null;
}

// These coordinators intentionally live for the renderer lifetime, not the
// Outline panel lifetime. Hidden/faulted panels therefore still participate in
// document handoff, deletion, and pagehide recovery.
registerDocFlusher(() => flushOutlineSnapshots(getCurrentDocId()));
registerDocDiscarder(() => discardRetainedOutlineSnapshot(getCurrentDocId()));
registerUnloadFlush(() => {
  const documentId = getCurrentDocId();
  if (blockedDocumentIds.has(documentId)) return;
  const queue = queues.get(documentId);
  if (!queue) return;
  queue.transport?.writeOnUnload?.(documentId, queue.latest, queue.revision);
});
