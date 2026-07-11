import { useCallback, useEffect, useMemo, useState, type ReactElement } from 'react';
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
  const [baseUrl, setBaseUrl] = useState<string | null>(null);
  const [projectId, setProjectId] = useState<number | undefined>(undefined);
  const [mode, setMode] = useState<WritingMode>('screenplay');
  const [sel, setSel] = useState(PANELS[0]!.label);
  const [pendingScene, setPendingScene] = useState<number | null>(null);

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

  // Cross-panel navigation: any panel can switch panels / open a scene.
  const navigate = useCallback((panel: string, opts?: { sceneId?: number }) => {
    if (PANELS.some((p) => p.label === panel)) setSel(panel);
    if (opts?.sceneId != null) setPendingScene(opts.sceneId);
  }, []);

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
      setSel(visiblePanels.find((p) => p.label === 'Manuscript')?.label ?? visiblePanels[0]?.label ?? 'Projects');
    }
  }, [visiblePanels, sel]);

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
    ...visiblePanels.map((p) => ({ id: `go-${p.label}`, kind: 'Go', label: p.label, run: () => setSel(p.label) })),
    ...AI_TOOL_KEYS.map((k) => ({ id: `ai-${k}`, kind: 'AI', label: k, run: () => openAi(k) })),
    { id: 'focus', kind: 'View', label: layout === 'focus' ? 'Exit focus mode' : 'Enter focus mode', run: toggleFocus },
  ], [layout, openAi, toggleFocus, visiblePanels]);

  useEffect(() => {
    if (!desktop) return;
    desktop.coreBaseUrl().then(setBaseUrl).catch(() => {});
    desktop.getCoreStatus().then(setStatus).catch(() => {});
    return desktop.onCoreStatus(setStatus);
  }, []);

  const api = useMemo<ApiClient | null>(() => (baseUrl != null ? createHttpApiClient(baseUrl) : null), [baseUrl]);

  // Project list + selection. On connect, load the projects; if there are none,
  // create a starter one so a fresh install can write immediately (otherwise
  // every panel shows an empty "open a project" state with no way to make one).
  const [projects, setProjects] = useState<ProjectDTO[]>([]);
  const [busy, setBusy] = useState(false);

  const refreshProjects = useCallback(async (): Promise<ProjectDTO[]> => {
    if (!api) return [];
    const ps = await api.listProjects().catch(() => [] as ProjectDTO[]);
    setProjects(ps);
    return ps;
  }, [api]);

  useEffect(() => {
    if (!api || status.state !== 'connected' || busy || projects.length > 0) return;
    setBusy(true);
    refreshProjects()
      .then(async (ps) => {
        if (ps.length === 0) {
          const created = await api.createProject({ title: 'Untitled Project', default_writing_format: mode });
          setProjects([created]);
          setProjectId(created.id);
        } else if (projectId == null) {
          setProjectId(ps[0]!.id);
        }
      })
      .catch(() => {})
      .finally(() => setBusy(false));
  }, [api, status.state, busy, projects.length, projectId, mode, refreshProjects]);

  const newProject = useCallback(async () => {
    if (!api || busy) return;
    setBusy(true);
    try {
      const created = await api.createProject({ title: 'Untitled Project', default_writing_format: mode });
      await refreshProjects();
      setProjectId(created.id);
    } catch {
      /* keep current selection on failure */
    } finally {
      setBusy(false);
    }
  }, [api, busy, mode, refreshProjects]);

  // Native menu (electron/menu.ts) → the same handlers the sidebar / palette use.
  useEffect(() => {
    if (!desktop?.onMenuCommand) return;
    return desktop.onMenuCommand((cmd) => {
      if (cmd === 'new-project') void newProject();
      else if (cmd === 'palette') setPaletteOpen((o) => !o);
      else if (cmd === 'focus') toggleFocus();
      else if (cmd === 'ai-dock') setAiOpen((o) => !o);
      else if (cmd.startsWith('nav:')) setSel(cmd.slice(4));
      else if (cmd.startsWith('ai:')) openAi(cmd.slice(3));
      else if (cmd.startsWith('theme:')) {
        const t = cmd.slice(6);
        if (t === 'dark' || t === 'light' || t === 'warm') setAmbiance(t);
      }
    });
  }, [newProject, toggleFocus, openAi]);

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

  const services = { api, platform: platform as PlatformAdapter };
  const current = PANELS.find((p) => p.label === sel) ?? PANELS[0]!;

  // The sections rail — dropped into the cockpit shell's navSlot (the shell's
  // TopBar already carries the LOGOSFORGE brand, so no duplicate here).
  const rail = (
    <aside className="rail">
      <CoreBadge status={status} />
      <label className="field">
        writing mode
        <select value={mode} onChange={(e) => setMode(e.target.value as WritingMode)}>
          {WRITING_MODES.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
      </label>
      <label className="field">
        project
        <select value={projectId ?? ''} onChange={(e) => setProjectId(Number(e.target.value) || undefined)}>
          {projects.length === 0 && <option value="">—</option>}
          {projects.map((p) => (
            <option key={p.id} value={p.id}>{p.title || `Project ${p.id}`}</option>
          ))}
        </select>
      </label>
      <button
        type="button"
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
              <button key={p.label} className={sel === p.label ? 'on' : ''} onClick={() => setSel(p.label)}>
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
      <StudioProvider
        services={services}
        writingMode={mode}
        projectId={projectId}
        nav={{
          navigate,
          manuscriptTargetSceneId: pendingScene,
          clearManuscriptTarget: () => setPendingScene(null),
          selectProject: (id: number) => setProjectId(id || undefined),
          refreshProjects: () => { void refreshProjects(); },
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
          centerSlot={<div className="panel-host">{current.node}</div>}
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
    </div>
  );
}
