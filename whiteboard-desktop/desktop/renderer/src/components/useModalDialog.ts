import { useEffect, useRef, type RefObject } from 'react';

const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  "[tabindex]:not([tabindex='-1'])",
].join(',');

interface ModalEntry {
  token: symbol;
  dialog: HTMLElement;
  layer: HTMLElement | null;
  returnFocus: HTMLElement | null;
  fallbackFocus: HTMLElement | null;
}

interface BackgroundState {
  inert: boolean;
  ariaHidden: string | null;
}

const modalStack: ModalEntry[] = [];
const backgroundStates = new Map<HTMLElement, BackgroundState>();
let unlockedBodyOverflow: string | null = null;

/** Used by capture-phase feature shortcuts that run before document listeners. */
export function isModalDialogOpen(): boolean {
  return modalStack.length > 0;
}

function restoreBackgroundElement(element: HTMLElement, state: BackgroundState): void {
  element.inert = state.inert;
  if (state.ariaHidden == null) element.removeAttribute('aria-hidden');
  else element.setAttribute('aria-hidden', state.ariaHidden);
}

/** Recompute isolation from the current topmost modal, including out-of-order unmounts. */
function syncBackgroundIsolation(): void {
  const top = modalStack[modalStack.length - 1];
  if (!top) {
    for (const [element, state] of backgroundStates) restoreBackgroundElement(element, state);
    backgroundStates.clear();
    if (unlockedBodyOverflow != null) {
      document.body.style.overflow = unlockedBodyOverflow;
      unlockedBodyOverflow = null;
    }
    return;
  }

  if (unlockedBodyOverflow == null) unlockedBodyOverflow = document.body.style.overflow;
  document.body.style.overflow = 'hidden';

  let visibleBranch = top.layer ?? top.dialog;
  while (visibleBranch.parentElement && visibleBranch.parentElement !== document.body) {
    visibleBranch = visibleBranch.parentElement;
  }

  for (const child of Array.from(document.body.children)) {
    if (!(child instanceof HTMLElement)) continue;
    if (child === visibleBranch) {
      const original = backgroundStates.get(child);
      if (original) {
        restoreBackgroundElement(child, original);
        backgroundStates.delete(child);
      }
      continue;
    }
    if (!backgroundStates.has(child)) {
      backgroundStates.set(child, {
        inert: child.inert,
        ariaHidden: child.getAttribute('aria-hidden'),
      });
    }
    child.inert = true;
    child.setAttribute('aria-hidden', 'true');
  }
}

function focusableElements(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((element) => {
    if (element.closest("[hidden],[aria-hidden='true']")) return false;
    const style = window.getComputedStyle(element);
    return element.tabIndex >= 0 && style.display !== 'none' && style.visibility !== 'hidden';
  });
}

function canRestoreFocus(element: HTMLElement | null, parentDialog?: HTMLElement): element is HTMLElement {
  if (!element?.isConnected || element.matches(':disabled')) return false;
  if (element.closest("[inert],[aria-hidden='true']")) return false;
  if (parentDialog && !parentDialog.contains(element)) return false;
  const style = window.getComputedStyle(element);
  return style.display !== 'none' && style.visibility !== 'hidden';
}

/**
 * Gives a Whiteboard modal its keyboard and isolation contract: initial focus,
 * a Tab loop, Escape handling, background inertness, and focus restoration.
 */
export function useModalDialog<T extends HTMLElement>({
  open,
  dialogRef,
  initialFocusRef,
  returnFocusFallbackRef,
  onClose,
  canClose = true,
}: {
  open: boolean;
  dialogRef: RefObject<T>;
  initialFocusRef?: RefObject<HTMLElement>;
  returnFocusFallbackRef?: RefObject<HTMLElement>;
  onClose: () => void;
  canClose?: boolean;
}): void {
  const onCloseRef = useRef(onClose);
  const canCloseRef = useRef(canClose);
  onCloseRef.current = onClose;
  canCloseRef.current = canClose;

  useEffect(() => {
    if (!open || typeof document === 'undefined') return undefined;
    const dialog = dialogRef.current;
    if (!dialog) return undefined;

    const token = Symbol('logosforge-whiteboard-modal');
    const layer = dialog.closest<HTMLElement>('[data-wb-modal-layer]');
    const previousFocus = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    const entry: ModalEntry = {
      token,
      dialog,
      layer,
      returnFocus: previousFocus,
      fallbackFocus: returnFocusFallbackRef?.current ?? null,
    };
    modalStack.push(entry);
    const isTop = () => modalStack[modalStack.length - 1]?.token === token;

    const focusInside = () => {
      if (!isTop() || !dialog.isConnected) return;
      const initial = initialFocusRef?.current;
      const destination = initial && dialog.contains(initial) && !initial.hasAttribute('disabled')
        ? initial
        : dialog;
      destination.focus({ preventScroll: true });
    };

    // Move focus before hiding the app root; Chromium rejects aria-hidden on an
    // ancestor that still owns the active element.
    focusInside();
    syncBackgroundIsolation();

    const onKeyDown = (event: KeyboardEvent) => {
      if (!isTop()) return;
      if (event.key === 'Escape' && canCloseRef.current) {
        event.preventDefault();
        event.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (event.key !== 'Tab') return;

      const focusable = focusableElements(dialog);
      if (focusable.length === 0) {
        event.preventDefault();
        dialog.focus({ preventScroll: true });
        return;
      }
      const activeIndex = focusable.indexOf(document.activeElement as HTMLElement);
      if (event.shiftKey && activeIndex <= 0) {
        event.preventDefault();
        focusable[focusable.length - 1]!.focus({ preventScroll: true });
      } else if (!event.shiftKey && (activeIndex < 0 || activeIndex === focusable.length - 1)) {
        event.preventDefault();
        focusable[0]!.focus({ preventScroll: true });
      }
    };

    const onFocusIn = (event: FocusEvent) => {
      if (isTop() && event.target instanceof Node && !dialog.contains(event.target)) focusInside();
    };

    document.addEventListener('keydown', onKeyDown, true);
    document.addEventListener('focusin', onFocusIn, true);
    const focusTimer = window.setTimeout(focusInside, 0);

    return () => {
      window.clearTimeout(focusTimer);
      document.removeEventListener('keydown', onKeyDown, true);
      document.removeEventListener('focusin', onFocusIn, true);
      const wasTop = isTop();
      const stackIndex = modalStack.findIndex((candidate) => candidate.token === token);

      // If a parent disappears before its child, carry the child's restoration
      // target through to the parent's own origin rather than a detached node.
      for (const remaining of modalStack) {
        if (remaining.token !== token && remaining.returnFocus && dialog.contains(remaining.returnFocus)) {
          remaining.returnFocus = entry.returnFocus;
        }
      }
      if (stackIndex >= 0) modalStack.splice(stackIndex, 1);
      syncBackgroundIsolation();

      if (wasTop) {
        const nextDialog = modalStack[modalStack.length - 1]?.dialog;
        const returnFocus = entry.returnFocus;
        const destination = canRestoreFocus(returnFocus, nextDialog)
          ? returnFocus
          : canRestoreFocus(entry.fallbackFocus, nextDialog)
            ? entry.fallbackFocus
            : nextDialog;
        destination?.focus({ preventScroll: true });
      }
    };
  }, [dialogRef, initialFocusRef, open, returnFocusFallbackRef]);
}
