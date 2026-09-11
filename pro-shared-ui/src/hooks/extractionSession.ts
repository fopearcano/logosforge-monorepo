import type { ExtractionApplyReportDTO } from "@logosforge/ui-contracts";

export interface RememberedExtractionState {
  jobId?: string;
  report?: ExtractionApplyReportDTO;
}

const memory = new Map<number, RememberedExtractionState>();
const key = (projectId: number) => `logosforge.extract.${projectId}`;

function clone(value: RememberedExtractionState): RememberedExtractionState {
  return JSON.parse(JSON.stringify(value)) as RememberedExtractionState;
}

export function rememberExtraction(projectId: number, value: RememberedExtractionState): void {
  const safe = clone(value);
  memory.set(projectId, safe);
  if (typeof sessionStorage === "undefined") return;
  try { sessionStorage.setItem(key(projectId), JSON.stringify(safe)); } catch { /* storage unavailable */ }
}

export function recallExtraction(projectId: number): RememberedExtractionState | null {
  const cached = memory.get(projectId);
  if (cached) return clone(cached);
  if (typeof sessionStorage === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(key(projectId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as RememberedExtractionState;
    if (!parsed || typeof parsed !== "object") return null;
    if (parsed.jobId != null && typeof parsed.jobId !== "string") return null;
    memory.set(projectId, clone(parsed));
    return clone(parsed);
  } catch {
    return null;
  }
}

export function forgetExtraction(projectId: number): void {
  memory.delete(projectId);
  if (typeof sessionStorage === "undefined") return;
  try { sessionStorage.removeItem(key(projectId)); } catch { /* storage unavailable */ }
}
