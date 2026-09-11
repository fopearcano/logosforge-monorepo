/** A tiny popover: a trigger button + a floating panel that closes on outside
 *  click or Escape. Used by the Screenplay toolbar (Settings / Format / Export). */

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';

interface Props {
  label: ReactNode;
  title: string;
  /** Render-prop receives a `close` callback (so menu items can dismiss). */
  children: (close: (options?: { restoreFocus?: boolean }) => void) => ReactNode;
  align?: 'left' | 'right';
  /** Trigger button class (defaults to the toolbar `wb-tool` look). */
  triggerClassName?: string;
}

export function Popover({ label, title, children, align = 'left', triggerClassName = 'wb-tool' }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const close = useCallback((options?: { restoreFocus?: boolean }) => {
    // A menu action removes its focused menu item. Restore the trigger by
    // default so keyboard focus never falls back to <body>; commands that move
    // focus into an editor explicitly opt out.
    if (options?.restoreFocus !== false) triggerRef.current?.focus({ preventScroll: true });
    setOpen(false);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        close();
      }
    };
    window.addEventListener('mousedown', onDown);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('mousedown', onDown);
      window.removeEventListener('keydown', onKey);
    };
  }, [open, close]);

  return (
    <div className="wb-popover" ref={ref}>
      <button
        ref={triggerRef}
        type="button"
        className={`${triggerClassName}${open ? ' is-active' : ''}`}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={title}
        title={title}
        onClick={() => setOpen((o) => !o)}
      >
        {label}
      </button>
      {open && (
        <div className={`wb-popover-panel wb-popover-${align}`} role="dialog" aria-label={title}>
          {children(close)}
        </div>
      )}
    </div>
  );
}
