/** Shared types for desktop file management (renderer side). */

export type FileStatus = 'saved' | 'unsaved' | 'saving' | 'error';
export type SaveChoice = 'save' | 'dont-save' | 'cancel';

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

/** The file IPC surface exposed by the Electron preload bridge. */
export interface FilesBridge {
  open(): Promise<OpenResult>;
  saveAs(content: string, suggestedName: string): Promise<SaveResult>;
  saveToPath(filePath: string, content: string): Promise<SaveResult>;
  confirmSaveChanges(reason?: string): Promise<SaveChoice>;
  setDirty(dirty: boolean): void;
  onSaveBeforeClose(cb: () => void): () => void;
  sendCloseResult(ok: boolean): void;
}
