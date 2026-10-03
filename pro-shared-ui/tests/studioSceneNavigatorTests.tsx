import { MessagePort } from "node:worker_threads";
import { act, create, type ReactTestInstance, type ReactTestRenderer } from "react-test-renderer";
import type { EventMessage, StoryStructureDTO, StoryStructurePlacementDTO } from "@logosforge/ui-contracts";
import type { ApiClient } from "../src/adapters/api";
import { ApiRequestError } from "../src/adapters/httpApiClient";
import type { PlatformAdapter } from "../src/adapters/platform";
import { StudioProvider } from "../src/adapters/StudioProvider";
import { useSelection } from "../src/adapters/selection";
import {
  StudioSceneNavigator,
  filterStudioStoryStructure,
} from "../src/components/shell/StudioSceneNavigator";
import { StructurePanel } from "../src/components/manuscript/StructurePanel";

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

const structureA: StoryStructureDTO = {
  project_id: 1,
  revision: "a".repeat(64),
  chapter_level: true,
  scene_count: 4,
  orphan_count: 0,
  acts: [
    {
      name: "Act One",
      number: "1",
      unassigned: false,
      scene_count: 3,
      chapters: [
        {
          name: "Chapter Alpha",
          number: "1.1",
          unassigned: false,
          scene_count: 2,
          scenes: [
            { id: 10, title: "Prelude", beat: "Setup", episode_id: null, number: "1.1.1", order_index: 1, is_orphan: false },
            { id: 20, title: "Opening", beat: "Catalyst", episode_id: null, number: "1.1.2", order_index: 2, is_orphan: false },
          ],
        },
        {
          name: "Chapter Beta",
          number: "1.2",
          unassigned: false,
          scene_count: 1,
          scenes: [
            { id: 25, title: "Threshold", beat: "Turn", episode_id: null, number: "1.2.1", order_index: 3, is_orphan: false },
          ],
        },
      ],
    },
    {
      name: "Act Two",
      number: "2",
      unassigned: false,
      scene_count: 1,
      chapters: [
        {
          name: "Chapter Gamma",
          number: "2.1",
          unassigned: false,
          scene_count: 1,
          scenes: [
            { id: 30, title: "Crossing", beat: "Midpoint", episode_id: 2, number: "2.1.1", order_index: 4, is_orphan: false },
          ],
        },
      ],
    },
  ],
};

const structureB: StoryStructureDTO = {
  project_id: 2,
  revision: "b".repeat(64),
  chapter_level: false,
  scene_count: 2,
  orphan_count: 1,
  acts: [
    {
      name: "Act A",
      number: "1",
      unassigned: false,
      scene_count: 1,
      chapters: [
        {
          name: "Internal One",
          number: "1.1",
          unassigned: false,
          scene_count: 1,
          scenes: [
            { id: 99, title: "Second project only", beat: "", episode_id: null, number: "1.1", order_index: 1, is_orphan: false },
          ],
        },
      ],
    },
    {
      name: "Unassigned",
      number: "",
      unassigned: true,
      scene_count: 1,
      chapters: [
        {
          name: "Unassigned",
          number: "",
          unassigned: true,
          scene_count: 1,
          scenes: [
            { id: 100, title: "Flat companion", beat: "", episode_id: null, number: "", order_index: 2, is_orphan: true },
          ],
        },
      ],
    },
  ],
};

const midpointProjection = filterStudioStoryStructure(structureA, "midpoint");
check(
  midpointProjection.acts.length === 1
    && midpointProjection.acts[0]?.act.name === "Act Two"
    && midpointProjection.acts[0]?.chapters[0]?.chapter.name === "Chapter Gamma"
    && midpointProjection.acts[0]?.chapters[0]?.scenes[0]?.id === 30,
  "scene matches should retain their Act and Chapter ancestors",
);
check(
  filterStudioStoryStructure(structureA, "act one").sceneCount === 3,
  "an Act match should include all of its descendants",
);
check(
  filterStudioStoryStructure(structureA, "chapter alpha").acts[0]?.chapters[0]?.scenes.map((scene) => scene.id).join(",") === "10,20",
  "a Chapter match should include all of its descendants",
);
check(
  filterStudioStoryStructure(structureA, "").acts.flatMap((act) => act.chapters.flatMap((chapter) => chapter.scenes)).map((scene) => scene.id).join(",") === "10,20,25,30",
  "the projection must preserve core array order instead of regrouping or sorting scenes",
);
check(
  structureA.acts[0]?.chapters[0]?.scenes.map((scene) => scene.id).join(",") === "10,20",
  "filtering must not mutate the core DTO",
);

const initialLoad = deferred<StoryStructureDTO>();
const subscriptions = new Map<number, (event: EventMessage) => void>();
const dataByProject = new Map<number, StoryStructureDTO>([
  [1, structureA],
  [2, structureB],
]);
let firstRead = true;
let nextReadError: Error | null = null;
let structureReads = 0;
let listSceneReads = 0;
const placementCalls: Array<{ projectId: number; sceneId: number; body: StoryStructurePlacementDTO }> = [];
let nextPlacementError: Error | null = null;
let nextPlacementDeferred: Deferred<StoryStructureDTO> | null = null;
const api = {
  getStoryStructure: (projectId: number) => {
    structureReads += 1;
    if (firstRead && projectId === 1) {
      firstRead = false;
      return initialLoad.promise;
    }
    if (nextReadError) {
      const failure = nextReadError;
      nextReadError = null;
      return Promise.reject(failure);
    }
    const value = dataByProject.get(projectId);
    if (!value) return Promise.reject(new Error(`No structure for project ${projectId}`));
    return Promise.resolve(structuredClone(value));
  },
  listScenes: () => {
    listSceneReads += 1;
    throw new Error("StudioSceneNavigator must not derive structure from listScenes");
  },
  placeScene: async (projectId: number, sceneId: number, body: StoryStructurePlacementDTO) => {
    placementCalls.push({ projectId, sceneId, body });
    if (nextPlacementDeferred) {
      const pending = nextPlacementDeferred;
      nextPlacementDeferred = null;
      return pending.promise;
    }
    if (nextPlacementError) {
      const failure = nextPlacementError;
      nextPlacementError = null;
      throw failure;
    }
    const value = dataByProject.get(projectId);
    if (!value) throw new Error(`No structure for project ${projectId}`);
    return structuredClone(value);
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

const scrollCalls: number[] = [];
const moveFocusCalls: number[] = [];
let renderer!: ReactTestRenderer;
act(() => {
  renderer = create(tree(1), {
    createNodeMock(element) {
      const sceneId = element.props["data-scene-id"];
      const moveSceneId = element.props["data-scene-move-id"];
      if (element.type === "button" && typeof sceneId === "number") {
        return { scrollIntoView: () => scrollCalls.push(sceneId) };
      }
      if (element.type === "button" && typeof moveSceneId === "number") {
        return { focus: () => moveFocusCalls.push(moveSceneId) };
      }
      return {};
    },
  });
});
check(
  renderer.root.findByProps({ role: "status" }).children.join("") === "Loading story structure…",
  "initial unresolved structure should expose a loading status",
);

await act(async () => {
  initialLoad.resolve(structuredClone(structureA));
  await initialLoad.promise;
  await Promise.resolve();
});
check(listSceneReads === 0, "the navigator must consume the core story-structure endpoint, never listScenes");

const sceneButtons = () => renderer.root.findAll(
  (node) => node.type === "button" && typeof node.props["data-scene-id"] === "number",
);
const moveHandles = () => renderer.root.findAll(
  (node) => node.type === "button" && typeof node.props["data-scene-move-id"] === "number",
);
const moveHandle = (sceneId: number) => renderer.root.findByProps({ "data-scene-move-id": sceneId });
const groupToggles = (level: "act" | "chapter") => renderer.root.findAllByProps({
  "data-scene-group-toggle": level,
});

check(
  renderer.root.findByProps({ "aria-label": "4 project scenes" }).children.join("") === "4",
  "heading should expose the authoritative core scene count",
);
check(groupToggles("act").length === 2, "chapter-aware mode should render one disclosure per core Act");
check(groupToggles("chapter").length === 3, "chapter-aware mode should render one disclosure per core Chapter");
check(
  groupToggles("act")[0]?.props["aria-expanded"] === true
    && groupToggles("act")[1]?.props["aria-expanded"] === false,
  "initial expansion should open only the first structural branch",
);
check(
  groupToggles("chapter")[0]?.props["aria-expanded"] === true
    && groupToggles("chapter")[1]?.props["aria-expanded"] === false,
  "initial expansion should open only the first Chapter in that branch",
);
check(
  groupToggles("act")[0]?.props["aria-controls"]
    && groupToggles("chapter")[0]?.props["aria-controls"],
  "every group disclosure should identify the native list it controls",
);
check(
  renderer.root.findByProps({ "data-scene-id": 10 }).props["aria-label"] === "Open scene 1.1.1: Prelude",
  "scene actions should announce their core-owned structural number and title",
);
check(moveHandles().length === 4, "each canonical scene should expose a separate move handle");
check(
  moveHandle(20).props["aria-label"] === "Move scene 1.1.2: Opening"
    && moveHandle(20).props["aria-pressed"] === false,
  "the move handle should be independently named and expose its idle keyboard state",
);

const keyEvent = (key: string) => ({
  key,
  preventDefault() {},
  stopPropagation() {},
});
act(() => { moveHandle(20).props.onKeyDown(keyEvent(" ")); });
check(
  moveHandle(20).props["aria-pressed"] === true
    && renderer.root.findAllByProps({ role: "status" }).some((node) => renderedText(node).includes("Use Up and Down")),
  "Space should lift a scene and announce the keyboard placement controls",
);
act(() => { moveHandle(10).props.onKeyDown(keyEvent("Enter")); });
check(
  moveHandle(20).props["aria-pressed"] === true
    && moveHandle(10).props["aria-pressed"] === false,
  "an aria-disabled non-owner handle must not replace the active keyboard move",
);
act(() => { moveHandle(20).props.onKeyDown(keyEvent("ArrowDown")); });
check(
  renderer.root.findAllByProps({ role: "status" }).some((node) => renderedText(node).includes("Chapter Beta")),
  "ArrowDown should stage the adjacent canonical position across a Chapter boundary",
);
const heldPlacement = deferred<StoryStructureDTO>();
nextPlacementDeferred = heldPlacement;
await act(async () => {
  moveHandle(20).props.onKeyDown(keyEvent("Enter"));
  await Promise.resolve();
  await Promise.resolve();
});
check(
  moveHandle(20).props["aria-disabled"] === true
    && moveHandle(20).props["aria-pressed"] === true
    && renderer.root.findAllByProps({ role: "status" }).some((node) => renderedText(node).includes("Saving the new position")),
  "the move owner should remain visibly locked while its placement transaction is pending",
);
act(() => {
  moveHandle(20).props.onKeyDown(keyEvent("ArrowDown"));
  moveHandle(20).props.onKeyDown(keyEvent("Escape"));
  moveHandle(20).props.onKeyDown(keyEvent("Enter"));
});
check(
  placementCalls.length === 1
    && moveHandle(20).props["aria-pressed"] === true
    && renderer.root.findAllByProps({ role: "status" }).some((node) => renderedText(node).includes("Saving the new position")),
  "the aria-disabled move owner must ignore move, cancel, and resubmit keys while its PUT is pending",
);
const structureAfterKeyboardMove = structuredClone(structureA);
structureAfterKeyboardMove.revision = "d".repeat(64);
const keyboardMovedScene = structureAfterKeyboardMove.acts[0]!.chapters[0]!.scenes.pop()!;
keyboardMovedScene.number = "1.2.2";
keyboardMovedScene.order_index = 3;
structureAfterKeyboardMove.acts[0]!.chapters[0]!.scene_count -= 1;
structureAfterKeyboardMove.acts[0]!.chapters[1]!.scenes.push(keyboardMovedScene);
structureAfterKeyboardMove.acts[0]!.chapters[1]!.scene_count += 1;
structureAfterKeyboardMove.acts[0]!.chapters[1]!.scenes[0]!.order_index = 2;
dataByProject.set(1, structureAfterKeyboardMove);
moveFocusCalls.length = 0;
await act(async () => {
  heldPlacement.resolve(structuredClone(structureAfterKeyboardMove));
  await heldPlacement.promise;
  await Promise.resolve();
  await Promise.resolve();
});
await act(async () => { await new Promise((resolve) => setTimeout(resolve, 1)); });
check(
  placementCalls.length === 1
    && placementCalls[0]?.projectId === 1
    && placementCalls[0]?.sceneId === 20
    && placementCalls[0]?.body.expected_revision === structureA.revision
    && placementCalls[0]?.body.act === "Act One"
    && placementCalls[0]?.body.chapter === "Chapter Beta"
    && placementCalls[0]?.body.index === 1
    && !("episode_id" in placementCalls[0]!.body),
  "keyboard movement should commit one revision-guarded placement while preserving episode ownership",
);
check(
  groupToggles("chapter")[1]?.props["aria-expanded"] === true
    && renderer.root.findByProps({ "data-scene-drop-id": 20 }).parent?.props.id === groupToggles("chapter")[1]?.props["aria-controls"],
  "the placement response should reveal the moved scene in its previously collapsed destination Chapter",
);
check(
  moveFocusCalls.join(",") === "20",
  "focus should be restored only after the reparented move handle mounts in the refreshed structure",
);

act(() => { moveHandle(20).props.onKeyDown(keyEvent("Enter")); });
act(() => { moveHandle(20).props.onKeyDown(keyEvent("ArrowDown")); });
check(
  renderer.root.findAllByProps({ role: "status" }).some((node) => renderedText(node).includes("episode boundary"))
    && placementCalls.length === 1,
  "keyboard movement should announce and reject a relative move across a Series episode boundary",
);
act(() => { moveHandle(20).props.onKeyDown(keyEvent("Escape")); });

const transferStore = new Map<string, string>();
const dataTransfer = {
  effectAllowed: "none",
  dropEffect: "none",
  setData(type: string, value: string) { transferStore.set(type, value); },
  getData(type: string) { return transferStore.get(type) ?? ""; },
};
act(() => {
  moveHandle(10).props.onDragStart({ dataTransfer, preventDefault() {} });
});
const pointerEvent = () => ({
  dataTransfer,
  clientY: 18,
  currentTarget: { getBoundingClientRect: () => ({ top: 0, height: 20 }) },
  preventDefault() {},
});
act(() => { renderer.root.findByProps({ "data-scene-drop-id": 25 }).props.onDragOver(pointerEvent()); });
check(
  renderer.root.findByProps({ "data-scene-drop-id": 25 }).props["data-drop-edge"] === "after",
  "pointer movement should expose the staged drop edge",
);
await act(async () => {
  renderer.root.findByProps({ "data-scene-drop-id": 25 }).props.onDrop(pointerEvent());
  moveHandle(10).props.onDragEnd();
  await Promise.resolve();
  await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 1));
});
check(
  placementCalls.length === 2
    && placementCalls[1]?.sceneId === 10
    && placementCalls[1]?.body.chapter === "Chapter Beta"
    && placementCalls[1]?.body.index === 1,
  "pointer movement should commit through the same transactional placement contract",
);
check(
  renderer.root.findAllByProps({ role: "status" }).some((node) => renderedText(node).includes("Moved Prelude")),
  "the trailing drag-end event must not overwrite a successful placement status with cancellation",
);

const staleTransferStore = new Map<string, string>();
const staleDataTransfer = {
  effectAllowed: "none",
  dropEffect: "none",
  setData(type: string, value: string) { staleTransferStore.set(type, value); },
  getData(type: string) { return staleTransferStore.get(type) ?? ""; },
};
act(() => {
  moveHandle(20).props.onDragStart({ dataTransfer: staleDataTransfer, preventDefault() {} });
});
const changedDuringDrag = structuredClone(structureA);
changedDuringDrag.revision = "c".repeat(64);
dataByProject.set(1, changedDuringDrag);
act(() => {
  subscriptions.get(1)?.({
    id: 100,
    event: "scene_changed",
    project_id: 1,
    data: { scene_id: 25 },
    ts: Date.now(),
  });
});
await act(async () => {
  await new Promise((resolve) => setTimeout(resolve, 140));
  await Promise.resolve();
});
check(
  renderer.root.findAllByProps({ role: "status" }).some((node) => renderedText(node).includes("cancelled because the story structure changed"))
    && renderer.root.findByProps({ "data-scene-drop-id": 20 }).props["data-drag-source"] === undefined,
  "a structure revision change should cancel and announce an in-flight local drag",
);
await act(async () => {
  renderer.root.findByProps({ "data-scene-drop-id": 25 }).props.onDrop({
    dataTransfer: staleDataTransfer,
    clientY: 18,
    currentTarget: { getBoundingClientRect: () => ({ top: 0, height: 20 }) },
    preventDefault() {},
  });
  await Promise.resolve();
});
check(
  placementCalls.length === 2,
  "a stale drag payload must not silently rebase against the refreshed structure",
);

const structureAfterConflict = structuredClone(changedDuringDrag);
structureAfterConflict.revision = "e".repeat(64);
const externallyMovedScene = structureAfterConflict.acts[0]!.chapters[0]!.scenes.shift()!;
externallyMovedScene.number = "2.1.1";
externallyMovedScene.order_index = 3;
structureAfterConflict.acts[0]!.scene_count -= 1;
structureAfterConflict.acts[0]!.chapters[0]!.scene_count -= 1;
structureAfterConflict.acts[1]!.scene_count += 1;
structureAfterConflict.acts[1]!.chapters[0]!.scene_count += 1;
structureAfterConflict.acts[1]!.chapters[0]!.scenes[0]!.number = "2.1.2";
structureAfterConflict.acts[1]!.chapters[0]!.scenes[0]!.order_index = 4;
structureAfterConflict.acts[1]!.chapters[0]!.scenes.unshift(externallyMovedScene);
dataByProject.set(1, structureAfterConflict);
nextPlacementError = new ApiRequestError(
  "PUT",
  "/api/projects/1/story-structure/scenes/10/placement",
  409,
  "The story structure changed",
  "structure_conflict",
);
moveFocusCalls.length = 0;
act(() => { moveHandle(10).props.onKeyDown(keyEvent("Enter")); });
act(() => { moveHandle(10).props.onKeyDown(keyEvent("ArrowDown")); });
await act(async () => {
  moveHandle(10).props.onKeyDown(keyEvent("Enter"));
  await Promise.resolve();
  await Promise.resolve();
});
await act(async () => { await new Promise((resolve) => setTimeout(resolve, 1)); });
check(
  renderer.root.findAllByProps({ role: "alert" }).some((node) => renderedText(node).includes("changed before this move could be saved")),
  "a revision conflict should remain explicit instead of silently retrying the stale intent",
);
check(
  groupToggles("act")[1]?.props["aria-expanded"] === true
    && groupToggles("chapter")[2]?.props["aria-expanded"] === true
    && renderer.root.findByProps({ "data-scene-drop-id": 10 }).parent?.props.id === groupToggles("chapter")[2]?.props["aria-controls"],
  "a conflict refresh should reveal the source scene in its externally changed structural path",
);
check(
  moveFocusCalls.join(",") === "10",
  `a conflict should restore focus only after the authoritative reparented handle mounts (got ${moveFocusCalls.join(",") || "none"})`,
);

const restoredAfterConflict = structuredClone(changedDuringDrag);
restoredAfterConflict.revision = "f".repeat(64);
dataByProject.set(1, restoredAfterConflict);
act(() => {
  subscriptions.get(1)?.({
    id: 101,
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

act(() => { publishSelection({ sceneId: 20, text: "", section: "Manuscript" }); });
check(
  renderer.root.findByProps({ "data-scene-id": 20 }).props["aria-current"] === "location",
  "selection scene should be exposed as the current location",
);

act(() => { publishSelection({ sceneId: 30, text: "", section: "Manuscript" }); });
await act(async () => { await new Promise((resolve) => setTimeout(resolve, 1)); });
check(
  groupToggles("act")[1]?.props["aria-expanded"] === true
    && groupToggles("chapter")[2]?.props["aria-expanded"] === true,
  "an externally active scene should reveal its complete structural path",
);
check(scrollCalls.includes(30), "active-scene reveal should scroll without moving keyboard focus");

act(() => { publishSelection({ sceneId: 20, text: "", section: "Manuscript" }); });
act(() => { groupToggles("act")[1]?.props.onClick(); });
check(groupToggles("act")[1]?.props["aria-expanded"] === false, "an Act disclosure should collapse its branch");
const filter = () => renderer.root.findByProps({ "aria-label": "Filter project scenes" });
act(() => { filter().props.onChange({ currentTarget: { value: "act two" } }); });
check(
  sceneButtons().map((button) => button.props["data-scene-id"]).join(",") === "30",
  "a matching group should retain all descendant scenes and remove unmatched ancestors",
);
check(
  moveHandle(30).props["aria-disabled"] === true && moveHandle(30).props.draggable === false,
  "filtered projections should keep move handles focusable but disable structural movement",
);
check(
  groupToggles("act")[0]?.props["aria-expanded"] === true
    && groupToggles("act")[0]?.props["aria-disabled"] === true,
  "filtering should force matching groups open as a non-interactive projection",
);
act(() => {
  filter().props.onKeyDown({ key: "Escape", preventDefault() {} });
});
check(filter().props.value === "", "Escape should clear the scene filter");
check(
  groupToggles("act")[1]?.props["aria-expanded"] === false,
  "clearing a filter should restore the writer's pre-filter expansion state",
);

act(() => { filter().props.onChange({ currentTarget: { value: "midpoint" } }); });
const hiddenNotice = renderer.root.findAllByProps({ role: "status" })
  .find((node) => renderedText(node).includes("Current scene hidden by filter"));
check(Boolean(hiddenNotice), "filtering out the active scene should announce that it is hidden");
check(
  renderer.root.findByProps({ "aria-label": "4 project scenes" }).children.join("") === "1/4",
  "filtered count should retain the authoritative project total",
);
act(() => { hiddenNotice!.findByProps({ "aria-label": "Clear scene filter" }).props.onClick(); });
check(filter().props.value === "", "the current-hidden notice should offer a direct clear action");

act(() => { groupToggles("chapter")[0]?.props.onClick(); });
act(() => { groupToggles("act")[0]?.props.onClick(); });
check(
  groupToggles("act")[0]?.props["aria-expanded"] === false
    && groupToggles("chapter")[0]?.props["aria-expanded"] === false,
  "the active scene path should be user-collapsible",
);
act(() => { filter().props.onChange({ currentTarget: { value: "chapter alpha" } }); });
check(
  sceneButtons().map((button) => button.props["data-scene-id"]).join(",") === "10,20",
  "a matching Chapter should keep its scenes in core order",
);
act(() => { filter().props.onChange({ currentTarget: { value: "absent" } }); });
check(
  renderer.root.findAllByProps({ role: "status" }).some((node) => renderedText(node) === "No matching scenes"),
  "an empty filter result should be announced",
);
act(() => { filter().props.onChange({ currentTarget: { value: "" } }); });
check(
  groupToggles("act")[0]?.props["aria-expanded"] === false
    && groupToggles("chapter")[0]?.props["aria-expanded"] === false,
  "filter edits should not mutate a user-collapsed active path",
);

await act(async () => {
  publishSelection({ sceneId: 10, text: "", section: "Manuscript" });
  await new Promise((resolve) => setTimeout(resolve, 1));
});
check(
  groupToggles("act")[0]?.props["aria-expanded"] === true
    && groupToggles("chapter")[0]?.props["aria-expanded"] === true,
  "a genuinely changed scene selection should reveal its path even when the structural path is unchanged",
);
await act(async () => {
  publishSelection({ sceneId: 20, text: "", section: "Manuscript" });
  await new Promise((resolve) => setTimeout(resolve, 1));
});
act(() => { groupToggles("chapter")[0]?.props.onClick(); });
act(() => { groupToggles("act")[0]?.props.onClick(); });

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
  "a pending save-barrier activation should retain a focusable row with aria-disabled semantics",
);
check(heldRow.props["data-opening"] === true, "the target row should expose its pending handoff state");
act(() => { renderer.root.findByProps({ "data-scene-id": 10 }).props.onClick(); });
check(openCalls.join(",") === "30", "the pending handoff guard should reject a second scene click");

await act(async () => {
  heldOpen.resolve(false);
  await heldOpen.promise;
  await Promise.resolve();
});
check(
  renderer.root.findAllByProps({ role: "alert" }).some((node) => renderedText(node).includes("stayed closed")),
  "a host-declined handoff should be announced without changing selection",
);
check(
  renderer.root.findByProps({ "data-scene-id": 20 }).props["aria-current"] === "location",
  "a declined handoff should preserve the prior active scene",
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
  "a rejected host handoff should surface its failure",
);
act(() => {
  renderer.root.findByProps({ "aria-label": "Dismiss scene navigation error" }).props.onClick();
});

const refreshedA = structuredClone(structureA);
refreshedA.acts[0]!.chapters[0]!.scenes[0]!.title = "Prelude revised";
dataByProject.set(1, refreshedA);
act(() => {
  subscriptions.get(1)?.({
    id: 1,
    event: "project_data_changed",
    project_id: 1,
    data: {},
    ts: Date.now(),
  });
});
await act(async () => {
  await new Promise((resolve) => setTimeout(resolve, 140));
  await Promise.resolve();
});
check(
  renderer.root.findByProps({ "data-scene-id": 10 }).props["aria-label"] === "Open scene 1.1.1: Prelude revised",
  "project_data_changed should refresh the core-owned structure",
);
check(structureReads >= 2, "a live structural event should perform a new structure read");
check(listSceneReads === 0, "live refreshes must never fall back to client-side scene grouping");
check(
  groupToggles("act")[0]?.props["aria-expanded"] === false
    && groupToggles("chapter")[0]?.props["aria-expanded"] === false,
  "a same-path structure refetch should preserve a user-collapsed active path",
);

const movedA = structuredClone(refreshedA);
const movedScene = movedA.acts[0]!.chapters[0]!.scenes.pop()!;
movedScene.number = "1.2.2";
movedA.acts[0]!.chapters[0]!.scene_count -= 1;
movedA.acts[0]!.chapters[1]!.scenes.push(movedScene);
movedA.acts[0]!.chapters[1]!.scene_count += 1;
dataByProject.set(1, movedA);
act(() => {
  subscriptions.get(1)?.({
    id: 2,
    event: "scene_changed",
    project_id: 1,
    data: { scene_id: 20 },
    ts: Date.now(),
  });
});
await act(async () => {
  await new Promise((resolve) => setTimeout(resolve, 140));
  await Promise.resolve();
});
check(
  groupToggles("act")[0]?.props["aria-expanded"] === true
    && groupToggles("chapter")[1]?.props["aria-expanded"] === true,
  "a selected scene whose structural path genuinely changes should reveal its new ancestry",
);

nextReadError = new Error("temporary structure read failure");
act(() => {
  subscriptions.get(1)?.({
    id: 3,
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
  .find((node) => renderedText(node).includes("temporary structure read failure"));
check(Boolean(refreshAlert), "a live refresh failure should be visible while canonical rows remain mounted");
check(sceneButtons().length === 4, "a refresh failure should retain the last canonical structure");
await act(async () => {
  refreshAlert!.findByType("button").props.onClick();
  await Promise.resolve();
  await Promise.resolve();
});
check(
  !renderer.root.findAllByProps({ role: "alert" }).some((node) => renderedText(node).includes("temporary structure read failure")),
  "Retry should clear a transient structure error",
);

const staleOpen = deferred<boolean>();
openScene = (sceneId) => {
  openCalls.push(sceneId);
  return staleOpen.promise;
};
act(() => { renderer.root.findByProps({ "data-scene-id": 10 }).props.onClick(); });
act(() => { filter().props.onChange({ currentTarget: { value: "prelude" } }); });
await act(async () => {
  renderer.update(tree(2));
  await Promise.resolve();
  await Promise.resolve();
});
check(
  sceneButtons().map((button) => button.props["data-scene-id"]).join(",") === "99,100",
  "a project identity change should replace, not retain, the previous project's structure",
);
check(filter().props.value === "", "a project identity change should reset the local filter");
check(groupToggles("chapter").length === 0, "chapter-less mode should flatten core Chapter wrappers to Act → Scene");
check(
  renderer.root.findByProps({ "data-scene-id": 99 }).props["data-structure-number"] === "1.1"
    && renderer.root.findByProps({ "data-scene-id": 100 }).props["data-structure-number"] === "",
  "flattened mode should retain core-owned scene numbers and order",
);
check(
  renderer.root.findByProps({ "data-scene-id": 100 }).props["aria-label"] === "Open unnumbered scene: Flat companion"
    && renderedText(renderer.root.findByProps({ "data-scene-id": 100 }).findByProps({ className: "lf-studio-scene-position" })) === "—",
  "an unassigned scene should remain explicitly unnumbered instead of borrowing its global order index",
);
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
  "the replacement project must not inherit the old activation lock",
);

act(() => { renderer.unmount(); });

const switchingStructureApi = {
  ...api,
  getStoryStructure: async (projectId: number) => structuredClone(projectId === 1 ? structureA : structureB),
} as unknown as ApiClient;
let structureRenderer!: ReactTestRenderer;
await act(async () => {
  structureRenderer = create(
    <StudioProvider services={{ api: switchingStructureApi, platform }} projectId={1}>
      <StructurePanel />
    </StudioProvider>,
  );
  await Promise.resolve();
  await Promise.resolve();
});
check(
  renderedText(structureRenderer.root).includes("Prelude")
    && renderedText(structureRenderer.root).includes("Act One"),
  "StructurePanel should render a structure payload owned by the current project",
);
let previousProjectRenderedDuringSwitch = false;
act(() => {
  // Inspect the committed update before passive resource effects clear/refetch
  // it; this is the render where an unguarded hook leaks project A.
  structureRenderer.unstable_flushSync(() => {
    structureRenderer.update(
      <StudioProvider services={{ api: switchingStructureApi, platform }} projectId={2}>
        <StructurePanel />
      </StudioProvider>,
    );
  });
  previousProjectRenderedDuringSwitch = renderedText(structureRenderer.root).includes("Prelude")
    || renderedText(structureRenderer.root).includes("Act One");
});
check(
  !previousProjectRenderedDuringSwitch,
  "StructurePanel must hide the previous project's payload in the identity-change render before resource effects run",
);
await act(async () => {
  await Promise.resolve();
  await Promise.resolve();
});
check(
  renderedText(structureRenderer.root).includes("Second project only")
    && !renderedText(structureRenderer.root).includes("Prelude"),
  "StructurePanel should replace the prior project with the new project's structure after an in-place identity change",
);
act(() => { structureRenderer.unmount(); });

const structurePanelApi = {
  ...api,
  getStoryStructure: async () => structuredClone(structureB),
} as unknown as ApiClient;
await act(async () => {
  structureRenderer = create(
    <StudioProvider services={{ api: structurePanelApi, platform }} projectId={2}>
      <StructurePanel />
    </StudioProvider>,
  );
  await Promise.resolve();
  await Promise.resolve();
});
check(
  structureRenderer.root.findByProps({ "aria-label": "Unnumbered scene" }).children.join("") === "—",
  "StructurePanel must render a blank core number as an explicit unnumbered marker",
);
act(() => { structureRenderer.unmount(); });

console.log(`${assertions} Studio scene navigator assertions passed.`);

for (const handle of process._getActiveHandles()) {
  if (handle instanceof MessagePort) handle.unref();
}
