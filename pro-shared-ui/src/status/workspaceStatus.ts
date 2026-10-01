import type { ProjectSaveStatusSnapshot } from "../adapters/projectSaveCoordinator";

export type WorkspaceCoreState = "connecting" | "connected" | "error";
export type WorkspaceHandoffPhase = "idle" | "switching" | "closing";
export type WorkspaceStatusTone = "neutral" | "info" | "success" | "warning" | "danger";

export type WorkspaceStatusKind =
  | "save-error"
  | "core-error-unsaved"
  | "core-error"
  | "layout-error"
  | "closing"
  | "switching"
  | "connecting-unsaved"
  | "connecting"
  | "saving"
  | "dirty"
  | "layout-saving"
  | "saved"
  | "ready";

export interface WorkspaceStatusInput {
  coreState: WorkspaceCoreState;
  coreDetail?: string;
  projectSave: ProjectSaveStatusSnapshot;
  workspaceLayoutSaving: boolean;
  workspaceLayoutError: unknown | null;
  handoffPhase: WorkspaceHandoffPhase;
  /** Pro currently persists on-device only; no cloud-sync claim is permitted. */
  storage: "local";
}

/** Pure render model shared by future desktop and web status surfaces. */
export interface WorkspaceStatusModel {
  kind: WorkspaceStatusKind;
  /** Higher values represent states that demand more immediate attention. */
  priority: number;
  tone: WorkspaceStatusTone;
  copy: string;
  detail: string;
  storage: "local";
  storageCopy: "LOCAL";
  dirty: boolean;
  inFlightCount: number;
  lastSavedAt: number | null;
}

function errorMessage(value: unknown): string {
  if (value instanceof Error) return value.message.trim();
  if (typeof value === "string") return value.trim();
  if (value == null) return "";
  try { return String(value).trim(); } catch { return ""; }
}

function withReason(prefix: string, reason: unknown): string {
  const message = errorMessage(reason);
  return message ? `${prefix} ${message}` : prefix;
}

/**
 * Reduce independent lifecycle signals to one truthful local-persistence state.
 * This deliberately models neither cloud sync nor file locks/conflicts: neither
 * capability exists in the current Pro transport contract.
 */
export function deriveWorkspaceStatus(input: WorkspaceStatusInput): WorkspaceStatusModel {
  const { projectSave } = input;
  const dirty = projectSave.dirty
    || projectSave.dirtyRevision > projectSave.savedRevision
    || projectSave.lastError !== null;
  const saving = projectSave.flushing || projectSave.inFlightCount > 0;
  const base = {
    storage: input.storage,
    storageCopy: "LOCAL" as const,
    dirty,
    inFlightCount: projectSave.inFlightCount,
    lastSavedAt: projectSave.lastSavedAt,
  };
  const status = (
    kind: WorkspaceStatusKind,
    priority: number,
    tone: WorkspaceStatusTone,
    copy: string,
    detail: string,
  ): WorkspaceStatusModel => ({ kind, priority, tone, copy, detail, ...base });

  if (projectSave.lastError !== null) {
    return status(
      "save-error",
      100,
      "danger",
      "SAVE FAILED",
      withReason("Pending project changes were not fully saved.", projectSave.lastError),
    );
  }
  if (input.coreState === "error" && (dirty || saving)) {
    return status(
      "core-error-unsaved",
      95,
      "danger",
      "CORE UNAVAILABLE · UNSAVED",
      withReason("Pending changes still need the local core.", input.coreDetail),
    );
  }
  if (input.coreState === "error") {
    return status(
      "core-error",
      90,
      "danger",
      "CORE UNAVAILABLE",
      withReason("The local core is unavailable.", input.coreDetail),
    );
  }
  if (input.workspaceLayoutError != null) {
    return status(
      "layout-error",
      80,
      "warning",
      "WORKSPACE LAYOUT NEEDS ATTENTION",
      withReason("Project data may be saved, but the local workspace layout was not.", input.workspaceLayoutError),
    );
  }
  if (input.handoffPhase === "closing") {
    return status(
      "closing",
      70,
      "info",
      dirty || saving || input.workspaceLayoutSaving ? "SAVING BEFORE CLOSE" : "CLOSING",
      dirty || saving || input.workspaceLayoutSaving
        ? "Pending local changes are being drained before the workspace closes."
        : "The workspace is closing.",
    );
  }
  if (input.handoffPhase === "switching") {
    return status(
      "switching",
      65,
      "info",
      dirty || saving || input.workspaceLayoutSaving ? "SAVING BEFORE SWITCH" : "SWITCHING PROJECT",
      dirty || saving || input.workspaceLayoutSaving
        ? "Pending local changes are being drained before the project changes."
        : "The active project is changing.",
    );
  }
  if (input.coreState === "connecting" && (dirty || saving)) {
    return status(
      "connecting-unsaved",
      60,
      "warning",
      "UNSAVED · CONNECTING",
      "Changes are pending while the local core connects.",
    );
  }
  if (input.coreState === "connecting") {
    return status(
      "connecting",
      55,
      "info",
      "CONNECTING TO CORE",
      withReason("Connecting to the local core.", input.coreDetail),
    );
  }
  if (saving) {
    return status(
      "saving",
      50,
      "info",
      projectSave.inFlightCount > 1
        ? `SAVING LOCALLY · ${projectSave.inFlightCount}`
        : "SAVING LOCALLY",
      "Project changes are being saved on this device.",
    );
  }
  if (dirty) {
    return status(
      "dirty",
      40,
      "warning",
      "UNSAVED CHANGES",
      "Project changes are waiting to be saved on this device.",
    );
  }
  if (input.workspaceLayoutSaving) {
    return status(
      "layout-saving",
      30,
      "info",
      "SAVING WORKSPACE",
      "The workspace layout is being saved on this device.",
    );
  }
  if (projectSave.lastSavedAt !== null) {
    return status(
      "saved",
      20,
      "success",
      "SAVED LOCALLY",
      "Project changes are saved on this device.",
    );
  }
  return status(
    "ready",
    10,
    "neutral",
    "LOCAL · READY",
    "Project data is stored on this device.",
  );
}
