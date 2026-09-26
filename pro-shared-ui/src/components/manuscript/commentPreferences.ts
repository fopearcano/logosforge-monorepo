import { useCallback, useEffect, useState } from "react";

export const COMMENT_VISIBILITY_STORAGE_KEY = "lf.comments.hideResolved";
export const COMMENT_VISIBILITY_EVENT = "logosforge:comments-visibility-changed";

function browserStorage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
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
): void {
  try {
    storage?.setItem(COMMENT_VISIBILITY_STORAGE_KEY, value ? "1" : "0");
  } catch {
    // Private browsing and locked-down webviews may reject localStorage writes.
  }
  if (typeof window !== "undefined") {
    try {
      window.dispatchEvent(new CustomEvent<boolean>(COMMENT_VISIBILITY_EVENT, { detail: value }));
    } catch {
      // A non-standard embedded host may expose window without event constructors.
    }
  }
}

/** Shared by the panel now and the manuscript mark layer when that Phase 5B slice lands. */
export function useHideResolvedPreference(): [boolean, (value: boolean) => void] {
  const [hideResolved, setHideResolvedState] = useState(readHideResolvedPreference);

  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    const onPreference = (event: Event) => {
      const value = event instanceof CustomEvent && typeof event.detail === "boolean"
        ? event.detail
        : readHideResolvedPreference();
      setHideResolvedState(value);
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === COMMENT_VISIBILITY_STORAGE_KEY || event.key == null) {
        setHideResolvedState(readHideResolvedPreference());
      }
    };
    window.addEventListener(COMMENT_VISIBILITY_EVENT, onPreference);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener(COMMENT_VISIBILITY_EVENT, onPreference);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  const setHideResolved = useCallback((value: boolean) => {
    setHideResolvedState(value);
    writeHideResolvedPreference(value);
  }, []);

  return [hideResolved, setHideResolved];
}
