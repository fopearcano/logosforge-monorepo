/** Runs a single Logos inline request lifecycle (request/response). */

import { useCallback, useRef, useState } from 'react';

import { logosInline } from '../littleboyApi';
import type { LogosInlineRequest, LogosInlineResponse } from '../littleboyTypes';
import type { LogosStatus } from './logosTypes';

interface Options {
  baseUrl: string;
}

interface Result {
  status: LogosStatus;
  response: LogosInlineResponse | null;
  error: string | null;
  run: (req: LogosInlineRequest) => Promise<void>;
  reset: () => void;
}

export function useLogosInline({ baseUrl }: Options): Result {
  const [status, setStatus] = useState<LogosStatus>('idle');
  const [response, setResponse] = useState<LogosInlineResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const reset = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    setStatus('idle');
    setResponse(null);
    setError(null);
  }, []);

  const run = useCallback(
    async (req: LogosInlineRequest) => {
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;
      setStatus('loading');
      setResponse(null);
      setError(null);
      try {
        const res = await logosInline(baseUrl, req, controller.signal);
        if (controller.signal.aborted) return;
        setResponse(res);
        setStatus('done');
      } catch (err: unknown) {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : String(err));
        setStatus('error');
      }
    },
    [baseUrl],
  );

  return { status, response, error, run, reset };
}
