import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import {
  StudioProvider,
  createHttpApiClient,
  type ApiClient,
  type PlatformAdapter,
  type SkinId,
  SKIN_OPTIONS,
  resolveSkin,
  WorkspaceShell,
  DockWorkspace,
  WorkspaceNavigator,
  StudioSceneNavigator,
  type WorkspaceDockRegion,
  type WorkspaceLayout,
  type WorkspacePanelDefinition,
  type ExternalFloatingWindowHost,
  type StudioNavigationOptions,
  type KnowledgeGraphNavigationTarget,
  type ProgressionNavigationTarget,
  type ContinuityRepairTarget,
  STUDIO_AI_COMPANIONS_PANEL_ID,
  STUDIO_PANELS,
  STUDIO_WORKSPACE_PANEL_IDS,
  findStudioPanel,
  studioPanelGroupsForMode,
  studioPanelShortcut,
  panelIdForKeyboardShortcut,
  formatStudioShortcut,
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
  setFloatingPanelBounds,
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
  createCommandRegistry,
  deriveWorkspaceStatus,
  getProjectSaveStatusSnapshot,
  getPanelHostDocuments,
  resetProjectSaveStatus,
  subscribeProjectSaveStatus,
  parseRecentProjectIds,
  rememberRecentProject,
  LiveContextPublishController,
  useSelection,
} from '@logosforge/pro-shared-ui';
import { WRITING_MODES, type WritingMode, type ProjectDTO } from '@logosforge/ui-contracts';
import { desktop, platform, type CoreStatus } from './platform';
import { AiDock, AI_TOOL_KEYS } from './AiDock';
import { CommandPalette, type Command } from './CommandPalette';
import { CoreGenerationTracker } from './coreGeneration';
import {
  projectIdFromSessionState,
  selectStartupProjectId,
} from './projectResume';
import { applySkinPreference, readSkinPreference, writeSkinPreference } from './skinPreference';

// Shared UI owns the platform-neutral panel catalog. The desktop host retains
// the AI companion container plus project/bootstrap and lifecycle orchestration.
const PANELS = STUDIO_PANELS;
const AI_PANEL_ID = STUDIO_AI_COMPANIONS_PANEL_ID;
const ALL_PANEL_IDS = STUDIO_WORKSPACE_PANEL_IDS;
const MANUSCRIPT_TAB_SELECTOR = `#lf-tab-${workspacePanelDomToken('manuscript')}`;
const EXPAND_RIGHT_DOCK_SELECTOR = '[aria-label="Expand right dock"]';
const RECENT_PROJECTS_KEY = 'lf.omnibox.recent-projects.v1';
const LEGACY_THEME_FOR_SKIN: Record<SkinId, 'dark' | 'light' | 'warm'> = {
  forge: 'dark',
  paper: 'light',
  lamplit: 'warm',
};

const resolvePanel = findStudioPanel;

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

interface BootstrapRun {
  api: ApiClient;
  attempt: number;
  coreGeneration: number;
}

async function loadLastActiveProjectId(): Promise<number | null> {
  try {
    return projectIdFromSessionState(await desktop?.loadDesktopSessionState());
  } catch {
    // Session resume is a convenience. A missing/corrupt/unreadable host file
    // must never stop the authoritative local project library from opening.
    return null;
  }
}

async function persistLastActiveProjectId(projectId: number | null): Promise<void> {
  try {
    await desktop?.saveLastActiveProjectId(projectId);
  } catch {
    // Project switching already committed in the core. Keep it successful even
    // if the small host-side resume hint cannot be updated on this launch.
  }
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

/** Publishes only transient Studio focus/selection state to the desktop host. */
function ProLiveContextPublisher({
  projectId,
  activePanelId,
}: {
  projectId: number | undefined;
  activePanelId: string;
}) {
  const { selection } = useSelection();
  const controllerRef = useRef<LiveContextPublishController | null>(null);

  useEffect(() => {
    const bridge = desktop;
    if (!bridge?.publishLiveContext || !bridge.clearLiveContext) return undefined;
    const controller = new LiveContextPublishController({
      publishLiveContext: (snapshot) => bridge.publishLiveContext(snapshot),
      clearLiveContext: () => bridge.clearLiveContext(),
    });
    controllerRef.current = controller;
    return () => {
      controllerRef.current = null;
      controller.dispose();
    };
  }, []);

  useEffect(() => {
    controllerRef.current?.update({
      projectId: projectId ?? null,
      activePanelId,
      activeSceneId: selection.sceneId,
      selectionSection: selection.section ?? '',
      selection: selection.text,
    });
  }, [activePanelId, projectId, selection.sceneId, selection.section, selection.text]);

  return null;
}

export function App() {
  const [status, setStatus] = useState<CoreStatus>({ state: 'connecting', baseUrl: '', managed: false });
  const coreStatusRef = useRef<CoreStatus>(status);
  const coreGenerationTrackerRef = useRef(new CoreGenerationTracker());
  const [projectId, setProjectId] = useState<number | undefined>(undefined);
  const [mode, setMode] = useState<WritingMode>('novel');
  const [modeBusy, setModeBusy] = useState(false);
  const [projectSwitching, setProjectSwitching] = useState(false);
  const [closePending, setClosePending] = useState(false);
  const [busy, setBusy] = useState(false);
  const [projectReady, setProjectReady] = useState(false);
  const [bootstrapAttempt, setBootstrapAttempt] = useState(0);
  const [pendingScene, setPendingScene] = useState<number | null>(null);
  const [pendingPsykeEntry, setPendingPsykeEntry] = useState<number | null>(null);
  const [pendingProgression, setPendingProgression] = useState<ProgressionNavigationTarget | null>(null);
  const [pendingNote, setPendingNote] = useState<number | null>(null);
  const [pendingComment, setPendingComment] = useState<number | null>(null);
  const [pendingKnowledgeGraph, setPendingKnowledgeGraph] = useState<KnowledgeGraphNavigationTarget | null>(null);
  const [pendingContinuityIssue, setPendingContinuityIssue] = useState<string | null>(null);
  const [pendingContinuityRepair, setPendingContinuityRepair] = useState<ContinuityRepairTarget | null>(null);
  const [handoffError, setHandoffError] = useState<string | null>(null);
  const { fault: runtimeFault, dismiss: dismissRuntimeFault } = useRuntimeFaultReporter();
  // Project handoffs, mode changes, and workspace mutations share one queue.
  // Separate queues let a delayed dock action run after a project switch and
  // accidentally mutate the newly opened project's layout.
  const operationQueue = useRef<Promise<void>>(Promise.resolve());
  const closingRef = useRef(false);
  const projectSwitchingRef = useRef(false);
  const projectReadyRef = useRef(false);
  const projectSwitchSequenceRef = useRef(0);
  const refreshProjectsSequenceRef = useRef(0);
  const projectIdRef = useRef(projectId);
  const bootstrapRunRef = useRef<BootstrapRun | null>(null);
  const bootstrapBusyOwnerRef = useRef<BootstrapRun | null>(null);
  const bootstrapRetryTimerRef = useRef<number | null>(null);
  const appMountedRef = useRef(true);
  const releaseBootstrapRun = useCallback((run: BootstrapRun | null) => {
    if (!run) return;
    if (bootstrapRunRef.current === run) bootstrapRunRef.current = null;
    if (bootstrapBusyOwnerRef.current === run) {
      bootstrapBusyOwnerRef.current = null;
      setBusy(false);
    }
  }, []);

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
  const projectSaveStatus = useSyncExternalStore(
    subscribeProjectSaveStatus,
    getProjectSaveStatusSnapshot,
    getProjectSaveStatusSnapshot,
  );
  const workspaceStatus = useMemo(() => deriveWorkspaceStatus({
    coreState: status.state,
    coreDetail: status.detail,
    projectSave: projectSaveStatus,
    workspaceLayoutSaving: workspaceSaving,
    workspaceLayoutError: workspaceError,
    handoffPhase: closePending ? 'closing' : projectSwitching ? 'switching' : 'idle',
    storage: 'local',
  }), [closePending, projectSaveStatus, projectSwitching, status.detail, status.state, workspaceError, workspaceSaving]);
  const workspaceHydratedProjectRef = useRef<number | undefined>(undefined);
  const workspaceLayoutRef = useRef(workspaceLayout);
  useLayoutEffect(() => {
    projectIdRef.current = projectId;
    workspaceHydratedProjectRef.current = workspaceHydrated ? projectId : undefined;
    workspaceLayoutRef.current = workspaceLayout;
  }, [projectId, workspaceHydrated, workspaceLayout]);

  // Companion choice and visual skin remain app preferences. Dock placement,
  // visibility, dimensions, and Focus/Cockpit are versioned per project above.
  const [aiTab, setAiTab] = useState<string>(() => localStorage.getItem('lf.aiTab') || AI_TOOL_KEYS[0] || 'Billy');
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [recentProjectIds, setRecentProjectIds] = useState<readonly number[]>(
    () => parseRecentProjectIds(localStorage.getItem(RECENT_PROJECTS_KEY)),
  );
  const [skin, setSkin] = useState<SkinId>(readSkinPreference);
  const nativePanelWindowTokensRef = useRef(new Map<string, string>());
  const externalFloatingWindows = useMemo<ExternalFloatingWindowHost | undefined>(() => {
    const bridge = desktop;
    if (!bridge?.nativePanelWindowFrameName) return undefined;
    const leases = new Map<string, { popup: Window; count: number; token: string }>();
    return {
      open: (panelId, _label, bounds) => {
        const current = leases.get(panelId);
        if (current && !current.popup.closed) {
          leases.set(panelId, { ...current, count: current.count + 1 });
          nativePanelWindowTokensRef.current.set(panelId, current.token);
          return current.popup;
        }
        if (current) leases.delete(panelId);

        const token = globalThis.crypto.randomUUID();
        const popup = window.open(
          'about:blank',
          bridge.nativePanelWindowFrameName(panelId, token),
          [
            'popup=yes',
            `left=${Math.round(bounds.x)}`,
            `top=${Math.round(bounds.y)}`,
            `width=${Math.round(bounds.width)}`,
            `height=${Math.round(bounds.height)}`,
            'resizable=yes',
            'scrollbars=no',
          ].join(','),
        );
        if (popup) {
          leases.set(panelId, { popup, count: 1, token });
          nativePanelWindowTokensRef.current.set(panelId, token);
        }
        return popup;
      },
      release: (panelId) => {
        const current = leases.get(panelId);
        if (!current) return;
        if (current && current.count > 1) {
          leases.set(panelId, { ...current, count: current.count - 1 });
          return;
        }
        leases.delete(panelId);
        if (nativePanelWindowTokensRef.current.get(panelId) === current.token) {
          nativePanelWindowTokensRef.current.delete(panelId);
        }
        void bridge.closeNativePanelWindow(panelId, current.token);
      },
      show: (panelId, activate) => {
        const token = leases.get(panelId)?.token;
        if (token) void bridge.showNativePanelWindow(panelId, token, activate);
      },
      focus: (panelId) => {
        const token = leases.get(panelId)?.token;
        if (token) void bridge.focusNativePanelWindow(panelId, token);
      },
    };
  }, []);
  useEffect(() => { localStorage.setItem('lf.aiTab', aiTab); }, [aiTab]);
  useEffect(() => { writeSkinPreference(skin); }, [skin]);
  useEffect(() => {
    if (projectId == null) return;
    setRecentProjectIds((current) => {
      const next = rememberRecentProject(current, projectId);
      localStorage.setItem(RECENT_PROJECTS_KEY, JSON.stringify(next));
      return next;
    });
  }, [projectId]);
  // Drive the global skin (body + command palette live outside the shared shell).
  useLayoutEffect(() => { applySkinPreference(skin); }, [skin]);
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
    if (closingRef.current || !projectReadyRef.current) return Promise.resolve(false);
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

  const selectPanel = useCallback((panelValue: string, opts?: StudioNavigationOptions): Promise<boolean> => {
    const panel = resolvePanel(panelValue);
    const panelId = panelValue === AI_PANEL_ID ? AI_PANEL_ID : panel?.id;
    if (!panelId) return Promise.resolve(false);
    const preferredRegion = panelId === AI_PANEL_ID ? 'right' : panel?.preferredRegion ?? 'center';
    const task = runWorkspaceMutation((layout) => {
      // The Focus Manuscript is a visual projection. Selecting it may publish
      // a scene target, but must not unminimize/raise/reorder its hidden saved
      // Cockpit placement.
      let next = layout.preset === 'focus' && panelId === 'manuscript'
        ? layout
        : openWorkspacePanel(layout, panelId, preferredRegion);
      if (next.preset === 'focus' && panelId !== 'manuscript') {
        next = setWorkspacePreset(next, 'cockpit');
      }
      return next;
    }, 'Panel switch stopped; the current workspace remains open.');
    return task.then((selected) => {
      if (!selected) return false;
      // A newer successful navigation supersedes every older one-shot target.
      // Publish a target only to its owning surface: all opened panels stay
      // mounted, so leaking an AI repair's Scene id to Manuscript can otherwise
      // scroll and steal focus after Billy becomes active.
      setPendingScene(panelId === 'manuscript' ? opts?.sceneId ?? null : null);
      setPendingPsykeEntry(panelId === 'psyke' ? opts?.psykeEntryId ?? null : null);
      setPendingProgression(panelId === 'progressions' && (
        opts?.progressionTrackId != null || opts?.progressionBeatId != null
      ) ? {
        trackId: opts.progressionTrackId ?? null,
        beatId: opts.progressionBeatId ?? null,
      } : null);
      setPendingNote(panelId === 'notes' ? opts?.noteId ?? null : null);
      setPendingComment(panelId === 'comments' ? opts?.commentId ?? null : null);
      setPendingKnowledgeGraph(panelId === 'graph' && opts?.graphFocusKey ? {
        focusKey: opts.graphFocusKey,
        viewMode: opts.graphViewMode ?? 'project_map',
        includeInferred: opts.graphIncludeInferred ?? true,
        depth: opts.graphDepth ?? 1,
      } : null);
      setPendingContinuityIssue(panelId === 'continuity' ? opts?.continuityIssueKey ?? null : null);
      setPendingContinuityRepair(panelId === AI_PANEL_ID ? opts?.continuityRepair ?? null : null);
      if (panelId === AI_PANEL_ID && opts?.aiTool && AI_TOOL_KEYS.includes(opts.aiTool)) {
        setAiTab(opts.aiTool);
      }
      if (getPanelPlacement(workspaceLayoutRef.current, panelId)?.kind === 'floating') {
        // Native child documents do not participate in the opener's DOM focus
        // search. The host restores/focuses the one existing window instead.
        const token = nativePanelWindowTokensRef.current.get(panelId);
        if (token) void desktop?.focusNativePanelWindow(panelId, token);
      } else {
        window.focus();
      }
      return true;
    });
  }, [runWorkspaceMutation]);

  const panelFocusTarget = useCallback((panelId: string): HTMLElement | null => {
    const layout = workspaceLayoutRef.current;
    if (layout.preset === 'focus' && panelId === 'manuscript') {
      return document.querySelector<HTMLElement>(MANUSCRIPT_TAB_SELECTOR);
    }
    const placement = getPanelPlacement(layout, panelId);
    const selector = placement?.kind === 'floating'
      ? `#lf-floating-title-${workspacePanelDomToken(panelId)}`
      : `#lf-tab-${workspacePanelDomToken(panelId)}`;
    return document.querySelector<HTMLElement>(selector);
  }, []);

  const selectPanelAndFocus = useCallback((panelId: string): Promise<boolean> => {
    // A true modal owns the interaction until it closes. Modeless floating
    // panels use aria-modal=false and therefore do not block navigation.
    if (document.querySelector('[role="dialog"][aria-modal="true"]')) {
      return Promise.resolve(false);
    }
    const task = selectPanel(panelId);
    focusAfterWorkspaceAction(task, () => panelFocusTarget(panelId));
    return task;
  }, [panelFocusTarget, selectPanel]);

  // Cross-panel navigation: any panel can switch panels / open a scene, but no
  // panel unmounts a dirty editor until its save barrier succeeds.
  const navigate = useCallback((panel: string, opts?: StudioNavigationOptions) => {
    return selectPanel(panel, opts);
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
      () => panelFocusTarget(AI_PANEL_ID),
    );
    return task;
  }, [panelFocusTarget, selectPanel]);
  const toggleFocus = useCallback((): Promise<boolean> => {
    const enteringFocus = workspaceLayoutRef.current.preset !== 'focus';
    const returnPanelId = workspaceLayoutRef.current.focused?.panelId ?? 'manuscript';
    const task = runWorkspaceMutation(
      toggleWorkspacePreset,
      'Focus-mode change stopped; the current workspace remains visible.',
    );
    if (enteringFocus) {
      focusAfterWorkspaceAction(
        task,
        () => document.querySelector<HTMLElement>(MANUSCRIPT_TAB_SELECTOR),
      );
    } else {
      focusAfterWorkspaceAction(task, () => panelFocusTarget(returnPanelId));
    }
    return task;
  }, [panelFocusTarget, runWorkspaceMutation]);

  // Mode-aware nav: mode-specific panels (Chapters=novel, Series=series) appear
  // only in their writing mode — mirroring the Python core's per-mode gating.
  const visibleGroups = useMemo(
    () => studioPanelGroupsForMode(mode),
    [mode],
  );
  const visiblePanels = useMemo(() => visibleGroups.flatMap((g) => g.panels), [visibleGroups]);
  const omniboxPanels = useMemo(() => [
    ...visiblePanels.map((panel) => ({
      id: panel.id,
      label: panel.label,
      keywords: [panel.id],
      shortcut: panel.shortcut,
    })),
    {
      id: AI_PANEL_ID,
      label: 'AI Companions',
      keywords: ['Billy', 'Logos', 'Counterpart', 'assistant'],
      shortcut: studioPanelShortcut(AI_PANEL_ID),
    },
  ], [visiblePanels]);

  // Normalize only mode-ineligible panels. Every eligible surface, including
  // Manuscript and AI Companions, keeps its saved dock/floating placement.
  useEffect(() => {
    if (!workspaceHydrated) return;
    const unavailable = new Set(PANELS
      .filter((panel) => panel.modes && !panel.modes.includes(mode))
      .map((panel) => panel.id));
    const unavailableIsOpen = [...unavailable]
      .some((panelId) => getPanelPlacement(workspaceLayout, panelId) !== null);
    if (!unavailableIsOpen) return;
    void runWorkspaceMutation((layout) => {
      let next = layout;
      unavailable.forEach((panelId) => {
        if (getPanelPlacement(next, panelId) !== null) next = closeWorkspacePanel(next, panelId);
      });
      return next.focused === null ? openWorkspacePanel(next, 'manuscript', 'center') : next;
    }, 'Workspace normalization stopped; the previous layout remains open.');
  }, [mode, runWorkspaceMutation, workspaceHydrated, workspaceLayout]);

  // Every catalog shortcut uses the same save-aware navigation path as a tab
  // click. Existing floating panels are restored/raised by openPanel; closed
  // panels open in their preferred dock. AltGraph is rejected by the matcher.
  const handleWorkspaceKeyDown = useCallback((e: KeyboardEvent) => {
    if (!projectReadyRef.current) return;
    if (getPanelHostDocuments().some(
      (hostDocument) => hostDocument.querySelector('[role="dialog"][aria-modal="true"]'),
    )) return;
    const panelId = panelIdForKeyboardShortcut(e);
    const panelAvailable = panelId === AI_PANEL_ID
      || visiblePanels.some((panel) => panel.id === panelId);
    if (panelId && panelAvailable && workspaceHydrated) {
      e.preventDefault();
      void selectPanelAndFocus(panelId);
    } else if ((e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey && !e.repeat && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      window.focus();
      setPaletteOpen(true);
    } else if (e.key === 'Escape' && workspaceLayoutRef.current.preset === 'focus' && !paletteOpen) {
      void toggleFocus();
    }
  }, [paletteOpen, selectPanelAndFocus, toggleFocus, visiblePanels, workspaceHydrated]);

  useEffect(() => {
    window.addEventListener('keydown', handleWorkspaceKeyDown);
    return () => window.removeEventListener('keydown', handleWorkspaceKeyDown);
  }, [handleWorkspaceKeyDown]);

  useEffect(() => {
    if (!desktop) return;
    let active = true;
    let liveEventSeen = false;
    const publishCoreStatus = (next: CoreStatus) => {
      coreStatusRef.current = next;
      const tracker = coreGenerationTrackerRef.current;
      const previousGeneration = tracker.current();
      const nextGeneration = tracker.observe(next);
      if (nextGeneration !== previousGeneration) {
        const invalidatedRun = bootstrapRunRef.current;
        releaseBootstrapRun(invalidatedRun);
        projectReadyRef.current = false;
        setProjectReady(false);
        setModeBusy(false);
        setPaletteOpen(false);
      }
      setStatus(next);
    };
    const unsubscribe = desktop.onCoreStatus((next) => {
      if (!active) return;
      liveEventSeen = true;
      publishCoreStatus(next);
    });
    void desktop.getCoreStatus().then((next) => {
      if (active && !liveEventSeen) publishCoreStatus(next);
    }).catch((error) => {
      if (active && !liveEventSeen) {
        publishCoreStatus({
          state: 'error', baseUrl: '', managed: false,
          detail: `Could not read core status. ${error instanceof Error ? error.message : String(error)}`,
        });
      }
    });
    return () => { active = false; unsubscribe(); };
  }, [releaseBootstrapRun]);

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
  const baseUrl = status.state === 'connected' && status.baseUrl ? status.baseUrl : null;
  const api = useMemo<ApiClient | null>(
    () => (baseUrl != null ? createHttpApiClient(baseUrl, status.authToken ?? '') : null),
    [baseUrl, status.authToken],
  );
  // Bound to the render that created `api`. Old callbacks retain this number,
  // so a synchronous status event invalidates them before React has to rerender.
  const apiCoreGeneration = coreGenerationTrackerRef.current.current();
  const apiDisposer = useMemo(
    () => createDeferredDisposer<ApiClient>((client) => client.dispose?.()),
    [],
  );
  useEffect(() => (api ? apiDisposer.acquire(api) : undefined), [api, apiDisposer]);

  const selectProject = useCallback((id: number): Promise<boolean> => {
    if (closingRef.current || !projectReadyRef.current) return Promise.resolve(false);
    const ownerApi = api;
    const ownerCoreGeneration = apiCoreGeneration;
    const isCurrentCore = () => coreGenerationTrackerRef.current.isCurrent(ownerCoreGeneration)
      && coreStatusRef.current.state === 'connected';
    const target = id || undefined;
    const requestSequence = projectSwitchSequenceRef.current + 1;
    projectSwitchSequenceRef.current = requestSequence;
    projectSwitchingRef.current = true;
    setProjectSwitching(true);
    const task = operationQueue.current.then(async () => {
      if (!isCurrentCore()) return false;
      if (projectIdRef.current === target) {
        void persistLastActiveProjectId(target ?? null);
        return true;
      }
      if (!ownerApi && target != null) return false;
      try {
        let opened: ProjectDTO | null = null;
        if (target == null) await flushPendingProjectSaves({ commitActiveField: true });
        else opened = await prepareProjectHandoff(() => {
          if (!isCurrentCore()) throw new Error('The core changed while opening the project.');
          return ownerApi!.openProject(target);
        });
        if (!isCurrentCore()) return false;
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
        if (!isCurrentCore()) return false;
        setHandoffError(
          `Project switch stopped; your current manuscript remains open. ${
            error instanceof Error ? error.message : String(error)
          }`,
        );
        return false;
      }
      workspaceHydratedProjectRef.current = undefined;
      resetProjectSaveStatus();
      setProjectId(target);
      projectIdRef.current = target;
      void persistLastActiveProjectId(target ?? null);
      setPendingScene(null);
      setPendingPsykeEntry(null);
      setPendingProgression(null);
      setPendingNote(null);
      setPendingComment(null);
      setPendingKnowledgeGraph(null);
      setPendingContinuityIssue(null);
      setPendingContinuityRepair(null);
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
  }, [api, apiCoreGeneration]);

  // Project list + selection. On connect, load the projects; if there are none,
  // create a starter one so a fresh install can write immediately (otherwise
  // every panel shows an empty "open a project" state with no way to make one).
  const [projects, setProjects] = useState<ProjectDTO[]>([]);

  const refreshProjects = useCallback(async (): Promise<ProjectDTO[]> => {
    if (!api) return [];
    const ownerApi = api;
    const ownerCoreGeneration = apiCoreGeneration;
    const refreshSequence = refreshProjectsSequenceRef.current + 1;
    refreshProjectsSequenceRef.current = refreshSequence;
    const isCurrentRefresh = () => coreGenerationTrackerRef.current.isCurrent(ownerCoreGeneration)
      && coreStatusRef.current.state === 'connected'
      && refreshProjectsSequenceRef.current === refreshSequence;
    let ps: ProjectDTO[];
    try {
      ps = await ownerApi.listProjects();
    } catch (error) {
      // An older request must not overwrite a newer result with a late error.
      if (!isCurrentRefresh()) return [];
      throw error;
    }
    if (!isCurrentRefresh()) return [];
    setProjects(ps);
    const active = ps.find((project) => project.id === projectIdRef.current);
    if (active) setMode(projectWritingMode(active));
    return ps;
  }, [api, apiCoreGeneration]);

  const changeProjectMode = useCallback((nextMode: WritingMode): Promise<boolean> => {
    if (closingRef.current || projectSwitchingRef.current) return Promise.resolve(false);
    const ownerApi = api;
    if (!ownerApi) return Promise.resolve(false);
    const ownerCoreGeneration = apiCoreGeneration;
    const isCurrentCore = () => coreGenerationTrackerRef.current.isCurrent(ownerCoreGeneration)
      && coreStatusRef.current.state === 'connected';
    const targetProjectId = projectIdRef.current;
    const task = operationQueue.current.then(async () => {
      if (!isCurrentCore()) return false;
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
        if (!isCurrentCore() || projectIdRef.current !== activeId) return false;
        const committed = await trackProjectWrite(
          ownerApi.updateProject(activeId, { narrative_engine: nextMode }),
        );
        if (!isCurrentCore() || projectIdRef.current !== activeId) return false;
        updated = committed;
        setProjects((current) => current.map((project) =>
          project.id === committed.id ? committed : project,
        ));
        if (projectIdRef.current === activeId) setMode(projectWritingMode(committed));
        // Capture edits made while the mode request was in flight. The core
        // update is already committed at this point, so retain the returned
        // project locally even when this final drain needs user attention.
        await flushPendingProjectSaves({ commitActiveField: true });
        if (!isCurrentCore() || projectIdRef.current !== activeId) return false;
        setHandoffError(null);
        return true;
      } catch (error) {
        if (!isCurrentCore()) return false;
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
        if (isCurrentCore()) setModeBusy(false);
      }
    });
    operationQueue.current = task.then(() => undefined, () => undefined);
    return task;
  }, [api, apiCoreGeneration]);

  useEffect(() => {
    const clearRetry = () => {
      if (bootstrapRetryTimerRef.current !== null) {
        window.clearTimeout(bootstrapRetryTimerRef.current);
        bootstrapRetryTimerRef.current = null;
      }
    };
    if (!api || status.state !== 'connected') {
      releaseBootstrapRun(bootstrapRunRef.current);
      clearRetry();
      return;
    }
    // A status event can invalidate the committed render before this passive
    // effect starts. Never let that stale render acquire shared busy ownership.
    if (!coreGenerationTrackerRef.current.isCurrent(apiCoreGeneration)
        || coreStatusRef.current.state !== 'connected') {
      releaseBootstrapRun(bootstrapRunRef.current);
      clearRetry();
      return;
    }
    if (bootstrapRunRef.current?.api !== api) {
      releaseBootstrapRun(bootstrapRunRef.current);
      clearRetry();
    }
    if (projectReady) {
      releaseBootstrapRun(bootstrapRunRef.current);
      clearRetry();
      return;
    }
    if (busy) return;
    const previous = bootstrapRunRef.current;
    if (previous?.api === api
      && previous.attempt === bootstrapAttempt
      && previous.coreGeneration === apiCoreGeneration) return;
    const run = { api, attempt: bootstrapAttempt, coreGeneration: apiCoreGeneration };
    bootstrapRunRef.current = run;
    bootstrapBusyOwnerRef.current = run;
    const isCurrent = () => appMountedRef.current
      && bootstrapRunRef.current === run
      && coreGenerationTrackerRef.current.isCurrent(run.coreGeneration)
      && coreStatusRef.current.state === 'connected'
      && !closingRef.current;
    setBusy(true);
    void (async () => {
      try {
        let nextProjects = await api.listProjects();
        if (!isCurrent()) return;
        if (nextProjects.length === 0) {
          const created = await api.createProject({ title: 'Untitled Project', narrative_engine: mode });
          if (!isCurrent()) return;
          nextProjects = [created];
        }

        const persistedProjectId = await loadLastActiveProjectId();
        if (!isCurrent()) return;
        const targetProjectId = selectStartupProjectId(nextProjects, persistedProjectId);
        if (targetProjectId == null) throw new Error('The local project library is empty.');

        // Startup has no outgoing project, but still use the normal open endpoint
        // and save barrier so project-loaded observers see the same lifecycle as a
        // writer-initiated switch. Keep all state publication behind the bootstrap
        // identity guard: a replacement core must never receive this stale result.
        const opened = await prepareProjectHandoff(() => {
          if (!isCurrent()) throw new Error('The core changed while opening the startup project.');
          return api.openProject(targetProjectId);
        });
        if (!isCurrent()) return;
        nextProjects = nextProjects.some((candidate) => candidate.id === opened.id)
          ? nextProjects.map((candidate) => candidate.id === opened.id ? opened : candidate)
          : [...nextProjects, opened];
        setProjects(nextProjects);
        workspaceHydratedProjectRef.current = undefined;
        resetProjectSaveStatus();
        setProjectId(opened.id);
        projectIdRef.current = opened.id;
        setMode(projectWritingMode(opened));
        setPendingScene(null);
        setPendingPsykeEntry(null);
        setPendingProgression(null);
        setPendingNote(null);
        setPendingComment(null);
        setPendingKnowledgeGraph(null);
        setPendingContinuityIssue(null);
        setPendingContinuityRepair(null);
        projectReadyRef.current = true;
        setProjectReady(true);
        void persistLastActiveProjectId(opened.id);
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
        if (bootstrapBusyOwnerRef.current === run) {
          bootstrapBusyOwnerRef.current = null;
          if (appMountedRef.current) setBusy(false);
        }
      }
    })();
  }, [
    api,
    apiCoreGeneration,
    status.state,
    busy,
    projects.length,
    projectId,
    projectReady,
    mode,
    bootstrapAttempt,
    releaseBootstrapRun,
  ]);

  const newProject = useCallback(async () => {
    if (!api || !projectReadyRef.current || busy || projectSwitchingRef.current || closingRef.current) return;
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
    return runWorkspaceMutation(
      (layout) => placePanel(layout, panelId, { kind: 'dock', region, index }),
      'Panel move stopped; the previous dock layout is unchanged.',
    );
  }, [runWorkspaceMutation]);

  const floatWorkspacePanel = useCallback((panelId: string, bounds?: Partial<FloatingPanelBounds>) => {
    return runWorkspaceMutation(
      (layout) => placePanel(layout, panelId, { kind: 'floating', bounds }),
      'Panel tear-off stopped; the previous workspace layout is unchanged.',
    );
  }, [runWorkspaceMutation]);

  const moveWorkspaceFloatingPanel = useCallback((panelId: string, x: number, y: number) => {
    applyWorkspaceLayout((layout) => moveFloatingPanel(layout, panelId, x, y));
  }, [applyWorkspaceLayout]);

  const resizeWorkspaceFloatingPanel = useCallback((panelId: string, width: number, height: number) => {
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
    const token = nativePanelWindowTokensRef.current.get(panelId);
    const task = runWorkspaceMutation(
      (layout) => minimized
        ? setFloatingPanelMinimized(layout, panelId, true)
        : focusWorkspacePanel(setFloatingPanelMinimized(layout, panelId, false), panelId),
      minimized
        ? 'Panel minimize stopped; the floating panel remains open.'
        : 'Panel restore stopped; the panel remains minimized.',
    );
    void task.then((changed) => {
      if (!changed || !token) return;
      if (minimized) void desktop?.minimizeNativePanelWindow(panelId, token);
      else void desktop?.restoreNativePanelWindow(panelId, token);
    });
    return task;
  }, [runWorkspaceMutation]);

  const closeDockPanel = useCallback((panelId: string) => {
    if (panelId === 'manuscript' || panelId === AI_PANEL_ID) return Promise.resolve(false);
    return runWorkspaceMutation(
      (layout) => closeWorkspacePanel(layout, panelId),
      'Panel close stopped; the panel remains open.',
    );
  }, [runWorkspaceMutation]);

  useEffect(() => {
    const bridge = desktop;
    if (!bridge?.onNativePanelWindowEvent) return;

    const persistNativeBounds = (panelId: string, bounds: FloatingPanelBounds) => {
      const current = workspaceLayoutRef.current.floatingPanels.find((entry) => entry.panelId === panelId);
      if (!current) return;
      if (
        current.coordinateSpace === 'screen'
        && current.x === bounds.x
        && current.y === bounds.y
        && current.width === bounds.width
        && current.height === bounds.height
      ) return;
      applyWorkspaceLayout((layout) => setFloatingPanelBounds(layout, panelId, bounds, 'screen'));
    };

    return bridge.onNativePanelWindowEvent((event) => {
      if (nativePanelWindowTokensRef.current.get(event.panelId) !== event.token) return;
      const placement = getPanelPlacement(workspaceLayoutRef.current, event.panelId);
      if (placement?.kind !== 'floating') return;
      if ('bounds' in event) persistNativeBounds(event.panelId, event.bounds);

      if (event.type === 'bounds-changed') return;
      if (event.type === 'focused') {
        const current = workspaceLayoutRef.current;
        const floating = current.floatingPanels.find((entry) => entry.panelId === event.panelId);
        const alreadyFront = floating?.zIndex === current.floatingPanels.length - 1
          && current.focused?.zone === 'floating'
          && current.focused.panelId === event.panelId;
        if (!alreadyFront) {
          applyWorkspaceLayout((layout) => bringFloatingPanelToFront(layout, event.panelId));
        }
        return;
      }
      if (event.type === 'minimized') {
        if (workspaceLayoutRef.current.floatingPanels.find(
          (entry) => entry.panelId === event.panelId,
        )?.minimized) return;
        void changeFloatingPanelMinimized(event.panelId, true).then((changed) => {
          if (!changed) void bridge.restoreNativePanelWindow(event.panelId, event.token);
        });
        return;
      }
      if (event.type === 'restored') {
        if (!workspaceLayoutRef.current.floatingPanels.find(
          (entry) => entry.panelId === event.panelId,
        )?.minimized) return;
        void changeFloatingPanelMinimized(event.panelId, false).then((changed) => {
          if (!changed) void bridge.minimizeNativePanelWindow(event.panelId, event.token);
        });
        return;
      }
      if (event.type === 'closed' && event.reason === 'renderer') return;
      if (event.type !== 'close-requested' && event.type !== 'closed') return;

      const permanent = event.panelId === 'manuscript' || event.panelId === AI_PANEL_ID;
      const preferredRegion: WorkspaceDockRegion = event.panelId === AI_PANEL_ID ? 'right' : 'center';
      void runWorkspaceMutation(
        (layout) => permanent
          ? placePanel(layout, event.panelId, {
            kind: 'dock',
            region: preferredRegion,
            index: layout.docks[preferredRegion].panelIds.length,
          })
          : closeWorkspacePanel(layout, event.panelId),
        permanent
          ? 'Panel redock stopped; the native window remains open.'
          : 'Panel close stopped; the native window remains open.',
      );
    });
  }, [applyWorkspaceLayout, changeFloatingPanelMinimized, runWorkspaceMutation]);

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
        node: (
          <PanelErrorBoundary name={`${panel.label} panel`} resetKey={`${projectId ?? 'none'}:${panel.id}`}>
            {panel.node}
          </PanelErrorBoundary>
        ),
      }];
    });
  }, [aiTab, applyWorkspaceLayout, collapseAiDock, projectId, workspaceLayout]);

  // One runtime registry drives the palette and every app-specific native-menu
  // command. Handlers retain the existing save barriers and focus restoration.
  const commands = useMemo<Command[]>(() => [
    {
      id: 'new-project', kind: 'Project', label: 'New project',
      keywords: ['create project', 'file'], shortcut: 'Primary+N',
      enabled: () => projectReadyRef.current && !busy && !projectSwitchingRef.current && !closingRef.current,
      run: newProject,
    },
    ...PANELS.map((panel) => ({
      id: `nav:${panel.id}`,
      kind: 'Go' as const,
      label: panel.label,
      aliases: [`nav:${panel.label}`, `go-${panel.label}`],
      keywords: ['panel', 'workspace', panel.id],
      shortcut: panel.shortcut,
      showInOmnibox: false,
      enabled: () => projectReadyRef.current && workspaceHydrated && !projectSwitchingRef.current && !closingRef.current,
      run: () => !panel.modes || panel.modes.includes(mode)
        ? selectPanelAndFocus(panel.id)
        : Promise.resolve(false),
    })),
    {
      id: `nav:${AI_PANEL_ID}`,
      kind: 'Go',
      label: 'AI Companions',
      aliases: ['nav:AI Companions', 'go-AI Companions'],
      keywords: ['panel', 'workspace', 'Billy', 'Logos', 'Counterpart'],
      shortcut: studioPanelShortcut(AI_PANEL_ID),
      showInOmnibox: false,
      enabled: () => projectReadyRef.current && workspaceHydrated && !projectSwitchingRef.current && !closingRef.current,
      run: () => selectPanelAndFocus(AI_PANEL_ID),
    },
    ...AI_TOOL_KEYS.map((key) => ({
      id: `ai:${key}`,
      kind: 'AI' as const,
      label: key,
      aliases: [`ai-${key}`],
      keywords: ['assistant', 'companion'],
      enabled: () => projectReadyRef.current && !projectSwitchingRef.current && !closingRef.current,
      run: () => openAi(key),
    })),
    {
      id: 'focus', kind: 'View',
      label: workspaceLayout.preset === 'focus' ? 'Exit focus mode' : 'Enter focus mode',
      aliases: ['workspace.focus'], keywords: ['cockpit', 'distraction free'],
      shortcut: 'Primary+Shift+F',
      enabled: () => projectReadyRef.current && !projectSwitchingRef.current && !closingRef.current,
      run: toggleFocus,
    },
    {
      id: 'ai-dock', kind: 'View', label: 'Open / focus AI Companions',
      aliases: ['workspace.ai-dock'],
      enabled: () => projectReadyRef.current && !projectSwitchingRef.current && !closingRef.current,
      run: () => selectPanelAndFocus(AI_PANEL_ID),
    },
    {
      id: 'reset-workspace', kind: 'View', label: 'Reset workspace layout',
      aliases: ['workspace.reset'], keywords: ['restore docks'],
      enabled: () => projectReadyRef.current && !projectSwitchingRef.current && !closingRef.current,
      run: restoreDefaultWorkspace,
    },
    ...SKIN_OPTIONS.map((skinOption) => ({
      id: `skin:${skinOption.id}`,
      kind: 'Skin' as const,
      label: `Use ${skinOption.label} skin`,
      aliases: [
        `theme:${LEGACY_THEME_FOR_SKIN[skinOption.id]}`,
        `appearance.${LEGACY_THEME_FOR_SKIN[skinOption.id]}`,
        `appearance.${skinOption.id}`,
      ],
      keywords: ['skin', skinOption.label, skinOption.description],
      run: () => setSkin(skinOption.id),
    })),
  ], [busy, mode, newProject, openAi, restoreDefaultWorkspace, selectPanelAndFocus, toggleFocus, workspaceHydrated, workspaceLayout.preset]);
  const commandRegistry = useMemo(() => createCommandRegistry(commands), [commands]);

  // Native menu (electron/menu.ts) → the same handlers the sidebar / palette use.
  useEffect(() => {
    if (!desktop?.onMenuCommand) return;
    return desktop.onMenuCommand((cmd) => {
      if (cmd === 'palette') {
        if (projectReadyRef.current) setPaletteOpen(true);
        return;
      }
      void commandRegistry.execute(cmd).catch((error) => setHandoffError(
        `Command “${cmd}” could not run. ${error instanceof Error ? error.message : String(error)}`,
      ));
    });
  }, [commandRegistry]);

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
  if (!api || status.state !== 'connected') {
    return (
      <div className="boot">
        Connecting to the logosforge core…
        <span className="detail">{status.detail}</span>
      </div>
    );
  }
  if (!projectReady) {
    return (
      <div className="boot">
        Preparing your project…
        <span className="detail">{handoffError ?? 'Checking the local library and creating a blank project only when needed.'}</span>
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
      <StudioSceneNavigator
        disabled={!workspaceHydrated || projectSwitching || closePending}
        onOpenScene={(sceneId) => selectPanel('manuscript', { sceneId })}
        onSearch={() => setPaletteOpen(true)}
      />
      <label className="field">
        skins
        <select value={skin} onChange={(e) => setSkin(resolveSkin(e.target.value))}>
          {SKIN_OPTIONS.map((skinOption) => (
            <option key={skinOption.id} value={skinOption.id}>{skinOption.label}</option>
          ))}
        </select>
      </label>
      <nav>
        {visibleGroups.map((g, gi) => (
          <div key={g.group || `top-${gi}`} className="nav-group">
            {g.group && <div className="nav-group-label">{g.group}</div>}
            {g.panels.map((p) => (
              <button type="button" key={p.id} title={`${p.label} — ${formatStudioShortcut(p.shortcut)}`} disabled={!workspaceHydrated || projectSwitching || closePending} className={focusedPanelId === p.id ? 'on' : ''} aria-current={focusedPanelId === p.id ? 'page' : undefined} onClick={() => { void selectPanel(p.id); }}>
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
          clearManuscriptTarget: (sceneId) => setPendingScene((current) => sceneId == null || current === sceneId ? null : current),
          psykeTargetEntryId: pendingPsykeEntry,
          clearPsykeTarget: (entryId) => setPendingPsykeEntry((current) => entryId == null || current === entryId ? null : current),
          progressionTarget: pendingProgression,
          clearProgressionTarget: (trackId, beatId) => setPendingProgression((current) => (
            (trackId == null && beatId == null)
            || (current?.trackId === (trackId ?? null) && current?.beatId === (beatId ?? null))
              ? null
              : current
          )),
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
          refreshProjects: () => {
            void refreshProjects().catch((error) => setHandoffError(
              `Could not refresh projects. ${error instanceof Error ? error.message : String(error)}`,
            ));
          },
        }}
      >
        <ProLiveContextPublisher projectId={projectId} activePanelId={focusedPanelId} />
        <WorkspaceShell
          writingMode={mode}
          layout={workspaceLayout.preset}
          skin={skin}
          showConsole
          bottomSlot={<></>}
          rightSlot={<></>}
          statusCenter={`${focusedLabel.toUpperCase()} · ${(projects.find((p) => p.id === projectId)?.title) ?? 'No project'}`}
          runtimeStatus={workspaceStatus}
          coreState={status.state}
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
                externalFloatingWindows={externalFloatingWindows}
                onExternalWindowKeyDown={handleWorkspaceKeyDown}
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
        <CommandPalette
          open={paletteOpen}
          onClose={() => setPaletteOpen(false)}
          onError={(error, label) => setHandoffError(
            `Omnibox action “${label}” could not run. ${error instanceof Error ? error.message : String(error)}`,
          )}
          registry={commandRegistry}
          panels={omniboxPanels}
          projects={projects}
          recentProjectIds={recentProjectIds}
          onNavigate={selectPanel}
          onSelectProject={selectProject}
        />
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
