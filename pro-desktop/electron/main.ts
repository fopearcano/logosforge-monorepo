import { app, BrowserWindow, Menu, dialog, ipcMain, screen, type IpcMainEvent, type IpcMainInvokeEvent } from 'electron';
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
import {
  NATIVE_PANEL_WINDOW_CHANNELS,
  nativePanelWindowRequestFromFrameName,
  recoverNativePanelWindowBounds,
  requireNativePanelId,
  requireNativePanelWindowToken,
  type NativePanelId,
  type NativePanelWindowBounds,
  type NativePanelWindowEvent,
  type NativePanelWindowRequest,
} from './native-panel-windows';

// Match the product name so per-user data lands in %APPDATA%\LogosForge Pro\
// (not the scoped package name @logosforge\pro-desktop). Must precede getPath.
app.setName('LogosForge Pro');

const DEV_SERVER_URL = process.env.VITE_DEV_SERVER_URL ?? 'http://localhost:5173';
const isProd = app.isPackaged || process.argv.includes('--prod');
const preloadPath = path.join(__dirname, 'preload.js');

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

interface NativePanelWindowEntry {
  panelId: NativePanelId;
  token: string;
  window: BrowserWindow;
  allowClose: boolean;
  suppressClosedEvent: boolean;
  lastPublishedBounds: string | null;
}

interface PendingNativePanelWindow {
  token: string;
  timer: ReturnType<typeof setTimeout>;
}

const nativePanelWindows = new Map<NativePanelId, NativePanelWindowEntry>();
const pendingNativePanelWindows = new Map<NativePanelId, PendingNativePanelWindow>();
const pendingNativePanelShows = new Map<NativePanelId, { token: string; activate: boolean }>();

function requireMainRenderer(event: IpcMainInvokeEvent): void {
  const win = mainWindow;
  if (!win || event.sender !== win.webContents || event.senderFrame !== win.webContents.mainFrame) {
    throw new Error('Rejected IPC call from an untrusted renderer frame.');
  }
}

function requireNativePanelPayload(payload: unknown): NativePanelWindowRequest {
  if (typeof payload !== 'object'
    || payload === null
    || !('panelId' in payload)
    || !('token' in payload)) {
    throw new Error('A native panel id and window token are required.');
  }
  const candidate = payload as { panelId?: unknown; token?: unknown };
  return {
    panelId: requireNativePanelId(candidate.panelId),
    token: requireNativePanelWindowToken(candidate.token),
  };
}

function sendNativePanelWindowEvent(event: NativePanelWindowEvent): void {
  const win = mainWindow;
  if (!win || win.webContents.isDestroyed() || win.webContents.isLoadingMainFrame()) return;
  win.webContents.send(NATIVE_PANEL_WINDOW_CHANNELS.event, event);
}

function getLiveNativePanelWindow(panelId: NativePanelId): NativePanelWindowEntry | null {
  const entry = nativePanelWindows.get(panelId);
  if (!entry) return null;
  if (!entry.window.isDestroyed()) return entry;
  nativePanelWindows.delete(panelId);
  return null;
}

function recoverNativePanelWindow(entry: NativePanelWindowEntry): NativePanelWindowBounds {
  const bounds = entry.window.getBounds();
  const displays = screen.getAllDisplays();
  const preferredWorkArea = screen.getDisplayMatching(bounds).workArea;
  const recovered = recoverNativePanelWindowBounds(
    bounds,
    displays.map((display) => display.workArea),
    preferredWorkArea,
  );
  if (recovered.x !== bounds.x
    || recovered.y !== bounds.y
    || recovered.width !== bounds.width
    || recovered.height !== bounds.height) {
    entry.window.setBounds(recovered);
  }
  return recovered;
}

function publishNativePanelBounds(entry: NativePanelWindowEntry, force = false): void {
  if (entry.window.isDestroyed()) return;
  const bounds = entry.window.getBounds();
  const serialized = `${bounds.x}:${bounds.y}:${bounds.width}:${bounds.height}`;
  if (!force && entry.lastPublishedBounds === serialized) return;
  entry.lastPublishedBounds = serialized;
  sendNativePanelWindowEvent({
    type: 'bounds-changed',
    panelId: entry.panelId,
    token: entry.token,
    bounds,
  });
}

function focusNativePanelWindow(entry: NativePanelWindowEntry): void {
  if (entry.window.isDestroyed()) return;
  if (entry.window.isMinimized()) entry.window.restore();
  recoverNativePanelWindow(entry);
  if (!entry.window.isVisible()) entry.window.show();
  entry.window.focus();
}

function showNativePanelWindow(entry: NativePanelWindowEntry, activate: boolean): void {
  if (entry.window.isDestroyed()) return;
  recoverNativePanelWindow(entry);
  if (activate) {
    focusNativePanelWindow(entry);
  } else if (!entry.window.isVisible()) {
    entry.window.showInactive();
  }
}

function registerNativePanelWindow(
  panelId: NativePanelId,
  token: string,
  panelWindow: BrowserWindow,
): void {
  const existing = getLiveNativePanelWindow(panelId);
  if (existing) {
    if (existing.token === token) {
      // A repeated request for one acquisition must never create a duplicate.
      panelWindow.destroy();
      focusNativePanelWindow(existing);
      return;
    }
    // A panel can be reacquired before its previous fire-and-forget release
    // reaches main. Retire that exact old generation without publishing a
    // layout-closing event; its stale close IPC cannot match the replacement.
    existing.allowClose = true;
    existing.suppressClosedEvent = true;
    if (!existing.window.isDestroyed()) existing.window.destroy();
  }

  const entry: NativePanelWindowEntry = {
    panelId,
    token,
    window: panelWindow,
    allowClose: false,
    suppressClosedEvent: false,
    lastPublishedBounds: null,
  };
  nativePanelWindows.set(panelId, entry);

  // A panel popup is a renderer-owned DOM surface, not a general browser. It
  // cannot navigate or create further windows even if panel content is faulty.
  panelWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  panelWindow.webContents.on('will-navigate', (event) => event.preventDefault());
  panelWindow.webContents.on('will-attach-webview', (event) => event.preventDefault());

  panelWindow.on('move', () => publishNativePanelBounds(entry));
  panelWindow.on('resize', () => publishNativePanelBounds(entry));
  panelWindow.on('focus', () => {
    sendNativePanelWindowEvent({ type: 'focused', panelId, token });
  });
  panelWindow.on('minimize', () => {
    sendNativePanelWindowEvent({ type: 'minimized', panelId, token });
  });
  panelWindow.on('restore', () => {
    const bounds = recoverNativePanelWindow(entry);
    sendNativePanelWindowEvent({ type: 'restored', panelId, token, bounds });
    publishNativePanelBounds(entry);
  });
  panelWindow.on('close', (event) => {
    if (entry.allowClose) return;
    event.preventDefault();
    sendNativePanelWindowEvent({
      type: 'close-requested',
      panelId,
      token,
      bounds: panelWindow.getBounds(),
    });
  });
  panelWindow.on('closed', () => {
    if (nativePanelWindows.get(panelId) === entry) nativePanelWindows.delete(panelId);
    if (!entry.suppressClosedEvent) {
      sendNativePanelWindowEvent({
        type: 'closed',
        panelId,
        token,
        reason: entry.allowClose ? 'renderer' : 'unexpected',
      });
    }
  });

  recoverNativePanelWindow(entry);
  publishNativePanelBounds(entry);
  const pendingShow = pendingNativePanelShows.get(panelId);
  if (pendingShow?.token === token) {
    pendingNativePanelShows.delete(panelId);
    showNativePanelWindow(entry, pendingShow.activate);
    publishNativePanelBounds(entry, true);
  }
}

function installNativePanelWindowHost(win: BrowserWindow): void {
  win.webContents.setWindowOpenHandler((details) => {
    const request = nativePanelWindowRequestFromFrameName(details.frameName);
    if (details.url !== 'about:blank'
      || request === null
      || closeInProgress
      || isQuitting
      || allowClose) return { action: 'deny' };
    const { panelId, token } = request;

    const existing = getLiveNativePanelWindow(panelId);
    if (existing?.token === token) {
      // Never reveal a still-being-styled window. Once a panel is visible, a
      // duplicate request for this acquisition is an ordinary focus/reuse.
      if (existing.window.isVisible()) focusNativePanelWindow(existing);
      return { action: 'deny' };
    }
    const pending = pendingNativePanelWindows.get(panelId);
    if (pending?.token === token) return { action: 'deny' };
    if (pending) {
      // A newer acquisition supersedes an earlier child that Chromium has not
      // delivered yet. Keep only the newest reservation; the late old child is
      // rejected by the token check in did-create-window below.
      clearTimeout(pending.timer);
      pendingNativePanelWindows.delete(panelId);
      if (pendingNativePanelShows.get(panelId)?.token === pending.token) {
        pendingNativePanelShows.delete(panelId);
      }
    }

    // did-create-window normally follows immediately. The timeout only releases
    // the reservation if Chromium aborts creation before emitting that event.
    const timer = setTimeout(() => {
      if (pendingNativePanelWindows.get(panelId)?.token !== token) return;
      pendingNativePanelWindows.delete(panelId);
      if (pendingNativePanelShows.get(panelId)?.token === token) {
        pendingNativePanelShows.delete(panelId);
      }
    }, 5_000);
    pendingNativePanelWindows.set(panelId, { token, timer });

    return {
      action: 'allow',
      outlivesOpener: false,
      overrideBrowserWindowOptions: {
        modal: false,
        frame: true,
        show: false,
        // Duplicates the shared layout model's native-safe minimums without
        // importing the renderer package into Electron's main process.
        minWidth: 240,
        minHeight: 160,
        maxWidth: 1_920,
        maxHeight: 1_200,
        backgroundColor: '#05070b',
        autoHideMenuBar: true,
        title: 'LogosForge Studio',
        webPreferences: {
          preload: preloadPath,
          contextIsolation: true,
          nodeIntegration: false,
          sandbox: true,
        },
      },
    };
  });

  win.webContents.on('did-create-window', (panelWindow, details) => {
    const request = details.url === 'about:blank'
      ? nativePanelWindowRequestFromFrameName(details.frameName)
      : null;
    if (request === null) {
      panelWindow.destroy();
      return;
    }
    const { panelId, token } = request;
    const pending = pendingNativePanelWindows.get(panelId);
    const reservationIsLive = pending?.token === token;
    const hostIsLive = mainWindow === win
      && !win.isDestroyed()
      && !win.webContents.isDestroyed()
      && !closeInProgress
      && !isQuitting
      && !allowClose;
    if (!reservationIsLive || !hostIsLive) {
      if (reservationIsLive && pending) {
        clearTimeout(pending.timer);
        pendingNativePanelWindows.delete(panelId);
        if (pendingNativePanelShows.get(panelId)?.token === token) {
          pendingNativePanelShows.delete(panelId);
        }
      }
      panelWindow.destroy();
      return;
    }
    clearTimeout(pending.timer);
    pendingNativePanelWindows.delete(panelId);
    registerNativePanelWindow(panelId, token, panelWindow);
  });
}

function recoverAllNativePanelWindows(): void {
  for (const entry of nativePanelWindows.values()) {
    if (!entry.window.isDestroyed()) {
      recoverNativePanelWindow(entry);
      publishNativePanelBounds(entry);
    }
  }
}

function destroyNativePanelWindows(): void {
  for (const pending of pendingNativePanelWindows.values()) clearTimeout(pending.timer);
  pendingNativePanelWindows.clear();
  pendingNativePanelShows.clear();
  for (const entry of nativePanelWindows.values()) {
    entry.allowClose = true;
    entry.suppressClosedEvent = true;
    if (!entry.window.isDestroyed()) entry.window.destroy();
  }
  nativePanelWindows.clear();
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
    // Child panel windows must not get a chance to veto app shutdown or publish
    // layout mutations after the renderer's save barrier has completed.
    destroyNativePanelWindows();
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
      destroyNativePanelWindows();
      await core.stop();
      shutdownPrepared = true;
      closeInProgress = false;
      allowClose = true;
      app.quit();
      return;
    }
    closeInProgress = false;
    destroyNativePanelWindows();
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
      preload: preloadPath,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  installNativePanelWindowHost(mainWindow);

  mainWindow.on('close', (event) => {
    if (allowClose) return;
    event.preventDefault();
    isQuitting = false;
    void handleCloseRequest();
  });

  mainWindow.on('closed', () => {
    pendingCloseResult?.finish(false);
    // Includes renderer crashes and other forced-destruction paths where the
    // normal save-barrier flow could not finish.
    destroyNativePanelWindows();
    mainWindow = null;
    // Fallback for renderer crashes / forced destruction. The normal close
    // path already awaited its ordered clear before the window disappeared.
    if (!allowClose) void core.suspendLiveContext();
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
  ipcMain.handle(NATIVE_PANEL_WINDOW_CHANNELS.show, (event, payload: unknown) => {
    requireMainRenderer(event);
    const { panelId, token } = requireNativePanelPayload(payload);
    const activate = typeof payload === 'object'
      && payload !== null
      && 'activate' in payload
      && (payload as { activate?: unknown }).activate === true;
    const entry = getLiveNativePanelWindow(panelId);
    if (entry?.token === token) {
      showNativePanelWindow(entry, activate);
      publishNativePanelBounds(entry, true);
      return true;
    }
    if (pendingNativePanelWindows.get(panelId)?.token === token) {
      pendingNativePanelShows.set(panelId, { token, activate });
      return true;
    }
    return false;
  });
  ipcMain.handle(NATIVE_PANEL_WINDOW_CHANNELS.focus, (event, payload: unknown) => {
    requireMainRenderer(event);
    const { panelId, token } = requireNativePanelPayload(payload);
    const entry = getLiveNativePanelWindow(panelId);
    if (!entry || entry.token !== token) return false;
    focusNativePanelWindow(entry);
    return true;
  });
  ipcMain.handle(NATIVE_PANEL_WINDOW_CHANNELS.minimize, (event, payload: unknown) => {
    requireMainRenderer(event);
    const { panelId, token } = requireNativePanelPayload(payload);
    const entry = getLiveNativePanelWindow(panelId);
    if (!entry || entry.token !== token) return false;
    if (!entry.window.isMinimized()) entry.window.minimize();
    return true;
  });
  ipcMain.handle(NATIVE_PANEL_WINDOW_CHANNELS.restore, (event, payload: unknown) => {
    requireMainRenderer(event);
    const { panelId, token } = requireNativePanelPayload(payload);
    const entry = getLiveNativePanelWindow(panelId);
    if (!entry || entry.token !== token) return false;
    focusNativePanelWindow(entry);
    return true;
  });
  ipcMain.handle(NATIVE_PANEL_WINDOW_CHANNELS.close, (event, payload: unknown) => {
    requireMainRenderer(event);
    const { panelId, token } = requireNativePanelPayload(payload);
    const entry = getLiveNativePanelWindow(panelId);
    if (!entry || entry.token !== token) {
      const pending = pendingNativePanelWindows.get(panelId);
      if (pending?.token !== token) return false;
      // Release can race the did-create-window notification. Revoking this
      // exact reservation guarantees that the eventual child is destroyed.
      clearTimeout(pending.timer);
      pendingNativePanelWindows.delete(panelId);
      if (pendingNativePanelShows.get(panelId)?.token === token) {
        pendingNativePanelShows.delete(panelId);
      }
      return true;
    }
    // This call is the renderer's acknowledgement that its layout mutation has
    // completed. The acquisition token prevents a delayed release from closing
    // a newer native window for the same panel id.
    entry.allowClose = true;
    entry.window.destroy();
    return true;
  });
  ipcMain.handle(NATIVE_PANEL_WINDOW_CHANNELS.bounds, (event, payload: unknown) => {
    requireMainRenderer(event);
    const { panelId, token } = requireNativePanelPayload(payload);
    const entry = getLiveNativePanelWindow(panelId);
    if (!entry || entry.token !== token) return null;
    return recoverNativePanelWindow(entry);
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
    screen.on('display-removed', recoverAllNativePanelWindows);
    screen.on('display-metrics-changed', recoverAllNativePanelWindows);

    void createWindow();
    void core.start();

    app.on('activate', () => {
      if (!mainWindow) void createWindow();
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
    destroyNativePanelWindows();
    shutdownPrepared = true;
    shutdownInProgress = false;
    app.quit();
  });
});

app.on('will-quit', () => {
  // before-quit normally awaited this. Keep an idempotent fallback for host
  // shutdown paths that do not complete the ordinary window-close protocol.
  destroyNativePanelWindows();
  void core.stop();
  rendererServer?.close();
  rendererServer = null;
});
