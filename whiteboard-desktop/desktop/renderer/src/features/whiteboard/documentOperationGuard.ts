let activeOwner: symbol | null = null;
const pendingOperations = new Set<Promise<void>>();
let closeBarrierRequestId: number | null = null;
let closeBarrierReleased: Promise<void> | null = null;
let resolveCloseBarrier: (() => void) | null = null;
let interactionLockCount = 0;
let bodyInertBeforeInteractionLock = false;

export class DocumentCloseInProgressError extends Error {
  constructor() {
    super('The window is closing; wait for the close attempt to finish.');
    this.name = 'DocumentCloseInProgressError';
  }
}

/** Claim lifecycle ownership as soon as a hook renders, invalidating retirees. */
export function createDocumentOperationOwner(): symbol {
  const owner = Symbol('whiteboard-document-owner');
  activeOwner = owner;
  return owner;
}

/** React StrictMode replays effects without re-rendering; reactivate the same owner. */
export function activateDocumentOperationOwner(owner: symbol): void {
  activeOwner = owner;
}

export function releaseDocumentOperationOwner(owner: symbol): void {
  if (activeOwner === owner) activeOwner = null;
}

export function isActiveDocumentOperationOwner(owner: symbol): boolean {
  return activeOwner === owner;
}

/**
 * Register a navigation/create/delete operation so a replacement hook waits for
 * its backend side effects before loading a coherent current document.
 */
export function beginTrackedDocumentOperation(): () => void {
  let finish!: () => void;
  let finished = false;
  const pending = new Promise<void>((resolve) => { finish = resolve; });
  pendingOperations.add(pending);
  return () => {
    if (finished) return;
    finished = true;
    pendingOperations.delete(pending);
    finish();
  };
}

/**
 * Serialize navigation/import/export transactions. The barrier check and the
 * registration of the returned operation happen in one JS turn, so a close
 * request cannot slip between them.
 */
export async function acquireTrackedDocumentOperation(
  options: { waitForCloseBarrier?: boolean } = {},
): Promise<() => void> {
  while (true) {
    if (closeBarrierRequestId !== null) {
      if (!options.waitForCloseBarrier) throw new DocumentCloseInProgressError();
      const released = closeBarrierReleased;
      if (released) await released;
      continue;
    }
    if (pendingOperations.size === 0) return beginTrackedDocumentOperation();
    await Promise.allSettled([...pendingOperations]);
  }
}

export async function waitForTrackedDocumentOperations(): Promise<void> {
  while (pendingOperations.size) await Promise.allSettled([...pendingOperations]);
}

/** Block new document transactions while main decides whether to close/reload. */
export function beginDocumentCloseBarrier(requestId: number): boolean {
  if (!Number.isSafeInteger(requestId) || requestId < 1 || closeBarrierRequestId !== null) {
    return false;
  }
  closeBarrierRequestId = requestId;
  closeBarrierReleased = new Promise<void>((resolve) => {
    resolveCloseBarrier = resolve;
  });
  return true;
}

/** Only the matching, correlated main-process attempt may reopen the editor. */
export function releaseDocumentCloseBarrier(requestId: number): boolean {
  if (closeBarrierRequestId !== requestId) return false;
  closeBarrierRequestId = null;
  const resolve = resolveCloseBarrier;
  resolveCloseBarrier = null;
  closeBarrierReleased = null;
  resolve?.();
  return true;
}

export function isDocumentCloseBarrierActive(): boolean {
  return closeBarrierRequestId !== null;
}

/**
 * Work already inside a tracked operation may finish after the barrier starts;
 * fresh direct/autosave mutations are rejected once those operations drain.
 */
export function canStartDocumentMutationDuringClose(): boolean {
  return closeBarrierRequestId === null || pendingOperations.size > 0;
}

/** Freeze root content and body-level modal portals for an atomic UI transaction. */
export function lockDocumentInteraction(): () => void {
  let released = false;
  if (typeof document !== 'undefined') {
    if (interactionLockCount === 0) bodyInertBeforeInteractionLock = document.body.inert;
    interactionLockCount += 1;
    document.body.inert = true;
  }
  return () => {
    if (released) return;
    released = true;
    if (typeof document === 'undefined' || interactionLockCount === 0) return;
    interactionLockCount -= 1;
    if (interactionLockCount === 0) document.body.inert = bodyInertBeforeInteractionLock;
  };
}

export function isDocumentInteractionLocked(): boolean {
  return interactionLockCount > 0;
}
