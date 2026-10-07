#!/usr/bin/env node

/**
 * Standalone packaged lifecycle acceptance for LogosForge Whiteboard.
 *
 * This launches electron-builder's unpacked packaged application through
 * Playwright's Electron transport. It deliberately covers only Whiteboard:
 * local document create/open/edit/autosave persistence and the private MCP
 * runtime boundary across graceful shutdown/relaunch, plus export-only
 * `.lfbundle` creation and schema validation. It never imports a bundle or
 * launches/tests LogosForge Pro.
 *
 * Optional overrides:
 *   LOGOSFORGE_WHITEBOARD_ACCEPTANCE_EXE=<absolute packaged executable>
 *   LOGOSFORGE_WHITEBOARD_PACKAGED_ACCEPTANCE_ROOT=<absolute empty directory>
 *
 * Linux runners need a display (for example `xvfb-run -a`).
 */

import assert from 'node:assert/strict';
import { execFile, spawn } from 'node:child_process';
import { promises as fs } from 'node:fs';
import { createRequire } from 'node:module';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';

import {
  MCP_RUNTIME_FILENAME,
  defaultWhiteboardExecutable,
  isMatchingWhiteboardBackendHealth,
  isSameOrInside,
  packagedLaunchArguments,
  packagedWhiteboardLayout,
  validateWhiteboardExportBundle,
  validateWhiteboardRuntimeDescriptor,
} from './whiteboard-packaged-acceptance-support.mjs';

const execFileAsync = promisify(execFile);
const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const DESKTOP_DIR = path.resolve(SCRIPT_DIR, '..');
const REPO_ROOT = path.resolve(DESKTOP_DIR, '..', '..');
const DEFAULT_EXECUTABLE = defaultWhiteboardExecutable(DESKTOP_DIR);
const STARTUP_TIMEOUT_MS = 90_000;
const UI_TIMEOUT_MS = 30_000;
const CLOSE_TIMEOUT_MS = 25_000;
const PROCESS_TIMEOUT_MS = 30_000;
const MAX_DESCRIPTOR_BYTES = 16 * 1024;
const MAX_MCP_OUTPUT_BYTES = 1024 * 1024;
const MAX_EXPORT_BYTES = 16 * 1024 * 1024;
const LOG_LIMIT = 2 * 1024 * 1024;

const activeSessions = new Set();
const usedPorts = new Set();
const logLines = [];
let diagnosticsDir = null;
let validatedRemovalRoot = null;
let rootCameFromOverride = false;

function now() {
  return new Date().toISOString();
}

function errorText(error) {
  return error instanceof Error ? (error.stack || error.message) : String(error);
}

function record(scope, value) {
  const clean = String(value ?? '').replace(/\r\n/g, '\n').trimEnd();
  const line = `${now()} [${scope}] ${clean.length > 12_000 ? `${clean.slice(0, 12_000)}\n...[truncated]` : clean}`;
  logLines.push(line);
  let total = 0;
  for (let index = logLines.length - 1; index >= 0; index -= 1) {
    total += logLines[index].length + 1;
    if (total > LOG_LIMIT) {
      logLines.splice(0, index + 1, `${now()} [harness] ...[older entries truncated]`);
      break;
    }
  }
  console.log(line);
}

function normalizedPathKey(value) {
  const resolved = path.resolve(value).replace(/[\\/]+$/, '');
  return process.platform === 'win32' ? resolved.toLocaleLowerCase('en-US') : resolved;
}

function assertSamePath(actual, expected, label) {
  assert.equal(normalizedPathKey(actual), normalizedPathKey(expected), `${label} path mismatch`);
}

function assertPathInside(child, parent, label) {
  assert.ok(isSameOrInside(child, parent), `${label} escaped ${parent}: ${child}`);
}

async function withTimeout(promise, timeoutMs, label) {
  let timeout;
  try {
    return await Promise.race([
      promise,
      new Promise((_, reject) => {
        timeout = setTimeout(() => reject(new Error(`${label} exceeded ${timeoutMs}ms`)), timeoutMs);
      }),
    ]);
  } finally {
    clearTimeout(timeout);
  }
}

async function waitFor(check, label, timeoutMs = UI_TIMEOUT_MS, intervalMs = 150) {
  const deadline = Date.now() + timeoutMs;
  let lastError = null;
  while (Date.now() < deadline) {
    try {
      const result = await check();
      if (result) return result;
    } catch (error) {
      lastError = error;
    }
    await delay(intervalMs);
  }
  const suffix = lastError ? ` Last error: ${errorText(lastError)}` : '';
  throw new Error(`Timed out waiting for ${label}.${suffix}`);
}

async function assertRegularFile(filePath, label, { executable = false } = {}) {
  let stat;
  try {
    stat = await fs.lstat(filePath);
  } catch (error) {
    throw new Error(`${label} is missing: ${filePath} (${errorText(error)})`);
  }
  assert.ok(stat.isFile() && !stat.isSymbolicLink() && stat.size > 0, `${label} is not a regular file: ${filePath}`);
  if (executable && process.platform !== 'win32') {
    assert.ok((stat.mode & 0o111) !== 0, `${label} is not executable: ${filePath}`);
  }
  return stat;
}

async function canonicalExecutable() {
  const override = process.env.LOGOSFORGE_WHITEBOARD_ACCEPTANCE_EXE?.trim();
  if (override && !path.isAbsolute(override)) {
    throw new Error(`LOGOSFORGE_WHITEBOARD_ACCEPTANCE_EXE must be absolute: ${override}`);
  }
  const requested = override || DEFAULT_EXECUTABLE;
  await assertRegularFile(requested, 'Packaged Whiteboard executable', { executable: true });
  return fs.realpath(requested);
}

async function createIsolationRoot() {
  const override = process.env.LOGOSFORGE_WHITEBOARD_PACKAGED_ACCEPTANCE_ROOT?.trim();
  if (!override) {
    const created = await fs.mkdtemp(path.join(os.tmpdir(), 'logosforge-whiteboard-lifecycle-'));
    const canonical = await fs.realpath(created);
    validatedRemovalRoot = canonical;
    rootCameFromOverride = false;
    return canonical;
  }
  if (!path.isAbsolute(override)) {
    throw new Error(`LOGOSFORGE_WHITEBOARD_PACKAGED_ACCEPTANCE_ROOT must be absolute: ${override}`);
  }
  let stat;
  try {
    stat = await fs.lstat(override);
  } catch (error) {
    if (error?.code !== 'ENOENT') throw error;
    const parent = path.dirname(override);
    const parentStat = await fs.lstat(parent);
    assert.ok(parentStat.isDirectory() && !parentStat.isSymbolicLink(), `Acceptance-root parent is unsafe: ${parent}`);
    await fs.mkdir(override);
    stat = await fs.lstat(override);
  }
  assert.ok(stat.isDirectory() && !stat.isSymbolicLink(), `Acceptance root is not a real directory: ${override}`);
  const entries = await fs.readdir(override);
  assert.equal(entries.length, 0, `Acceptance root must start empty: ${override}`);
  const canonical = await fs.realpath(override);
  validatedRemovalRoot = canonical;
  rootCameFromOverride = true;
  return canonical;
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
    if (Number.isSafeInteger(port) && port > 0 && !usedPorts.has(port)) {
      usedPorts.add(port);
      return port;
    }
  }
  throw new Error('Could not allocate an isolated Whiteboard port.');
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

async function prepareEnvironment(productRoot, port) {
  const dirs = {
    userData: path.join(productRoot, 'user-data'),
    data: path.join(productRoot, 'data'),
    home: path.join(productRoot, 'home'),
    runtime: path.join(productRoot, 'runtime'),
    models: path.join(productRoot, 'models'),
    qaLogs: path.join(productRoot, 'qa', 'logs'),
    qaReports: path.join(productRoot, 'qa', 'reports'),
    config: path.join(productRoot, 'config'),
  };
  await Promise.all(Object.values(dirs).map((directory) => fs.mkdir(directory, { recursive: true })));
  const descriptorPath = path.join(dirs.runtime, MCP_RUNTIME_FILENAME);
  const installedMcpPath = path.join(
    dirs.runtime,
    process.platform === 'win32' ? 'logosforge-whiteboard-mcp.exe' : 'logosforge-whiteboard-mcp',
  );
  const env = { ...process.env };
  for (const inherited of [
    'ELECTRON_RUN_AS_NODE',
    'LOGOSFORGE_CORE_DIR',
    'LOGOSFORGE_PYTHON',
    'API_AUTH_TOKEN',
    'LOGOSFORGE_WHITEBOARD_AUTH_TOKEN',
    'LOGOSFORGE_WHITEBOARD_MCP_ALLOW_WRITES',
    'OPENAI_API_KEY',
    'ANTHROPIC_API_KEY',
    'OPENROUTER_API_KEY',
    'GH_TOKEN',
    'GITHUB_TOKEN',
  ]) delete env[inherited];

  Object.assign(env, {
    HOME: dirs.home,
    USERPROFILE: dirs.home,
    LOGOSFORGE_HOST: '127.0.0.1',
    LOGOSFORGE_PORT: String(port),
    LOGOSFORGE_DATA_DIR: dirs.data,
    LOGOSFORGE_DB_PATH: path.join(dirs.data, 'whiteboard.db'),
    LOGOSFORGE_QA_MODE: '1',
    LOGOSFORGE_FAKE_PROVIDER_PROFILE: 'valid_novel_prose',
    LOGOSFORGE_QA_LOG_DIR: dirs.qaLogs,
    LOGOSFORGE_QA_REPORT_DIR: dirs.qaReports,
    LOGOSFORGE_MODELS_DIR: dirs.models,
    LOGOSFORGE_WHITEBOARD_MCP_CONNECTION_FILE: descriptorPath,
    LOGOSFORGE_WHITEBOARD_MCP_LAUNCHER_PATH: installedMcpPath,
  });
  if (process.platform !== 'win32') env.XDG_CONFIG_HOME = dirs.config;
  return { dirs, descriptorPath, installedMcpPath, env };
}

async function loadElectronDriver() {
  const module = await import('playwright-core');
  assert.ok(module._electron, 'playwright-core does not export its Electron driver');
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
  await assertRegularFile(loaderPath, 'Playwright Electron loader');
  record('harness', `playwright-core ${packageJson.version ?? 'unknown'} loader resolved`);
  return { electron: module._electron, loaderPath };
}

function attachDiagnostics(session) {
  for (const [streamName, stream] of [['stdout', session.child.stdout], ['stderr', session.child.stderr]]) {
    stream?.on('data', (chunk) => record(`${session.label}:${streamName}`, chunk));
  }
  session.child.once('exit', (code, signal) => {
    record(session.label, `root process exited (pid=${session.pid}, code=${code}, signal=${signal})`);
  });
  session.page.on('console', (message) => record(`${session.label}:renderer:${message.type()}`, message.text()));
  session.page.on('pageerror', (error) => record(`${session.label}:pageerror`, errorText(error)));
  session.page.on('crash', () => record(`${session.label}:renderer`, 'page crashed'));
}

async function installClosePromptResponder(session, markerPath) {
  await session.app.evaluate(({ dialog }, state) => {
    const original = dialog.showMessageBox.bind(dialog);
    dialog.showMessageBox = async (...args) => {
      const options = args.at(-1) ?? {};
      const message = String(options.message ?? '');
      const buttons = Array.isArray(options.buttons) ? options.buttons : [];
      const response = buttons.indexOf("Don't Save");
      if (!message.includes('Save changes before closing?') || response < 0) {
        return original(...args);
      }
      process.getBuiltinModule('node:fs').writeFileSync(
        state.markerPath,
        `Don't Save: ${message}\n`,
        'utf8',
      );
      return { response, checkboxChecked: false };
    };
  }, { markerPath });
}

async function installBundleExportResponder(session, bundlePath) {
  assert.ok(path.isAbsolute(bundlePath), 'Whiteboard export path must be absolute');
  assert.equal(path.extname(bundlePath), '.lfbundle', 'Whiteboard export path must use .lfbundle');
  assertPathInside(bundlePath, session.productRoot, 'Whiteboard export path');
  assertSamePath(path.dirname(bundlePath), session.productRoot, 'Whiteboard export parent');
  await fs.rm(bundlePath, { force: true });

  const key = `__logosforgeWhiteboardExport_${session.pid}_${Date.now()}`;
  await session.app.evaluate(({ dialog }, state) => {
    globalThis[state.key] = { used: false, filePath: state.bundlePath };
    dialog.showSaveDialog = async (...args) => {
      const queue = globalThis[state.key];
      if (!queue || queue.used) {
        throw new Error('Packaged Whiteboard export dialog was invoked more than once.');
      }
      const options = args.at(-1) ?? {};
      const extensions = Array.isArray(options.filters)
        ? options.filters.flatMap((filter) => Array.isArray(filter?.extensions) ? filter.extensions : [])
        : [];
      if (!extensions.includes('lfbundle') || !String(options.defaultPath ?? '').endsWith('.lfbundle')) {
        throw new Error('Packaged Whiteboard export did not request the .lfbundle save contract.');
      }
      queue.used = true;
      return { canceled: false, filePath: queue.filePath };
    };
  }, { key, bundlePath });
  session.bundleExportDialogKey = key;
  record(session.label, `installed one-shot .lfbundle save responder for ${path.basename(bundlePath)}`);
}

async function assertBundleExportDialogUsed(session, bundlePath) {
  assert.equal(typeof session.bundleExportDialogKey, 'string', 'Whiteboard export dialog responder was not installed');
  const state = await session.app.evaluate((_electron, key) => {
    const value = globalThis[key];
    if (!value) throw new Error(`Missing packaged Whiteboard export dialog state: ${key}`);
    return { used: value.used === true, filePath: value.filePath };
  }, session.bundleExportDialogKey);
  assert.equal(state.used, true, 'Whiteboard did not use the native .lfbundle save dialog');
  assertSamePath(state.filePath, bundlePath, 'Whiteboard export dialog target');
}

async function assertPackagedRuntime(session) {
  const runtime = await session.app.evaluate(({ app, BrowserWindow }) => {
    const windows = BrowserWindow.getAllWindows();
    const preferences = windows[0]?.webContents.getLastWebPreferences() ?? {};
    return {
      isPackaged: app.isPackaged,
      name: app.getName(),
      appPath: app.getAppPath(),
      execPath: process.execPath,
      pid: process.pid,
      resourcesPath: process.resourcesPath,
      userData: app.getPath('userData'),
      sessionData: app.getPath('sessionData'),
      homeEnv: process.env.HOME,
      userProfileEnv: process.env.USERPROFILE,
      hasNoSandboxSwitch: app.commandLine.hasSwitch('no-sandbox'),
      windowCount: windows.length,
      preferences: {
        contextIsolation: preferences.contextIsolation,
        nodeIntegration: preferences.nodeIntegration,
        sandbox: preferences.sandbox,
      },
    };
  });
  assert.equal(runtime.isPackaged, true, `${session.label} is not packaged`);
  assert.equal(runtime.name, 'LogosForge Whiteboard', `${session.label} product identity changed`);
  assert.ok(Number.isSafeInteger(runtime.pid) && runtime.pid > 0, `${session.label} main process has no PID`);
  assert.equal(runtime.windowCount, 1, `${session.label} must have one BrowserWindow`);
  assertSamePath(runtime.execPath, session.layout.executable, `${session.label} executable`);
  assertSamePath(runtime.resourcesPath, session.layout.resources, `${session.label} resources`);
  assertSamePath(runtime.appPath, session.layout.appArchive, `${session.label} app archive`);
  assertPathInside(runtime.userData, session.dirs.userData, `${session.label} userData`);
  assertPathInside(runtime.sessionData, session.dirs.userData, `${session.label} sessionData`);
  assertSamePath(runtime.homeEnv, session.dirs.home, `${session.label} HOME`);
  assertSamePath(runtime.userProfileEnv, session.dirs.home, `${session.label} USERPROFILE`);
  const rootLinuxFallback = process.platform === 'linux'
    && typeof process.getuid === 'function'
    && process.getuid() === 0;
  assert.equal(
    runtime.hasNoSandboxSwitch,
    rootLinuxFallback,
    rootLinuxFallback
      ? `${session.label} root-only Linux sandbox fallback changed`
      : `${session.label} launched Chromium with --no-sandbox`,
  );
  assert.deepEqual(
    runtime.preferences,
    { contextIsolation: true, nodeIntegration: false, sandbox: true },
    `${session.label} renderer isolation changed`,
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
  session.appPid = runtime.pid;
  record(session.label, `verified packaged runtime at ${runtime.execPath}`);
}

async function launchPackagedApp({ electron, loaderPath, executable, productRoot, label }) {
  if (process.platform === 'linux' && !process.env.DISPLAY && !process.env.WAYLAND_DISPLAY) {
    throw new Error('Linux Whiteboard packaged acceptance needs DISPLAY/WAYLAND_DISPLAY; run it under xvfb-run.');
  }
  const port = await allocateStrictPort();
  const prepared = await prepareEnvironment(productRoot, port);
  const layout = packagedWhiteboardLayout(executable);
  await Promise.all([
    assertRegularFile(layout.appArchive, `${label} app.asar`),
    assertRegularFile(layout.backend, `${label} backend`, { executable: true }),
    assertRegularFile(layout.bundledMcp, `${label} bundled MCP`, { executable: true }),
  ]);
  await fs.rm(prepared.descriptorPath, { force: true });

  record(label, `launching packaged Whiteboard on isolated port ${port}`);
  const app = await electron.launch({
    executablePath: executable,
    // Playwright otherwise injects --no-sandbox into Electron automatically.
    // Keep production-equivalent Chromium sandboxing on normal release hosts;
    // packagedLaunchArguments adds the unavoidable fallback only for root Linux.
    chromiumSandbox: true,
    args: packagedLaunchArguments(loaderPath, prepared.dirs.userData, {
      uid: typeof process.getuid === 'function' ? process.getuid() : undefined,
    }),
    cwd: path.dirname(executable),
    env: prepared.env,
    timeout: STARTUP_TIMEOUT_MS,
  });
  const child = app.process();
  assert.ok(Number.isSafeInteger(child.pid) && child.pid > 0, `${label} has no owned root PID`);
  const session = {
    ...prepared,
    app,
    child,
    pid: child.pid,
    port,
    page: null,
    label,
    productRoot,
    layout,
    closed: false,
    closeMarkerPath: path.join(productRoot, `${label}-close-prompt.txt`),
  };
  activeSessions.add(session);
  try {
    session.page = await app.firstWindow({ timeout: STARTUP_TIMEOUT_MS });
    attachDiagnostics(session);
    await installClosePromptResponder(session, session.closeMarkerPath);
    await assertPackagedRuntime(session);
    return session;
  } catch (error) {
    record(label, `launch verification failed: ${errorText(error)}`);
    try { await killOwnedProcess(session); } catch (cleanupError) {
      record(label, `launch cleanup failed: ${errorText(cleanupError)}`);
    }
    activeSessions.delete(session);
    throw error;
  }
}

async function inspectLocalService(session) {
  return session.page.evaluate(async (expectedPort) => {
    const readStatus = globalThis.logosforge?.getBackendStatus;
    if (typeof readStatus !== 'function') throw new Error('Missing getBackendStatus bridge method.');
    const status = await readStatus();
    if (!status || typeof status !== 'object') throw new Error('Invalid backend status.');
    const endpoint = new URL(status.baseUrl);
    if (
      endpoint.protocol !== 'http:'
      || !['127.0.0.1', '::1', '[::1]'].includes(endpoint.hostname)
      || Number(endpoint.port) !== expectedPort
      || endpoint.pathname !== '/'
      || endpoint.username
      || endpoint.password
      || endpoint.search
      || endpoint.hash
    ) throw new Error('Backend endpoint escaped the isolated loopback origin.');
    if (typeof status.authToken !== 'string' || status.authToken.length < 32) {
      throw new Error('Backend status has no in-memory credential.');
    }
    return {
      state: status.state,
      baseUrl: endpoint.origin,
      managed: status.managed === true,
      service: status.service,
    };
  }, session.port);
}

async function waitLocalService(session) {
  let status;
  await waitFor(async () => {
    status = await inspectLocalService(session);
    return status.state === 'connected';
  }, `${session.label} backend connection`, STARTUP_TIMEOUT_MS, 250);
  assert.equal(status.managed, true, `${session.label} did not start its packaged backend`);
  assert.equal(status.service, 'LogosForge Whiteboard', `${session.label} API identity changed`);
  record(session.label, `authenticated backend connected on port ${session.port}`);
}

async function localGet(session, requestPath, headers = {}) {
  assert.match(requestPath, /^\/api\//, `Unsafe Whiteboard API path: ${requestPath}`);
  return session.page.evaluate(async ({ requestPath: apiPath, requestHeaders, expectedPort }) => {
    const status = await globalThis.logosforge?.getBackendStatus?.();
    if (!status || status.state !== 'connected' || typeof status.authToken !== 'string') {
      throw new Error('Whiteboard backend is not authenticated.');
    }
    const origin = new URL(status.baseUrl);
    if (Number(origin.port) !== expectedPort) throw new Error('Whiteboard backend port changed.');
    const url = new URL(apiPath, `${origin.origin}/`);
    if (url.origin !== origin.origin || !url.pathname.startsWith('/api/')) {
      throw new Error('Whiteboard API request escaped its origin.');
    }
    const response = await fetch(url, {
      headers: { ...requestHeaders, Authorization: `Bearer ${status.authToken}` },
    });
    const text = await response.text();
    if (text.length > 4 * 1024 * 1024) throw new Error('Whiteboard API response was oversized.');
    if (!response.ok) throw new Error(`Whiteboard API returned HTTP ${response.status}.`);
    return text ? JSON.parse(text) : null;
  }, { requestPath, requestHeaders: headers, expectedPort: session.port });
}

async function readRuntimeDescriptor(session) {
  const stat = await fs.lstat(session.descriptorPath);
  assert.ok(stat.isFile() && !stat.isSymbolicLink(), 'Whiteboard MCP descriptor is not a regular file');
  assert.ok(stat.size > 0 && stat.size <= MAX_DESCRIPTOR_BYTES, 'Whiteboard MCP descriptor has an unsafe size');
  if (process.platform !== 'win32') {
    assert.equal(stat.mode & 0o077, 0, 'Whiteboard MCP descriptor is not private (expected mode 0600)');
  }
  const raw = await fs.readFile(session.descriptorPath, 'utf8');
  const value = JSON.parse(raw);
  const summary = validateWhiteboardRuntimeDescriptor(value, {
    expectedPort: session.port,
    expectedAppPid: session.appPid,
  });
  assert.doesNotThrow(() => process.kill(summary.backendPid, 0), 'Descriptor backend PID is not alive');
  return { value, summary };
}

async function fetchHealth(summary) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5_000);
  try {
    const response = await fetch(`${summary.baseUrl}/health`, {
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    });
    assert.equal(response.ok, true, `Whiteboard health returned HTTP ${response.status}`);
    const text = await response.text();
    assert.ok(text.length <= 64 * 1024, 'Whiteboard health response was oversized');
    return JSON.parse(text);
  } finally {
    clearTimeout(timeout);
  }
}

async function verifyLiveRuntimeBoundary(session) {
  await waitFor(async () => {
    try {
      await fs.access(session.descriptorPath);
      return true;
    } catch {
      return false;
    }
  }, `${session.label} MCP runtime descriptor`, STARTUP_TIMEOUT_MS, 200);
  const descriptor = await readRuntimeDescriptor(session);
  const health = await fetchHealth(descriptor.summary);
  assert.equal(health?.status, 'ok', 'Whiteboard health status changed');
  assert.equal(health?.service, 'logosforge-whiteboard-backend', 'Whiteboard health identity changed');
  assert.equal(health?.instance_nonce, descriptor.summary.instanceNonce, 'Whiteboard runtime nonce mismatch');
  session.verifiedBackend = descriptor.summary;
  await assertRegularFile(session.installedMcpPath, 'Installed Whiteboard MCP companion', { executable: true });
  record(session.label, 'verified private live descriptor, nonce-bound health, and installed MCP companion');
  return descriptor;
}

function boundedAppend(current, chunk, label) {
  const next = current + String(chunk);
  if (Buffer.byteLength(next, 'utf8') > MAX_MCP_OUTPUT_BYTES) {
    throw new Error(`${label} exceeded ${MAX_MCP_OUTPUT_BYTES} bytes.`);
  }
  return next;
}

async function exerciseLiveMcpDiscovery(session, authToken) {
  const child = spawn(session.installedMcpPath, [], {
    cwd: path.dirname(session.installedMcpPath),
    env: { ...session.env, LOGOSFORGE_WHITEBOARD_MCP_CONNECTION_FILE: session.descriptorPath },
    stdio: ['pipe', 'pipe', 'pipe'],
    windowsHide: true,
  });
  child.stdout.setEncoding('utf8');
  child.stderr.setEncoding('utf8');
  let stdout = '';
  let stderr = '';
  let parseError = null;
  const messages = [];
  const exited = new Promise((resolve) => child.once('exit', (code, signal) => resolve({ code, signal })));
  child.once('error', (error) => { parseError = error; });
  child.stdout.on('data', (chunk) => {
    try {
      stdout = boundedAppend(stdout, chunk, 'Whiteboard MCP stdout');
      while (stdout.includes('\n')) {
        const newline = stdout.indexOf('\n');
        const line = stdout.slice(0, newline).trim();
        stdout = stdout.slice(newline + 1);
        if (line) messages.push(JSON.parse(line));
      }
    } catch (error) {
      parseError = error;
    }
  });
  child.stderr.on('data', (chunk) => {
    try { stderr = boundedAppend(stderr, chunk, 'Whiteboard MCP stderr'); } catch (error) { parseError = error; }
  });
  const send = (message) => child.stdin.write(`${JSON.stringify(message)}\n`);
  const response = async (id, label) => waitFor(() => {
    if (parseError) throw parseError;
    const value = messages.find((message) => message?.id === id);
    if (value) return value;
    if (child.exitCode !== null) {
      const safe = stderr.replaceAll(authToken, '[REDACTED]').slice(-2_000);
      throw new Error(`Whiteboard MCP exited before ${label} (code=${child.exitCode}): ${safe}`);
    }
    return false;
  }, label, PROCESS_TIMEOUT_MS, 50);

  try {
    send({
      jsonrpc: '2.0',
      id: 1,
      method: 'initialize',
      params: {
        protocolVersion: '2025-06-18',
        capabilities: {},
        clientInfo: { name: 'logosforge-whiteboard-packaged-acceptance', version: '1.0.0' },
      },
    });
    const initialized = await response(1, 'Whiteboard MCP initialize response');
    assert.equal(initialized.error, undefined, `Whiteboard MCP initialize failed: ${JSON.stringify(initialized.error)}`);
    assert.equal(initialized.result?.serverInfo?.name, 'logosforge-whiteboard', 'Whiteboard MCP server identity changed');
    assert.equal(typeof initialized.result?.serverInfo?.version, 'string', 'Whiteboard MCP server has no version');
    send({ jsonrpc: '2.0', method: 'notifications/initialized', params: {} });
    send({ jsonrpc: '2.0', id: 2, method: 'tools/list', params: {} });
    const listed = await response(2, 'Whiteboard MCP tools/list response');
    assert.equal(listed.error, undefined, `Whiteboard MCP tools/list failed: ${JSON.stringify(listed.error)}`);
    const tools = listed.result?.tools;
    assert.ok(Array.isArray(tools) && tools.length > 0, 'Whiteboard MCP advertised no tools');
    const names = new Set(tools.map((tool) => tool?.name));
    for (const required of [
      'logosforge_whiteboard_get_capabilities',
      'logosforge_whiteboard_list_documents',
      'logosforge_whiteboard_get_current_document',
    ]) assert.ok(names.has(required), `Whiteboard MCP omitted ${required}`);
    assert.ok(
      tools.every((tool) => tool?.annotations?.openWorldHint === false),
      'Whiteboard MCP advertised an open-world tool',
    );
    child.stdin.end();
    const outcome = await withTimeout(exited, PROCESS_TIMEOUT_MS, 'Whiteboard MCP clean EOF');
    assert.equal(outcome.code, 0, `Whiteboard MCP discovery exited with code ${outcome.code}`);
    record(session.label, `live read-only MCP discovery passed (${tools.length} tools)`);
  } finally {
    if (child.exitCode === null) child.kill('SIGKILL');
  }
}

async function assertMcpFailsClosed(session) {
  await waitFor(async () => {
    try {
      await fs.lstat(session.descriptorPath);
      return false;
    } catch (error) {
      if (error?.code === 'ENOENT') return true;
      throw error;
    }
  }, `${session.label} runtime descriptor removal`, CLOSE_TIMEOUT_MS, 100);
  const child = spawn(session.installedMcpPath, [], {
    cwd: path.dirname(session.installedMcpPath),
    env: { ...session.env, LOGOSFORGE_WHITEBOARD_MCP_CONNECTION_FILE: session.descriptorPath },
    stdio: ['pipe', 'pipe', 'pipe'],
    windowsHide: true,
  });
  let stderr = '';
  child.stderr.setEncoding('utf8');
  child.stderr.on('data', (chunk) => {
    if (Buffer.byteLength(stderr, 'utf8') < MAX_MCP_OUTPUT_BYTES) stderr += chunk;
  });
  child.stdin.end();
  let outcome;
  try {
    outcome = await withTimeout(
      new Promise((resolve, reject) => {
        child.once('error', reject);
        child.once('exit', (code, signal) => resolve({ code, signal }));
      }),
      PROCESS_TIMEOUT_MS,
      'Whiteboard MCP fail-closed exit',
    );
  } catch (error) {
    if (child.exitCode === null) child.kill('SIGKILL');
    throw error;
  }
  assert.notEqual(
    outcome.code,
    0,
    'Whiteboard MCP accepted a session after its owning application shut down',
  );
  record(session.label, `MCP refused the removed runtime descriptor after shutdown (code=${outcome.code})`);
}

async function waitVisible(locator, label, timeoutMs = UI_TIMEOUT_MS) {
  await locator.first().waitFor({ state: 'visible', timeout: timeoutMs });
  return locator.first();
}

async function waitText(locator, expected, label, { exact = false, timeoutMs = UI_TIMEOUT_MS } = {}) {
  const target = locator.first();
  await waitFor(async () => {
    if (!(await target.isVisible().catch(() => false))) return false;
    const value = (await target.textContent()) ?? '';
    return exact ? value.trim() === expected : value.includes(expected);
  }, label, timeoutMs);
  return target;
}

async function openFileMenu(page) {
  const trigger = await waitVisible(page.locator('button[title="File menu"]'), 'Whiteboard File trigger');
  assert.equal((await trigger.textContent())?.trim(), 'File', 'Unexpected Whiteboard File trigger');
  await trigger.click();
  return waitVisible(page.getByRole('dialog', { name: 'File menu', exact: true }), 'Whiteboard File menu');
}

async function waitEditor(page) {
  return waitVisible(page.locator('.wb-editor[contenteditable="true"]'), 'Whiteboard editor', STARTUP_TIMEOUT_MS);
}

async function readPersistedDocument(session, title, marker) {
  const library = await localGet(session, '/api/documents');
  assert.ok(Array.isArray(library?.documents), 'Whiteboard document library response is invalid');
  const matches = library.documents.filter((document) => document?.title === title);
  assert.equal(matches.length, 1, `Expected exactly one Whiteboard document named ${title}`);
  const document = matches[0];
  assert.match(String(document.id), /^[1-9][0-9]*$/, 'Whiteboard document id is invalid');
  assert.match(String(document.incarnation), /^[0-9a-f]{32}$/, 'Whiteboard incarnation is invalid');
  const manuscript = await localGet(
    session,
    `/api/whiteboard?doc=${encodeURIComponent(document.id)}`,
    { 'X-LogosForge-Document-Incarnation': document.incarnation },
  );
  assert.ok(Array.isArray(manuscript?.blocks), 'Whiteboard manuscript response has no block list');
  assert.ok(
    manuscript.blocks.some((block) => typeof block?.text === 'string' && block.text.includes(marker)),
    'Whiteboard autosave did not persist the manuscript marker',
  );
  return document;
}

async function createEditAndAutosave(session, title, marker) {
  const { page } = session;
  let editor = await waitEditor(page);
  const previous = await editor.elementHandle();
  assert.ok(previous, 'Whiteboard initial editor was unavailable');
  const fileMenu = await openFileMenu(page);
  await fileMenu.getByRole('button', { name: 'New Document', exact: true }).click();
  await waitFor(
    () => previous.evaluate((element) => !element.isConnected),
    'new Whiteboard document editor replacement',
  );
  editor = await waitEditor(page);

  const renameMenu = await openFileMenu(page);
  await renameMenu.getByRole('button', { name: 'Rename current document…', exact: true }).click();
  const dialog = await waitVisible(page.getByRole('dialog', { name: 'Rename document', exact: true }), 'Rename dialog');
  await dialog.getByLabel('Document title', { exact: true }).fill(title);
  await dialog.getByRole('button', { name: 'Rename', exact: true }).click();
  await waitText(page.locator('button.app-title'), title, 'renamed Whiteboard document', { exact: true });

  await editor.click();
  await page.keyboard.press(`${process.platform === 'darwin' ? 'Meta' : 'Control'}+A`);
  await page.keyboard.press('Backspace');
  await page.keyboard.type('# Lifecycle chapter');
  await page.keyboard.press('Enter');
  await page.keyboard.type(marker);
  await waitText(editor, marker, 'typed lifecycle marker');
  await waitText(page.locator('.wb-draft-saved'), 'Draft saved', 'Whiteboard autosave receipt', { exact: true });
  const document = await waitFor(
    () => readPersistedDocument(session, title, marker).catch(() => false),
    'durable Whiteboard autosave in the packaged backend',
    UI_TIMEOUT_MS,
    200,
  );
  record('journey', `created, renamed, edited, and autosaved document ${document.id}`);
  return document;
}

async function openAndVerifyPersistedDocument(session, expected, title, marker) {
  const { page } = session;
  await waitEditor(page);
  const fileMenu = await openFileMenu(page);
  const candidates = fileMenu.locator('button[role="menuitemradio"]').filter({ hasText: title });
  assert.equal(await candidates.count(), 1, `Whiteboard File menu did not expose exactly one ${title}`);
  await candidates.first().click();
  const editor = await waitEditor(page);
  await waitText(page.locator('button.app-title'), title, 'reopened Whiteboard title', { exact: true });
  await waitText(editor, marker, 'reopened Whiteboard manuscript marker');
  const document = await readPersistedDocument(session, title, marker);
  assert.equal(String(document.id), String(expected.id), 'Whiteboard document id changed across restart');
  assert.equal(document.incarnation, expected.incarnation, 'Whiteboard incarnation changed across restart');
  record('journey', `opened document ${document.id} and verified durable content after relaunch`);
}

async function exportAndVerifyProjectBundle(session, bundlePath, document, title, marker) {
  await installBundleExportResponder(session, bundlePath);
  const fileMenu = await openFileMenu(session.page);
  await fileMenu.getByRole('button', { name: 'Export Project (.lfbundle)…', exact: true }).click();

  const stat = await waitFor(async () => {
    try {
      const candidate = await fs.lstat(bundlePath);
      return candidate.size > 0 ? candidate : false;
    } catch (error) {
      if (error?.code === 'ENOENT') return false;
      throw error;
    }
  }, 'Whiteboard .lfbundle export file', UI_TIMEOUT_MS, 100);
  assert.ok(
    stat.isFile() && !stat.isSymbolicLink(),
    `Whiteboard .lfbundle export is not a regular file: ${bundlePath}`,
  );
  assert.ok(stat.size <= MAX_EXPORT_BYTES, `Whiteboard .lfbundle export exceeded ${MAX_EXPORT_BYTES} bytes`);
  assertPathInside(bundlePath, session.productRoot, 'written Whiteboard export');
  assertSamePath(path.dirname(bundlePath), session.productRoot, 'written Whiteboard export parent');
  await assertBundleExportDialogUsed(session, bundlePath);
  await waitText(
    session.page.locator('[role="region"][aria-label="Notifications"]'),
    `Exported ${path.basename(bundlePath)}.`,
    'Whiteboard project export notification',
  );

  const raw = await fs.readFile(bundlePath);
  assert.equal(raw.byteLength, stat.size, 'Whiteboard export changed while it was being verified');
  const summary = validateWhiteboardExportBundle(JSON.parse(raw.toString('utf8')), {
    expectedProjectId: String(document.id),
    expectedTitle: title,
    expectedMarker: marker,
  });
  record(
    session.label,
    `verified export-only .lfbundle envelope for project ${summary.projectId} `
      + `(blocks=${summary.manuscriptBlockCount}, outline=${summary.outlineCount}, `
      + `comments=${summary.commentCount}, drafter=${summary.drafterPageCount}, `
      + `psyke=${summary.psykeElementCount}/${summary.psykeRelationCount}/${summary.psykeProgressionCount})`,
  );
}

async function killOwnedProcess(session) {
  if (session.child.exitCode === null) {
    if (process.platform === 'win32') {
      try {
        await execFileAsync(
          'taskkill.exe',
          ['/PID', String(session.pid), '/T', '/F'],
          { windowsHide: true, timeout: 15_000 },
        );
      } catch (error) {
        if (session.child.exitCode === null) throw error;
      }
    } else {
      try { await session.app.close(); } catch { /* best effort */ }
      if (session.child.exitCode === null) session.child.kill('SIGKILL');
    }
  }
}

async function terminateVerifiedBackendIfStillServing(session) {
  const verified = session.verifiedBackend;
  if (!verified || !(await canConnect(session.port))) return false;

  let health;
  try {
    health = await fetchHealth(verified);
  } catch (error) {
    record(session.label, `refusing backend-PID cleanup because health could not be verified: ${errorText(error)}`);
    return false;
  }
  if (!isMatchingWhiteboardBackendHealth(health, verified)) {
    record(session.label, 'refusing backend-PID cleanup because the live service identity/nonce changed');
    return false;
  }

  assert.ok(
    Number.isSafeInteger(verified.backendPid) && verified.backendPid > 0,
    `${session.label} has no verified backend PID`,
  );
  assert.notEqual(verified.backendPid, process.pid, `${session.label} backend PID points at the acceptance harness`);
  assert.notEqual(verified.backendPid, session.pid, `${session.label} backend PID points at the Electron root`);
  record(session.label, `terminating verified orphan backend pid=${verified.backendPid}`);

  if (process.platform === 'win32') {
    try {
      await execFileAsync(
        'taskkill.exe',
        ['/PID', String(verified.backendPid), '/T', '/F'],
        { windowsHide: true, timeout: 15_000 },
      );
    } catch (error) {
      if (await canConnect(session.port)) throw error;
    }
  } else {
    try {
      process.kill(verified.backendPid, 'SIGKILL');
    } catch (error) {
      if (error?.code !== 'ESRCH' && await canConnect(session.port)) throw error;
    }
  }
  return true;
}

async function closeSession(session, { requireGraceful = true, requirePrompt = false } = {}) {
  if (!session || session.closed) return;
  let closeError = null;
  let graceful = false;
  try {
    const exited = new Promise((resolve, reject) => {
      if (session.child.exitCode !== null) resolve();
      else {
        session.child.once('exit', resolve);
        session.child.once('error', reject);
      }
    });
    await session.app.evaluate(({ BrowserWindow }) => {
      const windows = BrowserWindow.getAllWindows();
      if (windows.length !== 1) throw new Error(`Expected one BrowserWindow, received ${windows.length}.`);
      windows[0].close();
    });
    await withTimeout(exited, CLOSE_TIMEOUT_MS, `${session.label} graceful close`);
    graceful = true;
  } catch (error) {
    closeError = error;
    record(session.label, `graceful close failed: ${errorText(error)}`);
    await killOwnedProcess(session);
  }

  let forcedBackendTeardown = false;
  let portCloseError = null;
  try {
    await waitFor(
      () => canConnect(session.port).then((open) => !open),
      `${session.label} backend port closure`,
      CLOSE_TIMEOUT_MS,
      200,
    );
  } catch (error) {
    portCloseError = error;
    if (!(await canConnect(session.port))) {
      portCloseError = null;
    } else {
      forcedBackendTeardown = await terminateVerifiedBackendIfStillServing(session);
    }
    if (portCloseError && forcedBackendTeardown) {
      await waitFor(
        () => canConnect(session.port).then((open) => !open),
        `${session.label} verified backend teardown`,
        CLOSE_TIMEOUT_MS,
        200,
      );
    }
  } finally {
    session.closed = true;
    activeSessions.delete(session);
  }
  if (portCloseError && !forcedBackendTeardown) throw portCloseError;
  if (requirePrompt) {
    await assertRegularFile(session.closeMarkerPath, `${session.label} close prompt marker`);
  }
  if (requireGraceful && (!graceful || forcedBackendTeardown)) {
    const reason = closeError ?? portCloseError ?? new Error('verified backend outlived the Electron process');
    throw new Error(`${session.label} required forced teardown: ${errorText(reason)}`);
  }
  record(session.label, 'closed gracefully and released its backend port');
}

async function captureScreenshot(session, name) {
  if (!session?.page || session.page.isClosed() || !diagnosticsDir) return;
  try {
    await fs.mkdir(diagnosticsDir, { recursive: true });
    const output = path.join(diagnosticsDir, `${session.label}-${name}.png`);
    await session.page.screenshot({ path: output, fullPage: true, animations: 'disabled' });
    record('diagnostics', `screenshot saved at ${output}`);
  } catch (error) {
    record('diagnostics', `screenshot failed: ${errorText(error)}`);
  }
}

async function writeFailureDiagnostics(error, metadata) {
  if (!diagnosticsDir) return;
  await fs.mkdir(diagnosticsDir, { recursive: true });
  await fs.writeFile(path.join(diagnosticsDir, 'failure.txt'), `${errorText(error)}\n`, 'utf8');
  await fs.writeFile(path.join(diagnosticsDir, 'acceptance.log'), `${logLines.join('\n')}\n`, 'utf8');
  await fs.writeFile(
    path.join(diagnosticsDir, 'run.json'),
    `${JSON.stringify({ ...metadata, failedAt: now() }, null, 2)}\n`,
    'utf8',
  );
}

async function removeFailureRuntimeDescriptor(productRoot) {
  const target = path.join(productRoot, 'runtime', MCP_RUNTIME_FILENAME);
  assertPathInside(target, productRoot, 'failure runtime descriptor');
  try {
    const stat = await fs.lstat(target);
    if (!stat.isFile() && !stat.isSymbolicLink()) {
      throw new Error(`Refusing unexpected runtime descriptor type: ${target}`);
    }
    await fs.rm(target, { force: true });
    record('cleanup', 'removed the private MCP runtime descriptor before preserving diagnostics');
  } catch (error) {
    if (error?.code !== 'ENOENT') throw error;
  }
}

async function removeSuccessfulRoot(root) {
  const resolved = path.resolve(root);
  assert.ok(validatedRemovalRoot, 'No validated lifecycle root is available for cleanup');
  assertSamePath(resolved, validatedRemovalRoot, 'lifecycle cleanup root');
  const stat = await fs.lstat(resolved);
  assert.ok(stat.isDirectory() && !stat.isSymbolicLink(), `Refusing unsafe cleanup target: ${resolved}`);
  assert.notEqual(normalizedPathKey(resolved), normalizedPathKey(path.parse(resolved).root), 'Refusing filesystem-root cleanup');
  const canonicalRepo = await fs.realpath(REPO_ROOT);
  assert.notEqual(normalizedPathKey(resolved), normalizedPathKey(canonicalRepo), 'Refusing workspace-root cleanup');
  assert.ok(!isSameOrInside(canonicalRepo, resolved), `Refusing cleanup of workspace ancestor: ${resolved}`);
  if (!rootCameFromOverride) {
    const tempParent = await fs.realpath(os.tmpdir());
    assertSamePath(path.dirname(resolved), tempParent, 'default lifecycle temp parent');
    assert.ok(path.basename(resolved).startsWith('logosforge-whiteboard-lifecycle-'), 'Unsafe lifecycle temp prefix');
  }
  await fs.rm(resolved, { recursive: true, force: true });
}

async function main() {
  assert.ok(['win32', 'darwin', 'linux'].includes(process.platform), `Unsupported platform: ${process.platform}`);
  const executable = await canonicalExecutable();
  const driver = await loadElectronDriver();
  const tempRoot = await createIsolationRoot();
  diagnosticsDir = path.join(tempRoot, 'diagnostics');
  const productRoot = path.join(tempRoot, 'whiteboard');
  await Promise.all([
    fs.mkdir(diagnosticsDir, { recursive: true }),
    fs.mkdir(productRoot, { recursive: true }),
  ]);
  const token = `${Date.now()}-${process.pid}`;
  const title = `Packaged Lifecycle ${token}`;
  const marker = `Durable Whiteboard marker ${token}.`;
  const metadata = { startedAt: now(), platform: process.platform, executable, tempRoot, title, marker };
  record('harness', `isolated lifecycle root: ${tempRoot}`);
  let succeeded = false;
  try {
    const first = await launchPackagedApp({
      electron: driver.electron,
      loaderPath: driver.loaderPath,
      executable,
      productRoot,
      label: 'whiteboard-lifecycle-1',
    });
    await waitLocalService(first);
    const firstRuntime = await verifyLiveRuntimeBoundary(first);
    await exerciseLiveMcpDiscovery(first, firstRuntime.value.auth_token);
    const document = await createEditAndAutosave(first, title, marker);
    await captureScreenshot(first, 'autosaved');
    await closeSession(first, { requirePrompt: true });
    await assertRegularFile(path.join(first.dirs.data, 'whiteboard.db'), 'Persisted Whiteboard database');
    await assertMcpFailsClosed(first);

    const second = await launchPackagedApp({
      electron: driver.electron,
      loaderPath: driver.loaderPath,
      executable,
      productRoot,
      label: 'whiteboard-lifecycle-2',
    });
    await waitLocalService(second);
    const secondRuntime = await verifyLiveRuntimeBoundary(second);
    assert.notEqual(second.port, first.port, 'Whiteboard relaunch reused its first isolated port');
    assert.notEqual(
      secondRuntime.summary.instanceNonce,
      firstRuntime.summary.instanceNonce,
      'Whiteboard relaunch reused a stale runtime nonce',
    );
    await openAndVerifyPersistedDocument(second, document, title, marker);
    const bundlePath = path.join(productRoot, 'packaged-whiteboard-export.lfbundle');
    await exportAndVerifyProjectBundle(second, bundlePath, document, title, marker);
    await captureScreenshot(second, 'reopened');
    await closeSession(second);
    await assertMcpFailsClosed(second);

    succeeded = true;
    record('harness', 'PASS: standalone packaged Whiteboard lifecycle completed');
  } catch (error) {
    record('harness', `FAIL: ${errorText(error)}`);
    for (const session of [...activeSessions]) await captureScreenshot(session, 'failure');
    for (const session of [...activeSessions]) {
      try { await closeSession(session, { requireGraceful: false }); } catch (cleanupError) {
        record('cleanup', `${session.label}: ${errorText(cleanupError)}`);
      }
    }
    try { await removeFailureRuntimeDescriptor(productRoot); } catch (cleanupError) {
      record('cleanup', `runtime descriptor sanitization failed: ${errorText(cleanupError)}`);
    }
    await writeFailureDiagnostics(error, metadata);
    console.error(`Whiteboard lifecycle acceptance failed. Diagnostics preserved at ${diagnosticsDir}`);
    throw error;
  } finally {
    if (succeeded) {
      await removeSuccessfulRoot(tempRoot);
      console.log('Whiteboard lifecycle acceptance passed; its exact temporary root was removed.');
    }
  }
}

main().catch((error) => {
  console.error(errorText(error));
  process.exitCode = 1;
});
