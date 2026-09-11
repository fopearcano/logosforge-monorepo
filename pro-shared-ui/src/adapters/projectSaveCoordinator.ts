/** Global barrier for local Pro editor state before panel/project handoffs. */

export type ProjectFlusher = () => Promise<boolean>;

const flushers = new Set<ProjectFlusher>();
const pendingWrites = new Set<Promise<unknown>>();
let revision = 0;

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

export function markProjectSavePending(): void {
  revision += 1;
}

/** Keep an in-flight write visible even if its editor unmounts. */
export function trackProjectWrite<T>(write: Promise<T>): Promise<T> {
  pendingWrites.add(write);
  revision += 1;
  void write.then(
    () => pendingWrites.delete(write),
    () => pendingWrites.delete(write),
  );
  return write;
}

export interface FlushProjectSaveOptions {
  /** Commit inline editors whose existing contract is save-on-blur. */
  commitActiveField?: boolean;
  /**
   * Skip the flusher that initiated this nested drain. This lets an editor
   * flush its peers before a compound write without waiting on itself.
   */
  excludeFlusher?: ProjectFlusher;
}

export async function flushPendingProjectSaves(
  options: FlushProjectSaveOptions = {},
): Promise<void> {
  if (options.commitActiveField && typeof document !== 'undefined' && typeof HTMLElement !== 'undefined') {
    const active = document.activeElement;
    if (active instanceof HTMLElement && active.matches('input, textarea, select')) {
      active.blur();
      // Let synchronous framework event handlers enqueue their tracked write.
      await Promise.resolve();
    }
  }
  const errors: unknown[] = [];
  while (true) {
    const passRevision = revision;
    const tasks: Promise<unknown>[] = [
      ...[...flushers].filter((flush) => flush !== options.excludeFlusher).map((flush) =>
        Promise.resolve()
          .then(flush)
          .then((saved) => {
            if (!saved) throw new Error('An editor still has unsaved changes.');
          }),
      ),
      ...pendingWrites,
    ];
    const results = await Promise.allSettled(tasks);
    for (const result of results) {
      if (result.status === 'rejected') errors.push(result.reason);
    }
    if (errors.length) break;
    if (revision === passRevision && pendingWrites.size === 0) break;
  }
  if (errors.length) throw new PendingProjectSaveError(errors);
}

/** Capture edits made while an asynchronous new-project/import operation runs. */
export async function prepareProjectHandoff<T>(prepare: () => Promise<T>): Promise<T> {
  await flushPendingProjectSaves({ commitActiveField: true });
  const target = await prepare();
  await flushPendingProjectSaves({ commitActiveField: true });
  return target;
}
