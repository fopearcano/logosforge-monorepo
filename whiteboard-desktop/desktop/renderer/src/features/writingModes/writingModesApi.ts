/** Frontend API client for the writing-modes endpoint. */

import type { WritingModesResponse } from './types';
import { backendFetch } from '../../api/backendAuth';
import { responseError } from '../../api/responseError';

const DEFAULT_BASE_URL = 'http://127.0.0.1:8777';

export async function getWritingModes(
  baseUrl: string = DEFAULT_BASE_URL,
  signal?: AbortSignal,
): Promise<WritingModesResponse> {
  const res = await backendFetch(`${baseUrl}/api/writing-modes`, { signal });
  if (!res.ok) throw await responseError(res, 'Could not load writing modes');
  return (await res.json()) as WritingModesResponse;
}
