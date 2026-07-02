/** Frontend API client for the PSYKE endpoints (search + create + update + delete). */

import { withDoc } from '../../state/currentDocument';
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
  const url = withDoc(`${baseUrl}/api/psyke/search?q=${encodeURIComponent(query)}`);
  const res = await fetch(url, { signal });
  if (!res.ok) throw new Error(`Request failed (HTTP ${res.status})`);
  return (await res.json()) as PsykeSearchResponse;
}

export async function createPsykeElement(
  baseUrl: string = DEFAULT_BASE_URL,
  payload: PsykeCreatePayload,
  signal?: AbortSignal,
): Promise<PsykeCreateResponse> {
  const res = await fetch(withDoc(`${baseUrl}/api/psyke/elements`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  });
  if (!res.ok) throw new Error(`Save failed (HTTP ${res.status})`);
  return (await res.json()) as PsykeCreateResponse;
}

export async function updatePsykeElement(
  baseUrl: string = DEFAULT_BASE_URL,
  id: string,
  patch: PsykeUpdatePayload,
  signal?: AbortSignal,
): Promise<PsykeCreateResponse> {
  const res = await fetch(withDoc(`${baseUrl}/api/psyke/elements/${encodeURIComponent(id)}`), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
    signal,
  });
  if (!res.ok) throw new Error(`Save failed (HTTP ${res.status})`);
  return (await res.json()) as PsykeCreateResponse;
}

export async function deletePsykeElement(
  baseUrl: string = DEFAULT_BASE_URL,
  id: string,
  signal?: AbortSignal,
): Promise<PsykeDeleteResponse> {
  const res = await fetch(withDoc(`${baseUrl}/api/psyke/elements/${encodeURIComponent(id)}`), {
    method: 'DELETE',
    signal,
  });
  if (!res.ok) throw new Error(`Delete failed (HTTP ${res.status})`);
  return (await res.json()) as PsykeDeleteResponse;
}
