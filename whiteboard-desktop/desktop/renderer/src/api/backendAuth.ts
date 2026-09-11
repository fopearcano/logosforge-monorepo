let sessionToken = '';

/** Configure the secret received from the Electron main process. Never persist it. */
export function setBackendAuthToken(token: string | null | undefined): void {
  sessionToken = typeof token === 'string' ? token : '';
}

export function withBackendAuth(init: RequestInit = {}): RequestInit {
  const headers = new Headers(init.headers);
  if (sessionToken) headers.set('Authorization', `Bearer ${sessionToken}`);
  return { ...init, headers };
}

/** Attach the generation captured when a document mutation was scheduled. */
export function withDocumentIncarnation(
  incarnation: string,
  headers?: HeadersInit,
): Headers {
  if (!incarnation) {
    throw new Error('The document identity is unavailable; reload the document and try again.');
  }
  const next = new Headers(headers);
  next.set('X-LogosForge-Document-Incarnation', incarnation);
  return next;
}

/** Attach an expected generation to lifecycle-aware reads when one is known. */
export function withExpectedDocumentIncarnation(
  incarnation: string,
  headers?: HeadersInit,
): Headers {
  const next = new Headers(headers);
  if (incarnation) next.set('X-LogosForge-Document-Incarnation', incarnation);
  return next;
}

/** Authenticated fetch for every Whiteboard wrapper `/api/*` request. */
export async function backendFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const response = await fetch(input, withBackendAuth(init));
  const url = typeof input === 'string' ? input : input.toString();
  // Local-state recovery can happen inside any wrapper request. Ask the UI to
  // consume notices after activity, excluding the notice request itself so the
  // signal cannot recurse.
  if (!url.includes('/api/recovery/notices')) requestRecoveryNoticeCheck();
  return response;
}
import { requestRecoveryNoticeCheck } from './recoverySignal';
