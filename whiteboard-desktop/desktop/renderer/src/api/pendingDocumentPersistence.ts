import { backendFetch, withDocumentIncarnation } from './backendAuth';
import { requestRecoveryNoticeCheck } from './recoverySignal';
import { responseError } from './responseError';
import type {
  LogosForgeBridge,
  PendingDocumentWrite,
} from './backend';
import { captureDocumentIncarnation } from '../state/currentDocument';

const sessionId = typeof globalThis.crypto?.randomUUID === 'function'
  ? globalThis.crypto.randomUUID()
  : `renderer_${Date.now()}_${Math.random().toString(36).slice(2)}`;

function nativeBridge(): LogosForgeBridge | null {
  if (typeof window === 'undefined') return null;
  const candidate = window.logosforge;
  return candidate && typeof candidate.persistPendingDocument === 'function' ? candidate : null;
}

function request(
  kind: PendingDocumentWrite['kind'],
  documentId: string,
  revision: number,
  payload: object,
  incarnation: string,
): PendingDocumentWrite {
  return { kind, documentId, incarnation, revision, sessionId, payload };
}

function endpoint(baseUrl: string, kind: PendingDocumentWrite['kind'], documentId: string): string {
  const route = kind === 'whiteboard' ? '/api/whiteboard' : '/api/outline/items';
  return `${baseUrl}${route}?doc=${encodeURIComponent(documentId)}`;
}

/** Electron uses the main-owned FIFO; the direct branch is Vite-browser development only. */
export async function persistPendingDocument(
  baseUrl: string,
  kind: PendingDocumentWrite['kind'],
  documentId: string,
  revision: number,
  payload: object,
  incarnation: string = captureDocumentIncarnation(documentId),
): Promise<void> {
  const native = nativeBridge();
  if (native) {
    await native.persistPendingDocument(request(kind, documentId, revision, payload, incarnation));
    requestRecoveryNoticeCheck();
    return;
  }
  const response = await backendFetch(endpoint(baseUrl, kind, documentId), {
    method: 'PUT',
    headers: withDocumentIncarnation(incarnation, { 'Content-Type': 'application/json' }),
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw await responseError(response, `Could not save ${kind}`);
}

/**
 * `sendSync` returns only after main has validated and copied the snapshot. The
 * main handler queues HTTP asynchronously, so pagehide never waits on network.
 */
export function persistPendingDocumentOnUnload(
  baseUrl: string,
  kind: PendingDocumentWrite['kind'],
  documentId: string,
  revision: number,
  payload: object,
  incarnation: string = captureDocumentIncarnation(documentId),
): void {
  const native = nativeBridge();
  if (native) {
    if (!native.persistPendingDocumentOnUnload(request(
      kind,
      documentId,
      revision,
      payload,
      incarnation,
    ))) {
      console.error(`[persistence] main process rejected ${kind} unload snapshot`);
    }
    return;
  }
  // Browser-only preview fallback. Packaged Electron never relies on Chromium's
  // aggregate keepalive quota or bypasses the main serializer.
  void backendFetch(endpoint(baseUrl, kind, documentId), {
    method: 'PUT',
    headers: withDocumentIncarnation(incarnation, { 'Content-Type': 'application/json' }),
    body: JSON.stringify(payload),
    keepalive: true,
  }).catch(() => {});
}

/** A fresh renderer waits for any teardown snapshot from the previous page. */
export function waitForPendingDocumentPersistence(): Promise<void> {
  return nativeBridge()?.waitForPendingDocumentPersistence() ?? Promise.resolve();
}

/**
 * Let main own the complete fence -> DELETE -> reconcile -> commit transaction.
 * The operation therefore survives renderer reload/crash after DELETE succeeds.
 * Plain-browser development returns false and uses the direct API fallback.
 */
export async function deleteDocumentWithNativePersistenceFence(
  documentId: string,
  incarnation: string,
): Promise<boolean> {
  const native = nativeBridge();
  if (!native) return false;
  await native.deleteDocumentWithPersistenceFence(documentId, incarnation);
  return true;
}
