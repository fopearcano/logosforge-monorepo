import { createHash, randomBytes } from 'node:crypto';
import * as fs from 'node:fs';
import * as path from 'node:path';

export const MCP_RUNTIME_FILENAME = 'mcp-runtime-v1.json';
const MAX_RUNTIME_DESCRIPTOR_BYTES = 16 * 1024;

export interface RuntimeDescriptor {
  schema_version: 1;
  base_url: string;
  auth_token: string;
  instance_nonce: string;
  app_pid: number;
  backend_pid: number;
  created_at: string;
}

type RuntimeEnvironment = Record<string, string | undefined>;

function fileDigest(filePath: string): string {
  return createHash('sha256').update(fs.readFileSync(filePath)).digest('hex');
}

export function runtimeDescriptorPath(
  userDataDir: string,
  environ: RuntimeEnvironment = process.env,
): string {
  const override = environ.LOGOSFORGE_WHITEBOARD_MCP_CONNECTION_FILE?.trim();
  if (override) {
    if (!path.isAbsolute(override) || path.basename(override) !== MCP_RUNTIME_FILENAME) {
      throw new Error(
        `The Whiteboard MCP connection-file override must be an absolute ${MCP_RUNTIME_FILENAME} path.`,
      );
    }
    return override;
  }
  return path.join(userDataDir, MCP_RUNTIME_FILENAME);
}

export function mcpCompanionPath(
  userDataDir: string,
  executableName: string,
  environ: RuntimeEnvironment = process.env,
): string {
  const override = environ.LOGOSFORGE_WHITEBOARD_MCP_LAUNCHER_PATH?.trim();
  if (override) {
    if (!path.isAbsolute(override) || path.basename(override) !== executableName) {
      throw new Error(
        `The Whiteboard MCP launcher override must be an absolute ${executableName} path.`,
      );
    }
    return override;
  }
  return path.join(userDataDir, 'mcp', executableName);
}

/** Copy the packaged console companion to the user's stable private path. */
export function installMcpCompanion(sourcePath: string, targetPath: string): boolean {
  if (!path.isAbsolute(sourcePath) || !path.isAbsolute(targetPath)) {
    throw new Error('MCP companion paths must be absolute.');
  }
  const source = fs.lstatSync(sourcePath);
  if (!source.isFile() || source.isSymbolicLink() || source.size <= 0) {
    throw new Error('The packaged MCP companion is missing or invalid.');
  }
  let existingTarget: fs.Stats | null = null;
  try {
    const target = fs.lstatSync(targetPath);
    if (!target.isFile() || target.isSymbolicLink()) {
      throw new Error('The MCP companion target must be a regular, non-symlink file.');
    }
    existingTarget = target;
    if (
      target.size === source.size
      && fileDigest(targetPath) === fileDigest(sourcePath)
    ) {
      if (process.platform !== 'win32') fs.chmodSync(targetPath, 0o700);
      return false;
    }
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
  }

  const parent = path.dirname(targetPath);
  fs.mkdirSync(parent, { recursive: true, mode: 0o700 });
  const temporaryPath = path.join(
    parent,
    `.${path.basename(targetPath)}.${process.pid}.${randomBytes(8).toString('hex')}.tmp`,
  );
  try {
    fs.copyFileSync(sourcePath, temporaryPath, fs.constants.COPYFILE_EXCL);
    if (process.platform !== 'win32') fs.chmodSync(temporaryPath, 0o700);
    const fd = fs.openSync(temporaryPath, 'r+');
    try { fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
    if (existingTarget) {
      const current = fs.lstatSync(targetPath);
      if (
        !current.isFile()
        || current.isSymbolicLink()
        || current.dev !== existingTarget.dev
        || current.ino !== existingTarget.ino
      ) {
        throw new Error('The MCP companion target changed during installation.');
      }
    }
    try {
      fs.renameSync(temporaryPath, targetPath);
    } catch (error) {
      const code = (error as NodeJS.ErrnoException).code;
      if (process.platform !== 'win32' || !['EEXIST', 'EPERM'].includes(code ?? '')) {
        throw error;
      }
      if (!existingTarget) throw error;
      const current = fs.lstatSync(targetPath);
      if (
        !current.isFile()
        || current.isSymbolicLink()
        || current.dev !== existingTarget.dev
        || current.ino !== existingTarget.ino
      ) {
        throw new Error('The MCP companion target changed during installation.');
      }
      fs.rmSync(targetPath, { force: true });
      fs.renameSync(temporaryPath, targetPath);
    }
    if (process.platform !== 'win32') fs.chmodSync(targetPath, 0o700);
    return true;
  } finally {
    try { fs.rmSync(temporaryPath, { force: true }); } catch { /* best effort */ }
  }
}

/** Write credentials through a private same-directory temporary file. */
export function writeRuntimeDescriptor(
  targetPath: string,
  descriptor: RuntimeDescriptor,
): void {
  if (!path.isAbsolute(targetPath)) {
    throw new Error('The MCP runtime descriptor path must be absolute.');
  }
  const parent = path.dirname(targetPath);
  fs.mkdirSync(parent, { recursive: true, mode: 0o700 });
  const temporaryPath = path.join(
    parent,
    `.${path.basename(targetPath)}.${process.pid}.${randomBytes(8).toString('hex')}.tmp`,
  );
  let fd: number | undefined;
  try {
    // Never overwrite an unrelated file selected by a mistyped environment
    // override. Existing targets must already be valid v1 runtime descriptors.
    inspectRuntimeDescriptor(targetPath);
    fd = fs.openSync(temporaryPath, 'wx', 0o600);
    fs.writeFileSync(fd, JSON.stringify(descriptor), { encoding: 'utf8' });
    fs.fsyncSync(fd);
    fs.closeSync(fd);
    fd = undefined;
    if (process.platform !== 'win32') fs.chmodSync(temporaryPath, 0o600);
    try {
      fs.renameSync(temporaryPath, targetPath);
    } catch (error) {
      const code = (error as NodeJS.ErrnoException).code;
      if (process.platform !== 'win32' || !['EEXIST', 'EPERM'].includes(code ?? '')) {
        throw error;
      }
      // Windows cannot atomically replace an existing file. Revalidate before
      // removing the exact destination so a symlink, directory, or unrelated
      // file is never deleted as part of the fallback.
      removeRuntimeDescriptor(targetPath);
      fs.renameSync(temporaryPath, targetPath);
    }
    if (process.platform !== 'win32') fs.chmodSync(targetPath, 0o600);
  } finally {
    if (fd !== undefined) fs.closeSync(fd);
    try { fs.rmSync(temporaryPath, { force: true }); } catch { /* best effort */ }
  }
}

interface InspectedRuntimeDescriptor {
  descriptor: RuntimeDescriptor;
  stats: fs.Stats;
}

function isPositivePid(value: unknown): value is number {
  return Number.isSafeInteger(value) && (value as number) > 0;
}

function isLoopbackBaseUrl(value: unknown): value is string {
  if (typeof value !== 'string' || !value) return false;
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    return false;
  }
  const port = Number(parsed.port);
  return parsed.protocol === 'http:'
    && ['127.0.0.1', '::1', '[::1]'].includes(parsed.hostname)
    && Number.isInteger(port)
    && port >= 1
    && port <= 65535
    && parsed.username.length === 0
    && parsed.password.length === 0
    && parsed.pathname === '/'
    && parsed.search.length === 0
    && parsed.hash.length === 0;
}

function isRuntimeDescriptor(value: unknown): value is RuntimeDescriptor {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const descriptor = value as Record<string, unknown>;
  return descriptor.schema_version === 1
    && isLoopbackBaseUrl(descriptor.base_url)
    && typeof descriptor.auth_token === 'string'
    && descriptor.auth_token.length >= 32
    && descriptor.auth_token === descriptor.auth_token.trim()
    && typeof descriptor.instance_nonce === 'string'
    && descriptor.instance_nonce.length >= 16
    && descriptor.instance_nonce === descriptor.instance_nonce.trim()
    && isPositivePid(descriptor.app_pid)
    && isPositivePid(descriptor.backend_pid)
    && typeof descriptor.created_at === 'string'
    && descriptor.created_at.endsWith('Z')
    && Number.isFinite(Date.parse(descriptor.created_at));
}

/** Read an existing target without following symlinks or accepting arbitrary data. */
function inspectRuntimeDescriptor(targetPath: string): InspectedRuntimeDescriptor | null {
  if (!path.isAbsolute(targetPath)) {
    throw new Error('The MCP runtime descriptor path must be absolute.');
  }

  let before: fs.Stats;
  try {
    before = fs.lstatSync(targetPath);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return null;
    throw new Error('Cannot inspect the MCP runtime descriptor safely.');
  }
  if (
    !before.isFile()
    || before.isSymbolicLink()
    || before.size <= 0
    || before.size > MAX_RUNTIME_DESCRIPTOR_BYTES
  ) {
    throw new Error('Cannot verify MCP runtime descriptor ownership.');
  }

  const noFollow = (fs.constants as typeof fs.constants & { O_NOFOLLOW?: number }).O_NOFOLLOW ?? 0;
  let readFd: number | undefined;
  try {
    readFd = fs.openSync(targetPath, fs.constants.O_RDONLY | noFollow);
    const opened = fs.fstatSync(readFd);
    if (
      !opened.isFile()
      || opened.dev !== before.dev
      || opened.ino !== before.ino
      || opened.size <= 0
      || opened.size > MAX_RUNTIME_DESCRIPTOR_BYTES
    ) {
      throw new Error('Cannot verify MCP runtime descriptor ownership.');
    }
    const buffer = Buffer.alloc(MAX_RUNTIME_DESCRIPTOR_BYTES + 1);
    let bytesRead = 0;
    while (bytesRead < buffer.length) {
      const count = fs.readSync(
        readFd,
        buffer,
        bytesRead,
        buffer.length - bytesRead,
        bytesRead,
      );
      if (count === 0) break;
      bytesRead += count;
    }
    if (bytesRead <= 0 || bytesRead > MAX_RUNTIME_DESCRIPTOR_BYTES) {
      throw new Error('Cannot verify MCP runtime descriptor ownership.');
    }
    const value: unknown = JSON.parse(buffer.subarray(0, bytesRead).toString('utf8'));
    if (!isRuntimeDescriptor(value)) {
      throw new Error('Cannot verify MCP runtime descriptor ownership.');
    }
    return { descriptor: value, stats: opened };
  } catch {
    throw new Error('Cannot verify MCP runtime descriptor ownership.');
  } finally {
    if (readFd !== undefined) fs.closeSync(readFd);
  }
}

/**
 * Remove a descriptor. Normal shutdown is nonce-guarded so an older process
 * cannot delete a replacement session; startup cleanup owns the exact path and
 * may remove a crash leftover without a nonce.
 */
export function removeRuntimeDescriptor(
  targetPath: string,
  expectedNonce?: string,
): boolean {
  const inspected = inspectRuntimeDescriptor(targetPath);
  if (!inspected) return false;
  if (
    expectedNonce !== undefined
    && inspected.descriptor.instance_nonce !== expectedNonce
  ) return false;
  const current = fs.lstatSync(targetPath);
  if (
    !current.isFile()
    || current.isSymbolicLink()
    || current.dev !== inspected.stats.dev
    || current.ino !== inspected.stats.ino
  ) {
    throw new Error('Cannot verify MCP runtime descriptor ownership.');
  }
  fs.rmSync(targetPath, { force: true });
  return true;
}
