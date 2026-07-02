/**
 * File / layout manager — the host side of the PlatformAdapter the renderer
 * injects into pro-shared-ui. Open/save dialogs, openExternal, and opaque
 * per-project layout persistence (for the dockable workspace).
 */

import { app, BrowserWindow, dialog, shell } from 'electron';
import * as fs from 'node:fs/promises';
import * as path from 'node:path';

export interface DialogFilter {
  name: string;
  extensions: string[];
}
export interface OpenFileResult {
  canceled: boolean;
  path?: string;
  content?: string;
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
    const content = await fs.readFile(fp, 'utf8');
    return { canceled: false, path: fp, content };
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
  await shell.openExternal(target);
}

// -- Per-project layout (opaque JSON in userData/layouts/{projectId}.json) ----

function layoutPath(projectId: number): string {
  return path.join(app.getPath('userData'), 'layouts', `${projectId}.json`);
}

export async function loadLayout(projectId: number): Promise<unknown | null> {
  try {
    return JSON.parse(await fs.readFile(layoutPath(projectId), 'utf8'));
  } catch {
    return null;
  }
}

export async function saveLayout(projectId: number, layout: unknown): Promise<void> {
  const fp = layoutPath(projectId);
  await fs.mkdir(path.dirname(fp), { recursive: true });
  await fs.writeFile(fp, JSON.stringify(layout), 'utf8');
}
