import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type CSSProperties,
} from "react";
import { WRITING_MODES, type ProjectDTO, type WritingMode } from "@logosforge/ui-contracts";
import {
  AssistantDock,
  DockWorkspace,
  PanelErrorBoundary,
  StudioOmnibox,
  STUDIO_AI_COMPANIONS_PANEL_ID,
  STUDIO_PANELS,
  STUDIO_WORKSPACE_PANEL_IDS,
  StudioProvider,
  WorkspaceNavigator,
  WorkspaceShell,
  activateDockPanel,
  bringFloatingPanelToFront,
  closePanel,
  createCommandRegistry,
  deriveWorkspaceStatus,
  findStudioPanel,
  flushPendingProjectSaves,
  focusPanel,
  getPanelPlacement,
  getProjectSaveStatusSnapshot,
  moveFloatingPanel,
  movePanel,
  openPanel,
  placePanel,
  prepareProjectHandoff,
  parseRecentProjectIds,
  rememberRecentProject,
  resetProjectSaveStatus,
  resetWorkspaceLayout,
  resizeDock,
  resizeFloatingPanel,
  resizeNavigator,
  setFloatingPanelMinimized,
  setNavigatorCollapsed,
  setWorkspacePreset,
  studioPanelGroupsForMode,
  subscribeProjectSaveStatus,
  toggleDockCollapsed,
  toggleWorkspacePreset,
  useStudio,
  useWorkspaceLayout,
  type WorkspaceLayout,
  type WorkspacePanelDefinition,
  type StudioNavigationOptions,
  type KnowledgeGraphNavigationTarget,
  type ContinuityRepairTarget,
} from "../src";
import {
  createPreviewLayoutPlatform,
  drainPreviewIdentityOperations,
  previewProjectNeedsReconciliation,
  previewUnloadNeedsConfirmation,
  selectPreviewBootstrapProject,
} from "./integratedWorkspaceRuntime";

const OMNIBOX_RECENT_PROJECTS_STORAGE_PREFIX = "logosforge.preview.omnibox.recent-projects.v1";

function loadRecentProjectIds(storageKey: string): readonly number[] {
  if (typeof window === "undefined") return [];
  try {
    return parseRecentProjectIds(window.localStorage.getItem(storageKey));
  } catch {
    // Locked-down/private browser contexts may reject storage reads. The
    // omnibox remains fully usable; it simply starts without recent projects.
    return [];
  }
}

function persistRecentProjectIds(storageKey: string, projectIds: readonly number[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(storageKey, JSON.stringify(projectIds));
  } catch {
    // Recent-project ranking is an optional client convenience, never a reason
    // to interrupt a successfully opened project.
  }
}

const railButton = (active: boolean): CSSProperties => ({
  width: "100%",
  border: "none",
  borderLeft: active ? "2px solid var(--accent)" : "2px solid transparent",
  background: active ? "var(--tint2)" : "transparent",
  color: active ? "var(--strong)" : "var(--txt2)",
  padding: "6px 10px",
  textAlign: "left",
  font: "inherit",
  fontSize: 10,
  cursor: "pointer",
});

function projectWritingMode(project: ProjectDTO | undefined): WritingMode {
  const candidate = project?.narrative_engine || project?.format_mode || "novel";
  return (WRITING_MODES as readonly string[]).includes(candidate)
    ? candidate as WritingMode
    : "novel";
}

/**
 * A browser-hosted version of the actual Pro workspace composition. Unlike the
 * design fixture, every visible panel is the shared API-backed implementation.
 */
export function IntegratedWorkspaceHarness({
  source,
  externalTransitioning,
  registerIdentityGuard,
}: {
  source: "mock" | "live";
  externalTransitioning: boolean;
  registerIdentityGuard: (guard: (() => Promise<void>) | null) => void;
}) {
  const upstream = useStudio();
  const api = upstream.api;
  const platform = useMemo(
    () => createPreviewLayoutPlatform(upstream.platform, source),
    [source, upstream.platform],
  );
  const [projects, setProjects] = useState<ProjectDTO[]>([]);
  // Do not mount project-scoped panels against the outer preview's placeholder
  // id. Bootstrap from the authoritative list/open response first.
  const [projectId, setProjectId] = useState<number | undefined>(undefined);
  const [projectReady, setProjectReady] = useState(false);
  const [projectLoading, setProjectLoading] = useState(true);
  const [projectSwitching, setProjectSwitching] = useState(false);
  const [coreState, setCoreState] = useState<"connecting" | "connected" | "error">("connecting");
  const [coreDetail, setCoreDetail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [theme, setTheme] = useState<"dark" | "light" | "warm">("dark");
  const [omniboxOpen, setOmniboxOpen] = useState(false);
  const omniboxRecentProjectsStorageKey = `${OMNIBOX_RECENT_PROJECTS_STORAGE_PREFIX}.${source}`;
  const [recentProjectIds, setRecentProjectIds] = useState<readonly number[]>(
    () => loadRecentProjectIds(omniboxRecentProjectsStorageKey),
  );
  const [pendingScene, setPendingScene] = useState<number | null>(null);
  const [pendingPsykeEntry, setPendingPsykeEntry] = useState<number | null>(null);
  const [pendingNote, setPendingNote] = useState<number | null>(null);
  const [pendingComment, setPendingComment] = useState<number | null>(null);
  const [pendingKnowledgeGraph, setPendingKnowledgeGraph] = useState<KnowledgeGraphNavigationTarget | null>(null);
  const [pendingContinuityIssue, setPendingContinuityIssue] = useState<string | null>(null);
  const [pendingContinuityRepair, setPendingContinuityRepair] = useState<ContinuityRepairTarget | null>(null);
  const projectIdRef = useRef(projectId);
  const projectSwitchingRef = useRef(false);
  const bootstrappedRef = useRef(false);
  const selectProjectRef = useRef<(targetId: number) => Promise<boolean>>(async () => false);
  const operationQueue = useRef<Promise<void>>(Promise.resolve());
  const refreshOperations = useRef<Set<Promise<ProjectDTO[]>>>(new Set());
  const loadSequence = useRef(0);

  const mode = projectWritingMode(projects.find((project) => project.id === projectId));
  const visibleGroups = useMemo(() => studioPanelGroupsForMode(mode), [mode]);
  const visiblePanelIds = useMemo(
    () => new Set(visibleGroups.flatMap((group) => group.panels.map((panel) => panel.id))),
    [visibleGroups],
  );

  const {
    layout,
    hydrated,
    saving: layoutSaving,
    error: layoutError,
    updateLayout,
    retryLayoutPersistence,
  } = useWorkspaceLayout({
    projectId,
    platform,
    allowedPanelIds: STUDIO_WORKSPACE_PANEL_IDS,
    // A preview can be switched away from instantly; persist its layout without
    // leaving a debounce window behind on unmount.
    debounceMs: 0,
  });
  const layoutRef = useRef(layout);
  const hydratedProjectRef = useRef<number | undefined>(undefined);
  useLayoutEffect(() => {
    projectIdRef.current = projectId;
    layoutRef.current = layout;
    hydratedProjectRef.current = hydrated ? projectId : undefined;
  }, [hydrated, layout, projectId]);

  const projectSave = useSyncExternalStore(
    subscribeProjectSaveStatus,
    getProjectSaveStatusSnapshot,
    getProjectSaveStatusSnapshot,
  );
  const runtimeStatus = useMemo(() => deriveWorkspaceStatus({
    coreState,
    coreDetail,
    projectSave,
    workspaceLayoutSaving: layoutSaving,
    workspaceLayoutError: layoutError,
    handoffPhase: projectSwitching ? "switching" : "idle",
    storage: "local",
  }), [coreDetail, coreState, layoutError, layoutSaving, projectSave, projectSwitching]);
  const omniboxAvailable = projectReady && hydrated && !projectSwitching && !externalTransitioning;
  const requestOpenOmnibox = useCallback(() => {
    if (omniboxAvailable) setOmniboxOpen(true);
  }, [omniboxAvailable]);

  const loadProjects = useCallback(async (): Promise<ProjectDTO[]> => {
    const sequence = ++loadSequence.current;
    setProjectLoading(true);
    setCoreState("connecting");
    try {
      await api.health();
      let next = await api.listProjects();
      if (sequence !== loadSequence.current) return next;
      if (!bootstrappedRef.current) {
        const selected = selectPreviewBootstrapProject(next, upstream.projectId);
        if (selected !== undefined) {
          const opened = await api.openProject(selected);
          if (sequence !== loadSequence.current) return next;
          next = next.some((project) => project.id === opened.id)
            ? next.map((project) => project.id === opened.id ? opened : project)
            : [...next, opened];
        }
        // This is the only direct identity assignment: no project-scoped panel
        // has mounted yet, so there is no old editor/layout state to hand off.
        bootstrappedRef.current = true;
        projectIdRef.current = selected;
        setProjectId(selected);
        setProjectReady(true);
      }
      setProjects(next);

      const current = projectIdRef.current;
      let reconciled = true;
      if (bootstrappedRef.current
        && previewProjectNeedsReconciliation(next, current)
        && !projectSwitchingRef.current) {
        // A later refresh may discover an externally/deleted active project.
        // Reconcile through the same queued save/open/reset path as a user pick.
        reconciled = await selectProjectRef.current(next[0]?.id ?? 0);
        if (sequence !== loadSequence.current) return next;
      }
      setCoreState("connected");
      setCoreDetail("");
      if (reconciled) setError(null);
      return next;
    } catch (loadError) {
      if (sequence === loadSequence.current) {
        const message = loadError instanceof Error ? loadError.message : String(loadError);
        setCoreState("error");
        setCoreDetail(message);
        setError(`Could not load the integrated workspace. ${message}`);
      }
      return [];
    } finally {
      if (sequence === loadSequence.current) setProjectLoading(false);
    }
  }, [api, upstream.projectId]);

  const refreshProjects = useCallback((): Promise<ProjectDTO[]> => {
    const running = loadProjects();
    refreshOperations.current.add(running);
    const release = () => { refreshOperations.current.delete(running); };
    void running.then(release, release);
    return running;
  }, [loadProjects]);

  useEffect(() => {
    void refreshProjects();
    return () => { loadSequence.current += 1; };
  }, [refreshProjects]);

  useEffect(() => {
    setRecentProjectIds(loadRecentProjectIds(omniboxRecentProjectsStorageKey));
  }, [omniboxRecentProjectsStorageKey]);

  // `projectId` is published only after the initial open or a queued project
  // handoff succeeds. Tracking that authoritative active identity keeps failed
  // selections out of the browser-only MRU list.
  useEffect(() => {
    if (!projectReady || projectId === undefined) return;
    setRecentProjectIds((current) => {
      const next = rememberRecentProject(current, projectId);
      persistRecentProjectIds(omniboxRecentProjectsStorageKey, next);
      return next;
    });
  }, [omniboxRecentProjectsStorageKey, projectId, projectReady]);

  useEffect(() => {
    const openOmnibox = (event: KeyboardEvent) => {
      if (!omniboxAvailable
        || event.repeat
        || event.altKey
        || event.shiftKey
        || (!event.metaKey && !event.ctrlKey)
        || event.key.toLowerCase() !== "k") return;
      event.preventDefault();
      setOmniboxOpen(true);
    };
    window.addEventListener("keydown", openOmnibox);
    return () => window.removeEventListener("keydown", openOmnibox);
  }, [omniboxAvailable]);

  useEffect(() => {
    if (!omniboxAvailable) setOmniboxOpen(false);
  }, [omniboxAvailable]);

  const applyLayout = useCallback((mutate: (current: WorkspaceLayout) => WorkspaceLayout): boolean => {
    const owner = projectIdRef.current;
    if (owner !== undefined && hydratedProjectRef.current !== owner) return false;
    const next = mutate(layoutRef.current);
    layoutRef.current = next;
    updateLayout(next);
    return true;
  }, [updateLayout]);

  const runWorkspaceMutation = useCallback((
    mutate: (current: WorkspaceLayout) => WorkspaceLayout,
    failurePrefix: string,
  ): Promise<boolean> => {
    if (externalTransitioning) return Promise.resolve(false);
    const owner = projectIdRef.current;
    const task = operationQueue.current.then(async () => {
      try {
        await flushPendingProjectSaves({ commitActiveField: true });
        if (projectIdRef.current !== owner) return false;
        if (owner !== undefined && hydratedProjectRef.current !== owner) {
          setError("Workspace action paused while this project's layout is loading.");
          return false;
        }
        if (!applyLayout(mutate)) return false;
        setError(null);
        return true;
      } catch (mutationError) {
        setError(`${failurePrefix} ${mutationError instanceof Error ? mutationError.message : String(mutationError)}`);
        return false;
      }
    });
    operationQueue.current = task.then(() => undefined, () => undefined);
    return task;
  }, [applyLayout, externalTransitioning]);

  const selectPanel = useCallback((
    value: string,
    options?: StudioNavigationOptions,
  ): Promise<boolean> => {
    const panel = findStudioPanel(value);
    const panelId = value === STUDIO_AI_COMPANIONS_PANEL_ID
      ? STUDIO_AI_COMPANIONS_PANEL_ID
      : panel?.id;
    if (!panelId) return Promise.resolve(false);
    const preferredRegion = panelId === STUDIO_AI_COMPANIONS_PANEL_ID
      ? "right"
      : panel?.preferredRegion ?? "center";
    const selected = runWorkspaceMutation((current) => {
      let next = openPanel(current, panelId, preferredRegion);
      if (next.preset === "focus" && panelId !== "manuscript") {
        next = setWorkspacePreset(next, "cockpit");
      }
      return next;
    }, "Panel navigation stopped; the current workspace remains open.");
    return selected.then((didSelect) => {
      if (!didSelect) return false;
      setPendingScene(panelId === "manuscript" ? options?.sceneId ?? null : null);
      setPendingPsykeEntry(panelId === "psyke" ? options?.psykeEntryId ?? null : null);
      setPendingNote(panelId === "notes" ? options?.noteId ?? null : null);
      setPendingComment(panelId === "comments" ? options?.commentId ?? null : null);
      setPendingKnowledgeGraph(panelId === "graph" && options?.graphFocusKey ? {
        focusKey: options.graphFocusKey,
        viewMode: options.graphViewMode ?? "project_map",
        includeInferred: options.graphIncludeInferred ?? true,
        depth: options.graphDepth ?? 1,
      } : null);
      setPendingContinuityIssue(panelId === "continuity" ? options?.continuityIssueKey ?? null : null);
      setPendingContinuityRepair(panelId === STUDIO_AI_COMPANIONS_PANEL_ID ? options?.continuityRepair ?? null : null);
      return true;
    });
  }, [runWorkspaceMutation]);

  const selectProject = useCallback((targetId: number): Promise<boolean> => {
    const target = targetId || undefined;
    if (externalTransitioning || projectSwitchingRef.current) return Promise.resolve(false);
    if (projectIdRef.current === target) return Promise.resolve(true);
    projectSwitchingRef.current = true;
    setProjectSwitching(true);
    const task = operationQueue.current.then(async () => {
      try {
        const opened = target === undefined
          ? (await flushPendingProjectSaves({ commitActiveField: true }), null)
          : await prepareProjectHandoff(() => api.openProject(target));
        if (opened) {
          setProjects((current) => {
            const next = current.some((project) => project.id === opened.id)
              ? current.map((project) => project.id === opened.id ? opened : project)
              : [...current, opened];
            return next;
          });
        }
        hydratedProjectRef.current = undefined;
        resetProjectSaveStatus();
        projectIdRef.current = target;
        setProjectId(target);
        setProjectReady(true);
        setPendingScene(null);
        setPendingPsykeEntry(null);
        setPendingNote(null);
        setPendingComment(null);
        setPendingKnowledgeGraph(null);
        setPendingContinuityIssue(null);
        setPendingContinuityRepair(null);
        setError(null);
        return true;
      } catch (switchError) {
        setError(`Project switch stopped; the current project remains open. ${switchError instanceof Error ? switchError.message : String(switchError)}`);
        return false;
      } finally {
        projectSwitchingRef.current = false;
        setProjectSwitching(false);
      }
    });
    operationQueue.current = task.then(() => undefined, () => undefined);
    return task;
  }, [api, externalTransitioning]);

  useLayoutEffect(() => {
    selectProjectRef.current = selectProject;
  }, [selectProject]);

  const omniboxPanels = useMemo(() => [
    ...visibleGroups.flatMap((group) => group.panels.map((panel) => ({
      id: panel.id,
      label: panel.label,
      keywords: group.group ? [group.group] : [],
    }))),
    {
      id: STUDIO_AI_COMPANIONS_PANEL_ID,
      label: "AI Companions",
      keywords: ["Billy", "assistant", "Logos", "Counterpart"],
    },
  ], [visibleGroups]);

  const omniboxRegistry = useMemo(() => createCommandRegistry([
    {
      id: "workspace:toggle-focus",
      label: layout.preset === "focus" ? "Exit Focus Mode" : "Enter Focus Mode",
      category: "Workspace",
      aliases: ["toggle-focus", "focus-mode"],
      keywords: ["workspace", "distraction free", "cockpit"],
      enabled: projectReady && hydrated && !projectSwitching && !externalTransitioning,
      run: () => runWorkspaceMutation(
        toggleWorkspacePreset,
        "Focus-mode change stopped; the current workspace remains visible.",
      ),
    },
    {
      id: "workspace:reset-layout",
      label: "Reset Workspace Layout",
      category: "Workspace",
      aliases: ["reset-layout", "restore-layout"],
      keywords: ["workspace", "panels", "docks", "default"],
      enabled: projectReady && hydrated && !projectSwitching && !externalTransitioning,
      run: () => runWorkspaceMutation(
        () => resetWorkspaceLayout(STUDIO_WORKSPACE_PANEL_IDS),
        "Workspace reset stopped; the previous layout is unchanged.",
      ),
    },
    {
      id: "appearance:dark",
      label: "Use Dark Appearance",
      category: "Appearance",
      aliases: ["theme-dark", "dark-theme"],
      keywords: ["theme", "appearance", "dark"],
      enabled: !externalTransitioning,
      run: () => { setTheme("dark"); return true; },
    },
    {
      id: "appearance:light",
      label: "Use Light Appearance",
      category: "Appearance",
      aliases: ["theme-light", "light-theme"],
      keywords: ["theme", "appearance", "light"],
      enabled: !externalTransitioning,
      run: () => { setTheme("light"); return true; },
    },
    {
      id: "appearance:warm",
      label: "Use Warm Appearance",
      category: "Appearance",
      aliases: ["theme-warm", "warm-theme"],
      keywords: ["theme", "appearance", "warm"],
      enabled: !externalTransitioning,
      run: () => { setTheme("warm"); return true; },
    },
  ]), [
    externalTransitioning,
    hydrated,
    layout.preset,
    projectReady,
    projectSwitching,
    runWorkspaceMutation,
  ]);

  const reportOmniboxError = useCallback((omniboxError: unknown, label: string) => {
    setError(`Omnibox action "${label}" failed. ${omniboxError instanceof Error ? omniboxError.message : String(omniboxError)}`);
  }, []);

  const drainIdentityOperations = useCallback(async () => {
    await drainPreviewIdentityOperations(
      refreshOperations.current,
      operationQueue,
      () => flushPendingProjectSaves({ commitActiveField: true }),
    );
  }, []);
  useEffect(() => {
    registerIdentityGuard(drainIdentityOperations);
    return () => registerIdentityGuard(null);
  }, [drainIdentityOperations, registerIdentityGuard]);

  const browserUnloadUnsafe = previewUnloadNeedsConfirmation({
    projectDirty: projectSave.dirty,
    projectWritesInFlight: projectSave.inFlightCount,
    projectFlushInProgress: projectSave.flushing,
    layoutSaving,
    layoutError,
    identityTransitioning: projectSwitching || externalTransitioning,
  });
  useEffect(() => {
    if (!browserUnloadUnsafe) return;
    const confirmPendingSaves = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      // Chromium and Firefox require returnValue for the native confirmation.
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", confirmPendingSaves);
    return () => window.removeEventListener("beforeunload", confirmPendingSaves);
  }, [browserUnloadUnsafe]);

  // Mode-ineligible panels cannot leak in from a saved layout. The preview also
  // mirrors the desktop host's permanent AI-companion home in the right dock.
  useEffect(() => {
    if (!hydrated) return;
    const unavailable = STUDIO_PANELS
      .filter((panel) => !visiblePanelIds.has(panel.id))
      .map((panel) => panel.id);
    const invalidPanelOpen = unavailable.some((panelId) => getPanelPlacement(layout, panelId) !== null);
    const aiPlacement = getPanelPlacement(layout, STUDIO_AI_COMPANIONS_PANEL_ID);
    const aiNeedsHome = aiPlacement?.kind !== "dock" || aiPlacement.region !== "right";
    if (!invalidPanelOpen && !aiNeedsHome) return;
    void runWorkspaceMutation((current) => {
      let next = current;
      unavailable.forEach((panelId) => { next = closePanel(next, panelId); });
      const nextAiPlacement = getPanelPlacement(next, STUDIO_AI_COMPANIONS_PANEL_ID);
      if (nextAiPlacement?.kind !== "dock" || nextAiPlacement.region !== "right") {
        next = placePanel(next, STUDIO_AI_COMPANIONS_PANEL_ID, {
          kind: "dock",
          region: "right",
          index: next.docks.right.panelIds.length,
        });
      }
      return next.focused === null ? openPanel(next, "manuscript", "center") : next;
    }, "Workspace normalization stopped; the saved layout remains visible.");
  }, [hydrated, layout, runWorkspaceMutation, visiblePanelIds]);

  const openedPanels = useMemo<WorkspacePanelDefinition[]>(() => {
    const openedIds = [...new Set([
      ...layout.docks.left.panelIds,
      ...layout.docks.center.panelIds,
      ...layout.docks.right.panelIds,
      ...layout.docks.bottom.panelIds,
      ...layout.floatingPanels.map((panel) => panel.panelId),
    ])];
    return openedIds.flatMap<WorkspacePanelDefinition>((panelId) => {
      if (panelId === STUDIO_AI_COMPANIONS_PANEL_ID) {
        return [{
          id: panelId,
          label: "AI Companions",
          closable: false,
          movable: false,
          flush: true,
          node: (
            <PanelErrorBoundary name="Billy Assistant preview" resetKey={`${projectId ?? "none"}:billy`}>
              <AssistantDock />
            </PanelErrorBoundary>
          ),
        }];
      }
      const panel = findStudioPanel(panelId);
      if (!panel) return [];
      return [{
        id: panel.id,
        label: panel.label,
        closable: panel.id !== "manuscript",
        movable: panel.id !== "manuscript",
        node: (
          <PanelErrorBoundary name={`${panel.label} preview panel`} resetKey={`${projectId ?? "none"}:${panel.id}`}>
            {panel.node}
          </PanelErrorBoundary>
        ),
      }];
    });
  }, [layout, projectId]);

  const focusedPanelId = layout.preset === "focus"
    ? "manuscript"
    : layout.focused?.panelId ?? layout.docks.center.activePanelId ?? "manuscript";
  const focusedLabel = focusedPanelId === STUDIO_AI_COMPANIONS_PANEL_ID
    ? "AI Companions"
    : findStudioPanel(focusedPanelId)?.label ?? "Workspace";
  const activeProject = projects.find((project) => project.id === projectId);

  const navigator = (
    <WorkspaceNavigator
      collapsed={layout.navigator.collapsed}
      widthPx={layout.navigator.widthPx}
      disabled={!projectReady || !hydrated || projectSwitching || externalTransitioning}
      onCollapsedChange={(collapsed) => collapsed
        ? runWorkspaceMutation(
          (current) => setNavigatorCollapsed(current, true),
          "Navigator collapse stopped; the workspace is unchanged.",
        )
        : Promise.resolve(applyLayout((current) => setNavigatorCollapsed(current, false)))}
      onWidthChange={(width) => applyLayout((current) => resizeNavigator(current, width))}
    >
      <aside aria-label="Integrated Studio navigator" style={{ width: "100%", minWidth: 0, overflowY: "auto", padding: "34px 10px 12px" }}>
        <div style={{ marginBottom: source === "mock" ? 5 : 12, color: "var(--accent)", fontSize: 9, letterSpacing: ".18em" }}>
          REAL PANELS · {source === "mock" ? "MOCK SAMPLE DATA" : "LIVE CORE"}
        </div>
        {source === "mock" && (
          <p style={{ margin: "0 0 12px", color: "var(--txt3)", fontSize: 9, lineHeight: 1.45 }}>
            UI fixture data may be shared between sample projects. Choose LIVE CORE for isolated project content.
          </p>
        )}
        <label style={{ display: "grid", gap: 4, marginBottom: 9, color: "var(--txt3)", fontSize: 9 }}>
          Project
          <select
            aria-label="Integrated workspace project"
            value={projectId ?? ""}
            disabled={!projectReady || projectLoading || projectSwitching || externalTransitioning}
            onChange={(event) => { void selectProject(Number(event.target.value)); }}
            style={{ width: "100%", background: "var(--panel)", color: "var(--txt)", border: "1px solid var(--line2)", padding: 5 }}
          >
            {projects.length === 0 && <option value="">No projects</option>}
            {projects.map((project) => <option key={project.id} value={project.id}>{project.title}</option>)}
          </select>
        </label>
        <label style={{ display: "grid", gap: 4, marginBottom: 12, color: "var(--txt3)", fontSize: 9 }}>
          Appearance
          <select
            aria-label="Integrated workspace appearance"
            value={theme}
            disabled={externalTransitioning}
            onChange={(event) => setTheme(event.target.value as typeof theme)}
            style={{ width: "100%", background: "var(--panel)", color: "var(--txt)", border: "1px solid var(--line2)", padding: 5 }}
          >
            <option value="dark">Dark</option>
            <option value="light">Light</option>
            <option value="warm">Warm</option>
          </select>
        </label>
        {visibleGroups.map((group, groupIndex) => (
          <div key={group.group || `primary-${groupIndex}`} style={{ marginBottom: 9 }}>
            {group.group && <div style={{ padding: "5px 10px", color: "var(--txt3)", fontSize: 8, letterSpacing: ".16em" }}>{group.group}</div>}
            {group.panels.map((panel) => (
              <button
                key={panel.id}
                type="button"
                aria-current={focusedPanelId === panel.id ? "page" : undefined}
                disabled={!projectReady || !hydrated || projectSwitching || externalTransitioning}
                onClick={() => { void selectPanel(panel.id); }}
                style={railButton(focusedPanelId === panel.id)}
              >
                {panel.label}
              </button>
            ))}
          </div>
        ))}
      </aside>
    </WorkspaceNavigator>
  );

  return (
    <div data-screen-label="Workspace Shell — Integrated" data-preview-source={source} style={{ position: "relative", width: "100%", height: "100%", minHeight: 0 }}>
      <StudioProvider
        key={`${source}:${projectId ?? "no-project"}`}
        services={{ api, platform }}
        writingMode={mode}
        projectId={projectId}
        nav={{
          navigate: selectPanel,
          manuscriptTargetSceneId: pendingScene,
          clearManuscriptTarget: (sceneId) => setPendingScene((current) => sceneId == null || current === sceneId ? null : current),
          psykeTargetEntryId: pendingPsykeEntry,
          clearPsykeTarget: (entryId) => setPendingPsykeEntry((current) => entryId == null || current === entryId ? null : current),
          noteTargetId: pendingNote,
          clearNoteTarget: (noteId) => setPendingNote((current) => noteId == null || current === noteId ? null : current),
          commentTargetId: pendingComment,
          clearCommentTarget: (commentId) => setPendingComment((current) => commentId == null || current === commentId ? null : current),
          knowledgeGraphTarget: pendingKnowledgeGraph,
          clearKnowledgeGraphTarget: (focusKey) => setPendingKnowledgeGraph((current) => focusKey == null || current?.focusKey === focusKey ? null : current),
          continuityTargetIssueKey: pendingContinuityIssue,
          clearContinuityTarget: (issueKey) => setPendingContinuityIssue((current) => issueKey == null || current === issueKey ? null : current),
          continuityRepairTarget: pendingContinuityRepair,
          clearContinuityRepairTarget: (handoffId) => setPendingContinuityRepair((current) => handoffId == null || current?.handoffId === handoffId ? null : current),
          selectProject,
          refreshProjects: () => { void refreshProjects(); },
        }}
      >
        <WorkspaceShell
          writingMode={mode}
          layout={layout.preset}
          theme={theme}
          showConsole
          runtimeStatus={runtimeStatus}
          coreState={coreState}
          statusCenter={`${focusedLabel.toUpperCase()} · ${activeProject?.title ?? "No project"}`}
          navSlot={navigator}
          rightSlot={<></>}
          bottomSlot={<></>}
          centerSlot={projectReady && hydrated ? (
            <DockWorkspace
              layout={layout}
              panels={openedPanels}
              disabled={projectSwitching || externalTransitioning}
              onActivate={(panelId, region) => runWorkspaceMutation(
                (current) => activateDockPanel(current, region, panelId),
                "Panel activation stopped; the current tab remains open.",
              )}
              onMove={(panelId, region, index) => runWorkspaceMutation(
                (current) => movePanel(current, panelId, { kind: "dock", region, index }),
                "Panel move stopped; the previous layout is unchanged.",
              )}
              onFloat={(panelId, bounds) => runWorkspaceMutation(
                (current) => movePanel(current, panelId, { kind: "floating", bounds }),
                "Panel tear-off stopped; the previous layout is unchanged.",
              )}
              onClose={(panelId) => panelId === "manuscript"
                ? Promise.resolve(false)
                : runWorkspaceMutation(
                  (current) => closePanel(current, panelId),
                  "Panel close stopped; the panel remains open.",
                )}
              onToggleDock={(region) => runWorkspaceMutation(
                (current) => toggleDockCollapsed(current, region),
                "Dock visibility change stopped; the workspace is unchanged.",
              )}
              onResizeDock={(region, size) => applyLayout((current) => resizeDock(current, region, size))}
              onMoveFloating={(panelId, x, y) => applyLayout((current) => moveFloatingPanel(current, panelId, x, y))}
              onResizeFloating={(panelId, width, height) => applyLayout((current) => resizeFloatingPanel(current, panelId, width, height))}
              onMinimizeFloating={(panelId, minimized) => runWorkspaceMutation(
                (current) => minimized
                  ? setFloatingPanelMinimized(current, panelId, true)
                  : focusPanel(setFloatingPanelMinimized(current, panelId, false), panelId),
                "Panel minimize change stopped; the workspace is unchanged.",
              )}
              onFocusFloating={(panelId) => applyLayout((current) => bringFloatingPanelToFront(current, panelId))}
              onReset={() => runWorkspaceMutation(
                () => resetWorkspaceLayout(STUDIO_WORKSPACE_PANEL_IDS),
                "Workspace reset stopped; the previous layout is unchanged.",
              )}
            />
          ) : (
            <div role="status" aria-live="polite" style={{ display: "grid", placeItems: "center", height: "100%", color: "var(--txt2)" }}>
              {projectReady ? "Loading this project's browser workspace…" : "Opening the browser workspace…"}
            </div>
          )}
          onToggleFocus={() => { void runWorkspaceMutation(
            toggleWorkspacePreset,
            "Focus-mode change stopped; the current workspace remains visible.",
          ); }}
          onCommandPalette={omniboxAvailable ? requestOpenOmnibox : undefined}
        />
        <StudioOmnibox
          open={omniboxOpen}
          onClose={() => setOmniboxOpen(false)}
          registry={omniboxRegistry}
          panels={omniboxPanels}
          projects={projects}
          recentProjectIds={recentProjectIds}
          onNavigate={selectPanel}
          onSelectProject={selectProject}
          onError={reportOmniboxError}
        />
      </StudioProvider>
      {(error || layoutError) && (
        <button
          type="button"
          role="alert"
          onClick={() => {
            if (error && !projectReady) void refreshProjects();
            else if (error) setError(null);
            else void retryLayoutPersistence();
          }}
          title={error
            ? (projectReady ? "Dismiss" : "Retry opening the browser workspace")
            : "Retry browser workspace layout persistence"}
          style={{ position: "absolute", left: "50%", bottom: 34, zIndex: 1000, transform: "translateX(-50%)", maxWidth: 760, border: "1px solid var(--crimson)", background: "var(--raised)", color: "var(--strong)", padding: "8px 12px", font: "inherit", cursor: "pointer" }}
        >
          {error
            ? `${error}${projectReady ? "" : " Click to retry."}`
            : `Workspace layout could not be loaded or saved. ${layoutError?.message ?? ""} Click to retry.`}
        </button>
      )}
    </div>
  );
}
