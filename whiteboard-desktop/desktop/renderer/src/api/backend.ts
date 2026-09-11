/**
 * Typed bridge to the Electron main process (exposed by the preload script).
 *
 * Includes a graceful fallback so the renderer still works when opened in a
 * plain browser via the Vite dev server (no Electron bridge present).
 */

export type BackendState = 'connecting' | 'connected' | 'error';

export interface BackendStatus {
  state: BackendState;
  baseUrl: string;
  managed: boolean;
  service?: string;
  version?: string;
  apiVersion?: string;
  authToken?: string;
  detail?: string;
}

export interface PendingDocumentWrite {
  kind: 'whiteboard' | 'outline';
  documentId: string;
  incarnation: string;
  revision: number;
  sessionId: string;
  payload: object;
}

export interface PendingDocumentDeleteFloor {
  whiteboard: number;
  outline: number;
}

export interface LogosForgeBridge {
  getBackendStatus(): Promise<BackendStatus>;
  onBackendStatus(cb: (status: BackendStatus) => void): () => void;
  persistPendingDocument(write: PendingDocumentWrite): Promise<void>;
  persistPendingDocumentOnUnload(write: PendingDocumentWrite): boolean;
  waitForPendingDocumentPersistence(): Promise<void>;
  deleteDocumentWithPersistenceFence(documentId: string, incarnation: string): Promise<void>;
  fileSetCloseHandshakeReady(ready: boolean): void;
  fileSetExternalSaveHandshakeReady(ready: boolean): void;
  fileOnFlushAutosaveBeforeClose(cb: (requestId: number) => void): () => void;
  fileSendAutosaveFlushResult(requestId: number, ok: boolean, fileDirty: boolean): void;
  fileOnCloseCancelled(cb: (requestId: number) => void): () => void;
}

declare global {
  interface Window {
    logosforge?: LogosForgeBridge;
  }
}

// Dev convenience: when opened in a plain browser (Vite dev server, no Electron
// bridge), probe a locally-running wrapper backend directly so the preview is
// fully functional. No effect in the packaged app, which always has the bridge.
const DEV_BASE_URL = 'http://127.0.0.1:8777';

const fallback: LogosForgeBridge = {
  async getBackendStatus() {
    try {
      const res = await fetch(DEV_BASE_URL + '/health');
      if (res.ok) {
        const h = (await res.json()) as Record<string, unknown>;
        return {
          state: 'connected',
          baseUrl: DEV_BASE_URL,
          managed: false,
          service: typeof h.service === 'string' ? h.service : undefined,
          version: typeof h.core_version === 'string' ? h.core_version : undefined,
          apiVersion: typeof h.api_version === 'string' ? h.api_version : undefined,
        };
      }
    } catch {
      /* not reachable — fall through to the error status */
    }
    return {
      state: 'error',
      baseUrl: '',
      managed: false,
      detail: `Not running inside Electron, and no dev backend at ${DEV_BASE_URL}.`,
    };
  },
  onBackendStatus() {
    return () => {};
  },
  persistPendingDocument() {
    return Promise.reject(new Error('Native document persistence is unavailable.'));
  },
  persistPendingDocumentOnUnload() {
    return false;
  },
  waitForPendingDocumentPersistence() {
    return Promise.resolve();
  },
  deleteDocumentWithPersistenceFence() {
    return Promise.resolve();
  },
  fileSetCloseHandshakeReady() {},
  fileSetExternalSaveHandshakeReady() {},
  fileOnFlushAutosaveBeforeClose() {
    return () => {};
  },
  fileSendAutosaveFlushResult() {},
  fileOnCloseCancelled() {
    return () => {};
  },
};

export const bridge: LogosForgeBridge = window.logosforge ?? fallback;
