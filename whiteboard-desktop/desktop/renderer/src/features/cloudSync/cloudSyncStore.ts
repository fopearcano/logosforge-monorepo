import { useSyncExternalStore } from 'react';

import type { CloudSyncUiState } from './cloudSyncUi';

const DISABLED_STATE: CloudSyncUiState = {
  enabled: false,
  automatic: false,
  folderPath: null,
  status: 'disabled',
  detail: 'Choose a provider-managed folder in Settings to sync across devices.',
  lastSuccessfulSyncAt: null,
  conflict: null,
  busy: false,
};

let currentState = DISABLED_STATE;
const subscribers = new Set<() => void>();

export function getCloudSyncUiState(): CloudSyncUiState {
  return currentState;
}

export function setCloudSyncUiState(state: CloudSyncUiState): void {
  currentState = state;
  subscribers.forEach((subscriber) => subscriber());
}

export function resetCloudSyncUiState(): void {
  setCloudSyncUiState(DISABLED_STATE);
}

export function subscribeCloudSyncUiState(subscriber: () => void): () => void {
  subscribers.add(subscriber);
  return () => subscribers.delete(subscriber);
}

export function useCloudSyncUiState(): CloudSyncUiState {
  return useSyncExternalStore(
    subscribeCloudSyncUiState,
    getCloudSyncUiState,
    getCloudSyncUiState,
  );
}
