import { createMockApiClient } from "./mockApi";
import { ApiRequestError } from "../src/adapters/httpApiClient";
import { flushPendingProjectSaves, getProjectSaveStatusSnapshot } from "../src/adapters/projectSaveCoordinator";
import type { KnowledgeGraphQueryDTO, StoryStructureDTO } from "@logosforge/ui-contracts";

let passed = 0;

function check(condition: unknown, message: string): void {
  if (!condition) throw new Error(message);
  passed += 1;
}

const structurePaths = (structure: StoryStructureDTO) => structure.acts.flatMap((act) => (
  act.chapters.flatMap((chapter) => chapter.scenes.map((scene) => ({
    act: act.name,
    chapter: chapter.name,
    ...scene,
  })))
));

const api = createMockApiClient();
check(typeof api.health === "function", "preview mock must implement core health");
check(typeof api.writingModes === "function", "preview mock must implement the writing-mode catalog");
check(typeof api.openProject === "function", "preview mock must implement project opening");
check(typeof api.createProject === "function", "preview mock must implement project creation");
check(typeof api.updateProject === "function", "preview mock must implement project metadata updates");
check(typeof api.deleteProject === "function", "preview mock must implement project deletion");
check(typeof api.searchProject === "function", "preview mock must implement typed project search");
check(typeof api.getAdapt === "function", "preview mock must implement getAdapt");
check(typeof api.patchAiBehavior === "function", "preview mock must implement patchAiBehavior");
check(typeof api.voiceHistory === "function", "preview mock must implement Voice history");
check(typeof api.voiceIntentCancel === "function", "preview mock must implement Voice preview cancellation");
check(typeof api.voiceBillyCancel === "function", "preview mock must implement Billy preview cancellation");
check(typeof api.planPsykeConsoleCommand === "function", "preview mock must implement PSYKE command planning");
check(typeof api.executePsykeConsoleCommand === "function", "preview mock must implement PSYKE command execution");
check(typeof api.executeTimelineCommand === "function", "preview mock must implement guarded Timeline commands");
check(typeof api.executeCanvasPlotCommand === "function", "preview mock must implement guarded Canvas Plot commands");
check(typeof api.getKnowledgeGraph === "function", "preview mock must implement the canonical Knowledge Graph read");
check(typeof api.executeKnowledgeGraphCommand === "function", "preview mock must implement guarded Knowledge Graph review commands");
check(typeof api.getKnowledgeGraphCommandReceipt === "function", "preview mock must implement durable Knowledge Graph command receipts");
check(typeof api.getKnowledgeGraphHiddenEdges === "function", "preview mock must implement the complete paged hidden-edge review queue");
check(typeof api.getContinuity === "function", "preview mock must implement canonical Continuity reads");
check(typeof api.executeContinuityCommand === "function", "preview mock must implement guarded Continuity review commands");
check(typeof api.getContinuityCommandReceipt === "function", "preview mock must implement durable Continuity command receipts");

const health = await api.health();
check(
  health.status === "ok" && health.version === "1.16.0" && health.api_version === "1.16.0",
  "preview health must satisfy the core contract",
);
const projectMap = await api.getKnowledgeGraph(1, { limit: 160, include_inferred: true });
check(
  projectMap.project_id === 1
    && projectMap.view_mode === "project_map"
    && projectMap.story_diagnostics_available === true
    && projectMap.story_gravity_available === true
    && projectMap.nodes.length > 1
    && projectMap.nodes.every((node) => Number.isSafeInteger(node.degree) && node.degree >= 0)
    && projectMap.nodes.every((node) => node.story_gravity === null
      || (Number.isFinite(node.story_gravity) && node.story_gravity >= 0 && node.story_gravity <= 1))
    && projectMap.nodes.some((node) => node.story_gravity !== null)
    && projectMap.weak_links.every((edge) => projectMap.nodes.some((node) => node.key === edge.source)
      && projectMap.nodes.some((node) => node.key === edge.target)),
  "preview Knowledge Graph must expose bounded canonical nodes, full-query degrees, and safe weak-link endpoints",
);
const structureGraph = await api.getKnowledgeGraph(1, {
  limit: 160,
  include_inferred: true,
  view_mode: "structure",
});
check(
  structureGraph.view_mode === "structure"
    && !structureGraph.story_diagnostics_available
    && structureGraph.orphan_keys.length === 0
    && structureGraph.orphan_count === 0
    && structureGraph.weak_links.length === 0
    && structureGraph.weak_link_count === 0
    && structureGraph.nodes.every((node) => [
      "project", "act", "chapter", "scene", "plot_block", "timeline_event",
    ].includes(node.node_type))
    && structureGraph.edges.every((edge) => [
      "contains", "belongs_to", "precedes", "follows",
    ].includes(edge.edge_type)),
  "preview Structure view must mirror the bounded Core projection without story diagnostics",
);
const previewFlowEdge = structureGraph.edges.find((edge) => edge.edge_type === "precedes");
check(
  previewFlowEdge != null
    && Number.isSafeInteger(previewFlowEdge.metadata.story_order_index)
    && previewFlowEdge.metadata.story_order_total === structureGraph.nodes.filter((node) => node.node_type === "scene").length
    && ["beginning", "middle", "ending"].includes(String(previewFlowEdge.metadata.story_order_band))
    && typeof previewFlowEdge.metadata.act_boundary === "boolean",
  "preview Structure flow must carry the same bounded story-order metadata as Core",
);
const confirmedStructureGraph = await api.getKnowledgeGraph(1, {
  limit: 160,
  include_inferred: false,
  view_mode: "structure",
});
check(
  confirmedStructureGraph.edges.every((edge) => edge.edge_type !== "precedes" && edge.edge_type !== "follows"),
  "preview Confirmed-only Structure must not resurrect inferred story-order flow",
);
const riskGraph = await api.getKnowledgeGraph(1, {
  limit: 160,
  include_inferred: true,
  view_mode: "recorded_risk",
});
check(
  riskGraph.view_mode === "recorded_risk"
    && !riskGraph.story_diagnostics_available
    && riskGraph.edges.length === 2
    && riskGraph.edges.every((edge) => edge.edge_type === "risks" || edge.edge_type === "contradicts")
    && riskGraph.hidden_edges.length === 0,
  "preview Recorded Risk view must include only recorded risk edges and exact endpoints",
);
const revisionGraph = await api.getKnowledgeGraph(1, {
  limit: 160,
  include_inferred: true,
  view_mode: "revision_impact",
});
check(
  revisionGraph.view_mode === "revision_impact"
    && !revisionGraph.story_diagnostics_available
    && revisionGraph.edges.length === 1
    && revisionGraph.edges.every((edge) => edge.source_system === "revision_intelligence"
      && (edge.edge_type === "revises" || edge.edge_type === "risks")),
  "preview Revision Impact view must include only recorded revision-intelligence impact edges",
);
let invalidGraphView: unknown = null;
try {
  await api.getKnowledgeGraph(1, {
    view_mode: "future_mode",
  } as unknown as KnowledgeGraphQueryDTO);
} catch (error) {
  invalidGraphView = error;
}
check(
  invalidGraphView instanceof ApiRequestError
    && invalidGraphView.status === 422
    && invalidGraphView.code === "validation_error",
  "preview Knowledge Graph must reject unknown view modes",
);
const focusNode = projectMap.nodes.find((node) => node.node_type === "scene")!;
const focusedProjectMap = await api.getKnowledgeGraph(1, {
  focus_key: focusNode.key,
  depth: 1,
  limit: 20,
  include_inferred: true,
});
check(
  focusedProjectMap.focus_key != null
    && focusedProjectMap.depth === 1
    && focusedProjectMap.nodes.some((node) => node.key === focusedProjectMap.focus_key),
  "preview Knowledge Graph must return a bounded neighborhood containing its requested focus",
);
check(
  focusedProjectMap.nodes.find((node) => node.key === focusNode.key)?.degree === focusNode.degree,
  "preview focused nodes must retain their complete selected-view degree",
);
const graphReviewApi = createMockApiClient();
const initialReviewGraph = await graphReviewApi.getKnowledgeGraph(1, { limit: 100, include_inferred: true });
const reviewEdge = initialReviewGraph.edges.find((edge) => edge.is_inferred && !edge.is_user_confirmed)!;
const hideGraphCommand = {
  kind: "hide_edge" as const,
  expected_revision: initialReviewGraph.revision,
  source: reviewEdge.source,
  target: reviewEdge.target,
  edge_type: reviewEdge.edge_type,
};
const graphReviewKey = "preview-graph-key-0001";
const hiddenResult = await graphReviewApi.executeKnowledgeGraphCommand(1, hideGraphCommand, graphReviewKey);
check(hiddenResult.changed && !hiddenResult.replayed && hiddenResult.applied_revision !== initialReviewGraph.revision, "preview graph hide must apply one revision-guarded mutation");
const hiddenPage = await graphReviewApi.getKnowledgeGraphHiddenEdges(1, 0, 25);
check(
  hiddenPage.hidden_edge_count === 1
    && hiddenPage.returned_edge_count === 1
    && hiddenPage.edges[0]?.is_hidden === true
    && hiddenPage.nodes.some((node) => node.key === reviewEdge.source)
    && hiddenPage.nodes.some((node) => node.key === reviewEdge.target),
  "preview hidden queue must return every hidden decision with exact endpoint nodes",
);
const graphReceipt = await graphReviewApi.getKnowledgeGraphCommandReceipt(1, graphReviewKey, hideGraphCommand);
check(graphReceipt.original_changed && graphReceipt.applied_revision === hiddenResult.applied_revision, "preview graph receipt must preserve the original mutation outcome");
const replayedHide = await graphReviewApi.executeKnowledgeGraphCommand(1, hideGraphCommand, graphReviewKey);
check(replayedHide.replayed && !replayedHide.changed && replayedHide.applied_revision === hiddenResult.applied_revision, "preview graph command replay must be idempotent and retain its original applied revision");
const restoredResult = await graphReviewApi.executeKnowledgeGraphCommand(1, {
  kind: "unhide_edge",
  expected_revision: hiddenPage.revision,
  source: reviewEdge.source,
  target: reviewEdge.target,
  edge_type: reviewEdge.edge_type,
}, "preview-graph-key-0002");
check(restoredResult.changed && restoredResult.knowledge_graph.hidden_edge_count === 0, "preview graph restore must remove the decision from the hidden queue");
const continuityApi = createMockApiClient();
const initialContinuity = await continuityApi.getContinuity(1);
check(
  initialContinuity.project_id === 1
    && /^[0-9a-f]{64}$/.test(initialContinuity.review_revision)
    && initialContinuity.issues.length === 2
    && initialContinuity.issues.every((issue) => /^[0-9a-f]{16}$/.test(issue.id) && issue.status === "open"),
  "preview Continuity must expose a project-bound revision and canonical open issue keys",
);
const continuityIssue = initialContinuity.issues[0]!;
const deferContinuityCommand = {
  kind: "defer_issue" as const,
  expected_revision: initialContinuity.review_revision,
  issue_id: continuityIssue.id,
  expected_issue_fingerprint: continuityIssue.review_fingerprint,
};
const continuityKey = "preview-continuity-key-0001";
const deferredContinuity = await continuityApi.executeContinuityCommand(
  1,
  deferContinuityCommand,
  continuityKey,
);
check(
  deferredContinuity.changed
    && !deferredContinuity.replayed
    && deferredContinuity.status === "deferred"
    && deferredContinuity.continuity.issues.find((issue) => issue.id === continuityIssue.id)?.status === "deferred"
    && deferredContinuity.applied_revision !== initialContinuity.review_revision,
  "preview Continuity must apply one revision-guarded review decision",
);
const continuityReceipt = await continuityApi.getContinuityCommandReceipt(
  1,
  continuityKey,
  deferContinuityCommand,
);
check(
  continuityReceipt.original_changed
    && continuityReceipt.original_affected_issue_id === continuityIssue.id
    && continuityReceipt.applied_revision === deferredContinuity.applied_revision,
  "preview Continuity receipt must preserve the original committed outcome",
);
const replayedContinuity = await continuityApi.executeContinuityCommand(
  1,
  deferContinuityCommand,
  continuityKey,
);
check(
  replayedContinuity.replayed
    && !replayedContinuity.changed
    && replayedContinuity.applied_revision === deferredContinuity.applied_revision,
  "preview Continuity replay must be idempotent and retain the original applied revision",
);
let continuityKeyConflict: unknown = null;
try {
  await continuityApi.executeContinuityCommand(1, {
    ...deferContinuityCommand,
    kind: "dismiss_issue",
  }, continuityKey);
} catch (error) {
  continuityKeyConflict = error;
}
check(
  continuityKeyConflict instanceof ApiRequestError
    && continuityKeyConflict.status === 409
    && continuityKeyConflict.code === "idempotency_key_conflict",
  "preview Continuity must reject reuse of a capability key for a different command",
);
const canvasApi = createMockApiClient();
const initialCanvas = await canvasApi.getCanvasPlot(1);
check(
  initialCanvas.nodes.length === 3
    && initialCanvas.links.length === 2
    && initialCanvas.frames.length === 1
    && initialCanvas.nodes.map((node) => node.sort_order).join(",") === "0,1,2",
  "preview Canvas Plot must expose independent nodes, links, frames, and dense zero-based z-order",
);
const createdCanvasNode = await canvasApi.executeCanvasPlotCommand(1, {
  kind: "create_node",
  expected_revision: initialCanvas.revision,
  x: 120,
  y: 160,
});
const defaultCanvasNode = createdCanvasNode.canvas_plot.nodes.find(
  (node) => node.id === createdCanvasNode.created_node_id,
)!;
check(
  createdCanvasNode.changed
    && createdCanvasNode.replayed === false
    && createdCanvasNode.applied_revision === createdCanvasNode.canvas_plot.revision
    && createdCanvasNode.created_node_id != null
    && defaultCanvasNode.title === ""
    && defaultCanvasNode.body === ""
    && defaultCanvasNode.width === 180
    && defaultCanvasNode.height === 110
    && defaultCanvasNode.sort_order === 3,
  "preview Canvas Plot commands must use the live node defaults and append in dense order",
);
let staleCanvasError: unknown = null;
try {
  await canvasApi.executeCanvasPlotCommand(1, {
    kind: "create_frame",
    expected_revision: initialCanvas.revision,
    title: "Stale frame",
  });
} catch (error) {
  staleCanvasError = error;
}
check(
  staleCanvasError instanceof ApiRequestError
    && staleCanvasError.status === 409
    && staleCanvasError.code === "canvas_plot_conflict"
    && !(await canvasApi.getCanvasPlot(1)).frames.some((frame) => frame.title === "Stale frame"),
  "preview Canvas Plot commands must reject stale revisions without partial mutation",
);
const deletedCanvasNode = await canvasApi.executeCanvasPlotCommand(1, {
  kind: "delete_node",
  expected_revision: createdCanvasNode.canvas_plot.revision,
  node_id: createdCanvasNode.created_node_id!,
});
const recreatedCanvasNode = await canvasApi.executeCanvasPlotCommand(1, {
  kind: "create_node",
  expected_revision: deletedCanvasNode.canvas_plot.revision,
});
check(
  recreatedCanvasNode.created_node_id! > createdCanvasNode.created_node_id!
    && recreatedCanvasNode.canvas_plot.nodes.map((node) => node.sort_order).join(",") === "0,1,2,3",
  "preview Canvas Plot deletion must re-densify order and must not reuse an ID in one mock session",
);
const reverseDuplicate = await canvasApi.executeCanvasPlotCommand(1, {
  kind: "create_link",
  expected_revision: recreatedCanvasNode.canvas_plot.revision,
  source_node_id: 2,
  target_node_id: 1,
});
check(
  !reverseDuplicate.changed
    && reverseDuplicate.created_link_id === null
    && reverseDuplicate.canvas_plot.revision === recreatedCanvasNode.canvas_plot.revision,
  "preview Canvas Plot links must preserve the live undirected duplicate no-op semantics",
);
let foreignCanvasSceneError: unknown = null;
try {
  await canvasApi.executeCanvasPlotCommand(1, {
    kind: "create_node",
    expected_revision: reverseDuplicate.canvas_plot.revision,
    scene_id: 999_999,
  });
} catch (error) {
  foreignCanvasSceneError = error;
}
check(
  foreignCanvasSceneError instanceof ApiRequestError
    && foreignCanvasSceneError.status === 404
    && (await canvasApi.getCanvasPlot(1)).revision === reverseDuplicate.canvas_plot.revision,
  "preview Canvas Plot nodes must reject Scene ids outside the scoped project without mutating state",
);
const emptyProjectCanvas = await canvasApi.getCanvasPlot(2);
check(
  emptyProjectCanvas.nodes.length === 0
    && emptyProjectCanvas.links.length === 0
    && emptyProjectCanvas.frames.length === 0,
  "preview Canvas Plot state must be isolated per project",
);

const canvasRevisionBeforeViewport = (await canvasApi.getCanvasPlot(1)).revision;
const firstProjectSettings = await canvasApi.patchSettings(1, {
  settings: { canvas_plot_view: { zoom: 1.25, cx: 40, cy: -15 } },
});
(firstProjectSettings.settings.canvas_plot_view as Record<string, unknown>).zoom = 99;
const storedFirstProjectSettings = await canvasApi.getSettings(1);
const untouchedSecondProjectSettings = await canvasApi.getSettings(2);
check(
  (storedFirstProjectSettings.settings.canvas_plot_view as { zoom: number }).zoom === 1.25
    && untouchedSecondProjectSettings.settings.canvas_plot_view === undefined,
  "preview viewport settings must be deep-cloned and isolated per project",
);
check(
  (await canvasApi.getCanvasPlot(1)).revision === canvasRevisionBeforeViewport,
  "preview viewport settings must not participate in the structural Canvas Plot revision",
);
await canvasApi.patchSettings(2, {
  settings: { canvas_plot_view: { zoom: 2, cx: 900, cy: 450 } },
});
check(
  ((await canvasApi.getSettings(1)).settings.canvas_plot_view as { zoom: number }).zoom === 1.25,
  "patching one preview project's viewport must not overwrite another project's viewport",
);
check(
  (await createMockApiClient().getSettings(1)).settings.canvas_plot_view === undefined,
  "a fresh preview client must not inherit project settings from a prior mock session",
);
const timelineApi = createMockApiClient();
const initialTimeline = await timelineApi.getTimeline(1);
check(
  initialTimeline.project_id === 1
    && initialTimeline.order_mode === "structural"
    && initialTimeline.lanes.length === 3
    && initialTimeline.events.length === 6
    && initialTimeline.off_timeline.map((scene) => scene.id).join(",") === "3",
  "preview Timeline snapshot must expose opt-in events, real lanes, and off-Timeline scenes",
);
check(
  initialTimeline.story_flow.points.map((point) => point.scene_id).join(",")
      === initialTimeline.events.map((event) => event.id).join(",")
    && initialTimeline.story_flow.points.every((point, index) => (
      point.order_index === initialTimeline.events[index]?.order_index
      && Number.isInteger(point.tension_value)
      && point.tension_value >= 0
      && point.tension_value <= 10
    ))
    && initialTimeline.story_flow.warnings[0]?.scene_ids.join(",")
      === initialTimeline.events.slice(0, 4).map((event) => event.id).join(","),
  "preview Timeline story flow must align 1:1 with active events and expose contiguous warnings",
);
check(
  initialTimeline.mode_projection.kind === "screenplay"
    && initialTimeline.mode_projection.scenes.map((scene) => scene.scene_id).join(",")
      === initialTimeline.events.map((event) => event.id).join(",")
    && initialTimeline.mode_projection.scenes.every((scene) => scene.visual_beat_count >= 0),
  "preview Timeline must derive the active project's discriminated screenplay projection",
);
const modeApi = createMockApiClient();
check(
  (await modeApi.getTimeline(2)).mode_projection.kind === "novel"
    && (await modeApi.getTimeline(3)).mode_projection.kind === "series",
  "preview Timeline mode projection must follow Novel and Series project engines",
);
const graphicNovelProject = await modeApi.createProject({
  title: "Graphic projection",
  narrative_engine: "graphic_novel",
});
const stageProject = await modeApi.createProject({
  title: "Stage projection",
  narrative_engine: "stage_script",
});
const stageScene = await modeApi.createScene(stageProject.id, {
  title: "Stage opening",
  act: "Act I",
  chapter: "Scene One",
});
const emptyStageTimeline = await modeApi.getTimeline(stageProject.id);
const placedStage = await modeApi.executeTimelineCommand(stageProject.id, {
  kind: "place_event",
  expected_revision: emptyStageTimeline.revision,
  scene_id: stageScene.id,
  lane_id: null,
}, "timeline-preview-stage-mode-01");
check(
  (await modeApi.getTimeline(graphicNovelProject.id)).mode_projection.kind === "graphic_novel"
    && placedStage.timeline.mode_projection.kind === "stage_script"
    && placedStage.timeline.mode_projection.scenes[0]?.scene_id === stageScene.id
    && placedStage.timeline.story_flow.points[0]?.scene_id === stageScene.id,
  "preview Timeline must expose Graphic Novel and event-aligned Stage Script projections",
);

const relationshipApi = createMockApiClient();
const relationshipProject = await relationshipApi.createProject({
  title: "Timeline relationships",
  narrative_engine: "novel",
});
const relationshipFirst = await relationshipApi.createScene(relationshipProject.id, {
  title: "First",
  act: "Act I",
  chapter: "One",
});
const relationshipSecond = await relationshipApi.createScene(relationshipProject.id, {
  title: "Second",
  act: "Act II",
  chapter: "Two",
});
let relationshipTimeline = await relationshipApi.getTimeline(relationshipProject.id);
const placedFirst = await relationshipApi.executeTimelineCommand(relationshipProject.id, {
  kind: "place_event",
  expected_revision: relationshipTimeline.revision,
  scene_id: relationshipFirst.id,
  lane_id: null,
}, "timeline-preview-rel-place-first");
const placedSecond = await relationshipApi.executeTimelineCommand(relationshipProject.id, {
  kind: "place_event",
  expected_revision: placedFirst.timeline.revision,
  scene_id: relationshipSecond.id,
  lane_id: null,
}, "timeline-preview-rel-place-second");
const createRelationshipCommand = {
  kind: "create_link" as const,
  expected_revision: placedSecond.timeline.revision,
  source_scene_id: relationshipFirst.id,
  target_scene_id: relationshipSecond.id,
  link_type: "causality" as const,
  color_label: "cyan",
  label: "therefore",
};
const createRelationshipKey = "timeline-preview-rel-create-001";
const createdRelationship = await relationshipApi.executeTimelineCommand(
  relationshipProject.id,
  createRelationshipCommand,
  createRelationshipKey,
);
const relationshipId = createdRelationship.created_link_id!;
check(
  createdRelationship.changed
    && relationshipId > 0
    && createdRelationship.affected_link_ids.join(",") === String(relationshipId)
    && createdRelationship.timeline.links[0]?.label === "therefore"
    && (await relationshipApi.getTimeline(relationshipProject.id)).links[0]?.id === relationshipId,
  "preview event-link creation must persist state and report focused created/affected ids",
);
const replayedRelationship = await relationshipApi.executeTimelineCommand(
  relationshipProject.id,
  createRelationshipCommand,
  createRelationshipKey,
);
const relationshipReceipt = await relationshipApi.getTimelineCommandReceipt(
  relationshipProject.id,
  createRelationshipKey,
  createRelationshipCommand,
);
check(
  replayedRelationship.replayed
    && !replayedRelationship.changed
    && replayedRelationship.created_link_id === null
    && replayedRelationship.affected_link_ids.length === 0
    && replayedRelationship.applied_revision === createdRelationship.applied_revision
    && relationshipReceipt.original_changed
    && relationshipReceipt.original_created_link_id === relationshipId
    && relationshipReceipt.original_affected_link_ids.join(",") === String(relationshipId),
  "preview Timeline idempotency must replay without mutation while preserving the durable original receipt",
);
const timelineReverseDuplicate = await relationshipApi.executeTimelineCommand(relationshipProject.id, {
  kind: "create_link",
  expected_revision: createdRelationship.timeline.revision,
  source_scene_id: relationshipSecond.id,
  target_scene_id: relationshipFirst.id,
  link_type: "echo",
}, "timeline-preview-rel-reverse-01");
check(
  !timelineReverseDuplicate.changed
    && timelineReverseDuplicate.created_link_id === null
    && timelineReverseDuplicate.affected_link_ids.length === 0
    && timelineReverseDuplicate.timeline.links.length === 1
    && timelineReverseDuplicate.timeline.links[0]?.source_scene_id === relationshipFirst.id,
  "preview reverse-pair creation must preserve legacy unordered uniqueness as an exact no-op",
);
const updatedRelationship = await relationshipApi.executeTimelineCommand(relationshipProject.id, {
  kind: "update_link",
  expected_revision: timelineReverseDuplicate.timeline.revision,
  link_id: relationshipId,
  link_type: "setup_payoff",
  color_label: "amber",
  label: "payoff",
}, "timeline-preview-rel-update-001");
check(
  updatedRelationship.changed
    && updatedRelationship.affected_link_ids.join(",") === String(relationshipId)
    && updatedRelationship.timeline.links[0]?.link_type === "setup_payoff",
  "preview event-link updates must persist typed metadata and report only the edited link",
);
const deletedRelationship = await relationshipApi.executeTimelineCommand(relationshipProject.id, {
  kind: "delete_link",
  expected_revision: updatedRelationship.timeline.revision,
  link_id: relationshipId,
}, "timeline-preview-rel-delete-001");
check(
  deletedRelationship.changed
    && deletedRelationship.affected_link_ids.join(",") === String(relationshipId)
    && deletedRelationship.timeline.links.length === 0,
  "preview event-link deletion must persist and report the removed id",
);
const createdStructureRelationship = await relationshipApi.executeTimelineCommand(relationshipProject.id, {
  kind: "create_structure_link",
  expected_revision: deletedRelationship.timeline.revision,
  source_scene_id: relationshipFirst.id,
  target_type: "act",
  target_ref: "Act I",
}, "timeline-preview-structure-create-01");
const structureRelationshipId = createdStructureRelationship.created_structure_link_id!;
check(
  createdStructureRelationship.changed
    && structureRelationshipId > 0
    && createdStructureRelationship.affected_structure_link_ids.join(",") === String(structureRelationshipId)
    && createdStructureRelationship.timeline.structure_links[0]?.target_exists === true,
  "preview structure-link creation must persist and resolve an existing target",
);
const relationshipStructure = await relationshipApi.getStoryStructure(relationshipProject.id);
await relationshipApi.executeStoryStructureCommand(relationshipProject.id, {
  kind: "rename_act",
  expected_revision: relationshipStructure.revision,
  act: "Act I",
  new_name: "Act Alpha",
});
relationshipTimeline = await relationshipApi.getTimeline(relationshipProject.id);
check(
  relationshipTimeline.structure_links[0]?.target_ref === "Act I"
    && relationshipTimeline.structure_links[0]?.target_exists === false,
  "preview snapshots must retain durable structure links and derive dangling target_exists after structure changes",
);
const repairedStructureRelationship = await relationshipApi.executeTimelineCommand(relationshipProject.id, {
  kind: "update_structure_link",
  expected_revision: relationshipTimeline.revision,
  structure_link_id: structureRelationshipId,
  target_ref: "Act Alpha",
}, "timeline-preview-structure-update-01");
check(
  repairedStructureRelationship.changed
    && repairedStructureRelationship.affected_structure_link_ids.join(",") === String(structureRelationshipId)
    && repairedStructureRelationship.timeline.structure_links[0]?.target_ref === "Act Alpha"
    && repairedStructureRelationship.timeline.structure_links[0]?.target_exists === true,
  "preview structure-link updates must repair dangling targets and report the edited id",
);
const deletedStructureRelationship = await relationshipApi.executeTimelineCommand(relationshipProject.id, {
  kind: "delete_structure_link",
  expected_revision: repairedStructureRelationship.timeline.revision,
  structure_link_id: structureRelationshipId,
}, "timeline-preview-structure-delete-01");
check(
  deletedStructureRelationship.changed
    && deletedStructureRelationship.affected_structure_link_ids.join(",") === String(structureRelationshipId)
    && deletedStructureRelationship.timeline.structure_links.length === 0,
  "preview structure-link deletion must persist and report the removed id",
);
const timelineSemanticsApi = createMockApiClient();
const semanticsStart = await timelineSemanticsApi.getTimeline(1);
const addedUnassigned = await timelineSemanticsApi.executeTimelineCommand(1, {
  kind: "place_event",
  expected_revision: semanticsStart.revision,
  scene_id: 3,
  lane_id: null,
}, "timeline-preview-add-unassigned");
check(
  addedUnassigned.changed && addedUnassigned.affected_scene_ids.length === 0,
  "preview membership-only placement must not claim that a Scene row changed",
);
const removedUnassigned = await timelineSemanticsApi.executeTimelineCommand(1, {
  kind: "remove_event",
  expected_revision: addedUnassigned.timeline.revision,
  scene_id: 3,
}, "timeline-preview-remove-unassigned");
check(
  removedUnassigned.changed && removedUnassigned.affected_scene_ids.length === 0,
  "preview membership-only removal must not claim that a Scene row changed",
);
const titleScene = (await timelineSemanticsApi.listScenes(1)).find((scene) => scene.id === 1)!;
const revisionBeforeTitleEdit = (await timelineSemanticsApi.getTimeline(1)).revision;
await timelineSemanticsApi.updateScene(1, titleScene.id, {
  title: `${titleScene.title} revised`,
  expected_revision: titleScene.revision,
});
const afterTitleEdit = await timelineSemanticsApi.getTimeline(1);
check(
  afterTitleEdit.revision === revisionBeforeTitleEdit
    && afterTitleEdit.events.find((event) => event.id === titleScene.id)?.title.endsWith(" revised"),
  "preview Timeline revisions must ignore title-only edits while snapshots show the latest title",
);
const chronologyScene = (await timelineSemanticsApi.listScenes(1))
  .find((scene) => scene.id === titleScene.id)!;
await timelineSemanticsApi.updateScene(1, chronologyScene.id, {
  time_of_day: "DUSK",
  location: "Docking ring",
  estimated_duration_minutes: 11,
  expected_revision: chronologyScene.revision,
});
const afterChronologyEdit = await timelineSemanticsApi.getTimeline(1);
const chronologyEvent = afterChronologyEdit.events.find((event) => event.id === chronologyScene.id);
check(
  afterChronologyEdit.revision === afterTitleEdit.revision
    && chronologyEvent?.time_of_day === "DUSK"
    && chronologyEvent?.location === "Docking ring"
    && chronologyEvent?.duration_minutes === 11,
  "preview Timeline snapshots must expose current Scene chronology without changing topology revision",
);
const primaryChronologyScene = (await timelineSemanticsApi.listScenes(1))
  .find((scene) => scene.id === chronologyScene.id)!;
await timelineSemanticsApi.updateScene(1, primaryChronologyScene.id, {
  location: "",
  slugline: "INT. AIRLOCK",
  estimated_duration_minutes: 0,
  performance_duration_minutes: 14,
  expected_revision: primaryChronologyScene.revision,
} as Parameters<typeof timelineSemanticsApi.updateScene>[2]);
const afterFallbackChronologyEdit = await timelineSemanticsApi.getTimeline(1);
const fallbackChronologyEvent = afterFallbackChronologyEdit.events
  .find((event) => event.id === primaryChronologyScene.id);
check(
  afterFallbackChronologyEdit.revision === afterChronologyEdit.revision
    && fallbackChronologyEvent?.location === "INT. AIRLOCK"
    && fallbackChronologyEvent?.duration_minutes === 14,
  "preview Timeline chronology must fall back from location/duration to slugline/performance duration",
);
const whitespaceApi = createMockApiClient();
const whitespaceProject = await whitespaceApi.createProject({
  title: "Whitespace lane membership",
  narrative_engine: "novel",
});
const whitespaceSceneDraft = await whitespaceApi.createScene(whitespaceProject.id, {
  title: "Indented plotline",
  act: "Act I",
  chapter: "One",
});
const whitespaceScene = await whitespaceApi.updateScene(
  whitespaceProject.id,
  whitespaceSceneDraft.id,
  { plotline: " Main ", expected_revision: whitespaceSceneDraft.revision },
);
const whitespaceStart = await whitespaceApi.getTimeline(whitespaceProject.id);
const whitespaceLane = await whitespaceApi.executeTimelineCommand(whitespaceProject.id, {
  kind: "create_lane",
  expected_revision: whitespaceStart.revision,
  name: "Main",
}, "timeline-preview-whitespace-create");
const whitespaceRenamed = await whitespaceApi.executeTimelineCommand(whitespaceProject.id, {
  kind: "update_lane",
  expected_revision: whitespaceLane.timeline.revision,
  lane_id: whitespaceLane.timeline.lanes[0]!.id,
  name: "Renamed",
}, "timeline-preview-whitespace-rename");
check(
  whitespaceRenamed.affected_scene_ids.join(",") === String(whitespaceScene.id)
    && whitespaceRenamed.timeline.events[0]?.plotline === "Renamed"
    && whitespaceRenamed.timeline.events[0]?.lane_id === whitespaceLane.timeline.lanes[0]!.id,
  "preview lane rename must retain normalized member Scenes",
);
const timelinePersistenceApi = createMockApiClient();
const timelinePersistenceProject = await timelinePersistenceApi.createProject({
  title: "Timeline persistence",
  narrative_engine: "novel",
});
const firstPersistentScene = await timelinePersistenceApi.createScene(
  timelinePersistenceProject.id,
  { title: "A", act: "Act I", chapter: "One" },
);
const secondPersistentScene = await timelinePersistenceApi.createScene(
  timelinePersistenceProject.id,
  { title: "B", act: "Act I", chapter: "One" },
);
const thirdPersistentScene = await timelinePersistenceApi.createScene(
  timelinePersistenceProject.id,
  { title: "C", act: "Act I", chapter: "One" },
);
const persistenceStart = await timelinePersistenceApi.getTimeline(timelinePersistenceProject.id);
const persistentFirst = await timelinePersistenceApi.executeTimelineCommand(timelinePersistenceProject.id, {
  kind: "place_event",
  expected_revision: persistenceStart.revision,
  scene_id: firstPersistentScene.id,
  lane_id: null,
}, "timeline-preview-persist-first");
const persistentCustom = await timelinePersistenceApi.executeTimelineCommand(timelinePersistenceProject.id, {
  kind: "set_order_mode",
  expected_revision: persistentFirst.timeline.revision,
  mode: "custom",
}, "timeline-preview-persist-custom");
const persistentThird = await timelinePersistenceApi.executeTimelineCommand(timelinePersistenceProject.id, {
  kind: "place_event",
  expected_revision: persistentCustom.timeline.revision,
  scene_id: thirdPersistentScene.id,
  lane_id: null,
  index: 1,
}, "timeline-preview-persist-third");
const persistentSecond = await timelinePersistenceApi.executeTimelineCommand(timelinePersistenceProject.id, {
  kind: "place_event",
  expected_revision: persistentThird.timeline.revision,
  scene_id: secondPersistentScene.id,
  lane_id: null,
}, "timeline-preview-persist-second");
check(
  persistentSecond.timeline.events.map((event) => event.id).join(",")
    === [firstPersistentScene.id, thirdPersistentScene.id, secondPersistentScene.id].join(","),
  "preview explicit placement must persist a newly opted-in event even when its effective index already matches",
);

await timelinePersistenceApi.deleteScene(timelinePersistenceProject.id, thirdPersistentScene.id);
const directReplacement = await timelinePersistenceApi.createScene(
  timelinePersistenceProject.id,
  { title: "Direct replacement", act: "Act I", chapter: "One" },
);
const afterDirectReuse = await timelinePersistenceApi.getTimeline(timelinePersistenceProject.id);
check(
  directReplacement.id === thirdPersistentScene.id
    && !afterDirectReuse.events.some((event) => event.id === directReplacement.id)
    && afterDirectReuse.off_timeline.some((scene) => scene.id === directReplacement.id),
  "preview direct Scene deletion must scrub Timeline membership before an id is reused",
);
const directReplacementPlaced = await timelinePersistenceApi.executeTimelineCommand(
  timelinePersistenceProject.id,
  {
    kind: "place_event",
    expected_revision: afterDirectReuse.revision,
    scene_id: directReplacement.id,
    lane_id: null,
  },
  "timeline-preview-direct-replacement",
);
check(
  directReplacementPlaced.timeline.events.at(-1)?.id === directReplacement.id,
  "preview direct Scene deletion must scrub stale custom order before an id is reused",
);

const structureBeforeDelete = await timelinePersistenceApi.getStoryStructure(timelinePersistenceProject.id);
await timelinePersistenceApi.executeStoryStructureCommand(timelinePersistenceProject.id, {
  kind: "delete_scene",
  expected_revision: structureBeforeDelete.revision,
  scene_id: directReplacement.id,
});
const structureReplacement = await timelinePersistenceApi.createScene(
  timelinePersistenceProject.id,
  { title: "Structure replacement", act: "Act I", chapter: "One" },
);
const afterStructureReuse = await timelinePersistenceApi.getTimeline(timelinePersistenceProject.id);
check(
  structureReplacement.id === directReplacement.id
    && !afterStructureReuse.events.some((event) => event.id === structureReplacement.id)
    && afterStructureReuse.off_timeline.some((scene) => scene.id === structureReplacement.id),
  "preview guarded structure deletion must scrub Timeline state before an id is reused",
);
const createdTimelineLane = await timelineApi.executeTimelineCommand(1, {
  kind: "create_lane",
  expected_revision: initialTimeline.revision,
  name: "Memory",
  color_label: "violet",
  index: 1,
}, "timeline-preview-create-memory");
check(
  createdTimelineLane.changed
    && createdTimelineLane.timeline.revision !== initialTimeline.revision
    && createdTimelineLane.timeline.lanes[1]?.name === "Memory"
    && createdTimelineLane.affected_scene_ids.length === 0,
  "preview Timeline lane creation must be revisioned and preserve dense lane order",
);
let staleTimelineError: unknown = null;
try {
  await timelineApi.executeTimelineCommand(1, {
    kind: "create_lane",
    expected_revision: initialTimeline.revision,
    name: "Stale lane",
  }, "timeline-preview-stale");
} catch (error) {
  staleTimelineError = error;
}
check(
  staleTimelineError instanceof ApiRequestError
    && staleTimelineError.status === 409
    && staleTimelineError.code === "timeline_conflict"
    && !(await timelineApi.getTimeline(1)).lanes.some((lane) => lane.name === "Stale lane"),
  "preview Timeline commands must reject stale revisions without partial mutation",
);
const memoryLane = createdTimelineLane.timeline.lanes.find((lane) => lane.name === "Memory")!;
const structureOrderBeforeTimelineMove = (await timelineApi.getStoryStructure(1)).acts
  .flatMap((act) => act.chapters.flatMap((chapter) => chapter.scenes.map((scene) => scene.id)))
  .join(",");
const placedTimelineEvent = await timelineApi.executeTimelineCommand(1, {
  kind: "place_event",
  expected_revision: createdTimelineLane.timeline.revision,
  scene_id: 3,
  lane_id: memoryLane.id,
  index: 0,
}, "timeline-preview-place-event");
check(
  placedTimelineEvent.timeline.order_mode === "custom"
    && placedTimelineEvent.timeline.events[0]?.id === 3
    && placedTimelineEvent.timeline.events[0]?.lane_id === memoryLane.id
    && placedTimelineEvent.timeline.off_timeline.length === 0
    && placedTimelineEvent.timeline.story_flow.points.map((point) => point.scene_id).join(",")
      === placedTimelineEvent.timeline.events.map((event) => event.id).join(",")
    && placedTimelineEvent.timeline.mode_projection.kind === "screenplay"
    && placedTimelineEvent.timeline.mode_projection.scenes.map((scene) => scene.scene_id).join(",")
      === placedTimelineEvent.timeline.events.map((event) => event.id).join(","),
  "preview Timeline placement must atomically add, assign, and custom-order an existing Scene",
);
const structureOrderAfterTimelineMove = (await timelineApi.getStoryStructure(1)).acts
  .flatMap((act) => act.chapters.flatMap((chapter) => chapter.scenes.map((scene) => scene.id)))
  .join(",");
check(
  structureOrderAfterTimelineMove === structureOrderBeforeTimelineMove,
  "preview Timeline custom order must never mutate canonical manuscript order",
);
const removedTimelineEvent = await timelineApi.executeTimelineCommand(1, {
  kind: "remove_event",
  expected_revision: placedTimelineEvent.timeline.revision,
  scene_id: 3,
}, "timeline-preview-remove-event");
check(
  !removedTimelineEvent.timeline.events.some((event) => event.id === 3)
    && removedTimelineEvent.timeline.off_timeline.some((scene) => scene.id === 3)
    && (await timelineApi.listScenes(1)).some((scene) => scene.id === 3)
    && removedTimelineEvent.timeline.story_flow.points.every((point, index) => (
      point.scene_id === removedTimelineEvent.timeline.events[index]?.id
    )),
  "preview Timeline removal must keep the underlying Scene and return it off-Timeline",
);
const mainLane = removedTimelineEvent.timeline.lanes.find((lane) => lane.name === "MAIN · Marlow")!;
const deletedTimelineLane = await timelineApi.executeTimelineCommand(1, {
  kind: "delete_lane",
  expected_revision: removedTimelineEvent.timeline.revision,
  lane_id: mainLane.id,
}, "timeline-preview-delete-lane");
check(
  !deletedTimelineLane.timeline.lanes.some((lane) => lane.id === mainLane.id)
    && deletedTimelineLane.timeline.events
      .filter((event) => [1, 12, 22].includes(event.id))
      .every((event) => event.lane_id === null && event.plotline === ""),
  "preview Timeline lane deletion must keep its events in the virtual Unassigned row",
);
const previewStructure = await api.getStoryStructure(1);
check(
  previewStructure.project_id === 1
    && previewStructure.chapter_level === false
    && previewStructure.scene_count === 7
    && previewStructure.acts[0]?.number === "1"
    && previewStructure.acts[0]?.chapters[0]?.scenes[0]?.number === "1.1",
  "preview story structure must mirror the core-owned mode-aware hierarchy",
);
check(
  !("content" in (previewStructure.acts[0]?.chapters[0]?.scenes[0] ?? {})),
  "preview story structure scene references must stay compact",
);
const previewManuscript = await api.getManuscriptSnapshot(1);
const previewStructureOrder = previewStructure.acts.flatMap((act) =>
  act.chapters.flatMap((chapter) => chapter.scenes.map((scene) => scene.id)));
check(
  previewManuscript.project_id === 1
    && previewManuscript.scene_count === previewManuscript.scenes.length
    && previewManuscript.scenes.map((scene) => scene.id).join(",") === previewStructureOrder.join(",")
    && previewManuscript.scenes.every((scene, index) => scene.order_index === index + 1 && Boolean(scene.revision)),
  "preview manuscript snapshot must preserve canonical structure order and revisioned full scenes",
);
const writingModes = await api.writingModes();
check(writingModes.default_mode === "novel" && writingModes.modes.length === 5,
  "preview writing-mode catalog must expose all five canonical modes");
check(writingModes.modes.find((mode) => mode.id === "series")?.default_writing_format === "screenplay",
  "preview Series mode must use the core's screenplay writing format");

const initialProjects = await api.listProjects();
const search = await api.searchProject(initialProjects[0]!.id, "Marlow", ["scene", "psyke"]);
check(search.matches.length > 0 && search.matches.every((match) => match.kind === "scene" || match.kind === "psyke"),
  "preview project search must respect its typed kind filter");
const fixtureText = await api.searchProject(initialProjects[0]!.id, "Marlow", ["note", "psyke"]);
check(new Set(fixtureText.matches.map((match) => match.kind)).size === 2,
  "preview fixture project search must expose its note and PSYKE matches");
const fixtureComment = await api.searchProject(initialProjects[0]!.id, "HELIOS-9", ["comment"]);
check(fixtureComment.matches.some((match) => match.kind === "comment"),
  "preview fixture project search must expose its comment matches");
const foreignText = await api.searchProject(initialProjects[1]!.id, "Marlow", ["note", "psyke"]);
const foreignComment = await api.searchProject(initialProjects[1]!.id, "HELIOS-9", ["comment"]);
check(foreignText.matches.length === 0 && foreignComment.matches.length === 0,
  "preview project search must not leak notes, PSYKE entries, or comments across projects");
const openedFixture = await api.openProject(initialProjects[0]!.id);
check(openedFixture.title === initialProjects[0]!.title, "preview project opening must return an existing project");
const pendingCreate = api.createProject({ title: "Project lifecycle test", narrative_engine: "series" });
check(getProjectSaveStatusSnapshot().inFlightCount === 1,
  "preview mock mutations must be visible to the global handoff barrier");
await flushPendingProjectSaves();
const createdProject = await pendingCreate;
check(getProjectSaveStatusSnapshot().inFlightCount === 0,
  "preview mock mutation tracking must settle after the write completes");
check(createdProject.default_writing_format === "screenplay" && createdProject.format_mode === "screenplay",
  "preview project creation must apply canonical mode defaults");
createdProject.title = "caller mutation";
check((await api.getProject(createdProject.id)).title === "Project lifecycle test",
  "preview project responses must not expose mutable backing records");
const updatedProject = await api.updateProject(createdProject.id, { title: "Renamed lifecycle test", description: "Round trip" });
check(updatedProject.title === "Renamed lifecycle test" && updatedProject.description === "Round trip",
  "preview project metadata updates must round-trip");
let invalidModeUpdate: unknown = null;
try {
  await api.updateProject(createdProject.id, { title: "Must not leak", narrative_engine: "invalid-mode" });
} catch (error) {
  invalidModeUpdate = error;
}
check(invalidModeUpdate instanceof ApiRequestError && (await api.getProject(createdProject.id)).title === "Renamed lifecycle test",
  "preview project updates must validate atomically before mutating metadata");
const seriesModeRevision = (await api.getStoryStructure(createdProject.id)).revision;
await api.updateProject(createdProject.id, { narrative_engine: "novel" });
const novelModeRevision = (await api.getStoryStructure(createdProject.id)).revision;
check(seriesModeRevision !== novelModeRevision,
  "preview structure revisions must include project mode even when the Scene set is unchanged");
await api.updateProject(createdProject.id, { narrative_engine: "series" });
check((await api.saveProject(createdProject.id)).project_id === createdProject.id,
  "preview project save must return the authoritative project id");
check((await api.closeProject(createdProject.id)).ok, "preview project close must acknowledge the lifecycle action");
check((await api.deleteProject(createdProject.id)).deleted === createdProject.id,
  "preview project deletion must identify the deleted project");
let missingProject: unknown = null;
try {
  await api.openProject(createdProject.id);
} catch (error) {
  missingProject = error;
}
check(missingProject instanceof ApiRequestError && missingProject.status === 404,
  "preview project lifecycle must reject missing project ids like the core");

const whiteboardImport = await api.importWhiteboard({
  title: "Imported draft",
  mode: "novel",
  blocks: [{ id: "heading", type: "heading", text: "Opening" }, { id: "body", type: "paragraph", text: "A first paragraph." }],
});
check(whiteboardImport.scenes_created === 1 && whiteboardImport.scene_ids_by_block.every((id) => id > 0),
  "preview Whiteboard import must return usable scene mappings");
check((await api.openProject(whiteboardImport.project_id)).title === "Imported draft",
  "preview Whiteboard imports must create immediately openable projects");
check((await api.listScenes(whiteboardImport.project_id)).length === 1 && (await api.listScenes(2)).length === 0,
  "preview imported scenes must remain scoped to their destination project");
const manuscriptImport = await api.importManuscript({
  title: "Imported prose",
  mode: "novel",
  filename: "imported.md",
  content_base64: "IyBPcGVuaW5n",
});
check(manuscriptImport.scenes_created === 1 && (await api.getProject(manuscriptImport.project_id)).title === "Imported prose",
  "preview manuscript imports must create immediately readable projects");
const isolatedApi = createMockApiClient();
check(!(await isolatedApi.listProjects()).some((project) => project.id === whiteboardImport.project_id || project.id === manuscriptImport.project_id),
  "new preview clients must not inherit project mutations from replaced transports");

const psykeCount = (await api.listPsyke(1)).length;
const commandPlan = await api.planPsykeConsoleCommand(1, { command: "/create character Ione" });
check(commandPlan.mutates && commandPlan.requires_confirmation, "preview command plan must identify project writes");
check((await api.listPsyke(1)).length === psykeCount, "preview command planning must stay read-only");
const commandResult = await api.executePsykeConsoleCommand(1, { plan_id: commandPlan.plan_id, confirmed: true }, commandPlan.mutates);
check(commandResult.mutated && commandResult.target_type === "psyke_entry", "preview command execution must return an authoritative navigation target");
let commandReplay: unknown = null;
try {
  await api.executePsykeConsoleCommand(1, { plan_id: commandPlan.plan_id, confirmed: true }, commandPlan.mutates);
} catch (error) {
  commandReplay = error;
}
check(commandReplay instanceof ApiRequestError && commandReplay.status === 404, "preview command plans must be single-use");

const initial = await api.getAdapt(1);
check(initial.mode === "Structure", "preview should start in automatic Structure mode");

await api.patchAiBehavior(1, { adaptive_override: "Refinement" });
const overridden = await api.getAdapt(1);
check(overridden.mode === "Refinement", "adaptive override must round-trip in preview");
check(overridden.override === "Refinement", "preview must expose the active override");

const voice = await api.voiceHistory(1);
check(voice.entries.length > 0, "preview Voice history should contain a reviewable segment");
const otherVoice = await api.voiceHistory(2);
check(otherVoice.entries.length === 0, "preview Voice history must stay project-scoped");

const scene = (await api.listScenes(1))[0]!;
const updatedScene = await api.updateScene(1, scene.id, {
  content: `${scene.content}\nrevision-safe`,
  expected_revision: scene.revision,
});
check(updatedScene.revision !== scene.revision, "scene mutation should advance its revision");
check((await isolatedApi.listScenes(1))[0]!.content === scene.content,
  "replaced preview clients must not inherit scene mutations from the old transport");
const structuralPatchBaseline = (await api.listScenes(1)).find((candidate) => candidate.id === scene.id)!;
const structuralPatchCases: Array<{
  field: "act" | "chapter" | "sort_order";
  patch: Parameters<typeof api.updateScene>[2];
}> = [
  { field: "act", patch: { act: "Moved Act", expected_revision: "stale" } },
  { field: "chapter", patch: { chapter: "Moved Chapter", expected_revision: updatedScene.revision } },
  { field: "sort_order", patch: { sort_order: 0, expected_revision: updatedScene.revision } },
];
for (const { field, patch } of structuralPatchCases) {
  let structuralPatchError: unknown = null;
  try {
    await api.updateScene(1, scene.id, patch);
  } catch (error) {
    structuralPatchError = error;
  }
  check(
    structuralPatchError instanceof ApiRequestError
      && structuralPatchError.status === 400
      && structuralPatchError.code === "bad_request"
      && structuralPatchError.message.includes(field),
    `preview Scene PATCH must reject the explicit structural field ${field}`,
  );
}
const structuralPatchAfter = (await api.listScenes(1)).find((candidate) => candidate.id === scene.id)!;
check(
  structuralPatchAfter.act === structuralPatchBaseline.act
    && structuralPatchAfter.chapter === structuralPatchBaseline.chapter
    && structuralPatchAfter.sort_order === structuralPatchBaseline.sort_order
    && structuralPatchAfter.revision === structuralPatchBaseline.revision,
  "rejected structural Scene PATCHes must not mutate or reorder preview state",
);
let staleConflict: unknown = null;
try {
  await api.updateScene(1, scene.id, { content: "stale", expected_revision: scene.revision });
} catch (error) {
  staleConflict = error;
}
check(staleConflict instanceof ApiRequestError && staleConflict.code === "scene_conflict",
  "preview mock should reject a stale scene revision like the core");

const structureBeforeMove = await api.getStoryStructure(1);
const movedStructure = await api.placeScene(1, 3, {
  expected_revision: structureBeforeMove.revision,
  act: "ACT I",
  chapter: "1.2",
  index: 1,
});
const movedChapter = movedStructure.acts
  .find((act) => act.name === "ACT I")?.chapters
  .find((chapter) => chapter.name === "1.2");
check(
  movedStructure.revision !== structureBeforeMove.revision
    && movedChapter?.scenes.map((item) => item.id).join(",") === "2,3",
  "preview structure placement must atomically reparent, resequence, and advance its revision",
);
let staleStructureConflict: unknown = null;
try {
  await api.placeScene(1, 3, {
    expected_revision: structureBeforeMove.revision,
    act: "ACT I",
    chapter: "1.2",
    index: 0,
  });
} catch (error) {
  staleStructureConflict = error;
}
check(
  staleStructureConflict instanceof ApiRequestError
    && staleStructureConflict.code === "structure_conflict",
  "preview structure placement must reject a stale project-wide revision",
);

const emptyNovelStructure = await api.getStoryStructure(2);
const pendingActCreate = api.executeStoryStructureCommand(2, {
  kind: "create_act",
  expected_revision: emptyNovelStructure.revision,
  act: "Act One",
  index: 0,
});
check(getProjectSaveStatusSnapshot().inFlightCount === 1,
  "preview structure commands must participate in the global handoff barrier");
await flushPendingProjectSaves();
const createdAct = await pendingActCreate;
const actSeedId = createdAct.created_scene_id!;
check(
  createdAct.changed
    && createdAct.affected_scene_ids.join(",") === String(actSeedId)
    && createdAct.structure.acts[0]?.name === "Act One"
    && createdAct.structure.acts[0]?.chapters[0]?.name === "Chapter 1",
  "preview create_act must seed and position a valid canonical Act chain",
);

const createdChapter = await api.executeStoryStructureCommand(2, {
  kind: "create_chapter",
  expected_revision: createdAct.structure.revision,
  act: "Act One",
  chapter: "Chapter Two",
  index: 1,
});
const chapterSeedId = createdChapter.created_scene_id!;
check(
  createdChapter.structure.acts[0]?.chapters.map((chapter) => chapter.name).join(",")
    === "Chapter 1,Chapter Two",
  "preview create_chapter must seed a named Chapter at its zero-based position",
);

const createdCanonicalScene = await api.executeStoryStructureCommand(2, {
  kind: "create_scene",
  expected_revision: createdChapter.structure.revision,
  title: "Chapter Two Follow-up",
  act: "Act One",
  chapter: "Chapter Two",
  index: 1,
});
const canonicalSceneId = createdCanonicalScene.created_scene_id!;
check(
  createdCanonicalScene.structure.acts[0]?.chapters[1]?.scenes.map((item) => item.id).join(",")
    === `${chapterSeedId},${canonicalSceneId}`,
  "preview create_scene must insert within existing destination siblings",
);

const renamedAct = await api.executeStoryStructureCommand(2, {
  kind: "rename_act",
  expected_revision: createdCanonicalScene.structure.revision,
  act: "Act One",
  new_name: "Opening",
});
check(
  renamedAct.affected_scene_ids.length === 3
    && renamedAct.structure.acts[0]?.name === "Opening",
  "preview rename_act must rewrite every matching member without merging",
);
const renamedChapter = await api.executeStoryStructureCommand(2, {
  kind: "rename_chapter",
  expected_revision: renamedAct.structure.revision,
  act: "Opening",
  chapter: "Chapter Two",
  new_name: "Middle",
});
check(
  renamedChapter.affected_scene_ids.join(",") === `${chapterSeedId},${canonicalSceneId}`
    && renamedChapter.structure.acts[0]?.chapters[1]?.name === "Middle",
  "preview rename_chapter must stay scoped to its parent Act",
);

const detachedChapter = await api.executeStoryStructureCommand(2, {
  kind: "detach_chapter",
  expected_revision: renamedChapter.structure.revision,
  act: "Opening",
  chapter: "Middle",
});
check(
  detachedChapter.structure.orphan_count === 2
    && detachedChapter.structure.acts[0]?.chapters.at(-1)?.unassigned === true,
  "preview detach_chapter must preserve Scenes while clearing only their Chapter label",
);
const detachedAct = await api.executeStoryStructureCommand(2, {
  kind: "detach_act",
  expected_revision: detachedChapter.structure.revision,
  act: "Opening",
});
check(
  detachedAct.affected_scene_ids.length === 3
    && detachedAct.structure.orphan_count === 3
    && detachedAct.structure.acts.at(-1)?.unassigned === true,
  "preview detach_act must preserve Scenes and Chapter labels while clearing their Act",
);
const repaired = await api.executeStoryStructureCommand(2, {
  kind: "repair_orphans",
  expected_revision: detachedAct.structure.revision,
});
check(
  repaired.changed
    && repaired.affected_scene_ids.length === 3
    && repaired.structure.orphan_count === 0
    && repaired.structure.acts[0]?.name === "Recovered Act",
  "preview repair_orphans must repair all and only missing canonical labels",
);

let duplicateRename: unknown = null;
try {
  await api.executeStoryStructureCommand(2, {
    kind: "rename_chapter",
    expected_revision: repaired.structure.revision,
    act: "Recovered Act",
    chapter: "Chapter 1",
    new_name: "Recovered Chapter",
  });
} catch (error) {
  duplicateRename = error;
}
check(
  duplicateRename instanceof ApiRequestError
    && duplicateRename.status === 400
    && duplicateRename.code === "bad_request"
    && (await api.getStoryStructure(2)).revision === repaired.structure.revision,
  "preview structure command validation must fail atomically before mutation",
);

const deletedCanonicalScene = await api.executeStoryStructureCommand(2, {
  kind: "delete_scene",
  expected_revision: repaired.structure.revision,
  scene_id: canonicalSceneId,
});
check(
  deletedCanonicalScene.created_scene_id === null
    && deletedCanonicalScene.affected_scene_ids.join(",") === String(canonicalSceneId)
    && !deletedCanonicalScene.structure.acts.some((act) => (
      act.chapters.some((chapter) => chapter.scenes.some((item) => item.id === canonicalSceneId))
    )),
  "preview delete_scene must remove exactly the requested Scene and return authoritative metadata",
);
const noRepairNeeded = await api.executeStoryStructureCommand(2, {
  kind: "repair_orphans",
  expected_revision: deletedCanonicalScene.structure.revision,
});
check(
  !noRepairNeeded.changed
    && noRepairNeeded.affected_scene_ids.length === 0
    && noRepairNeeded.structure.revision === deletedCanonicalScene.structure.revision,
  "preview repair_orphans must be idempotent",
);
let missingContainerError: unknown = null;
try {
  await api.executeStoryStructureCommand(2, {
    kind: "detach_act",
    expected_revision: noRepairNeeded.structure.revision,
    act: "Missing Act",
  });
} catch (error) {
  missingContainerError = error;
}
check(
  missingContainerError instanceof ApiRequestError
    && missingContainerError.status === 400
    && missingContainerError.code === "bad_request",
  "preview missing derived containers must be semantic 400 errors",
);
let missingSceneError: unknown = null;
try {
  await api.executeStoryStructureCommand(2, {
    kind: "delete_scene",
    expected_revision: noRepairNeeded.structure.revision,
    scene_id: 999_999,
  });
} catch (error) {
  missingSceneError = error;
}
check(
  missingSceneError instanceof ApiRequestError
    && missingSceneError.status === 404
    && missingSceneError.code === "not_found",
  "preview missing Scene resources must remain 404 errors",
);
let staleCommandConflict: unknown = null;
try {
  await api.executeStoryStructureCommand(2, {
    kind: "delete_scene",
    expected_revision: emptyNovelStructure.revision,
    scene_id: actSeedId,
  });
} catch (error) {
  staleCommandConflict = error;
}
check(
  staleCommandConflict instanceof ApiRequestError
    && staleCommandConflict.code === "structure_conflict",
  "preview structure commands must reject stale revisions before mutation",
);

const canonicalCommandApi = createMockApiClient();
const leadingOrphan = await canonicalCommandApi.createScene(2, { title: "Leading orphan" });
const trailingNamed = await canonicalCommandApi.createScene(2, {
  title: "Trailing named Scene",
  act: "Act One",
  chapter: "Chapter One",
});
check(
  (await canonicalCommandApi.listScenes(2)).map((sceneRow) => sceneRow.id).join(",")
    === `${leadingOrphan.id},${trailingNamed.id}`,
  "preview canonicalization regression must begin with a raw leading orphan",
);
const leadingOrphanStructure = await canonicalCommandApi.getStoryStructure(2);
const canonicalizedRename = await canonicalCommandApi.executeStoryStructureCommand(2, {
  kind: "rename_act",
  expected_revision: leadingOrphanStructure.revision,
  act: "Act One",
  new_name: "Opening",
});
check(
  canonicalizedRename.affected_scene_ids.join(",") === String(trailingNamed.id)
    && (await canonicalCommandApi.listScenes(2)).map((sceneRow) => sceneRow.id).join(",")
      === `${trailingNamed.id},${leadingOrphan.id}`,
  "preview non-Series commands must persist canonical order with Unassigned buckets last",
);

const episodeOne = await api.createEpisode(3, 1, { episode_number: 1, title: "Pilot" });
const episodeTwo = await api.createEpisode(3, 1, { episode_number: 2, title: "Aftermath" });
const episodeOneId = episodeOne.id!;
const episodeTwoId = episodeTwo.id!;
check(
  (await api.listEpisodes(3)).map((episode) => episode.id).join(",") === `${episodeOneId},${episodeTwoId}`,
  "preview Episodes must retain project ownership for Series command validation",
);

const emptySeriesStructure = await api.getStoryStructure(3);
let unknownEpisodeError: unknown = null;
try {
  await api.executeStoryStructureCommand(3, {
    kind: "create_act",
    expected_revision: emptySeriesStructure.revision,
    act: "Unknown Episode Act",
    index: 0,
    episode_id: 999_999,
  });
} catch (error) {
  unknownEpisodeError = error;
}
check(
  unknownEpisodeError instanceof ApiRequestError && unknownEpisodeError.status === 404,
  "preview Series commands must reject Episodes that are not owned by the project",
);

let nonSeriesEpisodeError: unknown = null;
try {
  await api.executeStoryStructureCommand(2, {
    kind: "create_act",
    expected_revision: noRepairNeeded.structure.revision,
    act: "Episode-only Act",
    index: 1,
    episode_id: episodeOneId,
  });
} catch (error) {
  nonSeriesEpisodeError = error;
}
check(
  nonSeriesEpisodeError instanceof ApiRequestError && nonSeriesEpisodeError.status === 400,
  "preview non-Series commands must reject a non-null episode_id",
);

let missingSeriesChapterError: unknown = null;
try {
  await api.executeStoryStructureCommand(3, {
    kind: "create_act",
    expected_revision: emptySeriesStructure.revision,
    act: "Missing Chapter",
    chapter: "",
    index: 0,
    episode_id: episodeOneId,
  });
} catch (error) {
  missingSeriesChapterError = error;
}
check(
  missingSeriesChapterError instanceof ApiRequestError && missingSeriesChapterError.status === 400,
  "preview Series groups must require a named Chapter parent",
);

const episodeOneShared = await api.executeStoryStructureCommand(3, {
  kind: "create_act",
  expected_revision: emptySeriesStructure.revision,
  act: "Shared Act",
  index: 0,
  episode_id: episodeOneId,
});
const episodeOneSharedId = episodeOneShared.created_scene_id!;
const episodeTwoShared = await api.executeStoryStructureCommand(3, {
  kind: "create_act",
  expected_revision: episodeOneShared.structure.revision,
  act: "Shared Act",
  index: 0,
  episode_id: episodeTwoId,
});
const episodeTwoSharedId = episodeTwoShared.created_scene_id!;
check(
  episodeTwoShared.structure.chapter_level === false
    && episodeTwoShared.structure.orphan_count === 0
    && structurePaths(episodeTwoShared.structure).filter((scene) => (
      scene.id === episodeOneSharedId || scene.id === episodeTwoSharedId
    )).every((scene) => scene.chapter === "Chapter 1"),
  "preview Series may reuse Act labels across Episodes while seeding required Chapter parents",
);

let duplicateSeriesAct: unknown = null;
try {
  await api.executeStoryStructureCommand(3, {
    kind: "create_act",
    expected_revision: episodeTwoShared.structure.revision,
    act: "Shared Act",
    index: 1,
    episode_id: episodeOneId,
  });
} catch (error) {
  duplicateSeriesAct = error;
}
check(
  duplicateSeriesAct instanceof ApiRequestError
    && duplicateSeriesAct.status === 400
    && duplicateSeriesAct.code === "bad_request",
  "preview Series duplicate checks must remain strict inside one Episode",
);

const episodeOneFirst = await api.executeStoryStructureCommand(3, {
  kind: "create_act",
  expected_revision: episodeTwoShared.structure.revision,
  act: "Episode One First",
  index: 0,
  episode_id: episodeOneId,
});
const episodeTwoFirst = await api.executeStoryStructureCommand(3, {
  kind: "create_act",
  expected_revision: episodeOneFirst.structure.revision,
  act: "Episode Two First",
  index: 0,
  episode_id: episodeTwoId,
});
check(
  structurePaths(episodeTwoFirst.structure).find((scene) => scene.id === episodeOneFirst.created_scene_id)?.episode_id
      === episodeOneId
    && structurePaths(episodeTwoFirst.structure).find((scene) => scene.id === episodeTwoFirst.created_scene_id)?.episode_id
      === episodeTwoId,
  "preview Series Act creation must retain the selected Episode scope",
);
let episodeLocalActIndexError: unknown = null;
try {
  await api.executeStoryStructureCommand(3, {
    kind: "create_act",
    expected_revision: episodeTwoFirst.structure.revision,
    act: "Outside Episode One",
    index: 3,
    episode_id: episodeOneId,
  });
} catch (error) {
  episodeLocalActIndexError = error;
}
check(
  episodeLocalActIndexError instanceof ApiRequestError && episodeLocalActIndexError.status === 400,
  "preview Series Act index bounds must count only Acts in the selected Episode",
);

const episodeOneChapter = await api.executeStoryStructureCommand(3, {
  kind: "create_chapter",
  expected_revision: episodeTwoFirst.structure.revision,
  act: "Shared Act",
  chapter: "Episode Chapter",
  index: 1,
  episode_id: episodeOneId,
});
const episodeOneChapterId = episodeOneChapter.created_scene_id!;
let episodeLocalChapterIndexError: unknown = null;
try {
  await api.executeStoryStructureCommand(3, {
    kind: "create_chapter",
    expected_revision: episodeOneChapter.structure.revision,
    act: "Shared Act",
    chapter: "Outside Episode Two",
    index: 2,
    episode_id: episodeTwoId,
  });
} catch (error) {
  episodeLocalChapterIndexError = error;
}
check(
  episodeLocalChapterIndexError instanceof ApiRequestError && episodeLocalChapterIndexError.status === 400,
  "preview Series Chapter index bounds must count only Chapters in the selected Episode",
);
let missingEpisodeDestination: unknown = null;
try {
  await api.executeStoryStructureCommand(3, {
    kind: "create_scene",
    expected_revision: episodeOneChapter.structure.revision,
    act: "Shared Act",
    chapter: "Episode Chapter",
    index: 1,
    episode_id: episodeTwoId,
  });
} catch (error) {
  missingEpisodeDestination = error;
}
check(
  missingEpisodeDestination instanceof ApiRequestError
    && missingEpisodeDestination.status === 400
    && missingEpisodeDestination.code === "bad_request",
  "preview Series create_scene must require its destination in the selected Episode",
);

const episodeTwoChapter = await api.executeStoryStructureCommand(3, {
  kind: "create_chapter",
  expected_revision: episodeOneChapter.structure.revision,
  act: "Shared Act",
  chapter: "Episode Chapter",
  index: 1,
  episode_id: episodeTwoId,
});
const episodeTwoChapterId = episodeTwoChapter.created_scene_id!;
check(
  structurePaths(episodeTwoChapter.structure).filter((scene) => (
    scene.id === episodeOneChapterId || scene.id === episodeTwoChapterId
  )).every((scene) => scene.chapter === "Episode Chapter"),
  "preview Series Chapter existence and duplicate checks must be Episode-scoped",
);

const rawSeriesOrderBeforePlacement = (await api.listScenes(3)).map((sceneRow) => sceneRow.id).join(",");
const placedSeriesStructure = await api.placeScene(3, episodeTwoChapterId, {
  expected_revision: episodeTwoChapter.structure.revision,
  act: "Shared Act",
  chapter: "Episode Chapter",
  index: 0,
  episode_id: episodeTwoId,
});
const rawSeriesOrderAfterPlacement = (await api.listScenes(3)).map((sceneRow) => sceneRow.id).join(",");
check(
  rawSeriesOrderAfterPlacement === rawSeriesOrderBeforePlacement,
  "preview Series placement must preserve raw cross-Episode order instead of flattening the collapsed DTO",
);

const renamedSeriesAct = await api.executeStoryStructureCommand(3, {
  kind: "rename_act",
  expected_revision: placedSeriesStructure.revision,
  act: "Shared Act",
  new_name: "Episode One Act",
  episode_id: episodeOneId,
});
check(
  renamedSeriesAct.affected_scene_ids.join(",") === `${episodeOneSharedId},${episodeOneChapterId}`
    && structurePaths(renamedSeriesAct.structure).find((scene) => scene.id === episodeTwoSharedId)?.act === "Shared Act",
  "preview Series Act renames must mutate only the selected Episode",
);

const renamedSeriesChapter = await api.executeStoryStructureCommand(3, {
  kind: "rename_chapter",
  expected_revision: renamedSeriesAct.structure.revision,
  act: "Shared Act",
  chapter: "Episode Chapter",
  new_name: "Episode Two Chapter",
  episode_id: episodeTwoId,
});
check(
  renamedSeriesChapter.affected_scene_ids.join(",") === String(episodeTwoChapterId)
    && structurePaths(renamedSeriesChapter.structure).find((scene) => scene.id === episodeOneChapterId)?.chapter
      === "Episode Chapter",
  "preview Series Chapter renames must mutate only the selected Episode",
);

const detachedSeriesChapter = await api.executeStoryStructureCommand(3, {
  kind: "detach_chapter",
  expected_revision: renamedSeriesChapter.structure.revision,
  act: "Shared Act",
  chapter: "Episode Two Chapter",
  episode_id: episodeTwoId,
});
check(
  detachedSeriesChapter.affected_scene_ids.join(",") === String(episodeTwoChapterId)
    && detachedSeriesChapter.structure.orphan_count === 1
    && structurePaths(detachedSeriesChapter.structure).find((scene) => scene.id === episodeTwoChapterId)?.is_orphan,
  "preview Series Chapter detachment must be Episode-scoped and produce a repairable orphan",
);

const repairedSeries = await api.executeStoryStructureCommand(3, {
  kind: "repair_orphans",
  expected_revision: detachedSeriesChapter.structure.revision,
});
check(
  repairedSeries.affected_scene_ids.join(",") === String(episodeTwoChapterId)
    && repairedSeries.structure.orphan_count === 0
    && structurePaths(repairedSeries.structure).find((scene) => scene.id === episodeTwoChapterId)?.chapter
      === "Recovered Chapter",
  "preview Series orphan repair must restore missing Chapter parents",
);

const detachedSeriesAct = await api.executeStoryStructureCommand(3, {
  kind: "detach_act",
  expected_revision: repairedSeries.structure.revision,
  act: "Shared Act",
  episode_id: episodeTwoId,
});
check(
  detachedSeriesAct.affected_scene_ids.join(",") === `${episodeTwoSharedId},${episodeTwoChapterId}`
    && structurePaths(detachedSeriesAct.structure).find((scene) => scene.id === episodeOneSharedId)?.act
      === "Episode One Act",
  "preview Series Act detachment must preserve same-named groups in other Episodes",
);

const legacyEpisodeSibling = await api.executeStoryStructureCommand(3, {
  kind: "create_scene",
  expected_revision: detachedSeriesAct.structure.revision,
  title: "Legacy Episode sibling",
  act: "Episode One First",
  chapter: "Chapter 1",
  index: 1,
  episode_id: episodeOneId,
});
const legacyEpisodeSiblingId = legacyEpisodeSibling.created_scene_id!;
await api.updateProject(3, { narrative_engine: "screenplay" });
const convertedFlatStructure = await api.getStoryStructure(3);
const clearedLegacyEpisode = await api.placeScene(3, legacyEpisodeSiblingId, {
  expected_revision: convertedFlatStructure.revision,
  act: "Episode One First",
  chapter: "Chapter 1",
  index: 0,
  episode_id: null,
});
const preservedLegacyEpisode = await api.placeScene(3, episodeOneFirst.created_scene_id!, {
  expected_revision: clearedLegacyEpisode.revision,
  act: "Episode One First",
  chapter: "Chapter 1",
  index: 0,
});
check(
  structurePaths(preservedLegacyEpisode).find((scene) => scene.id === legacyEpisodeSiblingId)?.episode_id === null
    && structurePaths(preservedLegacyEpisode).find((scene) => scene.id === episodeOneFirst.created_scene_id)?.episode_id
      === episodeOneId,
  "preview non-Series placement must clear a legacy Episode only for explicit episode_id null",
);

const initialComments = await api.listComments(1);
const rootComment = initialComments[0]!;
const withReply = await api.createCommentReply(1, rootComment.id, { body: "Native review reply", author: "you" });
const nativeReply = withReply.replies.find((reply) => reply.body === "Native review reply");
check(nativeReply?.source_id === "", "preview comment replies preserve native provenance");
await api.deleteCommentReply(1, rootComment.id, nativeReply!.id);
check(!(await api.listComments(1))[0]!.replies.some((reply) => reply.id === nativeReply!.id), "preview reply deletion round-trips");

const createdComment = await api.createComment(1, {
  anchor: { ...rootComment.anchor },
  quote: rootComment.quote,
  body: "Native panel comment",
});
check(createdComment.source_id === "" && createdComment.body === "Native panel comment", "preview comment creation uses native provenance");
const editedComment = await api.updateComment(1, createdComment.id, { body: "Edited native panel comment" });
check(editedComment.body === "Edited native panel comment", "preview comment editing round-trips");
await api.deleteComment(1, createdComment.id);
check(!(await api.listComments(1)).some((comment) => comment.id === createdComment.id), "preview thread deletion round-trips");
const editedImported = await api.updateComment(1, rootComment.id, { body: "Imported provenance stays immutable" });
check(editedImported.source_id === rootComment.source_id && editedImported.body === "Imported provenance stays immutable",
  "imported comment bodies remain editable without changing provenance");
const importedReply = editedImported.replies.find((reply) => reply.source_id)!;
await api.deleteCommentReply(1, rootComment.id, importedReply.id);
check(!(await api.listComments(1))[0]!.replies.some((reply) => reply.id === importedReply.id),
  "imported replies remain deletable while provenance is present");

const workflowApi = createMockApiClient();
const workflowTemplates = await workflowApi.getWorkflowTemplates(1);
const initialWorkflowRuns = await workflowApi.getWorkflows(1);
const initialWorkflow = initialWorkflowRuns.find((run) => run.template_id === "rewrite")!;
check(
  workflowTemplates.some((template) => template.id === "rewrite")
    && workflowTemplates.every((template) => template.modes.length === 0 || template.modes.includes("screenplay"))
    && initialWorkflow.project_id === 1
    && /^[0-9a-f]{64}$/.test(initialWorkflow.revision)
    && initialWorkflow.steps.every((step) => Boolean(step.kind) && step.created_at != null),
  "preview Guided Workflows must expose mode-filtered rich templates and revisioned project-owned runs",
);
const initialWorkflowEvents = await workflowApi.getWorkflowEvents(1, initialWorkflow.id, 1);
check(
  initialWorkflowEvents.length === 1
    && initialWorkflowEvents[0]?.workflow_run_id === initialWorkflow.id,
  "preview Guided Workflow events must honor the bounded run-owned limit",
);
const activeWorkflowStep = initialWorkflow.steps.find((step) => step.step_id === initialWorkflow.current_step_id)!;
const completeWorkflowCommand = {
  kind: "complete_step" as const,
  run_id: initialWorkflow.id,
  step_id: activeWorkflowStep.step_id,
  expected_revision: initialWorkflow.revision,
};
const workflowKey = "preview-workflow-key-0001";
const completedWorkflow = await workflowApi.executeWorkflowCommand(1, completeWorkflowCommand, workflowKey);
check(
  completedWorkflow.changed
    && !completedWorkflow.replayed
    && completedWorkflow.workflow.steps.find((step) => step.step_id === activeWorkflowStep.step_id)?.status === "completed"
    && completedWorkflow.applied_revision === completedWorkflow.workflow.revision,
  "preview Guided Workflow commands must atomically apply the current active step",
);
const workflowReceipt = await workflowApi.getWorkflowCommandReceipt(1, workflowKey, completeWorkflowCommand);
const replayedWorkflow = await workflowApi.executeWorkflowCommand(1, completeWorkflowCommand, workflowKey);
check(
  workflowReceipt.original_run_id === initialWorkflow.id
    && workflowReceipt.applied_revision === completedWorkflow.applied_revision
    && replayedWorkflow.replayed
    && !replayedWorkflow.changed,
  "preview Guided Workflow command recovery must preserve a durable exact-command receipt",
);
let staleWorkflowFailure: unknown = null;
try {
  await workflowApi.executeWorkflowCommand(1, {
    kind: "pause",
    run_id: initialWorkflow.id,
    expected_revision: initialWorkflow.revision,
  }, "preview-workflow-key-0002");
} catch (error) {
  staleWorkflowFailure = error;
}
check(
  staleWorkflowFailure instanceof ApiRequestError
    && staleWorkflowFailure.status === 409
    && staleWorkflowFailure.code === "workflow_conflict",
  "preview Guided Workflow commands must reject stale revisions without mutating",
);
const startedWorkflow = await workflowApi.executeWorkflowCommand(1, {
  kind: "start_workflow",
  template_id: "project_setup",
}, "preview-workflow-key-0003");
check(
  startedWorkflow.workflow.template_id === "project_setup"
    && startedWorkflow.workflow.current_step_id === "title"
    && startedWorkflow.workflow.steps[0]?.status === "active",
  "preview Guided Workflow starts must materialize the selected compatible template",
);

console.log(`Preview API tests: ${passed} passed, 0 failed`);
