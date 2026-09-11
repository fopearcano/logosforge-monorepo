/** Frontend API client for the PSYKE endpoints (search + create + update + delete). */

import {
  captureDocumentIdentity,
  captureDocumentIncarnation,
  getCurrentDocId,
  runPendingDocWrite,
} from '../../state/currentDocument';
import {
  backendFetch,
  withDocumentIncarnation,
  withExpectedDocumentIncarnation,
} from '../../api/backendAuth';
import { responseError } from '../../api/responseError';
import type {
  PsykeCreatePayload,
  PsykeCreateResponse,
  PsykeDeleteResponse,
  PsykeSearchResponse,
  PsykeUpdatePayload,
} from './types';

const DEFAULT_BASE_URL = 'http://127.0.0.1:8777';

export async function searchPsyke(
  baseUrl: string = DEFAULT_BASE_URL,
  query: string,
  signal?: AbortSignal,
): Promise<PsykeSearchResponse> {
  return searchPsykeForDocument(baseUrl, getCurrentDocId(), query, signal);
}

/** Search a captured document without consulting the active-id singleton. */
export async function searchPsykeForDocument(
  baseUrl: string,
  documentId: string,
  query: string,
  signal?: AbortSignal,
  incarnation: string = captureDocumentIncarnation(documentId),
): Promise<PsykeSearchResponse> {
  const url = new URL(`${baseUrl}/api/psyke/search`);
  url.searchParams.set('q', query);
  if (documentId) url.searchParams.set('doc', documentId);
  const res = await backendFetch(url.toString(), {
    headers: withExpectedDocumentIncarnation(incarnation),
    signal,
  });
  if (!res.ok) throw await responseError(res, 'Could not search PSYKE');
  return (await res.json()) as PsykeSearchResponse;
}

export async function createPsykeElement(
  baseUrl: string = DEFAULT_BASE_URL,
  payload: PsykeCreatePayload,
  signal?: AbortSignal,
): Promise<PsykeCreateResponse> {
  const documentId = getCurrentDocId();
  return createPsykeElementForDocument(baseUrl, documentId, payload, signal);
}

/** Explicit-id variant used by project import transactions pinned to one doc. */
export async function createPsykeElementForDocument(
  baseUrl: string,
  documentId: string,
  payload: PsykeCreatePayload,
  signal?: AbortSignal,
): Promise<PsykeCreateResponse> {
  const identity = captureDocumentIdentity(documentId);
  return runPendingDocWrite(
    async () => {
      const url = new URL(`${baseUrl}/api/psyke/elements`);
      if (documentId) url.searchParams.set('doc', documentId);
      const res = await backendFetch(url.toString(), {
        method: 'POST',
        headers: withDocumentIncarnation(identity.incarnation, { 'Content-Type': 'application/json' }),
        body: JSON.stringify(payload),
        signal,
      });
      if (!res.ok) throw await responseError(res, 'Could not save the PSYKE element');
      return (await res.json()) as PsykeCreateResponse;
    },
    documentId,
  );
}

export async function updatePsykeElement(
  baseUrl: string = DEFAULT_BASE_URL,
  id: string,
  patch: PsykeUpdatePayload,
  signal?: AbortSignal,
): Promise<PsykeCreateResponse> {
  const documentId = getCurrentDocId();
  const identity = captureDocumentIdentity(documentId);
  return runPendingDocWrite(
    async () => {
      const res = await backendFetch(
        `${baseUrl}/api/psyke/elements/${encodeURIComponent(id)}?doc=${encodeURIComponent(documentId)}`,
        {
        method: 'PATCH',
        headers: withDocumentIncarnation(identity.incarnation, { 'Content-Type': 'application/json' }),
        body: JSON.stringify(patch),
        signal,
        },
      );
      if (!res.ok) throw await responseError(res, 'Could not save the PSYKE element');
      return (await res.json()) as PsykeCreateResponse;
    },
    documentId,
  );
}

export async function deletePsykeElement(
  baseUrl: string = DEFAULT_BASE_URL,
  id: string,
  signal?: AbortSignal,
): Promise<PsykeDeleteResponse> {
  const documentId = getCurrentDocId();
  const identity = captureDocumentIdentity(documentId);
  return runPendingDocWrite(
    async () => {
      const res = await backendFetch(
        `${baseUrl}/api/psyke/elements/${encodeURIComponent(id)}?doc=${encodeURIComponent(documentId)}`,
        {
          method: 'DELETE',
          headers: withDocumentIncarnation(identity.incarnation),
          signal,
        },
      );
      if (!res.ok) throw await responseError(res, 'Could not delete the PSYKE element');
      return (await res.json()) as PsykeDeleteResponse;
    },
    documentId,
  );
}
