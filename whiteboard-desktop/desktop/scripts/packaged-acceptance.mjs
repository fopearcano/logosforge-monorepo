#!/usr/bin/env node

/**
 * Windows packaged-app acceptance for LogosForge Whiteboard -> LogosForge Pro.
 *
 * This deliberately launches electron-builder's unpacked *packaged* applications,
 * not `electron .` or a Vite preview.  It uses Playwright's Electron transport
 * from `playwright-core`; no browser download is required.  Native file pickers
 * are the only seam: their Electron main-process methods are replaced with
 * absolute, one-shot paths queued by this harness.
 *
 * Optional executable overrides (both must still be packaged app executables):
 *   LOGOSFORGE_WHITEBOARD_ACCEPTANCE_EXE=C:\...\LogosForge Whiteboard.exe
 *   LOGOSFORGE_PRO_ACCEPTANCE_EXE=C:\...\LogosForge Pro.exe
 * Optional exact run root (must be absolute, absent or an empty real directory):
 *   LOGOSFORGE_PACKAGED_ACCEPTANCE_ROOT=C:\...\packaged-acceptance-run
 */

import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { createHash } from 'node:crypto';
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
const REPO_ROOT = path.resolve(DESKTOP_DIR, '..', '..');

const DEFAULT_WHITEBOARD_EXE = path.join(
  DESKTOP_DIR,
  'release',
  'win-unpacked',
  'LogosForge Whiteboard.exe',
);
const DEFAULT_PRO_EXE = path.join(
  REPO_ROOT,
  'pro-desktop',
  'release',
  'win-unpacked',
  'LogosForge Pro.exe',
);

const PROJECT_TITLE = 'Packaged Acceptance';
const OUTLINE_TITLE = 'Acceptance Arc';
const PSYKE_NAME = 'Mara Acceptance';
const PSYKE_DESCRIPTION = 'Packaged acceptance protagonist';
const PSYKE_NOTES = 'Created through the packaged Whiteboard UI.';
const PSYKE_SECOND_NAME = 'Ivo Acceptance';
const PSYKE_SECOND_DESCRIPTION = 'Packaged acceptance rival';
const PSYKE_SECOND_NOTES = 'Created through the authenticated packaged Whiteboard API.';
// Use a relation with a distinct stored inverse so the packaged gate catches
// endpoint reversal as well as missing/unmapped relations.
const PSYKE_RELATION_TYPE = 'payoff';
const PSYKE_PROGRESSION_TEXTS = [
  'Mara vows to expose the archive.',
  'Mara risks the archive to reveal the truth.',
];
const OPEN_COMMENT_BODY = 'Tighten this opening image before the next draft.';
const OPEN_COMMENT_REPLY = 'Keep the concrete image; remove the explanatory clause.';
const RESOLVED_COMMENT_BODY = 'Chapter promise checked against the outline.';
const COMMENT_SCENE_TITLE = 'Chapter Two';
const FIRST_SCENE_BODY = 'The archive waits behind a sealed brass door.';
const QA_PREFIX = 'Ada stepped into the archive, dust hanging in the dawn light.';
const STARTUP_TIMEOUT_MS = 90_000;
const UI_TIMEOUT_MS = 30_000;
const CLOSE_TIMEOUT_MS = 20_000;
const PORT_CLOSE_TIMEOUT_MS = 12_000;
const LOG_LIMIT = 4 * 1024 * 1024;

const activeSessions = new Set();
const usedPorts = new Set();
const logLines = [];
let tempRoot = null;
let diagnosticsDir = null;
let validatedRemovalRoot = null;
let rootCameFromOverride = false;
let playwrightElectronLoader = null;
let realSettingsGuard = null;
let acceptanceMutationSequence = 0;

function now() {
  return new Date().toISOString();
}

function trimLogValue(value) {
  const text = String(value ?? '').replace(/\r\n/g, '\n').trimEnd();
  return text.length > 16_000 ? `${text.slice(0, 16_000)}\n...[entry truncated]` : text;
}

function record(scope, value) {
  const line = `${now()} [${scope}] ${trimLogValue(value)}`;
  logLines.push(line);
  let total = 0;
  for (let index = logLines.length - 1; index >= 0; index -= 1) {
    total += logLines[index].length + 1;
    if (total > LOG_LIMIT) {
      logLines.splice(0, index + 1, `${now()} [harness] ...[older log entries truncated]`);
      break;
    }
  }
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

function assertPathInside(child, parent, label) {
  const relative = path.relative(path.resolve(parent), path.resolve(child));
  assert.ok(
    relative === '' || (!relative.startsWith('..') && !path.isAbsolute(relative)),
    `${label}: ${child} is outside ${parent}`,
  );
}

async function canonicalFile(input, envName) {
  const override = process.env[envName]?.trim();
  if (override && !path.isAbsolute(override)) {
    throw new Error(`${envName} must be an absolute path; received ${override}`);
  }
  const requested = override || input;
  let stat;
  try {
    stat = await fs.stat(requested);
  } catch (error) {
    throw new Error(
      `Packaged executable is missing: ${requested}. Build a fresh win-unpacked package first. (${errorText(error)})`,
    );
  }
  assert.ok(stat.isFile(), `Packaged executable is not a file: ${requested}`);
  return fs.realpath(requested);
}

function isSameOrInside(candidate, parent) {
  const relative = path.relative(path.resolve(parent), path.resolve(candidate));
  return relative === '' || (!relative.startsWith('..') && !path.isAbsolute(relative));
}

async function createIsolationRoot() {
  const override = process.env.LOGOSFORGE_PACKAGED_ACCEPTANCE_ROOT?.trim();
  if (!override) {
    const created = await fs.mkdtemp(path.join(os.tmpdir(), 'logosforge-packaged-acceptance-'));
    const canonical = await fs.realpath(created);
    validatedRemovalRoot = canonical;
    rootCameFromOverride = false;
    return canonical;
  }

  if (!path.isAbsolute(override)) {
    throw new Error(
      `LOGOSFORGE_PACKAGED_ACCEPTANCE_ROOT must be absolute; received ${override}`,
    );
  }
  const resolved = path.resolve(override);
  const filesystemRoot = path.parse(resolved).root;
  assert.notEqual(
    windowsPathKey(resolved),
    windowsPathKey(filesystemRoot),
    `Refusing to use a filesystem root for packaged acceptance: ${resolved}`,
  );

  const canonicalRepo = await fs.realpath(REPO_ROOT);
  assert.notEqual(
    windowsPathKey(resolved),
    windowsPathKey(canonicalRepo),
    `Refusing to use the workspace root for packaged acceptance: ${resolved}`,
  );
  assert.ok(
    !isSameOrInside(canonicalRepo, resolved),
    `Refusing to use an ancestor of the workspace for packaged acceptance: ${resolved}`,
  );

  try {
    const existing = await fs.lstat(resolved);
    assert.ok(existing.isDirectory(), `Packaged acceptance root is not a directory: ${resolved}`);
    assert.ok(!existing.isSymbolicLink(), `Packaged acceptance root cannot be a symlink: ${resolved}`);
    const entries = await fs.readdir(resolved);
    assert.equal(
      entries.length,
      0,
      `Packaged acceptance root must be empty before the run: ${resolved}`,
    );
  } catch (error) {
    if (error?.code !== 'ENOENT') throw error;
    await fs.mkdir(resolved, { recursive: false });
  }

  const canonical = await fs.realpath(resolved);
  assert.notEqual(
    windowsPathKey(canonical),
    windowsPathKey(canonicalRepo),
    `Refusing to use the workspace root for packaged acceptance: ${canonical}`,
  );
  assert.ok(
    !isSameOrInside(canonicalRepo, canonical),
    `Refusing to use an ancestor of the workspace for packaged acceptance: ${canonical}`,
  );
  validatedRemovalRoot = canonical;
  rootCameFromOverride = true;
  return canonical;
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

async function fingerprintFile(filePath) {
  try {
    const [contents, stat] = await Promise.all([fs.readFile(filePath), fs.stat(filePath)]);
    return {
      exists: true,
      size: stat.size,
      birthtimeMs: stat.birthtimeMs,
      mtimeMs: stat.mtimeMs,
      sha256: createHash('sha256').update(contents).digest('hex'),
    };
  } catch (error) {
    if (error?.code === 'ENOENT') return { exists: false };
    throw error;
  }
}

async function initializeRealSettingsGuard() {
  const filePath = path.join(os.homedir(), '.logosforge', 'settings.json');
  realSettingsGuard = { filePath, fingerprint: await fingerprintFile(filePath) };
}

async function assertRealSettingsUnchanged(label) {
  assert.ok(realSettingsGuard, 'The real-settings fingerprint guard was not initialized.');
  const current = await fingerprintFile(realSettingsGuard.filePath);
  assert.deepEqual(
    current,
    realSettingsGuard.fingerprint,
    `${label} changed the runner user's real LogosForge settings: ${realSettingsGuard.filePath}`,
  );
  record('isolation', `${label}: real user settings unchanged`);
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
  await locator.first().waitFor({ state: 'visible', timeout: timeoutMs });
  record('ui', `visible: ${label}`);
  return locator.first();
}

async function waitText(locator, expected, label, { exact = false, timeoutMs = UI_TIMEOUT_MS } = {}) {
  const target = locator.first();
  await waitFor(async () => {
    if (!(await target.isVisible().catch(() => false))) return false;
    const value = (await target.textContent()) ?? '';
    return exact ? value.trim() === expected : value.includes(expected);
  }, label, timeoutMs);
  record('ui', `text: ${label} -> ${expected}`);
  return target;
}

async function waitFile(filePath, label, timeoutMs = UI_TIMEOUT_MS) {
  await waitFor(async () => {
    try {
      const stat = await fs.stat(filePath);
      return stat.isFile() && stat.size > 0;
    } catch {
      return false;
    }
  }, label, timeoutMs);
  record('file', `${label}: ${filePath}`);
}

function serviceStatusMethod(session) {
  if (session.product === 'whiteboard') return 'getBackendStatus';
  if (session.product === 'pro') return 'getCoreStatus';
  throw new Error(`Unsupported packaged product: ${session.product}`);
}

async function inspectLocalService(session) {
  const bridgeMethod = serviceStatusMethod(session);
  return session.page.evaluate(async ({ bridgeMethod: method, expectedPort }) => {
    const bridge = globalThis.logosforge;
    const readStatus = bridge?.[method];
    if (typeof readStatus !== 'function') {
      throw new Error(`The packaged bridge does not expose ${method}.`);
    }
    const status = await readStatus();
    if (!status || typeof status !== 'object') {
      throw new Error('The packaged service returned an invalid status payload.');
    }
    if (typeof status.baseUrl !== 'string' || !status.baseUrl) {
      throw new Error('The packaged service status has no endpoint.');
    }
    const endpoint = new URL(status.baseUrl);
    const loopback = endpoint.hostname === '127.0.0.1'
      || endpoint.hostname === '::1'
      || endpoint.hostname === '[::1]';
    if (endpoint.protocol !== 'http:' || !loopback || endpoint.username || endpoint.password
        || (endpoint.pathname !== '' && endpoint.pathname !== '/')
        || endpoint.search || endpoint.hash) {
      throw new Error('The packaged service endpoint is not a plain loopback HTTP origin.');
    }
    if (Number(endpoint.port) !== expectedPort) {
      throw new Error(`The packaged service endpoint did not use the isolated port ${expectedPort}.`);
    }
    if (typeof status.authToken !== 'string'
        || !/^[A-Za-z0-9_-]{32,}$/.test(status.authToken)) {
      throw new Error('The packaged service status has no valid in-memory credential.');
    }
    // Deliberately return no credential. Acceptance diagnostics may log this
    // object, while the secret must remain inside the sandboxed renderer.
    return {
      state: status.state,
      baseUrl: endpoint.origin,
      managed: status.managed === true,
      service: typeof status.service === 'string' ? status.service : '',
    };
  }, { bridgeMethod, expectedPort: session.port });
}

async function waitLocalServiceConnected(session, label = session.label) {
  let safeStatus = null;
  await waitFor(async () => {
    safeStatus = await inspectLocalService(session);
    return safeStatus.state === 'connected';
  }, `${label} authenticated local service`, STARTUP_TIMEOUT_MS, 250);
  assert.equal(safeStatus?.managed, true, `${label} did not launch its packaged local service`);
  record('process', `${label} authenticated local service connected on isolated port ${session.port}`);
  return safeStatus;
}

async function localServiceRequest(
  session,
  requestPath,
  { method = 'GET', headers = {}, body, timeoutMs = UI_TIMEOUT_MS } = {},
) {
  assert.match(requestPath, /^\/api\//, `Unsafe packaged service path: ${requestPath}`);
  assert.ok(
    Number.isSafeInteger(timeoutMs) && timeoutMs > 0 && timeoutMs <= STARTUP_TIMEOUT_MS,
    `Unsafe packaged service timeout: ${timeoutMs}`,
  );
  assert.ok(
    !Object.keys(headers).some((name) => name.toLowerCase() === 'authorization'),
    'Callers must not supply or retain packaged service credentials.',
  );
  const bridgeMethod = serviceStatusMethod(session);
  const upperMethod = String(method).toUpperCase();
  const result = await session.page.evaluate(async (request) => {
    const bridge = globalThis.logosforge;
    const readStatus = bridge?.[request.bridgeMethod];
    if (typeof readStatus !== 'function') {
      throw new Error(`The packaged bridge does not expose ${request.bridgeMethod}.`);
    }
    const status = await readStatus();
    if (!status || status.state !== 'connected'
        || typeof status.baseUrl !== 'string'
        || typeof status.authToken !== 'string'
        || !/^[A-Za-z0-9_-]{32,}$/.test(status.authToken)) {
      throw new Error('The packaged service is not connected with an in-memory credential.');
    }
    const endpoint = new URL(status.baseUrl);
    const loopback = endpoint.hostname === '127.0.0.1'
      || endpoint.hostname === '::1'
      || endpoint.hostname === '[::1]';
    if (endpoint.protocol !== 'http:' || !loopback || endpoint.username || endpoint.password
        || (endpoint.pathname !== '' && endpoint.pathname !== '/')
        || endpoint.search || endpoint.hash
        || Number(endpoint.port) !== request.expectedPort) {
      throw new Error('The packaged service endpoint escaped its isolated loopback origin.');
    }
    const url = new URL(request.path, `${endpoint.origin}/`);
    if (url.origin !== endpoint.origin || !url.pathname.startsWith('/api/')) {
      throw new Error('The packaged service request escaped its API origin.');
    }
    const requestHeaders = new Headers(request.headers);
    requestHeaders.set('Authorization', `Bearer ${status.authToken}`);
    if (request.hasBody && !requestHeaders.has('Content-Type')) {
      requestHeaders.set('Content-Type', 'application/json');
    }
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), request.timeoutMs);
    try {
      const response = await fetch(url, {
        method: request.method,
        headers: requestHeaders,
        body: request.hasBody ? JSON.stringify(request.body) : undefined,
        signal: controller.signal,
      });
      const text = await response.text();
      if (text.length > 4 * 1024 * 1024) {
        throw new Error('The packaged service response exceeded the acceptance limit.');
      }
      let data = null;
      if (text) {
        try {
          data = JSON.parse(text);
        } catch {
          data = text;
        }
      }
      return {
        ok: response.ok,
        status: response.status,
        data,
        etag: response.headers.get('ETag'),
      };
    } catch (error) {
      if (controller.signal.aborted) {
        throw new Error(`The packaged service request exceeded ${request.timeoutMs}ms.`);
      }
      throw error;
    } finally {
      clearTimeout(timeout);
    }
  }, {
    bridgeMethod,
    expectedPort: session.port,
    path: requestPath,
    method: upperMethod,
    headers,
    hasBody: body !== undefined,
    body,
    timeoutMs,
  });
  if (!result.ok) {
    const detail = typeof result.data === 'string'
      ? result.data
      : JSON.stringify(result.data ?? {});
    throw new Error(
      `${session.label} ${upperMethod} ${requestPath} failed with HTTP ${result.status}`
      + (detail ? `: ${detail.slice(0, 1000)}` : ''),
    );
  }
  record('api', `${session.label} ${upperMethod} ${requestPath} -> ${result.status}`);
  return result;
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
  await waitFor(async () => !(await canConnect(port)), `${label} port ${port} to close`, PORT_CLOSE_TIMEOUT_MS, 250);
  record('process', `${label} port ${port} closed`);
}

async function prepareProductEnvironment(productRoot, product, port) {
  const dirs = {
    userData: path.join(productRoot, 'user-data'),
    data: path.join(productRoot, 'data'),
    home: path.join(productRoot, 'home'),
    models: path.join(productRoot, 'models'),
    qaLogs: path.join(productRoot, 'qa', 'logs'),
    qaReports: path.join(productRoot, 'qa', 'reports'),
  };
  await Promise.all(Object.values(dirs).map((dir) => fs.mkdir(dir, { recursive: true })));

  const env = { ...process.env };
  for (const inherited of [
    'ELECTRON_RUN_AS_NODE',
    'LOGOSFORGE_CORE_DIR',
    'LOGOSFORGE_PYTHON',
    'LOGOSFORGE_VOICE_CUDA_DIRS',
    'API_AUTH_TOKEN',
    'LOGOSFORGE_WHITEBOARD_AUTH_TOKEN',
    'OPENAI_API_KEY',
    'ANTHROPIC_API_KEY',
    'OPENROUTER_API_KEY',
    'GH_TOKEN',
    'GITHUB_TOKEN',
  ]) {
    delete env[inherited];
  }

  Object.assign(env, {
    HOME: dirs.home,
    USERPROFILE: dirs.home,
    LOGOSFORGE_HOST: '127.0.0.1',
    LOGOSFORGE_PORT: String(port),
    LOGOSFORGE_QA_MODE: '1',
    LOGOSFORGE_FAKE_PROVIDER_PROFILE: 'valid_novel_prose',
    LOGOSFORGE_QA_LOG_DIR: dirs.qaLogs,
    LOGOSFORGE_QA_REPORT_DIR: dirs.qaReports,
    LOGOSFORGE_MODELS_DIR: dirs.models,
    // A non-empty, deliberately absent path disables Pro's real-profile model
    // auto-discovery while still exercising the normal "voice unavailable" path.
    LOGOSFORGE_VOICE_MODEL: path.join(dirs.models, 'acceptance-no-voice-model'),
    LOGOSFORGE_VOICE_DEVICE: 'cpu',
    LOGOSFORGE_VOICE_COMPUTE: 'int8',
  });

  if (product === 'whiteboard') {
    env.LOGOSFORGE_DATA_DIR = dirs.data;
    env.LOGOSFORGE_DB_PATH = path.join(dirs.data, 'whiteboard.db');
  } else {
    // The packaged Pro main process passes its userData DB as an explicit --db.
    // Keep the environment fallback isolated too, so no alternate path can leak.
    env.LOGOSFORGE_DB_PATH = path.join(dirs.data, 'logosforge.db');
    delete env.LOGOSFORGE_DATA_DIR;
  }

  return { env, dirs };
}

function attachProcessDiagnostics(session) {
  const child = session.app.process();
  for (const [streamName, stream] of [['stdout', child.stdout], ['stderr', child.stderr]]) {
    stream?.on('data', (chunk) => record(`${session.label}:${streamName}`, chunk));
  }
  child.once('exit', (code, signal) => {
    record(session.label, `root process exited (pid=${session.pid}, code=${code}, signal=${signal})`);
  });
}

function attachPageDiagnostics(session) {
  session.page.on('console', (message) => {
    const location = message.location();
    const where = location?.url ? ` (${location.url}:${location.lineNumber ?? 0})` : '';
    record(`${session.label}:renderer:${message.type()}`, `${message.text()}${where}`);
  });
  session.page.on('pageerror', (error) => record(`${session.label}:pageerror`, errorText(error)));
  session.page.on('crash', () => record(`${session.label}:renderer`, 'page crashed'));
}

async function assertPackagedRuntime(session, expected) {
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
      homeEnv: process.env.HOME,
      userProfileEnv: process.env.USERPROFILE,
      windowCount: windows.length,
      preferences: {
        contextIsolation: preferences.contextIsolation,
        nodeIntegration: preferences.nodeIntegration,
        sandbox: preferences.sandbox,
      },
    };
  });

  assert.equal(runtime.isPackaged, true, `${session.label} did not report app.isPackaged`);
  assert.equal(runtime.windowCount, 1, `${session.label} must expose exactly one BrowserWindow`);
  assertSamePath(runtime.execPath, expected.exePath, `${session.label} process.execPath`);
  assertSamePath(runtime.resourcesPath, expected.resourcesPath, `${session.label} process.resourcesPath`);
  assertSamePath(runtime.appPath, path.join(expected.resourcesPath, 'app.asar'), `${session.label} app.getAppPath()`);
  assertPathInside(runtime.userData, session.dirs.userData, `${session.label} userData isolation`);
  assertPathInside(runtime.sessionData, session.dirs.userData, `${session.label} sessionData isolation`);
  assertSamePath(runtime.homeEnv, session.dirs.home, `${session.label} HOME isolation`);
  assertSamePath(runtime.userProfileEnv, session.dirs.home, `${session.label} USERPROFILE isolation`);
  assert.deepEqual(
    runtime.preferences,
    { contextIsolation: true, nodeIntegration: false, sandbox: true },
    `${session.label} BrowserWindow security preferences changed`,
  );

  const globals = await session.page.evaluate(() => ({
    requireType: typeof globalThis.require,
    processType: typeof globalThis.process,
    moduleType: typeof globalThis.module,
  }));
  assert.deepEqual(
    globals,
    { requireType: 'undefined', processType: 'undefined', moduleType: 'undefined' },
    `${session.label} renderer main world exposes Node globals`,
  );
  session.runtimeVerified = true;
  session.runtime = runtime;
  record(
    session.label,
    `verified packaged runtime ${runtime.appName}; exec=${runtime.execPath}; resources=${runtime.resourcesPath}; userData=${runtime.userData}`,
  );
}

async function installDialogQueues(session, { open = [], save = [], message = [] }) {
  for (const queuedPath of [...open, ...save]) {
    assert.ok(path.isAbsolute(queuedPath), `Dialog queue paths must be absolute: ${queuedPath}`);
  }
  for (const item of message) {
    assert.ok(Number.isSafeInteger(item?.response) && item.response >= 0, 'Dialog response must be a non-negative integer.');
    assert.equal(typeof item?.button, 'string', 'Dialog response must name its expected button.');
    assert.equal(typeof item?.message, 'string', 'Dialog response must name its expected message.');
    assert.ok(path.isAbsolute(item?.markerPath), 'Dialog response marker must be an absolute path.');
  }
  if (open.length === 0 && save.length === 0 && message.length === 0) return null;

  const key = `__logosforgePackagedAcceptanceDialogs_${session.pid}_${Date.now()}`;
  await session.app.evaluate(({ dialog }, state) => {
    const queue = {
      open: [...state.open],
      save: [...state.save],
      message: state.message.map((item) => ({ ...item })),
      usedOpen: [],
      usedSave: [],
      usedMessage: [],
    };
    globalThis[state.key] = queue;

    if (queue.open.length > 0) {
      dialog.showOpenDialog = async () => {
        const filePath = queue.open.shift();
        if (!filePath) throw new Error('Packaged acceptance open-dialog queue was exhausted.');
        queue.usedOpen.push(filePath);
        return { canceled: false, filePaths: [filePath] };
      };
    }
    if (queue.save.length > 0) {
      dialog.showSaveDialog = async () => {
        const filePath = queue.save.shift();
        if (!filePath) throw new Error('Packaged acceptance save-dialog queue was exhausted.');
        queue.usedSave.push(filePath);
        return { canceled: false, filePath };
      };
    }
    if (queue.message.length > 0) {
      dialog.showMessageBox = async (...args) => {
        const expected = queue.message.shift();
        if (!expected) throw new Error('Packaged acceptance message-dialog queue was exhausted.');
        const options = args.at(-1) ?? {};
        const actualMessage = String(options.message ?? '');
        const actualButton = Array.isArray(options.buttons) ? options.buttons[expected.response] : undefined;
        if (!actualMessage.includes(expected.message) || actualButton !== expected.button) {
          throw new Error(
            `Unexpected packaged acceptance message dialog: message=${actualMessage}; response button=${actualButton}`,
          );
        }
        process.getBuiltinModule('node:fs').writeFileSync(
          expected.markerPath,
          `${actualButton}: ${actualMessage}\n`,
          'utf8',
        );
        queue.usedMessage.push({ ...expected, actualMessage });
        return { response: expected.response, checkboxChecked: false };
      };
    }
  }, { key, open, save, message });
  session.dialogQueueKey = key;
  record(
    session.label,
    `installed native dialog queues (open=${open.length}, save=${save.length}, message=${message.length})`,
  );
  return key;
}

async function dialogQueueState(session) {
  if (!session.dialogQueueKey) {
    return { open: 0, save: 0, message: 0, usedOpen: [], usedSave: [], usedMessage: [] };
  }
  return session.app.evaluate((_electron, key) => {
    const queue = globalThis[key];
    if (!queue) throw new Error(`Missing packaged acceptance dialog queue: ${key}`);
    return {
      open: queue.open.length,
      save: queue.save.length,
      message: queue.message.length,
      usedOpen: [...queue.usedOpen],
      usedSave: [...queue.usedSave],
      usedMessage: [...queue.usedMessage],
    };
  }, session.dialogQueueKey);
}

async function assertDialogQueuesDrained(session) {
  const state = await dialogQueueState(session);
  assert.equal(state.open, 0, `${session.label} left ${state.open} open-dialog path(s) unused`);
  assert.equal(state.save, 0, `${session.label} left ${state.save} save-dialog path(s) unused`);
  record(session.label, `dialog queues drained; open=${state.usedOpen.length}, save=${state.usedSave.length}`);
}

async function launchPackagedApp({ electron, label, product, exePath, productRoot, dialogs }) {
  assert.ok(
    playwrightElectronLoader && path.isAbsolute(playwrightElectronLoader),
    'The Playwright Electron loader was not resolved before launch.',
  );
  const port = await allocateStrictPort();
  const { env, dirs } = await prepareProductEnvironment(productRoot, product, port);
  const expectedResources = path.join(path.dirname(exePath), 'resources');
  const expectedSidecar = product === 'whiteboard'
    ? path.join(expectedResources, 'backend', 'logosforge-whiteboard-backend.exe')
    : path.join(expectedResources, 'core', 'logosforge-core.exe');
  await assertFile(path.join(expectedResources, 'app.asar'), `${label} app.asar`);
  await assertFile(expectedSidecar, `${label} packaged sidecar`);

  record(label, `launching ${exePath} on strict port ${port}`);
  const app = await electron.launch({
    executablePath: exePath,
    // playwright-core only auto-preloads this when it resolves Electron itself.
    // With an electron-builder executablePath we must preload the same loader so
    // Playwright can hold/release `ready` and establish its main-process channel.
    // Chromium's supported user-data switch isolates every persistent Electron
    // profile store without replacing Windows' process-level profile variables.
    // Repointing APPDATA/LOCALAPPDATA can crash current Chromium sandbox startup
    // before application JavaScript runs on supported Windows hosts.
    args: ['-r', playwrightElectronLoader, `--user-data-dir=${dirs.userData}`],
    cwd: path.dirname(exePath),
    env,
    timeout: STARTUP_TIMEOUT_MS,
  });
  const child = app.process();
  const pid = child.pid;
  assert.ok(Number.isSafeInteger(pid) && pid > 0, `${label} did not expose an owned root PID`);

  const session = {
    app,
    page: null,
    child,
    pid,
    port,
    label,
    product,
    dirs,
    productRoot,
    exePath,
    expectedResources,
    expectedSidecar,
    dialogQueueKey: null,
    runtimeVerified: false,
    runtime: null,
    closed: false,
  };
  activeSessions.add(session);
  attachProcessDiagnostics(session);

  try {
    session.page = await app.firstWindow({ timeout: STARTUP_TIMEOUT_MS });
    attachPageDiagnostics(session);
    await installDialogQueues(session, dialogs ?? {});
    await assertPackagedRuntime(session, { exePath, resourcesPath: expectedResources });
    return session;
  } catch (error) {
    record(label, `launch verification failed: ${errorText(error)}`);
    throw error;
  }
}

async function captureScreenshot(session, name) {
  if (!session?.page || session.page.isClosed()) return;
  const safeName = name.replace(/[^A-Za-z0-9_.-]+/g, '-');
  const output = path.join(diagnosticsDir, `${session.label}-${safeName}.png`);
  try {
    await session.page.screenshot({ path: output, fullPage: true, animations: 'disabled' });
    record('diagnostics', `screenshot: ${output}`);
  } catch (error) {
    record('diagnostics', `could not capture ${output}: ${errorText(error)}`);
  }
}

async function killOwnedTree(session) {
  assert.equal(session.child.pid, session.pid, `${session.label} root PID ownership changed`);
  assert.ok(Number.isSafeInteger(session.pid) && session.pid > 0, `${session.label} has an invalid root PID`);
  record(session.label, `fallback taskkill for owned root PID ${session.pid}`);
  try {
    const result = await execFileAsync(
      'taskkill.exe',
      ['/PID', String(session.pid), '/T', '/F'],
      { windowsHide: true, timeout: 15_000 },
    );
    if (result.stdout) record(`${session.label}:taskkill`, result.stdout);
    if (result.stderr) record(`${session.label}:taskkill`, result.stderr);
  } catch (error) {
    // "not found" is benign when the app exited between the timeout and taskkill.
    if (session.child.exitCode == null) throw error;
    record(session.label, `taskkill raced with process exit: ${errorText(error)}`);
  }
}

async function closeSession(session, { requireGraceful = true, timeoutMs = CLOSE_TIMEOUT_MS } = {}) {
  if (!session || session.closed) return;
  let graceful = false;
  let closeError = null;
  try {
    // Playwright's ElectronApplication.close() starts by closing its browser
    // context. That can sever the renderer before LogosForge's correlated
    // autosave/close handshake has replied. Exercise the real BrowserWindow
    // close path while the renderer is still connected, then observe the owned
    // root process exit instead.
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
        throw new Error(`Expected exactly one BrowserWindow before close; received ${windows.length}`);
      }
      windows[0].close();
    });
    await withTimeout(exited, timeoutMs, `${session.label} graceful close`);
    graceful = true;
    record(session.label, 'closed gracefully through the application handshake');
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
    throw new Error(`${session.label} required a forced PID-tree teardown: ${errorText(closeError)}`);
  }
}

async function openWhiteboardFileMenu(page) {
  // The trigger's accessible name is its visible `File` text; `File menu` is
  // currently a title attribute.  Key off the stable title and verify the text.
  const trigger = await waitVisible(page.locator('button[title="File menu"]'), 'Whiteboard File trigger');
  assert.equal((await trigger.textContent())?.trim(), 'File', 'Unexpected Whiteboard File trigger label');
  await trigger.click();
  return waitVisible(page.getByRole('dialog', { name: 'File menu', exact: true }), 'Whiteboard File menu');
}

async function waitWhiteboardReady(page) {
  const editor = page.locator('.wb-editor[contenteditable="true"]');
  await waitVisible(editor, 'Whiteboard editor', STARTUP_TIMEOUT_MS);
  return editor;
}

async function createAndEditWhiteboard(session, bodyMarker) {
  const { page } = session;
  let editor = await waitWhiteboardReady(page);
  const previousEditor = await editor.elementHandle();
  assert.ok(previousEditor, 'Whiteboard did not expose the initial editor element');

  const fileMenu = await openWhiteboardFileMenu(page);
  await fileMenu.getByRole('button', { name: 'New Document', exact: true }).click();
  await waitFor(
    async () => previousEditor.evaluate((element) => !element.isConnected),
    'the newly-created Whiteboard document editor to replace the previous editor',
  );
  editor = await waitWhiteboardReady(page);

  const renameMenu = await openWhiteboardFileMenu(page);
  await renameMenu.getByRole('button', { name: 'Rename current document…', exact: true }).click();
  const renameDialog = await waitVisible(
    page.getByRole('dialog', { name: 'Rename document', exact: true }),
    'Rename document dialog',
  );
  await renameDialog.getByLabel('Document title', { exact: true }).fill(PROJECT_TITLE);
  await renameDialog.getByRole('button', { name: 'Rename', exact: true }).click();
  await waitText(page.locator('button.app-title'), PROJECT_TITLE, 'renamed Whiteboard document', { exact: true });

  await editor.click();
  await page.keyboard.press('Control+A');
  await page.keyboard.press('Backspace');
  await page.keyboard.type('# ');
  await page.keyboard.type('Chapter One');
  await page.keyboard.press('Enter');
  await page.keyboard.type(FIRST_SCENE_BODY);
  await page.keyboard.press('Enter');
  await page.keyboard.type('# ');
  await page.keyboard.type(COMMENT_SCENE_TITLE);
  await page.keyboard.press('Enter');
  await page.keyboard.type(bodyMarker);
  await waitText(editor, bodyMarker, 'typed Whiteboard marker');
  await waitVisible(editor.getByRole('heading', { name: 'Chapter One', exact: true }), 'Whiteboard heading');
  await waitVisible(editor.getByRole('heading', { name: COMMENT_SCENE_TITLE, exact: true }), 'Whiteboard second heading');
  await waitText(page.locator('.wb-draft-saved'), 'Draft saved', 'Whiteboard autosave', {
    exact: true,
    timeoutMs: UI_TIMEOUT_MS,
  });
  record('journey', 'Whiteboard create/rename/keyboard edit/autosave complete');
}

async function addWhiteboardOutline(page) {
  const panel = page.locator('aside[aria-label="Outline"]');
  if (!(await panel.isVisible().catch(() => false))) {
    await page.getByRole('button', { name: 'Toggle outline', exact: true }).click();
  }
  await waitVisible(panel, 'Whiteboard Outline panel');
  await panel.getByRole('button', { name: '+ Add', exact: true }).click();
  const title = await waitVisible(panel.getByLabel('Outline item title', { exact: true }), 'Outline item title');
  await title.fill(OUTLINE_TITLE);
  await waitVisible(
    panel.locator('.outline-save-dirty, .outline-save-saving'),
    'Outline dirty/saving transition',
    10_000,
  );
  await waitText(panel.locator('.outline-save-saved'), 'Saved', 'Outline autosave', { exact: true });
  assert.equal(await title.inputValue(), OUTLINE_TITLE, 'Outline title did not remain in the editor');
  record('journey', 'Whiteboard Outline persistence complete');
}

async function addWhiteboardPsyke(page) {
  await page.getByRole('button', { name: 'PSYKE', exact: true }).click();
  const panel = await waitVisible(page.locator('aside[aria-label="PSYKE"]'), 'Whiteboard PSYKE panel');
  await panel.getByRole('button', { name: '+ Add', exact: true }).click();
  const form = await waitVisible(panel.locator('form.psyke-create'), 'Whiteboard PSYKE create form');
  await form.locator('select').selectOption('character');
  await form.getByPlaceholder('Name', { exact: true }).fill(PSYKE_NAME);
  await form.getByPlaceholder('Short description', { exact: true }).fill(PSYKE_DESCRIPTION);
  await form.getByPlaceholder('Notes', { exact: true }).fill(PSYKE_NOTES);
  await panel.getByRole('button', { name: 'Save', exact: true }).click();
  await waitText(panel, `Added “${PSYKE_NAME}”.`, 'Whiteboard PSYKE creation');
  record('journey', 'Whiteboard PSYKE creation complete');
}

function assertRevisionToken(value, label) {
  assert.equal(typeof value, 'string', `${label} is not a string`);
  assert.match(value, /^[0-9a-f]{32}$/, `${label} is not a resource revision`);
  return value;
}

function timestampMillis(value, label) {
  assert.equal(typeof value, 'string', `${label} is not a string`);
  const parsed = Date.parse(value);
  assert.ok(Number.isFinite(parsed), `${label} is not a valid timestamp`);
  return parsed;
}

function psykeEtag(incarnation, revision) {
  return `"lfwb:psyke:${incarnation}:${revision}"`;
}

function nextAcceptanceMutationId(label) {
  acceptanceMutationSequence += 1;
  const suffix = label.toLowerCase().replace(/[^a-z0-9._:-]+/g, '-').replace(/^-+|-+$/g, '');
  return `packaged-acceptance-${process.pid}-${acceptanceMutationSequence}-${suffix}`.slice(0, 128);
}

function assertWhiteboardPsykeResponse(result, document, label) {
  assert.ok(result.data && typeof result.data === 'object', `${label} returned no object`);
  const revision = assertRevisionToken(result.data.revision, `${label} revision`);
  assert.equal(
    result.etag,
    psykeEtag(document.incarnation, revision),
    `${label} returned an invalid PSYKE ETag`,
  );
  return revision;
}

async function conditionalWhiteboardPsykeWrite(
  session,
  document,
  revision,
  requestPath,
  body,
  label,
) {
  const result = await localServiceRequest(session, requestPath, {
    method: 'POST',
    headers: {
      'X-LogosForge-Document-Incarnation': document.incarnation,
      'If-Match': psykeEtag(document.incarnation, revision),
      'X-LogosForge-Mutation-Id': nextAcceptanceMutationId(label),
    },
    body,
  });
  const nextRevision = assertWhiteboardPsykeResponse(result, document, label);
  assert.notEqual(nextRevision, revision, `${label} did not advance the aggregate PSYKE revision`);
  return { result, revision: nextRevision };
}

async function addWhiteboardPsykeGraph(session) {
  await waitLocalServiceConnected(session, 'Whiteboard graph setup');
  const documentsResult = await localServiceRequest(session, '/api/documents');
  assert.ok(
    documentsResult.data && Array.isArray(documentsResult.data.documents),
    'Whiteboard document library response is invalid',
  );
  const matches = documentsResult.data.documents.filter((document) => document?.title === PROJECT_TITLE);
  assert.equal(matches.length, 1, `Expected exactly one ${PROJECT_TITLE} Whiteboard document`);
  const document = matches[0];
  assert.match(String(document.id), /^[1-9][0-9]*$/, 'Whiteboard document id is invalid');
  assertRevisionToken(document.incarnation, 'Whiteboard document incarnation');

  const documentQuery = `doc=${encodeURIComponent(document.id)}`;
  const identityHeaders = {
    'X-LogosForge-Document-Incarnation': document.incarnation,
  };
  const initialEntries = await localServiceRequest(
    session,
    `/api/psyke/search?q=&${documentQuery}`,
    { headers: identityHeaders },
  );
  let revision = assertWhiteboardPsykeResponse(
    initialEntries,
    document,
    'Whiteboard initial PSYKE read',
  );
  assert.ok(Array.isArray(initialEntries.data.results), 'Whiteboard PSYKE entry list is invalid');
  assert.equal(initialEntries.data.results.length, 1, 'Whiteboard UI should have created one PSYKE entry');
  const primary = initialEntries.data.results[0];
  assert.equal(primary?.name, PSYKE_NAME, 'Whiteboard wrapper lost the UI-created PSYKE entry');
  const primaryId = Number(primary?.id);
  assert.ok(Number.isSafeInteger(primaryId) && primaryId > 0, 'Whiteboard primary PSYKE id is invalid');

  const secondWrite = await conditionalWhiteboardPsykeWrite(
    session,
    document,
    revision,
    `/api/psyke/elements?${documentQuery}`,
    {
      type: 'character',
      name: PSYKE_SECOND_NAME,
      description: PSYKE_SECOND_DESCRIPTION,
      notes: PSYKE_SECOND_NOTES,
    },
    'create-second-entry',
  );
  revision = secondWrite.revision;
  assert.equal(secondWrite.result.data.ok, true, 'Whiteboard second-entry write was not acknowledged');
  const secondary = secondWrite.result.data.element;
  assert.equal(secondary?.name, PSYKE_SECOND_NAME, 'Whiteboard second-entry receipt has the wrong name');
  assert.equal(secondary?.entry_type, 'character', 'Whiteboard second-entry receipt has the wrong type');
  assert.equal(secondary?.description, PSYKE_SECOND_DESCRIPTION, 'Whiteboard second-entry description changed');
  assert.equal(secondary?.notes, PSYKE_SECOND_NOTES, 'Whiteboard second-entry notes changed');
  const secondaryId = Number(secondary?.id);
  assert.ok(Number.isSafeInteger(secondaryId) && secondaryId > 0, 'Whiteboard secondary PSYKE id is invalid');
  assert.notEqual(secondaryId, primaryId, 'Whiteboard returned the same id for two PSYKE entries');

  const relationWrite = await conditionalWhiteboardPsykeWrite(
    session,
    document,
    revision,
    `/api/psyke/relations?${documentQuery}`,
    { source_id: primaryId, target_id: secondaryId, relation_type: PSYKE_RELATION_TYPE },
    'create-relation',
  );
  revision = relationWrite.revision;
  assert.equal(relationWrite.result.data.ok, true, 'Whiteboard relation write was not acknowledged');
  const relationReceipt = relationWrite.result.data.relation;
  assert.equal(relationReceipt?.source_id, primaryId, 'Whiteboard relation receipt source changed');
  assert.equal(relationReceipt?.target_id, secondaryId, 'Whiteboard relation receipt target changed');
  assert.equal(relationReceipt?.source, PSYKE_NAME, 'Whiteboard relation receipt source name changed');
  assert.equal(relationReceipt?.target, PSYKE_SECOND_NAME, 'Whiteboard relation receipt target name changed');
  assert.equal(
    relationReceipt?.relation_type,
    PSYKE_RELATION_TYPE,
    'Whiteboard relation receipt type changed',
  );

  for (let index = 0; index < PSYKE_PROGRESSION_TEXTS.length; index += 1) {
    const progressionWrite = await conditionalWhiteboardPsykeWrite(
      session,
      document,
      revision,
      `/api/psyke/progressions?${documentQuery}`,
      { entry_id: primaryId, text: PSYKE_PROGRESSION_TEXTS[index], scene_id: null },
      `create-progression-${index + 1}`,
    );
    revision = progressionWrite.revision;
    assert.equal(
      progressionWrite.result.data.ok,
      true,
      `Whiteboard progression ${index + 1} write was not acknowledged`,
    );
  }

  const [entryList, relationList, progressionList] = await Promise.all([
    localServiceRequest(
      session,
      `/api/psyke/search?q=&${documentQuery}`,
      { headers: identityHeaders },
    ),
    localServiceRequest(
      session,
      `/api/psyke/relations?${documentQuery}`,
      { headers: identityHeaders },
    ),
    localServiceRequest(
      session,
      `/api/psyke/progressions?${documentQuery}`,
      { headers: identityHeaders },
    ),
  ]);
  for (const [label, result] of [
    ['Whiteboard final PSYKE entry read', entryList],
    ['Whiteboard final PSYKE relation read', relationList],
    ['Whiteboard final PSYKE progression read', progressionList],
  ]) {
    assert.equal(
      assertWhiteboardPsykeResponse(result, document, label),
      revision,
      `${label} did not observe the final aggregate revision`,
    );
  }

  assert.ok(Array.isArray(entryList.data.results), 'Whiteboard final PSYKE entries are invalid');
  assert.equal(entryList.data.results.length, 2, 'Whiteboard wrapper did not retain exactly two PSYKE entries');
  assert.deepEqual(
    new Set(entryList.data.results.map((entry) => entry.name)),
    new Set([PSYKE_NAME, PSYKE_SECOND_NAME]),
    'Whiteboard wrapper PSYKE names changed',
  );
  assert.ok(Array.isArray(relationList.data.relations), 'Whiteboard PSYKE relations are invalid');
  assert.equal(relationList.data.relations.length, 1, 'Whiteboard wrapper did not retain one relation');
  const relation = relationList.data.relations[0];
  assert.equal(relation?.source_id, primaryId, 'Whiteboard relation source changed');
  assert.equal(relation?.target_id, secondaryId, 'Whiteboard relation target changed');
  assert.equal(relation?.source, PSYKE_NAME, 'Whiteboard relation source name changed');
  assert.equal(relation?.target, PSYKE_SECOND_NAME, 'Whiteboard relation target name changed');
  assert.equal(relation?.relation_type, PSYKE_RELATION_TYPE, 'Whiteboard relation type changed');
  assert.ok(Array.isArray(progressionList.data.progressions), 'Whiteboard PSYKE progressions are invalid');
  const progressions = progressionList.data.progressions.filter((item) => item?.entry_id === primaryId);
  assert.equal(progressions.length, 2, 'Whiteboard wrapper did not retain two primary-entry progressions');
  assert.deepEqual(
    progressions.map((item) => item.text),
    PSYKE_PROGRESSION_TEXTS,
    'Whiteboard wrapper progression order changed',
  );
  assert.deepEqual(
    progressions.map((item) => item.sort_order),
    [1, 2],
    'Whiteboard wrapper progression sort orders changed',
  );
  assert.ok(
    progressions.every((item) => item.scene_id === null && item.scene_title === ''),
    'Whiteboard wrapper unexpectedly anchored a progression to a core scene',
  );
  record('journey', 'Whiteboard authenticated relation/progression setup and wrapper reads verified');
  return {
    documentId: String(document.id),
    incarnation: document.incarnation,
    primaryId,
    secondaryId,
  };
}

async function addWhiteboardComments(session, document, bodyMarker) {
  const documentQuery = `doc=${encodeURIComponent(document.documentId)}`;
  const identityHeaders = {
    'X-LogosForge-Document-Incarnation': document.incarnation,
  };
  const manuscript = await localServiceRequest(
    session,
    `/api/whiteboard?${documentQuery}`,
    { headers: identityHeaders },
  );
  const blocks = manuscript.data?.blocks;
  assert.ok(Array.isArray(blocks), 'Whiteboard manuscript read returned no blocks');
  const bodyIndex = blocks.findIndex((block) => block?.text === bodyMarker);
  const titleIndex = blocks.findIndex(
    (block) => block?.type === 'heading' && block?.text === 'Chapter One',
  );
  assert.ok(bodyIndex >= 0, 'Whiteboard body block is unavailable for comment setup');
  assert.ok(titleIndex >= 0, 'Whiteboard title block is unavailable for comment setup');

  const create = async (blockIndex, quote, body) => {
    const block = blocks[blockIndex];
    const result = await localServiceRequest(session, `/api/comments?${documentQuery}`, {
      method: 'POST',
      headers: identityHeaders,
      body: {
        anchor: {
          block_index: blockIndex,
          block_id: block.id,
          from_offset: 0,
          to_offset: quote.length,
          prefix: '',
          suffix: '',
        },
        quote,
        body,
      },
    });
    assert.match(String(result.data?.id), /^[A-Za-z0-9_-]+$/, 'Whiteboard comment id is invalid');
    return result.data;
  };

  const open = await create(bodyIndex, bodyMarker, OPEN_COMMENT_BODY);
  const replied = await localServiceRequest(
    session,
    `/api/comments/${encodeURIComponent(open.id)}/replies?${documentQuery}`,
    {
      method: 'POST',
      headers: identityHeaders,
      body: { body: OPEN_COMMENT_REPLY, author: 'Acceptance Editor' },
    },
  );
  assert.equal(replied.data?.replies?.length, 1, 'Whiteboard comment reply was not stored');
  assert.equal(replied.data.replies[0]?.body, OPEN_COMMENT_REPLY, 'Whiteboard reply body changed');

  const title = await create(titleIndex, 'Chapter One', RESOLVED_COMMENT_BODY);
  const resolved = await localServiceRequest(
    session,
    `/api/comments/${encodeURIComponent(title.id)}?${documentQuery}`,
    { method: 'PUT', headers: identityHeaders, body: { resolved: true } },
  );
  assert.equal(resolved.data?.resolved, true, 'Whiteboard title comment was not resolved');

  const final = await localServiceRequest(
    session,
    `/api/comments?${documentQuery}`,
    { headers: identityHeaders },
  );
  assert.equal(final.data?.comments?.length, 2, 'Whiteboard did not retain both comment threads');
  record('journey', 'Whiteboard open/resolved comment threads and reply verified');
  return { openId: open.id, resolvedId: title.id };
}

async function configureWhiteboardAi(page) {
  await page.getByRole('button', { name: 'AI provider settings', exact: true }).click();
  const dialog = await waitVisible(page.getByRole('dialog', { name: 'Settings', exact: true }), 'Whiteboard Settings');
  const field = (label) => dialog.locator('label.settings-field').filter({ hasText: new RegExp(`^${label}`) });
  await field('Provider').locator('select').selectOption({ label: 'LM Studio' });
  await field('Base URL').locator('input').fill('http://127.0.0.1:9/v1');
  await field('Model').locator('input').fill('packaged-acceptance-model');
  await field('Timeout \\(s\\)').locator('input').fill('5');
  await dialog.getByRole('button', { name: 'Save', exact: true }).click();
  await waitText(dialog.locator('.settings-status'), 'Saved.', 'Whiteboard AI settings save', { exact: true });
  await assertRealSettingsUnchanged('Whiteboard AI settings save');
  await dialog.getByRole('button', { name: 'Test connection', exact: true }).click();
  await waitText(
    dialog,
    'Connected — LM Studio responded.',
    'Whiteboard controlled-provider connection test',
  );
  await dialog.getByRole('button', { name: 'Close settings', exact: true }).click();
  record('journey', 'Whiteboard AI settings and controlled-provider test complete');
}

async function chatWithWhiteboardBilly(page) {
  const existing = page.locator('[aria-label="Billy chat"]');
  if (!(await existing.isVisible().catch(() => false))) {
    await page.getByRole('button', { name: 'LittleBoy', exact: true }).click();
  }
  const chat = await waitVisible(page.locator('[aria-label="Billy chat"]'), 'Whiteboard Billy chat');
  await chat.getByLabel('Message Billy', { exact: true }).fill('Give me one concrete prose beat for this chapter.');
  await chat.getByRole('button', { name: 'Send', exact: true }).click();
  await waitText(chat.locator('.billy-msg-assistant'), QA_PREFIX, 'Whiteboard deterministic Billy reply');
  record('journey', 'Whiteboard Billy controlled-provider chat complete');
}

function assertBundlePsykeGraph(bundle) {
  const psyke = bundle?.project?.psyke;
  assert.ok(psyke && typeof psyke === 'object', 'Whiteboard bundle has no PSYKE section');
  assert.ok(Array.isArray(psyke.elements), 'Whiteboard bundle has no PSYKE entry list');
  assert.ok(Array.isArray(psyke.relations), 'Whiteboard bundle has no PSYKE relation list');
  assert.ok(Array.isArray(psyke.progressions), 'Whiteboard bundle has no PSYKE progression list');
  assert.equal(psyke.elements.length, 2, 'Whiteboard bundle should contain exactly two PSYKE entries');
  const primary = psyke.elements.find((entry) => entry?.name === PSYKE_NAME);
  const secondary = psyke.elements.find((entry) => entry?.name === PSYKE_SECOND_NAME);
  assert.equal(primary?.entry_type, 'character', 'Whiteboard bundle lost the primary character type');
  assert.equal(primary?.description, PSYKE_DESCRIPTION, 'Whiteboard bundle lost the primary description');
  assert.equal(primary?.notes, PSYKE_NOTES, 'Whiteboard bundle lost the primary notes');
  assert.equal(secondary?.entry_type, 'character', 'Whiteboard bundle lost the secondary character type');
  assert.equal(secondary?.description, PSYKE_SECOND_DESCRIPTION, 'Whiteboard bundle lost the secondary description');
  assert.equal(secondary?.notes, PSYKE_SECOND_NOTES, 'Whiteboard bundle lost the secondary notes');
  const primaryId = Number(primary?.id);
  const secondaryId = Number(secondary?.id);
  assert.ok(Number.isSafeInteger(primaryId) && primaryId > 0, 'Whiteboard bundle primary PSYKE id is invalid');
  assert.ok(Number.isSafeInteger(secondaryId) && secondaryId > 0, 'Whiteboard bundle secondary PSYKE id is invalid');
  assert.notEqual(primaryId, secondaryId, 'Whiteboard bundle collapsed two PSYKE source ids');

  assert.equal(psyke.relations.length, 1, 'Whiteboard bundle should contain exactly one PSYKE relation');
  const relation = psyke.relations[0];
  assert.equal(relation?.source_id, primaryId, 'Whiteboard bundle relation source changed');
  assert.equal(relation?.target_id, secondaryId, 'Whiteboard bundle relation target changed');
  assert.equal(relation?.source, PSYKE_NAME, 'Whiteboard bundle relation source name changed');
  assert.equal(relation?.target, PSYKE_SECOND_NAME, 'Whiteboard bundle relation target name changed');
  assert.equal(relation?.relation_type, PSYKE_RELATION_TYPE, 'Whiteboard bundle relation type changed');

  assert.equal(psyke.progressions.length, 2, 'Whiteboard bundle should contain exactly two progression beats');
  const progressions = psyke.progressions
    .filter((item) => item?.entry_id === primaryId)
    .slice()
    .sort((left, right) => left.sort_order - right.sort_order || left.id - right.id);
  assert.equal(progressions.length, 2, 'Whiteboard bundle progression beats target the wrong source entry');
  assert.deepEqual(
    progressions.map((item) => item.text),
    PSYKE_PROGRESSION_TEXTS,
    'Whiteboard bundle progression text/order changed',
  );
  assert.deepEqual(
    progressions.map((item) => item.sort_order),
    [1, 2],
    'Whiteboard bundle progression sort orders changed',
  );
  assert.ok(
    progressions.every((item) => item.scene_id === null && item.scene_title === ''),
    'Whiteboard bundle unexpectedly contains a progression scene anchor',
  );
  return {
    primaryId,
    secondaryId,
    sourceIds: new Set([primaryId, secondaryId]),
  };
}

function assertBundleComments(bundle, bodyMarker) {
  const comments = bundle?.project?.comments;
  assert.ok(Array.isArray(comments), 'Whiteboard bundle has no comments list');
  assert.equal(comments.length, 2, 'Whiteboard bundle should contain exactly two comment threads');
  const open = comments.find((comment) => comment?.body === OPEN_COMMENT_BODY);
  const resolved = comments.find((comment) => comment?.body === RESOLVED_COMMENT_BODY);
  assert.ok(open, 'Whiteboard bundle lost the open comment thread');
  assert.equal(open.quote, bodyMarker, 'Whiteboard bundle changed the open comment quote');
  assert.equal(open.resolved, false, 'Whiteboard bundle changed the open comment state');
  assert.equal(open.replies?.length, 1, 'Whiteboard bundle lost the comment reply');
  assert.equal(open.replies[0]?.body, OPEN_COMMENT_REPLY, 'Whiteboard bundle changed the reply body');
  assert.equal(open.replies[0]?.author, 'Acceptance Editor', 'Whiteboard bundle changed the reply author');
  assert.equal(resolved?.quote, 'Chapter One', 'Whiteboard bundle changed the title comment quote');
  assert.equal(resolved?.resolved, true, 'Whiteboard bundle changed the resolved comment state');
  assert.match(String(open.id), /^[A-Za-z0-9_-]+$/, 'Whiteboard bundle open-comment id is invalid');
  assert.match(String(resolved.id), /^[A-Za-z0-9_-]+$/, 'Whiteboard bundle resolved-comment id is invalid');
  return { open, resolved };
}

async function exportWhiteboardBundle(session, bundlePath, bodyMarker) {
  const { page } = session;
  const menu = await openWhiteboardFileMenu(page);
  await menu.getByRole('button', { name: 'Export Project (.lfbundle)…', exact: true }).click();
  await waitFile(bundlePath, 'Whiteboard .lfbundle export');
  await waitText(
    page.locator('[role="region"][aria-label="Notifications"]'),
    `Exported ${path.basename(bundlePath)}.`,
    'Whiteboard export notification',
  );
  await assertDialogQueuesDrained(session);

  const bundle = JSON.parse(await fs.readFile(bundlePath, 'utf8'));
  assert.equal(bundle.format, 'logosforge-project-bundle', 'Unexpected Whiteboard bundle format');
  assert.equal(bundle.version, '1.0', 'Unexpected Whiteboard bundle version');
  assert.equal(bundle.project?.title, PROJECT_TITLE, 'Whiteboard bundle title mismatch');
  assert.equal(bundle.project?.mode, 'novel', 'Whiteboard bundle mode mismatch');
  const blocks = bundle.project?.manuscript?.blocks;
  assert.ok(Array.isArray(blocks), 'Whiteboard bundle has no manuscript block list');
  assert.ok(
    blocks.some((block) => block?.type === 'heading' && block?.level === 1 && block?.text === 'Chapter One'),
    'Whiteboard bundle lost the typed Chapter One heading',
  );
  assert.ok(
    blocks.some((block) => block?.type === 'heading' && block?.level === 1 && block?.text === COMMENT_SCENE_TITLE),
    'Whiteboard bundle lost the typed Chapter Two heading',
  );
  assert.ok(blocks.some((block) => block?.text?.includes(bodyMarker)), 'Whiteboard bundle lost the body marker');
  assert.ok(
    bundle.project?.outline?.some((node) => node?.title === OUTLINE_TITLE),
    'Whiteboard bundle lost the Outline item',
  );
  assertBundlePsykeGraph(bundle);
  assertBundleComments(bundle, bodyMarker);
  record('journey', 'Whiteboard .lfbundle parsed and all cross-product data verified');
  return bundle;
}

async function runWhiteboardJourney({ electron, exePath, root, bundlePath, bodyMarker }) {
  const closeDialogMarker = path.join(root, 'whiteboard-1-close-dialog-used.txt');
  const first = await launchPackagedApp({
    electron,
    label: 'whiteboard-1',
    product: 'whiteboard',
    exePath,
    productRoot: root,
    dialogs: {
      message: [{
        response: 1,
        button: "Don't Save",
        message: 'Save changes before closing?',
        markerPath: closeDialogMarker,
      }],
    },
  });
  await createAndEditWhiteboard(first, bodyMarker);
  await captureScreenshot(first, 'before-first-restart');
  await closeSession(first);
  await assertFile(closeDialogMarker, 'Whiteboard dirty-close dialog marker');

  const second = await launchPackagedApp({
    electron,
    label: 'whiteboard-2',
    product: 'whiteboard',
    exePath,
    productRoot: root,
    dialogs: { save: [bundlePath] },
  });
  const editor = await waitWhiteboardReady(second.page);
  await waitText(second.page.locator('button.app-title'), PROJECT_TITLE, 'Whiteboard title after restart', { exact: true });
  await waitText(editor, bodyMarker, 'Whiteboard body after restart');
  await waitVisible(
    editor.getByRole('heading', { name: 'Chapter One', exact: true }),
    'Whiteboard heading after restart',
  );
  await waitVisible(
    editor.getByRole('heading', { name: COMMENT_SCENE_TITLE, exact: true }),
    'Whiteboard second heading after restart',
  );
  await addWhiteboardOutline(second.page);
  await addWhiteboardPsyke(second.page);
  const sourceDocument = await addWhiteboardPsykeGraph(second);
  await addWhiteboardComments(second, sourceDocument, bodyMarker);
  await configureWhiteboardAi(second.page);
  await assertRealSettingsUnchanged('Whiteboard packaged journey');
  await waitFile(
    path.join(second.dirs.home, '.logosforge', 'settings.json'),
    'isolated Whiteboard core settings',
  );
  await chatWithWhiteboardBilly(second.page);
  const bundle = await exportWhiteboardBundle(second, bundlePath, bodyMarker);
  await captureScreenshot(second, 'bundle-exported');
  await closeSession(second);

  await assertFile(path.join(root, 'data', 'whiteboard.db'), 'isolated Whiteboard core DB');
  record('journey', 'Whiteboard graceful restart journey complete');
  return bundle;
}

function proScreen(page, name) {
  return page.locator(`[data-screen-label="${name}"]`);
}

function proProjectSelect(page) {
  // The rail owns three direct field selects in a stable order: project mode,
  // active project, appearance. The implicit label's accessible name includes
  // all option text, so exact getByLabel queries are intentionally avoided.
  return page.locator('aside.rail > label.field > select').nth(1);
}

async function waitProReady(session) {
  const { page } = session;
  const projects = await waitVisible(proScreen(page, 'Projects'), 'Pro Projects screen', STARTUP_TIMEOUT_MS);
  await waitLocalServiceConnected(session, 'Pro bundled core');
  record('ui', 'Pro bundled core connected');
  return projects;
}

async function selectProPanel(page, name, screenName) {
  await page.locator('aside.rail nav').getByRole('button', { name, exact: true }).click();
  return waitVisible(proScreen(page, screenName), `Pro ${screenName} screen`);
}

async function collapseProAiDock(page) {
  const collapse = page.getByRole('button', { name: 'Collapse AI dock', exact: true });
  if (!(await collapse.isVisible().catch(() => false))) return;
  await collapse.click();
  await waitVisible(
    page.getByRole('button', { name: 'Open AI dock', exact: true }),
    'collapsed Pro AI dock strip',
  );
}

async function preseedProPsykeIdSpace(session, bundle) {
  const source = assertBundlePsykeGraph(bundle);
  const maxSourceId = Math.max(source.primaryId, source.secondaryId);
  assert.ok(maxSourceId <= 64, `Unexpectedly large packaged source PSYKE id: ${maxSourceId}`);
  let projects = [];
  await waitFor(async () => {
    const result = await localServiceRequest(session, '/api/projects');
    projects = Array.isArray(result.data) ? result.data : [];
    return projects.length > 0;
  }, 'fresh Pro starter project');
  const activeProjectId = Number(await proProjectSelect(session.page).inputValue());
  const starter = projects.find((project) => project?.id === activeProjectId) ?? projects[0];
  const starterId = Number(starter?.id);
  assert.ok(Number.isSafeInteger(starterId) && starterId > 0, 'Fresh Pro starter project id is invalid');

  let highestSentinelId = 0;
  let sentinels = 0;
  while (highestSentinelId <= maxSourceId) {
    sentinels += 1;
    assert.ok(sentinels <= maxSourceId + 2, 'Could not advance the Pro PSYKE id space safely');
    const result = await localServiceRequest(
      session,
      `/api/projects/${starterId}/psyke/entries`,
      {
        method: 'POST',
        body: {
          name: `Packaged Acceptance ID Sentinel ${process.pid}-${sentinels}`,
          type: 'other',
          notes: 'Acceptance-only id offset in the isolated starter project.',
        },
      },
    );
    const createdId = Number(result.data?.id);
    assert.ok(Number.isSafeInteger(createdId) && createdId > highestSentinelId, 'Pro sentinel id did not advance');
    highestSentinelId = createdId;
  }
  assert.ok(highestSentinelId > maxSourceId, 'Pro destination id space still overlaps source ids');
  record(
    'journey',
    `Pro isolated starter seeded with ${sentinels} PSYKE id sentinel(s); imported ids must exceed ${maxSourceId}`,
  );
}

async function verifyProPsykeApi(session, projectId, bundle, expectedDestination = null) {
  const source = assertBundlePsykeGraph(bundle);
  const [entriesResult, relationsResult, progressionsResult] = await Promise.all([
    localServiceRequest(session, `/api/projects/${projectId}/psyke/entries`),
    localServiceRequest(session, `/api/projects/${projectId}/psyke/relations`),
    localServiceRequest(session, `/api/projects/${projectId}/psyke/progressions`),
  ]);
  assert.ok(Array.isArray(entriesResult.data), 'Pro PSYKE entry response is invalid');
  assert.ok(Array.isArray(relationsResult.data), 'Pro PSYKE relation response is invalid');
  assert.ok(Array.isArray(progressionsResult.data), 'Pro PSYKE progression response is invalid');
  assert.equal(entriesResult.data.length, 2, 'Imported Pro project should contain exactly two PSYKE entries');
  const primary = entriesResult.data.find((entry) => entry?.name === PSYKE_NAME);
  const secondary = entriesResult.data.find((entry) => entry?.name === PSYKE_SECOND_NAME);
  const primaryId = Number(primary?.id);
  const secondaryId = Number(secondary?.id);
  assert.ok(Number.isSafeInteger(primaryId) && primaryId > 0, 'Imported Pro primary id is invalid');
  assert.ok(Number.isSafeInteger(secondaryId) && secondaryId > 0, 'Imported Pro secondary id is invalid');
  assert.notEqual(primaryId, secondaryId, 'Imported Pro entries share an id');
  for (const destinationId of [primaryId, secondaryId]) {
    assert.equal(
      source.sourceIds.has(destinationId),
      false,
      `Imported Pro PSYKE id ${destinationId} reused a source id instead of remapping it`,
    );
  }
  if (expectedDestination) {
    assert.equal(primaryId, expectedDestination.primaryId, 'Primary PSYKE id changed across Pro restart');
    assert.equal(secondaryId, expectedDestination.secondaryId, 'Secondary PSYKE id changed across Pro restart');
  }
  assert.equal(primary?.type, 'character', 'Imported Pro primary entry type changed');
  assert.equal(primary?.notes, PSYKE_NOTES, 'Imported Pro primary notes changed');
  assert.equal(primary?.details?.description, PSYKE_DESCRIPTION, 'Imported Pro primary description changed');
  assert.equal(secondary?.type, 'character', 'Imported Pro secondary entry type changed');
  assert.equal(secondary?.notes, PSYKE_SECOND_NOTES, 'Imported Pro secondary notes changed');
  assert.equal(
    secondary?.details?.description,
    PSYKE_SECOND_DESCRIPTION,
    'Imported Pro secondary description changed',
  );

  assert.equal(relationsResult.data.length, 1, 'Imported Pro project should contain one PSYKE relation');
  const relation = relationsResult.data[0];
  assert.equal(relation?.source_id, primaryId, 'Imported Pro relation source was not remapped');
  assert.equal(relation?.target_id, secondaryId, 'Imported Pro relation target was not remapped');
  assert.equal(relation?.source, PSYKE_NAME, 'Imported Pro relation source name changed');
  assert.equal(relation?.target, PSYKE_SECOND_NAME, 'Imported Pro relation target name changed');
  assert.equal(relation?.relation_type, PSYKE_RELATION_TYPE, 'Imported Pro relation type changed');

  assert.equal(progressionsResult.data.length, 2, 'Imported Pro project should contain two progression beats');
  const progressions = progressionsResult.data
    .slice()
    .sort((left, right) => left.sort_order - right.sort_order || left.id - right.id);
  assert.ok(
    progressions.every((item) => item.entry_id === primaryId),
    'Imported Pro progressions did not target the remapped primary entry',
  );
  assert.deepEqual(
    progressions.map((item) => item.text),
    PSYKE_PROGRESSION_TEXTS,
    'Imported Pro progression text/order changed',
  );
  assert.deepEqual(
    progressions.map((item) => item.sort_order),
    [1, 2],
    'Imported Pro progression sort orders changed',
  );
  assert.ok(
    progressions.every((item) => item.scene_id === null && item.scene_title === ''),
    'Imported Pro progression unexpectedly gained a scene anchor',
  );
  record('journey', `Pro API verified remapped PSYKE graph for project ${projectId}`);
  return { projectId, primaryId, secondaryId };
}

async function verifyProCommentsApi(session, projectId, bundle, bodyMarker, expectedDestination = null) {
  const source = assertBundleComments(bundle, bodyMarker);
  const result = await localServiceRequest(session, `/api/projects/${projectId}/comments`);
  assert.ok(Array.isArray(result.data), 'Pro comments response is invalid');
  assert.equal(result.data.length, 2, 'Imported Pro project should contain two comment threads');
  const open = result.data.find((comment) => comment?.source_id === source.open.id);
  const resolved = result.data.find((comment) => comment?.source_id === source.resolved.id);
  assert.ok(open, 'Pro comments lost the open Whiteboard thread provenance');
  assert.ok(resolved, 'Pro comments lost the resolved Whiteboard thread provenance');
  assert.equal(open.quote, bodyMarker, 'Pro changed the open comment quote');
  assert.equal(open.body, OPEN_COMMENT_BODY, 'Pro changed the open comment body');
  assert.equal(open.resolved, false, 'Pro changed the open comment state');
  assert.equal(open.replies?.length, 1, 'Pro lost the imported comment reply');
  assert.equal(open.replies[0]?.source_id, source.open.replies[0].id, 'Pro lost reply provenance');
  assert.equal(open.replies[0]?.body, OPEN_COMMENT_REPLY, 'Pro changed the reply body');
  assert.equal(open.replies[0]?.author, 'Acceptance Editor', 'Pro changed the reply author');
  assert.equal(
    timestampMillis(open.replies[0]?.created_at, 'Pro reply created_at'),
    timestampMillis(source.open.replies[0]?.created_at, 'Whiteboard reply created_at'),
    'Pro changed the reply timestamp',
  );
  assert.equal(open.anchor?.start_field, 'content', 'Pro mapped the body comment to the wrong field');
  assert.equal(open.anchor?.end_field, 'content', 'Pro mapped the body comment end to the wrong field');
  assert.equal(open.anchor?.start_scene_id, open.anchor?.end_scene_id, 'Pro split a single-block body comment across scenes');
  assert.equal(open.anchor?.from_offset, 0, 'Pro changed the body comment start offset');
  assert.equal(open.anchor?.to_offset, bodyMarker.length, 'Pro changed the body comment end offset');

  assert.equal(resolved.quote, 'Chapter One', 'Pro changed the title comment quote');
  assert.equal(resolved.body, RESOLVED_COMMENT_BODY, 'Pro changed the title comment body');
  assert.equal(resolved.resolved, true, 'Pro changed the resolved comment state');
  assert.equal(resolved.anchor?.start_field, 'title', 'Pro mapped the title comment to the wrong field');
  assert.equal(resolved.anchor?.end_field, 'title', 'Pro mapped the title comment end to the wrong field');
  assert.equal(resolved.anchor?.from_offset, 0, 'Pro changed the title comment start offset');
  assert.equal(resolved.anchor?.to_offset, 'Chapter One'.length, 'Pro changed the title comment end offset');
  assert.equal(
    resolved.anchor?.start_scene_id,
    resolved.anchor?.end_scene_id,
    'Pro split the single-block title comment across scenes',
  );
  assert.notEqual(
    resolved.anchor?.start_scene_id,
    open.anchor?.start_scene_id,
    'Packaged navigation fixture did not place the body comment in a distinct scene',
  );

  for (const [thread, sourceThread] of [[open, source.open], [resolved, source.resolved]]) {
    assert.ok(Number.isSafeInteger(thread.id) && thread.id > 0, 'Pro comment id is invalid');
    assert.match(thread.created_at, /^\d{4}-\d{2}-\d{2}T/, 'Pro comment created_at is invalid');
    assert.match(thread.updated_at, /^\d{4}-\d{2}-\d{2}T/, 'Pro comment updated_at is invalid');
    assert.equal(
      timestampMillis(thread.created_at, 'Pro comment created_at'),
      timestampMillis(sourceThread.created_at, 'Whiteboard comment created_at'),
      'Pro changed a comment creation timestamp',
    );
    if (!expectedDestination) {
      assert.equal(
        timestampMillis(thread.updated_at, 'Pro comment updated_at'),
        timestampMillis(sourceThread.updated_at, 'Whiteboard comment updated_at'),
        'Pro changed an imported comment update timestamp',
      );
    }
  }
  if (expectedDestination) {
    assert.equal(open.id, expectedDestination.openCommentId, 'Open comment id changed across Pro restart');
    assert.equal(resolved.id, expectedDestination.resolvedCommentId, 'Resolved comment id changed across Pro restart');
  }
  record('journey', `Pro API verified migrated comment threads for project ${projectId}`);
  return {
    openCommentId: open.id,
    resolvedCommentId: resolved.id,
    openCommentSceneId: open.anchor.start_scene_id,
  };
}

async function verifyProPsykeUi(page) {
  const psyke = await selectProPanel(page, 'PSYKE', 'PSYKE Bible');
  const search = await waitVisible(
    psyke.getByLabel('Search PSYKE names and aliases', { exact: true }),
    'Pro PSYKE search',
  );
  await search.fill(PSYKE_NAME);
  await waitText(psyke, PSYKE_NAME, 'Pro imported PSYKE character');
  await psyke.locator('button').filter({ hasText: PSYKE_NAME }).first().click();
  await waitText(psyke, PSYKE_NOTES, 'Pro imported PSYKE notes');
  await psyke.getByRole('button', { name: 'DETAILS', exact: true }).click();
  await waitText(psyke, PSYKE_DESCRIPTION, 'Pro imported PSYKE description');

  const relationsTab = await waitVisible(
    psyke.getByRole('button', { name: /^RELATIONS\s+1$/ }),
    'Pro PSYKE relation tab count',
  );
  await relationsTab.click();
  await waitText(psyke, PSYKE_SECOND_NAME, 'Pro visible remapped PSYKE relation endpoint');
  await waitText(psyke, PSYKE_RELATION_TYPE, 'Pro visible PSYKE relation type');

  const progressionsTab = await waitVisible(
    psyke.getByRole('button', { name: /^PROGRESSIONS\s+2$/ }),
    'Pro PSYKE progression tab count',
  );
  await progressionsTab.click();
  for (let index = 0; index < PSYKE_PROGRESSION_TEXTS.length; index += 1) {
    await waitText(
      psyke,
      PSYKE_PROGRESSION_TEXTS[index],
      `Pro visible progression beat ${index + 1}`,
    );
  }
  await search.fill('');
  record('journey', 'Pro PSYKE relation/progression UI verified');
}

async function verifyProCommentsUi(
  page,
  bodyMarker,
  { exerciseWrites = false, expectedSceneId = null } = {},
) {
  const comments = await selectProPanel(page, 'Comments', 'Comments Panel');
  const openThread = comments.getByRole('button', { name: `Open comment on “${bodyMarker}”`, exact: true });
  await waitVisible(openThread, 'Pro open imported comment thread');
  await openThread.click();
  await waitText(comments, OPEN_COMMENT_BODY, 'Pro imported open comment body');
  await waitText(comments, OPEN_COMMENT_REPLY, 'Pro imported comment reply');
  await waitText(comments, 'Acceptance Editor', 'Pro imported comment reply author');

  if (exerciseWrites) {
    const resolve = comments.getByRole('button', { name: 'Resolve comment', exact: true });
    await waitVisible(resolve, 'Pro resolve-comment action');
    await resolve.click();
    const reopen = comments.getByRole('button', { name: 'Reopen comment', exact: true });
    await waitVisible(reopen, 'Pro comment resolved state');
    await reopen.click();
    await waitVisible(resolve, 'Pro comment reopened state');

    const resolvedThread = comments.getByRole('button', { name: 'Open comment on “Chapter One”', exact: true });
    await resolvedThread.click();
    await waitText(comments, RESOLVED_COMMENT_BODY, 'Pro imported resolved comment body');
    await waitVisible(reopen, 'Pro imported resolved state');
    await reopen.click();
    await waitVisible(resolve, 'Pro title comment reopened state');
    await resolve.click();
    await waitVisible(reopen, 'Pro title comment restored resolved state');
  }

  await openThread.click();
  const openScene = comments.getByRole('button', { name: /^Open .+ in Manuscript$/ }).first();
  await waitVisible(openScene, 'Pro comment scene navigation');
  await openScene.click();
  const manuscript = await waitVisible(proScreen(page, 'Manuscript Editor'), 'Pro Manuscript after comment navigation');
  await waitText(manuscript, bodyMarker, 'comment-anchored Pro scene');
  assert.ok(Number.isSafeInteger(expectedSceneId) && expectedSceneId > 0, 'Expected comment scene id is invalid');
  const targetScene = manuscript.locator(`#ms-scene-${expectedSceneId}`);
  await waitFor(
    async () => (await targetScene.getAttribute('data-scene-prose')) === 'live',
    'comment-targeted Pro scene to become the active live editor',
  );
  // Activating a virtualized scene commits the live editor first, then the
  // navigation jump focuses it on the following short timer.  Wait for that
  // user-visible outcome instead of racing the two intentional commits.
  await waitFor(
    async () => targetScene.locator('[data-prose]').evaluate(
      (element) => element === document.activeElement,
    ),
    'comment navigation to focus the anchored scene editor',
  );
  record('journey', 'Pro Comments panel threads, state changes, and scene navigation verified');
}

async function importAndVerifyInPro(session, bundlePath, bundle, bodyMarker) {
  const { page } = session;
  const projects = await waitProReady(session);
  await preseedProPsykeIdSpace(session, bundle);
  await projects.getByRole('button', { name: /IMPORT PROJECT/ }).click();
  const projectSelect = proProjectSelect(page);
  await waitFor(
    async () => (await projectSelect.locator('option:checked').textContent())?.trim() === PROJECT_TITLE,
    'Pro project-bundle import and imported-project selection',
    60_000,
  );
  assert.equal(await projectSelect.inputValue() !== '', true, 'Pro imported project has no selected id');
  const projectId = Number(await projectSelect.inputValue());
  assert.ok(Number.isSafeInteger(projectId) && projectId > 0, 'Pro imported project id is invalid');
  const importReport = projects.locator('div').filter({
    hasText: new RegExp(`^✓ Imported “${PROJECT_TITLE}”`),
  }).last();
  await waitText(importReport, '2 bible entries', 'Pro import report bible-entry count');
  await waitText(importReport, '1 bible relationship', 'Pro import report relationship count');
  await waitText(importReport, '2 progression beats', 'Pro import report progression count');
  await waitText(importReport, '2 comment threads', 'Pro import report comment count');
  await waitText(importReport, '1 comment reply', 'Pro import report comment-reply count');
  const reportText = (await importReport.textContent()) ?? '';
  assert.ok(
    !reportText.includes('progression scene link') && !reportText.includes('progression scene anchor'),
    'Pro import report unexpectedly claimed a progression scene link',
  );
  const destination = await verifyProPsykeApi(session, projectId, bundle);
  const commentDestination = await verifyProCommentsApi(session, projectId, bundle, bodyMarker);

  // GitHub's hosted Windows desktop is limited to a 1024px-wide work area.
  // Collapse the dock so the manuscript editor is exercised at that supported width.
  await collapseProAiDock(page);
  const manuscript = await selectProPanel(page, 'Manuscript', 'Manuscript Editor');
  await waitText(manuscript, bodyMarker, 'Pro imported manuscript marker');
  const firstTitle = await waitVisible(manuscript.getByLabel('Scene 1 title', { exact: true }), 'Pro first scene title');
  assert.equal(await firstTitle.inputValue(), 'Chapter One', 'Pro did not convert the Whiteboard heading into Scene 1');

  const outline = await selectProPanel(page, 'Outline', 'Outline Panel');
  await waitText(outline, OUTLINE_TITLE, 'Pro imported Outline item');

  await verifyProPsykeUi(page);
  await verifyProCommentsUi(page, bodyMarker, {
    exerciseWrites: true,
    expectedSceneId: commentDestination.openCommentSceneId,
  });
  const dialogState = await dialogQueueState(session);
  assert.equal(dialogState.open, 0, 'Pro did not consume the queued bundle-import path');
  assert.equal(dialogState.usedOpen.length, 1, 'Pro consumed an unexpected number of open-dialog paths');
  assert.equal(dialogState.save, 1, 'Pro consumed the Markdown save path before export');
  record('journey', `Pro imported and verified ${bundlePath}`);
  return { ...destination, ...commentDestination };
}

async function configureProAiAndChat(page) {
  const settings = await selectProPanel(page, 'AI Settings', 'AI Settings');
  await settings.getByLabel('AI provider', { exact: true }).selectOption({ label: 'LM Studio' });
  await settings.getByLabel('AI provider base URL', { exact: true }).fill('http://127.0.0.1:9/v1');
  await settings.getByLabel('AI model', { exact: true }).fill('packaged-acceptance-model');
  await settings.getByLabel('AI request timeout in seconds', { exact: true }).fill('5');
  await settings.getByRole('button', { name: 'SAVE', exact: true }).click();
  await waitText(
    settings,
    'Saved. Billy, Logos, Counterpart and voice-Billy now use this model.',
    'Pro AI settings save',
  );
  await assertRealSettingsUnchanged('Pro AI settings save');

  const billy = page.locator('[data-screen-label="Billy Assistant"]');
  if (!(await billy.isVisible().catch(() => false))) {
    const openBilly = page.getByRole('button', { name: 'Open Billy', exact: true });
    if (await openBilly.isVisible().catch(() => false)) await openBilly.click();
    else await page.locator('aside.ai-dock .ai-tabs button[title="Billy"]').click();
  }
  await waitVisible(billy, 'Pro Billy Assistant');
  await billy.getByLabel('Message Billy', { exact: true }).fill('Give me one concrete prose beat for this chapter.');
  await billy.getByRole('button', { name: 'SEND', exact: true }).click();
  await waitText(billy, QA_PREFIX, 'Pro deterministic Billy reply');
  record('journey', 'Pro AI settings and controlled-provider chat complete');
}

async function editProManuscript(page, bodyMarker, proMarker) {
  // The Billy exercise opens the dock again before this edit step.
  await collapseProAiDock(page);
  const manuscript = await selectProPanel(page, 'Manuscript', 'Manuscript Editor');
  await waitText(manuscript, bodyMarker, 'Pro manuscript before edit');
  const firstScene = manuscript.locator('[data-scene-id]').first();
  await waitVisible(firstScene, 'Pro first scene');
  await firstScene.scrollIntoViewIfNeeded();

  let editor = firstScene.locator('[data-prose][contenteditable="true"]');
  if (!(await editor.isVisible().catch(() => false))) {
    const staticProse = await waitVisible(firstScene.locator('[data-prose-static]'), 'Pro static prose');
    await staticProse.click();
    editor = await waitVisible(firstScene.locator('[data-prose][contenteditable="true"]'), 'Pro live prose editor');
  }
  await editor.click();
  await page.keyboard.press('Control+End');
  await page.keyboard.press('Enter');
  await page.keyboard.type(proMarker);
  await waitText(editor, proMarker, 'typed Pro manuscript marker');
  await waitFor(async () => {
    const text = (await manuscript.textContent()) ?? '';
    return text.includes('UNSAVED') || text.includes('SAVING…');
  }, 'Pro manuscript dirty/saving transition', 10_000);
  await waitText(manuscript, 'ALL SAVED', 'Pro manuscript autosave', { timeoutMs: UI_TIMEOUT_MS });
  record('journey', 'Pro manuscript keyboard edit/autosave complete');
}

async function exportProMarkdown(session, outputPath, bodyMarker, proMarker) {
  const panel = await selectProPanel(session.page, 'Export', 'Export Studio');
  await panel.getByRole('button', { name: 'EXPORT', exact: true }).click();
  await waitText(panel, 'DONE', 'Pro Markdown export generation');
  const save = panel.getByRole('button', { name: /SAVE$/ });
  await waitFor(async () => (await save.isEnabled().catch(() => false)), 'Pro export SAVE to become enabled');
  await save.click();
  await waitFile(outputPath, 'Pro Markdown disk export');
  await waitText(panel, `saved · ${outputPath}`, 'Pro Markdown save confirmation');
  await assertDialogQueuesDrained(session);

  const markdown = await fs.readFile(outputPath, 'utf8');
  assert.ok(markdown.includes(PROJECT_TITLE), 'Pro Markdown export lost the project title');
  assert.ok(markdown.includes('Chapter One'), 'Pro Markdown export lost the scene title');
  assert.ok(markdown.includes(bodyMarker), 'Pro Markdown export lost the Whiteboard body marker');
  assert.ok(markdown.includes(proMarker), 'Pro Markdown export lost the Pro edit marker');
  record('journey', 'Pro Markdown export written and verified');
}

async function verifyProRestart(session, bundle, expectedDestination, bodyMarker, proMarker) {
  const { page } = session;
  await waitProReady(session);
  const projectSelect = proProjectSelect(page);
  await waitFor(
    async () => (await projectSelect.locator('option').allTextContents()).some((title) => title.trim() === PROJECT_TITLE),
    'imported Pro project option after restart',
  );
  await projectSelect.selectOption({ label: PROJECT_TITLE });
  await waitFor(
    async () => (await projectSelect.locator('option:checked').textContent())?.trim() === PROJECT_TITLE,
    'imported Pro project to become active after restart',
  );
  assert.equal(
    Number(await projectSelect.inputValue()),
    expectedDestination.projectId,
    'A different Pro project id was selected after restart',
  );
  const manuscript = await selectProPanel(page, 'Manuscript', 'Manuscript Editor');
  await waitText(manuscript, bodyMarker, 'Whiteboard marker after Pro restart');
  await waitText(manuscript, proMarker, 'Pro marker after Pro restart');
  assert.equal(
    await manuscript.getByLabel('Scene 1 title', { exact: true }).inputValue(),
    'Chapter One',
    'Pro scene title changed across restart',
  );
  await verifyProPsykeApi(
    session,
    expectedDestination.projectId,
    bundle,
    expectedDestination,
  );
  await verifyProCommentsApi(
    session,
    expectedDestination.projectId,
    bundle,
    bodyMarker,
    expectedDestination,
  );
  await verifyProPsykeUi(page);
  await verifyProCommentsUi(page, bodyMarker, {
    expectedSceneId: expectedDestination.openCommentSceneId,
  });
  record('journey', 'Pro graceful restart persistence verified');
}

async function runProJourney({ electron, exePath, root, bundlePath, bundle, markdownPath, bodyMarker, proMarker }) {
  const first = await launchPackagedApp({
    electron,
    label: 'pro-1',
    product: 'pro',
    exePath,
    productRoot: root,
    dialogs: { open: [bundlePath], save: [markdownPath] },
  });
  const expectedDestination = await importAndVerifyInPro(first, bundlePath, bundle, bodyMarker);
  await configureProAiAndChat(first.page);
  await assertRealSettingsUnchanged('Pro packaged journey');
  await waitFile(
    path.join(first.dirs.home, '.logosforge', 'settings.json'),
    'isolated Pro core settings',
  );
  await editProManuscript(first.page, bodyMarker, proMarker);
  await exportProMarkdown(first, markdownPath, bodyMarker, proMarker);
  await captureScreenshot(first, 'markdown-exported');
  const proDbPath = path.join(first.runtime.userData, 'logosforge.db');
  await closeSession(first);
  await assertFile(proDbPath, 'isolated Pro project DB');

  const second = await launchPackagedApp({
    electron,
    label: 'pro-2',
    product: 'pro',
    exePath,
    productRoot: root,
    dialogs: {},
  });
  await verifyProRestart(second, bundle, expectedDestination, bodyMarker, proMarker);
  await captureScreenshot(second, 'restart-persistence');
  await closeSession(second);
  record('journey', 'Pro import/edit/export/graceful-restart journey complete');
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

async function removeSuccessfulTempRoot(root) {
  const resolvedRoot = path.resolve(root);
  assert.ok(validatedRemovalRoot, 'No validated packaged-acceptance root is available for removal.');
  assertSamePath(resolvedRoot, validatedRemovalRoot, 'packaged-acceptance cleanup root');
  const stat = await fs.lstat(resolvedRoot);
  assert.ok(stat.isDirectory() && !stat.isSymbolicLink(), `Refusing to remove a non-directory or symlink: ${resolvedRoot}`);
  const filesystemRoot = path.parse(resolvedRoot).root;
  assert.notEqual(windowsPathKey(resolvedRoot), windowsPathKey(filesystemRoot), `Refusing to remove filesystem root: ${resolvedRoot}`);
  const canonicalRepo = await fs.realpath(REPO_ROOT);
  assert.notEqual(windowsPathKey(resolvedRoot), windowsPathKey(canonicalRepo), `Refusing to remove workspace root: ${resolvedRoot}`);
  assert.ok(!isSameOrInside(canonicalRepo, resolvedRoot), `Refusing to remove an ancestor of the workspace: ${resolvedRoot}`);
  if (!rootCameFromOverride) {
    const canonicalTempParent = await fs.realpath(os.tmpdir());
    assertSamePath(
      path.dirname(resolvedRoot),
      canonicalTempParent,
      `default packaged-acceptance temp parent for ${resolvedRoot}`,
    );
    assert.ok(
      path.basename(resolvedRoot).startsWith('logosforge-packaged-acceptance-'),
      `Refusing to remove default temp path without the acceptance prefix: ${resolvedRoot}`,
    );
  }
  await fs.rm(resolvedRoot, { recursive: true, force: true });
}

async function loadElectronDriver() {
  try {
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
    record(
      'harness',
      `playwright-core ${packageJson.version ?? 'unknown'} Electron loader: ${loaderPath}`,
    );
    return { electron: module._electron, loaderPath };
  } catch (error) {
    throw new Error(
      'playwright-core is required to run packaged acceptance. Install the pinned test dependency before running this script. ' +
      `(${errorText(error)})`,
    );
  }
}

async function main() {
  assert.equal(process.platform, 'win32', 'Packaged acceptance must run on Windows.');
  await initializeRealSettingsGuard();
  const driver = await loadElectronDriver();
  const electron = driver.electron;
  playwrightElectronLoader = driver.loaderPath;
  const whiteboardExe = await canonicalFile(
    DEFAULT_WHITEBOARD_EXE,
    'LOGOSFORGE_WHITEBOARD_ACCEPTANCE_EXE',
  );
  const proExe = await canonicalFile(DEFAULT_PRO_EXE, 'LOGOSFORGE_PRO_ACCEPTANCE_EXE');

  tempRoot = await createIsolationRoot();
  diagnosticsDir = path.join(tempRoot, 'diagnostics');
  const transfersDir = path.join(tempRoot, 'transfers');
  const whiteboardRoot = path.join(tempRoot, 'whiteboard');
  const proRoot = path.join(tempRoot, 'pro');
  await Promise.all([
    fs.mkdir(diagnosticsDir, { recursive: true }),
    fs.mkdir(transfersDir, { recursive: true }),
    fs.mkdir(whiteboardRoot, { recursive: true }),
    fs.mkdir(proRoot, { recursive: true }),
  ]);

  const token = `${Date.now()}-${process.pid}`;
  const bodyMarker = `Whiteboard packaged marker ${token}.`;
  const proMarker = `Pro packaged marker ${token}.`;
  const bundlePath = path.join(transfersDir, 'packaged-acceptance.lfbundle');
  const markdownPath = path.join(transfersDir, 'packaged-acceptance-pro.md');
  const metadata = {
    startedAt: now(),
    tempRoot,
    whiteboardExe,
    proExe,
    bundlePath,
    markdownPath,
    bodyMarker,
    proMarker,
  };
  record('harness', `temporary isolation root: ${tempRoot}`);

  let succeeded = false;
  try {
    const bundle = await runWhiteboardJourney({
      electron,
      exePath: whiteboardExe,
      root: whiteboardRoot,
      bundlePath,
      bodyMarker,
    });
    await runProJourney({
      electron,
      exePath: proExe,
      root: proRoot,
      bundlePath,
      bundle,
      markdownPath,
      bodyMarker,
      proMarker,
    });
    await assertRealSettingsUnchanged('completed packaged acceptance');
    succeeded = true;
    record('harness', 'PASS: packaged Whiteboard -> Pro writer journey completed');
  } catch (error) {
    record('harness', `FAIL: ${errorText(error)}`);
    for (const session of [...activeSessions]) {
      await captureScreenshot(session, 'failure');
    }
    for (const session of [...activeSessions]) {
      try {
        await closeSession(session, { requireGraceful: false, timeoutMs: 5_000 });
      } catch (cleanupError) {
        record('cleanup', `${session.label}: ${errorText(cleanupError)}`);
      }
    }
    let reportedError = error;
    try {
      await assertRealSettingsUnchanged('failed packaged acceptance cleanup');
    } catch (guardError) {
      record('guard', `FAIL after cleanup: ${errorText(guardError)}`);
      reportedError = new AggregateError(
        [error, guardError],
        `Packaged acceptance failed and the real settings guard also failed: ${errorText(error)}`,
      );
    }
    await writeFailureDiagnostics(reportedError, metadata);
    console.error(`Packaged acceptance failed. Diagnostics preserved at ${diagnosticsDir}`);
    throw reportedError;
  } finally {
    if (succeeded) {
      await removeSuccessfulTempRoot(tempRoot);
      console.log('Packaged acceptance passed; the exact temporary isolation root was removed.');
    }
  }
}

main().catch((error) => {
  console.error(errorText(error));
  process.exitCode = 1;
});
