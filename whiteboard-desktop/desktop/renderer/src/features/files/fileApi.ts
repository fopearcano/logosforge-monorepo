/**
 * Typed access to the Electron file bridge. The preload exposes FLAT top-level
 * functions (a nested object was being dropped by contextBridge in the sandbox);
 * here we resolve them lazily from `window.logosforge` and re-compose the
 * `fileApi` façade the rest of the renderer uses. Degrades to a safe error
 * result in a plain browser (no native bridge).
 */

import type { FilesBridge } from './fileTypes';

interface FlatBridge {
  fileOpen?: FilesBridge['open'];
  fileSaveAs?: FilesBridge['saveAs'];
  fileSaveToPath?: FilesBridge['saveToPath'];
  fileConfirmSaveChanges?: FilesBridge['confirmSaveChanges'];
  fileSetDirty?: FilesBridge['setDirty'];
  fileSetCloseHandshakeReady?: FilesBridge['setCloseHandshakeReady'];
  fileSetExternalSaveHandshakeReady?: FilesBridge['setExternalSaveHandshakeReady'];
  fileOnSaveBeforeClose?: FilesBridge['onSaveBeforeClose'];
  fileSendCloseResult?: FilesBridge['sendCloseResult'];
  onMenuFile?(cb: (action: string) => void): () => void;
  onMenuView?(cb: (action: string) => void): () => void;
}

function lf(): FlatBridge | undefined {
  if (typeof window === 'undefined') return undefined;
  return (window as unknown as { logosforge?: FlatBridge }).logosforge;
}

export const filesAvailable = (): boolean => typeof lf()?.fileOpen === 'function';

const NO_BRIDGE = 'File system unavailable — the app is not running inside Electron.';

export const fileApi: FilesBridge = {
  open: () => lf()?.fileOpen?.() ?? Promise.resolve({ ok: false, error: NO_BRIDGE }),
  saveAs: (content, suggestedName) =>
    lf()?.fileSaveAs?.(content, suggestedName) ?? Promise.resolve({ ok: false, error: NO_BRIDGE }),
  saveToPath: (filePath, content) =>
    lf()?.fileSaveToPath?.(filePath, content) ?? Promise.resolve({ ok: false, error: NO_BRIDGE }),
  confirmSaveChanges: (reason) => lf()?.fileConfirmSaveChanges?.(reason) ?? Promise.resolve('dont-save'),
  setDirty: (dirty) => lf()?.fileSetDirty?.(dirty),
  setCloseHandshakeReady: (ready) => lf()?.fileSetCloseHandshakeReady?.(ready),
  setExternalSaveHandshakeReady: (ready) => lf()?.fileSetExternalSaveHandshakeReady?.(ready),
  onSaveBeforeClose: (cb) => lf()?.fileOnSaveBeforeClose?.(cb) ?? (() => {}),
  sendCloseResult: (requestId, ok) => lf()?.fileSendCloseResult?.(requestId, ok),
};

export function onMenuFile(cb: (action: string) => void): () => void {
  return lf()?.onMenuFile?.(cb) ?? (() => {});
}
export function onMenuView(cb: (action: string) => void): () => void {
  return lf()?.onMenuView?.(cb) ?? (() => {});
}
