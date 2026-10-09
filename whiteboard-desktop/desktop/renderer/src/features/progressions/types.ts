export type ProgressionKind =
  | 'story'
  | 'character'
  | 'relationship'
  | 'theme'
  | 'world'
  | 'custom';

export type ProgressionAnchorKind = 'unanchored' | 'scene' | 'document_block';
export type ProgressionCoverageStatus = 'empty' | 'unanchored' | 'partial' | 'complete';

export interface ProgressionBeat {
  id: number;
  track_id: number;
  text: string;
  sort_order: number;
  anchor_kind: ProgressionAnchorKind;
  scene_id: number | null;
  scene_title: string;
  anchor_ref: string | null;
  anchor_label: string;
}

export interface ProgressionCoverage {
  total_beats: number;
  anchored_beats: number;
  unanchored_beats: number;
  scene_anchored_beats: number;
  document_anchored_beats: number;
  coverage_percent: number;
  status: ProgressionCoverageStatus;
  out_of_order_beat_ids: number[];
}

export interface ProgressionTrack {
  id: number;
  project_id: number;
  kind: ProgressionKind;
  title: string;
  description: string;
  color_label: string;
  sort_order: number;
  legacy_compatibility: boolean;
  primary_psyke_entry_id: number | null;
  primary_psyke_entry_name: string;
  primary_psyke_entry_type: string;
  secondary_psyke_entry_id: number | null;
  secondary_psyke_entry_name: string;
  secondary_psyke_entry_type: string;
  beats: ProgressionBeat[];
  coverage: ProgressionCoverage;
}

export interface ProgressionSummary {
  total_tracks: number;
  total_beats: number;
  anchored_beats: number;
  unanchored_beats: number;
  coverage_percent: number;
  by_kind: Record<string, number>;
  by_status: Record<string, number>;
}

export interface ProgressionSnapshot {
  project_id: number;
  revision: string;
  tracks: ProgressionTrack[];
  summary: ProgressionSummary;
}

interface CommandBase {
  expected_revision: string;
}

export type ProgressionCommand =
  | (CommandBase & {
      kind: 'create_track';
      track_kind: ProgressionKind;
      title: string;
      description?: string;
      color_label?: string;
      primary_psyke_entry_id?: number | null;
      secondary_psyke_entry_id?: number | null;
      index?: number;
    })
  | (CommandBase & {
      kind: 'update_track';
      track_id: number;
      track_kind?: ProgressionKind;
      title?: string;
      description?: string;
      color_label?: string;
      primary_psyke_entry_id?: number | null;
      secondary_psyke_entry_id?: number | null;
    })
  | (CommandBase & { kind: 'delete_track'; track_id: number })
  | (CommandBase & { kind: 'reorder_tracks'; track_ids: number[] })
  | (CommandBase & {
      kind: 'create_beat';
      track_id: number;
      text: string;
      anchor_kind?: ProgressionAnchorKind;
      scene_id?: number | null;
      anchor_ref?: string | null;
      anchor_label?: string;
      index?: number;
    })
  | (CommandBase & {
      kind: 'update_beat';
      beat_id: number;
      text?: string;
      anchor_kind?: ProgressionAnchorKind;
      scene_id?: number | null;
      anchor_ref?: string | null;
      anchor_label?: string;
    })
  | (CommandBase & { kind: 'delete_beat'; beat_id: number })
  | (CommandBase & { kind: 'reorder_beats'; track_id: number; beat_ids: number[] });

export type ProgressionCommandInput = ProgressionCommand extends infer Command
  ? Command extends ProgressionCommand
    ? Omit<Command, 'expected_revision'>
    : never
  : never;

export interface ProgressionCommandResult {
  progressions: ProgressionSnapshot;
  changed: boolean;
  affected_track_ids: number[];
  affected_beat_ids: number[];
  created_track_id: number | null;
  created_beat_id: number | null;
  replayed: boolean;
  applied_revision: string;
}

export interface ProgressionCommandReceipt {
  project_id: number;
  request_digest: string;
  command_kind: ProgressionCommand['kind'];
  expected_revision: string;
  applied_revision: string;
  original_changed: boolean;
  original_affected_track_ids: number[];
  original_affected_beat_ids: number[];
  original_created_track_id: number | null;
  original_created_beat_id: number | null;
  committed_at: string;
}

export interface ManuscriptProgressionAnchor {
  anchor_kind: 'document_block';
  anchor_ref: string;
  anchor_label: string;
}
