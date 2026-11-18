import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import type { CloudProjectSnapshotDTO } from "@logosforge/ui-contracts";
import { flushPendingProjectSaves } from "../../adapters/projectSaveCoordinator";
import { useStudio } from "../../adapters/StudioProvider";
import type {
  CloudSyncActionKind,
  CloudSyncActionReceipt,
  CloudSyncBinding,
  CloudSyncHost,
  CloudSyncProjectInventory,
  CloudSyncSnapshotMetadata,
  CloudSyncState,
} from "../../adapters/platform";
import {
  completedReceiptPublish,
  decideCloudSync,
  matchingDescendantHead,
  newestCloudHead,
} from "./model";

// Complete snapshots are intentionally versioned, so automatic publishing is
// coarse-grained. Provider inventory still polls in the desktop host and Sync
// Now remains immediate.
const AUTO_INTERVAL_MS = 10 * 60_000;

export type ProCloudSyncStatus =
  | "unavailable"
  | "disabled"
  | "checking"
  | "syncing"
  | "up-to-date"
  | "attention"
  | "error";

export interface ProCloudSyncReview {
  projectId: number;
  localIncarnation: string;
  localDigest: string;
  localSnapshot: CloudProjectSnapshotDTO;
  binding: CloudSyncBinding;
  inventory: CloudSyncProjectInventory;
  heads: CloudSyncSnapshotMetadata[];
  reason: string;
}
export interface ProCloudSyncViewState {
  available: boolean;
  status: ProCloudSyncStatus;
  detail: string;
  busy: boolean;
  native: CloudSyncState | null;
  review: ProCloudSyncReview | null;
  activeProjectId: number | null;
}

export interface ProCloudSyncActions {
  chooseFolder(): Promise<void>;
  disable(): Promise<void>;
  setAutomatic(value: boolean): Promise<void>;
  syncNow(): Promise<void>;
  retryOutbox(): Promise<void>;
  useCloudCopy(): Promise<void>;
  replaceCloudCopy(): Promise<void>;
  keepBoth(): Promise<void>;
  importRemote(cloudProjectId: string): Promise<void>;
  recoverRemoteHead(cloudProjectId: string, snapshotId: string): Promise<void>;
  ignoreRemote(cloudProjectId: string): Promise<void>;
  forgetActiveBinding(): Promise<void>;
}

const UNAVAILABLE: ProCloudSyncViewState = {
  available: false,
  status: "unavailable",
  detail: "Cloud Folder Sync is available in the LogosForge Pro desktop app.",
  busy: false,
  native: null,
  review: null,
  activeProjectId: null,
};

const noAction = async () => {};
let externalState = UNAVAILABLE;
let externalActions: ProCloudSyncActions = {
  chooseFolder: noAction,
  disable: noAction,
  setAutomatic: async () => {},
  syncNow: noAction,
  retryOutbox: noAction,
  useCloudCopy: noAction,
  replaceCloudCopy: noAction,
  keepBoth: noAction,
  importRemote: async () => {},
  recoverRemoteHead: async () => {},
  ignoreRemote: async () => {},
  forgetActiveBinding: noAction,
};
const listeners = new Set<() => void>();

function publishExternal(state: ProCloudSyncViewState, actions: ProCloudSyncActions): void {
  externalState = state;
  externalActions = actions;
  for (const listener of listeners) listener();
}

export function useProCloudSync(): {
  state: ProCloudSyncViewState;
  actions: ProCloudSyncActions;
} {
  const state = useSyncExternalStore(
    (listener) => { listeners.add(listener); return () => listeners.delete(listener); },
    () => externalState,
    () => UNAVAILABLE,
  );
  return { state, actions: externalActions };
}

function errorMessage(error: unknown): string {
  return error instanceof Error && error.message.trim()
    ? error.message.trim()
    : "Cloud Folder Sync could not complete.";
}

function bindingForProject(
  state: CloudSyncState,
  projectId: number,
  incarnation: string,
): CloudSyncBinding | null {
  const localProjectId = String(projectId);
  return state.bindings.find((binding) => (
    binding.localProjectId === localProjectId && binding.localIncarnation === incarnation
  )) ?? null;
}

function inventoryForBinding(
  state: CloudSyncState,
  binding: CloudSyncBinding,
): CloudSyncProjectInventory | null {
  return state.projects.find((project) => project.cloudProjectId === binding.cloudProjectId) ?? null;
}

function actionId(): string {
  const uuid = globalThis.crypto?.randomUUID?.();
  if (uuid) return uuid;
  // RFC-4122-shaped fallback for older embedded runtimes. `kind` is persisted
  // in its own receipt field and must not be prefixed to the Core UUID key.
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (token) => {
    const random = Math.floor(Math.random() * 16);
    return (token === "x" ? random : (random & 0x3) | 0x8).toString(16);
  });
}

const ACTION_PHASE_ORDER = {
  prepared: 0,
  "local-forked": 1,
  restored: 2,
  "binding-installed": 3,
} as const;

function snapshotIdentity(snapshot: CloudProjectSnapshotDTO): string {
  return snapshot.project.sync_id || snapshot.project_identity;
}

function asProjectId(value: string): number | null {
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

function sameIdSet(left: readonly string[], right: readonly string[]): boolean {
  if (left.length !== right.length) return false;
  const wanted = new Set(left);
  return wanted.size === left.length && right.every((id) => wanted.has(id));
}

function matchingReceipt(
  state: CloudSyncState,
  kind: CloudSyncActionKind,
  review: ProCloudSyncReview,
  head: CloudSyncSnapshotMetadata,
): CloudSyncActionReceipt | null {
  return state.actionReceipts.find((receipt) => (
    receipt.kind === kind
    && receipt.sourceLocalProjectId === String(review.projectId)
    && receipt.sourceLocalIncarnation === review.localIncarnation
    && receipt.originalCloudProjectId === review.binding.cloudProjectId
    && receipt.snapshotId === head.snapshotId
    && receipt.snapshotDigest === head.digest
    && receipt.expectedSourceDigest === review.localDigest
    && ((kind !== "keep-both" && kind !== "replace-cloud")
      || sameIdSet(receipt.parentSnapshotIds, review.heads.map((candidate) => candidate.snapshotId)))
  )) ?? null;
}

/**
 * Always-mounted desktop controller. Render it once inside StudioProvider; the
 * dockable Cloud Sync panel consumes its external store and may be closed
 * without stopping automatic synchronization.
 */
export function ProCloudSyncController() {
  const studio = useStudio();
  const { api, platform, projectId, refreshProjects, selectProject } = studio;
  const host = platform.cloudSync;
  const [view, setView] = useState<ProCloudSyncViewState>(() => ({
    ...UNAVAILABLE,
    available: !!host,
    status: host ? "checking" : "unavailable",
    detail: host ? "Checking the provider-managed folder…" : UNAVAILABLE.detail,
    activeProjectId: projectId ?? null,
  }));
  const viewRef = useRef(view);
  viewRef.current = view;
  const mountedRef = useRef(true);
  const operationTailRef = useRef<Promise<void>>(Promise.resolve());
  const runningRef = useRef<Promise<void> | null>(null);
  const rerunRef = useRef(false);

  const runSerialized = useCallback(<T,>(operation: () => Promise<T>): Promise<T> => {
    const run = operationTailRef.current.catch(() => undefined).then(operation);
    operationTailRef.current = run.then(() => undefined, () => undefined);
    return run;
  }, []);

  const commit = useCallback((patch: Partial<ProCloudSyncViewState>) => {
    if (!mountedRef.current) return;
    setView((current) => ({ ...current, ...patch, activeProjectId: projectId ?? null }));
  }, [projectId]);

  const readSnapshot = useCallback(async (ownerProjectId: number): Promise<CloudProjectSnapshotDTO> => {
    if (!api.getCloudProjectSnapshot) throw new Error("This Core does not support Pro cloud snapshots.");
    return api.getCloudProjectSnapshot(ownerProjectId);
  }, [api]);

  const installBinding = useCallback(async (
    cloudHost: CloudSyncHost,
    ownerProjectId: number,
    incarnation: string,
    cloudProjectId: string,
    snapshot: CloudSyncSnapshotMetadata,
  ) => {
    await cloudHost.setBinding({
      localProjectId: String(ownerProjectId), localIncarnation: incarnation,
      cloudProjectId, snapshotId: snapshot.snapshotId, digest: snapshot.digest,
    });
  }, []);

  const recoverActionReceipts = useCallback(async (
    cloudHost: CloudSyncHost,
    initial: CloudSyncState,
  ): Promise<CloudSyncState> => {
    let native = initial;
    let changed = false;
    let firstError: unknown = null;
    for (const original of [...initial.actionReceipts]) {
      const receipt = native.actionReceipts.find((item) => item.actionId === original.actionId);
      if (!receipt) continue;
      const inventory = native.projects.find((item) => (
        item.cloudProjectId === receipt.originalCloudProjectId
      )) ?? null;
      const remote = inventory?.snapshots.find((item) => (
        item.snapshotId === receipt.snapshotId && item.digest === receipt.snapshotDigest
      )) ?? null;
      if (!remote) continue;
      try {
        const envelope = await cloudHost.readSnapshot(
          receipt.originalCloudProjectId,
          receipt.snapshotId,
        );

        if (receipt.kind === "discover" || receipt.kind === "remote-recovery") {
          if (!api.importCloudProject) continue;
          const restored = await api.importCloudProject({
            restore_id: receipt.actionId,
            snapshot: envelope.bundle as CloudProjectSnapshotDTO,
            mode: receipt.kind === "discover" ? "import" : "fork",
          });
          if (ACTION_PHASE_ORDER[receipt.phase] < ACTION_PHASE_ORDER.restored) {
            await cloudHost.saveActionReceipt({
              ...receipt,
              phase: "restored",
              restoredLocalProjectId: String(restored.project_id),
              restoredLocalIncarnation: restored.project_identity,
            });
          }
          if (receipt.kind === "remote-recovery") {
            await cloudHost.removeRecoveredRemoteHead(
              receipt.originalCloudProjectId,
              receipt.snapshotId,
            );
          } else {
            await installBinding(
              cloudHost,
              restored.project_id,
              restored.project_identity,
              receipt.originalCloudProjectId,
              remote,
            );
            if (ACTION_PHASE_ORDER[receipt.phase] < ACTION_PHASE_ORDER["binding-installed"]) {
              await cloudHost.saveActionReceipt({
                ...receipt,
                phase: "binding-installed",
                restoredLocalProjectId: String(restored.project_id),
                restoredLocalIncarnation: restored.project_identity,
              });
            }
          }
          await cloudHost.completeActionReceipt(receipt.actionId);
          native = await cloudHost.getState();
          changed = true;
          continue;
        }

        const sourceProjectId = asProjectId(receipt.sourceLocalProjectId);
        if (sourceProjectId == null) continue;
        let source = await readSnapshot(sourceProjectId);
        let sourceDigest = await cloudHost.digest(source);

        if (receipt.kind === "pull" || receipt.kind === "use-cloud") {
          let restoredProjectId = sourceProjectId;
          let restoredIncarnation = snapshotIdentity(source);
          if (sourceDigest !== receipt.snapshotDigest) {
            if (sourceDigest !== receipt.expectedSourceDigest || !api.restoreCloudProject) continue;
            const restored = await api.restoreCloudProject(sourceProjectId, {
              restore_id: receipt.actionId,
              snapshot: envelope.bundle as CloudProjectSnapshotDTO,
              expected_current_digest: source.digest,
            });
            restoredProjectId = restored.project_id;
            restoredIncarnation = restored.project_identity;
            if (ACTION_PHASE_ORDER[receipt.phase] < ACTION_PHASE_ORDER.restored) {
              await cloudHost.saveActionReceipt({
                ...receipt,
                phase: "restored",
                restoredLocalProjectId: String(restoredProjectId),
                restoredLocalIncarnation: restoredIncarnation,
              });
            }
          }
          await installBinding(
            cloudHost,
            restoredProjectId,
            restoredIncarnation,
            receipt.originalCloudProjectId,
            remote,
          );
          if (ACTION_PHASE_ORDER[receipt.phase] < ACTION_PHASE_ORDER["binding-installed"]) {
            await cloudHost.saveActionReceipt({
              ...receipt,
              phase: "binding-installed",
              restoredLocalProjectId: String(restoredProjectId),
              restoredLocalIncarnation: restoredIncarnation,
            });
          }
          await cloudHost.completeActionReceipt(receipt.actionId);
          native = await cloudHost.getState();
          changed = true;
          continue;
        }

        if (receipt.kind !== "keep-both" && receipt.kind !== "replace-cloud") continue;
        if (sourceDigest !== receipt.expectedSourceDigest
          || snapshotIdentity(source) !== receipt.sourceLocalIncarnation) continue;

        if (receipt.kind === "keep-both") {
          if (!api.importCloudProject) continue;
          const restored = await api.importCloudProject({
            restore_id: receipt.actionId,
            snapshot: envelope.bundle as CloudProjectSnapshotDTO,
            mode: "fork",
          });
          if (ACTION_PHASE_ORDER[receipt.phase] < ACTION_PHASE_ORDER["local-forked"]) {
            await cloudHost.saveActionReceipt({
              ...receipt,
              phase: "local-forked",
              restoredLocalProjectId: String(restored.project_id),
              restoredLocalIncarnation: restored.project_identity,
            });
          }
        }

        const superseded = receipt.kind === "keep-both"
          ? receipt.parentSnapshotIds.filter((id) => id !== receipt.snapshotId)
          : receipt.parentSnapshotIds;
        if (superseded.length) {
          await cloudHost.recordRecoveredRemoteHeads(
            receipt.originalCloudProjectId,
            superseded,
          );
        }
        native = await cloudHost.getState();
        const refreshedInventory = native.projects.find((item) => (
          item.cloudProjectId === receipt.originalCloudProjectId
        )) ?? inventory;
        let committed = completedReceiptPublish(receipt, refreshedInventory);
        if (!committed) {
          source = await readSnapshot(sourceProjectId);
          sourceDigest = await cloudHost.digest(source);
          if (sourceDigest !== receipt.expectedSourceDigest) continue;
          const published = await cloudHost.publish({
            localProjectId: receipt.sourceLocalProjectId,
            localIncarnation: receipt.sourceLocalIncarnation,
            bundle: source,
            cloudProjectId: receipt.originalCloudProjectId,
            parentSnapshotIds: receipt.parentSnapshotIds,
          });
          committed = published.snapshot;
        }
        await installBinding(
          cloudHost,
          sourceProjectId,
          receipt.sourceLocalIncarnation,
          receipt.originalCloudProjectId,
          committed,
        );
        await cloudHost.completeActionReceipt(receipt.actionId);
        native = await cloudHost.getState();
        changed = true;
      } catch (error) {
        firstError ??= error;
      }
    }
    if (changed) refreshProjects?.();
    if (firstError) {
      throw new Error(`An interrupted cloud action could not be recovered. ${errorMessage(firstError)}`);
    }
    return native;
  }, [api, installBinding, readSnapshot, refreshProjects]);

  const synchronize = useCallback(async (allowWrites: boolean): Promise<void> => {
    if (!host || projectId == null) return;
    if (runningRef.current) {
      rerunRef.current = rerunRef.current || allowWrites;
      return runningRef.current;
    }
    const run = runSerialized(async () => {
      commit({ status: "syncing", busy: true, detail: "Saving and comparing complete project snapshots…" });
      try {
        await flushPendingProjectSaves({ commitActiveField: true });
        let native = await host.retryOutbox();
        if (!native.enabled) {
          commit({ native, review: null, status: "disabled", busy: false,
            detail: "Choose a provider-managed folder to synchronize this project." });
          return;
        }
        if (!native.folderAvailable) {
          commit({ native, status: "error", busy: false,
            detail: native.lastError || "The selected provider folder is not available." });
          return;
        }
        native = await recoverActionReceipts(host, native);
        const localSnapshot = await readSnapshot(projectId);
        const localDigest = await host.digest(localSnapshot);
        const incarnation = snapshotIdentity(localSnapshot);
        let binding = bindingForProject(native, projectId, incarnation);
        if (!binding) {
          // Recover an interrupted first publish (or a history created by this
          // same portable project on another device) instead of seeding a
          // duplicate cloud project.
          const boundCloudIds = new Set(native.bindings.map((item) => item.cloudProjectId));
          const candidates: Array<{
            cloudProjectId: string;
            snapshot: CloudSyncSnapshotMetadata;
          }> = [];
          for (const cloudProject of native.projects) {
            if (boundCloudIds.has(cloudProject.cloudProjectId)
              || native.ignoredCloudProjectIds.includes(cloudProject.cloudProjectId)) continue;
            for (const candidate of cloudProject.snapshots) {
              if (candidate.digest !== localDigest) continue;
              try {
                const envelope = await host.readSnapshot(
                  cloudProject.cloudProjectId,
                  candidate.snapshotId,
                );
                if (snapshotIdentity(envelope.bundle as CloudProjectSnapshotDTO) === incarnation) {
                  candidates.push({ cloudProjectId: cloudProject.cloudProjectId, snapshot: candidate });
                }
              } catch { /* an invalid provider file is already reported by the host */ }
            }
          }
          if (candidates.length === 1) {
            const recovered = candidates[0]!;
            await installBinding(
              host,
              projectId,
              incarnation,
              recovered.cloudProjectId,
              recovered.snapshot,
            );
            native = await host.getState();
            binding = bindingForProject(native, projectId, incarnation);
          } else if (candidates.length > 1) {
            commit({
              native,
              review: null,
              busy: false,
              status: "attention",
              detail: "More than one matching cloud history exists. Nothing was overwritten; review the provider projects before linking this copy.",
            });
            return;
          }
        }
        let inventory = binding ? inventoryForBinding(native, binding) : null;
        if (binding && inventory) {
          const adopted = matchingDescendantHead(localDigest, binding, inventory);
          if (adopted && adopted.snapshotId !== binding.lastSnapshotId) {
            await installBinding(
              host,
              projectId,
              incarnation,
              binding.cloudProjectId,
              adopted,
            );
            native = await host.getState();
            binding = bindingForProject(native, projectId, incarnation);
            inventory = binding ? inventoryForBinding(native, binding) : null;
          }
        }
        const decision = decideCloudSync(localDigest, binding, inventory);
        const reviewInventory = binding && !inventory ? {
          cloudProjectId: binding.cloudProjectId,
          title: localSnapshot.project.title,
          snapshots: [],
          headSnapshotIds: [],
        } : inventory;

        if (!allowWrites) {
          const review = binding && reviewInventory && (decision.kind === "conflict" || decision.kind === "remote-missing")
            ? { projectId, localIncarnation: incarnation, localDigest, localSnapshot,
              binding, inventory: reviewInventory, heads: decision.heads, reason: decision.reason }
            : null;
          commit({ native, review, busy: false,
            status: review ? "attention" : decision.kind === "idle" ? "up-to-date" : "attention",
            detail: decision.reason });
          return;
        }

        if (decision.kind === "seed") {
          await host.publish({
            localProjectId: String(projectId), localIncarnation: incarnation,
            bundle: localSnapshot, createNewProject: true,
          });
        } else if (decision.kind === "push" && binding) {
          await host.publish({
            localProjectId: String(projectId), localIncarnation: incarnation,
            bundle: localSnapshot, cloudProjectId: binding.cloudProjectId,
            parentSnapshotIds: [binding.lastSnapshotId],
          });
        } else if (decision.kind === "pull" && binding) {
          const head = decision.heads[0]!;
          const envelope = await host.readSnapshot(binding.cloudProjectId, head.snapshotId);
          if (!api.restoreCloudProject) throw new Error("This Core cannot restore cloud snapshots.");
          const existingReceipt = native.actionReceipts.find((receipt) => (
            receipt.kind === "pull"
            && receipt.sourceLocalProjectId === String(projectId)
            && receipt.sourceLocalIncarnation === incarnation
            && receipt.originalCloudProjectId === binding.cloudProjectId
            && receipt.snapshotId === head.snapshotId
            && receipt.snapshotDigest === head.digest
            && receipt.expectedSourceDigest === localDigest
          ));
          const pullId = existingReceipt?.actionId ?? actionId();
          if (!existingReceipt) {
            await host.saveActionReceipt({
              actionId: pullId, kind: "pull", phase: "prepared",
              sourceLocalProjectId: String(projectId),
              sourceLocalIncarnation: incarnation,
              originalCloudProjectId: binding.cloudProjectId,
              snapshotId: head.snapshotId, snapshotDigest: head.digest,
              parentSnapshotIds: head.parentSnapshotIds,
              expectedSourceDigest: localDigest,
            });
          }
          const restored = await api.restoreCloudProject(projectId, {
            restore_id: pullId,
            snapshot: envelope.bundle as CloudProjectSnapshotDTO,
            expected_current_digest: localSnapshot.digest,
          });
          const receiptBase = existingReceipt ?? {
            actionId: pullId, kind: "pull" as const, phase: "prepared" as const,
            sourceLocalProjectId: String(projectId), sourceLocalIncarnation: incarnation,
            originalCloudProjectId: binding.cloudProjectId, intendedCloudProjectId: null,
            snapshotId: head.snapshotId, snapshotDigest: head.digest,
            parentSnapshotIds: head.parentSnapshotIds, expectedSourceDigest: localDigest,
            restoredLocalProjectId: null, restoredLocalIncarnation: null,
            createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(),
          };
          await host.saveActionReceipt({ ...receiptBase, phase: "restored",
            restoredLocalProjectId: String(restored.project_id), restoredLocalIncarnation: restored.project_identity });
          await installBinding(host, projectId, restored.project_identity, binding.cloudProjectId, head);
          await host.saveActionReceipt({ ...receiptBase, phase: "binding-installed",
            restoredLocalProjectId: String(restored.project_id), restoredLocalIncarnation: restored.project_identity });
          await host.completeActionReceipt(pullId);
          api.invalidatePendingReads?.();
          refreshProjects?.();
        } else if (decision.kind === "conflict" && binding && inventory) {
          commit({ native, busy: false, status: "attention", detail: decision.reason,
            review: { projectId, localIncarnation: incarnation, localDigest, localSnapshot,
              binding, inventory, heads: decision.heads, reason: decision.reason } });
          return;
        } else if (decision.kind === "remote-missing" && binding && reviewInventory) {
          commit({ native, busy: false, status: "attention", detail: decision.reason,
            review: { projectId, localIncarnation: incarnation, localDigest, localSnapshot,
              binding, inventory: reviewInventory, heads: decision.heads, reason: decision.reason } });
          return;
        }

        native = await host.getState();
        commit({ native, review: null, busy: false, status: "up-to-date",
          detail: native.outboxCount
            ? `${native.outboxCount} snapshot${native.outboxCount === 1 ? "" : "s"} safely queued for delivery.`
            : "Complete project snapshot is up to date." });
      } catch (error) {
        commit({ busy: false, status: "error", detail: errorMessage(error) });
      } finally {
        runningRef.current = null;
        if (rerunRef.current) {
          rerunRef.current = false;
          void synchronize(true);
        }
      }
    });
    runningRef.current = run;
    return run;
  }, [api, commit, host, installBinding, projectId, readSnapshot, recoverActionReceipts,
    refreshProjects, runSerialized]);

  const withReview = useCallback(async (
    kind: CloudSyncActionKind,
    operation: (
      review: ProCloudSyncReview,
      head: CloudSyncSnapshotMetadata,
      receipt: CloudSyncActionReceipt,
    ) => Promise<void>,
  ) => {
    if (!host) return;
    return runSerialized(async () => {
      const review = viewRef.current.review;
      const native = viewRef.current.native;
      if (!review || !native) throw new Error("There is no cloud conflict to resolve.");
      const head = newestCloudHead(review.heads);
      if (!head) throw new Error("The cloud history has no recoverable head.");
      commit({ busy: true, status: "syncing", detail: "Preparing a recoverable cloud action…" });
      try {
        await flushPendingProjectSaves({ commitActiveField: true });
        const current = await readSnapshot(review.projectId);
        const currentDigest = await host.digest(current);
        if (currentDigest !== review.localDigest) {
          throw new Error("The local project changed after this comparison. Check again before choosing.");
        }
        let receipt = matchingReceipt(native, kind, review, head);
        if (!receipt) {
          const id = actionId();
          const mergeParents = kind === "keep-both" || kind === "replace-cloud"
            ? review.heads.map((candidate) => candidate.snapshotId)
            : head.parentSnapshotIds;
          const saved = await host.saveActionReceipt({
            actionId: id, kind, phase: "prepared",
            sourceLocalProjectId: String(review.projectId),
            sourceLocalIncarnation: review.localIncarnation,
            originalCloudProjectId: review.binding.cloudProjectId,
            snapshotId: head.snapshotId, snapshotDigest: head.digest,
            parentSnapshotIds: mergeParents,
            expectedSourceDigest: review.localDigest,
          });
          receipt = saved.actionReceipts.find((candidate) => candidate.actionId === id) ?? null;
        }
        if (!receipt) throw new Error("The recovery receipt could not be saved.");
        await operation(review, head, receipt);
        await host.completeActionReceipt(receipt.actionId);
        const next = await host.getState();
        commit({ native: next, review: null, busy: false, status: "up-to-date",
          detail: "Cloud recovery completed; superseded provider heads remain available in Recovery Log." });
      } catch (error) {
        commit({ busy: false, status: "error", detail: errorMessage(error) });
      }
    });
  }, [commit, host, readSnapshot, runSerialized]);

  const chooseFolder = useCallback(async () => {
    if (!host) return;
    const shouldSync = await runSerialized(async () => {
      commit({ busy: true, status: "checking", detail: "Choosing a provider-managed folder…" });
      try {
        const native = await host.chooseFolder();
        commit({ native, busy: false, status: native.enabled ? "checking" : "disabled",
          detail: native.enabled ? "Folder linked. Creating the first safe snapshot…" : "Folder selection was cancelled." });
        return native.enabled;
      } catch (error) {
        commit({ busy: false, status: "error", detail: errorMessage(error) });
        return false;
      }
    });
    if (shouldSync) await synchronize(true);
  }, [commit, host, runSerialized, synchronize]);

  const disable = useCallback(async () => {
    if (!host) return;
    await runSerialized(async () => {
      const native = await host.disable();
      commit({ native, review: null, busy: false, status: "disabled",
        detail: "Automatic Cloud Folder Sync is disabled. Existing provider snapshots were kept." });
    });
  }, [commit, host, runSerialized]);

  const setAutomatic = useCallback(async (automatic: boolean) => {
    if (!host) return;
    await runSerialized(async () => {
      const native = await host.setAutomatic(automatic);
      commit({ native, detail: automatic ? "Automatic synchronization enabled." : "Automatic synchronization paused." });
    });
    if (automatic) await synchronize(true);
  }, [commit, host, runSerialized, synchronize]);

  const retryOutbox = useCallback(async () => {
    if (!host) return;
    await runSerialized(async () => {
      try { commit({ busy: true }); commit({ native: await host.retryOutbox(), busy: false }); }
      catch (error) { commit({ busy: false, status: "error", detail: errorMessage(error) }); }
    });
  }, [commit, host, runSerialized]);

  const useCloudCopy = useCallback(() => withReview("use-cloud", async (review, head, receipt) => {
    if (!host || !api.restoreCloudProject) throw new Error("Cloud restore is unavailable.");
    const envelope = await host.readSnapshot(review.binding.cloudProjectId, head.snapshotId);
    const restored = await api.restoreCloudProject(review.projectId, {
      restore_id: receipt.actionId,
      snapshot: envelope.bundle as CloudProjectSnapshotDTO,
      expected_current_digest: review.localSnapshot.digest,
    });
    await host.saveActionReceipt({ ...receipt, phase: "restored",
      restoredLocalProjectId: String(restored.project_id), restoredLocalIncarnation: restored.project_identity });
    await installBinding(host, restored.project_id, restored.project_identity, review.binding.cloudProjectId, head);
    await host.saveActionReceipt({ ...receipt, phase: "binding-installed",
      restoredLocalProjectId: String(restored.project_id), restoredLocalIncarnation: restored.project_identity });
    api.invalidatePendingReads?.();
    refreshProjects?.();
  }), [api, host, installBinding, refreshProjects, withReview]);

  const replaceCloudCopy = useCallback(() => withReview("replace-cloud", async (review, _head, receipt) => {
    if (!host) return;
    const snapshot = await readSnapshot(review.projectId);
    if (receipt.parentSnapshotIds.length) {
      await host.recordRecoveredRemoteHeads(
        review.binding.cloudProjectId,
        receipt.parentSnapshotIds,
      );
    }
    await host.publish({
      localProjectId: String(review.projectId), localIncarnation: review.localIncarnation,
      bundle: snapshot, cloudProjectId: review.binding.cloudProjectId,
      parentSnapshotIds: receipt.parentSnapshotIds,
    });
  }), [host, readSnapshot, withReview]);

  const keepBoth = useCallback(() => withReview("keep-both", async (review, head, receipt) => {
    if (!host || !api.importCloudProject) throw new Error("Cloud project import is unavailable.");
    const envelope = await host.readSnapshot(review.binding.cloudProjectId, head.snapshotId);
    const restored = await api.importCloudProject({
      restore_id: receipt.actionId,
      snapshot: envelope.bundle as CloudProjectSnapshotDTO,
      mode: "fork",
    });
    await host.saveActionReceipt({ ...receipt, phase: "local-forked",
      restoredLocalProjectId: String(restored.project_id), restoredLocalIncarnation: restored.project_identity });
    const superseded = receipt.parentSnapshotIds.filter((snapshotId) => snapshotId !== head.snapshotId);
    if (superseded.length) {
      await host.recordRecoveredRemoteHeads(review.binding.cloudProjectId, superseded);
    }
    const local = await readSnapshot(review.projectId);
    await host.publish({
      localProjectId: String(review.projectId), localIncarnation: review.localIncarnation,
      bundle: local, cloudProjectId: review.binding.cloudProjectId,
      parentSnapshotIds: receipt.parentSnapshotIds,
    });
    refreshProjects?.();
  }), [api, host, readSnapshot, refreshProjects, withReview]);

  const importRemote = useCallback(async (cloudProjectId: string) => {
    const importCloudProject = api.importCloudProject;
    if (!host || !importCloudProject) return;
    await runSerialized(async () => {
      commit({ busy: true, status: "syncing", detail: "Importing a complete cloud project…" });
      try {
        const native = await host.getState();
        const inventory = native.projects.find((project) => project.cloudProjectId === cloudProjectId);
        const head = inventory ? newestCloudHead(inventory.snapshots.filter((item) => inventory.headSnapshotIds.includes(item.snapshotId))) : null;
        if (!head) throw new Error("The selected cloud project has no recoverable snapshot.");
        const pending = native.actionReceipts.find((receipt) => (
          receipt.kind === "discover"
          && receipt.originalCloudProjectId === cloudProjectId
          && receipt.snapshotId === head.snapshotId
          && receipt.snapshotDigest === head.digest
        ));
        const id = pending?.actionId ?? actionId();
        const envelope = await host.readSnapshot(cloudProjectId, head.snapshotId);
        const receiptBase = pending ?? {
          actionId: id, kind: "discover" as const, phase: "prepared" as const,
          sourceLocalProjectId: "cloud", sourceLocalIncarnation: cloudProjectId,
          originalCloudProjectId: cloudProjectId, intendedCloudProjectId: null,
          snapshotId: head.snapshotId, snapshotDigest: head.digest,
          parentSnapshotIds: head.parentSnapshotIds, expectedSourceDigest: head.digest,
          restoredLocalProjectId: null, restoredLocalIncarnation: null,
          createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(),
        };
        if (!pending) await host.saveActionReceipt(receiptBase);
        const restored = await importCloudProject({
          restore_id: id, snapshot: envelope.bundle as CloudProjectSnapshotDTO, mode: "import",
        });
        if (ACTION_PHASE_ORDER[receiptBase.phase] < ACTION_PHASE_ORDER.restored) {
          await host.saveActionReceipt({ ...receiptBase, phase: "restored",
            restoredLocalProjectId: String(restored.project_id), restoredLocalIncarnation: restored.project_identity });
        }
        await installBinding(host, restored.project_id, restored.project_identity, cloudProjectId, head);
        if (ACTION_PHASE_ORDER[receiptBase.phase] < ACTION_PHASE_ORDER["binding-installed"]) {
          await host.saveActionReceipt({ ...receiptBase, phase: "binding-installed",
            restoredLocalProjectId: String(restored.project_id), restoredLocalIncarnation: restored.project_identity });
        }
        await host.completeActionReceipt(id);
        refreshProjects?.();
        await selectProject?.(restored.project_id);
        commit({ native: await host.getState(), busy: false, status: "up-to-date",
          detail: "Cloud project imported and linked on this device." });
      } catch (error) { commit({ busy: false, status: "error", detail: errorMessage(error) }); }
    });
  }, [api, commit, host, installBinding, refreshProjects, runSerialized, selectProject]);

  const recoverRemoteHead = useCallback(async (cloudProjectId: string, snapshotId: string) => {
    const importCloudProject = api.importCloudProject;
    if (!host || !importCloudProject) return;
    await runSerialized(async () => {
      commit({ busy: true, status: "syncing", detail: "Recovering a preserved provider branch…" });
      try {
        const native = await host.getState();
        const inventory = native.projects.find((project) => project.cloudProjectId === cloudProjectId);
        const snapshot = inventory?.snapshots.find((item) => item.snapshotId === snapshotId);
        if (!snapshot) throw new Error("The preserved cloud snapshot is no longer available.");
        const pending = native.actionReceipts.find((receipt) => (
          receipt.kind === "remote-recovery"
          && receipt.originalCloudProjectId === cloudProjectId
          && receipt.snapshotId === snapshotId
          && receipt.snapshotDigest === snapshot.digest
        ));
        const id = pending?.actionId ?? actionId();
        const envelope = await host.readSnapshot(cloudProjectId, snapshotId);
        const receiptBase = pending ?? {
          actionId: id, kind: "remote-recovery" as const, phase: "prepared" as const,
          sourceLocalProjectId: "cloud-recovery", sourceLocalIncarnation: cloudProjectId,
          originalCloudProjectId: cloudProjectId, intendedCloudProjectId: null,
          snapshotId, snapshotDigest: snapshot.digest,
          parentSnapshotIds: snapshot.parentSnapshotIds, expectedSourceDigest: snapshot.digest,
          restoredLocalProjectId: null, restoredLocalIncarnation: null,
          createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(),
        };
        if (!pending) await host.saveActionReceipt(receiptBase);
        const restored = await importCloudProject({
          restore_id: id,
          snapshot: envelope.bundle as CloudProjectSnapshotDTO,
          mode: "fork",
        });
        if (ACTION_PHASE_ORDER[receiptBase.phase] < ACTION_PHASE_ORDER.restored) {
          await host.saveActionReceipt({ ...receiptBase, phase: "restored",
            restoredLocalProjectId: String(restored.project_id), restoredLocalIncarnation: restored.project_identity });
        }
        await host.removeRecoveredRemoteHead(cloudProjectId, snapshotId);
        await host.completeActionReceipt(id);
        refreshProjects?.();
        await selectProject?.(restored.project_id);
        commit({ native: await host.getState(), busy: false, status: "up-to-date",
          detail: "Preserved provider branch recovered as a separate local project." });
      } catch (error) { commit({ busy: false, status: "error", detail: errorMessage(error) }); }
    });
  }, [api, commit, host, installBinding, refreshProjects, runSerialized, selectProject]);

  const ignoreRemote = useCallback(async (cloudProjectId: string) => {
    if (!host) return;
    await runSerialized(async () => {
      commit({ native: await host.setRemoteIgnored(cloudProjectId, true) });
    });
  }, [commit, host, runSerialized]);

  const forgetActiveBinding = useCallback(async () => {
    if (!host || projectId == null) return;
    await runSerialized(async () => {
      const native = viewRef.current.native;
      const binding = native?.bindings.find((item) => item.localProjectId === String(projectId));
      if (!binding) return;
      commit({ native: await host.forgetBinding(binding.localProjectId, binding.localIncarnation, false),
        review: null, status: "attention", detail: "This local project is no longer linked; cloud history was preserved." });
    });
  }, [commit, host, projectId, runSerialized]);

  const actions = useMemo<ProCloudSyncActions>(() => ({
    chooseFolder, disable, setAutomatic,
    syncNow: () => synchronize(true), retryOutbox,
    useCloudCopy, replaceCloudCopy, keepBoth,
    importRemote, recoverRemoteHead, ignoreRemote, forgetActiveBinding,
  }), [chooseFolder, disable, forgetActiveBinding, ignoreRemote, importRemote, keepBoth,
    recoverRemoteHead, replaceCloudCopy, retryOutbox, setAutomatic, synchronize, useCloudCopy]);

  useEffect(() => { publishExternal(view, actions); }, [actions, view]);
  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; publishExternal(UNAVAILABLE, externalActions); };
  }, []);

  useEffect(() => {
    if (!host) { commit(UNAVAILABLE); return undefined; }
    let cancelled = false;
    const refresh = async () => {
      try {
        const native = await host.getState();
        if (cancelled) return;
        commit({ native, status: native.enabled ? "checking" : "disabled", busy: false,
          detail: native.enabled ? "Checking local and cloud snapshots…" : "Choose a provider-managed folder to begin." });
        if (native.enabled && projectId != null) await synchronize(native.automatic);
      } catch (error) {
        if (!cancelled) commit({ status: "error", busy: false, detail: errorMessage(error) });
      }
    };
    void refresh();
    const unsubscribe = host.onChanged(() => { void synchronize(false); });
    return () => { cancelled = true; unsubscribe(); };
  }, [commit, host, projectId, synchronize]);

  useEffect(() => {
    if (!host || !view.native?.enabled || !view.native.automatic || projectId == null) return undefined;
    const timer = window.setInterval(() => { void synchronize(true); }, AUTO_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [host, projectId, synchronize, view.native?.automatic, view.native?.enabled]);

  return null;
}

