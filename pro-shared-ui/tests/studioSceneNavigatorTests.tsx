import { MessagePort } from "node:worker_threads";
import { act, create, type ReactTestInstance, type ReactTestRenderer } from "react-test-renderer";
import type { EventMessage, SceneDTO } from "@logosforge/ui-contracts";
import type { ApiClient } from "../src/adapters/api";
import type { PlatformAdapter } from "../src/adapters/platform";
import { StudioProvider } from "../src/adapters/StudioProvider";
import { useSelection } from "../src/adapters/selection";
import {
  StudioSceneNavigator,
  filterStudioNavigatorScenes,
} from "../src/components/shell/StudioSceneNavigator";

let assertions = 0;
function check(condition: unknown, message: string): asserts condition {
  assertions += 1;
  if (!condition) throw new Error(message);
}

function renderedText(node: ReactTestInstance): string {
  return node.children.map((child) => typeof child === "string" ? child : renderedText(child)).join("");
}

interface Deferred<T> {
  promise: Promise<T>;
  resolve(value: T): void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((next) => { resolve = next; });
  return { promise, resolve };
}

function scene(
  id: number,
  title: string,
  sortOrder: number,
  orderIndex: number,
  extras: Partial<SceneDTO> = {},
): SceneDTO {
  return {
    id,
    title,
    summary: "",
    synopsis: "",
    goal: "",
    conflict: "",
    outcome: "",
    beat: "",
    act: "",
    chapter: "",
    plotline: "",
    color_label: "",
    tags: [],
    content: "",
    sort_order: sortOrder,
    order_index: orderIndex,
    character_ids: [],
    place_ids: [],
    who_knows_what: "",
    ...extras,
  };
}

const scenesA = [
  scene(30, "Crossing", 2, 3, { act: "Act Two", beat: "Midpoint" }),
  scene(20, "Opening", 0, 2, { act: "Act One", chapter: "Chapter One" }),
  scene(10, "Prelude", 0, 1, { act: "Act One", chapter: "Chapter One" }),
];

const pureRows = filterStudioNavigatorScenes(scenesA, "midpoint");
check(pureRows.length === 1 && pureRows[0]?.scene.id === 30, "pure filter should include beat metadata");
check(
  filterStudioNavigatorScenes(scenesA, "").map((row) => row.scene.id).join(",") === "10,20,30",
  "pure projection should match Manuscript sort_order/id ordering",
);
check(scenesA.map((item) => item.id).join(",") === "30,20,10", "sorting must not mutate the resource list");

const initialLoad = deferred<SceneDTO[]>();
const subscriptions = new Map<number, (event: EventMessage) => void>();
const dataByProject = new Map<number, SceneDTO[]>([
  [1, scenesA],
  [2, [scene(99, "Second project only", 0, 1)]],
]);
let firstRead = true;
let nextReadError: Error | null = null;
let reads = 0;
const api = {
  listScenes: (projectId: number) => {
    reads += 1;
    if (firstRead && projectId === 1) {
      firstRead = false;
      return initialLoad.promise;
    }
    if (nextReadError) {
      const failure = nextReadError;
      nextReadError = null;
      return Promise.reject(failure);
    }
    return Promise.resolve([...(dataByProject.get(projectId) ?? [])]);
  },
  subscribe: (projectId: number, listener: (event: EventMessage) => void) => {
    subscriptions.set(projectId, listener);
    return () => {
      if (subscriptions.get(projectId) === listener) subscriptions.delete(projectId);
    };
  },
} as unknown as ApiClient;
const platform = { isDesktop: false } as PlatformAdapter;

let publishSelection: ReturnType<typeof useSelection>["setSelection"] = () => {};
function SelectionBridge() {
  const { setSelection } = useSelection();
  publishSelection = setSelection;
  return null;
}

let searchCalls = 0;
const openCalls: number[] = [];
let openScene: (sceneId: number) => Promise<boolean> = async (sceneId) => {
  openCalls.push(sceneId);
  return true;
};
const onOpenScene = (sceneId: number) => openScene(sceneId);

function tree(projectId: number, disabled = false) {
  return (
    <StudioProvider services={{ api, platform }} projectId={projectId}>
      <SelectionBridge />
      <StudioSceneNavigator
        disabled={disabled}
        onOpenScene={onOpenScene}
        onSearch={() => { searchCalls += 1; }}
      />
    </StudioProvider>
  );
}

let renderer!: ReactTestRenderer;
act(() => { renderer = create(tree(1)); });
check(
  renderer.root.findByProps({ role: "status" }).children.join("") === "Loading scenes…",
  "initial unresolved resource should expose a loading status",
);

await act(async () => {
  initialLoad.resolve([...scenesA]);
  await initialLoad.promise;
  await Promise.resolve();
});
act(() => { publishSelection({ sceneId: 20, text: "", section: "Manuscript" }); });

const sceneButtons = () => renderer.root.findAll(
  (node) => node.type === "button" && typeof node.props["data-scene-id"] === "number",
);
check(
  sceneButtons().map((button) => button.props["data-scene-id"]).join(",") === "10,20,30",
  "mounted rows should use deterministic manuscript ordering",
);
const openingButton = renderer.root.findByProps({ "data-scene-id": 20 });
check(openingButton.props["aria-current"] === "location", "selection scene should be exposed as the current location");
check(
  openingButton.props["aria-label"] === "Open scene 2: Opening",
  "scene action should expose its canonical position and title",
);
check(
  renderer.root.findByProps({ "aria-label": "3 project scenes" }).children.join("") === "3",
  "heading should expose the full project scene count",
);

act(() => { renderer.root.findByType("input").props.onChange({ currentTarget: { value: "midpoint" } }); });
check(
  sceneButtons().length === 1 && sceneButtons()[0]?.props["data-scene-id"] === 30,
  "mounted filter should search structural metadata",
);
act(() => { renderer.root.findByType("input").props.onChange({ currentTarget: { value: "absent" } }); });
check(
  renderer.root.findAllByProps({ role: "status" }).some((node) => node.children.join("") === "No matching scenes"),
  "empty filter result should be announced",
);
act(() => { renderer.root.findByType("input").props.onChange({ currentTarget: { value: "" } }); });

act(() => { renderer.root.findByProps({ className: "lf-studio-scene-search-action" }).props.onClick(); });
check(searchCalls === 1, "optional project-search action should call its host callback");
act(() => { renderer.update(tree(1, true)); });
const lifecycleBlockedRow = renderer.root.findByProps({ "data-scene-id": 10 });
check(
  lifecycleBlockedRow.props["aria-disabled"] === true && lifecycleBlockedRow.props.disabled === undefined,
  "host lifecycle guard should keep scene rows focusable but inoperable",
);
act(() => {
  lifecycleBlockedRow.props.onClick();
  renderer.root.findByProps({ className: "lf-studio-scene-search-action" }).props.onClick();
});
check(openCalls.length === 0 && searchCalls === 1, "host lifecycle guard should block scene and search actions");
act(() => { renderer.update(tree(1)); });

const heldOpen = deferred<boolean>();
openScene = (sceneId) => {
  openCalls.push(sceneId);
  return heldOpen.promise;
};
act(() => { renderer.root.findByProps({ "data-scene-id": 30 }).props.onClick(); });
const heldRow = renderer.root.findByProps({ "data-scene-id": 30 });
check(
  heldRow.props["aria-disabled"] === true && heldRow.props.disabled === undefined,
  "pending activation should retain a focusable row with aria-disabled semantics",
);
check(heldRow.props["data-opening"] === true, "pending row should expose its opening state");
act(() => { renderer.root.findByProps({ "data-scene-id": 10 }).props.onClick(); });
check(openCalls.join(",") === "30", "pending activation guard should reject a second scene click");

await act(async () => {
  heldOpen.resolve(false);
  await heldOpen.promise;
  await Promise.resolve();
});
check(
  renderer.root.findAllByProps({ role: "alert" }).some((node) => renderedText(node).includes("stayed closed")),
  "a host-declined navigation should be announced without changing selection",
);
check(
  renderer.root.findByProps({ "data-scene-id": 20 }).props["aria-current"] === "location",
  "declined navigation should preserve the prior active scene",
);
act(() => {
  renderer.root.findAllByProps({ role: "alert" })
    .find((node) => renderedText(node).includes("stayed closed"))
    ?.findByProps({ "aria-label": "Dismiss scene navigation error" }).props.onClick();
});

openScene = async (sceneId) => {
  openCalls.push(sceneId);
  throw new Error("simulated handoff failure");
};
await act(async () => {
  renderer.root.findByProps({ "data-scene-id": 10 }).props.onClick();
  await Promise.resolve();
  await Promise.resolve();
});
check(
  renderer.root.findAllByProps({ role: "alert" }).some((node) => renderedText(node).includes("simulated handoff failure")),
  "a rejected host navigation should surface its failure",
);

dataByProject.set(1, [
  scene(10, "Prelude revised", 0, 1),
  scene(20, "Opening", 1, 2),
]);
act(() => {
  subscriptions.get(1)?.({
    id: 1,
    event: "scene_changed",
    project_id: 1,
    data: { scene_id: 10 },
    ts: Date.now(),
  });
});
await act(async () => {
  await new Promise((resolve) => setTimeout(resolve, 140));
  await Promise.resolve();
});
check(
  renderer.root.findByProps({ "data-scene-id": 10 }).props["aria-label"] === "Open scene 1: Prelude revised",
  "live scene event should refresh the canonical rows",
);
check(reads >= 2, "live scene event should perform a new scene read");

nextReadError = new Error("temporary scene read failure");
act(() => {
  subscriptions.get(1)?.({
    id: 2,
    event: "scenes_changed",
    project_id: 1,
    data: {},
    ts: Date.now(),
  });
});
await act(async () => {
  await new Promise((resolve) => setTimeout(resolve, 140));
  await Promise.resolve();
});
const refreshAlert = renderer.root.findAllByProps({ role: "alert" })
  .find((node) => renderedText(node).includes("temporary scene read failure"));
check(Boolean(refreshAlert), "live refresh failure should be visible while canonical rows remain mounted");
check(sceneButtons().length === 2, "refresh failure should retain the last canonical rows");
await act(async () => {
  refreshAlert!.findByType("button").props.onClick();
  await Promise.resolve();
  await Promise.resolve();
});
check(
  !renderer.root.findAllByProps({ role: "alert" }).some((node) => renderedText(node).includes("temporary scene read failure")),
  "retry should clear a transient resource error",
);

const staleOpen = deferred<boolean>();
openScene = (sceneId) => {
  openCalls.push(sceneId);
  return staleOpen.promise;
};
act(() => { renderer.root.findByProps({ "data-scene-id": 10 }).props.onClick(); });
await act(async () => {
  renderer.update(tree(2));
  await Promise.resolve();
  await Promise.resolve();
});
check(
  sceneButtons().length === 1 && sceneButtons()[0]?.props["data-scene-id"] === 99,
  "project identity change should replace, not retain, the previous project's rows",
);
check(renderer.root.findByType("input").props.value === "", "project identity change should reset the local filter");
await act(async () => {
  staleOpen.resolve(false);
  await staleOpen.promise;
  await Promise.resolve();
});
check(
  !renderer.root.findAllByProps({ role: "alert" }).some((node) => renderedText(node).includes("stayed closed")),
  "a stale activation result must not write into the replacement project",
);
check(
  renderer.root.findByProps({ "data-scene-id": 99 }).props["aria-disabled"] === undefined,
  "replacement project must not inherit the old activation lock",
);

act(() => { renderer.unmount(); });
console.log(`${assertions} Studio scene navigator assertions passed.`);

for (const handle of process._getActiveHandles()) {
  if (handle instanceof MessagePort) handle.unref();
}
