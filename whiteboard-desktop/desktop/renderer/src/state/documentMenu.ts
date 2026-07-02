/**
 * Bridge for the title-bar project menu (the dropdown under the project name).
 * The document/file actions live in WhiteboardPage (useFileActions +
 * useImportExport); it registers them here so the App-shell title can invoke
 * them. `hasFileBridge` is false in a plain browser (Open/Save need Electron),
 * so the menu can hide those rows; Export works everywhere (download / print).
 */

import type { DocumentSummary } from '../features/whiteboard/documentsApi';

export interface DocumentMenuApi {
  // -- document library (multi-document) --
  documents: DocumentSummary[];
  currentDocId: string;
  selectDocument: (id: string) => void;
  createDocument: () => void;
  deleteDocument: (id: string) => void;
  renameCurrent: (title: string) => void;
  // -- disk file + export actions (operate on the current document) --
  newDocument: () => void;
  openDocument: () => void;
  saveDocument: () => void;
  saveDocumentAs: () => void;
  exportFountain: () => void;
  printDocument: () => void;
  hasFileBridge: boolean;
}

let api: DocumentMenuApi | null = null;
const subs = new Set<() => void>();

export function getDocumentMenuApi(): DocumentMenuApi | null {
  return api;
}
export function subscribeDocumentMenu(cb: () => void): () => void {
  subs.add(cb);
  return () => {
    subs.delete(cb);
  };
}
export function setDocumentMenuApi(next: DocumentMenuApi | null): void {
  api = next;
  subs.forEach((cb) => cb());
}
