/**
 * The active document id, shared across the app.
 *
 * A whiteboard "document" is identified by its id (the core project id). Every
 * doc-scoped backend route takes an optional `?doc=<id>`; `withDoc()` appends the
 * active id to a URL so the API clients stay one-liners and the hooks don't have
 * to thread the id through every call.
 *
 * Switching is race-free: `flushPendingDocSaves()` drains every registered
 * autosave store plus immediate doc-scoped writes (comments, PSYKE, title/mode)
 * BEFORE the id changes, so old-document work cannot land on the new one.
 */

import { useSyncExternalStore } from 'react';

import { canStartDocumentMutationDuringClose } from '../features/whiteboard/documentOperationGuard';

let currentDocId = '';
let currentDocIncarnation = '';
const subs = new Set<() => void>();
const flushers = new Set<() => Promise<void>>();
const discarders = new Set<() => void>();
const pendingWrites = new Set<Promise<unknown>>();
const serializedWriteTails = new Map<string, Promise<unknown>>();
const blockedMutationDocumentIds = new Set<string>();
let pendingRevision = 0;

/** One or more doc-scoped stores could not persist their pending state. */
export class PendingDocumentSaveError extends Error {
  readonly errors: unknown[];

  constructor(errors: unknown[]) {
    const details = [...new Set(errors.map((error) =>
      error instanceof Error ? error.message : String(error),
    ).filter(Boolean))].join('; ');
    super(`Could not save all pending document changes.${details ? ` ${details}` : ''}`);
    this.name = 'PendingDocumentSaveError';
    this.errors = errors;
  }
}

export function getCurrentDocId(): string {
  return currentDocId;
}

/** Opaque backend generation for the active numeric document id. */
export function getCurrentDocIncarnation(): string {
  return currentDocIncarnation;
}

/**
 * Capture the active document generation together with its id. Mutation callers
 * keep this value from scheduling through transport, so SQLite id reuse can
 * never retarget an old delayed request into a new project incarnation.
 */
export function captureDocumentIncarnation(documentId: string = currentDocId): string {
  return documentId === currentDocId ? currentDocIncarnation : '';
}

export interface CapturedDocumentIdentity {
  documentId: string;
  incarnation: string;
}

export function captureDocumentIdentity(
  documentId: string = currentDocId,
): CapturedDocumentIdentity {
  return {
    documentId,
    incarnation: captureDocumentIncarnation(documentId),
  };
}

export function setCurrentDocumentIdentity(id: string, incarnation: string): void {
  const normalizedIncarnation = typeof incarnation === 'string' ? incarnation : '';
  if (id === currentDocId && normalizedIncarnation === currentDocIncarnation) return;
  currentDocId = id;
  currentDocIncarnation = normalizedIncarnation;
  subs.forEach((s) => s());
}

export function setCurrentDocId(id: string): void {
  setCurrentDocumentIdentity(id, '');
}

export function subscribeCurrentDoc(cb: () => void): () => void {
  subs.add(cb);
  return () => {
    subs.delete(cb);
  };
}

export function useCurrentDocId(): string {
  return useSyncExternalStore(subscribeCurrentDoc, getCurrentDocId, getCurrentDocId);
}

/** Append `?doc=<active id>` (or `&doc=`) to a URL, scoping it to the active doc. */
export function withDoc(url: string): string {
  if (!currentDocId) return url;
  return `${url}${url.includes('?') ? '&' : '?'}doc=${encodeURIComponent(currentDocId)}`;
}

/** Hooks with a debounced save register a flush so a switch can drain it first. */
export function registerDocFlusher(fn: () => Promise<void>): () => void {
  flushers.add(fn);
  pendingRevision += 1; // make an active handoff notice a newly-mounted store
  return () => {
    flushers.delete(fn);
  };
}

/** Mark a debounced store dirty so an active handoff performs another pass. */
export function markPendingDocSave(): void {
  pendingRevision += 1;
}

/** Register cleanup for state that belongs to a document after it is deleted. */
export function registerDocDiscarder(fn: () => void): () => void {
  discarders.add(fn);
  return () => {
    discarders.delete(fn);
  };
}

/**
 * Track an immediate doc-scoped mutation (comments, PSYKE, title/mode, …) so a
 * document handoff waits for it just like it waits for debounced stores.
 */
export function trackPendingDocWrite<T>(write: Promise<T>): Promise<T> {
  pendingWrites.add(write);
  pendingRevision += 1;
  void write.then(
    () => pendingWrites.delete(write),
    () => pendingWrites.delete(write),
  );
  return write;
}

export class DocumentMutationBlockedError extends Error {
  constructor(documentId: string) {
    super(`Document ${documentId} is being deleted; the change was not sent.`);
    this.name = 'DocumentMutationBlockedError';
  }
}

export class DocumentCloseMutationBlockedError extends Error {
  constructor() {
    super('The window is closing; the change was not started.');
    this.name = 'DocumentCloseMutationBlockedError';
  }
}

/**
 * Check the deletion tombstone before invoking a direct mutation transport.
 * The factory is called synchronously after the check, so no browser event can
 * start DELETE between authorization and request creation.
 */
export function runPendingDocWrite<T>(
  write: () => Promise<T>,
  documentId: string = getCurrentDocId(),
): Promise<T> {
  if (!documentId || blockedMutationDocumentIds.has(documentId)) {
    return Promise.reject(new DocumentMutationBlockedError(documentId || 'unknown'));
  }
  if (!canStartDocumentMutationDuringClose()) {
    return Promise.reject(new DocumentCloseMutationBlockedError());
  }
  return trackPendingDocWrite(write());
}

/**
 * Track and serialize last-action-wins mutations for one logical resource.
 * The whole queued promise participates in handoff/close draining, and the
 * deletion/close guards are checked again immediately before transport.
 */
export function runSerializedPendingDocWrite<T>(
  resourceKey: string,
  write: () => Promise<T>,
  documentId: string = getCurrentDocId(),
): Promise<T> {
  if (!documentId || blockedMutationDocumentIds.has(documentId)) {
    return Promise.reject(new DocumentMutationBlockedError(documentId || 'unknown'));
  }
  if (!canStartDocumentMutationDuringClose()) {
    return Promise.reject(new DocumentCloseMutationBlockedError());
  }
  const key = `${documentId}:${resourceKey}`;
  const previous = serializedWriteTails.get(key) ?? Promise.resolve();
  const task = previous.catch(() => {}).then(() => {
    if (blockedMutationDocumentIds.has(documentId)) {
      throw new DocumentMutationBlockedError(documentId);
    }
    if (!canStartDocumentMutationDuringClose()) {
      throw new DocumentCloseMutationBlockedError();
    }
    return write();
  });
  serializedWriteTails.set(key, task);
  const cleanup = () => {
    if (serializedWriteTails.get(key) === task) serializedWriteTails.delete(key);
  };
  void task.then(cleanup, cleanup);
  return trackPendingDocWrite(task);
}

export function blockDocumentMutations(documentId: string): void {
  if (documentId) blockedMutationDocumentIds.add(documentId);
}

export function resumeDocumentMutations(documentId: string): void {
  blockedMutationDocumentIds.delete(documentId);
}

export function discardDocumentMutations(documentId: string): void {
  blockedMutationDocumentIds.delete(documentId);
}

/** Same-document remounts wait only for direct mutations, not failed outboxes. */
export async function waitForPendingDocWrites(): Promise<void> {
  while (pendingWrites.size) await Promise.allSettled([...pendingWrites]);
}

export async function flushPendingDocSaves(): Promise<void> {
  // Wait for every store even if one fails: manuscript and outline are separate
  // writes, and abandoning the second one after the first rejection would make
  // a retry/switch race much harder to reason about.
  const errors: unknown[] = [];
  const collect = (results: PromiseSettledResult<unknown>[]): void => {
    for (const result of results) {
      if (result.status === 'rejected') errors.push(result.reason);
    }
  };

  while (true) {
    const passRevision = pendingRevision;
    collect(
      await Promise.allSettled([
        ...[...flushers].map((flush) => Promise.resolve().then(flush)),
        ...pendingWrites,
      ]),
    );
    if (errors.length) break;
    if (pendingRevision === passRevision && pendingWrites.size === 0) break;
  }
  if (errors.length) throw new PendingDocumentSaveError(errors);
}

/**
 * Prepare a target document while the current id remains active, then drain a
 * second time. The second pass captures edits made during the asynchronous
 * prepare/load request; callers can commit the new id immediately afterwards.
 */
export async function prepareDocumentHandoff<T>(prepare: () => Promise<T>): Promise<T> {
  await flushPendingDocSaves();
  const target = await prepare();
  await flushPendingDocSaves();
  return target;
}

/** Forget queued state after the user has explicitly deleted the active doc. */
export function discardPendingDocSaves(): void {
  pendingRevision += 1;
  pendingWrites.clear();
  blockedMutationDocumentIds.delete(currentDocId);
  discarders.forEach((discard) => {
    try {
      discard();
    } catch {
      /* one store must not prevent the others from being cleared */
    }
  });
}

// -- orderly page-teardown recovery -------------------------------------------
// The debounced autosave may not have fired when a pagehide event accompanies a
// close/reload, so a hook with pending edits synchronously copies its latest
// snapshot to main. A hard renderer-process crash cannot emit pagehide and is
// intentionally outside this graceful-teardown guarantee.
const unloadFlushers = new Set<() => void>();

export function registerUnloadFlush(fn: () => void): () => void {
  unloadFlushers.add(fn);
  return () => {
    unloadFlushers.delete(fn);
  };
}

export function flushPendingDocSavesForUnload(): void {
  unloadFlushers.forEach((flush) => {
    try {
      flush();
    } catch {
      /* never block unload */
    }
  });
}

if (typeof window !== 'undefined') {
  window.addEventListener('pagehide', flushPendingDocSavesForUnload);
}
