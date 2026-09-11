/** Frontend API client for the whiteboard endpoints (scoped to the active doc). */

import { captureDocumentIdentity, captureDocumentIncarnation, withDoc } from '../../state/currentDocument';
import {
  backendFetch,
  withDocumentIncarnation,
  withExpectedDocumentIncarnation,
} from '../../api/backendAuth';
import { responseError } from '../../api/responseError';
import type { WhiteboardDocument, WhiteboardUpdate } from './types';

export const DEFAULT_BASE_URL = 'http://127.0.0.1:8777';

async function asJson<T>(res: Response): Promise<T> {
  if (!res.ok) throw await responseError(res, 'Request failed');
  return (await res.json()) as T;
}

export async function getWhiteboard(
  baseUrl: string = DEFAULT_BASE_URL,
  signal?: AbortSignal,
): Promise<WhiteboardDocument> {
  const identity = captureDocumentIdentity();
  return asJson<WhiteboardDocument>(
    await backendFetch(withDoc(`${baseUrl}/api/whiteboard`), {
      headers: withExpectedDocumentIncarnation(identity.incarnation),
      signal,
    }),
  );
}

/** Load a target document without changing (or consulting) the active id. */
export async function getWhiteboardForDocument(
  baseUrl: string,
  documentId: string,
  signal?: AbortSignal,
  incarnation: string = captureDocumentIncarnation(documentId),
): Promise<WhiteboardDocument> {
  return asJson<WhiteboardDocument>(
    await backendFetch(`${baseUrl}/api/whiteboard?doc=${encodeURIComponent(documentId)}`, {
      headers: withExpectedDocumentIncarnation(incarnation),
      signal,
    }),
  );
}

export async function updateWhiteboard(
  baseUrl: string = DEFAULT_BASE_URL,
  patch: WhiteboardUpdate,
  signal?: AbortSignal,
): Promise<WhiteboardDocument> {
  const identity = captureDocumentIdentity();
  const res = await backendFetch(withDoc(`${baseUrl}/api/whiteboard`), {
    method: 'PUT',
    headers: withDocumentIncarnation(identity.incarnation, { 'Content-Type': 'application/json' }),
    body: JSON.stringify(patch),
    signal,
  });
  return asJson<WhiteboardDocument>(res);
}

/** Save a queued patch to its owning document without consulting global UI state. */
export async function updateWhiteboardForDocument(
  baseUrl: string,
  documentId: string,
  patch: WhiteboardUpdate,
  signal?: AbortSignal,
  incarnation: string = captureDocumentIncarnation(documentId),
): Promise<WhiteboardDocument> {
  const res = await backendFetch(
    `${baseUrl}/api/whiteboard?doc=${encodeURIComponent(documentId)}`,
    {
      method: 'PUT',
      headers: withDocumentIncarnation(incarnation, { 'Content-Type': 'application/json' }),
      body: JSON.stringify(patch),
      signal,
    },
  );
  return asJson<WhiteboardDocument>(res);
}
