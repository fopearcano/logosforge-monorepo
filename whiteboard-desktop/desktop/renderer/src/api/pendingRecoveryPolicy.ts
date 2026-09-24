import type { PendingDocumentConflictReceipt } from './backend';

export interface RecoveryAbandonmentSteps {
  discardTarget(): boolean;
  flushOtherState(): Promise<void>;
  requestCoordinatedReload(): Promise<boolean>;
  restoreTarget(): Promise<void>;
}

/** Active recovery abandonment must reload so stale editor state cannot be re-saved. */
export function recoveryTargetsActiveDocument(
  recovery: PendingDocumentConflictReceipt,
  activeDocumentId: string,
  activeIncarnation: string,
): boolean {
  return recovery.documentId === activeDocumentId
    && recovery.incarnation === activeIncarnation;
}

export function samePendingDocumentConflict(
  left: PendingDocumentConflictReceipt,
  right: PendingDocumentConflictReceipt,
): boolean {
  return left.conflictId === right.conflictId
    && left.version === right.version
    && left.kind === right.kind
    && left.documentId === right.documentId
    && left.incarnation === right.incarnation;
}

/** Apply a main snapshot without letting an older async response undo local events. */
export function reconcilePendingDocumentRecoveries<
  T extends PendingDocumentConflictReceipt,
>(
  currentRecoveries: readonly T[],
  incomingRecoveries: readonly T[],
  requestGeneration: number,
  mutationGeneration: ReadonlyMap<string, number>,
): T[] {
  const current = new Map(currentRecoveries.map((item) => [item.conflictId, item]));
  const incoming = new Map(incomingRecoveries.map((item) => [item.conflictId, item]));
  const next: T[] = [];
  for (const recovery of incomingRecoveries) {
    const existing = current.get(recovery.conflictId);
    if ((mutationGeneration.get(recovery.conflictId) ?? 0) > requestGeneration) {
      if (existing) next.push(existing);
    } else {
      next.push(existing && existing.version >= recovery.version ? existing : recovery);
    }
  }
  for (const existing of currentRecoveries) {
    if (incoming.has(existing.conflictId)) continue;
    if ((mutationGeneration.get(existing.conflictId) ?? 0) > requestGeneration) {
      next.push(existing);
    }
  }
  return next;
}

/**
 * Remove only the selected local queue, prove every unrelated store is safe,
 * and then ask main to run the normal reload/save-prompt handshake. Main still
 * owns the rescue receipt throughout preparation, so any failure can hydrate
 * the exact draft again.
 */
export async function coordinateRecoveryAbandonment(
  steps: RecoveryAbandonmentSteps,
): Promise<boolean> {
  if (!steps.discardTarget()) {
    await steps.restoreTarget();
    return false;
  }
  try {
    await steps.flushOtherState();
    const reloading = await steps.requestCoordinatedReload();
    if (reloading) return true;
    await steps.restoreTarget();
    return false;
  } catch (error) {
    await steps.restoreTarget().catch(() => {});
    throw error;
  }
}
