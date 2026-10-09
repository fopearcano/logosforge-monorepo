#!/usr/bin/env node

/**
 * Pointer-driven acceptance for the packaged LogosForge Pro workspace shell.
 *
 * This launches electron-builder's unpacked Windows, macOS, or Linux application
 * through Playwright's Electron transport. It uses a fresh, isolated profile,
 * drives real mouse input through Canvas Plot and workspace move/resize
 * interactions, closes through the application's save handshake, and
 * relaunches the same profile to prove that project data and the project-scoped
 * layout were restored from disk.
 *
 * Optional overrides:
 *   LOGOSFORGE_PRO_WORKSPACE_ACCEPTANCE_EXE=<absolute packaged executable>
 *   LOGOSFORGE_PRO_WORKSPACE_ACCEPTANCE_ROOT=<absolute empty run directory>
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
const DEFAULT_WINDOWS_EXE = path.join(
  DESKTOP_DIR,
  'release',
  'win-unpacked',
  'LogosForge Pro.exe',
);
const DEFAULT_LINUX_EXE = path.join(
  DESKTOP_DIR,
  'release',
  'linux-unpacked',
  'logosforge-pro',
);

const STARTUP_TIMEOUT_MS = 90_000;
const UI_TIMEOUT_MS = 30_000;
const SAVE_BARRIER_TIMEOUT_MS = 90_000;
const TIMELINE_COMMAND_DISPATCH_TIMEOUT_MS = 20_000;
const TIMELINE_COMMAND_RESPONSE_TIMEOUT_MS = 90_000;
const TIMELINE_ADD_MAX_ATTEMPTS = 2;
const CLOSE_TIMEOUT_MS = 20_000;
const PORT_CLOSE_TIMEOUT_MS = 12_000;
const PROGRESSION_RECOVERY_STORAGE_PREFIX = 'logosforge.pro.progressions.pending.v1:';
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

function pathKey(value) {
  const resolved = path.resolve(value);
  const root = path.parse(resolved).root;
  const withoutTrailingSeparators = resolved === root
    ? resolved
    : resolved.replace(/[\\/]+$/, '');
  return process.platform === 'win32'
    ? withoutTrailingSeparators.toLocaleLowerCase('en-US')
    : withoutTrailingSeparators;
}

function assertSamePath(actual, expected, label) {
  assert.equal(
    pathKey(actual),
    pathKey(expected),
    `${label}: expected ${expected}, received ${actual}`,
  );
}

function packagedResourcesPath(exePath) {
  if (process.platform === 'win32' || process.platform === 'linux') {
    return path.join(path.dirname(exePath), 'resources');
  }
  if (process.platform === 'darwin') {
    return path.resolve(path.dirname(exePath), '..', 'Resources');
  }
  throw new Error(`Unsupported packaged workspace acceptance platform: ${process.platform}`);
}

function packagedCoreExecutableName() {
  return process.platform === 'win32' ? 'logosforge-core.exe' : 'logosforge-core';
}

function packagedMcpExecutableName() {
  return process.platform === 'win32' ? 'logosforge-mcp.exe' : 'logosforge-mcp';
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
  let requested = override;
  if (!requested && process.platform === 'win32') requested = DEFAULT_WINDOWS_EXE;
  if (!requested && process.platform === 'linux') requested = DEFAULT_LINUX_EXE;
  if (!requested && process.platform === 'darwin') {
    const releaseEntries = await fs.readdir(path.join(DESKTOP_DIR, 'release'), {
      withFileTypes: true,
    });
    const candidates = releaseEntries
      .filter((entry) => entry.isDirectory() && /^mac(?:-.+)?$/.test(entry.name))
      .map((entry) => path.join(
        DESKTOP_DIR,
        'release',
        entry.name,
        'LogosForge Pro.app',
        'Contents',
        'MacOS',
        'LogosForge Pro',
      ));
    const existing = [];
    for (const candidate of candidates) {
      try {
        if ((await fs.stat(candidate)).isFile()) existing.push(candidate);
      } catch (error) {
        if (error?.code !== 'ENOENT') throw error;
      }
    }
    assert.equal(
      existing.length,
      1,
      `Expected exactly one unpacked macOS Pro executable; found ${existing.length}.`,
    );
    [requested] = existing;
  }
  assert.ok(requested, `No default packaged executable for ${process.platform}.`);
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
    pathKey(resolved),
    pathKey(filesystemRoot),
    `Refusing to use a filesystem root for packaged workspace acceptance: ${resolved}`,
  );

  const canonicalRepo = await fs.realpath(REPO_ROOT);
  assert.notEqual(
    pathKey(resolved),
    pathKey(canonicalRepo),
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
    pathKey(canonical),
    pathKey(canonicalRepo),
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

async function clickAndWaitForNativeWindowClose(locator, closePromise, label) {
  const click = locator.click({ timeout: UI_TIMEOUT_MS }).catch((error) => {
    const message = error instanceof Error ? error.message : String(error);
    if (!message.includes('Target page, context or browser has been closed')) throw error;
  });
  await Promise.all([
    click,
    withTimeout(closePromise, UI_TIMEOUT_MS, `${label} close`),
  ]);
}

async function waitVisible(locator, label, timeoutMs = UI_TIMEOUT_MS) {
  const target = locator.first();
  await target.waitFor({ state: 'visible', timeout: timeoutMs });
  record('ui', `visible: ${label}`);
  return target;
}

async function clickExactRadarEvidenceAction(radarSurface, cardId, actionName) {
  const deadline = Date.now() + UI_TIMEOUT_MS;
  let lastError = null;
  let attempts = 0;
  while (Date.now() < deadline) {
    attempts += 1;
    const attemptTimeout = Math.max(250, Math.min(2_000, deadline - Date.now()));
    const card = radarSurface.locator(`[data-decision-card-id="${cardId}"]`).first();
    const details = card.locator(`details[data-decision-evidence="${cardId}"]`).first();
    const action = card.getByRole('button', { name: actionName, exact: true }).first();
    try {
      await card.waitFor({ state: 'visible', timeout: attemptTimeout });
      await details.waitFor({ state: 'visible', timeout: attemptTimeout });
      if (!await details.evaluate((element) => element.open)) {
        await details.locator('summary').click({ timeout: attemptTimeout });
      }
      await action.waitFor({ state: 'visible', timeout: attemptTimeout });
      if (!await details.evaluate((element) => element.open)) continue;
      await action.click({ timeout: attemptTimeout });
      record('ui', `clicked exact Radar evidence action after ${attempts} attempt(s): ${actionName}`);
      return;
    } catch (error) {
      lastError = error;
      await delay(75);
    }
  }
  throw new Error(
    `Timed out reopening Radar evidence ${cardId} and clicking ${actionName}.`
      + (lastError ? ` Last error: ${errorText(lastError)}` : ''),
  );
}

function compactUiText(value) {
  return String(value ?? '').replace(/\s+/g, ' ').trim();
}

async function releaseGateUiDiagnostics(page, extra = {}) {
  const safely = async (read, fallback = null) => {
    try {
      return await read();
    } catch (error) {
      return fallback ?? `<unavailable: ${compactUiText(errorText(error))}>`;
    }
  };
  const workspace = page.locator('[data-screen-label="Studio Dock Workspace"]').first();
  const workspaceStatus = page.locator('summary[aria-label^="Workspace status:"]').first();
  const statuses = await safely(
    () => page.getByRole('status').evaluateAll((nodes) => nodes
      .map((node) => (node.textContent || '').replace(/\s+/g, ' ').trim())
      .filter(Boolean)
      .slice(0, 8)),
    [],
  );
  const alerts = await safely(
    () => page.getByRole('alert').evaluateAll((nodes) => nodes
      .map((node) => (node.textContent || '').replace(/\s+/g, ' ').trim())
      .filter(Boolean)
      .slice(0, 8)),
    [],
  );
  return {
    workspacePreset: await safely(() => workspace.getAttribute('data-workspace-preset')),
    workspaceStatus: await safely(() => workspaceStatus.getAttribute('aria-label')),
    saveStatuses: statuses,
    alerts,
    ...extra,
  };
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
    LOGOSFORGE_MCP_LAUNCHER_PATH: path.join(
      dirs.userData,
      'mcp',
      packagedMcpExecutableName(),
    ),
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

function attachPageDiagnostics(session, page = session.page, surface = 'renderer') {
  if (!page || session.diagnosticPages.has(page)) return;
  session.diagnosticPages.add(page);
  page.on('console', (message) => {
    const location = message.location();
    const where = location?.url ? ` (${location.url}:${location.lineNumber ?? 0})` : '';
    record(`${session.label}:${surface}:${message.type()}`, `${message.text()}${where}`);
  });
  page.on('pageerror', (error) => {
    session.pageErrors.push(errorText(error));
    record(`${session.label}:${surface}:pageerror`, errorText(error));
  });
  page.on('crash', () => {
    session.pageErrors.push(`${surface} crashed`);
    record(`${session.label}:${surface}`, 'page crashed');
  });
}

async function verifyPackagedRuntime(session, exePath, allowedWindowCounts = [1]) {
  const expectedResources = packagedResourcesPath(exePath);
  const runtime = await session.app.evaluate(({ app, BrowserWindow }) => {
    const windows = BrowserWindow.getAllWindows();
    const rootWindow = windows.find((candidate) => candidate.webContents.getURL() !== 'about:blank');
    const preferences = rootWindow?.webContents.getLastWebPreferences() ?? {};
    return {
      isPackaged: app.isPackaged,
      appName: app.getName(),
      appPath: app.getAppPath(),
      execPath: process.execPath,
      resourcesPath: process.resourcesPath,
      userData: app.getPath('userData'),
      sessionData: app.getPath('sessionData'),
      hasNoSandboxSwitch: app.commandLine.hasSwitch('no-sandbox'),
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
  assert.ok(
    allowedWindowCounts.includes(runtime.windowCount),
    `${session.label} exposed ${runtime.windowCount} BrowserWindows; expected ${allowedWindowCounts.join(' or ')}`,
  );
  assertSamePath(runtime.execPath, exePath, `${session.label} process.execPath`);
  assertSamePath(runtime.resourcesPath, expectedResources, `${session.label} resourcesPath`);
  assertSamePath(runtime.appPath, path.join(expectedResources, 'app.asar'), `${session.label} appPath`);
  assertSamePath(runtime.userData, session.dirs.userData, `${session.label} userData isolation`);
  assertSamePath(runtime.sessionData, session.dirs.userData, `${session.label} sessionData isolation`);
  assert.equal(
    runtime.hasNoSandboxSwitch,
    false,
    `${session.label} launched Chromium with --no-sandbox`,
  );
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

async function launchPackagedApp({ electron, exePath, root, label, allowedWindowCounts = [1] }) {
  assert.ok(playwrightElectronLoader && path.isAbsolute(playwrightElectronLoader));
  const port = await allocateStrictPort();
  const { env, dirs } = await prepareEnvironment(root, port);
  const resources = packagedResourcesPath(exePath);
  await assertFile(path.join(resources, 'app.asar'), `${label} app.asar`);
  await assertFile(
    path.join(resources, 'core', packagedCoreExecutableName()),
    `${label} packaged core`,
  );

  record(label, `launching ${exePath} on isolated port ${port}`);
  const app = await electron.launch({
    executablePath: exePath,
    chromiumSandbox: true,
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
    diagnosticPages: new Set(),
    closed: false,
  };
  activeSessions.add(session);
  attachProcessDiagnostics(session);
  try {
    session.page = await app.firstWindow({ timeout: STARTUP_TIMEOUT_MS });
    attachPageDiagnostics(session, session.page, 'main-renderer');
    app.on('window', (page) => attachPageDiagnostics(session, page, `panel-${session.diagnosticPages.size}`));
    await verifyPackagedRuntime(session, exePath, allowedWindowCounts);
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

async function selectPanel(page, name, panelId, screenLabel) {
  const button = page.locator('aside.rail nav').getByRole('button', { name, exact: true });
  await waitFor(
    async () => await button.isVisible() && await button.isEnabled(),
    `enabled ${name} navigator`,
    STARTUP_TIMEOUT_MS,
  );
  await button.click();
  const surface = page.locator(`section[data-panel-id="${panelId}"]`).first();
  await waitVisible(surface, `${screenLabel} workspace surface`);
  await waitFor(
    async () => (await button.getAttribute('aria-current')) === 'page',
    `${name} navigator focus`,
  );
  return surface;
}

async function setWorkspaceMode(
  page,
  name,
  preset,
  { timeoutMs = UI_TIMEOUT_MS, waitLabel = `${name} workspace mode` } = {},
) {
  const mode = page
    .getByRole('group', { name: 'Workspace mode', exact: true })
    .getByRole('button', { name, exact: true });
  await waitFor(
    async () => await mode.isVisible() && await mode.isEnabled(),
    `enabled ${name} workspace mode`,
    STARTUP_TIMEOUT_MS,
  );
  if (await mode.getAttribute('aria-pressed') !== 'true') await mode.click();
  const workspace = page.locator('[data-screen-label="Studio Dock Workspace"]');
  try {
    await waitFor(
      async () => await workspace.getAttribute('data-workspace-preset') === preset
        && await mode.getAttribute('aria-pressed') === 'true',
      waitLabel,
      timeoutMs,
    );
  } catch (error) {
    const diagnostics = await releaseGateUiDiagnostics(page, {
      requestedMode: name,
      requestedPreset: preset,
      requestedModePressed: await mode.getAttribute('aria-pressed').catch(() => null),
    });
    throw new Error(`${errorText(error)} UI diagnostics: ${JSON.stringify(diagnostics)}`);
  }
  record('ui', `workspace mode: ${name}`);
}

async function activateBillyDock(page) {
  const workspaceTab = await waitVisible(
    page.getByRole('tab', { name: 'AI Companions', exact: true }),
    'AI Companions workspace tab',
  );
  await workspaceTab.click();
  const surface = await waitVisible(
    page.locator('section[data-panel-id="ai-companions"]'),
    'AI Companions workspace surface',
  );
  const billyTab = await waitVisible(surface.getByTitle('Billy', { exact: true }), 'Billy companion tab');
  if (await billyTab.getAttribute('aria-pressed') !== 'true') await billyTab.click();
  await waitVisible(surface.locator('[data-screen-label="Billy Assistant"]'), 'Billy Assistant');
  return surface;
}

async function waitForNativePanelWindow(session, panelId, label) {
  const prefix = `logosforge-panel:${panelId}:`;
  let panelWindow = null;
  await waitFor(async () => {
    for (const candidate of session.app.windows()) {
      if (candidate.isClosed()) continue;
      try {
        const name = await candidate.evaluate(() => window.name);
        const token = name.startsWith(prefix) ? name.slice(prefix.length) : '';
        if (/^[A-Za-z0-9_-]{16,128}$/.test(token)) {
          panelWindow = candidate;
          return true;
        }
      } catch {
        // A candidate can close while the Electron window list is sampled.
      }
    }
    return false;
  }, label, STARTUP_TIMEOUT_MS);
  attachPageDiagnostics(session, panelWindow, `${panelId}-native-window`);
  return panelWindow;
}

async function settleRendererFrames(page) {
  await page.evaluate(() => new Promise((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(resolve));
  }));
}

async function assertNoRuntimeFaults(session, pages, label) {
  const livePages = [...new Set([session.page, ...pages])]
    .filter((page) => page && !page.isClosed());
  await Promise.all(livePages.map((page) => settleRendererFrames(page)));
  for (const page of livePages) {
    assert.equal(
      await page.locator('[data-runtime-fault]').count(),
      0,
      `${label} displayed a runtime-fault banner`,
    );
  }
  assert.deepEqual(session.pageErrors, [], `${label} emitted a renderer pageerror`);
}

async function verifyBillyNativePanel(session, panelWindow, label) {
  const nativeSurface = panelWindow.locator('section[data-panel-id="ai-companions"]').first();
  await waitFor(
    async () => (await nativeSurface.getAttribute('data-floating-panel')) === 'true'
      && (await nativeSurface.getAttribute('data-native-floating-panel')) === 'true'
      && await nativeSurface.isVisible(),
    label,
    STARTUP_TIMEOUT_MS,
  );
  const billyTab = await waitVisible(
    nativeSurface.getByTitle('Billy', { exact: true }),
    `${label} Billy companion tab`,
  );
  await waitFor(
    async () => await billyTab.getAttribute('aria-pressed') === 'true',
    `${label} persisted Billy selection`,
  );
  await waitVisible(
    nativeSurface.locator('[data-screen-label="Billy Assistant"]'),
    `${label} Billy Assistant`,
  );
  const hiddenQuantum = nativeSurface.locator('[data-screen-label="Quantum Outliner"]');
  await waitFor(
    async () => (await hiddenQuantum.count()) === 1,
    `${label} mounted hidden Quantum companion`,
  );
  assert.equal(
    await hiddenQuantum.isVisible(),
    false,
    `${label} unexpectedly selected Quantum instead of Billy`,
  );
  await assertNoRuntimeFaults(session, [panelWindow], label);
  return nativeSurface;
}

async function packagedCoreJson(session, route, init = {}) {
  const status = await session.page.evaluate(async () => globalThis.logosforge?.getCoreStatus());
  assert.equal(status?.state, 'connected', `${session.label} packaged core is not connected`);
  assert.ok(status.baseUrl && status.authToken, `${session.label} did not expose its authenticated core endpoint`);
  const endpoint = new URL(status.baseUrl);
  assert.equal(endpoint.protocol, 'http:', `${session.label} packaged core must use loopback HTTP`);
  assert.equal(endpoint.hostname, '127.0.0.1', `${session.label} packaged core left the loopback boundary`);
  assert.equal(Number(endpoint.port), session.port, `${session.label} packaged core port changed`);
  const target = new URL(route, endpoint);
  assert.equal(target.origin, endpoint.origin, `Refusing to send the packaged Core bearer token to ${target.origin}`);
  const response = await fetch(target, {
    ...init,
    headers: {
      Accept: 'application/json',
      Authorization: `Bearer ${status.authToken}`,
      ...(init.body == null ? {} : { 'Content-Type': 'application/json' }),
      ...init.headers,
    },
  });
  const raw = await response.text();
  let body = null;
  if (raw) {
    try {
      body = JSON.parse(raw);
    } catch {
      body = raw;
    }
  }
  assert.ok(
    response.ok,
    `${init.method ?? 'GET'} ${route} failed with ${response.status}: ${typeof body === 'string' ? body : JSON.stringify(body)}`,
  );
  return body;
}

async function packagedCoreResponse(session, route, init = {}) {
  const status = await session.page.evaluate(async () => globalThis.logosforge?.getCoreStatus());
  assert.equal(status?.state, 'connected', `${session.label} packaged core is not connected`);
  assert.ok(status.baseUrl && status.authToken, `${session.label} did not expose its authenticated core endpoint`);
  const endpoint = new URL(status.baseUrl);
  assert.equal(endpoint.protocol, 'http:', `${session.label} packaged core must use loopback HTTP`);
  assert.equal(endpoint.hostname, '127.0.0.1', `${session.label} packaged core left the loopback boundary`);
  assert.equal(Number(endpoint.port), session.port, `${session.label} packaged core port changed`);
  const target = new URL(route, endpoint);
  assert.equal(target.origin, endpoint.origin, `Refusing to send the packaged Core bearer token to ${target.origin}`);
  const response = await fetch(target, {
    ...init,
    headers: {
      Accept: 'application/json',
      Authorization: `Bearer ${status.authToken}`,
      ...(init.body == null ? {} : { 'Content-Type': 'application/json' }),
      ...init.headers,
    },
  });
  const raw = await response.text();
  let body = null;
  if (raw) {
    try {
      body = JSON.parse(raw);
    } catch {
      body = raw;
    }
  }
  return { status: response.status, ok: response.ok, headers: response.headers, body };
}

async function seedIntelligenceJourney(session, projectId) {
  const post = (route, body) => packagedCoreJson(session, route, {
    method: 'POST',
    body: JSON.stringify(body),
  });
  const patch = (route, body) => packagedCoreJson(session, route, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });

  await post(`/api/projects/${projectId}/psyke/entries`, {
    name: 'Alice',
    type: 'character',
  });
  await post(`/api/projects/${projectId}/psyke/entries`, {
    name: 'Lonely Relic',
    type: 'object',
  });
  // The mounted Manuscript can observe each POST before the location PATCH.
  // Keep final prose in that same PATCH so it is a visible marker for the exact
  // revision the editor must reconcile before the save-barrier exercise.
  const createdOpening = await post(`/api/projects/${projectId}/scenes`, {
    title: 'Acceptance Opening',
  });
  const createdCrossing = await post(`/api/projects/${projectId}/scenes`, {
    title: 'Acceptance Crossing',
  });
  const crossing = await patch(`/api/projects/${projectId}/scenes/${createdCrossing.id}`, {
    expected_revision: createdCrossing.revision,
    location: 'Castle',
    content: 'Alice studies the silent stonework.',
  });
  // Finalize Opening last. Its unique rendered prose is therefore also a
  // happens-before marker for the complete two-scene fixture.
  const opening = await patch(`/api/projects/${projectId}/scenes/${createdOpening.id}`, {
    expected_revision: createdOpening.revision,
    location: 'Kitchen',
    content: 'Alice waits beside the sealed window.',
  });

  const radar = await packagedCoreJson(session, `/api/projects/${projectId}/decision-radar`);
  const continuity = await packagedCoreJson(session, `/api/projects/${projectId}/continuity`);
  assert.ok(radar.knowledge_graph_available, 'Packaged Decision Radar did not expose Knowledge Graph evidence');
  assert.ok(radar.knowledge_graph_cards.length > 0, 'Packaged Decision Radar returned no Knowledge Graph cards');
  assert.ok(radar.continuity_available, 'Packaged Decision Radar did not expose Semantic Continuity evidence');
  assert.ok(radar.continuity_cards.length > 0, 'Packaged Decision Radar returned no Continuity cards');
  assert.ok(continuity.issues.length > 0, 'Packaged Continuity returned no deterministic issue fixture');
  record(
    'fixture',
    `seeded traceable Graph/Radar/Continuity journey in project ${projectId} (scenes ${opening.id}, ${crossing.id})`,
  );
  return { opening, crossing, radar, continuity };
}

async function executePackagedProgressionCommand(
  session,
  projectId,
  command,
  keySuffix,
) {
  const idempotencyKey = `packaged-progression-${projectId}-${keySuffix}`;
  const result = await packagedCoreJson(
    session,
    `/api/projects/${projectId}/progressions/commands`,
    {
      method: 'POST',
      headers: { 'Idempotency-Key': idempotencyKey },
      body: JSON.stringify(command),
    },
  );
  assert.equal(result.changed, true, `${keySuffix} Progressions command reported no change`);
  assert.equal(result.replayed, false, `${keySuffix} Progressions command unexpectedly replayed`);
  assert.equal(
    result.applied_revision,
    result.progressions.revision,
    `${keySuffix} Progressions command returned mismatched revisions`,
  );
  const receipt = await packagedCoreJson(
    session,
    `/api/projects/${projectId}/progressions/command-receipt`,
    { headers: { 'Idempotency-Key': idempotencyKey } },
  );
  assert.equal(receipt.project_id, projectId, `${keySuffix} Progressions receipt changed project`);
  assert.equal(receipt.command_kind, command.kind, `${keySuffix} Progressions receipt changed command kind`);
  assert.equal(
    receipt.expected_revision,
    command.expected_revision,
    `${keySuffix} Progressions receipt lost its revision guard`,
  );
  assert.equal(
    receipt.applied_revision,
    result.applied_revision,
    `${keySuffix} Progressions receipt changed the committed revision`,
  );
  record(
    'transaction',
    `committed ${command.kind} through Progressions command + durable receipt (${idempotencyKey})`,
  );
  return { result, receipt, idempotencyKey, command: structuredClone(command) };
}

async function assertProgressionReceipt(session, expected, label) {
  const response = await packagedCoreResponse(
    session,
    `/api/projects/${expected.projectId}/progressions/command-receipt`,
    { headers: { 'Idempotency-Key': expected.idempotencyKey } },
  );
  assert.equal(response.status, 200, `${label} receipt lookup failed`);
  assert.equal(response.headers.get('cache-control'), 'no-store', `${label} receipt became cacheable`);
  const receipt = response.body;
  assert.equal(receipt.project_id, expected.projectId, `${label} receipt changed project`);
  assert.match(receipt.request_digest, /^[0-9a-f]{64}$/, `${label} receipt lost its canonical digest`);
  assert.equal(receipt.request_digest, expected.requestDigest, `${label} receipt changed its request digest`);
  assert.equal(receipt.command_kind, expected.commandKind, `${label} receipt changed command kind`);
  assert.equal(receipt.expected_revision, expected.expectedRevision, `${label} receipt lost its revision guard`);
  assert.equal(receipt.applied_revision, expected.appliedRevision, `${label} receipt lost its original applied revision`);
  assert.equal(receipt.original_changed, expected.originalChanged, `${label} receipt lost its original mutation outcome`);
  assert.deepEqual(
    receipt.original_affected_track_ids,
    expected.affectedTrackIds,
    `${label} receipt changed its affected track identities`,
  );
  assert.deepEqual(
    receipt.original_affected_beat_ids,
    expected.affectedBeatIds,
    `${label} receipt changed its affected beat identities`,
  );
  if (expected.createdTrackId != null) {
    assert.equal(receipt.original_created_track_id, expected.createdTrackId, `${label} receipt changed its track identity`);
  }
  if (expected.createdBeatId != null) {
    assert.equal(receipt.original_created_beat_id, expected.createdBeatId, `${label} receipt changed its beat identity`);
  }
  assert.equal(receipt.committed_at, expected.committedAt, `${label} receipt changed its commit timestamp`);
  assert.ok(Number.isFinite(Date.parse(receipt.committed_at)), `${label} receipt commit timestamp is invalid`);
  return receipt;
}

function progressionReceiptExpectation(projectId, committed) {
  return {
    projectId,
    idempotencyKey: committed.idempotencyKey,
    commandKind: committed.command.kind,
    expectedRevision: committed.command.expected_revision,
    appliedRevision: committed.receipt.applied_revision,
    requestDigest: committed.receipt.request_digest,
    originalChanged: committed.receipt.original_changed,
    affectedTrackIds: committed.receipt.original_affected_track_ids,
    affectedBeatIds: committed.receipt.original_affected_beat_ids,
    createdTrackId: committed.receipt.original_created_track_id,
    createdBeatId: committed.receipt.original_created_beat_id,
    committedAt: committed.receipt.committed_at,
  };
}

function waitForRendererGet(page, pathname, label) {
  return page.waitForResponse((response) => {
    const request = response.request();
    return request.method() === 'GET'
      && new URL(response.url()).pathname === pathname
      && response.ok();
  }, { timeout: UI_TIMEOUT_MS }).then((response) => {
    record('live-event', `Progressions invalidation refreshed ${label} (${response.status()})`);
    return response;
  });
}

async function waitForProgressionSnapshot(session, projectId, predicate, label) {
  let snapshot = null;
  await waitFor(async () => {
    snapshot = await packagedCoreJson(session, `/api/projects/${projectId}/progressions`);
    return predicate(snapshot);
  }, label, STARTUP_TIMEOUT_MS);
  return snapshot;
}

async function acceptNextConfirmation(page, action, expectedText, label) {
  let accepted = false;
  const handled = new Promise((resolve, reject) => {
    page.once('dialog', async (dialog) => {
      try {
        assert.equal(dialog.type(), 'confirm', `${label} opened a non-confirmation dialog`);
        assert.ok(dialog.message().includes(expectedText), `${label} confirmation text changed`);
        await dialog.accept();
        accepted = true;
        resolve();
      } catch (error) {
        reject(error);
      }
    });
  });
  await Promise.all([action(), handled]);
  assert.equal(accepted, true, `${label} confirmation was not accepted`);
}

async function exerciseProgressionEditorTransactions(
  session,
  {
    projectId,
    progressionsSurface,
    storyTrackId,
    documentAfterBeatId,
  },
) {
  const { page } = session;
  const entries = await packagedCoreJson(session, `/api/projects/${projectId}/psyke/entries`);
  const alice = entries.find((entry) => entry.name === 'Alice' && entry.type === 'character');
  assert.ok(alice, 'Progressions editor acceptance could not find its Alice PSYKE subject');

  const ambiguousTitle = 'Packaged Character Progression';
  const finalCharacterTitle = 'Packaged Character Progression · Recovered';
  const commandPath = `/api/projects/${projectId}/progressions/commands`;
  const commandPattern = `**${commandPath}`;
  let ambiguousDelivery = null;
  let ambiguousRouteFailure = null;
  const ambiguousHandler = async (route) => {
    try {
      const command = route.request().postDataJSON();
      if (command.kind !== 'create_track' || command.title !== ambiguousTitle) {
        await route.continue();
        return;
      }
      const headers = await route.request().allHeaders();
      const idempotencyKey = headers['idempotency-key'];
      assert.ok(idempotencyKey, 'Ambiguous Progressions delivery omitted its idempotency key');
      const response = await route.fetch();
      const result = await response.json();
      assert.equal(response.status(), 200, 'Ambiguous Progressions delivery did not commit upstream');
      ambiguousDelivery = { command, idempotencyKey, result };
      // The server has committed, but the renderer sees transport failure. Its
      // production recovery path must inspect the durable receipt rather than
      // inventing a fresh key or repeating the mutation.
      await route.abort('failed');
    } catch (error) {
      ambiguousRouteFailure = error;
      await route.abort('failed').catch(() => undefined);
    }
  };
  await page.route(commandPattern, ambiguousHandler);
  try {
    await progressionsSurface.getByRole('button', { name: '+ TRACK', exact: true }).click();
    const editor = await waitVisible(
      progressionsSurface.getByRole('dialog', { name: 'Progression track editor', exact: true }),
      'Progressions character track editor',
    );
    await editor.locator('label').filter({ hasText: 'TITLE' }).locator('input').fill(ambiguousTitle);
    await editor.locator('label').filter({ hasText: 'KIND' }).locator('select').selectOption('character');
    await editor.locator('label').filter({ hasText: 'DESCRIPTION' }).locator('textarea').fill('A PSYKE-bound arc committed through receipt recovery.');
    await editor.locator('label').filter({ hasText: 'COLOR' }).locator('select').selectOption('cyan');
    await editor.locator('label').filter({ hasText: 'PSYKE SUBJECT' }).locator('select').selectOption(String(alice.id));
    await editor.getByRole('button', { name: 'SAVE', exact: true }).click();
    await editor.waitFor({ state: 'hidden', timeout: STARTUP_TIMEOUT_MS });
  } finally {
    await page.unroute(commandPattern, ambiguousHandler);
  }
  if (ambiguousRouteFailure) throw ambiguousRouteFailure;
  assert.ok(ambiguousDelivery, 'Progressions editor did not exercise the ambiguous delivery route');
  assert.equal(ambiguousDelivery.result.changed, true);
  assert.equal(ambiguousDelivery.result.replayed, false);
  const characterTrackId = ambiguousDelivery.result.created_track_id;
  assert.ok(Number.isSafeInteger(characterTrackId) && characterTrackId > 0);
  let snapshot = await waitForProgressionSnapshot(
    session,
    projectId,
    (candidate) => candidate.tracks.some((track) => (
      track.id === characterTrackId
      && track.primary_psyke_entry_id === alice.id
    )),
    'receipt-recovered PSYKE-subject track',
  );
  const ambiguousReceipt = await packagedCoreJson(
    session,
    `/api/projects/${projectId}/progressions/command-receipt`,
    { headers: { 'Idempotency-Key': ambiguousDelivery.idempotencyKey } },
  );
  assert.equal(ambiguousReceipt.command_kind, 'create_track');
  assert.equal(ambiguousReceipt.original_created_track_id, characterTrackId);
  assert.equal(ambiguousReceipt.applied_revision, ambiguousDelivery.result.applied_revision);
  const ambiguousReceiptExpectation = {
    projectId,
    idempotencyKey: ambiguousDelivery.idempotencyKey,
    commandKind: ambiguousDelivery.command.kind,
    expectedRevision: ambiguousDelivery.command.expected_revision,
    appliedRevision: ambiguousDelivery.result.applied_revision,
    requestDigest: ambiguousReceipt.request_digest,
    originalChanged: true,
    affectedTrackIds: ambiguousReceipt.original_affected_track_ids,
    affectedBeatIds: ambiguousReceipt.original_affected_beat_ids,
    createdTrackId: characterTrackId,
    createdBeatId: null,
    committedAt: ambiguousReceipt.committed_at,
  };
  record('transaction', `Progressions editor recovered committed track ${characterTrackId} after an intentionally lost response`);

  // Force a real optimistic-concurrency conflict between the editor's latest
  // read and its update POST, then prove the kept draft succeeds on retry.
  const characterTrackButton = progressionsSurface.locator(
    `[data-progression-track-id="${characterTrackId}"]`,
  );
  await waitVisible(characterTrackButton, 'receipt-recovered character track');
  await characterTrackButton.click();
  await progressionsSurface.getByRole('button', { name: 'EDIT', exact: true }).first().click();
  const updateEditor = await waitVisible(
    progressionsSurface.getByRole('dialog', { name: 'Progression track editor', exact: true }),
    'Progressions track update editor',
  );
  await updateEditor.locator('label').filter({ hasText: 'TITLE' }).locator('input').fill(finalCharacterTitle);
  await updateEditor.locator('label').filter({ hasText: 'DESCRIPTION' }).locator('textarea').fill('A kept draft retried after an exact stale-revision conflict.');
  let staleInterloper = null;
  let staleResponse = null;
  let staleRouteFailure = null;
  const staleHandler = async (route) => {
    try {
      const request = route.request();
      const command = request.postDataJSON();
      if (command.kind !== 'update_track' || command.track_id !== characterTrackId) {
        await route.continue();
        return;
      }
      const originalHeaders = await request.allHeaders();
      const interloperKey = `packaged-progression-${projectId}-stale-interloper`;
      const interloperCommand = {
        kind: 'create_track',
        expected_revision: command.expected_revision,
        track_kind: 'custom',
        title: 'Stale-revision interloper',
        description: 'Created between the editor read and guarded write.',
        color_label: 'amber',
      };
      const interloperResponse = await fetch(request.url(), {
        method: 'POST',
        headers: {
          Accept: 'application/json',
          Authorization: originalHeaders.authorization,
          'Content-Type': 'application/json',
          'Idempotency-Key': interloperKey,
        },
        body: JSON.stringify(interloperCommand),
      });
      const interloperResult = await interloperResponse.json();
      assert.equal(interloperResponse.status, 200, 'Could not create the stale-revision interloper');
      staleInterloper = {
        command: interloperCommand,
        idempotencyKey: interloperKey,
        result: interloperResult,
      };
      const response = await route.fetch();
      staleResponse = {
        status: response.status(),
        body: await response.json(),
        idempotencyKey: originalHeaders['idempotency-key'],
      };
      await route.fulfill({ response });
    } catch (error) {
      staleRouteFailure = error;
      await route.abort('failed').catch(() => undefined);
    }
  };
  await page.route(commandPattern, staleHandler);
  try {
    await updateEditor.getByRole('button', { name: 'SAVE', exact: true }).click();
    await waitFor(
      async () => compactUiText(await progressionsSurface.getByRole('alert').textContent())
        .includes('Progressions changed elsewhere. Your draft was kept'),
      'kept Progressions draft after stale-revision rejection',
    );
  } finally {
    await page.unroute(commandPattern, staleHandler);
  }
  if (staleRouteFailure) throw staleRouteFailure;
  assert.equal(staleResponse?.status, 409, 'Stale Progressions editor write was not rejected');
  assert.equal(staleResponse?.body?.error?.code, 'progression_conflict');
  assert.ok(staleInterloper, 'Stale-revision interloper did not commit');
  assert.ok(staleResponse?.idempotencyKey, 'Stale Progressions editor write omitted its idempotency key');
  const rejectedReceipt = await packagedCoreResponse(
    session,
    `/api/projects/${projectId}/progressions/command-receipt`,
    { headers: { 'Idempotency-Key': staleResponse.idempotencyKey } },
  );
  assert.equal(rejectedReceipt.status, 404, 'Rejected stale Progressions write unexpectedly created a receipt');
  assert.equal(rejectedReceipt.body?.error?.code, 'progression_receipt_not_found');
  assert.equal(
    await updateEditor.locator('label').filter({ hasText: 'TITLE' }).locator('input').inputValue(),
    finalCharacterTitle,
    'Stale Progressions rejection discarded the writer\'s title draft',
  );
  assert.equal(
    await updateEditor.locator('label').filter({ hasText: 'DESCRIPTION' }).locator('textarea').inputValue(),
    'A kept draft retried after an exact stale-revision conflict.',
    'Stale Progressions rejection discarded the writer\'s description draft',
  );
  const repeatedStaleResponse = page.waitForResponse((response) => {
    const request = response.request();
    if (request.method() !== 'POST' || response.status() !== 409) return false;
    if (new URL(response.url()).pathname !== commandPath) return false;
    const command = request.postDataJSON();
    return command.kind === 'update_track' && command.track_id === characterTrackId;
  }, { timeout: UI_TIMEOUT_MS });
  await updateEditor.getByRole('button', { name: 'SAVE', exact: true }).click();
  const repeatedConflict = await repeatedStaleResponse;
  assert.equal(
    (await repeatedConflict.json())?.error?.code,
    'progression_conflict',
    'Repeated stale Progressions SAVE silently rebased instead of failing closed',
  );
  await updateEditor.getByRole('button', { name: 'CANCEL', exact: true }).click();
  await updateEditor.waitFor({ state: 'hidden', timeout: UI_TIMEOUT_MS });

  // A successful retry requires an explicit reread/reopen of the authoritative
  // row. The writer then reapplies the kept draft against that fresh revision.
  await characterTrackButton.click();
  await progressionsSurface.getByRole('button', { name: 'EDIT', exact: true }).first().click();
  const refreshedUpdateEditor = await waitVisible(
    progressionsSurface.getByRole('dialog', { name: 'Progression track editor', exact: true }),
    'Progressions track editor after explicit stale reread',
  );
  await refreshedUpdateEditor.locator('label').filter({ hasText: 'TITLE' }).locator('input').fill(finalCharacterTitle);
  await refreshedUpdateEditor.locator('label').filter({ hasText: 'DESCRIPTION' }).locator('textarea').fill('A kept draft retried after an exact stale-revision conflict.');
  await refreshedUpdateEditor.getByRole('button', { name: 'SAVE', exact: true }).click();
  await refreshedUpdateEditor.waitFor({ state: 'hidden', timeout: STARTUP_TIMEOUT_MS });
  snapshot = await waitForProgressionSnapshot(
    session,
    projectId,
    (candidate) => candidate.tracks.some((track) => (
      track.id === characterTrackId && track.title === finalCharacterTitle
    )),
    'retried Progressions track update',
  );
  const interloperTrackId = staleInterloper.result.created_track_id;
  assert.ok(Number.isSafeInteger(interloperTrackId) && interloperTrackId > 0);
  const interloperReceipt = await packagedCoreJson(
    session,
    `/api/projects/${projectId}/progressions/command-receipt`,
    { headers: { 'Idempotency-Key': staleInterloper.idempotencyKey } },
  );
  const interloperReceiptExpectation = {
    projectId,
    idempotencyKey: staleInterloper.idempotencyKey,
    commandKind: staleInterloper.command.kind,
    expectedRevision: staleInterloper.command.expected_revision,
    appliedRevision: interloperReceipt.applied_revision,
    requestDigest: interloperReceipt.request_digest,
    originalChanged: true,
    affectedTrackIds: interloperReceipt.original_affected_track_ids,
    affectedBeatIds: interloperReceipt.original_affected_beat_ids,
    createdTrackId: interloperTrackId,
    createdBeatId: null,
    committedAt: interloperReceipt.committed_at,
  };

  const interloperButton = progressionsSurface.locator(
    `[data-progression-track-id="${interloperTrackId}"]`,
  );
  await waitVisible(interloperButton, 'temporary stale-revision track');
  await interloperButton.click();
  await acceptNextConfirmation(
    page,
    () => progressionsSurface.getByRole('button', { name: 'DELETE', exact: true }).first().click(),
    'Delete this progression track',
    'Progressions track delete',
  );
  await waitForProgressionSnapshot(
    session,
    projectId,
    (candidate) => !candidate.tracks.some((track) => track.id === interloperTrackId),
    'UI-deleted Progressions track',
  );

  const storyTrackButton = progressionsSurface.locator(`[data-progression-track-id="${storyTrackId}"]`);
  await waitVisible(storyTrackButton, 'story track before document-anchor editing');
  await storyTrackButton.click();
  await progressionsSurface.getByRole('button', { name: '+ BEAT', exact: true }).click();
  let beatEditor = await waitVisible(
    progressionsSurface.getByRole('dialog', { name: 'Progression beat editor', exact: true }),
    'document-anchor beat editor',
  );
  const documentBeatInitialText = 'A document checkpoint preserves the private drafting reference.';
  const documentBeatText = 'A revised document checkpoint preserves the private drafting reference.';
  await beatEditor.locator('label').filter({ hasText: 'BEAT' }).locator('textarea').fill(documentBeatInitialText);
  await beatEditor.locator('label').filter({ hasText: 'ANCHOR' }).locator('select').selectOption('document_block');
  await beatEditor.locator('label').filter({ hasText: 'DOCUMENT REFERENCE' }).locator('input').fill('drafter:packaged-acceptance:block-7');
  await beatEditor.locator('label').filter({ hasText: 'DISPLAY LABEL' }).locator('input').fill('Private drafting block');
  await beatEditor.getByRole('button', { name: 'SAVE', exact: true }).click();
  await beatEditor.waitFor({ state: 'hidden', timeout: STARTUP_TIMEOUT_MS });
  snapshot = await waitForProgressionSnapshot(
    session,
    projectId,
    (candidate) => candidate.tracks.some((track) => (
      track.id === storyTrackId
      && track.beats.some((beat) => beat.text === documentBeatInitialText)
    )),
    'UI-created document-anchored Progressions beat',
  );
  let storyTrack = snapshot.tracks.find((track) => track.id === storyTrackId);
  const documentBeatId = storyTrack?.beats.find((beat) => beat.text === documentBeatInitialText)?.id;
  assert.ok(Number.isSafeInteger(documentBeatId) && documentBeatId > 0);
  let documentBeatButton = progressionsSurface.locator(`[data-progression-beat-id="${documentBeatId}"]`);
  await waitVisible(documentBeatButton, 'document-anchored Progressions beat');
  await documentBeatButton.locator('..').getByRole('button', { name: 'EDIT', exact: true }).click();
  beatEditor = await waitVisible(
    progressionsSurface.getByRole('dialog', { name: 'Progression beat editor', exact: true }),
    'Progressions beat update editor',
  );
  await beatEditor.locator('label').filter({ hasText: 'BEAT' }).locator('textarea').fill(documentBeatText);
  await beatEditor.locator('label').filter({ hasText: 'DISPLAY LABEL' }).locator('input').fill('Revised private drafting block');
  await beatEditor.getByRole('button', { name: 'SAVE', exact: true }).click();
  await beatEditor.waitFor({ state: 'hidden', timeout: STARTUP_TIMEOUT_MS });

  await progressionsSurface.getByRole('button', { name: '+ BEAT', exact: true }).click();
  beatEditor = await waitVisible(
    progressionsSurface.getByRole('dialog', { name: 'Progression beat editor', exact: true }),
    'disposable Progressions beat editor',
  );
  const disposableBeatText = 'Disposable UI beat';
  await beatEditor.locator('label').filter({ hasText: 'BEAT' }).locator('textarea').fill(disposableBeatText);
  await beatEditor.getByRole('button', { name: 'SAVE', exact: true }).click();
  await beatEditor.waitFor({ state: 'hidden', timeout: STARTUP_TIMEOUT_MS });
  snapshot = await waitForProgressionSnapshot(
    session,
    projectId,
    (candidate) => candidate.tracks.some((track) => (
      track.id === storyTrackId
      && track.beats.some((beat) => beat.text === disposableBeatText)
    )),
    'UI-created disposable Progressions beat',
  );
  storyTrack = snapshot.tracks.find((track) => track.id === storyTrackId);
  const disposableBeatId = storyTrack?.beats.find((beat) => beat.text === disposableBeatText)?.id;
  assert.ok(Number.isSafeInteger(disposableBeatId) && disposableBeatId > 0);
  const disposableBeatButton = progressionsSurface.locator(`[data-progression-beat-id="${disposableBeatId}"]`);
  await waitVisible(disposableBeatButton, 'disposable Progressions beat');
  await acceptNextConfirmation(
    page,
    () => disposableBeatButton.locator('..').getByRole('button', { name: 'DELETE', exact: true }).click(),
    'Delete this progression beat',
    'Progressions beat delete',
  );
  await waitForProgressionSnapshot(
    session,
    projectId,
    (candidate) => candidate.tracks.every((track) => (
      !track.beats.some((beat) => beat.id === disposableBeatId)
    )),
    'UI-deleted Progressions beat',
  );

  documentBeatButton = progressionsSurface.locator(`[data-progression-beat-id="${documentBeatId}"]`);
  await waitVisible(documentBeatButton, 'document beat before UI reorder');
  await documentBeatButton.locator('..').getByRole('button', { name: 'Move beat earlier', exact: true }).click();
  snapshot = await waitForProgressionSnapshot(
    session,
    projectId,
    (candidate) => {
      const candidateTrack = candidate.tracks.find((track) => track.id === storyTrackId);
      return candidateTrack?.beats.findIndex((beat) => beat.id === documentBeatId)
        === candidateTrack?.beats.findIndex((beat) => beat.id === documentAfterBeatId) + 1;
    },
    'UI-reordered Progressions beats',
  );

  const recoveredCharacterButton = progressionsSurface.locator(
    `[data-progression-track-id="${characterTrackId}"]`,
  );
  await recoveredCharacterButton.click();
  await progressionsSurface.getByRole('button', { name: 'Move track earlier', exact: true }).click();
  snapshot = await waitForProgressionSnapshot(
    session,
    projectId,
    (candidate) => candidate.tracks[0]?.id === characterTrackId
      && candidate.tracks[1]?.id === storyTrackId,
    'UI-reordered Progressions tracks',
  );
  storyTrack = snapshot.tracks.find((track) => track.id === storyTrackId);
  const characterTrack = snapshot.tracks.find((track) => track.id === characterTrackId);
  assert.ok(storyTrack && characterTrack);
  const documentBeat = storyTrack.beats.find((beat) => beat.id === documentBeatId);
  assert.deepEqual(
    documentBeat,
    {
      ...documentBeat,
      text: documentBeatText,
      anchor_kind: 'document_block',
      scene_id: null,
      anchor_ref: 'drafter:packaged-acceptance:block-7',
      anchor_label: 'Revised private drafting block',
    },
    'Progressions editor did not preserve its updated document anchor',
  );
  assert.equal(characterTrack.kind, 'character');
  assert.equal(characterTrack.primary_psyke_entry_id, alice.id);
  assert.equal(characterTrack.primary_psyke_entry_name, 'Alice');
  assert.equal(characterTrack.primary_psyke_entry_type, 'character');
  record('journey', 'real Progressions editor exercised PSYKE binding, create/update/delete/reorder, stale conflict retry, and ambiguous receipt recovery');
  return {
    snapshot,
    characterTrackId,
    characterTrackTitle: finalCharacterTitle,
    characterSubjectId: alice.id,
    documentBeatId,
    documentBeatText,
    documentAnchorRef: documentBeat.anchor_ref,
    documentAnchorLabel: documentBeat.anchor_label,
    receiptExpectations: [ambiguousReceiptExpectation, interloperReceiptExpectation],
  };
}

async function decisionCard(surface, sourceLabel) {
  const card = surface.locator('[data-decision-card-id]').filter({ hasText: sourceLabel }).first();
  await waitVisible(card, `${sourceLabel} Decision Radar card`);
  const id = await card.getAttribute('data-decision-card-id');
  assert.ok(id, `${sourceLabel} Decision Radar card has no stable identity`);
  return { card, id };
}

async function exerciseIntelligenceShell(session) {
  const { page } = session;
  const { projectId } = await waitProReady(session);
  const seeded = await seedIntelligenceJourney(session, projectId);
  // Fixture writes happen out-of-band through the packaged Core. Rehydrate the
  // renderer explicitly so this setup does not depend on when its event poll
  // subscribed or which intermediate scene revision it observed.
  await page.reload({ waitUntil: 'domcontentloaded', timeout: STARTUP_TIMEOUT_MS });
  const rehydrated = await waitProReady(session);
  assert.equal(rehydrated.projectId, projectId, 'Packaged renderer changed project while rehydrating its fixture');
  record('fixture', `rehydrated renderer on finalized project ${projectId}`);

  const manuscript = await selectPanel(page, 'Manuscript', 'manuscript', 'Manuscript Editor');
  await setWorkspaceMode(page, 'FOCUS', 'focus');
  const openingHost = manuscript.locator(`[data-scene-id="${seeded.opening.id}"]`).first();
  await openingHost.waitFor({ state: 'attached', timeout: UI_TIMEOUT_MS });
  await openingHost.scrollIntoViewIfNeeded({ timeout: UI_TIMEOUT_MS });
  await waitVisible(openingHost, 'seeded manuscript scene');
  const seededProse = openingHost.locator('[data-prose-static], [data-prose]').first();
  // SceneEditor publishes this prose only after synchronously advancing its
  // revision guard to the finalized fixture DTO.
  await waitFor(
    async () => await seededProse.innerText() === seeded.opening.content,
    'seeded manuscript scene revision',
  );
  const staticProse = openingHost.getByRole('button', {
    name: `Activate prose editor for ${seeded.opening.title}`,
    exact: true,
  });
  if (await staticProse.count() > 0 && await staticProse.isVisible()) await staticProse.click();
  const prose = await waitVisible(openingHost.locator('[data-prose]'), 'live seeded prose editor');
  const barrierText = `${seeded.opening.content}\n\nPackaged shell save barrier ${Date.now()}.`;
  await prose.fill(barrierText);
  await setWorkspaceMode(page, 'COCKPIT', 'cockpit', {
    timeoutMs: SAVE_BARRIER_TIMEOUT_MS,
    waitLabel: 'COCKPIT workspace mode after the manuscript save barrier',
  });

  let radarSurface = await selectPanel(page, 'Decision Radar', 'decision-radar', 'Decision Radar');
  const savedOpening = await packagedCoreJson(
    session,
    `/api/projects/${projectId}/scenes/${seeded.opening.id}`,
  );
  assert.equal(
    savedOpening.content,
    barrierText,
    'Workspace navigation crossed the save barrier before the pending manuscript edit was saved',
  );
  await waitVisible(radarSurface.getByText('GRAPH ONLINE', { exact: true }), 'Decision Radar Graph availability');
  await waitVisible(radarSurface.getByText('CONTINUITY ONLINE', { exact: true }), 'Decision Radar Continuity availability');

  const graphUi = await decisionCard(radarSurface, 'KNOWLEDGE GRAPH');
  const graphCard = seeded.radar.knowledge_graph_cards.find((candidate) => candidate.id === graphUi.id);
  assert.ok(graphCard?.graph_focus_key, `Displayed graph card ${graphUi.id} is not traceable to an exact graph node`);
  await graphUi.card.getByRole('button', { name: 'OPEN GRAPH EVIDENCE', exact: true }).click();
  const graphSurface = await waitVisible(
    page.locator('section[data-panel-id="graph"]'),
    'Knowledge Graph production workspace surface',
  );
  const graphCanvas = await waitVisible(
    graphSurface.locator('[data-knowledge-graph-canvas="true"]'),
    'focused Knowledge Graph canvas',
  );
  await waitFor(async () => (
    await graphCanvas.getAttribute('data-focus-key') === graphCard.graph_focus_key
      && await graphCanvas.getAttribute('data-view-mode') === graphCard.graph_view_mode
      && await graphCanvas.getAttribute('data-evidence-scope') === (
        graphCard.graph_include_inferred ? 'inferred_and_confirmed' : 'confirmed_only'
      )
  ), 'exact Decision Radar Knowledge Graph deep link');
  await waitVisible(
    graphSurface.locator('section[aria-label^="Selected graph node "]'),
    'focused Knowledge Graph inspector',
  );
  await waitFor(async () => page.evaluate((expectedKey) => {
    const active = document.activeElement;
    return active instanceof HTMLElement
      && active.dataset.graphNodeKey === expectedKey
      && active.closest('section[data-panel-id="graph"]') != null;
  }, graphCard.graph_focus_key), 'keyboard focus on exact Knowledge Graph evidence node');
  record('journey', `Decision Radar focused canonical graph evidence ${graphCard.graph_focus_key}`);

  const aiSurface = await activateBillyDock(page);
  const billyInput = await waitVisible(
    page.getByRole('textbox', { name: 'Message Billy', exact: true }),
    'Billy draft input',
  );
  const preservedDraft = 'Keep this existing Billy draft while reviewing Continuity.';
  await billyInput.fill(preservedDraft);
  const logosTab = await waitVisible(aiSurface.getByTitle('Logos', { exact: true }), 'Logos companion tab');
  await logosTab.click();
  await waitFor(
    async () => await logosTab.getAttribute('aria-pressed') === 'true',
    'Logos companion selection before Continuity handoff',
  );
  await waitVisible(aiSurface.locator('[data-screen-label="Logos"]'), 'Logos companion panel');

  radarSurface = await selectPanel(page, 'Decision Radar', 'decision-radar', 'Decision Radar');
  const continuityUi = await decisionCard(radarSurface, 'SEMANTIC CONTINUITY');
  const continuityCard = seeded.radar.continuity_cards.find(
    (candidate) => candidate.id === continuityUi.id,
  );
  assert.ok(
    continuityCard?.related_target_key,
    `Displayed Continuity card ${continuityUi.id} is not traceable to an exact issue`,
  );
  const issue = seeded.continuity.issues.find(
    (candidate) => candidate.id === continuityCard.related_target_key,
  );
  assert.ok(issue, `Decision Radar Continuity issue ${continuityCard.related_target_key} is absent from the authoritative report`);
  await continuityUi.card.getByRole('button', { name: 'OPEN CONTINUITY ISSUE', exact: true }).click();
  const continuitySurface = await waitVisible(
    page.locator('section[data-panel-id="continuity"]'),
    'Continuity production workspace surface',
  );
  const issueCard = await waitVisible(
    continuitySurface.locator(`[data-continuity-issue-id="${issue.id}"]`),
    'exact Continuity issue deep link',
  );
  await waitFor(
    async () => issueCard.evaluate((element) => document.activeElement === element),
    'Continuity issue focus after authoritative refresh',
  );

  const repairSceneId = issue.related_scene_ids[0] ?? null;
  const repairLabel = repairSceneId == null
    ? 'ASK BILLY TO PLAN REPAIR'
    : `REPAIR SC.${repairSceneId}`;
  const collapseRightDock = page.getByRole('button', {
    name: 'Collapse right dock',
    exact: true,
  });
  if (await collapseRightDock.isVisible().catch(() => false)) {
    await collapseRightDock.click();
    await waitVisible(
      page.getByRole('button', { name: 'Expand right dock', exact: true }),
      'collapsed right dock before Continuity repair handoff',
    );
  }
  await issueCard.getByRole('button', { name: repairLabel, exact: true }).click();
  const repairAiSurface = await waitVisible(
    page.locator('section[data-panel-id="ai-companions"]'),
    'Billy production workspace surface after Continuity handoff',
  );
  const repairedBillyTab = await waitVisible(
    repairAiSurface.getByTitle('Billy', { exact: true }),
    'Billy companion tab after Continuity handoff',
  );
  await waitFor(
    async () => await repairedBillyTab.getAttribute('aria-pressed') === 'true',
    'Continuity handoff reselected Billy in the production companion dock',
  );
  await waitVisible(
    page.getByText('CONTINUITY REPAIR WAITING · existing Billy draft preserved', { exact: true }),
    'Billy existing-draft preservation decision',
  );
  await waitFor(async () => page.evaluate(() => {
    const active = document.activeElement;
    return active instanceof HTMLElement
      && active.closest('section[data-panel-id="ai-companions"]') != null
      && active.closest('[data-scene-id]') == null;
  }), 'keyboard focus transferred from the hidden Manuscript to Billy');
  assert.equal(await billyInput.inputValue(), preservedDraft, 'Continuity handoff overwrote an existing Billy draft');
  await page.getByRole('button', { name: 'REPLACE DRAFT', exact: true }).click();
  await waitFor(
    async () => (await billyInput.inputValue()).includes(issue.title),
    'explicitly staged Continuity repair brief',
  );
  await waitVisible(
    page.locator('section[data-panel-id="ai-companions"] [role="status"]')
      .filter({ hasText: issue.id })
      .filter({ hasText: 'brief staged, not sent' }),
    'unsent Continuity repair status',
  );
  const unchangedOpening = await packagedCoreJson(
    session,
    `/api/projects/${projectId}/scenes/${seeded.opening.id}`,
  );
  assert.equal(
    unchangedOpening.content,
    barrierText,
    'Staging a Continuity repair changed manuscript prose before Controlled Apply',
  );
  assert.equal(
    repairSceneId,
    seeded.opening.id,
    'The deterministic Continuity fixture did not target the edited opening scene',
  );

  const stagedBrief = await billyInput.inputValue();
  const expectedReply = 'Ada stepped into the archive, dust hanging in the dawn light. Milo did not look up from the cabinet. "You\'re late," he said, and she heard the accusation folded under the words.';
  const assistantRequestPromise = page.waitForRequest((request) => (
    request.method() === 'POST'
      && new URL(request.url()).pathname === `/api/projects/${projectId}/assistant/chat`
  ), { timeout: UI_TIMEOUT_MS });
  await repairAiSurface.getByRole('button', { name: 'SEND', exact: true }).click();
  const assistantRequest = await assistantRequestPromise;
  assert.deepEqual(
    assistantRequest.postDataJSON(),
    {
      message: stagedBrief,
      history: [],
      active_scene_id: seeded.opening.id,
    },
    'Billy repair request lost its exact scene-bound, selection-free payload',
  );
  await waitVisible(
    repairAiSurface.getByText(expectedReply, { exact: true }),
    'deterministic packaged Billy repair reply',
  );
  await repairAiSurface.getByRole('button', { name: '↧ REPLACE', exact: true }).click();
  const applyDialog = await waitVisible(
    page.getByRole('dialog', { name: 'CONTROLLED APPLY', exact: true }),
    'Controlled Apply review for the Billy repair',
  );
  const applyReviewText = await applyDialog.textContent();
  assert.ok(
    applyReviewText?.includes(`REWRITE · ${seeded.opening.title.toUpperCase()}`),
    'Controlled Apply did not identify the exact repair scene',
  );
  assert.ok(
    applyReviewText?.includes('Packaged shell save barrier'),
    'Controlled Apply did not show the current manuscript prose',
  );
  assert.ok(
    applyReviewText?.includes(expectedReply),
    'Controlled Apply did not show Billy’s proposed prose',
  );
  const beforeApply = await packagedCoreJson(
    session,
    `/api/projects/${projectId}/scenes/${seeded.opening.id}`,
  );
  assert.equal(
    beforeApply.content,
    barrierText,
    'Opening the Controlled Apply review mutated manuscript prose',
  );
  assert.ok(beforeApply.revision, 'Controlled Apply target has no revision guard');
  const applyRequestPromise = page.waitForRequest((request) => (
    request.method() === 'PATCH'
      && new URL(request.url()).pathname === `/api/projects/${projectId}/scenes/${seeded.opening.id}`
  ), { timeout: UI_TIMEOUT_MS });
  await applyDialog.getByRole('button', { name: '✓ APPLY', exact: true }).click();
  const applyRequest = await applyRequestPromise;
  assert.deepEqual(
    applyRequest.postDataJSON(),
    {
      content: expectedReply,
      expected_revision: beforeApply.revision,
    },
    'Controlled Apply did not send the exact revision-bound scene mutation',
  );
  await applyDialog.waitFor({ state: 'hidden', timeout: UI_TIMEOUT_MS });
  await waitFor(async () => {
    const applied = await packagedCoreJson(
      session,
      `/api/projects/${projectId}/scenes/${seeded.opening.id}`,
    );
    return applied.content === expectedReply;
  }, 'confirmed Controlled Apply scene mutation');

  const reviewSurface = await selectPanel(page, 'Continuity', 'continuity', 'Continuity');
  const reviewIssue = await waitVisible(
    reviewSurface.locator(`[data-continuity-issue-id="${issue.id}"]`),
    'Continuity issue before transactional review',
  );
  const collapseRightForReview = page.getByRole('button', {
    name: 'Collapse right dock',
    exact: true,
  });
  const restoreRightAfterReview = await collapseRightForReview.isVisible().catch(() => false);
  if (restoreRightAfterReview) {
    await collapseRightForReview.click();
    await waitVisible(
      page.getByRole('button', { name: 'Expand right dock', exact: true }),
      'collapsed right dock before Continuity decision review',
    );
  }
  await reviewIssue.getByRole('button', { name: 'RESOLVE', exact: true }).click();
  const reviewDialog = await waitVisible(
    page.getByRole('dialog', { name: 'REVIEW CONTINUITY', exact: true }),
    'Continuity review confirmation',
  );
  await reviewDialog.getByRole('button', { name: 'CONFIRM DECISION', exact: true }).click();
  await reviewDialog.waitFor({ state: 'hidden', timeout: UI_TIMEOUT_MS });
  await waitFor(
    async () => (await reviewIssue.textContent())?.includes('RESOLVED') ?? false,
    'resolved Continuity review state',
  );
  if (restoreRightAfterReview) {
    await page.getByRole('button', { name: 'Expand right dock', exact: true }).click();
    await waitVisible(
      page.getByRole('button', { name: 'Collapse right dock', exact: true }),
      'restored right dock after Continuity decision review',
    );
  }
  const reviewedContinuity = await packagedCoreJson(
    session,
    `/api/projects/${projectId}/continuity`,
  );
  const reviewedIssue = reviewedContinuity.issues.find((candidate) => candidate.id === issue.id);
  assert.equal(reviewedIssue?.status, 'resolved', 'Continuity confirmation did not persist its review decision');
  const reviewedRadar = await packagedCoreJson(
    session,
    `/api/projects/${projectId}/decision-radar`,
  );
  assert.equal(
    reviewedRadar.continuity_cards.some((candidate) => candidate.id === continuityCard.id),
    false,
    'Resolved Continuity issue remained actionable in Decision Radar',
  );
  assert.deepEqual(session.pageErrors, [], 'Renderer errors occurred during the Graph/Radar/Continuity shell journey');
  record('journey', 'real shell completed Radar → Graph, Continuity → Billy → Controlled Apply, and confirmed durable review paths');
  return {
    projectId,
    openingSceneId: seeded.opening.id,
    openingSceneTitle: seeded.opening.title,
    openingSceneOrder: seeded.opening.sort_order,
    crossingSceneId: seeded.crossing.id,
    crossingSceneTitle: seeded.crossing.title,
    crossingSceneOrder: seeded.crossing.sort_order,
    savedOpeningContent: expectedReply,
    graphCardId: graphCard.id,
    continuityCardId: continuityCard.id,
    continuityIssueId: issue.id,
    continuityIssueStatus: 'resolved',
  };
}

async function exerciseProgressionsIntelligence(session, intelligenceExpected) {
  const { page } = session;
  const { projectId } = await waitProReady(session);
  assert.equal(
    projectId,
    intelligenceExpected.projectId,
    'Packaged shell switched projects before the Progressions journey',
  );
  assert.ok(
    intelligenceExpected.openingSceneOrder < intelligenceExpected.crossingSceneOrder,
    'Progressions acceptance requires Opening before Crossing in manuscript order',
  );

  let dashboardSurface = await selectPanel(page, 'Dashboard', 'dashboard', 'Narrative Dashboard');
  const dashboardScreen = await waitVisible(
    dashboardSurface.locator('[data-screen-label="Narrative Dashboard"]'),
    'Narrative Dashboard before Progressions mutation',
  );
  const tensionPolyline = dashboardScreen.locator('svg polyline').first();
  await waitFor(
    async () => Boolean(await tensionPolyline.getAttribute('points')),
    'baseline Dashboard tension curve',
  );
  const baselineTensionPoints = await tensionPolyline.getAttribute('points');

  let radarSurface = await selectPanel(page, 'Decision Radar', 'decision-radar', 'Decision Radar');
  await waitVisible(radarSurface.getByText('GRAPH ONLINE', { exact: true }), 'pre-Progressions Radar Graph availability');
  const graphSurfaceBefore = await selectPanel(page, 'Graph', 'graph', 'Knowledge Graph');
  await waitVisible(
    graphSurfaceBefore.locator('[data-knowledge-graph-canvas="true"]'),
    'Knowledge Graph before Progressions mutation',
  );
  let progressionsSurface = await selectPanel(
    page,
    'Progressions',
    'progressions',
    'BIBLE · PROGRESSIONS',
  );
  await waitVisible(
    progressionsSurface.locator('[data-screen-label="BIBLE · PROGRESSIONS"]'),
    'Progressions production workspace surface',
  );
  await waitVisible(
    progressionsSurface.locator('[aria-label="Progressions coverage"]'),
    'initial Progressions coverage summary',
  );

  let snapshot = await packagedCoreJson(
    session,
    `/api/projects/${projectId}/progressions`,
  );
  assert.equal(snapshot.tracks.length, 0, 'Fresh packaged acceptance project already has Progressions tracks');

  const liveRefetches = Promise.all([
    waitForRendererGet(page, `/api/projects/${projectId}/dashboard`, 'Dashboard'),
    waitForRendererGet(page, `/api/projects/${projectId}/decision-radar`, 'Decision Radar'),
    waitForRendererGet(page, `/api/projects/${projectId}/knowledge-graph`, 'Knowledge Graph'),
    waitForRendererGet(page, `/api/projects/${projectId}/progressions`, 'Progressions'),
  ]);
  const createdTrack = await executePackagedProgressionCommand(
    session,
    projectId,
    {
      kind: 'create_track',
      expected_revision: snapshot.revision,
      track_kind: 'story',
      title: 'Packaged Story Progression',
      description: 'A durable arc authored by the packaged acceptance journey.',
      color_label: 'violet',
    },
    'create-track',
  );
  await liveRefetches;
  const trackId = createdTrack.result.created_track_id;
  assert.ok(Number.isSafeInteger(trackId) && trackId > 0, 'Progressions create_track returned no track id');
  assert.equal(
    createdTrack.receipt.original_created_track_id,
    trackId,
    'Progressions track receipt lost the created identity',
  );
  const exactReplay = await packagedCoreJson(
    session,
    `/api/projects/${projectId}/progressions/commands`,
    {
      method: 'POST',
      headers: { 'Idempotency-Key': createdTrack.idempotencyKey },
      body: JSON.stringify(createdTrack.command),
    },
  );
  assert.equal(exactReplay.changed, false, 'Exact Progressions replay repeated the track mutation');
  assert.equal(exactReplay.replayed, true, 'Exact Progressions replay was not recognized');
  assert.equal(exactReplay.created_track_id, trackId, 'Exact Progressions replay changed the created track id');
  assert.equal(
    exactReplay.applied_revision,
    createdTrack.result.applied_revision,
    'Exact Progressions replay changed the original applied revision',
  );
  assert.equal(exactReplay.progressions.tracks.length, 1, 'Exact Progressions replay duplicated the track');
  record('transaction', `exact same-key Progressions replay recovered track ${trackId} without mutation`);
  snapshot = createdTrack.result.progressions;

  const mismatchedReplay = await packagedCoreResponse(
    session,
    `/api/projects/${projectId}/progressions/commands`,
    {
      method: 'POST',
      headers: { 'Idempotency-Key': createdTrack.idempotencyKey },
      body: JSON.stringify({
        ...createdTrack.command,
        title: 'This different command must never reuse the committed key',
      }),
    },
  );
  assert.equal(mismatchedReplay.status, 409, 'Different Progressions payload reused a committed idempotency key');
  assert.equal(mismatchedReplay.body?.error?.code, 'idempotency_key_conflict');
  assert.equal(
    (await packagedCoreJson(session, `/api/projects/${projectId}/progressions`)).revision,
    snapshot.revision,
    'Progressions idempotency-key collision mutated the canonical revision',
  );

  const noOpKey = `packaged-progression-${projectId}-noop-reorder`;
  const noOpCommand = {
    kind: 'reorder_tracks',
    expected_revision: snapshot.revision,
    track_ids: [trackId],
  };
  const noOpResult = await packagedCoreJson(
    session,
    `/api/projects/${projectId}/progressions/commands`,
    {
      method: 'POST',
      headers: { 'Idempotency-Key': noOpKey },
      body: JSON.stringify(noOpCommand),
    },
  );
  assert.equal(noOpResult.changed, false, 'Exact Progressions reorder no-op reported a mutation');
  assert.equal(noOpResult.replayed, false, 'Fresh Progressions no-op was misclassified as replay');
  assert.equal(noOpResult.applied_revision, snapshot.revision, 'Progressions no-op changed the applied revision');
  const noOpReceiptResponse = await packagedCoreResponse(
    session,
    `/api/projects/${projectId}/progressions/command-receipt`,
    { headers: { 'Idempotency-Key': noOpKey } },
  );
  assert.equal(noOpReceiptResponse.status, 200, 'Fresh Progressions no-op did not commit a durable receipt');
  assert.equal(noOpReceiptResponse.headers.get('cache-control'), 'no-store');
  const noOpReceipt = noOpReceiptResponse.body;
  assert.equal(noOpReceipt.original_changed, false);
  assert.deepEqual(noOpReceipt.original_affected_track_ids, []);
  assert.deepEqual(noOpReceipt.original_affected_beat_ids, []);
  const noOpReceiptExpectation = {
    projectId,
    idempotencyKey: noOpKey,
    commandKind: noOpCommand.kind,
    expectedRevision: noOpCommand.expected_revision,
    appliedRevision: noOpResult.applied_revision,
    requestDigest: noOpReceipt.request_digest,
    originalChanged: false,
    affectedTrackIds: [],
    affectedBeatIds: [],
    createdTrackId: null,
    createdBeatId: null,
    committedAt: noOpReceipt.committed_at,
  };
  record('transaction', `fresh no-op Progressions reorder committed durable receipt ${noOpKey}`);

  const createdCrossingBeat = await executePackagedProgressionCommand(
    session,
    projectId,
    {
      kind: 'create_beat',
      expected_revision: snapshot.revision,
      track_id: trackId,
      text: 'The crossing commits the irreversible turn.',
      anchor_kind: 'scene',
      scene_id: intelligenceExpected.crossingSceneId,
    },
    'create-crossing-beat',
  );
  const crossingBeatId = createdCrossingBeat.result.created_beat_id;
  assert.ok(Number.isSafeInteger(crossingBeatId) && crossingBeatId > 0, 'Progressions crossing beat has no id');
  snapshot = createdCrossingBeat.result.progressions;

  const createdOpeningBeat = await executePackagedProgressionCommand(
    session,
    projectId,
    {
      kind: 'create_beat',
      expected_revision: snapshot.revision,
      track_id: trackId,
      text: 'The opening doubt is deliberately ordered after the crossing.',
      anchor_kind: 'scene',
      scene_id: intelligenceExpected.openingSceneId,
    },
    'create-out-of-order-beat',
  );
  const openingBeatId = createdOpeningBeat.result.created_beat_id;
  assert.ok(Number.isSafeInteger(openingBeatId) && openingBeatId > 0, 'Progressions opening beat has no id');
  snapshot = createdOpeningBeat.result.progressions;

  const createdUnanchoredBeat = await executePackagedProgressionCommand(
    session,
    projectId,
    {
      kind: 'create_beat',
      expected_revision: snapshot.revision,
      track_id: trackId,
      text: 'An unresolved global turn still needs an anchor.',
      anchor_kind: 'unanchored',
    },
    'create-unanchored-beat',
  );
  const unanchoredBeatId = createdUnanchoredBeat.result.created_beat_id;
  assert.ok(Number.isSafeInteger(unanchoredBeatId) && unanchoredBeatId > 0, 'Progressions unanchored beat has no id');
  snapshot = createdUnanchoredBeat.result.progressions;

  const editorResult = await exerciseProgressionEditorTransactions(session, {
    projectId,
    progressionsSurface,
    storyTrackId: trackId,
    documentAfterBeatId: openingBeatId,
  });
  snapshot = editorResult.snapshot;

  const track = snapshot.tracks.find((candidate) => candidate.id === trackId);
  assert.ok(track, `Committed Progressions track ${trackId} is absent from its command result`);
  assert.deepEqual(
    track.beats.map((beat) => beat.id),
    [crossingBeatId, openingBeatId, editorResult.documentBeatId, unanchoredBeatId],
    'Progressions command results changed explicit beat order',
  );
  assert.equal(track.coverage.total_beats, 4, 'Progressions coverage lost a committed beat');
  assert.equal(track.coverage.anchored_beats, 3, 'Progressions coverage lost an anchored beat');
  assert.equal(track.coverage.scene_anchored_beats, 2, 'Progressions coverage lost scene anchors');
  assert.equal(track.coverage.document_anchored_beats, 1, 'Progressions coverage lost its document anchor');
  assert.equal(track.coverage.unanchored_beats, 1, 'Progressions coverage lost the unanchored beat');
  assert.ok(
    track.coverage.out_of_order_beat_ids.includes(openingBeatId),
    'Progressions coverage did not identify the deliberately out-of-order beat',
  );

  const dashboard = await packagedCoreJson(session, `/api/projects/${projectId}/dashboard`);
  const openingPoint = dashboard.tension.points.find(
    (point) => point.scene_id === intelligenceExpected.openingSceneId,
  );
  const crossingPoint = dashboard.tension.points.find(
    (point) => point.scene_id === intelligenceExpected.crossingSceneId,
  );
  assert.equal(openingPoint?.progression_count, 1, 'Dashboard did not count the opening scene anchor exactly once');
  assert.equal(crossingPoint?.progression_count, 1, 'Dashboard did not count the crossing scene anchor exactly once');
  dashboardSurface = await selectPanel(page, 'Dashboard', 'dashboard', 'Narrative Dashboard');
  const refreshedTensionPolyline = dashboardSurface.locator(
    '[data-screen-label="Narrative Dashboard"] svg polyline',
  ).first();
  await waitFor(
    async () => {
      const current = await refreshedTensionPolyline.getAttribute('points');
      return Boolean(current) && current !== baselineTensionPoints;
    },
    'live Dashboard progression-aware tension curve',
  );
  record('journey', 'Dashboard visibly recomputed after canonical scene-anchored Progressions beats');

  const graph = await packagedCoreJson(session, `/api/projects/${projectId}/knowledge-graph`);
  const trackGraphKey = `progression_track:progressions:${trackId}`;
  const crossingGraphKey = `progression_beat:progressions:${crossingBeatId}`;
  const openingGraphKey = `progression_beat:progressions:${openingBeatId}`;
  const documentGraphKey = `progression_beat:progressions:${editorResult.documentBeatId}`;
  const unanchoredGraphKey = `progression_beat:progressions:${unanchoredBeatId}`;
  const graphKeys = new Set(graph.nodes.map((node) => node.key));
  for (const key of [
    trackGraphKey,
    crossingGraphKey,
    openingGraphKey,
    documentGraphKey,
    unanchoredGraphKey,
    `progression_track:progressions:${editorResult.characterTrackId}`,
  ]) {
    assert.ok(graphKeys.has(key), `Knowledge Graph did not project canonical Progressions node ${key}`);
  }

  const radar = await packagedCoreJson(session, `/api/projects/${projectId}/decision-radar`);
  const progressionCard = radar.knowledge_graph_cards.find(
    (candidate) => candidate.id === `kg_progression_unanchored_${trackId}`,
  );
  assert.ok(progressionCard, 'Decision Radar did not emit the canonical unanchored Progressions card');
  assert.equal(progressionCard.category, 'progression', 'Progressions Radar card changed category');
  assert.equal(progressionCard.related_target_type, 'progression_track');
  assert.equal(progressionCard.related_target_id, trackId);
  assert.equal(progressionCard.graph_focus_key, trackGraphKey);
  const beatEvidence = progressionCard.evidence.find(
    (item) => item.related_target_type === 'progression_beat'
      && item.related_target_id === unanchoredBeatId,
  );
  assert.ok(beatEvidence, 'Progressions Radar card did not preserve exact beat evidence');
  assert.equal(beatEvidence.graph_focus_key, unanchoredGraphKey);

  radarSurface = await selectPanel(page, 'Decision Radar', 'decision-radar', 'Decision Radar');
  let progressionCardUi = await waitVisible(
    radarSurface.locator(`[data-decision-card-id="${progressionCard.id}"]`),
    'live Progressions Decision Radar card',
  );
  await waitVisible(progressionCardUi.getByText('PROGRESSIONS', { exact: true }), 'Progressions Radar provenance badge');
  await progressionCardUi.getByRole('button', { name: 'OPEN GRAPH EVIDENCE', exact: true }).click();
  let graphSurface = await waitVisible(
    page.locator('section[data-panel-id="graph"]'),
    'Progressions-focused Knowledge Graph surface',
  );
  const graphCanvas = await waitVisible(
    graphSurface.locator('[data-knowledge-graph-canvas="true"]'),
    'Progressions-focused Knowledge Graph canvas',
  );
  await waitFor(async () => (
    await graphCanvas.getAttribute('data-focus-key') === trackGraphKey
      && await graphCanvas.getAttribute('data-view-mode') === progressionCard.graph_view_mode
  ), 'exact Progressions card Graph deep link');
  await waitFor(async () => page.evaluate((expectedKey) => {
    const active = document.activeElement;
    return active instanceof HTMLElement && active.dataset.graphNodeKey === expectedKey;
  }, trackGraphKey), 'keyboard focus on the exact Progressions track graph node');

  radarSurface = await selectPanel(page, 'Decision Radar', 'decision-radar', 'Decision Radar');
  progressionCardUi = await waitVisible(
    radarSurface.locator(`[data-decision-card-id="${progressionCard.id}"]`),
    'Progressions card before exact track handoff',
  );
  await progressionCardUi.getByRole('button', { name: 'OPEN PROGRESSION', exact: true }).click();
  progressionsSurface = await waitVisible(
    page.locator('section[data-panel-id="progressions"]'),
    'Progressions surface after exact track handoff',
  );
  const trackButton = progressionsSurface.locator(`[data-progression-track-id="${trackId}"]`);
  await waitVisible(trackButton, 'exact Progressions track target');
  await waitFor(async () => page.evaluate((expectedId) => {
    const active = document.activeElement;
    return active instanceof HTMLElement && active.dataset.progressionTrackId === String(expectedId);
  }, trackId), 'keyboard focus on the exact Progressions track');

  radarSurface = await selectPanel(page, 'Decision Radar', 'decision-radar', 'Decision Radar');
  progressionCardUi = await waitVisible(
    radarSurface.locator(`[data-decision-card-id="${progressionCard.id}"]`),
    'Progressions card before exact beat handoff',
  );
  await clickExactRadarEvidenceAction(
    radarSurface,
    progressionCard.id,
    `Open Progressions evidence for ${beatEvidence.label}`,
  );
  progressionsSurface = await waitVisible(
    page.locator('section[data-panel-id="progressions"]'),
    'Progressions surface after exact beat handoff',
  );
  let beatButton = progressionsSurface.locator(`[data-progression-beat-id="${unanchoredBeatId}"]`);
  await waitVisible(beatButton, 'exact Progressions beat target');
  await waitFor(async () => page.evaluate((expectedId) => {
    const active = document.activeElement;
    return active instanceof HTMLElement && active.dataset.progressionBeatId === String(expectedId);
  }, unanchoredBeatId), 'keyboard focus on the exact Progressions beat');

  const dockRegion = await progressionsSurface.getAttribute('data-dock-region');
  assert.ok(
    ['left', 'center', 'right', 'bottom'].includes(dockRegion),
    `Progressions surface exposed an invalid dock region: ${dockRegion}`,
  );
  const progressionsWindowPromise = session.app.waitForEvent('window', {
    predicate: async (candidate) => {
      try {
        return await candidate.evaluate(() => (
          /^logosforge-panel:progressions:[A-Za-z0-9_-]{16,128}$/.test(window.name)
        ));
      } catch {
        return false;
      }
    },
    timeout: STARTUP_TIMEOUT_MS,
  });
  const floatProgressions = await waitVisible(
    page.locator(`[data-dock-drop-region="${dockRegion}"]`)
      .getByRole('button', { name: 'Float Progressions', exact: true }),
    'Float Progressions control',
  );
  await floatProgressions.click();
  const progressionsWindow = await progressionsWindowPromise;
  attachPageDiagnostics(session, progressionsWindow, 'progressions-native-window');
  const nativeProgressionsSurface = progressionsWindow
    .locator('section[data-panel-id="progressions"]')
    .first();
  await waitFor(
    async () => (await nativeProgressionsSurface.getAttribute('data-floating-panel')) === 'true'
      && (await nativeProgressionsSurface.getAttribute('data-native-floating-panel')) === 'true'
      && await nativeProgressionsSurface.isVisible(),
    'detached native Progressions window',
  );
  const detachedStoryTrack = await waitVisible(
    nativeProgressionsSurface.locator(`[data-progression-track-id="${trackId}"]`),
    'exact track inside detached Progressions window',
  );
  await detachedStoryTrack.click();
  await waitVisible(
    nativeProgressionsSurface.locator(`[data-progression-beat-id="${unanchoredBeatId}"]`),
    'exact beat inside detached Progressions window',
  );
  const detachedCharacterTitle = `${editorResult.characterTrackTitle} · Detached`;
  const detachedCharacterTrack = await waitVisible(
    nativeProgressionsSurface.locator(
      `[data-progression-track-id="${editorResult.characterTrackId}"]`,
    ),
    'PSYKE-subject track inside detached Progressions window',
  );
  await detachedCharacterTrack.click();
  await nativeProgressionsSurface.getByRole('button', { name: 'EDIT', exact: true }).first().click();
  const detachedTrackEditor = await waitVisible(
    nativeProgressionsSurface.getByRole('dialog', { name: 'Progression track editor', exact: true }),
    'interactive track editor inside detached Progressions window',
  );
  await detachedTrackEditor.locator('label').filter({ hasText: 'TITLE' }).locator('input').fill(detachedCharacterTitle);
  await detachedTrackEditor.getByRole('button', { name: 'SAVE', exact: true }).click();
  await detachedTrackEditor.waitFor({ state: 'hidden', timeout: STARTUP_TIMEOUT_MS });
  snapshot = await waitForProgressionSnapshot(
    session,
    projectId,
    (candidate) => candidate.tracks.some((candidateTrack) => (
      candidateTrack.id === editorResult.characterTrackId
      && candidateTrack.title === detachedCharacterTitle
    )),
    'track mutation committed from detached Progressions window',
  );
  editorResult.characterTrackTitle = detachedCharacterTitle;
  await detachedStoryTrack.click();
  await waitVisible(
    nativeProgressionsSurface.locator(`[data-progression-beat-id="${unanchoredBeatId}"]`),
    'exact beat after detached Progressions mutation',
  );
  record('journey', `detached Progressions window edited and saved track ${editorResult.characterTrackId}`);
  const nativeTitlebar = await waitVisible(
    progressionsWindow.getByRole('toolbar', { name: 'Progressions native window controls', exact: true }),
    'Progressions native window controls',
  );
  const progressionsWindowClosed = progressionsWindow.waitForEvent('close');
  await clickAndWaitForNativeWindowClose(
    nativeTitlebar.getByRole('button', { name: 'Dock Progressions to bottom', exact: true }),
    progressionsWindowClosed,
    'Progressions native window redock',
  );
  progressionsSurface = page.locator(
    'section[data-panel-id="progressions"][data-dock-region="bottom"]',
  ).first();
  await waitVisible(progressionsSurface, 'redocked Progressions workspace surface');
  await progressionsSurface.locator(`[data-progression-track-id="${trackId}"]`).click();
  beatButton = progressionsSurface.locator(`[data-progression-beat-id="${unanchoredBeatId}"]`);
  await waitVisible(beatButton, 'redocked exact Progressions beat');
  await beatButton.click();
  await waitFor(
    async () => beatButton.evaluate((element) => document.activeElement === element),
    'usable exact Progressions beat after native redock',
  );

  assert.deepEqual(session.pageErrors, [], 'Renderer errors occurred during the Progressions intelligence journey');
  record(
    'journey',
    `packaged Progressions track ${trackId} reached Dashboard, Radar, Graph, exact deep links, and a native panel`,
  );
  return {
    projectId,
    trackId,
    trackTitle: track.title,
    trackGraphKey,
    crossingBeatId,
    crossingBeatText: track.beats.find((beat) => beat.id === crossingBeatId).text,
    crossingSceneId: intelligenceExpected.crossingSceneId,
    openingBeatId,
    openingBeatText: track.beats.find((beat) => beat.id === openingBeatId).text,
    openingSceneId: intelligenceExpected.openingSceneId,
    unanchoredBeatId,
    unanchoredBeatText: track.beats.find((beat) => beat.id === unanchoredBeatId).text,
    documentBeatId: editorResult.documentBeatId,
    documentBeatText: editorResult.documentBeatText,
    documentAnchorRef: editorResult.documentAnchorRef,
    documentAnchorLabel: editorResult.documentAnchorLabel,
    characterTrackId: editorResult.characterTrackId,
    characterTrackTitle: editorResult.characterTrackTitle,
    characterSubjectId: editorResult.characterSubjectId,
    finalRevision: snapshot.revision,
    receiptExpectations: [
      progressionReceiptExpectation(projectId, createdTrack),
      noOpReceiptExpectation,
      ...editorResult.receiptExpectations,
    ],
    radarCardId: progressionCard.id,
  };
}

async function waitForTimelineSnapshot(session, projectId, predicate, label) {
  let snapshot = null;
  await waitFor(async () => {
    snapshot = await packagedCoreJson(session, `/api/projects/${projectId}/timeline`);
    return predicate(snapshot);
  }, label, STARTUP_TIMEOUT_MS);
  return snapshot;
}

async function addTimelineSceneThroughObservedCommand({
  page,
  projectId,
  scene,
  scenePicker,
  addEvent,
}) {
  const commandPath = `/api/projects/${projectId}/timeline/commands`;
  const requests = [];
  const responses = new Map();
  const isCommandRequest = (request) => {
    if (request.method() !== 'POST') return false;
    try {
      return new URL(request.url()).pathname === commandPath;
    } catch {
      return false;
    }
  };
  const onRequest = (request) => {
    if (isCommandRequest(request)) requests.push(request);
  };
  const onResponse = (response) => {
    const request = response.request();
    if (isCommandRequest(request)) responses.set(request, response);
  };
  page.on('request', onRequest);
  page.on('response', onResponse);

  try {
    for (let attempt = 1; attempt <= TIMELINE_ADD_MAX_ATTEMPTS; attempt += 1) {
      await scenePicker.selectOption(String(scene.id));
      await waitFor(
        async () => await addEvent.isEnabled(),
        `enabled Timeline add for ${scene.title} (attempt ${attempt})`,
      );
      const requestCountBeforeClick = requests.length;
      await addEvent.click();

      let dispatched = null;
      try {
        await waitFor(
          async () => requests.length > requestCountBeforeClick,
          `Timeline command dispatch for ${scene.title} (attempt ${attempt})`,
          TIMELINE_COMMAND_DISPATCH_TIMEOUT_MS,
        );
        dispatched = requests[requestCountBeforeClick];
      } catch (dispatchError) {
        // Resolve the boundary race before deciding whether a second click is
        // safe. Once any POST left the renderer, only the production
        // idempotency/receipt path may recover it; this harness must not invent
        // a new proposal by clicking again.
        dispatched = requests[requestCountBeforeClick] ?? null;
        if (!dispatched) {
          const addEnabled = await addEvent.isEnabled().catch(() => false);
          if (attempt < TIMELINE_ADD_MAX_ATTEMPTS && addEnabled) {
            record(
              'ui',
              `Timeline add for ${scene.title} dispatched no POST; safely retrying the still-enabled control once`,
            );
            continue;
          }
          const diagnostics = await releaseGateUiDiagnostics(page, {
            timelineScene: { id: scene.id, title: scene.title },
            attempt,
            selectedSceneId: await scenePicker.inputValue().catch(() => null),
            addEnabled,
            observedTimelineCommandPosts: requests.length,
          });
          throw new Error(`${errorText(dispatchError)} UI diagnostics: ${JSON.stringify(diagnostics)}`);
        }
      }

      assert.ok(dispatched, `No Timeline command request was captured for ${scene.title}`);
      const command = dispatched.postDataJSON();
      assert.equal(command?.kind, 'place_event', `Timeline add for ${scene.title} dispatched the wrong command`);
      assert.equal(command?.scene_id, scene.id, `Timeline add for ${scene.title} dispatched the wrong scene identity`);
      assert.equal(command?.lane_id, null, `Timeline add for ${scene.title} did not target the Unassigned lane`);

      try {
        await waitFor(
          async () => responses.has(dispatched),
          `Timeline command response for ${scene.title}`,
          TIMELINE_COMMAND_RESPONSE_TIMEOUT_MS,
        );
      } catch (responseError) {
        const diagnostics = await releaseGateUiDiagnostics(page, {
          timelineScene: { id: scene.id, title: scene.title },
          request: {
            method: dispatched.method(),
            url: dispatched.url(),
            command,
          },
          observedTimelineCommandPosts: requests.length,
        });
        throw new Error(`${errorText(responseError)} UI diagnostics: ${JSON.stringify(diagnostics)}`);
      }
      const response = responses.get(dispatched);
      assert.ok(response, `No Timeline command response was captured for ${scene.title}`);
      assert.ok(
        response.ok(),
        `Timeline add for ${scene.title} returned HTTP ${response.status()} ${response.statusText()}`,
      );
      record(
        'network',
        `observed Timeline place_event POST/response for ${scene.title} (HTTP ${response.status()}, attempt ${attempt})`,
      );
      return;
    }
  } finally {
    page.off('request', onRequest);
    page.off('response', onResponse);
  }

  throw new Error(`Timeline add for ${scene.title} exhausted its bounded UI attempts`);
}

async function exerciseTimelineRelationships(session, expectedProjectId) {
  const { page } = session;
  const { projectId } = await waitProReady(session);
  assert.equal(projectId, expectedProjectId, 'Packaged shell switched projects before the Timeline journey');
  const timelineSurface = await selectPanel(page, 'Timeline', 'timeline', 'Plot-Lane Timeline');
  const timelineScreen = await waitVisible(
    timelineSurface.locator('[data-screen-label="Plot-Lane Timeline"]'),
    'Timeline relationship screen',
  );

  let timeline = await packagedCoreJson(session, `/api/projects/${projectId}/timeline`);
  const allScenes = [...timeline.events, ...timeline.off_timeline];
  const opening = allScenes.find((scene) => scene.title === 'Acceptance Opening');
  const crossing = allScenes.find((scene) => scene.title === 'Acceptance Crossing');
  assert.ok(opening?.id > 0 && crossing?.id > 0, 'Timeline did not expose both seeded acceptance scenes');
  assert.notEqual(opening.id, crossing.id, 'Timeline acceptance scenes have the same identity');

  for (const scene of [opening, crossing]) {
    if (timeline.events.some((event) => event.id === scene.id)) continue;
    const scenePicker = await waitVisible(
      timelineScreen.getByRole('combobox', { name: 'Scene to add to Timeline', exact: true }),
      `Timeline scene picker for ${scene.title}`,
    );
    await scenePicker.selectOption(String(scene.id));
    const addEvent = await waitVisible(
      scenePicker.locator('..').getByRole('button', { name: 'ADD', exact: true }),
      `add ${scene.title} to Timeline`,
    );
    await addTimelineSceneThroughObservedCommand({
      page,
      projectId,
      scene,
      scenePicker,
      addEvent,
    });
    timeline = await waitForTimelineSnapshot(
      session,
      projectId,
      (candidate) => candidate.events.some((event) => event.id === scene.id),
      `${scene.title} placement on Timeline`,
    );
  }

  assert.equal(timeline.mode_projection?.kind, 'novel', 'Timeline returned the wrong packaged mode lens');
  assert.deepEqual(
    timeline.story_flow?.points?.map((point) => point.scene_id),
    timeline.events.map((event) => event.id),
    'Timeline story-flow points are not aligned one-to-one with packaged events',
  );
  assert.deepEqual(
    timeline.story_flow?.points?.map((point) => point.order_index),
    timeline.events.map((_, index) => index + 1),
    'Timeline story-flow points do not preserve packaged event order',
  );
  assert.ok(Array.isArray(timeline.story_flow?.warnings), 'Timeline returned no packaged pacing-warning list');
  const flowToggle = await waitVisible(
    timelineScreen.getByRole('button', { name: 'Toggle Timeline story flow', exact: true }),
    'Timeline story-flow toggle',
  );
  const flowRibbon = timelineScreen.locator('[aria-label="Timeline story flow"]');
  await waitVisible(flowRibbon, 'Timeline story-flow ribbon');
  await waitVisible(
    timelineScreen.locator('[aria-label="Timeline Story Pulse"]'),
    'Timeline Story Pulse summary',
  );
  const modeLens = await waitVisible(
    timelineScreen.locator('[aria-label="Timeline mode lens"]'),
    'Timeline mode lens',
  );
  assert.match(String(await modeLens.textContent()), /MODE LENS\s*·\s*NOVEL/, 'Timeline mode lens did not render the project mode');
  await waitFor(
    async () => await flowRibbon.locator('[data-flow-scene-id]').count() === timeline.events.length,
    'one packaged story-flow cell per Timeline event',
  );
  const flowLabels = await flowRibbon.locator('[data-flow-scene-id]').evaluateAll(
    (cells) => cells.map((cell) => cell.getAttribute('aria-label') || ''),
  );
  assert.ok(
    flowLabels.every((label) => /tension \d+(?:\.\d+)? out of 10/.test(label) && /(?:dialogue|action|exposition|mixed) scene/.test(label)),
    'Timeline story-flow cells relied on color without numeric tension and scene-type labels',
  );
  await flowToggle.click();
  await flowRibbon.waitFor({ state: 'hidden', timeout: UI_TIMEOUT_MS });
  await flowToggle.click();
  await waitVisible(flowRibbon, 'restored Timeline story-flow ribbon');

  const createSource = await waitVisible(
    timelineScreen.getByRole('button', {
      name: `Start relationship from ${opening.title}`,
      exact: true,
    }),
    'Timeline relationship source control',
  );
  await createSource.click();
  let relationshipEditor = await waitVisible(
    timelineScreen.locator('section[aria-label="Timeline relationship editor"]'),
    'Timeline relationship editor',
  );
  await relationshipEditor.getByRole('combobox', { name: 'New relationship type', exact: true })
    .selectOption('causality');
  await relationshipEditor.getByRole('combobox', { name: 'New relationship color', exact: true })
    .selectOption('amber');
  await relationshipEditor.getByRole('textbox', { name: 'New relationship label', exact: true })
    .fill('Packaged UI relationship draft');
  await timelineScreen.getByRole('button', {
    name: `Use ${crossing.title} as relationship target`,
    exact: true,
  }).click();
  timeline = await waitForTimelineSnapshot(
    session,
    projectId,
    (candidate) => candidate.links.length === 1
      && candidate.links[0].source_scene_id === opening.id
      && candidate.links[0].target_scene_id === crossing.id,
    'Timeline relationship creation through the production UI',
  );
  const firstLinkId = timeline.links[0].id;
  assert.ok(firstLinkId > 0, 'Timeline UI create returned no durable relationship identity');

  relationshipEditor = await waitVisible(
    timelineScreen.locator('section[aria-label="Timeline relationship editor"]'),
    'Timeline relationship editor after create',
  );
  await relationshipEditor.getByRole('button', {
    name: `Edit relationship ${firstLinkId}`,
    exact: true,
  }).click();
  await relationshipEditor.getByRole('combobox', {
    name: `Type for relationship ${firstLinkId}`,
    exact: true,
  }).selectOption('setup_payoff');
  await relationshipEditor.getByRole('textbox', {
    name: `Label for relationship ${firstLinkId}`,
    exact: true,
  }).fill('Packaged UI relationship updated');
  await relationshipEditor.getByRole('button', { name: 'SAVE', exact: true }).click();
  timeline = await waitForTimelineSnapshot(
    session,
    projectId,
    (candidate) => candidate.links.length === 1
      && candidate.links[0].id === firstLinkId
      && candidate.links[0].link_type === 'setup_payoff'
      && candidate.links[0].label === 'Packaged UI relationship updated',
    'Timeline relationship update through the production UI',
  );

  const deleteRelationship = await waitVisible(
    relationshipEditor.getByRole('button', {
      name: `Delete relationship ${firstLinkId}`,
      exact: true,
    }),
    'Timeline relationship delete control',
  );
  const commandPath = `/api/projects/${projectId}/timeline/commands`;
  const deleteDispatch = page.waitForRequest((request) => {
    if (request.method() !== 'POST') return false;
    try {
      if (new URL(request.url()).pathname !== commandPath) return false;
      const command = request.postDataJSON();
      return command?.kind === 'delete_link' && command?.link_id === firstLinkId;
    } catch {
      return false;
    }
  }, { timeout: TIMELINE_COMMAND_DISPATCH_TIMEOUT_MS }).then(
    (request) => ({ request, error: null }),
    (error) => ({ request: null, error }),
  );
  await deleteRelationship.click();
  const confirmDeleteRelationship = await waitVisible(
    relationshipEditor.getByRole('button', {
      name: `Confirm deletion of relationship ${firstLinkId}`,
      exact: true,
    }),
    'Timeline relationship delete confirmation',
  );
  await confirmDeleteRelationship.click();
  const deleteDispatchResult = await deleteDispatch;
  if (!deleteDispatchResult.request) {
    const diagnostics = await releaseGateUiDiagnostics(page, {
      timelineRelationship: { id: firstLinkId },
      deleteControlVisible: await deleteRelationship.isVisible().catch(() => false),
      confirmControlVisible: await confirmDeleteRelationship.isVisible().catch(() => false),
    });
    throw new Error(
      `Timeline relationship delete confirmation dispatched no delete_link POST within ${TIMELINE_COMMAND_DISPATCH_TIMEOUT_MS}ms. ${errorText(deleteDispatchResult.error)} UI diagnostics: ${JSON.stringify(diagnostics)}`,
    );
  }
  const dispatchedDelete = deleteDispatchResult.request;
  const dispatchedDeleteCommand = dispatchedDelete.postDataJSON();
  assert.equal(dispatchedDeleteCommand?.kind, 'delete_link', 'Timeline relationship deletion dispatched the wrong command');
  assert.equal(dispatchedDeleteCommand?.link_id, firstLinkId, 'Timeline relationship deletion dispatched the wrong identity');
  record('network', `observed Timeline delete_link POST for relationship ${firstLinkId}`);
  timeline = await waitForTimelineSnapshot(
    session,
    projectId,
    (candidate) => candidate.links.length === 0,
    'Timeline relationship deletion through the production UI',
  );

  await relationshipEditor.getByRole('button', {
    name: 'Close relationship editor',
    exact: true,
  }).click();
  await relationshipEditor.waitFor({ state: 'hidden', timeout: UI_TIMEOUT_MS });
  await timelineScreen.getByRole('button', {
    name: `Start relationship from ${crossing.title}`,
    exact: true,
  }).click();
  relationshipEditor = await waitVisible(
    timelineScreen.locator('section[aria-label="Timeline relationship editor"]'),
    'Timeline recovery relationship editor',
  );
  await relationshipEditor.getByRole('combobox', { name: 'New relationship type', exact: true })
    .selectOption('dependency');
  await relationshipEditor.getByRole('combobox', { name: 'New relationship color', exact: true })
    .selectOption('blue');
  const persistentLabel = 'Packaged UI relationship survived relaunch';
  await relationshipEditor.getByRole('textbox', { name: 'New relationship label', exact: true })
    .fill(persistentLabel);
  await timelineScreen.getByRole('button', {
    name: `Use ${opening.title} as relationship target`,
    exact: true,
  }).click();
  timeline = await waitForTimelineSnapshot(
    session,
    projectId,
    (candidate) => candidate.links.length === 1
      && candidate.links[0].source_scene_id === crossing.id
      && candidate.links[0].target_scene_id === opening.id
      && candidate.links[0].link_type === 'dependency'
      && candidate.links[0].label === persistentLabel,
    'committed Timeline relationship for packaged relaunch',
  );
  const persistentLink = timeline.links[0];
  assert.ok(persistentLink.id > 0, 'Timeline UI did not expose the committed relationship identity');
  assert.deepEqual(session.pageErrors, [], 'Renderer errors occurred during the Timeline relationship journey');
  record(
    'journey',
    `production Timeline UI created, edited, deleted, and committed relationship ${persistentLink.id}`,
  );
  return {
    projectId,
    linkId: persistentLink.id,
    sourceSceneId: crossing.id,
    targetSceneId: opening.id,
    linkType: 'dependency',
    colorLabel: 'blue',
    label: persistentLabel,
  };
}

async function verifyPersistedTimelineRelationships(session, expected) {
  const { page } = session;
  const { projectId } = await waitProReady(session);
  assert.equal(projectId, expected.projectId, 'Packaged relaunch resumed the wrong Timeline project');
  const timeline = await waitForTimelineSnapshot(
    session,
    projectId,
    (candidate) => candidate.links.length === 1 && candidate.links[0].id === expected.linkId,
    'persisted Timeline relationship after packaged relaunch',
  );
  const link = timeline.links[0];
  assert.deepEqual(
    {
      id: link.id,
      sourceSceneId: link.source_scene_id,
      targetSceneId: link.target_scene_id,
      linkType: link.link_type,
      colorLabel: link.color_label,
      label: link.label,
    },
    {
      id: expected.linkId,
      sourceSceneId: expected.sourceSceneId,
      targetSceneId: expected.targetSceneId,
      linkType: expected.linkType,
      colorLabel: expected.colorLabel,
      label: expected.label,
    },
    'Persisted Timeline relationship changed across packaged relaunch',
  );
  assert.deepEqual(timeline.structure_links, [], 'Timeline relaunch unexpectedly created a structure relationship');

  const timelineSurface = await selectPanel(page, 'Timeline', 'timeline', 'Plot-Lane Timeline');
  const timelineScreen = await waitVisible(
    timelineSurface.locator('[data-screen-label="Plot-Lane Timeline"]'),
    'restored Timeline relationship screen',
  );
  const relationshipSummary = await waitVisible(
    timelineScreen.getByRole('button', { name: 'RELATIONSHIPS · 1', exact: true }),
    'restored Timeline relationship summary',
  );
  await relationshipSummary.click();
  const relationshipEditor = await waitVisible(
    timelineScreen.locator('section[aria-label="Timeline relationship editor"]'),
    'restored Timeline relationship editor',
  );
  await waitVisible(
    relationshipEditor.getByRole('button', {
      name: `Edit relationship ${expected.linkId}`,
      exact: true,
    }),
    'restored Timeline relationship edit control',
  );
  await waitVisible(
    relationshipEditor.getByText(expected.label, { exact: false }),
    'restored Timeline relationship label',
  );
  assert.deepEqual(session.pageErrors, [], 'Renderer errors occurred while restoring Timeline relationships');
  record('journey', 'production Timeline relationship and exact identity survived graceful packaged relaunch');
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

async function pointerClickCenter(page, locator, label) {
  const bounds = await locator.boundingBox();
  assert.ok(bounds && bounds.width > 0 && bounds.height > 0, `${label} has no pointer target bounds`);
  const point = {
    x: bounds.x + bounds.width / 2,
    y: bounds.y + bounds.height / 2,
  };
  const receivesPointer = await locator.evaluate((element, target) => {
    const hit = document.elementFromPoint(target.x, target.y);
    return hit === element || (hit instanceof Node && element.contains(hit));
  }, point);
  assert.ok(receivesPointer, `${label} is obscured at its center point`);
  await page.mouse.click(point.x, point.y);
  record('pointer', `${label}: ${Math.round(point.x)},${Math.round(point.y)}`);
}

function finiteAttribute(raw, attribute, label) {
  assert.ok(typeof raw === 'string' && raw.trim() !== '', `${label} is missing ${attribute}`);
  const value = Number(raw);
  assert.ok(Number.isFinite(value), `${label} has invalid ${attribute}: ${raw}`);
  return value;
}

async function canvasEntityIds(locator, attribute, label) {
  const count = await locator.count();
  const ids = new Set();
  for (let index = 0; index < count; index += 1) {
    const raw = await locator.nth(index).getAttribute(attribute);
    const id = finiteAttribute(raw, attribute, label);
    assert.ok(Number.isSafeInteger(id) && id > 0, `${label} has invalid ${attribute}: ${raw}`);
    assert.ok(!ids.has(id), `${label} repeats ${attribute}=${id}`);
    ids.add(id);
  }
  return ids;
}

async function waitForAddedCanvasEntity(locator, attribute, before, label) {
  let createdId = null;
  await waitFor(async () => {
    const current = await canvasEntityIds(locator, attribute, label);
    const added = [...current].filter((id) => !before.has(id));
    if (added.length !== 1) return false;
    createdId = added[0];
    return true;
  }, label);
  assert.ok(Number.isSafeInteger(createdId) && createdId > 0, `${label} did not expose a created id`);
  return createdId;
}

async function canvasGeometry(locator, label) {
  const attributes = {
    x: 'data-x',
    y: 'data-y',
    width: 'data-width',
    height: 'data-height',
  };
  const geometry = {};
  for (const [key, attribute] of Object.entries(attributes)) {
    geometry[key] = finiteAttribute(await locator.getAttribute(attribute), attribute, label);
  }
  assert.ok(geometry.width > 0 && geometry.height > 0, `${label} has invalid geometry`);
  return geometry;
}

async function canvasViewport(board, label) {
  const viewport = {
    zoom: finiteAttribute(await board.getAttribute('data-zoom'), 'data-zoom', label),
    cx: finiteAttribute(await board.getAttribute('data-center-x'), 'data-center-x', label),
    cy: finiteAttribute(await board.getAttribute('data-center-y'), 'data-center-y', label),
  };
  assert.ok(viewport.zoom > 0, `${label} has invalid zoom`);
  return viewport;
}

function differsBy(left, right, minimum) {
  return Math.abs(left - right) >= minimum;
}

function assertNear(actual, expected, tolerance, label) {
  assert.ok(
    Math.abs(actual - expected) <= tolerance,
    `${label}: expected ${expected} +/- ${tolerance}, received ${actual}`,
  );
}

async function waitCanvasCommandSettled(addBlock, label) {
  await waitFor(
    async () => await addBlock.isVisible() && await addBlock.isEnabled(),
    label,
    UI_TIMEOUT_MS,
  );
}

async function dismissCanvasInspector(canvasScreen) {
  const closeButton = canvasScreen.getByRole('button', {
    name: 'Close Canvas Plot inspector',
    exact: true,
  });
  if (await closeButton.isVisible().catch(() => false)) {
    await closeButton.click();
    await waitFor(
      async () => !await closeButton.isVisible().catch(() => false),
      'Canvas Plot inspector dismissal',
    );
  }
}

const CANVAS_POINTER_DOCK_REGIONS = ['right', 'bottom', 'left'];

async function prepareCanvasPointerWorkspace(page, board, label) {
  const collapsedRegions = [];
  let bounds = await board.boundingBox();
  for (const region of CANVAS_POINTER_DOCK_REGIONS) {
    if (bounds && bounds.width > 420 && bounds.height > 300) break;
    const collapse = page.getByRole('button', {
      name: `Collapse ${region} dock`,
      exact: true,
    });
    if (!await collapse.isVisible().catch(() => false)) continue;
    await collapse.click();
    const expand = page.getByRole('button', {
      name: `Expand ${region} dock`,
      exact: true,
    });
    await waitFor(
      async () => await expand.isVisible() && await expand.isEnabled(),
      `${label} ${region} dock collapse`,
    );
    collapsedRegions.push(region);
    bounds = await board.boundingBox();
  }
  await waitFor(async () => {
    bounds = await board.boundingBox();
    return Boolean(bounds && bounds.width > 420 && bounds.height > 300);
  }, `${label} pointer-safe board size`);
  assert.ok(bounds, `${label} has no board bounds after workspace preparation`);
  record(
    'ui',
    `${label} pointer area ${Math.round(bounds.width)}x${Math.round(bounds.height)}`
      + (collapsedRegions.length ? ` after collapsing ${collapsedRegions.join(', ')} docks` : ''),
  );
  return { bounds, collapsedRegions };
}

async function restoreCanvasPointerWorkspace(page, collapsedRegions, label) {
  for (const region of [...collapsedRegions].reverse()) {
    const expand = await waitVisible(
      page.getByRole('button', { name: `Expand ${region} dock`, exact: true }),
      `${label} ${region} dock expand control`,
    );
    await expand.click();
    const collapse = page.getByRole('button', {
      name: `Collapse ${region} dock`,
      exact: true,
    });
    await waitFor(
      async () => await collapse.isVisible() && await collapse.isEnabled(),
      `${label} ${region} dock restoration`,
    );
  }
  if (collapsedRegions.length) {
    record('ui', `${label} restored ${[...collapsedRegions].reverse().join(', ')} docks`);
  }
}

async function exerciseCanvasPlot(session) {
  const { page } = session;
  await waitProReady(session);
  const canvasSurface = await selectPanel(page, 'Canvas Plot', 'canvas-plot', 'Canvas Plot');
  const canvasScreen = await waitVisible(
    canvasSurface.locator('[data-screen-label="Canvas Plot"]'),
    'Canvas Plot screen',
  );
  const board = await waitVisible(
    canvasScreen.locator('[data-canvas-plot-board]'),
    'Canvas Plot board',
  );
  await waitFor(
    async () => await board.getAttribute('data-viewport-ready') === 'true',
    'Canvas Plot viewport settings hydration',
    STARTUP_TIMEOUT_MS,
  );
  const nodes = canvasScreen.locator('[data-canvas-node-id]');
  const frames = canvasScreen.locator('[data-canvas-frame-id]');
  const links = canvasScreen.locator('[data-canvas-link-id]');
  const addBlock = await waitVisible(
    canvasScreen.getByRole('button', { name: 'Add Canvas Plot block', exact: true }),
    'Add Canvas Plot block control',
  );
  const addFrame = await waitVisible(
    canvasScreen.getByRole('button', { name: 'Add Canvas Plot frame', exact: true }),
    'Add Canvas Plot frame control',
  );

  assert.equal(await nodes.count(), 0, 'Fresh packaged profile unexpectedly contained Canvas Plot blocks');
  assert.equal(await frames.count(), 0, 'Fresh packaged profile unexpectedly contained Canvas Plot frames');
  assert.equal(await links.count(), 0, 'Fresh packaged profile unexpectedly contained Canvas Plot connections');

  const initialViewport = await canvasViewport(board, 'initial Canvas Plot viewport');
  const canvasWorkspace = await prepareCanvasPointerWorkspace(page, board, 'Canvas Plot');
  const boardBounds = canvasWorkspace.bounds;
  await page.mouse.move(
    boardBounds.x + boardBounds.width / 2,
    boardBounds.y + boardBounds.height / 2,
  );
  await page.mouse.wheel(0, 360);
  await waitFor(async () => {
    const current = await canvasViewport(board, 'wheel-zoomed Canvas Plot viewport');
    return differsBy(current.zoom, initialViewport.zoom, 0.04);
  }, 'real-wheel Canvas Plot zoom');
  const zoomedViewport = await canvasViewport(board, 'wheel-zoomed Canvas Plot viewport');

  await pointerDragBy(page, board, 68, 44, 'pan empty Canvas Plot board');
  await waitFor(async () => {
    const current = await canvasViewport(board, 'pointer-panned Canvas Plot viewport');
    return differsBy(current.cx, zoomedViewport.cx, 2)
      || differsBy(current.cy, zoomedViewport.cy, 2);
  }, 'real-pointer Canvas Plot pan');
  const viewport = await canvasViewport(board, 'pointer-authored Canvas Plot viewport');

  let beforeIds = await canvasEntityIds(nodes, 'data-canvas-node-id', 'Canvas Plot block');
  await addBlock.click();
  const firstNodeId = await waitForAddedCanvasEntity(
    nodes,
    'data-canvas-node-id',
    beforeIds,
    'first created Canvas Plot block',
  );
  await waitCanvasCommandSettled(addBlock, 'first Canvas Plot block command to settle');

  beforeIds = await canvasEntityIds(nodes, 'data-canvas-node-id', 'Canvas Plot block');
  await addBlock.click();
  const secondNodeId = await waitForAddedCanvasEntity(
    nodes,
    'data-canvas-node-id',
    beforeIds,
    'second created Canvas Plot block',
  );
  await waitCanvasCommandSettled(addBlock, 'second Canvas Plot block command to settle');
  assert.notEqual(firstNodeId, secondNodeId, 'Canvas Plot block ids must be distinct');
  await dismissCanvasInspector(canvasScreen);

  const firstNode = await waitVisible(
    canvasScreen.locator(`[data-canvas-node-id="${firstNodeId}"]`),
    'first Canvas Plot block',
  );
  const secondNode = await waitVisible(
    canvasScreen.locator(`[data-canvas-node-id="${secondNodeId}"]`),
    'second Canvas Plot block',
  );
  const nodeBeforeMove = await canvasGeometry(firstNode, 'first Canvas Plot block before move');
  const nodeMoveHandle = await waitVisible(
    firstNode.locator('[data-canvas-node-move-handle]'),
    'first Canvas Plot block move handle',
  );
  await nodeMoveHandle.click();
  const nodeInspector = await waitVisible(
    canvasScreen.getByRole('form', { name: 'Canvas Plot inspector', exact: true }),
    'first Canvas Plot block inspector',
  );
  const nodeTitle = `Pointer-flushed Canvas Plot block ${firstNodeId}`;
  const nodeSummary = `Distinctive unsaved inspector draft for block ${firstNodeId}.`;
  const titleInput = await waitVisible(
    nodeInspector.getByRole('textbox', { name: 'Block title', exact: true }),
    'Canvas Plot block title field',
  );
  const summaryInput = await waitVisible(
    nodeInspector.getByRole('textbox', { name: 'Block summary', exact: true }),
    'Canvas Plot block summary field',
  );
  await titleInput.click();
  await titleInput.press(process.platform === 'darwin' ? 'Meta+A' : 'Control+A');
  await titleInput.pressSequentially(nodeTitle);
  await summaryInput.click();
  await summaryInput.pressSequentially(nodeSummary);
  assert.equal(await titleInput.inputValue(), nodeTitle);
  assert.equal(await summaryInput.inputValue(), nodeSummary);
  await waitFor(
    async () => await nodeInspector.getByRole('button', { name: 'REVERT', exact: true }).isEnabled(),
    'dirty Canvas Plot inspector draft',
  );
  await pointerDragBy(page, nodeMoveHandle, -112, -66, 'move first Canvas Plot block');
  await waitFor(async () => {
    const current = await canvasGeometry(firstNode, 'first Canvas Plot block after move');
    return (differsBy(current.x, nodeBeforeMove.x, 40) || differsBy(current.y, nodeBeforeMove.y, 28))
      && await addBlock.isEnabled()
      && (await nodeMoveHandle.textContent())?.includes(nodeTitle);
  }, 'pointer-moved Canvas Plot block and flushed its inspector draft');
  const nodeGeometry = await canvasGeometry(firstNode, 'persisted first Canvas Plot block');
  record('journey', `Canvas Plot geometry command flushed unsaved inspector text for node ${firstNodeId}`);
  await dismissCanvasInspector(canvasScreen);

  const beforeFrameIds = await canvasEntityIds(frames, 'data-canvas-frame-id', 'Canvas Plot frame');
  await addFrame.click();
  const frameId = await waitForAddedCanvasEntity(
    frames,
    'data-canvas-frame-id',
    beforeFrameIds,
    'created Canvas Plot frame',
  );
  await waitCanvasCommandSettled(addBlock, 'Canvas Plot frame command to settle');
  await dismissCanvasInspector(canvasScreen);
  const frame = await waitVisible(
    canvasScreen.locator(`[data-canvas-frame-id="${frameId}"]`),
    'created Canvas Plot frame',
  );
  const frameBeforeResize = await canvasGeometry(frame, 'Canvas Plot frame before resize');
  const frameResizeHandle = await waitVisible(
    frame.locator('[data-canvas-frame-resize-handle]'),
    'Canvas Plot frame resize handle',
  );
  const frameMoveHandle = await waitVisible(
    frame.locator('[data-canvas-frame-move-handle]'),
    'Canvas Plot frame move handle for selection',
  );
  const frameMoveBounds = await frameMoveHandle.boundingBox();
  assert.ok(frameMoveBounds && frameMoveBounds.width > 80 && frameMoveBounds.height > 8, 'Canvas Plot frame move handle has no safe selection bounds');
  await page.mouse.click(
    frameMoveBounds.x + frameMoveBounds.width - 24,
    frameMoveBounds.y + frameMoveBounds.height / 2,
  );
  await waitVisible(
    canvasScreen.getByRole('form', { name: 'Canvas Plot inspector', exact: true }),
    'selected Canvas Plot frame inspector',
  );
  const frameBeforeMove = await canvasGeometry(frame, 'Canvas Plot frame before move');
  await pointerDragBy(page, frameMoveHandle, -180, 0, 'move selected Canvas Plot frame away from inspector');
  await waitFor(async () => {
    const current = await canvasGeometry(frame, 'Canvas Plot frame after move');
    return current.x <= frameBeforeMove.x - 100 && await addBlock.isEnabled();
  }, 'pointer-moved Canvas Plot frame to expose its resize handle');
  await pointerDragBy(page, frameResizeHandle, 84, 58, 'resize Canvas Plot frame');
  await waitFor(async () => {
    const current = await canvasGeometry(frame, 'Canvas Plot frame after resize');
    return (current.width >= frameBeforeResize.width + 40 || current.height >= frameBeforeResize.height + 28)
      && await addBlock.isEnabled();
  }, 'pointer-resized Canvas Plot frame to persist');
  const frameGeometry = await canvasGeometry(frame, 'persisted Canvas Plot frame');
  await dismissCanvasInspector(canvasScreen);

  const sourceHandle = await waitVisible(
    firstNode.locator('[data-canvas-node-connect-handle]'),
    'first Canvas Plot connection handle',
  );
  const targetHandle = await waitVisible(
    secondNode.locator('[data-canvas-node-connect-handle]'),
    'second Canvas Plot connection handle',
  );
  const beforeLinkIds = await canvasEntityIds(links, 'data-canvas-link-id', 'Canvas Plot connection');
  assert.equal(
    await sourceHandle.getAttribute('aria-label'),
    `Start connection from Canvas Plot block ${firstNodeId}`,
  );
  await pointerClickCenter(page, sourceHandle, 'start Canvas Plot connection');
  await waitFor(
    async () => await targetHandle.getAttribute('aria-label') === `Connect to Canvas Plot block ${secondNodeId}`,
    'Canvas Plot target connection mode',
  );
  await pointerClickCenter(page, targetHandle, 'finish Canvas Plot connection');
  record('pointer', `connected Canvas Plot block ${firstNodeId} to ${secondNodeId} with two real mouse clicks`);
  const linkId = await waitForAddedCanvasEntity(
    links,
    'data-canvas-link-id',
    beforeLinkIds,
    'created Canvas Plot connection',
  );
  await waitCanvasCommandSettled(addBlock, 'Canvas Plot connection command to settle');
  const link = canvasScreen.locator(`[data-canvas-link-id="${linkId}"]`);
  assert.equal(Number(await link.getAttribute('data-source-node-id')), firstNodeId);
  assert.equal(Number(await link.getAttribute('data-target-node-id')), secondNodeId);
  assert.deepEqual(session.pageErrors, [], 'Renderer errors occurred during Canvas Plot pointer exercise');
  record(
    'journey',
    `Canvas Plot mutations complete (nodes=${firstNodeId},${secondNodeId}; frame=${frameId}; link=${linkId})`,
  );
  await restoreCanvasPointerWorkspace(
    page,
    canvasWorkspace.collapsedRegions,
    'Canvas Plot',
  );
  return {
    nodeIds: [firstNodeId, secondNodeId],
    movedNodeId: firstNodeId,
    nodeGeometry,
    nodeTitle,
    nodeSummary,
    frameId,
    frameGeometry,
    linkId,
    sourceNodeId: firstNodeId,
    targetNodeId: secondNodeId,
    viewport,
  };
}

async function verifyPersistedCanvasPlot(session, expected) {
  const { page } = session;
  await waitProReady(session);
  const canvasSurface = await selectPanel(page, 'Canvas Plot', 'canvas-plot', 'Canvas Plot');
  const canvasScreen = await waitVisible(
    canvasSurface.locator('[data-screen-label="Canvas Plot"]'),
    'restored Canvas Plot screen',
  );
  const board = await waitVisible(
    canvasScreen.locator('[data-canvas-plot-board]'),
    'restored Canvas Plot board',
  );
  await waitFor(
    async () => await board.getAttribute('data-viewport-ready') === 'true',
    'restored Canvas Plot viewport settings hydration',
    STARTUP_TIMEOUT_MS,
  );
  const canvasWorkspace = await prepareCanvasPointerWorkspace(
    page,
    board,
    'restored Canvas Plot',
  );

  await waitFor(async () => {
    const current = await canvasViewport(board, 'restored Canvas Plot viewport');
    return Math.abs(current.zoom - expected.viewport.zoom) <= 0.01
      && Math.abs(current.cx - expected.viewport.cx) <= 0.25
      && Math.abs(current.cy - expected.viewport.cy) <= 0.25;
  }, 'project-scoped Canvas Plot viewport after relaunch', STARTUP_TIMEOUT_MS);
  const viewport = await canvasViewport(board, 'restored Canvas Plot viewport');
  assertNear(viewport.zoom, expected.viewport.zoom, 0.01, 'restored Canvas Plot zoom');
  assertNear(viewport.cx, expected.viewport.cx, 0.25, 'restored Canvas Plot center x');
  assertNear(viewport.cy, expected.viewport.cy, 0.25, 'restored Canvas Plot center y');

  const nodes = canvasScreen.locator('[data-canvas-node-id]');
  const frames = canvasScreen.locator('[data-canvas-frame-id]');
  const links = canvasScreen.locator('[data-canvas-link-id]');
  await waitFor(
    async () => (await nodes.count()) === expected.nodeIds.length
      && (await frames.count()) === 1
      && (await links.count()) === 1,
    'persisted Canvas Plot entity counts after relaunch',
    STARTUP_TIMEOUT_MS,
  );
  const restoredNodeIds = await canvasEntityIds(nodes, 'data-canvas-node-id', 'restored Canvas Plot block');
  assert.deepEqual([...restoredNodeIds].sort((left, right) => left - right), [...expected.nodeIds].sort((left, right) => left - right));

  const movedNode = await waitVisible(
    canvasScreen.locator(`[data-canvas-node-id="${expected.movedNodeId}"]`),
    'restored moved Canvas Plot block',
  );
  const nodeGeometry = await canvasGeometry(movedNode, 'restored moved Canvas Plot block');
  for (const key of ['x', 'y', 'width', 'height']) {
    assertNear(nodeGeometry[key], expected.nodeGeometry[key], 0.25, `restored Canvas Plot block ${key}`);
  }
  const restoredMoveHandle = await waitVisible(
    movedNode.locator('[data-canvas-node-move-handle]'),
    'restored moved Canvas Plot block handle',
  );
  await restoredMoveHandle.click();
  const restoredInspector = await waitVisible(
    canvasScreen.getByRole('form', { name: 'Canvas Plot inspector', exact: true }),
    'restored Canvas Plot block inspector',
  );
  const restoredTitle = restoredInspector.getByRole('textbox', { name: 'Block title', exact: true });
  const restoredSummary = restoredInspector.getByRole('textbox', { name: 'Block summary', exact: true });
  await waitFor(
    async () => await restoredTitle.inputValue() === expected.nodeTitle
      && await restoredSummary.inputValue() === expected.nodeSummary,
    'pointer-flushed Canvas Plot inspector text after relaunch',
  );
  assert.equal(await restoredTitle.inputValue(), expected.nodeTitle);
  assert.equal(await restoredSummary.inputValue(), expected.nodeSummary);
  await dismissCanvasInspector(canvasScreen);

  const frame = await waitVisible(
    canvasScreen.locator(`[data-canvas-frame-id="${expected.frameId}"]`),
    'restored resized Canvas Plot frame',
  );
  const frameGeometry = await canvasGeometry(frame, 'restored resized Canvas Plot frame');
  for (const key of ['x', 'y', 'width', 'height']) {
    assertNear(frameGeometry[key], expected.frameGeometry[key], 0.25, `restored Canvas Plot frame ${key}`);
  }

  const link = canvasScreen.locator(`[data-canvas-link-id="${expected.linkId}"]`);
  await waitFor(async () => (await link.count()) === 1, 'restored Canvas Plot connection');
  assert.equal(Number(await link.getAttribute('data-source-node-id')), expected.sourceNodeId);
  assert.equal(Number(await link.getAttribute('data-target-node-id')), expected.targetNodeId);
  assert.deepEqual(session.pageErrors, [], 'Renderer errors occurred while restoring Canvas Plot');
  await restoreCanvasPointerWorkspace(
    page,
    canvasWorkspace.collapsedRegions,
    'restored Canvas Plot',
  );
  record('journey', 'pointer-authored Canvas Plot content and viewport survived graceful packaged relaunch');
}

async function probeLiveProseEditor(page, prose, expectedText, marker, label) {
  await prose.focus();
  await prose.press(process.platform === 'darwin' ? 'Meta+ArrowDown' : 'Control+End');
  await page.keyboard.insertText(marker);
  await waitFor(
    async () => await prose.innerText() === `${expectedText}${marker}`,
    `${label} ProseMirror edit`,
  );
  await prose.press(process.platform === 'darwin' ? 'Meta+Z' : 'Control+Z');
  await waitFor(
    async () => await prose.innerText() === expectedText,
    `${label} ProseMirror undo`,
  );
  await prose.press(process.platform === 'darwin' ? 'Meta+S' : 'Control+S');
}

async function exerciseNativeManuscriptWindow(session, expected) {
  const { page } = session;
  const manuscriptSurface = await selectPanel(page, 'Manuscript', 'manuscript', 'Manuscript Editor');
  const manuscriptWorkspace = await prepareCanvasPointerWorkspace(
    page,
    manuscriptSurface,
    'Manuscript editor',
  );
  const scene = manuscriptSurface.locator(`[data-scene-id="${expected.openingSceneId}"]`).first();
  await scene.waitFor({ state: 'attached', timeout: UI_TIMEOUT_MS });
  await scene.scrollIntoViewIfNeeded({ timeout: UI_TIMEOUT_MS });
  const staticProse = scene.getByRole('button', {
    name: `Activate prose editor for ${expected.openingSceneTitle}`,
    exact: true,
  });
  if (await staticProse.count() > 0 && await staticProse.isVisible()) await staticProse.click();
  const dockedProse = await waitVisible(scene.locator('[data-prose]'), 'docked live Manuscript editor');
  await waitFor(
    async () => await dockedProse.innerText() === expected.savedOpeningContent,
    'current Manuscript content before native detach',
  );

  const manuscriptWindowPromise = session.app.waitForEvent('window', {
    predicate: async (candidate) => {
      try {
        return await candidate.evaluate(() => (
          /^logosforge-panel:manuscript:[A-Za-z0-9_-]{16,128}$/.test(window.name)
        ));
      } catch {
        return false;
      }
    },
    timeout: STARTUP_TIMEOUT_MS,
  });
  const floatManuscript = await waitVisible(
    page.locator('[data-dock-drop-region="center"]')
      .getByRole('button', { name: 'Float Manuscript', exact: true }),
    'Float Manuscript control',
  );
  await floatManuscript.click();
  const manuscriptWindow = await manuscriptWindowPromise;
  attachPageDiagnostics(session, manuscriptWindow, 'manuscript-native-window');
  const nativeSurface = manuscriptWindow.locator('section[data-panel-id="manuscript"]').first();
  await waitFor(
    async () => (await nativeSurface.getAttribute('data-native-floating-panel')) === 'true'
      && await nativeSurface.isVisible(),
    'native Manuscript window',
  );
  const nativeScene = nativeSurface.locator(`[data-scene-id="${expected.openingSceneId}"]`).first();
  await nativeScene.scrollIntoViewIfNeeded({ timeout: UI_TIMEOUT_MS });
  const nativeProse = await waitVisible(
    nativeScene.locator('[data-prose]'),
    'live Manuscript editor in native window',
  );
  await waitFor(
    async () => await nativeProse.innerText() === expected.savedOpeningContent,
    'preserved Manuscript state after native detach',
  );
  await probeLiveProseEditor(
    manuscriptWindow,
    nativeProse,
    expected.savedOpeningContent,
    'x',
    'detached Manuscript',
  );
  await waitVisible(
    nativeSurface.locator('[data-save-status="saved"]'),
    'saved detached Manuscript probe',
    SAVE_BARRIER_TIMEOUT_MS,
  );
  await waitFor(async () => {
    const persisted = await packagedCoreJson(
      session,
      `/api/projects/${expected.projectId}/scenes/${expected.openingSceneId}`,
    );
    return persisted.content === expected.savedOpeningContent;
  }, 'restored canonical prose after detached Manuscript probe', SAVE_BARRIER_TIMEOUT_MS);

  const titlebar = await waitVisible(
    manuscriptWindow.getByRole('toolbar', { name: 'Manuscript native window controls', exact: true }),
    'Manuscript native window controls',
  );
  const manuscriptWindowClosed = manuscriptWindow.waitForEvent('close');
  await clickAndWaitForNativeWindowClose(
    titlebar.getByRole('button', { name: 'Dock Manuscript to center', exact: true }),
    manuscriptWindowClosed,
    'Manuscript native window redock',
  );

  const redockedSurface = page.locator(
    'section[data-panel-id="manuscript"][data-dock-region="center"]',
  ).first();
  await waitVisible(redockedSurface, 'redocked Manuscript workspace surface');
  const redockedScene = redockedSurface.locator(`[data-scene-id="${expected.openingSceneId}"]`).first();
  await redockedScene.scrollIntoViewIfNeeded({ timeout: UI_TIMEOUT_MS });
  const redockedProse = await waitVisible(
    redockedScene.locator('[data-prose]'),
    'live redocked Manuscript editor',
  );
  await waitFor(
    async () => await redockedProse.innerText() === expected.savedOpeningContent,
    'preserved Manuscript state after redock',
  );
  await probeLiveProseEditor(
    page,
    redockedProse,
    expected.savedOpeningContent,
    'y',
    'redocked Manuscript',
  );
  await waitVisible(
    redockedSurface.locator('[data-save-status="saved"]'),
    'saved redocked Manuscript probe',
    SAVE_BARRIER_TIMEOUT_MS,
  );
  await waitFor(async () => {
    const persisted = await packagedCoreJson(
      session,
      `/api/projects/${expected.projectId}/scenes/${expected.openingSceneId}`,
    );
    return persisted.content === expected.savedOpeningContent;
  }, 'restored canonical prose after redocked Manuscript probe', SAVE_BARRIER_TIMEOUT_MS);
  await restoreCanvasPointerWorkspace(
    page,
    manuscriptWorkspace.collapsedRegions,
    'Manuscript editor',
  );
  assert.deepEqual(session.pageErrors, [], 'Renderer errors occurred during the native Manuscript editor exercise');
  record('journey', 'live Manuscript editing survived native detach and redock without changing canonical prose');
}

async function leaveBillyDetachedForRelaunch(session) {
  const { page } = session;
  const dockedSurface = await activateBillyDock(page);
  const billyTab = await waitVisible(
    dockedSurface.getByTitle('Billy', { exact: true }),
    'Billy companion tab before native detach',
  );
  await waitFor(
    async () => await billyTab.getAttribute('aria-pressed') === 'true',
    'Billy selection before native detach',
  );
  const floatBilly = await waitVisible(
    page.getByRole('button', { name: 'Float AI Companions', exact: true }),
    'Float AI Companions control',
  );
  await floatBilly.click();
  const panelWindow = await waitForNativePanelWindow(
    session,
    'ai-companions',
    'detached AI Companions native window',
  );
  await verifyBillyNativePanel(session, panelWindow, 'detached AI Companions native window');
  record('journey', 'Billy remained selected while AI Companions was left detached for relaunch');
}

async function verifyPersistedBillyNativeWindow(session) {
  const [ready, panelWindow] = await Promise.all([
    waitProReady(session),
    waitForNativePanelWindow(
      session,
      'ai-companions',
      'restored AI Companions native window',
    ),
  ]);
  await verifyBillyNativePanel(session, panelWindow, 'restored AI Companions native window');
  record('journey', 'persisted detached AI Companions restored with Billy selected and no runtime fault');
  return { panelWindow, projectId: ready.projectId };
}

async function redockPersistedBillyNativeWindow(session, panelWindow) {
  const titlebar = await waitVisible(
    panelWindow.getByRole('toolbar', { name: 'AI Companions native window controls', exact: true }),
    'restored AI Companions native window controls',
  );
  const panelWindowClosed = panelWindow.waitForEvent('close');
  await clickAndWaitForNativeWindowClose(
    titlebar.getByRole('button', { name: 'Dock AI Companions to right', exact: true }),
    panelWindowClosed,
    'AI Companions native window redock',
  );
  const redocked = session.page.locator(
    'section[data-panel-id="ai-companions"][data-dock-region="right"]',
  ).first();
  await waitFor(
    async () => (await redocked.count()) === 1
      && await redocked.getAttribute('data-floating-panel') === null,
    'redocked AI Companions in the right workspace region',
  );
}

async function exercisePointerWorkspace(session, manuscriptExpected) {
  const { page } = session;
  const { workspace, projectId } = await waitProReady(session);

  await exerciseNativeManuscriptWindow(session, manuscriptExpected);

  const notesSurface = await selectPanel(page, 'Notes', 'notes', 'Notes Panel');
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
  const notesWindowPromise = session.app.waitForEvent('window', {
    predicate: async (candidate) => {
      try {
        return await candidate.evaluate(() => (
          /^logosforge-panel:notes:[A-Za-z0-9_-]{16,128}$/.test(window.name)
        ));
      } catch {
        return false;
      }
    },
    timeout: STARTUP_TIMEOUT_MS,
  });
  await notesTab.dragTo(workspace, { targetPosition });
  const notesWindow = await notesWindowPromise;
  attachPageDiagnostics(session, notesWindow, 'notes-native-window');
  const nativeNotesSurface = notesWindow.locator('section[data-panel-id="notes"]').first();
  await waitFor(
    async () => (await nativeNotesSurface.getAttribute('data-floating-panel')) === 'true'
      && (await nativeNotesSurface.getAttribute('data-native-floating-panel')) === 'true'
      && (await nativeNotesSurface.getAttribute('role')) === 'dialog'
      && await nativeNotesSurface.isVisible(),
    'pointer tear-off to create a native modeless Notes window',
  );
  assert.match(
    await notesWindow.evaluate(() => window.name),
    /^logosforge-panel:notes:[A-Za-z0-9_-]{16,128}$/,
    'Notes native window used an unexpected frame identity',
  );
  record('pointer', 'Notes tab torn off with a real drag gesture into an OS window');

  const titlebar = await waitVisible(
    notesWindow.getByRole('toolbar', { name: 'Notes native window controls', exact: true }),
    'Notes native window controls',
  );
  const nativeGeometry = await session.app.evaluate(({ BrowserWindow, screen }) => {
    const windows = BrowserWindow.getAllWindows();
    const main = windows.find((candidate) => candidate.webContents.getURL() !== 'about:blank');
    const panel = windows.find((candidate) => candidate.webContents.getURL() === 'about:blank');
    if (!main || !panel) throw new Error('Could not resolve main and Notes BrowserWindows');
    const preferences = panel.webContents.getLastWebPreferences();
    const displays = screen.getAllDisplays();
    const mainBounds = main.getBounds();
    const mainDisplay = screen.getDisplayMatching(mainBounds);
    const targetDisplay = displays.find((display) => display.id !== mainDisplay.id) ?? mainDisplay;
    const work = targetDisplay.workArea;
    const width = Math.min(760, Math.max(420, work.width - 32));
    const height = Math.min(620, Math.max(320, work.height - 32));
    const x = targetDisplay.id !== mainDisplay.id
      ? work.x + 16
      : Math.max(work.x, work.x + work.width - width - 16);
    const y = work.y + 16;
    panel.setBounds({ x, y, width, height });
    panel.focus();
    return {
      windowCount: windows.length,
      displayCount: displays.length,
      mainDisplayId: mainDisplay.id,
      targetDisplayId: targetDisplay.id,
      parentIsNull: panel.getParentWindow() === null,
      modal: panel.isModal(),
      mainBounds,
      targetBounds: { x, y, width, height },
      preferences: {
        contextIsolation: preferences.contextIsolation,
        nodeIntegration: preferences.nodeIntegration,
        sandbox: preferences.sandbox,
      },
    };
  });
  assert.equal(nativeGeometry.windowCount, 2, 'Notes tear-off did not create exactly one native panel window');
  assert.deepEqual(
    nativeGeometry.preferences,
    { contextIsolation: true, nodeIntegration: false, sandbox: true },
    'Notes native window security preferences changed',
  );
  assert.equal(nativeGeometry.parentIsNull, true, 'Notes native window is still parent-constrained');
  assert.equal(nativeGeometry.modal, false, 'Notes native window unexpectedly became modal');
  let settledPanelBounds = null;
  await waitFor(async () => {
    settledPanelBounds = await session.app.evaluate(({ BrowserWindow }) => {
      const panel = BrowserWindow.getAllWindows()
        .find((candidate) => candidate.webContents.getURL() === 'about:blank');
      return panel?.getBounds() ?? null;
    });
    if (!settledPanelBounds) return false;
    return ['x', 'y', 'width', 'height'].every(
      (key) => Math.abs(settledPanelBounds[key] - nativeGeometry.targetBounds[key]) <= 2,
    );
  }, 'native Notes window bounds to settle');
  const mb = nativeGeometry.mainBounds;
  const pb = settledPanelBounds;
  const containedByMain = pb.x >= mb.x && pb.y >= mb.y
    && pb.x + pb.width <= mb.x + mb.width
    && pb.y + pb.height <= mb.y + mb.height;
  if (nativeGeometry.displayCount > 1) {
    const settledDisplayId = await session.app.evaluate(({ BrowserWindow, screen }) => {
      const panel = BrowserWindow.getAllWindows()
        .find((candidate) => candidate.webContents.getURL() === 'about:blank');
      return panel ? screen.getDisplayMatching(panel.getBounds()).id : null;
    });
    assert.notEqual(
      nativeGeometry.targetDisplayId,
      nativeGeometry.mainDisplayId,
      'Multi-display acceptance did not select a second display',
    );
    assert.equal(settledDisplayId, nativeGeometry.targetDisplayId, 'Notes did not settle on the selected display');
  }
  record(
    'native-window',
    `Notes is unparented/modeless and moved${nativeGeometry.displayCount > 1 ? ' onto another display' : containedByMain ? ' within the available single-display work area' : ' outside the main window'}: ${JSON.stringify(pb)}`,
  );

  await nativeNotesSurface.getByRole('button', { name: 'Minimize Notes', exact: true }).click();
  const restoreNotes = await waitVisible(
    page.getByRole('button', { name: 'Restore Notes', exact: true }),
    'minimized Notes restore control',
  );
  await waitFor(
    () => session.app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()
      .some((candidate) => candidate.webContents.getURL() === 'about:blank' && candidate.isMinimized())),
    'native Notes window to minimize',
  );
  await restoreNotes.click();
  await waitFor(
    async () => await nativeNotesSurface.isVisible()
      && (await nativeNotesSurface.getAttribute('data-native-floating-panel')) === 'true'
      && await session.app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()
        .some((candidate) => candidate.webContents.getURL() === 'about:blank' && !candidate.isMinimized())),
    'pointer-restored Notes native window',
  );

  const notesWindowClosed = notesWindow.waitForEvent('close');
  await clickAndWaitForNativeWindowClose(
    titlebar.getByRole('button', { name: 'Dock Notes to left', exact: true }),
    notesWindowClosed,
    'Notes native window redock',
  );
  await waitFor(
    async () => (await notesSurface.getAttribute('data-dock-region')) === 'left'
      && (await notesSurface.getAttribute('role')) === 'tabpanel'
      && await notesSurface.isVisible(),
    'redocked Notes in the left workspace region',
  );

  await leaveBillyDetachedForRelaunch(session);

  await page.getByRole('button', { name: 'Collapse right dock', exact: true }).click();
  await waitVisible(
    page.getByRole('button', { name: 'Expand right dock', exact: true }),
    'collapsed right dock strip',
  );
  const leftResizer = await waitVisible(
    page.getByRole('separator', { name: 'Resize left workspace dock', exact: true }),
    'left workspace dock resizer',
  );
  await waitFor(async () => {
    const current = Number(await leftResizer.getAttribute('aria-valuenow'));
    const maximum = Number(await leftResizer.getAttribute('aria-valuemax'));
    return Number.isFinite(current) && Number.isFinite(maximum) && maximum - current >= 64;
  }, 'left workspace dock pointer-resize capacity');
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
  return { projectId, leftDockSizePx, detachedAiCompanions: true };
}

async function verifyPersistedWorkspace(session, expected) {
  const { page } = session;
  const { projectId } = await waitProReady(session);
  assert.equal(projectId, expected.projectId, 'Packaged relaunch resumed the wrong project');
  const expandLeft = await waitVisible(
    page.getByRole('button', { name: 'Expand left dock', exact: true }),
    'persisted collapsed left dock after relaunch',
  );
  await waitVisible(
    page.getByRole('button', { name: 'Expand right dock', exact: true }),
    'persisted collapsed right dock after relaunch',
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

async function verifyPersistedIntelligence(session, expected) {
  const { projectId } = await waitProReady(session);
  assert.equal(projectId, expected.projectId, 'Packaged relaunch resumed the wrong intelligence project');
  const [scene, radar, continuity] = await Promise.all([
    packagedCoreJson(session, `/api/projects/${projectId}/scenes/${expected.openingSceneId}`),
    packagedCoreJson(session, `/api/projects/${projectId}/decision-radar`),
    packagedCoreJson(session, `/api/projects/${projectId}/continuity`),
  ]);
  assert.equal(scene.content, expected.savedOpeningContent, 'Confirmed Controlled Apply mutation did not survive relaunch');
  assert.ok(
    radar.knowledge_graph_cards.some((card) => card.id === expected.graphCardId),
    'Traceable Knowledge Graph card did not survive packaged relaunch',
  );
  assert.equal(
    radar.continuity_cards.some((card) => card.id === expected.continuityCardId),
    false,
    'Resolved Continuity decision became actionable again after packaged relaunch',
  );
  const issue = continuity.issues.find((candidate) => candidate.id === expected.continuityIssueId);
  assert.equal(
    issue?.status,
    expected.continuityIssueStatus,
    'Durable Continuity review state did not survive packaged relaunch',
  );
  record('journey', 'Graph evidence, Continuity review state, and the confirmed Controlled Apply mutation survived packaged relaunch');
}

async function verifyPersistedProgressions(session, expected) {
  const { page } = session;
  const { projectId } = await waitProReady(session);
  assert.equal(projectId, expected.projectId, 'Packaged relaunch resumed the wrong Progressions project');
  const [snapshot, radar, graph, dashboard] = await Promise.all([
    packagedCoreJson(session, `/api/projects/${projectId}/progressions`),
    packagedCoreJson(session, `/api/projects/${projectId}/decision-radar`),
    packagedCoreJson(session, `/api/projects/${projectId}/knowledge-graph`),
    packagedCoreJson(session, `/api/projects/${projectId}/dashboard`),
  ]);
  const track = snapshot.tracks.find((candidate) => candidate.id === expected.trackId);
  assert.ok(track, `Persisted Progressions track ${expected.trackId} is missing`);
  assert.equal(snapshot.revision, expected.finalRevision, 'Persisted Progressions revision changed across relaunch');
  assert.deepEqual(
    snapshot.tracks.slice(0, 2).map((candidate) => candidate.id),
    [expected.characterTrackId, expected.trackId],
    'Persisted Progressions track order changed across relaunch',
  );
  assert.equal(track.title, expected.trackTitle, 'Persisted Progressions track title changed');
  assert.deepEqual(
    track.beats.map((beat) => ({
      id: beat.id,
      text: beat.text,
      anchor_kind: beat.anchor_kind,
      scene_id: beat.scene_id,
      anchor_ref: beat.anchor_ref,
      anchor_label: beat.anchor_label,
    })),
    [
      {
        id: expected.crossingBeatId,
        text: expected.crossingBeatText,
        anchor_kind: 'scene',
        scene_id: expected.crossingSceneId,
        anchor_ref: null,
        anchor_label: '',
      },
      {
        id: expected.openingBeatId,
        text: expected.openingBeatText,
        anchor_kind: 'scene',
        scene_id: expected.openingSceneId,
        anchor_ref: null,
        anchor_label: '',
      },
      {
        id: expected.documentBeatId,
        text: expected.documentBeatText,
        anchor_kind: 'document_block',
        scene_id: null,
        anchor_ref: expected.documentAnchorRef,
        anchor_label: expected.documentAnchorLabel,
      },
      {
        id: expected.unanchoredBeatId,
        text: expected.unanchoredBeatText,
        anchor_kind: 'unanchored',
        scene_id: null,
        anchor_ref: null,
        anchor_label: '',
      },
    ],
    'Persisted Progressions beat identities, order, or anchors changed',
  );
  const characterTrack = snapshot.tracks.find((candidate) => candidate.id === expected.characterTrackId);
  assert.ok(characterTrack, `Persisted PSYKE-subject track ${expected.characterTrackId} is missing`);
  assert.equal(characterTrack.title, expected.characterTrackTitle);
  assert.equal(characterTrack.kind, 'character');
  assert.equal(characterTrack.primary_psyke_entry_id, expected.characterSubjectId);
  assert.equal(characterTrack.primary_psyke_entry_name, 'Alice');
  assert.equal(characterTrack.primary_psyke_entry_type, 'character');
  for (const receiptExpectation of expected.receiptExpectations) {
    await assertProgressionReceipt(
      session,
      receiptExpectation,
      `persisted ${receiptExpectation.commandKind}`,
    );
  }
  assert.ok(
    track.coverage.out_of_order_beat_ids.includes(expected.openingBeatId),
    'Persisted Progressions lost its out-of-order diagnostic',
  );
  assert.ok(
    radar.knowledge_graph_cards.some((card) => card.id === expected.radarCardId),
    'Persisted Progressions Radar evidence disappeared after relaunch',
  );
  const graphKeys = new Set(graph.nodes.map((node) => node.key));
  assert.ok(graphKeys.has(expected.trackGraphKey), 'Persisted Progressions Graph track disappeared');
  assert.ok(
    graphKeys.has(`progression_track:progressions:${expected.characterTrackId}`),
    'Persisted Progressions Graph PSYKE-subject track disappeared',
  );
  for (const beatId of [
    expected.crossingBeatId,
    expected.openingBeatId,
    expected.documentBeatId,
    expected.unanchoredBeatId,
  ]) {
    assert.ok(
      graphKeys.has(`progression_beat:progressions:${beatId}`),
      `Persisted Progressions Graph beat ${beatId} disappeared`,
    );
  }
  const progressionCounts = new Map(
    dashboard.tension.points.map((point) => [point.scene_id, point.progression_count]),
  );
  assert.equal(progressionCounts.get(expected.openingSceneId), 1);
  assert.equal(progressionCounts.get(expected.crossingSceneId), 1);

  let progressionSurface = await selectPanel(
    page,
    'Progressions',
    'progressions',
    'BIBLE · PROGRESSIONS',
  );
  const persistedStoryTrack = await waitVisible(
    progressionSurface.locator(`[data-progression-track-id="${expected.trackId}"]`),
    'persisted Progressions track in the real shell',
  );
  await persistedStoryTrack.click();
  await waitVisible(
    progressionSurface.locator(`[data-progression-beat-id="${expected.unanchoredBeatId}"]`),
    'persisted Progressions beat in the real shell',
  );
  await waitVisible(
    progressionSurface.locator(`[data-progression-track-id="${expected.characterTrackId}"]`),
    'persisted PSYKE-subject Progressions track in the real shell',
  );
  const radarSurface = await selectPanel(page, 'Decision Radar', 'decision-radar', 'Decision Radar');
  await waitVisible(
    radarSurface.locator(`[data-decision-card-id="${expected.radarCardId}"]`),
    'persisted Progressions Radar card in the real shell',
  );
  const graphSurface = await selectPanel(page, 'Graph', 'graph', 'Knowledge Graph');
  await waitVisible(
    graphSurface.locator(`[data-graph-node-key="${expected.trackGraphKey}"]`),
    'persisted Progressions Graph track in the real shell',
  );
  progressionSurface = await selectPanel(
    page,
    'Progressions',
    'progressions',
    'BIBLE · PROGRESSIONS',
  );
  assert.equal(
    await progressionSurface.getAttribute('data-dock-region'),
    'bottom',
    'Progressions did not preserve its redocked workspace placement',
  );
  assert.deepEqual(session.pageErrors, [], 'Renderer errors occurred while restoring Progressions');
  record(
    'journey',
    'Progressions commands, diagnostics, Graph/Radar evidence, Dashboard counts, and panel placement survived graceful packaged relaunch',
  );
}

async function writeProgressionBundleFixture(root) {
  const fixtureDir = path.join(root, 'fixtures');
  const bundlePath = path.join(fixtureDir, 'packaged-whiteboard-progressions.lfbundle');
  const bundle = {
    format: 'logosforge-project-bundle',
    version: '1.0',
    exportedAt: now(),
    source: { app: 'logosforge-whiteboard' },
    project: {
      id: 'packaged-whiteboard-source',
      title: 'Packaged Whiteboard Progressions',
      mode: 'novel',
      settings: {},
      manuscript: {
        blocks: [
          { id: 'block-1', type: 'heading', text: 'Imported Chapter', level: 1, sp: null, marks: [] },
          { id: 'block-2', type: 'paragraph', text: 'Mara listens before answering.', level: null, sp: null, marks: [] },
        ],
      },
      outline: [],
      comments: [],
      drafter: { pages: [] },
      psyke: {
        elements: [{
          id: '41',
          name: 'Mara',
          entry_type: 'character',
          aliases: [],
          description: 'Imported Whiteboard character.',
          notes: '',
        }],
        relations: [],
        progressions: [],
      },
      progression_tracks: [
        {
          id: 70,
          kind: 'story',
          title: 'Imported empty story arc',
          description: 'An intentionally empty canonical track.',
          color_label: 'blue',
          sort_order: 0,
          legacy_compatibility: false,
          primary_psyke_entry_id: null,
          primary_psyke_entry_name: '',
          primary_psyke_entry_type: '',
          secondary_psyke_entry_id: null,
          secondary_psyke_entry_name: '',
          secondary_psyke_entry_type: '',
          beats: [],
        },
        {
          id: 71,
          kind: 'character',
          title: 'Mara answers the signal',
          description: 'A Whiteboard-authored, PSYKE-bound character arc.',
          color_label: 'amber',
          sort_order: 1,
          legacy_compatibility: false,
          primary_psyke_entry_id: 41,
          primary_psyke_entry_name: 'Mara',
          primary_psyke_entry_type: 'character',
          secondary_psyke_entry_id: null,
          secondary_psyke_entry_name: '',
          secondary_psyke_entry_type: '',
          beats: [{
            id: 72,
            track_id: 71,
            text: 'Mara writes the answer alone.',
            sort_order: 0,
            anchor_kind: 'document_block',
            scene_id: null,
            scene_title: '',
            anchor_ref: 'drafter:imported:block-9',
            anchor_label: 'Imported private draft',
          }],
        },
      ],
    },
  };
  await fs.mkdir(fixtureDir, { recursive: true });
  await fs.writeFile(bundlePath, JSON.stringify(bundle, null, 2), 'utf8');
  record('fixture', `wrote Whiteboard-format Progressions bundle: ${bundlePath}`);
  return bundlePath;
}

async function routeNextNativeOpenDialog(session, filePath) {
  await assertFile(filePath, 'Progressions .lfbundle fixture');
  const installed = await session.app.evaluate(({ dialog }, selectedPath) => {
    const original = dialog.showOpenDialog.bind(dialog);
    dialog.showOpenDialog = async (...args) => {
      dialog.showOpenDialog = original;
      return { canceled: false, filePaths: [selectedPath], bookmarks: [] };
    };
    return typeof dialog.showOpenDialog === 'function';
  }, filePath);
  assert.equal(installed, true, 'Could not route the packaged native Open dialog to the bundle fixture');
}

async function exerciseProgressionBundleImport(session, bundlePath, previousProjectId) {
  const { page } = session;
  await waitProReady(session);
  let projectsSurface = await selectPanel(page, 'Projects', 'projects', 'Projects');
  await routeNextNativeOpenDialog(session, bundlePath);
  await projectsSurface.getByRole('button', { name: '⇩ IMPORT PROJECT', exact: true }).click();
  let importedProjectId = null;
  await waitFor(async () => {
    const select = page.locator('aside.rail > label.field > select').nth(1);
    const candidate = Number(await select.inputValue());
    if (Number.isSafeInteger(candidate) && candidate > 0 && candidate !== previousProjectId) {
      importedProjectId = candidate;
      return true;
    }
    return false;
  }, 'Whiteboard bundle project handoff', STARTUP_TIMEOUT_MS);
  assert.ok(importedProjectId);
  // Project handoff restores the imported workspace's saved panel selection, so
  // explicitly reopen Projects before asserting the import receipt rendered by
  // the production UI.
  projectsSurface = await selectPanel(page, 'Projects', 'projects', 'Projects');
  await waitVisible(
    projectsSurface.getByText(/Imported “Packaged Whiteboard Progressions”/),
    'Whiteboard bundle import accounting',
    STARTUP_TIMEOUT_MS,
  );
  await waitVisible(
    projectsSurface.getByText(/2 Progressions tracks/),
    'Whiteboard bundle Progressions-track accounting',
  );
  await waitVisible(
    projectsSurface.getByText(/1 tracked beat/),
    'Whiteboard bundle Progressions-beat accounting',
  );
  const snapshot = await packagedCoreJson(
    session,
    `/api/projects/${importedProjectId}/progressions`,
  );
  assert.deepEqual(
    snapshot.tracks.map((track) => track.title),
    ['Imported empty story arc', 'Mara answers the signal'],
    'Whiteboard bundle did not preserve canonical Progressions track order',
  );
  const emptyTrack = snapshot.tracks[0];
  const characterTrack = snapshot.tracks[1];
  assert.equal(emptyTrack.kind, 'story');
  assert.equal(emptyTrack.beats.length, 0, 'Whiteboard bundle did not preserve its empty track');
  assert.equal(emptyTrack.coverage.status, 'empty');
  assert.equal(characterTrack.kind, 'character');
  assert.ok(Number.isSafeInteger(characterTrack.primary_psyke_entry_id));
  assert.notEqual(characterTrack.primary_psyke_entry_id, 41, 'Whiteboard source PSYKE id leaked into Pro');
  assert.equal(characterTrack.primary_psyke_entry_name, 'Mara');
  assert.equal(characterTrack.primary_psyke_entry_type, 'character');
  assert.equal(characterTrack.beats.length, 1);
  const [beat] = characterTrack.beats;
  assert.equal(beat.text, 'Mara writes the answer alone.');
  assert.equal(beat.anchor_kind, 'document_block');
  assert.equal(beat.anchor_ref, 'drafter:imported:block-9');
  assert.equal(beat.anchor_label, 'Imported private draft');
  const progressionSurface = await selectPanel(
    page,
    'Progressions',
    'progressions',
    'BIBLE · PROGRESSIONS',
  );
  await waitVisible(
    progressionSurface.locator(`[data-progression-track-id="${emptyTrack.id}"]`),
    'imported empty Progressions track in production UI',
  );
  const importedCharacterTrack = await waitVisible(
    progressionSurface.locator(`[data-progression-track-id="${characterTrack.id}"]`),
    'imported PSYKE-subject Progressions track in production UI',
  );
  await importedCharacterTrack.click();
  await waitVisible(
    progressionSurface.locator(`[data-progression-beat-id="${beat.id}"]`),
    'imported document-anchored Progressions beat in production UI',
  );
  record('journey', `packaged UI imported Whiteboard Progressions bundle into project ${importedProjectId}`);
  return {
    projectId: importedProjectId,
    revision: snapshot.revision,
    emptyTrackId: emptyTrack.id,
    characterTrackId: characterTrack.id,
    characterSubjectId: characterTrack.primary_psyke_entry_id,
    beatId: beat.id,
  };
}

async function verifyPersistedProgressionBundleImport(session, expected) {
  const { page } = session;
  const { projectId } = await waitProReady(session);
  assert.equal(projectId, expected.projectId, 'Packaged relaunch did not resume the imported Whiteboard project');
  const snapshot = await packagedCoreJson(session, `/api/projects/${projectId}/progressions`);
  assert.equal(snapshot.revision, expected.revision, 'Imported Progressions revision changed across relaunch');
  const emptyTrack = snapshot.tracks.find((track) => track.id === expected.emptyTrackId);
  const characterTrack = snapshot.tracks.find((track) => track.id === expected.characterTrackId);
  assert.equal(emptyTrack?.coverage.status, 'empty');
  assert.equal(emptyTrack?.beats.length, 0);
  assert.equal(characterTrack?.primary_psyke_entry_id, expected.characterSubjectId);
  const beat = characterTrack?.beats.find((candidate) => candidate.id === expected.beatId);
  assert.equal(beat?.anchor_kind, 'document_block');
  assert.equal(beat?.anchor_ref, 'drafter:imported:block-9');
  assert.equal(beat?.anchor_label, 'Imported private draft');
  const progressionSurface = await selectPanel(
    page,
    'Progressions',
    'progressions',
    'BIBLE · PROGRESSIONS',
  );
  await waitVisible(
    progressionSurface.locator(`[data-progression-track-id="${expected.emptyTrackId}"]`),
    'persisted imported empty Progressions track',
  );
  const persistedImportedCharacter = await waitVisible(
    progressionSurface.locator(`[data-progression-track-id="${expected.characterTrackId}"]`),
    'persisted imported PSYKE-subject Progressions track',
  );
  await persistedImportedCharacter.click();
  await waitVisible(
    progressionSurface.locator(`[data-progression-beat-id="${expected.beatId}"]`),
    'persisted imported document-anchored Progressions beat',
  );
  record('journey', 'Whiteboard Progressions bundle, remapped PSYKE subject, empty track, order, and document anchor survived packaged relaunch');
}

async function clearOriginProgressionRecovery(page) {
  return page.evaluate((prefix) => {
    const removedKeys = Object.keys(localStorage).filter((key) => key.startsWith(prefix));
    for (const key of removedKeys) localStorage.removeItem(key);
    return { origin: location.origin, removedKeys };
  }, PROGRESSION_RECOVERY_STORAGE_PREFIX);
}

async function inspectDesktopProgressionRecovery(page, storageKey) {
  const inspection = await page.evaluate(async ({ key, prefix }) => {
    const load = globalThis.logosforge?.loadProgressionCommandRecovery;
    const originEntries = Object.entries(localStorage)
      .filter(([candidate]) => candidate.startsWith(prefix))
      .map(([candidate, value]) => ({ key: candidate, value }));
    return {
      apiType: typeof load,
      origin: location.origin,
      originEntries,
      value: typeof load === 'function'
        ? await globalThis.logosforge.loadProgressionCommandRecovery(key)
        : null,
    };
  }, { key: storageKey, prefix: PROGRESSION_RECOVERY_STORAGE_PREFIX });
  assert.equal(
    inspection.apiType,
    'function',
    'Packaged desktop did not expose its narrow Progressions recovery loader',
  );
  return inspection;
}

async function stageProgressionReceiptRecoveryAcrossCrash(session, expectedProjectId) {
  const { page } = session;
  const { projectId } = await waitProReady(session);
  assert.equal(projectId, expectedProjectId, 'Crash-recovery setup resumed the wrong project');
  const storageKey = `${PROGRESSION_RECOVERY_STORAGE_PREFIX}logosforge-pro-desktop-local-core:${projectId}`;
  const originCleanup = await clearOriginProgressionRecovery(page);
  assert.deepEqual(
    await page.evaluate(
      (prefix) => Object.keys(localStorage).filter((key) => key.startsWith(prefix)),
      PROGRESSION_RECOVERY_STORAGE_PREFIX,
    ),
    [],
    'Origin-local Progressions recovery storage could not be cleared before crash staging',
  );
  record(
    'transaction',
    `cleared ${originCleanup.removedKeys.length} origin-local recovery entries at ${originCleanup.origin}`,
  );
  const progressionsSurface = await selectPanel(
    page,
    'Progressions',
    'progressions',
    'BIBLE · PROGRESSIONS',
  );
  const title = 'Committed before packaged Core restart';
  const commandPath = `/api/projects/${projectId}/progressions/commands`;
  const receiptPath = `/api/projects/${projectId}/progressions/command-receipt`;
  let committed = null;
  let routeFailure = null;
  let commandDeliveries = 0;
  const commandHandler = async (route) => {
    try {
      const command = route.request().postDataJSON();
      if (command.kind !== 'create_track' || command.title !== title) {
        await route.continue();
        return;
      }
      commandDeliveries += 1;
      const headers = await route.request().allHeaders();
      const idempotencyKey = headers['idempotency-key'];
      assert.ok(idempotencyKey, 'Crash-recovery command omitted its idempotency key');
      const response = await route.fetch();
      const result = await response.json();
      assert.equal(response.status(), 200, 'Crash-recovery command did not commit before response loss');
      committed = { command, idempotencyKey, result };
      await route.abort('failed');
    } catch (error) {
      routeFailure = error;
      await route.abort('failed').catch(() => undefined);
    }
  };
  const receiptHandler = async (route) => {
    // Model a disconnected Core immediately after commit: the renderer cannot
    // yet prove whether the command landed, so it must durably retain the exact
    // key/command and become receipt-only before this process is crashed.
    await route.abort('failed');
  };
  await page.route(`**${commandPath}`, commandHandler);
  await page.route(`**${receiptPath}`, receiptHandler);
  try {
    await progressionsSurface.getByRole('button', { name: '+ TRACK', exact: true }).click();
    const editor = await waitVisible(
      progressionsSurface.getByRole('dialog', { name: 'Progression track editor', exact: true }),
      'crash-recovery Progressions editor',
    );
    await editor.locator('label').filter({ hasText: 'TITLE' }).locator('input').fill(title);
    await editor.locator('label').filter({ hasText: 'KIND' }).locator('select').selectOption('story');
    await editor.getByRole('button', { name: 'SAVE', exact: true }).click();
    await waitVisible(
      progressionsSurface.getByRole('button', { name: 'CHECK RECEIPT', exact: true }),
      'receipt-only recovery control before packaged crash',
      STARTUP_TIMEOUT_MS,
    );
    await waitFor(
      async () => compactUiText(await progressionsSurface.getByRole('alert').textContent())
        .includes('receipt-only'),
      'receipt-only Progressions status before packaged crash',
    );
  } finally {
    await page.unroute(`**${commandPath}`, commandHandler);
    await page.unroute(`**${receiptPath}`, receiptHandler);
  }
  if (routeFailure) throw routeFailure;
  assert.ok(committed, 'Crash-recovery Progressions command never committed upstream');
  assert.equal(commandDeliveries, 1, 'Crash-recovery Progressions command was delivered more than once');
  assert.equal(committed.result.changed, true);
  assert.equal(committed.result.replayed, false);
  const trackId = committed.result.created_track_id;
  assert.ok(Number.isSafeInteger(trackId) && trackId > 0);
  const storedPending = await inspectDesktopProgressionRecovery(page, storageKey);
  assert.equal(storedPending.origin, originCleanup.origin, 'Renderer origin changed before the packaged crash');
  assert.deepEqual(
    storedPending.originEntries,
    [],
    'Desktop Progressions recovery unexpectedly fell back to origin-local storage',
  );
  assert.equal(
    typeof storedPending.value,
    'string',
    'Progressions recovery command was not staged in stable desktop storage',
  );
  const pendingEnvelope = JSON.parse(storedPending.value);
  assert.equal(pendingEnvelope.pending.key, committed.idempotencyKey);
  assert.deepEqual(pendingEnvelope.pending.command, committed.command);
  assert.equal(pendingEnvelope.pending.receiptOnly, true);
  assert.equal(pendingEnvelope.pending.resendAttempted, false);
  record(
    'transaction',
    `staged committed Progressions track ${trackId} for receipt-only recovery across a packaged Core crash`,
  );
  return {
    projectId,
    title,
    trackId,
    idempotencyKey: committed.idempotencyKey,
    command: committed.command,
    appliedRevision: committed.result.applied_revision,
    storageKey,
    rendererOrigin: storedPending.origin,
  };
}

async function verifyProgressionReceiptRecoveryAfterCrash(session, expected) {
  const { page } = session;
  const commandPath = `/api/projects/${expected.projectId}/progressions/commands`;
  const receiptPath = `/api/projects/${expected.projectId}/progressions/command-receipt`;
  let unexpectedDeliveries = 0;
  let recoveryReceiptReads = 0;
  let receiptRouteFailure = null;
  const rejectUnexpectedCommand = async (route) => {
    unexpectedDeliveries += 1;
    await route.abort('failed');
  };
  const observeReceiptCheck = async (route) => {
    try {
      assert.equal(route.request().method(), 'GET', 'Progressions recovery receipt check changed HTTP method');
      const headers = await route.request().allHeaders();
      assert.equal(
        headers['idempotency-key'],
        expected.idempotencyKey,
        'Progressions recovery checked a different idempotency key',
      );
      assert.equal(headers['cache-control'], 'no-store', 'Progressions recovery receipt check became cacheable');
      recoveryReceiptReads += 1;
      await route.continue();
    } catch (error) {
      receiptRouteFailure = error;
      await route.abort('failed').catch(() => undefined);
    }
  };
  await page.route(`**${commandPath}`, rejectUnexpectedCommand);
  await page.route(`**${receiptPath}`, observeReceiptCheck);
  try {
    const { projectId } = await waitProReady(session);
    assert.equal(projectId, expected.projectId, 'Packaged crash relaunch resumed the wrong recovery project');
    const restoredPending = await inspectDesktopProgressionRecovery(page, expected.storageKey);
    assert.notEqual(
      restoredPending.origin,
      expected.rendererOrigin,
      'Packaged relaunch reused the renderer origin, so cross-origin recovery was not exercised',
    );
    assert.deepEqual(
      restoredPending.originEntries,
      [],
      'Relaunched desktop restored Progressions recovery through origin-local storage',
    );
    assert.equal(
      typeof restoredPending.value,
      'string',
      'Stable Progressions recovery state disappeared across crash',
    );
    const restoredEnvelope = JSON.parse(restoredPending.value);
    assert.equal(restoredEnvelope.pending.key, expected.idempotencyKey);
    assert.deepEqual(restoredEnvelope.pending.command, expected.command);
    assert.equal(restoredEnvelope.pending.receiptOnly, true);
    assert.equal(restoredEnvelope.pending.resendAttempted, false);
    const progressionsSurface = await selectPanel(
      page,
      'Progressions',
      'progressions',
      'BIBLE · PROGRESSIONS',
    );
    const checkReceipt = progressionsSurface.getByRole('button', { name: 'CHECK RECEIPT', exact: true });
    let recoveryMode = null;
    await waitFor(async () => {
      if (await checkReceipt.isVisible()) {
        recoveryMode = 'manual';
        return true;
      }
      const recovery = await inspectDesktopProgressionRecovery(page, expected.storageKey);
      if (recovery.value === null) {
        recoveryMode = 'automatic';
        return true;
      }
      return false;
    }, 'manual or automatic durable Progressions receipt recovery', STARTUP_TIMEOUT_MS);
    if (recoveryMode === 'manual') {
      const unresolved = progressionsSurface.getByText(/unresolved Progressions command/i);
      if (await checkReceipt.isVisible() && await unresolved.isVisible()) {
        assert.equal(
          await progressionsSurface.getByRole('button', { name: '+ TRACK', exact: true }).isDisabled(),
          true,
          'A new Progressions mutation remained enabled while receipt recovery was unresolved',
        );
        await checkReceipt.click().catch(async (error) => {
          const recovery = await inspectDesktopProgressionRecovery(page, expected.storageKey);
          if (recovery.value !== null) throw error;
          recoveryMode = 'automatic';
        });
      } else {
        recoveryMode = 'automatic';
      }
    }
    await waitFor(
      async () => (await inspectDesktopProgressionRecovery(page, expected.storageKey)).value === null,
      'durable Progressions recovery tombstone after packaged Core restart',
      STARTUP_TIMEOUT_MS,
    );
    if (recoveryMode === 'automatic') {
      record('transaction', 'project hydration reconciled the receipt-only Progressions command automatically');
    }
    const trackButton = await waitVisible(
      progressionsSurface.locator(`[data-progression-track-id="${expected.trackId}"]`),
      'receipt-recovered Progressions track after packaged Core restart',
    );
    assert.ok((await trackButton.textContent()).includes(expected.title));
  } finally {
    await page.unroute(`**${commandPath}`, rejectUnexpectedCommand);
    await page.unroute(`**${receiptPath}`, observeReceiptCheck);
  }
  if (receiptRouteFailure) throw receiptRouteFailure;
  assert.equal(unexpectedDeliveries, 0, 'Crash recovery resent the Progressions mutation instead of checking its receipt');
  assert.ok(recoveryReceiptReads >= 1, 'Crash recovery did not check the exact durable Progressions receipt');
  const snapshot = await packagedCoreJson(session, `/api/projects/${expected.projectId}/progressions`);
  assert.equal(
    snapshot.tracks.filter((track) => track.id === expected.trackId && track.title === expected.title).length,
    1,
    'Crash-recovered Progressions track was missing or duplicated',
  );
  assert.equal(snapshot.revision, expected.appliedRevision, 'Crash recovery changed the original committed revision');
  const receiptResponse = await packagedCoreResponse(
    session,
    `/api/projects/${expected.projectId}/progressions/command-receipt`,
    { headers: { 'Idempotency-Key': expected.idempotencyKey } },
  );
  assert.equal(receiptResponse.status, 200);
  assert.equal(receiptResponse.headers.get('cache-control'), 'no-store');
  const receipt = receiptResponse.body;
  assert.equal(receipt.command_kind, expected.command.kind);
  assert.equal(receipt.expected_revision, expected.command.expected_revision);
  assert.equal(receipt.applied_revision, expected.appliedRevision);
  assert.equal(receipt.original_changed, true);
  assert.deepEqual(receipt.original_affected_track_ids, [expected.trackId]);
  assert.deepEqual(receipt.original_affected_beat_ids, []);
  assert.equal(receipt.original_created_track_id, expected.trackId);
  assert.match(receipt.request_digest, /^[0-9a-f]{64}$/);
  assert.ok(Number.isFinite(Date.parse(receipt.committed_at)));
  const resolvedRecovery = await inspectDesktopProgressionRecovery(page, expected.storageKey);
  assert.equal(
    resolvedRecovery.value,
    null,
    'Recovered Progressions command did not write its durable tombstone',
  );
  assert.deepEqual(
    resolvedRecovery.originEntries,
    [],
    'Recovered Progressions command leaked into origin-local storage',
  );
  record(
    'journey',
    `packaged Core restart recovered committed Progressions track ${expected.trackId} from its durable receipt without resend`,
  );
  return { ...expected, recoveryRendererOrigin: resolvedRecovery.origin };
}

async function verifyProgressionReceiptRemainsResolvedAfterSecondRelaunch(session, expected) {
  const { page } = session;
  const commandPath = `/api/projects/${expected.projectId}/progressions/commands`;
  let unexpectedDeliveries = 0;
  const rejectUnexpectedCommand = async (route) => {
    unexpectedDeliveries += 1;
    await route.abort('failed');
  };
  await page.route(`**${commandPath}`, rejectUnexpectedCommand);
  try {
    const { projectId } = await waitProReady(session);
    assert.equal(projectId, expected.projectId, 'Second crash-recovery relaunch resumed the wrong project');
    const recovery = await inspectDesktopProgressionRecovery(page, expected.storageKey);
    assert.notEqual(
      recovery.origin,
      expected.recoveryRendererOrigin,
      'Second packaged relaunch reused the prior renderer origin',
    );
    assert.equal(recovery.value, null, 'Resolved Progressions recovery state resurrected on second relaunch');
    assert.deepEqual(recovery.originEntries, [], 'Second relaunch found origin-local Progressions recovery state');
    const progressionsSurface = await selectPanel(
      page,
      'Progressions',
      'progressions',
      'BIBLE · PROGRESSIONS',
    );
    await waitVisible(
      progressionsSurface.locator(`[data-progression-track-id="${expected.trackId}"]`),
      'resolved Progressions track on second packaged relaunch',
    );
    assert.equal(
      await progressionsSurface.getByRole('button', { name: 'CHECK RECEIPT', exact: true }).isVisible(),
      false,
      'Resolved Progressions receipt control resurrected on second relaunch',
    );
    assert.equal(
      await progressionsSurface.getByText(/unresolved Progressions command/i).isVisible(),
      false,
      'Resolved Progressions warning resurrected on second relaunch',
    );
  } finally {
    await page.unroute(`**${commandPath}`, rejectUnexpectedCommand);
  }
  assert.equal(unexpectedDeliveries, 0, 'Second relaunch resent a resolved Progressions mutation');
  const snapshot = await packagedCoreJson(session, `/api/projects/${expected.projectId}/progressions`);
  assert.equal(
    snapshot.tracks.filter((track) => track.id === expected.trackId && track.title === expected.title).length,
    1,
    'Second relaunch lost or duplicated the crash-recovered Progressions track',
  );
  assert.equal(snapshot.revision, expected.appliedRevision, 'Second relaunch changed the recovered Progressions revision');
  record('journey', 'durable Progressions recovery tombstone remained resolved across a second renderer-origin change');
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
  assert.equal(layout.docks?.right?.collapsed, true, 'Saved right dock was not collapsed');
  assert.equal(layout.docks?.left?.sizePx, expected.leftDockSizePx, 'Saved left dock width changed');
  assert.ok(layout.docks?.left?.panelIds?.includes('notes'), 'Saved left dock lost Notes');
  assert.equal(layout.floatingPanels?.some((entry) => entry?.panelId === 'notes'), false);
  assert.equal(expected.detachedAiCompanions, true, 'AI Companions relaunch fixture was not staged');
  const detachedAiCompanions = layout.floatingPanels?.find(
    (entry) => entry?.panelId === 'ai-companions',
  );
  assert.ok(detachedAiCompanions, 'Saved workspace layout lost detached AI Companions');
  assert.equal(
    detachedAiCompanions.coordinateSpace,
    'screen',
    'Saved AI Companions did not retain native-window coordinates',
  );
  assert.equal(detachedAiCompanions.minimized, false, 'Saved AI Companions became minimized');
  record('file', `verified saved project layout: ${layoutPath}`);
}

async function captureScreenshot(session, name) {
  if (!session?.page) return;
  const pages = [...session.diagnosticPages].filter((page) => !page.isClosed());
  for (const [index, page] of pages.entries()) {
    const suffix = index === 0 ? '' : `-panel-${index}`;
    const output = path.join(diagnosticsDir, `${session.label}-${name}${suffix}.png`);
    try {
      const visible = await page.evaluate(() => document.visibilityState === 'visible');
      if (!visible) continue;
      await page.screenshot({
        path: output,
        fullPage: true,
        animations: 'disabled',
        timeout: 10_000,
      });
      record('diagnostics', `screenshot: ${output}`);
    } catch (error) {
      record('diagnostics', `screenshot failed: ${errorText(error)}`);
    }
  }
}

async function killOwnedTree(session) {
  assert.equal(session.child.pid, session.pid, `${session.label} root PID ownership changed`);
  if (process.platform === 'win32') {
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
    return;
  }

  assert.ok(
    process.platform === 'darwin' || process.platform === 'linux',
    `Unsupported teardown platform: ${process.platform}`,
  );
  const signalProcessGroup = (signal) => {
    try {
      process.kill(-session.pid, signal);
      return true;
    } catch (error) {
      if (error?.code !== 'ESRCH') throw error;
      record(session.label, `${signal} raced with process-group exit for PID ${session.pid}`);
      return false;
    }
  };
  const processGroupExists = () => {
    try {
      process.kill(-session.pid, 0);
      return true;
    } catch (error) {
      if (error?.code !== 'ESRCH') throw error;
      return false;
    }
  };
  const waitForProcessGroupExit = async (timeoutMs) => {
    const deadline = Date.now() + timeoutMs;
    while (processGroupExists()) {
      const remaining = deadline - Date.now();
      if (remaining <= 0) return false;
      await delay(Math.min(250, remaining));
    }
    return true;
  };
  record(session.label, `fallback SIGTERM for owned process group ${session.pid}`);
  if (!signalProcessGroup('SIGTERM')) return;
  if (await waitForProcessGroupExit(10_000)) return;
  record(session.label, 'SIGTERM grace expired; sending SIGKILL to the owned process group');
  if (!signalProcessGroup('SIGKILL')) return;
  if (!await waitForProcessGroupExit(5_000)) {
    throw new Error(`${session.label} process group ${session.pid} survived SIGKILL`);
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
    await session.app.evaluate(({ app, BrowserWindow }) => {
      const windows = BrowserWindow.getAllWindows();
      const rootWindow = windows.find((candidate) => candidate.webContents.getURL() !== 'about:blank');
      if (!rootWindow) throw new Error(`Could not resolve the root BrowserWindow among ${windows.length} windows`);
      // Closing the root window invokes the production save handshake, which
      // then owns child-panel teardown. macOS intentionally keeps an app alive
      // with no windows, so request a real application quit there.
      if (process.platform === 'darwin') app.quit();
      else rootWindow.close();
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

async function crashSession(session) {
  if (!session || session.closed) return;
  record(session.label, 'intentionally crashing the owned packaged process tree for receipt recovery');
  try {
    await killOwnedTree(session);
  } finally {
    session.closed = true;
    activeSessions.delete(session);
  }
  await verifyPortClosed(session.port, session.label);
  record(session.label, 'owned packaged process tree stopped without the application save handshake');
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
  assert.notEqual(pathKey(resolved), pathKey(filesystemRoot));
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
  assert.ok(
    process.platform === 'win32' || process.platform === 'darwin' || process.platform === 'linux',
    `Packaged workspace acceptance requires Windows, macOS, or Linux; received ${process.platform}.`,
  );
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
  const progressionBundlePath = await writeProgressionBundleFixture(acceptanceRoot);
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
    const intelligenceExpected = await exerciseIntelligenceShell(first);
    await captureScreenshot(first, 'graph-radar-continuity');
    const progressionsExpected = await exerciseProgressionsIntelligence(
      first,
      intelligenceExpected,
    );
    await captureScreenshot(first, 'progressions-intelligence');
    const timelineExpected = await exerciseTimelineRelationships(
      first,
      intelligenceExpected.projectId,
    );
    await captureScreenshot(first, 'timeline-relationships');
    const canvasExpected = await exerciseCanvasPlot(first);
    await captureScreenshot(first, 'canvas-plot');
    const workspaceExpected = await exercisePointerWorkspace(first, intelligenceExpected);
    assert.equal(
      workspaceExpected.projectId,
      intelligenceExpected.projectId,
      'Packaged shell switched projects during the intelligence journey',
    );
    const expected = {
      ...workspaceExpected,
      canvas: canvasExpected,
      intelligence: intelligenceExpected,
      progressions: progressionsExpected,
      timeline: timelineExpected,
    };
    await captureScreenshot(first, 'pointer-layout');
    await closeSession(first);
    await readSavedLayout(first, expected);

    const second = await launchPackagedApp({
      electron: driver.electron,
      exePath,
      root: productRoot,
      label: 'pro-pointer-2',
      // The persisted AI Companions window can be created before or just after
      // the root-runtime probe, depending on renderer/layout hydration timing.
      allowedWindowCounts: [1, 2],
    });
    const restoredBilly = await verifyPersistedBillyNativeWindow(second);
    assert.equal(
      restoredBilly.projectId,
      expected.projectId,
      'Detached AI Companions restored for the wrong project',
    );
    await verifyPersistedIntelligence(second, expected.intelligence);
    // Assert the saved collapsed-dock state before any domain verification
    // activates a panel in those docks. Selecting Radar below intentionally
    // expands the right dock and must not invalidate this persistence check.
    await verifyPersistedWorkspace(second, expected);
    await redockPersistedBillyNativeWindow(second, restoredBilly.panelWindow);
    await verifyPersistedProgressions(second, expected.progressions);
    await captureScreenshot(second, 'restored-progressions');
    await verifyPersistedTimelineRelationships(second, expected.timeline);
    await verifyPersistedCanvasPlot(second, expected.canvas);
    await captureScreenshot(second, 'restored-layout');
    await closeSession(second);

    const importer = await launchPackagedApp({
      electron: driver.electron,
      exePath,
      root: productRoot,
      label: 'pro-pointer-import',
    });
    const importedProgressions = await exerciseProgressionBundleImport(
      importer,
      progressionBundlePath,
      expected.projectId,
    );
    await captureScreenshot(importer, 'progressions-bundle-import');
    await closeSession(importer);

    const importedRelaunch = await launchPackagedApp({
      electron: driver.electron,
      exePath,
      root: productRoot,
      label: 'pro-pointer-import-relaunch',
    });
    await verifyPersistedProgressionBundleImport(importedRelaunch, importedProgressions);
    await captureScreenshot(importedRelaunch, 'restored-progressions-bundle');
    const crashRecoveryExpected = await stageProgressionReceiptRecoveryAcrossCrash(
      importedRelaunch,
      importedProgressions.projectId,
    );
    await captureScreenshot(importedRelaunch, 'progressions-receipt-only-before-crash');
    await crashSession(importedRelaunch);

    const crashRelaunch = await launchPackagedApp({
      electron: driver.electron,
      exePath,
      root: productRoot,
      label: 'pro-pointer-crash-relaunch',
    });
    const resolvedCrashRecovery = await verifyProgressionReceiptRecoveryAfterCrash(
      crashRelaunch,
      crashRecoveryExpected,
    );
    await captureScreenshot(crashRelaunch, 'progressions-recovered-after-crash');
    await closeSession(crashRelaunch);

    const resolvedRelaunch = await launchPackagedApp({
      electron: driver.electron,
      exePath,
      root: productRoot,
      label: 'pro-pointer-resolved-relaunch',
    });
    await verifyProgressionReceiptRemainsResolvedAfterSecondRelaunch(
      resolvedRelaunch,
      resolvedCrashRecovery,
    );
    await captureScreenshot(resolvedRelaunch, 'progressions-recovery-remains-resolved');
    await closeSession(resolvedRelaunch);
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
