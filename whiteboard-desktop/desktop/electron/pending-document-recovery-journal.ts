import { randomBytes } from 'node:crypto';
import * as fs from 'node:fs';
import * as path from 'node:path';

import {
  validatePendingDocumentRecoveryJournalSnapshot,
  type PendingDocumentRecoveryJournal,
  type PendingDocumentRecoveryJournalSnapshot,
} from './pending-document-persistence';

export const PENDING_DOCUMENT_RECOVERY_JOURNAL_DIRECTORY = 'pending-document-recovery-v1';
const JOURNAL_FILE_RE = /^journal-(0*[1-9]\d*)\.json$/;
const JOURNAL_TEMP_RE = /^\.journal-\d+\.json\.\d+\.[a-f0-9]{16}\.tmp$/;
// Journal I/O is synchronous so a receipt can never precede durability. Cap
// total state at twice the per-write safety limit to bound main-thread stalls.
export const MAX_PENDING_DOCUMENT_RECOVERY_JOURNAL_BYTES = 256 * 1024 * 1024;

export interface PendingDocumentRecoveryJournalWarning {
  quarantinedPath: string;
  message: string;
}

export interface PendingDocumentRecoveryJournalOptions {
  /** Test hook for the post-rename directory durability barrier. */
  syncDirectory?: (directoryPath: string) => void;
}

function isMissing(error: unknown): boolean {
  return (error as NodeJS.ErrnoException)?.code === 'ENOENT';
}

function syncDirectory(directoryPath: string): void {
  // Windows cannot portably fsync directory handles. The journal commit point
  // there is the flushed file followed by a same-directory rename to a new,
  // previously-unused generation name.
  if (process.platform === 'win32') return;
  const fd = fs.openSync(directoryPath, 'r');
  try {
    fs.fsyncSync(fd);
  } finally {
    fs.closeSync(fd);
  }
}

function assertPrivateDirectory(directoryPath: string): void {
  fs.mkdirSync(directoryPath, { recursive: true, mode: 0o700 });
  const stats = fs.lstatSync(directoryPath);
  if (!stats.isDirectory() || stats.isSymbolicLink()) {
    throw new Error('The pending-document recovery journal path is not a private directory.');
  }
  if (process.platform !== 'win32') fs.chmodSync(directoryPath, 0o700);
}

function generationFromName(name: string): number | null {
  const match = JOURNAL_FILE_RE.exec(name);
  if (!match) return null;
  const generation = Number(match[1]);
  return Number.isSafeInteger(generation) && generation > 0 ? generation : null;
}

function generationFileName(generation: number): string {
  return `journal-${String(generation).padStart(16, '0')}.json`;
}

/**
 * Crash-safe recovery storage. Journal generations are immutable: a new state
 * is written, flushed, and renamed to a unique final name before an older
 * generation is removed. Startup always selects the highest valid generation.
 */
export class FilePendingDocumentRecoveryJournal implements PendingDocumentRecoveryJournal {
  readonly directoryPath: string;
  readonly startupWarnings: PendingDocumentRecoveryJournalWarning[] = [];
  private generation = 0;
  private initialized = false;
  private readonly flushDirectory: (directoryPath: string) => void;

  constructor(
    userDataDirectory: string,
    options: PendingDocumentRecoveryJournalOptions = {},
  ) {
    if (!path.isAbsolute(userDataDirectory)) {
      throw new Error('The pending-document recovery journal requires an absolute user-data path.');
    }
    this.directoryPath = path.join(
      userDataDirectory,
      PENDING_DOCUMENT_RECOVERY_JOURNAL_DIRECTORY,
    );
    this.flushDirectory = options.syncDirectory ?? syncDirectory;
  }

  private quarantine(filePath: string, reason: unknown): void {
    const baseName = path.basename(filePath);
    const quarantinePath = path.join(
      this.directoryPath,
      `${baseName}.quarantine-${Date.now()}-${randomBytes(6).toString('hex')}`,
    );
    try {
      fs.renameSync(filePath, quarantinePath);
      this.flushDirectory(this.directoryPath);
    } catch (error) {
      throw new AggregateError(
        [reason, error],
        `The malformed pending-document recovery journal could not be quarantined: ${filePath}`,
      );
    }
    this.startupWarnings.push({
      quarantinedPath: quarantinePath,
      message: reason instanceof Error ? reason.message : String(reason),
    });
  }

  private readGeneration(
    filePath: string,
    expectedGeneration: number,
  ): PendingDocumentRecoveryJournalSnapshot {
    const before = fs.lstatSync(filePath);
    if (
      !before.isFile()
      || before.isSymbolicLink()
      || before.size <= 0
      || before.size > MAX_PENDING_DOCUMENT_RECOVERY_JOURNAL_BYTES
    ) {
      throw new Error('Recovery journal generation is not a bounded regular file.');
    }
    const noFollow = (fs.constants as typeof fs.constants & { O_NOFOLLOW?: number }).O_NOFOLLOW ?? 0;
    let fd: number | undefined;
    try {
      fd = fs.openSync(filePath, fs.constants.O_RDONLY | noFollow);
      const opened = fs.fstatSync(fd);
      if (
        !opened.isFile()
        || opened.dev !== before.dev
        || opened.ino !== before.ino
        || opened.size !== before.size
      ) {
        throw new Error('Recovery journal generation changed while it was being opened.');
      }
      const bytes = Buffer.alloc(opened.size);
      let offset = 0;
      while (offset < bytes.length) {
        const count = fs.readSync(fd, bytes, offset, bytes.length - offset, offset);
        if (count === 0) break;
        offset += count;
      }
      if (offset !== bytes.length) throw new Error('Recovery journal generation was truncated.');
      const decoded: unknown = JSON.parse(bytes.toString('utf8'));
      if (!decoded || typeof decoded !== 'object' || Array.isArray(decoded)) {
        throw new Error('Recovery journal generation has an invalid envelope.');
      }
      const envelope = decoded as Record<string, unknown>;
      if (envelope.generation !== expectedGeneration) {
        throw new Error('Recovery journal filename and generation do not match.');
      }
      return validatePendingDocumentRecoveryJournalSnapshot(envelope.snapshot);
    } finally {
      if (fd !== undefined) fs.closeSync(fd);
    }
  }

  load(): PendingDocumentRecoveryJournalSnapshot | null {
    if (this.initialized) {
      throw new Error('The pending-document recovery journal was loaded more than once.');
    }
    try {
      assertPrivateDirectory(this.directoryPath);
    } catch (error) {
      if (isMissing(error)) return null;
      throw error;
    }

    const directoryEntries = fs.readdirSync(this.directoryPath, { withFileTypes: true });
    // A crash before the final rename can leave a private temp file. It can
    // never be authoritative and is safe to remove without following links.
    for (const entry of directoryEntries) {
      if (!JOURNAL_TEMP_RE.test(entry.name)) continue;
      const tempPath = path.join(this.directoryPath, entry.name);
      if (entry.isSymbolicLink()) {
        this.quarantine(tempPath, new Error('Recovery journal temp path is a symbolic link.'));
        continue;
      }
      if (!entry.isFile()) continue;
      try {
        fs.rmSync(tempPath, { force: true });
      } catch (error) {
        console.error('[persistence] could not remove a stale recovery journal temp file:', error);
      }
    }

    const candidates = directoryEntries
      .map((entry) => ({ entry, generation: generationFromName(entry.name) }))
      .filter((candidate): candidate is { entry: fs.Dirent; generation: number } => (
        candidate.generation !== null
      ))
      .sort((a, b) => b.generation - a.generation);

    let recovered: PendingDocumentRecoveryJournalSnapshot | null = null;
    for (const { entry, generation } of candidates) {
      this.generation = Math.max(this.generation, generation);
      const filePath = path.join(this.directoryPath, entry.name);
      try {
        if (entry.name !== generationFileName(generation)) {
          throw new Error('Recovery journal generation has a non-canonical filename.');
        }
        if (!entry.isFile() || entry.isSymbolicLink()) {
          throw new Error('Recovery journal generation is not a regular file.');
        }
        const candidate = this.readGeneration(filePath, generation);
        if (!recovered) recovered = candidate;
      } catch (error) {
        this.quarantine(filePath, error);
      }
    }
    this.initialized = true;
    return recovered;
  }

  replace(snapshotValue: PendingDocumentRecoveryJournalSnapshot): void {
    if (!this.initialized) {
      throw new Error('The pending-document recovery journal must be loaded before it is replaced.');
    }
    const snapshot = validatePendingDocumentRecoveryJournalSnapshot(snapshotValue);
    assertPrivateDirectory(this.directoryPath);
    if (this.generation >= Number.MAX_SAFE_INTEGER) {
      throw new Error('The pending-document recovery journal generation is exhausted.');
    }
    const generation = this.generation + 1;
    const finalPath = path.join(this.directoryPath, generationFileName(generation));
    const temporaryPath = path.join(
      this.directoryPath,
      `.${generationFileName(generation)}.${process.pid}.${randomBytes(8).toString('hex')}.tmp`,
    );
    const content = JSON.stringify({ generation, snapshot });
    if (Buffer.byteLength(content, 'utf8') > MAX_PENDING_DOCUMENT_RECOVERY_JOURNAL_BYTES) {
      throw new Error('The pending-document recovery journal exceeds its safety limit.');
    }

    let fd: number | undefined;
    try {
      fd = fs.openSync(temporaryPath, 'wx', 0o600);
      fs.writeFileSync(fd, content, { encoding: 'utf8' });
      fs.fsyncSync(fd);
      fs.closeSync(fd);
      fd = undefined;
      if (process.platform !== 'win32') fs.chmodSync(temporaryPath, 0o600);
      fs.renameSync(temporaryPath, finalPath);
      this.generation = generation;
      // Advance the immutable generation immediately so even a post-rename
      // durability error can never make a retry overwrite this visible file.
      // Unlike an ordinary export, a recovery receipt must not be published
      // until the directory entry is durably established on POSIX.
      try {
        this.flushDirectory(this.directoryPath);
      } catch (error) {
        throw new AggregateError(
          [error],
          'Could not make the pending-document recovery journal durable.',
        );
      }
    } finally {
      if (fd !== undefined) fs.closeSync(fd);
      try { fs.rmSync(temporaryPath, { force: true }); } catch { /* best effort */ }
    }

    // The new immutable generation is already the commit point. Cleanup cannot
    // turn a successful replacement into a reported failure.
    try {
      const generations = fs.readdirSync(this.directoryPath, { withFileTypes: true })
        .map((entry) => ({ entry, generation: generationFromName(entry.name) }))
        .filter((candidate): candidate is { entry: fs.Dirent; generation: number } => (
          candidate.generation !== null
          && candidate.entry.name === generationFileName(candidate.generation)
        ))
        .sort((a, b) => b.generation - a.generation);
      const retainedFallback = generations.find((candidate) => candidate.generation < generation)
        ?.generation;
      for (const { entry, generation: oldGeneration } of generations) {
        if (oldGeneration >= generation || oldGeneration === retainedFallback) continue;
        const oldPath = path.join(this.directoryPath, entry.name);
        const stats = fs.lstatSync(oldPath);
        if (!stats.isFile() || stats.isSymbolicLink()) continue;
        fs.rmSync(oldPath);
      }
      this.flushDirectory(this.directoryPath);
    } catch (error) {
      console.error('[persistence] could not clean an older recovery journal generation:', error);
    }
  }
}
