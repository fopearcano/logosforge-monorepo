/**
 * Typed access to the Electron import/export bridge (flat top-level functions,
 * same pattern as fileApi). Degrades to a safe error result in a plain browser.
 */

import type { DialogFilter } from './importExportFormats';
import type { OpenResult, SaveResult } from './fileTypes';

export type ImportMode = 'replace' | 'append' | 'cancel';

interface IeBridge {
  importOpen?(filters: DialogFilter[]): Promise<OpenResult>;
  importConfirmMode?(): Promise<ImportMode>;
  exportSave?(content: string, suggestedName: string, filters: DialogFilter[]): Promise<SaveResult>;
}

function lf(): IeBridge | undefined {
  if (typeof window === 'undefined') return undefined;
  return (window as unknown as { logosforge?: IeBridge }).logosforge;
}

const NO_BRIDGE = 'File system unavailable — the app is not running inside Electron.';

export const importExportAvailable = (): boolean => typeof lf()?.importOpen === 'function';

export function importOpen(filters: DialogFilter[]): Promise<OpenResult> {
  return lf()?.importOpen?.(filters) ?? Promise.resolve({ ok: false, error: NO_BRIDGE });
}

export function importConfirmMode(): Promise<ImportMode> {
  return lf()?.importConfirmMode?.() ?? Promise.resolve('cancel');
}

/**
 * Browser fallback for when the Electron save dialog is unavailable (running in
 * a plain browser): hand the content to the browser as a normal file download.
 * Lets Export work outside the desktop app instead of failing silently.
 */
function browserDownload(content: string, suggestedName: string): SaveResult {
  if (typeof document === 'undefined' || typeof URL?.createObjectURL !== 'function') {
    return { ok: false, error: NO_BRIDGE };
  }
  try {
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = suggestedName;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000); // after the click grabs it
    return { ok: true, fileName: suggestedName };
  } catch (err) {
    return { ok: false, error: String(err) };
  }
}

export function exportSave(
  content: string,
  suggestedName: string,
  filters: DialogFilter[],
): Promise<SaveResult> {
  const bridged = lf()?.exportSave;
  if (bridged) return bridged(content, suggestedName, filters);
  return Promise.resolve(browserDownload(content, suggestedName));
}
