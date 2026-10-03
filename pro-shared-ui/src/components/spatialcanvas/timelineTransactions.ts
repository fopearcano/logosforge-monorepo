import type {
  TimelineCommandDTO,
  TimelineLaneDTO,
  TimelineOrderMode,
  TimelineSnapshotDTO,
} from "@logosforge/ui-contracts";

export type TimelineCommandIntent =
  | { kind: "create_lane"; name: string; colorLabel?: string; index?: number }
  | {
    kind: "update_lane";
    laneId: number;
    name?: string;
    colorLabel?: string;
    collapsed?: boolean;
    index?: number;
  }
  | { kind: "move_lane"; laneId: number; delta: -1 | 1 }
  | { kind: "delete_lane"; laneId: number }
  | { kind: "place_event"; sceneId: number; laneId: number | null; index?: number }
  | { kind: "move_event"; sceneId: number; delta: -1 | 1 }
  | { kind: "remove_event"; sceneId: number }
  | { kind: "set_order_mode"; mode: TimelineOrderMode };

export type TimelineCommandPlanResult =
  | { command: TimelineCommandDTO; error?: never }
  | { command?: never; error: string };

export function timelineIntentCanRetry(intent: TimelineCommandIntent): boolean {
  return intent.kind !== "delete_lane" && intent.kind !== "remove_event";
}

export function describeTimelineIntent(intent: TimelineCommandIntent): string {
  if (intent.kind === "create_lane") return `create lane “${intent.name.trim()}”`;
  if (intent.kind === "move_lane") {
    return `move lane #${intent.laneId} one step ${intent.delta < 0 ? "up" : "down"}`;
  }
  if (intent.kind === "delete_lane") return `delete lane #${intent.laneId}`;
  if (intent.kind === "place_event") {
    return `place scene #${intent.sceneId} ${intent.laneId == null ? "as Unassigned" : `in lane #${intent.laneId}`}`;
  }
  if (intent.kind === "move_event") {
    return `move scene #${intent.sceneId} one step ${intent.delta < 0 ? "earlier" : "later"}`;
  }
  if (intent.kind === "remove_event") return `remove scene #${intent.sceneId} from the Timeline`;
  if (intent.kind === "set_order_mode") return `switch to ${intent.mode} order`;

  const changes = [
    intent.name != null ? `rename to “${intent.name.trim()}”` : "",
    intent.colorLabel != null ? `use color ${intent.colorLabel || "Auto"}` : "",
    intent.collapsed != null ? (intent.collapsed ? "collapse" : "expand") : "",
    intent.index != null ? `move to position ${intent.index + 1}` : "",
  ].filter(Boolean).join(", ");
  return `${changes || "update"} lane #${intent.laneId}`;
}

function comparable(value: string): string {
  return value.trim().toLocaleLowerCase();
}

function lane(snapshot: TimelineSnapshotDTO, laneId: number): TimelineLaneDTO | undefined {
  return snapshot.lanes.find((item) => item.id === laneId);
}

function sceneExists(snapshot: TimelineSnapshotDTO, sceneId: number): boolean {
  return snapshot.events.some((event) => event.id === sceneId)
    || snapshot.off_timeline.some((scene) => scene.id === sceneId);
}

/**
 * Bind a UI intent to the latest authoritative Timeline revision. Validation is
 * intentionally repeated by the core; this planner only keeps stale/missing
 * choices from being sent after a live refresh.
 */
export function planTimelineCommand(
  snapshot: TimelineSnapshotDTO,
  intent: TimelineCommandIntent,
): TimelineCommandPlanResult {
  const expected_revision = snapshot.revision;

  if (intent.kind === "create_lane") {
    const name = intent.name.trim();
    if (!name) return { error: "Lane name cannot be empty." };
    if (snapshot.lanes.some((item) => comparable(item.name) === comparable(name))) {
      return { error: `A lane named “${name}” already exists.` };
    }
    if (intent.index != null && (intent.index < 0 || intent.index > snapshot.lanes.length)) {
      return { error: "That lane position is no longer available." };
    }
    return {
      command: {
        kind: "create_lane",
        expected_revision,
        name,
        ...(intent.colorLabel?.trim() ? { color_label: intent.colorLabel.trim() } : {}),
        ...(intent.index != null ? { index: intent.index } : {}),
      },
    };
  }

  if (intent.kind === "update_lane") {
    const current = lane(snapshot, intent.laneId);
    if (!current) return { error: "That lane is no longer available." };
    const name = intent.name == null ? undefined : intent.name.trim();
    if (intent.name != null && !name) return { error: "Lane name cannot be empty." };
    if (name && snapshot.lanes.some((item) => (
      item.id !== current.id && comparable(item.name) === comparable(name)
    ))) {
      return { error: `A lane named “${name}” already exists.` };
    }
    if (intent.index != null && (intent.index < 0 || intent.index >= snapshot.lanes.length)) {
      return { error: "That lane position is no longer available." };
    }
    if (
      name == null
      && intent.colorLabel == null
      && intent.collapsed == null
      && intent.index == null
    ) return { error: "Choose a lane change first." };
    return {
      command: {
        kind: "update_lane",
        expected_revision,
        lane_id: current.id,
        ...(name != null ? { name } : {}),
        ...(intent.colorLabel != null ? { color_label: intent.colorLabel.trim() } : {}),
        ...(intent.collapsed != null ? { collapsed: intent.collapsed } : {}),
        ...(intent.index != null ? { index: intent.index } : {}),
      },
    };
  }

  if (intent.kind === "move_lane") {
    const index = snapshot.lanes.findIndex((item) => item.id === intent.laneId);
    if (index < 0) return { error: "That lane is no longer available." };
    const next = index + intent.delta;
    if (next < 0 || next >= snapshot.lanes.length) {
      return { error: `That lane is already ${intent.delta < 0 ? "first" : "last"}.` };
    }
    return {
      command: {
        kind: "update_lane",
        expected_revision,
        lane_id: intent.laneId,
        index: next,
      },
    };
  }

  if (intent.kind === "delete_lane") {
    if (!lane(snapshot, intent.laneId)) return { error: "That lane is no longer available." };
    return {
      command: {
        kind: "delete_lane",
        expected_revision,
        lane_id: intent.laneId,
      },
    };
  }

  if (intent.kind === "place_event") {
    if (!sceneExists(snapshot, intent.sceneId)) {
      return { error: "That scene is no longer available." };
    }
    if (intent.laneId != null && !lane(snapshot, intent.laneId)) {
      return { error: "That lane is no longer available." };
    }
    const alreadyPresent = snapshot.events.some((event) => event.id === intent.sceneId);
    const maxIndex = alreadyPresent
      ? Math.max(snapshot.events.length - 1, 0)
      : snapshot.events.length;
    if (intent.index != null && (intent.index < 0 || intent.index > maxIndex)) {
      return { error: "That Timeline position is no longer available." };
    }
    return {
      command: {
        kind: "place_event",
        expected_revision,
        scene_id: intent.sceneId,
        lane_id: intent.laneId,
        ...(intent.index != null ? { index: intent.index } : {}),
      },
    };
  }

  if (intent.kind === "move_event") {
    const index = snapshot.events.findIndex((event) => event.id === intent.sceneId);
    if (index < 0) return { error: "That event is no longer on the Timeline." };
    const next = index + intent.delta;
    if (next < 0 || next >= snapshot.events.length) {
      return { error: `That event is already ${intent.delta < 0 ? "first" : "last"}.` };
    }
    const event = snapshot.events[index]!;
    return {
      command: {
        kind: "place_event",
        expected_revision,
        scene_id: event.id,
        lane_id: event.lane_id,
        index: next,
      },
    };
  }

  if (intent.kind === "remove_event") {
    if (!snapshot.events.some((event) => event.id === intent.sceneId)) {
      return { error: "That event is no longer on the Timeline." };
    }
    return {
      command: {
        kind: "remove_event",
        expected_revision,
        scene_id: intent.sceneId,
      },
    };
  }

  return {
    command: {
      kind: "set_order_mode",
      expected_revision,
      mode: intent.mode,
    },
  };
}

/**
 * Accessible one-step alternative to pointer drag. The returned intent stays
 * relative so `planTimelineCommand` can recompute its target after the UI's
 * authoritative preflight refresh.
 */
export function moveTimelineEventIntent(
  snapshot: TimelineSnapshotDTO,
  sceneId: number,
  delta: -1 | 1,
): TimelineCommandIntent | null {
  const index = snapshot.events.findIndex((event) => event.id === sceneId);
  if (index < 0) return null;
  const next = Math.max(0, Math.min(index + delta, snapshot.events.length - 1));
  if (next === index) return null;
  return {
    kind: "move_event",
    sceneId,
    delta,
  };
}
