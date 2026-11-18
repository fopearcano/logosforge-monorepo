import { createHash, randomUUID } from 'node:crypto';
import { promises as fs } from 'node:fs';
import * as path from 'node:path';

import { atomicWriteTextFile } from './atomic-file-save';
import {
  MAX_PRO_CLOUD_SNAPSHOT_BYTES,
  MAX_PRO_PROJECT_SNAPSHOT_BYTES,
  readBoundedTextFile,
} from './bounded-text-file';

export const CLOUD_SYNC_FOLDER_NAME = 'LogosForge Pro';
export const CLOUD_SYNC_SNAPSHOT_FORMAT = 'logosforge-pro-cloud-snapshot';
export const CLOUD_SYNC_SNAPSHOT_VERSION = '1.0';
export const PRO_PROJECT_SNAPSHOT_FORMAT = 'logosforge-pro-project-snapshot';
export const PRO_PROJECT_SNAPSHOT_VERSION = '1.0';

const CONFIG_FORMAT = 'logosforge-pro-cloud-sync-config';
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

export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };

export interface CloudSyncBinding {
  localProjectId: string;
  localIncarnation: string;
  cloudProjectId: string;
  lastSnapshotId: string | null;
  lastContentDigest: string | null;
}

export interface CloudSyncRetiredLocalProject {
  localProjectId: string;
  localIncarnation: string;
  expectedContentDigest: string | null;
}

export type CloudSyncActionKind = 'pull' | 'replace-cloud' | 'keep-both' | 'use-cloud' | 'discover' | 'remote-recovery';
export type CloudSyncActionPhase = 'prepared' | 'local-forked' | 'restored' | 'binding-installed';

const ACTION_KINDS = new Set<CloudSyncActionKind>([
  'pull', 'replace-cloud', 'keep-both', 'use-cloud', 'discover', 'remote-recovery',
]);
const ACTION_PHASES = new Set<CloudSyncActionPhase>([
  'prepared', 'local-forked', 'restored', 'binding-installed',
]);
const ACTION_PHASE_ORDER: Record<CloudSyncActionPhase, number> = {
  prepared: 0,
  'local-forked': 1,
  restored: 2,
  'binding-installed': 3,
};

export interface CloudSyncActionReceipt {
  actionId: string;
  kind: CloudSyncActionKind;
  phase: CloudSyncActionPhase;
  sourceLocalProjectId: string;
  sourceLocalIncarnation: string;
  originalCloudProjectId: string;
  intendedCloudProjectId: string | null;
  snapshotId: string;
  snapshotContentDigest: string;
  parentSnapshotIds: string[];
  expectedSourceDigest: string;
  restoredLocalProjectId: string | null;
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
  retiredLocalProjects: CloudSyncRetiredLocalProject[];
  actionReceipts: CloudSyncActionReceipt[];
  recoveredRemoteHeads: CloudSyncRecoveredRemoteHeads[];
  ignoredCloudProjectIds: string[];
  pendingDeliveries: number;
  syncing: boolean;
  lastSuccessfulSyncAt: string | null;
  lastError: string | null;
}

export interface CloudSyncPublishRequest {
  localProjectId: string;
  localIncarnation: string;
  bundle: unknown;
  cloudProjectId?: string | null;
  parentSnapshotIds?: string[];
  createNewProject?: boolean;
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
  fromLocalProjectId: string;
  fromLocalIncarnation: string;
  toLocalProjectId: string;
  toLocalIncarnation: string;
  lastSnapshotId?: string | null;
  lastContentDigest?: string | null;
  expectedRetiredContentDigest?: string | null;
}

export interface CloudSyncSaveActionReceiptRequest {
  actionId: string;
  kind: CloudSyncActionKind;
  phase: CloudSyncActionPhase;
  sourceLocalProjectId: string;
  sourceLocalIncarnation: string;
  originalCloudProjectId: string;
  intendedCloudProjectId?: string | null;
  snapshotId: string;
  snapshotContentDigest: string;
  parentSnapshotIds: string[];
  expectedSourceDigest: string;
  restoredLocalProjectId?: string | null;
  restoredLocalIncarnation?: string | null;
}

export interface CloudSyncForgetBindingRequest {
  localProjectId: string;
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
  retiredLocalProjects: CloudSyncRetiredLocalProject[];
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

function hasCode(error: unknown, code: string): boolean {
  return !!error && typeof error === 'object' && 'code' in error
    && (error as NodeJS.ErrnoException).code === code;
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
  return value.toLowerCase();
}

function validateIdentity(value: unknown, label: string, maxLength = 32768): string {
  if (typeof value !== 'string' || !value.trim() || value.length > maxLength
    || /[\u0000-\u001f]/.test(value)) {
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

function normalizeJson(value: unknown, label: string, maxBytes: number): JsonValue {
  let serialized: string;
  try {
    serialized = JSON.stringify(value);
  } catch {
    throw new Error(`${label} is not valid JSON.`);
  }
  if (serialized === undefined || Buffer.byteLength(serialized, 'utf8') > maxBytes) {
    throw new Error(`${label} exceeds its safety limit.`);
  }
  return JSON.parse(serialized) as JsonValue;
}

function isRecord(value: JsonValue): value is { [key: string]: JsonValue } {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function stableJson(value: JsonValue): JsonValue {
  if (Array.isArray(value)) return value.map(stableJson);
  if (!isRecord(value)) return value;
  const result: { [key: string]: JsonValue } = {};
  for (const key of Object.keys(value).sort()) result[key] = stableJson(value[key]);
  return result;
}

function stableStringify(value: JsonValue): string {
  return JSON.stringify(stableJson(value));
}

function hasPortableProjectIdentity(value: JsonValue | undefined): boolean {
  if (typeof value === 'string') return !!value.trim() && value.length <= 32768;
  return isRecord(value ?? null) && Object.keys(value ?? {}).length > 0;
}

/** Validate the portable snapshot contract emitted by the Pro core. */
export function validateProProjectSnapshot(value: unknown): JsonValue {
  const snapshot = normalizeJson(
    value,
    'The Pro project snapshot',
    MAX_PRO_PROJECT_SNAPSHOT_BYTES,
  );
  if (!isRecord(snapshot)
    || snapshot.format !== PRO_PROJECT_SNAPSHOT_FORMAT
    || snapshot.version !== PRO_PROJECT_SNAPSHOT_VERSION) {
    throw new Error('The project snapshot is not a supported LogosForge Pro snapshot.');
  }
  if (snapshot.schema_version !== undefined
    && (!Number.isSafeInteger(snapshot.schema_version) || Number(snapshot.schema_version) < 1)) {
    throw new Error('The project snapshot schema version is invalid.');
  }
  if (!isRecord(snapshot.project)
    || typeof snapshot.project.title !== 'string'
    || !snapshot.project.title.trim()) {
    throw new Error('The project snapshot discovery summary is invalid.');
  }
  const projectIdentity = snapshot.project.sync_id ?? snapshot.project.identity;
  if (!hasPortableProjectIdentity(projectIdentity)) {
    throw new Error('The project snapshot has no stable sync identity.');
  }
  if (snapshot.project_identity !== undefined) {
    const outerIdentity = validateUuid(snapshot.project_identity, 'Project sync identity');
    if (typeof projectIdentity === 'string'
      && validateUuid(projectIdentity, 'Project discovery sync identity') !== outerIdentity) {
      throw new Error('The project snapshot sync identities do not match.');
    }
  }
  if (snapshot.tables !== undefined && !isRecord(snapshot.tables)) {
    throw new Error('The project snapshot table graph is invalid.');
  }
  if (snapshot.digest !== undefined) validateDigest(snapshot.digest, 'Project snapshot digest');
  return snapshot;
}

/** Canonical transport view: the core digest and any accidental export clock are excluded. */
export function canonicalProProjectSnapshot(value: unknown): string {
  const canonical = normalizeJson(
    validateProProjectSnapshot(value),
    'The Pro project snapshot',
    MAX_PRO_PROJECT_SNAPSHOT_BYTES,
  );
  if (!isRecord(canonical) || !isRecord(canonical.project)) {
    throw new Error('The project snapshot is invalid.');
  }
  delete canonical.digest;
  delete canonical.exportedAt;
  delete canonical.exported_at;
  delete canonical.project_id;
  delete canonical.local_project_id;
  // The current core contract contains no numeric device-local project id.
  // Keep this defensive normalization for compatible future envelopes.
  delete canonical.project.id;
  delete canonical.project.project_id;
  delete canonical.project.localProjectId;
  return stableStringify(canonical);
}

/** Compatibility name used by the renderer/controller contract. */
export const canonicalCloudSyncBundle = canonicalProProjectSnapshot;

/**
 * The core-supplied digest is authoritative and is defined over the canonical
 * payload above (never over its own `digest` field). Returning it avoids a
 * Python/JavaScript integral-float spelling mismatch while the core revalidates
 * the complete payload on every restore.
 */
export function cloudSyncContentDigest(value: unknown): string {
  const snapshot = validateProProjectSnapshot(value);
  if (!isRecord(snapshot)) throw new Error('The project snapshot is invalid.');
  if (snapshot.digest !== undefined) {
    return validateDigest(snapshot.digest, 'Project snapshot digest');
  }
  return createHash('sha256')
    .update(canonicalProProjectSnapshot(snapshot), 'utf8')
    .digest('hex');
}

function projectTitle(bundle: JsonValue): string {
  return isRecord(bundle) && isRecord(bundle.project) && typeof bundle.project.title === 'string'
    ? bundle.project.title
    : 'Untitled Project';
}

function projectSyncIdentity(bundle: JsonValue): string {
  if (!isRecord(bundle) || !isRecord(bundle.project)) {
    throw new Error('The project snapshot has no project payload.');
  }
  const value = bundle.project.sync_id ?? bundle.project.identity;
  if (typeof value !== 'string') {
    throw new Error('The project snapshot sync identity must be a string.');
  }
  return validateIdentity(value, 'Project snapshot sync identity');
}

function snapshotMetadata(
  envelope: CloudSyncSnapshotEnvelope,
  pendingDelivery: boolean,
): CloudSyncSnapshotMetadata {
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
  const raw = normalizeJson(value, 'The cloud snapshot', MAX_PRO_CLOUD_SNAPSHOT_BYTES);
  if (!isRecord(raw)
    || raw.format !== CLOUD_SYNC_SNAPSHOT_FORMAT
    || raw.version !== CLOUD_SYNC_SNAPSHOT_VERSION) {
    throw new Error('The file is not a supported LogosForge Pro cloud snapshot.');
  }
  const cloudProjectId = validateUuid(raw.cloudProjectId, 'Cloud project id');
  const snapshotId = validateUuid(raw.snapshotId, 'Snapshot id');
  const deviceId = validateUuid(raw.deviceId, 'Device id');
  if (!Array.isArray(raw.parentSnapshotIds)
    || raw.parentSnapshotIds.length > MAX_SNAPSHOT_PARENTS) {
    throw new Error('The cloud snapshot has an invalid parent list.');
  }
  const parentSnapshotIds = raw.parentSnapshotIds
    .map((item) => validateUuid(item, 'Parent snapshot id'));
  if (new Set(parentSnapshotIds).size !== parentSnapshotIds.length
    || parentSnapshotIds.includes(snapshotId)) {
    throw new Error('The cloud snapshot has an invalid parent graph.');
  }
  if (!Number.isSafeInteger(raw.generation) || Number(raw.generation) < 0) {
    throw new Error('The cloud snapshot has an invalid generation.');
  }
  const createdAt = validateTimestamp(raw.createdAt, 'Snapshot timestamp');
  const contentDigest = validateDigest(raw.contentDigest, 'Snapshot content digest');
  const bundle = validateProProjectSnapshot(raw.bundle);
  if (cloudSyncContentDigest(bundle) !== contentDigest) {
    throw new Error('The cloud snapshot digest does not match its project data.');
  }
  return {
    format: CLOUD_SYNC_SNAPSHOT_FORMAT,
    version: CLOUD_SYNC_SNAPSHOT_VERSION,
    cloudProjectId,
    snapshotId,
    deviceId,
    parentSnapshotIds,
    generation: Number(raw.generation),
    createdAt,
    contentDigest,
    bundle,
  };
}

function bindingKey(projectId: string, incarnation: string): string {
  return `${projectId}\u0000${incarnation}`;
}

function validateBinding(value: unknown): CloudSyncBinding {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Cloud project binding is invalid.');
  }
  const raw = value as Record<string, unknown>;
  return {
    localProjectId: validateIdentity(raw.localProjectId, 'Local project id'),
    localIncarnation: validateIdentity(raw.localIncarnation, 'Local project incarnation'),
    cloudProjectId: validateUuid(raw.cloudProjectId, 'Cloud project id'),
    lastSnapshotId: raw.lastSnapshotId == null
      ? null
      : validateUuid(raw.lastSnapshotId, 'Last snapshot id'),
    lastContentDigest: raw.lastContentDigest == null
      ? null
      : validateDigest(raw.lastContentDigest, 'Last content digest'),
  };
}

function validateRetired(value: unknown): CloudSyncRetiredLocalProject {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Retired local project identity is invalid.');
  }
  const raw = value as Record<string, unknown>;
  return {
    localProjectId: validateIdentity(raw.localProjectId, 'Retired local project id'),
    localIncarnation: validateIdentity(raw.localIncarnation, 'Retired local project incarnation'),
    expectedContentDigest: raw.expectedContentDigest == null
      ? null
      : validateDigest(raw.expectedContentDigest, 'Retired local project digest'),
  };
}

function validateActionKind(value: unknown): CloudSyncActionKind {
  if (typeof value !== 'string' || !ACTION_KINDS.has(value as CloudSyncActionKind)) {
    throw new Error('Cloud sync action kind is invalid.');
  }
  return value as CloudSyncActionKind;
}

function validateActionPhase(value: unknown): CloudSyncActionPhase {
  if (typeof value !== 'string' || !ACTION_PHASES.has(value as CloudSyncActionPhase)) {
    throw new Error('Cloud sync action phase is invalid.');
  }
  return value as CloudSyncActionPhase;
}

function validateNullableIdentityPair(
  projectIdValue: unknown,
  incarnationValue: unknown,
  label: string,
): { projectId: string | null; incarnation: string | null } {
  if (projectIdValue == null && incarnationValue == null) {
    return { projectId: null, incarnation: null };
  }
  if (projectIdValue == null || incarnationValue == null) {
    throw new Error(`${label} identity must be complete.`);
  }
  return {
    projectId: validateIdentity(projectIdValue, `${label} project id`),
    incarnation: validateIdentity(incarnationValue, `${label} project incarnation`),
  };
}

function validateActionReceipt(value: unknown): CloudSyncActionReceipt {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Cloud sync action receipt is invalid.');
  }
  const raw = value as Record<string, unknown>;
  const restored = validateNullableIdentityPair(
    raw.restoredLocalProjectId,
    raw.restoredLocalIncarnation,
    'Restored local',
  );
  if (!Array.isArray(raw.parentSnapshotIds)
    || raw.parentSnapshotIds.length > MAX_SNAPSHOT_PARENTS) {
    throw new Error('Cloud sync action parent snapshots are invalid.');
  }
  const parentSnapshotIds = raw.parentSnapshotIds
    .map((item) => validateUuid(item, 'Action parent snapshot id'));
  if (new Set(parentSnapshotIds).size !== parentSnapshotIds.length) {
    throw new Error('Cloud sync action parent snapshots are invalid.');
  }
  const receipt: CloudSyncActionReceipt = {
    actionId: validateUuid(raw.actionId, 'Cloud sync action id'),
    kind: validateActionKind(raw.kind),
    phase: validateActionPhase(raw.phase),
    sourceLocalProjectId: validateIdentity(raw.sourceLocalProjectId, 'Action source project id'),
    sourceLocalIncarnation: validateIdentity(raw.sourceLocalIncarnation, 'Action source incarnation'),
    originalCloudProjectId: validateUuid(raw.originalCloudProjectId, 'Original cloud project id'),
    intendedCloudProjectId: raw.intendedCloudProjectId == null
      ? null
      : validateUuid(raw.intendedCloudProjectId, 'Intended cloud project id'),
    snapshotId: validateUuid(raw.snapshotId, 'Action snapshot id'),
    snapshotContentDigest: validateDigest(raw.snapshotContentDigest, 'Action snapshot digest'),
    parentSnapshotIds,
    expectedSourceDigest: validateDigest(raw.expectedSourceDigest, 'Action source digest'),
    restoredLocalProjectId: restored.projectId,
    restoredLocalIncarnation: restored.incarnation,
    createdAt: validateTimestamp(raw.createdAt, 'Action creation timestamp'),
    updatedAt: validateTimestamp(raw.updatedAt, 'Action update timestamp'),
  };
  if (!['keep-both', 'use-cloud'].includes(receipt.kind) && receipt.phase === 'local-forked') {
    throw new Error('This cloud sync action cannot enter the local-forked phase.');
  }
  if (ACTION_PHASE_ORDER[receipt.phase] >= ACTION_PHASE_ORDER.restored
    && !receipt.restoredLocalProjectId) {
    throw new Error('A restored cloud sync action must name its restored project.');
  }
  return receipt;
}

function validateRecovered(value: unknown): CloudSyncRecoveredRemoteHeads {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Recovered remote heads entry is invalid.');
  }
  const raw = value as Record<string, unknown>;
  if (!Array.isArray(raw.snapshotIds) || raw.snapshotIds.length === 0
    || raw.snapshotIds.length > MAX_RECOVERED_HEADS_PER_PROJECT) {
    throw new Error('Recovered remote head snapshot list is invalid.');
  }
  const snapshotIds = raw.snapshotIds
    .map((item) => validateUuid(item, 'Recovered remote snapshot id'));
  if (new Set(snapshotIds).size !== snapshotIds.length) {
    throw new Error('Recovered remote head snapshot list has duplicates.');
  }
  return {
    cloudProjectId: validateUuid(raw.cloudProjectId, 'Recovered remote project id'),
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
    retiredLocalProjects: [],
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
  if (raw.folderPath !== null
    && (typeof raw.folderPath !== 'string' || !path.isAbsolute(raw.folderPath))) {
    throw new Error('The cloud sync folder path is invalid.');
  }
  if (typeof raw.enabled !== 'boolean' || typeof raw.automatic !== 'boolean') {
    throw new Error('The cloud sync configuration flags are invalid.');
  }
  if (!Array.isArray(raw.bindings) || !Array.isArray(raw.retiredLocalProjects)
    || !Array.isArray(raw.ignoredCloudProjectIds)) {
    throw new Error('The cloud sync configuration collections are invalid.');
  }
  const bindings = raw.bindings.map(validateBinding);
  const bindingKeys = bindings.map((item) => bindingKey(item.localProjectId, item.localIncarnation));
  if (new Set(bindingKeys).size !== bindings.length
    || new Set(bindings.map((item) => item.cloudProjectId)).size !== bindings.length) {
    throw new Error('The cloud sync configuration has duplicate bindings.');
  }
  const retiredLocalProjects = raw.retiredLocalProjects.map(validateRetired);
  const retiredKeys = retiredLocalProjects
    .map((item) => bindingKey(item.localProjectId, item.localIncarnation));
  if (new Set(retiredKeys).size !== retiredKeys.length
    || retiredKeys.some((key) => bindingKeys.includes(key))) {
    throw new Error('The cloud sync configuration has invalid retirement tombstones.');
  }
  const actionValues = raw.actionReceipts === undefined ? [] : raw.actionReceipts;
  if (!Array.isArray(actionValues) || actionValues.length > MAX_PENDING_ACTION_RECEIPTS) {
    throw new Error('The cloud sync action receipt collection is invalid.');
  }
  const actionReceipts = actionValues.map(validateActionReceipt);
  if (new Set(actionReceipts.map((item) => item.actionId)).size !== actionReceipts.length) {
    throw new Error('The cloud sync configuration has duplicate action receipts.');
  }
  const recoveredValues = raw.recoveredRemoteHeads === undefined ? [] : raw.recoveredRemoteHeads;
  if (!Array.isArray(recoveredValues)
    || recoveredValues.length > MAX_RECOVERED_REMOTE_PROJECTS) {
    throw new Error('The recovered remote heads collection is invalid.');
  }
  const recoveredRemoteHeads = recoveredValues.map(validateRecovered);
  if (new Set(recoveredRemoteHeads.map((item) => item.cloudProjectId)).size
    !== recoveredRemoteHeads.length) {
    throw new Error('The recovered remote heads collection has duplicate projects.');
  }
  const ignoredCloudProjectIds = raw.ignoredCloudProjectIds
    .map((item) => validateUuid(item, 'Ignored cloud project id'));
  if (new Set(ignoredCloudProjectIds).size !== ignoredCloudProjectIds.length) {
    throw new Error('The cloud sync configuration has duplicate ignored projects.');
  }
  return {
    format: CONFIG_FORMAT,
    version: CONFIG_VERSION,
    deviceId: validateUuid(raw.deviceId, 'Device id'),
    folderPath: raw.folderPath === null ? null : path.resolve(String(raw.folderPath)),
    enabled: raw.enabled,
    automatic: raw.automatic,
    bindings,
    retiredLocalProjects,
    actionReceipts,
    recoveredRemoteHeads,
    ignoredCloudProjectIds,
    lastSuccessfulSyncAt: raw.lastSuccessfulSyncAt == null
      ? null
      : validateTimestamp(raw.lastSuccessfulSyncAt, 'Last successful sync timestamp'),
  };
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
  if (!isWithin(parentPath, childPath)) {
    throw new Error('Cloud sync path escaped its authorized folder.');
  }
  try {
    await fs.mkdir(childPath);
  } catch (error) {
    if (!hasCode(error, 'EEXIST')) throw error;
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
  const serializedInput = await readBoundedTextFile(filePath);
  let parsed: unknown;
  try {
    parsed = JSON.parse(serializedInput) as unknown;
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

function compareMetadata(left: CloudSyncSnapshotMetadata, right: CloudSyncSnapshotMetadata): number {
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
  private lastPollFingerprint: string | null = null;
  private listeners = new Set<() => void>();

  constructor(
    private readonly userDataPath: string,
    options: CloudSyncManagerOptions = {},
  ) {
    if (!path.isAbsolute(userDataPath)) {
      throw new Error('Cloud sync userData path must be absolute.');
    }
    this.configPath = path.join(userDataPath, CONFIG_FILE_NAME);
    this.pollIntervalMs = options.pollIntervalMs ?? DEFAULT_POLL_INTERVAL_MS;
    this.now = options.now ?? (() => new Date());
    this.createId = options.createId ?? randomUUID;
    this.config = defaultConfig(validateUuid(this.createId(), 'Device id'));
  }

  async initialize(): Promise<void> {
    if (this.initialized) return;
    await fs.mkdir(this.userDataPath, { recursive: true });
    await requireSafeDirectory(this.userDataPath, 'LogosForge Pro user data');
    try {
      this.config = validateConfig(await readSmallConfig(this.configPath));
    } catch (error) {
      if (!hasCode(error, 'ENOENT')) {
        const quarantine = `${this.configPath}.invalid-${this.now().getTime()}-${this.createId()}`;
        try {
          await fs.rename(this.configPath, quarantine);
        } catch (renameError) {
          if (!hasCode(renameError, 'ENOENT')) throw renameError;
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
    if (this.initialized && this.config.enabled) {
      try { await this.retryOutbox(); } catch { /* durable outbox remains */ }
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
      } catch { /* reflected as false */ }
    }
    return {
      enabled: this.config.enabled,
      automatic: this.config.automatic,
      folderPath: this.config.folderPath,
      folderAvailable,
      deviceId: this.config.deviceId,
      bindings: this.config.bindings.map((item) => ({ ...item })),
      retiredLocalProjects: this.config.retiredLocalProjects.map((item) => ({ ...item })),
      actionReceipts: this.config.actionReceipts.map((item) => ({
        ...item,
        parentSnapshotIds: [...item.parentSnapshotIds],
      })),
      recoveredRemoteHeads: this.config.recoveredRemoteHeads.map((item) => ({
        cloudProjectId: item.cloudProjectId,
        snapshotIds: [...item.snapshotIds],
      })),
      ignoredCloudProjectIds: [...this.config.ignoredCloudProjectIds],
      pendingDeliveries: inventory.projects.flatMap((item) => item.snapshots)
        .filter((item) => item.pendingDelivery).length,
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

  async setFolder(folderPathValue: string): Promise<CloudSyncState> {
    return this.exclusive(async () => {
      const folderPath = path.resolve(validateIdentity(folderPathValue, 'Cloud folder path'));
      await requireSafeDirectory(folderPath, 'The selected sync folder');
      await this.ensureCloudProjectsDirectory(folderPath);
      this.config.folderPath = folderPath;
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
      if (typeof automatic !== 'boolean') throw new Error('Automatic cloud sync flag is invalid.');
      if (automatic && (!this.config.enabled || !this.config.folderPath)) {
        throw new Error('Choose and enable a cloud folder first.');
      }
      this.config.automatic = automatic;
      await this.saveConfig();
      this.emitChanged();
      return this.getState();
    });
  }

  computeDigest(bundle: unknown): string {
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
      await this.requireBindingBaseline(binding);
      this.clearRetired(binding.localProjectId, binding.localIncarnation);
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
      const fromProjectId = validateIdentity(request?.fromLocalProjectId, 'Source project id');
      const fromIncarnation = validateIdentity(request?.fromLocalIncarnation, 'Source incarnation');
      const toProjectId = validateIdentity(request?.toLocalProjectId, 'Destination project id');
      const toIncarnation = validateIdentity(request?.toLocalIncarnation, 'Destination incarnation');
      const sourceIndex = this.bindingIndex(fromProjectId, fromIncarnation);
      if (sourceIndex < 0) throw new Error('The source project has no cloud binding.');
      const destinationIndex = this.bindingIndex(toProjectId, toIncarnation);
      if (destinationIndex >= 0 && destinationIndex !== sourceIndex) {
        throw new Error('The destination project already has a cloud binding.');
      }
      const source = this.config.bindings[sourceIndex];
      const moved: CloudSyncBinding = {
        ...source,
        localProjectId: toProjectId,
        localIncarnation: toIncarnation,
        lastSnapshotId: request.lastSnapshotId === undefined
          ? source.lastSnapshotId
          : request.lastSnapshotId == null
            ? null
            : validateUuid(request.lastSnapshotId, 'Last snapshot id'),
        lastContentDigest: request.lastContentDigest === undefined
          ? source.lastContentDigest
          : request.lastContentDigest == null
            ? null
            : validateDigest(request.lastContentDigest, 'Last content digest'),
      };
      const expectedDigest = request.expectedRetiredContentDigest === undefined
        ? source.lastContentDigest
        : request.expectedRetiredContentDigest == null
          ? null
          : validateDigest(request.expectedRetiredContentDigest, 'Retired project digest');
      await this.requireBindingBaseline(moved);
      this.config.bindings.splice(sourceIndex, 1);
      this.retire(fromProjectId, fromIncarnation, expectedDigest);
      this.clearRetired(toProjectId, toIncarnation);
      this.upsertBinding(moved);
      await this.saveConfig();
      this.emitChanged();
      return { ...moved };
    });
  }

  async saveActionReceipt(
    request: CloudSyncSaveActionReceiptRequest,
  ): Promise<CloudSyncActionReceipt> {
    return this.exclusive(async () => {
      const now = this.now().toISOString();
      const restored = validateNullableIdentityPair(
        request?.restoredLocalProjectId,
        request?.restoredLocalIncarnation,
        'Restored local',
      );
      const candidate = validateActionReceipt({
        ...request,
        intendedCloudProjectId: request?.intendedCloudProjectId ?? null,
        restoredLocalProjectId: restored.projectId,
        restoredLocalIncarnation: restored.incarnation,
        createdAt: now,
        updatedAt: now,
      });
      const index = this.config.actionReceipts
        .findIndex((item) => item.actionId === candidate.actionId);
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
        const sameParents = existing.parentSnapshotIds.length === candidate.parentSnapshotIds.length
          && existing.parentSnapshotIds.every((id, i) => id === candidate.parentSnapshotIds[i]);
        if (existing.kind !== candidate.kind
          || existing.sourceLocalProjectId !== candidate.sourceLocalProjectId
          || existing.sourceLocalIncarnation !== candidate.sourceLocalIncarnation
          || existing.originalCloudProjectId !== candidate.originalCloudProjectId
          || existing.snapshotId !== candidate.snapshotId
          || existing.snapshotContentDigest !== candidate.snapshotContentDigest
          || existing.expectedSourceDigest !== candidate.expectedSourceDigest
          || !sameParents) {
          throw new Error('Cloud sync action identity cannot change while it is pending.');
        }
        if (ACTION_PHASE_ORDER[candidate.phase] < ACTION_PHASE_ORDER[existing.phase]) {
          throw new Error('Cloud sync action phase cannot move backwards.');
        }
        if (existing.intendedCloudProjectId && candidate.intendedCloudProjectId
          && existing.intendedCloudProjectId !== candidate.intendedCloudProjectId) {
          throw new Error('Cloud sync action destination cannot change while it is pending.');
        }
        if (existing.restoredLocalProjectId && candidate.restoredLocalProjectId
          && (existing.restoredLocalProjectId !== candidate.restoredLocalProjectId
            || existing.restoredLocalIncarnation !== candidate.restoredLocalIncarnation)) {
          throw new Error('Cloud sync restored project identity cannot change while it is pending.');
        }
        this.config.actionReceipts[index] = validateActionReceipt({
          ...candidate,
          intendedCloudProjectId: candidate.intendedCloudProjectId
            ?? existing.intendedCloudProjectId,
          restoredLocalProjectId: candidate.restoredLocalProjectId
            ?? existing.restoredLocalProjectId,
          restoredLocalIncarnation: candidate.restoredLocalIncarnation
            ?? existing.restoredLocalIncarnation,
          createdAt: existing.createdAt,
          updatedAt: now,
        });
      }
      await this.saveConfig();
      this.emitChanged();
      const saved = this.config.actionReceipts.find((item) => item.actionId === candidate.actionId);
      if (!saved) throw new Error('Cloud sync action receipt could not be saved.');
      return { ...saved, parentSnapshotIds: [...saved.parentSnapshotIds] };
    });
  }

  async completeActionReceipt(actionIdValue: string): Promise<boolean> {
    return this.exclusive(async () => {
      const actionId = validateUuid(actionIdValue, 'Cloud sync action id');
      const before = this.config.actionReceipts.length;
      this.config.actionReceipts = this.config.actionReceipts
        .filter((item) => item.actionId !== actionId);
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
      const incoming = validateRecovered({
        cloudProjectId: cloudProjectIdValue,
        snapshotIds: snapshotIdValues,
      });
      const index = this.config.recoveredRemoteHeads
        .findIndex((item) => item.cloudProjectId === incoming.cloudProjectId);
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
      const saved = this.config.recoveredRemoteHeads
        .find((item) => item.cloudProjectId === incoming.cloudProjectId);
      if (!saved) throw new Error('Recovered remote heads could not be recorded.');
      return { cloudProjectId: saved.cloudProjectId, snapshotIds: [...saved.snapshotIds] };
    });
  }

  async clearRecoveredRemoteHeads(cloudProjectIdValue: string): Promise<boolean> {
    return this.exclusive(async () => {
      const cloudProjectId = validateUuid(cloudProjectIdValue, 'Recovered cloud project id');
      const before = this.config.recoveredRemoteHeads.length;
      this.config.recoveredRemoteHeads = this.config.recoveredRemoteHeads
        .filter((item) => item.cloudProjectId !== cloudProjectId);
      if (before === this.config.recoveredRemoteHeads.length) return false;
      await this.saveConfig();
      this.emitChanged();
      return true;
    });
  }

  /** Remove one recovered head without racing away its siblings. */
  async removeRecoveredRemoteHead(
    cloudProjectIdValue: string,
    snapshotIdValue: string,
  ): Promise<boolean> {
    return this.exclusive(async () => {
      const cloudProjectId = validateUuid(cloudProjectIdValue, 'Recovered cloud project id');
      const snapshotId = validateUuid(snapshotIdValue, 'Recovered snapshot id');
      const projectIndex = this.config.recoveredRemoteHeads
        .findIndex((item) => item.cloudProjectId === cloudProjectId);
      if (projectIndex < 0) return false;
      const project = this.config.recoveredRemoteHeads[projectIndex];
      const snapshotIds = project.snapshotIds.filter((id) => id !== snapshotId);
      if (snapshotIds.length === project.snapshotIds.length) return false;
      if (snapshotIds.length === 0) {
        this.config.recoveredRemoteHeads.splice(projectIndex, 1);
      } else {
        this.config.recoveredRemoteHeads[projectIndex] = { cloudProjectId, snapshotIds };
      }
      await this.saveConfig();
      this.emitChanged();
      return true;
    });
  }

  async forgetBinding(request: CloudSyncForgetBindingRequest): Promise<boolean> {
    return this.exclusive(async () => {
      const localProjectId = validateIdentity(request?.localProjectId, 'Local project id');
      const incarnation = validateIdentity(request?.localIncarnation, 'Local project incarnation');
      const index = this.bindingIndex(localProjectId, incarnation);
      const existing = index >= 0 ? this.config.bindings[index] : null;
      const retired = this.clearRetired(localProjectId, incarnation);
      const cloudProjectId = request.cloudProjectId == null
        ? existing?.cloudProjectId ?? null
        : validateUuid(request.cloudProjectId, 'Cloud project id');
      if (existing && cloudProjectId && existing.cloudProjectId !== cloudProjectId) {
        throw new Error('The project cloud binding changed before it could be forgotten.');
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
    const localProjectId = validateIdentity(request?.localProjectId, 'Local project id');
    const localIncarnation = validateIdentity(request?.localIncarnation, 'Local project incarnation');
    if (this.isRetired(localProjectId, localIncarnation)) {
      throw new Error('This superseded local project is retired from cloud sync.');
    }
    const bundle = validateProProjectSnapshot(request?.bundle);
    const bundleIdentity = projectSyncIdentity(bundle);
    if (bundleIdentity !== localIncarnation) {
      throw new Error('The local project incarnation does not match its snapshot sync identity.');
    }
    const contentDigest = cloudSyncContentDigest(bundle);
    const existingIndex = this.bindingIndex(localProjectId, localIncarnation);
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
    if (existing && requestedCloudProjectId
      && requestedCloudProjectId !== existing.cloudProjectId
      && request.createNewProject !== true) {
      throw new Error('The local project is already bound to another cloud project.');
    }

    // A process can stop after the immutable outbox write but before the
    // binding config rename. Recover only a unique pending root written by
    // this device with the exact portable identity and digest. Provider files
    // are intentionally excluded: delivery happens only after config commit.
    if (request.createNewProject === true && !requestedNewCloudProjectId) {
      const orphan = await this.findRecoverableOutboxPublish(
        null,
        [],
        contentDigest,
        bundleIdentity,
      );
      if (orphan) {
        return this.adoptRecoverableOutboxPublish(
          localProjectId,
          localIncarnation,
          orphan,
        );
      }
    }
    const cloudProjectId = request.createNewProject === true
      ? requestedNewCloudProjectId ?? validateUuid(this.createId(), 'Cloud project id')
      : existing?.cloudProjectId
        ?? requestedCloudProjectId
        ?? validateUuid(this.createId(), 'Cloud project id');

    // Replaying a fork after an app crash must recover the exact preallocated
    // immutable root rather than create a second logical project.
    if (request.createNewProject === true && requestedNewCloudProjectId) {
      const inventory = await this.scanInventory();
      const priorProject = inventory.projects
        .find((item) => item.cloudProjectId === requestedNewCloudProjectId);
      if (priorProject) {
        const roots = priorProject.snapshots.filter((item) => (
          item.parentSnapshotIds.length === 0 && item.contentDigest === contentDigest
        ));
        if (priorProject.snapshots.length !== 1 || roots.length !== 1) {
          throw new Error('The preallocated cloud project id is already used by different history.');
        }
        const prior = roots[0];
        const recoveredBinding: CloudSyncBinding = {
          localProjectId,
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
    if (request.createNewProject === true && explicitParents
      && request.parentSnapshotIds?.length) {
      throw new Error('A new cloud project cannot inherit another project\'s snapshots.');
    }
    if (!explicitParents && request.createNewProject !== true
      && existing?.lastSnapshotId && existing.lastContentDigest === contentDigest) {
      const prior = await this.findSnapshot(cloudProjectId, existing.lastSnapshotId);
      if (prior) {
        if (projectSyncIdentity(prior.envelope.bundle) !== bundleIdentity) {
          throw new Error('The existing cloud binding belongs to another project identity.');
        }
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
      if (projectSyncIdentity(parent.envelope.bundle) !== bundleIdentity) {
        throw new Error('A cloud snapshot cannot inherit history from another project identity.');
      }
      parentSnapshots.push(parent);
    }
    if (request.createNewProject !== true) {
      const orphan = await this.findRecoverableOutboxPublish(
        cloudProjectId,
        parentSnapshotIds,
        contentDigest,
        bundleIdentity,
      );
      if (orphan) {
        return this.adoptRecoverableOutboxPublish(
          localProjectId,
          localIncarnation,
          orphan,
        );
      }
    }
    const generation = parentSnapshots.length
      ? Math.max(...parentSnapshots.map((item) => item.envelope.generation)) + 1
      : 0;
    if (!Number.isSafeInteger(generation)) {
      throw new Error('The cloud snapshot generation exceeds the safe transport limit.');
    }
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
    if (Buffer.byteLength(serialized, 'utf8') > MAX_PRO_CLOUD_SNAPSHOT_BYTES) {
      throw new Error('The cloud snapshot exceeds the 129 MiB transport safety limit.');
    }
    const outboxPath = await this.outboxSnapshotPath(envelope, true);
    await atomicWriteTextFile(outboxPath, serialized);

    const binding: CloudSyncBinding = {
      localProjectId,
      localIncarnation,
      cloudProjectId,
      lastSnapshotId: snapshotId,
      lastContentDigest: contentDigest,
    };
    this.upsertBinding(binding);
    this.config.ignoredCloudProjectIds = this.config.ignoredCloudProjectIds
      .filter((id) => id !== cloudProjectId);
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
    if (new Set(parents).size !== parents.length) {
      throw new Error('Snapshot parent list has duplicates.');
    }
    return parents;
  }

  private async findRecoverableOutboxPublish(
    cloudProjectId: string | null,
    parentSnapshotIds: string[],
    contentDigest: string,
    projectIdentity: string,
  ): Promise<LocatedSnapshot | null> {
    const snapshots = await this.scanSnapshotTree(
      await this.outboxProjectsPath(),
      'outbox',
      [],
    );
    const expectedParents = [...parentSnapshotIds].sort();
    const matches = snapshots.filter((snapshot) => (
      (cloudProjectId === null || snapshot.envelope.cloudProjectId === cloudProjectId)
      && snapshot.envelope.deviceId === this.config.deviceId
      && snapshot.envelope.contentDigest === contentDigest
      && projectSyncIdentity(snapshot.envelope.bundle) === projectIdentity
      && snapshot.envelope.parentSnapshotIds.length === expectedParents.length
      && [...snapshot.envelope.parentSnapshotIds].sort()
        .every((id, index) => id === expectedParents[index])
    ));
    if (matches.length > 1) {
      throw new Error('Multiple pending snapshots match this publish retry; resolve the outbox first.');
    }
    return matches[0] ?? null;
  }

  private async adoptRecoverableOutboxPublish(
    localProjectId: string,
    localIncarnation: string,
    snapshot: LocatedSnapshot,
  ): Promise<CloudSyncPublishResult> {
    const binding: CloudSyncBinding = {
      localProjectId,
      localIncarnation,
      cloudProjectId: snapshot.envelope.cloudProjectId,
      lastSnapshotId: snapshot.envelope.snapshotId,
      lastContentDigest: snapshot.envelope.contentDigest,
    };
    this.upsertBinding(binding);
    this.config.ignoredCloudProjectIds = this.config.ignoredCloudProjectIds
      .filter((id) => id !== binding.cloudProjectId);
    // Persist the recovered binding before attempting provider delivery. A
    // second stop can therefore replay either the binding or the same outbox.
    await this.saveConfig();
    let delivered = false;
    try {
      await this.deliverOne(
        snapshot.envelope,
        snapshot.serialized,
        await this.outboxSnapshotPath(snapshot.envelope, false),
      );
      delivered = true;
      this.config.lastSuccessfulSyncAt = this.now().toISOString();
      this.lastError = null;
      await this.saveConfig();
    } catch (error) {
      this.lastError = errorMessage(error);
    }
    this.emitChanged();
    return {
      created: false,
      delivered,
      binding: { ...binding },
      snapshot: snapshotMetadata(snapshot.envelope, !delivered),
    };
  }

  private async requireBindingBaseline(binding: CloudSyncBinding): Promise<LocatedSnapshot> {
    if (!binding.lastSnapshotId || !binding.lastContentDigest) {
      throw new Error('A cloud binding requires a complete snapshot baseline.');
    }
    const snapshot = await this.findSnapshot(binding.cloudProjectId, binding.lastSnapshotId);
    if (!snapshot) throw new Error('The cloud binding snapshot is not available on this device.');
    if (snapshot.envelope.contentDigest !== binding.lastContentDigest) {
      throw new Error('The cloud binding digest does not match its snapshot.');
    }
    if (projectSyncIdentity(snapshot.envelope.bundle) !== binding.localIncarnation) {
      throw new Error('The cloud binding project identity does not match the local incarnation.');
    }
    return snapshot;
  }

  private async deliverOutboxUnlocked(): Promise<{ delivered: number; pending: number }> {
    if (!this.config.enabled || !this.config.folderPath) {
      const pending = (await this.scanSnapshotTree(
        await this.outboxProjectsPath(), 'outbox', [],
      )).length;
      return { delivered: 0, pending };
    }
    this.syncing = true;
    let delivered = 0;
    let lastFailure: unknown = null;
    try {
      const snapshots = await this.scanSnapshotTree(
        await this.outboxProjectsPath(), 'outbox', [],
      );
      for (const snapshot of snapshots) {
        const outboxPath = await this.outboxSnapshotPath(snapshot.envelope, false);
        try {
          await this.deliverOne(snapshot.envelope, snapshot.serialized, outboxPath);
          delivered += 1;
        } catch (error) {
          lastFailure = error;
        }
      }
      const pending = (await this.scanSnapshotTree(
        await this.outboxProjectsPath(), 'outbox', [],
      )).length;
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
    const verifyDestination = async (): Promise<void> => {
      const raw = await readBoundedTextFile(destination);
      let parsed: unknown;
      try { parsed = JSON.parse(raw) as unknown; } catch {
        throw new Error('An immutable cloud snapshot destination contains invalid JSON.');
      }
      validateCloudSyncSnapshot(parsed);
      if (raw !== serialized) {
        throw new Error('A different cloud snapshot already uses the same immutable id.');
      }
    };
    try {
      await verifyDestination();
    } catch (error) {
      if (!hasCode(error, 'ENOENT')) throw error;
      // A replacing rename is not an immutable commit: another device could
      // create the destination after the existence check and be overwritten.
      // Publish a fully-fsynced same-directory staging inode, then hard-link it
      // into the final name. The link is atomic and refuses existing names.
      const staging = path.join(
        path.dirname(destination),
        `.${envelope.snapshotId}.${envelope.deviceId}.staging`,
      );
      if (!isWithin(path.dirname(destination), staging)) {
        throw new Error('Cloud staging path escaped its snapshot folder.');
      }
      await atomicWriteTextFile(staging, serialized);
      try {
        try {
          await fs.link(staging, destination);
        } catch (linkError) {
          if (!hasCode(linkError, 'EEXIST')) {
            throw new Error(
              `The selected folder cannot safely commit immutable snapshots: ${errorMessage(linkError)}`,
            );
          }
          // A concurrent writer won the name. Exact bytes are idempotent;
          // differing bytes remain queued and are never overwritten.
        }
        await verifyDestination();
      } finally {
        try { await fs.unlink(staging); } catch (cleanupError) {
          if (!hasCode(cleanupError, 'ENOENT')) {
            console.error('[cloud-sync] could not remove a provider staging file:', cleanupError);
          }
        }
      }
    }
    // On POSIX, an fsynced staging inode is not enough: the immutable hard-link
    // name itself is directory metadata. Flush that directory before deleting
    // the only durable retry record from the local outbox. Windows does not
    // support opening directory handles portably; link() is the atomic commit
    // primitive there and the local outbox remains until verification succeeds.
    if (process.platform !== 'win32') {
      const directory = await fs.open(path.dirname(destination), 'r');
      try {
        await directory.sync();
      } finally {
        await directory.close();
      }
    }
    try {
      await fs.unlink(outboxPath);
    } catch (error) {
      if (!hasCode(error, 'ENOENT')) throw error;
    }
  }

  private async scanInventory(): Promise<CloudSyncInventory> {
    const warnings: string[] = [];
    const located: LocatedSnapshot[] = [];
    try {
      located.push(...await this.scanSnapshotTree(
        await this.outboxProjectsPath(), 'outbox', warnings,
      ));
    } catch (error) {
      warnings.push(`The local cloud outbox could not be read: ${errorMessage(error)}`);
    }
    if (this.config.enabled && this.config.folderPath) {
      try {
        const projectsPath = await this.cloudProjectsPath(false);
        if (projectsPath) {
          located.push(...await this.scanSnapshotTree(projectsPath, 'cloud', warnings));
        }
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
      } else if (existing.source === 'outbox' && item.source === 'cloud') {
        project.set(item.envelope.snapshotId, item);
      }
    }

    const projects: CloudSyncProjectInventory[] = [];
    for (const [cloudProjectId, snapshotMap] of byProject) {
      const rows = [...snapshotMap.values()];
      const parentIds = new Set(rows.flatMap((item) => item.envelope.parentSnapshotIds));
      const snapshots = rows.map((item) => ({
        ...item.metadata,
        pendingDelivery: item.source === 'outbox',
      })).sort(compareMetadata);
      const heads = snapshots.filter((item) => !parentIds.has(item.snapshotId));
      projects.push({
        cloudProjectId,
        projectTitle: heads.at(-1)?.projectTitle
          ?? snapshots.at(-1)?.projectTitle
          ?? 'Untitled Project',
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
      if (hasCode(error, 'ENOENT')) return [];
      throw error;
    }
    const result: LocatedSnapshot[] = [];
    const projectEntries = await fs.readdir(projectsPath, { withFileTypes: true });
    for (const projectEntry of projectEntries) {
      if (!projectEntry.isDirectory() || projectEntry.isSymbolicLink()
        || !UUID_PATTERN.test(projectEntry.name)) continue;
      const cloudProjectId = projectEntry.name.toLowerCase();
      const projectPath = path.join(projectsPath, projectEntry.name);
      const snapshotsPath = path.join(projectPath, 'snapshots');
      try {
        await requireSafeDirectory(projectPath, 'A cloud project folder');
        await requireSafeDirectory(snapshotsPath, 'A cloud snapshots folder');
      } catch (error) {
        if (!hasCode(error, 'ENOENT')) {
          warnings.push(`Cloud project ${cloudProjectId} has an unsafe snapshots folder.`);
        }
        continue;
      }
      const entries = await fs.readdir(snapshotsPath, { withFileTypes: true });
      for (const entry of entries) {
        if (result.length >= MAX_SNAPSHOT_FILES) {
          warnings.push(`Cloud snapshot scan stopped at the ${MAX_SNAPSHOT_FILES}-file safety limit.`);
          return result;
        }
        if (!entry.isFile() || entry.isSymbolicLink() || !entry.name.endsWith('.lfsync')) continue;
        const filePath = path.join(snapshotsPath, entry.name);
        try {
          const snapshot = await readSnapshotFile(filePath);
          const expectedFileName = `${snapshot.envelope.snapshotId}.lfsync`;
          if (snapshot.envelope.cloudProjectId !== cloudProjectId) {
            throw new Error('Snapshot project id does not match its directory.');
          }
          if (entry.name.toLowerCase() !== expectedFileName) {
            throw new Error('Snapshot id does not match its file name.');
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

  private async findSnapshot(
    cloudProjectId: string,
    snapshotId: string,
  ): Promise<LocatedSnapshot | null> {
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
      filePath = await this.snapshotPathFromIds(
        await this.outboxProjectsPath(), cloudProjectId, snapshotId,
      );
    } else {
      const projectsPath = await this.cloudProjectsPath(false);
      if (!projectsPath) return null;
      filePath = await this.snapshotPathFromIds(projectsPath, cloudProjectId, snapshotId);
    }
    try {
      const result = await readSnapshotFile(filePath);
      if (result.envelope.cloudProjectId !== cloudProjectId
        || result.envelope.snapshotId !== snapshotId) {
        throw new Error('Snapshot identity does not match its file name.');
      }
      result.source = source;
      result.metadata.pendingDelivery = source === 'outbox';
      return result;
    } catch (error) {
      if (hasCode(error, 'ENOENT')) return null;
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
    if (!isWithin(projectsPath, result)) {
      throw new Error('Cloud snapshot path escaped its authorized folder.');
    }
    return result;
  }

  private async outboxSnapshotPath(
    envelope: CloudSyncSnapshotEnvelope,
    create: boolean,
  ): Promise<string> {
    const projects = await this.outboxProjectsPath();
    if (create) await this.ensureProjectSnapshotDirectory(projects, envelope.cloudProjectId);
    return this.snapshotPathFromIds(projects, envelope.cloudProjectId, envelope.snapshotId);
  }

  private async cloudSnapshotPath(
    envelope: CloudSyncSnapshotEnvelope,
    create: boolean,
  ): Promise<string> {
    const projects = await this.cloudProjectsPath(create);
    if (!projects) throw new Error('The selected cloud folder is unavailable.');
    if (create) await this.ensureProjectSnapshotDirectory(projects, envelope.cloudProjectId);
    return this.snapshotPathFromIds(projects, envelope.cloudProjectId, envelope.snapshotId);
  }

  private async ensureProjectSnapshotDirectory(
    projectsPath: string,
    cloudProjectIdValue: string,
  ): Promise<string> {
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
    if (!isWithin(this.config.folderPath, projects)) {
      throw new Error('Cloud sync path escaped its selected folder.');
    }
    await requireSafeDirectory(productRoot, 'The Pro cloud folder');
    await requireSafeDirectory(projects, 'The Pro cloud projects folder');
    return projects;
  }

  private isRetired(projectId: string, incarnation: string): boolean {
    const key = bindingKey(projectId, incarnation);
    return this.config.retiredLocalProjects.some((item) => (
      bindingKey(item.localProjectId, item.localIncarnation) === key
    ));
  }

  private retire(
    projectId: string,
    incarnation: string,
    expectedContentDigest: string | null,
  ): void {
    const key = bindingKey(projectId, incarnation);
    const existing = this.config.retiredLocalProjects.find((item) => (
      bindingKey(item.localProjectId, item.localIncarnation) === key
    ));
    if (existing) {
      if (existing.expectedContentDigest === null && expectedContentDigest !== null) {
        existing.expectedContentDigest = validateDigest(
          expectedContentDigest, 'Retired project digest',
        );
      } else if (existing.expectedContentDigest !== null && expectedContentDigest !== null
        && existing.expectedContentDigest !== expectedContentDigest) {
        throw new Error('Retired local project digest changed during ownership transfer.');
      }
      return;
    }
    this.config.retiredLocalProjects.push({
      localProjectId: projectId,
      localIncarnation: incarnation,
      expectedContentDigest: expectedContentDigest == null
        ? null
        : validateDigest(expectedContentDigest, 'Retired project digest'),
    });
  }

  private clearRetired(projectId: string, incarnation: string): boolean {
    const key = bindingKey(projectId, incarnation);
    const before = this.config.retiredLocalProjects.length;
    this.config.retiredLocalProjects = this.config.retiredLocalProjects.filter((item) => (
      bindingKey(item.localProjectId, item.localIncarnation) !== key
    ));
    return this.config.retiredLocalProjects.length !== before;
  }

  private bindingIndex(projectId: string, incarnation: string): number {
    const key = bindingKey(projectId, incarnation);
    return this.config.bindings.findIndex((item) => (
      bindingKey(item.localProjectId, item.localIncarnation) === key
    ));
  }

  private upsertBinding(binding: CloudSyncBinding): void {
    for (const candidate of this.config.bindings) {
      if (candidate.cloudProjectId === binding.cloudProjectId
        && bindingKey(candidate.localProjectId, candidate.localIncarnation)
          !== bindingKey(binding.localProjectId, binding.localIncarnation)) {
        this.retire(
          candidate.localProjectId,
          candidate.localIncarnation,
          candidate.lastContentDigest,
        );
      }
    }
    this.config.bindings = this.config.bindings.filter((candidate) => (
      candidate.cloudProjectId !== binding.cloudProjectId
      || bindingKey(candidate.localProjectId, candidate.localIncarnation)
        === bindingKey(binding.localProjectId, binding.localIncarnation)
    ));
    const index = this.bindingIndex(binding.localProjectId, binding.localIncarnation);
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
      if (!this.config.enabled) return;
      await this.exclusive(async () => {
        await this.deliverOutboxUnlocked();
        const inventory = await this.scanInventory();
        const fingerprint = createHash('sha256').update(JSON.stringify({
          projects: inventory.projects,
          warnings: [...inventory.warnings].sort(),
          lastError: this.lastError,
        })).digest('hex');
        if (fingerprint !== this.lastPollFingerprint) {
          this.lastPollFingerprint = fingerprint;
          this.emitChanged();
        }
      });
    } catch (error) {
      const next = errorMessage(error);
      this.lastError = next;
      const fingerprint = createHash('sha256')
        .update(JSON.stringify({ fatalPollError: next }))
        .digest('hex');
      if (fingerprint !== this.lastPollFingerprint) {
        this.lastPollFingerprint = fingerprint;
        this.emitChanged();
      }
    } finally {
      this.pollInFlight = false;
    }
  }

  private exclusive<T>(operation: () => Promise<T>): Promise<T> {
    const previous = this.mutationTail;
    let release!: () => void;
    this.mutationTail = new Promise<void>((resolve) => { release = resolve; });
    return previous.then(operation).finally(release);
  }

  private assertInitialized(): void {
    if (!this.initialized) throw new Error('Cloud sync manager has not initialized.');
  }

  private emitChanged(): void {
    for (const listener of [...this.listeners]) {
      try { listener(); } catch { /* observers cannot break persistence */ }
    }
  }
}
