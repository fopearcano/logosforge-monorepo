import { useCallback, useEffect, useRef, useState } from 'react';

import {
  createRuntimeFault,
  isExpectedCancellation,
  shouldReportRuntimeFault,
  wasRuntimeFaultHandled,
  type RuntimeFault,
  type RuntimeFaultSource,
} from './runtimeFaults';

/** Captures runtime failures that React render error boundaries cannot catch. */
export function useRuntimeFaultReporter(): {
  fault: RuntimeFault | null;
  dismiss: () => void;
} {
  const [fault, setFault] = useState<RuntimeFault | null>(null);
  const lastFaultRef = useRef<{ key: string; occurredAt: number } | null>(null);

  useEffect(() => {
    const pending = new Set<number>();
    const schedule = (source: RuntimeFaultSource, reason: unknown) => {
      if (isExpectedCancellation(reason)) return;
      // React can surface a render failure to `window.error` before its nearest
      // boundary runs componentDidCatch. Defer one task so the boundary can mark
      // the same Error object as handled and prevent a duplicate global banner.
      const timer = window.setTimeout(() => {
        pending.delete(timer);
        if (wasRuntimeFaultHandled(reason)) return;
        const next = createRuntimeFault(source, reason);
        if (!shouldReportRuntimeFault(lastFaultRef.current, next)) return;
        lastFaultRef.current = { key: next.key, occurredAt: next.occurredAt };
        setFault(next);
      }, 0);
      pending.add(timer);
    };

    const onError = (event: ErrorEvent) => schedule('event', event.error ?? event.message);
    const onUnhandledRejection = (event: PromiseRejectionEvent) => schedule('promise', event.reason);
    window.addEventListener('error', onError);
    window.addEventListener('unhandledrejection', onUnhandledRejection);
    return () => {
      window.removeEventListener('error', onError);
      window.removeEventListener('unhandledrejection', onUnhandledRejection);
      for (const timer of pending) window.clearTimeout(timer);
      pending.clear();
    };
  }, []);

  const dismiss = useCallback(() => setFault(null), []);
  return { fault, dismiss };
}
