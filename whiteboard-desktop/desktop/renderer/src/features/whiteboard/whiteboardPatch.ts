/** Pure merge rules for the serialized Whiteboard document-save queue. */

import type { WhiteboardUpdate } from './types';

/** Add a newer partial update; newer values win field-by-field. */
export function mergeWhiteboardPatch(
  queued: WhiteboardUpdate | null,
  newer: WhiteboardUpdate,
): WhiteboardUpdate {
  return { ...(queued ?? {}), ...newer };
}

/** Restore a failed snapshot without overwriting fields edited while it ran. */
export function restoreWhiteboardPatch(
  failed: WhiteboardUpdate,
  newer: WhiteboardUpdate | null,
): WhiteboardUpdate {
  return { ...failed, ...(newer ?? {}) };
}
