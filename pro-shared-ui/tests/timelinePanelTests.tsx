import { MessagePort } from "node:worker_threads";
import { act, create, type ReactTestInstance, type ReactTestRenderer } from "react-test-renderer";
import type {
  EventMessage,
  TimelineCommandDTO,
  TimelineCommandReceiptDTO,
  TimelineCommandResultDTO,
  TimelineModeProjectionDTO,
  TimelineSnapshotDTO,
} from "@logosforge/ui-contracts";
import type { ApiClient } from "../src/adapters/api";
import { ApiRequestError, ApiRequestTimeoutError } from "../src/adapters/httpApiClient";
import type { PlatformAdapter } from "../src/adapters/platform";
import { StudioProvider } from "../src/adapters/StudioProvider";
import { useSelection } from "../src/adapters/selection";
import { TimelinePanel } from "../src/components/spatialcanvas/TimelinePanel";
import { TimelineModeProjection } from "../src/components/spatialcanvas/TimelineModeProjection";

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

function snapshot(
  revision: string,
  orderMode: "structural" | "custom" = "structural",
  projectId = 7,
): TimelineSnapshotDTO {
  return {
    project_id: projectId,
    revision: revision.repeat(64),
    order_mode: orderMode,
    lanes: [{ id: 10, name: "Main", color_label: "blue", order_index: 0, collapsed: false, event_count: 2 }],
    events: [
      {
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
      },
      {
        id: 102,
        order_index: 2,
        title: "Promise",
        structural_number: "1.1.2",
        act: "Act I",
        chapter: "One",
        plotline: "Main",
        color_label: "blue",
        lane_id: 10,
        time_of_day: "Noon",
        location: "Bridge",
        duration_minutes: 3,
        character_states: [],
      },
    ],
    links: [{
      id: 502,
      source_scene_id: 103,
      target_scene_id: 104,
      link_type: "echo",
      color_label: "violet",
      label: "Dormant echo",
      created_at: "2026-10-07T09:00:00Z",
    }],
    structure_links: [
      {
        id: 601,
        source_scene_id: 102,
        target_type: "chapter",
        target_ref: "Deleted chapter",
        target_exists: false,
        created_at: "2026-10-07T10:00:00Z",
      },
      {
        id: 603,
        source_scene_id: 103,
        target_type: "act",
        target_ref: "Act I",
        target_exists: true,
        created_at: "2026-10-07T09:00:00Z",
      },
    ],
    off_timeline: [
      { id: 103, title: "Aftermath", structural_number: "1.1.3", act: "Act I", chapter: "One" },
      { id: 104, title: "Foreshadow", structural_number: "1.1.4", act: "Act I", chapter: "One" },
    ],
    story_flow: {
      points: [
        {
          scene_id: 101,
          order_index: 1,
          tension_value: 2,
          tension_source: "content",
          scene_type: "dialogue",
          dialogue_ratio: 0.75,
          action_ratio: 0.1,
        },
        {
          scene_id: 102,
          order_index: 2,
          tension_value: 3,
          tension_source: "beat",
          scene_type: "mixed",
          dialogue_ratio: 0.4,
          action_ratio: 0.55,
        },
      ],
      warnings: [{
        start_scene_id: 101,
        end_scene_id: 102,
        scene_ids: [101, 102],
        reason: "monotone_low",
      }],
    },
    mode_projection: projectId === 8
      ? { kind: "novel" }
      : {
        kind: "screenplay",
        scenes: [
          {
            scene_id: 101,
            interior_exterior: "EXT",
            cinematic_pacing: "measured",
            dramatic_turn: "A boat arrives",
            emotional_turn: "Hope",
            objective: "Secure passage",
            conflict: "The harbor is closed",
            turning_point: "The gate opens",
            emotional_shift: "Doubt to resolve",
            visual_beat_count: 3,
          },
          {
            scene_id: 102,
            interior_exterior: "INT",
            cinematic_pacing: "urgent",
            dramatic_turn: "The promise breaks",
            emotional_turn: "Fear",
            objective: "Reach the bridge",
            conflict: "Pursuit",
            turning_point: "The bridge lifts",
            emotional_shift: "Resolve to fear",
            visual_beat_count: 4,
          },
        ],
      },
  };
}

function emptySeriesSnapshot(projectId = 9): TimelineSnapshotDTO {
  return {
    ...snapshot("y", "structural", projectId),
    lanes: [],
    events: [],
    links: [],
    structure_links: [],
    off_timeline: [],
    story_flow: { points: [], warnings: [] },
    mode_projection: {
      kind: "series",
      episodes: [{
        episode_id: 901,
        order_index: 1,
        season_id: 90,
        season: "Season One",
        episode_number: 1,
        title: "Pilot",
        cliffhanger: "The signal returns",
        scene_ids: [],
        active_arcs: [],
        setup_arc_ids: [],
        payoff_arc_ids: [],
      }],
      arc_chains: [],
      unassigned_scene_ids: [],
    },
  };
}

let serverSnapshot = snapshot("a");
let timelineReads = 0;
let conflictNext = true;
let pendingResultRefetch: Deferred<TimelineSnapshotDTO> | null = null;
const commands: TimelineCommandDTO[] = [];
const commandKeys: string[] = [];
let revisionCode = "c".charCodeAt(0);
let ambiguousExecutionsRemaining = 0;
let receiptMissesRemaining = 0;
let receiptChecks = 0;
const receiptRequests: Array<{ key: string; command: TimelineCommandDTO }> = [];
const listeners = new Set<(event: EventMessage) => void>();

function nextRevision(): string {
  revisionCode += 1;
  return String.fromCharCode(revisionCode).repeat(64);
}

function resultFor(command: TimelineCommandDTO): TimelineCommandResultDTO {
  const next = structuredClone(serverSnapshot);
  next.revision = nextRevision();
  let createdLinkId: number | null = null;
  let createdStructureLinkId: number | null = null;
  let affectedLinkIds: number[] = [];
  let affectedStructureLinkIds: number[] = [];
  if (command.kind === "set_order_mode") next.order_mode = command.mode;
  if (command.kind === "create_link") {
    createdLinkId = 501;
    affectedLinkIds = [createdLinkId];
    next.links.push({
      id: createdLinkId,
      source_scene_id: command.source_scene_id,
      target_scene_id: command.target_scene_id,
      link_type: command.link_type ?? "custom",
      color_label: command.color_label ?? "amber",
      label: command.label ?? "",
      created_at: "2026-10-07T10:10:00Z",
    });
  }
  if (command.kind === "update_link") {
    const link = next.links.find((candidate) => candidate.id === command.link_id)!;
    if (command.link_type != null) link.link_type = command.link_type;
    if (command.color_label != null) link.color_label = command.color_label;
    if (command.label != null) link.label = command.label;
    affectedLinkIds = [command.link_id];
  }
  if (command.kind === "create_structure_link") {
    createdStructureLinkId = 602;
    affectedStructureLinkIds = [createdStructureLinkId];
    next.structure_links.push({
      id: createdStructureLinkId,
      source_scene_id: command.source_scene_id,
      target_type: command.target_type,
      target_ref: command.target_ref,
      target_exists: true,
      created_at: "2026-10-07T10:12:00Z",
    });
  }
  serverSnapshot = next;
  return {
    timeline: structuredClone(next),
    replayed: false,
    applied_revision: next.revision,
    changed: true,
    affected_scene_ids: [],
    affected_link_ids: affectedLinkIds,
    affected_structure_link_ids: affectedStructureLinkIds,
    created_link_id: createdLinkId,
    created_structure_link_id: createdStructureLinkId,
  };
}

const api = {
  getTimeline: async (projectId: number) => {
    timelineReads += 1;
    if (projectId === 9) return emptySeriesSnapshot(projectId);
    if (projectId !== 7) return snapshot("z", "structural", projectId);
    if (pendingResultRefetch) return pendingResultRefetch.promise;
    return structuredClone(serverSnapshot);
  },
  executeTimelineCommand: async (_projectId: number, command: TimelineCommandDTO, idempotencyKey: string): Promise<TimelineCommandResultDTO> => {
    commands.push(structuredClone(command));
    commandKeys.push(idempotencyKey);
    if (conflictNext) {
      conflictNext = false;
      serverSnapshot = snapshot("b");
      throw new ApiRequestError("POST", "/api/projects/7/timeline/commands", 409, "stale", "timeline_conflict");
    }
    if (ambiguousExecutionsRemaining > 0) {
      ambiguousExecutionsRemaining -= 1;
      throw new ApiRequestTimeoutError("POST", "/api/projects/7/timeline/commands", 1000);
    }
    if (command.kind === "set_order_mode") {
      serverSnapshot = snapshot("c", command.mode);
      pendingResultRefetch = deferred<TimelineSnapshotDTO>();
      return {
        timeline: structuredClone(serverSnapshot),
        replayed: false,
        applied_revision: serverSnapshot.revision,
        changed: true,
        affected_scene_ids: [],
        affected_link_ids: [],
        affected_structure_link_ids: [],
        created_link_id: null,
        created_structure_link_id: null,
      };
    }
    return resultFor(command);
  },
  getTimelineCommandReceipt: async (_projectId: number, key: string, command: TimelineCommandDTO): Promise<TimelineCommandReceiptDTO> => {
    receiptChecks += 1;
    receiptRequests.push({ key, command: structuredClone(command) });
    if (receiptMissesRemaining > 0) {
      receiptMissesRemaining -= 1;
      throw new ApiRequestError("GET", "/api/projects/7/timeline/commands/receipt", 404, "missing", "timeline_receipt_not_found");
    }
    return {
      project_id: 7,
      request_digest: "d".repeat(64),
      command_kind: command.kind,
      expected_revision: command.expected_revision,
      applied_revision: serverSnapshot.revision,
      original_changed: true,
      original_affected_scene_ids: [],
      original_affected_link_ids: [],
      original_affected_structure_link_ids: [],
      original_created_link_id: null,
      original_created_structure_link_id: null,
      committed_at: "2026-10-07T10:15:00Z",
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
for (const eventName of ["project_data_changed", "characters_changed", "psyke_changed"] as const) {
  const readsBeforeEvent = timelineReads;
  act(() => {
    listeners.forEach((listener) => listener({
      id: readsBeforeEvent,
      event: eventName,
      project_id: 7,
      data: {},
      ts: Date.now(),
    }));
  });
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 140));
    await Promise.resolve();
  });
  check(
    timelineReads === readsBeforeEvent + 1,
    `${eventName} must refresh the mounted mode projection`,
  );
}
const flowToggle = () => renderer.root.findByProps({ "aria-label": "Toggle Timeline story flow" });
check(flowToggle().props["aria-pressed"] === true, "the Story Flow ribbon must be visible by default");
check(renderer.root.findByProps({ "aria-label": "Timeline story flow" }), "the Story Flow ribbon must expose a stable accessible region");
check(
  renderer.root.findAll((node) => node.props["data-flow-scene-id"] != null).length === serverSnapshot.events.length,
  "the Story Flow ribbon must render one heat cell per Timeline event",
);
const openingFlowCell = renderer.root.findByProps({ "data-flow-scene-id": 101 });
check(
  openingFlowCell.props["aria-label"].includes("tension 2.0 out of 10, low")
    && openingFlowCell.props["aria-label"].includes("dialogue scene"),
  "flow cells must name both the numeric tension and semantic scene type instead of relying on color",
);
check(
  renderedText(openingFlowCell).includes("2.0") && renderedText(openingFlowCell).includes("LOW") && renderedText(openingFlowCell).includes("DIALOGUE"),
  "flow cells must visibly repeat their numeric and semantic meaning",
);
check(
  renderedText(renderer.root.findByProps({ "aria-label": "Timeline Story Pulse" })).includes("AVG 2.5/10")
    && renderedText(renderer.root.findByProps({ "aria-label": "Timeline Story Pulse" })).includes("1 WARNING"),
  "Story Pulse must summarize curve values and warning count",
);
check(
  renderer.root.findByProps({ "aria-label": "Pacing warning: low tension plateau from Opening to Promise" }),
  "pacing warning spans must expose a readable reason and affected scene range",
);
check(
  renderedText(renderer.root.findByProps({ "aria-label": "Timeline mode lens" })).includes("MODE LENS · SCREENPLAY")
    && renderedText(renderer.root.findByProps({ "aria-label": "Timeline mode lens" })).includes("7 visual beats")
    && renderedText(renderer.root.findByProps({ "aria-label": "Timeline mode lens" })).includes("2 objectives"),
  "the mode lens must expose compact, meaningful screenplay facets",
);
check(
  renderer.root.findByProps({ "data-timeline-board-scroll": "true" })
    .findAllByProps({ "aria-label": "Timeline mode lens" }).length === 1,
  "a populated Timeline must keep its mode lens inside the scrollable board so short docks cannot cover event controls",
);
check(
  renderer.root.findByProps({ "aria-label": "Scene type for Opening: dialogue" }),
  "event cards must expose a textual scene-type marker",
);
act(() => { flowToggle().props.onClick(); });
check(flowToggle().props["aria-pressed"] === false, "the Flow toggle must hide the ribbon");
check(renderer.root.findAllByProps({ "aria-label": "Timeline story flow" }).length === 0, "the hidden Flow ribbon must leave no stale visual region");
check(
  renderer.root.findAllByProps({ "aria-label": "Scene type for Opening: dialogue" }).length === 0,
  "the hidden Flow view must also remove per-card scene-type labels",
);
act(() => { flowToggle().props.onClick(); });
check(flowToggle().props["aria-pressed"] === true, "the Flow toggle must restore the ribbon");
check(renderer.root.findByProps({ "aria-label": "Lane for Opening" }).props.value === "10", "event cards must expose persisted lane membership");
check(
  renderedText(renderer.root.findByProps({ "aria-label": "Structure relationships for Promise" })).includes("⚠"),
  "event cards must expose dangling structure relationships with a visible warning",
);
act(() => {
  renderer.root.findAllByType("button").find((button) => renderedText(button).startsWith("RELATIONSHIPS ·"))?.props.onClick();
});
check(renderer.root.findByProps({ "aria-label": "Edit relationship 502" }), "the all-relationships view must keep dormant off-Timeline links editable");
check(renderedText(renderer.root).includes("Aftermath → Foreshadow"), "dormant relationship rows must preserve their directed endpoints");
act(() => {
  renderer.root.findAllByType("button").find((button) => renderedText(button) === "CLOSE")?.props.onClick();
});

const laneNameInput = () => renderer.root.findByProps({ "aria-label": "Name for lane Main" });
act(() => {
  laneNameInput().props.onChange({ currentTarget: { value: "Draft lane rename" } });
});
check(laneNameInput().props.value === "Draft lane rename", "lane rename drafts must render before they are saved");

act(() => {
  renderer.root.findAllByProps({ title: "Select this event for Timeline-aware tools" })
    .find((button) => renderedText(button).includes("Opening"))?.props.onClick();
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

await act(async () => {
  renderer.root.findAllByType("button").find((button) => renderedText(button) === "START LINK")?.props.onClick();
  await Promise.resolve();
});
check(
  renderer.root.findByProps({ "aria-label": "Opening is the relationship source" }),
  "starting a relationship must visibly retain the selected source event",
);
check(
  renderer.root.findByProps({ "aria-label": "Timeline relationship editor" }).props.style.maxHeight === 92,
  "target-picking mode must keep the relationship editor compact enough for short dock cards to remain reachable",
);
check(
  !renderedText(renderer.root.findByProps({ "aria-label": "Timeline relationship editor" })).includes("EVENT LINKS"),
  "target-picking mode must defer relationship management rows instead of covering the target board",
);
act(() => {
  const event: { currentTarget: { value: string } | null } = { currentTarget: { value: "setup_payoff" } };
  renderer.root.findByProps({ "aria-label": "New relationship type" }).props.onChange(event);
  // React only guarantees currentTarget during the callback. State updaters may
  // run after it has been cleared, as they do in the packaged renderer.
  event.currentTarget = null;
  renderer.root.findByProps({ "aria-label": "New relationship label" }).props.onChange({ currentTarget: { value: "Clue returns" } });
});

await act(async () => {
  renderer.root.findByProps({ "aria-label": "Use Promise as relationship target" }).props.onClick();
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
});
const createLinkCommand = commands.find((command) => command.kind === "create_link");
check(
  createLinkCommand?.kind === "create_link"
    && createLinkCommand.source_scene_id === 101
    && createLinkCommand.target_scene_id === 102
    && createLinkCommand.link_type === "setup_payoff",
  "the two-step source-to-target interaction must create a typed directed relationship",
);
check(
  renderer.root.findAllByType("text").some((node) => renderedText(node).includes("setup payoff →")),
  "active relationship endpoints must render a visible typed line label",
);

act(() => {
  renderer.root.findByProps({ "aria-label": "New structure target" }).props.onChange({ currentTarget: { value: "Act I" } });
});
await act(async () => {
  renderer.root.findByProps({ "aria-label": "Add structure relationship" }).props.onClick();
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
});
check(
  commands.some((command) => command.kind === "create_structure_link" && command.target_ref === "Act I"),
  "the relationship workspace must add a selected event-to-structure relationship",
);
check(
  renderedText(renderer.root.findByProps({ "aria-label": "Structure relationships for Opening" })).includes("Act I"),
  "new structure relationships must render as per-event chips",
);

act(() => {
  renderer.root.findByProps({ "aria-label": "Edit relationship 501" }).props.onClick();
});
act(() => {
  renderer.root.findByProps({ "aria-label": "Type for relationship 501" }).props.onChange({ currentTarget: { value: "dependency" } });
});
ambiguousExecutionsRemaining = 1;
receiptMissesRemaining = 1;
const recoveryCommandStart = commands.length;
const recoveryReceiptStart = receiptChecks;
await act(async () => {
  const save = renderer.root.findAllByType("button").find((button) => (
    renderedText(button) === "SAVE" && button.parent?.findAllByProps({ "aria-label": "Type for relationship 501" }).length
  ));
  save?.props.onClick();
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
});
check(commands.length === recoveryCommandStart + 2, "an ambiguous Timeline write may resend the exact command at most once after a proven receipt miss");
check(commandKeys.at(-1) === commandKeys.at(-2), "the one allowed Timeline resend must reuse the exact idempotency key");
check(receiptChecks === recoveryReceiptStart + 1, "ambiguous delivery must check the durable receipt before resending");
check(serverSnapshot.links.find((link) => link.id === 501)?.link_type === "dependency", "the recovered relationship edit must publish its authoritative result");

act(() => {
  renderer.root.findByProps({ "aria-label": "Edit relationship 501" }).props.onClick();
});
act(() => {
  renderer.root.findByProps({ "aria-label": "Label for relationship 501" }).props.onChange({ currentTarget: { value: "Receipt only" } });
});
ambiguousExecutionsRemaining = 2;
receiptMissesRemaining = 2;
const lockedCommandStart = commands.length;
await act(async () => {
  const save = renderer.root.findAllByType("button").find((button) => (
    renderedText(button) === "SAVE" && button.parent?.findAllByProps({ "aria-label": "Type for relationship 501" }).length
  ));
  save?.props.onClick();
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
});
check(commands.length === lockedCommandStart + 2, "a second ambiguous response must not trigger a second resend");
const checkReceiptButton = renderer.root.findAllByType("button").find((button) => renderedText(button) === "CHECK RECEIPT");
check(checkReceiptButton, "after one same-key resend and another proven miss, recovery must become receipt-only");
const beforeManualReceipt = commands.length;
receiptMissesRemaining = 1;
await act(async () => {
  checkReceiptButton.props.onClick();
  await Promise.resolve();
  await Promise.resolve();
});
check(commands.length === beforeManualReceipt, "manual receipt-only recovery must never resend the command");
check(renderedText(renderer.root.findByProps({ role: "alert" })).includes("receipt-only"), "receipt-only lock state must be explained accessibly");

const executeCountBeforeProjectSwitch = commands.length;
await act(async () => {
  renderer.update(tree(8));
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
});
check(orderButton()?.props.disabled === false, "an unresolved delivery owned by another project must not lock the active project's Timeline");
check(flowToggle().props["aria-pressed"] === true, "switching projects must restore the Flow ribbon's default-visible state");
check(
  renderedText(renderer.root.findByProps({ "aria-label": "Timeline mode lens" })).includes("MODE LENS · NOVEL")
    && renderedText(renderer.root.findByProps({ "aria-label": "Timeline mode lens" })).includes("BASE PROSE LENS"),
  "project switching must replace the mode lens with the active project's projection",
);
await act(async () => {
  renderer.update(tree(7));
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
});
const restoredReceiptButton = renderer.root.findAllByType("button")
  .find((button) => renderedText(button) === "CHECK RECEIPT");
check(restoredReceiptButton, "returning to the owner project must restore its exact unresolved delivery as receipt-only");
await act(async () => {
  restoredReceiptButton.props.onClick();
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
});
check(commands.length === executeCountBeforeProjectSwitch, "switch-away recovery must resolve through the receipt without invoking execute again");
check(
  receiptRequests.at(-1)?.key === commandKeys.at(-1)
    && JSON.stringify(receiptRequests.at(-1)?.command) === JSON.stringify(commands.at(-1)),
  "restored receipt recovery must preserve the exact original idempotency key and command",
);
check(
  renderer.root.findAllByType("button").every((button) => renderedText(button) !== "CHECK RECEIPT"),
  "a confirmed durable receipt must clear the restored project-owned delivery capability",
);

act(() => { renderer.unmount(); });
check(listeners.size === 0, "unmount must release Timeline live-event subscriptions");

let emptyRenderer!: ReactTestRenderer;
await act(async () => {
  emptyRenderer = create(tree(9));
  await Promise.resolve();
  await Promise.resolve();
});
check(
  renderedText(emptyRenderer.root.findByProps({ "aria-label": "Timeline mode lens" })).includes("MODE LENS · SERIES")
    && renderedText(emptyRenderer.root).includes("No Timeline yet"),
  "an empty Timeline must still expose its mode lens and independent mode metadata",
);
act(() => { emptyRenderer.unmount(); });
check(listeners.size === 0, "the empty Timeline must also release its live-event subscription");

function checkModeProjection(projection: TimelineModeProjectionDTO, expected: string, message: string) {
  let projectionRenderer!: ReactTestRenderer;
  act(() => { projectionRenderer = create(<TimelineModeProjection projection={projection} />); });
  check(renderedText(projectionRenderer.root).includes(expected), message);
  act(() => { projectionRenderer.unmount(); });
}

checkModeProjection({
  kind: "graphic_novel",
  pages: [{
    page_id: 11,
    page_number: 1,
    sequence_id: 2,
    issue_id: 3,
    issue_title: "Issue One",
    density: "explosive",
    rhythm: "fast",
    reveal_timing: "page turn",
    splash_page: true,
    panel_count: 5,
    action_density: 0.8,
    text_load: 22,
    pacing: "cinematic",
    is_silence: false,
    is_action: true,
  }],
  page_turns: [{ setup_page_id: 11, setup_page_number: 1, reveal_page_id: 12, reveal_page_number: 2, reveal_type: "character" }],
}, "1 page-turn reveal", "the graphic-novel lens must summarize page-turn staging");

checkModeProjection({
  kind: "stage_script",
  scenes: [{
    scene_id: 101,
    order_index: 1,
    act: "Act I",
    title: "Opening",
    entrances_exits: [
      { character: "Mara", type: "entrance", moment_order: 1, cue_text: "Mara enters" },
      { character: "Mara", type: "exit", moment_order: 3, cue_text: "Mara exits" },
    ],
    cues: [{ type: "light", text: "Blue wash", moment_order: 2 }],
    offstage_events: "Bell rings",
    has_offstage_events: true,
    props: ["Letter"],
    emotional_pressure: "conflict",
  }],
}, "1 entrance · 1 exit · 1 cue", "the stage-script lens must summarize blocking and cues");

checkModeProjection({
  kind: "series",
  episodes: [{
    episode_id: 21,
    order_index: 1,
    season_id: 4,
    season: "Season 1",
    episode_number: 1,
    title: "Pilot",
    cliffhanger: "The door opens",
    scene_ids: [101, 102],
    active_arcs: [{ arc_id: 31, title: "Homecoming", scope: "season", status: "active" }],
    setup_arc_ids: [31],
    payoff_arc_ids: [],
  }],
  arc_chains: [{ arc_id: 31, title: "Homecoming", scope: "season", setup_episode_id: 21, payoff_episode_id: 28, setup_order_index: 1, payoff_order_index: 8 }],
  unassigned_scene_ids: [103],
}, "1 cliffhanger · 1 setup · 0 payoffs", "the series lens must summarize episodic hooks and arc motion");

console.log(`${assertions} Timeline panel assertions passed.`);

for (const handle of process._getActiveHandles()) {
  if (handle instanceof MessagePort) handle.unref();
}
