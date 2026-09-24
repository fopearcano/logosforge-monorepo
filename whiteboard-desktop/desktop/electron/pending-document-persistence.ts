export type PendingDocumentKind = 'whiteboard' | 'outline';

export interface PendingDocumentWrite {
  kind: PendingDocumentKind;
  documentId: string;
  /** Backend generation captured before this mutation entered a queue. */
  incarnation: string;
  /** Opaque durable validator returned by the resource's latest GET/PUT. */
  resourceRevision: string;
  /** Monotonic within one renderer session and one resource kind. */
  revision: number;
  sessionId: string;
  payload: Record<string, unknown>;
}

export interface PendingDocumentWriteSuccess {
  ok: true;
  resourceRevision: string;
}

export interface PendingDocumentWriteConflict {
  ok: false;
  code: string;
  status: number;
  message: string;
  currentRevision?: string;
  currentEtag?: string;
  recovery: PendingDocumentConflictReceipt;
}

export type PendingDocumentWriteResult =
  | PendingDocumentWriteSuccess
  | PendingDocumentWriteConflict;

export interface PendingDocumentConflictReceipt {
  conflictId: string;
  version: number;
  kind: PendingDocumentKind;
  documentId: string;
  incarnation: string;
}

export interface PendingDocumentConflictRecovery extends PendingDocumentConflictReceipt {
  write: PendingDocumentWrite;
  error: {
    code: string;
    status: number;
    message: string;
    currentRevision?: string;
    currentEtag?: string;
  };
}

export type PendingDocumentRecoveryJournalErrorType = 'revision_conflict' | 'terminal';

export interface PendingDocumentRecoveryJournalEntry {
  recovery: PendingDocumentConflictRecovery;
  dispatchSequence: number;
  errorType: PendingDocumentRecoveryJournalErrorType;
}

export interface PendingDocumentRecoveryJournalSnapshot {
  schemaVersion: 1;
  nextConflictId: number;
  dispatchSequences: Array<{
    kind: PendingDocumentKind;
    documentId: string;
    sequence: number;
  }>;
  entries: PendingDocumentRecoveryJournalEntry[];
}

/** Synchronous by design: conflict receipts are not returned before durability. */
export interface PendingDocumentRecoveryJournal {
  load(): PendingDocumentRecoveryJournalSnapshot | null;
  replace(snapshot: PendingDocumentRecoveryJournalSnapshot): void;
}

export interface PendingDocumentConflictUpdateResult {
  ok: boolean;
  recovery?: PendingDocumentConflictReceipt;
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
  /** Effective validator after chaining earlier writes from the same renderer session. */
  resourceRevision: string,
) => Promise<PendingDocumentWriteSuccess>;

export class PendingDocumentRevisionConflictError extends Error {
  readonly code = 'revision_conflict';
  readonly status = 409;

  constructor(
    message: string,
    readonly currentRevision: string,
    readonly currentEtag: string,
    readonly recovery?: PendingDocumentConflictReceipt,
  ) {
    super(message);
    this.name = 'PendingDocumentRevisionConflictError';
  }
}

/** A deterministic backend/protocol rejection that an identical retry cannot fix. */
export class PendingDocumentTerminalError extends Error {
  readonly retryable = false;

  constructor(
    message: string,
    readonly code: string,
    readonly status?: number,
    readonly recovery?: PendingDocumentConflictReceipt,
  ) {
    super(message);
    this.name = 'PendingDocumentTerminalError';
  }
}

function isTerminalPersistenceError(
  error: unknown,
): error is PendingDocumentRevisionConflictError | PendingDocumentTerminalError {
  return (
    error instanceof PendingDocumentRevisionConflictError
    || error instanceof PendingDocumentTerminalError
  );
}

export const MAX_PENDING_DOCUMENT_BYTES = 128 * 1024 * 1024;
const RESOURCE_REVISION_RE = /^[a-f0-9]{32}$/;

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

export function validateResourceRevision(value: unknown): string {
  if (typeof value !== 'string' || !RESOURCE_REVISION_RE.test(value)) {
    throw new Error('Invalid pending-document resource revision.');
  }
  return value;
}

export function resourceEtag(
  kind: PendingDocumentKind,
  incarnation: string,
  revision: string,
): string {
  return `"lfwb:${kind}:${validatePendingDocumentIncarnation(incarnation)}:${validateResourceRevision(revision)}"`;
}

/** Validate the narrow IPC contract synchronously before acknowledging unload. */
export function validatePendingDocumentWrite(value: unknown): PendingDocumentWrite {
  if (!isRecord(value)) throw new Error('Invalid pending-document payload.');
  const { kind, documentId, incarnation, resourceRevision, revision, sessionId, payload } = value;
  if (kind !== 'whiteboard' && kind !== 'outline') {
    throw new Error('Invalid pending-document kind.');
  }
  const validatedDocumentId = validatePendingDocumentId(documentId);
  const validatedIncarnation = validatePendingDocumentIncarnation(incarnation);
  const validatedResourceRevision = validateResourceRevision(resourceRevision);
  if (!Number.isSafeInteger(revision) || (revision as number) < 1) {
    throw new Error('Invalid pending-document revision.');
  }
  // The backend caps the complete mutation id at 128 characters. Leave room
  // for "_" plus the largest safe-integer renderer revision (16 digits).
  if (typeof sessionId !== 'string' || !/^[A-Za-z0-9_-]{8,110}$/.test(sessionId)) {
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
    resourceRevision: validatedResourceRevision,
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
  effectiveResourceRevision: string = write.resourceRevision,
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
      'X-LogosForge-Mutation-Id': `${write.sessionId}_${write.revision}`,
      'If-Match': resourceEtag(write.kind, write.incarnation, effectiveResourceRevision),
      ...(dispatchSequence === undefined
        ? {}
        : { 'X-LogosForge-Persistence-Order': String(dispatchSequence) }),
    },
    body: JSON.stringify(write.payload),
  };
}

function validateBoundedJournalString(
  value: unknown,
  label: string,
  maxLength: number,
): string {
  if (typeof value !== 'string' || !value.length || value.length > maxLength) {
    throw new Error(`Invalid pending-document recovery ${label}.`);
  }
  return value;
}

function parseConflictSequence(value: string): number {
  const match = /^main_conflict_([1-9]\d*)$/.exec(value);
  if (!match) throw new Error('Invalid pending-document recovery conflict id.');
  const sequence = Number(match[1]);
  if (!Number.isSafeInteger(sequence) || sequence < 1) {
    throw new Error('Invalid pending-document recovery conflict id.');
  }
  return sequence;
}

/** Revalidate all journal data at the trust boundary before startup hydration. */
export function validatePendingDocumentRecoveryJournalSnapshot(
  value: unknown,
): PendingDocumentRecoveryJournalSnapshot {
  if (
    !isRecord(value)
    || value.schemaVersion !== 1
    || !Number.isSafeInteger(value.nextConflictId)
    || (value.nextConflictId as number) < 0
    || !Array.isArray(value.dispatchSequences)
    || !Array.isArray(value.entries)
  ) {
    throw new Error('Invalid pending-document recovery journal schema.');
  }
  if (value.entries.length > 10_000 || value.dispatchSequences.length > 20_000) {
    throw new Error('Pending-document recovery journal contains too many entries.');
  }

  const dispatchIdentities = new Set<string>();
  const dispatchWatermarks = new Map<string, number>();
  const dispatchSequences = value.dispatchSequences.map((item) => {
    if (!isRecord(item) || (item.kind !== 'whiteboard' && item.kind !== 'outline')) {
      throw new Error('Invalid pending-document recovery dispatch watermark.');
    }
    const documentId = validatePendingDocumentId(item.documentId);
    if (!Number.isSafeInteger(item.sequence) || (item.sequence as number) < 1) {
      throw new Error('Invalid pending-document recovery dispatch watermark.');
    }
    const identity = `${item.kind}:${documentId}`;
    if (dispatchIdentities.has(identity)) {
      throw new Error('Duplicate pending-document recovery dispatch watermark.');
    }
    dispatchIdentities.add(identity);
    dispatchWatermarks.set(identity, item.sequence as number);
    return {
      kind: item.kind as PendingDocumentKind,
      documentId,
      sequence: item.sequence as number,
    };
  });

  const identities = new Set<string>();
  const conflictIds = new Set<string>();
  const entries = value.entries.map((entryValue): PendingDocumentRecoveryJournalEntry => {
    if (!isRecord(entryValue)) throw new Error('Invalid pending-document recovery entry.');
    const receiptValue = isRecord(entryValue.recovery) ? entryValue.recovery : null;
    if (!receiptValue) throw new Error('Invalid pending-document recovery receipt.');
    const receipt = {
      conflictId: validateBoundedJournalString(
        receiptValue.conflictId,
        'conflict id',
        64,
      ),
      version: receiptValue.version,
      kind: receiptValue.kind,
      documentId: receiptValue.documentId,
      incarnation: receiptValue.incarnation,
    };
    const conflictSequence = parseConflictSequence(receipt.conflictId);
    if (conflictSequence > (value.nextConflictId as number)) {
      throw new Error('Pending-document recovery conflict id exceeds its journal watermark.');
    }
    if (!Number.isSafeInteger(receipt.version) || (receipt.version as number) < 1) {
      throw new Error('Invalid pending-document recovery conflict version.');
    }
    if (receipt.kind !== 'whiteboard' && receipt.kind !== 'outline') {
      throw new Error('Invalid pending-document recovery kind.');
    }
    const kind = receipt.kind;
    const documentId = validatePendingDocumentId(receipt.documentId);
    const incarnation = validatePendingDocumentIncarnation(receipt.incarnation);
    const write = validatePendingDocumentWrite(receiptValue.write);
    if (
      write.kind !== kind
      || write.documentId !== documentId
      || write.incarnation !== incarnation
    ) {
      throw new Error('Pending-document recovery identity does not match its write.');
    }

    const dispatchSequence = entryValue.dispatchSequence;
    if (!Number.isSafeInteger(dispatchSequence) || (dispatchSequence as number) < 1) {
      throw new Error('Invalid pending-document recovery dispatch sequence.');
    }
    if ((dispatchWatermarks.get(`${kind}:${documentId}`) ?? 0) < (dispatchSequence as number)) {
      throw new Error('Recovery dispatch sequence exceeds its journal watermark.');
    }
    if (entryValue.errorType !== 'revision_conflict' && entryValue.errorType !== 'terminal') {
      throw new Error('Invalid pending-document recovery error type.');
    }
    if (!isRecord(receiptValue.error)) {
      throw new Error('Invalid pending-document recovery error.');
    }
    const errorValue = receiptValue.error;
    const code = validateBoundedJournalString(errorValue.code, 'error code', 128);
    if (!/^[a-z][a-z0-9_]*$/.test(code)) {
      throw new Error('Invalid pending-document recovery error code.');
    }
    const status = errorValue.status;
    if (
      !Number.isSafeInteger(status)
      || (status as number) < 400
      || (status as number) > 499
    ) {
      throw new Error('Invalid pending-document recovery status.');
    }
    const message = validateBoundedJournalString(errorValue.message, 'error message', 8_192);
    let error: PendingDocumentConflictRecovery['error'];
    if (entryValue.errorType === 'revision_conflict') {
      if (code !== 'revision_conflict' || status !== 409) {
        throw new Error('Invalid revision-conflict recovery error.');
      }
      const currentRevision = validateResourceRevision(errorValue.currentRevision);
      const currentEtag = validateBoundedJournalString(errorValue.currentEtag, 'etag', 256);
      if (currentEtag !== resourceEtag(kind, incarnation, currentRevision)) {
        throw new Error('Invalid revision-conflict recovery validator.');
      }
      error = { code, status: 409, message, currentRevision, currentEtag };
    } else {
      if (errorValue.currentRevision !== undefined || errorValue.currentEtag !== undefined) {
        throw new Error('Terminal recovery unexpectedly contains revision-conflict validators.');
      }
      error = { code, status: status as number, message };
    }

    const identity = `${kind}:${documentId}:${incarnation}`;
    if (identities.has(identity) || conflictIds.has(receipt.conflictId)) {
      throw new Error('Pending-document recovery journal contains duplicate entries.');
    }
    identities.add(identity);
    conflictIds.add(receipt.conflictId);
    return {
      recovery: {
        conflictId: receipt.conflictId,
        version: receipt.version as number,
        kind,
        documentId,
        incarnation,
        write,
        error,
      },
      dispatchSequence: dispatchSequence as number,
      errorType: entryValue.errorType,
    };
  });
  return {
    schemaVersion: 1,
    nextConflictId: value.nextConflictId as number,
    dispatchSequences,
    entries,
  };
}

/**
 * Main-process FIFO for document snapshots. Normal and teardown writes share
 * this queue, so pagehide can never overtake an older renderer save. Revisions
 * additionally discard an older IPC message if delivery is observed late.
 */
interface PendingDocumentOperation {
  write: PendingDocumentWrite;
  dispatchSequence: number;
}

interface ResourceRevisionChain {
  current: string;
  aliases: Set<string>;
}

interface PendingDocumentConflictEntry {
  conflictId: string;
  version: number;
  operation: PendingDocumentOperation;
  error: PendingDocumentRevisionConflictError | PendingDocumentTerminalError;
}

const MAX_STRANDED_CONFLICT_RECEIPTS_PER_RESOURCE = 64;

export class PendingDocumentPersistence {
  private readonly tails = new Map<string, Promise<PendingDocumentWriteSuccess>>();
  private readonly pending = new Set<Promise<PendingDocumentWriteSuccess>>();
  private readonly latestSeen = new Map<string, number>();
  private readonly completed = new Map<string, number>();
  private readonly failedLatest = new Map<string, PendingDocumentOperation>();
  private readonly deferredLatest = new Map<string, PendingDocumentOperation>();
  private readonly conflictedLatest = new Map<string, PendingDocumentConflictEntry>();
  /** Candidate ledger states whose durable journal commit failed. */
  private readonly uncommittedConflicts = new Map<string, PendingDocumentConflictEntry>();
  /**
   * Exact renderer receipts stranded by a failed journal replacement. A later
   * local-only flush can make the candidate authoritative without returning its
   * newer receipt to the renderer. Remember only those proven versions so a
   * strictly newer cumulative snapshot from the same renderer session can
   * resynchronize; arbitrary stale receipts remain rejected.
   */
  private readonly strandedConflictReceiptVersions = new Map<string, {
    conflictId: string;
    versions: Set<number>;
  }>();
  private readonly revisionChains = new Map<string, ResourceRevisionChain>();
  private readonly nextDispatchSequence = new Map<string, number>();
  private readonly deletingDocuments = new Set<string>();
  private readonly deletedDocuments = new Set<string>();
  private draining: Promise<void> | null = null;
  private nextConflictId = 0;

  constructor(
    private readonly writer: PendingDocumentWriter,
    private readonly writerTimeoutMs = 10_000,
    private readonly recoveryJournal?: PendingDocumentRecoveryJournal,
  ) {
    if (!recoveryJournal) return;
    const snapshot = recoveryJournal.load();
    if (!snapshot) return;
    const validated = validatePendingDocumentRecoveryJournalSnapshot(snapshot);
    this.nextConflictId = validated.nextConflictId;
    for (const watermark of validated.dispatchSequences) {
      this.nextDispatchSequence.set(
        `${watermark.kind}:${watermark.documentId}`,
        watermark.sequence,
      );
    }
    for (const journalEntry of validated.entries) {
      const { recovery, dispatchSequence, errorType } = journalEntry;
      const error = errorType === 'revision_conflict'
        ? new PendingDocumentRevisionConflictError(
          recovery.error.message,
          recovery.error.currentRevision as string,
          recovery.error.currentEtag as string,
        )
        : new PendingDocumentTerminalError(
          recovery.error.message,
          recovery.error.code,
          recovery.error.status,
        );
      const entry: PendingDocumentConflictEntry = {
        conflictId: recovery.conflictId,
        version: recovery.version,
        operation: { write: recovery.write, dispatchSequence },
        error,
      };
      const key = this.conflictKey(recovery.write);
      this.conflictedLatest.set(key, entry);
      this.nextDispatchSequence.set(
        this.dispatchOrderKey(recovery.write),
        Math.max(
          this.nextDispatchSequence.get(this.dispatchOrderKey(recovery.write)) ?? 0,
          dispatchSequence,
        ),
      );
      this.nextConflictId = Math.max(
        this.nextConflictId,
        parseConflictSequence(recovery.conflictId),
      );
    }
  }

  private async writeWithDeadline(
    write: PendingDocumentWrite,
    dispatchSequence: number,
    resourceRevision: string,
  ): Promise<PendingDocumentWriteSuccess> {
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
      return await Promise.race([
        this.writer(write, controller.signal, dispatchSequence, resourceRevision),
        deadline,
      ]);
    } finally {
      if (timeout) clearTimeout(timeout);
    }
  }

  private serialKey(write: PendingDocumentWrite): string {
    return `${write.kind}:${write.documentId}:${write.incarnation}`;
  }

  private dispatchOrderKey(write: PendingDocumentWrite): string {
    return `${write.kind}:${write.documentId}`;
  }

  private revisionKey(write: PendingDocumentWrite): string {
    return `${this.serialKey(write)}:${write.sessionId}`;
  }

  private revisionChainKey(write: PendingDocumentWrite): string {
    return `${this.serialKey(write)}:${write.sessionId}`;
  }

  private conflictKey(write: PendingDocumentWrite): string {
    return this.serialKey(write);
  }

  private conflictReceipt(entry: PendingDocumentConflictEntry): PendingDocumentConflictReceipt {
    return {
      conflictId: entry.conflictId,
      version: entry.version,
      kind: entry.operation.write.kind,
      documentId: entry.operation.write.documentId,
      incarnation: entry.operation.write.incarnation,
    };
  }

  private recoveryFromEntry(entry: PendingDocumentConflictEntry): PendingDocumentConflictRecovery {
    const recovery = this.conflictReceipt(entry);
    const error = entry.error instanceof PendingDocumentRevisionConflictError
      ? {
        code: entry.error.code,
        status: entry.error.status,
        message: entry.error.message,
        currentRevision: entry.error.currentRevision,
        currentEtag: entry.error.currentEtag,
      }
      : {
        code: entry.error.code,
        status: entry.error.status ?? 409,
        message: entry.error.message,
      };
    return { ...recovery, write: entry.operation.write, error };
  }

  private journalSnapshot(
    entries: ReadonlyMap<string, PendingDocumentConflictEntry>,
  ): PendingDocumentRecoveryJournalSnapshot {
    return {
      schemaVersion: 1,
      nextConflictId: this.nextConflictId,
      dispatchSequences: [...this.nextDispatchSequence.entries()].map(([key, sequence]) => {
        const separator = key.indexOf(':');
        return {
          kind: key.slice(0, separator) as PendingDocumentKind,
          documentId: key.slice(separator + 1),
          sequence,
        };
      }),
      entries: [...entries.values()].map((entry) => ({
        recovery: this.recoveryFromEntry(entry),
        dispatchSequence: entry.operation.dispatchSequence,
        errorType: entry.error instanceof PendingDocumentRevisionConflictError
          ? 'revision_conflict'
          : 'terminal',
      })),
    };
  }

  private replaceCommittedConflicts(
    next: ReadonlyMap<string, PendingDocumentConflictEntry>,
  ): void {
    this.recoveryJournal?.replace(this.journalSnapshot(next));
  }

  private flushUncommittedConflicts(): void {
    if (!this.uncommittedConflicts.size) return;
    const next = new Map(this.conflictedLatest);
    for (const [key, entry] of this.uncommittedConflicts) next.set(key, entry);
    this.replaceCommittedConflicts(next);
    for (const [key, entry] of this.uncommittedConflicts) {
      this.conflictedLatest.set(key, entry);
    }
    this.uncommittedConflicts.clear();
  }

  private commitConflictEntry(
    key: string,
    entry: PendingDocumentConflictEntry,
    acceptedReceiptVersion?: number,
  ): void {
    const next = new Map(this.conflictedLatest);
    next.set(key, entry);
    try {
      this.replaceCommittedConflicts(next);
    } catch (error) {
      // Do not publish a receipt for a state that was not journaled. Keep the
      // candidate separately so drain can retry the local journal commit
      // without ever retrying the deterministic backend rejection.
      this.uncommittedConflicts.set(key, entry);
      const current = this.conflictedLatest.get(key);
      if (current && current.conflictId === entry.conflictId) {
        const strandedVersion = acceptedReceiptVersion ?? current.version;
        const remembered = this.strandedConflictReceiptVersions.get(key);
        if (remembered?.conflictId === current.conflictId) {
          // Never evict the oldest proven renderer receipt. Repeated
          // background snapshots can advance the locally committed generation
          // without returning any newer receipt to that renderer; replacing a
          // full set with those silent generations would eventually strand the
          // only receipt the renderer can use to resynchronize.
          if (
            remembered.versions.size < MAX_STRANDED_CONFLICT_RECEIPTS_PER_RESOURCE
            || remembered.versions.has(strandedVersion)
          ) remembered.versions.add(strandedVersion);
        } else {
          this.strandedConflictReceiptVersions.set(key, {
            conflictId: current.conflictId,
            versions: new Set([strandedVersion]),
          });
        }
      }
      throw error;
    }
    this.conflictedLatest.set(key, entry);
    this.uncommittedConflicts.delete(key);
    // The caller receives this exact committed generation synchronously.
    this.strandedConflictReceiptVersions.delete(key);
  }

  private canResynchronizeConflictReceipt(
    key: string,
    receipt: PendingDocumentConflictReceipt,
    current: PendingDocumentConflictEntry,
    write: PendingDocumentWrite,
  ): boolean {
    const stranded = this.strandedConflictReceiptVersions.get(key);
    return !!stranded
      && stranded.conflictId === receipt.conflictId
      && stranded.versions.has(receipt.version)
      && current.conflictId === receipt.conflictId
      && write.sessionId === current.operation.write.sessionId
      && write.resourceRevision === current.operation.write.resourceRevision
      && write.revision > current.operation.write.revision;
  }

  private errorWithRecovery(
    error: PendingDocumentRevisionConflictError | PendingDocumentTerminalError,
    recovery: PendingDocumentConflictReceipt,
  ): PendingDocumentRevisionConflictError | PendingDocumentTerminalError {
    if (error instanceof PendingDocumentRevisionConflictError) {
      return new PendingDocumentRevisionConflictError(
        error.message,
        error.currentRevision,
        error.currentEtag,
        recovery,
      );
    }
    return new PendingDocumentTerminalError(
      error.message,
      error.code,
      error.status,
      recovery,
    );
  }

  private recordRecoverableConflict(
    operation: PendingDocumentOperation,
    error: PendingDocumentRevisionConflictError | PendingDocumentTerminalError,
  ): PendingDocumentRevisionConflictError | PendingDocumentTerminalError {
    this.flushUncommittedConflicts();
    const key = this.conflictKey(operation.write);
    const current = this.conflictedLatest.get(key);
    if (current && operation.dispatchSequence < current.operation.dispatchSequence) {
      return this.errorWithRecovery(current.error, this.conflictReceipt(current));
    }
    const payload = current && operation.write.kind === 'whiteboard'
      ? { ...current.operation.write.payload, ...operation.write.payload }
      : operation.write.payload;
    const entry: PendingDocumentConflictEntry = {
      conflictId: current?.conflictId ?? `main_conflict_${++this.nextConflictId}`,
      version: (current?.version ?? 0) + 1,
      operation: {
        ...operation,
        write: { ...operation.write, payload },
      },
      error,
    };
    this.commitConflictEntry(key, entry);
    return this.errorWithRecovery(error, this.conflictReceipt(entry));
  }

  private validateConflictReceipt(value: unknown): PendingDocumentConflictReceipt {
    if (!isRecord(value)) throw new Error('Invalid pending-document conflict receipt.');
    const { conflictId, version, kind, documentId, incarnation } = value;
    if (typeof conflictId !== 'string') {
      throw new Error('Invalid pending-document conflict id.');
    }
    parseConflictSequence(conflictId);
    if (!Number.isSafeInteger(version) || (version as number) < 1) {
      throw new Error('Invalid pending-document conflict version.');
    }
    if (kind !== 'whiteboard' && kind !== 'outline') {
      throw new Error('Invalid pending-document conflict kind.');
    }
    return {
      conflictId,
      version: version as number,
      kind,
      documentId: validatePendingDocumentId(documentId),
      incarnation: validatePendingDocumentIncarnation(incarnation),
    };
  }

  private effectiveResourceRevision(write: PendingDocumentWrite): string {
    const key = this.revisionChainKey(write);
    const chain = this.revisionChains.get(key);
    if (!chain) {
      this.revisionChains.set(key, { current: write.resourceRevision, aliases: new Set() });
      return write.resourceRevision;
    }
    if (write.resourceRevision === chain.current || chain.aliases.has(write.resourceRevision)) {
      return chain.current;
    }
    // A renderer can perform an explicit reread or conflict resolution without
    // changing its session id. A validator outside our acknowledged local chain
    // is therefore a fresh authoritative base, not something to overwrite.
    chain.current = write.resourceRevision;
    chain.aliases.clear();
    return write.resourceRevision;
  }

  private recordResourceRevision(
    write: PendingDocumentWrite,
    expected: string,
    result: PendingDocumentWriteSuccess,
  ): void {
    const next = validateResourceRevision(result.resourceRevision);
    const key = this.revisionChainKey(write);
    const chain = this.revisionChains.get(key) ?? { current: expected, aliases: new Set<string>() };
    chain.aliases.add(expected);
    while (chain.aliases.size > 32) {
      const oldest = chain.aliases.values().next().value as string | undefined;
      if (!oldest) break;
      chain.aliases.delete(oldest);
    }
    chain.current = next;
    this.revisionChains.set(key, chain);
  }

  private async executeOperation(
    operation: PendingDocumentOperation,
  ): Promise<PendingDocumentWriteSuccess> {
    const { write, dispatchSequence } = operation;
    if (this.deletingDocuments.has(`${write.documentId}:${write.incarnation}`)) {
      throw new Error(`Document ${write.documentId} is being deleted.`);
    }
    const expected = this.effectiveResourceRevision(write);
    const result = await this.writeWithDeadline(write, dispatchSequence, expected);
    this.recordResourceRevision(write, expected, result);
    return result;
  }

  private markCompleted(operation: PendingDocumentOperation): void {
    const key = this.revisionKey(operation.write);
    this.completed.set(key, Math.max(this.completed.get(key) ?? 0, operation.write.revision));
  }

  enqueue(value: unknown): Promise<PendingDocumentWriteSuccess> {
    const write = validatePendingDocumentWrite(value);
    this.flushUncommittedConflicts();
    if (this.deletedDocuments.has(`${write.documentId}:${write.incarnation}`)) {
      return Promise.resolve({ ok: true, resourceRevision: write.resourceRevision });
    }
    const serialKey = this.serialKey(write);
    const dispatchOrderKey = this.dispatchOrderKey(write);
    const dispatchSequence = (this.nextDispatchSequence.get(dispatchOrderKey) ?? 0) + 1;
    this.nextDispatchSequence.set(dispatchOrderKey, dispatchSequence);
    const operation = { write, dispatchSequence };
    const revisionKey = this.revisionKey(write);
    this.latestSeen.set(
      revisionKey,
      Math.max(this.latestSeen.get(revisionKey) ?? 0, write.revision),
    );

    // Once a resource needs user recovery, do not issue more blind writes from
    // a stale renderer. Pagehide and late IPC snapshots still refresh the
    // main-owned rescue payload synchronously before their rejected promise is
    // observed, so a renderer reload cannot erase edits made after the failure.
    const activeConflict = this.conflictedLatest.get(this.conflictKey(write));
    if (activeConflict) {
      const currentWrite = activeConflict.operation.write;
      const error = write.sessionId === currentWrite.sessionId
        && write.revision > currentWrite.revision
        ? this.recordRecoverableConflict(operation, activeConflict.error)
        : this.errorWithRecovery(activeConflict.error, this.conflictReceipt(activeConflict));
      return Promise.reject(error);
    }

    const previous = this.tails.get(serialKey) ?? Promise.resolve();
    const task = previous.catch(() => {}).then(async () => {
      const latest = this.latestSeen.get(revisionKey) ?? write.revision;
      const completed = this.completed.get(revisionKey) ?? 0;
      if (write.revision < latest || write.revision <= completed) {
        const chain = this.revisionChains.get(this.revisionChainKey(write));
        return { ok: true as const, resourceRevision: chain?.current ?? write.resourceRevision };
      }

      // A predecessor can become terminal after this operation was enqueued.
      // Promote the cumulative newer snapshot into the rescue ledger instead
      // of issuing another stale PUT or leaving a stale conflict behind.
      const chainedConflict = this.conflictedLatest.get(this.conflictKey(write));
      if (chainedConflict) {
        const currentWrite = chainedConflict.operation.write;
        if (write.sessionId === currentWrite.sessionId && write.revision > currentWrite.revision) {
          throw this.recordRecoverableConflict(operation, chainedConflict.error);
        }
        throw this.errorWithRecovery(chainedConflict.error, this.conflictReceipt(chainedConflict));
      }

      const failed = this.failedLatest.get(serialKey);
      if (failed && failed !== operation) {
        try {
          const recovered = await this.executeOperation(failed);
          this.markCompleted(failed);
          if (this.failedLatest.get(serialKey) === failed) this.failedLatest.delete(serialKey);
          if (
            this.revisionKey(failed.write) === revisionKey
            && write.revision <= (this.completed.get(revisionKey) ?? 0)
          ) {
            return recovered;
          }
        } catch (error) {
          if (isTerminalPersistenceError(error)) {
            const retained = operation;
            if (this.failedLatest.get(serialKey) === failed) this.failedLatest.delete(serialKey);
            this.deferredLatest.delete(serialKey);
            throw this.recordRecoverableConflict(retained, error);
          } else {
            // The newest unload snapshot is cumulative for both supported
            // resources. Keep it until the uncertain older operation recovers.
            this.deferredLatest.set(serialKey, operation);
          }
          throw error;
        }
      }

      try {
        const result = await this.executeOperation(operation);
        this.markCompleted(operation);
        this.failedLatest.delete(serialKey);
        this.deferredLatest.delete(serialKey);
        return result;
      } catch (error) {
        // Deterministic protocol failures require a caller/user decision. The
        // renderer outbox retains the snapshot; main must not blindly retry it.
        if (!isTerminalPersistenceError(error)) {
          this.failedLatest.set(serialKey, operation);
        } else {
          this.failedLatest.delete(serialKey);
          this.deferredLatest.delete(serialKey);
          throw this.recordRecoverableConflict(operation, error);
        }
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
  async beginDocumentDelete(
    value: unknown,
    incarnationValue: unknown,
  ): Promise<PendingDocumentDeleteFloor> {
    const documentId = validatePendingDocumentId(value);
    const incarnation = validatePendingDocumentIncarnation(incarnationValue);
    this.deletingDocuments.add(`${documentId}:${incarnation}`);
    const serialKeys = [
      `whiteboard:${documentId}:${incarnation}`,
      `outline:${documentId}:${incarnation}`,
    ];
    // Renderer-side queues are blocked before this call. Looping closes the
    // small IPC-delivery window for a snapshot that main had already received.
    while (true) {
      const active = serialKeys
        .map((serialKey) => this.tails.get(serialKey))
        .filter((tail): tail is Promise<PendingDocumentWriteSuccess> => !!tail);
      if (!active.length) break;
      await Promise.allSettled(active);
    }
    return {
      whiteboard: this.nextDispatchSequence.get(`whiteboard:${documentId}`) ?? 0,
      outline: this.nextDispatchSequence.get(`outline:${documentId}`) ?? 0,
    };
  }

  /** Phase 2 success: discard retries while retaining old revision watermarks. */
  commitDocumentDelete(value: unknown, incarnationValue: unknown): void {
    const documentId = validatePendingDocumentId(value);
    const incarnation = validatePendingDocumentIncarnation(incarnationValue);
    this.flushUncommittedConflicts();
    const serialKeys = [
      `whiteboard:${documentId}:${incarnation}`,
      `outline:${documentId}:${incarnation}`,
    ];
    const nextConflicts = new Map(this.conflictedLatest);
    let removesRecovery = false;
    for (const serialKey of serialKeys) {
      removesRecovery = nextConflicts.delete(serialKey) || removesRecovery;
    }
    // The durable ledger must stop referencing a successfully deleted
    // incarnation before its in-memory rescue entries or delete fence change.
    if (removesRecovery) this.replaceCommittedConflicts(nextConflicts);
    for (const serialKey of serialKeys) {
      this.failedLatest.delete(serialKey);
      this.deferredLatest.delete(serialKey);
      this.conflictedLatest.delete(serialKey);
      this.strandedConflictReceiptVersions.delete(serialKey);
      for (const key of this.revisionChains.keys()) {
        if (key.startsWith(`${serialKey}:`)) this.revisionChains.delete(key);
      }
    }
    for (const key of this.latestSeen.keys()) {
      if (
        key.startsWith(`whiteboard:${documentId}:${incarnation}:`)
        || key.startsWith(`outline:${documentId}:${incarnation}:`)
      ) {
        // SQLite may reuse the highest deleted integer id. A delayed message
        // from the old session is suppressed; a higher revision or new session
        // remains tombstoned; only a genuinely new incarnation is accepted.
        this.completed.set(key, this.latestSeen.get(key) ?? 0);
      }
    }
    this.deletingDocuments.delete(`${documentId}:${incarnation}`);
    this.deletedDocuments.add(`${documentId}:${incarnation}`);
  }

  /** Phase 2 failure: make retained snapshots eligible for a later retry. */
  cancelDocumentDelete(value: unknown, incarnationValue: unknown): void {
    const documentId = validatePendingDocumentId(value);
    const incarnation = validatePendingDocumentIncarnation(incarnationValue);
    this.deletingDocuments.delete(`${documentId}:${incarnation}`);
  }

  /**
   * Refresh an already-conflicted rescue snapshot without touching the network.
   * The exact version check prevents an older renderer from replacing or
   * acknowledging edits captured by a newer renderer.
   */
  retainConflict(value: unknown): PendingDocumentConflictUpdateResult {
    if (!isRecord(value)) throw new Error('Invalid pending-document conflict update.');
    const receipt = this.validateConflictReceipt(value.recovery);
    const write = validatePendingDocumentWrite(value.write);
    if (
      write.kind !== receipt.kind
      || write.documentId !== receipt.documentId
      || write.incarnation !== receipt.incarnation
    ) {
      throw new Error('Pending-document conflict update identity does not match its receipt.');
    }
    this.flushUncommittedConflicts();
    const key = this.conflictKey(write);
    const current = this.conflictedLatest.get(key);
    if (!current || current.conflictId !== receipt.conflictId) return { ok: false };
    const exactReceipt = current.version === receipt.version;
    if (
      !exactReceipt
      && !this.canResynchronizeConflictReceipt(key, receipt, current, write)
    ) return { ok: false };

    const payload = write.kind === 'whiteboard'
      ? { ...current.operation.write.payload, ...write.payload }
      : write.payload;
    const updated: PendingDocumentConflictEntry = {
      ...current,
      version: current.version + 1,
      operation: {
        ...current.operation,
        write: { ...write, payload },
      },
    };
    this.commitConflictEntry(key, updated, receipt.version);
    return { ok: true, recovery: this.conflictReceipt(updated) };
  }

  /** Remove only the precise rescue generation the renderer explicitly resolved. */
  acknowledgeConflict(value: unknown): boolean {
    this.flushUncommittedConflicts();
    const receipt = this.validateConflictReceipt(value);
    const key = `${receipt.kind}:${receipt.documentId}:${receipt.incarnation}`;
    const current = this.conflictedLatest.get(key);
    if (
      !current
      || current.conflictId !== receipt.conflictId
      || current.version !== receipt.version
    ) return false;
    const next = new Map(this.conflictedLatest);
    next.delete(key);
    // Persist removal first. A disk failure leaves the exact prior receipt
    // authoritative both in memory and after a process restart.
    this.replaceCommittedConflicts(next);
    this.conflictedLatest.delete(key);
    this.strandedConflictReceiptVersions.delete(key);
    return true;
  }

  /** Validate an untrusted receipt and confirm that its exact rescue generation is current. */
  hasConflict(value: unknown): boolean {
    const receipt = this.validateConflictReceipt(value);
    const key = `${receipt.kind}:${receipt.documentId}:${receipt.incarnation}`;
    const current = this.conflictedLatest.get(key);
    return !!current
      && current.conflictId === receipt.conflictId
      && current.version === receipt.version;
  }

  listConflicts(): PendingDocumentConflictRecovery[] {
    return [...this.conflictedLatest.values()].map((entry) => this.recoveryFromEntry(entry));
  }

  /** Wait for active writes and retry retained uncertain failures exactly once. */
  drain(): Promise<void> {
    if (this.draining) return this.draining;
    const run = (async () => {
      while (this.pending.size) await Promise.allSettled([...this.pending]);

      // A previous disk error may have prevented publication of a conflict
      // receipt. Commit that state locally before any network retry logic.
      this.flushUncommittedConflicts();

      const retryErrors: unknown[] = [];
      const retries = [...this.failedLatest.entries()];
      for (const [key, failed] of retries) {
        if (this.failedLatest.get(key) !== failed) continue;
        let attempted = failed;
        try {
          await this.executeOperation(failed);
          this.markCompleted(failed);
          if (this.failedLatest.get(key) === failed) this.failedLatest.delete(key);

          const deferred = this.deferredLatest.get(key);
          if (deferred) {
            const latest = this.latestSeen.get(this.revisionKey(deferred.write))
              ?? deferred.write.revision;
            if (deferred.write.revision >= latest) {
              attempted = deferred;
              await this.executeOperation(deferred);
              this.markCompleted(deferred);
            }
            if (this.deferredLatest.get(key) === deferred) this.deferredLatest.delete(key);
          }
        } catch (error) {
          if (isTerminalPersistenceError(error)) {
            const deferred = this.deferredLatest.get(key);
            const retained = attempted !== failed ? attempted : deferred ?? failed;
            if (this.failedLatest.get(key) === failed) this.failedLatest.delete(key);
            this.deferredLatest.delete(key);
            this.recordRecoverableConflict(retained, error);
          } else if (attempted !== failed) {
            // The uncertain predecessor is now durable; the deferred newest
            // snapshot becomes the retry owner if its own dispatch failed.
            this.failedLatest.set(key, attempted);
            if (this.deferredLatest.get(key) === attempted) {
              this.deferredLatest.delete(key);
            }
          }
          if (!isTerminalPersistenceError(error)) retryErrors.push(error);
        }
      }

      if (this.failedLatest.size || this.deferredLatest.size || retryErrors.length) {
        const aggregateErrors: Error[] = [
          ...retryErrors.map((error) => error instanceof Error ? error : new Error(String(error))),
          ...this.failedLatest.values(),
          ...this.deferredLatest.values(),
        ].map((failed) => failed instanceof Error
          ? failed
          : new Error(
            `Could not persist ${failed.write.kind} for document ${failed.write.documentId}.`,
          ));
        throw new AggregateError(
          aggregateErrors,
          'Pending document persistence failed.',
        );
      }
      this.flushUncommittedConflicts();
    })();
    const tracked = run.finally(() => {
      if (this.draining === tracked) this.draining = null;
    });
    this.draining = tracked;
    return tracked;
  }

  async drainStrict(): Promise<void> {
    await this.drain();
    const conflicts = this.listConflicts();
    if (conflicts.length) {
      throw new AggregateError(
        conflicts.map((conflict) => new Error(
          `Unresolved ${conflict.kind} recovery for document ${conflict.documentId}: ${conflict.error.message}`,
        )),
        'Pending document conflicts require explicit recovery.',
      );
    }
  }

  get pendingCount(): number {
    return this.pending.size;
  }

  get conflictCount(): number {
    return new Set([
      ...this.conflictedLatest.keys(),
      ...this.uncommittedConflicts.keys(),
    ]).size;
  }
}
