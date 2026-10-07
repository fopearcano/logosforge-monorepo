import { backendFetch, withDocumentIncarnation, withExpectedDocumentIncarnation } from '../../api/backendAuth';
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
import type { DrafterPage, DrafterPagesDocument } from './types';
import { validateDrafterPagesDocument } from '../../api/runtimeDtoValidation';

const REVISION_RE = /^[a-f0-9]{32}$/;

function endpoint(baseUrl: string, documentId: string): string {
  return `${baseUrl}/api/drafter/pages?doc=${encodeURIComponent(documentId)}`;
}

export async function getDrafterPages(
  baseUrl: string,
  documentId: string,
  incarnation: string,
  signal?: AbortSignal,
): Promise<DrafterPagesDocument> {
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const read = beginResourceRevisionRead('drafter', documentId, incarnation);
    const response = await backendFetch(endpoint(baseUrl, documentId), {
      headers: withExpectedDocumentIncarnation(incarnation),
      signal,
    });
    if (!response.ok) throw await responseError(response, 'Could not load Drafter pages');
    const document = validateDrafterPagesDocument(await response.json());
    const revision = validateResourceRevisionResponse(
      'drafter',
      incarnation,
      document.revision,
      response.headers.get('ETag'),
    );
    const committed = commitResourceRevisionRead(
      'drafter',
      documentId,
      incarnation,
      revision,
      read,
    );
    if (committed.accepted && committed.revision === revision) return document;
  }
  throw new StaleResourceReadError('drafter');
}

export async function putDrafterPages(
  baseUrl: string,
  documentId: string,
  incarnation: string,
  pages: DrafterPage[],
  expectedRevision: string,
  signal?: AbortSignal,
): Promise<DrafterPagesDocument> {
  const currentRevision = requireResourceRevision('drafter', documentId, incarnation);
  if (!REVISION_RE.test(expectedRevision) || expectedRevision !== currentRevision) {
    throw new Error('The Drafter revision is unavailable; reload the document and try again.');
  }
  const response = await backendFetch(endpoint(baseUrl, documentId), {
    method: 'PUT',
    headers: withDocumentIncarnation(incarnation, {
      'Content-Type': 'application/json',
      'If-Match': resourceEtag('drafter', incarnation, expectedRevision),
    }),
    body: JSON.stringify({ pages }),
    signal,
  });
  if (!response.ok) throw await responseError(response, 'Could not save Drafter pages');
  const document = validateDrafterPagesDocument(await response.json());
  const nextRevision = validateResourceRevisionResponse(
    'drafter',
    incarnation,
    document.revision,
    response.headers.get('ETag'),
  );
  advanceResourceRevision(
    'drafter',
    documentId,
    incarnation,
    expectedRevision,
    nextRevision,
  );
  return document;
}
