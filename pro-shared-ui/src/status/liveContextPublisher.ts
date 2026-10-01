/** Maximum live selection forwarded to the desktop host. */
export const LIVE_CONTEXT_SELECTION_LIMIT = 20_000;

const LIVE_CONTEXT_LABEL_LIMIT = 128;

export interface LiveContextSnapshot {
  projectId: number | null;
  activePanelId: string;
  activeSceneId: number | null;
  selectionSection: string;
  selection: string;
}

export interface LiveContextPublishBridge {
  publishLiveContext(snapshot: LiveContextSnapshot): void | Promise<void>;
  clearLiveContext(): void | Promise<void>;
}

interface LiveContextScheduler {
  setTimeout(callback: () => void, delayMs: number): unknown;
  clearTimeout(handle: unknown): void;
  setInterval(callback: () => void, delayMs: number): unknown;
  clearInterval(handle: unknown): void;
}

export interface LiveContextPublishControllerOptions {
  debounceMs?: number;
  heartbeatMs?: number;
  scheduler?: LiveContextScheduler;
}

const defaultScheduler: LiveContextScheduler = {
  setTimeout: (callback, delayMs) => globalThis.setTimeout(callback, delayMs),
  clearTimeout: (handle) => globalThis.clearTimeout(handle as ReturnType<typeof setTimeout>),
  setInterval: (callback, delayMs) => globalThis.setInterval(callback, delayMs),
  clearInterval: (handle) => globalThis.clearInterval(handle as ReturnType<typeof setInterval>),
};

function safeInteger(value: number | null): number | null {
  return Number.isSafeInteger(value) && (value as number) > 0 ? value : null;
}

function truncateCodePoints(value: string, limit: number): string {
  if (value.length <= limit) return value;
  return Array.from(value).slice(0, limit).join("");
}

function safeLabel(value: string): string {
  return truncateCodePoints(value.trim(), LIVE_CONTEXT_LABEL_LIMIT);
}

export function normalizeLiveContextSnapshot(snapshot: LiveContextSnapshot): LiveContextSnapshot {
  const projectId = safeInteger(snapshot.projectId);
  return {
    projectId,
    activePanelId: projectId == null ? "" : safeLabel(snapshot.activePanelId),
    activeSceneId: projectId == null ? null : safeInteger(snapshot.activeSceneId),
    selectionSection: projectId == null ? "" : safeLabel(snapshot.selectionSection),
    selection: projectId == null
      ? ""
      : truncateCodePoints(snapshot.selection, LIVE_CONTEXT_SELECTION_LIMIT),
  };
}

/**
 * Debounces renderer churn while keeping the core's transient context alive.
 *
 * The desktop main process owns ordering and revision numbers. This controller
 * deliberately sends an explicit clear before crossing project boundaries and
 * on dispose; the main-process queue makes clear → publish deterministic.
 */
export class LiveContextPublishController {
  private readonly debounceMs: number;
  private readonly scheduler: LiveContextScheduler;
  private readonly heartbeatHandle: unknown;
  private debounceHandle: unknown | null = null;
  private current: LiveContextSnapshot | null = null;
  private disposed = false;

  constructor(
    private readonly bridge: LiveContextPublishBridge,
    options: LiveContextPublishControllerOptions = {},
  ) {
    this.debounceMs = options.debounceMs ?? 150;
    this.scheduler = options.scheduler ?? defaultScheduler;
    this.heartbeatHandle = this.scheduler.setInterval(
      () => this.publishCurrent(),
      options.heartbeatMs ?? 10_000,
    );
  }

  update(snapshot: LiveContextSnapshot): void {
    if (this.disposed) return;
    const next = normalizeLiveContextSnapshot(snapshot);
    const previousProjectId = this.current?.projectId ?? null;
    const projectChanged = this.current !== null && previousProjectId !== next.projectId;

    this.cancelDebounce();
    if (projectChanged && previousProjectId != null) this.clearHost();
    this.current = next;

    if (next.projectId == null) {
      this.clearHost();
      return;
    }
    this.debounceHandle = this.scheduler.setTimeout(() => {
      this.debounceHandle = null;
      this.publishCurrent();
    }, this.debounceMs);
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.cancelDebounce();
    this.scheduler.clearInterval(this.heartbeatHandle);
    this.current = null;
    this.clearHost();
  }

  private cancelDebounce(): void {
    if (this.debounceHandle === null) return;
    this.scheduler.clearTimeout(this.debounceHandle);
    this.debounceHandle = null;
  }

  private publishCurrent(): void {
    if (this.disposed || this.current?.projectId == null) return;
    this.ignoreFailure(this.bridge.publishLiveContext(this.current));
  }

  private clearHost(): void {
    this.ignoreFailure(this.bridge.clearLiveContext());
  }

  private ignoreFailure(result: void | Promise<void>): void {
    if (result && typeof (result as Promise<void>).catch === "function") {
      void (result as Promise<void>).catch(() => undefined);
    }
  }
}
