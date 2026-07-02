/** Shared open/closed state for the Comments side panel — the title-bar button
 *  and the Ctrl/Cmd+Shift+C hotkey (App) toggle it; WhiteboardPage renders the
 *  panel from it. A tiny external store so both sides stay in sync. */

import { useSyncExternalStore } from 'react';

let open = false;
const subs = new Set<() => void>();

export function isCommentsPanelOpen(): boolean {
  return open;
}

export function setCommentsPanelOpen(value: boolean): void {
  if (value === open) return;
  open = value;
  subs.forEach((s) => s());
}

export function toggleCommentsPanel(): void {
  setCommentsPanelOpen(!open);
}

function subscribe(cb: () => void): () => void {
  subs.add(cb);
  return () => {
    subs.delete(cb);
  };
}

export function useCommentsPanelOpen(): boolean {
  return useSyncExternalStore(subscribe, isCommentsPanelOpen, isCommentsPanelOpen);
}

// --- "hide resolved" preference (persisted) ---------------------------------
// Filters resolved comments out of BOTH the panel list and the editor highlights
// (WhiteboardPage drops them from the reconcile input). Orphan cleanup still runs
// over all comments, so a resolved note whose block is deleted is still removed.

const HIDE_RESOLVED_KEY = 'logosforge-comments-hide-resolved';

function readHideResolved(): boolean {
  try {
    return localStorage.getItem(HIDE_RESOLVED_KEY) === '1';
  } catch {
    return false;
  }
}

let hideResolved = readHideResolved();
const hideSubs = new Set<() => void>();

export function isResolvedHidden(): boolean {
  return hideResolved;
}

export function setResolvedHidden(value: boolean): void {
  if (value === hideResolved) return;
  hideResolved = value;
  try {
    localStorage.setItem(HIDE_RESOLVED_KEY, value ? '1' : '0');
  } catch {
    /* private mode / no storage — keep the in-memory value */
  }
  hideSubs.forEach((s) => s());
}

export function toggleResolvedHidden(): void {
  setResolvedHidden(!hideResolved);
}

function subscribeHide(cb: () => void): () => void {
  hideSubs.add(cb);
  return () => {
    hideSubs.delete(cb);
  };
}

export function useResolvedHidden(): boolean {
  return useSyncExternalStore(subscribeHide, isResolvedHidden, isResolvedHidden);
}
