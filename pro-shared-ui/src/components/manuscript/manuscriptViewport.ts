export const WARM_SCENE_LIMIT = 6;
export const SCENE_FOCUS_RETRY_DELAY_MS = 40;
export const SCENE_FOCUS_RETRY_ATTEMPTS = 100;

export interface SceneFocusRetryOptions {
  shouldContinue: () => boolean;
  tryFocus: () => boolean;
  isFocusStable: () => boolean;
  schedule: (callback: () => void, delayMs: number) => number;
  cancel: (handle: number) => void;
  delayMs?: number;
  maxAttempts?: number;
}

/**
 * Keep a requested scene focus alive while its asynchronously-created editor
 * mounts and confirm that focus survives a later tick. A newer navigation or
 * unmount cancels the returned request.
 */
export function startSceneFocusRetry({
  shouldContinue,
  tryFocus,
  isFocusStable,
  schedule,
  cancel,
  delayMs = SCENE_FOCUS_RETRY_DELAY_MS,
  maxAttempts = SCENE_FOCUS_RETRY_ATTEMPTS,
}: SceneFocusRetryOptions): () => void {
  const boundedDelay = Number.isFinite(delayMs)
    ? Math.max(0, Math.floor(delayMs))
    : SCENE_FOCUS_RETRY_DELAY_MS;
  const boundedAttempts = Number.isFinite(maxAttempts)
    ? Math.max(1, Math.floor(maxAttempts))
    : SCENE_FOCUS_RETRY_ATTEMPTS;
  let cancelled = false;
  let attempts = 0;
  let handle: number | null = null;
  let confirming = false;

  const run = () => {
    handle = null;
    if (cancelled || !shouldContinue()) {
      cancelled = true;
      return;
    }
    if (confirming) {
      confirming = false;
      if (isFocusStable()) {
        cancelled = true;
        return;
      }
      if (attempts >= boundedAttempts) {
        cancelled = true;
        return;
      }
    }
    attempts += 1;
    if (tryFocus()) {
      // Modal teardown and dock commits can reclaim focus after a synchronous
      // focus() succeeds. Confirm ownership on a later tick before settling.
      confirming = true;
      handle = schedule(run, boundedDelay);
      return;
    }
    if (attempts >= boundedAttempts) {
      cancelled = true;
      return;
    }
    handle = schedule(run, boundedDelay);
  };

  handle = schedule(run, boundedDelay);
  return () => {
    cancelled = true;
    if (handle != null) {
      cancel(handle);
      handle = null;
    }
  };
}

/** Most-recently-used scene ids whose editor history should stay mounted. */
export function touchWarmSceneIds(current: number[], id: number, limit = WARM_SCENE_LIMIT): number[] {
  const size = Math.max(0, Math.floor(limit));
  if (size === 0) return [];
  const next = [id, ...current.filter((candidate) => candidate !== id)].slice(0, size);
  return next.length === current.length && next.every((value, index) => value === current[index])
    ? current
    : next;
}

export function pruneSceneIds(current: number[], validIds: ReadonlySet<number>): number[] {
  const next = current.filter((id) => validIds.has(id));
  return next.length === current.length ? current : next;
}

export function pruneSceneRecord<T>(current: Record<number, T>, validIds: ReadonlySet<number>): Record<number, T> {
  const entries = Object.entries(current).filter(([id]) => validIds.has(Number(id)));
  return entries.length === Object.keys(current).length
    ? current
    : Object.fromEntries(entries) as Record<number, T>;
}
