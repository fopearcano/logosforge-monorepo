/** Synchronously invalidates asynchronous renderer work when core identity changes. */

export interface CoreGenerationStatus {
  readonly state: "connecting" | "connected" | "error";
  readonly baseUrl: string;
  readonly managed: boolean;
  readonly authToken?: string;
}

function statusIdentity(status: CoreGenerationStatus): string {
  return JSON.stringify([
    status.state,
    status.baseUrl,
    status.authToken ?? "",
    status.managed,
  ]);
}

export class CoreGenerationTracker {
  private identity: string | null = null;
  private generation = 0;

  observe(status: CoreGenerationStatus): number {
    const nextIdentity = statusIdentity(status);
    if (nextIdentity !== this.identity) {
      this.identity = nextIdentity;
      this.generation += 1;
    }
    return this.generation;
  }

  current(): number {
    return this.generation;
  }

  isCurrent(generation: number): boolean {
    return generation === this.generation;
  }
}
