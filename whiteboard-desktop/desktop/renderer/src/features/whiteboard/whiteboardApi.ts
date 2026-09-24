/** Frontend API client for the whiteboard endpoints (scoped to the active doc). */

import { captureDocumentIdentity, captureDocumentIncarnation, withDoc } from '../../state/currentDocument';
import {
  backendFetch,
  withDocumentIncarnation,
  withExpectedDocumentIncarnation,
} from '../../api/backendAuth';
import { responseError } from '../../api/responseError';
import {
  advanceResourceRevision,
  beginResourceRevisionRead,
  commitResourceRevisionRead,
  requireResourceRevision,
  resourceEtag,
  StaleResourceReadError,
  validateResourceRevisionResponse,
} from '../../api/resourceRevision';
import type { WhiteboardDocument, WhiteboardUpdate } from './types';

export const DEFAULT_BASE_URL = 'http://127.0.0.1:8777';

async function asJson<T>(res: Response): Promise<T> {
  if (!res.ok) throw await responseError(res, 'Request failed');
  return (await res.json()) as T;
}

function assertWhiteboardIdentity(
  document: WhiteboardDocument,
  documentId: string,
  incarnation: string,
): void {
  if (document.id !== documentId || document.incarnation !== incarnation) {
    throw new Error('The backend returned the wrong document identity.');
  }
}

async function readWhiteboard(
  url: string,
  documentId: string,
  incarnation: string,
  signal?: AbortSignal,
): Promise<WhiteboardDocument> {
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const read = beginResourceRevisionRead('whiteboard', documentId, incarnation);
    const res = await backendFetch(url, {
      headers: withExpectedDocumentIncarnation(incarnation),
      signal,
    });
    const document = await asJson<WhiteboardDocument>(res);
    assertWhiteboardIdentity(document, documentId, incarnation);
    const bodyRevision = validateResourceRevisionResponse(
      'whiteboard',
      incarnation,
      document.revision,
      res.headers.get('ETag'),
    );
    const committed = commitResourceRevisionRead(
      'whiteboard',
      documentId,
      incarnation,
      bodyRevision,
      read,
    );
    if (committed.accepted && committed.revision === bodyRevision) return document;
  }
  throw new StaleResourceReadError('whiteboard');
}

export async function getWhiteboard(
  baseUrl: string = DEFAULT_BASE_URL,
  signal?: AbortSignal,
): Promise<WhiteboardDocument> {
  const identity = captureDocumentIdentity();
  return readWhiteboard(
    withDoc(`${baseUrl}/api/whiteboard`),
    identity.documentId,
    identity.incarnation,
    signal,
  );
}

/** Load a target document without changing (or consulting) the active id. */
export async function getWhiteboardForDocument(
  baseUrl: string,
  documentId: string,
  signal?: AbortSignal,
  incarnation: string = captureDocumentIncarnation(documentId),
): Promise<WhiteboardDocument> {
  return readWhiteboard(
    `${baseUrl}/api/whiteboard?doc=${encodeURIComponent(documentId)}`,
    documentId,
    incarnation,
    signal,
  );
}

export async function updateWhiteboard(
  baseUrl: string = DEFAULT_BASE_URL,
  patch: WhiteboardUpdate,
  signal?: AbortSignal,
): Promise<WhiteboardDocument> {
  const identity = captureDocumentIdentity();
  const expectedRevision = requireResourceRevision(
    'whiteboard',
    identity.documentId,
    identity.incarnation,
  );
  const res = await backendFetch(withDoc(`${baseUrl}/api/whiteboard`), {
    method: 'PUT',
    headers: withDocumentIncarnation(identity.incarnation, {
      'Content-Type': 'application/json',
      'If-Match': resourceEtag('whiteboard', identity.incarnation, expectedRevision),
    }),
    body: JSON.stringify(patch),
    signal,
  });
  const document = await asJson<WhiteboardDocument>(res);
  assertWhiteboardIdentity(document, identity.documentId, identity.incarnation);
  const nextRevision = validateResourceRevisionResponse(
    'whiteboard',
    identity.incarnation,
    document.revision,
    res.headers.get('ETag'),
  );
  advanceResourceRevision(
    'whiteboard',
    identity.documentId,
    identity.incarnation,
    expectedRevision,
    nextRevision,
  );
  return document;
}

/** Save a queued patch to its owning document without consulting global UI state. */
export async function updateWhiteboardForDocument(
  baseUrl: string,
  documentId: string,
  patch: WhiteboardUpdate,
  signal?: AbortSignal,
  incarnation: string = captureDocumentIncarnation(documentId),
): Promise<WhiteboardDocument> {
  const expectedRevision = requireResourceRevision('whiteboard', documentId, incarnation);
  const res = await backendFetch(
    `${baseUrl}/api/whiteboard?doc=${encodeURIComponent(documentId)}`,
    {
      method: 'PUT',
      headers: withDocumentIncarnation(incarnation, {
        'Content-Type': 'application/json',
        'If-Match': resourceEtag('whiteboard', incarnation, expectedRevision),
      }),
      body: JSON.stringify(patch),
      signal,
    },
  );
  const document = await asJson<WhiteboardDocument>(res);
  assertWhiteboardIdentity(document, documentId, incarnation);
  const nextRevision = validateResourceRevisionResponse(
    'whiteboard',
    incarnation,
    document.revision,
    res.headers.get('ETag'),
  );
  advanceResourceRevision(
    'whiteboard',
    documentId,
    incarnation,
    expectedRevision,
    nextRevision,
  );
  return document;
}
