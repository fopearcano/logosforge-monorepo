import { useCallback, useEffect, useRef, useState } from "react";
import {
  createRuntimeFault,
  isExpectedCancellation,
  isResizeObserverLoopNotification,
  shouldReportRuntimeFault,
  wasRuntimeFaultHandled,
  type RuntimeFault,
  type RuntimeFaultSource,
} from "./runtimeFaults";
import { usePanelHostWindow } from "./PanelHost";

/** Captures runtime failures that React error boundaries cannot catch. */
export function useRuntimeFaultReporter(): {
  fault: RuntimeFault | null;
  dismiss: () => void;
} {
  const ownerWindow = usePanelHostWindow();
  const [fault, setFault] = useState<RuntimeFault | null>(null);
  const lastFaultRef = useRef<{ key: string; occurredAt: number } | null>(null);

  useEffect(() => {
    if (!ownerWindow) return undefined;
    const pending = new Set<number>();
    const schedule = (source: RuntimeFaultSource, reason: unknown) => {
      if (isExpectedCancellation(reason)) return;
      const timer = ownerWindow.setTimeout(() => {
        pending.delete(timer);
        if (wasRuntimeFaultHandled(reason)) return;
        const next = createRuntimeFault(source, reason);
        if (!shouldReportRuntimeFault(lastFaultRef.current, next)) return;
        lastFaultRef.current = { key: next.key, occurredAt: next.occurredAt };
        setFault(next);
      }, 0);
      pending.add(timer);
    };
    const onError = (event: ErrorEvent) => {
      if (isResizeObserverLoopNotification(event)) return;
      schedule("event", event.error ?? event.message);
    };
    const onUnhandledRejection = (event: PromiseRejectionEvent) => schedule("promise", event.reason);
    ownerWindow.addEventListener("error", onError);
    ownerWindow.addEventListener("unhandledrejection", onUnhandledRejection);
    return () => {
      ownerWindow.removeEventListener("error", onError);
      ownerWindow.removeEventListener("unhandledrejection", onUnhandledRejection);
      for (const timer of pending) ownerWindow.clearTimeout(timer);
    };
  }, [ownerWindow]);

  const dismiss = useCallback(() => setFault(null), []);
  return { fault, dismiss };
}
