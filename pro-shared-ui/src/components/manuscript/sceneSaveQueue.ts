/** Pure serialized latest-snapshot save queue used by each Pro scene editor. */

export type SceneQueueStatus = 'dirty' | 'saving' | 'saved' | 'error';

export interface SceneSaveQueue<T> {
  update(value: T): void;
  reset(value: T): void;
  flush(): Promise<boolean>;
  cancel(): void;
  isDirty(): boolean;
}

export function createSceneSaveQueue<T>({
  initial,
  write,
  onStatus,
  onDirty,
}: {
  initial: T;
  write: (value: T) => Promise<void>;
  onStatus: (status: SceneQueueStatus) => void;
  onDirty: () => void;
}): SceneSaveQueue<T> {
  let latest = initial;
  let revision = 0;
  let savedRevision = 0;
  let cancelled = false;
  let inFlight: Promise<boolean> | null = null;

  const flush = (): Promise<boolean> => {
    if (cancelled) return Promise.resolve(true);
    if (inFlight) return inFlight;
    const run = async (): Promise<boolean> => {
      while (!cancelled && savedRevision < revision) {
        const targetRevision = revision;
        const snapshot = latest;
        onStatus('saving');
        try {
          await write(snapshot);
        } catch {
          if (cancelled) return true;
          onStatus('error');
          return false;
        }
        savedRevision = targetRevision;
      }
      if (!cancelled && savedRevision === revision) onStatus('saved');
      return cancelled || savedRevision === revision;
    };
    const tracked = run().finally(() => {
      if (inFlight === tracked) inFlight = null;
    });
    inFlight = tracked;
    return tracked;
  };

  return {
    update(value) {
      if (cancelled) return;
      latest = value;
      revision += 1;
      onDirty();
      onStatus('dirty');
    },
    reset(value) {
      if (cancelled) return;
      latest = value;
      revision = 0;
      savedRevision = 0;
    },
    flush,
    cancel() {
      cancelled = true;
      savedRevision = revision;
    },
    isDirty: () => !cancelled && savedRevision < revision,
  };
}
