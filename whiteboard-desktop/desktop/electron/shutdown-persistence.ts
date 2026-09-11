import type { RendererSaveOutcome } from './renderer-save-gate';

export interface PersistenceRetryClock {
  delay(delayMs: number): Promise<void>;
}

const systemClock: PersistenceRetryClock = {
  delay: (delayMs) => new Promise((resolve) => setTimeout(resolve, delayMs)),
};

export interface PersistenceDrainRetryOptions {
  retryDelayMs?: number;
  clock?: PersistenceRetryClock;
  onFailure?: (error: unknown) => void;
}

export type RequestedCloseAction = 'close' | 'reload';
export type EffectiveCloseAction = RequestedCloseAction | 'quit';
export type ClosePreparationOwner = 'ordinary' | 'system-session-end';

/**
 * Main has one renderer autosave request slot, so close/reload and operating-
 * system shutdown preparation must never overlap. Ownership is explicit so a
 * stale async completion cannot release a newer preparation.
 */
export class ClosePreparationCoordinator {
  private owner: ClosePreparationOwner | null = null;
  private readonly idleWaiters = new Set<() => void>();

  begin(owner: ClosePreparationOwner): boolean {
    if (this.owner !== null) return false;
    this.owner = owner;
    return true;
  }

  end(owner: ClosePreparationOwner): boolean {
    if (this.owner !== owner) return false;
    this.owner = null;
    const waiters = [...this.idleWaiters];
    this.idleWaiters.clear();
    for (const resolve of waiters) resolve();
    return true;
  }

  isOwnedBy(owner: ClosePreparationOwner): boolean {
    return this.owner === owner;
  }

  waitUntilIdle(): Promise<void> {
    if (this.owner === null) return Promise.resolve();
    return new Promise((resolve) => this.idleWaiters.add(resolve));
  }
}

export type SystemSessionRendererOutcome =
  | 'success'
  | 'explicit-failure'
  | 'timeout'
  | 'unavailable';

export type SystemSessionPersistenceResult =
  | { ready: true }
  | {
      ready: false;
      reason: 'renderer-failure' | 'renderer-timeout' | 'main-persistence-failure';
      error?: unknown;
    };

/** A quit requested during an existing reload/close handshake always wins. */
export function effectiveCloseAction(
  requested: RequestedCloseAction,
  quitRequested: boolean,
): EffectiveCloseAction {
  return quitRequested ? 'quit' : requested;
}

/** Operating-system session end supersedes any not-yet-started human prompt. */
export function ordinaryCloseCanContinue(systemSessionEndPending: boolean): boolean {
  return !systemSessionEndPending;
}

/**
 * Convert the renderer watchdog result into a session-end decision. A renderer
 * that explicitly rejected the flush remains authoritative while it is live;
 * renderer loss may instead fall back to the main-owned durable queues.
 */
export function classifySystemSessionRendererOutcome(
  outcome: RendererSaveOutcome | null,
  rendererAvailable: boolean,
): SystemSessionRendererOutcome {
  if (outcome === null) return 'unavailable';
  if (outcome === 'success') return 'success';
  if (!rendererAvailable) return 'unavailable';
  return outcome === 'timeout' ? 'timeout' : 'explicit-failure';
}

/**
 * Prepare for a non-interactive operating-system session end. This deliberately
 * has no external-file Save/Save-As callback: a successful renderer flush has
 * already protected the same manuscript in document autosave, and opening a
 * human-blocking dialog would deadlock shutdown. Only a successful renderer
 * flush or an unavailable renderer may advance to the main-owned final drain.
 */
export async function prepareSystemSessionEndPersistence(
  rendererOutcome: SystemSessionRendererOutcome,
  drainMainPersistence: () => Promise<void>,
): Promise<SystemSessionPersistenceResult> {
  if (rendererOutcome === 'explicit-failure') {
    return { ready: false, reason: 'renderer-failure' };
  }
  if (rendererOutcome === 'timeout') {
    return { ready: false, reason: 'renderer-timeout' };
  }
  try {
    await drainMainPersistence();
    return { ready: true };
  } catch (error) {
    return { ready: false, reason: 'main-persistence-failure', error };
  }
}

/**
 * Keep the process (and its backend) alive until every main-owned write/delete
 * reaches a terminal state. A fixed shutdown deadline can turn a slow but
 * acknowledged persistence operation into deterministic data loss.
 */
export async function drainPersistenceUntilSettled(
  drain: () => Promise<void>,
  options: PersistenceDrainRetryOptions = {},
): Promise<void> {
  const retryDelayMs = Math.max(0, options.retryDelayMs ?? 1_000);
  const clock = options.clock ?? systemClock;
  while (true) {
    try {
      await drain();
      return;
    } catch (error) {
      options.onFailure?.(error);
      await clock.delay(retryDelayMs);
    }
  }
}
