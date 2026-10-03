import { app, BrowserWindow, Menu, dialog, ipcMain, type IpcMainEvent, type IpcMainInvokeEvent } from 'electron';
import * as path from 'node:path';

import { CoreManager, type CoreStatus } from './core-manager';
import { serveStatic, type StaticServer } from './static-server';
import {
  openFile,
  saveFile,
  openExternal,
  loadLayout,
  loadLayoutBackup,
  saveLayout,
  loadDesktopSessionState,
  saveLastActiveProjectId,
  drainDesktopSessionSaves,
  type DialogFilter,
} from './file-manager';
import { buildAppMenu } from './menu';
import { installMcpCompanion, mcpCompanionPath, runtimeDescriptorPath } from './mcp-runtime';
import {
  bundledMcpExecutableName,
  resolveBundledCorePath,
  resolveBundledMcpPath,
} from './platform-paths';

// Match the product name so per-user data lands in %APPDATA%\LogosForge Pro\
// (not the scoped package name @logosforge\pro-desktop). Must precede getPath.
app.setName('LogosForge Pro');

const DEV_SERVER_URL = process.env.VITE_DEV_SERVER_URL ?? 'http://localhost:5173';
const isProd = app.isPackaged || process.argv.includes('--prod');

// Packaged builds ship a self-contained core under resources/core; dev spawns
// the sibling repo's venv (bundledCorePath undefined → CoreManager uses python).
const bundledCorePath = app.isPackaged ? resolveBundledCorePath(process.resourcesPath) : undefined;
const bundledMcpPath = app.isPackaged ? resolveBundledMcpPath(process.resourcesPath) : undefined;
// Packaged builds pin the DB to a stable per-user dir (NOT the install/temp dir,
// which a portable build wipes on exit). Dev leaves it unset (unchanged).
const dbPath = app.isPackaged ? path.join(app.getPath('userData'), 'logosforge.db') : undefined;
const mcpRuntimePath = runtimeDescriptorPath(app.getPath('userData'));
const installedMcpPath = mcpCompanionPath(
  app.getPath('userData'),
  bundledMcpExecutableName(process.platform),
);

let mainWindow: BrowserWindow | null = null;
let rendererServer: StaticServer | null = null;
const core = new CoreManager({ production: isProd, bundledCorePath, dbPath, mcpRuntimePath });
let allowClose = false;
let isQuitting = false;
let closeInProgress = false;
let shutdownPrepared = false;
let shutdownInProgress = false;
let nextCloseAttemptId = 1;
let pendingCloseResult: { attemptId: number; finish: (saved: boolean) => void } | null = null;

function requireMainRenderer(event: IpcMainInvokeEvent): void {
  const win = mainWindow;
  if (!win || event.sender !== win.webContents || event.senderFrame !== win.webContents.mainFrame) {
    throw new Error('Rejected IPC call from an untrusted renderer frame.');
  }
}

function requestRendererFlush(): Promise<boolean> {
  const win = mainWindow;
  if (!win || win.webContents.isDestroyed()) return Promise.resolve(true);
  if (win.webContents.isLoadingMainFrame()) return Promise.resolve(true);
  return new Promise((resolve) => {
    const attemptId = nextCloseAttemptId;
    nextCloseAttemptId += 1;
    let settled = false;
    const finish = (saved: boolean) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (pendingCloseResult?.attemptId === attemptId) pendingCloseResult = null;
      resolve(saved);
    };
    const timer = setTimeout(() => finish(false), 15_000);
    pendingCloseResult = { attemptId, finish };
    win.webContents.send('app:save-before-close', attemptId);
  });
}

async function handleCloseRequest(): Promise<void> {
  const win = mainWindow;
  if (!win || closeInProgress) return;
  closeInProgress = true;
  let saved = await requestRendererFlush();
  while (!saved && mainWindow === win) {
    const choice = await dialog.showMessageBox(win, {
      type: 'warning',
      title: 'Unsaved manuscript changes',
      message: 'LogosForge Pro could not save every pending manuscript change.',
      detail: 'Retry after checking the core connection, keep the app open, or explicitly close without saving.',
      buttons: ['Retry Save', 'Keep Open', 'Close Without Saving'],
      defaultId: 0,
      cancelId: 1,
      noLink: true,
    });
    if (choice.response === 0) saved = await requestRendererFlush();
    else if (choice.response === 2) break;
    else {
      closeInProgress = false;
      isQuitting = false;
      if (!win.webContents.isDestroyed()) win.webContents.send('app:close-cancelled');
      return;
    }
  }
  if (mainWindow !== win) {
    closeInProgress = false;
    return;
  }
  // Resume state is host-owned and may still be fsyncing after the renderer's
  // project/save barrier completed. Do not destroy the window or process until
  // every session operation accepted so far has settled.
  await drainDesktopSessionSaves();
  if (isQuitting) {
    await core.stop();
    shutdownPrepared = true;
    closeInProgress = false;
    allowClose = true;
    app.quit();
  } else {
    await core.suspendLiveContext();
    if (mainWindow !== win) {
      closeInProgress = false;
      return;
    }
    // Cmd+Q may arrive while the ordered live-context clear is in flight.
    // before-quit records that intent but cannot start a second close flow, so
    // promote this ordinary window close to a full app shutdown here.
    if (isQuitting) {
      await core.stop();
      shutdownPrepared = true;
      closeInProgress = false;
      allowClose = true;
      app.quit();
      return;
    }
    closeInProgress = false;
    allowClose = true;
    win.close();
  }
}

async function createWindow(): Promise<void> {
  allowClose = false;
  core.resumeLiveContext();
  mainWindow = new BrowserWindow({
    width: 1480,
    height: 920,
    minWidth: 1024,
    minHeight: 640,
    title: 'LogosForge Studio',
    backgroundColor: '#05070b',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  if (isProd) {
    // Serve the built renderer from localhost (NOT file://) so its origin is in
    // the core's desktop-mode CORS allow-list and renderer→core fetches work.
    const rendererDist = path.join(__dirname, '..', 'renderer', 'dist');
    rendererServer = await serveStatic(rendererDist);
    await mainWindow.loadURL(rendererServer.url);
  } else {
    await mainWindow.loadURL(DEV_SERVER_URL);
  }

  mainWindow.on('close', (event) => {
    if (allowClose) return;
    event.preventDefault();
    isQuitting = false;
    void handleCloseRequest();
  });

  mainWindow.on('closed', () => {
    pendingCloseResult?.finish(false);
    mainWindow = null;
    // Fallback for renderer crashes / forced destruction. The normal close
    // path already awaited its ordered clear before the window disappeared.
    if (!allowClose) void core.suspendLiveContext();
  });
}

function registerIpc(): void {
  ipcMain.handle('core:base-url', (event) => {
    requireMainRenderer(event);
    return core.baseUrl;
  });
  ipcMain.handle('core:get-status', (event) => {
    requireMainRenderer(event);
    return core.getStatus();
  });
  ipcMain.handle('live-context:publish', (event, payload: unknown) => {
    requireMainRenderer(event);
    return core.publishLiveContext(payload);
  });
  ipcMain.handle('live-context:clear', (event) => {
    requireMainRenderer(event);
    return core.clearLiveContextFromRenderer();
  });
  ipcMain.handle('file:open', (event, p: { filters?: DialogFilter[] }) => {
    requireMainRenderer(event);
    return openFile(mainWindow, p?.filters);
  });
  ipcMain.handle('file:save', (event, p: { suggestedName?: string; content?: string; contentBase64?: string; mimeType?: string }) => {
    requireMainRenderer(event);
    return saveFile(mainWindow, p);
  });
  ipcMain.handle('shell:open-external', (event, p: { target: string }) => {
    requireMainRenderer(event);
    return openExternal(p.target);
  });
  ipcMain.handle('layout:load', (event, p: { projectId: number }) => {
    requireMainRenderer(event);
    return loadLayout(p.projectId);
  });
  ipcMain.handle('layout:load-backup', (event, p: { projectId: number }) => {
    requireMainRenderer(event);
    return loadLayoutBackup(p.projectId);
  });
  ipcMain.handle('layout:save', (event, p: { projectId: number; layout: unknown; preserveBackup?: boolean }) => {
    requireMainRenderer(event);
    return saveLayout(p.projectId, p.layout, { preserveBackup: p.preserveBackup === true });
  });
  ipcMain.handle('session:load', (event) => {
    requireMainRenderer(event);
    return loadDesktopSessionState();
  });
  ipcMain.handle('session:save-last-project', (event, p?: { projectId: number | null }) => {
    requireMainRenderer(event);
    if (!p || !Object.prototype.hasOwnProperty.call(p, 'projectId')) {
      throw new Error('A last active project id or null is required.');
    }
    return saveLastActiveProjectId(p.projectId);
  });
  ipcMain.on('app:close-result', (event: IpcMainEvent, attemptId: number, saved: boolean) => {
    const win = mainWindow;
    if (!win || event.sender !== win.webContents || event.senderFrame !== win.webContents.mainFrame) return;
    if (!Number.isSafeInteger(attemptId) || pendingCloseResult?.attemptId !== attemptId) return;
    pendingCloseResult.finish(saved === true);
  });
}

// Single-instance: a second GUI launch focuses the existing window instead of
// starting another process that would race for the core port and DB.
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  void app.whenReady().then(() => {
    if (bundledMcpPath) {
      try {
        installMcpCompanion(bundledMcpPath, installedMcpPath);
      } catch (error) {
        const detail = error instanceof Error ? error.message : String(error);
        console.error(`[mcp] Could not install the local MCP companion: ${detail}`);
      }
    }
    registerIpc();
    Menu.setApplicationMenu(buildAppMenu(() => mainWindow));
    core.onStatus((s: CoreStatus) => mainWindow?.webContents.send('core:status', s));

    void createWindow();
    void core.start();

    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) void createWindow();
    });
  });
}

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', (event) => {
  if (shutdownPrepared) return;
  event.preventDefault();
  isQuitting = true;
  if (mainWindow && !allowClose) {
    void handleCloseRequest();
    return;
  }
  if (shutdownInProgress) return;
  shutdownInProgress = true;
  void drainDesktopSessionSaves().then(() => core.stop()).finally(() => {
    shutdownPrepared = true;
    shutdownInProgress = false;
    app.quit();
  });
});

app.on('will-quit', () => {
  // before-quit normally awaited this. Keep an idempotent fallback for host
  // shutdown paths that do not complete the ordinary window-close protocol.
  void core.stop();
  rendererServer?.close();
  rendererServer = null;
});
