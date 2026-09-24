import { createHash, randomBytes } from 'node:crypto';
import * as fs from 'node:fs';
import * as path from 'node:path';

export const MCP_RUNTIME_FILENAME = 'mcp-runtime-v1.json';

export interface RuntimeDescriptor {
  schema_version: 1;
  base_url: string;
  auth_token: string;
  instance_nonce: string;
  app_pid: number;
  core_pid: number;
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
  const override = environ.LOGOSFORGE_MCP_CONNECTION_FILE?.trim();
  return override || path.join(userDataDir, MCP_RUNTIME_FILENAME);
}

export function mcpCompanionPath(
  userDataDir: string,
  executableName: string,
  environ: RuntimeEnvironment = process.env,
): string {
  const override = environ.LOGOSFORGE_MCP_LAUNCHER_PATH?.trim();
  return override || path.join(userDataDir, 'mcp', executableName);
}

/** Copy the packaged console companion to the user's stable private path. */
export function installMcpCompanion(sourcePath: string, targetPath: string): boolean {
  if (!path.isAbsolute(sourcePath) || !path.isAbsolute(targetPath)) {
    throw new Error('MCP companion paths must be absolute.');
  }
  const source = fs.statSync(sourcePath);
  if (!source.isFile() || source.size <= 0) {
    throw new Error('The packaged MCP companion is missing or invalid.');
  }
  try {
    const target = fs.lstatSync(targetPath);
    if (
      target.isFile()
      && !target.isSymbolicLink()
      && target.size === source.size
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
    try {
      fs.renameSync(temporaryPath, targetPath);
    } catch (error) {
      const code = (error as NodeJS.ErrnoException).code;
      if (process.platform !== 'win32' || !['EEXIST', 'EPERM'].includes(code ?? '')) {
        throw error;
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
      // Windows cannot always atomically replace an existing destination.
      // Remove only this exact descriptor path, then complete the same-dir move.
      removeRuntimeDescriptor(targetPath);
      fs.renameSync(temporaryPath, targetPath);
    }
    if (process.platform !== 'win32') fs.chmodSync(targetPath, 0o600);
  } finally {
    if (fd !== undefined) fs.closeSync(fd);
    try { fs.rmSync(temporaryPath, { force: true }); } catch { /* best effort */ }
  }
}

/**
 * Remove a descriptor. During normal shutdown the nonce guard prevents an old
 * process from deleting a replacement session. An unguarded call is reserved
 * for startup cleanup of this application's exact user-data path.
 */
export function removeRuntimeDescriptor(
  targetPath: string,
  expectedNonce?: string,
): boolean {
  if (!fs.existsSync(targetPath)) return false;
  if (expectedNonce !== undefined) {
    let actualNonce: unknown;
    try {
      const info = fs.lstatSync(targetPath);
      if (!info.isFile() || info.isSymbolicLink() || info.size > 16 * 1024) {
        throw new Error('unsafe descriptor');
      }
      const value: unknown = JSON.parse(fs.readFileSync(targetPath, 'utf8'));
      actualNonce = value && typeof value === 'object'
        ? (value as { instance_nonce?: unknown }).instance_nonce
        : undefined;
    } catch {
      throw new Error('Cannot verify MCP runtime descriptor ownership.');
    }
    if (actualNonce !== expectedNonce) return false;
  }
  fs.rmSync(targetPath, { force: true });
  return true;
}
