import type { WhiteboardDocument, WhiteboardUpdate } from './types';
import { mergeWhiteboardPatch, restoreWhiteboardPatch } from './whiteboardPatch';
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
  /** Identifies this in-memory queue even if SQLite later reuses the document id. */
  queueEpoch: number;
  revision: number;
}

export interface RetainedWhiteboardPatch extends WhiteboardPatchReceipt {
  patch: WhiteboardUpdate;
}

interface SaveQueue {
  epoch: number;
  generation: number;
  revision: number;
  persistedRevision: number;
  latest: WhiteboardUpdate;
  pending: WhiteboardUpdate | null;
  running: Promise<void> | null;
  transport: WhiteboardPatchTransport | null;
}

export type WhiteboardPatchWriter = (
  documentId: string,
  patch: WhiteboardUpdate,
  revision: number,
) => Promise<unknown>;

export interface WhiteboardPatchTransport {
  write: WhiteboardPatchWriter;
  writeOnUnload?: (documentId: string, patch: WhiteboardUpdate, revision: number) => void;
}

const queues = new Map<string, SaveQueue>();
const blockedDocumentIds = new Set<string>();
let nextRevision = 0;
let nextQueueEpoch = 0;

export function queueWhiteboardPatch(
  documentId: string,
  patch: WhiteboardUpdate,
  transport?: WhiteboardPatchTransport,
): RetainedWhiteboardPatch | null {
  if (!documentId || Object.keys(patch).length === 0) return null;
  const current = queues.get(documentId);
  const queue: SaveQueue = current ?? {
    epoch: ++nextQueueEpoch,
    generation: 0,
    revision: 0,
    persistedRevision: 0,
    latest: {},
    pending: null,
    running: null,
    transport: null,
  };
  queue.revision = ++nextRevision;
  queue.latest = mergeWhiteboardPatch(queue.latest, patch);
  queue.pending = mergeWhiteboardPatch(queue.pending, patch);
  if (transport) queue.transport = transport;
  queues.set(documentId, queue);
  return {
    documentId,
    queueEpoch: queue.epoch,
    revision: queue.revision,
    patch: queue.latest,
  };
}

export function peekRetainedWhiteboardPatch(documentId: string): RetainedWhiteboardPatch | null {
  const queue = queues.get(documentId);
  if (!queue || Object.keys(queue.latest).length === 0) return null;
  return {
    documentId,
    queueEpoch: queue.epoch,
    revision: queue.revision,
    patch: queue.latest,
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
  blockedDocumentIds.delete(documentId);
}

export function waitForWhiteboardWrites(documentId: string): Promise<void> {
  return queues.get(documentId)?.running ?? Promise.resolve();
}

export function applyRetainedWhiteboardPatch(
  document: WhiteboardDocument,
  retained: RetainedWhiteboardPatch | null,
): WhiteboardDocument {
  if (!retained || retained.documentId !== document.id) return document;
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
