import { useCallback, useEffect, useState } from "react";
import type { EventName } from "@logosforge/ui-contracts";
import { useStudio } from "../adapters/StudioProvider";

export interface Resource<T> {
  data: T | undefined;
  loading: boolean;
  error: string | null;
  /** Force a re-fetch (also runs automatically when `key` or a `refetchOn` event changes). */
  refetch: () => void;
}

/**
 * Generic data hook over the injected `ApiClient`. Fetches when `key` changes,
 * tracks loading/error, and re-fetches when one of `refetchOn` change-events
 * fires on the active project's live event stream (SSE/poll via `api.subscribe`).
 *
 * `key` is the value the fetch depends on (usually the project id) — pass `null`
 * to mean "nothing to fetch yet" (e.g. no project open), which clears loading.
 */
export function useResource<T>(
  key: number | string | null,
  fetcher: () => Promise<T>,
  refetchOn: EventName[] = [],
): Resource<T> {
  const { api, projectId } = useStudio();
  const [data, setData] = useState<T>();
  const [loading, setLoading] = useState(key != null);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const refetch = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    if (key == null) {
      setLoading(false);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.resolve(fetcher()).then(
      (d) => {
        if (!cancelled) {
          setData(d);
          setLoading(false);
        }
      },
      (e) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
          setLoading(false);
        }
      },
    );
    return () => {
      cancelled = true;
    };
    // `fetcher` is intentionally excluded — `key`, `nonce`, and the api identity
    // drive (re)fetching, so a fresh inline fetcher each render doesn't re-request,
    // but swapping the injected ApiClient (e.g. mock → live core) does.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, nonce, api]);

  useEffect(() => {
    if (refetchOn.length === 0 || projectId == null || typeof api?.subscribe !== "function") return;
    // Coalesce a burst of change-events (e.g. a manuscript save-all emitting one
    // `scene_changed` per scene) into a single refetch, instead of refetching once
    // per event. Manual refetch() (writes) stays immediate; only the live event
    // stream is debounced.
    let t: ReturnType<typeof setTimeout> | undefined;
    const unsub = api.subscribe(projectId, (e) => {
      if (refetchOn.includes(e.event as EventName)) {
        if (t) clearTimeout(t);
        t = setTimeout(refetch, 120);
      }
    });
    return () => { if (t) clearTimeout(t); unsub?.(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, projectId, refetch, refetchOn.join(",")]);

  return { data, loading, error, refetch };
}
