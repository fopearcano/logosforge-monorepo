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

async function verifyPackagedRuntime(session, exePath) {
  const expectedResources = packagedResourcesPath(exePath);
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
  assert.equal(runtime.windowCount, 1, `${session.label} must expose exactly one BrowserWindow`);
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

async function launchPackagedApp({ electron, exePath, root, label }) {
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
    savedOpeningContent: expectedReply,
    graphCardId: graphCard.id,
    continuityCardId: continuityCard.id,
    continuityIssueId: issue.id,
    continuityIssueStatus: 'resolved',
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
    });
    await verifyPersistedIntelligence(second, expected.intelligence);
    await verifyPersistedTimelineRelationships(second, expected.timeline);
    await verifyPersistedCanvasPlot(second, expected.canvas);
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
