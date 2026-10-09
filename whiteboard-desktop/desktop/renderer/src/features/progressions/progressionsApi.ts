import { backendFetch, withDocumentIncarnation, withExpectedDocumentIncarnation } from '../../api/backendAuth';
import { BackendResponseError, responseError } from '../../api/responseError';
import {
  captureDocumentIdentity,
  registerDocDiscarder,
  registerDocFlusher,
  runSerializedPendingDocWrite,
  type CapturedDocumentIdentity,
} from '../../state/currentDocument';
import type {
  ProgressionCommand,
  ProgressionCommandReceipt,
  ProgressionSnapshot,
} from './types';
import {
  validateProgressionCommandResult,
  validateProgressionReceipt,
  validateProgressionSnapshot,
} from './progressionValidation';

function url(baseUrl: string, path: string, documentId: string): string {
  const result = new URL(`${baseUrl}${path}`);
  result.searchParams.set('doc', documentId);
  return result.toString();
}

function projectId(identity: CapturedDocumentIdentity): number {
  const value = Number(identity.documentId);
  if (!Number.isSafeInteger(value) || value < 1) throw new Error('The active document has no valid project id.');
  return value;
}

export async function getProgressions(
  baseUrl: string,
  identity: CapturedDocumentIdentity = captureDocumentIdentity(),
  signal?: AbortSignal,
): Promise<ProgressionSnapshot> {
  const res = await backendFetch(url(baseUrl, '/api/progressions', identity.documentId), {
    headers: withExpectedDocumentIncarnation(identity.incarnation),
    signal,
  });
  if (!res.ok) throw await responseError(res, 'Could not load Progressions');
  return validateProgressionSnapshot(await res.json(), projectId(identity));
}

function idempotencyKey(): string {
  return `whiteboard-progressions:${crypto.randomUUID()}`;
}

function canonicalize(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (value !== null && typeof value === 'object') {
    const source = value as Record<string, unknown>;
    const result: Record<string, unknown> = {};
    for (const key of Object.keys(source).sort()) result[key] = canonicalize(source[key]);
    return result;
  }
  if (typeof value === 'number' && !Number.isFinite(value)) {
    throw new Error('The Progressions command contains a non-finite number.');
  }
  return value;
}

function stableCompact(value: unknown): string {
  return JSON.stringify(canonicalize(value));
}

export async function progressionCommandRequestDigest(
  expectedProjectId: number,
  command: ProgressionCommand,
): Promise<string> {
  const { kind, expected_revision, ...fields } = command;
  const encoded = new TextEncoder().encode(stableCompact({
    scope: 'progression-command-v1',
    project_id: expectedProjectId,
    kind,
    expected_revision,
    fields,
  }));
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) throw new Error('Progressions receipt integrity is unavailable in this runtime.');
  const digest = await subtle.digest('SHA-256', encoded);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

interface PendingProgressionAttempt {
  baseUrl: string;
  identity: CapturedDocumentIdentity;
  command: ProgressionCommand;
  key: string;
  requestDigest: string;
  resendAttempted: boolean;
  receiptObserved: boolean;
}

const pendingAttempts = new Map<string, PendingProgressionAttempt>();
let lifecycleRegistered = false;

function attemptId(baseUrl: string, identity: CapturedDocumentIdentity): string {
  // The durable delivery belongs to the document generation, not the current
  // transport address. A backend restart may update `baseUrl`; it must not make
  // the unresolved command disappear and allow a fresh Idempotency-Key.
  void baseUrl;
  return stableCompact([identity.documentId, identity.incarnation]);
}

function sameIdentity(
  left: CapturedDocumentIdentity,
  right: CapturedDocumentIdentity,
): boolean {
  return left.documentId === right.documentId && left.incarnation === right.incarnation;
}

function isAmbiguousFailure(error: unknown): boolean {
  if (!(error instanceof BackendResponseError)) return true;
  return error.status === 408 || error.status === 429 || error.status >= 500;
}

export class ProgressionRecoveryPendingError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ProgressionRecoveryPendingError';
  }
}

function recoveryPending(detail: string): ProgressionRecoveryPendingError {
  return new ProgressionRecoveryPendingError(
    `${detail} The exact Progressions command and Idempotency-Key were retained. `
    + 'Retry recovery later or explicitly abandon it after verifying the project.',
  );
}

async function progressionReceipt(
  attempt: PendingProgressionAttempt,
): Promise<ProgressionCommandReceipt | null> {
  const res = await backendFetch(
    url(attempt.baseUrl, '/api/progressions/command-receipt', attempt.identity.documentId),
    {
      headers: withExpectedDocumentIncarnation(
        attempt.identity.incarnation,
        { 'Idempotency-Key': attempt.key },
      ),
    },
  );
  if (res.status === 404) {
    const miss = await responseError(res, 'Could not recover the Progressions command');
    if (miss.code === 'progression_receipt_not_found') return null;
    throw miss;
  }
  if (!res.ok) throw await responseError(res, 'Could not recover the Progressions command');
  const payload = validateProgressionReceipt(await res.json(),
    projectId(attempt.identity),
    attempt.command,
    attempt.requestDigest,
  );
  return payload;
}

async function postProgressionCommand(
  attempt: PendingProgressionAttempt,
): Promise<ProgressionSnapshot> {
  const res = await backendFetch(
    url(attempt.baseUrl, '/api/progressions/commands', attempt.identity.documentId),
    {
      method: 'POST',
      headers: withDocumentIncarnation(attempt.identity.incarnation, {
        'Content-Type': 'application/json',
        'Idempotency-Key': attempt.key,
      }),
      body: JSON.stringify(attempt.command),
    },
  );
  if (!res.ok) throw await responseError(res, 'Could not update Progressions');
  const payload = validateProgressionCommandResult(await res.json(),
    projectId(attempt.identity),
    attempt.command,
  );
  return payload.progressions;
}

async function finishFromReceipt(
  attempt: PendingProgressionAttempt,
  receipt: ProgressionCommandReceipt,
): Promise<ProgressionSnapshot> {
  void receipt;
  attempt.receiptObserved = true;
  try {
    const snapshot = await getProgressions(attempt.baseUrl, attempt.identity);
    pendingAttempts.delete(attemptId(attempt.baseUrl, attempt.identity));
    return snapshot;
  } catch (error) {
    throw recoveryPending(
      `The durable receipt is committed, but the refreshed Progressions snapshot is unavailable: ${error instanceof Error ? error.message : String(error)}`,
    );
  }
}

async function recoverAttempt(
  attempt: PendingProgressionAttempt,
): Promise<ProgressionSnapshot> {
  let receipt: ProgressionCommandReceipt | null;
  try {
    receipt = await progressionReceipt(attempt);
  } catch (error) {
    throw recoveryPending(
      `Receipt lookup was inconclusive: ${error instanceof Error ? error.message : String(error)}`,
    );
  }
  if (receipt) return finishFromReceipt(attempt, receipt);
  if (attempt.receiptObserved) {
    throw recoveryPending('A previously observed durable receipt is temporarily unavailable.');
  }
  if (attempt.resendAttempted) {
    throw recoveryPending('No durable receipt is visible and the single bounded resend was already used.');
  }

  attempt.resendAttempted = true;
  try {
    const snapshot = await postProgressionCommand(attempt);
    pendingAttempts.delete(attemptId(attempt.baseUrl, attempt.identity));
    return snapshot;
  } catch (error) {
    if (!isAmbiguousFailure(error)) {
      pendingAttempts.delete(attemptId(attempt.baseUrl, attempt.identity));
      throw error;
    }
    try {
      receipt = await progressionReceipt(attempt);
    } catch (receiptError) {
      throw recoveryPending(
        `The bounded resend was ambiguous and receipt lookup was inconclusive: ${receiptError instanceof Error ? receiptError.message : String(receiptError)}`,
      );
    }
    if (receipt) return finishFromReceipt(attempt, receipt);
    throw recoveryPending('The bounded resend was ambiguous and no durable receipt is visible yet.');
  }
}

async function beginAttempt(attempt: PendingProgressionAttempt): Promise<ProgressionSnapshot> {
  try {
    const snapshot = await postProgressionCommand(attempt);
    pendingAttempts.delete(attemptId(attempt.baseUrl, attempt.identity));
    return snapshot;
  } catch (error) {
    if (!isAmbiguousFailure(error)) {
      pendingAttempts.delete(attemptId(attempt.baseUrl, attempt.identity));
      throw error;
    }
    return recoverAttempt(attempt);
  }
}

function ensureLifecycleRegistration(): void {
  if (lifecycleRegistered) return;
  lifecycleRegistered = true;
  registerDocFlusher(async () => {
    const current = captureDocumentIdentity();
    const attempts = [...pendingAttempts.values()].filter((attempt) =>
      sameIdentity(attempt.identity, current));
    for (const attempt of attempts) {
      await runSerializedPendingDocWrite(
        'progressions',
        () => recoverAttempt(attempt),
        attempt.identity.documentId,
      );
    }
  });
  registerDocDiscarder(() => {
    const current = captureDocumentIdentity();
    for (const [key, attempt] of pendingAttempts) {
      if (sameIdentity(attempt.identity, current)) pendingAttempts.delete(key);
    }
  });
}

export function hasPendingProgressionCommand(
  baseUrl: string,
  identity: CapturedDocumentIdentity = captureDocumentIdentity(),
): boolean {
  return pendingAttempts.has(attemptId(baseUrl, identity));
}

export function abandonPendingProgressionCommand(
  baseUrl: string,
  identity: CapturedDocumentIdentity = captureDocumentIdentity(),
): void {
  pendingAttempts.delete(attemptId(baseUrl, identity));
}

export async function resumePendingProgressionCommand(
  baseUrl: string,
  identity: CapturedDocumentIdentity = captureDocumentIdentity(),
): Promise<ProgressionSnapshot | null> {
  const attempt = pendingAttempts.get(attemptId(baseUrl, identity));
  if (!attempt) return null;
  attempt.baseUrl = baseUrl;
  return runSerializedPendingDocWrite(
    'progressions',
    () => recoverAttempt(attempt),
    identity.documentId,
  );
}

export async function runProgressionCommand(
  baseUrl: string,
  command: ProgressionCommand,
): Promise<ProgressionSnapshot> {
  const identity = captureDocumentIdentity();
  ensureLifecycleRegistration();
  return runSerializedPendingDocWrite('progressions', async () => {
    const key = attemptId(baseUrl, identity);
    const pending = pendingAttempts.get(key);
    if (pending) {
      if (stableCompact(pending.command) !== stableCompact(command)) {
        throw recoveryPending('Another Progressions command has an unresolved outcome.');
      }
      pending.baseUrl = baseUrl;
      return recoverAttempt(pending);
    }

    const attempt: PendingProgressionAttempt = {
      baseUrl,
      identity,
      command: structuredClone(command),
      key: idempotencyKey(),
      requestDigest: await progressionCommandRequestDigest(projectId(identity), command),
      resendAttempted: false,
      receiptObserved: false,
    };
    pendingAttempts.set(key, attempt);
    return beginAttempt(attempt);
  }, identity.documentId);
}
