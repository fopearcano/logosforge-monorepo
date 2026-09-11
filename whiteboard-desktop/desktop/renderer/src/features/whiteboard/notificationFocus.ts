const WORKSPACE_FOCUS_FALLBACK = [
  '.wb-editor',
  'button[aria-label="File menu"]',
  'button[aria-label="Quick Start and hotkeys"]',
].join(', ');

/**
 * Restore a usable keyboard destination after React removes a focused toast
 * button. A zero-delay caller lets the state commit happen first. If focus was
 * deliberately moved to another connected element meanwhile, leave it alone.
 */
export function restoreFocusAfterNotificationDismiss(
  ownerDocument: Document = document,
): void {
  const active = ownerDocument.activeElement;
  if (
    active
    && active !== ownerDocument.body
    && active !== ownerDocument.documentElement
    && active.isConnected
  ) return;

  const fallback = ownerDocument.querySelector<HTMLElement>('.wb-toast-dismiss')
    ?? ownerDocument.querySelector<HTMLElement>(WORKSPACE_FOCUS_FALLBACK);
  fallback?.focus({ preventScroll: true });
}
