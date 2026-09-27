import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { PlatformAdapter } from "../adapters/platform";
import {
  markProjectSavePending,
  registerProjectFlusher,
  trackProjectWrite,
} from "../adapters/projectSaveCoordinator";
import {
  reconcileWorkspaceLayout,
  resetWorkspaceLayout,
  restoreWorkspaceLayout,
  serializeWorkspaceLayout,
  type WorkspaceLayout,
} from "./layoutModel";

export interface UseWorkspaceLayoutOptions {
  projectId?: number;
  platform: PlatformAdapter;
  allowedPanelIds: readonly string[];
  debounceMs?: number;
}

export interface WorkspaceLayoutState {
  layout: WorkspaceLayout;
  hydrated: boolean;
  loading: boolean;
  saving: boolean;
  error: Error | null;
  updateLayout: (update: WorkspaceLayout | ((current: WorkspaceLayout) => WorkspaceLayout)) => void;
  resetLayout: () => void;
  flushLayout: () => Promise<boolean>;
  retryLayoutPersistence: () => Promise<boolean>;
}

interface OwnedWorkspaceLayout {
  projectId: number | undefined;
  layout: WorkspaceLayout;
}

function asError(error: unknown): Error {
  return error instanceof Error ? error : new Error(String(error));
}

function sameLayout(a: WorkspaceLayout, b: WorkspaceLayout): boolean {
  return a === b || serializeWorkspaceLayout(a) === serializeWorkspaceLayout(b);
}

function canonicalPanelIds(panelIds: readonly string[]): string[] {
  return [...new Set(panelIds)].sort((left, right) => left.localeCompare(right));
}

/**
 * Load and persist a versioned layout without ever writing the first-run value
 * over a still-loading project. Its registered flusher joins the same global
 * barrier used by editor fields, project handoffs, and the Electron close flow.
 */
export function useWorkspaceLayout({
  projectId,
  platform,
  allowedPanelIds,
  debounceMs = 300,
}: UseWorkspaceLayoutOptions): WorkspaceLayoutState {
  // Panel availability is set-like configuration. Canonicalizing it prevents a
  // freshly allocated but equivalent registry array from restarting hydration.
  const nextAllowedPanelIds = canonicalPanelIds(allowedPanelIds);
  const allowedPanelFingerprint = JSON.stringify(nextAllowedPanelIds);
  const stableAllowedPanelIds = useMemo(
    () => nextAllowedPanelIds,
    [allowedPanelFingerprint],
  );
  const safeFallback = useMemo(
    () => resetWorkspaceLayout(stableAllowedPanelIds),
    [stableAllowedPanelIds],
  );

  const initialRef = useRef<WorkspaceLayout>();
  if (!initialRef.current) initialRef.current = safeFallback;

  const [ownedLayout, setOwnedLayout] = useState<OwnedWorkspaceLayout>({
    projectId,
    layout: initialRef.current,
  });
  const [hydrated, setHydrated] = useState(projectId === undefined);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);

  const mountedRef = useRef(true);
  const layoutRef = useRef(initialRef.current);
  const projectRef = useRef(projectId);
  const renderedProjectRef = useRef(projectId);
  const loadLayoutCapability = platform.loadLayout;
  const loadLayoutBackupCapability = platform.loadLayoutBackup;
  const renderedLoadLayoutRef = useRef(loadLayoutCapability);
  const renderedLoadLayoutBackupRef = useRef(loadLayoutBackupCapability);
  const renderedReloadNonceRef = useRef(reloadNonce);
  const hydratedProjectRef = useRef<number | undefined>(undefined);
  const platformRef = useRef(platform);
  const allowedRef = useRef<readonly string[]>(stableAllowedPanelIds);
  const allowedFingerprintRef = useRef(allowedPanelFingerprint);
  const debounceMsRef = useRef(debounceMs);
  const hydratedRef = useRef(hydrated);
  const dirtyRef = useRef(false);
  const dirtyRevisionRef = useRef(0);
  const preserveBackupRef = useRef(false);
  const loadGenerationRef = useRef(0);
  const errorOwnerRef = useRef<{
    projectId: number | undefined;
    generation: number;
  } | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const flushPromiseRef = useRef<Promise<boolean> | null>(null);

  const renderedConfigurationMatches = renderedProjectRef.current === projectId
    && renderedLoadLayoutRef.current === loadLayoutCapability
    && renderedLoadLayoutBackupRef.current === loadLayoutBackupCapability
    && renderedReloadNonceRef.current === reloadNonce;

  // Commit ownership before paint/event delivery. Mutating these refs during
  // render would let an abandoned concurrent render invalidate the still-live
  // project's load, saves, and event handlers.
  useLayoutEffect(() => {
    const configurationChanged = renderedProjectRef.current !== projectId
      || renderedLoadLayoutRef.current !== loadLayoutCapability
      || renderedLoadLayoutBackupRef.current !== loadLayoutBackupCapability
      || renderedReloadNonceRef.current !== reloadNonce;
    projectRef.current = projectId;
    platformRef.current = platform;
    allowedRef.current = stableAllowedPanelIds;
    debounceMsRef.current = debounceMs;
    if (!configurationChanged) return;
    renderedProjectRef.current = projectId;
    renderedLoadLayoutRef.current = loadLayoutCapability;
    renderedLoadLayoutBackupRef.current = loadLayoutBackupCapability;
    renderedReloadNonceRef.current = reloadNonce;
    loadGenerationRef.current += 1;
    hydratedProjectRef.current = undefined;
    hydratedRef.current = projectId === undefined;
  }, [debounceMs, loadLayoutBackupCapability, loadLayoutCapability, platform, projectId, reloadNonce, stableAllowedPanelIds]);

  const projectIsHydrated = projectId === undefined
    || (renderedConfigurationMatches
      && hydrated
      && hydratedProjectRef.current === projectId
      && hydratedRef.current);

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const drainLayout = useCallback(async (): Promise<boolean> => {
    while (dirtyRef.current) {
      const targetProjectId = projectRef.current;
      if (targetProjectId === undefined) return true;
      if (!hydratedRef.current || hydratedProjectRef.current !== targetProjectId) return false;

      const targetGeneration = loadGenerationRef.current;
      const targetRevision = dirtyRevisionRef.current;
      const preserveBackup = preserveBackupRef.current;
      const targetPlatform = platformRef.current;
      const saveLayout = targetPlatform.saveLayout;
      const ownerIsCurrent = () => (
        projectRef.current === targetProjectId
        && loadGenerationRef.current === targetGeneration
        && hydratedProjectRef.current === targetProjectId
        && hydratedRef.current
      );

      if (!saveLayout) {
        if (mountedRef.current && ownerIsCurrent()) {
          setSaving(false);
          errorOwnerRef.current = {
            projectId: targetProjectId,
            generation: targetGeneration,
          };
          setError(new Error("This platform cannot persist Studio workspace layouts."));
        }
        return false;
      }

      let write: Promise<void>;
      try {
        const snapshot = reconcileWorkspaceLayout(layoutRef.current, allowedRef.current);
        // Canonicalize before crossing the host boundary. This validates the
        // payload and prevents later in-memory mutations from changing it.
        const payload = JSON.parse(serializeWorkspaceLayout(snapshot)) as WorkspaceLayout;
        if (mountedRef.current && ownerIsCurrent()) setSaving(true);
        write = Promise.resolve().then(() => saveLayout.call(
          targetPlatform,
          targetProjectId,
          payload,
          { preserveBackup },
        ));
        await trackProjectWrite(write);
      } catch (saveError) {
        // A completion belonging to an old project/reload may neither publish
        // an error nor clear the current owner's dirty state.
        if (!ownerIsCurrent()) continue;
        if (mountedRef.current) {
          setSaving(false);
          errorOwnerRef.current = {
            projectId: targetProjectId,
            generation: targetGeneration,
          };
          setError(asError(saveError));
        }
        // Keep dirty=true so an explicit retry, later edit, handoff, or close
        // barrier retries instead of silently accepting data loss.
        return false;
      }

      if (!ownerIsCurrent()) continue;
      if (preserveBackup) preserveBackupRef.current = false;
      if (dirtyRevisionRef.current === targetRevision) dirtyRef.current = false;
      if (!dirtyRef.current && mountedRef.current) {
        setSaving(false);
        errorOwnerRef.current = null;
        setError(null);
      }
      // If an edit landed during the write, the same drain owns the next pass.
    }
    return true;
  }, []);

  const flushLayout = useCallback((): Promise<boolean> => {
    clearTimer();
    const current = flushPromiseRef.current;
    if (current) return current;

    const running = drainLayout();
    flushPromiseRef.current = running;
    const release = () => {
      if (flushPromiseRef.current === running) flushPromiseRef.current = null;
    };
    // Do not use an ignored finally() chain here: it would create a second
    // rejected promise if an unexpected drain error escaped.
    void running.then(release, release);
    return running;
  }, [clearTimer, drainLayout]);

  const scheduleSave = useCallback(() => {
    clearTimer();
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      void flushLayout();
    }, Math.max(0, debounceMsRef.current));
  }, [clearTimer, flushLayout]);

  const updateLayout = useCallback((
    update: WorkspaceLayout | ((current: WorkspaceLayout) => WorkspaceLayout),
  ) => {
    const currentProjectId = projectRef.current;
    // A concrete project must remain immutable until its own saved layout (or
    // an explicit no-storage fallback) has hydrated.
    if (currentProjectId !== undefined
      && (!hydratedRef.current || hydratedProjectRef.current !== currentProjectId)) return;

    const current = layoutRef.current;
    const candidate = typeof update === "function" ? update(current) : update;
    const next = reconcileWorkspaceLayout(candidate, allowedRef.current);
    if (sameLayout(current, next)) return;
    layoutRef.current = next;
    setOwnedLayout({ projectId: currentProjectId, layout: next });
    if (currentProjectId !== undefined) {
      dirtyRef.current = true;
      dirtyRevisionRef.current += 1;
      markProjectSavePending();
      scheduleSave();
    }
  }, [scheduleSave]);

  const resetLayout = useCallback(() => {
    updateLayout(resetWorkspaceLayout(allowedRef.current));
  }, [updateLayout]);

  const retryLayoutPersistence = useCallback(async (): Promise<boolean> => {
    if (dirtyRef.current) return flushLayout();
    setReloadNonce((value) => value + 1);
    return true;
  }, [flushLayout]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      clearTimer();
    };
  }, [clearTimer]);

  useEffect(() => registerProjectFlusher(flushLayout), [flushLayout]);

  // Reconcile genuine panel-catalog changes in place. Equivalent array
  // instances do not reload the project or discard a pending write.
  useEffect(() => {
    if (allowedFingerprintRef.current === allowedPanelFingerprint) return;
    allowedFingerprintRef.current = allowedPanelFingerprint;
    const currentProjectId = projectRef.current;
    if (currentProjectId !== undefined
      && (!hydratedRef.current || hydratedProjectRef.current !== currentProjectId)) return;

    const current = layoutRef.current;
    const next = reconcileWorkspaceLayout(current, stableAllowedPanelIds);
    if (sameLayout(current, next)) return;
    layoutRef.current = next;
    setOwnedLayout({ projectId: currentProjectId, layout: next });
    if (currentProjectId !== undefined) {
      dirtyRef.current = true;
      dirtyRevisionRef.current += 1;
      markProjectSavePending();
      scheduleSave();
    }
  }, [allowedPanelFingerprint, scheduleSave, stableAllowedPanelIds]);

  useEffect(() => {
    const generation = loadGenerationRef.current + 1;
    loadGenerationRef.current = generation;
    const targetProjectId = projectId;
    const targetPlatform = platformRef.current;
    const loadLayout = loadLayoutCapability;
    const loadLayoutBackup = loadLayoutBackupCapability;
    const ownerIsCurrent = () => (
      projectRef.current === targetProjectId
      && loadGenerationRef.current === generation
    );

    clearTimer();
    dirtyRef.current = false;
    preserveBackupRef.current = false;
    hydratedProjectRef.current = undefined;
    hydratedRef.current = targetProjectId === undefined;
    setHydrated(targetProjectId === undefined);
    setSaving(false);
    errorOwnerRef.current = null;
    setError(null);

    const fallback = resetWorkspaceLayout(allowedRef.current);
    layoutRef.current = fallback;
    setOwnedLayout({ projectId: targetProjectId, layout: fallback });
    if (targetProjectId === undefined) return;

    if (!loadLayout) {
      if (!ownerIsCurrent()) return;
      hydratedProjectRef.current = targetProjectId;
      hydratedRef.current = true;
      setHydrated(true);
      errorOwnerRef.current = { projectId: targetProjectId, generation };
      setError(new Error("This platform cannot restore Studio workspace layouts."));
      return;
    }

    let active = true;
    void Promise.resolve()
      .then(() => loadLayout.call(targetPlatform, targetProjectId))
      .then(async (saved) => {
        if (!active || !ownerIsCurrent()) return;
        let restored = restoreWorkspaceLayout(saved, allowedRef.current);
        let recoveredFromBackup = false;
        if (restored.source === "default"
          && restored.fallbackReason !== "future"
          && loadLayoutBackup) {
          const backup = await loadLayoutBackup.call(targetPlatform, targetProjectId);
          if (!active || !ownerIsCurrent()) return;
          const restoredBackup = restoreWorkspaceLayout(backup, allowedRef.current);
          if (restoredBackup.source !== "default") {
            restored = restoredBackup;
            recoveredFromBackup = true;
          } else if (restored.fallbackReason === "absent"
            && restoredBackup.fallbackReason !== "absent") {
            // A missing primary with an invalid/future backup is not a clean
            // first run; retain its diagnostics for the recovery banner.
            restored = restoredBackup;
          }
        }
        layoutRef.current = restored.layout;
        setOwnedLayout({ projectId: targetProjectId, layout: restored.layout });
        hydratedProjectRef.current = targetProjectId;
        hydratedRef.current = true;
        setHydrated(true);

        // Validated backup recovery and known schema/catalog transformations
        // can repair storage. Unsupported future/invalid values remain intact.
        if (recoveredFromBackup
          || (saved !== null && saved !== undefined
            && (restored.source === "migrated"
              || (restored.source === "current" && restored.diagnostics.length > 0)))) {
          preserveBackupRef.current = recoveredFromBackup;
          dirtyRef.current = true;
          dirtyRevisionRef.current += 1;
          markProjectSavePending();
          scheduleSave();
        } else if (restored.source === "default" && restored.fallbackReason !== "absent") {
          // If the writer deliberately resets after an invalid primary, do not
          // rotate that invalid generation over any still-useful backup.
          preserveBackupRef.current = restored.fallbackReason === "invalid";
          errorOwnerRef.current = { projectId: targetProjectId, generation };
          setError(new Error(
            restored.fallbackReason === "future"
              ? "This workspace layout was created by a newer LogosForge version and was not overwritten."
              : `The saved workspace layout is invalid and defaults are being used. ${restored.diagnostics.join("; ")}`,
          ));
        }
      })
      .catch((loadError) => {
        if (!active || !ownerIsCurrent()) return;
        // Keep the safe in-memory default but do not overwrite a layout that
        // may only be temporarily unreadable.
        hydratedProjectRef.current = undefined;
        hydratedRef.current = false;
        setHydrated(false);
        errorOwnerRef.current = { projectId: targetProjectId, generation };
        setError(asError(loadError));
      });

    return () => {
      active = false;
    };
  }, [clearTimer, loadLayoutBackupCapability, loadLayoutCapability, projectId, reloadNonce, scheduleSave]);

  const visibleLayout = ownedLayout.projectId === projectId
    && (projectId === undefined || projectIsHydrated)
    ? ownedLayout.layout
    : safeFallback;
  const errorOwner = errorOwnerRef.current;
  const visibleError = errorOwner !== null
    && renderedConfigurationMatches
    && errorOwner.projectId === projectId
    && errorOwner.generation === loadGenerationRef.current
    ? error
    : null;

  return {
    layout: visibleLayout,
    hydrated: projectIsHydrated,
    loading: projectId !== undefined && !projectIsHydrated,
    saving: saving && projectIsHydrated,
    error: visibleError,
    updateLayout,
    resetLayout,
    flushLayout,
    retryLayoutPersistence,
  };
}
