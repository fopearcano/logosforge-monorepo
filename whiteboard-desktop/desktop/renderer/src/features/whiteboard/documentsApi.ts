/** Frontend API client for the document library (list / create / delete).
 *
 * These routes manage the SET of documents (not doc-scoped) — a document is one
 * core project (its isolated PSYKE bible) plus local blocks + outline keyed by id.
 */

import type { WhiteboardDocument } from './types';

const DEFAULT_BASE_URL = 'http://127.0.0.1:8777';

export interface DocumentSummary {
  id: string;
  title: string;
  mode: string;
  updated_at: string;
}

export async function listDocuments(
  baseUrl: string = DEFAULT_BASE_URL,
  signal?: AbortSignal,
): Promise<DocumentSummary[]> {
  const res = await fetch(`${baseUrl}/api/documents`, { signal });
  if (!res.ok) throw new Error(`Request failed (HTTP ${res.status})`);
  const data = (await res.json()) as { documents?: DocumentSummary[] };
  return data.documents ?? [];
}

export async function createDocument(
  baseUrl: string = DEFAULT_BASE_URL,
  payload: { title?: string; mode?: string } = {},
): Promise<WhiteboardDocument> {
  const res = await fetch(`${baseUrl}/api/documents`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Create failed (HTTP ${res.status})`);
  const data = (await res.json()) as { document: WhiteboardDocument };
  return data.document;
}

export async function deleteDocument(
  baseUrl: string = DEFAULT_BASE_URL,
  id: string,
): Promise<void> {
  const res = await fetch(`${baseUrl}/api/documents/${encodeURIComponent(id)}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Delete failed (HTTP ${res.status})`);
}
