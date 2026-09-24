import type { PendingDocumentDeleteFloor } from './pending-document-persistence';

export interface DocumentDeleteTransaction {
  begin(): Promise<PendingDocumentDeleteFloor>;
  deleteBackend(floor: PendingDocumentDeleteFloor): Promise<void>;
  backendDocumentExists(): Promise<boolean>;
  commit(): void;
  cancel(): void;
  /** Test hook/custom scheduler; production uses the bounded default backoff. */
  waitBeforeRetry?(uncertainAttempt: number, error: unknown): Promise<void>;
  /** Test hook for durable local cleanup after backend deletion is terminal. */
  waitBeforeCommitRetry?(attempt: number, error: unknown): Promise<void>;
}

const DELETE_RETRY_INITIAL_DELAY_MS = 250;
const DELETE_RETRY_MAX_DELAY_MS = 2_000;
const DELETE_COMMIT_MAX_ATTEMPTS = 3;

function waitForDeleteRetry(uncertainAttempt: number): Promise<void> {
  const exponent = Math.min(Math.max(uncertainAttempt - 1, 0), 3);
  const delay = Math.min(
    DELETE_RETRY_INITIAL_DELAY_MS * (2 ** exponent),
    DELETE_RETRY_MAX_DELAY_MS,
  );
  return new Promise((resolve) => setTimeout(resolve, delay));
}

async function commitDeleteUntilDurable(transaction: DocumentDeleteTransaction): Promise<void> {
  let attempt = 0;
  while (true) {
    try {
      transaction.commit();
      return;
    } catch (error) {
      attempt += 1;
      // Keep the persistence fence but return control to the UI after a bounded
      // number of local attempts. A later delete retries the idempotent backend
      // operation and then this durable cleanup; close remains fail-closed if
      // an unresolved recovery entry is still journaled.
      if (attempt >= DELETE_COMMIT_MAX_ATTEMPTS) {
        throw new AggregateError(
          [error],
          'The document was deleted, but local recovery cleanup is not durable yet.',
        );
      }
      if (transaction.waitBeforeCommitRetry) {
        await transaction.waitBeforeCommitRetry(attempt, error);
      } else {
        await waitForDeleteRetry(attempt);
      }
    }
  }
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
    let firstDeleteSucceeded = false;
    try {
      await transaction.deleteBackend(floor);
      firstDeleteSucceeded = true;
    } catch (error) {
      firstDeleteError = error;
    }
    if (firstDeleteSucceeded) {
      await commitDeleteUntilDurable(transaction);
      return;
    }

    let retryDeleteError: unknown;
    let retryDeleteSucceeded = false;
    try {
      await transaction.deleteBackend(floor);
      retryDeleteSucceeded = true;
    } catch (error) {
      retryDeleteError = error;
    }
    if (retryDeleteSucceeded) {
      await commitDeleteUntilDurable(transaction);
      return;
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
      await commitDeleteUntilDurable(transaction);
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
