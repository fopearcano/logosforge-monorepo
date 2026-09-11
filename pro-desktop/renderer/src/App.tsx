import { useCallback, useEffect, useMemo, useRef, useState, type ReactElement } from 'react';
import {
  StudioProvider,
  createHttpApiClient,
  type ApiClient,
  type PlatformAdapter,
  WorkspaceShell,
  ManuscriptEditor,
  NotesPanel,
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
} from '@logosforge/pro-shared-ui';
import { WRITING_MODES, type WritingMode, type ProjectDTO } from '@logosforge/ui-contracts';
import { desktop, platform, type CoreStatus } from './platform';
import { AiDock, AI_TOOL_KEYS } from './AiDock';
import { CommandPalette, type Command } from './CommandPalette';

interface Panel {
  label: string;
  node: ReactElement;
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
      { label: 'Projects', node: <ProjectsPanel /> },
      { label: 'Dashboard', node: <NarrativeDashboard /> },
      { label: 'Manuscript', node: <ManuscriptEditor /> },
      { label: 'Notes', node: <NotesPanel /> },
      { label: "Dexter's Room", node: <VoiceHud /> },
    ],
  },
  {
    group: 'PLAN',
    // "Chapters" is no longer a permanent PLAN entry (it made no sense in
    // screenplay mode). It moved to STRUCTURE, gated to novel mode — mirroring
    // how the Python core gates mode-specific nav members by writing mode.
    panels: [
      { label: 'Outline', node: <OutlinePanel /> },
      { label: 'Story Grid', node: <StoryGrid /> },
      { label: 'Timeline', node: <TimelinePanel /> },
      { label: 'Canvas Plot', node: <CanvasPlot /> },
      // Series is meaningful only in series mode (the core gates it the same way);
      // outside series mode the seasons/episodes tables are always empty.
      { label: 'Series', node: <SeriesNavigator />, modes: ['series'] },
    ],
  },
  {
    group: 'STRUCTURE',
    panels: [
      { label: 'Structure', node: <StructurePanel /> },
      { label: 'Acts', node: <ActsView /> },
      { label: 'Beats', node: <BeatsView /> },
      // Chapters are a prose-novel structure — shown only in novel mode (they made
      // no sense as a permanent entry in screenplay/GN/stage/series).
      { label: 'Chapters', node: <ChaptersView />, modes: ['novel'] },
      { label: 'Structure Analysis', node: <CoverageAnalysis /> },
      { label: 'Format Studio', node: <FormatStructure /> },
    ],
  },
  {
    group: 'ANALYTICS',
    panels: [
      { label: 'Health', node: <StoryHealthHud /> },
      { label: 'Pacing', node: <PacingInsights /> },
      { label: 'Balance', node: <CharacterBalance /> },
      { label: 'Tags', node: <TagsView /> },
      { label: 'Continuity', node: <ContinuityPanel /> },
      { label: 'Decision Radar', node: <DecisionRadar /> },
      { label: 'Adapt', node: <AdaptView /> },
      { label: 'Review', node: <ReviewDashboard /> },
    ],
  },
  {
    group: 'BIBLE',
    panels: [
      { label: 'PSYKE', node: <PsykeBible /> },
      { label: 'Characters', node: <CharacterLinks /> },
      { label: 'Theme Scenes', node: <ThemeScenes /> },
      { label: 'Graph', node: <KnowledgeGraph /> },
    ],
  },
  {
    group: '',
    panels: [
      { label: 'Plugins', node: <PluginsPanel /> },
      { label: 'Connector', node: <ConnectorPanel /> },
      { label: 'Export', node: <ExportDialog /> },
      { label: 'AI Settings', node: <AiSettingsPanel /> },
      { label: 'Settings', node: <CrossCutting /> },
      { label: 'Help', node: <HelpPanel /> },
    ],
  },
];

const PANELS: Panel[] = PANEL_GROUPS.flatMap((g) => g.panels);

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
  const [bootstrapAttempt, setBootstrapAttempt] = useState(0);
  const [sel, setSel] = useState(PANELS[0]!.label);
  const [pendingScene, setPendingScene] = useState<number | null>(null);
  const [handoffError, setHandoffError] = useState<string | null>(null);
  const { fault: runtimeFault, dismiss: dismissRuntimeFault } = useRuntimeFaultReporter();
  const selRef = useRef(sel);
  selRef.current = sel;
  const panelQueue = useRef<Promise<void>>(Promise.resolve());
  const projectIdRef = useRef(projectId);
  projectIdRef.current = projectId;
  const projectQueue = useRef<Promise<void>>(Promise.resolve());
  const bootstrapRunRef = useRef<{ api: ApiClient; attempt: number } | null>(null);
  const bootstrapRetryTimerRef = useRef<number | null>(null);
  const appMountedRef = useRef(true);

  // Cockpit HUD state: the AI dock (right rail), the shell layout (cockpit vs
  // distraction-free focus), and the ⌘K command palette.
  // These persist across launches so the writer's dock size / tool / appearance stick.
  const [aiOpen, setAiOpen] = useState(() => localStorage.getItem('lf.aiOpen') !== '0');
  const [aiTab, setAiTab] = useState<string>(() => localStorage.getItem('lf.aiTab') || AI_TOOL_KEYS[0] || 'Billy');
  const [aiWidth, setAiWidth] = useState(() => { const v = Number(localStorage.getItem('lf.aiWidth')); return v >= 340 && v <= 900 ? v : 460; });
  const [layout, setLayout] = useState<'cockpit' | 'focus'>('cockpit');
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [ambiance, setAmbiance] = useState<'dark' | 'light' | 'warm'>(() => {
    const v = localStorage.getItem('lf.theme');
    return v === 'dark' || v === 'light' || v === 'warm' ? v : 'dark';
  });
  useEffect(() => { localStorage.setItem('lf.aiOpen', aiOpen ? '1' : '0'); }, [aiOpen]);
  useEffect(() => { localStorage.setItem('lf.aiTab', aiTab); }, [aiTab]);
  useEffect(() => { localStorage.setItem('lf.aiWidth', String(aiWidth)); }, [aiWidth]);
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

  const selectPanel = useCallback((panel: string, opts?: { sceneId?: number }): Promise<boolean> => {
    const task = panelQueue.current.then(async () => {
      if (!PANELS.some((candidate) => candidate.label === panel)) return false;
      if (selRef.current !== panel) {
        try {
          await flushPendingProjectSaves({ commitActiveField: true });
        } catch (error) {
          setHandoffError(
            `Panel switch stopped; the manuscript remains open. ${
              error instanceof Error ? error.message : String(error)
            }`,
          );
          return false;
        }
        setSel(panel);
        selRef.current = panel;
      }
      if (opts?.sceneId != null) setPendingScene(opts.sceneId);
      setHandoffError(null);
      return true;
    });
    panelQueue.current = task.then(() => undefined, () => undefined);
    return task;
  }, []);

  // Cross-panel navigation: any panel can switch panels / open a scene, but no
  // panel unmounts a dirty editor until its save barrier succeeds.
  const navigate = useCallback((panel: string, opts?: { sceneId?: number }) => {
    void selectPanel(panel, opts);
  }, [selectPanel]);

  // Open an AI companion (used by the dock and the palette). Bring the dock into
  // view — and drop out of focus mode so it's actually visible.
  const openAi = useCallback((key: string) => {
    setAiTab(key);
    setAiOpen(true);
    setLayout((l) => (l === 'focus' ? 'cockpit' : l));
  }, []);
  const toggleFocus = useCallback(() => setLayout((l) => (l === 'focus' ? 'cockpit' : 'focus')), []);

  // Mode-aware nav: mode-specific panels (Chapters=novel, Series=series) appear
  // only in their writing mode — mirroring the Python core's per-mode gating.
  const visibleGroups = useMemo(
    () => PANEL_GROUPS
      .map((g) => ({ ...g, panels: g.panels.filter((p) => !p.modes || p.modes.includes(mode)) }))
      .filter((g) => g.panels.length > 0),
    [mode],
  );
  const visiblePanels = useMemo(() => visibleGroups.flatMap((g) => g.panels), [visibleGroups]);

  // If a mode switch hides the active panel, fall back to Manuscript (the core
  // bounces to Dashboard; Manuscript is the writer's home in this shell).
  useEffect(() => {
    if (!visiblePanels.some((p) => p.label === sel)) {
      void selectPanel(visiblePanels.find((p) => p.label === 'Manuscript')?.label ?? visiblePanels[0]?.label ?? 'Projects');
    }
  }, [visiblePanels, sel, selectPanel]);

  // ⌘K / Ctrl+K toggles the command palette anywhere; Escape leaves focus mode
  // (when the palette isn't the one consuming the keystroke).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      } else if (e.key === 'Escape' && layout === 'focus' && !paletteOpen) {
        setLayout('cockpit');
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [layout, paletteOpen]);

  // Everything the palette can do: jump to any section, open any AI companion,
  // toggle focus mode.
  const commands = useMemo<Command[]>(() => [
    ...visiblePanels.map((p) => ({ id: `go-${p.label}`, kind: 'Go', label: p.label, run: () => { void selectPanel(p.label); } })),
    ...AI_TOOL_KEYS.map((k) => ({ id: `ai-${k}`, kind: 'AI', label: k, run: () => openAi(k) })),
    { id: 'focus', kind: 'View', label: layout === 'focus' ? 'Exit focus mode' : 'Enter focus mode', run: toggleFocus },
  ], [layout, openAi, toggleFocus, visiblePanels, selectPanel]);

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
    return bridge.onSaveBeforeClose(() => {
      void flushPendingProjectSaves({ commitActiveField: true }).then(
        () => bridge.sendCloseResult(true),
        (error) => {
          setHandoffError(
            `Close stopped because pending changes could not be saved. ${
              error instanceof Error ? error.message : String(error)
            }`,
          );
          bridge.sendCloseResult(false);
        },
      );
    });
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
    const target = id || undefined;
    const task = projectQueue.current.then(async () => {
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
      setProjectId(target);
      projectIdRef.current = target;
      setPendingScene(null);
      setHandoffError(null);
      return true;
    });
    projectQueue.current = task.then(() => undefined, () => undefined);
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
    const task = projectQueue.current.then(async () => {
      if (!api) return false;
      const activeId = projectIdRef.current;
      if (activeId == null) {
        setMode(nextMode);
        return true;
      }
      setModeBusy(true);
      try {
        await flushPendingProjectSaves({ commitActiveField: true });
        if (projectIdRef.current !== activeId) return false;
        const updated = await prepareProjectHandoff(() =>
          trackProjectWrite(api.updateProject(activeId, { narrative_engine: nextMode })),
        );
        setProjects((current) => current.map((project) =>
          project.id === updated.id ? updated : project,
        ));
        if (projectIdRef.current === activeId) setMode(projectWritingMode(updated));
        setHandoffError(null);
        return true;
      } catch (error) {
        setHandoffError(
          `Writing-mode change stopped. ${error instanceof Error ? error.message : String(error)}`,
        );
        return false;
      } finally {
        setModeBusy(false);
      }
    });
    projectQueue.current = task.then(() => undefined, () => undefined);
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
          setProjectId(created.id);
          projectIdRef.current = created.id;
          setMode(projectWritingMode(created));
        } else if (projectId == null) {
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
    if (!api || busy) return;
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

  // Native menu (electron/menu.ts) → the same handlers the sidebar / palette use.
  useEffect(() => {
    if (!desktop?.onMenuCommand) return;
    return desktop.onMenuCommand((cmd) => {
      if (cmd === 'new-project') void newProject();
      else if (cmd === 'palette') setPaletteOpen((o) => !o);
      else if (cmd === 'focus') toggleFocus();
      else if (cmd === 'ai-dock') setAiOpen((o) => !o);
      else if (cmd.startsWith('nav:')) void selectPanel(cmd.slice(4));
      else if (cmd.startsWith('ai:')) openAi(cmd.slice(3));
      else if (cmd.startsWith('theme:')) {
        const t = cmd.slice(6);
        if (t === 'dark' || t === 'light' || t === 'warm') setAmbiance(t);
      }
    });
  }, [newProject, toggleFocus, openAi, selectPanel]);

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
  const current = PANELS.find((p) => p.label === sel) ?? PANELS[0]!;

  // The sections rail — dropped into the cockpit shell's navSlot (the shell's
  // TopBar already carries the LOGOSFORGE brand, so no duplicate here).
  const rail = (
    <aside className="rail">
      <CoreBadge status={status} />
      <label className="field">
        project mode
        <select value={mode} disabled={modeBusy || busy} onChange={(e) => { void changeProjectMode(e.target.value as WritingMode); }}>
          {WRITING_MODES.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
      </label>
      <label className="field">
        project
        <select value={projectId ?? ''} disabled={busy} onChange={(e) => { void selectProject(Number(e.target.value) || 0); }}>
          {projects.length === 0 && <option value="">—</option>}
          {projects.map((p) => (
            <option key={p.id} value={p.id}>{p.title || `Project ${p.id}`}</option>
          ))}
        </select>
      </label>
      <button type="button"
        onClick={newProject}
        disabled={busy}
        style={{ width: '100%', marginTop: 2, padding: '7px 0', background: 'transparent', border: '1px solid #2b6f8f', color: '#9fd4ec', cursor: busy ? 'default' : 'pointer', fontSize: 11, letterSpacing: '.12em', opacity: busy ? 0.5 : 1 }}
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
              <button type="button" key={p.label} className={sel === p.label ? 'on' : ''} aria-current={sel === p.label ? 'page' : undefined} onClick={() => { void selectPanel(p.label); }}>
                {p.label}
              </button>
            ))}
          </div>
        ))}
      </nav>
    </aside>
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
          layout={layout}
          theme={ambiance}
          showConsole={false}
          bottomSlot={<></>}
          statusCenter={`${current.label.toUpperCase()} · ${(projects.find((p) => p.id === projectId)?.title) ?? 'No project'}`}
          countdown="LIVE"
          sync="100"
          navSlot={rail}
          centerSlot={
            <div className="panel-host">
              <PanelErrorBoundary name={`${current.label} panel`} resetKey={`${projectId ?? 'none'}:${current.label}`}>
                {current.node}
              </PanelErrorBoundary>
            </div>
          }
          rightSlot={
            <AiDock
              open={aiOpen}
              tab={aiTab}
              width={aiWidth}
              onOpenChange={setAiOpen}
              onTabChange={setAiTab}
              onWidthChange={setAiWidth}
            />
          }
          onCommandPalette={() => setPaletteOpen(true)}
          onToggleFocus={toggleFocus}
        />
        <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} commands={commands} />
      </StudioProvider>
      </PanelErrorBoundary>
      {handoffError && (
        <button type="button"
          role="alert"
          onClick={() => setHandoffError(null)}
          title="Dismiss"
          style={{
            position: 'fixed', left: '50%', bottom: 24, zIndex: 1000,
            transform: 'translateX(-50%)', maxWidth: 'min(760px, calc(100% - 40px))',
            padding: '9px 14px', border: '1px solid var(--crimson)',
            background: 'var(--panel)', color: 'var(--strong)', font: 'inherit',
            fontSize: 11, lineHeight: 1.4, cursor: 'pointer', boxShadow: '0 12px 40px rgba(0,0,0,.45)',
          }}
        >
          {handoffError}
        </button>
      )}
      <RuntimeFaultBanner fault={runtimeFault} onDismiss={dismissRuntimeFault} bottom={handoffError ? 78 : 24} />
    </div>
  );
}
