export interface RendererSaveClock {
  setTimeout(callback: () => void, delayMs: number): unknown;
  clearTimeout(handle: unknown): void;
}

const systemClock: RendererSaveClock = {
  setTimeout: (callback, delayMs) => setTimeout(callback, delayMs),
  clearTimeout: (handle) => clearTimeout(handle as ReturnType<typeof setTimeout>),
};

export interface RendererSaveGate {
  result: Promise<boolean>;
  outcome: Promise<RendererSaveOutcome>;
  /** Returns false when a timeout or earlier response already settled the gate. */
  complete(saved: boolean): boolean;
  /** Temporarily stop the watchdog while main owns a native dialog/write. */
  pause(): boolean;
  /** Re-arm a full watchdog period after a paused main-owned operation settles. */
  resume(): boolean;
}

export type RendererSaveOutcome = 'success' | 'failure' | 'timeout';

export interface CorrelatedRendererSaveRequest {
  requestId: number;
  result: Promise<boolean>;
  outcome: Promise<RendererSaveOutcome>;
}

/**
 * The module-lifetime autosave listener survives an App error-boundary fallback;
 * the external-file Save handler does not. Keep those capabilities independent
 * while still clearing both for a real renderer navigation/loss.
 */
export class RendererCloseCapabilities {
  private autosaveReady = false;
  private externalSaveReady = false;

  setAutosaveReady(ready: boolean): void {
    this.autosaveReady = ready;
    if (!ready) this.externalSaveReady = false;
  }

  setExternalSaveReady(ready: boolean): void {
    // A hook-scoped handler can never make an uninitialized renderer usable.
    this.externalSaveReady = ready && this.autosaveReady;
  }

  clearForRendererLoss(): void {
    this.autosaveReady = false;
    this.externalSaveReady = false;
  }

  get canFlushAutosave(): boolean {
    return this.autosaveReady;
  }

  get canSaveExternalFile(): boolean {
    return this.externalSaveReady;
  }
}

/**
 * Resolve a renderer save request exactly once, treating silence as failure.
 * The injectable clock keeps timeout and late-response behavior deterministic
 * in tests without importing Electron's side-effectful main process.
 */
export function createRendererSaveGate(
  timeoutMs: number,
  clock: RendererSaveClock = systemClock,
): RendererSaveGate {
  let settled = false;
  let timeoutArmed = false;
  let timeoutHandle: unknown;
  let timeoutGeneration = 0;
  let resolveOutcome!: (outcome: RendererSaveOutcome) => void;

  const outcome = new Promise<RendererSaveOutcome>((resolve) => {
    resolveOutcome = resolve;
  });
  const result = outcome.then((value) => value === 'success');

  const settle = (value: RendererSaveOutcome): boolean => {
    if (settled) return false;
    settled = true;
    if (timeoutArmed) {
      timeoutArmed = false;
      clock.clearTimeout(timeoutHandle);
    }
    resolveOutcome(value);
    return true;
  };
  const complete = (saved: boolean): boolean => settle(saved ? 'success' : 'failure');

  const armTimeout = (): boolean => {
    if (settled || timeoutArmed) return false;
    const generation = ++timeoutGeneration;
    timeoutArmed = true;
    const handle = clock.setTimeout(() => {
      if (settled || !timeoutArmed || timeoutGeneration !== generation) return;
      timeoutArmed = false;
      settle('timeout');
    }, Math.max(0, timeoutMs));
    timeoutHandle = handle;
    // A custom clock may invoke zero-delay callbacks synchronously.
    if (settled) clock.clearTimeout(handle);
    return !settled;
  };

  const pause = (): boolean => {
    if (settled || !timeoutArmed) return false;
    timeoutArmed = false;
    timeoutGeneration += 1;
    clock.clearTimeout(timeoutHandle);
    return true;
  };

  const resume = (): boolean => armTimeout();

  armTimeout();

  return { result, outcome, complete, pause, resume };
}

/** Correlate retries so a late reply from a timed-out request cannot close the app. */
export class RendererSaveRequestRegistry {
  private nextRequestId = 0;
  private active: { requestId: number; gate: RendererSaveGate } | null = null;
  private timeoutSuspensionDepth = 0;

  constructor(
    private readonly timeoutMs: number,
    private readonly clock: RendererSaveClock = systemClock,
  ) {}

  begin(): CorrelatedRendererSaveRequest {
    if (this.active) {
      throw new Error('A renderer save request is already active.');
    }
    const requestId = ++this.nextRequestId;
    const gate = createRendererSaveGate(this.timeoutMs, this.clock);
    if (this.timeoutSuspensionDepth > 0) gate.pause();
    const entry = { requestId, gate };
    this.active = entry;
    void gate.result.then(() => {
      if (this.active === entry) this.active = null;
    });
    return { requestId, result: gate.result, outcome: gate.outcome };
  }

  complete(requestId: number, saved: boolean): boolean {
    if (this.active?.requestId !== requestId) return false;
    return this.active.gate.complete(saved);
  }

  /** Release an in-flight wait immediately when the renderer can no longer reply. */
  failActive(): boolean {
    return this.active?.gate.complete(false) ?? false;
  }

  /** Nestable pause used while a trusted main-process dialog or write is active. */
  suspendTimeouts(): void {
    this.timeoutSuspensionDepth += 1;
    this.active?.gate.pause();
  }

  resumeTimeouts(): void {
    if (this.timeoutSuspensionDepth === 0) return;
    this.timeoutSuspensionDepth -= 1;
    if (this.timeoutSuspensionDepth === 0) this.active?.gate.resume();
  }
}
