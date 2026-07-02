/**
 * The active document id, shared across the app.
 *
 * A whiteboard "document" is identified by its id (the core project id). Every
 * doc-scoped backend route takes an optional `?doc=<id>`; `withDoc()` appends the
 * active id to a URL so the API clients stay one-liners and the hooks don't have
 * to thread the id through every call.
 *
 * Switching is race-free: `flushPendingDocSaves()` runs every registered flusher
 * (the whiteboard + outline autosaves) BEFORE the id changes, so a debounced save
 * for the old document can never land on the new one.
 */

import { useSyncExternalStore } from 'react';

let currentDocId = '';
const subs = new Set<() => void>();
const flushers = new Set<() => Promise<void>>();

export function getCurrentDocId(): string {
  return currentDocId;
}

export function setCurrentDocId(id: string): void {
  if (id === currentDocId) return;
  currentDocId = id;
  subs.forEach((s) => s());
}

export function subscribeCurrentDoc(cb: () => void): () => void {
  subs.add(cb);
  return () => {
    subs.delete(cb);
  };
}

export function useCurrentDocId(): string {
  return useSyncExternalStore(subscribeCurrentDoc, getCurrentDocId, getCurrentDocId);
}

/** Append `?doc=<active id>` (or `&doc=`) to a URL, scoping it to the active doc. */
export function withDoc(url: string): string {
  if (!currentDocId) return url;
  return `${url}${url.includes('?') ? '&' : '?'}doc=${encodeURIComponent(currentDocId)}`;
}

/** Hooks with a debounced save register a flush so a switch can drain it first. */
export function registerDocFlusher(fn: () => Promise<void>): () => void {
  flushers.add(fn);
  return () => {
    flushers.delete(fn);
  };
}

export async function flushPendingDocSaves(): Promise<void> {
  await Promise.all([...flushers].map((f) => f().catch(() => {})));
}

// -- crash recovery: flush pending edits on an unclean exit --------------------
// The debounced autosave may not have fired when the window closes/reloads, so a
// hook with pending edits registers a SYNCHRONOUS flush that fires a `keepalive`
// fetch — those survive page teardown, closing the sub-debounce data-loss window.
const unloadFlushers = new Set<() => void>();

export function registerUnloadFlush(fn: () => void): () => void {
  unloadFlushers.add(fn);
  return () => {
    unloadFlushers.delete(fn);
  };
}

if (typeof window !== 'undefined') {
  window.addEventListener('pagehide', () => {
    unloadFlushers.forEach((f) => {
      try {
        f();
      } catch {
        /* never block unload */
      }
    });
  });
}
