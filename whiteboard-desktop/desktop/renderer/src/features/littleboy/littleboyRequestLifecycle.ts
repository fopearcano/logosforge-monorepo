/** Document-lifecycle coordination for long-running LittleBoy requests. */

import {
  captureDocumentIdentity,
  runPendingDocWrite,
  type CapturedDocumentIdentity,
} from '../../state/currentDocument';

export class StaleLittleBoyResponseError extends Error {
  constructor() {
    super('The LittleBoy response belongs to a document that is no longer active.');
    this.name = 'StaleLittleBoyResponseError';
  }
}

export function sameDocumentIdentity(
  left: CapturedDocumentIdentity,
  right: CapturedDocumentIdentity,
): boolean {
  return left.documentId === right.documentId && left.incarnation === right.incarnation;
}

export function isCurrentLittleBoyIdentity(identity: CapturedDocumentIdentity): boolean {
  return sameDocumentIdentity(identity, captureDocumentIdentity());
}

/**
 * Admit the request through the same close/delete guard as persistent writes and
 * expose a non-failing shadow to the document drain. AI/provider errors still
 * reach the caller, but they do not masquerade as unsaved-data failures. The
 * handoff does wait for the request to settle, keeping the backend's matching
 * lifecycle lock out of a subsequent numeric-id reuse transaction.
 */
export function runLittleBoyDocumentRequest<T>(
  identity: CapturedDocumentIdentity,
  request: () => Promise<T>,
): Promise<T> {
  if (!isCurrentLittleBoyIdentity(identity)) {
    return Promise.reject(new StaleLittleBoyResponseError());
  }

  let started: Promise<T> | undefined;
  const coordination = runPendingDocWrite(
    () => {
      try {
        started = request();
      } catch (error) {
        started = Promise.reject(error);
      }
      return started.then(
        () => undefined,
        () => undefined,
      );
    },
    identity.documentId,
  );

  // A close/delete guard rejects before invoking the factory. Preserve that
  // rejection for the caller without manufacturing a transport request.
  if (!started) {
    return coordination.then(() => {
      throw new Error('The LittleBoy request was not started.');
    }) as Promise<T>;
  }

  return started.then(
    (value) => {
      if (!isCurrentLittleBoyIdentity(identity)) {
        throw new StaleLittleBoyResponseError();
      }
      return value;
    },
    (error: unknown) => {
      if (!isCurrentLittleBoyIdentity(identity)) {
        throw new StaleLittleBoyResponseError();
      }
      throw error;
    },
  );
}
