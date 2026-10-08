import { useEffect, useState } from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import {
  DockWorkspace,
  WorkspaceNavigator,
  projectFloatingBounds,
  type DockWorkspaceProps,
  type WorkspacePanelDefinition,
} from "../src/components/shell/DockWorkspace";
import { TopBar } from "../src/components/shell/Chrome";
import { ShellStyles } from "../src/components/shell/ShellStyles";
import { StudioProvider } from "../src/adapters/StudioProvider";
import { workspacePanelDomToken } from "../src/components/shell/workspaceInteraction";
import {
  activateDockPanel,
  closePanel,
  createDefaultWorkspaceLayout,
  focusPanel,
  moveFloatingPanel,
  placePanel,
  resizeFloatingPanel,
  serializeWorkspaceLayout,
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
const focusedSelectors: string[] = [];
const queriedSelectors: string[] = [];
const workspaceBounds = {
  left: 0, top: 0, right: 1_200, bottom: 800, width: 1_200, height: 800,
};

class TestHTMLElement {
  constructor(private readonly attributes: Record<string, string> = {}) {}
  getAttribute(name: string) { return this.attributes[name] ?? null; }
}

(globalThis as unknown as { HTMLElement: typeof TestHTMLElement }).HTMLElement = TestHTMLElement;
(globalThis as unknown as { requestAnimationFrame: (callback: () => void) => number }).requestAnimationFrame = (callback) => {
  callback();
  return 1;
};
(globalThis as unknown as { document: { body: { style: Record<string, string> } } }).document = {
  body: { style: {} },
};

const createNodeMock = (element: { props?: Record<string, unknown> }) => {
  if (element.props?.className !== "lf-dock-workspace") return {};
  return {
    getBoundingClientRect: () => workspaceBounds,
    contains: () => false,
    querySelector: (selector: string) => {
      queriedSelectors.push(selector);
      const width = selector.includes("panel-left") ? 300 : selector.includes("panel-right") ? 460 : 640;
      const height = selector.includes("panel-bottom") ? 220 : 480;
      return {
        focus: () => focusedSelectors.push(selector),
        getBoundingClientRect: () => ({
          left: 0, top: 0, right: width, bottom: height, width, height,
        }),
      };
    },
  };
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

let manuscriptMounts = 0;
let manuscriptUnmounts = 0;
let nextManuscriptToken = 0;
function StatefulManuscriptProbe() {
  const [token] = useState(() => `manuscript-${++nextManuscriptToken}`);
  useEffect(() => {
    manuscriptMounts += 1;
    return () => { manuscriptUnmounts += 1; };
  }, []);
  return <textarea aria-label="Stateful manuscript draft" data-manuscript-token={token} defaultValue="Uncommitted prose" />;
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

function keyboardEvent(key: string, target: object, shiftKey = false) {
  let prevented = false;
  return {
    key,
    shiftKey,
    target,
    currentTarget: target,
    preventDefault: () => { prevented = true; },
    get prevented() { return prevented; },
  };
}

async function settleWorkspaceAction(run: () => void) {
  act(run);
  await Promise.resolve();
}

const projectedOffscreen = projectFloatingBounds(
  { x: 2_400, y: -600, width: 900, height: 800 },
  { width: 720, height: 480 },
);
check(projectedOffscreen.width === 720 && projectedOffscreen.height === 480, "viewport projection should fit oversized floating content");
check(projectedOffscreen.x <= 624 && projectedOffscreen.y === 0, "viewport projection should keep the titlebar reachable");

let layout = activateDockPanel(createDefaultWorkspaceLayout(), "center", "dashboard");
let renderer!: ReactTestRenderer;
act(() => { renderer = create(renderWorkspace(layout, [panel]), { createNodeMock }); });
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
  id: "locked-utility",
  label: "Locked Utility",
  movable: false,
  closable: false,
  node: <div>Deliberately fixed utility surface</div>,
};
layout = placePanel(createDefaultWorkspaceLayout(), "locked-utility", {
  kind: "floating",
  bounds: { x: 30, y: 30, width: 480, height: 320 },
});
act(() => { renderer.update(renderWorkspace(layout, [immovablePanel])); });
check(
  renderer.root.findByProps({ "aria-label": "Move Locked Utility floating panel" }).props.tabIndex === -1,
  "non-movable floating surfaces must not expose the drag handle to keyboard users",
);
check(
  renderer.root.findByProps({ "aria-label": "Dock Locked Utility to left" }).props.disabled === true
    && renderer.root.findByProps({ "aria-label": "Minimize Locked Utility" }).props.disabled === true
    && renderer.root.findByProps({ "aria-label": "Resize Locked Utility floating panel" }).props.tabIndex === -1,
  "non-movable floating surfaces must disable dock, minimize, and resize controls",
);

// Mounted ARIA relationships: every dock tab owns one tabpanel, with a single
// roving tab stop and a visibility state matching the selected tab.
const relationshipPanels: readonly WorkspacePanelDefinition[] = [
  { id: "manuscript", label: "Manuscript", closable: false, node: <StatefulManuscriptProbe /> },
  { id: "dashboard", label: "Dashboard", node: <div>Dashboard body</div> },
  { id: "ai-companions", label: "AI Companions", closable: false, node: <div>AI body</div> },
  { id: "decision-radar", label: "Decision Radar", node: <div>Radar body</div> },
  { id: "outline", label: "Outline", node: <div>Outline body</div> },
  { id: "health", label: "Health", node: <div>Health body</div> },
];
const activationCalls: Array<[string, string]> = [];
const panelMoveCalls: Array<[string, string, number]> = [];
const resizeDockCalls: Array<[string, number]> = [];
const moveFloatingCalls: Array<[string, number, number]> = [];
const resizeFloatingCalls: Array<[string, number, number]> = [];
const minimizeFloatingCalls: Array<[string, boolean]> = [];
const focusedFloatingPanels: string[] = [];
const interactiveProps: Omit<DockWorkspaceProps, "layout" | "panels"> = {
  ...staticProps,
  onActivate: (panelId, region) => { activationCalls.push([panelId, region]); return true; },
  onMove: (panelId, region, index) => { panelMoveCalls.push([panelId, region, index]); return true; },
  onResizeDock: (region, size) => { resizeDockCalls.push([region, size]); },
  onMoveFloating: (panelId, x, y) => { moveFloatingCalls.push([panelId, x, y]); },
  onResizeFloating: (panelId, width, height) => { resizeFloatingCalls.push([panelId, width, height]); },
  onMinimizeFloating: (panelId, minimized) => { minimizeFloatingCalls.push([panelId, minimized]); return true; },
  onFocusFloating: (panelId) => { focusedFloatingPanels.push(panelId); },
};
let accessibleLayout = createDefaultWorkspaceLayout();
let accessibleRenderer!: ReactTestRenderer;
act(() => {
  accessibleRenderer = create(
    <DockWorkspace {...interactiveProps} layout={accessibleLayout} panels={relationshipPanels} />,
    { createNodeMock },
  );
});
check(manuscriptMounts === 1 && manuscriptUnmounts === 0, "manuscript should mount once in its default dock");
const manuscriptToken = accessibleRenderer.root
  .findByProps({ "aria-label": "Stateful manuscript draft" })
  .props["data-manuscript-token"];
check(
  accessibleRenderer.root.findByProps({ "aria-label": "Float Manuscript" }).props.disabled === false
    && accessibleRenderer.root.findByProps({ "aria-label": "Float AI Companions" }).props.disabled === false,
  "Manuscript and AI Companions should both expose enabled tear-off controls",
);
check(
  accessibleRenderer.root.findByProps({ id: `lf-tab-${workspacePanelDomToken("manuscript")}` }).props.draggable === true
    && accessibleRenderer.root.findByProps({ id: `lf-tab-${workspacePanelDomToken("ai-companions")}` }).props.draggable === true,
  "Manuscript and AI Companions dock tabs should both support pointer movement",
);

const dockTabs = accessibleRenderer.root.findAllByProps({ role: "tab" });
const dockTabPanels = accessibleRenderer.root.findAllByProps({ role: "tabpanel" });
check(dockTabs.length === relationshipPanels.length, "every docked panel should expose one tab");
check(dockTabPanels.length === relationshipPanels.length, "every docked panel should expose one tabpanel");
for (const tab of dockTabs) {
  const controlled = tab.props["aria-controls"];
  const ownedPanel = dockTabPanels.find((candidate) => candidate.props.id === controlled);
  check(Boolean(ownedPanel), `tab ${tab.props.id} should reference a mounted tabpanel`);
  check(ownedPanel!.props["aria-labelledby"] === tab.props.id, `tabpanel ${controlled} should be labelled by its tab`);
  check(
    ownedPanel!.props.hidden === !tab.props["aria-selected"]
      && ownedPanel!.props["aria-hidden"] === !tab.props["aria-selected"],
    `tabpanel ${controlled} visibility should match tab selection`,
  );
}
for (const tablist of accessibleRenderer.root.findAllByProps({ role: "tablist" })) {
  const tabs = tablist.findAllByProps({ role: "tab" });
  if (tabs.length === 0) continue;
  check(tabs.filter((tab) => tab.props.tabIndex === 0).length === 1, `${tablist.props["aria-label"]} should have one roving tab stop`);
  check(tabs.find((tab) => tab.props.tabIndex === 0)?.props["aria-selected"] === true, `${tablist.props["aria-label"]} tab stop should be selected`);
}

// Arrow/Home/End activate tabs through the host callback and move focus only
// after the action reports success. A declined activation restores the old tab.
const centerTablist = accessibleRenderer.root.findByProps({ "aria-label": "Center workspace dock" });
const tabEventTarget = new TestHTMLElement({ role: "tab" });
const arrowRight = keyboardEvent("ArrowRight", tabEventTarget);
focusedSelectors.length = 0;
queriedSelectors.length = 0;
await settleWorkspaceAction(() => centerTablist.props.onKeyDown(arrowRight));
check(arrowRight.prevented, "ArrowRight on a dock tab should prevent browser scrolling");
check(
  activationCalls.at(-1)?.[0] === "dashboard" && activationCalls.at(-1)?.[1] === "center",
  "ArrowRight should request the next center tab",
);
check(
  focusedSelectors.at(-1) === `#lf-tab-${workspacePanelDomToken("dashboard")}`,
  "successful keyboard activation should focus the newly selected tab",
);

const declinedProps = { ...interactiveProps, onActivate: () => false };
act(() => {
  accessibleRenderer.update(
    <DockWorkspace {...declinedProps} layout={accessibleLayout} panels={relationshipPanels} />,
  );
});
const declinedCenterTablist = accessibleRenderer.root.findByProps({ "aria-label": "Center workspace dock" });
focusedSelectors.length = 0;
await settleWorkspaceAction(() => declinedCenterTablist.props.onKeyDown(keyboardEvent("End", tabEventTarget)));
check(
  focusedSelectors.at(-1) === `#lf-tab-${workspacePanelDomToken("manuscript")}`,
  "declined keyboard activation should restore focus to the selected tab",
);

// Dock and navigator separators publish the value contract and support the
// documented arrow/Home/End keyboard operations.
act(() => {
  accessibleRenderer.update(
    <DockWorkspace {...interactiveProps} layout={accessibleLayout} panels={relationshipPanels} />,
  );
});
const rightSeparator = accessibleRenderer.root.findByProps({ "aria-label": "Resize right workspace dock" });
check(
  rightSeparator.props.role === "separator"
    && rightSeparator.props["aria-orientation"] === "vertical"
    && rightSeparator.props.tabIndex === 0
    && rightSeparator.props["aria-valuenow"] === accessibleLayout.docks.right.sizePx,
  "right dock resizer should expose an operable vertical separator value",
);
const rightResizeEvent = keyboardEvent("ArrowLeft", rightSeparator);
act(() => { rightSeparator.props.onKeyDown(rightResizeEvent); });
check(rightResizeEvent.prevented, "dock separator keyboard resize should prevent browser scrolling");
check(
  resizeDockCalls.at(-1)?.[0] === "right"
    && resizeDockCalls.at(-1)?.[1] === accessibleLayout.docks.right.sizePx + 16,
  "ArrowLeft should grow the right dock by one keyboard step",
);
const bottomSeparator = accessibleRenderer.root.findByProps({ "aria-label": "Resize bottom workspace dock" });
check(bottomSeparator.props["aria-orientation"] === "horizontal", "bottom dock resizer should be a horizontal separator");
act(() => { bottomSeparator.props.onKeyDown(keyboardEvent("Home", bottomSeparator)); });
check(resizeDockCalls.at(-1)?.[0] === "bottom" && resizeDockCalls.at(-1)?.[1] === 120, "Home should resize the bottom dock to its minimum");

const navigatorWidths: number[] = [];
let navigatorRenderer!: ReactTestRenderer;
act(() => {
  navigatorRenderer = create(
    <WorkspaceNavigator
      collapsed={false}
      widthPx={232}
      onCollapsedChange={() => true}
      onWidthChange={(width) => navigatorWidths.push(width)}
    >
      <div>Navigator content</div>
    </WorkspaceNavigator>,
  );
});
const navigatorSeparator = navigatorRenderer.root.findByProps({ "aria-label": "Resize workspace navigator" });
check(
  navigatorSeparator.props.role === "separator"
    && navigatorSeparator.props["aria-orientation"] === "vertical"
    && navigatorSeparator.props["aria-valuemin"] === 160
    && navigatorSeparator.props["aria-valuemax"] === 480,
  "navigator resizer should expose its separator range",
);
act(() => { navigatorSeparator.props.onKeyDown(keyboardEvent("ArrowRight", navigatorSeparator, true)); });
check(navigatorWidths.at(-1) === 296, "Shift+ArrowRight should grow the navigator by its large keyboard step");

// Floating dialogs expose labelled move/resize controls; their keyboard paths
// focus the float and send projected, bounded geometry to the host.
accessibleLayout = placePanel(accessibleLayout, "dashboard", {
  kind: "floating",
  bounds: { x: 40, y: 50, width: 520, height: 360 },
});
act(() => {
  accessibleRenderer.update(
    <DockWorkspace {...interactiveProps} layout={accessibleLayout} panels={relationshipPanels} />,
  );
});
const floatingDialog = accessibleRenderer.root.findByProps({ "data-panel-id": "dashboard" });
const floatingTitle = accessibleRenderer.root.findByProps({ "aria-label": "Move Dashboard floating panel" });
check(
  floatingDialog.props.role === "dialog"
    && floatingDialog.props["aria-modal"] === false
    && floatingDialog.props["aria-labelledby"] === floatingTitle.props.id,
  "floating panel should be a labelled modeless dialog",
);
const moveEvent = keyboardEvent("ArrowRight", floatingTitle);
act(() => { floatingTitle.props.onKeyDown(moveEvent); });
check(moveEvent.prevented, "floating-panel keyboard move should prevent browser scrolling");
check(
  focusedFloatingPanels.at(-1) === "dashboard"
    && JSON.stringify(moveFloatingCalls.at(-1)) === JSON.stringify(["dashboard", 52, 50]),
  "ArrowRight should focus and move the floating panel by one step",
);
const floatingResizer = accessibleRenderer.root.findByProps({ "aria-label": "Resize Dashboard floating panel" });
check(floatingResizer.props.tabIndex === 0 && /520 by 360 pixels/.test(floatingResizer.props["aria-description"]), "floating resizer should expose its current dimensions");
const floatingResizeEvent = keyboardEvent("ArrowDown", floatingResizer);
act(() => { floatingResizer.props.onKeyDown(floatingResizeEvent); });
check(floatingResizeEvent.prevented, "floating-panel keyboard resize should prevent browser scrolling");
check(
  focusedFloatingPanels.at(-1) === "dashboard"
    && JSON.stringify(resizeFloatingCalls.at(-1)) === JSON.stringify(["dashboard", 520, 372]),
  "ArrowDown should focus and grow the floating panel height by one step",
);

// Manuscript and the composite AI surface are ordinary movable workspace
// panels. They retain the permanent/nonclosable policy, but expose the same
// modeless movement, sizing, minimization, and redocking affordances as every
// other float.
accessibleLayout = placePanel(accessibleLayout, "manuscript", {
  kind: "floating",
  bounds: { x: 96, y: 88, width: 840, height: 620 },
});
accessibleLayout = placePanel(accessibleLayout, "ai-companions", {
  kind: "floating",
  bounds: { x: 248, y: 126, width: 610, height: 490 },
});
const floatingCockpitSnapshot = serializeWorkspaceLayout(accessibleLayout);
act(() => {
  accessibleRenderer.update(
    <DockWorkspace {...interactiveProps} layout={accessibleLayout} panels={relationshipPanels} />,
  );
});

for (const panelLabel of ["Manuscript", "AI Companions"] as const) {
  const titlebar = accessibleRenderer.root.findByProps({ "aria-label": `Move ${panelLabel} floating panel` });
  const resizer = accessibleRenderer.root.findByProps({ "aria-label": `Resize ${panelLabel} floating panel` });
  const minimize = accessibleRenderer.root.findByProps({ "aria-label": `Minimize ${panelLabel}` });
  check(
    titlebar.props.tabIndex === 0 && resizer.props.tabIndex === 0 && minimize.props.disabled === false,
    `${panelLabel} should expose keyboard move, resize, and minimize controls while floating`,
  );
  check(
    ["left", "center", "right", "bottom"].every((region) => (
      accessibleRenderer.root.findByProps({ "aria-label": `Dock ${panelLabel} to ${region}` }).props.disabled === false
    )),
    `${panelLabel} should be redockable into every workspace region`,
  );
}

const manuscriptFloatingTitle = accessibleRenderer.root.findByProps({ "aria-label": "Move Manuscript floating panel" });
const manuscriptMoveEvent = keyboardEvent("ArrowLeft", manuscriptFloatingTitle);
act(() => { manuscriptFloatingTitle.props.onKeyDown(manuscriptMoveEvent); });
check(
  manuscriptMoveEvent.prevented
    && focusedFloatingPanels.at(-1) === "manuscript"
    && JSON.stringify(moveFloatingCalls.at(-1)) === JSON.stringify(["manuscript", 84, 88]),
  "Manuscript floating movement should use the shared keyboard path",
);
const manuscriptFloatingResizer = accessibleRenderer.root.findByProps({ "aria-label": "Resize Manuscript floating panel" });
const manuscriptResizeEvent = keyboardEvent("ArrowUp", manuscriptFloatingResizer);
act(() => { manuscriptFloatingResizer.props.onKeyDown(manuscriptResizeEvent); });
check(
  manuscriptResizeEvent.prevented
    && JSON.stringify(resizeFloatingCalls.at(-1)) === JSON.stringify(["manuscript", 840, 608]),
  "Manuscript floating resize should use the shared keyboard path",
);
await settleWorkspaceAction(() => {
  accessibleRenderer.root.findByProps({ "aria-label": "Minimize AI Companions" }).props.onClick();
});
check(
  JSON.stringify(minimizeFloatingCalls.at(-1)) === JSON.stringify(["ai-companions", true]),
  "AI Companions should use the shared floating minimize callback",
);
await settleWorkspaceAction(() => {
  accessibleRenderer.root.findByProps({ "aria-label": "Dock Manuscript to left" }).props.onClick();
});
check(
  panelMoveCalls.at(-1)?.[0] === "manuscript" && panelMoveCalls.at(-1)?.[1] === "left",
  "Manuscript should use the shared redock callback for a non-center destination",
);

// Focus is a visual projection, not a destructive layout mutation. A floated
// manuscript becomes the sole center tabpanel while focused and returns to the
// exact saved floating geometry afterward without remounting its editor state.
const focusWithFloatedManuscript = setWorkspacePreset(accessibleLayout, "focus");
check(
  serializeWorkspaceLayout(accessibleLayout) === floatingCockpitSnapshot,
  "creating the Focus projection must not mutate the Cockpit layout",
);
act(() => {
  accessibleRenderer.update(
    <DockWorkspace {...interactiveProps} layout={focusWithFloatedManuscript} panels={relationshipPanels} />,
  );
});
const projectedManuscript = accessibleRenderer.root.findByProps({ "data-panel-id": "manuscript" });
check(
  projectedManuscript.props.role === "tabpanel"
    && projectedManuscript.props.hidden === false
    && projectedManuscript.props["data-dock-region"] === "center"
    && projectedManuscript.props["data-floating-panel"] === undefined,
  "Focus should visually project a floated Manuscript into the center work surface",
);
const projectedManuscriptTab = accessibleRenderer.root.findByProps({
  id: `lf-tab-${workspacePanelDomToken("manuscript")}`,
});
check(
  projectedManuscriptTab.props.draggable === false
    && accessibleRenderer.root.findAllByProps({ "aria-label": "Float Manuscript" }).length === 0
    && accessibleRenderer.root.findAll((node) => (
      typeof node.props?.["aria-label"] === "string"
      && node.props["aria-label"].startsWith("Move Manuscript to ")
    )).length === 0,
  "the temporary Focus projection must not expose controls that rewrite the saved Cockpit placement",
);
check(
  accessibleRenderer.root.findByProps({ "data-panel-id": "ai-companions" }).props.hidden === true,
  "Focus should continue hiding non-Manuscript floating panels",
);
check(
  manuscriptMounts === 1
    && manuscriptUnmounts === 0
    && accessibleRenderer.root.findByProps({ "aria-label": "Stateful manuscript draft" }).props["data-manuscript-token"] === manuscriptToken,
  "Focus projection must preserve the mounted Manuscript editor instance and draft state",
);

accessibleLayout = setWorkspacePreset(focusWithFloatedManuscript, "cockpit");
check(
  serializeWorkspaceLayout(accessibleLayout) === floatingCockpitSnapshot,
  "leaving Focus should restore the byte-identical Cockpit placement",
);
act(() => {
  accessibleRenderer.update(
    <DockWorkspace {...interactiveProps} layout={accessibleLayout} panels={relationshipPanels} />,
  );
});
const restoredFloatingManuscript = accessibleRenderer.root.findByProps({ "data-panel-id": "manuscript" });
check(
  restoredFloatingManuscript.props.role === "dialog"
    && restoredFloatingManuscript.props["data-floating-panel"] === "true"
    && restoredFloatingManuscript.props.style.left === 96
    && restoredFloatingManuscript.props.style.top === 88
    && restoredFloatingManuscript.props.style.width === 840
    && restoredFloatingManuscript.props.style.height === 620,
  "Cockpit should restore the Manuscript floating dialog at its exact saved bounds",
);
check(
  manuscriptMounts === 1
    && manuscriptUnmounts === 0
    && accessibleRenderer.root.findByProps({ "aria-label": "Stateful manuscript draft" }).props["data-manuscript-token"] === manuscriptToken,
  "Focus round-trip must not remount the Manuscript editor",
);

// The Focus/Cockpit segmented control must expose its selected state, not only
// color. Mount the real TopBar under the provider with a minimal project list.
let modeToggleCalls = 0;
let topBarRenderer!: ReactTestRenderer;
act(() => {
  topBarRenderer = create(
    <StudioProvider
      services={{
        api: { listProjects: async () => [] } as never,
        platform: {} as never,
      }}
      writingMode="novel"
    >
      <TopBar
        formatBadge="NOVEL"
        layout="focus"
        onToggleFocus={() => { modeToggleCalls += 1; }}
      />
    </StudioProvider>,
  );
});
const workspaceModeGroup = topBarRenderer.root.findByProps({ "aria-label": "Workspace mode" });
const modeButtons = workspaceModeGroup.findAllByType("button");
const focusButton = modeButtons.find((button) => button.children.join("") === "FOCUS");
const cockpitButton = modeButtons.find((button) => button.children.join("") === "COCKPIT");
check(focusButton?.props["aria-pressed"] === true, "Focus mode button should expose its selected state");
check(cockpitButton?.props["aria-pressed"] === false, "Cockpit mode button should expose its unselected state");
act(() => { cockpitButton?.props.onClick(); });
check(modeToggleCalls === 1, "unselected workspace mode should remain keyboard/click operable");

// Responsive Studio chrome depends on stable semantic regions: the shared CSS
// rearranges these nodes at the compact breakpoint without changing TopBar's
// platform-neutral markup or hiding an always-on control.
const topBarRegions = [
  "lf-topbar",
  "lf-topbar-brand",
  "lf-topbar-format",
  "lf-topbar-command",
  "lf-topbar-adaptive",
  "lf-topbar-layout",
  "lf-topbar-status",
] as const;
for (const className of topBarRegions) {
  check(
    topBarRenderer.root.findAllByProps({ className }).length === 1,
    `${className} should identify exactly one responsive top-bar region`,
  );
}
const commandButton = topBarRenderer.root.findByProps({ className: "lf-cmd" });
check(
  commandButton.props.style.width === "100%"
    && commandButton.props.style.maxWidth === 560
    && commandButton.props.style.minWidth === 0,
  "command palette control should shrink below its preferred desktop width",
);
const commandShortcut = topBarRenderer.root.findByProps({ className: "lf-topbar-command-shortcut" });
check(commandShortcut.children.join("") === "Ctrl/⌘ K", "command palette should display a cross-platform shortcut hint");

let shellStylesRenderer!: ReactTestRenderer;
act(() => { shellStylesRenderer = create(<ShellStyles />); });
const shellCss = shellStylesRenderer.root.findByType("style").children.join("");
check(
  /\.lf-topbar-command\{[^}]*min-width:0;/.test(shellCss)
    && /\.lf-topbar-command \.lf-cmd\{[^}]*min-width:0;/.test(shellCss),
  "shell CSS should allow both the command region and command control to shrink",
);
const compactTopBarStart = shellCss.indexOf("@media (max-width:1280px)");
const mobileWorkspaceStart = shellCss.indexOf("@media (max-width:760px)", compactTopBarStart);
check(
  compactTopBarStart >= 0 && mobileWorkspaceStart > compactTopBarStart,
  "shell CSS should define the compact top-bar breakpoint at 1280px",
);
const compactTopBarCss = shellCss.slice(compactTopBarStart, mobileWorkspaceStart);
check(
  /\.lf-topbar\{[^}]*height:78px;[^}]*display:grid;[^}]*grid-template-areas:"brand format command" "adaptive layout status";/.test(compactTopBarCss),
  "compact top bar should use the documented two-row grid",
);
check(
  ["brand", "format", "command", "adaptive", "layout", "status"].every((area) => (
    new RegExp(`\\.lf-topbar-${area}\\{[^}]*grid-area:${area};`).test(compactTopBarCss)
  )),
  "each compact top-bar region should be assigned to its semantic grid area",
);

act(() => {
  renderer.unmount();
  accessibleRenderer.unmount();
  navigatorRenderer.unmount();
  topBarRenderer.unmount();
  shellStylesRenderer.unmount();
});

console.log(`${assertions} workspace dock render assertions passed.`);
