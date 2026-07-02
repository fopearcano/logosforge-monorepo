/** Frontend API client for the whiteboard endpoints (scoped to the active doc). */

import { withDoc } from '../../state/currentDocument';
import type { WhiteboardDocument, WhiteboardUpdate } from './types';

export const DEFAULT_BASE_URL = 'http://127.0.0.1:8777';

async function asJson<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`Request failed (HTTP ${res.status})`);
  return (await res.json()) as T;
}

export async function getWhiteboard(
  baseUrl: string = DEFAULT_BASE_URL,
  signal?: AbortSignal,
): Promise<WhiteboardDocument> {
  return asJson<WhiteboardDocument>(await fetch(withDoc(`${baseUrl}/api/whiteboard`), { signal }));
}

export async function updateWhiteboard(
  baseUrl: string = DEFAULT_BASE_URL,
  patch: WhiteboardUpdate,
  signal?: AbortSignal,
): Promise<WhiteboardDocument> {
  const res = await fetch(withDoc(`${baseUrl}/api/whiteboard`), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
    signal,
  });
  return asJson<WhiteboardDocument>(res);
}
