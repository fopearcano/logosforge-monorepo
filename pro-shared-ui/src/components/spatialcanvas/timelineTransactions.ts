import type {
  TimelineCommandDTO,
  TimelineLaneDTO,
  TimelineLinkType,
  TimelineOrderMode,
  TimelineSnapshotDTO,
  TimelineStructureTargetType,
} from "@logosforge/ui-contracts";

export const TIMELINE_LINK_TYPES: readonly TimelineLinkType[] = [
  "causality",
  "setup_payoff",
  "echo",
  "conflict",
  "dependency",
  "custom",
] as const;

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
  | { kind: "set_order_mode"; mode: TimelineOrderMode }
  | {
    kind: "create_link";
    sourceSceneId: number;
    targetSceneId: number;
    linkType?: TimelineLinkType;
    colorLabel?: string;
    label?: string;
  }
  | {
    kind: "update_link";
    linkId: number;
    linkType?: TimelineLinkType;
    colorLabel?: string;
    label?: string;
  }
  | { kind: "delete_link"; linkId: number }
  | {
    kind: "create_structure_link";
    sourceSceneId: number;
    targetType: TimelineStructureTargetType;
    targetRef: string;
  }
  | {
    kind: "update_structure_link";
    structureLinkId: number;
    targetType?: TimelineStructureTargetType;
    targetRef?: string;
  }
  | { kind: "delete_structure_link"; structureLinkId: number };

export type TimelineCommandPlanResult =
  | { command: TimelineCommandDTO; error?: never }
  | { command?: never; error: string };

export function timelineIntentCanRetry(intent: TimelineCommandIntent): boolean {
  return intent.kind !== "delete_lane"
    && intent.kind !== "remove_event"
    && intent.kind !== "delete_link"
    && intent.kind !== "delete_structure_link";
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
  if (intent.kind === "create_link") {
    return `link scene #${intent.sourceSceneId} to scene #${intent.targetSceneId}`;
  }
  if (intent.kind === "update_link") return `update relationship #${intent.linkId}`;
  if (intent.kind === "delete_link") return `delete relationship #${intent.linkId}`;
  if (intent.kind === "create_structure_link") {
    return `link scene #${intent.sourceSceneId} to ${intent.targetType} “${intent.targetRef.trim()}”`;
  }
  if (intent.kind === "update_structure_link") {
    return `update structure relationship #${intent.structureLinkId}`;
  }
  if (intent.kind === "delete_structure_link") {
    return `delete structure relationship #${intent.structureLinkId}`;
  }

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

function timelineEventExists(snapshot: TimelineSnapshotDTO, sceneId: number): boolean {
  return snapshot.events.some((event) => event.id === sceneId);
}

function structureTargetExists(
  snapshot: TimelineSnapshotDTO,
  targetType: TimelineStructureTargetType,
  targetRef: string,
): boolean {
  const normalized = comparable(targetRef);
  if (!normalized) return false;
  return [...snapshot.events, ...snapshot.off_timeline].some((scene) => (
    comparable(targetType === "act" ? scene.act : scene.chapter) === normalized
  ));
}

function sameUnorderedPair(
  sourceSceneId: number,
  targetSceneId: number,
  otherSourceSceneId: number,
  otherTargetSceneId: number,
): boolean {
  return (sourceSceneId === otherSourceSceneId && targetSceneId === otherTargetSceneId)
    || (sourceSceneId === otherTargetSceneId && targetSceneId === otherSourceSceneId);
}

let timelineFallbackSequence = 0;

/** Create a transport-safe key that remains stable for one delivery/recovery cycle. */
export function createTimelineIdempotencyKey(): string {
  const randomUuid = globalThis.crypto?.randomUUID?.();
  if (randomUuid) return `timeline-ui-${randomUuid}`;
  timelineFallbackSequence += 1;
  return `timeline-ui-${Date.now().toString(36)}-${timelineFallbackSequence.toString(36)}-${Math.random().toString(36).slice(2, 14)}`;
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

  if (intent.kind === "create_link") {
    if (!timelineEventExists(snapshot, intent.sourceSceneId)
      || !timelineEventExists(snapshot, intent.targetSceneId)) {
      return { error: "Both relationship endpoints must still be on the Timeline." };
    }
    if (intent.sourceSceneId === intent.targetSceneId) {
      return { error: "A Timeline event cannot link to itself." };
    }
    if (snapshot.links.some((link) => sameUnorderedPair(
      link.source_scene_id,
      link.target_scene_id,
      intent.sourceSceneId,
      intent.targetSceneId,
    ))) {
      return { error: "Those events already have a Timeline relationship." };
    }
    const linkType = intent.linkType;
    const colorLabel = intent.colorLabel?.trim();
    const label = intent.label?.trim();
    return {
      command: {
        kind: "create_link",
        expected_revision,
        source_scene_id: intent.sourceSceneId,
        target_scene_id: intent.targetSceneId,
        ...(linkType ? { link_type: linkType } : {}),
        ...(colorLabel ? { color_label: colorLabel } : {}),
        ...(label ? { label } : {}),
      },
    };
  }

  if (intent.kind === "update_link") {
    const current = snapshot.links.find((link) => link.id === intent.linkId);
    if (!current) return { error: "That relationship is no longer available." };
    if (intent.linkType == null && intent.colorLabel == null && intent.label == null) {
      return { error: "Choose a relationship change first." };
    }
    const linkType = intent.linkType;
    const colorLabel = intent.colorLabel?.trim();
    const label = intent.label?.trim();
    return {
      command: {
        kind: "update_link",
        expected_revision,
        link_id: current.id,
        ...(intent.linkType != null ? { link_type: linkType! } : {}),
        ...(intent.colorLabel != null ? { color_label: colorLabel ?? "" } : {}),
        ...(intent.label != null ? { label: label ?? "" } : {}),
      },
    };
  }

  if (intent.kind === "delete_link") {
    if (!snapshot.links.some((link) => link.id === intent.linkId)) {
      return { error: "That relationship is no longer available." };
    }
    return {
      command: {
        kind: "delete_link",
        expected_revision,
        link_id: intent.linkId,
      },
    };
  }

  if (intent.kind === "create_structure_link") {
    const targetRef = intent.targetRef.trim();
    if (!timelineEventExists(snapshot, intent.sourceSceneId)) {
      return { error: "That source event is no longer on the Timeline." };
    }
    if (!targetRef) return { error: "Choose an act or chapter first." };
    if (!structureTargetExists(snapshot, intent.targetType, targetRef)) {
      return { error: `That ${intent.targetType} is no longer available.` };
    }
    if (snapshot.structure_links.some((link) => (
      link.source_scene_id === intent.sourceSceneId
      && link.target_type === intent.targetType
      && comparable(link.target_ref) === comparable(targetRef)
    ))) {
      return { error: "That structure relationship already exists." };
    }
    return {
      command: {
        kind: "create_structure_link",
        expected_revision,
        source_scene_id: intent.sourceSceneId,
        target_type: intent.targetType,
        target_ref: targetRef,
      },
    };
  }

  if (intent.kind === "update_structure_link") {
    const current = snapshot.structure_links.find((link) => link.id === intent.structureLinkId);
    if (!current) return { error: "That structure relationship is no longer available." };
    if (intent.targetType == null && intent.targetRef == null) {
      return { error: "Choose a structure relationship change first." };
    }
    const targetType = intent.targetType ?? current.target_type;
    const targetRef = intent.targetRef == null ? current.target_ref : intent.targetRef.trim();
    if (!targetRef) return { error: "Choose an act or chapter first." };
    if (!structureTargetExists(snapshot, targetType, targetRef)) {
      return { error: `That ${targetType} is no longer available.` };
    }
    if (snapshot.structure_links.some((link) => (
      link.id !== current.id
      && link.source_scene_id === current.source_scene_id
      && link.target_type === targetType
      && comparable(link.target_ref) === comparable(targetRef)
    ))) {
      return { error: "That structure relationship already exists." };
    }
    return {
      command: {
        kind: "update_structure_link",
        expected_revision,
        structure_link_id: current.id,
        ...(intent.targetType != null ? { target_type: targetType } : {}),
        ...(intent.targetRef != null ? { target_ref: targetRef } : {}),
      },
    };
  }

  if (intent.kind === "delete_structure_link") {
    if (!snapshot.structure_links.some((link) => link.id === intent.structureLinkId)) {
      return { error: "That structure relationship is no longer available." };
    }
    return {
      command: {
        kind: "delete_structure_link",
        expected_revision,
        structure_link_id: intent.structureLinkId,
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
