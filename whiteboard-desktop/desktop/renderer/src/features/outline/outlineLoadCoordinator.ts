export interface OutlineLoadRequest {
  documentId: string;
  revision: number;
  controller: AbortController;
  signal: AbortSignal;
}

/**
 * One ordering domain for initial loads and out-of-band refreshes. Starting a
 * newer request invalidates and aborts every older path, regardless of origin.
 */
export class OutlineLoadCoordinator {
  private revision = 0;
  private activeController: AbortController | null = null;

  begin(documentId: string): OutlineLoadRequest {
    this.activeController?.abort();
    const controller = new AbortController();
    this.activeController = controller;
    return {
      documentId,
      revision: ++this.revision,
      controller,
      signal: controller.signal,
    };
  }

  isCurrent(request: OutlineLoadRequest, currentDocumentId: string): boolean {
    return !request.signal.aborted
      && request.revision === this.revision
      && request.documentId === currentDocumentId;
  }

  finish(request: OutlineLoadRequest): void {
    if (this.activeController === request.controller) this.activeController = null;
  }

  cancel(request?: OutlineLoadRequest): void {
    if (request && this.activeController !== request.controller) {
      request.controller.abort();
      return;
    }
    this.activeController?.abort();
    this.activeController = null;
    this.revision += 1;
  }
}
