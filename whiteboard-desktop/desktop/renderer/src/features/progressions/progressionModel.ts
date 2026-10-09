import type { PsykeEntry } from '../psyke/types';
import type { ProgressionKind, ProgressionTrack } from './types';

export function defaultProgressionKind(entryType: string): ProgressionKind {
  if (entryType === 'character') return 'character';
  if (entryType === 'theme') return 'theme';
  if (entryType === 'place' || entryType === 'object' || entryType === 'lore') return 'world';
  return 'custom';
}

export function progressionKindsForEntry(entryType: string): ProgressionKind[] {
  const kinds: ProgressionKind[] = ['story', 'relationship', 'custom'];
  if (entryType === 'character') kinds.splice(1, 0, 'character');
  if (entryType === 'theme') kinds.splice(1, 0, 'theme');
  if (entryType === 'place' || entryType === 'object' || entryType === 'lore') kinds.splice(1, 0, 'world');
  return kinds;
}

export function createTrackSubjects(
  kind: ProgressionKind,
  entryId: number,
  partnerId?: number,
): { primary_psyke_entry_id?: number; secondary_psyke_entry_id?: number } {
  if (kind === 'story' || kind === 'custom') return {};
  if (!Number.isSafeInteger(entryId) || entryId < 1) throw new Error('A valid PSYKE subject is required.');
  if (kind !== 'relationship') return { primary_psyke_entry_id: entryId };
  if (!Number.isSafeInteger(partnerId) || !partnerId || partnerId < 1 || partnerId === entryId) {
    throw new Error('Relationship tracks require two distinct PSYKE subjects.');
  }
  return { primary_psyke_entry_id: entryId, secondary_psyke_entry_id: partnerId };
}

export function tracksForEntry(tracks: ProgressionTrack[], entry: PsykeEntry): ProgressionTrack[] {
  const entryId = Number(entry.id);
  return tracks.filter((track) =>
    track.kind === 'story'
    || (track.kind === 'custom' && !track.legacy_compatibility)
    || track.primary_psyke_entry_id === entryId
    || track.secondary_psyke_entry_id === entryId);
}

export interface ResolvedAnchorCoverage {
  totalBeats: number;
  resolvedAnchors: number;
  unresolvedAnchors: number;
  missingDocumentAnchors: number;
  percent: number;
}

/**
 * Core coverage records structurally valid anchor references. Whiteboard is the
 * owner of manuscript block identities, so only the renderer can distinguish a
 * live document-block reference from one whose block was deleted.
 */
export function resolvedAnchorCoverage(
  track: ProgressionTrack,
  manuscriptBlockIds: ReadonlySet<string>,
): ResolvedAnchorCoverage {
  let resolvedAnchors = 0;
  let missingDocumentAnchors = 0;
  for (const beat of track.beats) {
    if (beat.anchor_kind === 'scene') {
      resolvedAnchors += 1;
    } else if (beat.anchor_kind === 'document_block') {
      if (beat.anchor_ref && manuscriptBlockIds.has(beat.anchor_ref)) resolvedAnchors += 1;
      else missingDocumentAnchors += 1;
    }
  }
  const totalBeats = track.beats.length;
  return {
    totalBeats,
    resolvedAnchors,
    unresolvedAnchors: totalBeats - resolvedAnchors,
    missingDocumentAnchors,
    percent: totalBeats ? Math.round((resolvedAnchors * 10_000) / totalBeats) / 100 : 0,
  };
}
