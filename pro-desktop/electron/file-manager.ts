/**
 * File / layout manager — the host side of the PlatformAdapter the renderer
 * injects into pro-shared-ui. Open/save dialogs, openExternal, and opaque
 * per-project layout persistence (for the dockable workspace).
 */

import { app, BrowserWindow, dialog, shell } from 'electron';
import { constants as fsConstants } from 'node:fs';
import * as fs from 'node:fs/promises';
import * as path from 'node:path';
import { randomUUID } from 'node:crypto';

import { normalizeExternalUrl, requireProjectId } from './security';

export interface DialogFilter {
  name: string;
  extensions: string[];
}
export interface OpenFileResult {
  canceled: boolean;
  path?: string;
  content?: string;
  /** raw file bytes base64-encoded — for binary imports (.docx) a utf8 read corrupts. */
  contentBase64?: string;
}
export interface SaveFileResult {
  canceled: boolean;
  path?: string;
}

export async function openFile(win: BrowserWindow | null, filters?: DialogFilter[]): Promise<OpenFileResult> {
  const r = await dialog.showOpenDialog(win ?? undefined!, {
    properties: ['openFile'],
    filters: filters && filters.length ? filters : undefined,
  });
  const fp = r.filePaths[0];
  if (r.canceled || !fp) return { canceled: true };
  try {
    // Read once as raw bytes, then expose BOTH a utf8 view (text imports) and a
    // base64 view (binary imports like .docx a utf8 read would corrupt).
    const buf = await fs.readFile(fp);
    return { canceled: false, path: fp, content: buf.toString('utf8'), contentBase64: buf.toString('base64') };
  } catch {
    return { canceled: false, path: fp };
  }
}

function saveFilters(suggestedName?: string): DialogFilter[] | undefined {
  const ext = suggestedName && suggestedName.includes('.') ? suggestedName.split('.').pop()! : '';
  if (!ext) return undefined;
  return [
    { name: ext.toUpperCase(), extensions: [ext.toLowerCase()] },
    { name: 'All Files', extensions: ['*'] },
  ];
}

export async function saveFile(
  win: BrowserWindow | null,
  payload: { suggestedName?: string; content?: string; contentBase64?: string; mimeType?: string },
): Promise<SaveFileResult> {
  const r = await dialog.showSaveDialog(win ?? undefined!, {
    defaultPath: payload.suggestedName,
    filters: saveFilters(payload.suggestedName),
  });
  if (r.canceled || !r.filePath) return { canceled: true };
  // Binary exports (PDF/DOCX) arrive base64-encoded — decode to raw bytes. A 'utf8'
  // string write would corrupt them, so only text exports take the utf8 path.
  if (payload.contentBase64 != null) {
    await fs.writeFile(r.filePath, Buffer.from(payload.contentBase64, 'base64'));
  } else {
    await fs.writeFile(r.filePath, payload.content ?? '', 'utf8');
  }
  return { canceled: false, path: r.filePath };
}

export async function openExternal(target: string): Promise<void> {
  await shell.openExternal(normalizeExternalUrl(target));
}

// -- Per-project layout (opaque JSON in userData/layouts/{projectId}.json) ----

function layoutPath(projectId: number): string {
  return path.join(app.getPath('userData'), 'layouts', `${requireProjectId(projectId)}.json`);
}

const MAX_LAYOUT_BYTES = 256 * 1024;
const REPLACE_REFUSAL_CODES = new Set(['EEXIST', 'EPERM', 'ENOTEMPTY']);

export interface LayoutSaveOptions {
  /** Keep an already validated backup while replacing a corrupt primary. */
  preserveBackup?: boolean;
}

export const INVALID_STORED_LAYOUT = Object.freeze({
  storage: 'logosforge.pro.workspace-layout',
  status: 'invalid',
});

type LayoutFileRead =
  | { state: 'missing' }
  | { state: 'invalid' }
  | { state: 'parsed'; value: unknown };

async function readLayoutFile(fp: string): Promise<LayoutFileRead> {
  let raw: string;
  try {
    const stat = await fs.stat(fp);
    if (stat.size > MAX_LAYOUT_BYTES) return { state: 'invalid' };
    raw = await fs.readFile(fp, 'utf8');
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return { state: 'missing' };
    throw error;
  }
  try {
    const value = JSON.parse(raw) as unknown;
    return value === null ? { state: 'invalid' } : { state: 'parsed', value };
  } catch {
    return { state: 'invalid' };
  }
}

async function loadLayoutGeneration(fp: string): Promise<unknown | null> {
  const result = await readLayoutFile(fp);
  if (result.state === 'missing') return null;
  if (result.state === 'invalid') return INVALID_STORED_LAYOUT;
  return result.value;
}

export async function loadLayout(projectId: number): Promise<unknown | null> {
  return loadLayoutGeneration(layoutPath(projectId));
}

export async function loadLayoutBackup(projectId: number): Promise<unknown | null> {
  return loadLayoutGeneration(`${layoutPath(projectId)}.bak`);
}

async function syncDirectory(directory: string): Promise<void> {
  // Windows does not support opening directory handles through this API. Its
  // replacement fallback still keeps either the primary or backup available.
  if (process.platform === 'win32') return;
  let handle: Awaited<ReturnType<typeof fs.open>> | undefined;
  try {
    handle = await fs.open(directory, 'r');
    await handle.sync();
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    // Some otherwise supported filesystems reject directory fsync. The file
    // generations themselves are already synced and remain recoverable.
    if (code !== 'EINVAL' && code !== 'ENOTSUP' && code !== 'EPERM' && code !== 'EISDIR') throw error;
  } finally {
    await handle?.close().catch(() => undefined);
  }
}

async function durableCopy(source: string, destination: string): Promise<void> {
  await fs.copyFile(source, destination, fsConstants.COPYFILE_EXCL);
  const handle = await fs.open(destination, 'r+');
  try {
    await handle.sync();
  } finally {
    await handle.close();
  }
}

function isReplaceRefusal(error: unknown): boolean {
  return REPLACE_REFUSAL_CODES.has((error as NodeJS.ErrnoException).code ?? '');
}

async function replaceBackup(temporary: string, backup: string): Promise<void> {
  try {
    await fs.rename(temporary, backup);
  } catch (error) {
    if (!isReplaceRefusal(error)) throw error;
    // The primary is still untouched here, so a Windows remove-then-rename gap
    // cannot leave the project without a valid generation.
    await fs.rm(backup, { force: true });
    await fs.rename(temporary, backup);
  }
}

async function replacePrimary(
  temporary: string,
  primary: string,
  retired: string,
): Promise<void> {
  try {
    // POSIX atomically replaces the current generation in one operation.
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
        // A durable backup remains available even if Windows refuses restore.
      }
    }
    throw replacementError;
  } finally {
    if (retiredCurrent && installed) await fs.rm(retired, { force: true }).catch(() => undefined);
  }
}

export async function saveLayout(
  projectId: number,
  layout: unknown,
  options: LayoutSaveOptions = {},
): Promise<void> {
  const fp = layoutPath(projectId);
  const serialized = JSON.stringify(layout);
  if (serialized === undefined) throw new Error('Workspace layout must be JSON-serializable.');
  if (Buffer.byteLength(serialized, 'utf8') > MAX_LAYOUT_BYTES) {
    throw new Error('Workspace layout exceeds the 256 KiB safety limit.');
  }
  const directory = path.dirname(fp);
  const temporary = path.join(directory, `.${path.basename(fp)}.${process.pid}.${randomUUID()}.tmp`);
  const backup = `${fp}.bak`;
  const backupTemporary = path.join(directory, `.${path.basename(backup)}.${process.pid}.${randomUUID()}.tmp`);
  const retired = path.join(directory, `.${path.basename(fp)}.${process.pid}.${randomUUID()}.retired`);
  await fs.mkdir(directory, { recursive: true });
  let handle: Awaited<ReturnType<typeof fs.open>> | undefined;
  try {
    handle = await fs.open(temporary, 'wx', 0o600);
    await handle.writeFile(serialized, 'utf8');
    await handle.sync();
    await handle.close();
    handle = undefined;

    // Refresh the recovery generation before replacing a known-good primary.
    // A renderer recovering a semantically corrupt primary explicitly asks us
    // to preserve its already validated backup instead.
    const current = await readLayoutFile(fp);
    if (!options.preserveBackup && current.state === 'parsed') {
      await durableCopy(fp, backupTemporary);
      await replaceBackup(backupTemporary, backup);
      await syncDirectory(directory);
    }

    await replacePrimary(temporary, fp, retired);
    await syncDirectory(directory);
  } finally {
    await handle?.close().catch(() => undefined);
    await fs.rm(temporary, { force: true }).catch(() => undefined);
    await fs.rm(backupTemporary, { force: true }).catch(() => undefined);
  }
}
