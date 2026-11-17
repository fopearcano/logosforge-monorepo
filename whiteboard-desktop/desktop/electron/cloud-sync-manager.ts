import { createHash, randomUUID } from 'node:crypto';
import { promises as fs } from 'node:fs';
import * as path from 'node:path';

import { atomicWriteTextFile } from './atomic-file-save';
import { MAX_RECOVERY_IMPORT_FILE_BYTES, readBoundedImportTextFile } from './import-file-limit';

export const CLOUD_SYNC_FOLDER_NAME = 'LogosForge Whiteboard';
export const CLOUD_SYNC_SNAPSHOT_FORMAT = 'logosforge-whiteboard-cloud-snapshot';
export const CLOUD_SYNC_SNAPSHOT_VERSION = '1.0';
export const MAX_CLOUD_SYNC_SNAPSHOT_BYTES = MAX_RECOVERY_IMPORT_FILE_BYTES;

const CONFIG_FORMAT = 'logosforge-whiteboard-cloud-sync-config';
const CONFIG_VERSION = 1;
const CONFIG_FILE_NAME = 'cloud-sync-config.json';
const OUTBOX_FOLDER_NAME = 'cloud-sync-outbox';
const MAX_CONFIG_BYTES = 1024 * 1024;
const MAX_SNAPSHOT_FILES = 4096;
const MAX_SNAPSHOT_PARENTS = 32;
const MAX_PENDING_ACTION_RECEIPTS = 128;
const MAX_RECOVERED_REMOTE_PROJECTS = 256;
const MAX_RECOVERED_HEADS_PER_PROJECT = 64;
const DEFAULT_POLL_INTERVAL_MS = 15_000;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const DIGEST_PATTERN = /^[0-9a-f]{64}$/;
const CLOUD_SYNC_ACTION_KINDS = new Set<CloudSyncActionKind>([
  'pull',
  'keep-both',
  'use-cloud',
  'discover',
  'remote-recovery',
]);
const CLOUD_SYNC_ACTION_PHASES = new Set<CloudSyncActionPhase>([
  'prepared',
  'local-forked',
  'restored',
  'binding-installed',
]);
const CLOUD_SYNC_ACTION_PHASE_ORDER: Record<CloudSyncActionPhase, number> = {
  prepared: 0,
  'local-forked': 1,
  restored: 2,
  'binding-installed': 3,
};

type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };

export interface CloudSyncBinding {
  localDocumentId: string;
  localIncarnation: string;
  cloudProjectId: string;
  lastSnapshotId: string | null;
  lastContentDigest: string | null;
}

export interface CloudSyncRetiredLocalDocument {
  localDocumentId: string;
  localIncarnation: string;
  /**
   * Canonical complete-project digest observed immediately before ownership
   * moved away from this document. A null value is a legacy tombstone and is
   * deliberately not safe for automatic deletion.
   */
  expectedContentDigest: string | null;
}

export type CloudSyncActionKind = 'pull' | 'keep-both' | 'use-cloud' | 'discover' | 'remote-recovery';
export type CloudSyncActionPhase = 'prepared' | 'local-forked' | 'restored' | 'binding-installed';

export interface CloudSyncActionReceipt {
  actionId: string;
  kind: CloudSyncActionKind;
  phase: CloudSyncActionPhase;
  sourceLocalDocumentId: string;
  sourceLocalIncarnation: string;
  originalCloudProjectId: string;
  intendedCloudProjectId: string | null;
  snapshotId: string;
  snapshotContentDigest: string;
  parentSnapshotIds: string[];
  expectedSourceDigest: string;
  restoredLocalDocumentId: string | null;
  restoredLocalIncarnation: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface CloudSyncRecoveredRemoteHeads {
  cloudProjectId: string;
  snapshotIds: string[];
}

export interface CloudSyncSnapshotEnvelope {
  format: typeof CLOUD_SYNC_SNAPSHOT_FORMAT;
  version: typeof CLOUD_SYNC_SNAPSHOT_VERSION;
  cloudProjectId: string;
  snapshotId: string;
  deviceId: string;
  parentSnapshotIds: string[];
  generation: number;
  createdAt: string;
  contentDigest: string;
  bundle: JsonValue;
}

export interface CloudSyncSnapshotMetadata {
  cloudProjectId: string;
  snapshotId: string;
  deviceId: string;
  parentSnapshotIds: string[];
  generation: number;
  createdAt: string;
  contentDigest: string;
  projectTitle: string;
  pendingDelivery: boolean;
}

export interface CloudSyncProjectInventory {
  cloudProjectId: string;
  projectTitle: string;
  snapshots: CloudSyncSnapshotMetadata[];
  heads: CloudSyncSnapshotMetadata[];
}

export interface CloudSyncInventory {
  projects: CloudSyncProjectInventory[];
  warnings: string[];
}

export interface CloudSyncState extends CloudSyncInventory {
  enabled: boolean;
  automatic: boolean;
  folderPath: string | null;
  folderAvailable: boolean;
  deviceId: string;
  bindings: CloudSyncBinding[];
  retiredLocalDocuments: CloudSyncRetiredLocalDocument[];
  actionReceipts: CloudSyncActionReceipt[];
  recoveredRemoteHeads: CloudSyncRecoveredRemoteHeads[];
  ignoredCloudProjectIds: string[];
  pendingDeliveries: number;
  syncing: boolean;
  lastSuccessfulSyncAt: string | null;
  lastError: string | null;
}

export interface CloudSyncPublishRequest {
  localDocumentId: string;
  localIncarnation: string;
  bundle: unknown;
  cloudProjectId?: string | null;
  parentSnapshotIds?: string[];
  createNewProject?: boolean;
  /** Caller-preallocated UUID makes a fork publish replay-safe across crashes. */
  newCloudProjectId?: string | null;
}

export interface CloudSyncPublishResult {
  created: boolean;
  delivered: boolean;
  binding: CloudSyncBinding;
  snapshot: CloudSyncSnapshotMetadata;
}

export interface CloudSyncSetBindingRequest extends CloudSyncBinding {}

export interface CloudSyncMoveBindingRequest {
  fromLocalDocumentId: string;
  fromLocalIncarnation: string;
  toLocalDocumentId: string;
  toLocalIncarnation: string;
  lastSnapshotId?: string | null;
  lastContentDigest?: string | null;
  expectedRetiredContentDigest?: string | null;
}

export interface CloudSyncSaveActionReceiptRequest {
  actionId: string;
  kind: CloudSyncActionKind;
  phase: CloudSyncActionPhase;
  sourceLocalDocumentId: string;
  sourceLocalIncarnation: string;
  originalCloudProjectId: string;
  intendedCloudProjectId?: string | null;
  snapshotId: string;
  snapshotContentDigest: string;
  parentSnapshotIds: string[];
  expectedSourceDigest: string;
  restoredLocalDocumentId?: string | null;
  restoredLocalIncarnation?: string | null;
}

export interface CloudSyncForgetBindingRequest {
  localDocumentId: string;
  localIncarnation: string;
  cloudProjectId?: string | null;
  ignoreRemote?: boolean;
}

export interface CloudSyncReadSnapshotRequest {
  cloudProjectId: string;
  snapshotId: string;
}

interface StoredCloudSyncConfig {
  format: typeof CONFIG_FORMAT;
  version: typeof CONFIG_VERSION;
  deviceId: string;
  folderPath: string | null;
  enabled: boolean;
  automatic: boolean;
  bindings: CloudSyncBinding[];
  retiredLocalDocuments: CloudSyncRetiredLocalDocument[];
  actionReceipts: CloudSyncActionReceipt[];
  recoveredRemoteHeads: CloudSyncRecoveredRemoteHeads[];
  ignoredCloudProjectIds: string[];
  lastSuccessfulSyncAt: string | null;
}

interface LocatedSnapshot {
  envelope: CloudSyncSnapshotEnvelope;
  metadata: CloudSyncSnapshotMetadata;
  serialized: string;
  source: 'cloud' | 'outbox';
}

export interface CloudSyncManagerOptions {
  pollIntervalMs?: number;
  now?: () => Date;
  createId?: () => string;
}

function errorMessage(error: unknown): string {
  return error instanceof Error && error.message.trim()
    ? error.message.trim()
    : 'Cloud folder sync could not complete.';
}

function isMissing(error: unknown): boolean {
  return !!error && typeof error === 'object' && 'code' in error
    && (error as NodeJS.ErrnoException).code === 'ENOENT';
}

function validateUuid(value: unknown, label: string): string {
  if (typeof value !== 'string' || !UUID_PATTERN.test(value)) {
    throw new Error(`${label} must be a UUID.`);
  }
  return value.toLowerCase();
}

function validateDigest(value: unknown, label: string): string {
  if (typeof value !== 'string' || !DIGEST_PATTERN.test(value)) {
    throw new Error(`${label} must be a SHA-256 digest.`);
  }
  return value;
}

function validateLocalIdentity(value: unknown, label: string): string {
  if (typeof value !== 'string' || !value.trim() || value.length > 32768 || /[\u0000-\u001f]/.test(value)) {
    throw new Error(`${label} is invalid.`);
  }
  return value;
}

function validateTimestamp(value: unknown, label: string): string {
  if (typeof value !== 'string' || !value.trim() || !Number.isFinite(Date.parse(value))) {
    throw new Error(`${label} must be an ISO timestamp.`);
  }
  return value;
}

function normalizeJson(value: unknown, label: string): JsonValue {
  let serialized: string;
  try {
    serialized = JSON.stringify(value);
  } catch {
    throw new Error(`${label} is not valid JSON.`);
  }
  if (serialized === undefined) throw new Error(`${label} is not valid JSON.`);
  if (Buffer.byteLength(serialized, 'utf8') > MAX_CLOUD_SYNC_SNAPSHOT_BYTES) {
    throw new Error(`${label} is larger than the 257 MiB safety limit.`);
  }
  return JSON.parse(serialized) as JsonValue;
}

function isRecord(value: JsonValue): value is { [key: string]: JsonValue } {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

function stableJsonValue(value: JsonValue): JsonValue {
  if (Array.isArray(value)) return value.map(stableJsonValue);
  if (!isRecord(value)) return value;
  const sorted: { [key: string]: JsonValue } = {};
  for (const key of Object.keys(value).sort()) sorted[key] = stableJsonValue(value[key]);
  return sorted;
}

function stableStringify(value: JsonValue): string {
  return JSON.stringify(stableJsonValue(value));
}

export function validateCloudSyncBundle(value: unknown): JsonValue {
  const bundle = normalizeJson(value, 'The project snapshot');
  if (!isRecord(bundle) || bundle.format !== 'logosforge-project-bundle' || bundle.version !== '1.0') {
    throw new Error('The project snapshot is not a supported LogosForge Whiteboard bundle.');
  }
  if (!isRecord(bundle.source) || bundle.source.app !== 'logosforge-whiteboard') {
    throw new Error('The project snapshot was not produced by LogosForge Whiteboard.');
  }
  if (!isRecord(bundle.project)) throw new Error('The project snapshot has no project payload.');
  if (typeof bundle.project.title !== 'string' || !bundle.project.title.trim()) {
    throw new Error('The project snapshot has no project title.');
  }
  return bundle;
}

/** Device-local ids and the export clock are transport metadata, not content. */
export function canonicalCloudSyncBundle(value: unknown): string {
  const canonical = normalizeJson(validateCloudSyncBundle(value), 'The project snapshot');
  if (!isRecord(canonical)) throw new Error('The project snapshot is invalid.');
  delete canonical.exportedAt;
  if (isRecord(canonical.project)) {
    delete canonical.project.id;
    canonicalizeCoreOwnedProjectIds(canonical.project);
  }
  return stableStringify(canonical);
}

/**
 * Core allocates fresh integer ids and timestamps during copy-on-write restore.
 * They are reference plumbing rather than story content. Canonicalize them by
 * stable exported order while preserving every relationship and meaningful
 * field, so the same project converges after moving between devices.
 */
function canonicalizeCoreOwnedProjectIds(project: { [key: string]: JsonValue }): void {
  if (!isRecord(project.psyke)) return;
  const psyke = project.psyke;
  const elements = Array.isArray(psyke.elements) ? psyke.elements : [];
  const entryIds = new Map<string, number>();
  elements.forEach((value, index) => {
    if (!isRecord(value)) return;
    entryIds.set(String(value.id), index + 1);
    value.id = String(index + 1);
    delete value.created_at;
    delete value.updated_at;
  });

  if (Array.isArray(psyke.relations)) {
    psyke.relations.forEach((value) => {
      if (!isRecord(value)) return;
      const source = entryIds.get(String(value.source_id));
      const target = entryIds.get(String(value.target_id));
      if (source !== undefined) value.source_id = source;
      if (target !== undefined) value.target_id = target;
      if (source !== undefined && target !== undefined) value.id = `${source}:${target}`;
    });
  }

  if (Array.isArray(psyke.progressions)) {
    psyke.progressions.forEach((value, index) => {
      if (!isRecord(value)) return;
      value.id = index + 1;
      const entryId = entryIds.get(String(value.entry_id));
      if (entryId !== undefined) value.entry_id = entryId;
    });
  }

  if (!Array.isArray(project.progression_tracks)) return;
  const trackIds = new Map<string, number>();
  project.progression_tracks.forEach((value, index) => {
    if (!isRecord(value)) return;
    trackIds.set(String(value.id), index + 1);
  });
  let nextBeatId = 1;
  project.progression_tracks.forEach((value, index) => {
    if (!isRecord(value)) return;
    const canonicalTrackId = index + 1;
    value.id = canonicalTrackId;
    for (const field of ['primary_psyke_entry_id', 'secondary_psyke_entry_id']) {
      if (value[field] === null || value[field] === undefined) continue;
      const canonicalEntryId = entryIds.get(String(value[field]));
      if (canonicalEntryId !== undefined) value[field] = canonicalEntryId;
    }
    if (!Array.isArray(value.beats)) return;
    value.beats.forEach((beat) => {
      if (!isRecord(beat)) return;
      beat.id = nextBeatId;
      nextBeatId += 1;
      const exportedTrackId = trackIds.get(String(beat.track_id));
      beat.track_id = exportedTrackId ?? canonicalTrackId;
    });
  });
}

export function cloudSyncContentDigest(value: unknown): string {
  return createHash('sha256').update(canonicalCloudSyncBundle(value), 'utf8').digest('hex');
}

function projectTitle(bundle: JsonValue): string {
  return isRecord(bundle) && isRecord(bundle.project) && typeof bundle.project.title === 'string'
    ? bundle.project.title
    : 'Untitled Project';
}

function snapshotMetadata(envelope: CloudSyncSnapshotEnvelope, pendingDelivery: boolean): CloudSyncSnapshotMetadata {
  return {
    cloudProjectId: envelope.cloudProjectId,
    snapshotId: envelope.snapshotId,
    deviceId: envelope.deviceId,
    parentSnapshotIds: [...envelope.parentSnapshotIds],
    generation: envelope.generation,
    createdAt: envelope.createdAt,
    contentDigest: envelope.contentDigest,
    projectTitle: projectTitle(envelope.bundle),
    pendingDelivery,
  };
}

export function validateCloudSyncSnapshot(value: unknown): CloudSyncSnapshotEnvelope {
  const raw = normalizeJson(value, 'The cloud snapshot');
  if (!isRecord(raw) || raw.format !== CLOUD_SYNC_SNAPSHOT_FORMAT || raw.version !== CLOUD_SYNC_SNAPSHOT_VERSION) {
    throw new Error('The file is not a supported Whiteboard cloud snapshot.');
  }
  const cloudProjectId = validateUuid(raw.cloudProjectId, 'Cloud project id');
  const snapshotId = validateUuid(raw.snapshotId, 'Snapshot id');
  const deviceId = validateUuid(raw.deviceId, 'Device id');
  if (!Array.isArray(raw.parentSnapshotIds) || raw.parentSnapshotIds.length > MAX_SNAPSHOT_PARENTS) {
    throw new Error('The cloud snapshot has an invalid parent list.');
  }
  const parentSnapshotIds = raw.parentSnapshotIds.map((item) => validateUuid(item, 'Parent snapshot id'));
  if (new Set(parentSnapshotIds).size !== parentSnapshotIds.length || parentSnapshotIds.includes(snapshotId)) {
    throw new Error('The cloud snapshot has an invalid parent graph.');
  }
  if (!Number.isSafeInteger(raw.generation) || (raw.generation as number) < 0) {
    throw new Error('The cloud snapshot has an invalid generation.');
  }
  const createdAt = validateTimestamp(raw.createdAt, 'Snapshot timestamp');
  const contentDigest = validateDigest(raw.contentDigest, 'Snapshot content digest');
  const bundle = validateCloudSyncBundle(raw.bundle);
  if (cloudSyncContentDigest(bundle) !== contentDigest) {
    throw new Error('The cloud snapshot content digest does not match its project data.');
  }
  return {
    format: CLOUD_SYNC_SNAPSHOT_FORMAT,
    version: CLOUD_SYNC_SNAPSHOT_VERSION,
    cloudProjectId,
    snapshotId,
    deviceId,
    parentSnapshotIds,
    generation: raw.generation as number,
    createdAt,
    contentDigest,
    bundle,
  };
}

function validateBinding(value: unknown): CloudSyncBinding {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Cloud project binding is invalid.');
  const raw = value as Record<string, unknown>;
  return {
    localDocumentId: validateLocalIdentity(raw.localDocumentId, 'Local document id'),
    localIncarnation: validateLocalIdentity(raw.localIncarnation, 'Local document incarnation'),
    cloudProjectId: validateUuid(raw.cloudProjectId, 'Cloud project id'),
    lastSnapshotId: raw.lastSnapshotId === null ? null : validateUuid(raw.lastSnapshotId, 'Last snapshot id'),
    lastContentDigest: raw.lastContentDigest === null ? null : validateDigest(raw.lastContentDigest, 'Last content digest'),
  };
}

function validateRetiredLocalDocument(value: unknown): CloudSyncRetiredLocalDocument {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Retired local document identity is invalid.');
  }
  const raw = value as Record<string, unknown>;
  return {
    localDocumentId: validateLocalIdentity(raw.localDocumentId, 'Retired local document id'),
    localIncarnation: validateLocalIdentity(raw.localIncarnation, 'Retired local document incarnation'),
    // Version-one configurations created before digest-guarded retirement did
    // not have this field. Keep those tombstones, but mark them unsafe for
    // unattended deletion instead of quarantining the whole configuration.
    expectedContentDigest: raw.expectedContentDigest == null
      ? null
      : validateDigest(raw.expectedContentDigest, 'Retired local document digest'),
  };
}

function validateActionKind(value: unknown): CloudSyncActionKind {
  if (typeof value !== 'string' || !CLOUD_SYNC_ACTION_KINDS.has(value as CloudSyncActionKind)) {
    throw new Error('Cloud sync action kind is invalid.');
  }
  return value as CloudSyncActionKind;
}

function validateActionPhase(value: unknown): CloudSyncActionPhase {
  if (typeof value !== 'string' || !CLOUD_SYNC_ACTION_PHASES.has(value as CloudSyncActionPhase)) {
    throw new Error('Cloud sync action phase is invalid.');
  }
  return value as CloudSyncActionPhase;
}

function validateNullableIdentityPair(
  documentIdValue: unknown,
  incarnationValue: unknown,
  label: string,
): { documentId: string | null; incarnation: string | null } {
  if (documentIdValue == null && incarnationValue == null) {
    return { documentId: null, incarnation: null };
  }
  if (documentIdValue == null || incarnationValue == null) {
    throw new Error(`${label} identity must be complete.`);
  }
  return {
    documentId: validateLocalIdentity(documentIdValue, `${label} document id`),
    incarnation: validateLocalIdentity(incarnationValue, `${label} document incarnation`),
  };
}

function validateActionReceipt(value: unknown): CloudSyncActionReceipt {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Cloud sync action receipt is invalid.');
  }
  const raw = value as Record<string, unknown>;
  const restored = validateNullableIdentityPair(
    raw.restoredLocalDocumentId,
    raw.restoredLocalIncarnation,
    'Restored local',
  );
  const parentSnapshotIds = Array.isArray(raw.parentSnapshotIds)
    ? raw.parentSnapshotIds.map((item) => validateUuid(item, 'Action parent snapshot id'))
    : (() => { throw new Error('Cloud sync action parent snapshots are invalid.'); })();
  if (parentSnapshotIds.length > MAX_SNAPSHOT_PARENTS
    || new Set(parentSnapshotIds).size !== parentSnapshotIds.length) {
    throw new Error('Cloud sync action parent snapshots are invalid.');
  }
  const actionId = validateLocalIdentity(raw.actionId, 'Cloud sync action id');
  if (actionId.length > 512) throw new Error('Cloud sync action id is too long.');
  const receipt: CloudSyncActionReceipt = {
    actionId,
    kind: validateActionKind(raw.kind),
    phase: validateActionPhase(raw.phase),
    sourceLocalDocumentId: validateLocalIdentity(raw.sourceLocalDocumentId, 'Action source document id'),
    sourceLocalIncarnation: validateLocalIdentity(raw.sourceLocalIncarnation, 'Action source document incarnation'),
    originalCloudProjectId: validateUuid(raw.originalCloudProjectId, 'Original cloud project id'),
    intendedCloudProjectId: raw.intendedCloudProjectId == null
      ? null
      : validateUuid(raw.intendedCloudProjectId, 'Intended cloud project id'),
    snapshotId: validateUuid(raw.snapshotId, 'Action snapshot id'),
    snapshotContentDigest: validateDigest(raw.snapshotContentDigest, 'Action snapshot digest'),
    parentSnapshotIds,
    expectedSourceDigest: validateDigest(raw.expectedSourceDigest, 'Action source digest'),
    restoredLocalDocumentId: restored.documentId,
    restoredLocalIncarnation: restored.incarnation,
    createdAt: validateTimestamp(raw.createdAt, 'Action creation timestamp'),
    updatedAt: validateTimestamp(raw.updatedAt, 'Action update timestamp'),
  };
  if (!['keep-both', 'use-cloud'].includes(receipt.kind) && receipt.phase === 'local-forked') {
    throw new Error('This cloud sync action cannot enter the local-forked phase.');
  }
  if (
    CLOUD_SYNC_ACTION_PHASE_ORDER[receipt.phase] >= CLOUD_SYNC_ACTION_PHASE_ORDER.restored
    && !receipt.restoredLocalDocumentId
  ) {
    throw new Error('A restored cloud sync action must name its restored document.');
  }
  return receipt;
}

function validateRecoveredRemoteHeads(value: unknown): CloudSyncRecoveredRemoteHeads {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Recovered remote heads entry is invalid.');
  }
  const raw = value as Record<string, unknown>;
  if (!Array.isArray(raw.snapshotIds) || raw.snapshotIds.length === 0
    || raw.snapshotIds.length > MAX_RECOVERED_HEADS_PER_PROJECT) {
    throw new Error('Recovered remote head snapshot list is invalid.');
  }
  const snapshotIds = raw.snapshotIds.map((item) => (
    validateUuid(item, 'Recovered remote snapshot id')
  ));
  if (new Set(snapshotIds).size !== snapshotIds.length) {
    throw new Error('Recovered remote head snapshot list has duplicates.');
  }
  return {
    cloudProjectId: validateUuid(raw.cloudProjectId, 'Recovered remote cloud project id'),
    snapshotIds,
  };
}

function defaultConfig(deviceId: string): StoredCloudSyncConfig {
  return {
    format: CONFIG_FORMAT,
    version: CONFIG_VERSION,
    deviceId,
    folderPath: null,
    enabled: false,
    automatic: true,
    bindings: [],
    retiredLocalDocuments: [],
    actionReceipts: [],
    recoveredRemoteHeads: [],
    ignoredCloudProjectIds: [],
    lastSuccessfulSyncAt: null,
  };
}

function validateConfig(value: unknown): StoredCloudSyncConfig {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('The cloud sync configuration is invalid.');
  }
  const raw = value as Record<string, unknown>;
  if (raw.format !== CONFIG_FORMAT || raw.version !== CONFIG_VERSION) {
    throw new Error('The cloud sync configuration version is unsupported.');
  }
  if (raw.folderPath !== null && (typeof raw.folderPath !== 'string' || !path.isAbsolute(raw.folderPath))) {
    throw new Error('The cloud sync folder path is invalid.');
  }
  if (typeof raw.enabled !== 'boolean' || typeof raw.automatic !== 'boolean') {
    throw new Error('The cloud sync configuration flags are invalid.');
  }
  if (!Array.isArray(raw.bindings) || !Array.isArray(raw.retiredLocalDocuments)
    || !Array.isArray(raw.ignoredCloudProjectIds)) {
    throw new Error('The cloud sync configuration collections are invalid.');
  }
  const bindings = raw.bindings.map(validateBinding);
  const bindingKeys = bindings.map((binding) => `${binding.localDocumentId}\u0000${binding.localIncarnation}`);
  if (new Set(bindingKeys).size !== bindingKeys.length) {
    throw new Error('The cloud sync configuration has duplicate local bindings.');
  }
  if (new Set(bindings.map((binding) => binding.cloudProjectId)).size !== bindings.length) {
    throw new Error('The cloud sync configuration binds one cloud project more than once.');
  }
  const retiredLocalDocuments = raw.retiredLocalDocuments.map(validateRetiredLocalDocument);
  const retiredKeys = retiredLocalDocuments.map((identity) => (
    bindingKey(identity.localDocumentId, identity.localIncarnation)
  ));
  if (new Set(retiredKeys).size !== retiredKeys.length) {
    throw new Error('The cloud sync configuration has duplicate retired local documents.');
  }
  if (retiredKeys.some((key) => bindingKeys.includes(key))) {
    throw new Error('A cloud-bound document cannot also be retired.');
  }
  // `actionReceipts` was added without changing the version-one envelope so
  // existing installations can be upgraded in place. Missing means no
  // interrupted orchestration; a present value remains strictly validated.
  const actionReceiptsRaw = raw.actionReceipts === undefined ? [] : raw.actionReceipts;
  if (!Array.isArray(actionReceiptsRaw)) {
    throw new Error('The cloud sync action receipt collection is invalid.');
  }
  const actionReceipts = actionReceiptsRaw.map(validateActionReceipt);
  if (actionReceipts.length > MAX_PENDING_ACTION_RECEIPTS) {
    throw new Error('The cloud sync configuration has too many pending action receipts.');
  }
  if (new Set(actionReceipts.map((receipt) => receipt.actionId)).size !== actionReceipts.length) {
    throw new Error('The cloud sync configuration has duplicate action receipts.');
  }
  // Added to the version-one envelope for in-place upgrades. Missing means no
  // remote conflict branch has yet been durably recovered on this device.
  const recoveredRemoteHeadsRaw = raw.recoveredRemoteHeads === undefined
    ? []
    : raw.recoveredRemoteHeads;
  if (!Array.isArray(recoveredRemoteHeadsRaw)
    || recoveredRemoteHeadsRaw.length > MAX_RECOVERED_REMOTE_PROJECTS) {
    throw new Error('The recovered remote heads collection is invalid.');
  }
  const recoveredRemoteHeads = recoveredRemoteHeadsRaw.map(validateRecoveredRemoteHeads);
  if (new Set(recoveredRemoteHeads.map((entry) => entry.cloudProjectId)).size
    !== recoveredRemoteHeads.length) {
    throw new Error('The recovered remote heads collection has duplicate projects.');
  }
  const ignoredCloudProjectIds = raw.ignoredCloudProjectIds.map((item) => validateUuid(item, 'Ignored cloud project id'));
  if (new Set(ignoredCloudProjectIds).size !== ignoredCloudProjectIds.length) {
    throw new Error('The cloud sync configuration has duplicate ignored projects.');
  }
  const lastSuccessfulSyncAt = raw.lastSuccessfulSyncAt === null
    ? null
    : validateTimestamp(raw.lastSuccessfulSyncAt, 'Last successful sync timestamp');
  return {
    format: CONFIG_FORMAT,
    version: CONFIG_VERSION,
    deviceId: validateUuid(raw.deviceId, 'Device id'),
    folderPath: raw.folderPath === null ? null : path.resolve(raw.folderPath),
    enabled: raw.enabled,
    automatic: raw.automatic,
    bindings,
    retiredLocalDocuments,
    actionReceipts,
    recoveredRemoteHeads,
    ignoredCloudProjectIds,
    lastSuccessfulSyncAt,
  };
}

function bindingKey(documentId: string, incarnation: string): string {
  return `${documentId}\u0000${incarnation}`;
}

function isWithin(root: string, candidate: string): boolean {
  const relative = path.relative(path.resolve(root), path.resolve(candidate));
  return relative === '' || (!relative.startsWith('..') && !path.isAbsolute(relative));
}

async function requireSafeDirectory(directoryPath: string, label: string): Promise<void> {
  const stat = await fs.lstat(directoryPath);
  if (!stat.isDirectory() || stat.isSymbolicLink()) {
    throw new Error(`${label} is not a safe local directory.`);
  }
}

async function ensureSafeChildDirectory(parentPath: string, childName: string): Promise<string> {
  if (!childName || childName === '.' || childName === '..' || path.basename(childName) !== childName) {
    throw new Error('Cloud sync attempted to use an invalid directory name.');
  }
  await requireSafeDirectory(parentPath, 'The parent sync folder');
  const childPath = path.join(parentPath, childName);
  if (!isWithin(parentPath, childPath)) throw new Error('Cloud sync path escaped its authorized folder.');
  try {
    await fs.mkdir(childPath);
  } catch (error) {
    if (!error || typeof error !== 'object' || !('code' in error)
      || (error as NodeJS.ErrnoException).code !== 'EEXIST') throw error;
  }
  await requireSafeDirectory(childPath, 'The cloud sync folder');
  return childPath;
}

async function readSmallConfig(filePath: string): Promise<unknown> {
  const stat = await fs.lstat(filePath);
  if (!stat.isFile() || stat.isSymbolicLink() || stat.size < 0 || stat.size > MAX_CONFIG_BYTES) {
    throw new Error('The cloud sync configuration file is invalid.');
  }
  return JSON.parse(await fs.readFile(filePath, 'utf8')) as unknown;
}

async function readSnapshotFile(filePath: string): Promise<LocatedSnapshot> {
  const serialized = await readBoundedImportTextFile(filePath);
  let parsed: unknown;
  try {
    parsed = JSON.parse(serialized) as unknown;
  } catch {
    throw new Error('A cloud snapshot is not valid JSON.');
  }
  const envelope = validateCloudSyncSnapshot(parsed);
  return {
    envelope,
    metadata: snapshotMetadata(envelope, false),
    serialized: stableStringify(envelope as unknown as JsonValue),
    source: 'cloud',
  };
}

function compareSnapshotMetadata(left: CloudSyncSnapshotMetadata, right: CloudSyncSnapshotMetadata): number {
  return left.generation - right.generation
    || left.createdAt.localeCompare(right.createdAt)
    || left.snapshotId.localeCompare(right.snapshotId);
}

export class CloudSyncManager {
  private readonly configPath: string;
  private readonly pollIntervalMs: number;
  private readonly now: () => Date;
  private readonly createId: () => string;
  private config: StoredCloudSyncConfig;
  private initialized = false;
  private lastError: string | null = null;
  private syncing = false;
  private mutationTail: Promise<void> = Promise.resolve();
  private pollTimer: NodeJS.Timeout | null = null;
  private pollInFlight = false;
  private listeners = new Set<() => void>();

  constructor(private readonly userDataPath: string, options: CloudSyncManagerOptions = {}) {
    if (!path.isAbsolute(userDataPath)) throw new Error('Cloud sync userData path must be absolute.');
    this.configPath = path.join(userDataPath, CONFIG_FILE_NAME);
    this.pollIntervalMs = options.pollIntervalMs ?? DEFAULT_POLL_INTERVAL_MS;
    this.now = options.now ?? (() => new Date());
    this.createId = options.createId ?? randomUUID;
    this.config = defaultConfig(validateUuid(this.createId(), 'Device id'));
  }

  async initialize(): Promise<void> {
    if (this.initialized) return;
    await fs.mkdir(this.userDataPath, { recursive: true });
    await requireSafeDirectory(this.userDataPath, 'Whiteboard user data');
    try {
      this.config = validateConfig(await readSmallConfig(this.configPath));
    } catch (error) {
      if (!isMissing(error)) {
        const quarantine = `${this.configPath}.invalid-${this.now().getTime()}-${this.createId()}`;
        try {
          await fs.rename(this.configPath, quarantine);
        } catch (renameError) {
          if (!isMissing(renameError)) throw renameError;
        }
        this.lastError = 'An invalid cloud sync configuration was preserved in quarantine.';
      }
      await this.saveConfig();
    }
    await this.ensureOutboxProjectsDirectory();
    this.initialized = true;
  }

  onChanged(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  start(): void {
    this.assertInitialized();
    if (this.pollTimer) return;
    this.pollTimer = setInterval(() => { void this.poll(); }, this.pollIntervalMs);
    this.pollTimer.unref?.();
    void this.poll();
  }

  async stop(): Promise<void> {
    if (this.pollTimer) clearInterval(this.pollTimer);
    this.pollTimer = null;
    if (this.config.enabled) {
      try {
        await this.retryOutbox();
      } catch {
        // The durable outbox intentionally survives an unavailable provider.
      }
    }
    await this.mutationTail;
  }

  async getState(): Promise<CloudSyncState> {
    this.assertInitialized();
    const inventory = await this.scanInventory();
    let folderAvailable = false;
    if (this.config.folderPath) {
      try {
        await requireSafeDirectory(this.config.folderPath, 'The selected sync folder');
        folderAvailable = true;
      } catch {
        folderAvailable = false;
      }
    }
    return {
      enabled: this.config.enabled,
      automatic: this.config.automatic,
      folderPath: this.config.folderPath,
      folderAvailable,
      deviceId: this.config.deviceId,
      bindings: this.config.bindings.map((binding) => ({ ...binding })),
      retiredLocalDocuments: this.config.retiredLocalDocuments.map((identity) => ({ ...identity })),
      actionReceipts: this.config.actionReceipts.map((receipt) => ({ ...receipt })),
      recoveredRemoteHeads: this.config.recoveredRemoteHeads.map((entry) => ({
        cloudProjectId: entry.cloudProjectId,
        snapshotIds: [...entry.snapshotIds],
      })),
      ignoredCloudProjectIds: [...this.config.ignoredCloudProjectIds],
      pendingDeliveries: inventory.projects.flatMap((project) => project.snapshots)
        .filter((snapshot) => snapshot.pendingDelivery).length,
      syncing: this.syncing,
      lastSuccessfulSyncAt: this.config.lastSuccessfulSyncAt,
      lastError: this.lastError,
      ...inventory,
    };
  }

  async getInventory(): Promise<CloudSyncInventory> {
    this.assertInitialized();
    return this.scanInventory();
  }

  async setFolder(folderPath: string): Promise<CloudSyncState> {
    return this.exclusive(async () => {
      const resolved = path.resolve(validateLocalIdentity(folderPath, 'Cloud folder path'));
      if (!path.isAbsolute(resolved)) throw new Error('The cloud folder path must be absolute.');
      await requireSafeDirectory(resolved, 'The selected sync folder');
      await this.ensureCloudProjectsDirectory(resolved);
      this.config.folderPath = resolved;
      this.config.enabled = true;
      this.config.automatic = true;
      this.lastError = null;
      await this.saveConfig();
      await this.deliverOutboxUnlocked();
      this.emitChanged();
      return this.getState();
    });
  }

  async disable(): Promise<CloudSyncState> {
    return this.exclusive(async () => {
      this.config.enabled = false;
      this.config.automatic = false;
      await this.saveConfig();
      this.emitChanged();
      return this.getState();
    });
  }

  async setAutomatic(automatic: boolean): Promise<CloudSyncState> {
    return this.exclusive(async () => {
      if (typeof automatic !== 'boolean') throw new Error('Automatic sync flag is invalid.');
      if (automatic && (!this.config.enabled || !this.config.folderPath)) {
        throw new Error('Choose a cloud folder before enabling automatic sync.');
      }
      this.config.automatic = automatic;
      await this.saveConfig();
      this.emitChanged();
      return this.getState();
    });
  }

  computeDigest(bundle: unknown): string {
    this.assertInitialized();
    return cloudSyncContentDigest(bundle);
  }

  async publish(request: CloudSyncPublishRequest): Promise<CloudSyncPublishResult> {
    return this.exclusive(async () => this.publishUnlocked(request));
  }

  async readSnapshot(request: CloudSyncReadSnapshotRequest): Promise<CloudSyncSnapshotEnvelope> {
    this.assertInitialized();
    const cloudProjectId = validateUuid(request?.cloudProjectId, 'Cloud project id');
    const snapshotId = validateUuid(request?.snapshotId, 'Snapshot id');
    const located = await this.findSnapshot(cloudProjectId, snapshotId);
    if (!located) throw new Error('The requested cloud snapshot is not available on this device.');
    return located.envelope;
  }

  async setBinding(request: CloudSyncSetBindingRequest): Promise<CloudSyncBinding> {
    return this.exclusive(async () => {
      const binding = validateBinding(request);
      this.clearRetiredLocalDocument(binding.localDocumentId, binding.localIncarnation);
      this.upsertBinding(binding);
      this.config.ignoredCloudProjectIds = this.config.ignoredCloudProjectIds
        .filter((id) => id !== binding.cloudProjectId);
      await this.saveConfig();
      this.emitChanged();
      return { ...binding };
    });
  }

  async moveBinding(request: CloudSyncMoveBindingRequest): Promise<CloudSyncBinding> {
    return this.exclusive(async () => {
      const fromDocumentId = validateLocalIdentity(request?.fromLocalDocumentId, 'Source document id');
      const fromIncarnation = validateLocalIdentity(request?.fromLocalIncarnation, 'Source document incarnation');
      const toDocumentId = validateLocalIdentity(request?.toLocalDocumentId, 'Destination document id');
      const toIncarnation = validateLocalIdentity(request?.toLocalIncarnation, 'Destination document incarnation');
      const sourceIndex = this.bindingIndex(fromDocumentId, fromIncarnation);
      if (sourceIndex < 0) throw new Error('The source document has no cloud binding.');
      const destinationIndex = this.bindingIndex(toDocumentId, toIncarnation);
      if (destinationIndex >= 0 && destinationIndex !== sourceIndex) {
        throw new Error('The destination document already has a cloud binding.');
      }
      const source = this.config.bindings[sourceIndex];
      const moved: CloudSyncBinding = {
        ...source,
        localDocumentId: toDocumentId,
        localIncarnation: toIncarnation,
        lastSnapshotId: request.lastSnapshotId === undefined
          ? source.lastSnapshotId
          : request.lastSnapshotId === null
            ? null
            : validateUuid(request.lastSnapshotId, 'Last snapshot id'),
        lastContentDigest: request.lastContentDigest === undefined
          ? source.lastContentDigest
          : request.lastContentDigest === null
            ? null
            : validateDigest(request.lastContentDigest, 'Last content digest'),
      };
      const expectedRetiredContentDigest = request.expectedRetiredContentDigest === undefined
        ? source.lastContentDigest
        : request.expectedRetiredContentDigest === null
          ? null
          : validateDigest(request.expectedRetiredContentDigest, 'Retired local document digest');
      this.config.bindings.splice(sourceIndex, 1);
      this.retireLocalDocument(fromDocumentId, fromIncarnation, expectedRetiredContentDigest);
      this.clearRetiredLocalDocument(toDocumentId, toIncarnation);
      this.upsertBinding(moved);
      await this.saveConfig();
      this.emitChanged();
      return { ...moved };
    });
  }

  async saveActionReceipt(request: CloudSyncSaveActionReceiptRequest): Promise<CloudSyncActionReceipt> {
    return this.exclusive(async () => {
      const now = this.now().toISOString();
      const restored = validateNullableIdentityPair(
        request?.restoredLocalDocumentId,
        request?.restoredLocalIncarnation,
        'Restored local',
      );
      const candidate = validateActionReceipt({
        actionId: request?.actionId,
        kind: request?.kind,
        phase: request?.phase,
        sourceLocalDocumentId: request?.sourceLocalDocumentId,
        sourceLocalIncarnation: request?.sourceLocalIncarnation,
        originalCloudProjectId: request?.originalCloudProjectId,
        intendedCloudProjectId: request?.intendedCloudProjectId ?? null,
        snapshotId: request?.snapshotId,
        snapshotContentDigest: request?.snapshotContentDigest,
        parentSnapshotIds: request?.parentSnapshotIds,
        expectedSourceDigest: request?.expectedSourceDigest,
        restoredLocalDocumentId: restored.documentId,
        restoredLocalIncarnation: restored.incarnation,
        createdAt: now,
        updatedAt: now,
      });
      const index = this.config.actionReceipts.findIndex((receipt) => receipt.actionId === candidate.actionId);
      if (index < 0) {
        if (candidate.phase !== 'prepared') {
          throw new Error('A new cloud sync action must begin in the prepared phase.');
        }
        if (this.config.actionReceipts.length >= MAX_PENDING_ACTION_RECEIPTS) {
          throw new Error('Resolve pending cloud sync actions before starting another one.');
        }
        this.config.actionReceipts.push(candidate);
      } else {
        const existing = this.config.actionReceipts[index];
        if (
          existing.kind !== candidate.kind
          || existing.sourceLocalDocumentId !== candidate.sourceLocalDocumentId
          || existing.sourceLocalIncarnation !== candidate.sourceLocalIncarnation
          || existing.originalCloudProjectId !== candidate.originalCloudProjectId
          || existing.snapshotId !== candidate.snapshotId
          || existing.snapshotContentDigest !== candidate.snapshotContentDigest
          || existing.expectedSourceDigest !== candidate.expectedSourceDigest
          || existing.parentSnapshotIds.length !== candidate.parentSnapshotIds.length
          || existing.parentSnapshotIds.some((id, parentIndex) => id !== candidate.parentSnapshotIds[parentIndex])
        ) {
          throw new Error('Cloud sync action identity cannot change while it is pending.');
        }
        if (CLOUD_SYNC_ACTION_PHASE_ORDER[candidate.phase] < CLOUD_SYNC_ACTION_PHASE_ORDER[existing.phase]) {
          throw new Error('Cloud sync action phase cannot move backwards.');
        }
        if (
          existing.intendedCloudProjectId
          && candidate.intendedCloudProjectId
          && candidate.intendedCloudProjectId !== existing.intendedCloudProjectId
        ) {
          throw new Error('Cloud sync action destination cannot change while it is pending.');
        }
        if (
          existing.restoredLocalDocumentId
          && candidate.restoredLocalDocumentId
          && (
            candidate.restoredLocalDocumentId !== existing.restoredLocalDocumentId
            || candidate.restoredLocalIncarnation !== existing.restoredLocalIncarnation
          )
        ) {
          throw new Error('Cloud sync restored document identity cannot change while it is pending.');
        }
        const merged = validateActionReceipt({
          ...candidate,
          intendedCloudProjectId: candidate.intendedCloudProjectId ?? existing.intendedCloudProjectId,
          restoredLocalDocumentId: candidate.restoredLocalDocumentId ?? existing.restoredLocalDocumentId,
          restoredLocalIncarnation: candidate.restoredLocalIncarnation ?? existing.restoredLocalIncarnation,
          createdAt: existing.createdAt,
          updatedAt: now,
        });
        this.config.actionReceipts[index] = merged;
      }
      await this.saveConfig();
      this.emitChanged();
      const saved = this.config.actionReceipts.find((receipt) => receipt.actionId === candidate.actionId);
      if (!saved) throw new Error('Cloud sync action receipt could not be saved.');
      return { ...saved };
    });
  }

  async completeActionReceipt(actionIdValue: string): Promise<boolean> {
    return this.exclusive(async () => {
      const actionId = validateLocalIdentity(actionIdValue, 'Cloud sync action id');
      const before = this.config.actionReceipts.length;
      this.config.actionReceipts = this.config.actionReceipts.filter((receipt) => receipt.actionId !== actionId);
      if (before === this.config.actionReceipts.length) return false;
      await this.saveConfig();
      this.emitChanged();
      return true;
    });
  }

  async recordRecoveredRemoteHeads(
    cloudProjectIdValue: string,
    snapshotIdValues: string[],
  ): Promise<CloudSyncRecoveredRemoteHeads> {
    return this.exclusive(async () => {
      const incoming = validateRecoveredRemoteHeads({
        cloudProjectId: cloudProjectIdValue,
        snapshotIds: snapshotIdValues,
      });
      const index = this.config.recoveredRemoteHeads.findIndex((entry) => (
        entry.cloudProjectId === incoming.cloudProjectId
      ));
      if (index < 0) {
        if (this.config.recoveredRemoteHeads.length >= MAX_RECOVERED_REMOTE_PROJECTS) {
          throw new Error('Clear old recovered cloud histories before recording another one.');
        }
        this.config.recoveredRemoteHeads.push(incoming);
      } else {
        const existing = this.config.recoveredRemoteHeads[index];
        const snapshotIds = [...new Set([...existing.snapshotIds, ...incoming.snapshotIds])];
        if (snapshotIds.length > MAX_RECOVERED_HEADS_PER_PROJECT) {
          throw new Error('This cloud project has too many recovered heads to record safely.');
        }
        this.config.recoveredRemoteHeads[index] = {
          cloudProjectId: existing.cloudProjectId,
          snapshotIds,
        };
      }
      await this.saveConfig();
      this.emitChanged();
      const saved = this.config.recoveredRemoteHeads.find((entry) => (
        entry.cloudProjectId === incoming.cloudProjectId
      ));
      if (!saved) throw new Error('Recovered remote heads could not be recorded.');
      return { cloudProjectId: saved.cloudProjectId, snapshotIds: [...saved.snapshotIds] };
    });
  }

  async clearRecoveredRemoteHeads(cloudProjectIdValue: string): Promise<boolean> {
    return this.exclusive(async () => {
      const cloudProjectId = validateUuid(cloudProjectIdValue, 'Recovered remote cloud project id');
      const before = this.config.recoveredRemoteHeads.length;
      this.config.recoveredRemoteHeads = this.config.recoveredRemoteHeads.filter((entry) => (
        entry.cloudProjectId !== cloudProjectId
      ));
      if (this.config.recoveredRemoteHeads.length === before) return false;
      await this.saveConfig();
      this.emitChanged();
      return true;
    });
  }

  async forgetBinding(request: CloudSyncForgetBindingRequest): Promise<boolean> {
    return this.exclusive(async () => {
      const documentId = validateLocalIdentity(request?.localDocumentId, 'Local document id');
      const incarnation = validateLocalIdentity(request?.localIncarnation, 'Local document incarnation');
      const index = this.bindingIndex(documentId, incarnation);
      const existing = index >= 0 ? this.config.bindings[index] : null;
      const retired = this.clearRetiredLocalDocument(documentId, incarnation);
      const cloudProjectId = request.cloudProjectId == null
        ? existing?.cloudProjectId ?? null
        : validateUuid(request.cloudProjectId, 'Cloud project id');
      if (existing && cloudProjectId && existing.cloudProjectId !== cloudProjectId) {
        throw new Error('The document cloud binding changed before it could be forgotten.');
      }
      if (index >= 0) this.config.bindings.splice(index, 1);
      if (request.ignoreRemote === true && cloudProjectId) {
        this.config.ignoredCloudProjectIds = [...new Set([
          ...this.config.ignoredCloudProjectIds,
          cloudProjectId,
        ])];
      }
      await this.saveConfig();
      this.emitChanged();
      return index >= 0 || retired;
    });
  }

  async setRemoteIgnored(cloudProjectIdValue: string, ignored: boolean): Promise<void> {
    await this.exclusive(async () => {
      const cloudProjectId = validateUuid(cloudProjectIdValue, 'Cloud project id');
      this.config.ignoredCloudProjectIds = ignored
        ? [...new Set([...this.config.ignoredCloudProjectIds, cloudProjectId])]
        : this.config.ignoredCloudProjectIds.filter((id) => id !== cloudProjectId);
      await this.saveConfig();
      this.emitChanged();
    });
  }

  async retryOutbox(): Promise<{ delivered: number; pending: number }> {
    return this.exclusive(async () => {
      const result = await this.deliverOutboxUnlocked();
      this.emitChanged();
      return result;
    });
  }

  private async publishUnlocked(request: CloudSyncPublishRequest): Promise<CloudSyncPublishResult> {
    this.assertInitialized();
    if (!this.config.enabled || !this.config.folderPath) {
      throw new Error('Choose and enable a cloud folder before syncing.');
    }
    const localDocumentId = validateLocalIdentity(request?.localDocumentId, 'Local document id');
    const localIncarnation = validateLocalIdentity(request?.localIncarnation, 'Local document incarnation');
    if (this.isRetiredLocalDocument(localDocumentId, localIncarnation)) {
      throw new Error('This superseded local document is retired from cloud sync.');
    }
    const bundle = validateCloudSyncBundle(request?.bundle);
    const contentDigest = cloudSyncContentDigest(bundle);
    const existingIndex = this.bindingIndex(localDocumentId, localIncarnation);
    const existing = existingIndex >= 0 ? this.config.bindings[existingIndex] : null;
    const requestedCloudProjectId = request.cloudProjectId == null
      ? null
      : validateUuid(request.cloudProjectId, 'Cloud project id');
    const requestedNewCloudProjectId = request.newCloudProjectId == null
      ? null
      : validateUuid(request.newCloudProjectId, 'New cloud project id');
    if (requestedNewCloudProjectId && request.createNewProject !== true) {
      throw new Error('A preallocated cloud project id requires createNewProject.');
    }
    if (existing && requestedCloudProjectId && requestedCloudProjectId !== existing.cloudProjectId
      && request.createNewProject !== true) {
      throw new Error('The document is already bound to another cloud project.');
    }
    const cloudProjectId = request.createNewProject === true
      ? requestedNewCloudProjectId ?? validateUuid(this.createId(), 'Cloud project id')
      : existing?.cloudProjectId ?? requestedCloudProjectId ?? validateUuid(this.createId(), 'Cloud project id');

    // A renderer action persists its preallocated UUID before asking us to
    // fork. If Electron or the renderer dies after the immutable root was
    // written, replay must recover that exact root rather than create a second
    // logical project (or a competing root in the same project).
    if (request.createNewProject === true && requestedNewCloudProjectId) {
      const inventory = await this.scanInventory();
      const priorProject = inventory.projects.find((project) => (
        project.cloudProjectId === requestedNewCloudProjectId
      ));
      if (priorProject) {
        const exactRoots = priorProject.snapshots.filter((snapshot) => (
          snapshot.parentSnapshotIds.length === 0 && snapshot.contentDigest === contentDigest
        ));
        if (priorProject.snapshots.length !== 1 || exactRoots.length !== 1) {
          throw new Error('The preallocated cloud project id is already used by different history.');
        }
        const prior = exactRoots[0];
        const recoveredBinding: CloudSyncBinding = {
          localDocumentId,
          localIncarnation,
          cloudProjectId: requestedNewCloudProjectId,
          lastSnapshotId: prior.snapshotId,
          lastContentDigest: prior.contentDigest,
        };
        this.upsertBinding(recoveredBinding);
        this.config.ignoredCloudProjectIds = this.config.ignoredCloudProjectIds
          .filter((id) => id !== requestedNewCloudProjectId);
        await this.saveConfig();
        this.emitChanged();
        return {
          created: false,
          delivered: !prior.pendingDelivery,
          binding: { ...recoveredBinding },
          snapshot: { ...prior },
        };
      }
    }

    const explicitParents = request.parentSnapshotIds !== undefined;
    const parentSnapshotIds = request.createNewProject === true
      ? []
      : explicitParents
        ? this.validateParentIds(request.parentSnapshotIds)
        : existing?.lastSnapshotId ? [existing.lastSnapshotId] : [];
    if (request.createNewProject === true && explicitParents && request.parentSnapshotIds?.length) {
      throw new Error('A new cloud project cannot inherit snapshots from another cloud project.');
    }
    if (!explicitParents && request.createNewProject !== true && existing?.lastSnapshotId
      && existing.lastContentDigest === contentDigest) {
      const prior = await this.findSnapshot(cloudProjectId, existing.lastSnapshotId);
      if (prior) {
        return {
          created: false,
          delivered: prior.source === 'cloud',
          binding: { ...existing },
          snapshot: { ...prior.metadata, pendingDelivery: prior.source === 'outbox' },
        };
      }
    }

    const parentSnapshots: LocatedSnapshot[] = [];
    for (const parentId of parentSnapshotIds) {
      const parent = await this.findSnapshot(cloudProjectId, parentId);
      if (!parent) throw new Error(`Parent snapshot ${parentId} is not available on this device.`);
      parentSnapshots.push(parent);
    }
    const generation = parentSnapshots.length
      ? Math.max(...parentSnapshots.map((parent) => parent.envelope.generation)) + 1 : 0;
    const snapshotId = validateUuid(this.createId(), 'Snapshot id');
    const envelope: CloudSyncSnapshotEnvelope = {
      format: CLOUD_SYNC_SNAPSHOT_FORMAT,
      version: CLOUD_SYNC_SNAPSHOT_VERSION,
      cloudProjectId,
      snapshotId,
      deviceId: this.config.deviceId,
      parentSnapshotIds,
      generation,
      createdAt: this.now().toISOString(),
      contentDigest,
      bundle,
    };
    const serialized = stableStringify(envelope as unknown as JsonValue);
    if (Buffer.byteLength(serialized, 'utf8') > MAX_CLOUD_SYNC_SNAPSHOT_BYTES) {
      throw new Error('The cloud snapshot is larger than the 257 MiB safety limit.');
    }
    const outboxPath = await this.outboxSnapshotPath(envelope, true);
    await atomicWriteTextFile(outboxPath, serialized);

    const binding: CloudSyncBinding = {
      localDocumentId,
      localIncarnation,
      cloudProjectId,
      lastSnapshotId: snapshotId,
      lastContentDigest: contentDigest,
    };
    this.upsertBinding(binding);
    this.config.ignoredCloudProjectIds = this.config.ignoredCloudProjectIds.filter((id) => id !== cloudProjectId);
    await this.saveConfig();

    let delivered = false;
    try {
      await this.deliverOne(envelope, serialized, outboxPath);
      delivered = true;
      this.config.lastSuccessfulSyncAt = this.now().toISOString();
      this.lastError = null;
      await this.saveConfig();
    } catch (error) {
      this.lastError = errorMessage(error);
    }
    this.emitChanged();
    return {
      created: true,
      delivered,
      binding: { ...binding },
      snapshot: snapshotMetadata(envelope, !delivered),
    };
  }

  private validateParentIds(value: unknown): string[] {
    if (!Array.isArray(value) || value.length > MAX_SNAPSHOT_PARENTS) {
      throw new Error('Snapshot parent list is invalid.');
    }
    const parents = value.map((item) => validateUuid(item, 'Parent snapshot id'));
    if (new Set(parents).size !== parents.length) throw new Error('Snapshot parent list has duplicates.');
    return parents;
  }

  private async deliverOutboxUnlocked(): Promise<{ delivered: number; pending: number }> {
    if (!this.config.enabled || !this.config.folderPath) {
      const pending = (await this.scanSnapshotTree(await this.outboxProjectsPath(), 'outbox', [])).length;
      return { delivered: 0, pending };
    }
    this.syncing = true;
    let delivered = 0;
    let lastFailure: unknown = null;
    try {
      const snapshots = await this.scanSnapshotTree(await this.outboxProjectsPath(), 'outbox', []);
      for (const snapshot of snapshots) {
        const outboxPath = await this.outboxSnapshotPath(snapshot.envelope, false);
        try {
          await this.deliverOne(snapshot.envelope, snapshot.serialized, outboxPath);
          delivered += 1;
        } catch (error) {
          lastFailure = error;
        }
      }
      const pending = (await this.scanSnapshotTree(await this.outboxProjectsPath(), 'outbox', [])).length;
      if (delivered) {
        this.config.lastSuccessfulSyncAt = this.now().toISOString();
        await this.saveConfig();
      }
      this.lastError = lastFailure ? errorMessage(lastFailure) : null;
      return { delivered, pending };
    } finally {
      this.syncing = false;
    }
  }

  private async deliverOne(
    envelope: CloudSyncSnapshotEnvelope,
    serialized: string,
    outboxPath: string,
  ): Promise<void> {
    if (!this.config.folderPath) throw new Error('No cloud folder is selected.');
    const destination = await this.cloudSnapshotPath(envelope, true);
    try {
      const existing = await readSnapshotFile(destination);
      if (existing.serialized !== serialized) {
        throw new Error('A different cloud snapshot already uses the same immutable id.');
      }
    } catch (error) {
      if (!isMissing(error)) throw error;
      await atomicWriteTextFile(destination, serialized);
      const committed = await readSnapshotFile(destination);
      if (committed.serialized !== serialized) {
        throw new Error('The cloud provider changed a snapshot while it was being committed.');
      }
    }
    try {
      await fs.unlink(outboxPath);
    } catch (error) {
      if (!isMissing(error)) throw error;
    }
  }

  private async scanInventory(): Promise<CloudSyncInventory> {
    const warnings: string[] = [];
    const located: LocatedSnapshot[] = [];
    try {
      located.push(...await this.scanSnapshotTree(await this.outboxProjectsPath(), 'outbox', warnings));
    } catch (error) {
      warnings.push(`The local cloud outbox could not be read: ${errorMessage(error)}`);
    }
    if (this.config.enabled && this.config.folderPath) {
      try {
        const projectsPath = await this.cloudProjectsPath(false);
        if (projectsPath) located.push(...await this.scanSnapshotTree(projectsPath, 'cloud', warnings));
      } catch (error) {
        warnings.push(`The selected cloud folder is unavailable: ${errorMessage(error)}`);
      }
    }

    const byProject = new Map<string, Map<string, LocatedSnapshot>>();
    for (const item of located) {
      let project = byProject.get(item.envelope.cloudProjectId);
      if (!project) {
        project = new Map();
        byProject.set(item.envelope.cloudProjectId, project);
      }
      const existing = project.get(item.envelope.snapshotId);
      if (!existing) project.set(item.envelope.snapshotId, item);
      else if (existing.serialized !== item.serialized) {
        warnings.push(`Cloud project ${item.envelope.cloudProjectId} contains a duplicate snapshot id.`);
      }
    }

    const projects: CloudSyncProjectInventory[] = [];
    for (const [cloudProjectId, snapshotMap] of byProject) {
      const rows = [...snapshotMap.values()];
      const parentIds = new Set(rows.flatMap((item) => item.envelope.parentSnapshotIds));
      const snapshots = rows.map((item) => ({ ...item.metadata, pendingDelivery: item.source === 'outbox' }))
        .sort(compareSnapshotMetadata);
      const heads = snapshots.filter((snapshot) => !parentIds.has(snapshot.snapshotId));
      projects.push({
        cloudProjectId,
        projectTitle: heads.at(-1)?.projectTitle ?? snapshots.at(-1)?.projectTitle ?? 'Untitled Project',
        snapshots,
        heads,
      });
    }
    projects.sort((left, right) => left.projectTitle.localeCompare(right.projectTitle)
      || left.cloudProjectId.localeCompare(right.cloudProjectId));
    return { projects, warnings: warnings.slice(0, 50) };
  }

  private async scanSnapshotTree(
    projectsPath: string,
    source: 'cloud' | 'outbox',
    warnings: string[],
  ): Promise<LocatedSnapshot[]> {
    try {
      await requireSafeDirectory(projectsPath, 'The cloud projects folder');
    } catch (error) {
      if (isMissing(error)) return [];
      throw error;
    }
    const result: LocatedSnapshot[] = [];
    const projectEntries = await fs.readdir(projectsPath, { withFileTypes: true });
    for (const projectEntry of projectEntries) {
      if (!projectEntry.isDirectory() || projectEntry.isSymbolicLink() || !UUID_PATTERN.test(projectEntry.name)) continue;
      const cloudProjectId = projectEntry.name.toLowerCase();
      const projectPath = path.join(projectsPath, projectEntry.name);
      const snapshotsPath = path.join(projectPath, 'snapshots');
      try {
        await requireSafeDirectory(projectPath, 'A cloud project folder');
        await requireSafeDirectory(snapshotsPath, 'A cloud snapshots folder');
      } catch (error) {
        if (!isMissing(error)) warnings.push(`Cloud project ${cloudProjectId} has an unsafe snapshots folder.`);
        continue;
      }
      for (const entry of await fs.readdir(snapshotsPath, { withFileTypes: true })) {
        if (result.length >= MAX_SNAPSHOT_FILES) {
          warnings.push(`Cloud snapshot scan stopped at the ${MAX_SNAPSHOT_FILES}-file safety limit.`);
          return result;
        }
        if (!entry.isFile() || entry.isSymbolicLink() || !entry.name.endsWith('.lfsync')) continue;
        const filePath = path.join(snapshotsPath, entry.name);
        try {
          const snapshot = await readSnapshotFile(filePath);
          if (snapshot.envelope.cloudProjectId !== cloudProjectId) {
            throw new Error('Snapshot project id does not match its directory.');
          }
          snapshot.source = source;
          snapshot.metadata.pendingDelivery = source === 'outbox';
          result.push(snapshot);
        } catch (error) {
          warnings.push(`A ${source} snapshot was ignored: ${errorMessage(error)}`);
        }
      }
    }
    return result;
  }

  private async findSnapshot(cloudProjectId: string, snapshotId: string): Promise<LocatedSnapshot | null> {
    const outbox = await this.snapshotAtKnownLocation('outbox', cloudProjectId, snapshotId);
    if (outbox) return outbox;
    return this.snapshotAtKnownLocation('cloud', cloudProjectId, snapshotId);
  }

  private async snapshotAtKnownLocation(
    source: 'cloud' | 'outbox',
    cloudProjectId: string,
    snapshotId: string,
  ): Promise<LocatedSnapshot | null> {
    let filePath: string | null;
    if (source === 'outbox') {
      filePath = await this.snapshotPathFromIds(await this.outboxProjectsPath(), cloudProjectId, snapshotId);
    } else {
      const projectsPath = await this.cloudProjectsPath(false);
      if (!projectsPath) return null;
      filePath = await this.snapshotPathFromIds(projectsPath, cloudProjectId, snapshotId);
    }
    try {
      const result = await readSnapshotFile(filePath);
      if (result.envelope.cloudProjectId !== cloudProjectId || result.envelope.snapshotId !== snapshotId) {
        throw new Error('Snapshot identity does not match its file name.');
      }
      result.source = source;
      result.metadata.pendingDelivery = source === 'outbox';
      return result;
    } catch (error) {
      if (isMissing(error)) return null;
      throw error;
    }
  }

  private async snapshotPathFromIds(
    projectsPath: string,
    cloudProjectIdValue: string,
    snapshotIdValue: string,
  ): Promise<string> {
    const cloudProjectId = validateUuid(cloudProjectIdValue, 'Cloud project id');
    const snapshotId = validateUuid(snapshotIdValue, 'Snapshot id');
    const result = path.join(projectsPath, cloudProjectId, 'snapshots', `${snapshotId}.lfsync`);
    if (!isWithin(projectsPath, result)) throw new Error('Cloud snapshot path escaped its authorized folder.');
    return result;
  }

  private async outboxSnapshotPath(envelope: CloudSyncSnapshotEnvelope, create: boolean): Promise<string> {
    const projects = await this.outboxProjectsPath();
    if (create) await this.ensureProjectSnapshotDirectory(projects, envelope.cloudProjectId);
    return this.snapshotPathFromIds(projects, envelope.cloudProjectId, envelope.snapshotId);
  }

  private async cloudSnapshotPath(envelope: CloudSyncSnapshotEnvelope, create: boolean): Promise<string> {
    const projects = await this.cloudProjectsPath(create);
    if (!projects) throw new Error('The selected cloud folder is unavailable.');
    if (create) await this.ensureProjectSnapshotDirectory(projects, envelope.cloudProjectId);
    return this.snapshotPathFromIds(projects, envelope.cloudProjectId, envelope.snapshotId);
  }

  private async ensureProjectSnapshotDirectory(projectsPath: string, cloudProjectIdValue: string): Promise<string> {
    const cloudProjectId = validateUuid(cloudProjectIdValue, 'Cloud project id');
    const projectPath = await ensureSafeChildDirectory(projectsPath, cloudProjectId);
    return ensureSafeChildDirectory(projectPath, 'snapshots');
  }

  private async ensureOutboxProjectsDirectory(): Promise<string> {
    const outbox = await ensureSafeChildDirectory(this.userDataPath, OUTBOX_FOLDER_NAME);
    return ensureSafeChildDirectory(outbox, 'Projects');
  }

  private async outboxProjectsPath(): Promise<string> {
    return this.ensureOutboxProjectsDirectory();
  }

  private async ensureCloudProjectsDirectory(folderPath: string): Promise<string> {
    const productRoot = await ensureSafeChildDirectory(folderPath, CLOUD_SYNC_FOLDER_NAME);
    return ensureSafeChildDirectory(productRoot, 'Projects');
  }

  private async cloudProjectsPath(create: boolean): Promise<string | null> {
    if (!this.config.folderPath) return null;
    await requireSafeDirectory(this.config.folderPath, 'The selected sync folder');
    if (create) return this.ensureCloudProjectsDirectory(this.config.folderPath);
    const productRoot = path.join(this.config.folderPath, CLOUD_SYNC_FOLDER_NAME);
    const projects = path.join(productRoot, 'Projects');
    if (!isWithin(this.config.folderPath, projects)) throw new Error('Cloud sync path escaped its selected folder.');
    await requireSafeDirectory(productRoot, 'The Whiteboard cloud folder');
    await requireSafeDirectory(projects, 'The Whiteboard cloud projects folder');
    return projects;
  }

  private isRetiredLocalDocument(documentId: string, incarnation: string): boolean {
    const key = bindingKey(documentId, incarnation);
    return this.config.retiredLocalDocuments.some((identity) => (
      bindingKey(identity.localDocumentId, identity.localIncarnation) === key
    ));
  }

  private retireLocalDocument(
    documentId: string,
    incarnation: string,
    expectedContentDigest: string | null = null,
  ): void {
    const key = bindingKey(documentId, incarnation);
    const existing = this.config.retiredLocalDocuments.find((identity) => (
      bindingKey(identity.localDocumentId, identity.localIncarnation) === key
    ));
    if (existing) {
      // We may safely upgrade a legacy/unknown tombstone when the renderer has
      // just supplied a fresh digest. Never replace one known digest with a
      // different value: that would erase evidence of an intervening edit.
      if (existing.expectedContentDigest === null && expectedContentDigest !== null) {
        existing.expectedContentDigest = validateDigest(
          expectedContentDigest,
          'Retired local document digest',
        );
      } else if (
        existing.expectedContentDigest !== null
        && expectedContentDigest !== null
        && existing.expectedContentDigest !== expectedContentDigest
      ) {
        throw new Error('Retired local document digest changed before ownership transfer completed.');
      }
      return;
    }
    this.config.retiredLocalDocuments.push({
      localDocumentId: documentId,
      localIncarnation: incarnation,
      expectedContentDigest: expectedContentDigest === null
        ? null
        : validateDigest(expectedContentDigest, 'Retired local document digest'),
    });
  }

  private clearRetiredLocalDocument(documentId: string, incarnation: string): boolean {
    const key = bindingKey(documentId, incarnation);
    const before = this.config.retiredLocalDocuments.length;
    this.config.retiredLocalDocuments = this.config.retiredLocalDocuments.filter((identity) => (
      bindingKey(identity.localDocumentId, identity.localIncarnation) !== key
    ));
    return this.config.retiredLocalDocuments.length !== before;
  }

  private bindingIndex(documentId: string, incarnation: string): number {
    const key = bindingKey(documentId, incarnation);
    return this.config.bindings.findIndex((binding) => (
      bindingKey(binding.localDocumentId, binding.localIncarnation) === key
    ));
  }

  private upsertBinding(binding: CloudSyncBinding): void {
    // A cloud UUID names one logical project. Keeping two local documents tied
    // to it would make the next automatic pass publish both as competing
    // branches. Moving/restoring a project therefore transfers ownership.
    for (const candidate of this.config.bindings) {
      if (
        candidate.cloudProjectId === binding.cloudProjectId
        && bindingKey(candidate.localDocumentId, candidate.localIncarnation)
          !== bindingKey(binding.localDocumentId, binding.localIncarnation)
      ) {
        this.retireLocalDocument(
          candidate.localDocumentId,
          candidate.localIncarnation,
          candidate.lastContentDigest,
        );
      }
    }
    this.config.bindings = this.config.bindings.filter((candidate) => (
      candidate.cloudProjectId !== binding.cloudProjectId
      || bindingKey(candidate.localDocumentId, candidate.localIncarnation)
        === bindingKey(binding.localDocumentId, binding.localIncarnation)
    ));
    const index = this.bindingIndex(binding.localDocumentId, binding.localIncarnation);
    if (index >= 0) this.config.bindings[index] = binding;
    else this.config.bindings.push(binding);
  }

  private async saveConfig(): Promise<void> {
    const validated = validateConfig(this.config);
    this.config = validated;
    await atomicWriteTextFile(this.configPath, `${JSON.stringify(validated, null, 2)}\n`);
  }

  private async poll(): Promise<void> {
    if (this.pollInFlight || !this.initialized) return;
    this.pollInFlight = true;
    try {
      if (this.config.enabled) await this.retryOutbox();
      this.emitChanged();
    } catch (error) {
      const nextError = errorMessage(error);
      if (nextError !== this.lastError) {
        this.lastError = nextError;
        this.emitChanged();
      }
    } finally {
      this.pollInFlight = false;
    }
  }

  private emitChanged(): void {
    for (const listener of this.listeners) {
      try {
        listener();
      } catch (error) {
        console.error('[cloud-sync] state listener failed:', error);
      }
    }
  }

  private exclusive<T>(operation: () => Promise<T>): Promise<T> {
    this.assertInitialized();
    const run = this.mutationTail.then(operation, operation);
    this.mutationTail = run.then(() => undefined, () => undefined);
    return run;
  }

  private assertInitialized(): void {
    if (!this.initialized) throw new Error('Cloud sync has not been initialized.');
  }
}
