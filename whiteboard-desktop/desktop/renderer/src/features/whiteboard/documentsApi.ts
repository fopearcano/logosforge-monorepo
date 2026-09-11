/** Frontend API client for the document library (list / create / delete).
 *
 * These routes manage the SET of documents (not doc-scoped) — a document is one
 * core project (its isolated PSYKE bible) plus local blocks + outline keyed by id.
 */

import type { WhiteboardDocument } from './types';
import { backendFetch, withDocumentIncarnation } from '../../api/backendAuth';
import { responseError } from '../../api/responseError';
import type { PendingDocumentDeleteFloor } from '../../api/backend';

const DEFAULT_BASE_URL = 'http://127.0.0.1:8777';
const DOCUMENT_REQUEST_TIMEOUT_MS = 10_000;

async function withDocumentRequestDeadline<T>(
  label: string,
  run: (signal: AbortSignal) => Promise<T>,
): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), DOCUMENT_REQUEST_TIMEOUT_MS);
  try {
    return await run(controller.signal);
  } catch (error) {
    if (controller.signal.aborted) {
      throw new Error(`${label} timed out.`);
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

export interface DocumentSummary {
  id: string;
  incarnation: string;
  title: string;
  mode: string;
  updated_at: string;
}

export async function listDocuments(
  baseUrl: string = DEFAULT_BASE_URL,
  signal?: AbortSignal,
): Promise<DocumentSummary[]> {
  const res = await backendFetch(`${baseUrl}/api/documents`, { signal });
  if (!res.ok) throw await responseError(res, 'Could not load the document library');
  const data = (await res.json()) as { documents?: DocumentSummary[] };
  return data.documents ?? [];
}

export async function createDocument(
  baseUrl: string = DEFAULT_BASE_URL,
  payload: { title?: string; mode?: string } = {},
): Promise<WhiteboardDocument> {
  const res = await backendFetch(`${baseUrl}/api/documents`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw await responseError(res, 'Could not create the document');
  const data = (await res.json()) as { document: WhiteboardDocument };
  return data.document;
}

export async function deleteDocument(
  baseUrl: string = DEFAULT_BASE_URL,
  id: string,
  incarnation: string,
  floor: PendingDocumentDeleteFloor = { whiteboard: 0, outline: 0 },
): Promise<void> {
  await withDocumentRequestDeadline('Document delete', async (signal) => {
    const res = await backendFetch(`${baseUrl}/api/documents/${encodeURIComponent(id)}`, {
      method: 'DELETE',
      headers: withDocumentIncarnation(incarnation, {
        'X-LogosForge-Whiteboard-Order-Floor': String(floor.whiteboard),
        'X-LogosForge-Outline-Order-Floor': String(floor.outline),
      }),
      signal,
    });
    if (!res.ok) throw await responseError(res, 'Could not delete the document');
  });
}

export async function documentExists(
  baseUrl: string = DEFAULT_BASE_URL,
  id: string,
  incarnation: string,
): Promise<boolean> {
  return withDocumentRequestDeadline('Document delete reconciliation', async (signal) => {
    const res = await backendFetch(
      `${baseUrl}/api/documents/${encodeURIComponent(id)}/exists`,
      { headers: withDocumentIncarnation(incarnation), signal },
    );
    if (!res.ok) throw await responseError(res, 'Could not reconcile the document delete');
    const data = (await res.json()) as { exists?: unknown };
    if (typeof data.exists !== 'boolean') {
      throw new Error('The document-existence response was invalid.');
    }
    return data.exists;
  });
}
