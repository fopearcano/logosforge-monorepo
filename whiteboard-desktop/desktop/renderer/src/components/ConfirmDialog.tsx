/**
 * A small, accessible, non-blocking confirm dialog — a theme-styled replacement
 * for window.confirm (which froze the renderer synchronously). Escape or an
 * overlay click cancels, Enter confirms, focus starts on the confirm button, and
 * Tab is trapped between the two actions.
 */

import { useEffect, useRef } from 'react';

interface Props {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  onConfirm,
  onCancel,
}: Props) {
  const confirmRef = useRef<HTMLButtonElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return undefined;
    confirmRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onCancel();
      } else if (e.key === 'Enter') {
        e.preventDefault();
        onConfirm();
      } else if (e.key === 'Tab') {
        // Two-button focus trap.
        const a = cancelRef.current;
        const b = confirmRef.current;
        if (!a || !b) return;
        e.preventDefault();
        (document.activeElement === b ? a : b).focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onConfirm, onCancel]);

  if (!open) return null;

  return (
    <div
      className="cf-overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      <div
        className="cf-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="cf-title"
        aria-describedby="cf-msg"
      >
        <h2 id="cf-title" className="cf-title">
          {title}
        </h2>
        <p id="cf-msg" className="cf-msg">
          {message}
        </p>
        <div className="cf-actions">
          <button type="button" className="cf-btn cf-cancel" ref={cancelRef} onClick={onCancel}>
            {cancelLabel}
          </button>
          <button type="button" className="cf-btn cf-confirm" ref={confirmRef} onClick={onConfirm}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
