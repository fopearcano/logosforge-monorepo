/**
 * Core manager — owns the lifecycle of the logosforge core HTTP API.
 *
 *  - Reuse only a core carrying this manager's one-time nonce, or
 *  - spawn `python -m logosforge.api --mode desktop` from the core's venv,
 *  - wait for GET /api/health,
 *  - report status to the renderer,
 *  - stop the core on app close — but only if this process launched it.
 *
 * The core IS the backend: pro-desktop talks to it directly via the HTTP
 * ApiClient (createHttpApiClient). There is no separate FastAPI layer.
 */

import { spawn, type ChildProcess } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import * as fs from 'node:fs';
import * as http from 'node:http';
import * as os from 'node:os';
import * as path from 'node:path';

import { removeRuntimeDescriptor, writeRuntimeDescriptor } from './mcp-runtime';
import { selectAvailablePort } from './port-selection';
import { isExpectedCoreHealth, resolveCoreHost } from './security';

export type CoreState = 'connecting' | 'connected' | 'error';

export interface CoreStatus {
  state: CoreState;
  baseUrl: string;
  managed: boolean;
  detail?: string;
  /** Per-process secret used only by renderer → local core requests. */
  authToken?: string;
}

const RAW_PORT = process.env.LOGOSFORGE_PORT;
const INITIAL_PORT = Number(RAW_PORT ?? 8765);
const PORT_WAS_EXPLICIT = typeof RAW_PORT === 'string' && RAW_PORT.trim().length > 0;
const HEALTH_RESPONSE_MAX_BYTES = 64 * 1024;
const LIVE_CONTEXT_RESPONSE_MAX_BYTES = 64 * 1024;
const LIVE_CONTEXT_TIMEOUT_MS = 1500;
export const LIVE_CONTEXT_SELECTION_MAX_CHARS = 20_000;
export const LIVE_CONTEXT_LABEL_MAX_CHARS = 128;

const delay = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/** Resolve the manager's actual bind address; wildcard listeners use loopback. */
export function liveContextEndpoint(baseUrl: string): string {
  const target = new URL('/api/live-context', baseUrl);
  if (target.hostname === '0.0.0.0' || target.hostname === '[::]') {
    target.hostname = '127.0.0.1';
  }
  return target.toString();
}

/** Read and decode one small JSON health response. */
function httpGetJson(url: string, timeoutMs = 1500): Promise<unknown> {
  return new Promise((resolve) => {
    const req = http.get(url, (res) => {
      if (res.statusCode !== 200) {
        res.resume();
        resolve(null);
        return;
      }
      let body = '';
      res.setEncoding('utf8');
      res.on('data', (chunk) => {
        body += chunk;
        if (body.length > HEALTH_RESPONSE_MAX_BYTES) {
          res.destroy();
          resolve(null);
        }
      });
      res.on('end', () => {
        try { resolve(JSON.parse(body)); }
        catch { resolve(null); }
      });
    });
    req.setTimeout(timeoutMs, () => req.destroy());
    req.on('error', () => resolve(null));
    req.on('timeout', () => resolve(null));
  });
}

interface JsonPutResult {
  statusCode: number;
  body: unknown;
}

/** Send one bounded authenticated JSON update to the local desktop core. */
function httpPutJson(
  url: string,
  authToken: string,
  liveContextToken: string,
  value: unknown,
  timeoutMs = LIVE_CONTEXT_TIMEOUT_MS,
): Promise<JsonPutResult> {
  return new Promise((resolve, reject) => {
    const encoded = JSON.stringify(value);
    const target = new URL(url);
    let settled = false;
    const finish = (error: Error | null, result?: JsonPutResult) => {
      if (settled) return;
      settled = true;
      if (error) reject(error);
      else resolve(result!);
    };
    const req = http.request({
      protocol: target.protocol,
      hostname: target.hostname,
      port: target.port,
      path: `${target.pathname}${target.search}`,
      method: 'PUT',
      headers: {
        Accept: 'application/json',
        Authorization: `Bearer ${authToken}`,
        'X-LogosForge-Live-Context': liveContextToken,
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(encoded),
      },
    }, (res) => {
      const chunks: Buffer[] = [];
      let byteLength = 0;
      res.on('data', (chunk: Buffer | string) => {
        const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
        byteLength += bytes.length;
        if (byteLength > LIVE_CONTEXT_RESPONSE_MAX_BYTES) {
          res.destroy();
          finish(new Error('The core returned an oversized live-context response.'));
          return;
        }
        chunks.push(bytes);
      });
      res.on('end', () => {
        const text = Buffer.concat(chunks).toString('utf8');
        let body: unknown = null;
        if (text) {
          try {
            body = JSON.parse(text);
          } catch {
            finish(new Error('The core returned an invalid live-context response.'));
            return;
          }
        }
        finish(null, { statusCode: res.statusCode ?? 0, body });
      });
      res.on('error', (error) => finish(error));
    });
    req.setTimeout(timeoutMs, () => {
      req.destroy(new Error('The live-context update timed out.'));
    });
    req.on('error', (error) => finish(error));
    req.end(encoded);
  });
}

export interface RendererLiveContextPayload {
  projectId: number | null;
  activePanelId: string | null;
  activeSceneId: number | null;
  selectionSection: string | null;
  selection: string;
}

interface CoreLiveContextPayload {
  source_id: string;
  revision: number;
  project_id: number | null;
  active_panel_id: string | null;
  active_scene_id: number | null;
  selection_section: string | null;
  selection: string;
}

interface LiveContextQueueWaiter {
  resolve: () => void;
  reject: (error: unknown) => void;
}

interface LiveContextQueueEntry {
  payload: CoreLiveContextPayload;
  waiters: LiveContextQueueWaiter[];
}

function nullablePositiveId(value: unknown, name: string): number | null {
  if (value === null) return null;
  if (!Number.isSafeInteger(value) || (value as number) < 1) {
    throw new Error(`${name} must be a positive integer or null.`);
  }
  return value as number;
}

function truncateCodePoints(value: string, limit: number): string {
  if (value.length <= limit) return value;
  return Array.from(value).slice(0, limit).join('');
}

function nullableLabel(value: unknown, name: string): string | null {
  if (value === null) return null;
  if (typeof value !== 'string') throw new Error(`${name} must be a string or null.`);
  const normalized = value.trim();
  if (!normalized) return null;
  return truncateCodePoints(normalized, LIVE_CONTEXT_LABEL_MAX_CHARS);
}

/** Validate the narrow renderer-owned part of a live-context update. */
export function normalizeRendererLiveContext(value: unknown): RendererLiveContextPayload {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Live context must be an object.');
  }
  const input = value as Record<string, unknown>;
  if (typeof input.selection !== 'string') {
    throw new Error('selection must be a string.');
  }
  if (input.projectId === null) {
    return {
      projectId: null,
      activePanelId: null,
      activeSceneId: null,
      selectionSection: null,
      selection: '',
    };
  }
  if (!Number.isSafeInteger(input.projectId) || (input.projectId as number) < 1) {
    throw new Error('projectId must be a positive integer or null.');
  }
  return {
    projectId: input.projectId as number,
    activePanelId: nullableLabel(input.activePanelId, 'activePanelId'),
    activeSceneId: nullablePositiveId(input.activeSceneId, 'activeSceneId'),
    selectionSection: nullableLabel(input.selectionSection, 'selectionSection'),
    selection: truncateCodePoints(input.selection, LIVE_CONTEXT_SELECTION_MAX_CHARS),
  };
}

/**
 * How to launch the core. A packaged build runs the self-contained PyInstaller
 * bundle directly; a dev build runs `python -m logosforge.api` from the venv.
 */
type Launcher =
  | { kind: 'bundled'; exe: string; cwd: string; args: string[] }
  | { kind: 'python'; python: string; coreDir: string; args: string[] };

export interface CoreManagerOptions {
  /** Pin production launches to loopback; source development may opt into LAN binding. */
  production?: boolean;
  /** Absolute path to the bundled `logosforge-core(.exe)` (packaged builds only). */
  bundledCorePath?: string;
  /**
   * Explicit SQLite path passed to the core as `--db`. Packaged builds MUST set
   * this to a stable per-user location (e.g. app.getPath('userData')): the core
   * otherwise opens a cwd-relative `logosforge.db`, which for a portable build
   * lands in a temp dir that is wiped on exit (data loss). Dev leaves it unset
   * to preserve the existing behaviour / connect-to-running-core.
   */
  dbPath?: string;
  /** Private per-user descriptor used by the packaged stdio MCP launcher. */
  mcpRuntimePath?: string;
}

/** The core repo dir (sibling of pro-desktop) and its venv python. Both overridable via env. */
function resolveDevPython(): { coreDir: string; python: string } {
  // Compiled location: pro-desktop/dist-electron → repo root → /logosforge
  const coreDir = process.env.LOGOSFORGE_CORE_DIR ?? path.resolve(__dirname, '..', '..', 'logosforge');
  if (process.env.LOGOSFORGE_PYTHON) return { coreDir, python: process.env.LOGOSFORGE_PYTHON };
  const venv =
    process.platform === 'win32'
      ? path.join(coreDir, 'venv', 'Scripts', 'python.exe')
      : path.join(coreDir, 'venv', 'bin', 'python');
  if (fs.existsSync(venv)) return { coreDir, python: venv };
  return { coreDir, python: process.platform === 'win32' ? 'python' : 'python3' };
}

/**
 * Dexter's Room voice: point the core at the user's local faster-whisper model.
 * Nothing is bundled (the model is ~1.5GB) — an explicit LOGOSFORGE_VOICE_MODEL
 * env wins; otherwise auto-detect a `faster-whisper-large-v3` dir in a few known
 * spots and, if a sibling `_cuda_runtime` exists, enable GPU. No model found →
 * empty env → the core reports voice unavailable (handled gracefully in the UI).
 */
function resolveVoiceEnv(): Record<string, string> {
  if (process.env.LOGOSFORGE_VOICE_MODEL) {
    return {
      LOGOSFORGE_VOICE_MODEL: process.env.LOGOSFORGE_VOICE_MODEL,
      LOGOSFORGE_VOICE_DEVICE: process.env.LOGOSFORGE_VOICE_DEVICE ?? 'cuda',
      LOGOSFORGE_VOICE_COMPUTE: process.env.LOGOSFORGE_VOICE_COMPUTE ?? 'float16',
      LOGOSFORGE_VOICE_CUDA_DIRS: process.env.LOGOSFORGE_VOICE_CUDA_DIRS ?? '',
    };
  }
  const home = os.homedir();
  const modelsDir = process.env.LOGOSFORGE_MODELS_DIR;
  const candidates = [
    modelsDir ? path.join(modelsDir, 'faster-whisper-large-v3') : '',
    path.join(home, '.logosforge', 'models', 'faster-whisper-large-v3'),
    path.resolve(__dirname, '..', '..', 'models', 'faster-whisper-large-v3'), // dev monorepo checkout
    path.join(home, 'Desktop', 'Logosforge Alphatest', 'models', 'faster-whisper-large-v3'), // this machine's setup
  ].filter(Boolean);
  for (const model of candidates) {
    if (!fs.existsSync(model)) continue;
    const cudaDir = path.join(path.dirname(model), '_cuda_runtime');
    const hasCuda = fs.existsSync(cudaDir);
    return {
      LOGOSFORGE_VOICE_MODEL: model,
      LOGOSFORGE_VOICE_DEVICE: hasCuda ? 'cuda' : 'cpu',
      LOGOSFORGE_VOICE_COMPUTE: hasCuda ? 'float16' : 'int8',
      LOGOSFORGE_VOICE_CUDA_DIRS: hasCuda ? cudaDir : '',
    };
  }
  return {};
}

export class CoreManager {
  private child: ChildProcess | null = null;
  private managed = false;
  private spawnFailed = false;
  private port = INITIAL_PORT;
  private readonly host: string;
  private endpoint: string;
  private readonly authToken = randomBytes(32).toString('base64url');
  private readonly instanceNonce = randomBytes(18).toString('base64url');
  private readonly liveContextToken = randomBytes(32).toString('base64url');
  private status: CoreStatus;
  private readonly listeners = new Set<(s: CoreStatus) => void>();
  private liveContextRevision = 0;
  private readonly liveContextQueue: LiveContextQueueEntry[] = [];
  private liveContextDrainPromise: Promise<void> | null = null;
  private liveContextPublishingEnabled = true;
  private stopping = false;
  private stopPromise: Promise<void> | null = null;

  constructor(private readonly opts: CoreManagerOptions = {}) {
    const requestedHost = process.env.LOGOSFORGE_HOST?.trim();
    const production = opts.production ?? Boolean(opts.bundledCorePath);
    this.host = resolveCoreHost(requestedHost, production);
    this.endpoint = `http://${this.host}:${INITIAL_PORT}`;
    this.status = {
      state: 'connecting', baseUrl: this.endpoint, managed: false, authToken: this.authToken,
    };
    if (production && requestedHost && requestedHost !== this.host) {
      console.warn(
        `[security] Ignoring LOGOSFORGE_HOST=${requestedHost}; production cores bind to ${this.host}.`,
      );
    }
  }

  get baseUrl(): string {
    return this.endpoint;
  }

  onStatus(cb: (s: CoreStatus) => void): () => void {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }

  getStatus(): CoreStatus {
    return this.status;
  }

  private setStatus(patch: Partial<CoreStatus>): void {
    this.status = { ...this.status, ...patch };
    for (const cb of this.listeners) cb(this.status);
  }

  private clearRuntimeDescriptor(requireCurrentNonce = true): void {
    const target = this.opts.mcpRuntimePath;
    if (!target) return;
    try {
      removeRuntimeDescriptor(target, requireCurrentNonce ? this.instanceNonce : undefined);
    } catch (error) {
      if (this.stopping) return;
      const detail = error instanceof Error ? error.message : String(error);
      console.error(`[mcp] Could not remove the runtime descriptor: ${detail}`);
    }
  }

  private publishRuntimeDescriptor(): string | null {
    const target = this.opts.mcpRuntimePath;
    if (!target) return null;
    const corePid = this.child?.pid;
    if (!corePid) return 'the managed core process id is unavailable';
    try {
      writeRuntimeDescriptor(target, {
        schema_version: 1,
        base_url: this.endpoint,
        auth_token: this.authToken,
        instance_nonce: this.instanceNonce,
        app_pid: process.pid,
        core_pid: corePid,
        created_at: new Date().toISOString(),
      });
      return null;
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      console.error(`[mcp] Could not publish the runtime descriptor: ${detail}`);
      return 'the local Codex bridge could not publish its private connection file';
    }
  }

  private setConnected(detail: string): void {
    const bridgeError = this.publishRuntimeDescriptor();
    this.setStatus({
      state: 'connected',
      managed: this.managed,
      detail: bridgeError ? `${detail} MCP unavailable: ${bridgeError}.` : detail,
    });
  }

  private enqueueLiveContext(
    context: Omit<CoreLiveContextPayload, 'source_id' | 'revision'>,
  ): Promise<void> {
    const revision = this.liveContextRevision + 1;
    this.liveContextRevision = revision;
    const payload: CoreLiveContextPayload = {
      ...context,
      source_id: this.instanceNonce,
      revision,
    };
    return new Promise<void>((resolve, reject) => {
      const waiter = { resolve, reject };
      const isClear = payload.project_id === null;

      if (isClear && this.liveContextQueue.length > 0) {
        // A final clear supersedes every update that has not started yet.
        // Superseded callers can complete immediately; only the authoritative
        // clear retains a waiter, keeping both payloads and closures bounded.
        const superseded = this.liveContextQueue.splice(0);
        superseded.forEach((entry) => entry.waiters.forEach(({ resolve }) => resolve()));
        this.liveContextQueue.push({
          payload,
          waiters: [waiter],
        });
      } else {
        const pending = this.liveContextQueue.at(-1);
        if (pending && (pending.payload.project_id === null) === isClear) {
          // Renderer churn and heartbeats only need the newest pending state.
          // The in-flight request plus at most clear→publish remain bounded.
          pending.waiters.forEach(({ resolve }) => resolve());
          pending.payload = payload;
          pending.waiters = [waiter];
        } else {
          this.liveContextQueue.push({ payload, waiters: [waiter] });
        }
      }
      this.drainLiveContextQueue();
    });
  }

  private drainLiveContextQueue(): void {
    if (this.liveContextDrainPromise) return;
    this.liveContextDrainPromise = (async () => {
      while (this.liveContextQueue.length > 0) {
        const entry = this.liveContextQueue.shift()!;
        try {
          await this.sendLiveContext(entry.payload);
          entry.waiters.forEach(({ resolve }) => resolve());
        } catch (error) {
          entry.waiters.forEach(({ reject }) => reject(error));
        }
      }
    })().finally(() => {
      this.liveContextDrainPromise = null;
      // An enqueue cannot normally interleave with the synchronous end of the
      // loop, but keep the drain self-healing if that invariant ever changes.
      if (this.liveContextQueue.length > 0) this.drainLiveContextQueue();
    });
  }

  private async sendLiveContext(payload: CoreLiveContextPayload): Promise<void> {
    if (this.status.state !== 'connected') {
      throw new Error('The logosforge core is not connected.');
    }
    // Production is pinned to loopback. Source development may explicitly use
    // a concrete LAN bind, so target the same verified core rather than a
    // loopback address on which that listener may not exist.
    const target = liveContextEndpoint(this.endpoint);
    const response = await httpPutJson(
      target,
      this.authToken,
      this.liveContextToken,
      payload,
    );
    const body = response.body as Record<string, unknown> | null;
    if (response.statusCode !== 200 || !body || body.ok !== true) {
      throw new Error(`The core rejected live context (HTTP ${response.statusCode}).`);
    }
    if (body.revision !== payload.revision) {
      throw new Error('The core acknowledged a different live-context revision.');
    }
  }

  /** Publish renderer state without allowing it to choose source or revision. */
  publishLiveContext(value: unknown): Promise<void> {
    const context = normalizeRendererLiveContext(value);
    if (!this.liveContextPublishingEnabled || this.status.state !== 'connected') {
      return Promise.resolve();
    }
    if (context.projectId === null) return this.clearLiveContextFromRenderer();
    return this.enqueueLiveContext({
      project_id: context.projectId,
      active_panel_id: context.activePanelId,
      active_scene_id: context.activeSceneId,
      selection_section: context.selectionSection,
      selection: context.selection,
    });
  }

  /** An ordered clear is represented by a null project and empty context. */
  clearLiveContext(): Promise<void> {
    if (this.status.state !== 'connected') return Promise.resolve();
    return this.enqueueLiveContext({
      project_id: null,
      active_panel_id: null,
      active_scene_id: null,
      selection_section: null,
      selection: '',
    });
  }

  /** Ignore renderer cleanup after main has begun its authoritative clear. */
  clearLiveContextFromRenderer(): Promise<void> {
    if (!this.liveContextPublishingEnabled) return Promise.resolve();
    return this.clearLiveContext();
  }

  /** Stop renderer publications first, then place one final clear in the queue. */
  suspendLiveContext(): Promise<void> {
    this.liveContextPublishingEnabled = false;
    return this.clearLiveContextBestEffort();
  }

  /** A new macOS window may publish again while the same core stays alive. */
  resumeLiveContext(): void {
    if (!this.stopping && !this.stopPromise) this.liveContextPublishingEnabled = true;
  }

  /** Lifecycle cleanup must never prevent the user from closing the app. */
  async clearLiveContextBestEffort(): Promise<void> {
    if (this.status.state !== 'connected') return;
    try {
      await this.clearLiveContext();
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      console.warn(`[mcp] Could not clear live editor context: ${detail}`);
    }
  }

  async start(): Promise<void> {
    if (this.stopping) return;
    // The single-instance Electron shell owns this exact path. Remove a crash
    // leftover before a new session can publish credentials.
    this.clearRuntimeDescriptor(false);
    this.setStatus({ state: 'connecting', detail: 'Looking for the logosforge core…' });

    // 1. Reuse only a process carrying this manager's one-time nonce (normally
    // reachable only if start() is called twice on the same manager instance).
    if (await this.ping()) {
      if (this.stopping) return;
      this.setConnected(
        this.managed ? 'Core launched by the app.' : 'Connected to a verified core.',
      );
      return;
    }

    try {
      const selectedPort = await selectAvailablePort(
        this.host, this.port, !PORT_WAS_EXPLICIT,
      );
      if (this.stopping) return;
      if (selectedPort !== this.port) {
        this.port = selectedPort;
        this.endpoint = `http://${this.host}:${selectedPort}`;
        this.setStatus({
          baseUrl: this.endpoint,
          detail: `Default port was occupied; using local port ${selectedPort}.`,
        });
      }
    } catch (error) {
      if (this.stopping) return;
      const detail = error instanceof Error ? error.message : String(error);
      this.setStatus({ state: 'error', detail });
      return;
    }

    // 2. Otherwise spawn one.
    if (this.stopping) return;
    this.spawnCore();
    if (this.spawnFailed) return;

    // 3. Wait for /api/health.
    for (let i = 0; i < 40; i += 1) {
      if (this.spawnFailed || this.stopping) return;
      if (await this.ping()) {
        if (this.stopping) return;
        this.managed = true;
        this.setConnected('Core launched by the app.');
        return;
      }
      await delay(1000);
    }
    if (!this.stopping && this.status.state !== 'error') {
      this.clearRuntimeDescriptor();
      this.setStatus({ state: 'error', detail: 'Core did not become healthy in time.' });
    }
  }

  stop(): Promise<void> {
    if (this.stopPromise) return this.stopPromise;
    this.stopping = true;
    this.liveContextPublishingEnabled = false;
    this.stopPromise = (async () => {
      // Keep this ahead of descriptor removal and process termination so an
      // MCP client cannot observe stale editor state during orderly shutdown.
      await this.clearLiveContextBestEffort();
      this.clearRuntimeDescriptor();
      // A non-null child is always one this manager spawned. Kill it even if
      // shutdown lands before the health probe has promoted it to `managed`.
      if (this.child) {
        const child = this.child;
        this.child = null;
        try {
          child.kill();
        } catch {
          /* ignore */
        }
      }
    })();
    return this.stopPromise;
  }

  private async ping(): Promise<boolean> {
    return isExpectedCoreHealth(
      await httpGetJson(`${this.endpoint}/api/health`),
      this.instanceNonce,
    );
  }

  /** Decide how to launch the core: the bundled exe (packaged) or dev python. */
  private resolveLauncher(): Launcher | null {
    const args = ['--host', this.host, '--port', String(this.port), '--mode', 'desktop'];
    if (this.opts.dbPath) args.push('--db', this.opts.dbPath);
    const bundled = this.opts.bundledCorePath;
    if (bundled) {
      if (!fs.existsSync(bundled)) {
        this.setStatus({ state: 'error', detail: `Bundled core not found at ${bundled}.` });
        return null;
      }
      return { kind: 'bundled', exe: bundled, cwd: path.dirname(bundled), args };
    }
    const { coreDir, python } = resolveDevPython();
    if (!fs.existsSync(coreDir)) {
      this.setStatus({ state: 'error', detail: `Core repo not found at ${coreDir}.` });
      return null;
    }
    return { kind: 'python', python, coreDir, args: ['-m', 'logosforge.api', ...args] };
  }

  private spawnCore(): void {
    const launcher = this.resolveLauncher();
    if (!launcher) {
      this.spawnFailed = true;
      return;
    }

    const command = launcher.kind === 'bundled' ? launcher.exe : launcher.python;
    const cwd = launcher.kind === 'bundled' ? launcher.cwd : launcher.coreDir;
    const child = spawn(command, launcher.args, {
      cwd,
      env: {
        ...process.env,
        API_HOST: this.host,
        API_PORT: String(this.port),
        API_MODE: 'desktop',
        API_AUTH_TOKEN: this.authToken,
        API_INSTANCE_NONCE: this.instanceNonce,
        API_LIVE_CONTEXT_TOKEN: this.liveContextToken,
        ...resolveVoiceEnv(),
      },
      stdio: 'pipe',
      windowsHide: true, // the bundled core is a console exe; don't flash a window
    });
    this.child = child;
    child.stdout?.on('data', (d) => console.log('[core]', String(d).trim()));
    child.stderr?.on('data', (d) => console.log('[core]', String(d).trim()));

    child.on('error', (err) => {
      this.clearRuntimeDescriptor();
      this.spawnFailed = true;
      this.child = null;
      if (this.stopping) return;
      const hint = this.opts.bundledCorePath ? 'The bundled core failed to launch.' : 'Is the logosforge venv set up?';
      this.setStatus({ state: 'error', detail: `Failed to start the core (${err.message}). ${hint}` });
    });
    child.on('exit', (code) => {
      this.clearRuntimeDescriptor();
      this.child = null;
      if (this.stopping) return;
      if (this.status.state !== 'connected') {
        this.spawnFailed = true;
        this.setStatus({ state: 'error', detail: `Core exited before startup (code ${code}).` });
      } else if (this.managed) {
        this.setStatus({ state: 'error', detail: `Core process exited (code ${code}).` });
      }
    });
  }
}
