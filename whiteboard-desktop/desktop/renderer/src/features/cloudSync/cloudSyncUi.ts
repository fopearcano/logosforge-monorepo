export type CloudSyncStatus =
  | 'disabled'
  | 'checking'
  | 'syncing'
  | 'up-to-date'
  | 'folder-unavailable'
  | 'attention'
  | 'error';

export interface CloudSyncConflictSummary {
  kind: 'bound-conflict' | 'remote-recovery';
  projectTitle: string;
  localDeviceLabel: string;
  remoteDeviceLabel: string;
  localChangedAt?: string | null;
  remoteChangedAt?: string | null;
  branchCount: number;
}
export interface CloudSyncUiState {
  enabled: boolean;
  automatic: boolean;
  folderPath: string | null;
  status: CloudSyncStatus;
  detail?: string | null;
  lastSuccessfulSyncAt?: string | null;
  conflict?: CloudSyncConflictSummary | null;
  busy?: boolean;
}

export interface CloudSyncControls {
  state: CloudSyncUiState;
  onChooseFolder: () => void | Promise<void>;
  onSyncNow: () => void | Promise<void>;
  onRetry: () => void | Promise<void>;
  onDisable: () => void | Promise<void>;
  onAutomaticChange: (automatic: boolean) => void | Promise<void>;
  onReviewConflict: () => void;
}

const STATUS_LABELS: Record<CloudSyncStatus, string> = {
  disabled: 'Disabled',
  checking: 'Checking',
  syncing: 'Syncing',
  'up-to-date': 'Up to date',
  'folder-unavailable': 'Folder unavailable',
  attention: 'Attention required',
  error: 'Error',
};

export function cloudSyncStatusLabel(status: CloudSyncStatus): string {
  return STATUS_LABELS[status];
}

export function formatCloudSyncTime(value: string | null | undefined): string {
  if (!value) return 'Not yet';
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? 'Unknown' : date.toLocaleString();
}
