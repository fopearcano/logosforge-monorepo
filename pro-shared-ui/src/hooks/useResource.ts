import { useCallback, useEffect, useRef, useState } from "react";
import type { EventName } from "@logosforge/ui-contracts";
import { useStudio } from "../adapters/StudioProvider";

export interface Resource<T> {
  data: T | undefined;
  loading: boolean;
  error: string | null;
  /**
   * Force a re-fetch and return its monotonic request id. Consumers that must
   * act only on post-request data can compare it with the settled ids below.
   */
  refetch: () => number;
  /** Most recent request id that either succeeded or failed for this identity. */
  lastSettledRequest: number;
  /** Most recent request id that published authoritative data. */
  lastSuccessfulRequest: number;
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
  const requestSequence = useRef(0);
  // Keep settlement and success generations in one state value. Consumers use
  // the pair as a barrier, so publishing them in separate renders could make a
  // successful request briefly look like a settled failure.
  const [requestState, setRequestState] = useState({
    settled: -1,
    successful: -1,
  });
  const refetch = useCallback(() => {
    // A live event can arrive while the identical GET is still pending. Clear
    // transport coalescing first so the post-event generation cannot join and
    // publish the pre-event snapshot.
    api.invalidatePendingReads?.();
    const requestId = ++requestSequence.current;
    setNonce(requestId);
    return requestId;
  }, [api]);

  // A resource value belongs to one exact key + API instance. Keeping A's data
  // visible while B loads leaks project context and can enable actions against a
  // stale row. Manual refetches keep the current value; identity changes clear it.
  useEffect(() => {
    setData(undefined);
    setError(null);
    setRequestState({ settled: -1, successful: -1 });
  }, [key, api]);

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
          setRequestState({ settled: nonce, successful: nonce });
        }
      },
      (e) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
          setLoading(false);
          setRequestState((current) => ({
            settled: Math.max(current.settled, nonce),
            successful: current.successful,
          }));
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

  return {
    data,
    loading,
    error,
    refetch,
    lastSettledRequest: requestState.settled,
    lastSuccessfulRequest: requestState.successful,
  };
}
