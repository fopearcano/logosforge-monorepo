/** Import files cross an IPC boundary as one string, so reject non-files and
 * oversized inputs before allocating/reading them in the main process. */

import { constants, promises as fs } from 'node:fs';

/**
 * A max-sized whiteboard conflict v1 contains one max-sized pending patch plus
 * its merged document (the format intentionally duplicates both for recovery
 * auditability). Rescue exporters use compact JSON, leaving one MiB for the
 * fixed envelope. Keep this shared by main's pre-read guard and renderer parse.
 */
export const MAX_PENDING_DOCUMENT_PAYLOAD_BYTES = 128 * 1024 * 1024;
export const MAX_RECOVERY_IMPORT_FILE_BYTES =
  (2 * MAX_PENDING_DOCUMENT_PAYLOAD_BYTES) + (1024 * 1024);

export interface ImportFileMetadata {
  size: number;
  isFile: () => boolean;
  dev?: number | bigint;
  ino?: number | bigint;
  mtimeMs?: number;
  ctimeMs?: number;
}

export interface ImportFileHandle {
  stat: () => Promise<ImportFileMetadata>;
  read: (
    buffer: Uint8Array,
    offset: number,
    length: number,
    position: number,
  ) => Promise<{ bytesRead: number }>;
  close: () => Promise<void>;
}

export interface ImportFileSystem {
  lstat: (filePath: string) => Promise<ImportFileMetadata>;
  open: (filePath: string, flags: number) => Promise<ImportFileHandle>;
}

const defaultFileSystem: ImportFileSystem = {
  lstat: (filePath) => fs.lstat(filePath),
  open: (filePath, flags) => fs.open(filePath, flags),
};

export function assertImportFileMetadata(metadata: ImportFileMetadata): void {
  if (!metadata.isFile()) {
    throw new Error('The selected import path is not a regular file.');
  }
  if (!Number.isSafeInteger(metadata.size) || metadata.size < 0) {
    throw new Error('The selected import file has an invalid size.');
  }
  if (metadata.size > MAX_RECOVERY_IMPORT_FILE_BYTES) {
    throw new Error('The selected import file is larger than the 257 MiB safety limit.');
  }
}

function sameFileIdentity(left: ImportFileMetadata, right: ImportFileMetadata): boolean {
  // Node supplies dev+ino on supported local filesystems. If a platform cannot,
  // O_NOFOLLOW (when available), regular-file checks, and the same open handle
  // still preserve the bounded-allocation guarantee.
  if (left.dev === undefined || left.ino === undefined || right.dev === undefined || right.ino === undefined) {
    return true;
  }
  return left.dev === right.dev && left.ino === right.ino;
}

export function assertImportFileIdentity(
  selected: ImportFileMetadata,
  opened: ImportFileMetadata,
  currentPath: ImportFileMetadata,
): void {
  assertImportFileMetadata(selected);
  assertImportFileMetadata(opened);
  assertImportFileMetadata(currentPath);
  if (!sameFileIdentity(selected, opened) || !sameFileIdentity(opened, currentPath)) {
    throw new Error('The selected import file changed before it could be read.');
  }
}

/** Read exactly the fstat-bounded bytes from one already-open descriptor. */
export async function readBoundedImportHandle(
  handle: ImportFileHandle,
  opened: ImportFileMetadata,
): Promise<string> {
  assertImportFileMetadata(opened);
  const buffer = Buffer.allocUnsafe(opened.size + 1);
  let offset = 0;
  while (offset < buffer.length) {
    const { bytesRead } = await handle.read(buffer, offset, buffer.length - offset, offset);
    if (!bytesRead) break;
    offset += bytesRead;
  }
  const final = await handle.stat();
  if (
    offset !== opened.size
    || final.size !== opened.size
    || (opened.mtimeMs !== undefined && final.mtimeMs !== opened.mtimeMs)
    || (opened.ctimeMs !== undefined && final.ctimeMs !== opened.ctimeMs)
  ) {
    throw new Error('The selected import file changed size or contents while it was being read.');
  }
  return buffer.subarray(0, offset).toString('utf8');
}

/**
 * Reject symlinks/non-files, bind validation and bytes to one fd, and never
 * allocate beyond the recovery-envelope cap. O_NOFOLLOW closes the path-swap
 * gap on platforms that expose it; dev+ino checks cover ordinary swaps too.
 */
export async function readBoundedImportTextFile(
  filePath: string,
  fileSystem: ImportFileSystem = defaultFileSystem,
): Promise<string> {
  const selected = await fileSystem.lstat(filePath);
  assertImportFileMetadata(selected);
  const noFollow = typeof constants.O_NOFOLLOW === 'number' ? constants.O_NOFOLLOW : 0;
  const handle = await fileSystem.open(filePath, constants.O_RDONLY | noFollow);
  try {
    const opened = await handle.stat();
    const currentPath = await fileSystem.lstat(filePath);
    assertImportFileIdentity(selected, opened, currentPath);
    return await readBoundedImportHandle(handle, opened);
  } finally {
    await handle.close();
  }
}
