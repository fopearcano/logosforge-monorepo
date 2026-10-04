import { MessagePort } from "node:worker_threads";
import { act, create, type ReactTestInstance, type ReactTestRenderer } from "react-test-renderer";
import type {
  EventMessage,
  TimelineCommandDTO,
  TimelineCommandResultDTO,
  TimelineSnapshotDTO,
} from "@logosforge/ui-contracts";
import type { ApiClient } from "../src/adapters/api";
import { ApiRequestError } from "../src/adapters/httpApiClient";
import type { PlatformAdapter } from "../src/adapters/platform";
import { StudioProvider } from "../src/adapters/StudioProvider";
import { useSelection } from "../src/adapters/selection";
import { TimelinePanel } from "../src/components/spatialcanvas/TimelinePanel";

let assertions = 0;
function check(value: unknown, message: string): asserts value {
  assertions += 1;
  if (!value) throw new Error(message);
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

function snapshot(revision: string, orderMode: "structural" | "custom" = "structural"): TimelineSnapshotDTO {
  return {
    project_id: 7,
    revision: revision.repeat(64),
    order_mode: orderMode,
    lanes: [{ id: 10, name: "Main", color_label: "blue", order_index: 0, collapsed: false, event_count: 1 }],
    events: [{
      id: 101,
      order_index: 1,
      title: "Opening",
      structural_number: "1.1.1",
      act: "Act I",
      chapter: "One",
      plotline: "Main",
      color_label: "blue",
      lane_id: 10,
      time_of_day: "Morning",
      location: "Harbor",
      duration_minutes: 4,
      character_states: [],
    }],
    off_timeline: [{ id: 102, title: "Aftermath", structural_number: "1.1.2", act: "Act I", chapter: "One" }],
  };
}

let serverSnapshot = snapshot("a");
let timelineReads = 0;
let conflictNext = true;
let pendingResultRefetch: Deferred<TimelineSnapshotDTO> | null = null;
const commands: TimelineCommandDTO[] = [];
const listeners = new Set<(event: EventMessage) => void>();

const api = {
  getTimeline: async () => {
    timelineReads += 1;
    if (pendingResultRefetch) return pendingResultRefetch.promise;
    return structuredClone(serverSnapshot);
  },
  executeTimelineCommand: async (_projectId: number, command: TimelineCommandDTO): Promise<TimelineCommandResultDTO> => {
    commands.push(structuredClone(command));
    if (conflictNext) {
      conflictNext = false;
      serverSnapshot = snapshot("b");
      throw new ApiRequestError("POST", "/api/projects/7/timeline/commands", 409, "stale", "timeline_conflict");
    }
    check(command.kind === "set_order_mode", "retry must preserve the writer's original order-mode intent");
    serverSnapshot = snapshot("c", command.mode);
    pendingResultRefetch = deferred<TimelineSnapshotDTO>();
    return {
      timeline: structuredClone(serverSnapshot),
      replayed: false,
      applied_revision: serverSnapshot.revision,
      changed: true,
      affected_scene_ids: [],
    };
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
  return <output data-selection-scene={selection.sceneId ?? ""} data-selection-section={selection.section ?? ""} />;
}

function tree(projectId = 7) {
  return (
    <StudioProvider services={{ api, platform }} projectId={projectId}>
      <TimelinePanel />
      <SelectionProbe />
    </StudioProvider>
  );
}

let renderer!: ReactTestRenderer;
await act(async () => {
  renderer = create(tree());
  await Promise.resolve();
  await Promise.resolve();
});

check(timelineReads === 1, "the panel must load one coherent Timeline snapshot");
check(renderer.root.findByProps({ "aria-label": "Lane for Opening" }).props.value === "10", "event cards must expose persisted lane membership");

const laneNameInput = () => renderer.root.findByProps({ "aria-label": "Name for lane Main" });
act(() => {
  laneNameInput().props.onChange({ currentTarget: { value: "Draft lane rename" } });
});
check(laneNameInput().props.value === "Draft lane rename", "lane rename drafts must render before they are saved");

act(() => {
  renderer.root.findByProps({ title: "Select this event for Timeline-aware tools" }).props.onClick();
});
const selection = renderer.root.findByType("output");
check(selection.props["data-selection-scene"] === 101 && selection.props["data-selection-section"] === "Timeline", "Timeline selection must publish project-aware scene context");

const orderButton = () => renderer.root.findAllByType("button")
  .find((button) => renderedText(button).startsWith("ORDER ·"));
check(orderButton()?.props["aria-pressed"] === false, "structural order must be announced as inactive custom order");

await act(async () => {
  orderButton()?.props.onClick();
  orderButton()?.props.onClick();
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
});

check(commands.length === 1, "a busy Timeline command must suppress duplicate clicks");
check(commands[0]?.expected_revision === "a".repeat(64), "the command must bind to a freshly fetched revision");
check(timelineReads >= 3, "a conflict must refresh the authoritative Timeline snapshot");
check(laneNameInput().props.value === "Draft lane rename", "preflight and conflict refreshes must not discard an unsaved lane rename");
const retry = renderer.root.findAllByType("button").find((button) => renderedText(button) === "RETRY");
check(retry, "a revision conflict must retain intent behind an explicit retry control");
check(
  renderedText(renderer.root.findByProps({ role: "alert" })).includes("switch to custom order"),
  "a conflict affordance must expose the retained intent before retry",
);

await act(async () => {
  retry.props.onClick();
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
});

check(commands.length === 2, "retry must issue exactly one new command");
check(commands[1]?.expected_revision === "b".repeat(64), "retry must rebind intent to the newly fetched revision");
check(commands[1]?.kind === "set_order_mode" && commands[1].mode === "custom", "retry must preserve the requested semantic change");
check(orderButton()?.props["aria-pressed"] === true, "the command receipt must render immediately while its confirming refetch is still pending");
check(orderButton()?.props.disabled === true, "controls must remain disabled while the confirming refetch is pending");
check(renderer.root.findAllByType("button").every((button) => renderedText(button) !== "RETRY"), "successful retry must clear the conflict affordance");

await act(async () => {
  pendingResultRefetch?.resolve(structuredClone(serverSnapshot));
  pendingResultRefetch = null;
  await Promise.resolve();
  await Promise.resolve();
});
check(orderButton()?.props.disabled === false, "controls must re-enable after the authoritative refetch completes");

act(() => { renderer.unmount(); });
check(listeners.size === 0, "unmount must release Timeline live-event subscriptions");

console.log(`${assertions} Timeline panel assertions passed.`);

for (const handle of process._getActiveHandles()) {
  if (handle instanceof MessagePort) handle.unref();
}
