/** Track main-process operations whose lifetime must outlive their renderer. */
export class PendingOperationTracker {
  private readonly pending = new Set<Promise<unknown>>();

  track<T>(operation: Promise<T>): Promise<T> {
    let tracked!: Promise<T>;
    tracked = operation.finally(() => {
      this.pending.delete(tracked);
    });
    this.pending.add(tracked);
    return tracked;
  }

  /** Wait for the current set and any operations registered while it settles. */
  async drain(): Promise<void> {
    while (this.pending.size > 0) {
      await Promise.allSettled([...this.pending]);
    }
  }

  get size(): number {
    return this.pending.size;
  }
}
