/** Bounded, identity-stable reads for untrusted provider-folder snapshots. */

import { constants, promises as fs } from 'node:fs';

// The core caps its portable project payload at 128 MiB. The immutable cloud
// envelope adds only fixed transport metadata; one MiB keeps both boundaries
// coherent without permitting an unbounded main-process allocation.
export const MAX_PRO_PROJECT_SNAPSHOT_BYTES = 128 * 1024 * 1024;
export const MAX_PRO_CLOUD_SNAPSHOT_BYTES = MAX_PRO_PROJECT_SNAPSHOT_BYTES + (1024 * 1024);

export interface BoundedFileMetadata {
  size: number;
  isFile(): boolean;
  isSymbolicLink?(): boolean;
  dev?: number | bigint;
  ino?: number | bigint;
  mtimeMs?: number;
  ctimeMs?: number;
}

export interface BoundedFileHandle {
  stat(): Promise<BoundedFileMetadata>;
  read(
    buffer: Uint8Array,
    offset: number,
    length: number,
    position: number,
  ): Promise<{ bytesRead: number }>;
  close(): Promise<void>;
}

export interface BoundedFileSystem {
  lstat(filePath: string): Promise<BoundedFileMetadata>;
  open(filePath: string, flags: number): Promise<BoundedFileHandle>;
}

const systemFileSystem: BoundedFileSystem = {
  lstat: (filePath) => fs.lstat(filePath),
  open: (filePath, flags) => fs.open(filePath, flags),
};

function validateMetadata(metadata: BoundedFileMetadata, maxBytes: number): void {
  if (!metadata.isFile() || metadata.isSymbolicLink?.()) {
    throw new Error('The cloud snapshot path is not a regular file.');
  }
  if (!Number.isSafeInteger(metadata.size) || metadata.size < 0 || metadata.size > maxBytes) {
    throw new Error(`The cloud snapshot exceeds the ${Math.floor(maxBytes / (1024 * 1024))} MiB safety limit.`);
  }
}

function sameIdentity(left: BoundedFileMetadata, right: BoundedFileMetadata): boolean {
  if (left.dev === undefined || left.ino === undefined
    || right.dev === undefined || right.ino === undefined) return true;
  return left.dev === right.dev && left.ino === right.ino;
}

export async function readBoundedTextFile(
  filePath: string,
  maxBytes = MAX_PRO_CLOUD_SNAPSHOT_BYTES,
  fileSystem: BoundedFileSystem = systemFileSystem,
): Promise<string> {
  const selected = await fileSystem.lstat(filePath);
  validateMetadata(selected, maxBytes);
  const noFollow = typeof constants.O_NOFOLLOW === 'number' ? constants.O_NOFOLLOW : 0;
  const handle = await fileSystem.open(filePath, constants.O_RDONLY | noFollow);
  try {
    const opened = await handle.stat();
    const currentPath = await fileSystem.lstat(filePath);
    validateMetadata(opened, maxBytes);
    validateMetadata(currentPath, maxBytes);
    if (!sameIdentity(selected, opened) || !sameIdentity(opened, currentPath)) {
      throw new Error('The cloud snapshot changed before it could be read.');
    }

    // One extra byte detects growth without allocating beyond the hard bound.
    const buffer = Buffer.allocUnsafe(opened.size + 1);
    let offset = 0;
    while (offset < buffer.length) {
      const { bytesRead } = await handle.read(buffer, offset, buffer.length - offset, offset);
      if (!bytesRead) break;
      offset += bytesRead;
    }
    const final = await handle.stat();
    if (offset !== opened.size || final.size !== opened.size
      || (opened.mtimeMs !== undefined && final.mtimeMs !== opened.mtimeMs)
      || (opened.ctimeMs !== undefined && final.ctimeMs !== opened.ctimeMs)) {
      throw new Error('The cloud snapshot changed while it was being read.');
    }
    return buffer.subarray(0, offset).toString('utf8');
  } finally {
    await handle.close();
  }
}
