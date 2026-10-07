import type { RecoveryNotice } from './recoveryApi';
import type { Comment, CommentAnchor, CommentReply } from '../features/comments/commentsApi';
import type { DrafterPage, DrafterPagesDocument } from '../features/drafter/types';
import type {
  BillyChatResponse,
  ChatMessage,
  LogosInlineResponse,
} from '../features/littleboy/littleboyTypes';
import type {
  PsykeCreateResponse,
  PsykeDeleteResponse,
  PsykeEntry,
  PsykeSearchResponse,
} from '../features/psyke/types';
import type { AiSettings, AiTestResult } from '../features/settings/settingsApi';
import type { DocumentSummary } from '../features/whiteboard/documentsApi';
import type {
  InlineMark,
  WhiteboardBlock,
  WhiteboardDocument,
} from '../features/whiteboard/types';
import type { WritingMode, WritingModesResponse } from '../features/writingModes/types';

type JsonRecord = Record<string, unknown>;

export type RuntimeDtoValidator<T> = (value: unknown) => T;

function valueKind(value: unknown): string {
  if (value === null) return 'null';
  if (Array.isArray(value)) return 'array';
  if (typeof value === 'number' && !Number.isFinite(value)) return 'non-finite number';
  return typeof value;
}

export class RuntimeDtoValidationError extends Error {
  constructor(
    readonly valuePath: string,
    readonly expected: string,
    value: unknown,
  ) {
    super(`${valuePath} must be ${expected}; received ${valueKind(value)}`);
    this.name = 'RuntimeDtoValidationError';
  }
}

function fail(path: string, expected: string, value: unknown): never {
  throw new RuntimeDtoValidationError(path, expected, value);
}

function fieldPath(path: string, field: string): string {
  return path === '$' ? `$.${field}` : `${path}.${field}`;
}

function record(value: unknown, path: string): JsonRecord {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return fail(path, 'an object', value);
  }
  return value as JsonRecord;
}

function requireField(value: JsonRecord, key: string, path: string): unknown {
  if (!Object.prototype.hasOwnProperty.call(value, key)) {
    return fail(fieldPath(path, key), 'present', undefined);
  }
  return value[key];
}

function stringValue(value: unknown, path: string): string {
  return typeof value === 'string' ? value : fail(path, 'a string', value);
}

function nonEmptyString(value: unknown, path: string): string {
  const result = stringValue(value, path);
  return result.length > 0 ? result : fail(path, 'a non-empty string', value);
}

function booleanValue(value: unknown, path: string): boolean {
  return typeof value === 'boolean' ? value : fail(path, 'a boolean', value);
}

function integerValue(value: unknown, path: string): number {
  return typeof value === 'number' && Number.isSafeInteger(value)
    ? value
    : fail(path, 'a safe integer', value);
}

function nonNegativeInteger(value: unknown, path: string): number {
  const result = integerValue(value, path);
  return result >= 0 ? result : fail(path, 'a non-negative safe integer', value);
}

function positiveInteger(value: unknown, path: string): number {
  const result = integerValue(value, path);
  return result > 0 ? result : fail(path, 'a positive safe integer', value);
}

function arrayOf<T>(
  value: unknown,
  path: string,
  validate: (item: unknown, itemPath: string) => T,
): T[] {
  if (!Array.isArray(value)) return fail(path, 'an array', value);
  return value.map((item, index) => validate(item, `${path}[${index}]`));
}

function optional<T>(
  value: unknown,
  path: string,
  validate: (item: unknown, itemPath: string) => T,
): T | undefined {
  return value === undefined ? undefined : validate(value, path);
}

function nullable<T>(
  value: unknown,
  path: string,
  validate: (item: unknown, itemPath: string) => T,
): T | null {
  return value === null ? null : validate(value, path);
}

function optionalNullable<T>(
  value: unknown,
  path: string,
  validate: (item: unknown, itemPath: string) => T,
): T | null | undefined {
  return value === undefined ? undefined : nullable(value, path, validate);
}

function literal<T extends string>(value: unknown, path: string, allowed: readonly T[]): T {
  return typeof value === 'string' && (allowed as readonly string[]).includes(value)
    ? value as T
    : fail(path, allowed.map((item) => JSON.stringify(item)).join(' or '), value);
}

const REVISION_RE = /^[a-f0-9]{32}$/;
const INCARNATION_RE = /^[a-f0-9]{32}$/;

function revisionValue(value: unknown, path: string): string {
  return typeof value === 'string' && REVISION_RE.test(value)
    ? value
    : fail(path, 'a 32-character lowercase hexadecimal revision', value);
}

function incarnationValue(value: unknown, path: string): string {
  return typeof value === 'string' && INCARNATION_RE.test(value)
    ? value
    : fail(path, 'a 32-character lowercase hexadecimal incarnation', value);
}

function inlineMark(value: unknown, path: string, textLength: number): InlineMark {
  const dto = record(value, path);
  const type = literal(requireField(dto, 'type', path), fieldPath(path, 'type'), ['bold', 'italic']);
  const from = nonNegativeInteger(requireField(dto, 'from', path), fieldPath(path, 'from'));
  const to = nonNegativeInteger(requireField(dto, 'to', path), fieldPath(path, 'to'));
  if (to <= from || to > textLength) {
    fail(path, `an inline range within its ${textLength}-character block`, value);
  }
  return { type, from, to };
}

function whiteboardBlock(value: unknown, path: string): WhiteboardBlock {
  const dto = record(value, path);
  const id = nonEmptyString(requireField(dto, 'id', path), fieldPath(path, 'id'));
  const type = nonEmptyString(requireField(dto, 'type', path), fieldPath(path, 'type'));
  const text = stringValue(requireField(dto, 'text', path), fieldPath(path, 'text'));
  optionalNullable(dto.level, fieldPath(path, 'level'), integerValue);
  optionalNullable(dto.sp, fieldPath(path, 'sp'), stringValue);
  if (dto.marks !== undefined && dto.marks !== null) {
    arrayOf(dto.marks, fieldPath(path, 'marks'), (item, itemPath) =>
      inlineMark(item, itemPath, text.length));
  }
  return value as WhiteboardBlock;
}

function whiteboardBlocks(value: unknown, path: string): WhiteboardBlock[] {
  const blocks = arrayOf(value, path, whiteboardBlock);
  const ids = new Set<string>();
  blocks.forEach((block, index) => {
    if (ids.has(block.id)) fail(`${path}[${index}].id`, 'unique within the document', block.id);
    ids.add(block.id);
  });
  return blocks;
}

function whiteboardDocument(value: unknown, path: string): WhiteboardDocument {
  const dto = record(value, path);
  nonEmptyString(requireField(dto, 'id', path), fieldPath(path, 'id'));
  incarnationValue(requireField(dto, 'incarnation', path), fieldPath(path, 'incarnation'));
  revisionValue(requireField(dto, 'revision', path), fieldPath(path, 'revision'));
  stringValue(requireField(dto, 'title', path), fieldPath(path, 'title'));
  nonEmptyString(requireField(dto, 'mode', path), fieldPath(path, 'mode'));
  whiteboardBlocks(requireField(dto, 'blocks', path), fieldPath(path, 'blocks'));
  record(requireField(dto, 'settings', path), fieldPath(path, 'settings'));
  stringValue(requireField(dto, 'updated_at', path), fieldPath(path, 'updated_at'));
  optional(dto.viewRevision, fieldPath(path, 'viewRevision'), nonNegativeInteger);
  return value as WhiteboardDocument;
}

function documentSummary(value: unknown, path: string): DocumentSummary {
  const dto = record(value, path);
  nonEmptyString(requireField(dto, 'id', path), fieldPath(path, 'id'));
  incarnationValue(requireField(dto, 'incarnation', path), fieldPath(path, 'incarnation'));
  revisionValue(requireField(dto, 'revision', path), fieldPath(path, 'revision'));
  stringValue(requireField(dto, 'title', path), fieldPath(path, 'title'));
  nonEmptyString(requireField(dto, 'mode', path), fieldPath(path, 'mode'));
  stringValue(requireField(dto, 'updated_at', path), fieldPath(path, 'updated_at'));
  return value as DocumentSummary;
}

export interface DocumentListResponse {
  documents: DocumentSummary[];
}

export interface DocumentCreateResponse {
  ok: true;
  document: WhiteboardDocument;
}

export interface DocumentExistsResponse {
  exists: boolean;
}

export interface DocumentDeleteResponse {
  ok: true;
  deleted: string;
  cleanup_pending: boolean;
}

export const validateWhiteboardDocument: RuntimeDtoValidator<WhiteboardDocument> = (value) =>
  whiteboardDocument(value, '$');

export const validateDocumentListResponse: RuntimeDtoValidator<DocumentListResponse> = (value) => {
  const dto = record(value, '$');
  arrayOf(requireField(dto, 'documents', '$'), '$.documents', documentSummary);
  return value as DocumentListResponse;
};

export const validateDocumentCreateResponse: RuntimeDtoValidator<DocumentCreateResponse> = (value) => {
  const dto = record(value, '$');
  if (requireField(dto, 'ok', '$') !== true) fail('$.ok', 'true', dto.ok);
  whiteboardDocument(requireField(dto, 'document', '$'), '$.document');
  return value as DocumentCreateResponse;
};

export const validateDocumentExistsResponse: RuntimeDtoValidator<DocumentExistsResponse> = (value) => {
  const dto = record(value, '$');
  booleanValue(requireField(dto, 'exists', '$'), '$.exists');
  return value as DocumentExistsResponse;
};

export const validateDocumentDeleteResponse: RuntimeDtoValidator<DocumentDeleteResponse> = (value) => {
  const dto = record(value, '$');
  if (requireField(dto, 'ok', '$') !== true) fail('$.ok', 'true', dto.ok);
  nonEmptyString(requireField(dto, 'deleted', '$'), '$.deleted');
  booleanValue(requireField(dto, 'cleanup_pending', '$'), '$.cleanup_pending');
  return value as DocumentDeleteResponse;
};

export interface ResourceRevisionEnvelope {
  revision: string;
}

export const validateResourceRevisionEnvelope: RuntimeDtoValidator<ResourceRevisionEnvelope> = (value) => {
  const dto = record(value, '$');
  revisionValue(requireField(dto, 'revision', '$'), '$.revision');
  return value as ResourceRevisionEnvelope;
};

function drafterPage(value: unknown, path: string, fallbackNow: string): DrafterPage {
  const dto = record(value, path);
  const id = nonEmptyString(requireField(dto, 'id', path), fieldPath(path, 'id'));
  const title = nonEmptyString(requireField(dto, 'title', path), fieldPath(path, 'title'));
  const blocks = whiteboardBlocks(requireField(dto, 'blocks', path), fieldPath(path, 'blocks'));
  // Released pre-Drafter-recovery snapshots could omit timestamps. Preserve the
  // existing one-time renderer fallback, but never coerce malformed core fields.
  const createdAt = dto.created_at === undefined
    ? fallbackNow
    : stringValue(dto.created_at, fieldPath(path, 'created_at'));
  const updatedAt = dto.updated_at === undefined
    ? fallbackNow
    : stringValue(dto.updated_at, fieldPath(path, 'updated_at'));
  return { ...dto, id, title, blocks, created_at: createdAt, updated_at: updatedAt } as DrafterPage;
}

export const validateDrafterPagesDocument: RuntimeDtoValidator<DrafterPagesDocument> = (value) => {
  const dto = record(value, '$');
  const now = new Date().toISOString();
  const pages = arrayOf(requireField(dto, 'pages', '$'), '$.pages', (item, path) =>
    drafterPage(item, path, now));
  const ids = new Set<string>();
  pages.forEach((page, index) => {
    if (ids.has(page.id)) fail(`$.pages[${index}].id`, 'unique within the Drafter collection', page.id);
    ids.add(page.id);
  });
  const revision = revisionValue(requireField(dto, 'revision', '$'), '$.revision');
  return { pages, revision };
};

export interface OutlineItemsResponse {
  items: unknown[];
  revision: string;
}

export const validateOutlineItemsResponse: RuntimeDtoValidator<OutlineItemsResponse> = (value) => {
  const dto = record(value, '$');
  const items = requireField(dto, 'items', '$');
  if (!Array.isArray(items)) fail('$.items', 'an array', items);
  const revision = revisionValue(requireField(dto, 'revision', '$'), '$.revision');
  return { items, revision };
};

function commentAnchor(value: unknown, path: string): CommentAnchor {
  const dto = record(value, path);
  const surface = dto.surface === undefined
    ? 'manuscript'
    : literal(dto.surface, fieldPath(path, 'surface'), ['manuscript', 'drafter']);
  const drafterPageId = optionalNullable(
    dto.drafter_page_id,
    fieldPath(path, 'drafter_page_id'),
    nonEmptyString,
  );
  if (surface === 'drafter' && !drafterPageId) {
    fail(fieldPath(path, 'drafter_page_id'), 'a Drafter page id', dto.drafter_page_id);
  }
  if (surface === 'manuscript' && drafterPageId != null) {
    fail(fieldPath(path, 'drafter_page_id'), 'null or absent for a manuscript comment', drafterPageId);
  }
  const blockIndex = nonNegativeInteger(
    requireField(dto, 'block_index', path),
    fieldPath(path, 'block_index'),
  );
  const fromOffset = nonNegativeInteger(
    requireField(dto, 'from_offset', path),
    fieldPath(path, 'from_offset'),
  );
  const toOffset = nonNegativeInteger(
    requireField(dto, 'to_offset', path),
    fieldPath(path, 'to_offset'),
  );
  const endBlockIndex = optionalNullable(
    dto.end_block_index,
    fieldPath(path, 'end_block_index'),
    nonNegativeInteger,
  );
  if ((endBlockIndex == null || endBlockIndex === blockIndex) && toOffset < fromOffset) {
    fail(fieldPath(path, 'to_offset'), 'at least from_offset for a single-block anchor', toOffset);
  }
  optionalNullable(dto.block_id, fieldPath(path, 'block_id'), nonEmptyString);
  optionalNullable(dto.end_block_id, fieldPath(path, 'end_block_id'), nonEmptyString);
  optional(dto.prefix, fieldPath(path, 'prefix'), stringValue);
  optional(dto.suffix, fieldPath(path, 'suffix'), stringValue);
  return value as CommentAnchor;
}

function commentReply(value: unknown, path: string): CommentReply {
  const dto = record(value, path);
  nonEmptyString(requireField(dto, 'id', path), fieldPath(path, 'id'));
  stringValue(requireField(dto, 'body', path), fieldPath(path, 'body'));
  nonEmptyString(requireField(dto, 'author', path), fieldPath(path, 'author'));
  nonEmptyString(requireField(dto, 'created_at', path), fieldPath(path, 'created_at'));
  return value as CommentReply;
}

function comment(value: unknown, path: string): Comment {
  const dto = record(value, path);
  nonEmptyString(requireField(dto, 'id', path), fieldPath(path, 'id'));
  commentAnchor(requireField(dto, 'anchor', path), fieldPath(path, 'anchor'));
  stringValue(requireField(dto, 'quote', path), fieldPath(path, 'quote'));
  stringValue(requireField(dto, 'body', path), fieldPath(path, 'body'));
  booleanValue(requireField(dto, 'resolved', path), fieldPath(path, 'resolved'));
  arrayOf(requireField(dto, 'replies', path), fieldPath(path, 'replies'), commentReply);
  nonEmptyString(requireField(dto, 'created_at', path), fieldPath(path, 'created_at'));
  nonEmptyString(requireField(dto, 'updated_at', path), fieldPath(path, 'updated_at'));
  return value as Comment;
}

export interface CommentsResponse {
  comments: Comment[];
  revision: string;
}

export const validateComment: RuntimeDtoValidator<Comment> = (value) => comment(value, '$');

/** Validate a comment mutation response and bind it to the requested thread. */
export function validateCommentMutationResponse(
  value: unknown,
  expectedCommentId: string,
): Comment {
  const result = validateComment(value);
  if (result.id !== expectedCommentId) {
    fail('$.id', `the requested comment id "${expectedCommentId}"`, result.id);
  }
  return result;
}

export const validateCommentsResponse: RuntimeDtoValidator<CommentsResponse> = (value) => {
  const dto = record(value, '$');
  arrayOf(requireField(dto, 'comments', '$'), '$.comments', comment);
  revisionValue(requireField(dto, 'revision', '$'), '$.revision');
  return value as CommentsResponse;
};

export interface CommentDeleteResponse {
  ok: true;
  deleted: string;
}

export const validateCommentDeleteResponse: RuntimeDtoValidator<CommentDeleteResponse> = (value) => {
  const dto = record(value, '$');
  if (requireField(dto, 'ok', '$') !== true) fail('$.ok', 'true', dto.ok);
  nonEmptyString(requireField(dto, 'deleted', '$'), '$.deleted');
  return value as CommentDeleteResponse;
};

function chatMessage(value: unknown, path: string): ChatMessage {
  const dto = record(value, path);
  literal(requireField(dto, 'role', path), fieldPath(path, 'role'), ['user', 'assistant', 'system']);
  stringValue(requireField(dto, 'content', path), fieldPath(path, 'content'));
  return value as ChatMessage;
}

export const validateBillyChatResponse: RuntimeDtoValidator<BillyChatResponse> = (value) => {
  const dto = record(value, '$');
  booleanValue(requireField(dto, 'ok', '$'), '$.ok');
  nonEmptyString(requireField(dto, 'conversation_id', '$'), '$.conversation_id');
  chatMessage(requireField(dto, 'message', '$'), '$.message');
  nonEmptyString(requireField(dto, 'provider', '$'), '$.provider');
  optionalNullable(dto.note, '$.note', stringValue);
  return value as BillyChatResponse;
};

export const validateLogosInlineResponse: RuntimeDtoValidator<LogosInlineResponse> = (value) => {
  const dto = record(value, '$');
  booleanValue(requireField(dto, 'ok', '$'), '$.ok');
  nonEmptyString(requireField(dto, 'action', '$'), '$.action');
  stringValue(requireField(dto, 'result', '$'), '$.result');
  optionalNullable(dto.suggested_replacement, '$.suggested_replacement', stringValue);
  nonEmptyString(requireField(dto, 'provider', '$'), '$.provider');
  optionalNullable(dto.note, '$.note', stringValue);
  return value as LogosInlineResponse;
};

function psykeEntry(value: unknown, path: string): PsykeEntry {
  const dto = record(value, path);
  nonEmptyString(requireField(dto, 'id', path), fieldPath(path, 'id'));
  stringValue(requireField(dto, 'name', path), fieldPath(path, 'name'));
  nonEmptyString(requireField(dto, 'entry_type', path), fieldPath(path, 'entry_type'));
  arrayOf(requireField(dto, 'aliases', path), fieldPath(path, 'aliases'), stringValue);
  optional(dto.description, fieldPath(path, 'description'), stringValue);
  optional(dto.notes, fieldPath(path, 'notes'), stringValue);
  optionalNullable(dto.created_at, fieldPath(path, 'created_at'), stringValue);
  optionalNullable(dto.updated_at, fieldPath(path, 'updated_at'), stringValue);
  return value as PsykeEntry;
}

export const validatePsykeSearchResponse: RuntimeDtoValidator<PsykeSearchResponse> = (value) => {
  const dto = record(value, '$');
  stringValue(requireField(dto, 'query', '$'), '$.query');
  arrayOf(requireField(dto, 'results', '$'), '$.results', psykeEntry);
  revisionValue(requireField(dto, 'revision', '$'), '$.revision');
  return value as PsykeSearchResponse;
};

export const validatePsykeCreateResponse: RuntimeDtoValidator<PsykeCreateResponse> = (value) => {
  const dto = record(value, '$');
  if (requireField(dto, 'ok', '$') !== true) fail('$.ok', 'true', dto.ok);
  psykeEntry(requireField(dto, 'element', '$'), '$.element');
  revisionValue(requireField(dto, 'revision', '$'), '$.revision');
  return value as PsykeCreateResponse;
};

/** Validate an update response and bind it to the requested PSYKE element. */
export function validatePsykeElementMutationResponse(
  value: unknown,
  expectedElementId: string,
): PsykeCreateResponse {
  const result = validatePsykeCreateResponse(value);
  if (result.element.id !== expectedElementId) {
    fail('$.element.id', `the requested PSYKE element id "${expectedElementId}"`, result.element.id);
  }
  return result;
}

export const validatePsykeDeleteResponse: RuntimeDtoValidator<PsykeDeleteResponse> = (value) => {
  const dto = record(value, '$');
  if (requireField(dto, 'ok', '$') !== true) fail('$.ok', 'true', dto.ok);
  positiveInteger(requireField(dto, 'deleted', '$'), '$.deleted');
  return value as PsykeDeleteResponse;
};

/** Validate a delete acknowledgement and bind it to the requested PSYKE element. */
export function validatePsykeDeleteAcknowledgement(
  value: unknown,
  expectedElementId: string,
): PsykeDeleteResponse {
  const result = validatePsykeDeleteResponse(value);
  if (String(result.deleted) !== expectedElementId) {
    fail('$.deleted', `the requested PSYKE element id "${expectedElementId}"`, result.deleted);
  }
  return result;
}

export const validateAiSettingsResponse: RuntimeDtoValidator<AiSettings> = (value) => {
  const dto = record(value, '$');
  stringValue(requireField(dto, 'provider', '$'), '$.provider');
  stringValue(requireField(dto, 'model', '$'), '$.model');
  stringValue(requireField(dto, 'base_url', '$'), '$.base_url');
  nonNegativeInteger(requireField(dto, 'timeout', '$'), '$.timeout');
  if (dto.api_key !== undefined && dto.api_key !== null) {
    fail('$.api_key', 'null or absent because API keys are write-only', dto.api_key);
  }
  return value as AiSettings;
};

export const validateAiTestResult: RuntimeDtoValidator<AiTestResult> = (value) => {
  const dto = record(value, '$');
  booleanValue(requireField(dto, 'ok', '$'), '$.ok');
  nonEmptyString(requireField(dto, 'provider', '$'), '$.provider');
  optionalNullable(dto.reply, '$.reply', stringValue);
  optionalNullable(dto.error, '$.error', stringValue);
  return value as AiTestResult;
};

function writingMode(value: unknown, path: string): WritingMode {
  const dto = record(value, path);
  nonEmptyString(requireField(dto, 'id', path), fieldPath(path, 'id'));
  nonEmptyString(requireField(dto, 'label', path), fieldPath(path, 'label'));
  arrayOf(requireField(dto, 'structural_units', path), fieldPath(path, 'structural_units'), stringValue);
  nonEmptyString(
    requireField(dto, 'default_writing_format', path),
    fieldPath(path, 'default_writing_format'),
  );
  stringValue(requireField(dto, 'medium_constraints', path), fieldPath(path, 'medium_constraints'));
  return value as WritingMode;
}

export const validateWritingModesResponse: RuntimeDtoValidator<WritingModesResponse> = (value) => {
  const dto = record(value, '$');
  const modes = arrayOf(requireField(dto, 'modes', '$'), '$.modes', writingMode);
  const defaultMode = nonEmptyString(requireField(dto, 'default_mode', '$'), '$.default_mode');
  if (!modes.some((mode) => mode.id === defaultMode)) {
    fail('$.default_mode', 'the id of a returned writing mode', defaultMode);
  }
  return value as WritingModesResponse;
};

function recoveryNotice(value: unknown, path: string): RecoveryNotice {
  const dto = record(value, path);
  for (const key of [
    'id',
    'label',
    'message',
    'recovered_from',
    'quarantined_path',
    'recovered_at',
  ] as const) {
    nonEmptyString(requireField(dto, key, path), fieldPath(path, key));
  }
  return value as RecoveryNotice;
}

export interface RecoveryNoticesResponse {
  notices: RecoveryNotice[];
}

export const validateRecoveryNoticesResponse: RuntimeDtoValidator<RecoveryNoticesResponse> = (value) => {
  const dto = record(value, '$');
  arrayOf(requireField(dto, 'notices', '$'), '$.notices', recoveryNotice);
  return value as RecoveryNoticesResponse;
};

export interface BackendHealthResponse {
  status: 'ok';
  service: string;
  instance_nonce: string;
  project_id: number;
  api_version: string | null;
  core_version: string | null;
  core: JsonRecord;
}

export const validateBackendHealthResponse: RuntimeDtoValidator<BackendHealthResponse> = (value) => {
  const dto = record(value, '$');
  if (requireField(dto, 'status', '$') !== 'ok') fail('$.status', '"ok"', dto.status);
  nonEmptyString(requireField(dto, 'service', '$'), '$.service');
  stringValue(requireField(dto, 'instance_nonce', '$'), '$.instance_nonce');
  positiveInteger(requireField(dto, 'project_id', '$'), '$.project_id');
  nullable(requireField(dto, 'api_version', '$'), '$.api_version', stringValue);
  nullable(requireField(dto, 'core_version', '$'), '$.core_version', stringValue);
  record(requireField(dto, 'core', '$'), '$.core');
  return value as BackendHealthResponse;
};

export interface ProjectBundleSnapshot {
  format: 'logosforge-project-bundle';
  version: '1.0';
  exportedAt: string;
  source: { app: 'logosforge-whiteboard' };
  project: {
    id: string;
    title: string;
    mode: string;
    settings: JsonRecord;
    manuscript: { blocks: WhiteboardBlock[] };
    outline: JsonRecord[];
    comments: Comment[];
    drafter: { pages: DrafterPage[] };
    psyke: {
      elements: PsykeEntry[];
      relations: JsonRecord[];
      progressions: JsonRecord[];
    };
  };
}

function psykeRelation(value: unknown, path: string): JsonRecord {
  const dto = record(value, path);
  nonEmptyString(requireField(dto, 'id', path), fieldPath(path, 'id'));
  positiveInteger(requireField(dto, 'source_id', path), fieldPath(path, 'source_id'));
  positiveInteger(requireField(dto, 'target_id', path), fieldPath(path, 'target_id'));
  stringValue(requireField(dto, 'source', path), fieldPath(path, 'source'));
  stringValue(requireField(dto, 'target', path), fieldPath(path, 'target'));
  stringValue(requireField(dto, 'relation_type', path), fieldPath(path, 'relation_type'));
  return dto;
}

function psykeProgression(value: unknown, path: string): JsonRecord {
  const dto = record(value, path);
  positiveInteger(requireField(dto, 'id', path), fieldPath(path, 'id'));
  positiveInteger(requireField(dto, 'entry_id', path), fieldPath(path, 'entry_id'));
  stringValue(requireField(dto, 'text', path), fieldPath(path, 'text'));
  nullable(requireField(dto, 'scene_id', path), fieldPath(path, 'scene_id'), positiveInteger);
  stringValue(requireField(dto, 'scene_title', path), fieldPath(path, 'scene_title'));
  nonNegativeInteger(requireField(dto, 'sort_order', path), fieldPath(path, 'sort_order'));
  return dto;
}

export const validateProjectBundleSnapshot: RuntimeDtoValidator<ProjectBundleSnapshot> = (value) => {
  const root = record(value, '$');
  if (requireField(root, 'format', '$') !== 'logosforge-project-bundle') {
    fail('$.format', '"logosforge-project-bundle"', root.format);
  }
  if (requireField(root, 'version', '$') !== '1.0') fail('$.version', '"1.0"', root.version);
  nonEmptyString(requireField(root, 'exportedAt', '$'), '$.exportedAt');
  const source = record(requireField(root, 'source', '$'), '$.source');
  if (requireField(source, 'app', '$.source') !== 'logosforge-whiteboard') {
    fail('$.source.app', '"logosforge-whiteboard"', source.app);
  }

  const project = record(requireField(root, 'project', '$'), '$.project');
  nonEmptyString(requireField(project, 'id', '$.project'), '$.project.id');
  stringValue(requireField(project, 'title', '$.project'), '$.project.title');
  nonEmptyString(requireField(project, 'mode', '$.project'), '$.project.mode');
  record(requireField(project, 'settings', '$.project'), '$.project.settings');

  const manuscript = record(requireField(project, 'manuscript', '$.project'), '$.project.manuscript');
  whiteboardBlocks(
    requireField(manuscript, 'blocks', '$.project.manuscript'),
    '$.project.manuscript.blocks',
  );
  arrayOf(requireField(project, 'outline', '$.project'), '$.project.outline', record);
  arrayOf(requireField(project, 'comments', '$.project'), '$.project.comments', comment);

  const drafter = record(requireField(project, 'drafter', '$.project'), '$.project.drafter');
  arrayOf(requireField(drafter, 'pages', '$.project.drafter'), '$.project.drafter.pages',
    (item, path) => {
      const page = record(item, path);
      nonEmptyString(requireField(page, 'created_at', path), fieldPath(path, 'created_at'));
      nonEmptyString(requireField(page, 'updated_at', path), fieldPath(path, 'updated_at'));
      return drafterPage(item, path, '');
    });

  const psyke = record(requireField(project, 'psyke', '$.project'), '$.project.psyke');
  arrayOf(requireField(psyke, 'elements', '$.project.psyke'), '$.project.psyke.elements', psykeEntry);
  arrayOf(requireField(psyke, 'relations', '$.project.psyke'), '$.project.psyke.relations', psykeRelation);
  arrayOf(
    requireField(psyke, 'progressions', '$.project.psyke'),
    '$.project.psyke.progressions',
    psykeProgression,
  );
  return value as ProjectBundleSnapshot;
};

/** Validate a project export and bind it to the explicitly requested document. */
export function validateProjectBundleForDocument(
  value: unknown,
  expectedDocumentId: string,
): ProjectBundleSnapshot {
  const result = validateProjectBundleSnapshot(value);
  if (result.project.id !== expectedDocumentId) {
    fail('$.project.id', `the requested document id "${expectedDocumentId}"`, result.project.id);
  }
  return result;
}
