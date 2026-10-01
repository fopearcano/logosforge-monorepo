import { useCallback, useMemo, useRef, useState, type ReactElement } from "react";
import {
  StudioProvider,
  createHttpApiClient,
  flushPendingProjectSaves,
  resetProjectSaveStatus,
  type ApiClient,
  type PlatformAdapter,
  // 01 shell
  WorkspaceShell,
  // 02 manuscript
  ManuscriptEditor, StoryGrid, OutlinePanel, StructurePanel, NotesPanel, CommentsPanel,
  // 04 psyke
  PsykeBible, RelationGraph, PsykeInspector, ControllingIdeaCompass, PsykeConsoleInbox, CharacterLinks, ThemeScenes,
  // 06 project os
  DiffConfirmModal, NarrativeDashboard, DecisionRadar, GuidedWorkflowStepper, ContinuityPanel,
  // 03 spatial
  KnowledgeGraph, CanvasPlot, TimelinePanel,
  // 05 ai & quantum
  QuantumOutliner, AssistantDock, CounterpartPanel, Logos, ExtractionReview, FormatStructure,
  // 07 formats/stages/voice/export
  ModeReskin, StagesPanel, VoiceHud, PageCanvas, ExportDialog, ModeReviewDashboard, CrossCutting,
} from "../src/index";
import { WRITING_MODES, type WritingMode } from "@logosforge/ui-contracts";
import { createMockApiClient } from "./mockApi";
import { previewWorkspaceStatus } from "./previewStatus";
import { IntegratedWorkspaceHarness } from "./IntegratedWorkspaceHarness";

// Two ApiClient implementations the preview switches between: a static mock and a
// live HTTP client that hits the running logosforge core via the /api Vite proxy.
const mockApi = createMockApiClient();
const liveApi = createHttpApiClient(); // baseUrl "" → Vite proxies /api → localhost:8765

type PreviewDataSource = "mock" | "live";
type PreviewIdentityGuard = () => Promise<void>;
type PreviewItemContext = {
  source: PreviewDataSource;
  identitySwitching: boolean;
  registerIdentityGuard: (guard: PreviewIdentityGuard | null) => void;
};
type ItemNode = ReactElement | ((context: PreviewItemContext) => ReactElement);
type Item = [label: string, node: ItemNode, w: number, h: number];
type Group = { name: string; items: Item[] };

function WorkspaceShellDesignFixture() {
  return (
    <div
      data-preview-fixture="workspace-shell-design"
      style={{ position: "relative", width: "100%", height: "100%" }}
    >
      <div style={{ position: "absolute", top: 50, right: 14, zIndex: 1000, border: "1px solid #ffb454", background: "#11151e", color: "#ffb454", padding: "5px 8px", fontSize: 9, letterSpacing: ".12em", pointerEvents: "none" }}>
        SYNTHETIC DESIGN FIXTURE
      </div>
      <WorkspaceShell runtimeStatus={previewWorkspaceStatus} coreState="connected" />
    </div>
  );
}

const GROUPS: Group[] = [
  { name: "01 · Workspace Shell", items: [
    ["Workspace Shell — Integrated", ({ source, identitySwitching, registerIdentityGuard }) => (
      <IntegratedWorkspaceHarness
        source={source}
        externalTransitioning={identitySwitching}
        registerIdentityGuard={registerIdentityGuard}
      />
    ), 1600, 900],
    ["Workspace Shell — Design Fixture", <WorkspaceShellDesignFixture />, 1600, 900],
  ] },
  { name: "02 · Manuscript & Structure", items: [
    ["Manuscript Editor", <ManuscriptEditor />, 1520, 900],
    ["Story Grid", <StoryGrid />, 1280, 600],
    ["Outline Panel", <OutlinePanel />, 600, 880],
    ["Structure Panel", <StructurePanel />, 600, 880],
    ["Notes Panel", <NotesPanel />, 1280, 440],
    ["Comments Panel", <CommentsPanel />, 1280, 700],
  ] },
  { name: "03 · Spatial Canvases", items: [
    ["Knowledge Graph", <KnowledgeGraph />, 1760, 980],
    ["Canvas Plot", <CanvasPlot />, 1160, 980],
    ["Plot-Lane Timeline", <TimelinePanel />, 1500, 540],
  ] },
  { name: "04 · PSYKE Story Bible", items: [
    ["PSYKE Bible", <PsykeBible />, 1500, 880],
    ["Relation Graph", <RelationGraph />, 1240, 880],
    ["Temporal Scrubber + Inspector", <PsykeInspector />, 1500, 380],
    ["Controlling-Idea Compass", <ControllingIdeaCompass />, 600, 540],
    ["PSYKE Console + Inbox", <PsykeConsoleInbox />, 560, 540],
    ["Character Links", <CharacterLinks />, 1200, 720],
    ["Theme Scenes", <ThemeScenes />, 1200, 720],
  ] },
  { name: "05 · AI & Quantum", items: [
    ["Quantum Outliner", <QuantumOutliner />, 1800, 1020],
    ["Billy Assistant", <AssistantDock />, 700, 1020],
    ["Counterpart", <CounterpartPanel />, 1230, 620],
    ["Logos", <Logos />, 1280, 620],
    ["Extraction Review", <ExtractionReview />, 1230, 760],
    ["Format Structure", <FormatStructure />, 1230, 760],
  ] },
  { name: "06 · Project OS", items: [
    ["Diff / Impact Confirm", <DiffConfirmModal />, 1500, 900],
    ["Narrative Dashboard", <NarrativeDashboard />, 1400, 900],
    ["Decision Radar", <DecisionRadar />, 560, 840],
    ["Guided Workflow Stepper", <GuidedWorkflowStepper />, 900, 840],
    ["Continuity Panel", <ContinuityPanel />, 1400, 840],
  ] },
  { name: "07 · Formats / Stages / Voice / Export", items: [
    ["Mode Re-skin (5 modes)", <ModeReskin />, 2000, 680],
    ["Stages", <StagesPanel />, 1180, 540],
    ["Dexter's Room Voice", <VoiceHud />, 1140, 540],
    ["GN Page Canvas", <PageCanvas />, 1180, 660],
    ["Export Studio", <ExportDialog />, 1140, 660],
    ["Mode Review + Pipeline", <ModeReviewDashboard />, 1180, 620],
    ["Cross-cutting", <CrossCutting />, 1140, 620],
  ] },
];

const ALL = GROUPS.flatMap((g) => g.items);

// Browser PlatformAdapter for the preview harness: saveFile triggers a real
// download (text via Blob; binary via base64 → bytes → Blob), so Export Studio's
// SAVE works in `npm run dev`. The other capabilities are best-effort no-ops.
const previewPlatform: PlatformAdapter = {
  isDesktop: false,
  openFile: async (options) => new Promise((resolve) => {
    const picker = document.createElement("input");
    picker.type = "file";
    picker.accept = (options?.filters ?? [])
      .flatMap((filter) => filter.extensions)
      .map((extension) => `.${extension.replace(/^\./, "")}`)
      .join(",");
    picker.style.display = "none";
    document.body.appendChild(picker);
    let settled = false;
    const finish = (result: Awaited<ReturnType<PlatformAdapter["openFile"]>>) => {
      if (settled) return;
      settled = true;
      picker.remove();
      resolve(result);
    };
    picker.addEventListener("cancel", () => finish({ canceled: true }), { once: true });
    picker.addEventListener("change", () => {
      const file = picker.files?.[0];
      if (!file) { finish({ canceled: true }); return; }
      void file.arrayBuffer().then((buffer) => {
        const bytes = new Uint8Array(buffer);
        let binary = "";
        for (let offset = 0; offset < bytes.length; offset += 0x8000) {
          binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
        }
        finish({
          canceled: false,
          path: file.name,
          content: new TextDecoder().decode(bytes),
          contentBase64: btoa(binary),
        });
      }, () => finish({ canceled: true }));
    }, { once: true });
    try { picker.click(); } catch { finish({ canceled: true }); }
  }),
  openExternal: async (target) => { window.open(target, "_blank", "noopener"); },
  saveFile: async ({ suggestedName, content, contentBase64, mimeType }) => {
    let blob: Blob;
    if (contentBase64 != null) {
      const bin = atob(contentBase64);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      blob = new Blob([bytes], { type: mimeType || "application/octet-stream" });
    } else {
      blob = new Blob([content ?? ""], { type: mimeType || "text/plain" });
    }
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = suggestedName ?? "export";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    return { canceled: false };
  },
};

export function App() {
  const [sel, setSel] = useState("Workspace Shell — Integrated");
  const [mode, setMode] = useState<WritingMode>("screenplay");
  const [source, setSource] = useState<PreviewDataSource>("mock");
  const [projectId, setProjectId] = useState(1);
  const [identityError, setIdentityError] = useState<string | null>(null);
  const [identitySwitching, setIdentitySwitching] = useState(false);
  const identitySwitchingRef = useRef(false);
  const identityGuardRef = useRef<PreviewIdentityGuard | null>(null);
  const registerIdentityGuard = useCallback((guard: PreviewIdentityGuard | null) => {
    identityGuardRef.current = guard;
  }, []);
  const services = useMemo(() => ({ api: source === "live" ? liveApi : mockApi, platform: previewPlatform }), [source]);
  const item = ALL.find((i) => i[0] === sel) ?? ALL[0]!;
  const [label, itemNode, w, h] = item;
  const integratedWorkspace = label === "Workspace Shell — Integrated";
  const node = typeof itemNode === "function"
    ? itemNode({ source, identitySwitching, registerIdentityGuard })
    : itemNode;
  const changeIdentity = useCallback(async (change: () => void) => {
    if (identitySwitchingRef.current) return;
    identitySwitchingRef.current = true;
    setIdentitySwitching(true);
    try {
      // The integrated host has its own serialized queue (project opens, panel
      // mutations). Drain it before the global editor/layout barrier so an old
      // async handoff cannot publish state after the new source/screen mounts.
      await identityGuardRef.current?.();
      await flushPendingProjectSaves({ commitActiveField: true });
      resetProjectSaveStatus();
      change();
      setIdentityError(null);
    } catch (error) {
      setIdentityError(`Preview switch stopped because pending edits could not be saved. ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      identitySwitchingRef.current = false;
      setIdentitySwitching(false);
    }
  }, []);

  return (
    <div style={{ display: "flex", height: "100vh", background: "#000", color: "#e4e8ef", fontFamily: "'JetBrains Mono', monospace", fontSize: 12 }}>
      <div style={{ width: 252, flex: "none", borderRight: "1px solid #1c2430", overflowY: "auto", background: "#06080c" }}>
        <div style={{ padding: "12px 14px", borderBottom: "1px solid #1c2430" }}>
          <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: ".12em", color: "#fff" }}>LOGOSFORGE STUDIO</div>
          <div style={{ fontSize: 8, letterSpacing: ".3em", color: "#e8443a", marginTop: 3 }}>UI PREVIEW · {ALL.length} PANELS</div>
          <div style={{ marginTop: 11, fontSize: 9, color: "#8b95a5" }}>
            {integratedWorkspace ? "writing mode:" : "writing mode (drives --accent re-skin):"}
          </div>
          {integratedWorkspace ? (
            <div style={{ marginTop: 4, border: "1px solid #1c2430", padding: "5px 6px", color: "#8b95a5", fontSize: 9, lineHeight: 1.4 }}>
              Core-owned by the project selected inside the workspace.
            </div>
          ) : (
            <select value={mode} onChange={(e) => setMode(e.target.value as WritingMode)} style={{ width: "100%", marginTop: 4, background: "#11151e", color: "#e4e8ef", border: "1px solid #1c2430", fontSize: 11, padding: "4px 6px" }}>
              {WRITING_MODES.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          )}
          <div style={{ marginTop: 9, fontSize: 9, color: "#8b95a5" }}>data source (ApiClient):</div>
          <select value={source} disabled={identitySwitching} onChange={(e) => { const next = e.target.value as PreviewDataSource; void changeIdentity(() => setSource(next)); }} style={{ width: "100%", marginTop: 4, background: "#11151e", color: "#e4e8ef", border: "1px solid #1c2430", fontSize: 11, padding: "4px 6px" }}>
            <option value="mock">mock (sample data)</option>
            <option value="live">live core (:8765)</option>
          </select>
          {!integratedWorkspace && (
            <>
              <div style={{ marginTop: 9, fontSize: 9, color: "#8b95a5" }}>project id:</div>
              <input type="number" min={1} value={projectId} disabled={identitySwitching} onChange={(e) => { const next = Number(e.target.value) || 1; void changeIdentity(() => setProjectId(next)); }} style={{ width: "100%", marginTop: 4, background: "#11151e", color: "#e4e8ef", border: "1px solid #1c2430", fontSize: 11, padding: "4px 6px" }} />
            </>
          )}
          {identityError && <div role="alert" style={{ marginTop: 8, color: "#ffb454", fontSize: 9, lineHeight: 1.5 }}>{identityError}</div>}
        </div>
        {GROUPS.map((g) => (
          <div key={g.name} style={{ padding: "8px 0" }}>
            <div style={{ padding: "5px 14px", fontSize: 8, letterSpacing: ".18em", color: "#525c6b" }}>{g.name}</div>
            {g.items.map(([l]) => (
              <button
                key={l}
                type="button"
                data-panel={l}
                disabled={identitySwitching}
                onClick={() => {
                  if (sel !== l) void changeIdentity(() => setSel(l));
                }}
                style={{ display: "block", width: "100%", padding: "6px 14px", border: "none", borderLeft: sel === l ? "2px solid #4cc2ff" : "2px solid transparent", font: "inherit", fontSize: 11, textAlign: "left", cursor: identitySwitching ? "default" : "pointer", color: sel === l ? "#4cc2ff" : "#8b95a5", background: sel === l ? "rgba(76,194,255,.08)" : "transparent", opacity: identitySwitching ? 0.6 : 1 }}
              >
                {l}
              </button>
            ))}
          </div>
        ))}
      </div>
      <div style={{ flex: 1, overflow: "auto", padding: 24 }}>
        <div style={{ marginBottom: 10, fontSize: 11, color: "#8b95a5" }}>{label}<span style={{ color: "#525c6b" }}> · {w}×{h}</span></div>
        <StudioProvider key={`${source}:${projectId}`} services={services} writingMode={mode} projectId={projectId}>
          <div style={{ width: w, height: h, boxShadow: "0 0 0 1px #1c2430" }}>{node}</div>
        </StudioProvider>
      </div>
    </div>
  );
}
