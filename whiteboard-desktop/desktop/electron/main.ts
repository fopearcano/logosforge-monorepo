import { app, BrowserWindow, ipcMain, type IpcMainEvent, type IpcMainInvokeEvent } from 'electron';
import * as path from 'node:path';

import { BackendManager, type BackendStatus } from './backend-manager';
import {
  confirmImportMode,
  confirmContinueAfterRendererFailure,
  confirmSaveChanges,
  type DialogFilter,
  type SaveChoice,
  openFileDialog,
  openImportDialog,
  saveExportDialog,
  saveFileDialog,
  saveFileToPath,
} from './file-manager';
import { setAppMenu } from './menu';
import { installMcpCompanion, mcpCompanionPath, runtimeDescriptorPath } from './mcp-runtime';
import { bundledMcpExecutableName, resolveBundledMcpPath } from './platform-paths';
import { runDocumentDeleteTransaction } from './document-delete-transaction';
import { PathGrantRegistry } from './path-grants';
import { PendingOperationTracker } from './pending-operation-tracker';
import {
  RendererCloseCapabilities,
  RendererSaveRequestRegistry,
  type CorrelatedRendererSaveRequest,
} from './renderer-save-gate';
import {
  ClosePreparationCoordinator,
  classifySystemSessionRendererOutcome,
  drainPersistenceUntilSettled,
  effectiveCloseAction,
  ordinaryCloseCanContinue,
  prepareSystemSessionEndPersistence,
} from './shutdown-persistence';
import {
  buildPendingDocumentHttpRequest,
  PendingDocumentRevisionConflictError,
  PendingDocumentTerminalError,
  PendingDocumentPersistence,
  type PendingDocumentConflictRecovery,
  resourceEtag,
  validatePendingDocumentId,
  validatePendingDocumentIncarnation,
  validateResourceRevision,
} from './pending-document-persistence';

// Keep packaged user data under the product identity rather than the npm name.
// This must run before the first user-data path lookup below.
app.setName('LogosForge Whiteboard');

const DEV_SERVER_URL = process.env.VITE_DEV_SERVER_URL ?? 'http://localhost:5173';
const isProd = app.isPackaged || process.argv.includes('--prod');
const bundledMcpPath = app.isPackaged ? resolveBundledMcpPath(process.resourcesPath) : undefined;
let mcpRuntimePath: string | undefined;
let installedMcpPath: string | undefined;
try {
  mcpRuntimePath = runtimeDescriptorPath(app.getPath('userData'));
  installedMcpPath = mcpCompanionPath(
    app.getPath('userData'),
    bundledMcpExecutableName(process.platform),
  );
} catch (error) {
  // A bad advanced-test override must disable the bridge, not the writing app.
  const detail = error instanceof Error ? error.message : String(error);
  console.error(`[mcp] Ignoring invalid local MCP path configuration: ${detail}`);
}

let mainWindow: BrowserWindow | null = null;
const backend = new BackendManager({ production: isProd, mcpRuntimePath });
const writablePaths = new PathGrantRegistry();
const mainFileWrites = new PendingOperationTracker();
const documentPersistence = new PendingDocumentPersistence(async (
  write,
  signal,
  dispatchSequence,
  resourceRevision,
) => {
  const request = buildPendingDocumentHttpRequest(
    write,
    backend.getStatus(),
    dispatchSequence,
    resourceRevision,
  );
  const response = await fetch(request.url, {
    method: request.method,
    headers: request.headers,
    body: request.body,
    signal,
  });
  let body: Record<string, unknown> = {};
  try {
    const parsed = await response.json() as unknown;
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      body = parsed as Record<string, unknown>;
    }
  } catch {
    /* A stable HTTP error below is safer than exposing transport internals. */
  }
  if (!response.ok) {
    const error = body.error && typeof body.error === 'object' && !Array.isArray(body.error)
      ? body.error as Record<string, unknown>
      : {};
    const message = typeof error.message === 'string' && error.message.trim()
      ? error.message.trim()
      : `Could not persist ${write.kind} (HTTP ${response.status}).`;
    if (response.status === 409 && error.code === 'revision_conflict') {
      const currentRevision = validateResourceRevision(error.current_revision);
      const currentEtag = typeof error.current_etag === 'string'
        ? error.current_etag
        : response.headers.get('etag') ?? '';
      throw new PendingDocumentRevisionConflictError(
        message,
        currentRevision,
        currentEtag,
      );
    }
    const rendered = `${message} (HTTP ${response.status}).`;
    if (response.status >= 400 && response.status < 500) {
      throw new PendingDocumentTerminalError(
        rendered,
        typeof error.code === 'string' ? error.code : 'persistence_request_rejected',
        response.status,
      );
    }
    throw new Error(rendered);
  }
  let nextRevision: string;
  try {
    nextRevision = validateResourceRevision(body.revision);
  } catch (error) {
    throw new PendingDocumentTerminalError(
      `The ${write.kind} save returned an invalid resource revision.`,
      'invalid_persistence_response',
    );
  }
  const expectedEtag = resourceEtag(write.kind, write.incarnation, nextRevision);
  if (response.headers.get('etag') !== expectedEtag) {
    throw new PendingDocumentTerminalError(
      `The ${write.kind} save returned an invalid revision validator.`,
      'invalid_persistence_response',
    );
  }
  return { ok: true, resourceRevision: nextRevision };
});
const DOCUMENT_DELETE_REQUEST_TIMEOUT_MS = 10_000;
interface ActiveDocumentDelete {
  incarnation: string;
  promise: Promise<void>;
}
const documentDeleteOperations = new Map<string, ActiveDocumentDelete>();

async function backendRequestWithDeadline<T>(
  route: string,
  init: RequestInit,
  operation: string,
  consume: (response: Response) => Promise<T>,
): Promise<T> {
  const status = backend.getStatus();
  if (status.state !== 'connected' || !status.baseUrl || !status.authToken) {
    throw new Error('The Whiteboard backend is not connected.');
  }
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), DOCUMENT_DELETE_REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(new URL(route, status.baseUrl), {
      ...init,
      headers: {
        Authorization: `Bearer ${status.authToken}`,
        ...init.headers,
      },
      signal: controller.signal,
    });
    return await consume(response);
  } catch (error) {
    if (controller.signal.aborted) {
      throw new Error(`${operation} timed out.`);
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

async function deleteBackendDocument(
  documentId: string,
  incarnation: string,
  floor: { whiteboard: number; outline: number },
): Promise<void> {
  await backendRequestWithDeadline(
    `/api/documents/${encodeURIComponent(documentId)}`,
    {
      method: 'DELETE',
      headers: {
        'X-LogosForge-Document-Incarnation': incarnation,
        'X-LogosForge-Whiteboard-Order-Floor': String(floor.whiteboard),
        'X-LogosForge-Outline-Order-Floor': String(floor.outline),
      },
    },
    'Document delete',
    async (response) => {
      void response.body?.cancel();
      if (!response.ok) {
        throw new Error(`Could not delete the document (HTTP ${response.status}).`);
      }
    },
  );
}

async function backendDocumentExists(documentId: string, incarnation: string): Promise<boolean> {
  return backendRequestWithDeadline(
    `/api/documents/${encodeURIComponent(documentId)}/exists`,
    {
      method: 'GET',
      headers: { 'X-LogosForge-Document-Incarnation': incarnation },
    },
    'Document delete reconciliation',
    async (response) => {
      if (!response.ok) {
        void response.body?.cancel();
        throw new Error(`Could not reconcile the document delete (HTTP ${response.status}).`);
      }
      const data = await response.json() as { exists?: unknown };
      if (typeof data.exists !== 'boolean') {
        throw new Error('The document-existence response was invalid.');
      }
      return data.exists;
    },
  );
}

/**
 * Main owns the complete delete transaction. Unlike a renderer-side fetch,
 * this promise survives reload/render-process loss and always releases the
 * persistence tombstone after either commit or authoritative reconciliation.
 */
function deleteDocumentWithPersistenceFence(value: unknown): Promise<void> {
  if (!value || typeof value !== 'object') {
    return Promise.reject(new Error('Invalid document delete request.'));
  }
  const payload = value as { documentId?: unknown; incarnation?: unknown };
  let documentId: string;
  let incarnation: string;
  try {
    documentId = validatePendingDocumentId(payload.documentId);
    incarnation = validatePendingDocumentIncarnation(payload.incarnation);
  } catch (error) {
    return Promise.reject(error);
  }
  const active = documentDeleteOperations.get(documentId);
  if (active) {
    if (active.incarnation !== incarnation) {
      return Promise.reject(
        new Error('A delete for an earlier incarnation of this document id is still settling.'),
      );
    }
    return active.promise;
  }

  const run = runDocumentDeleteTransaction({
    begin: () => documentPersistence.beginDocumentDelete(documentId, incarnation),
    deleteBackend: (floor) => deleteBackendDocument(documentId, incarnation, floor),
    backendDocumentExists: () => backendDocumentExists(documentId, incarnation),
    commit: () => documentPersistence.commitDocumentDelete(documentId, incarnation),
    cancel: () => documentPersistence.cancelDocumentDelete(documentId, incarnation),
  });
  const tracked = run.finally(() => {
    if (documentDeleteOperations.get(documentId)?.promise === tracked) {
      documentDeleteOperations.delete(documentId);
    }
  });
  documentDeleteOperations.set(documentId, { incarnation, promise: tracked });
  return tracked;
}

async function recoverMainDocumentPersistence(): Promise<PendingDocumentConflictRecovery[]> {
  await mainFileWrites.drain();
  while (documentDeleteOperations.size) {
    await Promise.allSettled(
      [...documentDeleteOperations.values()].map((operation) => operation.promise),
    );
  }
  await documentPersistence.drain();
  return documentPersistence.listConflicts();
}

async function waitForMainDocumentPersistence(): Promise<void> {
  await mainFileWrites.drain();
  while (documentDeleteOperations.size) {
    await Promise.allSettled(
      [...documentDeleteOperations.values()].map((operation) => operation.promise),
    );
  }
  await documentPersistence.drainStrict();
}

function isMainRenderer(event: IpcMainInvokeEvent | IpcMainEvent): boolean {
  const win = mainWindow;
  return !!win
    && event.sender === win.webContents
    && event.senderFrame === win.webContents.mainFrame;
}

function requireMainRenderer(event: IpcMainInvokeEvent): void {
  if (!isMainRenderer(event)) throw new Error('Rejected IPC call from an untrusted renderer frame.');
}

// --- Unsaved-changes close/quit protection ---------------------------------
let isDirty = false; // reported by the renderer via file:set-dirty
let allowClose = false; // true once the user has confirmed closing
let isQuitting = false; // a real quit (Cmd/Ctrl+Q) is underway, not just a window close
let closePromptOpen = false; // guard against duplicate prompts
let systemSessionEndInFlight = false;
const closePreparations = new ClosePreparationCoordinator();
const rendererCloseCapabilities = new RendererCloseCapabilities();
const RENDERER_SAVE_TIMEOUT_MS = 15_000;
const fileSaveRequests = new RendererSaveRequestRegistry(RENDERER_SAVE_TIMEOUT_MS);
const autosaveFlushRequests = new RendererSaveRequestRegistry(RENDERER_SAVE_TIMEOUT_MS);

function trackMainOwnedFileWrite<T>(operation: () => Promise<T>): Promise<T> {
  fileSaveRequests.suspendTimeouts();
  autosaveFlushRequests.suspendTimeouts();
  let tracked: Promise<T>;
  try {
    tracked = mainFileWrites.track(operation());
  } catch (error) {
    autosaveFlushRequests.resumeTimeouts();
    fileSaveRequests.resumeTimeouts();
    return Promise.reject(error);
  }
  return tracked.finally(() => {
    autosaveFlushRequests.resumeTimeouts();
    fileSaveRequests.resumeTimeouts();
  });
}

function requestRendererSave(): CorrelatedRendererSaveRequest | null {
  const win = mainWindow;
  if (
    !win
    || !rendererCloseCapabilities.canSaveExternalFile
    || win.isDestroyed()
    || win.webContents.isDestroyed()
  ) return null;

  const request = fileSaveRequests.begin();
  void request.result.then((saved) => {
    if (!saved && mainWindow === win) {
      console.warn('[close] renderer did not confirm a successful save; keeping the window open');
    }
  });

  try {
    win.webContents.send('app:save-before-close', request.requestId);
  } catch (error) {
    console.error('[close] could not request a renderer save:', error);
    fileSaveRequests.complete(request.requestId, false);
  }
  return request;
}

function requestRendererAutosaveFlush(): CorrelatedRendererSaveRequest | null {
  const win = mainWindow;
  if (
    !win
    || !rendererCloseCapabilities.canFlushAutosave
    || win.isDestroyed()
    || win.webContents.isDestroyed()
  ) return null;

  const request = autosaveFlushRequests.begin();
  void request.result.then((saved) => {
    if (!saved && mainWindow === win) {
      console.warn('[close] document autosave did not drain; keeping the window open');
    }
  });

  try {
    win.webContents.send('app:flush-autosave-before-close', request.requestId);
  } catch (error) {
    console.error('[close] could not request a document autosave flush:', error);
    autosaveFlushRequests.complete(request.requestId, false);
  }
  return request;
}

function rendererCanCompleteCloseHandshake(win: BrowserWindow): boolean {
  return mainWindow === win
    && rendererCloseCapabilities.canFlushAutosave
    && !win.isDestroyed()
    && !win.webContents.isDestroyed();
}

async function prepareCloseWithoutRenderer(
  win: BrowserWindow,
  action: 'close' | 'reload',
): Promise<boolean> {
  try {
    console.warn('[close] renderer unavailable; draining main-owned persistence directly');
    if (action === 'reload') {
      // A renderer crash must remain recoverable: settle active/uncertain writes,
      // but preserve terminal ledger entries for the replacement renderer to
      // hydrate. A true close/quit stays strict and cannot erase the RAM ledger.
      await recoverMainDocumentPersistence();
    } else {
      await waitForMainDocumentPersistence();
    }
  } catch (error) {
    console.error('[close] main-owned persistence did not drain; keeping the window open:', error);
    return false;
  }
  if (!ordinaryCloseCanContinue(systemSessionEndInFlight)) return false;
  return confirmContinueAfterRendererFailure(win, action, isDirty);
}

function cancelRendererCloseBarrier(win: BrowserWindow, requestId: number | null): void {
  if (requestId === null || win.isDestroyed() || win.webContents.isDestroyed()) return;
  try {
    win.webContents.send('app:close-cancelled', requestId);
  } catch (error) {
    console.error('[close] could not release the renderer close barrier:', error);
  }
}

async function handleCloseRequest(
  action: 'close' | 'reload' = 'close',
  recoveryToAbandon?: unknown,
): Promise<boolean> {
  const win = mainWindow;
  if (!win || !closePreparations.begin('ordinary')) return false;
  closePromptOpen = true;
  console.log('[close] preparing document persistence');
  let proceed = false;
  let autosaveRequestId: number | null = null;
  try {
    // Establish the renderer barrier first. Its correlated reply contains the
    // synchronous external-file dirty state after every tracked operation has
    // finished, so the prompt decision cannot race a final edit/import.
    const autosaveRequest = requestRendererAutosaveFlush();
    if (autosaveRequest) {
      autosaveRequestId = autosaveRequest.requestId;
      const outcome = await autosaveRequest.outcome;
      proceed = outcome === 'success';
      if (outcome === 'timeout' || !rendererCanCompleteCloseHandshake(win)) {
        proceed = await prepareCloseWithoutRenderer(win, action);
      }
    } else {
      proceed = await prepareCloseWithoutRenderer(win, action);
    }
    if (
      proceed
      && rendererCanCompleteCloseHandshake(win)
      && ordinaryCloseCanContinue(systemSessionEndInFlight)
    ) {
      let choice: SaveChoice = 'dont-save';
      if (isDirty) choice = await confirmSaveChanges(win, 'Save changes before closing?');
      if (!ordinaryCloseCanContinue(systemSessionEndInFlight)) proceed = false;
      else if (choice === 'cancel') proceed = false;
      else if (choice === 'save') {
        const saveRequest = requestRendererSave();
        if (!saveRequest) {
          proceed = await prepareCloseWithoutRenderer(win, action);
        } else {
          const outcome = await saveRequest.outcome;
          proceed = outcome === 'success';
          if (
            outcome === 'timeout'
            || !rendererCanCompleteCloseHandshake(win)
            || !rendererCloseCapabilities.canSaveExternalFile
          ) {
            proceed = await prepareCloseWithoutRenderer(win, action);
          }
        }
      }
    }
    if (!ordinaryCloseCanContinue(systemSessionEndInFlight)) proceed = false;
  } catch (error) {
    console.error('[close] close request failed; keeping the window open:', error);
  } finally {
    closePromptOpen = false;
    closePreparations.end('ordinary');
  }

  if (!proceed) {
    cancelRendererCloseBarrier(win, autosaveRequestId);
    isQuitting = false; // Cancel / failed save → stay open, abort any quit
    return false;
  }
  if (mainWindow !== win) {
    cancelRendererCloseBarrier(win, autosaveRequestId);
    isQuitting = false;
    return false;
  }
  const finalAction = effectiveCloseAction(action, isQuitting);
  if (finalAction === 'reload') {
    try {
      if (recoveryToAbandon && !documentPersistence.hasConflict(recoveryToAbandon)) {
        cancelRendererCloseBarrier(win, autosaveRequestId);
        return false;
      }
      win.webContents.reload();
      // Calling reload successfully transfers control to a fresh renderer. Ack
      // afterwards so a thrown reload cannot erase the only main-owned copy;
      // an exact-version miss leaves a newer recovery for hydration.
      if (recoveryToAbandon) documentPersistence.acknowledgeConflict(recoveryToAbandon);
      return true;
    } catch (error) {
      console.error('[close] reload failed; keeping the window open:', error);
      cancelRendererCloseBarrier(win, autosaveRequestId);
      return false;
    }
  }
  if (recoveryToAbandon) {
    // A quit that overtakes the requested recovery reload must not consume an
    // in-memory rescue entry under the reload-only exemption.
    cancelRendererCloseBarrier(win, autosaveRequestId);
    isQuitting = false;
    return false;
  }
  allowClose = true;
  if (finalAction === 'quit') app.quit();
  else win.close();
  return true;
}

/**
 * Windows does not emit app before-quit/will-quit for shutdown, restart, or
 * logout. Its query-session-end path must therefore establish the renderer
 * autosave barrier itself. It never requests an external-file Save/Save As:
 * the same manuscript is already protected by document autosave, and a native
 * filename prompt would leave the operating-system shutdown waiting on a user.
 */
async function handleSystemSessionEnd(win: BrowserWindow): Promise<void> {
  let autosaveRequestId: number | null = null;
  let rendererOutcome = classifySystemSessionRendererOutcome(null, false);
  try {
    const request = requestRendererAutosaveFlush();
    if (request) {
      autosaveRequestId = request.requestId;
      const outcome = await request.outcome;
      rendererOutcome = classifySystemSessionRendererOutcome(
        outcome,
        rendererCanCompleteCloseHandshake(win),
      );
    }

    const result = await prepareSystemSessionEndPersistence(
      rendererOutcome,
      waitForMainDocumentPersistence,
    );
    if (!result.ready) {
      if (result.reason === 'main-persistence-failure') {
        console.error(
          '[shutdown] Windows session end blocked because main persistence did not drain:',
          result.error,
        );
      } else {
        console.error(`[shutdown] Windows session end blocked: ${result.reason}`);
      }
      cancelRendererCloseBarrier(win, autosaveRequestId);
      return;
    }
    if (mainWindow !== win) {
      cancelRendererCloseBarrier(win, autosaveRequestId);
      return;
    }

    // Bypass the ordinary interactive close path. will-quit performs one final
    // main-owned drain after the renderer has emitted any graceful pagehide copy.
    allowClose = true;
    isQuitting = true;
    app.quit();
  } catch (error) {
    console.error('[shutdown] Windows session end preparation failed:', error);
    cancelRendererCloseBarrier(win, autosaveRequestId);
  }
}

/**
 * A Windows session-end request has priority over starting another ordinary
 * close, but it must not overwrite an ordinary renderer request already in
 * flight. Wait for that owner to finish, then run the non-interactive path.
 */
function queueSystemSessionEnd(win: BrowserWindow): void {
  if (systemSessionEndInFlight) return;
  // Electron does not expose cancellation for an already-open native message
  // box or Save As chooser. Mark priority synchronously so ordinary close will
  // start no further dialog, then take the renderer slot as soon as that one
  // pre-existing interaction settles and the ordinary owner releases it.
  systemSessionEndInFlight = true;
  isQuitting = true;
  void (async () => {
    while (true) {
      await closePreparations.waitUntilIdle();
      if (allowClose || mainWindow !== win) return;
      if (closePreparations.begin('system-session-end')) break;
    }
    try {
      await handleSystemSessionEnd(win);
    } finally {
      closePreparations.end('system-session-end');
    }
  })().finally(() => {
    systemSessionEndInFlight = false;
    if (!allowClose) isQuitting = false;
  });
}

function createWindow(): void {
  allowClose = false;
  isDirty = false;
  rendererCloseCapabilities.clearForRendererLoss();

  mainWindow = new BrowserWindow({
    width: 1100,
    height: 720,
    minWidth: 720,
    minHeight: 480,
    title: 'LogosForge Whiteboard',
    backgroundColor: '#0e0f13',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  if (isProd) {
    void mainWindow.loadFile(path.join(__dirname, '..', 'renderer', 'dist', 'index.html'));
  } else {
    void mainWindow.loadURL(DEV_SERVER_URL);
  }

  const createdWindow = mainWindow;
  createdWindow.webContents.on('did-start-loading', () => {
    if (mainWindow !== createdWindow) return;
    rendererCloseCapabilities.clearForRendererLoss();
    fileSaveRequests.failActive();
    autosaveFlushRequests.failActive();
  });
  createdWindow.webContents.on('render-process-gone', (_event, details) => {
    if (mainWindow !== createdWindow) return;
    rendererCloseCapabilities.clearForRendererLoss();
    fileSaveRequests.failActive();
    autosaveFlushRequests.failActive();
    console.error(`[close] renderer process unavailable (${details.reason})`);
  });
  createdWindow.webContents.on('destroyed', () => {
    if (mainWindow !== createdWindow) return;
    rendererCloseCapabilities.clearForRendererLoss();
    fileSaveRequests.failActive();
    autosaveFlushRequests.failActive();
  });

  // Intercept every close so backend autosave drains even if no external file is dirty.
  mainWindow.on('close', (e) => {
    if (allowClose) return;
    e.preventDefault();
    if (!closePromptOpen) isQuitting = false;
    void handleCloseRequest();
  });

  // Electron does not emit before-quit/will-quit when Windows ends the user
  // session. Prevent that one event until the non-interactive persistence path
  // either reaches a durable terminal state or fails closed.
  mainWindow.on('query-session-end', (event) => {
    if (allowClose) return;
    event.preventDefault();
    queueSystemSessionEnd(createdWindow);
  });

  mainWindow.on('closed', () => {
    rendererCloseCapabilities.clearForRendererLoss();
    fileSaveRequests.failActive();
    autosaveFlushRequests.failActive();
    mainWindow = null;
  });
}

function registerFileIpc(): void {
  ipcMain.handle('document:persist', async (event, payload: unknown) => {
    requireMainRenderer(event);
    try {
      return await documentPersistence.enqueue(payload);
    } catch (error) {
      if (
        error instanceof PendingDocumentRevisionConflictError
        || error instanceof PendingDocumentTerminalError
      ) {
        if (!error.recovery) throw error;
        return {
          ok: false,
          code: error.code,
          status: error.status ?? 409,
          message: error.message,
          ...(error instanceof PendingDocumentRevisionConflictError
            ? {
              currentRevision: error.currentRevision,
              currentEtag: error.currentEtag,
            }
            : {}),
          recovery: error.recovery,
        };
      }
      throw error;
    }
  });
  ipcMain.handle('document:drain-persistence', (event) => {
    requireMainRenderer(event);
    return recoverMainDocumentPersistence();
  });
  ipcMain.on('document:retain-conflict', (event, payload: unknown) => {
    if (!isMainRenderer(event)) {
      event.returnValue = { ok: false };
      return;
    }
    try {
      event.returnValue = documentPersistence.retainConflict(payload);
    } catch (error) {
      console.error('[persistence] rejected conflict snapshot:', error);
      event.returnValue = { ok: false };
    }
  });
  ipcMain.handle('document:acknowledge-conflict', (event, payload: unknown) => {
    requireMainRenderer(event);
    return documentPersistence.acknowledgeConflict(payload);
  });
  ipcMain.handle('document:reload-after-abandoning-conflict', (event, payload: unknown) => {
    requireMainRenderer(event);
    if (!documentPersistence.hasConflict(payload)) return false;
    return handleCloseRequest('reload', payload);
  });
  ipcMain.handle('document:delete-with-fence', (event, payload: unknown) => {
    requireMainRenderer(event);
    return deleteDocumentWithPersistenceFence(payload);
  });
  ipcMain.on('document:persist-on-unload', (event, payload: unknown) => {
    if (!isMainRenderer(event)) {
      event.returnValue = false;
      return;
    }
    try {
      const pending = documentPersistence.enqueue(payload);
      void pending.catch((error) => {
        console.error('[persistence] unload snapshot failed:', error);
      });
      event.returnValue = true;
    } catch (error) {
      console.error('[persistence] rejected unload snapshot:', error);
      event.returnValue = false;
    }
  });

  ipcMain.handle('file:open-dialog', async (event) => {
    requireMainRenderer(event);
    console.log('[ipc] file:open-dialog');
    const result = await openFileDialog(mainWindow);
    if (result.ok && !result.canceled && result.filePath) writablePaths.grant(result.filePath);
    return result;
  });
  ipcMain.handle(
    'file:save-dialog',
    async (event, payload: { content: string; currentPath?: string | null; suggestedName: string }) => {
      requireMainRenderer(event);
      console.log('[ipc] file:save-dialog');
      const currentPath = payload.currentPath && writablePaths.allows(payload.currentPath)
        ? payload.currentPath
        : null;
      const result = await trackMainOwnedFileWrite(() => (
        saveFileDialog(mainWindow, payload.content, currentPath, payload.suggestedName)
      ));
      if (result.ok && !result.canceled && result.filePath) writablePaths.grant(result.filePath);
      return result;
    },
  );
  ipcMain.handle('file:save-to-path', (event, payload: { filePath: string; content: string }) => {
    requireMainRenderer(event);
    console.log('[ipc] file:save-to-path');
    if (!writablePaths.allows(payload.filePath)) {
      return {
        ok: false,
        canceled: false,
        error: 'Save target was not authorized by an Open or Save As dialog.',
      };
    }
    return trackMainOwnedFileWrite(() => saveFileToPath(payload.filePath, payload.content));
  });
  ipcMain.handle('file:confirm-save-changes', (event, payload: { reason?: string }) => {
    requireMainRenderer(event);
    console.log('[ipc] file:confirm-save-changes');
    return confirmSaveChanges(mainWindow, payload?.reason);
  });

  // Import / Export (extends the file system; reuses the same window guard).
  ipcMain.handle('import:open-dialog', (event, payload: { filters: DialogFilter[] }) => {
    requireMainRenderer(event);
    console.log('[ipc] import:open-dialog');
    return openImportDialog(mainWindow, payload.filters);
  });
  ipcMain.handle(
    'export:save-dialog',
    (event, payload: { content: string; suggestedName: string; filters: DialogFilter[] }) => {
      requireMainRenderer(event);
      console.log('[ipc] export:save-dialog');
      return trackMainOwnedFileWrite(() => (
        saveExportDialog(mainWindow, payload.content, payload.suggestedName, payload.filters)
      ));
    },
  );
  ipcMain.handle('import:confirm-mode', (event) => {
    requireMainRenderer(event);
    console.log('[ipc] import:confirm-mode');
    return confirmImportMode(mainWindow);
  });

  ipcMain.on('file:set-dirty', (event, dirty: boolean) => {
    if (!isMainRenderer(event)) return;
    isDirty = !!dirty;
  });
  ipcMain.on('app:set-close-handshake-ready', (event, ready: boolean) => {
    if (!isMainRenderer(event)) return;
    rendererCloseCapabilities.setAutosaveReady(ready === true);
    if (!rendererCloseCapabilities.canFlushAutosave) {
      fileSaveRequests.failActive();
      autosaveFlushRequests.failActive();
    }
  });
  ipcMain.on('app:set-external-save-handshake-ready', (event, ready: boolean) => {
    if (!isMainRenderer(event)) return;
    rendererCloseCapabilities.setExternalSaveReady(ready === true);
    if (!rendererCloseCapabilities.canSaveExternalFile) fileSaveRequests.failActive();
  });
  ipcMain.on('app:close-result', (event, payload: { requestId?: unknown; ok?: unknown }) => {
    if (!isMainRenderer(event)) return;
    if (!Number.isSafeInteger(payload?.requestId)) return;
    fileSaveRequests.complete(payload.requestId as number, payload.ok === true);
  });
  ipcMain.on('app:autosave-flush-result', (event, payload: {
    requestId?: unknown;
    ok?: unknown;
    fileDirty?: unknown;
  }) => {
    if (!isMainRenderer(event)) return;
    if (!Number.isSafeInteger(payload?.requestId)) return;
    if (autosaveFlushRequests.complete(payload.requestId as number, payload.ok === true)) {
      isDirty = payload.fileDirty === true;
    }
  });
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (!mainWindow) return;
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  });

  app.whenReady().then(() => {
    if (bundledMcpPath && installedMcpPath) {
      try {
        installMcpCompanion(bundledMcpPath, installedMcpPath);
      } catch (error) {
        const detail = error instanceof Error ? error.message : String(error);
        console.error(`[mcp] Could not install the local MCP companion: ${detail}`);
      }
    }
    ipcMain.handle('backend:get-status', (event) => {
      requireMainRenderer(event);
      return backend.getStatus();
    });
    backend.onStatus((status: BackendStatus) => {
      mainWindow?.webContents.send('backend:status', status);
    });

    registerFileIpc();
    setAppMenu({
      getWindow: () => mainWindow,
      reloadWindow: async () => { await handleCloseRequest('reload'); },
    });

    createWindow();
    void backend.start();

    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
  });
}

// Quit (Cmd/Ctrl+Q, app.quit) — prompt before tearing the window down.
app.on('before-quit', (e) => {
  if (allowClose || !mainWindow) return;
  e.preventDefault();
  isQuitting = true;
  void handleCloseRequest();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

let shutdownPersistenceDrained = false;
let shutdownPersistenceDraining = false;

async function drainPersistenceBeforeQuit(): Promise<void> {
  await drainPersistenceUntilSettled(waitForMainDocumentPersistence, {
    onFailure: (error) => {
      console.error('[persistence] shutdown drain failed; retrying without stopping the backend:', error);
    },
  });
}

app.on('will-quit', (event) => {
  if (shutdownPersistenceDrained) {
    backend.stop();
    return;
  }
  event.preventDefault();
  if (shutdownPersistenceDraining) return;
  shutdownPersistenceDraining = true;
  void drainPersistenceBeforeQuit()
    .then(() => {
      shutdownPersistenceDrained = true;
      shutdownPersistenceDraining = false;
      app.quit();
    })
    .catch((error) => {
      // The production retry clock does not reject, but keep the backend/window
      // alive if an unexpected scheduler failure ever escapes the loop.
      shutdownPersistenceDraining = false;
      console.error('[persistence] shutdown retry loop failed; quit remains blocked:', error);
    });
});
