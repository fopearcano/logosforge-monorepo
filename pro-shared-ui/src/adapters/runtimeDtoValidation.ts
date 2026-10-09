import type {
  AiBehaviorDTO,
  AssistantResponseDTO,
  AssistantSettingsDTO,
  ConnectorActionDTO,
  ConnectorResultDTO,
  DeleteResultDTO,
  DecisionCardDTO,
  DecisionEvidenceDTO,
  DecisionRadarDTO,
  ExtractionJobDTO,
  ExtractionResultDTO,
  InlineCommentDTO,
  LogosActionDTO,
  LogosResultDTO,
  LogosSuggestionDTO,
  NearDupHintDTO,
  OutlineGenerateResultDTO,
  OutlineNodeDTO,
  ProjectDTO,
  ProjectActionResultDTO,
  ProjectSearchKind,
  ProjectSearchMatchDTO,
  ProjectSearchResponseDTO,
  PsykeConsoleAction,
  PsykeConsoleCommandPlanDTO,
  PsykeConsoleExecutionDTO,
  PsykeConsoleTarget,
  QuantumSettingsDTO,
  QuantumResultDTO,
  RelationProposalDTO,
  SceneDTO,
  ManuscriptSnapshotDTO,
  StoryStructureActDTO,
  StoryStructureChapterDTO,
  StoryStructureCommandDTO,
  StoryStructureCommandResultDTO,
  StoryStructureDTO,
  StoryStructureSceneDTO,
  TimelineCommandDTO,
  TimelineCommandReceiptDTO,
  TimelineCommandResultDTO,
  TimelineEventDTO,
  TimelineLaneDTO,
  TimelineLinkDTO,
  TimelineOffTimelineSceneDTO,
  TimelineOrderMode,
  TimelineSnapshotDTO,
  TimelineStructureLinkDTO,
  ProgressionAnchorKind,
  ProgressionCommandDTO,
  ProgressionCommandReceiptDTO,
  ProgressionCommandResultDTO,
  ProgressionCoverageDTO,
  ProgressionCoverageStatus,
  ProgressionKind,
  ProgressionSnapshotDTO,
  ProgressionTrackDTO,
  ProgressionBeatDTO,
  ProgressionSummaryDTO,
  CanvasPlotCommandDTO,
  CanvasPlotCommandResultDTO,
  CanvasPlotFrameDTO,
  CanvasPlotLinkDTO,
  CanvasPlotNodeDTO,
  CanvasPlotSnapshotDTO,
  ContinuityCommandDTO,
  ContinuityCommandReceiptDTO,
  ContinuityCommandResultDTO,
  ContinuityIssueDTO,
  ContinuityReportDTO,
  WorkflowCommandDTO,
  WorkflowCommandReceiptDTO,
  WorkflowCommandResultDTO,
  WorkflowEventDTO,
  WorkflowRecommendationDTO,
  WorkflowRunDTO,
  WorkflowStepDTO,
  WorkflowTemplateDTO,
  WorkflowTemplateStepDTO,
  KnowledgeGraphEdgeDTO,
  KnowledgeGraphEdgeIdentityDTO,
  KnowledgeGraphNodeDTO,
  KnowledgeGraphQueryDTO,
  KnowledgeGraphReadDTO,
  KnowledgeGraphViewMode,
  KnowledgeGraphCommandDTO,
  KnowledgeGraphCommandResultDTO,
  KnowledgeGraphCommandReceiptDTO,
  KnowledgeGraphHiddenEdgePageDTO,
  SceneExtractionDTO,
  SettingsDTO,
  VoiceBillyProposalDTO,
  WhiteboardImportResultDTO,
} from "@logosforge/ui-contracts";

type JsonRecord = Record<string, unknown>;

export type RuntimeDtoValidator<T> = (value: unknown) => T;

function valueKind(value: unknown): string {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  if (typeof value === "number" && !Number.isFinite(value)) return "non-finite number";
  return typeof value;
}

export class RuntimeDtoValidationError extends Error {
  readonly valuePath: string;
  readonly expected: string;
  readonly actual: string;

  constructor(valuePath: string, expected: string, value: unknown) {
    const actual = valueKind(value);
    super(valuePath + " must be " + expected + "; received " + actual);
    this.name = "RuntimeDtoValidationError";
    this.valuePath = valuePath;
    this.expected = expected;
    this.actual = actual;
  }
}

function fail(path: string, expected: string, value: unknown): never {
  throw new RuntimeDtoValidationError(path, expected, value);
}

function fieldPath(path: string, field: string): string {
  return path === "$" ? "$." + field : path + "." + field;
}

function record(value: unknown, path: string): JsonRecord {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return fail(path, "an object", value);
  }
  return value as JsonRecord;
}

function stringValue(value: unknown, path: string): string {
  return typeof value === "string" ? value : fail(path, "a string", value);
}

function booleanValue(value: unknown, path: string): boolean {
  return typeof value === "boolean" ? value : fail(path, "a boolean", value);
}

function integerValue(value: unknown, path: string): number {
  return typeof value === "number" && Number.isSafeInteger(value)
    ? value
    : fail(path, "a safe integer", value);
}

function numberValue(value: unknown, path: string): number {
  return typeof value === "number" && Number.isFinite(value)
    ? value
    : fail(path, "a finite number", value);
}

function stringOrIntegerValue(value: unknown, path: string): string | number {
  return typeof value === "string" ? value : integerValue(value, path);
}

function nullable<T>(
  value: unknown,
  path: string,
  validate: (item: unknown, itemPath: string) => T,
): T | null {
  return value === null ? null : validate(value, path);
}

function arrayOf<T>(
  value: unknown,
  path: string,
  validate: (item: unknown, itemPath: string) => T,
): T[] {
  if (!Array.isArray(value)) return fail(path, "an array", value);
  value.forEach((item, index) => validate(item, path + "[" + index + "]"));
  return value as T[];
}

function optional<T>(
  value: unknown,
  path: string,
  validate: (item: unknown, itemPath: string) => T,
): T | undefined {
  return value === undefined ? undefined : validate(value, path);
}

function stringArray(value: unknown, path: string): string[] {
  return arrayOf(value, path, stringValue);
}

function integerArray(value: unknown, path: string): number[] {
  return arrayOf(value, path, integerValue);
}

function recordArray(value: unknown, path: string): JsonRecord[] {
  return arrayOf(value, path, record);
}

function requireField(value: JsonRecord, key: string, path: string): unknown {
  if (!Object.prototype.hasOwnProperty.call(value, key)) {
    return fail(fieldPath(path, key), "present", undefined);
  }
  return value[key];
}

function project(value: unknown, path: string): ProjectDTO {
  const dto = record(value, path);
  integerValue(requireField(dto, "id", path), fieldPath(path, "id"));
  stringValue(requireField(dto, "title", path), fieldPath(path, "title"));
  stringValue(requireField(dto, "description", path), fieldPath(path, "description"));
  stringValue(requireField(dto, "narrative_engine", path), fieldPath(path, "narrative_engine"));
  stringValue(requireField(dto, "default_writing_format", path), fieldPath(path, "default_writing_format"));
  stringValue(requireField(dto, "format_mode", path), fieldPath(path, "format_mode"));
  return value as ProjectDTO;
}

const DECISION_SEVERITIES = new Set(["blocking", "warning", "suggestion", "opportunity", "info"]);
const DECISION_CONFIDENCES = new Set(["confirmed", "likely", "possible", "unknown"]);

function boundedDecisionString(
  value: unknown,
  path: string,
  maxLength: number,
  nonEmpty = false,
): string {
  const result = stringValue(value, path);
  if (result.length > maxLength || (nonEmpty && !result.trim())) {
    fail(path, `${nonEmpty ? "a non-empty " : "a "}string of at most ${maxLength} characters`, result);
  }
  return result;
}

function decisionEvidence(value: unknown, path: string): DecisionEvidenceDTO {
  const dto = record(value, path);
  boundedDecisionString(requireField(dto, "kind", path), fieldPath(path, "kind"), 32, true);
  boundedDecisionString(requireField(dto, "label", path), fieldPath(path, "label"), 512, true);
  boundedDecisionString(requireField(dto, "detail", path), fieldPath(path, "detail"), 1000);
  for (const key of ["graph_focus_key", "source_key", "target_key"] as const) {
    boundedDecisionString(requireField(dto, key, path), fieldPath(path, key), 512);
  }
  boundedDecisionString(requireField(dto, "edge_type", path), fieldPath(path, "edge_type"), 128);
  const confidence = boundedDecisionString(
    requireField(dto, "confidence", path),
    fieldPath(path, "confidence"),
    32,
  );
  if (confidence && !DECISION_CONFIDENCES.has(confidence)) {
    fail(fieldPath(path, "confidence"), "blank, confirmed, likely, possible, or unknown", confidence);
  }
  boundedDecisionString(requireField(dto, "source_system", path), fieldPath(path, "source_system"), 128);
  boundedDecisionString(requireField(dto, "provenance", path), fieldPath(path, "provenance"), 512);
  boundedDecisionString(requireField(dto, "related_section", path), fieldPath(path, "related_section"), 128);
  const relatedTargetType = boundedDecisionString(
    requireField(dto, "related_target_type", path),
    fieldPath(path, "related_target_type"),
    128,
  );
  const relatedTargetId = nullable(
    requireField(dto, "related_target_id", path),
    fieldPath(path, "related_target_id"),
    integerValue,
  );
  const relatedTargetKey = boundedDecisionString(
    requireField(dto, "related_target_key", path),
    fieldPath(path, "related_target_key"),
    512,
  );
  if (relatedTargetType === "scene" && (
    relatedTargetId === null || relatedTargetId <= 0 || relatedTargetKey
  )) {
    fail(path, "scene evidence with only a positive related_target_id", value);
  }
  if (relatedTargetType === "continuity_issue" && (
    relatedTargetId !== null || !/^[0-9a-f]{16}$/.test(relatedTargetKey)
  )) {
    fail(path, "continuity issue evidence with a canonical issue key", value);
  }
  if ((relatedTargetType === "progression_track" || relatedTargetType === "progression_beat") && (
    relatedTargetId === null || relatedTargetId <= 0 || relatedTargetKey
  )) {
    fail(path, "Progressions evidence with only a positive related_target_id", value);
  }
  if (!relatedTargetType && (relatedTargetId !== null || relatedTargetKey)) {
    fail(path, "related_target_type when an evidence target is set", value);
  }
  return value as DecisionEvidenceDTO;
}

function decisionCard(value: unknown, path: string): DecisionCardDTO {
  const dto = record(value, path);
  for (const key of ["id", "category", "title"] as const) {
    boundedDecisionString(requireField(dto, key, path), fieldPath(path, key), 512, true);
  }
  const severity = boundedDecisionString(
    requireField(dto, "severity", path),
    fieldPath(path, "severity"),
    32,
    true,
  );
  if (!DECISION_SEVERITIES.has(severity)) {
    fail(fieldPath(path, "severity"), "blocking, warning, suggestion, opportunity, or info", severity);
  }
  const confidence = boundedDecisionString(
    requireField(dto, "confidence", path),
    fieldPath(path, "confidence"),
    32,
    true,
  );
  if (!DECISION_CONFIDENCES.has(confidence)) {
    fail(fieldPath(path, "confidence"), "confirmed, likely, possible, or unknown", confidence);
  }
  boundedDecisionString(requireField(dto, "explanation", path), fieldPath(path, "explanation"), 4000);
  boundedDecisionString(requireField(dto, "suggested_action", path), fieldPath(path, "suggested_action"), 1000);
  boundedDecisionString(requireField(dto, "related_section", path), fieldPath(path, "related_section"), 128);
  const relatedTargetType = boundedDecisionString(
    requireField(dto, "related_target_type", path),
    fieldPath(path, "related_target_type"),
    128,
  );
  const relatedTargetId = nullable(
    requireField(dto, "related_target_id", path),
    fieldPath(path, "related_target_id"),
    integerValue,
  );
  const relatedTargetKey = boundedDecisionString(
    requireField(dto, "related_target_key", path),
    fieldPath(path, "related_target_key"),
    512,
  );
  if ((relatedTargetType === "progression_track" || relatedTargetType === "progression_beat") && (
    relatedTargetId === null || relatedTargetId <= 0 || relatedTargetKey
  )) {
    fail(path, "a Progressions target with only a positive related_target_id", value);
  }
  const createdFrom = boundedDecisionString(
    requireField(dto, "created_from", path),
    fieldPath(path, "created_from"),
    64,
    true,
  );
  const graphFocusKey = boundedDecisionString(
    requireField(dto, "graph_focus_key", path),
    fieldPath(path, "graph_focus_key"),
    512,
  );
  const graphViewMode = nullable(
    requireField(dto, "graph_view_mode", path),
    fieldPath(path, "graph_view_mode"),
    knowledgeGraphViewMode,
  );
  if (Boolean(graphFocusKey) !== (graphViewMode !== null)) {
    fail(fieldPath(path, "graph_view_mode"), "set exactly when graph_focus_key is set", graphViewMode);
  }
  booleanValue(requireField(dto, "graph_include_inferred", path), fieldPath(path, "graph_include_inferred"));
  const graphDepth = integerValue(requireField(dto, "graph_depth", path), fieldPath(path, "graph_depth"));
  if (graphDepth !== 1 && graphDepth !== 2) {
    fail(fieldPath(path, "graph_depth"), "1 or 2", graphDepth);
  }
  const evidence = arrayOf(
    requireField(dto, "evidence", path),
    fieldPath(path, "evidence"),
    decisionEvidence,
  );
  if (evidence.length > 5) fail(fieldPath(path, "evidence"), "an array with at most 5 items", evidence);
  const evidenceTotal = integerValue(
    requireField(dto, "evidence_total", path),
    fieldPath(path, "evidence_total"),
  );
  if (evidenceTotal < evidence.length) {
    fail(fieldPath(path, "evidence_total"), `at least the returned evidence length (${evidence.length})`, evidenceTotal);
  }
  if (createdFrom === "knowledge_graph" && (!graphFocusKey || evidence.length === 0)) {
    fail(path, "a graph focus and evidence for knowledge_graph cards", value);
  }
  if (createdFrom === "semantic_continuity") {
    const evidenceValid = evidence.length > 0 && evidence.every((item) => (
      !item.graph_focus_key
      && !item.source_key
      && !item.target_key
      && !item.edge_type
      && (item.related_target_type === "continuity_issue" || item.related_target_type === "scene")
      && (item.related_target_type !== "continuity_issue" || item.related_target_key === relatedTargetKey)
    ));
    const hasIssueAnchor = evidence.some((item) => (
      item.related_target_type === "continuity_issue"
      && item.related_target_key === relatedTargetKey
    ));
    if (
      relatedTargetType !== "continuity_issue"
      || relatedTargetId !== null
      || !/^[0-9a-f]{16}$/.test(relatedTargetKey)
      || Boolean(graphFocusKey)
      || graphViewMode !== null
      || !evidenceValid
      || !hasIssueAnchor
    ) {
      fail(path, "one canonical issue target and unmixed issue/scene evidence for semantic_continuity cards", value);
    }
  }
  return value as DecisionCardDTO;
}

export function validateDecisionRadarDTOForRequest(
  value: unknown,
  projectId: number,
): DecisionRadarDTO {
  const dto = record(value, "$");
  const responseProjectId = integerValue(requireField(dto, "project_id", "$"), "$.project_id");
  if (responseProjectId !== projectId) {
    fail("$.project_id", `the requested project id ${projectId}`, responseProjectId);
  }
  booleanValue(requireField(dto, "generated_light", "$"), "$.generated_light");
  stringValue(requireField(dto, "summary_line", "$"), "$.summary_line");
  const radar = arrayOf(requireField(dto, "radar", "$"), "$.radar", decisionCard);
  if (radar.length > 10) fail("$.radar", "an array with at most 10 items", radar);
  const graphAvailable = booleanValue(
    requireField(dto, "knowledge_graph_available", "$"),
    "$.knowledge_graph_available",
  );
  const graphCards = arrayOf(
    requireField(dto, "knowledge_graph_cards", "$"),
    "$.knowledge_graph_cards",
    decisionCard,
  );
  if (graphCards.length > 8) {
    fail("$.knowledge_graph_cards", "an array with at most 8 items", graphCards);
  }
  if (!graphAvailable && graphCards.length > 0) {
    fail("$.knowledge_graph_cards", "empty when the Knowledge Graph is unavailable", graphCards);
  }
  graphCards.forEach((card, index) => {
    if (card.created_from !== "knowledge_graph") {
      fail(`$.knowledge_graph_cards[${index}].created_from`, "knowledge_graph", card.created_from);
    }
  });
  const continuityAvailable = booleanValue(
    requireField(dto, "continuity_available", "$"),
    "$.continuity_available",
  );
  const continuityCards = arrayOf(
    requireField(dto, "continuity_cards", "$"),
    "$.continuity_cards",
    decisionCard,
  );
  if (continuityCards.length > 8) {
    fail("$.continuity_cards", "an array with at most 8 items", continuityCards);
  }
  if (!continuityAvailable && continuityCards.length > 0) {
    fail("$.continuity_cards", "empty when Semantic Continuity is unavailable", continuityCards);
  }
  continuityCards.forEach((card, index) => {
    if (card.created_from !== "semantic_continuity") {
      fail(
        `$.continuity_cards[${index}].created_from`,
        "semantic_continuity",
        card.created_from,
      );
    }
  });
  return value as DecisionRadarDTO;
}

function projectActionResult(value: unknown, path: string): ProjectActionResultDTO {
  const dto = record(value, path);
  booleanValue(requireField(dto, "ok", path), fieldPath(path, "ok"));
  integerValue(requireField(dto, "project_id", path), fieldPath(path, "project_id"));
  return value as ProjectActionResultDTO;
}

function projectSearchKind(value: unknown, path: string): ProjectSearchKind {
  return value === "scene" || value === "note" || value === "psyke" || value === "comment"
    ? value
    : fail(path, '"scene", "note", "psyke", or "comment"', value);
}

function projectSearchMatch(value: unknown, path: string): ProjectSearchMatchDTO {
  const dto = record(value, path);
  projectSearchKind(requireField(dto, "kind", path), fieldPath(path, "kind"));
  integerValue(requireField(dto, "id", path), fieldPath(path, "id"));
  stringValue(requireField(dto, "title", path), fieldPath(path, "title"));
  stringValue(requireField(dto, "excerpt", path), fieldPath(path, "excerpt"));
  optional(dto.revision, fieldPath(path, "revision"), (item, itemPath) =>
    nullable(item, itemPath, stringValue));
  optional(dto.resolved, fieldPath(path, "resolved"), (item, itemPath) =>
    nullable(item, itemPath, booleanValue));
  return value as ProjectSearchMatchDTO;
}

function projectSearchResponse(value: unknown, path: string): ProjectSearchResponseDTO {
  const dto = record(value, path);
  stringValue(requireField(dto, "query", path), fieldPath(path, "query"));
  arrayOf(requireField(dto, "matches", path), fieldPath(path, "matches"), projectSearchMatch);
  integerValue(requireField(dto, "limit", path), fieldPath(path, "limit"));
  return value as ProjectSearchResponseDTO;
}

function deleteResult(value: unknown, path: string): DeleteResultDTO {
  const dto = record(value, path);
  booleanValue(requireField(dto, "ok", path), fieldPath(path, "ok"));
  stringOrIntegerValue(requireField(dto, "deleted", path), fieldPath(path, "deleted"));
  return value as DeleteResultDTO;
}

function inlineCommentField(value: unknown, path: string): "content" | "title" {
  return value === "content" || value === "title"
    ? value
    : fail(path, '"content" or "title"', value);
}

function inlineCommentAnchor(value: unknown, path: string): void {
  const dto = record(value, path);
  integerValue(requireField(dto, "start_scene_id", path), fieldPath(path, "start_scene_id"));
  inlineCommentField(requireField(dto, "start_field", path), fieldPath(path, "start_field"));
  integerValue(requireField(dto, "from_offset", path), fieldPath(path, "from_offset"));
  integerValue(requireField(dto, "end_scene_id", path), fieldPath(path, "end_scene_id"));
  inlineCommentField(requireField(dto, "end_field", path), fieldPath(path, "end_field"));
  integerValue(requireField(dto, "to_offset", path), fieldPath(path, "to_offset"));
  stringValue(requireField(dto, "prefix", path), fieldPath(path, "prefix"));
  stringValue(requireField(dto, "suffix", path), fieldPath(path, "suffix"));
}

function commentReply(value: unknown, path: string): void {
  const dto = record(value, path);
  integerValue(requireField(dto, "id", path), fieldPath(path, "id"));
  stringValue(requireField(dto, "source_id", path), fieldPath(path, "source_id"));
  stringValue(requireField(dto, "body", path), fieldPath(path, "body"));
  stringValue(requireField(dto, "author", path), fieldPath(path, "author"));
  integerValue(requireField(dto, "sort_order", path), fieldPath(path, "sort_order"));
  stringValue(requireField(dto, "created_at", path), fieldPath(path, "created_at"));
}

function inlineComment(value: unknown, path: string): InlineCommentDTO {
  const dto = record(value, path);
  integerValue(requireField(dto, "id", path), fieldPath(path, "id"));
  stringValue(requireField(dto, "source_id", path), fieldPath(path, "source_id"));
  inlineCommentAnchor(requireField(dto, "anchor", path), fieldPath(path, "anchor"));
  stringValue(requireField(dto, "quote", path), fieldPath(path, "quote"));
  stringValue(requireField(dto, "body", path), fieldPath(path, "body"));
  booleanValue(requireField(dto, "resolved", path), fieldPath(path, "resolved"));
  arrayOf(requireField(dto, "replies", path), fieldPath(path, "replies"), (reply, replyPath) => {
    commentReply(reply, replyPath);
    return reply;
  });
  stringValue(requireField(dto, "created_at", path), fieldPath(path, "created_at"));
  stringValue(requireField(dto, "updated_at", path), fieldPath(path, "updated_at"));
  stringValue(requireField(dto, "revision", path), fieldPath(path, "revision"));
  return value as InlineCommentDTO;
}

function whiteboardImportResult(value: unknown, path: string): WhiteboardImportResultDTO {
  const dto = record(value, path);
  integerValue(requireField(dto, "project_id", path), fieldPath(path, "project_id"));
  stringValue(requireField(dto, "title", path), fieldPath(path, "title"));
  stringValue(requireField(dto, "mode", path), fieldPath(path, "mode"));
  integerValue(requireField(dto, "scenes_created", path), fieldPath(path, "scenes_created"));
  stringArray(requireField(dto, "scene_titles", path), fieldPath(path, "scene_titles"));
  integerArray(requireField(dto, "scene_ids_by_block", path), fieldPath(path, "scene_ids_by_block"));
  for (const key of [
    "comments_created",
    "comments_skipped",
    "comment_replies_created",
    "comment_replies_skipped",
  ]) {
    integerValue(requireField(dto, key, path), fieldPath(path, key));
  }
  return value as WhiteboardImportResultDTO;
}

function scene(value: unknown, path: string): SceneDTO {
  const dto = record(value, path);
  integerValue(requireField(dto, "id", path), fieldPath(path, "id"));
  for (const key of [
    "title", "summary", "synopsis", "goal", "conflict", "outcome", "beat", "act",
    "chapter", "plotline", "color_label", "content", "who_knows_what",
  ]) {
    stringValue(requireField(dto, key, path), fieldPath(path, key));
  }
  stringArray(requireField(dto, "tags", path), fieldPath(path, "tags"));
  integerValue(requireField(dto, "sort_order", path), fieldPath(path, "sort_order"));
  integerValue(requireField(dto, "order_index", path), fieldPath(path, "order_index"));
  integerArray(requireField(dto, "character_ids", path), fieldPath(path, "character_ids"));
  integerArray(requireField(dto, "place_ids", path), fieldPath(path, "place_ids"));
  optional(dto.revision, fieldPath(path, "revision"), stringValue);
  return value as SceneDTO;
}

function manuscriptSnapshot(value: unknown, path: string): ManuscriptSnapshotDTO {
  const dto = record(value, path);
  integerValue(requireField(dto, "project_id", path), fieldPath(path, "project_id"));
  booleanValue(requireField(dto, "chapter_level", path), fieldPath(path, "chapter_level"));
  const sceneCountPath = fieldPath(path, "scene_count");
  const sceneCount = integerValue(requireField(dto, "scene_count", path), sceneCountPath);
  const orphanCountPath = fieldPath(path, "orphan_count");
  const orphanCount = integerValue(requireField(dto, "orphan_count", path), orphanCountPath);
  const scenesPath = fieldPath(path, "scenes");
  const scenes = requireField(dto, "scenes", path);
  if (!Array.isArray(scenes)) fail(scenesPath, "an array", scenes);
  if (sceneCount !== scenes.length) {
    fail(sceneCountPath, `equal to scenes.length (${scenes.length})`, sceneCount);
  }
  if (orphanCount < 0 || orphanCount > sceneCount) {
    fail(orphanCountPath, `between 0 and scene_count (${sceneCount})`, orphanCount);
  }
  const sceneIds = new Set<number>();
  scenes.forEach((item, index) => {
    const itemPath = `${scenesPath}[${index}]`;
    const validated = scene(item, itemPath);
    if (typeof validated.revision !== "string" || validated.revision.length === 0) {
      fail(fieldPath(itemPath, "revision"), "a non-empty string", validated.revision);
    }
    if (validated.order_index !== index + 1) {
      fail(fieldPath(itemPath, "order_index"), `canonical position ${index + 1}`, validated.order_index);
    }
    if (sceneIds.has(validated.id)) {
      fail(fieldPath(itemPath, "id"), "a unique scene id", validated.id);
    }
    sceneIds.add(validated.id);
  });
  return value as ManuscriptSnapshotDTO;
}

function storyStructureScene(value: unknown, path: string): StoryStructureSceneDTO {
  const dto = record(value, path);
  integerValue(requireField(dto, "id", path), fieldPath(path, "id"));
  nullable(requireField(dto, "episode_id", path), fieldPath(path, "episode_id"), integerValue);
  for (const key of ["title", "beat", "number"]) {
    stringValue(requireField(dto, key, path), fieldPath(path, key));
  }
  integerValue(requireField(dto, "order_index", path), fieldPath(path, "order_index"));
  booleanValue(requireField(dto, "is_orphan", path), fieldPath(path, "is_orphan"));
  return value as StoryStructureSceneDTO;
}

function storyStructureChapter(value: unknown, path: string): StoryStructureChapterDTO {
  const dto = record(value, path);
  for (const key of ["name", "number"]) {
    stringValue(requireField(dto, key, path), fieldPath(path, key));
  }
  booleanValue(requireField(dto, "unassigned", path), fieldPath(path, "unassigned"));
  integerValue(requireField(dto, "scene_count", path), fieldPath(path, "scene_count"));
  const scenesPath = fieldPath(path, "scenes");
  const scenes = requireField(dto, "scenes", path);
  if (!Array.isArray(scenes)) fail(scenesPath, "an array", scenes);
  scenes.forEach((item, index) => storyStructureScene(item, `${scenesPath}[${index}]`));
  return value as StoryStructureChapterDTO;
}

function storyStructureAct(value: unknown, path: string): StoryStructureActDTO {
  const dto = record(value, path);
  for (const key of ["name", "number"]) {
    stringValue(requireField(dto, key, path), fieldPath(path, key));
  }
  booleanValue(requireField(dto, "unassigned", path), fieldPath(path, "unassigned"));
  integerValue(requireField(dto, "scene_count", path), fieldPath(path, "scene_count"));
  const chaptersPath = fieldPath(path, "chapters");
  const chapters = requireField(dto, "chapters", path);
  if (!Array.isArray(chapters)) fail(chaptersPath, "an array", chapters);
  chapters.forEach((item, index) => storyStructureChapter(item, `${chaptersPath}[${index}]`));
  return value as StoryStructureActDTO;
}

function storyStructure(value: unknown, path: string): StoryStructureDTO {
  const dto = record(value, path);
  integerValue(requireField(dto, "project_id", path), fieldPath(path, "project_id"));
  const revision = stringValue(requireField(dto, "revision", path), fieldPath(path, "revision"));
  if (!/^[0-9a-f]{64}$/.test(revision)) {
    fail(fieldPath(path, "revision"), "a 64-character lowercase hexadecimal revision", revision);
  }
  booleanValue(requireField(dto, "chapter_level", path), fieldPath(path, "chapter_level"));
  integerValue(requireField(dto, "scene_count", path), fieldPath(path, "scene_count"));
  integerValue(requireField(dto, "orphan_count", path), fieldPath(path, "orphan_count"));
  const actsPath = fieldPath(path, "acts");
  const acts = requireField(dto, "acts", path);
  if (!Array.isArray(acts)) fail(actsPath, "an array", acts);
  acts.forEach((item, index) => storyStructureAct(item, `${actsPath}[${index}]`));
  return value as StoryStructureDTO;
}

function storyStructureCommandResult(value: unknown, path: string): StoryStructureCommandResultDTO {
  const dto = record(value, path);
  const structure = storyStructure(requireField(dto, "structure", path), fieldPath(path, "structure"));
  const changed = booleanValue(requireField(dto, "changed", path), fieldPath(path, "changed"));
  const createdSceneIdPath = fieldPath(path, "created_scene_id");
  const createdSceneId = nullable(
    requireField(dto, "created_scene_id", path),
    createdSceneIdPath,
    integerValue,
  );
  if (createdSceneId !== null && createdSceneId <= 0) {
    fail(createdSceneIdPath, "a positive safe integer or null", createdSceneId);
  }
  const affectedSceneIdsPath = fieldPath(path, "affected_scene_ids");
  const affectedSceneIds = integerArray(
    requireField(dto, "affected_scene_ids", path),
    affectedSceneIdsPath,
  );
  const seen = new Set<number>();
  affectedSceneIds.forEach((sceneId, index) => {
    const sceneIdPath = `${affectedSceneIdsPath}[${index}]`;
    if (sceneId <= 0) fail(sceneIdPath, "a positive safe integer", sceneId);
    if (seen.has(sceneId)) fail(sceneIdPath, "a unique scene id", sceneId);
    seen.add(sceneId);
  });
  if (!changed) {
    if (createdSceneId !== null) {
      fail(createdSceneIdPath, "null when changed is false", createdSceneId);
    }
    if (affectedSceneIds.length !== 0) {
      fail(affectedSceneIdsPath, "an empty array when changed is false", affectedSceneIds);
    }
  } else if (affectedSceneIds.length === 0) {
    fail(affectedSceneIdsPath, "a non-empty array when changed is true", affectedSceneIds);
  }
  if (createdSceneId !== null) {
    if (!seen.has(createdSceneId)) {
      fail(createdSceneIdPath, "an id included in affected_scene_ids", createdSceneId);
    }
    const returnedSceneIds = new Set(structure.acts.flatMap((act) => (
      act.chapters.flatMap((chapter) => chapter.scenes.map((scene) => scene.id))
    )));
    if (!returnedSceneIds.has(createdSceneId)) {
      fail(createdSceneIdPath, "an id present in the returned structure", createdSceneId);
    }
  }
  return value as StoryStructureCommandResultDTO;
}

function timelineOrderMode(value: unknown, path: string): TimelineOrderMode {
  return value === "structural" || value === "custom"
    ? value
    : fail(path, '"structural" or "custom"', value);
}

function timelineLane(value: unknown, path: string): TimelineLaneDTO {
  const dto = record(value, path);
  integerValue(requireField(dto, "id", path), fieldPath(path, "id"));
  stringValue(requireField(dto, "name", path), fieldPath(path, "name"));
  stringValue(requireField(dto, "color_label", path), fieldPath(path, "color_label"));
  integerValue(requireField(dto, "order_index", path), fieldPath(path, "order_index"));
  booleanValue(requireField(dto, "collapsed", path), fieldPath(path, "collapsed"));
  integerValue(requireField(dto, "event_count", path), fieldPath(path, "event_count"));
  return value as TimelineLaneDTO;
}

const TIMELINE_LINK_TYPES = new Set([
  "custom",
  "causality",
  "setup_payoff",
  "echo",
  "conflict",
  "dependency",
]);

function timelineLink(value: unknown, path: string): TimelineLinkDTO {
  const dto = record(value, path);
  for (const key of ["id", "source_scene_id", "target_scene_id"] as const) {
    const id = integerValue(requireField(dto, key, path), fieldPath(path, key));
    if (id <= 0) fail(fieldPath(path, key), "a positive safe integer", id);
  }
  const linkType = stringValue(
    requireField(dto, "link_type", path),
    fieldPath(path, "link_type"),
  );
  if (!TIMELINE_LINK_TYPES.has(linkType)) {
    fail(fieldPath(path, "link_type"), "a supported Timeline link type", linkType);
  }
  stringValue(requireField(dto, "color_label", path), fieldPath(path, "color_label"));
  stringValue(requireField(dto, "label", path), fieldPath(path, "label"));
  isoTimestamp(requireField(dto, "created_at", path), fieldPath(path, "created_at"));
  return value as TimelineLinkDTO;
}

function timelineStructureLink(value: unknown, path: string): TimelineStructureLinkDTO {
  const dto = record(value, path);
  for (const key of ["id", "source_scene_id"] as const) {
    const id = integerValue(requireField(dto, key, path), fieldPath(path, key));
    if (id <= 0) fail(fieldPath(path, key), "a positive safe integer", id);
  }
  const targetType = stringValue(
    requireField(dto, "target_type", path),
    fieldPath(path, "target_type"),
  );
  if (targetType !== "act" && targetType !== "chapter") {
    fail(fieldPath(path, "target_type"), '"act" or "chapter"', targetType);
  }
  const targetRef = stringValue(
    requireField(dto, "target_ref", path),
    fieldPath(path, "target_ref"),
  );
  if (!targetRef.trim()) {
    fail(fieldPath(path, "target_ref"), "a non-empty structural reference", targetRef);
  }
  booleanValue(requireField(dto, "target_exists", path), fieldPath(path, "target_exists"));
  isoTimestamp(requireField(dto, "created_at", path), fieldPath(path, "created_at"));
  return value as TimelineStructureLinkDTO;
}

function timelineEvent(value: unknown, path: string): TimelineEventDTO {
  const dto = record(value, path);
  integerValue(requireField(dto, "id", path), fieldPath(path, "id"));
  integerValue(requireField(dto, "order_index", path), fieldPath(path, "order_index"));
  for (const key of [
    "title", "structural_number", "act", "chapter", "plotline", "color_label",
    "time_of_day", "location",
  ]) {
    stringValue(requireField(dto, key, path), fieldPath(path, key));
  }
  nullable(requireField(dto, "lane_id", path), fieldPath(path, "lane_id"), integerValue);
  integerValue(requireField(dto, "duration_minutes", path), fieldPath(path, "duration_minutes"));
  arrayOf(
    requireField(dto, "character_states", path),
    fieldPath(path, "character_states"),
    (item, itemPath) => {
      const state = record(item, itemPath);
      stringValue(requireField(state, "character", itemPath), fieldPath(itemPath, "character"));
      stringValue(requireField(state, "state", itemPath), fieldPath(itemPath, "state"));
      return item;
    },
  );
  return value as TimelineEventDTO;
}

function timelineOffTimelineScene(value: unknown, path: string): TimelineOffTimelineSceneDTO {
  const dto = record(value, path);
  integerValue(requireField(dto, "id", path), fieldPath(path, "id"));
  for (const key of ["title", "structural_number", "act", "chapter"]) {
    stringValue(requireField(dto, key, path), fieldPath(path, key));
  }
  return value as TimelineOffTimelineSceneDTO;
}

const TIMELINE_MAX_COLLECTION_LENGTH = 10_000;
const TIMELINE_MAX_NESTED_COLLECTION_LENGTH = 1_000;
const TIMELINE_MAX_TEXT_LENGTH = 4_096;

function timelineBoundedString(value: unknown, path: string, maxLength = TIMELINE_MAX_TEXT_LENGTH): string {
  const result = stringValue(value, path);
  if (Array.from(result).length > maxLength) {
    fail(path, `a string of at most ${maxLength} characters`, result);
  }
  return result;
}

function timelineBoundedArray<T>(
  value: unknown,
  path: string,
  validate: (item: unknown, itemPath: string) => T,
  maxLength = TIMELINE_MAX_COLLECTION_LENGTH,
): T[] {
  const result = arrayOf(value, path, validate);
  if (result.length > maxLength) {
    fail(path, `an array of at most ${maxLength} items`, result);
  }
  return result;
}

function timelinePositiveInteger(value: unknown, path: string): number {
  const result = integerValue(value, path);
  if (result <= 0) fail(path, "a positive safe integer", result);
  return result;
}

function timelineNonNegativeInteger(value: unknown, path: string): number {
  const result = integerValue(value, path);
  if (result < 0) fail(path, "a non-negative safe integer", result);
  return result;
}

function timelineBoundedNumber(value: unknown, path: string, minimum: number, maximum: number): number {
  const result = numberValue(value, path);
  if (result < minimum || result > maximum) {
    fail(path, `a finite number from ${minimum} through ${maximum}`, result);
  }
  return result;
}

function timelineEnum(
  value: unknown,
  path: string,
  allowed: ReadonlySet<string>,
  description: string,
): string {
  const result = timelineBoundedString(value, path, 64);
  if (!allowed.has(result)) fail(path, description, result);
  return result;
}

const TIMELINE_TENSION_SOURCES = new Set(["manual", "beat", "conflict", "content", "default"]);
const TIMELINE_SCENE_TYPES = new Set(["dialogue", "action", "exposition", "mixed"]);
const TIMELINE_PACING_WARNING_REASONS = new Set(["monotone_low", "monotone_high", "no_variation"]);
const TIMELINE_MODE_KINDS = new Set(["novel", "screenplay", "graphic_novel", "stage_script", "series"]);

function timelineStoryFlow(value: unknown, path: string, events: TimelineEventDTO[]): void {
  const dto = record(value, path);
  const pointsPath = fieldPath(path, "points");
  const points = arrayOf(
    requireField(dto, "points", path),
    pointsPath,
    (item, itemPath) => {
      const point = record(item, itemPath);
      timelinePositiveInteger(requireField(point, "scene_id", itemPath), fieldPath(itemPath, "scene_id"));
      timelinePositiveInteger(requireField(point, "order_index", itemPath), fieldPath(itemPath, "order_index"));
      const tension = integerValue(
        requireField(point, "tension_value", itemPath),
        fieldPath(itemPath, "tension_value"),
      );
      if (tension < 0 || tension > 10) {
        fail(fieldPath(itemPath, "tension_value"), "an integer from 0 through 10", tension);
      }
      timelineEnum(
        requireField(point, "tension_source", itemPath),
        fieldPath(itemPath, "tension_source"),
        TIMELINE_TENSION_SOURCES,
        "a supported Timeline tension source",
      );
      timelineEnum(
        requireField(point, "scene_type", itemPath),
        fieldPath(itemPath, "scene_type"),
        TIMELINE_SCENE_TYPES,
        "a supported Timeline scene type",
      );
      timelineBoundedNumber(
        requireField(point, "dialogue_ratio", itemPath),
        fieldPath(itemPath, "dialogue_ratio"),
        0,
        1,
      );
      timelineBoundedNumber(
        requireField(point, "action_ratio", itemPath),
        fieldPath(itemPath, "action_ratio"),
        0,
        1,
      );
      return point;
    },
  );
  if (points.length !== events.length) {
    fail(pointsPath, `exactly ${events.length} points aligned with events`, points);
  }
  points.forEach((point, index) => {
    const event = events[index];
    const pointPath = `${pointsPath}[${index}]`;
    if (!event || point.scene_id !== event.id) {
      fail(fieldPath(pointPath, "scene_id"), "the scene id at the same events position", point.scene_id);
    }
    if (point.order_index !== event.order_index) {
      fail(
        fieldPath(pointPath, "order_index"),
        "the order_index at the same events position",
        point.order_index,
      );
    }
  });

  const pointIds = points.map((point) => point.scene_id as number);
  const pointIndexById = new Map(pointIds.map((sceneId, index) => [sceneId, index]));
  const warningsPath = fieldPath(path, "warnings");
  const warnings = arrayOf(
    requireField(dto, "warnings", path),
    warningsPath,
    (item, itemPath) => {
      const warning = record(item, itemPath);
      const startSceneId = timelinePositiveInteger(
        requireField(warning, "start_scene_id", itemPath),
        fieldPath(itemPath, "start_scene_id"),
      );
      const endSceneId = timelinePositiveInteger(
        requireField(warning, "end_scene_id", itemPath),
        fieldPath(itemPath, "end_scene_id"),
      );
      const sceneIdsPath = fieldPath(itemPath, "scene_ids");
      const sceneIds = timelineBoundedArray(
        requireField(warning, "scene_ids", itemPath),
        sceneIdsPath,
        timelinePositiveInteger,
        Math.max(points.length, 1),
      );
      if (sceneIds.length === 0) fail(sceneIdsPath, "a non-empty contiguous point-id array", sceneIds);
      if (sceneIds[0] !== startSceneId) {
        fail(fieldPath(itemPath, "start_scene_id"), "the first scene_ids value", startSceneId);
      }
      if (sceneIds.at(-1) !== endSceneId) {
        fail(fieldPath(itemPath, "end_scene_id"), "the last scene_ids value", endSceneId);
      }
      const startIndex = pointIndexById.get(startSceneId);
      if (startIndex === undefined) {
        fail(fieldPath(itemPath, "start_scene_id"), "a story-flow point scene id", startSceneId);
      }
      const expectedIds = pointIds.slice(startIndex, startIndex + sceneIds.length);
      if (expectedIds.length !== sceneIds.length
          || expectedIds.some((sceneId, index) => sceneId !== sceneIds[index])) {
        fail(sceneIdsPath, "a contiguous subset of story-flow point ids in order", sceneIds);
      }
      timelineEnum(
        requireField(warning, "reason", itemPath),
        fieldPath(itemPath, "reason"),
        TIMELINE_PACING_WARNING_REASONS,
        "a supported Timeline pacing-warning reason",
      );
      return warning;
    },
  );
  if (warnings.length > events.length) {
    fail(warningsPath, `at most ${events.length} warnings for returned events`, warnings);
  }
}

const TIMELINE_GRAPHIC_NOVEL_DENSITIES = new Set([
  "silent", "light", "medium", "dense", "explosive", "unset",
]);
const TIMELINE_GRAPHIC_NOVEL_RHYTHMS = new Set(["held", "slow", "steady", "fast", "chaotic"]);
const TIMELINE_GRAPHIC_NOVEL_PACING = new Set([
  "quiet", "dense", "explosive", "exposition-heavy", "cinematic",
]);
const TIMELINE_STAGE_CUE_TYPES = new Set(["light", "sound", "music", "prop", "movement", "other"]);
const TIMELINE_STAGE_PRESSURES = new Set(["turn", "conflict", "pursuit", "flat"]);
const TIMELINE_SERIES_ARC_SCOPES = new Set([
  "series", "season", "episode", "character", "relationship", "mystery",
]);
const TIMELINE_SERIES_ARC_STATUSES = new Set(["active", "resolved", "abandoned", "delayed"]);

function timelineModeProjection(
  value: unknown,
  path: string,
  events: TimelineEventDTO[],
): string {
  const dto = record(value, path);
  const kind = timelineEnum(
    requireField(dto, "kind", path),
    fieldPath(path, "kind"),
    TIMELINE_MODE_KINDS,
    "novel, screenplay, graphic_novel, stage_script, or series",
  );
  const eventIds = events.map((event) => event.id);
  const eventIdSet = new Set(eventIds);

  if (kind === "novel") return kind;

  if (kind === "screenplay") {
    const scenesPath = fieldPath(path, "scenes");
    const scenes = arrayOf(
      requireField(dto, "scenes", path),
      scenesPath,
      (item, itemPath) => {
        const scene = record(item, itemPath);
        timelinePositiveInteger(requireField(scene, "scene_id", itemPath), fieldPath(itemPath, "scene_id"));
        for (const key of ["interior_exterior", "cinematic_pacing"] as const) {
          timelineBoundedString(requireField(scene, key, itemPath), fieldPath(itemPath, key), 256);
        }
        for (const key of [
          "dramatic_turn", "emotional_turn", "objective", "conflict", "turning_point",
          "emotional_shift",
        ] as const) {
          timelineBoundedString(requireField(scene, key, itemPath), fieldPath(itemPath, key));
        }
        timelineNonNegativeInteger(
          requireField(scene, "visual_beat_count", itemPath),
          fieldPath(itemPath, "visual_beat_count"),
        );
        return scene;
      },
    );
    if (scenes.length !== events.length) {
      fail(scenesPath, `exactly ${events.length} scene projections aligned with events`, scenes);
    }
    scenes.forEach((scene, index) => {
      if (scene.scene_id !== eventIds[index]) {
        fail(
          fieldPath(`${scenesPath}[${index}]`, "scene_id"),
          "the scene id at the same events position",
          scene.scene_id,
        );
      }
    });
    return kind;
  }

  if (kind === "graphic_novel") {
    const pagesPath = fieldPath(path, "pages");
    const pageIds = new Set<number>();
    const pageNumberById = new Map<number, number>();
    const pageIndexById = new Map<number, number>();
    timelineBoundedArray(
      requireField(dto, "pages", path),
      pagesPath,
      (item, itemPath) => {
        const page = record(item, itemPath);
        const pageId = timelinePositiveInteger(
          requireField(page, "page_id", itemPath),
          fieldPath(itemPath, "page_id"),
        );
        const pageNumber = timelineNonNegativeInteger(
          requireField(page, "page_number", itemPath),
          fieldPath(itemPath, "page_number"),
        );
        if (pageIds.has(pageId)) fail(fieldPath(itemPath, "page_id"), "a unique page id", pageId);
        for (const key of ["sequence_id", "issue_id"] as const) {
          const id = nullable(requireField(page, key, itemPath), fieldPath(itemPath, key), timelinePositiveInteger);
          if (id !== null && id <= 0) fail(fieldPath(itemPath, key), "a positive safe integer or null", id);
        }
        timelineBoundedString(requireField(page, "issue_title", itemPath), fieldPath(itemPath, "issue_title"), 256);
        timelineEnum(
          requireField(page, "density", itemPath),
          fieldPath(itemPath, "density"),
          TIMELINE_GRAPHIC_NOVEL_DENSITIES,
          "a supported graphic-novel density",
        );
        timelineEnum(
          requireField(page, "rhythm", itemPath),
          fieldPath(itemPath, "rhythm"),
          TIMELINE_GRAPHIC_NOVEL_RHYTHMS,
          "a supported graphic-novel rhythm",
        );
        timelineBoundedString(requireField(page, "reveal_timing", itemPath), fieldPath(itemPath, "reveal_timing"), 256);
        booleanValue(requireField(page, "splash_page", itemPath), fieldPath(itemPath, "splash_page"));
        timelineNonNegativeInteger(requireField(page, "panel_count", itemPath), fieldPath(itemPath, "panel_count"));
        timelineBoundedNumber(requireField(page, "action_density", itemPath), fieldPath(itemPath, "action_density"), 0, 1);
        timelineNonNegativeInteger(requireField(page, "text_load", itemPath), fieldPath(itemPath, "text_load"));
        timelineEnum(
          requireField(page, "pacing", itemPath),
          fieldPath(itemPath, "pacing"),
          TIMELINE_GRAPHIC_NOVEL_PACING,
          "a supported graphic-novel pacing value",
        );
        booleanValue(requireField(page, "is_silence", itemPath), fieldPath(itemPath, "is_silence"));
        booleanValue(requireField(page, "is_action", itemPath), fieldPath(itemPath, "is_action"));
        pageIds.add(pageId);
        pageNumberById.set(pageId, pageNumber);
        pageIndexById.set(pageId, pageIndexById.size);
        return page;
      },
    );
    const turnsPath = fieldPath(path, "page_turns");
    const turnIdentities = new Set<string>();
    timelineBoundedArray(
      requireField(dto, "page_turns", path),
      turnsPath,
      (item, itemPath) => {
        const turn = record(item, itemPath);
        const setupId = timelinePositiveInteger(
          requireField(turn, "setup_page_id", itemPath),
          fieldPath(itemPath, "setup_page_id"),
        );
        const setupNumber = timelineNonNegativeInteger(
          requireField(turn, "setup_page_number", itemPath),
          fieldPath(itemPath, "setup_page_number"),
        );
        const revealId = timelinePositiveInteger(
          requireField(turn, "reveal_page_id", itemPath),
          fieldPath(itemPath, "reveal_page_id"),
        );
        const revealNumber = timelineNonNegativeInteger(
          requireField(turn, "reveal_page_number", itemPath),
          fieldPath(itemPath, "reveal_page_number"),
        );
        if (pageNumberById.get(setupId) !== setupNumber) {
          fail(fieldPath(itemPath, "setup_page_id"), "a returned page matching setup_page_number", setupId);
        }
        if (pageNumberById.get(revealId) !== revealNumber) {
          fail(fieldPath(itemPath, "reveal_page_id"), "a returned page matching reveal_page_number", revealId);
        }
        if (setupId === revealId) {
          fail(fieldPath(itemPath, "reveal_page_id"), "a page different from setup_page_id", revealId);
        }
        const setupIndex = pageIndexById.get(setupId);
        if (setupIndex === undefined || pageIndexById.get(revealId) !== setupIndex + 1) {
          fail(
            fieldPath(itemPath, "reveal_page_id"),
            "the immediately following returned page after setup_page_id",
            revealId,
          );
        }
        const identity = `${setupId}:${revealId}`;
        if (turnIdentities.has(identity)) fail(itemPath, "a unique page-turn pair", turn);
        timelineBoundedString(requireField(turn, "reveal_type", itemPath), fieldPath(itemPath, "reveal_type"), 256);
        turnIdentities.add(identity);
        return turn;
      },
    );
    return kind;
  }

  if (kind === "stage_script") {
    const scenesPath = fieldPath(path, "scenes");
    const scenes = arrayOf(
      requireField(dto, "scenes", path),
      scenesPath,
      (item, itemPath) => {
        const scene = record(item, itemPath);
        timelinePositiveInteger(requireField(scene, "scene_id", itemPath), fieldPath(itemPath, "scene_id"));
        timelinePositiveInteger(requireField(scene, "order_index", itemPath), fieldPath(itemPath, "order_index"));
        timelineBoundedString(requireField(scene, "act", itemPath), fieldPath(itemPath, "act"), 256);
        timelineBoundedString(requireField(scene, "title", itemPath), fieldPath(itemPath, "title"), 256);
        timelineBoundedArray(
          requireField(scene, "entrances_exits", itemPath),
          fieldPath(itemPath, "entrances_exits"),
          (entryItem, entryPath) => {
            const entry = record(entryItem, entryPath);
            timelineBoundedString(requireField(entry, "character", entryPath), fieldPath(entryPath, "character"), 256);
            timelineEnum(
              requireField(entry, "type", entryPath),
              fieldPath(entryPath, "type"),
              new Set(["entrance", "exit"]),
              '"entrance" or "exit"',
            );
            timelineNonNegativeInteger(requireField(entry, "moment_order", entryPath), fieldPath(entryPath, "moment_order"));
            timelineBoundedString(requireField(entry, "cue_text", entryPath), fieldPath(entryPath, "cue_text"));
            return entry;
          },
          TIMELINE_MAX_NESTED_COLLECTION_LENGTH,
        );
        timelineBoundedArray(
          requireField(scene, "cues", itemPath),
          fieldPath(itemPath, "cues"),
          (cueItem, cuePath) => {
            const cue = record(cueItem, cuePath);
            timelineEnum(
              requireField(cue, "type", cuePath),
              fieldPath(cuePath, "type"),
              TIMELINE_STAGE_CUE_TYPES,
              "a supported stage cue type",
            );
            timelineBoundedString(requireField(cue, "text", cuePath), fieldPath(cuePath, "text"));
            timelineNonNegativeInteger(requireField(cue, "moment_order", cuePath), fieldPath(cuePath, "moment_order"));
            return cue;
          },
          TIMELINE_MAX_NESTED_COLLECTION_LENGTH,
        );
        timelineBoundedString(requireField(scene, "offstage_events", itemPath), fieldPath(itemPath, "offstage_events"));
        booleanValue(requireField(scene, "has_offstage_events", itemPath), fieldPath(itemPath, "has_offstage_events"));
        timelineBoundedArray(
          requireField(scene, "props", itemPath),
          fieldPath(itemPath, "props"),
          (prop, propPath) => timelineBoundedString(prop, propPath, 256),
          TIMELINE_MAX_NESTED_COLLECTION_LENGTH,
        );
        timelineEnum(
          requireField(scene, "emotional_pressure", itemPath),
          fieldPath(itemPath, "emotional_pressure"),
          TIMELINE_STAGE_PRESSURES,
          "a supported stage emotional-pressure value",
        );
        return scene;
      },
    );
    if (scenes.length !== events.length) {
      fail(scenesPath, `exactly ${events.length} scene projections aligned with events`, scenes);
    }
    scenes.forEach((scene, index) => {
      const event = events[index];
      const scenePath = `${scenesPath}[${index}]`;
      if (!event || scene.scene_id !== event.id) {
        fail(fieldPath(scenePath, "scene_id"), "the scene id at the same events position", scene.scene_id);
      }
      if (scene.order_index !== event.order_index) {
        fail(fieldPath(scenePath, "order_index"), "the events order_index at the same position", scene.order_index);
      }
    });
    return kind;
  }

  const episodesPath = fieldPath(path, "episodes");
  const episodeIds = new Set<number>();
  const episodeOrderById = new Map<number, number>();
  const assignedSceneIds = new Set<number>();
  const episodes = arrayOf(
    requireField(dto, "episodes", path),
    episodesPath,
    (item, itemPath) => {
      const episode = record(item, itemPath);
      const episodeId = timelinePositiveInteger(
        requireField(episode, "episode_id", itemPath),
        fieldPath(itemPath, "episode_id"),
      );
      if (episodeIds.has(episodeId)) {
        fail(fieldPath(itemPath, "episode_id"), "a unique episode id", episodeId);
      }
      const orderIndex = timelinePositiveInteger(
        requireField(episode, "order_index", itemPath),
        fieldPath(itemPath, "order_index"),
      );
      const expectedOrder = episodeIds.size + 1;
      if (orderIndex !== expectedOrder) {
        fail(fieldPath(itemPath, "order_index"), `dense episode position ${expectedOrder}`, orderIndex);
      }
      nullable(requireField(episode, "season_id", itemPath), fieldPath(itemPath, "season_id"), timelinePositiveInteger);
      timelineBoundedString(requireField(episode, "season", itemPath), fieldPath(itemPath, "season"), 256);
      timelineNonNegativeInteger(requireField(episode, "episode_number", itemPath), fieldPath(itemPath, "episode_number"));
      timelineBoundedString(requireField(episode, "title", itemPath), fieldPath(itemPath, "title"), 256);
      timelineBoundedString(requireField(episode, "cliffhanger", itemPath), fieldPath(itemPath, "cliffhanger"));
      const sceneIds = arrayOf(
        requireField(episode, "scene_ids", itemPath),
        fieldPath(itemPath, "scene_ids"),
        timelinePositiveInteger,
      );
      sceneIds.forEach((sceneId, index) => {
        const sceneIdPath = `${fieldPath(itemPath, "scene_ids")}[${index}]`;
        if (!eventIdSet.has(sceneId)) fail(sceneIdPath, "an active Timeline event scene id", sceneId);
        if (assignedSceneIds.has(sceneId)) fail(sceneIdPath, "a scene assigned only once", sceneId);
        assignedSceneIds.add(sceneId);
      });
      const activeArcIds = new Set<number>();
      timelineBoundedArray(
        requireField(episode, "active_arcs", itemPath),
        fieldPath(itemPath, "active_arcs"),
        (arcItem, arcPath) => {
          const arc = record(arcItem, arcPath);
          const arcId = timelinePositiveInteger(requireField(arc, "arc_id", arcPath), fieldPath(arcPath, "arc_id"));
          if (activeArcIds.has(arcId)) fail(fieldPath(arcPath, "arc_id"), "a unique active arc id", arcId);
          timelineBoundedString(requireField(arc, "title", arcPath), fieldPath(arcPath, "title"), 256);
          timelineEnum(requireField(arc, "scope", arcPath), fieldPath(arcPath, "scope"), TIMELINE_SERIES_ARC_SCOPES, "a supported series arc scope");
          timelineEnum(requireField(arc, "status", arcPath), fieldPath(arcPath, "status"), TIMELINE_SERIES_ARC_STATUSES, "a supported series arc status");
          activeArcIds.add(arcId);
          return arc;
        },
        TIMELINE_MAX_NESTED_COLLECTION_LENGTH,
      );
      for (const key of ["setup_arc_ids", "payoff_arc_ids"] as const) {
        const ids = timelineBoundedArray(
          requireField(episode, key, itemPath),
          fieldPath(itemPath, key),
          timelinePositiveInteger,
          TIMELINE_MAX_NESTED_COLLECTION_LENGTH,
        );
        const uniqueIds = new Set(ids);
        if (uniqueIds.size !== ids.length) fail(fieldPath(itemPath, key), "unique positive arc ids", ids);
      }
      episodeIds.add(episodeId);
      episodeOrderById.set(episodeId, orderIndex);
      return episode;
    },
  );
  const episodeLimit = Math.max(TIMELINE_MAX_COLLECTION_LENGTH, eventIds.length);
  if (episodes.length > episodeLimit) {
    fail(episodesPath, `an array of at most ${episodeLimit} event-aware items`, episodes);
  }
  const chainsPath = fieldPath(path, "arc_chains");
  const chainArcIds = new Set<number>();
  timelineBoundedArray(
    requireField(dto, "arc_chains", path),
    chainsPath,
    (item, itemPath) => {
      const chain = record(item, itemPath);
      const arcId = timelinePositiveInteger(requireField(chain, "arc_id", itemPath), fieldPath(itemPath, "arc_id"));
      if (chainArcIds.has(arcId)) fail(fieldPath(itemPath, "arc_id"), "a unique arc-chain id", arcId);
      timelineBoundedString(requireField(chain, "title", itemPath), fieldPath(itemPath, "title"), 256);
      timelineEnum(requireField(chain, "scope", itemPath), fieldPath(itemPath, "scope"), TIMELINE_SERIES_ARC_SCOPES, "a supported series arc scope");
      const setupId = timelinePositiveInteger(
        requireField(chain, "setup_episode_id", itemPath),
        fieldPath(itemPath, "setup_episode_id"),
      );
      const payoffId = timelinePositiveInteger(
        requireField(chain, "payoff_episode_id", itemPath),
        fieldPath(itemPath, "payoff_episode_id"),
      );
      if (!episodeIds.has(setupId)) {
        fail(fieldPath(itemPath, "setup_episode_id"), "an episode id returned by this projection", setupId);
      }
      if (!episodeIds.has(payoffId)) {
        fail(fieldPath(itemPath, "payoff_episode_id"), "an episode id returned by this projection", payoffId);
      }
      for (const [key, episodeId] of [
        ["setup_order_index", setupId],
        ["payoff_order_index", payoffId],
      ] as const) {
        const orderIndex = timelinePositiveInteger(
          requireField(chain, key, itemPath),
          fieldPath(itemPath, key),
        );
        if (orderIndex !== episodeOrderById.get(episodeId)) {
          fail(fieldPath(itemPath, key), "the referenced episode order_index", orderIndex);
        }
      }
      chainArcIds.add(arcId);
      return chain;
    },
  );
  const unassignedPath = fieldPath(path, "unassigned_scene_ids");
  const unassigned = arrayOf(
    requireField(dto, "unassigned_scene_ids", path),
    unassignedPath,
    timelinePositiveInteger,
  );
  unassigned.forEach((sceneId, index) => {
    const sceneIdPath = `${unassignedPath}[${index}]`;
    if (!eventIdSet.has(sceneId)) fail(sceneIdPath, "an active Timeline event scene id", sceneId);
    if (assignedSceneIds.has(sceneId)) fail(sceneIdPath, "a scene assigned only once", sceneId);
    assignedSceneIds.add(sceneId);
  });
  if (assignedSceneIds.size !== eventIds.length
      || eventIds.some((sceneId) => !assignedSceneIds.has(sceneId))) {
    fail(path, "a complete one-time partition of active Timeline event scene ids", value);
  }
  return kind;
}

function timelineSnapshot(value: unknown, path: string): TimelineSnapshotDTO {
  const dto = record(value, path);
  integerValue(requireField(dto, "project_id", path), fieldPath(path, "project_id"));
  const revision = stringValue(requireField(dto, "revision", path), fieldPath(path, "revision"));
  if (!/^[0-9a-f]{64}$/.test(revision)) {
    fail(fieldPath(path, "revision"), "a 64-character lowercase hexadecimal revision", revision);
  }
  timelineOrderMode(requireField(dto, "order_mode", path), fieldPath(path, "order_mode"));

  const lanesPath = fieldPath(path, "lanes");
  const lanes = arrayOf(requireField(dto, "lanes", path), lanesPath, timelineLane);
  const laneIds = new Set<number>();
  const laneIdByName = new Map<string, number>();
  lanes.forEach((lane, index) => {
    const lanePath = `${lanesPath}[${index}]`;
    if (lane.id <= 0) fail(fieldPath(lanePath, "id"), "a positive safe integer", lane.id);
    if (laneIds.has(lane.id)) fail(fieldPath(lanePath, "id"), "a unique lane id", lane.id);
    if (lane.order_index !== index) {
      fail(fieldPath(lanePath, "order_index"), `dense lane position ${index}`, lane.order_index);
    }
    if (lane.event_count < 0) {
      fail(fieldPath(lanePath, "event_count"), "zero or greater", lane.event_count);
    }
    laneIds.add(lane.id);
    if (!laneIdByName.has(lane.name)) laneIdByName.set(lane.name, lane.id);
  });

  const eventsPath = fieldPath(path, "events");
  const events = arrayOf(requireField(dto, "events", path), eventsPath, timelineEvent);
  const sceneIds = new Set<number>();
  const laneCounts = new Map<number, number>();
  events.forEach((event, index) => {
    const eventPath = `${eventsPath}[${index}]`;
    if (event.id <= 0) fail(fieldPath(eventPath, "id"), "a positive safe integer", event.id);
    if (sceneIds.has(event.id)) fail(fieldPath(eventPath, "id"), "a unique scene id", event.id);
    if (event.order_index !== index + 1) {
      fail(fieldPath(eventPath, "order_index"), `effective Timeline position ${index + 1}`, event.order_index);
    }
    const matchingLaneId = laneIdByName.get(event.plotline.trim());
    if (event.lane_id !== null) {
      if (!laneIds.has(event.lane_id)) {
        fail(fieldPath(eventPath, "lane_id"), "a lane id present in lanes or null", event.lane_id);
      }
      if (matchingLaneId !== event.lane_id) {
        fail(
          fieldPath(eventPath, "lane_id"),
          "the returned lane whose persisted name matches the trimmed plotline",
          event.lane_id,
        );
      }
      laneCounts.set(event.lane_id, (laneCounts.get(event.lane_id) ?? 0) + 1);
    } else if (matchingLaneId !== undefined) {
      fail(
        fieldPath(eventPath, "lane_id"),
        `matching lane id ${matchingLaneId} for the trimmed plotline`,
        event.lane_id,
      );
    }
    sceneIds.add(event.id);
  });
  lanes.forEach((lane, index) => {
    const actual = laneCounts.get(lane.id) ?? 0;
    if (lane.event_count !== actual) {
      fail(
        fieldPath(`${lanesPath}[${index}]`, "event_count"),
        `the number of returned events in this lane (${actual})`,
        lane.event_count,
      );
    }
  });

  const offTimelinePath = fieldPath(path, "off_timeline");
  const offTimeline = arrayOf(
    requireField(dto, "off_timeline", path),
    offTimelinePath,
    timelineOffTimelineScene,
  );
  offTimeline.forEach((sceneRef, index) => {
    const idPath = fieldPath(`${offTimelinePath}[${index}]`, "id");
    if (sceneRef.id <= 0) fail(idPath, "a positive safe integer", sceneRef.id);
    if (sceneIds.has(sceneRef.id)) {
      fail(idPath, "a scene id not already present in events or off_timeline", sceneRef.id);
    }
    sceneIds.add(sceneRef.id);
  });

  const linksPath = fieldPath(path, "links");
  const links = arrayOf(requireField(dto, "links", path), linksPath, timelineLink);
  const linkIds = new Set<number>();
  const linkIdentities = new Set<string>();
  links.forEach((link, index) => {
    const linkPath = `${linksPath}[${index}]`;
    if (linkIds.has(link.id)) {
      fail(fieldPath(linkPath, "id"), "a unique Timeline link id", link.id);
    }
    if (!sceneIds.has(link.source_scene_id)) {
      fail(
        fieldPath(linkPath, "source_scene_id"),
        "a scene id present in the returned Timeline",
        link.source_scene_id,
      );
    }
    if (!sceneIds.has(link.target_scene_id)) {
      fail(
        fieldPath(linkPath, "target_scene_id"),
        "a scene id present in the returned Timeline",
        link.target_scene_id,
      );
    }
    if (link.source_scene_id === link.target_scene_id) {
      fail(
        fieldPath(linkPath, "target_scene_id"),
        "a different scene from source_scene_id",
        link.target_scene_id,
      );
    }
    const identity = [link.source_scene_id, link.target_scene_id]
      .sort((left, right) => left - right)
      .join(":");
    if (linkIdentities.has(identity)) {
      fail(linkPath, "a unique unordered scene pair", link);
    }
    linkIds.add(link.id);
    linkIdentities.add(identity);
  });

  const actRefs = new Set<string>();
  const chapterRefs = new Set<string>();
  for (const scene of [...events, ...offTimeline]) {
    if (scene.act.trim()) actRefs.add(scene.act.trim());
    if (scene.chapter.trim()) chapterRefs.add(scene.chapter.trim());
  }
  const structureLinksPath = fieldPath(path, "structure_links");
  const structureLinks = arrayOf(
    requireField(dto, "structure_links", path),
    structureLinksPath,
    timelineStructureLink,
  );
  const structureLinkIds = new Set<number>();
  const structureLinkIdentities = new Set<string>();
  structureLinks.forEach((link, index) => {
    const linkPath = `${structureLinksPath}[${index}]`;
    if (structureLinkIds.has(link.id)) {
      fail(fieldPath(linkPath, "id"), "a unique Timeline structure-link id", link.id);
    }
    if (!sceneIds.has(link.source_scene_id)) {
      fail(
        fieldPath(linkPath, "source_scene_id"),
        "a scene id present in the returned Timeline",
        link.source_scene_id,
      );
    }
    const targetRef = link.target_ref.trim();
    const targetExists = link.target_type === "act"
      ? actRefs.has(targetRef)
      : chapterRefs.has(targetRef);
    if (link.target_exists !== targetExists) {
      fail(
        fieldPath(linkPath, "target_exists"),
        `the existence of ${link.target_type} ${JSON.stringify(targetRef)}`,
        link.target_exists,
      );
    }
    const identity = `${link.source_scene_id}\u0000${link.target_type}\u0000${targetRef}`;
    if (structureLinkIdentities.has(identity)) {
      fail(linkPath, "a unique scene and structural target", link);
    }
    structureLinkIds.add(link.id);
    structureLinkIdentities.add(identity);
  });
  timelineStoryFlow(
    requireField(dto, "story_flow", path),
    fieldPath(path, "story_flow"),
    events,
  );
  timelineModeProjection(
    requireField(dto, "mode_projection", path),
    fieldPath(path, "mode_projection"),
    events,
  );
  return value as TimelineSnapshotDTO;
}

function timelineCommandResult(value: unknown, path: string): TimelineCommandResultDTO {
  const dto = record(value, path);
  const timeline = timelineSnapshot(
    requireField(dto, "timeline", path),
    fieldPath(path, "timeline"),
  );
  const replayed = booleanValue(
    requireField(dto, "replayed", path),
    fieldPath(path, "replayed"),
  );
  const appliedRevision = stringValue(
    requireField(dto, "applied_revision", path),
    fieldPath(path, "applied_revision"),
  );
  if (!/^[0-9a-f]{64}$/.test(appliedRevision)) {
    fail(
      fieldPath(path, "applied_revision"),
      "a 64-character lowercase hexadecimal revision",
      appliedRevision,
    );
  }
  const changed = booleanValue(requireField(dto, "changed", path), fieldPath(path, "changed"));
  const idsPath = fieldPath(path, "affected_scene_ids");
  const ids = integerArray(requireField(dto, "affected_scene_ids", path), idsPath);
  const returnedSceneIds = new Set([
    ...timeline.events.map((event) => event.id),
    ...timeline.off_timeline.map((scene) => scene.id),
  ]);
  const seen = new Set<number>();
  ids.forEach((sceneId, index) => {
    const idPath = `${idsPath}[${index}]`;
    if (sceneId <= 0) fail(idPath, "a positive safe integer", sceneId);
    if (seen.has(sceneId)) fail(idPath, "a unique scene id", sceneId);
    if (!returnedSceneIds.has(sceneId)) {
      fail(idPath, "a scene id present in the returned Timeline", sceneId);
    }
    seen.add(sceneId);
  });
  if (!changed && ids.length !== 0) {
    fail(idsPath, "an empty array when changed is false", ids);
  }
  for (const [field, label] of [
    ["affected_link_ids", "Timeline link"],
    ["affected_structure_link_ids", "Timeline structure-link"],
  ] as const) {
    const affectedPath = fieldPath(path, field);
    const affectedIds = integerArray(requireField(dto, field, path), affectedPath);
    const affectedSeen = new Set<number>();
    affectedIds.forEach((id, index) => {
      const idPath = `${affectedPath}[${index}]`;
      if (id <= 0) fail(idPath, `a positive ${label} id`, id);
      if (affectedSeen.has(id)) fail(idPath, `a unique ${label} id`, id);
      affectedSeen.add(id);
    });
    if (!changed && affectedIds.length !== 0) {
      fail(affectedPath, "an empty array when changed is false", affectedIds);
    }
  }
  for (const field of ["created_link_id", "created_structure_link_id"] as const) {
    const id = nullable(requireField(dto, field, path), fieldPath(path, field), integerValue);
    if (id !== null && id <= 0) {
      fail(fieldPath(path, field), "a positive safe integer or null", id);
    }
    if (!changed && id !== null) fail(fieldPath(path, field), "null when changed is false", id);
  }
  const createdLinkId = dto.created_link_id as number | null;
  const createdStructureLinkId = dto.created_structure_link_id as number | null;
  if (createdLinkId !== null) {
    if (!(dto.affected_link_ids as number[]).includes(createdLinkId)) {
      fail(
        fieldPath(path, "created_link_id"),
        "an id included in affected_link_ids",
        createdLinkId,
      );
    }
    if (!timeline.links.some((link) => link.id === createdLinkId)) {
      fail(
        fieldPath(path, "created_link_id"),
        "an id present in timeline.links",
        createdLinkId,
      );
    }
  }
  if (createdStructureLinkId !== null) {
    if (!(dto.affected_structure_link_ids as number[]).includes(createdStructureLinkId)) {
      fail(
        fieldPath(path, "created_structure_link_id"),
        "an id included in affected_structure_link_ids",
        createdStructureLinkId,
      );
    }
    if (!timeline.structure_links.some((link) => link.id === createdStructureLinkId)) {
      fail(
        fieldPath(path, "created_structure_link_id"),
        "an id present in timeline.structure_links",
        createdStructureLinkId,
      );
    }
  }
  if (replayed && changed) {
    fail(fieldPath(path, "changed"), "false when replayed is true", changed);
  }
  return value as TimelineCommandResultDTO;
}

interface TimelineAffectedOutcome {
  changed: boolean;
  sceneIds: number[];
  linkIds: number[];
  structureLinkIds: number[];
  createdLinkId: number | null;
  createdStructureLinkId: number | null;
  fieldPrefix: "" | "original_";
}

function requireExactTimelineAffectedIds(
  actual: number[],
  expected: number[],
  path: string,
  commandKind: TimelineCommandDTO["kind"],
): void {
  if (
    actual.length !== expected.length
    || actual.some((id, index) => id !== expected[index])
  ) {
    fail(
      path,
      expected.length === 0
        ? `an empty array for ${commandKind}`
        : `exactly [${expected.join(", ")}] for ${commandKind}`,
      actual,
    );
  }
}

function validateTimelineAffectedFamilies(
  command: TimelineCommandDTO,
  outcome: TimelineAffectedOutcome,
): void {
  if (!outcome.changed) return;
  const scenePath = `$.${outcome.fieldPrefix}affected_scene_ids`;
  const linkPath = `$.${outcome.fieldPrefix}affected_link_ids`;
  const structurePath = `$.${outcome.fieldPrefix}affected_structure_link_ids`;
  const exact = (
    requireEmptySceneIds: boolean,
    linkIds: number[],
    structureLinkIds: number[],
  ) => {
    if (requireEmptySceneIds) {
      requireExactTimelineAffectedIds(outcome.sceneIds, [], scenePath, command.kind);
    }
    requireExactTimelineAffectedIds(outcome.linkIds, linkIds, linkPath, command.kind);
    requireExactTimelineAffectedIds(
      outcome.structureLinkIds,
      structureLinkIds,
      structurePath,
      command.kind,
    );
  };

  switch (command.kind) {
    case "create_link":
      exact(true, [outcome.createdLinkId!], []);
      break;
    case "update_link":
    case "delete_link":
      exact(true, [command.link_id], []);
      break;
    case "create_structure_link":
      exact(true, [], [outcome.createdStructureLinkId!]);
      break;
    case "update_structure_link":
    case "delete_structure_link":
      exact(true, [], [command.structure_link_id]);
      break;
    default:
      // Legacy lane/event/order commands may report scene effects, but never
      // relationship effects.
      exact(false, [], []);
  }
}

export function validateTimelineCommandResultDTOForRequest(
  value: unknown,
  projectId: number,
  command: TimelineCommandDTO,
): TimelineCommandResultDTO {
  const result = timelineCommandResult(value, "$");
  if (result.timeline.project_id !== projectId) {
    fail(
      "$.timeline.project_id",
      `the requested project id ${projectId}`,
      result.timeline.project_id,
    );
  }
  if (!result.replayed && result.applied_revision !== result.timeline.revision) {
    fail(
      "$.applied_revision",
      "the returned Timeline revision for a fresh command",
      result.applied_revision,
    );
  }
  if (
    !result.replayed
    && !result.changed
    && result.timeline.revision !== command.expected_revision
  ) {
    fail(
      "$.timeline.revision",
      "the command's expected revision when changed is false",
      result.timeline.revision,
    );
  }
  if (
    !result.replayed
    && result.changed
    && result.timeline.revision === command.expected_revision
  ) {
    fail(
      "$.timeline.revision",
      "a new revision when changed is true",
      result.timeline.revision,
    );
  }
  const expectedCreatedField = command.kind === "create_link"
    ? "created_link_id"
    : command.kind === "create_structure_link"
      ? "created_structure_link_id"
      : null;
  for (const field of ["created_link_id", "created_structure_link_id"] as const) {
    const id = result[field];
    if (field === expectedCreatedField && !result.replayed && result.changed && id === null) {
      fail(`$.${field}`, `a created id for ${command.kind}`, id);
    }
    if (field !== expectedCreatedField && id !== null) {
      fail(`$.${field}`, `null for ${command.kind}`, id);
    }
  }
  validateTimelineAffectedFamilies(command, {
    changed: result.changed,
    sceneIds: result.affected_scene_ids,
    linkIds: result.affected_link_ids,
    structureLinkIds: result.affected_structure_link_ids,
    createdLinkId: result.created_link_id,
    createdStructureLinkId: result.created_structure_link_id,
    fieldPrefix: "",
  });
  return result;
}

export function validateTimelineCommandReceiptDTOForRequest(
  value: unknown,
  projectId: number,
  command: TimelineCommandDTO,
  expectedRequestDigest: string,
): TimelineCommandReceiptDTO {
  const dto = record(value, "$");
  const returnedProjectId = integerValue(requireField(dto, "project_id", "$"), "$.project_id");
  const requestDigest = stringValue(requireField(dto, "request_digest", "$"), "$.request_digest");
  const commandKind = stringValue(requireField(dto, "command_kind", "$"), "$.command_kind");
  const expectedRevision = stringValue(
    requireField(dto, "expected_revision", "$"),
    "$.expected_revision",
  );
  const appliedRevision = stringValue(
    requireField(dto, "applied_revision", "$"),
    "$.applied_revision",
  );
  const originalChanged = booleanValue(
    requireField(dto, "original_changed", "$"),
    "$.original_changed",
  );
  if (returnedProjectId !== projectId) {
    fail("$.project_id", `the requested project id ${projectId}`, returnedProjectId);
  }
  if (!/^[0-9a-f]{64}$/.test(requestDigest)) {
    fail("$.request_digest", "a 64-character lowercase hexadecimal digest", requestDigest);
  }
  if (!/^[0-9a-f]{64}$/.test(expectedRequestDigest)) {
    fail(
      "$.request_digest",
      "validation against a canonical 64-character lowercase hexadecimal digest",
      expectedRequestDigest,
    );
  }
  if (requestDigest !== expectedRequestDigest) {
    fail(
      "$.request_digest",
      "the canonical digest for the submitted Timeline command",
      requestDigest,
    );
  }
  if (commandKind !== command.kind) {
    fail("$.command_kind", `the submitted command kind ${command.kind}`, commandKind);
  }
  if (expectedRevision !== command.expected_revision) {
    fail("$.expected_revision", "the submitted expected revision", expectedRevision);
  }
  if (!/^[0-9a-f]{64}$/.test(appliedRevision)) {
    fail("$.applied_revision", "a 64-character lowercase hexadecimal revision", appliedRevision);
  }

  for (const [field, label] of [
    ["original_affected_scene_ids", "scene"],
    ["original_affected_link_ids", "Timeline link"],
    ["original_affected_structure_link_ids", "Timeline structure-link"],
  ] as const) {
    const ids = integerArray(requireField(dto, field, "$"), `$.${field}`);
    const seen = new Set<number>();
    ids.forEach((id, index) => {
      if (id <= 0) fail(`$.${field}[${index}]`, `a positive ${label} id`, id);
      if (seen.has(id)) fail(`$.${field}[${index}]`, `a unique ${label} id`, id);
      seen.add(id);
    });
    if (!originalChanged && ids.length !== 0) {
      fail(`$.${field}`, "an empty array when original_changed is false", ids);
    }
  }

  for (const field of [
    "original_created_link_id",
    "original_created_structure_link_id",
  ] as const) {
    const id = nullable(requireField(dto, field, "$"), `$.${field}`, integerValue);
    if (id !== null && id <= 0) fail(`$.${field}`, "a positive safe integer or null", id);
    if (!originalChanged && id !== null) fail(`$.${field}`, "null when original_changed is false", id);
  }
  const originalCreatedLinkId = dto.original_created_link_id as number | null;
  const originalCreatedStructureLinkId = dto.original_created_structure_link_id as number | null;
  if (
    originalCreatedLinkId !== null
    && !(dto.original_affected_link_ids as number[]).includes(originalCreatedLinkId)
  ) {
    fail(
      "$.original_created_link_id",
      "an id included in original_affected_link_ids",
      originalCreatedLinkId,
    );
  }
  if (
    originalCreatedStructureLinkId !== null
    && !(dto.original_affected_structure_link_ids as number[]).includes(originalCreatedStructureLinkId)
  ) {
    fail(
      "$.original_created_structure_link_id",
      "an id included in original_affected_structure_link_ids",
      originalCreatedStructureLinkId,
    );
  }

  const expectedCreatedField = command.kind === "create_link"
    ? "original_created_link_id"
    : command.kind === "create_structure_link"
      ? "original_created_structure_link_id"
      : null;
  for (const field of [
    "original_created_link_id",
    "original_created_structure_link_id",
  ] as const) {
    const id = dto[field] as number | null;
    if (field === expectedCreatedField && originalChanged && id === null) {
      fail(`$.${field}`, `a created id for ${command.kind}`, id);
    }
    if (field !== expectedCreatedField && id !== null) {
      fail(`$.${field}`, `null for ${command.kind}`, id);
    }
  }
  validateTimelineAffectedFamilies(command, {
    changed: originalChanged,
    sceneIds: dto.original_affected_scene_ids as number[],
    linkIds: dto.original_affected_link_ids as number[],
    structureLinkIds: dto.original_affected_structure_link_ids as number[],
    createdLinkId: originalCreatedLinkId,
    createdStructureLinkId: originalCreatedStructureLinkId,
    fieldPrefix: "original_",
  });
  if (originalChanged && appliedRevision === expectedRevision) {
    fail("$.applied_revision", "a new committed revision", appliedRevision);
  }
  if (!originalChanged && appliedRevision !== expectedRevision) {
    fail("$.applied_revision", "the expected revision for a no-op command", appliedRevision);
  }
  isoTimestamp(requireField(dto, "committed_at", "$"), "$.committed_at");
  return value as TimelineCommandReceiptDTO;
}

export function validateTimelineSnapshotDTOForProject(
  value: unknown,
  projectId: number,
): TimelineSnapshotDTO {
  const snapshot = timelineSnapshot(value, "$");
  if (snapshot.project_id !== projectId) {
    fail("$.project_id", `the requested project id ${projectId}`, snapshot.project_id);
  }
  return snapshot;
}

const PROGRESSION_KINDS = [
  "story", "character", "relationship", "theme", "world", "custom",
] as const satisfies readonly ProgressionKind[];
const PROGRESSION_ANCHOR_KINDS = [
  "unanchored", "scene", "document_block",
] as const satisfies readonly ProgressionAnchorKind[];
const PROGRESSION_COVERAGE_STATUSES = [
  "empty", "unanchored", "partial", "complete",
] as const satisfies readonly ProgressionCoverageStatus[];
const PROGRESSION_COMMAND_KINDS = [
  "create_track", "update_track", "delete_track", "reorder_tracks",
  "create_beat", "update_beat", "delete_beat", "reorder_beats",
] as const satisfies readonly ProgressionCommandDTO["kind"][];

function enumString<T extends string>(
  value: unknown,
  path: string,
  choices: readonly T[],
): T {
  const candidate = stringValue(value, path);
  return choices.includes(candidate as T)
    ? candidate as T
    : fail(path, choices.map((choice) => JSON.stringify(choice)).join(", "), value);
}

function positiveInteger(value: unknown, path: string): number {
  const result = integerValue(value, path);
  return result > 0 ? result : fail(path, "a positive safe integer", value);
}

function nonNegativeInteger(value: unknown, path: string): number {
  const result = integerValue(value, path);
  return result >= 0 ? result : fail(path, "a non-negative safe integer", value);
}

function lowercaseRevision(value: unknown, path: string): string {
  const result = stringValue(value, path);
  return /^[0-9a-f]{64}$/.test(result)
    ? result
    : fail(path, "a 64-character lowercase hexadecimal revision", value);
}

function progressionBeat(value: unknown, path: string): ProgressionBeatDTO {
  const dto = record(value, path);
  positiveInteger(requireField(dto, "id", path), fieldPath(path, "id"));
  positiveInteger(requireField(dto, "track_id", path), fieldPath(path, "track_id"));
  stringValue(requireField(dto, "text", path), fieldPath(path, "text"));
  nonNegativeInteger(requireField(dto, "sort_order", path), fieldPath(path, "sort_order"));
  const anchorKind = enumString(
    requireField(dto, "anchor_kind", path),
    fieldPath(path, "anchor_kind"),
    PROGRESSION_ANCHOR_KINDS,
  );
  const sceneId = nullable(
    requireField(dto, "scene_id", path),
    fieldPath(path, "scene_id"),
    positiveInteger,
  );
  const sceneTitle = stringValue(
    requireField(dto, "scene_title", path),
    fieldPath(path, "scene_title"),
  );
  const anchorRef = nullable(
    requireField(dto, "anchor_ref", path),
    fieldPath(path, "anchor_ref"),
    stringValue,
  );
  stringValue(requireField(dto, "anchor_label", path), fieldPath(path, "anchor_label"));
  if (anchorKind === "scene" && sceneId === null) {
    fail(fieldPath(path, "scene_id"), "a positive scene id for a scene anchor", sceneId);
  }
  if (anchorKind !== "scene" && sceneId !== null) {
    fail(fieldPath(path, "scene_id"), `null for a ${anchorKind} anchor`, sceneId);
  }
  if (anchorKind === "document_block" && !anchorRef?.trim()) {
    fail(fieldPath(path, "anchor_ref"), "a non-empty reference for a document-block anchor", anchorRef);
  }
  if (anchorKind !== "document_block" && anchorRef !== null) {
    fail(fieldPath(path, "anchor_ref"), `null for a ${anchorKind} anchor`, anchorRef);
  }
  if (anchorKind !== "scene" && sceneTitle) {
    fail(fieldPath(path, "scene_title"), `blank for a ${anchorKind} anchor`, sceneTitle);
  }
  return value as ProgressionBeatDTO;
}

function progressionCoverage(value: unknown, path: string): ProgressionCoverageDTO {
  const dto = record(value, path);
  const total = nonNegativeInteger(requireField(dto, "total_beats", path), fieldPath(path, "total_beats"));
  const anchored = nonNegativeInteger(requireField(dto, "anchored_beats", path), fieldPath(path, "anchored_beats"));
  const unanchored = nonNegativeInteger(requireField(dto, "unanchored_beats", path), fieldPath(path, "unanchored_beats"));
  const scene = nonNegativeInteger(requireField(dto, "scene_anchored_beats", path), fieldPath(path, "scene_anchored_beats"));
  const document = nonNegativeInteger(requireField(dto, "document_anchored_beats", path), fieldPath(path, "document_anchored_beats"));
  const percent = numberValue(requireField(dto, "coverage_percent", path), fieldPath(path, "coverage_percent"));
  const status = enumString(
    requireField(dto, "status", path),
    fieldPath(path, "status"),
    PROGRESSION_COVERAGE_STATUSES,
  );
  const outOfOrderPath = fieldPath(path, "out_of_order_beat_ids");
  const outOfOrder = integerArray(requireField(dto, "out_of_order_beat_ids", path), outOfOrderPath);
  const seen = new Set<number>();
  outOfOrder.forEach((id, index) => {
    if (id <= 0) fail(`${outOfOrderPath}[${index}]`, "a positive beat id", id);
    if (seen.has(id)) fail(`${outOfOrderPath}[${index}]`, "a unique beat id", id);
    seen.add(id);
  });
  if (anchored + unanchored !== total || scene + document !== anchored) {
    fail(path, "internally consistent progression coverage counts", value);
  }
  if (percent < 0 || percent > 100) {
    fail(fieldPath(path, "coverage_percent"), "a percentage from 0 to 100", percent);
  }
  const expectedStatus: ProgressionCoverageStatus = total === 0
    ? "empty"
    : anchored === 0
      ? "unanchored"
      : anchored === total
        ? "complete"
        : "partial";
  if (status !== expectedStatus) {
    fail(fieldPath(path, "status"), expectedStatus, status);
  }
  return value as ProgressionCoverageDTO;
}

function progressionTrack(value: unknown, path: string): ProgressionTrackDTO {
  const dto = record(value, path);
  const id = positiveInteger(requireField(dto, "id", path), fieldPath(path, "id"));
  positiveInteger(requireField(dto, "project_id", path), fieldPath(path, "project_id"));
  const kind = enumString(requireField(dto, "kind", path), fieldPath(path, "kind"), PROGRESSION_KINDS);
  for (const key of [
    "title", "description", "color_label",
    "primary_psyke_entry_name", "primary_psyke_entry_type",
    "secondary_psyke_entry_name", "secondary_psyke_entry_type",
  ] as const) stringValue(requireField(dto, key, path), fieldPath(path, key));
  nonNegativeInteger(requireField(dto, "sort_order", path), fieldPath(path, "sort_order"));
  const legacyCompatibility = booleanValue(
    requireField(dto, "legacy_compatibility", path),
    fieldPath(path, "legacy_compatibility"),
  );
  const primaryId = nullable(requireField(dto, "primary_psyke_entry_id", path), fieldPath(path, "primary_psyke_entry_id"), positiveInteger);
  const secondaryId = nullable(requireField(dto, "secondary_psyke_entry_id", path), fieldPath(path, "secondary_psyke_entry_id"), positiveInteger);
  const primaryName = dto.primary_psyke_entry_name as string;
  const primaryType = dto.primary_psyke_entry_type as string;
  const secondaryName = dto.secondary_psyke_entry_name as string;
  const secondaryType = dto.secondary_psyke_entry_type as string;
  // Core permits intentionally blank PsykeEntry names and entry types. Stable
  // ids carry generic relationship/legacy identity; kind-specific rules below
  // still require character/theme/world subjects to have their exact types.
  if (primaryId === null && (!!primaryName || !!primaryType)) {
    fail(path, "a primary PSYKE id with optional label/type strings, or three blank values", value);
  }
  if (secondaryId === null && (!!secondaryName || !!secondaryType)) {
    fail(path, "a secondary PSYKE id with optional label/type strings, or three blank values", value);
  }
  const legacyCustomSubject = kind === "custom"
    && legacyCompatibility
    && primaryId !== null
    && secondaryId === null;
  const subjectsValid = kind === "story" || kind === "custom"
    ? primaryId === null && secondaryId === null || legacyCustomSubject
    : kind === "character"
      ? primaryId !== null && primaryType === "character" && secondaryId === null
      : kind === "theme"
        ? primaryId !== null && primaryType === "theme" && secondaryId === null
        : kind === "world"
          ? primaryId !== null && ["place", "object", "lore"].includes(primaryType) && secondaryId === null
          : primaryId !== null && secondaryId !== null && primaryId !== secondaryId;
  if (!subjectsValid) fail(path, `valid ${kind} progression subjects`, value);
  const beatsPath = fieldPath(path, "beats");
  const beats = arrayOf(requireField(dto, "beats", path), beatsPath, progressionBeat);
  const beatIds = new Set<number>();
  beats.forEach((beat, index) => {
    if (beat.track_id !== id) {
      fail(`${beatsPath}[${index}].track_id`, `the containing track id ${id}`, beat.track_id);
    }
    if (beatIds.has(beat.id)) fail(`${beatsPath}[${index}].id`, "a unique beat id", beat.id);
    beatIds.add(beat.id);
  });
  const coverage = progressionCoverage(
    requireField(dto, "coverage", path),
    fieldPath(path, "coverage"),
  );
  if (coverage.total_beats !== beats.length) {
    fail(`${fieldPath(path, "coverage")}.total_beats`, `the returned beat count ${beats.length}`, coverage.total_beats);
  }
  for (const [field, count] of [
    ["anchored_beats", beats.filter((beat) => beat.anchor_kind !== "unanchored").length],
    ["unanchored_beats", beats.filter((beat) => beat.anchor_kind === "unanchored").length],
    ["scene_anchored_beats", beats.filter((beat) => beat.anchor_kind === "scene").length],
    ["document_anchored_beats", beats.filter((beat) => beat.anchor_kind === "document_block").length],
  ] as const) {
    if (coverage[field] !== count) {
      fail(`${fieldPath(path, "coverage")}.${field}`, `the derived count ${count}`, coverage[field]);
    }
  }
  coverage.out_of_order_beat_ids.forEach((beatId, index) => {
    if (!beatIds.has(beatId)) {
      fail(`${fieldPath(path, "coverage")}.out_of_order_beat_ids[${index}]`, "an id in this track", beatId);
    }
  });
  return value as ProgressionTrackDTO;
}

function progressionSummary(value: unknown, path: string): ProgressionSummaryDTO {
  const dto = record(value, path);
  for (const key of ["total_tracks", "total_beats", "anchored_beats", "unanchored_beats"] as const) {
    nonNegativeInteger(requireField(dto, key, path), fieldPath(path, key));
  }
  const percent = numberValue(requireField(dto, "coverage_percent", path), fieldPath(path, "coverage_percent"));
  if (percent < 0 || percent > 100) fail(fieldPath(path, "coverage_percent"), "a percentage from 0 to 100", percent);
  const byKind = record(requireField(dto, "by_kind", path), fieldPath(path, "by_kind"));
  for (const kind of PROGRESSION_KINDS) {
    nonNegativeInteger(requireField(byKind, kind, fieldPath(path, "by_kind")), `${fieldPath(path, "by_kind")}.${kind}`);
  }
  const byStatus = record(requireField(dto, "by_status", path), fieldPath(path, "by_status"));
  for (const status of PROGRESSION_COVERAGE_STATUSES) {
    nonNegativeInteger(requireField(byStatus, status, fieldPath(path, "by_status")), `${fieldPath(path, "by_status")}.${status}`);
  }
  return value as ProgressionSummaryDTO;
}

function progressionSnapshot(value: unknown, path: string): ProgressionSnapshotDTO {
  const dto = record(value, path);
  const projectId = positiveInteger(requireField(dto, "project_id", path), fieldPath(path, "project_id"));
  lowercaseRevision(requireField(dto, "revision", path), fieldPath(path, "revision"));
  const tracksPath = fieldPath(path, "tracks");
  const tracks = arrayOf(requireField(dto, "tracks", path), tracksPath, progressionTrack);
  const trackIds = new Set<number>();
  const beatIds = new Set<number>();
  tracks.forEach((track, trackIndex) => {
    if (track.project_id !== projectId) {
      fail(`${tracksPath}[${trackIndex}].project_id`, `the snapshot project id ${projectId}`, track.project_id);
    }
    if (trackIds.has(track.id)) fail(`${tracksPath}[${trackIndex}].id`, "a unique track id", track.id);
    trackIds.add(track.id);
    track.beats.forEach((beat, beatIndex) => {
      if (beatIds.has(beat.id)) fail(`${tracksPath}[${trackIndex}].beats[${beatIndex}].id`, "a project-unique beat id", beat.id);
      beatIds.add(beat.id);
    });
  });
  const summary = progressionSummary(requireField(dto, "summary", path), fieldPath(path, "summary"));
  const totalBeats = tracks.reduce((sum, track) => sum + track.coverage.total_beats, 0);
  const anchored = tracks.reduce((sum, track) => sum + track.coverage.anchored_beats, 0);
  const unanchored = tracks.reduce((sum, track) => sum + track.coverage.unanchored_beats, 0);
  if (summary.total_tracks !== tracks.length) fail(`${fieldPath(path, "summary")}.total_tracks`, `the returned track count ${tracks.length}`, summary.total_tracks);
  if (summary.total_beats !== totalBeats) fail(`${fieldPath(path, "summary")}.total_beats`, `the returned beat count ${totalBeats}`, summary.total_beats);
  if (summary.anchored_beats !== anchored) fail(`${fieldPath(path, "summary")}.anchored_beats`, `the derived anchored count ${anchored}`, summary.anchored_beats);
  if (summary.unanchored_beats !== unanchored) fail(`${fieldPath(path, "summary")}.unanchored_beats`, `the derived unanchored count ${unanchored}`, summary.unanchored_beats);
  for (const kind of PROGRESSION_KINDS) {
    const expected = tracks.filter((track) => track.kind === kind).length;
    if (summary.by_kind[kind] !== expected) fail(`${fieldPath(path, "summary")}.by_kind.${kind}`, `the derived count ${expected}`, summary.by_kind[kind]);
  }
  for (const status of PROGRESSION_COVERAGE_STATUSES) {
    const expected = tracks.filter((track) => track.coverage.status === status).length;
    if (summary.by_status[status] !== expected) fail(`${fieldPath(path, "summary")}.by_status.${status}`, `the derived count ${expected}`, summary.by_status[status]);
  }
  return value as ProgressionSnapshotDTO;
}

function progressionAffectedIds(
  dto: JsonRecord,
  prefix: "" | "original_",
  changed: boolean,
  replayed = false,
): void {
  for (const family of ["track", "beat"] as const) {
    const field = `${prefix}affected_${family}_ids`;
    const ids = integerArray(requireField(dto, field, "$"), `$.${field}`);
    const seen = new Set<number>();
    ids.forEach((id, index) => {
      if (id <= 0) fail(`$.${field}[${index}]`, `a positive ${family} id`, id);
      if (seen.has(id)) fail(`$.${field}[${index}]`, `a unique ${family} id`, id);
      seen.add(id);
    });
    if (!changed && ids.length) fail(`$.${field}`, "empty when changed is false", ids);
    const createdField = `${prefix}created_${family}_id`;
    const created = nullable(requireField(dto, createdField, "$"), `$.${createdField}`, positiveInteger);
    if (!changed && created !== null && !replayed) {
      fail(`$.${createdField}`, "null when changed is false for a fresh command", created);
    }
    if (created !== null && !ids.includes(created) && !replayed) {
      fail(`$.${createdField}`, `an id in ${field}`, created);
    }
  }
}

export function validateProgressionCommandResultDTOForRequest(
  value: unknown,
  projectId: number,
  command: ProgressionCommandDTO,
): ProgressionCommandResultDTO {
  const dto = record(value, "$");
  const progressions = progressionSnapshot(requireField(dto, "progressions", "$"), "$.progressions");
  const changed = booleanValue(requireField(dto, "changed", "$"), "$.changed");
  const replayed = booleanValue(requireField(dto, "replayed", "$"), "$.replayed");
  const appliedRevision = lowercaseRevision(requireField(dto, "applied_revision", "$"), "$.applied_revision");
  progressionAffectedIds(dto, "", changed, replayed);
  if (progressions.project_id !== projectId) fail("$.progressions.project_id", `the requested project id ${projectId}`, progressions.project_id);
  if (replayed && changed) fail("$.changed", "false for a replay", changed);
  if (!replayed && appliedRevision !== progressions.revision) fail("$.applied_revision", "the returned Progressions revision", appliedRevision);
  if (!replayed && !changed && progressions.revision !== command.expected_revision) fail("$.progressions.revision", "the expected revision for a no-op", progressions.revision);
  if (!replayed && changed && progressions.revision === command.expected_revision) fail("$.progressions.revision", "a new revision for a changed command", progressions.revision);
  const expectedCreated = command.kind === "create_track"
    ? "created_track_id"
    : command.kind === "create_beat"
      ? "created_beat_id"
      : null;
  for (const field of ["created_track_id", "created_beat_id"] as const) {
    const id = dto[field] as number | null;
    if (!replayed && changed && field === expectedCreated && id === null) fail(`$.${field}`, `a created id for ${command.kind}`, id);
    if (field !== expectedCreated && id !== null) fail(`$.${field}`, `null for ${command.kind}`, id);
  }
  return value as ProgressionCommandResultDTO;
}

export function validateProgressionCommandReceiptDTOForRequest(
  value: unknown,
  projectId: number,
  command: ProgressionCommandDTO,
  expectedRequestDigest: string,
): ProgressionCommandReceiptDTO {
  const dto = record(value, "$");
  const returnedProjectId = positiveInteger(requireField(dto, "project_id", "$"), "$.project_id");
  const requestDigest = lowercaseRevision(requireField(dto, "request_digest", "$"), "$.request_digest");
  const commandKind = enumString(requireField(dto, "command_kind", "$"), "$.command_kind", PROGRESSION_COMMAND_KINDS);
  const expectedRevision = lowercaseRevision(requireField(dto, "expected_revision", "$"), "$.expected_revision");
  const appliedRevision = lowercaseRevision(requireField(dto, "applied_revision", "$"), "$.applied_revision");
  const changed = booleanValue(requireField(dto, "original_changed", "$"), "$.original_changed");
  progressionAffectedIds(dto, "original_", changed);
  isoTimestamp(requireField(dto, "committed_at", "$"), "$.committed_at");
  if (returnedProjectId !== projectId) fail("$.project_id", `the requested project id ${projectId}`, returnedProjectId);
  if (requestDigest !== expectedRequestDigest) fail("$.request_digest", "the canonical digest for the submitted Progressions command", requestDigest);
  if (commandKind !== command.kind) fail("$.command_kind", `the submitted command kind ${command.kind}`, commandKind);
  if (expectedRevision !== command.expected_revision) fail("$.expected_revision", "the submitted expected revision", expectedRevision);
  if (changed && appliedRevision === expectedRevision) fail("$.applied_revision", "a new committed revision", appliedRevision);
  if (!changed && appliedRevision !== expectedRevision) fail("$.applied_revision", "the expected revision for a no-op command", appliedRevision);
  const expectedCreated = command.kind === "create_track"
    ? "original_created_track_id"
    : command.kind === "create_beat"
      ? "original_created_beat_id"
      : null;
  for (const field of ["original_created_track_id", "original_created_beat_id"] as const) {
    const id = dto[field] as number | null;
    if (changed && field === expectedCreated && id === null) fail(`$.${field}`, `a created id for ${command.kind}`, id);
    if (field !== expectedCreated && id !== null) fail(`$.${field}`, `null for ${command.kind}`, id);
  }
  return value as ProgressionCommandReceiptDTO;
}

export function validateProgressionSnapshotDTOForProject(
  value: unknown,
  projectId: number,
): ProgressionSnapshotDTO {
  const snapshot = progressionSnapshot(value, "$");
  if (snapshot.project_id !== projectId) fail("$.project_id", `the requested project id ${projectId}`, snapshot.project_id);
  return snapshot;
}

function canvasPlotNode(value: unknown, path: string): CanvasPlotNodeDTO {
  const dto = record(value, path);
  const id = integerValue(requireField(dto, "id", path), fieldPath(path, "id"));
  if (id <= 0) fail(fieldPath(path, "id"), "a positive safe integer", id);
  for (const key of ["title", "body", "color_label", "group_label", "created_at"]) {
    stringValue(requireField(dto, key, path), fieldPath(path, key));
  }
  for (const key of ["x", "y", "width", "height"]) {
    const number = numberValue(requireField(dto, key, path), fieldPath(path, key));
    if ((key === "width" || key === "height") && number <= 0) {
      fail(fieldPath(path, key), "a positive finite number", number);
    }
  }
  const sceneId = nullable(
    requireField(dto, "scene_id", path),
    fieldPath(path, "scene_id"),
    integerValue,
  );
  if (sceneId != null && sceneId <= 0) {
    fail(fieldPath(path, "scene_id"), "a positive safe integer or null", sceneId);
  }
  const sortOrder = integerValue(
    requireField(dto, "sort_order", path),
    fieldPath(path, "sort_order"),
  );
  if (sortOrder < 0) fail(fieldPath(path, "sort_order"), "zero or greater", sortOrder);
  return value as CanvasPlotNodeDTO;
}

function canvasPlotLink(value: unknown, path: string): CanvasPlotLinkDTO {
  const dto = record(value, path);
  for (const key of ["id", "source_node_id", "target_node_id"]) {
    const id = integerValue(requireField(dto, key, path), fieldPath(path, key));
    if (id <= 0) fail(fieldPath(path, key), "a positive safe integer", id);
  }
  for (const key of ["label", "color_label", "link_type", "created_at"]) {
    stringValue(requireField(dto, key, path), fieldPath(path, key));
  }
  return value as CanvasPlotLinkDTO;
}

function canvasPlotFrame(value: unknown, path: string): CanvasPlotFrameDTO {
  const dto = record(value, path);
  const id = integerValue(requireField(dto, "id", path), fieldPath(path, "id"));
  if (id <= 0) fail(fieldPath(path, "id"), "a positive safe integer", id);
  for (const key of ["title", "color_label", "created_at"]) {
    stringValue(requireField(dto, key, path), fieldPath(path, key));
  }
  for (const key of ["x", "y", "width", "height"]) {
    const number = numberValue(requireField(dto, key, path), fieldPath(path, key));
    if ((key === "width" || key === "height") && number <= 0) {
      fail(fieldPath(path, key), "a positive finite number", number);
    }
  }
  return value as CanvasPlotFrameDTO;
}

function canvasPlotSnapshot(value: unknown, path: string): CanvasPlotSnapshotDTO {
  const dto = record(value, path);
  const projectId = integerValue(
    requireField(dto, "project_id", path),
    fieldPath(path, "project_id"),
  );
  if (projectId <= 0) fail(fieldPath(path, "project_id"), "a positive safe integer", projectId);
  const revision = stringValue(requireField(dto, "revision", path), fieldPath(path, "revision"));
  if (!/^[0-9a-f]{64}$/.test(revision)) {
    fail(fieldPath(path, "revision"), "a 64-character lowercase hexadecimal revision", revision);
  }

  const nodesPath = fieldPath(path, "nodes");
  const nodes = arrayOf(requireField(dto, "nodes", path), nodesPath, canvasPlotNode);
  const nodeIds = new Set<number>();
  nodes.forEach((node, index) => {
    if (nodeIds.has(node.id)) fail(`${nodesPath}[${index}].id`, "a unique node id", node.id);
    nodeIds.add(node.id);
  });

  const linksPath = fieldPath(path, "links");
  const links = arrayOf(requireField(dto, "links", path), linksPath, canvasPlotLink);
  const linkIds = new Set<number>();
  const pairs = new Set<string>();
  links.forEach((link, index) => {
    const linkPath = `${linksPath}[${index}]`;
    if (linkIds.has(link.id)) fail(`${linkPath}.id`, "a unique link id", link.id);
    if (!nodeIds.has(link.source_node_id)) {
      fail(`${linkPath}.source_node_id`, "an id present in nodes", link.source_node_id);
    }
    if (!nodeIds.has(link.target_node_id)) {
      fail(`${linkPath}.target_node_id`, "an id present in nodes", link.target_node_id);
    }
    if (link.source_node_id === link.target_node_id) {
      fail(`${linkPath}.target_node_id`, "a different node id", link.target_node_id);
    }
    const pair = [link.source_node_id, link.target_node_id].sort((a, b) => a - b).join(":");
    if (pairs.has(pair)) fail(linkPath, "a unique undirected node pair", link);
    pairs.add(pair);
    linkIds.add(link.id);
  });

  const framesPath = fieldPath(path, "frames");
  const frames = arrayOf(requireField(dto, "frames", path), framesPath, canvasPlotFrame);
  const frameIds = new Set<number>();
  frames.forEach((frame, index) => {
    if (frameIds.has(frame.id)) fail(`${framesPath}[${index}].id`, "a unique frame id", frame.id);
    frameIds.add(frame.id);
  });
  return value as CanvasPlotSnapshotDTO;
}

function canvasPlotCommandResult(value: unknown, path: string): CanvasPlotCommandResultDTO {
  const dto = record(value, path);
  const canvasPlot = canvasPlotSnapshot(
    requireField(dto, "canvas_plot", path),
    fieldPath(path, "canvas_plot"),
  );
  const replayed = booleanValue(
    requireField(dto, "replayed", path),
    fieldPath(path, "replayed"),
  );
  const appliedRevision = stringValue(
    requireField(dto, "applied_revision", path),
    fieldPath(path, "applied_revision"),
  );
  if (!/^[0-9a-f]{64}$/.test(appliedRevision)) {
    fail(
      fieldPath(path, "applied_revision"),
      "a 64-character lowercase hexadecimal revision",
      appliedRevision,
    );
  }
  const changed = booleanValue(requireField(dto, "changed", path), fieldPath(path, "changed"));
  if (replayed && changed) {
    fail(fieldPath(path, "changed"), "false when replayed is true", changed);
  }
  const affected = [
    ["affected_node_ids", "node"],
    ["affected_link_ids", "link"],
    ["affected_frame_ids", "frame"],
  ] as const;
  for (const [field, label] of affected) {
    const ids = integerArray(requireField(dto, field, path), fieldPath(path, field));
    const seen = new Set<number>();
    ids.forEach((id, index) => {
      if (id <= 0) fail(`${fieldPath(path, field)}[${index}]`, `a positive ${label} id`, id);
      if (seen.has(id)) fail(`${fieldPath(path, field)}[${index}]`, `a unique ${label} id`, id);
      seen.add(id);
    });
    if (!changed && ids.length) fail(fieldPath(path, field), "an empty array when changed is false", ids);
  }
  for (const field of ["created_node_id", "created_link_id", "created_frame_id"] as const) {
    const id = nullable(requireField(dto, field, path), fieldPath(path, field), integerValue);
    if (id != null && id <= 0) fail(fieldPath(path, field), "a positive safe integer or null", id);
    if (!changed && id != null) fail(fieldPath(path, field), "null when changed is false", id);
  }
  const createdNodeId = dto.created_node_id as number | null;
  const createdLinkId = dto.created_link_id as number | null;
  const createdFrameId = dto.created_frame_id as number | null;
  if (createdNodeId != null && !canvasPlot.nodes.some((node) => node.id === createdNodeId)) {
    fail(fieldPath(path, "created_node_id"), "an id present in canvas_plot.nodes", createdNodeId);
  }
  if (createdLinkId != null && !canvasPlot.links.some((link) => link.id === createdLinkId)) {
    fail(fieldPath(path, "created_link_id"), "an id present in canvas_plot.links", createdLinkId);
  }
  if (createdFrameId != null && !canvasPlot.frames.some((frame) => frame.id === createdFrameId)) {
    fail(fieldPath(path, "created_frame_id"), "an id present in canvas_plot.frames", createdFrameId);
  }
  return value as CanvasPlotCommandResultDTO;
}

export function validateCanvasPlotSnapshotDTOForProject(
  value: unknown,
  projectId: number,
): CanvasPlotSnapshotDTO {
  const snapshot = canvasPlotSnapshot(value, "$");
  if (snapshot.project_id !== projectId) {
    fail("$.project_id", `the requested project id ${projectId}`, snapshot.project_id);
  }
  return snapshot;
}

export function validateCanvasPlotCommandResultDTOForRequest(
  value: unknown,
  projectId: number,
  command: CanvasPlotCommandDTO,
): CanvasPlotCommandResultDTO {
  const result = canvasPlotCommandResult(value, "$");
  if (result.canvas_plot.project_id !== projectId) {
    fail(
      "$.canvas_plot.project_id",
      `the requested project id ${projectId}`,
      result.canvas_plot.project_id,
    );
  }
  if (!result.replayed && result.applied_revision !== result.canvas_plot.revision) {
    fail(
      "$.applied_revision",
      "the returned Canvas Plot revision for a fresh command",
      result.applied_revision,
    );
  }
  if (
    !result.replayed
    && !result.changed
    && result.canvas_plot.revision !== command.expected_revision
  ) {
    fail(
      "$.canvas_plot.revision",
      "the command's expected revision when changed is false",
      result.canvas_plot.revision,
    );
  }
  if (
    !result.replayed
    && result.changed
    && result.canvas_plot.revision === command.expected_revision
  ) {
    fail(
      "$.canvas_plot.revision",
      "a new revision when changed is true",
      result.canvas_plot.revision,
    );
  }
  const expectedCreatedField = command.kind === "create_node"
    ? "created_node_id"
    : command.kind === "create_link"
      ? "created_link_id"
      : command.kind === "create_frame"
        ? "created_frame_id"
        : null;
  for (const field of ["created_node_id", "created_link_id", "created_frame_id"] as const) {
    const id = result[field];
    if (field === expectedCreatedField && !result.replayed && result.changed && id == null) {
      fail(`$.${field}`, `a created id for ${command.kind}`, id);
    }
    if (field !== expectedCreatedField && id != null) {
      fail(`$.${field}`, `null for ${command.kind}`, id);
    }
  }
  return result;
}

function continuityIssue(value: unknown, path: string): ContinuityIssueDTO {
  const dto = record(value, path);
  const id = stringValue(requireField(dto, "id", path), fieldPath(path, "id"));
  if (!/^[0-9a-f]{16}$/.test(id)) {
    fail(fieldPath(path, "id"), "a 16-character lowercase hexadecimal issue key", id);
  }
  const reviewFingerprint = stringValue(
    requireField(dto, "review_fingerprint", path),
    fieldPath(path, "review_fingerprint"),
  );
  if (!/^[0-9a-f]{64}$/.test(reviewFingerprint)) {
    fail(fieldPath(path, "review_fingerprint"), "a 64-character lowercase hexadecimal fingerprint", reviewFingerprint);
  }
  for (const key of ["issue_type", "dimension", "title", "explanation", "suggested_action"] as const) {
    stringValue(requireField(dto, key, path), fieldPath(path, key));
  }
  const severity = stringValue(requireField(dto, "severity", path), fieldPath(path, "severity"));
  if (!["info", "suggestion", "warning", "blocking"].includes(severity)) {
    fail(fieldPath(path, "severity"), "a supported Continuity severity", severity);
  }
  const confidence = stringValue(requireField(dto, "confidence", path), fieldPath(path, "confidence"));
  if (!["confirmed", "likely", "possible", "unknown"].includes(confidence)) {
    fail(fieldPath(path, "confidence"), "a supported Continuity confidence", confidence);
  }
  const status = stringValue(requireField(dto, "status", path), fieldPath(path, "status"));
  if (!["open", "deferred", "dismissed", "resolved"].includes(status)) {
    fail(fieldPath(path, "status"), "a supported Continuity review status", status);
  }
  const sceneIds = integerArray(
    requireField(dto, "related_scene_ids", path),
    fieldPath(path, "related_scene_ids"),
  );
  sceneIds.forEach((sceneId, index) => {
    if (sceneId <= 0) fail(`${fieldPath(path, "related_scene_ids")}[${index}]`, "a positive Scene id", sceneId);
  });
  if (new Set(sceneIds).size !== sceneIds.length) {
    fail(fieldPath(path, "related_scene_ids"), "unique Scene ids", sceneIds);
  }
  return value as ContinuityIssueDTO;
}

function continuityReport(value: unknown, path: string): ContinuityReportDTO {
  const dto = record(value, path);
  const projectId = integerValue(requireField(dto, "project_id", path), fieldPath(path, "project_id"));
  if (projectId <= 0) fail(fieldPath(path, "project_id"), "a positive Project id", projectId);
  const revision = stringValue(
    requireField(dto, "review_revision", path),
    fieldPath(path, "review_revision"),
  );
  if (!/^[0-9a-f]{64}$/.test(revision)) {
    fail(fieldPath(path, "review_revision"), "a 64-character lowercase hexadecimal revision", revision);
  }
  stringValue(requireField(dto, "writing_mode", path), fieldPath(path, "writing_mode"));
  const issues = arrayOf(
    requireField(dto, "issues", path),
    fieldPath(path, "issues"),
    continuityIssue,
  );
  if (issues.length > 120) fail(fieldPath(path, "issues"), "at most 120 issues", issues);
  const keys = issues.map((issue) => issue.id);
  if (new Set(keys).size !== keys.length) fail(fieldPath(path, "issues"), "unique issue ids", issues);
  const blockingCount = integerValue(
    requireField(dto, "blocking_count", path),
    fieldPath(path, "blocking_count"),
  );
  const warningCount = integerValue(
    requireField(dto, "warning_count", path),
    fieldPath(path, "warning_count"),
  );
  const expectedBlocking = issues.filter((issue) => issue.status === "open" && issue.severity === "blocking").length;
  const expectedWarning = issues.filter((issue) => issue.status === "open" && issue.severity === "warning").length;
  if (blockingCount !== expectedBlocking) {
    fail(fieldPath(path, "blocking_count"), `the open blocking issue count (${expectedBlocking})`, blockingCount);
  }
  if (warningCount !== expectedWarning) {
    fail(fieldPath(path, "warning_count"), `the open warning issue count (${expectedWarning})`, warningCount);
  }
  stringArray(requireField(dto, "unavailable", path), fieldPath(path, "unavailable"));
  return value as ContinuityReportDTO;
}

export function validateContinuityReportDTOForRequest(
  value: unknown,
  projectId: number,
): ContinuityReportDTO {
  const report = continuityReport(value, "$");
  if (report.project_id !== projectId) {
    fail("$.project_id", `the requested project id ${projectId}`, report.project_id);
  }
  return report;
}

function continuityStatusForCommand(kind: ContinuityCommandDTO["kind"]): "deferred" | "dismissed" | "resolved" {
  if (kind === "defer_issue") return "deferred";
  if (kind === "dismiss_issue") return "dismissed";
  return "resolved";
}

export function validateContinuityCommandResultDTOForRequest(
  value: unknown,
  projectId: number,
  command: ContinuityCommandDTO,
): ContinuityCommandResultDTO {
  const dto = record(value, "$");
  const continuity = continuityReport(requireField(dto, "continuity", "$"), "$.continuity");
  const changed = booleanValue(requireField(dto, "changed", "$"), "$.changed");
  const replayed = booleanValue(requireField(dto, "replayed", "$"), "$.replayed");
  const affectedIssueId = stringValue(requireField(dto, "affected_issue_id", "$"), "$.affected_issue_id");
  const previousStatus = stringValue(requireField(dto, "previous_status", "$"), "$.previous_status");
  const status = stringValue(requireField(dto, "status", "$"), "$.status");
  const appliedRevision = stringValue(requireField(dto, "applied_revision", "$"), "$.applied_revision");
  if (continuity.project_id !== projectId) fail("$.continuity.project_id", `the requested project id ${projectId}`, continuity.project_id);
  if (affectedIssueId !== command.issue_id) fail("$.affected_issue_id", "the issue targeted by the submitted command", affectedIssueId);
  if (previousStatus !== "open") fail("$.previous_status", '"open"', previousStatus);
  const expectedStatus = continuityStatusForCommand(command.kind);
  if (status !== expectedStatus) fail("$.status", `the command result status ${expectedStatus}`, status);
  if (!/^[0-9a-f]{64}$/.test(appliedRevision)) fail("$.applied_revision", "a 64-character lowercase hexadecimal revision", appliedRevision);
  if (replayed && changed) fail("$.changed", "false for an idempotent replay", changed);
  if (!replayed && !changed) fail("$.changed", "true for a freshly accepted Continuity command", changed);
  if (!replayed && appliedRevision === command.expected_revision) fail("$.applied_revision", "a new revision for a fresh command", appliedRevision);
  if (!replayed && continuity.review_revision !== appliedRevision) {
    fail("$.continuity.review_revision", "the freshly applied revision", continuity.review_revision);
  }
  return value as ContinuityCommandResultDTO;
}

export function validateContinuityCommandReceiptDTOForRequest(
  value: unknown,
  projectId: number,
  command: ContinuityCommandDTO,
): ContinuityCommandReceiptDTO {
  const dto = record(value, "$");
  const returnedProjectId = integerValue(requireField(dto, "project_id", "$"), "$.project_id");
  const requestDigest = stringValue(requireField(dto, "request_digest", "$"), "$.request_digest");
  const commandKind = stringValue(requireField(dto, "command_kind", "$"), "$.command_kind");
  const expectedRevision = stringValue(requireField(dto, "expected_revision", "$"), "$.expected_revision");
  const appliedRevision = stringValue(requireField(dto, "applied_revision", "$"), "$.applied_revision");
  const originalChanged = booleanValue(requireField(dto, "original_changed", "$"), "$.original_changed");
  const affectedIssueId = stringValue(requireField(dto, "original_affected_issue_id", "$"), "$.original_affected_issue_id");
  const expectedIssueFingerprint = stringValue(
    requireField(dto, "expected_issue_fingerprint", "$"),
    "$.expected_issue_fingerprint",
  );
  const previousStatus = stringValue(requireField(dto, "previous_status", "$"), "$.previous_status");
  const status = stringValue(requireField(dto, "status", "$"), "$.status");
  const committedAt = stringValue(requireField(dto, "committed_at", "$"), "$.committed_at");
  if (returnedProjectId !== projectId) fail("$.project_id", `the requested project id ${projectId}`, returnedProjectId);
  if (!/^[0-9a-f]{64}$/.test(requestDigest)) fail("$.request_digest", "a 64-character lowercase hexadecimal digest", requestDigest);
  if (commandKind !== command.kind) fail("$.command_kind", `the submitted command kind ${command.kind}`, commandKind);
  if (expectedRevision !== command.expected_revision) fail("$.expected_revision", "the submitted expected revision", expectedRevision);
  if (!/^[0-9a-f]{64}$/.test(appliedRevision)) fail("$.applied_revision", "a 64-character lowercase hexadecimal revision", appliedRevision);
  if (!originalChanged) fail("$.original_changed", "true for a committed Continuity command", originalChanged);
  if (affectedIssueId !== command.issue_id) fail("$.original_affected_issue_id", "the issue targeted by the submitted command", affectedIssueId);
  if (expectedIssueFingerprint !== command.expected_issue_fingerprint) {
    fail("$.expected_issue_fingerprint", "the reviewed issue fingerprint submitted with the command", expectedIssueFingerprint);
  }
  if (!/^[0-9a-f]{64}$/.test(expectedIssueFingerprint)) {
    fail("$.expected_issue_fingerprint", "a 64-character lowercase hexadecimal fingerprint", expectedIssueFingerprint);
  }
  if (previousStatus !== "open") fail("$.previous_status", '"open"', previousStatus);
  const expectedStatus = continuityStatusForCommand(command.kind);
  if (status !== expectedStatus) fail("$.status", `the command result status ${expectedStatus}`, status);
  if (appliedRevision === expectedRevision) fail("$.applied_revision", "a new committed revision", appliedRevision);
  if (!committedAt.trim() || Number.isNaN(Date.parse(committedAt))) fail("$.committed_at", "a non-empty ISO timestamp", committedAt);
  return value as ContinuityCommandReceiptDTO;
}

const WORKFLOW_STEP_KINDS = new Set(["creative", "check", "manual"]);
const WORKFLOW_STEP_STATUSES = new Set(["pending", "active", "completed", "skipped", "blocked"]);
const WORKFLOW_RUN_STATUSES = new Set(["active", "paused", "completed", "cancelled", "blocked"]);

function isoTimestamp(value: unknown, path: string): string {
  const timestamp = stringValue(value, path);
  if (!timestamp.trim() || Number.isNaN(Date.parse(timestamp))) {
    fail(path, "a non-empty ISO timestamp", timestamp);
  }
  return timestamp;
}

function nullableIsoTimestamp(value: unknown, path: string): string | null {
  return nullable(value, path, isoTimestamp);
}

function workflowTemplateStep(value: unknown, path: string): WorkflowTemplateStepDTO {
  const dto = record(value, path);
  for (const key of ["id", "title", "description", "section_name", "action_id", "completion_check"] as const) {
    const item = stringValue(requireField(dto, key, path), fieldPath(path, key));
    if ((key === "id" || key === "title") && !item.trim()) {
      fail(fieldPath(path, key), "a non-empty string", item);
    }
  }
  const kind = stringValue(requireField(dto, "kind", path), fieldPath(path, "kind"));
  if (!WORKFLOW_STEP_KINDS.has(kind)) {
    fail(fieldPath(path, "kind"), "creative, check, or manual", kind);
  }
  stringArray(requireField(dto, "modes", path), fieldPath(path, "modes"));
  return value as WorkflowTemplateStepDTO;
}

function workflowTemplate(value: unknown, path: string): WorkflowTemplateDTO {
  const dto = record(value, path);
  for (const key of ["id", "title", "description", "category"] as const) {
    const item = stringValue(requireField(dto, key, path), fieldPath(path, key));
    if ((key === "id" || key === "title") && !item.trim()) {
      fail(fieldPath(path, key), "a non-empty string", item);
    }
  }
  stringArray(requireField(dto, "modes", path), fieldPath(path, "modes"));
  const steps = arrayOf(
    requireField(dto, "steps", path),
    fieldPath(path, "steps"),
    workflowTemplateStep,
  );
  const stepIds = steps.map((step) => step.id);
  if (new Set(stepIds).size !== stepIds.length) {
    fail(fieldPath(path, "steps"), "unique step ids", steps);
  }
  return value as WorkflowTemplateDTO;
}

function workflowRecommendation(value: unknown, path: string): WorkflowRecommendationDTO {
  const dto = record(value, path);
  for (const key of ["template_id", "title", "reason", "severity"] as const) {
    const item = stringValue(requireField(dto, key, path), fieldPath(path, key));
    if ((key === "template_id" || key === "title") && !item.trim()) {
      fail(fieldPath(path, key), "a non-empty string", item);
    }
  }
  return value as WorkflowRecommendationDTO;
}

function workflowStep(value: unknown, path: string): WorkflowStepDTO {
  const dto = record(value, path);
  for (const key of [
    "step_id", "title", "description", "section_name", "action_id",
    "completion_check", "notes", "target_type",
  ] as const) {
    const item = stringValue(requireField(dto, key, path), fieldPath(path, key));
    if ((key === "step_id" || key === "title") && !item.trim()) {
      fail(fieldPath(path, key), "a non-empty string", item);
    }
  }
  const kind = stringValue(requireField(dto, "kind", path), fieldPath(path, "kind"));
  if (!WORKFLOW_STEP_KINDS.has(kind)) {
    fail(fieldPath(path, "kind"), "creative, check, or manual", kind);
  }
  const status = stringValue(requireField(dto, "status", path), fieldPath(path, "status"));
  if (!WORKFLOW_STEP_STATUSES.has(status)) {
    fail(fieldPath(path, "status"), "a supported workflow step status", status);
  }
  const sortIndex = integerValue(requireField(dto, "sort_index", path), fieldPath(path, "sort_index"));
  if (sortIndex < 0) fail(fieldPath(path, "sort_index"), "zero or greater", sortIndex);
  const targetId = nullable(requireField(dto, "target_id", path), fieldPath(path, "target_id"), integerValue);
  if (targetId !== null && targetId <= 0) fail(fieldPath(path, "target_id"), "null or a positive id", targetId);
  nullableIsoTimestamp(requireField(dto, "created_at", path), fieldPath(path, "created_at"));
  nullableIsoTimestamp(requireField(dto, "updated_at", path), fieldPath(path, "updated_at"));
  return value as WorkflowStepDTO;
}

function workflowRun(value: unknown, path: string): WorkflowRunDTO {
  const dto = record(value, path);
  const id = integerValue(requireField(dto, "id", path), fieldPath(path, "id"));
  const projectId = integerValue(requireField(dto, "project_id", path), fieldPath(path, "project_id"));
  if (id <= 0) fail(fieldPath(path, "id"), "a positive Workflow run id", id);
  if (projectId <= 0) fail(fieldPath(path, "project_id"), "a positive Project id", projectId);
  for (const key of [
    "title", "description", "writing_mode", "template_id", "current_step_id", "source_type",
  ] as const) {
    stringValue(requireField(dto, key, path), fieldPath(path, key));
  }
  const status = stringValue(requireField(dto, "status", path), fieldPath(path, "status"));
  if (!WORKFLOW_RUN_STATUSES.has(status)) {
    fail(fieldPath(path, "status"), "a supported workflow run status", status);
  }
  const totalSteps = integerValue(requireField(dto, "total_steps", path), fieldPath(path, "total_steps"));
  const completedSteps = integerValue(requireField(dto, "completed_steps", path), fieldPath(path, "completed_steps"));
  const revision = stringValue(requireField(dto, "revision", path), fieldPath(path, "revision"));
  if (!/^[0-9a-f]{64}$/.test(revision)) {
    fail(fieldPath(path, "revision"), "a 64-character lowercase hexadecimal revision", revision);
  }
  const sourceId = nullable(requireField(dto, "source_id", path), fieldPath(path, "source_id"), integerValue);
  if (sourceId !== null && sourceId <= 0) fail(fieldPath(path, "source_id"), "null or a positive id", sourceId);
  nullableIsoTimestamp(requireField(dto, "created_at", path), fieldPath(path, "created_at"));
  nullableIsoTimestamp(requireField(dto, "updated_at", path), fieldPath(path, "updated_at"));
  nullableIsoTimestamp(requireField(dto, "completed_at", path), fieldPath(path, "completed_at"));
  const steps = arrayOf(requireField(dto, "steps", path), fieldPath(path, "steps"), workflowStep);
  if (totalSteps !== steps.length) {
    fail(fieldPath(path, "total_steps"), `the returned step count (${steps.length})`, totalSteps);
  }
  const countedCompleted = steps.filter((step) => step.status === "completed" || step.status === "skipped").length;
  if (completedSteps !== countedCompleted) {
    fail(fieldPath(path, "completed_steps"), `the completed/skipped step count (${countedCompleted})`, completedSteps);
  }
  const stepIds = steps.map((step) => step.step_id);
  if (new Set(stepIds).size !== stepIds.length) fail(fieldPath(path, "steps"), "unique step ids", steps);
  const currentStepId = stringValue(requireField(dto, "current_step_id", path), fieldPath(path, "current_step_id"));
  if (currentStepId && !steps.some((step) => step.step_id === currentStepId)) {
    fail(fieldPath(path, "current_step_id"), "an id present in steps", currentStepId);
  }
  const activeSteps = steps.filter((step) => step.status === "active");
  if (activeSteps.length > 1) {
    fail(fieldPath(path, "steps"), "at most one active workflow step", steps);
  }
  const expectedPointerStatus = status === "blocked"
    ? "blocked"
    : status === "active" || status === "paused"
      ? "active"
      : null;
  const pointerStatusSteps = expectedPointerStatus == null
    ? []
    : steps.filter((step) => step.status === expectedPointerStatus);
  if (pointerStatusSteps.length > 1) {
    fail(fieldPath(path, "steps"), `at most one ${expectedPointerStatus} workflow step`, steps);
  }
  if (currentStepId && expectedPointerStatus != null
      && !pointerStatusSteps.some((step) => step.step_id === currentStepId)) {
    fail(fieldPath(path, "current_step_id"), `the ${expectedPointerStatus} workflow step id`, currentStepId);
  }
  if ((status === "completed" || status === "cancelled") && currentStepId) {
    fail(fieldPath(path, "current_step_id"), `empty for a ${status} workflow`, currentStepId);
  }
  if (status === "completed" && completedSteps !== totalSteps) {
    fail(fieldPath(path, "completed_steps"), "all steps completed or skipped for a completed workflow", completedSteps);
  }
  return value as WorkflowRunDTO;
}

function workflowEvent(value: unknown, path: string): WorkflowEventDTO {
  const dto = record(value, path);
  for (const key of ["id", "project_id", "workflow_run_id"] as const) {
    const id = integerValue(requireField(dto, key, path), fieldPath(path, key));
    if (id <= 0) fail(fieldPath(path, key), "a positive id", id);
  }
  nullable(requireField(dto, "step_id", path), fieldPath(path, "step_id"), stringValue);
  stringValue(requireField(dto, "event_type", path), fieldPath(path, "event_type"));
  stringValue(requireField(dto, "message", path), fieldPath(path, "message"));
  record(requireField(dto, "metadata", path), fieldPath(path, "metadata"));
  isoTimestamp(requireField(dto, "created_at", path), fieldPath(path, "created_at"));
  return value as WorkflowEventDTO;
}

export const validateWorkflowTemplateListDTO: RuntimeDtoValidator<WorkflowTemplateDTO[]> = (value) =>
  arrayOf(value, "$", workflowTemplate);

export const validateWorkflowRecommendationListDTO: RuntimeDtoValidator<WorkflowRecommendationDTO[]> = (value) =>
  arrayOf(value, "$", workflowRecommendation);

export function validateWorkflowRunDTOForRequest(
  value: unknown,
  projectId: number,
  runId?: number,
): WorkflowRunDTO {
  const run = workflowRun(value, "$");
  if (run.project_id !== projectId) fail("$.project_id", `the requested project id ${projectId}`, run.project_id);
  if (runId != null && run.id !== runId) fail("$.id", `the requested workflow run id ${runId}`, run.id);
  return run;
}

export function validateWorkflowRunListDTOForRequest(
  value: unknown,
  projectId: number,
): WorkflowRunDTO[] {
  const runs = arrayOf(value, "$", workflowRun);
  const ids = new Set<number>();
  runs.forEach((run, index) => {
    if (run.project_id !== projectId) fail(`$[${index}].project_id`, `the requested project id ${projectId}`, run.project_id);
    if (ids.has(run.id)) fail(`$[${index}].id`, "a unique workflow run id", run.id);
    ids.add(run.id);
  });
  return runs;
}

export function validateWorkflowEventListDTOForRequest(
  value: unknown,
  projectId: number,
  runId: number,
  limit = 40,
): WorkflowEventDTO[] {
  const events = arrayOf(value, "$", workflowEvent);
  const cap = Math.max(1, Math.min(200, Math.floor(limit) || 40));
  if (events.length > cap) fail("$", `at most the requested ${cap} workflow events`, events);
  events.forEach((event, index) => {
    if (event.project_id !== projectId) fail(`$[${index}].project_id`, `the requested project id ${projectId}`, event.project_id);
    if (event.workflow_run_id !== runId) fail(`$[${index}].workflow_run_id`, `the requested workflow run id ${runId}`, event.workflow_run_id);
  });
  return events;
}

export function validateWorkflowCommandResultDTOForRequest(
  value: unknown,
  projectId: number,
  command: WorkflowCommandDTO,
): WorkflowCommandResultDTO {
  const dto = record(value, "$");
  const run = workflowRun(requireField(dto, "workflow", "$"), "$.workflow");
  const changed = booleanValue(requireField(dto, "changed", "$"), "$.changed");
  const replayed = booleanValue(requireField(dto, "replayed", "$"), "$.replayed");
  const appliedRevision = stringValue(requireField(dto, "applied_revision", "$"), "$.applied_revision");
  if (!/^[0-9a-f]{64}$/.test(appliedRevision)) fail("$.applied_revision", "a 64-character lowercase hexadecimal revision", appliedRevision);
  if (run.project_id !== projectId) fail("$.workflow.project_id", `the requested project id ${projectId}`, run.project_id);
  if (command.kind === "start_workflow") {
    if (run.template_id !== command.template_id) fail("$.workflow.template_id", "the submitted template id", run.template_id);
  } else {
    if (run.id !== command.run_id) fail("$.workflow.id", `the submitted workflow run id ${command.run_id}`, run.id);
  }
  if (replayed && changed) fail("$.changed", "false for an idempotent replay", changed);
  if (!replayed && run.revision !== appliedRevision) {
    fail("$.workflow.revision", "the freshly applied revision", run.revision);
  }
  return value as WorkflowCommandResultDTO;
}

export function validateWorkflowCommandReceiptDTOForRequest(
  value: unknown,
  projectId: number,
  command: WorkflowCommandDTO,
): WorkflowCommandReceiptDTO {
  const dto = record(value, "$");
  const returnedProjectId = integerValue(requireField(dto, "project_id", "$"), "$.project_id");
  const requestDigest = stringValue(requireField(dto, "request_digest", "$"), "$.request_digest");
  const commandKind = stringValue(requireField(dto, "command_kind", "$"), "$.command_kind");
  const expectedRevision = stringValue(requireField(dto, "expected_revision", "$"), "$.expected_revision");
  const appliedRevision = stringValue(requireField(dto, "applied_revision", "$"), "$.applied_revision");
  booleanValue(requireField(dto, "original_changed", "$"), "$.original_changed");
  const originalRunId = integerValue(requireField(dto, "original_run_id", "$"), "$.original_run_id");
  const committedAt = isoTimestamp(requireField(dto, "committed_at", "$"), "$.committed_at");
  if (returnedProjectId !== projectId) fail("$.project_id", `the requested project id ${projectId}`, returnedProjectId);
  if (!/^[0-9a-f]{64}$/.test(requestDigest)) fail("$.request_digest", "a 64-character lowercase hexadecimal digest", requestDigest);
  if (commandKind !== command.kind) fail("$.command_kind", `the submitted command kind ${command.kind}`, commandKind);
  const submittedRevision = command.kind === "start_workflow" ? "" : command.expected_revision;
  if (expectedRevision !== submittedRevision) fail("$.expected_revision", "the submitted expected revision", expectedRevision);
  if (!/^[0-9a-f]{64}$/.test(appliedRevision)) fail("$.applied_revision", "a 64-character lowercase hexadecimal revision", appliedRevision);
  if (originalRunId <= 0) fail("$.original_run_id", "a positive Workflow run id", originalRunId);
  if (command.kind !== "start_workflow" && originalRunId !== command.run_id) {
    fail("$.original_run_id", `the submitted workflow run id ${command.run_id}`, originalRunId);
  }
  if (!committedAt) fail("$.committed_at", "a non-empty ISO timestamp", committedAt);
  return value as WorkflowCommandReceiptDTO;
}

function knowledgeGraphNode(value: unknown, path: string): KnowledgeGraphNodeDTO {
  const dto = record(value, path);
  for (const key of ["key", "node_type", "source_type", "label", "summary"] as const) {
    const field = stringValue(requireField(dto, key, path), fieldPath(path, key));
    if ((key === "key" || key === "node_type") && !field.trim()) {
      fail(fieldPath(path, key), "a non-empty string", field);
    }
  }
  nullable(requireField(dto, "source_id", path), fieldPath(path, "source_id"), stringValue);
  record(requireField(dto, "metadata", path), fieldPath(path, "metadata"));
  const degree = integerValue(requireField(dto, "degree", path), fieldPath(path, "degree"));
  if (degree < 0) fail(fieldPath(path, "degree"), "zero or greater", degree);
  const storyGravity = nullable(
    requireField(dto, "story_gravity", path),
    fieldPath(path, "story_gravity"),
    numberValue,
  );
  if (storyGravity !== null && (storyGravity < 0 || storyGravity > 1)) {
    fail(fieldPath(path, "story_gravity"), "null or a finite number from 0 through 1", storyGravity);
  }
  return value as KnowledgeGraphNodeDTO;
}

const STORY_ORDER_METADATA_FIELDS = [
  "story_order_index",
  "story_order_total",
  "story_order_band",
  "act_boundary",
] as const;

function validateStoryOrderMetadata(
  metadata: JsonRecord,
  edgeType: string,
  path: string,
): void {
  const present = STORY_ORDER_METADATA_FIELDS.filter((key) => (
    Object.prototype.hasOwnProperty.call(metadata, key)
  ));
  if (present.length === 0) return;
  if (edgeType !== "precedes" && edgeType !== "follows") {
    fail(path, "story-order metadata only on precedes or follows edges", metadata);
  }
  if (present.length !== STORY_ORDER_METADATA_FIELDS.length) {
    fail(path, "all four story-order metadata fields when any is present", metadata);
  }
  const index = integerValue(metadata.story_order_index, fieldPath(path, "story_order_index"));
  const total = integerValue(metadata.story_order_total, fieldPath(path, "story_order_total"));
  if (index < 0) fail(fieldPath(path, "story_order_index"), "zero or greater", index);
  if (total < 2) fail(fieldPath(path, "story_order_total"), "two or greater for an order segment", total);
  if (edgeType === "precedes" && index >= total - 1) {
    fail(fieldPath(path, "story_order_index"), `less than story_order_total - 1 (${total - 1}) for precedes`, index);
  }
  if (edgeType === "follows" && (index < 1 || index >= total)) {
    fail(fieldPath(path, "story_order_index"), `from 1 through story_order_total - 1 (${total - 1}) for follows`, index);
  }
  const band = stringValue(metadata.story_order_band, fieldPath(path, "story_order_band"));
  if (!["beginning", "middle", "ending"].includes(band)) {
    fail(fieldPath(path, "story_order_band"), "beginning, middle, or ending", band);
  }
  booleanValue(metadata.act_boundary, fieldPath(path, "act_boundary"));
}

function knowledgeGraphEdge(value: unknown, path: string): KnowledgeGraphEdgeDTO {
  const dto = record(value, path);
  for (const key of [
    "source", "target", "edge_type", "confidence", "provenance", "source_system", "explanation",
  ] as const) {
    const field = stringValue(requireField(dto, key, path), fieldPath(path, key));
    if ((key === "source" || key === "target" || key === "edge_type") && !field.trim()) {
      fail(fieldPath(path, key), "a non-empty string", field);
    }
  }
  if (!["confirmed", "likely", "possible", "unknown"].includes(dto.confidence as string)) {
    fail(fieldPath(path, "confidence"), "confirmed, likely, possible, or unknown", dto.confidence);
  }
  booleanValue(requireField(dto, "is_user_confirmed", path), fieldPath(path, "is_user_confirmed"));
  booleanValue(requireField(dto, "is_inferred", path), fieldPath(path, "is_inferred"));
  booleanValue(requireField(dto, "is_hidden", path), fieldPath(path, "is_hidden"));
  const metadataPath = fieldPath(path, "metadata");
  const metadata = record(requireField(dto, "metadata", path), metadataPath);
  validateStoryOrderMetadata(metadata, dto.edge_type as string, metadataPath);
  return value as KnowledgeGraphEdgeDTO;
}

function knowledgeGraphEdgeIdentity(value: unknown, path: string): KnowledgeGraphEdgeIdentityDTO {
  const dto = record(value, path);
  for (const key of ["source", "target", "edge_type"] as const) {
    const field = stringValue(requireField(dto, key, path), fieldPath(path, key));
    if (!field.trim()) fail(fieldPath(path, key), "a non-empty string", field);
  }
  return value as KnowledgeGraphEdgeIdentityDTO;
}

function graphEdgeIdentity(edge: KnowledgeGraphEdgeDTO): string {
  return [edge.source, edge.target, edge.edge_type].join("\u0000");
}

const KNOWLEDGE_GRAPH_VIEW_MODES: readonly KnowledgeGraphViewMode[] = [
  "project_map",
  "structure",
  "recorded_risk",
  "revision_impact",
];

function knowledgeGraphViewMode(value: unknown, path: string): KnowledgeGraphViewMode {
  const mode = stringValue(value, path);
  return KNOWLEDGE_GRAPH_VIEW_MODES.includes(mode as KnowledgeGraphViewMode)
    ? mode as KnowledgeGraphViewMode
    : fail(path, "project_map, structure, recorded_risk, or revision_impact", value);
}

function knowledgeGraphRead(value: unknown, path: string): KnowledgeGraphReadDTO {
  const dto = record(value, path);
  const projectId = integerValue(requireField(dto, "project_id", path), fieldPath(path, "project_id"));
  if (projectId <= 0) fail(fieldPath(path, "project_id"), "a positive safe integer", projectId);
  const revision = stringValue(requireField(dto, "revision", path), fieldPath(path, "revision"));
  if (!/^[0-9a-f]{64}$/.test(revision)) {
    fail(fieldPath(path, "revision"), "a 64-character lowercase hexadecimal revision", revision);
  }
  stringValue(requireField(dto, "writing_mode", path), fieldPath(path, "writing_mode"));
  const focusKey = nullable(
    requireField(dto, "focus_key", path),
    fieldPath(path, "focus_key"),
    stringValue,
  );
  const depth = integerValue(requireField(dto, "depth", path), fieldPath(path, "depth"));
  if (depth < 1 || depth > 2) fail(fieldPath(path, "depth"), "1 or 2", depth);
  const includeInferred = booleanValue(
    requireField(dto, "include_inferred", path),
    fieldPath(path, "include_inferred"),
  );
  const viewMode = knowledgeGraphViewMode(
    requireField(dto, "view_mode", path),
    fieldPath(path, "view_mode"),
  );
  const storyDiagnosticsAvailable = booleanValue(
    requireField(dto, "story_diagnostics_available", path),
    fieldPath(path, "story_diagnostics_available"),
  );
  if (storyDiagnosticsAvailable !== (viewMode === "project_map")) {
    fail(
      fieldPath(path, "story_diagnostics_available"),
      viewMode === "project_map"
        ? "true for the project_map view"
        : `false for the ${viewMode} view`,
      storyDiagnosticsAvailable,
    );
  }
  const storyGravityAvailable = booleanValue(
    requireField(dto, "story_gravity_available", path),
    fieldPath(path, "story_gravity_available"),
  );

  const nodesPath = fieldPath(path, "nodes");
  const nodes = arrayOf(requireField(dto, "nodes", path), nodesPath, knowledgeGraphNode);
  const nodeKeys = new Set<string>();
  nodes.forEach((node, index) => {
    if (nodeKeys.has(node.key)) fail(`${nodesPath}[${index}].key`, "a unique node key", node.key);
    nodeKeys.add(node.key);
    if (!storyGravityAvailable && node.story_gravity !== null) {
      fail(
        `${nodesPath}[${index}].story_gravity`,
        "null when story_gravity_available is false",
        node.story_gravity,
      );
    }
  });
  if (focusKey !== null && !nodeKeys.has(focusKey)) {
    fail(fieldPath(path, "focus_key"), "a key present in nodes", focusKey);
  }

  const edgesPath = fieldPath(path, "edges");
  const edges = arrayOf(requireField(dto, "edges", path), edgesPath, knowledgeGraphEdge);
  const edgeKeys = new Set<string>();
  edges.forEach((edge, index) => {
    const edgePath = `${edgesPath}[${index}]`;
    if (!nodeKeys.has(edge.source)) fail(fieldPath(edgePath, "source"), "a key present in nodes", edge.source);
    if (!nodeKeys.has(edge.target)) fail(fieldPath(edgePath, "target"), "a key present in nodes", edge.target);
    const identity = graphEdgeIdentity(edge);
    if (edgeKeys.has(identity)) fail(edgePath, "a unique directed source/target/type edge", edge);
    if (edge.is_hidden) fail(fieldPath(edgePath, "is_hidden"), "false for a visible edge", edge.is_hidden);
    if (!includeInferred && edge.is_inferred) {
      fail(fieldPath(edgePath, "is_inferred"), "false when include_inferred is false", edge.is_inferred);
    }
    edgeKeys.add(identity);
  });

  const counts = {} as Record<"node_count" | "edge_count" | "returned_node_count" | "returned_edge_count" | "orphan_count" | "weak_link_count" | "hidden_edge_count", number>;
  for (const key of [
    "node_count", "edge_count", "returned_node_count", "returned_edge_count", "orphan_count", "weak_link_count", "hidden_edge_count",
  ] as const) {
    const count = integerValue(requireField(dto, key, path), fieldPath(path, key));
    if (count < 0) fail(fieldPath(path, key), "zero or greater", count);
    counts[key] = count;
  }
  if (counts.returned_node_count !== nodes.length) {
    fail(fieldPath(path, "returned_node_count"), `the nodes length (${nodes.length})`, counts.returned_node_count);
  }
  if (counts.returned_edge_count !== edges.length) {
    fail(fieldPath(path, "returned_edge_count"), `the edges length (${edges.length})`, counts.returned_edge_count);
  }
  if (counts.node_count < nodes.length) {
    fail(fieldPath(path, "node_count"), `at least the returned nodes length (${nodes.length})`, counts.node_count);
  }
  if (counts.edge_count < edges.length) {
    fail(fieldPath(path, "edge_count"), `at least the returned edges length (${edges.length})`, counts.edge_count);
  }

  const orphanKeysPath = fieldPath(path, "orphan_keys");
  const orphanKeys = stringArray(requireField(dto, "orphan_keys", path), orphanKeysPath);
  const seenOrphans = new Set<string>();
  orphanKeys.forEach((key, index) => {
    if (!nodeKeys.has(key)) fail(`${orphanKeysPath}[${index}]`, "a key present in nodes", key);
    if (seenOrphans.has(key)) fail(`${orphanKeysPath}[${index}]`, "a unique orphan key", key);
    seenOrphans.add(key);
  });
  if (counts.orphan_count < orphanKeys.length) {
    fail(fieldPath(path, "orphan_count"), `at least the returned orphan key count (${orphanKeys.length})`, counts.orphan_count);
  }
  if (!storyDiagnosticsAvailable && (orphanKeys.length > 0 || counts.orphan_count !== 0)) {
    fail(
      fieldPath(path, "orphan_count"),
      "zero when story diagnostics are unavailable",
      counts.orphan_count,
    );
  }

  const weakLinksPath = fieldPath(path, "weak_links");
  const weakLinks = arrayOf(
    requireField(dto, "weak_links", path),
    weakLinksPath,
    knowledgeGraphEdge,
  );
  const seenWeakLinks = new Set<string>();
  weakLinks.forEach((edge, index) => {
    const edgePath = `${weakLinksPath}[${index}]`;
    if (!nodeKeys.has(edge.source)) fail(fieldPath(edgePath, "source"), "a key present in nodes", edge.source);
    if (!nodeKeys.has(edge.target)) fail(fieldPath(edgePath, "target"), "a key present in nodes", edge.target);
    const identity = graphEdgeIdentity(edge);
    if (seenWeakLinks.has(identity)) fail(edgePath, "a unique weak link", edge);
    if (edge.is_hidden) fail(fieldPath(edgePath, "is_hidden"), "false for a visible weak link", edge.is_hidden);
    if (!includeInferred && edge.is_inferred) {
      fail(fieldPath(edgePath, "is_inferred"), "false when include_inferred is false", edge.is_inferred);
    }
    seenWeakLinks.add(identity);
  });
  if (counts.weak_link_count < weakLinks.length) {
    fail(fieldPath(path, "weak_link_count"), `at least the returned weak-link count (${weakLinks.length})`, counts.weak_link_count);
  }
  if (!storyDiagnosticsAvailable && (weakLinks.length > 0 || counts.weak_link_count !== 0)) {
    fail(
      fieldPath(path, "weak_link_count"),
      "zero when story diagnostics are unavailable",
      counts.weak_link_count,
    );
  }

  const hiddenEdgesPath = fieldPath(path, "hidden_edges");
  const hiddenEdges = arrayOf(
    requireField(dto, "hidden_edges", path),
    hiddenEdgesPath,
    knowledgeGraphEdge,
  );
  const seenHiddenEdges = new Set<string>();
  hiddenEdges.forEach((edge, index) => {
    const edgePath = `${hiddenEdgesPath}[${index}]`;
    if (!nodeKeys.has(edge.source)) fail(fieldPath(edgePath, "source"), "a key present in nodes", edge.source);
    if (!nodeKeys.has(edge.target)) fail(fieldPath(edgePath, "target"), "a key present in nodes", edge.target);
    const identity = graphEdgeIdentity(edge);
    if (seenHiddenEdges.has(identity)) fail(edgePath, "a unique hidden edge", edge);
    if (edgeKeys.has(identity)) fail(edgePath, "an edge not also present in visible edges", edge);
    if (!edge.is_hidden) fail(fieldPath(edgePath, "is_hidden"), "true for a hidden edge", edge.is_hidden);
    seenHiddenEdges.add(identity);
  });
  if (counts.hidden_edge_count < hiddenEdges.length) {
    fail(fieldPath(path, "hidden_edge_count"), `at least the returned hidden-edge count (${hiddenEdges.length})`, counts.hidden_edge_count);
  }
  if (viewMode !== "project_map" && hiddenEdges.length > 0) {
    fail(
      hiddenEdgesPath,
      `empty for the ${viewMode} view; use the complete hidden-edge queue`,
      hiddenEdges,
    );
  }

  const truncated = booleanValue(requireField(dto, "truncated", path), fieldPath(path, "truncated"));
  const hasMissingRows = counts.node_count > nodes.length
    || counts.edge_count > edges.length
    || (storyDiagnosticsAvailable && counts.orphan_count > orphanKeys.length)
    || (storyDiagnosticsAvailable && counts.weak_link_count > weakLinks.length)
    || (viewMode === "project_map" && counts.hidden_edge_count > hiddenEdges.length);
  if (truncated !== hasMissingRows) {
    fail(fieldPath(path, "truncated"), hasMissingRows ? "true when any graph collection is capped" : "false when every graph collection is returned", truncated);
  }
  const warnings = stringArray(requireField(dto, "warnings", path), fieldPath(path, "warnings"));
  if (warnings.length > 25) fail(fieldPath(path, "warnings"), "at most 25 entries", warnings);
  const unavailable = stringArray(requireField(dto, "unavailable", path), fieldPath(path, "unavailable"));
  if (unavailable.length > 25) fail(fieldPath(path, "unavailable"), "at most 25 entries", unavailable);
  return value as KnowledgeGraphReadDTO;
}

export function validateKnowledgeGraphReadDTOForRequest(
  value: unknown,
  projectId: number,
  query: KnowledgeGraphQueryDTO = {},
): KnowledgeGraphReadDTO {
  const graph = knowledgeGraphRead(value, "$");
  if (graph.project_id !== projectId) {
    fail("$.project_id", `the requested project id ${projectId}`, graph.project_id);
  }
  const expectedFocus = query.focus_key ?? null;
  if (graph.focus_key !== expectedFocus) {
    fail("$.focus_key", expectedFocus === null ? "null for a full-view request" : `the requested focus key ${expectedFocus}`, graph.focus_key);
  }
  const expectedDepth = query.depth ?? 1;
  if (graph.depth !== expectedDepth) {
    fail("$.depth", `the requested depth ${expectedDepth}`, graph.depth);
  }
  const expectedInferred = query.include_inferred ?? true;
  if (graph.include_inferred !== expectedInferred) {
    fail("$.include_inferred", `the requested value ${expectedInferred}`, graph.include_inferred);
  }
  const expectedViewMode = knowledgeGraphViewMode(
    query.view_mode ?? "project_map",
    "$request.view_mode",
  );
  if (graph.view_mode !== expectedViewMode) {
    fail("$.view_mode", `the requested view mode ${expectedViewMode}`, graph.view_mode);
  }
  const limit = query.limit ?? 100;
  if (graph.nodes.length > limit) fail("$.nodes", `at most the requested limit (${limit})`, graph.nodes);
  if (graph.edges.length > limit) fail("$.edges", `at most the requested limit (${limit})`, graph.edges);
  const weakLinkLimit = Math.min(limit, 25);
  if (graph.weak_links.length > weakLinkLimit) fail("$.weak_links", `at most ${weakLinkLimit} entries`, graph.weak_links);
  if (graph.hidden_edges.length > weakLinkLimit) fail("$.hidden_edges", `at most ${weakLinkLimit} entries`, graph.hidden_edges);
  return graph;
}

function sameKnowledgeGraphEdgeIdentity(
  left: KnowledgeGraphEdgeIdentityDTO,
  right: KnowledgeGraphEdgeIdentityDTO,
): boolean {
  return left.source === right.source
    && left.target === right.target
    && left.edge_type === right.edge_type;
}

export function validateKnowledgeGraphCommandResultDTOForRequest(
  value: unknown,
  projectId: number,
  command: KnowledgeGraphCommandDTO,
): KnowledgeGraphCommandResultDTO {
  const dto = record(value, "$");
  const knowledgeGraph = knowledgeGraphRead(
    requireField(dto, "knowledge_graph", "$"),
    "$.knowledge_graph",
  );
  const changed = booleanValue(requireField(dto, "changed", "$"), "$.changed");
  const replayed = booleanValue(requireField(dto, "replayed", "$"), "$.replayed");
  const affectedEdge = knowledgeGraphEdgeIdentity(
    requireField(dto, "affected_edge", "$"),
    "$.affected_edge",
  );
  const appliedRevision = stringValue(
    requireField(dto, "applied_revision", "$"),
    "$.applied_revision",
  );
  if (!/^[0-9a-f]{64}$/.test(appliedRevision)) {
    fail("$.applied_revision", "a 64-character lowercase hexadecimal revision", appliedRevision);
  }
  if (knowledgeGraph.project_id !== projectId) {
    fail("$.knowledge_graph.project_id", `the requested project id ${projectId}`, knowledgeGraph.project_id);
  }
  if (
    knowledgeGraph.focus_key !== null
    || knowledgeGraph.depth !== 1
    || !knowledgeGraph.include_inferred
    || knowledgeGraph.view_mode !== "project_map"
    || !knowledgeGraph.story_diagnostics_available
  ) {
    fail("$.knowledge_graph", "the default Project Map query (no focus, depth 1, inferred edges and story diagnostics included)", knowledgeGraph);
  }
  if (knowledgeGraph.nodes.length > 100) fail("$.knowledge_graph.nodes", "at most 100 entries", knowledgeGraph.nodes);
  if (knowledgeGraph.edges.length > 100) fail("$.knowledge_graph.edges", "at most 100 entries", knowledgeGraph.edges);
  if (knowledgeGraph.weak_links.length > 25) fail("$.knowledge_graph.weak_links", "at most 25 entries", knowledgeGraph.weak_links);
  if (knowledgeGraph.hidden_edges.length > 25) fail("$.knowledge_graph.hidden_edges", "at most 25 entries", knowledgeGraph.hidden_edges);
  if (!sameKnowledgeGraphEdgeIdentity(affectedEdge, command)) {
    fail("$.affected_edge", "the edge targeted by the submitted command", affectedEdge);
  }
  if (replayed && changed) fail("$.changed", "false for an idempotent replay", changed);
  if (!replayed && !changed) fail("$.changed", "true for a freshly accepted graph command", changed);
  if (!replayed && changed && appliedRevision === command.expected_revision) {
    fail("$.applied_revision", "a new revision when changed is true", appliedRevision);
  }
  return value as KnowledgeGraphCommandResultDTO;
}

export function validateKnowledgeGraphCommandReceiptDTOForRequest(
  value: unknown,
  projectId: number,
  command: KnowledgeGraphCommandDTO,
): KnowledgeGraphCommandReceiptDTO {
  const dto = record(value, "$");
  const returnedProjectId = integerValue(requireField(dto, "project_id", "$"), "$.project_id");
  const requestDigest = stringValue(requireField(dto, "request_digest", "$"), "$.request_digest");
  const commandKind = stringValue(requireField(dto, "command_kind", "$"), "$.command_kind");
  const expectedRevision = stringValue(requireField(dto, "expected_revision", "$"), "$.expected_revision");
  const appliedRevision = stringValue(requireField(dto, "applied_revision", "$"), "$.applied_revision");
  const originalChanged = booleanValue(requireField(dto, "original_changed", "$"), "$.original_changed");
  const affectedEdge = knowledgeGraphEdgeIdentity(
    requireField(dto, "original_affected_edge", "$"),
    "$.original_affected_edge",
  );
  const committedAt = stringValue(requireField(dto, "committed_at", "$"), "$.committed_at");
  if (returnedProjectId !== projectId) fail("$.project_id", `the requested project id ${projectId}`, returnedProjectId);
  if (!/^[0-9a-f]{64}$/.test(requestDigest)) fail("$.request_digest", "a 64-character lowercase hexadecimal digest", requestDigest);
  if (commandKind !== command.kind) fail("$.command_kind", `the submitted command kind ${command.kind}`, commandKind);
  if (expectedRevision !== command.expected_revision) fail("$.expected_revision", "the submitted expected revision", expectedRevision);
  if (!/^[0-9a-f]{64}$/.test(expectedRevision)) fail("$.expected_revision", "a 64-character lowercase hexadecimal revision", expectedRevision);
  if (!/^[0-9a-f]{64}$/.test(appliedRevision)) fail("$.applied_revision", "a 64-character lowercase hexadecimal revision", appliedRevision);
  if (!originalChanged) fail("$.original_changed", "true for a committed graph edge-review command", originalChanged);
  if (originalChanged && appliedRevision === expectedRevision) fail("$.applied_revision", "a new revision when original_changed is true", appliedRevision);
  if (!sameKnowledgeGraphEdgeIdentity(affectedEdge, command)) fail("$.original_affected_edge", "the edge targeted by the submitted command", affectedEdge);
  if (!committedAt.trim() || Number.isNaN(Date.parse(committedAt))) fail("$.committed_at", "a non-empty ISO timestamp", committedAt);
  return value as KnowledgeGraphCommandReceiptDTO;
}

export function validateKnowledgeGraphHiddenEdgePageDTOForRequest(
  value: unknown,
  projectId: number,
  offset: number,
  limit: number,
): KnowledgeGraphHiddenEdgePageDTO {
  const dto = record(value, "$");
  const returnedProjectId = integerValue(requireField(dto, "project_id", "$"), "$.project_id");
  const revision = stringValue(requireField(dto, "revision", "$"), "$.revision");
  const returnedOffset = integerValue(requireField(dto, "offset", "$"), "$.offset");
  const returnedLimit = integerValue(requireField(dto, "limit", "$"), "$.limit");
  const hiddenEdgeCount = integerValue(requireField(dto, "hidden_edge_count", "$"), "$.hidden_edge_count");
  const returnedEdgeCount = integerValue(requireField(dto, "returned_edge_count", "$"), "$.returned_edge_count");
  const nodes = arrayOf(requireField(dto, "nodes", "$"), "$.nodes", knowledgeGraphNode);
  const edges = arrayOf(requireField(dto, "edges", "$"), "$.edges", knowledgeGraphEdge);
  if (returnedProjectId !== projectId) fail("$.project_id", `the requested project id ${projectId}`, returnedProjectId);
  if (!/^[0-9a-f]{64}$/.test(revision)) fail("$.revision", "a 64-character lowercase hexadecimal revision", revision);
  if (returnedOffset !== offset) fail("$.offset", `the requested offset ${offset}`, returnedOffset);
  if (returnedLimit !== limit) fail("$.limit", `the requested limit ${limit}`, returnedLimit);
  if (hiddenEdgeCount < 0) fail("$.hidden_edge_count", "zero or greater", hiddenEdgeCount);
  if (returnedEdgeCount !== edges.length) fail("$.returned_edge_count", `the edges length (${edges.length})`, returnedEdgeCount);
  const expectedPageLength = Math.min(limit, Math.max(hiddenEdgeCount - offset, 0));
  if (edges.length !== expectedPageLength) fail("$.edges", `exactly ${expectedPageLength} entries for this page`, edges);
  if (edges.length > limit) fail("$.edges", `at most the requested limit (${limit})`, edges);
  if (edges.length > 0 && offset + edges.length > hiddenEdgeCount) fail("$.edges", "a page within hidden_edge_count", edges);
  if (nodes.length > limit * 2) fail("$.nodes", `at most ${limit * 2} endpoint nodes`, nodes);
  const nodeKeys = new Set<string>();
  nodes.forEach((node, index) => {
    if (nodeKeys.has(node.key)) fail(`$.nodes[${index}].key`, "a unique endpoint-node key", node.key);
    nodeKeys.add(node.key);
  });
  const seen = new Set<string>();
  const endpointKeys = new Set<string>();
  edges.forEach((edge, index) => {
    const edgePath = `$.edges[${index}]`;
    if (!edge.is_hidden) fail(`${edgePath}.is_hidden`, "true for a hidden edge", edge.is_hidden);
    if (!nodeKeys.has(edge.source)) fail(`${edgePath}.source`, "a key present in nodes", edge.source);
    if (!nodeKeys.has(edge.target)) fail(`${edgePath}.target`, "a key present in nodes", edge.target);
    endpointKeys.add(edge.source);
    endpointKeys.add(edge.target);
    const identity = graphEdgeIdentity(edge);
    if (seen.has(identity)) fail(edgePath, "a unique hidden edge", edge);
    seen.add(identity);
  });
  nodes.forEach((node, index) => {
    if (!endpointKeys.has(node.key)) fail(`$.nodes[${index}].key`, "an endpoint referenced by this page", node.key);
  });
  return value as KnowledgeGraphHiddenEdgePageDTO;
}

export function validateStoryStructureCommandResultDTOForRequest(
  value: unknown,
  projectId: number,
  command: StoryStructureCommandDTO,
): StoryStructureCommandResultDTO {
  const result = storyStructureCommandResult(value, "$");
  if (result.structure.project_id !== projectId) {
    fail("$.structure.project_id", `the requested project id ${projectId}`, result.structure.project_id);
  }

  const returnedSceneIds = new Set(result.structure.acts.flatMap((act) => (
    act.chapters.flatMap((chapter) => chapter.scenes.map((scene) => scene.id))
  )));
  const createsScene = command.kind === "create_scene"
    || command.kind === "create_act"
    || command.kind === "create_chapter";
  if (createsScene && result.changed && result.created_scene_id === null) {
    fail("$.created_scene_id", `a positive Scene id for ${command.kind}`, result.created_scene_id);
  }
  if (!createsScene && result.created_scene_id !== null) {
    fail("$.created_scene_id", `null for ${command.kind}`, result.created_scene_id);
  }

  if (command.kind === "delete_scene") {
    if (!result.affected_scene_ids.includes(command.scene_id)) {
      fail("$.affected_scene_ids", `an array including deleted Scene ${command.scene_id}`, result.affected_scene_ids);
    }
    if (returnedSceneIds.has(command.scene_id)) {
      fail("$.structure", `a structure without deleted Scene ${command.scene_id}`, result.structure);
    }
    result.affected_scene_ids.forEach((sceneId, index) => {
      if (sceneId !== command.scene_id && !returnedSceneIds.has(sceneId)) {
        fail(
          `$.affected_scene_ids[${index}]`,
          "the id of a surviving Scene present in the returned structure",
          sceneId,
        );
      }
    });
  } else {
    result.affected_scene_ids.forEach((sceneId, index) => {
      if (!returnedSceneIds.has(sceneId)) {
        fail(
          `$.affected_scene_ids[${index}]`,
          "the id of a surviving Scene present in the returned structure",
          sceneId,
        );
      }
    });
  }
  return result;
}

function settings(value: unknown, path: string): SettingsDTO {
  const dto = record(value, path);
  record(requireField(dto, "settings", path), fieldPath(path, "settings"));
  return value as SettingsDTO;
}

function psykeConsoleAction(value: unknown, path: string): PsykeConsoleAction {
  return value === "create_psyke_entry"
    || value === "open_scene"
    || value === "open_psyke_entry"
    ? value
    : fail(path, "a supported PSYKE Console action", value);
}

function psykeConsoleTarget(value: unknown, path: string): PsykeConsoleTarget {
  return value === "scene" || value === "psyke_entry"
    ? value
    : fail(path, '\"scene\" or \"psyke_entry\"', value);
}

function psykeConsoleCommandPlan(value: unknown, path: string): PsykeConsoleCommandPlanDTO {
  const dto = record(value, path);
  for (const key of ["plan_id", "command", "normalized_command", "summary", "expires_at"]) {
    stringValue(requireField(dto, key, path), fieldPath(path, key));
  }
  psykeConsoleAction(requireField(dto, "action", path), fieldPath(path, "action"));
  stringArray(requireField(dto, "effects", path), fieldPath(path, "effects"));
  booleanValue(requireField(dto, "requires_confirmation", path), fieldPath(path, "requires_confirmation"));
  booleanValue(requireField(dto, "mutates", path), fieldPath(path, "mutates"));
  psykeConsoleTarget(requireField(dto, "target_type", path), fieldPath(path, "target_type"));
  nullable(requireField(dto, "target_id", path), fieldPath(path, "target_id"), integerValue);
  return value as PsykeConsoleCommandPlanDTO;
}

function psykeConsoleExecution(value: unknown, path: string): PsykeConsoleExecutionDTO {
  const dto = record(value, path);
  booleanValue(requireField(dto, "ok", path), fieldPath(path, "ok"));
  psykeConsoleAction(requireField(dto, "action", path), fieldPath(path, "action"));
  stringValue(requireField(dto, "message", path), fieldPath(path, "message"));
  booleanValue(requireField(dto, "mutated", path), fieldPath(path, "mutated"));
  psykeConsoleTarget(requireField(dto, "target_type", path), fieldPath(path, "target_type"));
  integerValue(requireField(dto, "target_id", path), fieldPath(path, "target_id"));
  return value as PsykeConsoleExecutionDTO;
}

function outlineNode(value: unknown, path: string): OutlineNodeDTO {
  const pending: Array<{ value: unknown; path: string }> = [{ value, path }];
  while (pending.length) {
    const current = pending.pop()!;
    const dto = record(current.value, current.path);
    integerValue(requireField(dto, "id", current.path), fieldPath(current.path, "id"));
    nullable(
      requireField(dto, "parent_id", current.path),
      fieldPath(current.path, "parent_id"),
      integerValue,
    );
    stringValue(requireField(dto, "title", current.path), fieldPath(current.path, "title"));
    stringValue(
      requireField(dto, "description", current.path),
      fieldPath(current.path, "description"),
    );
    integerValue(
      requireField(dto, "sort_order", current.path),
      fieldPath(current.path, "sort_order"),
    );
    nullable(
      requireField(dto, "scene_id", current.path),
      fieldPath(current.path, "scene_id"),
      integerValue,
    );
    const childrenPath = fieldPath(current.path, "children");
    const children = requireField(dto, "children", current.path);
    if (!Array.isArray(children)) fail(childrenPath, "an array", children);
    for (let index = children.length - 1; index >= 0; index -= 1) {
      pending.push({ value: children[index], path: childrenPath + "[" + index + "]" });
    }
  }
  return value as OutlineNodeDTO;
}

function outlineGenerateResult(value: unknown, path: string): OutlineGenerateResultDTO {
  const dto = record(value, path);
  booleanValue(requireField(dto, "ok", path), fieldPath(path, "ok"));
  integerValue(requireField(dto, "created", path), fieldPath(path, "created"));
  integerArray(requireField(dto, "node_ids", path), fieldPath(path, "node_ids"));
  stringArray(requireField(dto, "warnings", path), fieldPath(path, "warnings"));
  stringArray(requireField(dto, "errors", path), fieldPath(path, "errors"));
  return value as OutlineGenerateResultDTO;
}

function voiceBillyProposal(value: unknown, path: string): VoiceBillyProposalDTO {
  const dto = record(value, path);
  for (const key of [
    "id", "proposal_type", "operation", "prompt_text", "response_text",
    "target_summary", "gn_field", "reason_if_blocked",
  ]) {
    stringValue(requireField(dto, key, path), fieldPath(path, key));
  }
  integerValue(requireField(dto, "project_id", path), fieldPath(path, "project_id"));
  numberValue(requireField(dto, "created_at", path), fieldPath(path, "created_at"));
  stringArray(
    requireField(dto, "source_segment_ids", path),
    fieldPath(path, "source_segment_ids"),
  );
  for (const key of ["before_text", "after_text", "diff"]) {
    nullable(requireField(dto, key, path), fieldPath(path, key), stringValue);
  }
  for (const key of ["note_preview", "psyke_preview"]) {
    nullable(requireField(dto, key, path), fieldPath(path, key), record);
  }
  nullable(requireField(dto, "gn_ref", path), fieldPath(path, "gn_ref"), integerArray);
  for (const key of ["can_apply", "applied", "cancelled"]) {
    booleanValue(requireField(dto, key, path), fieldPath(path, key));
  }
  nullable(requireField(dto, "applied_at", path), fieldPath(path, "applied_at"), numberValue);
  return value as VoiceBillyProposalDTO;
}

function nearDupHint(value: unknown, path: string): NearDupHintDTO {
  const dto = record(value, path);
  integerValue(requireField(dto, "existing_id", path), fieldPath(path, "existing_id"));
  stringValue(requireField(dto, "existing_name", path), fieldPath(path, "existing_name"));
  numberValue(requireField(dto, "score", path), fieldPath(path, "score"));
  return value as NearDupHintDTO;
}

function relationProposal(value: unknown, path: string): RelationProposalDTO {
  const dto = record(value, path);
  for (const key of ["source", "target", "rel_type"]) {
    stringValue(requireField(dto, key, path), fieldPath(path, key));
  }
  optional(dto.why, fieldPath(path, "why"), stringValue);
  optional(dto.confidence, fieldPath(path, "confidence"), numberValue);
  optional(dto.source_status, fieldPath(path, "source_status"), stringValue);
  optional(dto.target_status, fieldPath(path, "target_status"), stringValue);
  optional(dto.source_hint, fieldPath(path, "source_hint"), (item, itemPath) =>
    nullable(item, itemPath, nearDupHint));
  optional(dto.target_hint, fieldPath(path, "target_hint"), (item, itemPath) =>
    nullable(item, itemPath, nearDupHint));
  return value as RelationProposalDTO;
}

function sceneExtraction(value: unknown, path: string): SceneExtractionDTO {
  const dto = record(value, path);
  integerValue(requireField(dto, "scene_id", path), fieldPath(path, "scene_id"));
  optional(dto.title, fieldPath(path, "title"), stringValue);
  stringArray(requireField(dto, "characters", path), fieldPath(path, "characters"));
  optional(dto.who_knows_what, fieldPath(path, "who_knows_what"), stringValue);
  arrayOf(requireField(dto, "relations", path), fieldPath(path, "relations"), relationProposal);
  return value as SceneExtractionDTO;
}

function extractionResult(value: unknown, path: string): ExtractionResultDTO {
  const dto = record(value, path);
  integerValue(requireField(dto, "project_id", path), fieldPath(path, "project_id"));
  booleanValue(requireField(dto, "used_llm", path), fieldPath(path, "used_llm"));
  arrayOf(requireField(dto, "scenes", path), fieldPath(path, "scenes"), sceneExtraction);
  arrayOf(
    requireField(dto, "setup_payoffs", path),
    fieldPath(path, "setup_payoffs"),
    relationProposal,
  );
  return value as ExtractionResultDTO;
}

function extractionJob(value: unknown, path: string): ExtractionJobDTO {
  const dto = record(value, path);
  stringValue(requireField(dto, "job_id", path), fieldPath(path, "job_id"));
  stringValue(requireField(dto, "status", path), fieldPath(path, "status"));
  integerValue(requireField(dto, "done", path), fieldPath(path, "done"));
  integerValue(requireField(dto, "total", path), fieldPath(path, "total"));
  optional(dto.error, fieldPath(path, "error"), stringValue);
  optional(dto.result, fieldPath(path, "result"), (item, itemPath) =>
    nullable(item, itemPath, extractionResult));
  return value as ExtractionJobDTO;
}

function assistantResponse(value: unknown, path: string): AssistantResponseDTO {
  const dto = record(value, path);
  stringValue(requireField(dto, "reply", path), fieldPath(path, "reply"));
  booleanValue(requireField(dto, "cached", path), fieldPath(path, "cached"));
  return value as AssistantResponseDTO;
}

function assistantSettings(value: unknown, path: string): AssistantSettingsDTO {
  const dto = record(value, path);
  stringValue(requireField(dto, "provider", path), fieldPath(path, "provider"));
  stringValue(requireField(dto, "model", path), fieldPath(path, "model"));
  stringValue(requireField(dto, "base_url", path), fieldPath(path, "base_url"));
  integerValue(requireField(dto, "timeout", path), fieldPath(path, "timeout"));
  if (dto.api_key !== undefined && dto.api_key !== null) {
    fail(fieldPath(path, "api_key"), "absent or null because it is write-only", dto.api_key);
  }
  return value as AssistantSettingsDTO;
}

function connectorAction(value: unknown, path: string): ConnectorActionDTO {
  const dto = record(value, path);
  stringValue(requireField(dto, "name", path), fieldPath(path, "name"));
  stringValue(requireField(dto, "description", path), fieldPath(path, "description"));
  stringValue(requireField(dto, "category", path), fieldPath(path, "category"));
  arrayOf(requireField(dto, "params", path), fieldPath(path, "params"), (item, itemPath) => {
    const param = record(item, itemPath);
    stringValue(requireField(param, "name", itemPath), fieldPath(itemPath, "name"));
    stringValue(requireField(param, "param_type", itemPath), fieldPath(itemPath, "param_type"));
    booleanValue(requireField(param, "required", itemPath), fieldPath(itemPath, "required"));
    requireField(param, "default", itemPath);
    return item;
  });
  return value as ConnectorActionDTO;
}

function aiBehavior(value: unknown, path: string): AiBehaviorDTO {
  const dto = record(value, path);
  for (const key of [
    "ctx_outline", "ctx_bible", "ctx_memory", "connector_enabled",
    "connector_allow_writes", "connector_confirm_writes",
  ]) {
    booleanValue(requireField(dto, key, path), fieldPath(path, key));
  }
  stringArray(requireField(dto, "connector_disabled_actions", path), fieldPath(path, "connector_disabled_actions"));
  stringValue(requireField(dto, "adaptive_override", path), fieldPath(path, "adaptive_override"));
  return value as AiBehaviorDTO;
}

function logosAction(value: unknown, path: string): LogosActionDTO {
  const dto = record(value, path);
  for (const key of ["name", "label", "description", "category"]) {
    stringValue(requireField(dto, key, path), fieldPath(path, key));
  }
  stringArray(requireField(dto, "sections", path), fieldPath(path, "sections"));
  for (const key of ["needs_selection", "deterministic", "generative"]) {
    booleanValue(requireField(dto, key, path), fieldPath(path, key));
  }
  return value as LogosActionDTO;
}

function logosResult(value: unknown, path: string): LogosResultDTO {
  const dto = record(value, path);
  booleanValue(requireField(dto, "ok", path), fieldPath(path, "ok"));
  for (const key of ["action", "title", "message"]) {
    stringValue(requireField(dto, key, path), fieldPath(path, key));
  }
  stringArray(requireField(dto, "suggestions", path), fieldPath(path, "suggestions"));
  recordArray(requireField(dto, "proposed_operations", path), fieldPath(path, "proposed_operations"));
  booleanValue(requireField(dto, "generative", path), fieldPath(path, "generative"));
  optional(dto.error, fieldPath(path, "error"), (item, itemPath) => nullable(item, itemPath, stringValue));
  return value as LogosResultDTO;
}

function logosSuggestion(value: unknown, path: string): LogosSuggestionDTO {
  const dto = record(value, path);
  for (const key of [
    "id", "type", "title", "message", "section_name", "evidence", "severity",
    "target_type", "target_id",
  ]) {
    stringValue(requireField(dto, key, path), fieldPath(path, key));
  }
  numberValue(requireField(dto, "confidence", path), fieldPath(path, "confidence"));
  stringArray(requireField(dto, "suggested_actions", path), fieldPath(path, "suggested_actions"));
  return value as LogosSuggestionDTO;
}

function connectorResult(value: unknown, path: string): ConnectorResultDTO {
  const dto = record(value, path);
  booleanValue(requireField(dto, "ok", path), fieldPath(path, "ok"));
  stringValue(requireField(dto, "action", path), fieldPath(path, "action"));
  requireField(dto, "result", path);
  stringValue(requireField(dto, "error", path), fieldPath(path, "error"));
  return value as ConnectorResultDTO;
}

function quantumResult(value: unknown, path: string): QuantumResultDTO {
  const dto = record(value, path);
  stringValue(requireField(dto, "kind", path), fieldPath(path, "kind"));
  stringValue(requireField(dto, "title", path), fieldPath(path, "title"));
  stringValue(requireField(dto, "body", path), fieldPath(path, "body"));
  record(requireField(dto, "payload", path), fieldPath(path, "payload"));
  return value as QuantumResultDTO;
}

function quantumSettings(value: unknown, path: string): QuantumSettingsDTO {
  const dto = record(value, path);
  stringValue(requireField(dto, "preset", path), fieldPath(path, "preset"));
  const weightsPath = fieldPath(path, "weights");
  const weights = record(requireField(dto, "weights", path), weightsPath);
  for (const [key, weight] of Object.entries(weights)) {
    numberValue(weight, fieldPath(weightsPath, key));
  }
  stringValue(requireField(dto, "selection_mode", path), fieldPath(path, "selection_mode"));
  booleanValue(requireField(dto, "show_tradeoffs", path), fieldPath(path, "show_tradeoffs"));
  numberValue(requireField(dto, "ensemble_alpha", path), fieldPath(path, "ensemble_alpha"));
  booleanValue(requireField(dto, "weight_learning", path), fieldPath(path, "weight_learning"));
  stringArray(requireField(dto, "preset_names", path), fieldPath(path, "preset_names"));
  stringArray(requireField(dto, "weight_keys", path), fieldPath(path, "weight_keys"));
  return value as QuantumSettingsDTO;
}

export const validateProjectDTO: RuntimeDtoValidator<ProjectDTO> = (value) => project(value, "$");
export const validateProjectListDTO: RuntimeDtoValidator<ProjectDTO[]> = (value) =>
  arrayOf(value, "$", project);
export const validateProjectActionResultDTO: RuntimeDtoValidator<ProjectActionResultDTO> = (value) =>
  projectActionResult(value, "$");
export const validateProjectSearchResponseDTO: RuntimeDtoValidator<ProjectSearchResponseDTO> = (value) =>
  projectSearchResponse(value, "$");
export const validateDeleteResultDTO: RuntimeDtoValidator<DeleteResultDTO> = (value) =>
  deleteResult(value, "$");
export const validateInlineCommentDTO: RuntimeDtoValidator<InlineCommentDTO> = (value) =>
  inlineComment(value, "$");
export const validateInlineCommentListDTO: RuntimeDtoValidator<InlineCommentDTO[]> = (value) =>
  arrayOf(value, "$", inlineComment);
export const validateWhiteboardImportResultDTO: RuntimeDtoValidator<WhiteboardImportResultDTO> = (value) =>
  whiteboardImportResult(value, "$");
export const validateSceneDTO: RuntimeDtoValidator<SceneDTO> = (value) => scene(value, "$");
export const validateSceneListDTO: RuntimeDtoValidator<SceneDTO[]> = (value) =>
  arrayOf(value, "$", scene);
export const validateManuscriptSnapshotDTO: RuntimeDtoValidator<ManuscriptSnapshotDTO> = (value) =>
  manuscriptSnapshot(value, "$");
export const validateStoryStructureDTO: RuntimeDtoValidator<StoryStructureDTO> = (value) =>
  storyStructure(value, "$");
export const validateStoryStructureCommandResultDTO: RuntimeDtoValidator<StoryStructureCommandResultDTO> = (value) =>
  storyStructureCommandResult(value, "$");
export const validateTimelineSnapshotDTO: RuntimeDtoValidator<TimelineSnapshotDTO> = (value) =>
  timelineSnapshot(value, "$");
export const validateTimelineCommandResultDTO: RuntimeDtoValidator<TimelineCommandResultDTO> = (value) =>
  timelineCommandResult(value, "$");
export const validateProgressionSnapshotDTO: RuntimeDtoValidator<ProgressionSnapshotDTO> = (value) =>
  progressionSnapshot(value, "$");
export const validateProgressionCommandResultDTO: RuntimeDtoValidator<ProgressionCommandResultDTO> = (value) => {
  const dto = record(value, "$");
  progressionSnapshot(requireField(dto, "progressions", "$"), "$.progressions");
  const changed = booleanValue(requireField(dto, "changed", "$"), "$.changed");
  const replayed = booleanValue(requireField(dto, "replayed", "$"), "$.replayed");
  lowercaseRevision(requireField(dto, "applied_revision", "$"), "$.applied_revision");
  progressionAffectedIds(dto, "", changed, replayed);
  return value as ProgressionCommandResultDTO;
};
export const validateCanvasPlotSnapshotDTO: RuntimeDtoValidator<CanvasPlotSnapshotDTO> = (value) =>
  canvasPlotSnapshot(value, "$");
export const validateCanvasPlotCommandResultDTO: RuntimeDtoValidator<CanvasPlotCommandResultDTO> = (value) =>
  canvasPlotCommandResult(value, "$");
export const validateKnowledgeGraphReadDTO: RuntimeDtoValidator<KnowledgeGraphReadDTO> = (value) =>
  knowledgeGraphRead(value, "$");
export const validateSettingsDTO: RuntimeDtoValidator<SettingsDTO> = (value) => settings(value, "$");
export const validatePsykeConsoleCommandPlanDTO: RuntimeDtoValidator<PsykeConsoleCommandPlanDTO> = (value) =>
  psykeConsoleCommandPlan(value, "$");
export const validatePsykeConsoleExecutionDTO: RuntimeDtoValidator<PsykeConsoleExecutionDTO> = (value) =>
  psykeConsoleExecution(value, "$");
export const validateOutlineNodeDTO: RuntimeDtoValidator<OutlineNodeDTO> = (value) => outlineNode(value, "$");
export const validateOutlineListDTO: RuntimeDtoValidator<OutlineNodeDTO[]> = (value) =>
  arrayOf(value, "$", outlineNode);
export const validateOutlineGenerateResultDTO: RuntimeDtoValidator<OutlineGenerateResultDTO> = (value) =>
  outlineGenerateResult(value, "$");
export const validateVoiceBillyProposalDTO: RuntimeDtoValidator<VoiceBillyProposalDTO> = (value) =>
  voiceBillyProposal(value, "$");
export const validateExtractionJobDTO: RuntimeDtoValidator<ExtractionJobDTO> = (value) =>
  extractionJob(value, "$");
export const validateAssistantResponseDTO: RuntimeDtoValidator<AssistantResponseDTO> = (value) =>
  assistantResponse(value, "$");
export const validateAssistantSettingsDTO: RuntimeDtoValidator<AssistantSettingsDTO> = (value) =>
  assistantSettings(value, "$");
export const validateAiBehaviorDTO: RuntimeDtoValidator<AiBehaviorDTO> = (value) => aiBehavior(value, "$");
export const validateLogosActionListDTO: RuntimeDtoValidator<LogosActionDTO[]> = (value) =>
  arrayOf(value, "$", logosAction);
export const validateLogosResultDTO: RuntimeDtoValidator<LogosResultDTO> = (value) => logosResult(value, "$");
export const validateLogosSuggestionListDTO: RuntimeDtoValidator<LogosSuggestionDTO[]> = (value) =>
  arrayOf(value, "$", logosSuggestion);
export const validateConnectorActionListDTO: RuntimeDtoValidator<ConnectorActionDTO[]> = (value) =>
  arrayOf(value, "$", connectorAction);
export const validateConnectorResultDTO: RuntimeDtoValidator<ConnectorResultDTO> = (value) =>
  connectorResult(value, "$");
export const validateQuantumResultDTO: RuntimeDtoValidator<QuantumResultDTO> = (value) =>
  quantumResult(value, "$");
export const validateQuantumSettingsDTO: RuntimeDtoValidator<QuantumSettingsDTO> = (value) =>
  quantumSettings(value, "$");
