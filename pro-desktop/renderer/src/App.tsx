import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactElement } from 'react';
import {
  StudioProvider,
  createHttpApiClient,
  type ApiClient,
  type PlatformAdapter,
  WorkspaceShell,
  DockWorkspace,
  WorkspaceNavigator,
  type WorkspaceDockRegion,
  type WorkspaceLayout,
  type WorkspacePanelDefinition,
  ManuscriptEditor,
  NotesPanel,
  CommentsPanel,
  StoryGrid,
  StructurePanel,
  OutlinePanel,
  FormatStructure,
  ActsView,
  BeatsView,
  ChaptersView,
  TagsView,
  PsykeBible,
  KnowledgeGraph,
  CanvasPlot,
  TimelinePanel,
  NarrativeDashboard,
  ContinuityPanel,
  DecisionRadar,
  ProjectsPanel,
  AdaptView,
  ReviewDashboard,
  PluginsPanel,
  SeriesNavigator,
  StoryHealthHud,
  PacingInsights,
  CharacterBalance,
  CoverageAnalysis,
  VoiceHud,
  ExportDialog,
  CrossCutting,
  CharacterLinks,
  ThemeScenes,
  AiSettingsPanel,
  ConnectorPanel,
  HelpPanel,
  flushPendingProjectSaves,
  prepareProjectHandoff,
  trackProjectWrite,
  PanelErrorBoundary,
  RuntimeFaultBanner,
  useRuntimeFaultReporter,
  createDeferredDisposer,
  closePanel as closeWorkspacePanel,
  bringFloatingPanelToFront,
  focusPanel as focusWorkspacePanel,
  getPanelPlacement,
  moveFloatingPanel,
  openPanel as openWorkspacePanel,
  placePanel,
  resetWorkspaceLayout,
  resizeDock,
  resizeFloatingPanel,
  resizeNavigator,
  setDockCollapsed,
  setFloatingPanelMinimized,
  setNavigatorCollapsed,
  setWorkspacePreset,
  toggleDockCollapsed,
  toggleWorkspacePreset,
  useWorkspaceLayout,
  focusAfterWorkspaceAction,
  workspacePanelDomToken,
  type FloatingPanelBounds,
} from '@logosforge/pro-shared-ui';
import { WRITING_MODES, type WritingMode, type ProjectDTO } from '@logosforge/ui-contracts';
import { desktop, platform, type CoreStatus } from './platform';
import { AiDock, AI_TOOL_KEYS } from './AiDock';
import { CommandPalette, type Command } from './CommandPalette';

interface Panel {
  id: string;
  label: string;
  node: ReactElement;
  preferredRegion?: WorkspaceDockRegion;
  /** If set, the panel only appears in these writing modes (mirrors the Python
   *  core's per-mode nav gating: Pages=GN-only, Series Navigator=series-only). */
  modes?: WritingMode[];
}

interface PanelGroup {
  group: string;
  panels: Panel[];
}

// Nav mirrors the Logosforge Python app's sidebar (main_window._SIDEBAR_LAYOUT):
// ungrouped top items + the Plan / Structure / Analytics groups, then PSYKE +
// Graph, the AI tools, and Export/Settings. Uses the panels that exist in React.
const PANEL_GROUPS: PanelGroup[] = [
  {
    group: '',
    panels: [
      { id: 'projects', label: 'Projects', node: <ProjectsPanel /> },
      { id: 'dashboard', label: 'Dashboard', node: <NarrativeDashboard /> },
      { id: 'manuscript', label: 'Manuscript', node: <ManuscriptEditor /> },
      { id: 'notes', label: 'Notes', node: <NotesPanel /> },
      { id: 'comments', label: 'Comments', node: <CommentsPanel /> },
      { id: 'dexters-room', label: "Dexter's Room", node: <VoiceHud /> },
    ],
  },
  {
    group: 'PLAN',
    // "Chapters" is no longer a permanent PLAN entry (it made no sense in
    // screenplay mode). It moved to STRUCTURE, gated to novel mode — mirroring
    // how the Python core gates mode-specific nav members by writing mode.
    panels: [
      { id: 'outline', label: 'Outline', node: <OutlinePanel />, preferredRegion: 'bottom' },
      { id: 'story-grid', label: 'Story Grid', node: <StoryGrid /> },
      { id: 'timeline', label: 'Timeline', node: <TimelinePanel /> },
      { id: 'canvas-plot', label: 'Canvas Plot', node: <CanvasPlot /> },
      // Series is meaningful only in series mode (the core gates it the same way);
      // outside series mode the seasons/episodes tables are always empty.
      { id: 'series', label: 'Series', node: <SeriesNavigator />, modes: ['series'] },
    ],
  },
  {
    group: 'STRUCTURE',
    panels: [
      { id: 'structure', label: 'Structure', node: <StructurePanel /> },
      { id: 'acts', label: 'Acts', node: <ActsView /> },
      { id: 'beats', label: 'Beats', node: <BeatsView /> },
      // Chapters are a prose-novel structure — shown only in novel mode (they made
      // no sense as a permanent entry in screenplay/GN/stage/series).
      { id: 'chapters', label: 'Chapters', node: <ChaptersView />, modes: ['novel'] },
      { id: 'structure-analysis', label: 'Structure Analysis', node: <CoverageAnalysis /> },
      { id: 'format-studio', label: 'Format Studio', node: <FormatStructure /> },
    ],
  },
  {
    group: 'ANALYTICS',
    panels: [
      { id: 'health', label: 'Health', node: <StoryHealthHud />, preferredRegion: 'bottom' },
      { id: 'pacing', label: 'Pacing', node: <PacingInsights /> },
      { id: 'balance', label: 'Balance', node: <CharacterBalance /> },
      { id: 'tags', label: 'Tags', node: <TagsView /> },
      { id: 'continuity', label: 'Continuity', node: <ContinuityPanel /> },
      { id: 'decision-radar', label: 'Decision Radar', node: <DecisionRadar />, preferredRegion: 'right' },
      { id: 'adapt', label: 'Adapt', node: <AdaptView /> },
      { id: 'review', label: 'Review', node: <ReviewDashboard /> },
    ],
  },
  {
    group: 'BIBLE',
    panels: [
      { id: 'psyke', label: 'PSYKE', node: <PsykeBible /> },
      { id: 'characters', label: 'Characters', node: <CharacterLinks /> },
      { id: 'theme-scenes', label: 'Theme Scenes', node: <ThemeScenes /> },
      { id: 'graph', label: 'Graph', node: <KnowledgeGraph /> },
    ],
  },
  {
    group: '',
    panels: [
      { id: 'plugins', label: 'Plugins', node: <PluginsPanel /> },
      { id: 'connector', label: 'Connector', node: <ConnectorPanel /> },
      { id: 'export', label: 'Export', node: <ExportDialog /> },
      { id: 'ai-settings', label: 'AI Settings', node: <AiSettingsPanel /> },
      { id: 'settings', label: 'Settings', node: <CrossCutting /> },
      { id: 'help', label: 'Help', node: <HelpPanel /> },
    ],
  },
];

const PANELS: Panel[] = PANEL_GROUPS.flatMap((g) => g.panels);
const AI_PANEL_ID = 'ai-companions';
const ALL_PANEL_IDS = [...PANELS.map((panel) => panel.id), AI_PANEL_ID] as const;
const MANUSCRIPT_TAB_SELECTOR = `#lf-tab-${workspacePanelDomToken('manuscript')}`;
const ACTIVE_RIGHT_TAB_SELECTOR = '[data-dock-drop-region="right"] [role="tab"][aria-selected="true"]';
const EXPAND_RIGHT_DOCK_SELECTOR = '[aria-label="Expand right dock"]';

function resolvePanel(value: string): Panel | undefined {
  return PANELS.find((panel) => panel.id === value || panel.label === value);
}

const DOT: Record<CoreStatus['state'], string> = {
  connecting: '#f5b133',
  connected: '#62d99a',
  error: '#e8443a',
};

function projectWritingMode(project: ProjectDTO): WritingMode {
  const candidate = project.narrative_engine || project.format_mode || 'novel';
  return (WRITING_MODES as readonly string[]).includes(candidate)
    ? candidate as WritingMode
    : 'novel';
}

function CoreBadge({ status }: { status: CoreStatus }) {
  return (
    <div className="badge">
      <span className="dot" style={{ background: DOT[status.state] }} />
      CORE · {status.state.toUpperCase()}
      {status.managed ? ' · MANAGED' : ''}
    </div>
  );
}

export function App() {
  const [status, setStatus] = useState<CoreStatus>({ state: 'connecting', baseUrl: '', managed: false });
  const [projectId, setProjectId] = useState<number | undefined>(undefined);
  const [mode, setMode] = useState<WritingMode>('novel');
  const [modeBusy, setModeBusy] = useState(false);
  const [projectSwitching, setProjectSwitching] = useState(false);
  const [closePending, setClosePending] = useState(false);
  const [bootstrapAttempt, setBootstrapAttempt] = useState(0);
  const [pendingScene, setPendingScene] = useState<number | null>(null);
  const [handoffError, setHandoffError] = useState<string | null>(null);
  const { fault: runtimeFault, dismiss: dismissRuntimeFault } = useRuntimeFaultReporter();
  // Project handoffs, mode changes, and workspace mutations share one queue.
  // Separate queues let a delayed dock action run after a project switch and
  // accidentally mutate the newly opened project's layout.
  const operationQueue = useRef<Promise<void>>(Promise.resolve());
  const closingRef = useRef(false);
  const projectSwitchingRef = useRef(false);
  const projectSwitchSequenceRef = useRef(0);
  const projectIdRef = useRef(projectId);
  const bootstrapRunRef = useRef<{ api: ApiClient; attempt: number } | null>(null);
  const bootstrapRetryTimerRef = useRef<number | null>(null);
  const appMountedRef = useRef(true);

  const {
    layout: workspaceLayout,
    hydrated: workspaceHydrated,
    saving: workspaceSaving,
    error: workspaceError,
    updateLayout,
    retryLayoutPersistence,
  } = useWorkspaceLayout({
    projectId,
    platform: platform as PlatformAdapter,
    allowedPanelIds: ALL_PANEL_IDS,
  });
  const workspaceHydratedProjectRef = useRef<number | undefined>(undefined);
  const workspaceLayoutRef = useRef(workspaceLayout);
  useLayoutEffect(() => {
    projectIdRef.current = projectId;
    workspaceHydratedProjectRef.current = workspaceHydrated ? projectId : undefined;
    workspaceLayoutRef.current = workspaceLayout;
  }, [projectId, workspaceHydrated, workspaceLayout]);

  // Companion choice and visual theme remain app preferences. Dock placement,
  // visibility, dimensions, and Focus/Cockpit are versioned per project above.
  const [aiTab, setAiTab] = useState<string>(() => localStorage.getItem('lf.aiTab') || AI_TOOL_KEYS[0] || 'Billy');
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [ambiance, setAmbiance] = useState<'dark' | 'light' | 'warm'>(() => {
    const v = localStorage.getItem('lf.theme');
    return v === 'dark' || v === 'light' || v === 'warm' ? v : 'dark';
  });
  useEffect(() => { localStorage.setItem('lf.aiTab', aiTab); }, [aiTab]);
  useEffect(() => { localStorage.setItem('lf.theme', ambiance); }, [ambiance]);
  // Drive the global CSS palette (body + command palette live outside the shell).
  useEffect(() => { document.documentElement.dataset.theme = ambiance; }, [ambiance]);
  useEffect(() => {
    appMountedRef.current = true;
    return () => {
      appMountedRef.current = false;
      if (bootstrapRetryTimerRef.current !== null) {
        window.clearTimeout(bootstrapRetryTimerRef.current);
        bootstrapRetryTimerRef.current = null;
      }
    };
  }, []);

  const applyWorkspaceLayout = useCallback((mutate: (current: WorkspaceLayout) => WorkspaceLayout) => {
    if (closingRef.current) return false;
    const ownerProjectId = projectIdRef.current;
    if (ownerProjectId !== undefined
      && workspaceHydratedProjectRef.current !== ownerProjectId) return false;
    const next = mutate(workspaceLayoutRef.current);
    workspaceLayoutRef.current = next;
    updateLayout(next);
    return true;
  }, [updateLayout]);

  const runWorkspaceMutation = useCallback((
    mutate: (current: WorkspaceLayout) => WorkspaceLayout,
    failurePrefix: string,
  ): Promise<boolean> => {
    if (closingRef.current) return Promise.resolve(false);
    const targetProjectId = projectIdRef.current;
    const task = operationQueue.current.then(async () => {
      try {
        await flushPendingProjectSaves({ commitActiveField: true });
        // A project selection may have been queued before this interaction was
        // able to run. Never replay the old project's click against a different
        // (or still-hydrating) layout.
        if (projectIdRef.current !== targetProjectId) return false;
        if (targetProjectId !== undefined
          && workspaceHydratedProjectRef.current !== targetProjectId) {
          setHandoffError('Workspace action skipped while the project layout is still loading.');
          return false;
        }
        if (!applyWorkspaceLayout(mutate)) return false;
        setHandoffError(null);
        return true;
      } catch (error) {
        setHandoffError(`${failurePrefix} ${error instanceof Error ? error.message : String(error)}`);
        return false;
      }
    });
    operationQueue.current = task.then(() => undefined, () => undefined);
    return task;
  }, [applyWorkspaceLayout]);

  const selectPanel = useCallback((panelValue: string, opts?: { sceneId?: number }): Promise<boolean> => {
    const panel = resolvePanel(panelValue);
    const panelId = panelValue === AI_PANEL_ID ? AI_PANEL_ID : panel?.id;
    if (!panelId) return Promise.resolve(false);
    const preferredRegion = panelId === AI_PANEL_ID ? 'right' : panel?.preferredRegion ?? 'center';
    const task = runWorkspaceMutation((layout) => {
      let next = openWorkspacePanel(layout, panelId, preferredRegion);
      if (next.preset === 'focus' && panelId !== 'manuscript') {
        next = setWorkspacePreset(next, 'cockpit');
      }
      return next;
    }, 'Panel switch stopped; the current workspace remains open.');
    void task.then((selected) => {
      if (selected && opts?.sceneId != null) setPendingScene(opts.sceneId);
    });
    return task;
  }, [runWorkspaceMutation]);

  // Cross-panel navigation: any panel can switch panels / open a scene, but no
  // panel unmounts a dirty editor until its save barrier succeeds.
  const navigate = useCallback((panel: string, opts?: { sceneId?: number }) => {
    void selectPanel(panel, opts);
  }, [selectPanel]);

  // Open an AI companion (used by the dock and the palette). Bring the dock into
  // view — and drop out of focus mode so it's actually visible.
  const openAi = useCallback((key: string): Promise<boolean> => {
    const task = selectPanel(AI_PANEL_ID);
    void task.then((selected) => {
      if (selected) setAiTab(key);
    });
    focusAfterWorkspaceAction(
      task,
      () => document.querySelector<HTMLElement>(ACTIVE_RIGHT_TAB_SELECTOR),
    );
    return task;
  }, [selectPanel]);
  const toggleFocus = useCallback((): Promise<boolean> => {
    const enteringFocus = workspaceLayoutRef.current.preset !== 'focus';
    const task = runWorkspaceMutation(
      toggleWorkspacePreset,
      'Focus-mode change stopped; the current workspace remains visible.',
    );
    if (enteringFocus) {
      focusAfterWorkspaceAction(
        task,
        () => document.querySelector<HTMLElement>(MANUSCRIPT_TAB_SELECTOR),
      );
    }
    return task;
  }, [runWorkspaceMutation]);

  // Mode-aware nav: mode-specific panels (Chapters=novel, Series=series) appear
  // only in their writing mode — mirroring the Python core's per-mode gating.
  const visibleGroups = useMemo(
    () => PANEL_GROUPS
      .map((g) => ({ ...g, panels: g.panels.filter((p) => !p.modes || p.modes.includes(mode)) }))
      .filter((g) => g.panels.length > 0),
    [mode],
  );
  const visiblePanels = useMemo(() => visibleGroups.flatMap((g) => g.panels), [visibleGroups]);

  // Normalize mode-ineligible panels and keep the permanent AI surface in its
  // right-hand home. Left docks and floating windows are first-class rendered
  // placements and must survive hydration unchanged.
  useEffect(() => {
    if (!workspaceHydrated) return;
    const unavailable = new Set(PANELS
      .filter((panel) => panel.modes && !panel.modes.includes(mode))
      .map((panel) => panel.id));
    const unavailableIsOpen = [...unavailable]
      .some((panelId) => getPanelPlacement(workspaceLayout, panelId) !== null);
    const aiPlacement = getPanelPlacement(workspaceLayout, AI_PANEL_ID);
    const aiNeedsHome = aiPlacement?.kind !== 'dock' || aiPlacement.region !== 'right';
    if (!unavailableIsOpen && !aiNeedsHome) return;
    void runWorkspaceMutation((layout) => {
      let next = layout;
      unavailable.forEach((panelId) => {
        if (getPanelPlacement(next, panelId) !== null) next = closeWorkspacePanel(next, panelId);
      });
      const previouslyFocused = next.focused?.panelId;
      const nextAiPlacement = getPanelPlacement(next, AI_PANEL_ID);
      if (nextAiPlacement?.kind !== 'dock' || nextAiPlacement.region !== 'right') {
        next = placePanel(next, AI_PANEL_ID, {
          kind: 'dock',
          region: 'right',
          index: next.docks.right.panelIds.length,
        });
      }
      if (previouslyFocused) {
        const placement = getPanelPlacement(next, previouslyFocused);
        if (placement?.kind === 'dock') {
          next.docks[placement.region].activePanelId = previouslyFocused;
          next.focused = { zone: placement.region, panelId: previouslyFocused };
        } else if (placement?.kind === 'floating') {
          next = focusWorkspacePanel(next, previouslyFocused);
        }
      }
      return next.focused === null ? openWorkspacePanel(next, 'manuscript', 'center') : next;
    }, 'Workspace normalization stopped; the previous layout remains open.');
  }, [mode, runWorkspaceMutation, workspaceHydrated, workspaceLayout]);

  // ⌘K / Ctrl+K toggles the command palette anywhere; Escape leaves focus mode
  // (when the palette isn't the one consuming the keystroke).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === 'c') {
        e.preventDefault();
        void selectPanel('Comments');
      } else if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      } else if (e.key === 'Escape' && workspaceLayoutRef.current.preset === 'focus' && !paletteOpen) {
        void toggleFocus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [paletteOpen, selectPanel, toggleFocus]);

  // Everything the palette can do: jump to any section, open any AI companion,
  // toggle focus mode.
  const commands = useMemo<Command[]>(() => [
    ...visiblePanels.map((p) => ({ id: `go-${p.label}`, kind: 'Go', label: p.label, run: () => { void selectPanel(p.label); } })),
    ...AI_TOOL_KEYS.map((k) => ({ id: `ai-${k}`, kind: 'AI', label: k, run: () => openAi(k) })),
    { id: 'focus', kind: 'View', label: workspaceLayout.preset === 'focus' ? 'Exit focus mode' : 'Enter focus mode', run: toggleFocus },
  ], [openAi, toggleFocus, visiblePanels, selectPanel, workspaceLayout.preset]);

  useEffect(() => {
    if (!desktop) return;
    let active = true;
    let liveEventSeen = false;
    const unsubscribe = desktop.onCoreStatus((next) => {
      if (!active) return;
      liveEventSeen = true;
      setStatus(next);
    });
    void desktop.getCoreStatus().then((next) => {
      if (active && !liveEventSeen) setStatus(next);
    }).catch((error) => {
      if (active && !liveEventSeen) setStatus({
        state: 'error', baseUrl: '', managed: false,
        detail: `Could not read core status. ${error instanceof Error ? error.message : String(error)}`,
      });
    });
    return () => { active = false; unsubscribe(); };
  }, []);

  // Electron close/quit handshake: never let the process disappear inside the
  // scene debounce window. Main waits for this result before closing.
  useEffect(() => {
    const bridge = desktop;
    if (!bridge?.onSaveBeforeClose) return;
    const unsubscribeSave = bridge.onSaveBeforeClose((attemptId) => {
      closingRef.current = true;
      setClosePending(true);
      const queuedOperations = operationQueue.current;
      void queuedOperations.then(() => flushPendingProjectSaves({ commitActiveField: true })).then(
        () => bridge.sendCloseResult(attemptId, true),
        (error) => {
          setHandoffError(
            `Close stopped because pending changes could not be saved. ${
              error instanceof Error ? error.message : String(error)
            }`,
          );
          bridge.sendCloseResult(attemptId, false);
        },
      );
    });
    const unsubscribeCancel = bridge.onCloseCancelled(() => {
      closingRef.current = false;
      setClosePending(false);
    });
    return () => {
      unsubscribeSave();
      unsubscribeCancel();
    };
  }, []);

  // The manager may move away from the default port when an orphaned process
  // occupies it. Always derive the API endpoint from the latest status event;
  // a one-time coreBaseUrl() read would become stale during that fallback.
  const baseUrl = status.baseUrl || null;
  const api = useMemo<ApiClient | null>(
    () => (baseUrl != null ? createHttpApiClient(baseUrl, status.authToken ?? '') : null),
    [baseUrl, status.authToken],
  );
  const apiDisposer = useMemo(
    () => createDeferredDisposer<ApiClient>((client) => client.dispose?.()),
    [],
  );
  useEffect(() => (api ? apiDisposer.acquire(api) : undefined), [api, apiDisposer]);

  const selectProject = useCallback((id: number): Promise<boolean> => {
    if (closingRef.current) return Promise.resolve(false);
    const target = id || undefined;
    const requestSequence = projectSwitchSequenceRef.current + 1;
    projectSwitchSequenceRef.current = requestSequence;
    projectSwitchingRef.current = true;
    setProjectSwitching(true);
    const task = operationQueue.current.then(async () => {
      if (projectIdRef.current === target) return true;
      if (!api && target != null) return false;
      try {
        let opened: ProjectDTO | null = null;
        if (target == null) await flushPendingProjectSaves({ commitActiveField: true });
        else opened = await prepareProjectHandoff(() => api!.openProject(target));
        if (opened) {
          setProjects((current) => {
            const found = current.some((project) => project.id === opened.id);
            return found
              ? current.map((project) => project.id === opened.id ? opened : project)
              : [...current, opened];
          });
          setMode(projectWritingMode(opened));
        }
      } catch (error) {
        setHandoffError(
          `Project switch stopped; your current manuscript remains open. ${
            error instanceof Error ? error.message : String(error)
          }`,
        );
        return false;
      }
      workspaceHydratedProjectRef.current = undefined;
      setProjectId(target);
      projectIdRef.current = target;
      setPendingScene(null);
      setHandoffError(null);
      return true;
    });
    operationQueue.current = task.then(() => undefined, () => undefined);
    const finishSwitch = () => {
      if (projectSwitchSequenceRef.current === requestSequence) {
        projectSwitchingRef.current = false;
        setProjectSwitching(false);
      }
    };
    void task.then(finishSwitch, finishSwitch);
    return task;
  }, [api]);

  // Project list + selection. On connect, load the projects; if there are none,
  // create a starter one so a fresh install can write immediately (otherwise
  // every panel shows an empty "open a project" state with no way to make one).
  const [projects, setProjects] = useState<ProjectDTO[]>([]);
  const [busy, setBusy] = useState(false);

  const refreshProjects = useCallback(async (): Promise<ProjectDTO[]> => {
    if (!api) return [];
    const ps = await api.listProjects();
    setProjects(ps);
    const active = ps.find((project) => project.id === projectIdRef.current);
    if (active) setMode(projectWritingMode(active));
    return ps;
  }, [api]);

  const changeProjectMode = useCallback((nextMode: WritingMode): Promise<boolean> => {
    if (closingRef.current || projectSwitchingRef.current) return Promise.resolve(false);
    const targetProjectId = projectIdRef.current;
    const task = operationQueue.current.then(async () => {
      if (!api) return false;
      if (projectIdRef.current !== targetProjectId) return false;
      const activeId = targetProjectId;
      if (activeId == null) {
        setMode(nextMode);
        return true;
      }
      setModeBusy(true);
      let updated: ProjectDTO | null = null;
      try {
        await flushPendingProjectSaves({ commitActiveField: true });
        if (projectIdRef.current !== activeId) return false;
        const committed = await trackProjectWrite(
          api.updateProject(activeId, { narrative_engine: nextMode }),
        );
        updated = committed;
        setProjects((current) => current.map((project) =>
          project.id === committed.id ? committed : project,
        ));
        if (projectIdRef.current === activeId) setMode(projectWritingMode(committed));
        // Capture edits made while the mode request was in flight. The core
        // update is already committed at this point, so retain the returned
        // project locally even when this final drain needs user attention.
        await flushPendingProjectSaves({ commitActiveField: true });
        setHandoffError(null);
        return true;
      } catch (error) {
        if (updated) {
          setHandoffError(
            `Writing mode changed, but pending workspace changes still need to be saved. ${
              error instanceof Error ? error.message : String(error)
            }`,
          );
          return true;
        }
        setHandoffError(
          `Writing-mode change stopped. ${error instanceof Error ? error.message : String(error)}`,
        );
        return false;
      } finally {
        setModeBusy(false);
      }
    });
    operationQueue.current = task.then(() => undefined, () => undefined);
    return task;
  }, [api]);

  useEffect(() => {
    const clearRetry = () => {
      if (bootstrapRetryTimerRef.current !== null) {
        window.clearTimeout(bootstrapRetryTimerRef.current);
        bootstrapRetryTimerRef.current = null;
      }
    };
    if (!api || status.state !== 'connected') {
      bootstrapRunRef.current = null;
      clearRetry();
      return;
    }
    if (bootstrapRunRef.current?.api !== api) {
      bootstrapRunRef.current = null;
      clearRetry();
    }
    if (projects.length > 0 || projectId != null) {
      bootstrapRunRef.current = null;
      clearRetry();
      return;
    }
    if (busy) return;
    const previous = bootstrapRunRef.current;
    if (previous?.api === api && previous.attempt === bootstrapAttempt) return;
    const run = { api, attempt: bootstrapAttempt };
    bootstrapRunRef.current = run;
    const isCurrent = () => appMountedRef.current && bootstrapRunRef.current === run;
    setBusy(true);
    void (async () => {
      try {
        const ps = await api.listProjects();
        if (!isCurrent()) return;
        setProjects(ps);
        if (ps.length === 0) {
          const created = await api.createProject({ title: 'Untitled Project', narrative_engine: mode });
          if (!isCurrent()) return;
          setProjects([created]);
          workspaceHydratedProjectRef.current = undefined;
          setProjectId(created.id);
          projectIdRef.current = created.id;
          setMode(projectWritingMode(created));
        } else if (projectId == null) {
          workspaceHydratedProjectRef.current = undefined;
          setProjectId(ps[0]!.id);
          projectIdRef.current = ps[0]!.id;
          setMode(projectWritingMode(ps[0]!));
        }
        setHandoffError(null);
      } catch (error) {
        if (!isCurrent()) return;
        setHandoffError(
          `Could not load projects; retrying shortly. ${error instanceof Error ? error.message : String(error)}`,
        );
        clearRetry();
        const timer = window.setTimeout(() => {
          if (bootstrapRetryTimerRef.current === timer) bootstrapRetryTimerRef.current = null;
          if (!isCurrent()) return;
          bootstrapRunRef.current = null;
          setBootstrapAttempt((attempt) => attempt + 1);
        }, 3000);
        bootstrapRetryTimerRef.current = timer;
      } finally {
        if (appMountedRef.current) setBusy(false);
      }
    })();
  }, [api, status.state, busy, projects.length, projectId, mode, bootstrapAttempt]);

  const newProject = useCallback(async () => {
    if (!api || busy || projectSwitchingRef.current || closingRef.current) return;
    setBusy(true);
    try {
      const created = await prepareProjectHandoff(() =>
        api.createProject({ title: 'Untitled Project', narrative_engine: mode }),
      );
      await selectProject(created.id);
      await refreshProjects();
    } catch (error) {
      // Creation may have succeeded before the second safety drain failed.
      // Refresh so the recoverable blank project remains visible.
      await refreshProjects();
      setHandoffError(
        `New project stopped; your current manuscript remains open. ${
          error instanceof Error ? error.message : String(error)
        }`,
      );
    } finally {
      setBusy(false);
    }
  }, [api, busy, mode, refreshProjects, selectProject]);

  const activateDockPanel = useCallback((panelId: string) => {
    return selectPanel(panelId);
  }, [selectPanel]);

  const moveDockPanel = useCallback((panelId: string, region: WorkspaceDockRegion, index: number) => {
    if (panelId === 'manuscript' && region !== 'center') return Promise.resolve(false);
    if (panelId === AI_PANEL_ID && region !== 'right') return Promise.resolve(false);
    return runWorkspaceMutation(
      (layout) => placePanel(layout, panelId, { kind: 'dock', region, index }),
      'Panel move stopped; the previous dock layout is unchanged.',
    );
  }, [runWorkspaceMutation]);

  const floatWorkspacePanel = useCallback((panelId: string, bounds?: Partial<FloatingPanelBounds>) => {
    if (panelId === 'manuscript' || panelId === AI_PANEL_ID) return Promise.resolve(false);
    return runWorkspaceMutation(
      (layout) => placePanel(layout, panelId, { kind: 'floating', bounds }),
      'Panel tear-off stopped; the previous workspace layout is unchanged.',
    );
  }, [runWorkspaceMutation]);

  const moveWorkspaceFloatingPanel = useCallback((panelId: string, x: number, y: number) => {
    if (panelId === 'manuscript' || panelId === AI_PANEL_ID) return;
    applyWorkspaceLayout((layout) => moveFloatingPanel(layout, panelId, x, y));
  }, [applyWorkspaceLayout]);

  const resizeWorkspaceFloatingPanel = useCallback((panelId: string, width: number, height: number) => {
    if (panelId === 'manuscript' || panelId === AI_PANEL_ID) return;
    applyWorkspaceLayout((layout) => resizeFloatingPanel(layout, panelId, width, height));
  }, [applyWorkspaceLayout]);

  const focusWorkspaceFloatingPanel = useCallback((panelId: string) => {
    const current = workspaceLayoutRef.current;
    const floating = current.floatingPanels.find((entry) => entry.panelId === panelId);
    const alreadyFront = floating?.zIndex === current.floatingPanels.length - 1
      && current.focused?.zone === 'floating'
      && current.focused.panelId === panelId;
    if (!alreadyFront) applyWorkspaceLayout((layout) => bringFloatingPanelToFront(layout, panelId));
  }, [applyWorkspaceLayout]);

  const changeFloatingPanelMinimized = useCallback((panelId: string, minimized: boolean) => {
    if (panelId === 'manuscript' || panelId === AI_PANEL_ID) return Promise.resolve(false);
    return runWorkspaceMutation(
      (layout) => minimized
        ? setFloatingPanelMinimized(layout, panelId, true)
        : focusWorkspacePanel(setFloatingPanelMinimized(layout, panelId, false), panelId),
      minimized
        ? 'Panel minimize stopped; the floating panel remains open.'
        : 'Panel restore stopped; the panel remains minimized.',
    );
  }, [runWorkspaceMutation]);

  const closeDockPanel = useCallback((panelId: string) => {
    if (panelId === 'manuscript') return Promise.resolve(false);
    return runWorkspaceMutation(
      (layout) => closeWorkspacePanel(layout, panelId),
      'Panel close stopped; the panel remains open.',
    );
  }, [runWorkspaceMutation]);

  const changeDockCollapsed = useCallback((region: 'left' | 'right' | 'bottom') => {
    return runWorkspaceMutation(
      (layout) => toggleDockCollapsed(layout, region),
      'Dock visibility change stopped; the workspace is unchanged.',
    );
  }, [runWorkspaceMutation]);

  const collapseAiDock = useCallback((): Promise<boolean> => {
    const task = runWorkspaceMutation(
      (layout) => setDockCollapsed(layout, 'right', true),
      'AI dock collapse stopped; the workspace is unchanged.',
    );
    focusAfterWorkspaceAction(
      task,
      () => document.querySelector<HTMLElement>(EXPAND_RIGHT_DOCK_SELECTOR),
    );
    return task;
  }, [runWorkspaceMutation]);

  const changeNavigatorCollapsed = useCallback((collapsed: boolean) => {
    if (!collapsed) {
      return Promise.resolve(applyWorkspaceLayout((layout) => setNavigatorCollapsed(layout, false)));
    }
    return runWorkspaceMutation(
      (layout) => setNavigatorCollapsed(layout, true),
      'Navigator collapse stopped; the workspace is unchanged.',
    );
  }, [applyWorkspaceLayout, runWorkspaceMutation]);

  const restoreDefaultWorkspace = useCallback(() => {
    return runWorkspaceMutation(
      () => resetWorkspaceLayout(ALL_PANEL_IDS),
      'Workspace reset stopped; the previous layout is unchanged.',
    );
  }, [runWorkspaceMutation]);

  const toggleAiDock = useCallback((): Promise<boolean> => {
    const layout = workspaceLayoutRef.current;
    const placement = getPanelPlacement(layout, AI_PANEL_ID);
    if (placement?.kind === 'dock' && placement.region === 'right' && !layout.docks.right.collapsed) {
      return collapseAiDock();
    }
    return openAi(aiTab);
  }, [aiTab, collapseAiDock, openAi]);

  const openedPanels = useMemo<WorkspacePanelDefinition[]>(() => {
    const openedIds = [...new Set([
      ...workspaceLayout.docks.left.panelIds,
      ...workspaceLayout.docks.center.panelIds,
      ...workspaceLayout.docks.right.panelIds,
      ...workspaceLayout.docks.bottom.panelIds,
      ...workspaceLayout.floatingPanels.map((panel) => panel.panelId),
    ])];
    return openedIds.flatMap<WorkspacePanelDefinition>((panelId): WorkspacePanelDefinition[] => {
      if (panelId === AI_PANEL_ID) {
        return [{
          id: AI_PANEL_ID,
          label: 'AI Companions',
          closable: false,
          movable: false,
          flush: true,
          node: (
            <AiDock
              embedded
              open
              tab={aiTab}
              width={workspaceLayout.docks.right.sizePx}
              onOpenChange={(open) => { if (!open) void collapseAiDock(); }}
              onTabChange={setAiTab}
              onWidthChange={(width) => applyWorkspaceLayout((layout) => resizeDock(layout, 'right', width))}
            />
          ),
        }];
      }
      const panel = PANELS.find((candidate) => candidate.id === panelId);
      if (!panel) return [];
      return [{
        id: panel.id,
        label: panel.label,
        closable: panel.id !== 'manuscript',
        movable: panel.id !== 'manuscript',
        node: (
          <PanelErrorBoundary name={`${panel.label} panel`} resetKey={`${projectId ?? 'none'}:${panel.id}`}>
            {panel.node}
          </PanelErrorBoundary>
        ),
      }];
    });
  }, [aiTab, applyWorkspaceLayout, collapseAiDock, projectId, workspaceLayout]);

  // Native menu (electron/menu.ts) → the same handlers the sidebar / palette use.
  useEffect(() => {
    if (!desktop?.onMenuCommand) return;
    return desktop.onMenuCommand((cmd) => {
      if (cmd === 'new-project') void newProject();
      else if (cmd === 'palette') setPaletteOpen((o) => !o);
      else if (cmd === 'focus') toggleFocus();
      else if (cmd === 'ai-dock') toggleAiDock();
      else if (cmd === 'reset-workspace') restoreDefaultWorkspace();
      else if (cmd.startsWith('nav:')) void selectPanel(cmd.slice(4));
      else if (cmd.startsWith('ai:')) openAi(cmd.slice(3));
      else if (cmd.startsWith('theme:')) {
        const t = cmd.slice(6);
        if (t === 'dark' || t === 'light' || t === 'warm') setAmbiance(t);
      }
    });
  }, [newProject, toggleFocus, toggleAiDock, restoreDefaultWorkspace, openAi, selectPanel]);

  if (!desktop) {
    return (
      <div className="boot">
        This renderer runs inside the LogosForge Studio desktop app.
        <span className="detail">
          Launch it with <code>npm run dev</code> (Electron) — opening the Vite URL in a plain browser has no host bridge.
        </span>
      </div>
    );
  }
  if (!api) {
    return (
      <div className="boot">
        Connecting to the logosforge core…
        <span className="detail">{status.detail}</span>
      </div>
    );
  }
  if (busy && projects.length === 0 && projectId == null) {
    return (
      <div className="boot">
        Preparing your project…
        <span className="detail">Checking the local library and creating a blank project only when needed.</span>
      </div>
    );
  }

  const services = { api, platform: platform as PlatformAdapter };
  const focusedPanelId = workspaceLayout.preset === 'focus'
    ? 'manuscript'
    : workspaceLayout.focused?.panelId ?? workspaceLayout.docks.center.activePanelId ?? 'manuscript';
  const focusedLabel = focusedPanelId === AI_PANEL_ID
    ? 'AI Companions'
    : PANELS.find((panel) => panel.id === focusedPanelId)?.label ?? 'Workspace';

  // The sections rail — dropped into the cockpit shell's navSlot (the shell's
  // TopBar already carries the LOGOSFORGE brand, so no duplicate here).
  const railContent = (
    <aside className="rail">
      <CoreBadge status={status} />
      <label className="field">
        project mode
        <select value={mode} disabled={modeBusy || busy || projectSwitching || closePending || !workspaceHydrated} onChange={(e) => { void changeProjectMode(e.target.value as WritingMode); }}>
          {WRITING_MODES.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
      </label>
      <label className="field">
        project
        <select value={projectId ?? ''} disabled={busy || projectSwitching || closePending} onChange={(e) => { void selectProject(Number(e.target.value) || 0); }}>
          {projects.length === 0 && <option value="">—</option>}
          {projects.map((p) => (
            <option key={p.id} value={p.id}>{p.title || `Project ${p.id}`}</option>
          ))}
        </select>
      </label>
      <button type="button"
        onClick={newProject}
        disabled={busy || projectSwitching || closePending}
        style={{ width: '100%', marginTop: 2, padding: '7px 0', background: 'transparent', border: '1px solid #2b6f8f', color: '#9fd4ec', cursor: busy || projectSwitching || closePending ? 'default' : 'pointer', fontSize: 11, letterSpacing: '.12em', opacity: busy || projectSwitching || closePending ? 0.5 : 1 }}
      >
        ＋ NEW PROJECT
      </button>
      <label className="field">
        appearance
        <select value={ambiance} onChange={(e) => setAmbiance(e.target.value as typeof ambiance)}>
          <option value="dark">Dark</option>
          <option value="light">Light</option>
          <option value="warm">Warm</option>
        </select>
      </label>
      <nav>
        {visibleGroups.map((g, gi) => (
          <div key={g.group || `top-${gi}`} className="nav-group">
            {g.group && <div className="nav-group-label">{g.group}</div>}
            {g.panels.map((p) => (
              <button type="button" key={p.id} disabled={!workspaceHydrated || projectSwitching || closePending} className={focusedPanelId === p.id ? 'on' : ''} aria-current={focusedPanelId === p.id ? 'page' : undefined} onClick={() => { void selectPanel(p.id); }}>
                {p.label}
              </button>
            ))}
          </div>
        ))}
      </nav>
    </aside>
  );
  const rail = (
    <WorkspaceNavigator
      collapsed={workspaceLayout.navigator.collapsed}
      widthPx={workspaceLayout.navigator.widthPx}
      disabled={!workspaceHydrated || projectSwitching || closePending}
      onCollapsedChange={changeNavigatorCollapsed}
      onWidthChange={(width) => applyWorkspaceLayout((layout) => resizeNavigator(layout, width))}
    >
      {railContent}
    </WorkspaceNavigator>
  );

  return (
    <div className="cockpit-root">
      <PanelErrorBoundary name="Studio workspace" resetKey={`${projectId ?? 'none'}:${mode}`}>
      <StudioProvider
        key={projectId ?? 'no-project'}
        services={services}
        writingMode={mode}
        projectId={projectId}
        nav={{
          navigate,
          manuscriptTargetSceneId: pendingScene,
          clearManuscriptTarget: () => setPendingScene(null),
          selectProject,
          refreshProjects: () => {
            void refreshProjects().catch((error) => setHandoffError(
              `Could not refresh projects. ${error instanceof Error ? error.message : String(error)}`,
            ));
          },
        }}
      >
        <WorkspaceShell
          writingMode={mode}
          layout={workspaceLayout.preset}
          theme={ambiance}
          showConsole={false}
          bottomSlot={<></>}
          rightSlot={<></>}
          statusCenter={`${focusedLabel.toUpperCase()} · ${(projects.find((p) => p.id === projectId)?.title) ?? 'No project'}`}
          countdown="LIVE"
          sync={closePending ? 'CLOSING' : workspaceSaving ? 'SAVING' : projectSwitching ? 'SWITCHING' : workspaceHydrated ? '100' : 'LOADING'}
          navSlot={rail}
          centerSlot={
            workspaceHydrated ? (
              <DockWorkspace
                layout={workspaceLayout}
                panels={openedPanels}
                disabled={projectSwitching || closePending}
                onActivate={(panelId) => activateDockPanel(panelId)}
                onMove={(panelId, region, index) => moveDockPanel(panelId, region, index)}
                onFloat={floatWorkspacePanel}
                onClose={closeDockPanel}
                onToggleDock={changeDockCollapsed}
                onResizeDock={(region, size) => applyWorkspaceLayout((layout) => resizeDock(layout, region, size))}
                onMoveFloating={moveWorkspaceFloatingPanel}
                onResizeFloating={resizeWorkspaceFloatingPanel}
                onMinimizeFloating={changeFloatingPanelMinimized}
                onFocusFloating={focusWorkspaceFloatingPanel}
                onReset={restoreDefaultWorkspace}
              />
            ) : (
              <div className="panel-host" role="status" aria-live="polite">
                Loading this project's workspace layout…
              </div>
            )
          }
          onCommandPalette={() => setPaletteOpen(true)}
          onToggleFocus={toggleFocus}
        />
        <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} commands={commands} />
      </StudioProvider>
      </PanelErrorBoundary>
      {(handoffError || workspaceError) && (
        <button type="button"
          role="alert"
          onClick={() => {
            if (handoffError) setHandoffError(null);
            else void retryLayoutPersistence();
          }}
          title={handoffError ? 'Dismiss' : 'Retry workspace layout persistence'}
          style={{
            position: 'fixed', left: '50%', bottom: 24, zIndex: 1000,
            transform: 'translateX(-50%)', maxWidth: 'min(760px, calc(100% - 40px))',
            padding: '9px 14px', border: '1px solid var(--crimson)',
            background: 'var(--panel)', color: 'var(--strong)', font: 'inherit',
            fontSize: 11, lineHeight: 1.4, cursor: 'pointer', boxShadow: '0 12px 40px rgba(0,0,0,.45)',
          }}
        >
          {handoffError ?? `Workspace layout could not be loaded or saved. ${workspaceError?.message ?? ''} Click to retry.`}
        </button>
      )}
      <RuntimeFaultBanner fault={runtimeFault} onDismiss={dismissRuntimeFault} bottom={(handoffError || workspaceError) ? 78 : 24} />
    </div>
  );
}
