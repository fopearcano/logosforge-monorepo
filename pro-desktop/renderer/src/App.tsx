import { useCallback, useEffect, useMemo, useState, type ReactElement } from 'react';
import {
  StudioProvider,
  createHttpApiClient,
  type ApiClient,
  type PlatformAdapter,
  ManuscriptEditor,
  NotesPanel,
  StoryGrid,
  StructurePanel,
  OutlinePanel,
  PsykeBible,
  CharacterLinks,
  ThemeScenes,
  KnowledgeGraph,
  CanvasPlot,
  TimelinePanel,
  NarrativeDashboard,
  ContinuityPanel,
  DecisionRadar,
  AssistantDock,
  Logos,
  QuantumOutliner,
  CounterpartPanel,
  ExtractionReview,
  ExportDialog,
  CrossCutting,
} from '@logosforge/pro-shared-ui';
import { WRITING_MODES, type WritingMode, type ProjectDTO } from '@logosforge/ui-contracts';
import { desktop, platform, type CoreStatus } from './platform';

interface Panel {
  label: string;
  node: ReactElement;
}

interface PanelGroup {
  group: string;
  panels: Panel[];
}

const PANEL_GROUPS: PanelGroup[] = [
  {
    group: 'WRITE',
    panels: [
      { label: 'Manuscript', node: <ManuscriptEditor /> },
      { label: 'Story Grid', node: <StoryGrid /> },
      { label: 'Outline', node: <OutlinePanel /> },
      { label: 'Structure', node: <StructurePanel /> },
      { label: 'Notes', node: <NotesPanel /> },
    ],
  },
  {
    group: 'BIBLE',
    panels: [
      { label: 'PSYKE Bible', node: <PsykeBible /> },
      { label: 'Character Links', node: <CharacterLinks /> },
      { label: 'Themes', node: <ThemeScenes /> },
      { label: 'Knowledge Graph', node: <KnowledgeGraph /> },
    ],
  },
  {
    group: 'CANVASES',
    panels: [
      { label: 'Timeline', node: <TimelinePanel /> },
      { label: 'Canvas Plot', node: <CanvasPlot /> },
    ],
  },
  {
    group: 'INTELLIGENCE',
    panels: [
      { label: 'Narrative Dashboard', node: <NarrativeDashboard /> },
      { label: 'Continuity', node: <ContinuityPanel /> },
      { label: 'Decision Radar', node: <DecisionRadar /> },
    ],
  },
  {
    group: 'AI',
    panels: [
      { label: 'Billy', node: <AssistantDock /> },
      { label: 'Logos', node: <Logos /> },
      { label: 'Quantum Outliner', node: <QuantumOutliner /> },
      { label: 'Counterpart', node: <CounterpartPanel /> },
      { label: 'Extraction', node: <ExtractionReview /> },
    ],
  },
  {
    group: 'PROJECT',
    panels: [
      { label: 'Export', node: <ExportDialog /> },
      { label: 'Launchpad & Settings', node: <CrossCutting /> },
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

  // Cross-panel navigation: any panel can switch panels / open a scene.
  const navigate = useCallback((panel: string, opts?: { sceneId?: number }) => {
    if (PANELS.some((p) => p.label === panel)) setSel(panel);
    if (opts?.sceneId != null) setPendingScene(opts.sceneId);
  }, []);

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

  return (
    <div className="app">
      <aside className="rail">
        <div className="brand">
          LOGOSFORGE <span>STUDIO</span>
        </div>
        <CoreBadge status={status} />
        <label className="field">
          writing mode
          <select value={mode} onChange={(e) => setMode(e.target.value as WritingMode)}>
            {WRITING_MODES.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          project
          <select
            value={projectId ?? ''}
            onChange={(e) => setProjectId(Number(e.target.value) || undefined)}
          >
            {projects.length === 0 && <option value="">—</option>}
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.title || `Project ${p.id}`}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={newProject}
          disabled={busy}
          style={{
            width: '100%',
            marginTop: 2,
            padding: '7px 0',
            background: 'transparent',
            border: '1px solid #2b6f8f',
            color: '#9fd4ec',
            cursor: busy ? 'default' : 'pointer',
            fontSize: 11,
            letterSpacing: '.12em',
            opacity: busy ? 0.5 : 1,
          }}
        >
          ＋ NEW PROJECT
        </button>
        <nav>
          {PANEL_GROUPS.map((g) => (
            <div key={g.group} className="nav-group">
              <div className="nav-group-label">{g.group}</div>
              {g.panels.map((p) => (
                <button key={p.label} className={sel === p.label ? 'on' : ''} onClick={() => setSel(p.label)}>
                  {p.label}
                </button>
              ))}
            </div>
          ))}
        </nav>
      </aside>
      <main className="stage">
        <StudioProvider
          services={services}
          writingMode={mode}
          projectId={projectId}
          nav={{ navigate, manuscriptTargetSceneId: pendingScene, clearManuscriptTarget: () => setPendingScene(null) }}
        >
          <div className="panel-host">{current.node}</div>
        </StudioProvider>
      </main>
    </div>
  );
}
