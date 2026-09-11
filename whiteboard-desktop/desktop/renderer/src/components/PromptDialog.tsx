/**
 * A small, accessible, non-blocking single-line text prompt — the theme-styled
 * replacement for window.prompt (which is unreliable in the packaged Electron
 * app). Escape or an overlay click cancels, Enter confirms, the input is focused
 * + selected on open. Reuses the ConfirmDialog overlay/dialog styling.
 */

import { useEffect, useId, useRef, useState } from 'react';

import { ModalPortal } from './ModalPortal';
import { useModalDialog } from './useModalDialog';

interface Props {
  open: boolean;
  title: string;
  message?: string;
  initialValue?: string;
  placeholder?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Called with the trimmed value; the dialog does not close itself. */
  onConfirm: (value: string) => void;
  onCancel: () => void;
}

export function PromptDialog({
  open,
  title,
  message,
  initialValue = '',
  placeholder,
  confirmLabel = 'OK',
  cancelLabel = 'Cancel',
  onConfirm,
  onCancel,
}: Props) {
  const [value, setValue] = useState(initialValue);
  const inputRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const messageId = useId();

  useModalDialog({ open, dialogRef, initialFocusRef: inputRef, onClose: onCancel });

  // Seed the field + focus/select it whenever the dialog opens (deps: [open]).
  useEffect(() => {
    if (!open) return;
    setValue(initialValue);
    const el = inputRef.current;
    if (el) {
      el.focus();
      el.select();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;

  const submit = () => {
    const v = value.trim();
    if (v) onConfirm(v);
  };

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
          aria-describedby={message ? messageId : undefined}
          tabIndex={-1}
        >
          <h2 id={titleId} className="cf-title">
            {title}
          </h2>
          {message && <p id={messageId} className="cf-msg">{message}</p>}
          <input
            ref={inputRef}
            className="pd-input"
            type="text"
            aria-label={placeholder || title}
            value={value}
            placeholder={placeholder}
            spellCheck={false}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                submit();
              }
            }}
          />
          <div className="cf-actions">
            <button type="button" className="cf-btn cf-cancel" onClick={onCancel}>
              {cancelLabel}
            </button>
            <button type="button" className="cf-btn cf-confirm" onClick={submit} disabled={!value.trim()}>
              {confirmLabel}
            </button>
          </div>
        </div>
      </div>
    </ModalPortal>
  );
}
