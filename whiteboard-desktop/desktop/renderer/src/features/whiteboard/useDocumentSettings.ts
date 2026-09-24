/** React glue for project-scoped Document Settings. */

import { useCallback, useEffect, useRef, useState } from 'react';

import {
  DEFAULT_SETTINGS,
  clearLegacySettingsMigration,
  documentSettingsSnapshotKey,
  legacySettingsForDocument,
  normalizeDocumentSettings,
  type DocumentSettings,
} from './documentSettings';

export interface DocumentSettingsApi {
  settings: DocumentSettings;
  update: <K extends keyof DocumentSettings>(key: K, value: DocumentSettings[K]) => void;
  /** Replace all settings at once (e.g. importing a LogosForge document). */
  replace: (partial: Partial<DocumentSettings>) => void;
}

interface Options {
  documentId: string | null;
  documentRevision: string | null;
  initialSettings?: unknown;
  onChange: (settings: DocumentSettings) => void;
}

export function useDocumentSettings({
  documentId,
  documentRevision,
  initialSettings,
  onChange,
}: Options): DocumentSettingsApi {
  const [settings, setSettings] = useState<DocumentSettings>(DEFAULT_SETTINGS);
  const settingsRef = useRef(settings);
  settingsRef.current = settings;
  const initialRef = useRef(initialSettings);
  initialRef.current = initialSettings;
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  const snapshotKey = documentSettingsSnapshotKey(documentId, documentRevision);
  useEffect(() => {
    if (!documentId || !snapshotKey) return;
    const raw = initialRef.current;
    const hasPersisted = !!raw && typeof raw === 'object' &&
      !Array.isArray(raw) && Object.keys(raw as Record<string, unknown>).length > 0;
    const legacy = hasPersisted ? null : legacySettingsForDocument(documentId);
    const next = normalizeDocumentSettings(hasPersisted ? raw : legacy);
    settingsRef.current = next;
    setSettings(next);
    if (hasPersisted) clearLegacySettingsMigration(documentId);
    else if (legacy) onChangeRef.current(next);
  }, [documentId, snapshotKey]);

  const update = useCallback(
    <K extends keyof DocumentSettings>(key: K, value: DocumentSettings[K]) => {
      const next = normalizeDocumentSettings({ ...settingsRef.current, [key]: value });
      settingsRef.current = next;
      setSettings(next);
      onChangeRef.current(next);
    },
    [],
  );

  const replace = useCallback((partial: Partial<DocumentSettings>) => {
    // Start from defaults so an imported document fully defines its settings;
    // unknown or malformed keys are discarded by normalization.
    const next = normalizeDocumentSettings(partial);
    settingsRef.current = next;
    setSettings(next);
    onChangeRef.current(next);
  }, []);

  return { settings, update, replace };
}
