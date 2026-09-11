import type { PendingDocumentDeleteFloor } from './pending-document-persistence';

export interface DocumentDeleteTransaction {
  begin(): Promise<PendingDocumentDeleteFloor>;
  deleteBackend(floor: PendingDocumentDeleteFloor): Promise<void>;
  backendDocumentExists(): Promise<boolean>;
  commit(): void;
  cancel(): void;
  /** Test hook/custom scheduler; production uses the bounded default backoff. */
  waitBeforeRetry?(uncertainAttempt: number, error: unknown): Promise<void>;
}

const DELETE_RETRY_INITIAL_DELAY_MS = 250;
const DELETE_RETRY_MAX_DELAY_MS = 2_000;

function waitForDeleteRetry(uncertainAttempt: number): Promise<void> {
  const exponent = Math.min(Math.max(uncertainAttempt - 1, 0), 3);
  const delay = Math.min(
    DELETE_RETRY_INITIAL_DELAY_MS * (2 ** exponent),
    DELETE_RETRY_MAX_DELAY_MS,
  );
  return new Promise((resolve) => setTimeout(resolve, delay));
}

/**
 * Run an idempotent two-phase document deletion to a terminal local state.
 * A failed/lost DELETE response is retried, then reconciled against the
 * authoritative core before the main-owned persistence fence is released.
 * A transport-failed reconciliation is not evidence that the document survived:
 * keep the fence and retry with bounded backoff until a terminal answer arrives.
 */
export async function runDocumentDeleteTransaction(
  transaction: DocumentDeleteTransaction,
): Promise<void> {
  const floor = await transaction.begin();
  let uncertainAttempt = 0;
  while (true) {
    let firstDeleteError: unknown;
    try {
      await transaction.deleteBackend(floor);
      transaction.commit();
      return;
    } catch (error) {
      firstDeleteError = error;
    }

    let retryDeleteError: unknown;
    try {
      await transaction.deleteBackend(floor);
      transaction.commit();
      return;
    } catch (error) {
      retryDeleteError = error;
    }

    let exists: boolean;
    try {
      exists = await transaction.backendDocumentExists();
    } catch (reconciliationError) {
      uncertainAttempt += 1;
      if (transaction.waitBeforeRetry) {
        await transaction.waitBeforeRetry(uncertainAttempt, reconciliationError);
      } else {
        await waitForDeleteRetry(uncertainAttempt);
      }
      continue;
    }

    if (!exists) {
      transaction.commit();
      return;
    }

    // Only an authoritative, incarnation-aware "still exists" answer proves
    // that it is safe to reopen queues for this same document incarnation.
    transaction.cancel();
    throw new AggregateError(
      [firstDeleteError, retryDeleteError],
      'The document delete could not be confirmed.',
    );
  }
}
