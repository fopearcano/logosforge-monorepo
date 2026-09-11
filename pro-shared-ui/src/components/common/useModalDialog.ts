import { useEffect, useRef, type RefObject } from "react";

const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

interface ModalEntry {
  token: symbol;
  dialog: HTMLElement;
  layer: HTMLElement | null;
  returnFocus: HTMLElement | null;
}

interface BackgroundState {
  inert: boolean;
  ariaHidden: string | null;
}

const modalStack: ModalEntry[] = [];
const backgroundStates = new Map<HTMLElement, BackgroundState>();
let unlockedBodyOverflow: string | null = null;

function restoreBackgroundElement(element: HTMLElement, state: BackgroundState): void {
  element.inert = state.inert;
  if (state.ariaHidden == null) element.removeAttribute("aria-hidden");
  else element.setAttribute("aria-hidden", state.ariaHidden);
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
  document.body.style.overflow = "hidden";

  let visibleBranch = top.layer;
  while (visibleBranch?.parentElement && visibleBranch.parentElement !== document.body) {
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
        ariaHidden: child.getAttribute("aria-hidden"),
      });
    }
    child.inert = true;
    child.setAttribute("aria-hidden", "true");
  }
}

function focusableElements(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((element) => {
    if (element.closest("[hidden],[aria-hidden='true']")) return false;
    const style = window.getComputedStyle(element);
    return element.tabIndex >= 0 && style.display !== "none" && style.visibility !== "hidden";
  });
}

/**
 * Gives a modal its complete keyboard contract: initial focus, a Tab loop,
 * Escape handling, background isolation and focus restoration on close.
 * Callback/permission refs deliberately keep the effect stable while a dialog
 * rerenders (for example while an Apply request changes from idle to busy).
 */
export function useModalDialog<T extends HTMLElement>({
  open,
  dialogRef,
  initialFocusRef,
  onClose,
  canClose = true,
}: {
  open: boolean;
  dialogRef: RefObject<T>;
  initialFocusRef?: RefObject<HTMLElement>;
  onClose: () => void;
  canClose?: boolean;
}): void {
  const onCloseRef = useRef(onClose);
  const canCloseRef = useRef(canClose);
  onCloseRef.current = onClose;
  canCloseRef.current = canClose;

  useEffect(() => {
    if (!open || typeof document === "undefined") return undefined;
    const dialog = dialogRef.current;
    if (!dialog) return undefined;

    const token = Symbol("logosforge-modal");
    const layer = dialog.closest<HTMLElement>("[data-lf-modal-layer]");
    const previousFocus = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    const entry: ModalEntry = { token, dialog, layer, returnFocus: previousFocus };
    modalStack.push(entry);
    const isTop = () => modalStack[modalStack.length - 1]?.token === token;

    const focusInside = () => {
      if (!isTop() || !dialog.isConnected) return;
      const initial = initialFocusRef?.current;
      const destination = initial && !initial.hasAttribute("disabled")
        ? initial
        : dialog;
      destination.focus({ preventScroll: true });
    };

    // Move focus before applying aria-hidden, otherwise Chromium rejects hiding
    // the application root while it still owns the active element.
    focusInside();
    syncBackgroundIsolation();

    const onKeyDown = (event: KeyboardEvent) => {
      if (!isTop()) return;
      if (event.key === "Escape" && canCloseRef.current) {
        event.preventDefault();
        event.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;

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
      if (isTop() && event.target instanceof Node && !dialog.contains(event.target)) {
        focusInside();
      }
    };

    document.addEventListener("keydown", onKeyDown, true);
    document.addEventListener("focusin", onFocusIn, true);
    const focusTimer = window.setTimeout(focusInside, 0);

    return () => {
      window.clearTimeout(focusTimer);
      document.removeEventListener("keydown", onKeyDown, true);
      document.removeEventListener("focusin", onFocusIn, true);
      const wasTop = isTop();
      const stackIndex = modalStack.findIndex((candidate) => candidate.token === token);
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
        const destination = returnFocus?.isConnected && (!nextDialog || nextDialog.contains(returnFocus))
          ? returnFocus
          : nextDialog;
        destination?.focus({ preventScroll: true });
      }
    };
  }, [dialogRef, initialFocusRef, open]);
}
