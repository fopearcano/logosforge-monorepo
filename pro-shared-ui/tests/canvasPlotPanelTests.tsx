import { MessagePort } from "node:worker_threads";
import { act, create, type ReactTestInstance, type ReactTestRenderer } from "react-test-renderer";
import type {
  CanvasPlotCommandDTO,
  CanvasPlotCommandResultDTO,
  CanvasPlotSnapshotDTO,
  EventMessage,
  SettingsDTO,
} from "@logosforge/ui-contracts";
import type { ApiClient } from "../src/adapters/api";
import type { PlatformAdapter } from "../src/adapters/platform";
import { flushPendingProjectSaves } from "../src/adapters/projectSaveCoordinator";
import { StudioProvider } from "../src/adapters/StudioProvider";
import { useSelection } from "../src/adapters/selection";
import { CanvasPlot } from "../src/components/spatialcanvas/CanvasPlot";

let assertions = 0;
function check(value: unknown, message: string): asserts value {
  assertions += 1;
  if (!value) throw new Error(message);
}

function text(node: ReactTestInstance): string {
  return node.children.map((child) => typeof child === "string" ? child : text(child)).join("");
}

function snapshot(projectId: number, revisionSeed: string, offset = 0): CanvasPlotSnapshotDTO {
  return {
    project_id: projectId,
    revision: revisionSeed.repeat(64),
    nodes: [
      { id: offset + 1, title: "Alpha", body: "Opening idea", x: 0, y: 0, width: 188, height: 116, color_label: "cyan", group_label: "main", scene_id: offset + 101, sort_order: 0, created_at: "2026-01-01T00:00:00Z" },
      { id: offset + 2, title: "Beta", body: "Payoff idea", x: 320, y: 40, width: 188, height: 116, color_label: "amber", group_label: "main", scene_id: null, sort_order: 1, created_at: "2026-01-01T00:00:01Z" },
    ],
    links: [],
    frames: [{ id: offset + 10, title: "Act I", color_label: "blue", x: -60, y: -50, width: 640, height: 270, created_at: "2026-01-01T00:00:02Z" }],
  };
}

const snapshots = new Map<number, CanvasPlotSnapshotDTO>([
  [7, snapshot(7, "a")],
  [8, snapshot(8, "b", 100)],
]);
const projectSettings = new Map<number, Record<string, unknown>>([
  [7, { canvas_plot_view: { zoom: 1, cx: 12, cy: -8 } }],
  [8, { canvas_plot_view: { zoom: 2, cx: 900, cy: 450 } }],
]);
const commands: CanvasPlotCommandDTO[] = [];
const listeners = new Set<(event: EventMessage) => void>();
let revisionCounter = 10;
let nextLinkId = 50;
let pointerCaptures = 0;
let wheelListenerPassive: boolean | null = null;
let deferredSettingsProject: number | null = null;
let resolveDeferredSettings: ((value: SettingsDTO) => void) | null = null;
let deferredSettings: Promise<SettingsDTO> | null = null;

function deferSettings(projectId: number): void {
  deferredSettingsProject = projectId;
  deferredSettings = new Promise<SettingsDTO>((resolve) => { resolveDeferredSettings = resolve; });
}

function clone<T>(value: T): T {
  return structuredClone(value);
}

function apply(projectId: number, command: CanvasPlotCommandDTO): CanvasPlotCommandResultDTO {
  const current = clone(snapshots.get(projectId)!);
  const created = { node: null as number | null, link: null as number | null, frame: null as number | null };
  if (command.kind === "update_node") {
    const node = current.nodes.find((candidate) => candidate.id === command.node_id)!;
    for (const key of ["title", "body", "x", "y", "width", "height", "color_label", "group_label", "scene_id"] as const) {
      if (command[key] !== undefined) Object.assign(node, { [key]: command[key] });
    }
    if (command.index != null) {
      const ordered = current.nodes.filter((candidate) => candidate.id !== node.id);
      ordered.splice(command.index, 0, node);
      ordered.forEach((candidate, index) => { candidate.sort_order = index; });
      current.nodes = ordered;
    }
  } else if (command.kind === "delete_node") {
    current.nodes = current.nodes.filter((node) => node.id !== command.node_id);
    current.links = current.links.filter((link) => link.source_node_id !== command.node_id && link.target_node_id !== command.node_id);
  } else if (command.kind === "create_link") {
    created.link = nextLinkId++;
    current.links.push({ id: created.link, source_node_id: command.source_node_id, target_node_id: command.target_node_id, label: command.label ?? "", color_label: command.color_label ?? "gray", link_type: command.link_type ?? "", created_at: "2026-01-01T00:00:03Z" });
  } else if (command.kind === "update_frame") {
    const frame = current.frames.find((candidate) => candidate.id === command.frame_id)!;
    for (const key of ["title", "x", "y", "width", "height", "color_label"] as const) {
      if (command[key] !== undefined) Object.assign(frame, { [key]: command[key] });
    }
  } else if (command.kind === "delete_frame") {
    current.frames = current.frames.filter((frame) => frame.id !== command.frame_id);
  } else if (command.kind === "delete_link") {
    current.links = current.links.filter((link) => link.id !== command.link_id);
  } else if (command.kind === "update_link") {
    const link = current.links.find((candidate) => candidate.id === command.link_id)!;
    for (const key of ["label", "color_label", "link_type"] as const) {
      if (command[key] !== undefined) Object.assign(link, { [key]: command[key] });
    }
  } else if (command.kind === "create_node") {
    created.node = Math.max(0, ...current.nodes.map((node) => node.id)) + 1;
    current.nodes.push({ id: created.node, title: command.title ?? "", body: command.body ?? "", x: command.x ?? 0, y: command.y ?? 0, width: command.width ?? 188, height: command.height ?? 116, color_label: command.color_label ?? "", group_label: command.group_label ?? "", scene_id: command.scene_id ?? null, sort_order: current.nodes.length, created_at: "2026-01-01T00:00:04Z" });
  } else if (command.kind === "create_frame") {
    created.frame = Math.max(0, ...current.frames.map((frame) => frame.id)) + 1;
    current.frames.push({ id: created.frame, title: command.title ?? "", color_label: command.color_label ?? "", x: command.x ?? 0, y: command.y ?? 0, width: command.width ?? 360, height: command.height ?? 260, created_at: "2026-01-01T00:00:05Z" });
  }
  revisionCounter += 1;
  current.revision = revisionCounter.toString(16).padStart(64, "0");
  snapshots.set(projectId, current);
  return {
    canvas_plot: clone(current),
    replayed: false,
    applied_revision: current.revision,
    changed: true,
    affected_node_ids: command.kind.includes("node") ? ["node_id" in command ? command.node_id : created.node!].filter((value) => value != null) : [],
    affected_link_ids: command.kind.includes("link") ? ["link_id" in command ? command.link_id : created.link!].filter((value) => value != null) : [],
    affected_frame_ids: command.kind.includes("frame") ? ["frame_id" in command ? command.frame_id : created.frame!].filter((value) => value != null) : [],
    created_node_id: created.node,
    created_link_id: created.link,
    created_frame_id: created.frame,
  };
}

const api = {
  getCanvasPlot: async (projectId: number) => clone(snapshots.get(projectId)!),
  executeCanvasPlotCommand: async (projectId: number, command: CanvasPlotCommandDTO) => {
    commands.push(clone(command));
    return apply(projectId, command);
  },
  getSettings: async (projectId: number): Promise<SettingsDTO> => {
    if (deferredSettingsProject === projectId && deferredSettings) return deferredSettings;
    return { settings: clone(projectSettings.get(projectId) ?? {}) };
  },
  patchSettings: async (projectId: number, body: SettingsDTO): Promise<SettingsDTO> => {
    const next = { ...(projectSettings.get(projectId) ?? {}), ...body.settings };
    projectSettings.set(projectId, next);
    return { settings: clone(next) };
  },
  subscribe: (_projectId: number, listener: (event: EventMessage) => void) => {
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  },
} as unknown as ApiClient;

const platform: PlatformAdapter = {
  isDesktop: false,
  openFile: async () => ({ canceled: true }),
  saveFile: async () => ({ canceled: true }),
  openExternal: async () => undefined,
};

function SelectionProbe() {
  const { selection } = useSelection();
  return <output data-scene={selection.sceneId ?? ""} data-section={selection.section ?? ""} data-node={selection.nodeId ?? ""}>{selection.text}</output>;
}

function tree(projectId: number) {
  return (
    <StudioProvider services={{ api, platform }} projectId={projectId}>
      <CanvasPlot />
      <SelectionProbe />
    </StudioProvider>
  );
}

async function flush() {
  for (let index = 0; index < 12; index += 1) await Promise.resolve();
}

async function emitCanvasChange(projectId: number): Promise<void> {
  for (const listener of [...listeners]) {
    listener({
      id: revisionCounter,
      event: "canvas_plot_changed",
      project_id: projectId,
      data: {},
      ts: Date.now(),
    });
  }
  await new Promise((resolve) => setTimeout(resolve, 140));
  await flush();
}

const pointer = (pointerId: number, clientX: number, clientY: number) => ({
  button: 0,
  pointerId,
  clientX,
  clientY,
  preventDefault() {},
  stopPropagation() {},
});

let renderer!: ReactTestRenderer;
await act(async () => {
  renderer = create(tree(7), {
    createNodeMock: (element) => element.props["data-canvas-plot-board"] ? {
      getBoundingClientRect: () => ({ left: 0, top: 0, width: 1000, height: 700 }),
      setPointerCapture() { pointerCaptures += 1; },
      releasePointerCapture() {},
      addEventListener(type: string, _listener: EventListener, options?: AddEventListenerOptions) {
        if (type === "wheel") wheelListenerPassive = options?.passive ?? null;
      },
      removeEventListener() {},
    } : {},
  });
  await flush();
});

const board = () => renderer.root.findByProps({ "data-canvas-plot-board": "true" });
const node = (id: number) => renderer.root.findByProps({ "data-canvas-node-id": id });
check(board().props["data-center-x"] === 12 && board().props["data-center-y"] === -8, "the board must hydrate its project-owned viewport");
check(board().props["data-viewport-ready"] === "true", "the board must expose completed viewport hydration before enabling interaction");
check(wheelListenerPassive === false, "Canvas Plot wheel zoom must use a non-passive listener so it can prevent page scrolling");
check(renderer.root.findByProps({ "aria-label": "Add Canvas Plot block" }), "the add-block action must have a stable accessible name");
check(renderer.root.findByProps({ "aria-label": "Add Canvas Plot frame" }), "the add-frame action must have a stable accessible name");
act(() => board().props.onPointerDown({ ...pointer(99, 10, 10), target: { closest: () => ({}) } }));
check(pointerCaptures === 0, "pointerdown from an interactive Canvas Plot entity must never start board panning or capture its click");
act(() => board().props.onKeyDown({ key: "ArrowLeft", target: { closest: () => ({}) }, preventDefault() {} }));
check(board().props["data-center-x"] === 12, "keyboard commands from an entity handle must not also pan the board");

await act(async () => {
  node(1).props.onClick({ stopPropagation() {} });
  await flush();
});
const selection = renderer.root.findByType("output");
check(selection.props["data-scene"] === 101 && selection.props["data-section"] === "Canvas Plot" && selection.props["data-node"] === 1, "selecting a block must publish Studio/AI context including its optional scene");
check(text(selection).includes("Alpha") && text(selection).includes("Opening idea"), "Canvas Plot selection must publish the block text");

act(() => renderer.root.findByProps({ "aria-label": "Block title" }).props.onChange({ currentTarget: { value: "Draft Alpha" } }));
check(renderer.root.findByProps({ "aria-label": "Block title" }).props.value === "Draft Alpha", "typing in the inspector must create a controlled local draft");
act(() => node(1).props.onClick({ stopPropagation() {} }));
check(renderer.root.findByProps({ "aria-label": "Block title" }).props.value === "Draft Alpha", "clicking the already-selected block must not reset its inspector draft");

const moveAlpha = () => renderer.root.findByProps({ "aria-label": "Move Canvas Plot block 1" });
act(() => moveAlpha().props.onPointerDown(pointer(1, 100, 100)));
check(renderer.root.findByProps({ "aria-label": "Block title" }).props.value === "Draft Alpha", "same-block pointerdown must not reselect and overwrite the inspector draft");
act(() => board().props.onPointerMove(pointer(1, 140, 130)));
check(node(1).props["data-x"] === 40 && node(1).props["data-y"] === 30, "pointer movement must preview node geometry without a network write");
check(commands.length === 0, "pointermove must not emit intermediate persistence commands");
const beforeMoveCommands = commands.length;
await act(async () => {
  board().props.onPointerUp(pointer(1, 140, 130));
  await flush();
});
check(commands.length === beforeMoveCommands + 2, "a dirty inspector must save once before the gesture's one geometry command");
const inspectorSave = commands.at(-2);
check(inspectorSave?.kind === "update_node" && inspectorSave.title === "Draft Alpha", "geometry persistence must first commit the exact inspector draft");
check(commands.at(-1)?.kind === "update_node", "pointerup must commit one atomic node command");
const moved = commands.at(-1);
check(moved?.kind === "update_node" && moved.x === 40 && moved.y === 30, "node move must persist world-space coordinates");
check(renderer.root.findByProps({ "aria-label": "Block title" }).props.value === "Draft Alpha", "geometry refetches must retain the saved inspector value");

const resizeAlpha = () => renderer.root.findByProps({ "aria-label": "Resize Canvas Plot block 1" });
act(() => resizeAlpha().props.onPointerDown(pointer(2, 300, 200)));
act(() => board().props.onPointerMove(pointer(2, 330, 225)));
check(node(1).props["data-width"] === 218 && node(1).props["data-height"] === 141, "pointer resize must preview dimensions and keep link geometry live");
const beforeResizeCommands = commands.length;
await act(async () => {
  board().props.onPointerUp(pointer(2, 330, 225));
  await flush();
});
check(commands.length === beforeResizeCommands + 1, "one resize gesture must emit exactly one persistence command");
check(commands.at(-1)?.kind === "update_node" && commands.at(-1)?.width === 218, "node resize must persist through update_node");

act(() => renderer.root.findByProps({ "aria-label": "Start connection from Canvas Plot block 1" }).props.onClick({ stopPropagation() {} }));
check(renderer.root.findByProps({ "aria-label": "Connect to Canvas Plot block 2" }), "two-step connection mode must expose the target affordance");
await act(async () => {
  renderer.root.findByProps({ "aria-label": "Connect to Canvas Plot block 2" }).props.onClick({ stopPropagation() {} });
  await flush();
});
check(commands.at(-1)?.kind === "create_link", "choosing a connection target must commit one create_link command");
check(renderer.root.findAll((item) => item.props["data-canvas-link-id"] != null).length === 1, "the committed connection must render in the board SVG");

const frameMove = () => renderer.root.findByProps({ "data-canvas-frame-move-handle": "true" });
await act(async () => {
  renderer.root.findByProps({ "data-canvas-frame-id": 10 }).props.onClick({ stopPropagation() {} });
  await flush();
});
act(() => frameMove().props.onPointerDown(pointer(3, 40, 40)));
act(() => board().props.onPointerMove(pointer(3, 60, 50)));
check(renderer.root.findByProps({ "data-canvas-frame-id": 10 }).props["data-x"] === -40, "frame drag must preview independently from nodes");
await act(async () => {
  board().props.onPointerUp(pointer(3, 60, 50));
  await flush();
});
check(commands.at(-1)?.kind === "update_frame", "frame pointerup must commit an atomic update_frame command");

await act(async () => {
  node(1).props.onClick({ stopPropagation() {} });
  await flush();
});
act(() => renderer.root.findAllByType("button").find((button) => text(button) === "DELETE")!.props.onClick());
check(renderer.root.findAllByType("button").some((button) => text(button) === "CONFIRM DELETE"), "node deletion must require explicit confirmation");
await act(async () => {
  renderer.root.findAllByType("button").find((button) => text(button) === "CONFIRM DELETE")!.props.onClick();
  await flush();
});
check(commands.at(-1)?.kind === "delete_node", "confirmed deletion must use the transactional delete_node command");
check(renderer.root.findAll((item) => item.props["data-canvas-node-id"] === 1).length === 0, "a committed node deletion must remove the block");

await act(async () => {
  node(2).props.onClick({ stopPropagation() {} });
  await flush();
});
act(() => renderer.root.findByProps({ "aria-label": "Block summary" }).props.onChange({ currentTarget: { value: "Draft survives a live refresh" } }));
const commandsBeforeLiveRefresh = commands.length;
const collaboratorSnapshot = clone(snapshots.get(7)!);
const collaboratorNode = collaboratorSnapshot.nodes.find((candidate) => candidate.id === 2)!;
collaboratorNode.title = "Beta from collaborator";
revisionCounter += 1;
collaboratorSnapshot.revision = revisionCounter.toString(16).padStart(64, "0");
snapshots.set(7, collaboratorSnapshot);
await act(async () => { await emitCanvasChange(7); });
check(renderer.root.findByProps({ "aria-label": "Block summary" }).props.value === "Draft survives a live refresh", "live Canvas Plot refetches must preserve a dirty inspector draft");
check(renderer.root.findByProps({ "aria-label": "Block title" }).props.value === "Beta from collaborator", "live refetches must merge authoritative changes into untouched inspector fields");
check(commands.length === commandsBeforeLiveRefresh, "a read-only live refetch must not implicitly save the inspector");

await act(async () => {
  renderer.root.findByProps({ "data-canvas-frame-id": 10 }).props.onClick({ stopPropagation() {} });
  await flush();
});
check(commands.length === commandsBeforeLiveRefresh + 1, "choosing a different entity must save the previous inspector draft first");
const selectionSave = commands.at(-1);
check(selectionSave?.kind === "update_node" && selectionSave.body === "Draft survives a live refresh", "selection handoff must persist the draft against its original entity");
check(selectionSave?.kind === "update_node" && selectionSave.title === undefined, "saving one dirty field must not overwrite a collaborator's untouched field");
check(snapshots.get(7)?.nodes.find((candidate) => candidate.id === 2)?.title === "Beta from collaborator", "the authoritative collaborator value must survive inspector persistence");
check(renderer.root.findByProps({ "aria-label": "Frame title" }).props.value === "Act I", "the requested entity must open only after the previous draft saves");

act(() => renderer.root.findByProps({ "aria-label": "Frame title" }).props.onChange({ currentTarget: { value: "Act I revised" } }));
await act(async () => {
  renderer.root.findByProps({ "aria-label": "Close Canvas Plot inspector" }).props.onClick();
  await flush();
});
check(commands.at(-1)?.kind === "update_frame" && commands.at(-1)?.title === "Act I revised", "closing the inspector must save its dirty draft before hiding it");
check(renderer.root.findAllByProps({ "aria-label": "Canvas Plot inspector" }).length === 0, "the inspector may close after its draft has persisted");

await act(async () => {
  node(2).props.onClick({ stopPropagation() {} });
  await flush();
});
act(() => renderer.root.findByProps({ "aria-label": "Block category" }).props.onChange({ currentTarget: { value: "handoff-safe" } }));
const commandsBeforeHandoff = commands.length;
await act(async () => {
  await flushPendingProjectSaves({ commitActiveField: true });
  await flush();
});
check(commands.length === commandsBeforeHandoff + 1, "the project-save barrier must flush a dirty Canvas Plot inspector");
check(commands.at(-1)?.kind === "update_node" && commands.at(-1)?.group_label === "handoff-safe", "the handoff barrier must persist the latest keyed inspector revision");
check(renderer.root.findAllByType("button").every((button) => text(button) !== "REVERT DRAFT"), "a completed handoff flush must leave no orphaned dirty inspector revision");

act(() => renderer.root.findByProps({ "aria-label": "Block summary" }).props.onChange({ currentTarget: { value: "Serialize selection during create" } }));
await act(async () => {
  renderer.root.findByProps({ "aria-label": "Add Canvas Plot block" }).props.onClick();
  renderer.root.findByProps({ "data-canvas-frame-id": 10 }).props.onClick({ stopPropagation() {} });
  await flush();
});
check(commands.at(-2)?.kind === "update_node" && commands.at(-1)?.kind === "create_node", "a compound create must serialize the dirty inspector save before its command");
check(renderer.root.findByType("output").props["data-node"] === 3, "a foreign selection click during a compound save must not overwrite the command's created selection");

const commandsBeforeViewportChange = commands.length;
await act(async () => {
  renderer.root.findByProps({ "aria-label": "Pan Canvas Plot right" }).props.onClick();
  await flush();
});
const savedView = projectSettings.get(7)?.canvas_plot_view as { zoom?: number; cx?: number; cy?: number } | undefined;
check(commands.length === commandsBeforeViewportChange, "viewport persistence must remain outside the revision-bound Canvas Plot command stream");
check(savedView?.cx === 92 && savedView.cy === -8 && savedView.zoom === 1, "viewport controls must persist the project-owned canvas_plot_view setting");

deferSettings(8);
await act(async () => {
  renderer.update(tree(8));
  await Promise.resolve();
});
check(board().props["data-viewport-ready"] === "false", "a switched board must remain interaction-locked while its own viewport settings are pending");
check(board().props["data-center-x"] === 0 && board().props["data-center-y"] === 0, "a switched board must not display the previous project's viewport while hydration is pending");
await act(async () => {
  resolveDeferredSettings?.({ settings: clone(projectSettings.get(8) ?? {}) });
  deferredSettingsProject = null;
  deferredSettings = null;
  resolveDeferredSettings = null;
  await flush();
});
check(board().props["data-center-x"] === 900 && board().props["data-center-y"] === 450 && board().props["data-zoom"] === 2, "switching projects must hydrate B's viewport rather than retaining A's settings");
check(board().props["data-viewport-ready"] === "true", "project B must not become viewport-ready until its own settings resolve");
check(renderer.root.findAll((item) => item.props["data-canvas-node-id"] === 101).length === 1, "switching projects must replace the board with B's owned entities");

await act(async () => {
  node(101).props.onClick({ stopPropagation() {} });
  await flush();
});
act(() => renderer.root.findByProps({ "aria-label": "Block title" }).props.onChange({ currentTarget: { value: "Unsaved deleted block" } }));
const externallyChanged = clone(snapshots.get(8)!);
externallyChanged.nodes = externallyChanged.nodes.filter((candidate) => candidate.id !== 101);
revisionCounter += 1;
externallyChanged.revision = revisionCounter.toString(16).padStart(64, "0");
snapshots.set(8, externallyChanged);
await act(async () => { await emitCanvasChange(8); });
check(renderer.root.findAllByProps({ "aria-label": "Canvas Plot inspector" }).length === 0, "an externally deleted selected entity must no longer render a stale inspector");
const revertOrphan = renderer.root.findAllByType("button").find((button) => text(button) === "REVERT DRAFT");
check(revertOrphan, "an externally deleted dirty entity must expose an explicit Revert Draft escape hatch");
act(() => revertOrphan.props.onClick());
check(renderer.root.findAllByType("button").every((button) => text(button) !== "REVERT DRAFT"), "reverting an orphaned draft must clear its project-save blocker");
check(renderer.root.findByType("output").props["data-node"] === "", "reverting an orphaned draft must also clear the dead selection context");

await act(async () => {
  node(102).props.onClick({ stopPropagation() {} });
  await flush();
});
act(() => renderer.root.findByProps({ "aria-label": "Block summary" }).props.onChange({ currentTarget: { value: "Save through unexpected unmount" } }));
const commandsBeforeUnmount = commands.length;
await act(async () => {
  renderer.unmount();
  await flush();
});
check(commands.length === commandsBeforeUnmount + 1, "a dirty inspector must finish its owned save if the panel unmounts unexpectedly");
check(commands.at(-1)?.kind === "update_node" && commands.at(-1)?.body === "Save through unexpected unmount", "unmount preservation must write the latest draft without UI state");
await flushPendingProjectSaves({ commitActiveField: true });
check(listeners.size === 0, "unmount must release Canvas Plot live-event subscriptions");

console.log(`${assertions} Canvas Plot panel assertions passed.`);

for (const handle of process._getActiveHandles()) {
  if (handle instanceof MessagePort) handle.unref();
}
