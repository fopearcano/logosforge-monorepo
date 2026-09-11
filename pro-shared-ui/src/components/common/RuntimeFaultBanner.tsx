import { useEffect, useRef } from "react";
import type { RuntimeFault } from "./runtimeFaults";

export function RuntimeFaultBanner({
  fault,
  onDismiss,
  bottom = 24,
}: {
  fault: RuntimeFault | null;
  onDismiss: () => void;
  bottom?: number;
}) {
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const wasVisibleRef = useRef(false);
  const focusTimerRef = useRef<number | null>(null);

  useEffect(() => {
    if (fault && !wasVisibleRef.current) {
      if (focusTimerRef.current !== null) {
        window.clearTimeout(focusTimerRef.current);
        focusTimerRef.current = null;
      }
      returnFocusRef.current = document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    }
    wasVisibleRef.current = fault != null;
    if (!fault) returnFocusRef.current = null;
  }, [fault]);
  useEffect(() => () => {
    if (focusTimerRef.current !== null) window.clearTimeout(focusTimerRef.current);
  }, []);

  if (!fault) return null;
  const dismiss = () => {
    const returnFocus = returnFocusRef.current;
    onDismiss();
    if (focusTimerRef.current !== null) window.clearTimeout(focusTimerRef.current);
    focusTimerRef.current = window.setTimeout(() => {
      focusTimerRef.current = null;
      if (returnFocus?.isConnected) returnFocus.focus({ preventScroll: true });
    }, 0);
  };
  return (
    <div role="alert" aria-atomic="true" data-runtime-fault={fault.key} style={{
      position: "fixed", left: "50%", bottom, zIndex: 1200,
      transform: "translateX(-50%)", width: "min(760px,calc(100% - 40px))",
      display: "flex", alignItems: "center", gap: 10, padding: "9px 12px",
      border: "1px solid var(--crimson,#e8443a)", background: "var(--panel,#080a0f)",
      color: "var(--txt,#e4e8ef)", boxShadow: "0 12px 40px rgba(0,0,0,.45)",
      fontFamily: "'JetBrains Mono',monospace",
    }}>
      <span style={{ flex: "none", color: "var(--crimson,#e8443a)", fontSize: 8, letterSpacing: ".14em" }}>{fault.source === "promise" ? "ASYNC ERROR" : "UI ERROR"}</span>
      <span style={{ flex: 1, minWidth: 0, fontSize: 10.5, lineHeight: 1.4, overflowWrap: "anywhere" }}>{fault.message}</span>
      <button type="button" onClick={dismiss} aria-label="Dismiss runtime error" style={{ flex: "none", border: "1px solid var(--line2,rgba(150,162,180,.1))", background: "transparent", color: "var(--txt2,#8b95a5)", font: "inherit", fontSize: 9, padding: "4px 7px", cursor: "pointer" }}>DISMISS</button>
    </div>
  );
}
