import type { PendingDocumentConflictReceipt } from './backend';

export class BackendResponseError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string | null = null,
    readonly details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = 'BackendResponseError';
  }
}

export class PersistenceRecoveryError extends BackendResponseError {
  constructor(
    message: string,
    status: number,
    code: string,
    readonly recovery?: PendingDocumentConflictReceipt,
    details: Record<string, unknown> = {},
  ) {
    super(message, status, code, details);
    this.name = 'PersistenceRecoveryError';
  }
}

export class RevisionConflictError extends PersistenceRecoveryError {
  readonly currentRevision: string;
  readonly currentEtag: string;

  constructor(
    message: string,
    currentRevision: string,
    currentEtag: string,
    recovery?: PendingDocumentConflictReceipt,
  ) {
    super(message, 409, 'revision_conflict', recovery, {
      current_revision: currentRevision,
      current_etag: currentEtag,
    });
    this.name = 'RevisionConflictError';
    this.currentRevision = currentRevision;
    this.currentEtag = currentEtag;
  }
}

export function isPersistenceRecoveryError(error: unknown): error is PersistenceRecoveryError {
  return error instanceof PersistenceRecoveryError;
}

export function isRevisionConflictError(error: unknown): error is RevisionConflictError {
  return error instanceof RevisionConflictError
    || (
      error instanceof BackendResponseError
      && error.status === 409
      && error.code === 'revision_conflict'
    );
}

/** Extract an actionable, typed error from FastAPI/core error envelopes. */
export async function responseError(res: Response, fallback: string): Promise<BackendResponseError> {
  let message = '';
  let code: string | null = null;
  let details: Record<string, unknown> = {};
  try {
    const data = (await res.clone().json()) as unknown;
    if (data && typeof data === 'object') {
      const record = data as Record<string, unknown>;
      const error = record.error;
      const detail = record.detail;
      if (error && typeof error === 'object') {
        details = error as Record<string, unknown>;
        const nested = details.message;
        if (typeof nested === 'string') message = nested.trim();
        if (typeof details.code === 'string') code = details.code;
      } else if (typeof error === 'string') {
        message = error.trim();
      }
      if (!message && typeof detail === 'string') message = detail.trim();
      if (!message && detail && typeof detail === 'object') {
        const nested = (detail as Record<string, unknown>).message;
        if (typeof nested === 'string') message = nested.trim();
      }
    }
  } catch {
    try {
      message = (await res.text()).trim();
    } catch {
      /* Keep the caller's stable fallback. */
    }
  }
  const rendered = `${message || fallback} (HTTP ${res.status})`;
  if (
    res.status === 409
    && code === 'revision_conflict'
    && typeof details.current_revision === 'string'
  ) {
    return new RevisionConflictError(
      rendered,
      details.current_revision,
      typeof details.current_etag === 'string' ? details.current_etag : res.headers.get('etag') ?? '',
    );
  }
  return new BackendResponseError(rendered, res.status, code, details);
}
