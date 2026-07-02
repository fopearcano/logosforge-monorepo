/** Debounced PSYKE search backed by GET /api/psyke/search. */

import { useEffect, useState } from 'react';

import { searchPsyke } from './psykeApi';
import type { PsykeEntry } from './types';

const DEBOUNCE_MS = 250;

interface Options {
  baseUrl: string;
  initialQuery?: string;
}

interface Result {
  query: string;
  setQuery: (q: string) => void;
  results: PsykeEntry[];
  loading: boolean;
  error: string | null;
  /** Re-run the current search (e.g. after an edit/delete mutation). */
  refresh: () => void;
}

export function usePsykeSearch({ baseUrl, initialQuery = '' }: Options): Result {
  const [query, setQuery] = useState(initialQuery);
  const [results, setResults] = useState<PsykeEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setResults([]);
      setError(null);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    const handle = setTimeout(() => {
      setLoading(true);
      setError(null);
      searchPsyke(baseUrl, q, controller.signal)
        .then((res) => {
          setResults(res.results);
          setLoading(false);
        })
        .catch((err: unknown) => {
          if (controller.signal.aborted) return;
          setError(err instanceof Error ? err.message : String(err));
          setLoading(false);
        });
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(handle);
      controller.abort();
    };
  }, [query, baseUrl, refreshKey]);

  return { query, setQuery, results, loading, error, refresh: () => setRefreshKey((k) => k + 1) };
}
