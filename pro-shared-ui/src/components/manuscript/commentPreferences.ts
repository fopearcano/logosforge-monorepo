import { useCallback, useEffect, useState } from "react";
import { usePanelHostWindow } from "../common/PanelHost";

export const COMMENT_VISIBILITY_STORAGE_KEY = "lf.comments.hideResolved";
export const COMMENT_VISIBILITY_EVENT = "logosforge:comments-visibility-changed";

function ambientWindow(): Window | null {
  return typeof window === "undefined" ? null : window;
}

function browserStorage(ownerWindow: Window | null = ambientWindow()): Storage | null {
  if (!ownerWindow) return null;
  try {
    return ownerWindow.localStorage;
  } catch {
    return null;
  }
}

/** Read the shared comment-mark visibility preference without assuming storage is available. */
export function readHideResolvedPreference(storage: Pick<Storage, "getItem"> | null = browserStorage()): boolean {
  if (!storage) return false;
  try {
    return storage.getItem(COMMENT_VISIBILITY_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

/** Persist and broadcast the shared preference. Storage failures never break comment review. */
export function writeHideResolvedPreference(
  value: boolean,
  storage: Pick<Storage, "setItem"> | null = browserStorage(),
  ownerWindow: Window | null = ambientWindow(),
): void {
  try {
    storage?.setItem(COMMENT_VISIBILITY_STORAGE_KEY, value ? "1" : "0");
  } catch {
    // Private browsing and locked-down webviews may reject localStorage writes.
  }
  if (ownerWindow) {
    try {
      const event = ownerWindow.document.createEvent("CustomEvent");
      event.initCustomEvent(COMMENT_VISIBILITY_EVENT, false, false, value);
      ownerWindow.dispatchEvent(event);
    } catch {
      // A non-standard embedded host may expose window without event constructors.
    }
  }
}

/** Shared by the panel now and the manuscript mark layer when that Phase 5B slice lands. */
export function useHideResolvedPreference(): [boolean, (value: boolean) => void] {
  const ownerWindow = usePanelHostWindow();
  const [hideResolved, setHideResolvedState] = useState(() => readHideResolvedPreference(browserStorage(ownerWindow)));

  useEffect(() => {
    if (!ownerWindow) return undefined;
    const onPreference = (event: Event) => {
      const detail = (event as CustomEvent<unknown>).detail;
      const value = typeof detail === "boolean"
        ? detail
        : readHideResolvedPreference(browserStorage(ownerWindow));
      setHideResolvedState(value);
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === COMMENT_VISIBILITY_STORAGE_KEY || event.key == null) {
        setHideResolvedState(readHideResolvedPreference(browserStorage(ownerWindow)));
      }
    };
    setHideResolvedState(readHideResolvedPreference(browserStorage(ownerWindow)));
    ownerWindow.addEventListener(COMMENT_VISIBILITY_EVENT, onPreference);
    ownerWindow.addEventListener("storage", onStorage);
    return () => {
      ownerWindow.removeEventListener(COMMENT_VISIBILITY_EVENT, onPreference);
      ownerWindow.removeEventListener("storage", onStorage);
    };
  }, [ownerWindow]);

  const setHideResolved = useCallback((value: boolean) => {
    setHideResolvedState(value);
    writeHideResolvedPreference(value, browserStorage(ownerWindow), ownerWindow);
  }, [ownerWindow]);

  return [hideResolved, setHideResolved];
}
