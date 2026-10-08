/** Global barrier for local Pro editor state before panel/project handoffs. */

import {
  getPanelHostDocuments,
  isPanelHostHTMLElement,
} from "../components/common/panelHostDocuments";

export type ProjectFlusher = () => Promise<boolean>;

/** Observable, process-local persistence state for the active Pro workspace. */
export interface ProjectSaveStatusSnapshot {
  /** Monotonic revision of the newest edit or tracked mutation. */
  readonly dirtyRevision: number;
  /** Newest revision known to have completed successfully. */
  readonly savedRevision: number;
  /** True while any revision or failed save still needs a successful retry. */
  readonly dirty: boolean;
  /** Mutating API promises currently visible to the project handoff barrier. */
  readonly inFlightCount: number;
  /** True while one or more callers are draining the handoff barrier. */
  readonly flushing: boolean;
  /** Completion time of the most recent successful write or non-empty drain. */
  readonly lastSavedAt: number | null;
  /** Most recent failure, retained until the same save owner retries successfully. */
  readonly lastError: Error | null;
}

export type ProjectSaveStatusListener = (snapshot: ProjectSaveStatusSnapshot) => void;

const flushers = new Set<ProjectFlusher>();
interface PendingWrite {
  revision: number;
  saveKey?: string;
}

interface PendingOperation {
  ownerFlusher?: ProjectFlusher;
  /** The operation persists data, but has no recoverable local draft owner. */
  persistence: boolean;
}

interface FlushTask {
  promise: Promise<unknown>;
  /** Present only for a write captured directly from pendingWrites. */
  write?: PendingWrite;
}

interface FailureRecord {
  error: Error;
  sequence: number;
  revision: number;
}

const pendingWrites = new Map<Promise<unknown>, PendingWrite>();
const pendingOperations = new Map<Promise<unknown>, PendingOperation>();
const statusListeners = new Set<ProjectSaveStatusListener>();
const unresolvedRevisions = new Set<number>();
const pendingEditRevisions = new Set<number>();
const saveKeyByRevision = new Map<number, string>();
const revisionsBySaveKey = new Map<string, Set<number>>();
const failures = new Map<string, FailureRecord>();
let revision = 0;
let dirtyRevision = 0;
let savedRevision = 0;
let flushDepth = 0;
let lastSavedAt: number | null = null;
let failureSequence = 0;

const asError = (error: unknown): Error =>
  error instanceof Error ? error : new Error(String(error));

const normalizeSaveKey = (value: string | undefined): string | undefined => {
  const key = value?.trim();
  return key ? key : undefined;
};

const latestFailure = (): Error | null => {
  let latest: FailureRecord | undefined;
  for (const record of failures.values()) {
    if (!latest || record.sequence > latest.sequence) latest = record;
  }
  return latest?.error ?? null;
};

const pendingPersistenceCount = (): number => {
  let count = pendingWrites.size;
  for (const operation of pendingOperations.values()) {
    if (operation.persistence) count += 1;
  }
  return count;
};

const createStatusSnapshot = (): ProjectSaveStatusSnapshot => Object.freeze({
  dirtyRevision,
  savedRevision,
  dirty: unresolvedRevisions.size > 0 || failures.size > 0,
  inFlightCount: pendingPersistenceCount(),
  flushing: flushDepth > 0,
  lastSavedAt,
  lastError: latestFailure(),
});

let statusSnapshot = createStatusSnapshot();

function publishStatus(): void {
  statusSnapshot = createStatusSnapshot();
  for (const listener of [...statusListeners]) {
    try { listener(statusSnapshot); } catch { /* observers cannot break persistence */ }
  }
}

function advanceSavedRevision(): void {
  while (savedRevision < dirtyRevision && !unresolvedRevisions.has(savedRevision + 1)) {
    savedRevision += 1;
  }
}

function associateRevisionWithSaveKey(targetRevision: number, rawSaveKey: string | undefined): void {
  const saveKey = normalizeSaveKey(rawSaveKey);
  const previous = saveKeyByRevision.get(targetRevision);
  if (previous === saveKey) return;
  if (previous) {
    const previousRevisions = revisionsBySaveKey.get(previous);
    previousRevisions?.delete(targetRevision);
    if (previousRevisions?.size === 0) revisionsBySaveKey.delete(previous);
  }
  if (!saveKey) {
    saveKeyByRevision.delete(targetRevision);
    return;
  }
  saveKeyByRevision.set(targetRevision, saveKey);
  const revisions = revisionsBySaveKey.get(saveKey) ?? new Set<number>();
  revisions.add(targetRevision);
  revisionsBySaveKey.set(saveKey, revisions);
}

function allocateDirtyRevision(saveKey?: string, pendingEdit = false): number {
  const normalizedSaveKey = normalizeSaveKey(saveKey);
  dirtyRevision += 1;
  const targetRevision = dirtyRevision;
  unresolvedRevisions.add(targetRevision);
  // Only legacy unkeyed fields need a successful all-editor pass as proof.
  // Keyed drafts may be resolved only by their own write or explicit discard.
  if (pendingEdit && !normalizedSaveKey) pendingEditRevisions.add(targetRevision);
  associateRevisionWithSaveKey(targetRevision, normalizedSaveKey);
  return targetRevision;
}

function resolveRevision(targetRevision: number): void {
  unresolvedRevisions.delete(targetRevision);
  pendingEditRevisions.delete(targetRevision);
  associateRevisionWithSaveKey(targetRevision, undefined);
  advanceSavedRevision();
}

function resolveSaveKey(rawSaveKey: string, throughRevision: number): void {
  const saveKey = normalizeSaveKey(rawSaveKey);
  if (!saveKey) return;
  const targets = [...(revisionsBySaveKey.get(saveKey) ?? [])]
    .filter((targetRevision) => targetRevision <= throughRevision);
  for (const targetRevision of targets) resolveRevision(targetRevision);
  const failureId = `save:${saveKey}`;
  const failure = failures.get(failureId);
  if (failure && failure.revision <= throughRevision) failures.delete(failureId);
}

function recordFailure(id: string, error: unknown, targetRevision: number): void {
  failures.set(id, {
    error: asError(error),
    sequence: ++failureSequence,
    revision: targetRevision,
  });
}

function recordSuccessfulWrite(target: PendingWrite): void {
  // A newer success or an explicit discard may already have resolved this
  // owner. Its stale completion must not manufacture a fresh save timestamp.
  if (!unresolvedRevisions.has(target.revision)) {
    publishStatus();
    return;
  }
  if (target.saveKey) resolveSaveKey(target.saveKey, target.revision);
  else resolveRevision(target.revision);
  lastSavedAt = Date.now();
  publishStatus();
}

/** Read the current snapshot without subscribing. The object is immutable. */
export function getProjectSaveStatusSnapshot(): ProjectSaveStatusSnapshot {
  return statusSnapshot;
}

/** Subscribe to future snapshot changes. Read the initial value with the getter. */
export function subscribeProjectSaveStatus(listener: ProjectSaveStatusListener): () => void {
  statusListeners.add(listener);
  return () => statusListeners.delete(listener);
}

/** Start a fresh active-project status after its previous project drained. */
export function resetProjectSaveStatus(): void {
  if (pendingWrites.size > 0 || pendingOperations.size > 0 || flushDepth > 0
    || unresolvedRevisions.size > 0 || failures.size > 0) {
    throw new Error("Cannot reset project save status before the active project is fully drained.");
  }
  revision += 1;
  dirtyRevision = 0;
  savedRevision = 0;
  lastSavedAt = null;
  unresolvedRevisions.clear();
  pendingEditRevisions.clear();
  saveKeyByRevision.clear();
  revisionsBySaveKey.clear();
  failures.clear();
  publishStatus();
}

export class PendingProjectSaveError extends Error {
  readonly errors: unknown[];

  constructor(errors: unknown[]) {
    const details = [...new Set(errors.map((error) =>
      error instanceof Error ? error.message : String(error),
    ).filter(Boolean))].join('; ');
    super(`Could not save all pending project changes.${details ? ` ${details}` : ''}`);
    this.name = 'PendingProjectSaveError';
    this.errors = errors;
  }
}

export function registerProjectFlusher(flusher: ProjectFlusher): () => void {
  flushers.add(flusher);
  revision += 1;
  return () => flushers.delete(flusher);
}

export function markProjectSavePending(saveKey?: string): void {
  revision += 1;
  allocateDirtyRevision(saveKey, true);
  publishStatus();
}

/** Explicitly abandon a keyed local draft (Cancel/Revert) without claiming it was saved. */
export function discardProjectSavePending(saveKey: string): void {
  const normalized = normalizeSaveKey(saveKey);
  if (!normalized) return;
  resolveSaveKey(normalized, Number.MAX_SAFE_INTEGER);
  publishStatus();
}

export interface TrackProjectWriteOptions {
  /** Stable logical owner. Only a success for this owner may clear its failure. */
  saveKey?: string;
}

/** Keep an in-flight write visible even if its editor unmounts. */
export function trackProjectWrite<T>(write: Promise<T>, options: TrackProjectWriteOptions = {}): Promise<T> {
  // The HTTP adapter registers mutations as ownerless barriers. A draft owner
  // can upgrade that exact promise here without inflating counts or revisions.
  pendingOperations.delete(write);
  const existing = pendingWrites.get(write);
  if (existing) {
    const saveKey = normalizeSaveKey(options.saveKey);
    if (saveKey && saveKey !== existing.saveKey) {
      existing.saveKey = saveKey;
      associateRevisionWithSaveKey(existing.revision, saveKey);
      publishStatus();
    }
    return write;
  }
  revision += 1;
  const target: PendingWrite = {
    revision: allocateDirtyRevision(options.saveKey),
    saveKey: normalizeSaveKey(options.saveKey),
  };
  pendingWrites.set(write, target);
  publishStatus();
  void write.then(
    () => {
      pendingWrites.delete(write);
      recordSuccessfulWrite(target);
    },
    (error) => {
      pendingWrites.delete(write);
      if (unresolvedRevisions.has(target.revision)) {
        if (target.saveKey) {
          recordFailure(`save:${target.saveKey}`, error, target.revision);
        } else {
          // With no stable owner there is no local draft that can be retried or
          // discarded. A drain already awaiting this promise still receives the
          // rejection, but later handoffs must not be poisoned permanently.
          resolveRevision(target.revision);
        }
      }
      publishStatus();
    },
  );
  return write;
}

/** Keep a non-persistence operation in the handoff barrier without claiming unsaved data. */
export function trackProjectOperation<T>(
  operation: Promise<T>,
  options: { ownerFlusher?: ProjectFlusher; persistence?: boolean } = {},
): Promise<T> {
  if (pendingWrites.has(operation)) return operation;
  const existing = pendingOperations.get(operation);
  if (existing) {
    if (options.ownerFlusher) existing.ownerFlusher = options.ownerFlusher;
    if (options.persistence) existing.persistence = true;
    publishStatus();
    return operation;
  }
  const pending: PendingOperation = {
    ownerFlusher: options.ownerFlusher,
    persistence: options.persistence === true,
  };
  pendingOperations.set(operation, pending);
  revision += 1;
  publishStatus();
  void operation.then(
    () => {
      if (pendingOperations.get(operation) !== pending) return;
      pendingOperations.delete(operation);
      if (pending.persistence) lastSavedAt = Date.now();
      publishStatus();
    },
    () => {
      if (pendingOperations.get(operation) !== pending) return;
      pendingOperations.delete(operation);
      publishStatus();
    },
  );
  return operation;
}

export interface FlushProjectSaveOptions {
  /** Commit inline editors whose existing contract is save-on-blur. */
  commitActiveField?: boolean;
  /**
   * Skip the flusher that initiated this nested drain. This lets an editor
   * flush its peers before a compound write without waiting on itself.
   */
  excludeFlusher?: ProjectFlusher;
  /**
   * Let one failed owner reach its retry write after peer editors drain. The
   * failure and dirty revisions remain intact until that owner's write succeeds.
   */
  retrySaveKey?: string;
}

export async function flushPendingProjectSaves(
  options: FlushProjectSaveOptions = {},
): Promise<void> {
  const retrySaveKey = normalizeSaveKey(options.retrySaveKey);
  const retryFailureId = retrySaveKey ? `save:${retrySaveKey}` : undefined;
  let invokedFlushers = 0;
  flushDepth += 1;
  publishStatus();
  try {
    if (options.commitActiveField) {
      let blurredActiveField = false;
      for (const ownerDocument of getPanelHostDocuments()) {
        const active = ownerDocument.activeElement;
        if (isPanelHostHTMLElement(active, ownerDocument) && active.matches('input, textarea, select')) {
          active.blur();
          blurredActiveField = true;
        }
      }
      if (blurredActiveField) {
        // Let synchronous framework event handlers enqueue their tracked write.
        await Promise.resolve();
      }
    }
    const errors: unknown[] = [];
    while (true) {
      const passRevision = revision;
      const activeFlushers = [...flushers].filter((flush) => flush !== options.excludeFlusher);
      const activeOperations = [...pendingOperations.entries()]
        .filter(([, operation]) => options.excludeFlusher == null
          || operation.ownerFlusher !== options.excludeFlusher)
        .map(([operation]) => operation);
      invokedFlushers += activeFlushers.length;
      const tasks: FlushTask[] = [
        ...activeFlushers.map((flush) =>
          ({
            promise: Promise.resolve()
              .then(flush)
              .then((saved) => {
                if (!saved) throw new Error('An editor still has unsaved changes.');
              }),
          }),
        ),
        ...[...pendingWrites.entries()].map(([promise, write]) => ({ promise, write })),
        ...activeOperations.map((promise) => ({ promise })),
      ];
      const results = await Promise.allSettled(tasks.map((task) => task.promise));
      for (let index = 0; index < results.length; index += 1) {
        const result = results[index];
        if (result?.status !== 'rejected') continue;
        const target = tasks[index]?.write;
        // A newer success or explicit discard for the same keyed owner can
        // supersede an older rejection while this drain is already waiting.
        if (target?.saveKey && !unresolvedRevisions.has(target.revision)) continue;
        errors.push(result.reason);
      }
      if (errors.length) break;
      const hasActiveOperations = [...pendingOperations.values()]
        .some((operation) => options.excludeFlusher == null
          || operation.ownerFlusher !== options.excludeFlusher);
      if (revision === passRevision && pendingWrites.size === 0 && !hasActiveOperations) break;
    }

    const persistentErrors = [...failures.entries()]
      .filter(([id]) => id !== retryFailureId)
      .map(([, record]) => record.error);
    if (errors.length || persistentErrors.length) {
      publishStatus();
      throw new PendingProjectSaveError([...errors, ...persistentErrors]);
    }

    // A stable pass through every registered editor is the only unkeyed proof
    // that its dirty field has reached persistence. Individual write success
    // never clears another owner's pending revision.
    if (invokedFlushers > 0 && pendingEditRevisions.size > 0) {
      for (const targetRevision of [...pendingEditRevisions]) resolveRevision(targetRevision);
      lastSavedAt = Date.now();
    }
    const hasBlockingRevision = retrySaveKey == null
      ? unresolvedRevisions.size > 0
      : [...unresolvedRevisions]
        .some((targetRevision) => saveKeyByRevision.get(targetRevision) !== retrySaveKey);
    if (hasBlockingRevision) {
      throw new PendingProjectSaveError([new Error('An editor still has unsaved changes.')]);
    }
    publishStatus();
  } finally {
    flushDepth = Math.max(0, flushDepth - 1);
    publishStatus();
  }
}

/** Capture edits made while an asynchronous new-project/import operation runs. */
export async function prepareProjectHandoff<T>(prepare: () => Promise<T>): Promise<T> {
  await flushPendingProjectSaves({ commitActiveField: true });
  const target = await prepare();
  await flushPendingProjectSaves({ commitActiveField: true });
  return target;
}
