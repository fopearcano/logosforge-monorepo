import type { CanvasPlotSnapshotDTO } from "@logosforge/ui-contracts";
import {
  canvasPlotIntentCanRetry,
  describeCanvasPlotIntent,
  planCanvasPlotCommand,
} from "../src/components/spatialcanvas/canvasPlotTransactions";

let assertions = 0;
function check(value: unknown, message: string): asserts value {
  assertions += 1;
  if (!value) throw new Error(message);
}

const snapshot: CanvasPlotSnapshotDTO = {
  project_id: 7,
  revision: "a".repeat(64),
  nodes: [
    { id: 1, title: "A", body: "", x: 0, y: 0, width: 180, height: 110, color_label: "cyan", group_label: "", scene_id: null, sort_order: 0, created_at: "2026-01-01T00:00:00Z" },
    { id: 2, title: "B", body: "", x: 300, y: 0, width: 180, height: 110, color_label: "amber", group_label: "", scene_id: 9, sort_order: 1, created_at: "2026-01-01T00:00:01Z" },
  ],
  links: [{ id: 3, source_node_id: 1, target_node_id: 2, label: "causes", color_label: "gray", link_type: "causality", created_at: "2026-01-01T00:00:02Z" }],
  frames: [{ id: 4, title: "Act I", color_label: "blue", x: -40, y: -40, width: 560, height: 240, created_at: "2026-01-01T00:00:03Z" }],
};

const created = planCanvasPlotCommand(snapshot, {
  kind: "create_node",
  title: "  New idea  ",
  body: "  note  ",
  x: 12,
  y: 34,
  width: 188,
  height: 116,
  index: 1,
});
check(created.command?.kind === "create_node", "create intent must plan a create_node command");
check(created.command?.expected_revision === snapshot.revision, "commands must bind to the authoritative board revision");
check(created.command?.kind === "create_node" && created.command.title === "New idea" && created.command.body === "note" && created.command.index === 1, "node fields and dense z-order index must be normalized and preserved");

const moved = planCanvasPlotCommand(snapshot, {
  kind: "update_node",
  nodeId: 2,
  x: 480,
  y: -120,
  width: 240,
  height: 140,
  index: 0,
});
check(moved.command?.kind === "update_node" && moved.command.node_id === 2, "node geometry must target the selected owned block");
check(moved.command?.kind === "update_node" && moved.command.x === 480 && moved.command.index === 0, "node move/resize/z-order must share one atomic update command");

check(!planCanvasPlotCommand(snapshot, { kind: "update_node", nodeId: 99, x: 4 }).command, "stale node intents must be rejected before transport");
check(!planCanvasPlotCommand(snapshot, { kind: "update_node", nodeId: 1 }).command, "empty update intents must be rejected");
check(!planCanvasPlotCommand(snapshot, { kind: "update_node", nodeId: 1, width: 20 }).command, "undersized node geometry must be rejected");
check(!planCanvasPlotCommand(snapshot, { kind: "create_node", index: -1 }).command, "node creation must reject a negative dense z-order index");
check(!planCanvasPlotCommand(snapshot, { kind: "update_node", nodeId: 1, index: 1.5 }).command, "node updates must reject a fractional dense z-order index");
check(!planCanvasPlotCommand(snapshot, { kind: "update_frame", frameId: 4, height: Number.NaN }).command, "non-finite frame geometry must be rejected");

check(!planCanvasPlotCommand(snapshot, { kind: "create_link", sourceNodeId: 1, targetNodeId: 1 }).command, "self-links must be rejected");
check(!planCanvasPlotCommand(snapshot, { kind: "create_link", sourceNodeId: 2, targetNodeId: 1 }).command, "reverse duplicate links must be rejected");
const link = planCanvasPlotCommand({ ...snapshot, links: [] }, { kind: "create_link", sourceNodeId: 1, targetNodeId: 2, label: " echo ", linkType: " echo " });
check(link.command?.kind === "create_link" && link.command.label === "echo" && link.command.link_type === "echo", "connection semantics must serialize to snake_case DTO fields");

const frame = planCanvasPlotCommand(snapshot, { kind: "update_frame", frameId: 4, title: " Act Two ", width: 600 });
check(frame.command?.kind === "update_frame" && frame.command.frame_id === 4 && frame.command.title === "Act Two", "frame edits must remain revision-bound and normalized");

check(canvasPlotIntentCanRetry({ kind: "create_node", title: "A" }), "additive node creation may be explicitly retried after a conflict");
check(!canvasPlotIntentCanRetry({ kind: "delete_node", nodeId: 1 }), "destructive commands must require fresh confirmation after a conflict");
check(!canvasPlotIntentCanRetry({ kind: "update_node", nodeId: 1, x: 20 }), "absolute geometry overwrites must not be retried blindly");
check(describeCanvasPlotIntent({ kind: "create_link", sourceNodeId: 1, targetNodeId: 2 }).includes("#1"), "conflict copy must describe the retained semantic intent");

console.log(`${assertions} Canvas Plot transaction assertions passed.`);
