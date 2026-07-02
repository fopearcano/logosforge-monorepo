/** React glue for Document Settings — load once, persist on change. */

import { useCallback, useState } from 'react';

import { DEFAULT_SETTINGS, loadSettings, saveSettings, type DocumentSettings } from './documentSettings';

export interface DocumentSettingsApi {
  settings: DocumentSettings;
  update: <K extends keyof DocumentSettings>(key: K, value: DocumentSettings[K]) => void;
  /** Replace all settings at once (e.g. importing a LogosForge document). */
  replace: (partial: Partial<DocumentSettings>) => void;
}

export function useDocumentSettings(): DocumentSettingsApi {
  const [settings, setSettings] = useState<DocumentSettings>(loadSettings);

  const update = useCallback(
    <K extends keyof DocumentSettings>(key: K, value: DocumentSettings[K]) => {
      setSettings((prev) => {
        const next = { ...prev, [key]: value };
        saveSettings(next);
        return next;
      });
    },
    [],
  );

  const replace = useCallback((partial: Partial<DocumentSettings>) => {
    setSettings(() => {
      // Start from defaults so an imported document fully defines its settings;
      // recognized keys override, anything unexpected in the file is inert (only
      // known keys are ever read, e.g. by surfaceDataAttrs). JSON has no
      // `undefined`, so a missing key simply keeps the default.
      const next: DocumentSettings = { ...DEFAULT_SETTINGS, ...partial };
      saveSettings(next);
      return next;
    });
  }, []);

  return { settings, update, replace };
}
