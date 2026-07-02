/** Frontend API client for the LittleBoy endpoints (Billy chat + Logos inline). */

import { withDoc } from '../../state/currentDocument';
import type {
  BillyChatRequest,
  BillyChatResponse,
  LogosInlineRequest,
  LogosInlineResponse,
} from './littleboyTypes';

const DEFAULT_BASE_URL = 'http://127.0.0.1:8777';

export async function billyChat(
  baseUrl: string = DEFAULT_BASE_URL,
  req: BillyChatRequest,
  signal?: AbortSignal,
): Promise<BillyChatResponse> {
  const res = await fetch(withDoc(`${baseUrl}/api/littleboy/billy/chat`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
    signal,
  });
  if (!res.ok) throw new Error(`Request failed (HTTP ${res.status})`);
  return (await res.json()) as BillyChatResponse;
}

export async function logosInline(
  baseUrl: string = DEFAULT_BASE_URL,
  req: LogosInlineRequest,
  signal?: AbortSignal,
): Promise<LogosInlineResponse> {
  const res = await fetch(withDoc(`${baseUrl}/api/littleboy/logos/inline`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
    signal,
  });
  if (!res.ok) throw new Error(`Request failed (HTTP ${res.status})`);
  return (await res.json()) as LogosInlineResponse;
}
