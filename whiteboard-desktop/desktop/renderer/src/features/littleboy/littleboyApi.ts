/** Frontend API client for the LittleBoy endpoints (Billy chat + Logos inline). */

import {
  captureDocumentIdentity,
  type CapturedDocumentIdentity,
} from '../../state/currentDocument';
import { backendFetch, withDocumentIncarnation } from '../../api/backendAuth';
import { responseError } from '../../api/responseError';
import { runLittleBoyDocumentRequest } from './littleboyRequestLifecycle';
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
  identity: CapturedDocumentIdentity = captureDocumentIdentity(),
): Promise<BillyChatResponse> {
  return runLittleBoyDocumentRequest(identity, async () => {
    const res = await backendFetch(
      `${baseUrl}/api/littleboy/billy/chat?doc=${encodeURIComponent(identity.documentId)}`,
      {
        method: 'POST',
        headers: withDocumentIncarnation(
          identity.incarnation,
          { 'Content-Type': 'application/json' },
        ),
        body: JSON.stringify(req),
        signal,
      },
    );
    if (!res.ok) throw await responseError(res, 'Billy could not respond');
    return (await res.json()) as BillyChatResponse;
  });
}

export async function logosInline(
  baseUrl: string = DEFAULT_BASE_URL,
  req: LogosInlineRequest,
  signal?: AbortSignal,
  identity: CapturedDocumentIdentity = captureDocumentIdentity(),
): Promise<LogosInlineResponse> {
  return runLittleBoyDocumentRequest(identity, async () => {
    const res = await backendFetch(
      `${baseUrl}/api/littleboy/logos/inline?doc=${encodeURIComponent(identity.documentId)}`,
      {
        method: 'POST',
        headers: withDocumentIncarnation(
          identity.incarnation,
          { 'Content-Type': 'application/json' },
        ),
        body: JSON.stringify(req),
        signal,
      },
    );
    if (!res.ok) throw await responseError(res, 'Logos could not respond');
    return (await res.json()) as LogosInlineResponse;
  });
}
