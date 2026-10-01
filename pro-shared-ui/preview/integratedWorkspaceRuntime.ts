import type { ProjectDTO } from "@logosforge/ui-contracts";
import type { PlatformAdapter } from "../src/adapters/platform";

export type PreviewDataSource = "mock" | "live";

export interface PreviewStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export const PREVIEW_WORKSPACE_STORAGE_PREFIX = "logosforge.preview.integrated-workspace.v1";

export function previewWorkspaceStorageKey(
  source: PreviewDataSource,
  projectId: number,
  backup = false,
): string {
  return `${PREVIEW_WORKSPACE_STORAGE_PREFIX}.${source}.${projectId}${backup ? ".bak" : ""}`;
}

/** Browser host persistence with one recoverable generation per source/project. */
export function createPreviewLayoutPlatform(
  host: PlatformAdapter,
  source: PreviewDataSource,
  storage: PreviewStorage = localStorage,
): PlatformAdapter {
  return {
    isDesktop: host.isDesktop,
    openFile: (options) => host.openFile(options),
    saveFile: (options) => host.saveFile(options),
    openExternal: (target) => host.openExternal(target),
    navigate: host.navigate ? (target) => host.navigate?.(target) : undefined,
    loadLayout: async (projectId) => storage.getItem(previewWorkspaceStorageKey(source, projectId)),
    loadLayoutBackup: async (projectId) => storage.getItem(previewWorkspaceStorageKey(source, projectId, true)),
    saveLayout: async (projectId, layout, options) => {
      const currentKey = previewWorkspaceStorageKey(source, projectId);
      const backupKey = previewWorkspaceStorageKey(source, projectId, true);
      const current = storage.getItem(currentKey);
      const previousBackup = storage.getItem(backupKey);
      let rotated = false;
      try {
        if (!options?.preserveBackup && current !== null) {
          storage.setItem(backupKey, current);
          rotated = true;
        }
        storage.setItem(currentKey, JSON.stringify(layout));
      } catch (error) {
        if (rotated) {
          if (previousBackup === null) storage.removeItem(backupKey);
          else storage.setItem(backupKey, previousBackup);
        }
        throw error;
      }
    },
  };
}

/** Initial selection happens before project-scoped panels mount. */
export function selectPreviewBootstrapProject(
  projects: readonly ProjectDTO[],
  preferredProjectId: number | undefined,
): number | undefined {
  return projects.some((project) => project.id === preferredProjectId)
    ? preferredProjectId
    : projects[0]?.id;
}

export function previewProjectNeedsReconciliation(
  projects: readonly ProjectDTO[],
  activeProjectId: number | undefined,
): boolean {
  return activeProjectId !== undefined
    && !projects.some((project) => project.id === activeProjectId);
}

export interface PreviewUnloadState {
  projectDirty: boolean;
  projectWritesInFlight: number;
  projectFlushInProgress: boolean;
  layoutSaving: boolean;
  layoutError: Error | null;
  identityTransitioning: boolean;
}

/** Browsers cannot finish arbitrary async writes during unload; warn instead. */
export function previewUnloadNeedsConfirmation(state: PreviewUnloadState): boolean {
  return state.projectDirty
    || state.projectWritesInFlight > 0
    || state.projectFlushInProgress
    || state.layoutSaving
    || state.layoutError !== null
    || state.identityTransitioning;
}

/**
 * Reach a stable host boundary. A refresh may enqueue a project-open task while
 * it resolves, so both collections are re-read until neither changed.
 */
export async function drainPreviewIdentityOperations(
  refreshOperations: ReadonlySet<Promise<unknown>>,
  operationQueue: { current: Promise<void> },
  flushPendingSaves: () => Promise<void>,
): Promise<void> {
  while (true) {
    const refreshes = [...refreshOperations];
    const queued = operationQueue.current;
    await Promise.allSettled(refreshes);
    await queued;
    await flushPendingSaves();
    if (refreshOperations.size === 0 && operationQueue.current === queued) break;
  }
}
