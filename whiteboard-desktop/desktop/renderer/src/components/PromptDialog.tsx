/**
 * A small, accessible, non-blocking single-line text prompt — the theme-styled
 * replacement for window.prompt (which is unreliable in the packaged Electron
 * app). Escape or an overlay click cancels, Enter confirms, the input is focused
 * + selected on open. Reuses the ConfirmDialog overlay/dialog styling.
 */

import { useEffect, useRef, useState } from 'react';

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
    <div
      className="cf-overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      <div className="cf-dialog" role="dialog" aria-modal="true" aria-labelledby="pd-title">
        <h2 id="pd-title" className="cf-title">
          {title}
        </h2>
        {message && <p className="cf-msg">{message}</p>}
        <input
          ref={inputRef}
          className="pd-input"
          type="text"
          value={value}
          placeholder={placeholder}
          spellCheck={false}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              submit();
            } else if (e.key === 'Escape') {
              e.preventDefault();
              onCancel();
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
  );
}
