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
    // Windows does not support opening directory handles through fs.open in a
    // portable way. The flushed file plus MoveFileEx-backed rename are the
    // appropriate guarantees there; POSIX filesystems can additionally flush
    // the directory entry after the rename.
    if (process.platform === 'win32') return;
    const handle = await fs.open(directoryPath, 'r');
    try {
      await handle.sync();
    } finally {
      await handle.close();
    }
  },
};

function createSystemTempPath(destinationPath: string): string {
  const directory = path.dirname(destinationPath);
  const fileName = path.basename(destinationPath);
  return path.join(directory, `.${fileName}.${process.pid}.${randomUUID()}.tmp`);
}

function isAlreadyExistsError(error: unknown): boolean {
  return !!error
    && typeof error === 'object'
    && 'code' in error
    && (error as { code?: unknown }).code === 'EEXIST';
}

async function removeTempFile(fileSystem: AtomicFileSystem, tempPath: string): Promise<void> {
  try {
    await fileSystem.remove(tempPath);
  } catch (error) {
    if (
      !error
      || typeof error !== 'object'
      || !('code' in error)
      || (error as { code?: unknown }).code !== 'ENOENT'
    ) {
      console.error('[files] could not clean up atomic-save temp file:', error);
    }
  }
}

/**
 * Replace a text file with a single same-directory rename. The destination is
 * never opened or truncated: every fallible write/flush/close step happens on
 * a uniquely-created temp file first.
 */
export async function atomicWriteTextFile(
  destinationPath: string,
  content: string,
  options: AtomicWriteOptions = {},
): Promise<void> {
  const fileSystem = options.fileSystem ?? systemFileSystem;
  const createTempPath = options.createTempPath
    ?? ((filePath: string) => createSystemTempPath(filePath));
  let handle: AtomicWriteHandle | null = null;
  let tempPath = '';

  for (let attempt = 0; attempt < MAX_TEMP_PATH_ATTEMPTS; attempt += 1) {
    tempPath = createTempPath(destinationPath, attempt);
    try {
      handle = await fileSystem.openExclusive(tempPath);
      break;
    } catch (error) {
      if (!isAlreadyExistsError(error)) throw error;
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
      try {
        await handle.close();
      } catch {
        // Preserve the primary save failure; cleanup below remains best-effort.
      }
    }
    await removeTempFile(fileSystem, tempPath);
    throw error;
  }

  // The rename is the commit point. A directory-sync failure cannot be
  // reported as a failed save because the destination has already changed.
  try {
    await fileSystem.syncDirectory(path.dirname(destinationPath));
  } catch (error) {
    try {
      options.onDirectorySyncError?.(error);
    } catch (reportingError) {
      console.error('[files] directory-sync error reporter failed:', reportingError);
    }
  }
}
