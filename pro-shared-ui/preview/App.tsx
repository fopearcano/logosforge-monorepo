import { useMemo, useState, type ReactElement } from "react";
import {
  StudioProvider,
  createHttpApiClient,
  type ApiClient,
  type PlatformAdapter,
  // 01 shell
  WorkspaceShell,
  // 02 manuscript
  ManuscriptEditor, StoryGrid, OutlinePanel, StructurePanel, NotesPanel,
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

// Two ApiClient implementations the preview switches between: a static mock and a
// live HTTP client that hits the running logosforge core via the /api Vite proxy.
const mockApi = createMockApiClient();
const liveApi = createHttpApiClient(); // baseUrl "" → Vite proxies /api → localhost:8765

type Item = [label: string, node: ReactElement, w: number, h: number];
type Group = { name: string; items: Item[] };

const GROUPS: Group[] = [
  { name: "01 · Workspace Shell", items: [
    ["Workspace Shell — Cockpit", <WorkspaceShell />, 1600, 900],
  ] },
  { name: "02 · Manuscript & Structure", items: [
    ["Manuscript Editor", <ManuscriptEditor />, 1520, 900],
    ["Story Grid", <StoryGrid />, 1280, 600],
    ["Outline Panel", <OutlinePanel />, 600, 880],
    ["Structure Panel", <StructurePanel />, 600, 880],
    ["Notes Panel", <NotesPanel />, 1280, 440],
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
  openFile: async () => ({ canceled: true }),
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
  const [sel, setSel] = useState("Workspace Shell — Cockpit");
  const [mode, setMode] = useState<WritingMode>("screenplay");
  const [source, setSource] = useState<"mock" | "live">("mock");
  const [projectId, setProjectId] = useState(1);
  const services = useMemo(() => ({ api: source === "live" ? liveApi : mockApi, platform: previewPlatform }), [source]);
  const item = ALL.find((i) => i[0] === sel) ?? ALL[0]!;
  const [label, node, w, h] = item;

  return (
    <div style={{ display: "flex", height: "100vh", background: "#000", color: "#e4e8ef", fontFamily: "'JetBrains Mono', monospace", fontSize: 12 }}>
      <div style={{ width: 252, flex: "none", borderRight: "1px solid #1c2430", overflowY: "auto", background: "#06080c" }}>
        <div style={{ padding: "12px 14px", borderBottom: "1px solid #1c2430" }}>
          <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: ".12em", color: "#fff" }}>LOGOSFORGE STUDIO</div>
          <div style={{ fontSize: 8, letterSpacing: ".3em", color: "#e8443a", marginTop: 3 }}>UI PREVIEW · {ALL.length} PANELS</div>
          <div style={{ marginTop: 11, fontSize: 9, color: "#8b95a5" }}>writing mode (drives --accent re-skin):</div>
          <select value={mode} onChange={(e) => setMode(e.target.value as WritingMode)} style={{ width: "100%", marginTop: 4, background: "#11151e", color: "#e4e8ef", border: "1px solid #1c2430", fontSize: 11, padding: "4px 6px" }}>
            {WRITING_MODES.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
          <div style={{ marginTop: 9, fontSize: 9, color: "#8b95a5" }}>data source (ApiClient):</div>
          <select value={source} onChange={(e) => setSource(e.target.value as "mock" | "live")} style={{ width: "100%", marginTop: 4, background: "#11151e", color: "#e4e8ef", border: "1px solid #1c2430", fontSize: 11, padding: "4px 6px" }}>
            <option value="mock">mock (sample data)</option>
            <option value="live">live core (:8765)</option>
          </select>
          <div style={{ marginTop: 9, fontSize: 9, color: "#8b95a5" }}>project id:</div>
          <input type="number" min={1} value={projectId} onChange={(e) => setProjectId(Number(e.target.value) || 1)} style={{ width: "100%", marginTop: 4, background: "#11151e", color: "#e4e8ef", border: "1px solid #1c2430", fontSize: 11, padding: "4px 6px" }} />
        </div>
        {GROUPS.map((g) => (
          <div key={g.name} style={{ padding: "8px 0" }}>
            <div style={{ padding: "5px 14px", fontSize: 8, letterSpacing: ".18em", color: "#525c6b" }}>{g.name}</div>
            {g.items.map(([l]) => (
              <div key={l} data-panel={l} onClick={() => setSel(l)} style={{ padding: "6px 14px", fontSize: 11, cursor: "pointer", color: sel === l ? "#4cc2ff" : "#8b95a5", background: sel === l ? "rgba(76,194,255,.08)" : undefined, borderLeft: sel === l ? "2px solid #4cc2ff" : "2px solid transparent" }}>{l}</div>
            ))}
          </div>
        ))}
      </div>
      <div style={{ flex: 1, overflow: "auto", padding: 24 }}>
        <div style={{ marginBottom: 10, fontSize: 11, color: "#8b95a5" }}>{label}<span style={{ color: "#525c6b" }}> · {w}×{h}</span></div>
        <StudioProvider services={services} writingMode={mode} projectId={projectId}>
          <div style={{ width: w, height: h, boxShadow: "0 0 0 1px #1c2430" }}>{node}</div>
        </StudioProvider>
      </div>
    </div>
  );
}
