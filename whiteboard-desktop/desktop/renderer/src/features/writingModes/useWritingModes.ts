/** Loads the available Writing Modes from GET /api/writing-modes. */

import { useEffect, useState } from 'react';

import type { WritingMode } from './types';
import { getWritingModes } from './writingModesApi';

// Modes hidden in the Whiteboard product even though the shared backend exposes
// them (the core still supports `series`; Studio/Pro keeps it).
const HIDDEN_MODES = new Set<string>(['series']);
const coerceMode = (m: string): string => (HIDDEN_MODES.has(m) ? 'novel' : m);

interface Options {
  baseUrl: string;
  ready: boolean;
}

interface Result {
  modes: WritingMode[];
  defaultMode: string;
  loading: boolean;
  error: string | null;
}

export function useWritingModes({ baseUrl, ready }: Options): Result {
  const [modes, setModes] = useState<WritingMode[]>([]);
  const [defaultMode, setDefaultMode] = useState('novel');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ready) return;
    let active = true;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    getWritingModes(baseUrl, controller.signal)
      .then((res) => {
        if (!active) return;
        setModes(res.modes.filter((m) => !HIDDEN_MODES.has(m.id)));
        setDefaultMode(coerceMode(res.default_mode));
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (!active || controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [baseUrl, ready]);

  return { modes, defaultMode, loading, error };
}
