import { useEffect, useRef, type RefObject } from "react";
import {
  isPanelHostHTMLElement,
  isPanelHostNode,
  usePanelHostDocument,
} from "./PanelHost";

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

interface ModalEnvironment {
  ownerDocument: Document;
  modalStack: ModalEntry[];
  backgroundStates: Map<HTMLElement, BackgroundState>;
  unlockedBodyOverflow: string | null;
}

const modalEnvironments = new WeakMap<Document, ModalEnvironment>();

function modalEnvironment(ownerDocument: Document): ModalEnvironment {
  const existing = modalEnvironments.get(ownerDocument);
  if (existing) return existing;
  const created: ModalEnvironment = {
    ownerDocument,
    modalStack: [],
    backgroundStates: new Map(),
    unlockedBodyOverflow: null,
  };
  modalEnvironments.set(ownerDocument, created);
  return created;
}

function restoreBackgroundElement(element: HTMLElement, state: BackgroundState): void {
  element.inert = state.inert;
  if (state.ariaHidden == null) element.removeAttribute("aria-hidden");
  else element.setAttribute("aria-hidden", state.ariaHidden);
}

/** Recompute isolation from the current topmost modal, including out-of-order unmounts. */
function syncBackgroundIsolation(environment: ModalEnvironment): void {
  const { ownerDocument, modalStack, backgroundStates } = environment;
  const top = modalStack[modalStack.length - 1];
  if (!top) {
    for (const [element, state] of backgroundStates) restoreBackgroundElement(element, state);
    backgroundStates.clear();
    if (environment.unlockedBodyOverflow != null) {
      ownerDocument.body.style.overflow = environment.unlockedBodyOverflow;
      environment.unlockedBodyOverflow = null;
    }
    return;
  }

  if (environment.unlockedBodyOverflow == null) {
    environment.unlockedBodyOverflow = ownerDocument.body.style.overflow;
  }
  ownerDocument.body.style.overflow = "hidden";

  let visibleBranch = top.layer;
  while (visibleBranch?.parentElement && visibleBranch.parentElement !== ownerDocument.body) {
    visibleBranch = visibleBranch.parentElement;
  }

  for (const child of Array.from(ownerDocument.body.children)) {
    if (!isPanelHostHTMLElement(child, ownerDocument)) continue;
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

function focusableElements(root: HTMLElement, ownerWindow: Window | null): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((element) => {
    if (element.closest("[hidden],[aria-hidden='true']")) return false;
    const style = ownerWindow?.getComputedStyle(element);
    return element.tabIndex >= 0 && style?.display !== "none" && style?.visibility !== "hidden";
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
  const hostDocument = usePanelHostDocument();
  const onCloseRef = useRef(onClose);
  const canCloseRef = useRef(canClose);
  onCloseRef.current = onClose;
  canCloseRef.current = canClose;

  useEffect(() => {
    if (!open) return undefined;
    const dialog = dialogRef.current;
    if (!dialog) return undefined;
    const ownerDocument = dialog.ownerDocument ?? hostDocument;
    if (!ownerDocument?.body) return undefined;
    const ownerWindow = ownerDocument.defaultView;
    const environment = modalEnvironment(ownerDocument);
    const { modalStack } = environment;

    const token = Symbol("logosforge-modal");
    const layer = dialog.closest<HTMLElement>("[data-lf-modal-layer]");
    const previousFocus = isPanelHostHTMLElement(ownerDocument.activeElement, ownerDocument)
      ? ownerDocument.activeElement
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
    syncBackgroundIsolation(environment);

    const onKeyDown = (event: KeyboardEvent) => {
      if (!isTop()) return;
      if (event.key === "Escape" && canCloseRef.current) {
        event.preventDefault();
        event.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;

      const focusable = focusableElements(dialog, ownerWindow);
      if (focusable.length === 0) {
        event.preventDefault();
        dialog.focus({ preventScroll: true });
        return;
      }
      const activeIndex = focusable.indexOf(ownerDocument.activeElement as HTMLElement);
      if (event.shiftKey && activeIndex <= 0) {
        event.preventDefault();
        focusable[focusable.length - 1]!.focus({ preventScroll: true });
      } else if (!event.shiftKey && (activeIndex < 0 || activeIndex === focusable.length - 1)) {
        event.preventDefault();
        focusable[0]!.focus({ preventScroll: true });
      }
    };

    const onFocusIn = (event: FocusEvent) => {
      if (isTop() && isPanelHostNode(event.target, ownerDocument) && !dialog.contains(event.target)) {
        focusInside();
      }
    };

    ownerDocument.addEventListener("keydown", onKeyDown, true);
    ownerDocument.addEventListener("focusin", onFocusIn, true);
    const focusTimer = ownerWindow
      ? ownerWindow.setTimeout(focusInside, 0)
      : globalThis.setTimeout(focusInside, 0);

    return () => {
      if (ownerWindow) ownerWindow.clearTimeout(focusTimer);
      else globalThis.clearTimeout(focusTimer);
      ownerDocument.removeEventListener("keydown", onKeyDown, true);
      ownerDocument.removeEventListener("focusin", onFocusIn, true);
      const wasTop = isTop();
      const stackIndex = modalStack.findIndex((candidate) => candidate.token === token);
      for (const remaining of modalStack) {
        if (remaining.token !== token && remaining.returnFocus && dialog.contains(remaining.returnFocus)) {
          remaining.returnFocus = entry.returnFocus;
        }
      }
      if (stackIndex >= 0) modalStack.splice(stackIndex, 1);
      syncBackgroundIsolation(environment);
      if (wasTop) {
        const nextDialog = modalStack[modalStack.length - 1]?.dialog;
        const returnFocus = entry.returnFocus;
        const destination = returnFocus?.isConnected && (!nextDialog || nextDialog.contains(returnFocus))
          ? returnFocus
          : nextDialog;
        destination?.focus({ preventScroll: true });
      }
    };
  }, [dialogRef, hostDocument, initialFocusRef, open]);
}
