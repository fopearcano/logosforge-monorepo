import type {
  ProgressionAnchorKind,
  ProgressionCommand,
  ProgressionCommandReceipt,
  ProgressionCommandResult,
  ProgressionCoverageStatus,
  ProgressionKind,
  ProgressionSnapshot,
} from './types';

type Row = Record<string, unknown>;
const KINDS: ProgressionKind[] = ['story', 'character', 'relationship', 'theme', 'world', 'custom'];
const ANCHORS: ProgressionAnchorKind[] = ['unanchored', 'scene', 'document_block'];
const STATUSES: ProgressionCoverageStatus[] = ['empty', 'unanchored', 'partial', 'complete'];
const COMMAND_KINDS: ProgressionCommand['kind'][] = [
  'create_track', 'update_track', 'delete_track', 'reorder_tracks',
  'create_beat', 'update_beat', 'delete_beat', 'reorder_beats',
];
const SHA256 = /^[0-9a-f]{64}$/;

function bad(path: string): never {
  throw new Error(`Invalid Progressions response at ${path}.`);
}

function row(value: unknown, path: string): Row {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Row
    : bad(path);
}

function str(value: unknown, path: string, allowEmpty = true): string {
  return typeof value === 'string' && (allowEmpty || value.trim().length > 0) ? value : bad(path);
}

function int(value: unknown, path: string, positive = false): number {
  return typeof value === 'number' && Number.isSafeInteger(value) && (!positive || value > 0)
    ? value
    : bad(path);
}

function num(value: unknown, path: string): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : bad(path);
}

function bool(value: unknown, path: string): boolean {
  return typeof value === 'boolean' ? value : bad(path);
}

function nullable<T>(value: unknown, path: string, parse: (value: unknown, path: string) => T): T | null {
  return value === null ? null : parse(value, path);
}

function list<T>(value: unknown, path: string, parse: (value: unknown, path: string) => T): T[] {
  if (!Array.isArray(value)) return bad(path);
  return value.map((item, index) => parse(item, `${path}[${index}]`));
}

function enumValue<T extends string>(value: unknown, values: readonly T[], path: string): T {
  return typeof value === 'string' && values.includes(value as T) ? value as T : bad(path);
}

function integerMap(value: unknown, path: string): Record<string, number> {
  const object = row(value, path);
  for (const [key, count] of Object.entries(object)) int(count, `${path}.${key}`);
  return object as Record<string, number>;
}

function uniquePositiveIds(value: unknown, path: string): number[] {
  const ids = list(value, path, (item, itemPath) => int(item, itemPath, true));
  if (new Set(ids).size !== ids.length) bad(path);
  return ids;
}

function sha256(value: unknown, path: string): string {
  const digest = str(value, path, false);
  return SHA256.test(digest) ? digest : bad(path);
}

export function validateProgressionSnapshot(
  value: unknown,
  expectedProjectId?: number,
): ProgressionSnapshot {
  const dto = row(value, '$');
  const projectId = int(dto.project_id, '$.project_id', true);
  if (expectedProjectId !== undefined && projectId !== expectedProjectId) bad('$.project_id');
  const revision = str(dto.revision, '$.revision', false);
  if (!/^[0-9a-f]{64}$/.test(revision)) bad('$.revision');
  list(dto.tracks, '$.tracks', (trackValue, trackPath) => {
    const track = row(trackValue, trackPath);
    int(track.id, `${trackPath}.id`, true);
    if (int(track.project_id, `${trackPath}.project_id`, true) !== projectId) bad(`${trackPath}.project_id`);
    const kind = enumValue(track.kind, KINDS, `${trackPath}.kind`);
    str(track.title, `${trackPath}.title`, false);
    str(track.description, `${trackPath}.description`);
    str(track.color_label, `${trackPath}.color_label`);
    int(track.sort_order, `${trackPath}.sort_order`);
    const legacyCompatibility = bool(
      track.legacy_compatibility,
      `${trackPath}.legacy_compatibility`,
    );
    const primaryId = nullable(track.primary_psyke_entry_id, `${trackPath}.primary_psyke_entry_id`, (v, p) => int(v, p, true));
    str(track.primary_psyke_entry_name, `${trackPath}.primary_psyke_entry_name`);
    const primaryType = str(track.primary_psyke_entry_type, `${trackPath}.primary_psyke_entry_type`);
    const secondaryId = nullable(track.secondary_psyke_entry_id, `${trackPath}.secondary_psyke_entry_id`, (v, p) => int(v, p, true));
    str(track.secondary_psyke_entry_name, `${trackPath}.secondary_psyke_entry_name`);
    str(track.secondary_psyke_entry_type, `${trackPath}.secondary_psyke_entry_type`);
    if (legacyCompatibility) {
      const expectedKind = primaryType === 'character'
        ? 'character'
        : primaryType === 'theme'
          ? 'theme'
          : ['place', 'object', 'lore'].includes(primaryType)
            ? 'world'
            : 'custom';
      if (primaryId === null || secondaryId !== null || kind !== expectedKind) bad(trackPath);
    } else if (kind === 'story' || kind === 'custom') {
      if (primaryId !== null || secondaryId !== null) bad(trackPath);
    } else if (kind === 'relationship') {
      if (primaryId === null || secondaryId === null || primaryId === secondaryId) bad(trackPath);
    } else {
      const allowed = kind === 'character'
        ? ['character']
        : kind === 'theme'
          ? ['theme']
          : ['place', 'object', 'lore'];
      if (primaryId === null || secondaryId !== null || !allowed.includes(primaryType)) bad(trackPath);
    }
    list(track.beats, `${trackPath}.beats`, (beatValue, beatPath) => {
      const beat = row(beatValue, beatPath);
      int(beat.id, `${beatPath}.id`, true);
      if (int(beat.track_id, `${beatPath}.track_id`, true) !== track.id) bad(`${beatPath}.track_id`);
      // Legacy PsykeProgression rows historically allowed blank text.  The
      // canonical command boundary rejects new blank beats, but migrated
      // compatibility rows must remain readable and exportable.
      str(beat.text, `${beatPath}.text`);
      int(beat.sort_order, `${beatPath}.sort_order`);
      const anchorKind = enumValue(beat.anchor_kind, ANCHORS, `${beatPath}.anchor_kind`);
      nullable(beat.scene_id, `${beatPath}.scene_id`, (v, p) => int(v, p, true));
      str(beat.scene_title, `${beatPath}.scene_title`);
      const anchorRef = nullable(beat.anchor_ref, `${beatPath}.anchor_ref`, str);
      str(beat.anchor_label, `${beatPath}.anchor_label`);
      if (anchorKind === 'document_block' && !anchorRef?.trim()) bad(`${beatPath}.anchor_ref`);
      return beat;
    });
    const coverage = row(track.coverage, `${trackPath}.coverage`);
    for (const key of [
      'total_beats', 'anchored_beats', 'unanchored_beats',
      'scene_anchored_beats', 'document_anchored_beats',
    ]) int(coverage[key], `${trackPath}.coverage.${key}`);
    num(coverage.coverage_percent, `${trackPath}.coverage.coverage_percent`);
    enumValue(coverage.status, STATUSES, `${trackPath}.coverage.status`);
    list(coverage.out_of_order_beat_ids, `${trackPath}.coverage.out_of_order_beat_ids`, (v, p) => int(v, p, true));
    return track;
  });
  const summary = row(dto.summary, '$.summary');
  for (const key of ['total_tracks', 'total_beats', 'anchored_beats', 'unanchored_beats']) {
    int(summary[key], `$.summary.${key}`);
  }
  num(summary.coverage_percent, '$.summary.coverage_percent');
  integerMap(summary.by_kind, '$.summary.by_kind');
  integerMap(summary.by_status, '$.summary.by_status');
  return value as ProgressionSnapshot;
}

export function validateProgressionCommandResult(
  value: unknown,
  expectedProjectId: number,
  command: ProgressionCommand,
): ProgressionCommandResult {
  const dto = row(value, '$');
  const snapshot = validateProgressionSnapshot(dto.progressions, expectedProjectId);
  const changed = bool(dto.changed, '$.changed');
  const affectedTrackIds = uniquePositiveIds(dto.affected_track_ids, '$.affected_track_ids');
  const affectedBeatIds = uniquePositiveIds(dto.affected_beat_ids, '$.affected_beat_ids');
  const createdTrackId = nullable(dto.created_track_id, '$.created_track_id', (v, p) => int(v, p, true));
  const createdBeatId = nullable(dto.created_beat_id, '$.created_beat_id', (v, p) => int(v, p, true));
  const replayed = bool(dto.replayed, '$.replayed');
  const appliedRevision = sha256(dto.applied_revision, '$.applied_revision');
  const createTrack = command.kind === 'create_track';
  const createBeat = command.kind === 'create_beat';
  const noOpKind = ['update_track', 'reorder_tracks', 'update_beat', 'reorder_beats']
    .includes(command.kind);

  if (createdTrackId !== null && !createTrack) bad('$.created_track_id');
  if (createdBeatId !== null && !createBeat) bad('$.created_beat_id');
  if (createTrack && createdTrackId === null) bad('$.created_track_id');
  if (createBeat && createdBeatId === null) bad('$.created_beat_id');

  if (replayed) {
    if (changed || affectedTrackIds.length || affectedBeatIds.length) bad('$');
  } else {
    if (appliedRevision !== snapshot.revision) bad('$.applied_revision');
    if (!changed && !noOpKind) bad('$.changed');
    if (!changed && (
      affectedTrackIds.length || affectedBeatIds.length
      || createdTrackId !== null || createdBeatId !== null
      || appliedRevision !== command.expected_revision
    )) bad('$');
    if (changed && appliedRevision === command.expected_revision) bad('$.applied_revision');
    if (changed && !affectedTrackIds.length) bad('$.affected_track_ids');
    if (changed && ['create_beat', 'update_beat', 'delete_beat', 'reorder_beats'].includes(command.kind)
      && !affectedBeatIds.length) {
      bad('$.affected_beat_ids');
    }
    if (createdTrackId !== null && !affectedTrackIds.includes(createdTrackId)) bad('$.created_track_id');
    if (createdBeatId !== null && !affectedBeatIds.includes(createdBeatId)) bad('$.created_beat_id');
  }
  return value as ProgressionCommandResult;
}

export function validateProgressionReceipt(
  value: unknown,
  expectedProjectId: number,
  command: ProgressionCommand,
  expectedRequestDigest: string,
): ProgressionCommandReceipt {
  const dto = row(value, '$');
  if (int(dto.project_id, '$.project_id', true) !== expectedProjectId) bad('$.project_id');
  const requestDigest = sha256(dto.request_digest, '$.request_digest');
  const commandKind = enumValue(dto.command_kind, COMMAND_KINDS, '$.command_kind');
  const expectedRevision = sha256(dto.expected_revision, '$.expected_revision');
  const appliedRevision = sha256(dto.applied_revision, '$.applied_revision');
  const changed = bool(dto.original_changed, '$.original_changed');
  const trackIds = uniquePositiveIds(
    dto.original_affected_track_ids,
    '$.original_affected_track_ids',
  );
  const beatIds = uniquePositiveIds(
    dto.original_affected_beat_ids,
    '$.original_affected_beat_ids',
  );
  const createdTrackId = nullable(
    dto.original_created_track_id,
    '$.original_created_track_id',
    (v, p) => int(v, p, true),
  );
  const createdBeatId = nullable(
    dto.original_created_beat_id,
    '$.original_created_beat_id',
    (v, p) => int(v, p, true),
  );
  const committedAt = str(dto.committed_at, '$.committed_at', false);
  if (!Number.isFinite(Date.parse(committedAt))) bad('$.committed_at');

  if (
    requestDigest !== expectedRequestDigest
    || commandKind !== command.kind
    || expectedRevision !== command.expected_revision
  ) bad('$');
  if (changed ? appliedRevision === expectedRevision : appliedRevision !== expectedRevision) {
    bad('$.applied_revision');
  }

  const noOpKind = ['update_track', 'reorder_tracks', 'update_beat', 'reorder_beats']
    .includes(commandKind);
  const trackOnlyKind = ['create_track', 'update_track', 'reorder_tracks'].includes(commandKind);
  const beatKind = ['create_beat', 'update_beat', 'delete_beat', 'reorder_beats'].includes(commandKind);
  if (!changed && !noOpKind) bad('$.original_changed');
  if (!changed && (trackIds.length || beatIds.length || createdTrackId !== null || createdBeatId !== null)) bad('$');
  if (changed && !trackIds.length) bad('$.original_affected_track_ids');
  if (changed && trackOnlyKind && beatIds.length) bad('$.original_affected_beat_ids');
  if (changed && beatKind && !beatIds.length) bad('$.original_affected_beat_ids');
  if (createdTrackId !== null && commandKind !== 'create_track') bad('$.original_created_track_id');
  if (createdBeatId !== null && commandKind !== 'create_beat') bad('$.original_created_beat_id');
  if (changed && commandKind === 'create_track' && createdTrackId === null) bad('$.original_created_track_id');
  if (changed && commandKind === 'create_beat' && createdBeatId === null) bad('$.original_created_beat_id');
  if (createdTrackId !== null && !trackIds.includes(createdTrackId)) bad('$.original_created_track_id');
  if (createdBeatId !== null && !beatIds.includes(createdBeatId)) bad('$.original_created_beat_id');
  return value as ProgressionCommandReceipt;
}
