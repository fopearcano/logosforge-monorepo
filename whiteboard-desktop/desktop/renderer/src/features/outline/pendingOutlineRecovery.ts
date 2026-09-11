import type { OutlineNode } from './outlineModel';
import {
  getCurrentDocId,
  registerDocDiscarder,
  registerDocFlusher,
  registerUnloadFlush,
} from '../../state/currentDocument';

export interface RetainedOutlineSnapshot {
  documentId: string;
  revision: number;
  items: OutlineNode[];
}

interface OutlineQueue {
  generation: number;
  revision: number;
  latest: OutlineNode[];
  pending: OutlineNode[] | null;
  running: Promise<void> | null;
  transport: OutlineSnapshotTransport | null;
}

export type OutlineSnapshotWriter = (
  documentId: string,
  items: OutlineNode[],
  revision: number,
) => Promise<unknown>;

export interface OutlineSnapshotTransport {
  write: OutlineSnapshotWriter;
  writeOnUnload?: (documentId: string, items: OutlineNode[], revision: number) => void;
}

const queues = new Map<string, OutlineQueue>();
const blockedDocumentIds = new Set<string>();
let nextRevision = 0;

/** Queue a complete outline snapshot under the document that owns it. */
export function queueOutlineSnapshot(
  documentId: string,
  items: OutlineNode[],
  transport?: OutlineSnapshotTransport,
): RetainedOutlineSnapshot | null {
  if (!documentId) return null;
  const current = queues.get(documentId);
  const queue: OutlineQueue = current ?? {
    generation: 0,
    revision: 0,
    latest: items,
    pending: null,
    running: null,
    transport: null,
  };
  queue.revision = ++nextRevision;
  queue.latest = items;
  queue.pending = items;
  if (transport) queue.transport = transport;
  queues.set(documentId, queue);
  return { documentId, revision: queue.revision, items };
}

export function peekRetainedOutlineSnapshot(documentId: string): RetainedOutlineSnapshot | null {
  const queue = queues.get(documentId);
  if (!queue) return null;
  return { documentId, revision: queue.revision, items: queue.latest };
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

export function waitForOutlineWrites(documentId: string): Promise<void> {
  return queues.get(documentId)?.running ?? Promise.resolve();
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
