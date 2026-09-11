/**
 * A small, accessible, non-blocking confirm dialog — a theme-styled replacement
 * for window.confirm (which froze the renderer synchronously). Escape or an
 * overlay click cancels, Enter activates the focused action, focus starts on the
 * confirm button, and focus stays within the modal until it closes.
 */

import { useId, useRef, type RefObject } from 'react';

import { ModalPortal } from './ModalPortal';
import { useModalDialog } from './useModalDialog';

interface Props {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  returnFocusFallbackRef?: RefObject<HTMLElement>;
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  onConfirm,
  onCancel,
  returnFocusFallbackRef,
}: Props) {
  const confirmRef = useRef<HTMLButtonElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const messageId = useId();

  useModalDialog({
    open,
    dialogRef,
    initialFocusRef: confirmRef,
    returnFocusFallbackRef,
    onClose: onCancel,
  });

  if (!open) return null;

  return (
    <ModalPortal>
      <div
        data-wb-modal-layer
        className="cf-overlay"
        onClick={(event) => {
          if (event.target === event.currentTarget) onCancel();
        }}
      >
        <div
          ref={dialogRef}
          className="cf-dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          aria-describedby={messageId}
          tabIndex={-1}
        >
          <h2 id={titleId} className="cf-title">
            {title}
          </h2>
          <p id={messageId} className="cf-msg">
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
    </ModalPortal>
  );
}
