import type { DrafterPage } from './types';
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

export interface RetainedDrafterSnapshot {
  documentId: string;
  incarnation?: string;
  revision: number;
  pages: DrafterPage[];
  mainRecovery?: PendingDocumentConflictReceipt;
}

interface DrafterQueue {
  incarnation: string | null;
  generation: number;
  revision: number;
  latest: DrafterPage[];
  pending: DrafterPage[] | null;
  running: Promise<void> | null;
  transport: DrafterSnapshotTransport | null;
  conflict: Error | null;
  mainRecovery: PendingDocumentConflictReceipt | null;
}

/**
 * `revision` is the renderer-local mutation sequence used by the desktop FIFO.
 * The opaque backend revision is owned by resourceRevision.ts and is advanced
 * by persistPendingDocument after each acknowledgement.
 */
export type DrafterSnapshotWriter = (
  documentId: string,
  pages: DrafterPage[],
  revision: number,
) => Promise<unknown>;

export interface DrafterSnapshotTransport {
  incarnation?: string;
  write: DrafterSnapshotWriter;
  writeOnUnload?: (documentId: string, pages: DrafterPage[], revision: number) => void;
  retainConflict?: (
    documentId: string,
    pages: DrafterPage[],
    revision: number,
    recovery: PendingDocumentConflictReceipt,
  ) => PendingDocumentConflictReceipt | null;
}

const queues = new Map<string, DrafterQueue>();
const stagedConflicts = new Map<string, {
  recovery: PendingDocumentConflictRecovery;
  error: Error;
}>();
const blockedDocumentIds = new Set<string>();
let nextRevision = 0;

/** Queue a complete Drafter collection under the document that owns it. */
export function queueDrafterSnapshot(
  documentId: string,
  pages: DrafterPage[],
  transport?: DrafterSnapshotTransport,
): RetainedDrafterSnapshot | null {
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
  const queue: DrafterQueue = current ?? {
    incarnation: transport?.incarnation ?? null,
    generation: 0,
    revision: 0,
    latest: pages,
    pending: null,
    running: null,
    transport: null,
    conflict: null,
    mainRecovery: null,
  };
  if (!queue.incarnation && transport?.incarnation) queue.incarnation = transport.incarnation;
  queue.revision = ++nextRevision;
  queue.latest = pages;
  queue.pending = pages;
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
      pages,
      queue.revision,
      queue.mainRecovery,
    );
    if (recovery) queue.mainRecovery = recovery;
  }
  return {
    documentId,
    ...(queue.incarnation ? { incarnation: queue.incarnation } : {}),
    revision: queue.revision,
    pages,
    ...(queue.mainRecovery ? { mainRecovery: queue.mainRecovery } : {}),
  };
}

function installDrafterConflict(
  recovery: PendingDocumentConflictRecovery,
  error: Error,
): RetainedDrafterSnapshot | null {
  const pages = (recovery.write.payload as { pages?: unknown }).pages;
  if (!Array.isArray(pages)) return null;
  const current = queues.get(recovery.documentId);
  if (
    current?.mainRecovery
    && current.mainRecovery.conflictId === recovery.conflictId
    && current.mainRecovery.version >= recovery.version
  ) return peekRetainedDrafterSnapshot(recovery.documentId, recovery.incarnation);

  const queue: DrafterQueue = current ?? {
    incarnation: recovery.incarnation,
    generation: 0,
    revision: 0,
    latest: pages as DrafterPage[],
    pending: null,
    running: null,
    transport: null,
    conflict: null,
    mainRecovery: null,
  };
  queue.incarnation = recovery.incarnation;
  queue.revision = ++nextRevision;
  if (!current) queue.latest = pages as DrafterPage[];
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
  return peekRetainedDrafterSnapshot(recovery.documentId, recovery.incarnation);
}

/** Restore a main-owned full Drafter collection without retrying its stale PUT. */
export function restoreDrafterConflict(
  recovery: PendingDocumentConflictRecovery,
  error: Error,
): RetainedDrafterSnapshot | null {
  if (recovery.kind !== 'drafter' || recovery.write.kind !== 'drafter') return null;
  const current = queues.get(recovery.documentId);
  if (!current || (current.incarnation && current.incarnation !== recovery.incarnation)) {
    const key = `${recovery.documentId}:${recovery.incarnation}`;
    const staged = stagedConflicts.get(key);
    if (!staged || staged.recovery.version < recovery.version) {
      stagedConflicts.set(key, { recovery, error });
    }
    return null;
  }
  return installDrafterConflict(recovery, error);
}

export function claimDrafterConflict(
  documentId: string,
  incarnation: string,
): RetainedDrafterSnapshot | null {
  const current = queues.get(documentId);
  if (current?.incarnation && current.incarnation !== incarnation) queues.delete(documentId);
  const key = `${documentId}:${incarnation}`;
  const staged = stagedConflicts.get(key);
  if (staged) {
    stagedConflicts.delete(key);
    installDrafterConflict(staged.recovery, staged.error);
  }
  const queue = queues.get(documentId);
  if (queue && !queue.incarnation) queue.incarnation = incarnation;
  return peekRetainedDrafterSnapshot(documentId, incarnation);
}

export function peekRetainedDrafterSnapshot(
  documentId: string,
  incarnation?: string,
): RetainedDrafterSnapshot | null {
  const queue = queues.get(documentId);
  if (!queue || (incarnation && queue.incarnation && queue.incarnation !== incarnation)) return null;
  return {
    documentId,
    ...(queue.incarnation ? { incarnation: queue.incarnation } : {}),
    revision: queue.revision,
    pages: queue.latest,
    ...(queue.mainRecovery ? { mainRecovery: queue.mainRecovery } : {}),
  };
}

export function newestRetainedDrafterSnapshot(
  first: RetainedDrafterSnapshot | null,
  second: RetainedDrafterSnapshot | null,
): RetainedDrafterSnapshot | null {
  if (!first) return second;
  if (!second) return first;
  return first.revision >= second.revision ? first : second;
}

/** Serialize complete-collection writes for one immutable document id. */
export function flushDrafterSnapshots(
  documentId: string,
  write?: DrafterSnapshotWriter,
): Promise<void> {
  const queue = queues.get(documentId);
  if (!queue) return Promise.resolve();
  if (queue.running) return queue.running;
  if (blockedDocumentIds.has(documentId)) return Promise.resolve();
  if (queue.conflict) return Promise.reject(queue.conflict);
  if (!queue.pending) return Promise.resolve();
  const writer = write ?? queue.transport?.write;
  if (!writer) return Promise.reject(new Error(`No save transport for Drafter ${documentId}`));

  const generation = queue.generation;
  const run = async (): Promise<void> => {
    while (
      queue.pending
      && queues.get(documentId) === queue
      && queue.generation === generation
      && !blockedDocumentIds.has(documentId)
    ) {
      const pages = queue.pending;
      const savedRevision = queue.revision;
      queue.pending = null;
      try {
        await writer(documentId, pages, savedRevision);
      } catch (error) {
        if (queues.get(documentId) === queue && queue.generation === generation) {
          // Every update is a complete collection; a newer snapshot includes
          // the failed one's intended history and must win.
          queue.pending ??= pages;
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
export function blockDrafterWrites(documentId: string): void {
  if (documentId) blockedDocumentIds.add(documentId);
}

/** Re-enable persistence after a failed DELETE; retained snapshots can retry. */
export function resumeDrafterWrites(documentId: string): void {
  blockedDocumentIds.delete(documentId);
}

export function discardRetainedDrafterSnapshot(documentId: string): void {
  const queue = queues.get(documentId);
  if (queue) queue.generation += 1;
  queues.delete(documentId);
  blockedDocumentIds.delete(documentId);
}

export function discardDrafterConflictRecovery(
  recovery: PendingDocumentConflictReceipt,
): boolean {
  if (recovery.kind !== 'drafter') return false;
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

/** Commit an explicit conflict reload only when its captured collection is unchanged. */
export function discardConflictedDrafterSnapshot(
  retained: RetainedDrafterSnapshot,
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

export function waitForDrafterWrites(documentId: string): Promise<void> {
  return queues.get(documentId)?.running ?? Promise.resolve();
}

export function drafterRevisionConflict(documentId: string): Error | null {
  return queues.get(documentId)?.conflict ?? null;
}

// These coordinators intentionally live for the renderer lifetime, not the
// Drafter surface lifetime. Hidden/faulted pages therefore still participate
// in document handoff, deletion, and pagehide recovery.
registerDocFlusher(() => flushDrafterSnapshots(getCurrentDocId()));
registerDocDiscarder(() => discardRetainedDrafterSnapshot(getCurrentDocId()));
registerUnloadFlush(() => {
  const documentId = getCurrentDocId();
  if (blockedDocumentIds.has(documentId)) return;
  const queue = queues.get(documentId);
  if (!queue) return;
  queue.transport?.writeOnUnload?.(documentId, queue.latest, queue.revision);
});
