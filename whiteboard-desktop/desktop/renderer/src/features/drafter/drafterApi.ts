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

const REVISION_RE = /^[a-f0-9]{32}$/;

function endpoint(baseUrl: string, documentId: string): string {
  return `${baseUrl}/api/drafter/pages?doc=${encodeURIComponent(documentId)}`;
}

function assertDocument(value: unknown): DrafterPagesDocument {
  if (!value || typeof value !== 'object') throw new Error('The backend returned invalid Drafter pages.');
  const candidate = value as Record<string, unknown>;
  if (!Array.isArray(candidate.pages) || typeof candidate.revision !== 'string') {
    throw new Error('The backend returned invalid Drafter pages.');
  }
  if (!REVISION_RE.test(candidate.revision)) {
    throw new Error('The backend returned an invalid Drafter revision.');
  }
  const now = new Date().toISOString();
  const pages: DrafterPage[] = [];
  for (const page of candidate.pages) {
    if (
      !page || typeof page !== 'object'
      || typeof (page as DrafterPage).id !== 'string'
      || typeof (page as DrafterPage).title !== 'string'
      || !Array.isArray((page as DrafterPage).blocks)
    ) {
      throw new Error('The backend returned an invalid Drafter page.');
    }
    const typed = page as DrafterPage;
    pages.push({
      ...typed,
      created_at: typeof typed.created_at === 'string' ? typed.created_at : now,
      updated_at: typeof typed.updated_at === 'string' ? typed.updated_at : now,
    });
  }
  return { pages, revision: candidate.revision };
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
    const document = assertDocument(await response.json());
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
  const document = assertDocument(await response.json());
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
