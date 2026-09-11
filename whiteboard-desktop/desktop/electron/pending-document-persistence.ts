export type PendingDocumentKind = 'whiteboard' | 'outline';

export interface PendingDocumentWrite {
  kind: PendingDocumentKind;
  documentId: string;
  /** Backend generation captured before this mutation entered a queue. */
  incarnation: string;
  /** Monotonic within one renderer session and one resource kind. */
  revision: number;
  sessionId: string;
  payload: Record<string, unknown>;
}

export interface PendingDocumentDeleteFloor {
  whiteboard: number;
  outline: number;
}

export interface PersistenceBackendStatus {
  state: 'connecting' | 'connected' | 'error';
  baseUrl: string;
  authToken?: string;
}

export interface PendingDocumentHttpRequest {
  url: string;
  method: 'PUT';
  headers: Record<string, string>;
  body: string;
}

export type PendingDocumentWriter = (
  write: PendingDocumentWrite,
  signal: AbortSignal,
  /** Main-owned total order for this resource, across renderer sessions/retries. */
  dispatchSequence: number,
) => Promise<void>;

export const MAX_PENDING_DOCUMENT_BYTES = 128 * 1024 * 1024;

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

export function validatePendingDocumentId(value: unknown): string {
  if (typeof value !== 'string' || !/^[1-9]\d*$/.test(value)) {
    throw new Error('Invalid pending-document id.');
  }
  return value;
}

export function validatePendingDocumentIncarnation(value: unknown): string {
  if (typeof value !== 'string' || !/^[a-f0-9]{32}$/i.test(value)) {
    throw new Error('Invalid pending-document incarnation.');
  }
  return value.toLowerCase();
}

/** Validate the narrow IPC contract synchronously before acknowledging unload. */
export function validatePendingDocumentWrite(value: unknown): PendingDocumentWrite {
  if (!isRecord(value)) throw new Error('Invalid pending-document payload.');
  const { kind, documentId, incarnation, revision, sessionId, payload } = value;
  if (kind !== 'whiteboard' && kind !== 'outline') {
    throw new Error('Invalid pending-document kind.');
  }
  const validatedDocumentId = validatePendingDocumentId(documentId);
  const validatedIncarnation = validatePendingDocumentIncarnation(incarnation);
  if (!Number.isSafeInteger(revision) || (revision as number) < 1) {
    throw new Error('Invalid pending-document revision.');
  }
  if (typeof sessionId !== 'string' || !/^[A-Za-z0-9_-]{8,128}$/.test(sessionId)) {
    throw new Error('Invalid pending-document session.');
  }
  if (!isRecord(payload)) throw new Error('Invalid pending-document body.');

  const keys = Object.keys(payload);
  if (kind === 'whiteboard') {
    const allowed = new Set(['title', 'mode', 'blocks', 'settings']);
    if (!keys.length || keys.some((key) => !allowed.has(key))) {
      throw new Error('Invalid whiteboard update shape.');
    }
    if ('title' in payload && typeof payload.title !== 'string') {
      throw new Error('Invalid whiteboard title.');
    }
    if ('mode' in payload && typeof payload.mode !== 'string') {
      throw new Error('Invalid whiteboard mode.');
    }
    if ('blocks' in payload && !Array.isArray(payload.blocks)) {
      throw new Error('Invalid whiteboard blocks.');
    }
    if ('settings' in payload && !isRecord(payload.settings)) {
      throw new Error('Invalid whiteboard settings.');
    }
  } else if (keys.length !== 1 || keys[0] !== 'items' || !Array.isArray(payload.items)) {
    throw new Error('Invalid outline update shape.');
  }

  let serialized: string;
  try {
    serialized = JSON.stringify(payload);
  } catch {
    throw new Error('Pending-document body is not serializable.');
  }
  if (Buffer.byteLength(serialized, 'utf8') > MAX_PENDING_DOCUMENT_BYTES) {
    throw new Error('Pending-document body exceeds the desktop safety limit.');
  }

  return {
    kind,
    documentId: validatedDocumentId,
    incarnation: validatedIncarnation,
    revision: revision as number,
    sessionId,
    payload,
  };
}

/** Construct only the two fixed loopback-backend routes; the renderer supplies no URL or auth. */
export function buildPendingDocumentHttpRequest(
  write: PendingDocumentWrite,
  status: PersistenceBackendStatus,
  dispatchSequence?: number,
): PendingDocumentHttpRequest {
  if (status.state !== 'connected' || !status.baseUrl || !status.authToken) {
    throw new Error('The Whiteboard backend is not connected.');
  }
  const route = write.kind === 'whiteboard' ? '/api/whiteboard' : '/api/outline/items';
  const url = new URL(route, status.baseUrl);
  url.searchParams.set('doc', write.documentId);
  return {
    url: url.toString(),
    method: 'PUT',
    headers: {
      Authorization: `Bearer ${status.authToken}`,
      'Content-Type': 'application/json',
      'X-LogosForge-Document-Incarnation': write.incarnation,
      ...(dispatchSequence === undefined
        ? {}
        : { 'X-LogosForge-Persistence-Order': String(dispatchSequence) }),
    },
    body: JSON.stringify(write.payload),
  };
}

/**
 * Main-process FIFO for document snapshots. Normal and teardown writes share
 * this queue, so pagehide can never overtake an older renderer save. Revisions
 * additionally discard an older IPC message if delivery is observed late.
 */
export class PendingDocumentPersistence {
  private readonly tails = new Map<string, Promise<void>>();
  private readonly pending = new Set<Promise<void>>();
  private readonly latestSeen = new Map<string, number>();
  private readonly completed = new Map<string, number>();
  private readonly failedLatest = new Map<string, PendingDocumentWrite>();
  private readonly nextDispatchSequence = new Map<string, number>();
  private readonly deletingDocumentIds = new Set<string>();
  private draining: Promise<void> | null = null;

  constructor(
    private readonly writer: PendingDocumentWriter,
    private readonly writerTimeoutMs = 10_000,
  ) {}

  private async writeWithDeadline(
    write: PendingDocumentWrite,
    dispatchSequence: number,
  ): Promise<void> {
    const controller = new AbortController();
    let timeout: ReturnType<typeof setTimeout> | undefined;
    const deadline = new Promise<never>((_resolve, reject) => {
      timeout = setTimeout(() => {
        controller.abort();
        reject(new Error(
          `Timed out persisting ${write.kind} for document ${write.documentId}.`,
        ));
      }, this.writerTimeoutMs);
    });
    try {
      await Promise.race([
        this.writer(write, controller.signal, dispatchSequence),
        deadline,
      ]);
    } finally {
      if (timeout) clearTimeout(timeout);
    }
  }

  enqueue(value: unknown): Promise<void> {
    const write = validatePendingDocumentWrite(value);
    const serialKey = `${write.kind}:${write.documentId}`;
    const dispatchSequence = (this.nextDispatchSequence.get(serialKey) ?? 0) + 1;
    this.nextDispatchSequence.set(serialKey, dispatchSequence);
    const revisionKey = `${serialKey}:${write.sessionId}`;
    this.latestSeen.set(
      revisionKey,
      Math.max(this.latestSeen.get(revisionKey) ?? 0, write.revision),
    );

    const previous = this.tails.get(serialKey) ?? Promise.resolve();
    const task = previous.catch(() => {}).then(async () => {
      const latest = this.latestSeen.get(revisionKey) ?? write.revision;
      const completed = this.completed.get(revisionKey) ?? 0;
      if (write.revision < latest || write.revision <= completed) return;
      try {
        // This check deliberately lives inside the serial task. A snapshot may
        // already be queued when DELETE begins; retaining the newest blocked
        // value lets a failed DELETE resume without losing that edit.
        if (this.deletingDocumentIds.has(write.documentId)) {
          throw new Error(`Document ${write.documentId} is being deleted.`);
        }
        await this.writeWithDeadline(write, dispatchSequence);
        this.completed.set(revisionKey, write.revision);
        this.failedLatest.delete(serialKey);
      } catch (error) {
        // The serial tail means a later write will either replace this entry or
        // clear it on success. Until then main retains the only unload copy.
        this.failedLatest.set(serialKey, write);
        throw error;
      }
    });
    this.tails.set(serialKey, task);
    this.pending.add(task);
    const cleanup = () => {
      this.pending.delete(task);
      if (this.tails.get(serialKey) === task) this.tails.delete(serialKey);
    };
    void task.then(cleanup, cleanup);
    return task;
  }

  /**
   * Phase 1 of DELETE: reject future/queued writers and settle every main-owned
   * tail before the renderer is allowed to issue the backend DELETE.
   */
  async beginDocumentDelete(value: unknown): Promise<PendingDocumentDeleteFloor> {
    const documentId = validatePendingDocumentId(value);
    this.deletingDocumentIds.add(documentId);
    const serialKeys = [`whiteboard:${documentId}`, `outline:${documentId}`];
    // Renderer-side queues are blocked before this call. Looping closes the
    // small IPC-delivery window for a snapshot that main had already received.
    while (true) {
      const active = serialKeys
        .map((serialKey) => this.tails.get(serialKey))
        .filter((tail): tail is Promise<void> => !!tail);
      if (!active.length) break;
      await Promise.allSettled(active);
    }
    return {
      whiteboard: this.nextDispatchSequence.get(`whiteboard:${documentId}`) ?? 0,
      outline: this.nextDispatchSequence.get(`outline:${documentId}`) ?? 0,
    };
  }

  /** Phase 2 success: discard retries while retaining old revision watermarks. */
  commitDocumentDelete(value: unknown): void {
    const documentId = validatePendingDocumentId(value);
    const serialKeys = [`whiteboard:${documentId}`, `outline:${documentId}`];
    for (const serialKey of serialKeys) this.failedLatest.delete(serialKey);
    for (const key of this.latestSeen.keys()) {
      if (key.startsWith(`whiteboard:${documentId}:`) || key.startsWith(`outline:${documentId}:`)) {
        // SQLite may reuse the highest deleted integer id. A delayed message
        // from the old session is suppressed; a higher revision or new session
        // still belongs to the new incarnation and is accepted.
        this.completed.set(key, this.latestSeen.get(key) ?? 0);
      }
    }
    this.deletingDocumentIds.delete(documentId);
  }

  /** Phase 2 failure: make retained snapshots eligible for a later retry. */
  cancelDocumentDelete(value: unknown): void {
    this.deletingDocumentIds.delete(validatePendingDocumentId(value));
  }

  /** Wait for active writes and retry each retained latest failure once. */
  drain(): Promise<void> {
    if (this.draining) return this.draining;
    const run = (async () => {
      while (this.pending.size) await Promise.allSettled([...this.pending]);

      const retries = [...this.failedLatest.entries()];
      for (const [key, failed] of retries) {
        if (this.failedLatest.get(key) !== failed) continue;
        this.failedLatest.delete(key);
        void this.enqueue(failed).catch(() => {});
      }
      while (this.pending.size) await Promise.allSettled([...this.pending]);

      if (this.failedLatest.size) {
        throw new AggregateError(
          [...this.failedLatest.values()].map((failed) =>
            new Error(`Could not persist ${failed.kind} for document ${failed.documentId}.`)),
          'Pending document persistence failed.',
        );
      }
    })();
    const tracked = run.finally(() => {
      if (this.draining === tracked) this.draining = null;
    });
    this.draining = tracked;
    return tracked;
  }

  get pendingCount(): number {
    return this.pending.size;
  }
}
