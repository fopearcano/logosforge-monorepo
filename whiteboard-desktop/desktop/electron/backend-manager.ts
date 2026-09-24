/**
 * Backend manager.
 *
 * Responsibilities (per milestone):
 *  - reuse only a backend carrying this manager's nonce, otherwise start one;
 *  - wait for GET /health;
 *  - report status to the renderer (via the main process);
 *  - handle startup failure gracefully;
 *  - stop the backend on app close, but only if this process launched it.
 */

import { spawn, type ChildProcess } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import * as fs from 'node:fs';
import * as http from 'node:http';
import * as path from 'node:path';

import { removeRuntimeDescriptor, writeRuntimeDescriptor } from './mcp-runtime';
import { selectAvailablePort } from './port-selection';
import { isExpectedBackendHealth, resolveBackendHost } from './service-identity';

export type BackendState = 'connecting' | 'connected' | 'error';

export interface BackendStatus {
  state: BackendState;
  baseUrl: string;
  managed: boolean;
  service?: string;
  version?: string;
  apiVersion?: string;
  /** Per-process secret used only by renderer → local wrapper requests. */
  authToken?: string;
  detail?: string;
}

export interface BackendManagerOptions {
  /** Pin production launches to loopback; source development may opt into LAN binding. */
  production?: boolean;
  /** Private per-user descriptor used by the packaged stdio MCP companion. */
  mcpRuntimePath?: string;
}

const RAW_PORT = process.env.LOGOSFORGE_PORT;
const INITIAL_PORT = Number(RAW_PORT ?? 8777);
const PORT_WAS_EXPLICIT = typeof RAW_PORT === 'string' && RAW_PORT.trim().length > 0;
const HEALTH_RESPONSE_MAX_BYTES = 64 * 1024;

// In a packaged app the PyInstaller-frozen backend ships under resources/backend.
const FROZEN_EXE =
  process.platform === 'win32'
    ? 'logosforge-whiteboard-backend.exe'
    : 'logosforge-whiteboard-backend';

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function httpGetJson(url: string, timeoutMs = 1500, authToken = ''): Promise<any> {
  return new Promise((resolve, reject) => {
    const options: http.RequestOptions = authToken
      ? { headers: { Authorization: `Bearer ${authToken}` } }
      : {};
    const req = http.get(url, options, (res) => {
      if (res.statusCode !== 200) {
        res.resume();
        reject(new Error(`HTTP ${res.statusCode}`));
        return;
      }
      let body = '';
      res.setEncoding('utf8');
      res.on('data', (chunk) => {
        body += chunk;
        if (body.length > HEALTH_RESPONSE_MAX_BYTES) {
          res.destroy(new Error('health response too large'));
        }
      });
      res.on('error', reject);
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
  private port = INITIAL_PORT;
  private readonly host: string;
  private baseUrl: string;
  private readonly authToken = randomBytes(32).toString('base64url');
  private readonly instanceNonce = randomBytes(18).toString('base64url');
  private status: BackendStatus;
  private readonly listeners = new Set<(status: BackendStatus) => void>();

  constructor(private readonly opts: BackendManagerOptions = {}) {
    const requestedHost = process.env.LOGOSFORGE_HOST?.trim();
    this.host = resolveBackendHost(requestedHost, opts.production === true);
    this.baseUrl = `http://${this.host}:${INITIAL_PORT}`;
    this.status = {
      state: 'connecting',
      baseUrl: this.baseUrl,
      managed: false,
      authToken: this.authToken,
    };
    if (opts.production && requestedHost && requestedHost !== this.host) {
      console.warn(
        `[security] Ignoring LOGOSFORGE_HOST=${requestedHost}; production backends bind to ${this.host}.`,
      );
    }
  }

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
    const backendPid = this.child?.pid;
    if (!backendPid) return 'the managed backend process id is unavailable';
    let descriptorUrl: URL;
    try {
      descriptorUrl = new URL(this.baseUrl);
    } catch {
      return 'the backend connection URL is invalid';
    }
    if (!['127.0.0.1', '::1', '[::1]'].includes(descriptorUrl.hostname)) {
      return 'the backend connection is not loopback-only';
    }
    try {
      writeRuntimeDescriptor(target, {
        schema_version: 1,
        base_url: this.baseUrl,
        auth_token: this.authToken,
        instance_nonce: this.instanceNonce,
        app_pid: process.pid,
        backend_pid: backendPid,
        created_at: new Date().toISOString(),
      });
      return null;
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      console.error(`[mcp] Could not publish the runtime descriptor: ${detail}`);
      return 'the local Codex bridge could not publish its private connection file';
    }
  }

  async start(): Promise<void> {
    // The single-instance Electron shell owns this exact path. Remove a crash
    // leftover before a new session can publish credentials.
    this.clearRuntimeDescriptor(false);
    this.setStatus({ state: 'connecting', detail: 'Looking for backend…' });

    // 1. Reuse only a process carrying this manager's one-time nonce (normally
    // reachable only if start() is called twice on the same manager instance).
    if (await this.ping()) {
      await this.markConnected(this.managed);
      return;
    }

    // A backend orphaned by an earlier crash has a different nonce. Keep an
    // explicit user port strict, but move the default endpoint to a free local
    // port so the writer can reopen the app without killing processes manually.
    try {
      const selectedPort = await selectAvailablePort(
        this.host, this.port, !PORT_WAS_EXPLICIT,
      );
      if (selectedPort !== this.port) {
        this.port = selectedPort;
        this.baseUrl = `http://${this.host}:${selectedPort}`;
        this.setStatus({
          baseUrl: this.baseUrl,
          detail: `Default port was occupied; using local port ${selectedPort}.`,
        });
      }
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      this.setStatus({ state: 'error', detail });
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
      this.clearRuntimeDescriptor();
      this.setStatus({ state: 'error', detail: 'Backend did not become healthy in time.' });
    }
  }

  stop(): void {
    this.clearRuntimeDescriptor();
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
      const json = await httpGetJson(`${this.baseUrl}/health`);
      return isExpectedBackendHealth(json, this.instanceNonce);
    } catch {
      return false;
    }
  }

  private async markConnected(managed: boolean): Promise<void> {
    let version: string | undefined;
    let apiVersion: string | undefined;
    let service: string | undefined;
    try {
      const v = await httpGetJson(`${this.baseUrl}/api/version`, 1500, this.authToken);
      version = v.version;
      apiVersion = v.api_version;
      service = v.name;
    } catch {
      /* version is best-effort */
    }
    const bridgeError = this.publishRuntimeDescriptor();
    const detail = managed ? 'Backend launched by the app.' : 'Connected to a running backend.';
    this.setStatus({
      state: 'connected',
      managed,
      version,
      apiVersion,
      service,
      detail: bridgeError ? `${detail} MCP unavailable: ${bridgeError}.` : detail,
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
    const env = {
      ...process.env,
      LOGOSFORGE_HOST: this.host,
      LOGOSFORGE_PORT: String(this.port),
      LOGOSFORGE_WHITEBOARD_AUTH_TOKEN: this.authToken,
      LOGOSFORGE_WHITEBOARD_INSTANCE_NONCE: this.instanceNonce,
    };

    // Production: spawn the self-contained, PyInstaller-frozen backend (it embeds
    // the core — no Python needed on the user's machine).
    const frozen = this.frozenBackendPath();
    if (frozen) {
      const child = spawn(frozen, ['--host', this.host, '--port', String(this.port)], {
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
      ['-m', 'uvicorn', 'app.main:app', '--host', this.host, '--port', String(this.port)],
      { cwd: backendDir, env, stdio: 'pipe' },
    );
    this.attachChildHandlers(child, 'dev');
  }

  private attachChildHandlers(child: ChildProcess, kind: 'bundled' | 'dev'): void {
    this.child = child;

    child.stdout?.on('data', (d) => console.log('[backend]', String(d).trim()));
    child.stderr?.on('data', (d) => console.log('[backend]', String(d).trim()));

    child.on('error', (err) => {
      this.clearRuntimeDescriptor();
      this.spawnFailed = true;
      this.child = null;
      const hint = kind === 'dev' ? ' Is Python installed and are backend deps set up?' : '';
      this.setStatus({ state: 'error', detail: `Failed to start backend (${err.message}).${hint}` });
    });

    child.on('exit', (code) => {
      this.clearRuntimeDescriptor();
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
