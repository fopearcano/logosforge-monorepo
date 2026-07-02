import { app, BrowserWindow, ipcMain } from 'electron';
import * as path from 'node:path';

import { CoreManager, type CoreStatus } from './core-manager';
import { serveStatic, type StaticServer } from './static-server';
import { openFile, saveFile, openExternal, loadLayout, saveLayout, type DialogFilter } from './file-manager';

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

async function createWindow(): Promise<void> {
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

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function registerIpc(): void {
  ipcMain.handle('core:base-url', () => core.baseUrl);
  ipcMain.handle('core:get-status', () => core.getStatus());
  ipcMain.handle('file:open', (_e, p: { filters?: DialogFilter[] }) => openFile(mainWindow, p?.filters));
  ipcMain.handle('file:save', (_e, p: { suggestedName?: string; content?: string; contentBase64?: string; mimeType?: string }) => saveFile(mainWindow, p));
  ipcMain.handle('shell:open-external', (_e, p: { target: string }) => openExternal(p.target));
  ipcMain.handle('layout:load', (_e, p: { projectId: number }) => loadLayout(p.projectId));
  ipcMain.handle('layout:save', (_e, p: { projectId: number; layout: unknown }) => saveLayout(p.projectId, p.layout));
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

app.on('will-quit', () => {
  core.stop();
  rendererServer?.close();
  rendererServer = null;
});
