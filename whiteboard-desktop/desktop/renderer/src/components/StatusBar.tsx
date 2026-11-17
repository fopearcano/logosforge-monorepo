import React from 'react';

import type { BackendStatus } from '../api/backend';
import { cloudSyncStatusLabel, type CloudSyncUiState } from '../features/cloudSync/cloudSyncUi';

const COLORS: Record<string, string> = {
  connecting: '#e0b341',
  connected: '#4ade80',
  error: '#f87171',
};

const LABELS: Record<string, string> = {
  connecting: 'Connecting…',
  connected: 'Connected',
  error: 'Unavailable',
};

export function StatusBar({ status, cloudSync }: { status: BackendStatus; cloudSync?: CloudSyncUiState }) {
  const color = COLORS[status.state] ?? '#888c99';
  const label = LABELS[status.state] ?? status.state;
  return (
    <footer className="statusbar" title={status.detail ?? ''}>
      <span className="status">
        <span className="dot" style={{ backgroundColor: color }} />
        Backend: {label}
      </span>
      {cloudSync && (
        <span className="cloud-status" data-status={cloudSync.status} aria-live="polite">
          <span className="cloud-status-dot" aria-hidden="true" />
          Cloud: {cloudSyncStatusLabel(cloudSync.status)}
        </span>
      )}
      <span className="spacer" />
      <span className="version">
        API v{status.apiVersion ?? '—'}
        {status.version ? ` · core ${status.version}` : ''}
      </span>
    </footer>
  );
}
