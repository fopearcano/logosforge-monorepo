/** Frontend API client for the writing-modes endpoint. */

import type { WritingModesResponse } from './types';

const DEFAULT_BASE_URL = 'http://127.0.0.1:8777';

export async function getWritingModes(
  baseUrl: string = DEFAULT_BASE_URL,
  signal?: AbortSignal,
): Promise<WritingModesResponse> {
  const res = await fetch(`${baseUrl}/api/writing-modes`, { signal });
  if (!res.ok) throw new Error(`Request failed (HTTP ${res.status})`);
  return (await res.json()) as WritingModesResponse;
}
