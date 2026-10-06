import type {
  AiBehaviorDTO,
  AssistantResponseDTO,
  AssistantSettingsDTO,
  ConnectorActionDTO,
  ConnectorResultDTO,
  DeleteResultDTO,
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
  TimelineCommandResultDTO,
  TimelineEventDTO,
  TimelineLaneDTO,
  TimelineOffTimelineSceneDTO,
  TimelineOrderMode,
  TimelineSnapshotDTO,
  CanvasPlotCommandDTO,
  CanvasPlotCommandResultDTO,
  CanvasPlotFrameDTO,
  CanvasPlotLinkDTO,
  CanvasPlotNodeDTO,
  CanvasPlotSnapshotDTO,
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
  if (replayed && changed) {
    fail(fieldPath(path, "changed"), "false when replayed is true", changed);
  }
  return value as TimelineCommandResultDTO;
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
  return result;
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
