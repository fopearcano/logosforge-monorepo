import { useEffect, useRef } from 'react';

import type { RuntimeFault } from './runtimeFaults';

export function RuntimeFaultBanner({
  fault,
  onDismiss,
  top = 54,
}: {
  fault: RuntimeFault | null;
  onDismiss: () => void;
  /** Distance from the viewport top; defaults below the Whiteboard title bar. */
  top?: number;
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
    <div
      role="alert"
      aria-atomic="true"
      data-runtime-fault={fault.key}
      style={{
        position: 'fixed',
        top,
        left: '50%',
        zIndex: 900,
        transform: 'translateX(-50%)',
        width: 'min(760px, calc(100% - 40px))',
        boxSizing: 'border-box',
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '9px 12px',
        border: '1px solid var(--error, #c0473b)',
        borderRadius: 'var(--r-md, 6px)',
        background: 'var(--panel-2, #fff)',
        color: 'var(--text, #252422)',
        boxShadow: 'var(--page-shadow, 0 12px 40px rgba(0, 0, 0, .28))',
        fontFamily: 'var(--font-ui, sans-serif)',
      }}
    >
      <span
        style={{
          flex: 'none',
          color: 'var(--error, #c0473b)',
          fontFamily: 'var(--font-mono, monospace)',
          fontSize: 9,
          fontWeight: 600,
          letterSpacing: '.1em',
        }}
      >
        {fault.source === 'promise' ? 'ASYNC ERROR' : 'UI ERROR'}
      </span>
      <span style={{ flex: 1, minWidth: 0, fontSize: 11.5, lineHeight: 1.4, overflowWrap: 'anywhere' }}>
        {fault.message}
      </span>
      <button
        type="button"
        onClick={dismiss}
        aria-label="Dismiss runtime error"
        style={{
          flex: 'none',
          border: '1px solid var(--border, #e6e5e0)',
          borderRadius: 'var(--r-sm, 4px)',
          background: 'transparent',
          color: 'var(--muted, #716f69)',
          padding: '4px 7px',
          font: 'inherit',
          fontSize: 10,
          cursor: 'pointer',
        }}
      >
        Dismiss
      </button>
    </div>
  );
}
