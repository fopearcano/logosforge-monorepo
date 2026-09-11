/** Debounced PSYKE search backed by GET /api/psyke/search. */

import { useEffect, useRef, useState } from 'react';

import { getCurrentDocId, waitForPendingDocWrites } from '../../state/currentDocument';
import { searchPsykeForDocument } from './psykeApi';
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
  const requestSeq = useRef(0);

  useEffect(() => {
    const seq = (requestSeq.current += 1);
    const q = query.trim();
    if (!q) {
      setResults([]);
      setError(null);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    const handle = setTimeout(() => {
      const requestDocId = getCurrentDocId();
      void (async () => {
        setLoading(true);
        setError(null);
        try {
          // A retrying mutation from a retiring view must settle before this GET
          // takes its snapshot. Re-check identity on both sides of the request.
          await waitForPendingDocWrites();
          if (
            controller.signal.aborted
            || seq !== requestSeq.current
            || requestDocId !== getCurrentDocId()
          ) return;
          const res = await searchPsykeForDocument(
            baseUrl,
            requestDocId,
            q,
            controller.signal,
          );
          if (
            controller.signal.aborted
            || seq !== requestSeq.current
            || requestDocId !== getCurrentDocId()
          ) return;
          setResults(res.results);
        } catch (err: unknown) {
          if (controller.signal.aborted || seq !== requestSeq.current) return;
          setError(err instanceof Error ? err.message : String(err));
        } finally {
          if (!controller.signal.aborted && seq === requestSeq.current) setLoading(false);
        }
      })();
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(handle);
      controller.abort();
    };
  }, [query, baseUrl, refreshKey]);

  return { query, setQuery, results, loading, error, refresh: () => setRefreshKey((k) => k + 1) };
}
