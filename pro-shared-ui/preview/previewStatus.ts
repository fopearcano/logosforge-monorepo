import type { WorkspaceStatusModel } from "../src";

/** Explicit local-only state for static preview hosts that have no save runtime. */
export const previewWorkspaceStatus: WorkspaceStatusModel = Object.freeze({
  kind: "ready",
  priority: 10,
  tone: "neutral",
  copy: "LOCAL · READY",
  detail: "Preview data is stored only in this browser session.",
  storage: "local",
  storageCopy: "LOCAL",
  dirty: false,
  inFlightCount: 0,
  lastSavedAt: null,
});
