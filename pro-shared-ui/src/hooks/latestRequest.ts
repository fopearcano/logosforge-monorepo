/** Pure keyed generation gate: only the newest async request may publish data. */

export interface RequestToken {
  key: string;
  revision: number;
  epoch: number;
}

export interface LatestRequestGate {
  open(): void;
  begin(key?: string): RequestToken;
  isCurrent(token: RequestToken): boolean;
  invalidate(key?: string): void;
  close(): void;
}

export function createLatestRequestGate(): LatestRequestGate {
  const revisions = new Map<string, number>();
  let closed = false;
  let epoch = 0;
  const next = (key: string) => {
    const revision = (revisions.get(key) ?? 0) + 1;
    revisions.set(key, revision);
    return revision;
  };
  return {
    open() {
      closed = false;
    },
    begin(key = "default") {
      return { key, revision: next(key), epoch: closed ? -1 : epoch };
    },
    isCurrent(token) {
      return !closed && token.epoch === epoch && revisions.get(token.key) === token.revision;
    },
    invalidate(key = "default") {
      next(key);
    },
    close() {
      closed = true;
      epoch += 1;
      // Preserve monotonically increasing per-key revisions. React StrictMode may
      // immediately re-open this instance; the mount epoch keeps every prior
      // response invalid even if no replacement request for its key is started.
    },
  };
}
