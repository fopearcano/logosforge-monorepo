import type { TimelineSnapshotDTO } from "@logosforge/ui-contracts";
import {
  describeTimelineIntent,
  moveTimelineEventIntent,
  planTimelineCommand,
  timelineIntentCanRetry,
} from "../src/components/spatialcanvas/timelineTransactions";

function check(value: unknown, message: string): asserts value {
  if (!value) throw new Error(message);
}

const snapshot: TimelineSnapshotDTO = {
  project_id: 7,
  revision: "a".repeat(64),
  order_mode: "structural",
  lanes: [
    { id: 10, name: "Main Plot", color_label: "blue", order_index: 0, collapsed: false, event_count: 1 },
    { id: 20, name: "Romance", color_label: "red", order_index: 1, collapsed: false, event_count: 1 },
  ],
  events: [
    {
      id: 101,
      order_index: 1,
      title: "Opening",
      structural_number: "1.1.1",
      act: "Act 1",
      chapter: "Chapter 1",
      plotline: "Main Plot",
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
      act: "Act 1",
      chapter: "Chapter 1",
      plotline: "Romance",
      color_label: "red",
      lane_id: 20,
      time_of_day: "",
      location: "",
      duration_minutes: 0,
      character_states: [],
    },
  ],
  off_timeline: [
    { id: 103, title: "Reversal", structural_number: "1.2.1", act: "Act 1", chapter: "Chapter 2" },
  ],
};

{
  const planned = planTimelineCommand(snapshot, { kind: "create_lane", name: "  Mystery  ", colorLabel: "purple", index: 1 });
  check(planned.command?.kind === "create_lane", "valid lane creation must produce a command");
  check(planned.command.expected_revision === snapshot.revision, "commands must bind to the latest snapshot revision");
  check(planned.command.name === "Mystery" && planned.command.color_label === "purple" && planned.command.index === 1, "lane creation must normalize UI intent");
}

{
  const planned = planTimelineCommand(snapshot, { kind: "create_lane", name: "MAIN PLOT" });
  check(!planned.command && planned.error.includes("already exists"), "duplicate lane names must be rejected before transport");
}

{
  const planned = planTimelineCommand(snapshot, { kind: "update_lane", laneId: 20, name: "  Relationship  ", collapsed: true });
  check(planned.command?.kind === "update_lane", "valid lane updates must produce a command");
  check(planned.command.name === "Relationship" && planned.command.collapsed === true, "lane edits must preserve requested fields");
}

{
  const planned = planTimelineCommand(snapshot, { kind: "delete_lane", laneId: 999 });
  check(!planned.command && planned.error.includes("no longer available"), "deleted lanes must be caught after a refresh");
}

{
  const planned = planTimelineCommand(snapshot, { kind: "place_event", sceneId: 103, laneId: 10, index: 2 });
  check(planned.command?.kind === "place_event", "off-Timeline scenes must be placeable");
  check(planned.command.scene_id === 103 && planned.command.lane_id === 10 && planned.command.index === 2, "placement must retain membership and custom-order intent");
}

{
  const planned = planTimelineCommand(snapshot, { kind: "remove_event", sceneId: 103 });
  check(!planned.command && planned.error.includes("no longer on"), "only current events may be removed");
}

{
  const planned = planTimelineCommand(snapshot, { kind: "set_order_mode", mode: "custom" });
  check(planned.command?.kind === "set_order_mode" && planned.command.mode === "custom", "order-mode commands must use the canonical mode field");
}

{
  const intent = moveTimelineEventIntent(snapshot, 102, -1);
  check(intent?.kind === "move_event" && intent.delta === -1, "keyboard movement must preserve relative intent until it binds to the latest snapshot");
  check(moveTimelineEventIntent(snapshot, 101, -1) === null, "movement beyond the first event must be a no-op");
  check(snapshot.events.map((event) => event.id).join(",") === "101,102", "planning must never mutate the authoritative snapshot");
}

{
  const intent = moveTimelineEventIntent(snapshot, 102, -1);
  check(intent?.kind === "move_event", "event movement must produce a relative intent");
  const concurrentlyChanged: TimelineSnapshotDTO = {
    ...snapshot,
    revision: "b".repeat(64),
    events: [
      { ...snapshot.events[0]!, id: 104, title: "Concurrent insert", order_index: 1 },
      { ...snapshot.events[0]!, order_index: 2 },
      { ...snapshot.events[1]!, order_index: 3, lane_id: 10, plotline: "Main Plot" },
    ],
  };
  const planned = planTimelineCommand(concurrentlyChanged, intent);
  check(planned.command?.kind === "place_event", "a relative event move must bind to the refreshed snapshot");
  check(planned.command.index === 1, "a relative event move must advance exactly one position after a concurrent insert");
  check(planned.command.lane_id === 10, "a relative event move must preserve the lane from the refreshed snapshot");
  check(planned.command.expected_revision === concurrentlyChanged.revision, "a relative event move must bind to the refreshed revision");
}

{
  const concurrentlyChanged: TimelineSnapshotDTO = {
    ...snapshot,
    revision: "c".repeat(64),
    lanes: [
      { id: 5, name: "Concurrent lane", color_label: "green", order_index: 0, collapsed: false, event_count: 0 },
      { ...snapshot.lanes[0]!, order_index: 1 },
      { ...snapshot.lanes[1]!, order_index: 2 },
    ],
  };
  const planned = planTimelineCommand(concurrentlyChanged, { kind: "move_lane", laneId: 20, delta: -1 });
  check(planned.command?.kind === "update_lane", "a relative lane move must plan an update command");
  check(planned.command.index === 1, "a relative lane move must advance exactly one position after a concurrent insert");
  check(planned.command.expected_revision === concurrentlyChanged.revision, "a relative lane move must bind to the refreshed revision");
}

{
  check(
    !timelineIntentCanRetry({ kind: "delete_lane", laneId: 10 })
      && !timelineIntentCanRetry({ kind: "remove_event", sceneId: 101 }),
    "destructive Timeline intents must require a fresh confirmation after conflict",
  );
  check(
    timelineIntentCanRetry({ kind: "move_event", sceneId: 102, delta: -1 }),
    "non-destructive semantic Timeline intents may be retried after review",
  );
  check(
    describeTimelineIntent({ kind: "move_event", sceneId: 102, delta: -1 }).includes("one step earlier"),
    "retry messaging must expose the retained semantic intent",
  );
}

console.log("timeline transaction tests passed");
