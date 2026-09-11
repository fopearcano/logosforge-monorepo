import React from 'react';
import ReactDOM from 'react-dom/client';

import { App } from './App';
import { RenderErrorBoundary } from './components/RenderErrorBoundary';
import { RuntimeFaultBanner } from './components/RuntimeFaultBanner';
import { useRuntimeFaultReporter } from './components/useRuntimeFaultReporter';
import './styles/app.css';
import { applyStoredTheme } from './styles/themes/customThemeStorage';
import { ThemeProvider } from './styles/themes/ThemeProvider';
import { bridge } from './api/backend';
import { waitForPendingDocumentPersistence } from './api/pendingDocumentPersistence';
import { flushPendingDocSaves } from './state/currentDocument';
import {
  getFileSessionState,
  waitForPendingFileSaves,
} from './features/files/fileSessionStore';
import {
  beginDocumentCloseBarrier,
  lockDocumentInteraction,
  releaseDocumentCloseBarrier,
  waitForTrackedDocumentOperations,
} from './features/whiteboard/documentOperationGuard';

// Apply the persisted theme before React renders → no theme flash on startup.
applyStoredTheme();

// Installed at module lifetime, outside the faultable React tree. Main asks for
// this drain on every close, including clean and Don't Save external-file paths.
let releaseCloseInteraction: (() => void) | null = null;

function releaseCloseUi(requestId: number): void {
  if (!releaseDocumentCloseBarrier(requestId)) return;
  releaseCloseInteraction?.();
  releaseCloseInteraction = null;
}

bridge.fileOnFlushAutosaveBeforeClose((requestId) => {
  if (!beginDocumentCloseBarrier(requestId)) {
    bridge.fileSendAutosaveFlushResult(requestId, false, getFileSessionState().dirty);
    return;
  }
  // Modal portals are body siblings of #root, so freeze the whole body rather
  // than only the app root while the persistence snapshot is being finalized.
  releaseCloseInteraction = lockDocumentInteraction();
  void (async () => {
    await waitForTrackedDocumentOperations();
    await flushPendingDocSaves();
    await waitForPendingDocumentPersistence();
    // Stabilize the external-file dirty state before main decides whether to
    // prompt. The shared queue includes saves started by either File menu.
    await waitForPendingFileSaves();
  })().then(
    () => bridge.fileSendAutosaveFlushResult(requestId, true, getFileSessionState().dirty),
    (error: unknown) => {
      console.error('[close] document autosave flush failed:', error);
      releaseCloseUi(requestId);
      bridge.fileSendAutosaveFlushResult(requestId, false, getFileSessionState().dirty);
    },
  );
});

bridge.fileOnCloseCancelled((requestId) => {
  releaseCloseUi(requestId);
});

// This capability belongs to the module-lifetime autosave listener above, not
// to the faultable App/useFileActions tree. Main independently clears it for a
// real navigation, renderer crash, or destroyed webContents.
bridge.fileSetCloseHandshakeReady(true);

function RendererFaultHost() {
  const { fault, dismiss } = useRuntimeFaultReporter();

  return (
    <>
      <RenderErrorBoundary name="Whiteboard application" className="wb-app-boundary">
        <ThemeProvider>
          <App />
        </ThemeProvider>
      </RenderErrorBoundary>
      <RuntimeFaultBanner fault={fault} onDismiss={dismiss} />
    </>
  );
}

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <RendererFaultHost />
  </React.StrictMode>,
);
