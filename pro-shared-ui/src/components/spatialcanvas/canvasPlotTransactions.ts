import type {
  CanvasPlotCommandDTO,
  CanvasPlotSnapshotDTO,
} from "@logosforge/ui-contracts";
import {
  CANVAS_FRAME_MIN_HEIGHT,
  CANVAS_FRAME_MIN_WIDTH,
  CANVAS_NODE_MIN_HEIGHT,
  CANVAS_NODE_MIN_WIDTH,
} from "./canvasPlotGeometry";

type NodePatch = {
  title?: string;
  body?: string;
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  colorLabel?: string;
  groupLabel?: string;
  sceneId?: number | null;
  index?: number;
};

type LinkPatch = {
  label?: string;
  colorLabel?: string;
  linkType?: string;
};

type FramePatch = {
  title?: string;
  colorLabel?: string;
  x?: number;
  y?: number;
  width?: number;
  height?: number;
};

export type CanvasPlotCommandIntent =
  | ({ kind: "create_node" } & NodePatch)
  | ({ kind: "update_node"; nodeId: number } & NodePatch)
  | { kind: "delete_node"; nodeId: number }
  | ({ kind: "create_link"; sourceNodeId: number; targetNodeId: number } & LinkPatch)
  | ({ kind: "update_link"; linkId: number } & LinkPatch)
  | { kind: "delete_link"; linkId: number }
  | ({ kind: "create_frame" } & FramePatch)
  | ({ kind: "update_frame"; frameId: number } & FramePatch)
  | { kind: "delete_frame"; frameId: number };

export type CanvasPlotCommandPlanResult =
  | { command: CanvasPlotCommandDTO; error?: never }
  | { command?: never; error: string };

const finite = (value: number | undefined): boolean => value == null || Number.isFinite(value);
const positiveId = (value: number): boolean => Number.isSafeInteger(value) && value > 0;
const validIndex = (value: number | undefined): boolean => value == null || (Number.isSafeInteger(value) && value >= 0);

function validateGeometry(
  patch: { x?: number; y?: number; width?: number; height?: number },
  kind: "node" | "frame",
): string | null {
  if (![patch.x, patch.y, patch.width, patch.height].every(finite)) {
    return "Canvas geometry must use finite numbers.";
  }
  const minWidth = kind === "node" ? CANVAS_NODE_MIN_WIDTH : CANVAS_FRAME_MIN_WIDTH;
  const minHeight = kind === "node" ? CANVAS_NODE_MIN_HEIGHT : CANVAS_FRAME_MIN_HEIGHT;
  if (patch.width != null && patch.width < minWidth) return `${kind === "node" ? "Block" : "Frame"} width is too small.`;
  if (patch.height != null && patch.height < minHeight) return `${kind === "node" ? "Block" : "Frame"} height is too small.`;
  return null;
}

function assignNodePatch(target: Record<string, unknown>, intent: NodePatch): void {
  if (intent.title != null) target.title = intent.title.trim();
  if (intent.body != null) target.body = intent.body.trim();
  if (intent.x != null) target.x = intent.x;
  if (intent.y != null) target.y = intent.y;
  if (intent.width != null) target.width = intent.width;
  if (intent.height != null) target.height = intent.height;
  if (intent.colorLabel != null) target.color_label = intent.colorLabel.trim();
  if (intent.groupLabel != null) target.group_label = intent.groupLabel.trim();
  if (intent.sceneId !== undefined) target.scene_id = intent.sceneId;
  if (intent.index != null) target.index = intent.index;
}

function assignLinkPatch(target: Record<string, unknown>, intent: LinkPatch): void {
  if (intent.label != null) target.label = intent.label.trim();
  if (intent.colorLabel != null) target.color_label = intent.colorLabel.trim();
  if (intent.linkType != null) target.link_type = intent.linkType.trim();
}

function assignFramePatch(target: Record<string, unknown>, intent: FramePatch): void {
  if (intent.title != null) target.title = intent.title.trim();
  if (intent.colorLabel != null) target.color_label = intent.colorLabel.trim();
  if (intent.x != null) target.x = intent.x;
  if (intent.y != null) target.y = intent.y;
  if (intent.width != null) target.width = intent.width;
  if (intent.height != null) target.height = intent.height;
}

function hasPatch(command: Record<string, unknown>, identityKeys: readonly string[]): boolean {
  return Object.keys(command).some((key) => key !== "kind" && key !== "expected_revision" && !identityKeys.includes(key));
}

/** Bind a semantic UI intent to one freshly read authoritative board revision. */
export function planCanvasPlotCommand(
  snapshot: CanvasPlotSnapshotDTO,
  intent: CanvasPlotCommandIntent,
): CanvasPlotCommandPlanResult {
  const expected_revision = snapshot.revision;

  if (intent.kind === "create_node") {
    const geometryError = validateGeometry(intent, "node");
    if (geometryError) return { error: geometryError };
    if (!validIndex(intent.index)) return { error: "Block order must be a non-negative integer." };
    const command: Record<string, unknown> = { kind: intent.kind, expected_revision };
    assignNodePatch(command, intent);
    return { command: command as unknown as CanvasPlotCommandDTO };
  }

  if (intent.kind === "update_node") {
    if (!positiveId(intent.nodeId) || !snapshot.nodes.some((node) => node.id === intent.nodeId)) {
      return { error: "That Canvas Plot block is no longer available." };
    }
    const geometryError = validateGeometry(intent, "node");
    if (geometryError) return { error: geometryError };
    if (!validIndex(intent.index)) return { error: "Block order must be a non-negative integer." };
    const command: Record<string, unknown> = {
      kind: intent.kind,
      expected_revision,
      node_id: intent.nodeId,
    };
    assignNodePatch(command, intent);
    if (!hasPatch(command, ["node_id"])) return { error: "Choose a block change first." };
    return { command: command as unknown as CanvasPlotCommandDTO };
  }

  if (intent.kind === "delete_node") {
    if (!snapshot.nodes.some((node) => node.id === intent.nodeId)) {
      return { error: "That Canvas Plot block is no longer available." };
    }
    return { command: { kind: intent.kind, expected_revision, node_id: intent.nodeId } };
  }

  if (intent.kind === "create_link") {
    if (intent.sourceNodeId === intent.targetNodeId) return { error: "A block cannot connect to itself." };
    const nodeIds = new Set(snapshot.nodes.map((node) => node.id));
    if (!nodeIds.has(intent.sourceNodeId) || !nodeIds.has(intent.targetNodeId)) {
      return { error: "One of those Canvas Plot blocks is no longer available." };
    }
    if (snapshot.links.some((link) => (
      (link.source_node_id === intent.sourceNodeId && link.target_node_id === intent.targetNodeId)
      || (link.source_node_id === intent.targetNodeId && link.target_node_id === intent.sourceNodeId)
    ))) return { error: "Those blocks are already connected." };
    const command: Record<string, unknown> = {
      kind: intent.kind,
      expected_revision,
      source_node_id: intent.sourceNodeId,
      target_node_id: intent.targetNodeId,
    };
    assignLinkPatch(command, intent);
    return { command: command as unknown as CanvasPlotCommandDTO };
  }

  if (intent.kind === "update_link") {
    if (!snapshot.links.some((link) => link.id === intent.linkId)) {
      return { error: "That Canvas Plot connection is no longer available." };
    }
    const command: Record<string, unknown> = {
      kind: intent.kind,
      expected_revision,
      link_id: intent.linkId,
    };
    assignLinkPatch(command, intent);
    if (!hasPatch(command, ["link_id"])) return { error: "Choose a connection change first." };
    return { command: command as unknown as CanvasPlotCommandDTO };
  }

  if (intent.kind === "delete_link") {
    if (!snapshot.links.some((link) => link.id === intent.linkId)) {
      return { error: "That Canvas Plot connection is no longer available." };
    }
    return { command: { kind: intent.kind, expected_revision, link_id: intent.linkId } };
  }

  if (intent.kind === "create_frame") {
    const geometryError = validateGeometry(intent, "frame");
    if (geometryError) return { error: geometryError };
    const command: Record<string, unknown> = { kind: intent.kind, expected_revision };
    assignFramePatch(command, intent);
    return { command: command as unknown as CanvasPlotCommandDTO };
  }

  if (intent.kind === "update_frame") {
    if (!snapshot.frames.some((frame) => frame.id === intent.frameId)) {
      return { error: "That Canvas Plot frame is no longer available." };
    }
    const geometryError = validateGeometry(intent, "frame");
    if (geometryError) return { error: geometryError };
    const command: Record<string, unknown> = {
      kind: intent.kind,
      expected_revision,
      frame_id: intent.frameId,
    };
    assignFramePatch(command, intent);
    if (!hasPatch(command, ["frame_id"])) return { error: "Choose a frame change first." };
    return { command: command as unknown as CanvasPlotCommandDTO };
  }

  if (!snapshot.frames.some((frame) => frame.id === intent.frameId)) {
    return { error: "That Canvas Plot frame is no longer available." };
  }
  return { command: { kind: intent.kind, expected_revision, frame_id: intent.frameId } };
}

export function canvasPlotIntentCanRetry(intent: CanvasPlotCommandIntent): boolean {
  return intent.kind === "create_node" || intent.kind === "create_frame" || intent.kind === "create_link";
}

export function describeCanvasPlotIntent(intent: CanvasPlotCommandIntent): string {
  if (intent.kind === "create_node") return `create block “${intent.title?.trim() || "New block"}”`;
  if (intent.kind === "update_node") return `update block #${intent.nodeId}`;
  if (intent.kind === "delete_node") return `delete block #${intent.nodeId}`;
  if (intent.kind === "create_link") return `connect block #${intent.sourceNodeId} to #${intent.targetNodeId}`;
  if (intent.kind === "update_link") return `update connection #${intent.linkId}`;
  if (intent.kind === "delete_link") return `delete connection #${intent.linkId}`;
  if (intent.kind === "create_frame") return `create frame “${intent.title?.trim() || "Group"}”`;
  if (intent.kind === "update_frame") return `update frame #${intent.frameId}`;
  return `delete frame #${intent.frameId}`;
}
