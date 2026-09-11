import type { ExtractionJobDTO } from "@logosforge/ui-contracts";

export class ExtractionPollingCancelled extends Error {
  constructor() {
    super("Extraction polling cancelled");
    this.name = "ExtractionPollingCancelled";
  }
}

export type ExtractionPollOutcome = {
  kind: "done" | "error" | "cancelled" | "timeout";
  job: ExtractionJobDTO;
};

function wait(ms: number, signal: AbortSignal): Promise<void> {
  if (signal.aborted) return Promise.reject(new ExtractionPollingCancelled());
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(new ExtractionPollingCancelled());
    };
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

export async function pollExtractionJob({
  initial,
  load,
  signal,
  onProgress,
  intervalMs = 900,
  maxPolls = 800,
}: {
  initial: ExtractionJobDTO;
  load: () => Promise<ExtractionJobDTO>;
  signal: AbortSignal;
  onProgress?: (job: ExtractionJobDTO) => void;
  intervalMs?: number;
  maxPolls?: number;
}): Promise<ExtractionPollOutcome> {
  let current = initial;
  onProgress?.(current);
  let polls = 0;
  while ((current.status === "running" || current.status === "cancelling") && polls < maxPolls) {
    await wait(intervalMs, signal);
    if (signal.aborted) throw new ExtractionPollingCancelled();
    current = await load();
    if (signal.aborted) throw new ExtractionPollingCancelled();
    polls += 1;
    onProgress?.(current);
  }
  if (current.status === "running" || current.status === "cancelling") {
    return { kind: "timeout", job: current };
  }
  if (current.status === "done") return { kind: "done", job: current };
  if (current.status === "cancelled") return { kind: "cancelled", job: current };
  return { kind: "error", job: current };
}
