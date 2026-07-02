/**
 * Main-process file manager. ALL native dialogs + filesystem IO live here (the
 * renderer reaches these only through secure IPC). Every entry point logs so the
 * full chain can be traced from the terminal that runs `npm run dev`.
 */

import { BrowserWindow, dialog } from 'electron';
import { promises as fs } from 'node:fs';
import * as path from 'node:path';

export interface OpenResult {
  ok: boolean;
  canceled?: boolean;
  filePath?: string;
  fileName?: string;
  content?: string;
  error?: string;
}

export interface SaveResult {
  ok: boolean;
  canceled?: boolean;
  filePath?: string;
  fileName?: string;
  error?: string;
}

export type SaveChoice = 'save' | 'dont-save' | 'cancel';

const OPEN_FILTERS = [
  { name: 'Writing Files', extensions: ['fountain', 'txt', 'md', 'logosforge', 'logforge'] },
  { name: 'All Files', extensions: ['*'] },
];
const SAVE_FILTERS = [
  { name: 'Fountain', extensions: ['fountain'] },
  { name: 'Markdown', extensions: ['md'] },
  { name: 'Text', extensions: ['txt'] },
  { name: 'LogosForge', extensions: ['logosforge'] },
];

/** Read a file from disk into a structured result. */
export async function readFileFromPath(filePath: string): Promise<OpenResult> {
  try {
    const content = await fs.readFile(filePath, 'utf8');
    return { ok: true, canceled: false, filePath, fileName: path.basename(filePath), content };
  } catch (err) {
    console.error('[files] read error:', err);
    return { ok: false, error: String(err) };
  }
}

/** Write content to a known path. */
export async function saveFileToPath(filePath: string, content: string): Promise<SaveResult> {
  console.log('[files] save to path:', filePath);
  try {
    await fs.writeFile(filePath, content, 'utf8');
    return { ok: true, canceled: false, filePath, fileName: path.basename(filePath) };
  } catch (err) {
    console.error('[files] save to path error:', err);
    return { ok: false, error: String(err) };
  }
}

/** Native Open dialog → read the chosen file. */
export async function openFileDialog(win: BrowserWindow | null): Promise<OpenResult> {
  console.log('[files] open dialog requested');
  try {
    const options = { properties: ['openFile' as const], filters: OPEN_FILTERS };
    const res = win ? await dialog.showOpenDialog(win, options) : await dialog.showOpenDialog(options);
    console.log('[files] open dialog result:', res.canceled ? 'canceled' : res.filePaths[0]);
    if (res.canceled || res.filePaths.length === 0) return { ok: true, canceled: true };
    return readFileFromPath(res.filePaths[0]);
  } catch (err) {
    console.error('[files] open dialog error:', err);
    return { ok: false, error: String(err) };
  }
}

/** Native Save dialog → write content to the chosen path. */
export async function saveFileDialog(
  win: BrowserWindow | null,
  content: string,
  currentPath: string | null,
  suggestedName: string,
): Promise<SaveResult> {
  console.log('[files] save dialog requested');
  try {
    const options = { defaultPath: currentPath ?? suggestedName, filters: SAVE_FILTERS };
    const res = win ? await dialog.showSaveDialog(win, options) : await dialog.showSaveDialog(options);
    console.log('[files] save dialog result:', res.canceled ? 'canceled' : res.filePath);
    if (res.canceled || !res.filePath) return { ok: true, canceled: true };
    return saveFileToPath(res.filePath, content);
  } catch (err) {
    console.error('[files] save dialog error:', err);
    return { ok: false, error: String(err) };
  }
}

// --- Import / Export (extends the file system; Open/Save are untouched) -----

export interface DialogFilter {
  name: string;
  extensions: string[];
}

export type ImportMode = 'replace' | 'append' | 'cancel';

/** Native Open dialog for Import → read the chosen file (caller-supplied filters). */
export async function openImportDialog(
  win: BrowserWindow | null,
  filters: DialogFilter[],
): Promise<OpenResult> {
  console.log('[import] open dialog requested');
  try {
    const options = { properties: ['openFile' as const], filters };
    const res = win ? await dialog.showOpenDialog(win, options) : await dialog.showOpenDialog(options);
    if (res.canceled || res.filePaths.length === 0) return { ok: true, canceled: true };
    return readFileFromPath(res.filePaths[0]);
  } catch (err) {
    console.error('[import] open dialog error:', err);
    return { ok: false, error: String(err) };
  }
}

/** Native Save dialog for Export → write content to the chosen path. */
export async function saveExportDialog(
  win: BrowserWindow | null,
  content: string,
  suggestedName: string,
  filters: DialogFilter[],
): Promise<SaveResult> {
  console.log('[export] save dialog requested:', suggestedName);
  try {
    const options = { defaultPath: suggestedName, filters };
    const res = win ? await dialog.showSaveDialog(win, options) : await dialog.showSaveDialog(options);
    if (res.canceled || !res.filePath) return { ok: true, canceled: true };
    return saveFileToPath(res.filePath, content);
  } catch (err) {
    console.error('[export] save dialog error:', err);
    return { ok: false, error: String(err) };
  }
}

/** Native "How should this import be applied?" 3-button prompt. */
export async function confirmImportMode(win: BrowserWindow | null): Promise<ImportMode> {
  const options = {
    type: 'question' as const,
    buttons: ['Replace current document', 'Append to current document', 'Cancel'],
    defaultId: 0,
    cancelId: 2,
    noLink: true,
    message: 'How should this import be applied?',
    detail: 'Replace swaps the whole document; Append adds the imported content to the end.',
  };
  const res = win ? await dialog.showMessageBox(win, options) : await dialog.showMessageBox(options);
  return res.response === 0 ? 'replace' : res.response === 1 ? 'append' : 'cancel';
}

/** Native "Save changes?" 3-button prompt. */
export async function confirmSaveChanges(
  win: BrowserWindow | null,
  reason?: string,
): Promise<SaveChoice> {
  const options = {
    type: 'warning' as const,
    buttons: ['Save', "Don't Save", 'Cancel'],
    defaultId: 0,
    cancelId: 2,
    noLink: true,
    message: reason || 'Save changes before closing?',
    detail: 'Your document has unsaved changes.',
  };
  const res = win ? await dialog.showMessageBox(win, options) : await dialog.showMessageBox(options);
  return res.response === 0 ? 'save' : res.response === 1 ? 'dont-save' : 'cancel';
}
