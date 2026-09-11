export interface DeferredDisposer<T extends object> {
  acquire(value: T): () => void;
}

/**
 * Defers zero-lease disposal by one microtask. React Strict Mode can therefore
 * run setup → cleanup → setup without destroying the same client between its
 * two development probes, while a genuinely replaced client is still closed
 * immediately after the commit.
 */
export function createDeferredDisposer<T extends object>(
  dispose: (value: T) => void,
  schedule: (task: () => void) => void = queueMicrotask,
): DeferredDisposer<T> {
  const leases = new Map<T, number>();
  return {
    acquire(value) {
      leases.set(value, (leases.get(value) ?? 0) + 1);
      let released = false;
      return () => {
        if (released) return;
        released = true;
        const remaining = Math.max(0, (leases.get(value) ?? 1) - 1);
        leases.set(value, remaining);
        if (remaining !== 0) return;
        schedule(() => {
          if (leases.get(value) !== 0) return;
          leases.delete(value);
          dispose(value);
        });
      };
    },
  };
}
