import { app, BrowserWindow, Menu, dialog, ipcMain, type IpcMainEvent, type IpcMainInvokeEvent } from 'electron';
import * as path from 'node:path';

import { CoreManager, type CoreStatus } from './core-manager';
import { serveStatic, type StaticServer } from './static-server';
import { openFile, saveFile, openExternal, loadLayout, saveLayout, type DialogFilter } from './file-manager';
import { buildAppMenu } from './menu';

// Match the product name so per-user data lands in %APPDATA%\LogosForge Pro\
// (not the scoped package name @logosforge\pro-desktop). Must precede getPath.
app.setName('LogosForge Pro');

const DEV_SERVER_URL = process.env.VITE_DEV_SERVER_URL ?? 'http://localhost:5173';
const isProd = app.isPackaged || process.argv.includes('--prod');

// Packaged builds ship a self-contained core under resources/core; dev spawns
// the sibling repo's venv (bundledCorePath undefined → CoreManager uses python).
const CORE_EXE = process.platform === 'win32' ? 'logosforge-core.exe' : 'logosforge-core';
const bundledCorePath = app.isPackaged ? path.join(process.resourcesPath, 'core', CORE_EXE) : undefined;
// Packaged builds pin the DB to a stable per-user dir (NOT the install/temp dir,
// which a portable build wipes on exit). Dev leaves it unset (unchanged).
const dbPath = app.isPackaged ? path.join(app.getPath('userData'), 'logosforge.db') : undefined;

let mainWindow: BrowserWindow | null = null;
let rendererServer: StaticServer | null = null;
const core = new CoreManager({ bundledCorePath, dbPath });
let allowClose = false;
let isQuitting = false;
let closeInProgress = false;
let pendingCloseResult: ((saved: boolean) => void) | null = null;

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
    let settled = false;
    const finish = (saved: boolean) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      pendingCloseResult = null;
      resolve(saved);
    };
    const timer = setTimeout(() => finish(false), 15_000);
    pendingCloseResult = finish;
    win.webContents.send('app:save-before-close');
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
      return;
    }
  }
  closeInProgress = false;
  if (mainWindow !== win) return;
  allowClose = true;
  if (isQuitting) app.quit();
  else win.close();
}

async function createWindow(): Promise<void> {
  allowClose = false;
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
    pendingCloseResult?.(false);
    mainWindow = null;
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
  ipcMain.handle('layout:save', (event, p: { projectId: number; layout: unknown }) => {
    requireMainRenderer(event);
    return saveLayout(p.projectId, p.layout);
  });
  ipcMain.on('app:close-result', (event: IpcMainEvent, saved: boolean) => {
    const win = mainWindow;
    if (!win || event.sender !== win.webContents || event.senderFrame !== win.webContents.mainFrame) return;
    pendingCloseResult?.(saved === true);
  });
}

// Single-instance: a second launch focuses the existing window instead of
// starting a second app (which would race for the core port and DB).
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(() => {
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
  if (allowClose || !mainWindow) return;
  event.preventDefault();
  isQuitting = true;
  void handleCloseRequest();
});

app.on('will-quit', () => {
  core.stop();
  rendererServer?.close();
  rendererServer = null;
});
