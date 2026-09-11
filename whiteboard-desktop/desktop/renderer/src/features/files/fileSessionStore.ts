import type { FileStatus } from './fileTypes';

export interface FileSessionState {
  filePath: string | null;
  dirty: boolean;
  status: FileStatus;
  /** Incremented synchronously for every editor content change. */
  contentRevision: number;
  /** Incremented whenever Open/New/document switching replaces the file context. */
  contextRevision: number;
}

export interface FileSessionToken {
  readonly documentId: string;
  readonly contentRevision: number;
  readonly contextRevision: number;
}

export interface FileSaveCompletion {
  readonly currentContext: boolean;
  readonly clean: boolean;
  readonly state: FileSessionState;
}

const INITIAL_STATE: FileSessionState = {
  filePath: null,
  dirty: false,
  status: 'saved',
  contentRevision: 0,
  contextRevision: 0,
};

/**
 * Module-lifetime file state and save queue. Keeping both outside React means an
 * app error-boundary remount cannot forget an in-flight write or let a later
 * write overtake it.
 */
export class FileSessionCoordinator {
  private state: FileSessionState;
  private readonly subscribers = new Set<() => void>();
  private saveTail: Promise<void> = Promise.resolve();

  constructor(initial: FileSessionState = INITIAL_STATE) {
    this.state = { ...initial };
  }

  getSnapshot = (): FileSessionState => this.state;

  subscribe = (subscriber: () => void): (() => void) => {
    this.subscribers.add(subscriber);
    return () => this.subscribers.delete(subscriber);
  };

  patch(patch: Partial<FileSessionState>): FileSessionState {
    this.publish({ ...this.state, ...patch });
    return this.state;
  }

  markDirty(): FileSessionState {
    this.publish({
      ...this.state,
      dirty: true,
      status: 'unsaved',
      contentRevision: this.state.contentRevision + 1,
    });
    return this.state;
  }

  replaceContext(filePath: string | null): FileSessionState {
    this.publish({
      filePath,
      dirty: false,
      status: 'saved',
      contentRevision: this.state.contentRevision + 1,
      contextRevision: this.state.contextRevision + 1,
    });
    return this.state;
  }

  capture(documentId: string): FileSessionToken {
    return {
      documentId,
      contentRevision: this.state.contentRevision,
      contextRevision: this.state.contextRevision,
    };
  }

  isContextCurrent(token: FileSessionToken, currentDocumentId: string): boolean {
    return (
      token.documentId === currentDocumentId &&
      token.contextRevision === this.state.contextRevision
    );
  }

  /**
   * Associate a successful Save As path with the same file context, but clear
   * dirty only when the exact content revision that was written is still current.
   */
  completeSave(
    token: FileSessionToken,
    currentDocumentId: string,
    filePath?: string | null,
  ): FileSaveCompletion {
    if (!this.isContextCurrent(token, currentDocumentId)) {
      return { currentContext: false, clean: false, state: this.state };
    }
    const clean = token.contentRevision === this.state.contentRevision;
    this.publish({
      ...this.state,
      ...(filePath === undefined ? {} : { filePath }),
      dirty: !clean,
      status: clean ? 'saved' : 'unsaved',
    });
    return { currentContext: true, clean, state: this.state };
  }

  setStatusIfCurrent(
    token: FileSessionToken,
    currentDocumentId: string,
    status: FileStatus,
  ): boolean {
    if (!this.isContextCurrent(token, currentDocumentId)) return false;
    this.patch({ status });
    return true;
  }

  /** FIFO serialization prevents an older disk write from completing last. */
  runSave<T>(save: () => Promise<T>): Promise<T> {
    const result = this.saveTail.then(save, save);
    this.saveTail = result.then(
      () => undefined,
      () => undefined,
    );
    return result;
  }

  async waitForSaves(): Promise<void> {
    while (true) {
      const observed = this.saveTail;
      await observed;
      if (observed === this.saveTail) return;
    }
  }

  private publish(next: FileSessionState): void {
    this.state = next;
    this.subscribers.forEach((subscriber) => {
      try {
        subscriber();
      } catch {
        // One retired React subscriber must not prevent the shared state update.
      }
    });
  }
}

const fileSession = new FileSessionCoordinator();

export function getFileSessionState(): FileSessionState {
  return fileSession.getSnapshot();
}

export function subscribeFileSessionState(subscriber: () => void): () => void {
  return fileSession.subscribe(subscriber);
}

export function updateFileSessionState(patch: Partial<FileSessionState>): FileSessionState {
  return fileSession.patch(patch);
}

export function markFileSessionDirty(): FileSessionState {
  return fileSession.markDirty();
}

export function replaceFileSessionContext(filePath: string | null): FileSessionState {
  return fileSession.replaceContext(filePath);
}

export function captureFileSession(documentId: string): FileSessionToken {
  return fileSession.capture(documentId);
}

export function isFileSessionContextCurrent(
  token: FileSessionToken,
  currentDocumentId: string,
): boolean {
  return fileSession.isContextCurrent(token, currentDocumentId);
}

export function completeFileSessionSave(
  token: FileSessionToken,
  currentDocumentId: string,
  filePath?: string | null,
): FileSaveCompletion {
  return fileSession.completeSave(token, currentDocumentId, filePath);
}

export function setFileSessionStatusIfCurrent(
  token: FileSessionToken,
  currentDocumentId: string,
  status: FileStatus,
): boolean {
  return fileSession.setStatusIfCurrent(token, currentDocumentId, status);
}

export function runSerializedFileSave<T>(save: () => Promise<T>): Promise<T> {
  return fileSession.runSave(save);
}

export function waitForPendingFileSaves(): Promise<void> {
  return fileSession.waitForSaves();
}
