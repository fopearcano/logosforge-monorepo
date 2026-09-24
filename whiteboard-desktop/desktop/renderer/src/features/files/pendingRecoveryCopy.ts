import type { PendingDocumentConflictRecovery } from '../../api/backend';
import { canonicalizeOutlineConflictItems } from '../outline/outlineConflictCopy';
import type { OutlineNode } from '../outline/outlineModel';
import { canonicalizeWhiteboardRecoveryPayload } from '../whiteboard/whiteboardRecoveryCanonical';

export interface PendingDocumentRecoveryEnvelope {
  format: 'logosforge-pending-document-recovery';
  version: 1;
  exported_at: string;
  recovery: PendingDocumentConflictRecovery;
}

/**
 * Build the portable copy shown by the app-lifetime recovery banner. Stored
 * snapshots may contain tolerated legacy metadata, so normalize only the
 * schema-owned fields needed for a same-build round trip. Authored text stays
 * byte-for-byte intact.
 */
export function pendingDocumentRecoveryEnvelope(
  recovery: PendingDocumentConflictRecovery,
  exportedAt: string = new Date().toISOString(),
): PendingDocumentRecoveryEnvelope {
  const payload = recovery.write.payload as Record<string, unknown>;
  const portablePayload = recovery.kind === 'outline'
    ? {
      ...payload,
      items: Array.isArray(payload.items)
        ? canonicalizeOutlineConflictItems(payload.items as OutlineNode[], exportedAt)
        : payload.items,
    }
    : canonicalizeWhiteboardRecoveryPayload(payload);
  return {
    format: 'logosforge-pending-document-recovery',
    version: 1,
    exported_at: exportedAt,
    recovery: {
      ...recovery,
      write: { ...recovery.write, payload: portablePayload },
    },
  };
}
