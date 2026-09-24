import type { SaveResult } from '../files/fileTypes';
import type { DialogFilter } from '../files/importExportFormats';
import { exportSave } from '../files/importExportApi';
import type { WhiteboardDocument } from './types';
import {
  applyRetainedWhiteboardPatch,
  type RetainedWhiteboardPatch,
} from './pendingWhiteboardRecovery';

type ConflictCopySaver = (
  content: string,
  suggestedName: string,
  filters: DialogFilter[],
) => Promise<SaveResult>;

export interface WhiteboardConflictEnvelope {
  format: 'logosforge-whiteboard-conflict';
  version: 1;
  document_id: string;
  incarnation: string;
  base_revision: string;
  exported_at: string;
  pending_patch: RetainedWhiteboardPatch['patch'];
  document: WhiteboardDocument;
}

/** Build a complete rescue snapshot without acknowledging or mutating its queue. */
export function whiteboardConflictEnvelope(
  document: WhiteboardDocument,
  retained: RetainedWhiteboardPatch,
  exportedAt: string = new Date().toISOString(),
): WhiteboardConflictEnvelope {
  if (retained.documentId !== document.id) {
    throw new Error('The conflicted draft no longer belongs to the open document.');
  }
  return {
    format: 'logosforge-whiteboard-conflict',
    version: 1,
    document_id: document.id,
    incarnation: document.incarnation,
    base_revision: document.revision,
    exported_at: exportedAt,
    pending_patch: retained.patch,
    document: applyRetainedWhiteboardPatch(document, retained),
  };
}

export function saveWhiteboardConflictCopy(
  document: WhiteboardDocument,
  retained: RetainedWhiteboardPatch,
  save: ConflictCopySaver = exportSave,
): Promise<SaveResult> {
  const content = JSON.stringify(whiteboardConflictEnvelope(document, retained), null, 2);
  return save(
    content,
    `whiteboard-${document.id}-conflict.json`,
    [{ name: 'JSON', extensions: ['json'] }],
  );
}
