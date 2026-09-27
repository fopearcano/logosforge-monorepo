import { useMemo, useState } from "react";
import {
  DockWorkspace,
  StudioProvider,
  WorkspaceNavigator,
  WorkspaceShell,
  activateDockPanel,
  closePanel,
  createDefaultWorkspaceLayout,
  movePanel,
  resizeDock,
  resizeNavigator,
  setNavigatorCollapsed,
  toggleDockCollapsed,
  toggleWorkspacePreset,
  type ApiClient,
  type PlatformAdapter,
  type WorkspaceDockRegion,
  type WorkspacePanelDefinition,
} from "../src";
import { createMockApiClient } from "./mockApi";

const api: ApiClient = createMockApiClient();
const platform: PlatformAdapter = {
  isDesktop: false,
  openFile: async () => ({ canceled: true }),
  saveFile: async () => ({ canceled: true }),
  openExternal: async () => undefined,
};

function PreviewPanel({ title, color, editable = false }: { title: string; color: string; editable?: boolean }) {
  return (
    <div style={{ height: "100%", minHeight: 0, padding: 18, background: `linear-gradient(145deg,${color}18,transparent 60%)` }}>
      <div style={{ color, fontSize: 11, letterSpacing: ".18em", marginBottom: 14 }}>{title.toUpperCase()}</div>
      {editable ? (
        <textarea
          aria-label="State-preservation test draft"
          defaultValue="Type here, then move this tab: the draft must remain mounted."
          style={{ width: "100%", minHeight: 180, resize: "vertical", background: "var(--panel)", color: "var(--txt)", border: "1px solid var(--line2)", padding: 12 }}
        />
      ) : (
        <div style={{ color: "var(--txt2)", lineHeight: 1.7 }}>
          Live dock preview for resize, collapse, tab activation, keyboard movement, and Focus projection.
        </div>
      )}
    </div>
  );
}

export function WorkspaceDockHarness() {
  const [layout, setLayout] = useState(createDefaultWorkspaceLayout);
  const panels = useMemo<WorkspacePanelDefinition[]>(() => [
    { id: "manuscript", label: "Manuscript", closable: false, movable: false, node: <PreviewPanel title="Manuscript" color="#e8443a" editable /> },
    { id: "dashboard", label: "Dashboard", node: <PreviewPanel title="Dashboard" color="#4cc2ff" editable /> },
    { id: "ai-companions", label: "AI Companions", node: <PreviewPanel title="AI Companions" color="#b07cff" /> },
    { id: "decision-radar", label: "Decision Radar", node: <PreviewPanel title="Decision Radar" color="#ffb454" /> },
    { id: "outline", label: "Outline", node: <PreviewPanel title="Outline" color="#62d99a" /> },
    { id: "health", label: "Health", node: <PreviewPanel title="Story Health" color="#f481a8" /> },
  ], []);

  const move = (panelId: string, region: WorkspaceDockRegion, index: number) => {
    setLayout((current) => movePanel(current, panelId, { kind: "dock", region, index }));
  };

  const navigator = (
    <WorkspaceNavigator
      collapsed={layout.navigator.collapsed}
      widthPx={layout.navigator.widthPx}
      onCollapsedChange={(collapsed) => setLayout((current) => setNavigatorCollapsed(current, collapsed))}
      onWidthChange={(width) => setLayout((current) => resizeNavigator(current, width))}
    >
      <aside style={{ width: "100%", padding: 14, overflow: "auto" }}>
        <div style={{ color: "var(--strong)", fontSize: 13, letterSpacing: ".12em", marginBottom: 16 }}>WORKSPACE QA</div>
        <button type="button" onClick={() => setLayout((current) => toggleWorkspacePreset(current))} style={{ width: "100%", padding: 8 }}>
          {layout.preset === "focus" ? "Exit Focus" : "Enter Focus"}
        </button>
        <p style={{ color: "var(--txt3)", fontSize: 10, lineHeight: 1.6 }}>Drag resize grips or focus them and use arrow keys. Move tabs with ↦ or drag them to another header.</p>
      </aside>
    </WorkspaceNavigator>
  );

  return (
    <StudioProvider services={{ api, platform }} writingMode="novel" projectId={1}>
      <div style={{ width: "100vw", height: "100vh" }}>
        <WorkspaceShell
          writingMode="novel"
          layout={layout.preset}
          theme="dark"
          showConsole={false}
          navSlot={navigator}
          rightSlot={<></>}
          bottomSlot={<></>}
          statusCenter={`${layout.focused?.panelId ?? "workspace"} · DOCK QA`}
          onToggleFocus={() => setLayout((current) => toggleWorkspacePreset(current))}
          centerSlot={
            <DockWorkspace
              layout={layout}
              panels={panels}
              onActivate={(panelId, region) => setLayout((current) => activateDockPanel(current, region, panelId))}
              onMove={move}
              onClose={(panelId) => setLayout((current) => closePanel(current, panelId))}
              onToggleDock={(region) => setLayout((current) => toggleDockCollapsed(current, region))}
              onResizeDock={(region, size) => setLayout((current) => resizeDock(current, region, size))}
              onReset={() => setLayout(createDefaultWorkspaceLayout())}
            />
          }
        />
      </div>
    </StudioProvider>
  );
}
