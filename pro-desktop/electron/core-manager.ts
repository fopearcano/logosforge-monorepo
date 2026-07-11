/**
 * Core manager — owns the lifecycle of the logosforge core HTTP API.
 *
 *  - Connect to an already-running core (e.g. one you started by hand), or
 *  - spawn `python -m logosforge.api --mode desktop` from the core's venv,
 *  - wait for GET /api/health,
 *  - report status to the renderer,
 *  - stop the core on app close — but only if this process launched it.
 *
 * The core IS the backend: pro-desktop talks to it directly via the HTTP
 * ApiClient (createHttpApiClient). There is no separate FastAPI layer.
 */

import { spawn, type ChildProcess } from 'node:child_process';
import * as fs from 'node:fs';
import * as http from 'node:http';
import * as os from 'node:os';
import * as path from 'node:path';

export type CoreState = 'connecting' | 'connected' | 'error';

export interface CoreStatus {
  state: CoreState;
  baseUrl: string;
  managed: boolean;
  detail?: string;
}

const HOST = process.env.LOGOSFORGE_HOST ?? '127.0.0.1';
const PORT = Number(process.env.LOGOSFORGE_PORT ?? 8765);
const BASE_URL = `http://${HOST}:${PORT}`;

const delay = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/** Resolve true on any 2xx from the URL (lenient health probe). */
function httpOk(url: string, timeoutMs = 1500): Promise<boolean> {
  return new Promise((resolve) => {
    const req = http.get(url, (res) => {
      res.resume();
      resolve(res.statusCode != null && res.statusCode >= 200 && res.statusCode < 300);
    });
    req.setTimeout(timeoutMs, () => req.destroy());
    req.on('error', () => resolve(false));
    req.on('timeout', () => resolve(false));
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
  private status: CoreStatus = { state: 'connecting', baseUrl: BASE_URL, managed: false };
  private readonly listeners = new Set<(s: CoreStatus) => void>();

  constructor(private readonly opts: CoreManagerOptions = {}) {}

  get baseUrl(): string {
    return BASE_URL;
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

  async start(): Promise<void> {
    this.setStatus({ state: 'connecting', detail: 'Looking for the logosforge core…' });

    // 1. Connect to an already-running core.
    if (await this.ping()) {
      this.managed = false;
      this.setStatus({ state: 'connected', managed: false, detail: 'Connected to a running core.' });
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
        this.setStatus({ state: 'connected', managed: true, detail: 'Core launched by the app.' });
        return;
      }
      await delay(1000);
    }
    if (this.status.state !== 'error') {
      this.setStatus({ state: 'error', detail: 'Core did not become healthy in time.' });
    }
  }

  stop(): void {
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

  private ping(): Promise<boolean> {
    return httpOk(`${BASE_URL}/api/health`);
  }

  /** Decide how to launch the core: the bundled exe (packaged) or dev python. */
  private resolveLauncher(): Launcher | null {
    const args = ['--host', HOST, '--port', String(PORT), '--mode', 'desktop'];
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
      env: { ...process.env, API_HOST: HOST, API_PORT: String(PORT), API_MODE: 'desktop', ...resolveVoiceEnv() },
      stdio: 'pipe',
      windowsHide: true, // the bundled core is a console exe; don't flash a window
    });
    this.child = child;
    child.stdout?.on('data', (d) => console.log('[core]', String(d).trim()));
    child.stderr?.on('data', (d) => console.log('[core]', String(d).trim()));

    child.on('error', (err) => {
      this.spawnFailed = true;
      this.child = null;
      const hint = this.opts.bundledCorePath ? 'The bundled core failed to launch.' : 'Is the logosforge venv set up?';
      this.setStatus({ state: 'error', detail: `Failed to start the core (${err.message}). ${hint}` });
    });
    child.on('exit', (code) => {
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
