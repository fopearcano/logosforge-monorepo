#!/usr/bin/env node

/**
 * Pointer-driven acceptance for the packaged LogosForge Pro workspace shell.
 *
 * This launches electron-builder's unpacked Windows application through
 * Playwright's Electron transport. It uses a fresh, isolated profile, drives
 * real mouse input through tear-off/move/resize/minimize/dock interactions,
 * closes through the application's save handshake, and relaunches the same
 * profile to prove that the project-scoped layout was restored from disk.
 *
 * Optional overrides:
 *   LOGOSFORGE_PRO_WORKSPACE_ACCEPTANCE_EXE=C:\...\LogosForge Pro.exe
 *   LOGOSFORGE_PRO_WORKSPACE_ACCEPTANCE_ROOT=C:\...\empty-run-directory
 */

import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { promises as fs } from 'node:fs';
import { createRequire } from 'node:module';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);
const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const DESKTOP_DIR = path.resolve(SCRIPT_DIR, '..');
const REPO_ROOT = path.resolve(DESKTOP_DIR, '..');
const DEFAULT_EXE = path.join(
  DESKTOP_DIR,
  'release',
  'win-unpacked',
  'LogosForge Pro.exe',
);

const STARTUP_TIMEOUT_MS = 90_000;
const UI_TIMEOUT_MS = 30_000;
const CLOSE_TIMEOUT_MS = 20_000;
const PORT_CLOSE_TIMEOUT_MS = 12_000;
const activeSessions = new Set();
const logLines = [];
const usedPorts = new Set();
let acceptanceRoot = null;
let diagnosticsDir = null;
let validatedRemovalRoot = null;
let rootCameFromOverride = false;
let playwrightElectronLoader = null;

function now() {
  return new Date().toISOString();
}

function record(scope, value) {
  const text = String(value ?? '').replace(/\r\n/g, '\n').trimEnd();
  const clipped = text.length > 16_000 ? `${text.slice(0, 16_000)}\n...[entry truncated]` : text;
  const line = `${now()} [${scope}] ${clipped}`;
  logLines.push(line);
  console.log(line);
}

function errorText(error) {
  return error instanceof Error ? (error.stack || error.message) : String(error);
}

function windowsPathKey(value) {
  return path.resolve(value).replace(/[\\/]+$/, '').toLocaleLowerCase('en-US');
}

function assertSamePath(actual, expected, label) {
  assert.equal(
    windowsPathKey(actual),
    windowsPathKey(expected),
    `${label}: expected ${expected}, received ${actual}`,
  );
}

function isSameOrInside(candidate, parent) {
  const relative = path.relative(path.resolve(parent), path.resolve(candidate));
  return relative === '' || (!relative.startsWith('..') && !path.isAbsolute(relative));
}

async function assertFile(filePath, label) {
  let stat;
  try {
    stat = await fs.stat(filePath);
  } catch (error) {
    throw new Error(`${label} is missing at ${filePath}: ${errorText(error)}`);
  }
  assert.ok(stat.isFile(), `${label} is not a file: ${filePath}`);
}

async function canonicalExecutable() {
  const override = process.env.LOGOSFORGE_PRO_WORKSPACE_ACCEPTANCE_EXE?.trim();
  if (override && !path.isAbsolute(override)) {
    throw new Error(`LOGOSFORGE_PRO_WORKSPACE_ACCEPTANCE_EXE must be absolute: ${override}`);
  }
  const requested = override || DEFAULT_EXE;
  await assertFile(requested, 'packaged Pro executable');
  return fs.realpath(requested);
}

async function createIsolationRoot() {
  const override = process.env.LOGOSFORGE_PRO_WORKSPACE_ACCEPTANCE_ROOT?.trim();
  if (!override) {
    const created = await fs.mkdtemp(path.join(os.tmpdir(), 'logosforge-pro-workspace-acceptance-'));
    const canonical = await fs.realpath(created);
    validatedRemovalRoot = canonical;
    rootCameFromOverride = false;
    return canonical;
  }

  if (!path.isAbsolute(override)) {
    throw new Error(`LOGOSFORGE_PRO_WORKSPACE_ACCEPTANCE_ROOT must be absolute: ${override}`);
  }
  const resolved = path.resolve(override);
  const filesystemRoot = path.parse(resolved).root;
  assert.notEqual(
    windowsPathKey(resolved),
    windowsPathKey(filesystemRoot),
    `Refusing to use a filesystem root for packaged workspace acceptance: ${resolved}`,
  );

  const canonicalRepo = await fs.realpath(REPO_ROOT);
  assert.notEqual(
    windowsPathKey(resolved),
    windowsPathKey(canonicalRepo),
    `Refusing to use the repository root for packaged workspace acceptance: ${resolved}`,
  );
  assert.ok(
    !isSameOrInside(canonicalRepo, resolved),
    `Refusing to use an ancestor of the repository: ${resolved}`,
  );
  assert.ok(
    !isSameOrInside(resolved, canonicalRepo),
    `Refusing to use a directory inside the repository: ${resolved}`,
  );

  try {
    const existing = await fs.lstat(resolved);
    assert.ok(existing.isDirectory(), `Acceptance root is not a directory: ${resolved}`);
    assert.ok(!existing.isSymbolicLink(), `Acceptance root cannot be a symlink: ${resolved}`);
    assert.deepEqual(
      await fs.readdir(resolved),
      [],
      `Acceptance root must be empty before the run: ${resolved}`,
    );
  } catch (error) {
    if (error?.code !== 'ENOENT') throw error;
    await fs.mkdir(resolved, { recursive: false });
  }

  const canonical = await fs.realpath(resolved);
  assert.notEqual(
    windowsPathKey(canonical),
    windowsPathKey(canonicalRepo),
    `Refusing to use the repository root for packaged workspace acceptance: ${canonical}`,
  );
  assert.ok(
    !isSameOrInside(canonicalRepo, canonical),
    `Refusing to use an ancestor of the repository: ${canonical}`,
  );
  assert.ok(
    !isSameOrInside(canonical, canonicalRepo),
    `Refusing to use a directory inside the repository: ${canonical}`,
  );
  validatedRemovalRoot = canonical;
  rootCameFromOverride = true;
  return canonical;
}

async function waitFor(predicate, label, timeoutMs = UI_TIMEOUT_MS, intervalMs = 150) {
  const deadline = Date.now() + timeoutMs;
  let lastError = null;
  while (Date.now() < deadline) {
    try {
      if (await predicate()) return;
    } catch (error) {
      lastError = error;
    }
    await delay(intervalMs);
  }
  const suffix = lastError ? ` Last error: ${errorText(lastError)}` : '';
  throw new Error(`Timed out waiting for ${label}.${suffix}`);
}

async function withTimeout(promise, timeoutMs, label) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`${label} exceeded ${timeoutMs}ms`)), timeoutMs);
  });
  try {
    return await Promise.race([promise, timeout]);
  } finally {
    clearTimeout(timer);
  }
}

async function waitVisible(locator, label, timeoutMs = UI_TIMEOUT_MS) {
  const target = locator.first();
  await target.waitFor({ state: 'visible', timeout: timeoutMs });
  record('ui', `visible: ${label}`);
  return target;
}

async function allocateStrictPort() {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const port = await new Promise((resolve, reject) => {
      const server = net.createServer();
      server.unref();
      server.once('error', reject);
      server.listen({ host: '127.0.0.1', port: 0, exclusive: true }, () => {
        const address = server.address();
        const selected = typeof address === 'object' && address ? address.port : 0;
        server.close((error) => (error ? reject(error) : resolve(selected)));
      });
    });
    if (Number.isInteger(port) && port > 0 && !usedPorts.has(port)) {
      usedPorts.add(port);
      return port;
    }
  }
  throw new Error('Could not allocate a unique loopback port.');
}

async function canConnect(port) {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host: '127.0.0.1', port });
    let settled = false;
    const finish = (open) => {
      if (settled) return;
      settled = true;
      socket.destroy();
      resolve(open);
    };
    socket.setTimeout(400, () => finish(false));
    socket.once('connect', () => finish(true));
    socket.once('error', () => finish(false));
  });
}

async function verifyPortClosed(port, label) {
  await waitFor(
    async () => !(await canConnect(port)),
    `${label} core port ${port} to close`,
    PORT_CLOSE_TIMEOUT_MS,
    250,
  );
  record('process', `${label} core port ${port} closed`);
}

async function prepareEnvironment(root, port) {
  const dirs = {
    userData: path.join(root, 'user-data'),
    data: path.join(root, 'data'),
    home: path.join(root, 'home'),
    models: path.join(root, 'models'),
    qaLogs: path.join(root, 'qa', 'logs'),
    qaReports: path.join(root, 'qa', 'reports'),
  };
  await Promise.all(Object.values(dirs).map((directory) => fs.mkdir(directory, { recursive: true })));

  const env = { ...process.env };
  for (const inherited of [
    'ELECTRON_RUN_AS_NODE',
    'LOGOSFORGE_CORE_DIR',
    'LOGOSFORGE_PYTHON',
    'LOGOSFORGE_VOICE_CUDA_DIRS',
    'API_AUTH_TOKEN',
    'OPENAI_API_KEY',
    'ANTHROPIC_API_KEY',
    'OPENROUTER_API_KEY',
    'GH_TOKEN',
    'GITHUB_TOKEN',
  ]) {
    delete env[inherited];
  }
  delete env.LOGOSFORGE_DATA_DIR;
  Object.assign(env, {
    // Keep writer settings and Python's home resolution inside the run root.
    // APPDATA/LOCALAPPDATA deliberately stay intact: repointing those process
    // folders can make current Chromium sandbox startup fail before Electron
    // application code runs. The supported --user-data-dir switch below is
    // consumed before that code and its exact result is asserted immediately.
    HOME: dirs.home,
    USERPROFILE: dirs.home,
    LOGOSFORGE_HOST: '127.0.0.1',
    LOGOSFORGE_PORT: String(port),
    LOGOSFORGE_DB_PATH: path.join(dirs.data, 'logosforge.db'),
    LOGOSFORGE_QA_MODE: '1',
    LOGOSFORGE_FAKE_PROVIDER_PROFILE: 'valid_novel_prose',
    LOGOSFORGE_QA_LOG_DIR: dirs.qaLogs,
    LOGOSFORGE_QA_REPORT_DIR: dirs.qaReports,
    LOGOSFORGE_MODELS_DIR: dirs.models,
    LOGOSFORGE_MCP_CONNECTION_FILE: path.join(dirs.userData, 'mcp-runtime.json'),
    LOGOSFORGE_MCP_LAUNCHER_PATH: path.join(dirs.userData, 'mcp', 'logosforge-mcp.exe'),
    LOGOSFORGE_VOICE_MODEL: path.join(dirs.models, 'acceptance-no-voice-model'),
    LOGOSFORGE_VOICE_DEVICE: 'cpu',
    LOGOSFORGE_VOICE_COMPUTE: 'int8',
  });
  return { env, dirs };
}

async function loadElectronDriver() {
  const module = await import('playwright-core');
  assert.ok(module._electron, 'playwright-core does not export _electron');
  const require = createRequire(import.meta.url);
  const packageJsonPath = require.resolve('playwright-core/package.json');
  const packageJson = JSON.parse(await fs.readFile(packageJsonPath, 'utf8'));
  const loaderPath = path.join(
    path.dirname(packageJsonPath),
    'lib',
    'server',
    'electron',
    'loader.js',
  );
  await assertFile(loaderPath, 'playwright-core Electron loader');
  record('harness', `playwright-core ${packageJson.version ?? 'unknown'} loader: ${loaderPath}`);
  return { electron: module._electron, loaderPath };
}

function attachProcessDiagnostics(session) {
  for (const [streamName, stream] of [['stdout', session.child.stdout], ['stderr', session.child.stderr]]) {
    stream?.on('data', (chunk) => record(`${session.label}:${streamName}`, chunk));
  }
  session.child.once('exit', (code, signal) => {
    record(session.label, `root process exited (pid=${session.pid}, code=${code}, signal=${signal})`);
  });
}

function attachPageDiagnostics(session) {
  session.page.on('console', (message) => {
    const location = message.location();
    const where = location?.url ? ` (${location.url}:${location.lineNumber ?? 0})` : '';
    record(`${session.label}:renderer:${message.type()}`, `${message.text()}${where}`);
  });
  session.page.on('pageerror', (error) => {
    session.pageErrors.push(errorText(error));
    record(`${session.label}:pageerror`, errorText(error));
  });
  session.page.on('crash', () => {
    session.pageErrors.push('renderer crashed');
    record(`${session.label}:renderer`, 'page crashed');
  });
}

async function verifyPackagedRuntime(session, exePath) {
  const expectedResources = path.join(path.dirname(exePath), 'resources');
  const runtime = await session.app.evaluate(({ app, BrowserWindow }) => {
    const windows = BrowserWindow.getAllWindows();
    const preferences = windows[0]?.webContents.getLastWebPreferences() ?? {};
    return {
      isPackaged: app.isPackaged,
      appName: app.getName(),
      appPath: app.getAppPath(),
      execPath: process.execPath,
      resourcesPath: process.resourcesPath,
      userData: app.getPath('userData'),
      sessionData: app.getPath('sessionData'),
      windowCount: windows.length,
      preferences: {
        contextIsolation: preferences.contextIsolation,
        nodeIntegration: preferences.nodeIntegration,
        sandbox: preferences.sandbox,
      },
    };
  });
  assert.equal(runtime.isPackaged, true, `${session.label} did not report app.isPackaged`);
  assert.equal(runtime.appName, 'LogosForge Pro', `${session.label} exposed the wrong app name`);
  assert.equal(runtime.windowCount, 1, `${session.label} must expose exactly one BrowserWindow`);
  assertSamePath(runtime.execPath, exePath, `${session.label} process.execPath`);
  assertSamePath(runtime.resourcesPath, expectedResources, `${session.label} resourcesPath`);
  assertSamePath(runtime.appPath, path.join(expectedResources, 'app.asar'), `${session.label} appPath`);
  assertSamePath(runtime.userData, session.dirs.userData, `${session.label} userData isolation`);
  assertSamePath(runtime.sessionData, session.dirs.userData, `${session.label} sessionData isolation`);
  assert.deepEqual(
    runtime.preferences,
    { contextIsolation: true, nodeIntegration: false, sandbox: true },
    `${session.label} renderer security preferences changed`,
  );
  const globals = await session.page.evaluate(() => ({
    requireType: typeof globalThis.require,
    processType: typeof globalThis.process,
    moduleType: typeof globalThis.module,
  }));
  assert.deepEqual(
    globals,
    { requireType: 'undefined', processType: 'undefined', moduleType: 'undefined' },
    `${session.label} renderer exposed Node globals`,
  );
  session.runtime = runtime;
  record('runtime', `${session.label} verified packaged runtime at ${runtime.execPath}`);
}

async function launchPackagedApp({ electron, exePath, root, label }) {
  assert.ok(playwrightElectronLoader && path.isAbsolute(playwrightElectronLoader));
  const port = await allocateStrictPort();
  const { env, dirs } = await prepareEnvironment(root, port);
  const resources = path.join(path.dirname(exePath), 'resources');
  await assertFile(path.join(resources, 'app.asar'), `${label} app.asar`);
  await assertFile(path.join(resources, 'core', 'logosforge-core.exe'), `${label} packaged core`);

  record(label, `launching ${exePath} on isolated port ${port}`);
  const app = await electron.launch({
    executablePath: exePath,
    args: ['-r', playwrightElectronLoader, `--user-data-dir=${dirs.userData}`],
    cwd: path.dirname(exePath),
    env,
    timeout: STARTUP_TIMEOUT_MS,
  });
  const child = app.process();
  assert.ok(Number.isSafeInteger(child.pid) && child.pid > 0, `${label} has no owned root PID`);
  const session = {
    app,
    page: null,
    child,
    pid: child.pid,
    port,
    label,
    dirs,
    root,
    runtime: null,
    pageErrors: [],
    closed: false,
  };
  activeSessions.add(session);
  attachProcessDiagnostics(session);
  try {
    session.page = await app.firstWindow({ timeout: STARTUP_TIMEOUT_MS });
    attachPageDiagnostics(session);
    await verifyPackagedRuntime(session, exePath);
    return session;
  } catch (error) {
    record(label, `launch verification failed: ${errorText(error)}`);
    throw error;
  }
}

async function waitProReady(session) {
  const { page } = session;
  const workspace = await waitVisible(
    page.locator('[data-screen-label="Studio Dock Workspace"]'),
    `${session.label} Studio workspace`,
    STARTUP_TIMEOUT_MS,
  );
  const projects = await waitVisible(
    page.locator('aside.rail nav').getByRole('button', { name: 'Projects', exact: true }),
    `${session.label} Projects navigator`,
    STARTUP_TIMEOUT_MS,
  );
  await waitFor(
    async () => await projects.isEnabled(),
    `${session.label} workspace layout hydration`,
    STARTUP_TIMEOUT_MS,
  );
  const projectSelect = page.locator('aside.rail > label.field > select').nth(1);
  await waitFor(
    async () => {
      const projectId = Number(await projectSelect.inputValue());
      return Number.isSafeInteger(projectId) && projectId > 0;
    },
    `${session.label} active project`,
    STARTUP_TIMEOUT_MS,
  );
  const projectId = Number(await projectSelect.inputValue());
  record('ui', `${session.label} ready on project ${projectId}`);
  return { workspace, projectSelect, projectId };
}

async function selectPanel(page, name, screenLabel) {
  const button = page.locator('aside.rail nav').getByRole('button', { name, exact: true });
  await waitFor(
    async () => await button.isVisible() && await button.isEnabled(),
    `enabled ${name} navigator`,
    STARTUP_TIMEOUT_MS,
  );
  await button.click();
  const panelId = name.toLocaleLowerCase('en-US');
  const surface = page.locator(`section[data-panel-id="${panelId}"]`).first();
  await waitVisible(surface, `${screenLabel} workspace surface`);
  await waitFor(
    async () => (await button.getAttribute('aria-current')) === 'page',
    `${name} navigator focus`,
  );
  return surface;
}

async function numericInlineBounds(locator) {
  return locator.evaluate((element) => ({
    left: Number.parseFloat(element.style.left),
    top: Number.parseFloat(element.style.top),
    width: Number.parseFloat(element.style.width),
    height: Number.parseFloat(element.style.height),
  }));
}

async function pointerDragBy(page, locator, deltaX, deltaY, label, anchor = 'center') {
  const bounds = await locator.boundingBox();
  assert.ok(bounds && bounds.width > 0 && bounds.height > 0, `${label} has no pointer target bounds`);
  const startX = anchor === 'leading' ? bounds.x + Math.min(28, bounds.width / 3) : bounds.x + bounds.width / 2;
  const startY = bounds.y + bounds.height / 2;
  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.mouse.move(startX + deltaX, startY + deltaY, { steps: 8 });
  await page.mouse.up();
  record('pointer', `${label}: ${deltaX},${deltaY}`);
}

async function exercisePointerWorkspace(session) {
  const { page } = session;
  const { workspace, projectId } = await waitProReady(session);

  const notesSurface = await selectPanel(page, 'Notes', 'Notes Panel');
  assert.equal(await notesSurface.getAttribute('data-dock-region'), 'center');
  const notesTab = await waitVisible(
    page.locator('[data-dock-drop-region="center"]')
      .getByRole('tab', { name: 'Notes', exact: true }),
    'center-docked Notes tab',
  );
  const workspaceBounds = await workspace.boundingBox();
  assert.ok(workspaceBounds && workspaceBounds.width > 520 && workspaceBounds.height > 420);
  const targetPosition = {
    x: Math.max(260, Math.min(workspaceBounds.width - 260, Math.round(workspaceBounds.width * 0.42))),
    y: Math.max(120, Math.min(workspaceBounds.height - 220, Math.round(workspaceBounds.height * 0.28))),
  };
  await notesTab.dragTo(workspace, { targetPosition });
  await waitFor(
    async () => (await notesSurface.getAttribute('data-floating-panel')) === 'true'
      && (await notesSurface.getAttribute('role')) === 'dialog'
      && await notesSurface.isVisible(),
    'pointer tear-off to create a modeless Notes panel',
  );
  record('pointer', 'Notes tab torn off with a real drag gesture');

  const titlebar = await waitVisible(
    page.getByRole('toolbar', { name: 'Move Notes floating panel', exact: true }),
    'Notes floating titlebar',
  );
  const beforeMove = await numericInlineBounds(notesSurface);
  assert.ok(Object.values(beforeMove).every(Number.isFinite));
  const containedPosition = {
    left: Math.max(0, Math.min(16, Math.floor(workspaceBounds.width - beforeMove.width))),
    top: Math.max(0, Math.min(16, Math.floor(workspaceBounds.height - beforeMove.height))),
  };
  const moveDeltaX = containedPosition.left - beforeMove.left;
  const moveDeltaY = containedPosition.top - beforeMove.top;
  assert.ok(
    Math.abs(moveDeltaX) >= 32 || Math.abs(moveDeltaY) >= 32,
    'Tear-off did not leave enough distance for a meaningful pointer move',
  );
  await pointerDragBy(
    page,
    titlebar,
    moveDeltaX,
    moveDeltaY,
    'move Notes floating panel fully into the workspace',
    'leading',
  );
  await waitFor(async () => {
    const current = await numericInlineBounds(notesSurface);
    return Math.abs(current.left - containedPosition.left) <= 2
      && Math.abs(current.top - containedPosition.top) <= 2;
  }, 'pointer-moved Notes bounds fully inside the workspace');

  const resizeHandle = await waitVisible(
    page.getByRole('button', { name: 'Resize Notes floating panel', exact: true }),
    'Notes floating resize handle',
  );
  const resizeHandleBounds = await resizeHandle.boundingBox();
  assert.ok(resizeHandleBounds, 'Notes floating resize handle has no pointer bounds');
  assert.ok(
    resizeHandleBounds.x >= workspaceBounds.x
      && resizeHandleBounds.y >= workspaceBounds.y
      && resizeHandleBounds.x + resizeHandleBounds.width <= workspaceBounds.x + workspaceBounds.width
      && resizeHandleBounds.y + resizeHandleBounds.height <= workspaceBounds.y + workspaceBounds.height,
    `Notes floating resize handle is outside the workspace: ${JSON.stringify({
      resizeHandleBounds,
      workspaceBounds,
    })}`,
  );
  const beforeResize = await numericInlineBounds(notesSurface);
  assert.ok(Number.isFinite(beforeResize.width) && Number.isFinite(beforeResize.height));
  await pointerDragBy(page, resizeHandle, -72, -52, 'resize Notes floating panel');
  await waitFor(async () => {
    const current = await numericInlineBounds(notesSurface);
    return current.width <= beforeResize.width - 48 && current.height <= beforeResize.height - 32;
  }, 'pointer-resized Notes bounds');

  await notesSurface.getByRole('button', { name: 'Minimize Notes', exact: true }).click();
  const restoreNotes = await waitVisible(
    page.getByRole('button', { name: 'Restore Notes', exact: true }),
    'minimized Notes restore control',
  );
  assert.equal(await notesSurface.getAttribute('hidden'), '', 'Minimized Notes remained visible');
  await restoreNotes.click();
  await waitFor(
    async () => await notesSurface.isVisible()
      && (await notesSurface.getAttribute('data-floating-panel')) === 'true',
    'pointer-restored Notes floating panel',
  );

  await notesSurface.getByRole('button', { name: 'Dock Notes to left', exact: true }).click();
  await waitFor(
    async () => (await notesSurface.getAttribute('data-dock-region')) === 'left'
      && (await notesSurface.getAttribute('role')) === 'tabpanel'
      && await notesSurface.isVisible(),
    'pointer-docked Notes in the left workspace region',
  );

  const leftResizer = await waitVisible(
    page.getByRole('separator', { name: 'Resize left workspace dock', exact: true }),
    'left workspace dock resizer',
  );
  const initialLeftSize = Number(await leftResizer.getAttribute('aria-valuenow'));
  assert.ok(Number.isFinite(initialLeftSize) && initialLeftSize > 0);
  await pointerDragBy(page, leftResizer, 64, 0, 'resize left workspace dock');
  await waitFor(
    async () => Number(await leftResizer.getAttribute('aria-valuenow')) >= initialLeftSize + 48,
    'pointer-resized left workspace dock',
  );
  const leftDockSizePx = Number(await leftResizer.getAttribute('aria-valuenow'));

  await page.getByRole('button', { name: 'Collapse left dock', exact: true }).click();
  await waitVisible(
    page.getByRole('button', { name: 'Expand left dock', exact: true }),
    'collapsed left dock strip',
  );
  assert.deepEqual(session.pageErrors, [], 'Renderer errors occurred during pointer workspace exercise');
  record(
    'journey',
    `pointer workspace mutations complete (project=${projectId}, leftDockSize=${leftDockSizePx})`,
  );
  return { projectId, leftDockSizePx };
}

async function verifyPersistedWorkspace(session, expected) {
  const { page } = session;
  const { projectId } = await waitProReady(session);
  assert.equal(projectId, expected.projectId, 'Packaged relaunch resumed the wrong project');
  const expandLeft = await waitVisible(
    page.getByRole('button', { name: 'Expand left dock', exact: true }),
    'persisted collapsed left dock after relaunch',
  );
  const notesSurface = page.locator(
    'section[data-panel-id="notes"][data-dock-region="left"][hidden]',
  );
  await waitFor(
    async () => (await notesSurface.count()) === 1,
    'persisted Notes left-dock placement after relaunch',
    STARTUP_TIMEOUT_MS,
  );
  await expandLeft.click();
  await waitVisible(
    page.locator('section[data-panel-id="notes"][data-dock-region="left"]:not([hidden])'),
    'restored Notes left-dock surface after relaunch',
  );
  const leftResizer = await waitVisible(
    page.getByRole('separator', { name: 'Resize left workspace dock', exact: true }),
    'restored left workspace dock resizer',
  );
  await waitFor(
    async () => Number(await leftResizer.getAttribute('aria-valuenow')) === expected.leftDockSizePx,
    'restored pointer-selected left dock width',
  );
  assert.deepEqual(session.pageErrors, [], 'Renderer errors occurred while restoring the workspace');
  record('journey', 'pointer-authored project layout survived graceful packaged relaunch');
}

async function readSavedLayout(session, expected) {
  const layoutPath = path.join(session.runtime.userData, 'layouts', `${expected.projectId}.json`);
  await waitFor(async () => {
    try {
      return (await fs.stat(layoutPath)).size > 0;
    } catch {
      return false;
    }
  }, 'saved workspace layout file');
  const layout = JSON.parse(await fs.readFile(layoutPath, 'utf8'));
  assert.equal(layout.docks?.left?.collapsed, true, 'Saved left dock was not collapsed');
  assert.equal(layout.docks?.left?.sizePx, expected.leftDockSizePx, 'Saved left dock width changed');
  assert.ok(layout.docks?.left?.panelIds?.includes('notes'), 'Saved left dock lost Notes');
  assert.equal(layout.floatingPanels?.some((entry) => entry?.panelId === 'notes'), false);
  record('file', `verified saved project layout: ${layoutPath}`);
}

async function captureScreenshot(session, name) {
  if (!session?.page || session.page.isClosed()) return;
  const output = path.join(diagnosticsDir, `${session.label}-${name}.png`);
  try {
    await session.page.screenshot({ path: output, fullPage: true, animations: 'disabled' });
    record('diagnostics', `screenshot: ${output}`);
  } catch (error) {
    record('diagnostics', `screenshot failed: ${errorText(error)}`);
  }
}

async function killOwnedTree(session) {
  assert.equal(session.child.pid, session.pid, `${session.label} root PID ownership changed`);
  record(session.label, `fallback taskkill for owned root PID ${session.pid}`);
  try {
    await execFileAsync(
      'taskkill.exe',
      ['/PID', String(session.pid), '/T', '/F'],
      { windowsHide: true, timeout: 15_000 },
    );
  } catch (error) {
    if (session.child.exitCode == null) throw error;
    record(session.label, `taskkill raced with process exit: ${errorText(error)}`);
  }
}

async function closeSession(session, { requireGraceful = true } = {}) {
  if (!session || session.closed) return;
  let graceful = false;
  let closeError = null;
  try {
    const exited = new Promise((resolve, reject) => {
      if (session.child.exitCode != null) {
        resolve();
        return;
      }
      session.child.once('exit', resolve);
      session.child.once('error', reject);
    });
    await session.app.evaluate(({ BrowserWindow }) => {
      const windows = BrowserWindow.getAllWindows();
      if (windows.length !== 1) {
        throw new Error(`Expected one BrowserWindow before close; received ${windows.length}`);
      }
      windows[0].close();
    });
    await withTimeout(exited, CLOSE_TIMEOUT_MS, `${session.label} graceful close`);
    graceful = true;
    record(session.label, 'closed through the real application save handshake');
  } catch (error) {
    closeError = error;
    record(session.label, `graceful close failed: ${errorText(error)}`);
    if (session.child.exitCode == null) await killOwnedTree(session);
  } finally {
    session.closed = true;
    activeSessions.delete(session);
  }
  await verifyPortClosed(session.port, session.label);
  if (requireGraceful && !graceful) {
    throw new Error(`${session.label} required forced teardown: ${errorText(closeError)}`);
  }
}

async function writeFailureDiagnostics(error, metadata) {
  if (!diagnosticsDir) return;
  await fs.mkdir(diagnosticsDir, { recursive: true });
  await fs.writeFile(path.join(diagnosticsDir, 'failure.txt'), `${errorText(error)}\n`, 'utf8');
  await fs.writeFile(path.join(diagnosticsDir, 'acceptance.log'), `${logLines.join('\n')}\n`, 'utf8');
  await fs.writeFile(
    path.join(diagnosticsDir, 'run.json'),
    `${JSON.stringify({ ...metadata, failedAt: now(), error: errorText(error) }, null, 2)}\n`,
    'utf8',
  );
}

async function removeSuccessfulRoot(root) {
  assert.ok(validatedRemovalRoot, 'No validated acceptance root is available for cleanup.');
  const resolved = path.resolve(root);
  assertSamePath(resolved, validatedRemovalRoot, 'acceptance cleanup root');
  const stat = await fs.lstat(resolved);
  assert.ok(stat.isDirectory() && !stat.isSymbolicLink(), `Unsafe cleanup root: ${resolved}`);
  const filesystemRoot = path.parse(resolved).root;
  assert.notEqual(windowsPathKey(resolved), windowsPathKey(filesystemRoot));
  const canonicalRepo = await fs.realpath(REPO_ROOT);
  assert.ok(!isSameOrInside(canonicalRepo, resolved), `Refusing to remove repository ancestor: ${resolved}`);
  assert.ok(!isSameOrInside(resolved, canonicalRepo), `Refusing to remove a directory inside the repository: ${resolved}`);
  if (!rootCameFromOverride) {
    const canonicalTemp = await fs.realpath(os.tmpdir());
    assertSamePath(path.dirname(resolved), canonicalTemp, 'default acceptance temp parent');
    assert.ok(path.basename(resolved).startsWith('logosforge-pro-workspace-acceptance-'));
  }
  await fs.rm(resolved, { recursive: true, force: true });
}

async function main() {
  assert.equal(process.platform, 'win32', 'Packaged workspace acceptance currently runs on Windows.');
  const exePath = await canonicalExecutable();
  const driver = await loadElectronDriver();
  playwrightElectronLoader = driver.loaderPath;
  acceptanceRoot = await createIsolationRoot();
  diagnosticsDir = path.join(acceptanceRoot, 'diagnostics');
  const productRoot = path.join(acceptanceRoot, 'pro');
  await Promise.all([
    fs.mkdir(diagnosticsDir, { recursive: true }),
    fs.mkdir(productRoot, { recursive: true }),
  ]);
  const metadata = { startedAt: now(), acceptanceRoot, exePath };
  record('harness', `isolated run root: ${acceptanceRoot}`);

  let succeeded = false;
  try {
    const first = await launchPackagedApp({
      electron: driver.electron,
      exePath,
      root: productRoot,
      label: 'pro-pointer-1',
    });
    const expected = await exercisePointerWorkspace(first);
    await captureScreenshot(first, 'pointer-layout');
    await closeSession(first);
    await readSavedLayout(first, expected);

    const second = await launchPackagedApp({
      electron: driver.electron,
      exePath,
      root: productRoot,
      label: 'pro-pointer-2',
    });
    await verifyPersistedWorkspace(second, expected);
    await captureScreenshot(second, 'restored-layout');
    await closeSession(second);
    succeeded = true;
    record('harness', 'PASS: packaged Pro pointer workspace journey completed');
  } catch (error) {
    record('harness', `FAIL: ${errorText(error)}`);
    for (const session of [...activeSessions]) await captureScreenshot(session, 'failure');
    for (const session of [...activeSessions]) {
      try {
        await closeSession(session, { requireGraceful: false });
      } catch (cleanupError) {
        record('cleanup', errorText(cleanupError));
      }
    }
    await writeFailureDiagnostics(error, metadata);
    console.error(`Packaged workspace acceptance failed. Diagnostics: ${diagnosticsDir}`);
    throw error;
  } finally {
    if (succeeded) {
      await removeSuccessfulRoot(acceptanceRoot);
      console.log('Packaged workspace acceptance passed; its isolated run root was removed.');
    }
  }
}

main().catch((error) => {
  console.error(errorText(error));
  process.exitCode = 1;
});
