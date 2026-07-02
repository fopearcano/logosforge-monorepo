/**
 * Backend manager.
 *
 * Responsibilities (per milestone):
 *  - connect to an already-running backend, or start one in development;
 *  - wait for GET /health;
 *  - report status to the renderer (via the main process);
 *  - handle startup failure gracefully;
 *  - stop the backend on app close, but only if this process launched it.
 */

import { spawn, type ChildProcess } from 'node:child_process';
import * as fs from 'node:fs';
import * as http from 'node:http';
import * as path from 'node:path';

export type BackendState = 'connecting' | 'connected' | 'error';

export interface BackendStatus {
  state: BackendState;
  baseUrl: string;
  managed: boolean;
  service?: string;
  version?: string;
  apiVersion?: string;
  detail?: string;
}

const HOST = process.env.LOGOSFORGE_HOST ?? '127.0.0.1';
const PORT = Number(process.env.LOGOSFORGE_PORT ?? 8777);
const BASE_URL = `http://${HOST}:${PORT}`;

// In a packaged app the PyInstaller-frozen backend ships under resources/backend.
const FROZEN_EXE =
  process.platform === 'win32'
    ? 'logosforge-whiteboard-backend.exe'
    : 'logosforge-whiteboard-backend';

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function httpGetJson(url: string, timeoutMs = 1500): Promise<any> {
  return new Promise((resolve, reject) => {
    const req = http.get(url, (res) => {
      if (res.statusCode !== 200) {
        res.resume();
        reject(new Error(`HTTP ${res.statusCode}`));
        return;
      }
      let body = '';
      res.setEncoding('utf8');
      res.on('data', (chunk) => {
        body += chunk;
      });
      res.on('end', () => {
        try {
          resolve(JSON.parse(body));
        } catch (err) {
          reject(err);
        }
      });
    });
    req.setTimeout(timeoutMs, () => req.destroy(new Error('timeout')));
    req.on('error', reject);
  });
}

function resolvePython(backendDir: string): string {
  const venv =
    process.platform === 'win32'
      ? path.join(backendDir, '.venv', 'Scripts', 'python.exe')
      : path.join(backendDir, '.venv', 'bin', 'python');
  if (fs.existsSync(venv)) return venv;
  return process.platform === 'win32' ? 'python' : 'python3';
}

export class BackendManager {
  private child: ChildProcess | null = null;
  private managed = false;
  private spawnFailed = false;
  private status: BackendStatus = {
    state: 'connecting',
    baseUrl: BASE_URL,
    managed: false,
  };
  private readonly listeners = new Set<(status: BackendStatus) => void>();

  onStatus(cb: (status: BackendStatus) => void): () => void {
    this.listeners.add(cb);
    return () => {
      this.listeners.delete(cb);
    };
  }

  getStatus(): BackendStatus {
    return this.status;
  }

  private setStatus(patch: Partial<BackendStatus>): void {
    this.status = { ...this.status, ...patch };
    for (const listener of this.listeners) listener(this.status);
  }

  async start(): Promise<void> {
    this.setStatus({ state: 'connecting', detail: 'Looking for backend…' });

    // 1. Connect to an already-running backend, if any.
    if (await this.ping()) {
      this.managed = false;
      await this.markConnected(false);
      return;
    }

    // 2. Otherwise launch one (development / when Python is available).
    this.spawnBackend();
    if (this.spawnFailed) return;

    // 3. Wait for it to become healthy.
    const healthy = await this.waitForHealth(30, 1000);
    if (healthy) {
      this.managed = true;
      await this.markConnected(true);
    } else if (this.status.state !== 'error') {
      this.setStatus({ state: 'error', detail: 'Backend did not become healthy in time.' });
    }
  }

  stop(): void {
    // Only stop the backend if we launched it.
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
    try {
      const json = await httpGetJson(`${BASE_URL}/health`);
      return json?.status === 'ok';
    } catch {
      return false;
    }
  }

  private async markConnected(managed: boolean): Promise<void> {
    let version: string | undefined;
    let apiVersion: string | undefined;
    let service: string | undefined;
    try {
      const v = await httpGetJson(`${BASE_URL}/api/version`);
      version = v.version;
      apiVersion = v.api_version;
      service = v.name;
    } catch {
      /* version is best-effort */
    }
    this.setStatus({
      state: 'connected',
      managed,
      version,
      apiVersion,
      service,
      detail: managed ? 'Backend launched by the app.' : 'Connected to a running backend.',
    });
  }

  /**
   * In a packaged app the PyInstaller-frozen backend ships as an Electron
   * extraResource at resources/backend/. Returns its exe path when present
   * (production); null in dev, where we fall back to python + uvicorn.
   */
  private frozenBackendPath(): string | null {
    const candidate = path.join(process.resourcesPath, 'backend', FROZEN_EXE);
    return fs.existsSync(candidate) ? candidate : null;
  }

  private spawnBackend(): void {
    const env = { ...process.env, LOGOSFORGE_HOST: HOST, LOGOSFORGE_PORT: String(PORT) };

    // Production: spawn the self-contained, PyInstaller-frozen backend (it embeds
    // the core — no Python needed on the user's machine).
    const frozen = this.frozenBackendPath();
    if (frozen) {
      const child = spawn(frozen, ['--host', HOST, '--port', String(PORT)], {
        cwd: path.dirname(frozen),
        env,
        stdio: 'pipe',
        windowsHide: true,
      });
      this.attachChildHandlers(child, 'bundled');
      return;
    }

    // Development: run the backend from source via the project venv (or a system
    // Python), exactly like the dev `npm run` flow.
    // Compiled location: desktop/dist-electron/ -> repo/backend
    const backendDir = path.resolve(__dirname, '..', '..', 'backend');
    if (!fs.existsSync(backendDir)) {
      this.spawnFailed = true;
      this.setStatus({ state: 'error', detail: `Backend directory not found at ${backendDir}.` });
      return;
    }

    const python = resolvePython(backendDir);
    const child = spawn(
      python,
      ['-m', 'uvicorn', 'app.main:app', '--host', HOST, '--port', String(PORT)],
      { cwd: backendDir, env, stdio: 'pipe' },
    );
    this.attachChildHandlers(child, 'dev');
  }

  private attachChildHandlers(child: ChildProcess, kind: 'bundled' | 'dev'): void {
    this.child = child;

    child.stdout?.on('data', (d) => console.log('[backend]', String(d).trim()));
    child.stderr?.on('data', (d) => console.log('[backend]', String(d).trim()));

    child.on('error', (err) => {
      this.spawnFailed = true;
      this.child = null;
      const hint = kind === 'dev' ? ' Is Python installed and are backend deps set up?' : '';
      this.setStatus({ state: 'error', detail: `Failed to start backend (${err.message}).${hint}` });
    });

    child.on('exit', (code) => {
      this.child = null;
      if (this.status.state !== 'connected') {
        this.spawnFailed = true;
        const hint = kind === 'dev' ? ' Try: cd backend && pip install -r requirements.txt' : '';
        this.setStatus({
          state: 'error',
          detail: `Backend exited before startup (code ${code}).${hint}`,
        });
      } else if (this.managed) {
        this.setStatus({ state: 'error', detail: `Backend process exited (code ${code}).` });
      }
    });
  }

  private async waitForHealth(attempts: number, intervalMs: number): Promise<boolean> {
    for (let i = 0; i < attempts; i += 1) {
      if (this.spawnFailed) return false;
      if (await this.ping()) return true;
      await delay(intervalMs);
    }
    return false;
  }
}
