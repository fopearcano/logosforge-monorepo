import { useEffect, useState } from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import {
  DockWorkspace,
  projectFloatingBounds,
  type DockWorkspaceProps,
  type WorkspacePanelDefinition,
} from "../src/components/shell/DockWorkspace";
import {
  activateDockPanel,
  closePanel,
  createDefaultWorkspaceLayout,
  focusPanel,
  moveFloatingPanel,
  placePanel,
  resizeFloatingPanel,
  setFloatingPanelMinimized,
  setWorkspacePreset,
  type WorkspaceLayout,
} from "../src/workspace/layoutModel";

let assertions = 0;
function check(condition: unknown, message: string): asserts condition {
  assertions += 1;
  if (!condition) throw new Error(message);
}

// Pointer cleanup is intentionally DOM-facing, while this renderer test only
// needs the body style sink used by effect cleanup.
(globalThis as unknown as { document: { body: { style: Record<string, string> } } }).document = {
  body: { style: {} },
};

let mounts = 0;
let unmounts = 0;
let nextToken = 0;
function StatefulProbe() {
  const [token] = useState(() => `probe-${++nextToken}`);
  useEffect(() => {
    mounts += 1;
    return () => { unmounts += 1; };
  }, []);
  return <input aria-label="Stateful draft" data-probe-token={token} defaultValue="unsaved draft" />;
}

const panel: WorkspacePanelDefinition = {
  id: "dashboard",
  label: "Dashboard",
  node: <StatefulProbe />,
};
const staticProps: Omit<DockWorkspaceProps, "layout" | "panels"> = {
  onActivate: () => true,
  onMove: () => true,
  onFloat: () => true,
  onClose: () => true,
  onToggleDock: () => true,
  onResizeDock: () => undefined,
  onMoveFloating: () => undefined,
  onResizeFloating: () => undefined,
  onMinimizeFloating: () => true,
  onFocusFloating: () => undefined,
  onReset: () => true,
};

function renderWorkspace(layout: WorkspaceLayout, panels: readonly WorkspacePanelDefinition[]) {
  return <DockWorkspace {...staticProps} layout={layout} panels={panels} />;
}

const projectedOffscreen = projectFloatingBounds(
  { x: 2_400, y: -600, width: 900, height: 800 },
  { width: 720, height: 480 },
);
check(projectedOffscreen.width === 720 && projectedOffscreen.height === 480, "viewport projection should fit oversized floating content");
check(projectedOffscreen.x <= 624 && projectedOffscreen.y === 0, "viewport projection should keep the titlebar reachable");

let layout = activateDockPanel(createDefaultWorkspaceLayout(), "center", "dashboard");
let renderer!: ReactTestRenderer;
act(() => { renderer = create(renderWorkspace(layout, [panel])); });
check(mounts === 1 && unmounts === 0, "probe should mount exactly once initially");
const initialToken = renderer.root.findByProps({ "aria-label": "Stateful draft" }).props["data-probe-token"];

layout = placePanel(layout, "dashboard", { kind: "dock", region: "left", index: 0 });
act(() => { renderer.update(renderWorkspace(layout, [panel])); });
check(mounts === 1 && unmounts === 0, "center-to-left docking must not remount panel content");

layout = placePanel(layout, "dashboard", {
  kind: "floating",
  bounds: { x: 40, y: 50, width: 520, height: 360 },
});
act(() => { renderer.update(renderWorkspace(layout, [panel])); });
check(renderer.root.findByProps({ "data-panel-id": "dashboard" }).props.role === "dialog", "tear-off should use modeless dialog semantics");
check(mounts === 1 && unmounts === 0, "dock-to-floating must not remount panel content");

layout = moveFloatingPanel(layout, "dashboard", 140, 110);
layout = resizeFloatingPanel(layout, "dashboard", 680, 440);
act(() => { renderer.update(renderWorkspace(layout, [panel])); });
check(mounts === 1 && unmounts === 0, "floating move/resize must preserve panel instance");

layout = setFloatingPanelMinimized(layout, "dashboard", true);
act(() => { renderer.update(renderWorkspace(layout, [panel])); });
check(renderer.root.findByProps({ "data-panel-id": "dashboard" }).props.hidden === true, "minimized float should remain mounted but hidden");
check(mounts === 1 && unmounts === 0, "minimizing must not unmount panel content");

layout = focusPanel(setFloatingPanelMinimized(layout, "dashboard", false), "dashboard");
layout = setWorkspacePreset(layout, "focus");
act(() => { renderer.update(renderWorkspace(layout, [panel])); });
check(renderer.root.findByProps({ "data-panel-id": "dashboard" }).props.hidden === true, "Focus must hide floating panels non-destructively");
layout = setWorkspacePreset(layout, "cockpit");
layout = placePanel(layout, "dashboard", { kind: "dock", region: "right", index: 0 });
act(() => { renderer.update(renderWorkspace(layout, [panel])); });
check(mounts === 1 && unmounts === 0, "Focus round-trip and redocking must preserve panel instance");
check(
  renderer.root.findByProps({ "aria-label": "Stateful draft" }).props["data-probe-token"] === initialToken,
  "internal panel state token should survive every placement transition",
);

layout = closePanel(layout, "dashboard");
act(() => { renderer.update(renderWorkspace(layout, [])); });
check(unmounts === 1, "closing a panel should unmount it exactly once");

const immovablePanel: WorkspacePanelDefinition = {
  id: "ai-companions",
  label: "AI Companions",
  movable: false,
  closable: false,
  node: <div>Permanent AI surface</div>,
};
layout = placePanel(createDefaultWorkspaceLayout(), "ai-companions", {
  kind: "floating",
  bounds: { x: 30, y: 30, width: 480, height: 320 },
});
act(() => { renderer.update(renderWorkspace(layout, [immovablePanel])); });
check(
  renderer.root.findByProps({ "aria-label": "Move AI Companions floating panel" }).props.tabIndex === -1,
  "non-movable floating surfaces must not expose the drag handle to keyboard users",
);
check(
  renderer.root.findByProps({ "aria-label": "Dock AI Companions to left" }).props.disabled === true
    && renderer.root.findByProps({ "aria-label": "Minimize AI Companions" }).props.disabled === true
    && renderer.root.findByProps({ "aria-label": "Resize AI Companions floating panel" }).props.tabIndex === -1,
  "non-movable floating surfaces must disable dock, minimize, and resize controls",
);

console.log(`${assertions} workspace dock render assertions passed.`);
