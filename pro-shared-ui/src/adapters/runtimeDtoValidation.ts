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
  QuantumSettingsDTO,
  QuantumResultDTO,
  RelationProposalDTO,
  SceneDTO,
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

function settings(value: unknown, path: string): SettingsDTO {
  const dto = record(value, path);
  record(requireField(dto, "settings", path), fieldPath(path, "settings"));
  return value as SettingsDTO;
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
export const validateSettingsDTO: RuntimeDtoValidator<SettingsDTO> = (value) => settings(value, "$");
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
