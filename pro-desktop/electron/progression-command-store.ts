/**
 * Main-process durable store for the one unresolved Progressions command per
 * project. The packaged renderer is served from an ephemeral localhost port,
 * so origin-scoped localStorage cannot be the desktop recovery authority.
 */

import { app } from 'electron';
import { constants as fsConstants } from 'node:fs';
import * as fs from 'node:fs/promises';
import * as path from 'node:path';
import { createHash, randomUUID } from 'node:crypto';

const STORAGE_PREFIX = 'logosforge.pro.progressions.pending.v1';
const STORE_VERSION = 1 as const;
const MAX_ENVELOPE_BYTES = 128 * 1024;
const MAX_DISK_BYTES = MAX_ENVELOPE_BYTES + 4 * 1024;
const REPLACE_REFUSAL_CODES = new Set(['EEXIST', 'EPERM', 'ENOTEMPTY']);
const IDEMPOTENCY_KEY = /^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$/;
const REVISION = /^[0-9a-f]{64}$/;
const COMMAND_KINDS = new Set([
  'create_track',
  'update_track',
  'delete_track',
  'reorder_tracks',
  'create_beat',
  'update_beat',
  'delete_beat',
  'reorder_beats',
]);

interface StorageIdentity {
  storageKey: string;
  scope: string;
  projectId: number;
}

interface ParsedEnvelope {
  raw: string;
  saveKey: string;
  idempotencyKey: string;
  command: Record<string, unknown>;
  resendAttempted: boolean;
  receiptOnly: boolean;
}

interface DiskRecord {
  version: 1;
  storageKey: string;
  value: string | null;
}

type DiskRead =
  | { state: 'missing' }
  | { state: 'invalid' }
  | { state: 'parsed'; value: string | null };

let operationQueue: Promise<void> = Promise.resolve();

function isRecord(value: unknown): value is Record<string, unknown> {
  return value != null && typeof value === 'object' && !Array.isArray(value);
}

function storageIdentity(value: unknown): StorageIdentity {
  if (typeof value !== 'string' || value.length > 768) {
    throw new Error('A bounded Progressions recovery storage key is required.');
  }
  const prefix = `${STORAGE_PREFIX}:`;
  if (!value.startsWith(prefix)) throw new Error('Unknown Progressions recovery storage key.');
  const suffix = value.slice(prefix.length);
  const separator = suffix.lastIndexOf(':');
  if (separator <= 0) throw new Error('Invalid Progressions recovery storage key.');
  const encodedScope = suffix.slice(0, separator);
  const projectText = suffix.slice(separator + 1);
  if (!/^[1-9][0-9]*$/.test(projectText)) throw new Error('Invalid Progressions recovery project id.');
  const projectId = Number(projectText);
  if (!Number.isSafeInteger(projectId)) throw new Error('Invalid Progressions recovery project id.');
  let scope: string;
  try { scope = decodeURIComponent(encodedScope); } catch { throw new Error('Invalid Progressions recovery scope.'); }
  if (!scope || scope.length > 200 || encodeURIComponent(scope) !== encodedScope) {
    throw new Error('Invalid Progressions recovery scope.');
  }
  return { storageKey: value, scope, projectId };
}

function parseEnvelope(raw: unknown, identity: StorageIdentity): ParsedEnvelope {
  if (typeof raw !== 'string' || Buffer.byteLength(raw, 'utf8') > MAX_ENVELOPE_BYTES) {
    throw new Error('Progressions recovery envelope exceeds the 128 KiB safety limit.');
  }
  let value: unknown;
  try { value = JSON.parse(raw); } catch { throw new Error('Progressions recovery envelope is not valid JSON.'); }
  if (!isRecord(value)
    || value.version !== 1
    || value.scope !== identity.scope
    || typeof value.saveKey !== 'string'
    || !value.saveKey.trim()
    || value.saveKey.length > 512
    || typeof value.storedAt !== 'number'
    || !Number.isFinite(value.storedAt)
    || !isRecord(value.pending)) {
    throw new Error('Progressions recovery envelope is invalid.');
  }
  const pending = value.pending;
  if (pending.projectId !== identity.projectId
    || typeof pending.key !== 'string'
    || !IDEMPOTENCY_KEY.test(pending.key)
    || typeof pending.resendAttempted !== 'boolean'
    || typeof pending.receiptOnly !== 'boolean'
    || !isRecord(pending.command)
    || typeof pending.command.kind !== 'string'
    || !COMMAND_KINDS.has(pending.command.kind)
    || typeof pending.command.expected_revision !== 'string'
    || !REVISION.test(pending.command.expected_revision)) {
    throw new Error('Progressions recovery command is invalid.');
  }
  return {
    raw,
    saveKey: value.saveKey,
    idempotencyKey: pending.key,
    command: pending.command,
    resendAttempted: pending.resendAttempted,
    receiptOnly: pending.receiptOnly,
  };
}

function sameCommand(left: ParsedEnvelope, right: ParsedEnvelope): boolean {
  return left.saveKey === right.saveKey
    && left.idempotencyKey === right.idempotencyKey
    && JSON.stringify(left.command) === JSON.stringify(right.command);
}

function filePath(identity: StorageIdentity): string {
  const digest = createHash('sha256').update(identity.storageKey, 'utf8').digest('hex');
  return path.join(app.getPath('userData'), 'progression-command-recovery', `${digest}.json`);
}

async function readDiskFile(file: string, identity: StorageIdentity): Promise<DiskRead> {
  let raw: string;
  try {
    const stat = await fs.stat(file);
    if (stat.size > MAX_DISK_BYTES) return { state: 'invalid' };
    raw = await fs.readFile(file, 'utf8');
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return { state: 'missing' };
    throw error;
  }
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!isRecord(parsed)
      || parsed.version !== STORE_VERSION
      || parsed.storageKey !== identity.storageKey
      || (parsed.value !== null && typeof parsed.value !== 'string')) return { state: 'invalid' };
    if (typeof parsed.value === 'string') parseEnvelope(parsed.value, identity);
    return { state: 'parsed', value: parsed.value as string | null };
  } catch {
    return { state: 'invalid' };
  }
}

async function readEffective(identity: StorageIdentity): Promise<string | null> {
  const primary = await readDiskFile(filePath(identity), identity);
  if (primary.state === 'parsed') return primary.value;
  const backup = await readDiskFile(`${filePath(identity)}.bak`, identity);
  if (backup.state === 'parsed') return backup.value;
  if (primary.state === 'invalid' || backup.state === 'invalid') {
    throw new Error('Progressions recovery storage is corrupt.');
  }
  return null;
}

async function syncDirectory(directory: string): Promise<void> {
  if (process.platform === 'win32') return;
  let handle: Awaited<ReturnType<typeof fs.open>> | undefined;
  try {
    handle = await fs.open(directory, 'r');
    await handle.sync();
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code !== 'EINVAL' && code !== 'ENOTSUP' && code !== 'EPERM' && code !== 'EISDIR') throw error;
  } finally {
    await handle?.close().catch(() => undefined);
  }
}

async function durableCopy(source: string, destination: string): Promise<void> {
  await fs.copyFile(source, destination, fsConstants.COPYFILE_EXCL);
  const handle = await fs.open(destination, 'r+');
  try { await handle.sync(); } finally { await handle.close(); }
}

function isReplaceRefusal(error: unknown): boolean {
  return REPLACE_REFUSAL_CODES.has((error as NodeJS.ErrnoException).code ?? '');
}

async function replaceBackup(temporary: string, backup: string): Promise<void> {
  try {
    await fs.rename(temporary, backup);
  } catch (error) {
    if (!isReplaceRefusal(error)) throw error;
    await fs.rm(backup, { force: true });
    await fs.rename(temporary, backup);
  }
}

async function replacePrimary(temporary: string, primary: string, retired: string): Promise<void> {
  try {
    await fs.rename(temporary, primary);
    return;
  } catch (error) {
    if (!isReplaceRefusal(error)) throw error;
  }
  let retiredCurrent = false;
  let installed = false;
  try {
    try {
      await fs.rename(primary, retired);
      retiredCurrent = true;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
    }
    await fs.rename(temporary, primary);
    installed = true;
  } catch (replacementError) {
    if (retiredCurrent) {
      try {
        await fs.rename(retired, primary);
        retiredCurrent = false;
      } catch {
        // The fsynced backup remains a recoverable generation.
      }
    }
    throw replacementError;
  } finally {
    if (retiredCurrent && installed) await fs.rm(retired, { force: true }).catch(() => undefined);
  }
}

async function writeRecord(identity: StorageIdentity, value: string | null): Promise<void> {
  const primary = filePath(identity);
  const backup = `${primary}.bak`;
  const directory = path.dirname(primary);
  const temporary = path.join(directory, `.${path.basename(primary)}.${process.pid}.${randomUUID()}.tmp`);
  const backupTemporary = path.join(directory, `.${path.basename(backup)}.${process.pid}.${randomUUID()}.tmp`);
  const retired = path.join(directory, `.${path.basename(primary)}.${process.pid}.${randomUUID()}.retired`);
  const serialized = JSON.stringify({
    version: STORE_VERSION,
    storageKey: identity.storageKey,
    value,
  } satisfies DiskRecord);
  await fs.mkdir(directory, { recursive: true });
  let handle: Awaited<ReturnType<typeof fs.open>> | undefined;
  try {
    handle = await fs.open(temporary, 'wx', 0o600);
    await handle.writeFile(serialized, 'utf8');
    await handle.sync();
    await handle.close();
    handle = undefined;
    const current = await readDiskFile(primary, identity);
    if (current.state === 'parsed') {
      await durableCopy(primary, backupTemporary);
      await replaceBackup(backupTemporary, backup);
      await syncDirectory(directory);
    }
    await replacePrimary(temporary, primary, retired);
    await syncDirectory(directory);
  } finally {
    await handle?.close().catch(() => undefined);
    await fs.rm(temporary, { force: true }).catch(() => undefined);
    await fs.rm(backupTemporary, { force: true }).catch(() => undefined);
  }
}

function enqueue<T>(operation: () => Promise<T>): Promise<T> {
  const task = operationQueue.then(operation);
  operationQueue = task.then(() => undefined, () => undefined);
  return task;
}

export function loadProgressionCommandRecovery(storageKey: unknown): Promise<string | null> {
  const identity = storageIdentity(storageKey);
  return enqueue(() => readEffective(identity));
}

export function saveProgressionCommandRecovery(storageKey: unknown, raw: unknown): Promise<void> {
  const identity = storageIdentity(storageKey);
  const incoming = parseEnvelope(raw, identity);
  return enqueue(async () => {
    const currentRaw = await readEffective(identity);
    if (currentRaw != null) {
      const current = parseEnvelope(currentRaw, identity);
      if (!sameCommand(current, incoming)) {
        throw new Error('A different unresolved Progressions command already owns this project slot.');
      }
      if ((current.resendAttempted && !incoming.resendAttempted)
        || (current.receiptOnly && !incoming.receiptOnly)) {
        throw new Error('Progressions recovery safety flags cannot move backwards.');
      }
    }
    await writeRecord(identity, incoming.raw);
  });
}

export function removeProgressionCommandRecovery(
  storageKey: unknown,
  expectedRaw: unknown,
): Promise<boolean> {
  const identity = storageIdentity(storageKey);
  const expected = parseEnvelope(expectedRaw, identity);
  return enqueue(async () => {
    const currentRaw = await readEffective(identity);
    if (currentRaw == null) return true;
    const current = parseEnvelope(currentRaw, identity);
    if (!sameCommand(current, expected)) return false;
    await writeRecord(identity, null);
    return true;
  });
}

/** Await every accepted operation before normal app shutdown. */
export function drainProgressionCommandRecoveryOperations(): Promise<void> {
  return operationQueue;
}
