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
import { isExpectedCoreHealth } from './security';

export type CoreState = 'connecting' | 'connected' | 'error';

export interface CoreStatus {
  state: CoreState;
  baseUrl: string;
  managed: boolean;
  detail?: string;
  /** Per-process secret used only by renderer → local core requests. */
  authToken?: string;
}

const HOST = process.env.LOGOSFORGE_HOST ?? '127.0.0.1';
const RAW_PORT = process.env.LOGOSFORGE_PORT;
const INITIAL_PORT = Number(RAW_PORT ?? 8765);
const PORT_WAS_EXPLICIT = typeof RAW_PORT === 'string' && RAW_PORT.trim().length > 0;
const HEALTH_RESPONSE_MAX_BYTES = 64 * 1024;

const delay = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

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

/**
 * How to launch the core. A packaged build runs the self-contained PyInstaller
 * bundle directly; a dev build runs `python -m logosforge.api` from the venv.
 */
type Launcher =
  | { kind: 'bundled'; exe: string; cwd: string; args: string[] }
  | { kind: 'python'; python: string; coreDir: string; args: string[] };

export interface CoreManagerOptions {
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
  private endpoint = `http://${HOST}:${INITIAL_PORT}`;
  private readonly authToken = randomBytes(32).toString('base64url');
  private readonly instanceNonce = randomBytes(18).toString('base64url');
  private status: CoreStatus = {
    state: 'connecting', baseUrl: this.endpoint, managed: false, authToken: this.authToken,
  };
  private readonly listeners = new Set<(s: CoreStatus) => void>();

  constructor(private readonly opts: CoreManagerOptions = {}) {}

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

  async start(): Promise<void> {
    // The single-instance Electron shell owns this exact path. Remove a crash
    // leftover before a new session can publish credentials.
    this.clearRuntimeDescriptor(false);
    this.setStatus({ state: 'connecting', detail: 'Looking for the logosforge core…' });

    // 1. Reuse only a process carrying this manager's one-time nonce (normally
    // reachable only if start() is called twice on the same manager instance).
    if (await this.ping()) {
      this.setConnected(
        this.managed ? 'Core launched by the app.' : 'Connected to a verified core.',
      );
      return;
    }

    try {
      const selectedPort = await selectAvailablePort(
        HOST, this.port, !PORT_WAS_EXPLICIT,
      );
      if (selectedPort !== this.port) {
        this.port = selectedPort;
        this.endpoint = `http://${HOST}:${selectedPort}`;
        this.setStatus({
          baseUrl: this.endpoint,
          detail: `Default port was occupied; using local port ${selectedPort}.`,
        });
      }
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      this.setStatus({ state: 'error', detail });
      return;
    }

    // 2. Otherwise spawn one.
    this.spawnCore();
    if (this.spawnFailed) return;

    // 3. Wait for /api/health.
    for (let i = 0; i < 40; i += 1) {
      if (this.spawnFailed) return;
      if (await this.ping()) {
        this.managed = true;
        this.setConnected('Core launched by the app.');
        return;
      }
      await delay(1000);
    }
    if (this.status.state !== 'error') {
      this.clearRuntimeDescriptor();
      this.setStatus({ state: 'error', detail: 'Core did not become healthy in time.' });
    }
  }

  stop(): void {
    this.clearRuntimeDescriptor();
    if (this.child && this.managed) {
      const child = this.child;
      this.child = null;
      try {
        child.kill();
      } catch {
        /* ignore */
      }
    }
  }

  private async ping(): Promise<boolean> {
    return isExpectedCoreHealth(
      await httpGetJson(`${this.endpoint}/api/health`),
      this.instanceNonce,
    );
  }

  /** Decide how to launch the core: the bundled exe (packaged) or dev python. */
  private resolveLauncher(): Launcher | null {
    const args = ['--host', HOST, '--port', String(this.port), '--mode', 'desktop'];
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
        API_HOST: HOST,
        API_PORT: String(this.port),
        API_MODE: 'desktop',
        API_AUTH_TOKEN: this.authToken,
        API_INSTANCE_NONCE: this.instanceNonce,
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
      const hint = this.opts.bundledCorePath ? 'The bundled core failed to launch.' : 'Is the logosforge venv set up?';
      this.setStatus({ state: 'error', detail: `Failed to start the core (${err.message}). ${hint}` });
    });
    child.on('exit', (code) => {
      this.clearRuntimeDescriptor();
      this.child = null;
      if (this.status.state !== 'connected') {
        this.spawnFailed = true;
        this.setStatus({ state: 'error', detail: `Core exited before startup (code ${code}).` });
      } else if (this.managed) {
        this.setStatus({ state: 'error', detail: `Core process exited (code ${code}).` });
      }
    });
  }
}
