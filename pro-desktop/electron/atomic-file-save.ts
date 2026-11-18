import { randomUUID } from 'node:crypto';
import * as path from 'node:path';
import { promises as fs } from 'node:fs';

export interface AtomicWriteHandle {
  writeText(content: string): Promise<void>;
  sync(): Promise<void>;
  close(): Promise<void>;
}

export interface AtomicFileSystem {
  openExclusive(filePath: string): Promise<AtomicWriteHandle>;
  rename(sourcePath: string, destinationPath: string): Promise<void>;
  remove(filePath: string): Promise<void>;
  syncDirectory(directoryPath: string): Promise<void>;
}

export interface AtomicWriteOptions {
  fileSystem?: AtomicFileSystem;
  createTempPath?: (destinationPath: string, attempt: number) => string;
  onDirectorySyncError?: (error: unknown) => void;
}

const MAX_TEMP_PATH_ATTEMPTS = 16;

const systemFileSystem: AtomicFileSystem = {
  async openExclusive(filePath) {
    const handle = await fs.open(filePath, 'wx', 0o666);
    return {
      writeText: (content) => handle.writeFile(content, 'utf8'),
      sync: () => handle.sync(),
      close: () => handle.close(),
    };
  },
  rename: (sourcePath, destinationPath) => fs.rename(sourcePath, destinationPath),
  remove: (filePath) => fs.unlink(filePath),
  async syncDirectory(directoryPath) {
    // Windows cannot portably fsync directory handles. The flushed file and
    // MoveFileEx-backed rename remain the commit guarantee there.
    if (process.platform === 'win32') return;
    const handle = await fs.open(directoryPath, 'r');
    try {
      await handle.sync();
    } finally {
      await handle.close();
    }
  },
};

function systemTempPath(destinationPath: string): string {
  return path.join(
    path.dirname(destinationPath),
    `.${path.basename(destinationPath)}.${process.pid}.${randomUUID()}.tmp`,
  );
}

function hasCode(error: unknown, code: string): boolean {
  return !!error && typeof error === 'object' && 'code' in error
    && (error as { code?: unknown }).code === code;
}

async function removeTempFile(fileSystem: AtomicFileSystem, tempPath: string): Promise<void> {
  try {
    await fileSystem.remove(tempPath);
  } catch (error) {
    if (!hasCode(error, 'ENOENT')) {
      console.error('[cloud-sync] could not clean up an atomic-save temporary file:', error);
    }
  }
}

/** Replace a text file through one same-directory rename after fsyncing it. */
export async function atomicWriteTextFile(
  destinationPath: string,
  content: string,
  options: AtomicWriteOptions = {},
): Promise<void> {
  const fileSystem = options.fileSystem ?? systemFileSystem;
  const createTempPath = options.createTempPath
    ?? ((filePath: string) => systemTempPath(filePath));
  let handle: AtomicWriteHandle | null = null;
  let tempPath = '';

  for (let attempt = 0; attempt < MAX_TEMP_PATH_ATTEMPTS; attempt += 1) {
    tempPath = createTempPath(destinationPath, attempt);
    try {
      handle = await fileSystem.openExclusive(tempPath);
      break;
    } catch (error) {
      if (!hasCode(error, 'EEXIST')) throw error;
    }
  }
  if (!handle) throw new Error('Could not allocate a unique temporary file for saving.');

  try {
    await handle.writeText(content);
    await handle.sync();
    await handle.close();
    handle = null;
    await fileSystem.rename(tempPath, destinationPath);
  } catch (error) {
    if (handle) {
      try { await handle.close(); } catch { /* preserve the primary failure */ }
    }
    await removeTempFile(fileSystem, tempPath);
    throw error;
  }

  // The rename is the commit point. A later directory-fsync failure cannot be
  // represented as a failed write because the destination has already changed.
  try {
    await fileSystem.syncDirectory(path.dirname(destinationPath));
  } catch (error) {
    try { options.onDirectorySyncError?.(error); } catch { /* reporting only */ }
  }
}
