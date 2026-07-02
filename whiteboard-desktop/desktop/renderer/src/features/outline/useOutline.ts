/**
 * Manual story-outliner store hook.
 *
 * Loads the persisted node list once the backend is ready, exposes editing
 * operations (wrapping the pure `outlineModel` mutations), and autosaves edits
 * back to the backend with a debounce. Selection + which row's details panel is
 * open are tracked here too. New nodes are created with a real id + timestamps
 * and become the selection (so the row autofocuses for inline rename).
 *
 * Mode-aware defaults (Part 8) are read from a live ref so the *current* writing
 * mode decides the type of a freshly added root/child.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { registerDocFlusher, registerUnloadFlush, withDoc } from '../../state/currentDocument';
import { getOutlineItems, onOutlineRefresh, saveOutlineItems } from './outlineApi';
import * as M from './outlineModel';
import {
  EMPTY_FILTER,
  type OutlineColor,
  type OutlineFilter,
  type OutlineItemType,
  type OutlineNode,
  type OutlineStatus,
} from './outlineModel';

const SAVE_DEBOUNCE_MS = 600;
const ZOOM_KEY = 'lf-outline-zoom';

function loadZoom(): string | null {
  try {
    return localStorage.getItem(ZOOM_KEY) || null;
  } catch {
    return null;
  }
}
function saveZoom(id: string | null): void {
  try {
    if (id) localStorage.setItem(ZOOM_KEY, id);
    else localStorage.removeItem(ZOOM_KEY);
  } catch {
    /* ignore */
  }
}

type SaveState = 'idle' | 'saving' | 'saved' | 'error';

function newId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `o-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

const now = (): string => new Date().toISOString();

export interface OutlineStore {
  items: OutlineNode[];
  loading: boolean;
  error: string | null;
  saveState: SaveState;
  selectedId: string | null;
  setSelectedId: (id: string | null) => void;
  detailsOpenId: string | null;
  setDetailsOpenId: (id: string | null) => void;
  // view: zoom (hoist) + search/filter
  zoomRootId: string | null;
  zoomInto: (id: string) => void;
  zoomOut: () => void;
  setZoomRootId: (id: string | null) => void;
  filter: OutlineFilter;
  setFilter: (patch: Partial<OutlineFilter>) => void;
  clearFilter: () => void;
  // mutations
  addRoot: () => void;
  addChild: (parentId: string) => void;
  addSibling: (afterId: string) => void;
  rename: (id: string, title: string) => void;
  setType: (id: string, type: OutlineItemType) => void;
  setNotes: (id: string, notes: string) => void;
  setStatus: (id: string, status: OutlineStatus) => void;
  setColorLabel: (id: string, color: OutlineColor) => void;
  toggleCompleted: (id: string) => void;
  addTag: (id: string, tag: string) => void;
  removeTag: (id: string, tag: string) => void;
  duplicate: (id: string) => void;
  remove: (id: string) => void;
  indent: (id: string) => void;
  outdent: (id: string) => void;
  moveUp: (id: string) => void;
  moveDown: (id: string) => void;
  toggleCollapse: (id: string) => void;
  collapseBranch: (id: string, collapsed: boolean) => void;
  collapseAll: () => void;
  expandAll: () => void;
}

interface Options {
  baseUrl: string;
  ready: boolean;
  mode: string;
}

export function useOutline({ baseUrl, ready, mode }: Options): OutlineStore {
  const [items, setItems] = useState<OutlineNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<SaveState>('idle');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detailsOpenId, setDetailsOpenId] = useState<string | null>(null);
  const [zoomRootId, setZoomState] = useState<string | null>(loadZoom);
  const [filter, setFilterState] = useState<OutlineFilter>(EMPTY_FILTER);

  // Live refs so callbacks stay stable but always see current values.
  const itemsRef = useRef<OutlineNode[]>(items);
  const zoomRef = useRef<string | null>(zoomRootId);
  zoomRef.current = zoomRootId;
  const modeRef = useRef(mode);
  modeRef.current = mode;
  const baseUrlRef = useRef(baseUrl);
  baseUrlRef.current = baseUrl;

  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pending = useRef<OutlineNode[] | null>(null);

  const flush = useCallback(async () => {
    const next = pending.current;
    if (!next) return;
    pending.current = null;
    setSaveState('saving');
    try {
      await saveOutlineItems(baseUrlRef.current, next);
      setSaveState('saved');
    } catch {
      setSaveState('error');
    }
  }, []);

  const scheduleSave = useCallback(
    (next: OutlineNode[]) => {
      pending.current = next;
      setSaveState('saving');
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => void flush(), SAVE_DEBOUNCE_MS);
    },
    [flush],
  );

  // Apply a pure model mutation, update state + ref, and queue a save.
  const mutate = useCallback(
    (fn: (items: OutlineNode[]) => OutlineNode[]): OutlineNode[] => {
      const next = fn(itemsRef.current);
      itemsRef.current = next;
      setItems(next);
      scheduleSave(next);
      return next;
    },
    [scheduleSave],
  );

  // Load once the backend is reachable.
  useEffect(() => {
    if (!ready) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    getOutlineItems(baseUrl, controller.signal)
      .then((loaded) => {
        itemsRef.current = loaded;
        setItems(loaded);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      });
    return () => controller.abort();
  }, [ready, baseUrl]);

  // Reload when the persisted list is rewritten out-of-band (e.g. a LogosForge
  // import). Keeps the panel in sync without a manual refresh.
  useEffect(() => {
    if (!ready) return undefined;
    return onOutlineRefresh(() => {
      getOutlineItems(baseUrl)
        .then((loaded) => {
          itemsRef.current = loaded;
          setItems(loaded);
        })
        .catch(() => {
          /* best-effort; the next mount reload will recover */
        });
    });
  }, [ready, baseUrl]);

  // Flush a pending save on unmount (e.g. when the Outline panel is hidden).
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
      if (pending.current) void flush();
    },
    [flush],
  );

  // Drain a pending outline save into the OLD document before a switch changes
  // the active id (the new doc reloads via emitOutlineRefresh).
  useEffect(() => registerDocFlusher(flush), [flush]);

  // Crash recovery: flush the pending outline with a keepalive PUT on an unclean exit.
  useEffect(
    () =>
      registerUnloadFlush(() => {
        const items = pending.current;
        if (!items) return;
        fetch(withDoc(`${baseUrlRef.current}/api/outline/items`), {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ items }),
          keepalive: true,
        });
      }),
    [],
  );

  // Keep the zoom root valid — clear it if that node vanishes (delete/import).
  useEffect(() => {
    if (zoomRootId && !M.getNode(items, zoomRootId)) {
      setZoomState(null);
      saveZoom(null);
    }
  }, [items, zoomRootId]);

  const setZoomRootId = useCallback((id: string | null) => {
    setZoomState(id);
    saveZoom(id);
  }, []);
  const zoomInto = useCallback((id: string) => setZoomRootId(id), [setZoomRootId]);
  const zoomOut = useCallback(() => {
    const z = zoomRef.current;
    if (!z) return;
    setZoomRootId(M.getNode(itemsRef.current, z)?.parentId ?? null);
  }, [setZoomRootId]);

  const setFilter = useCallback(
    (patch: Partial<OutlineFilter>) => setFilterState((prev) => ({ ...prev, ...patch })),
    [],
  );
  const clearFilter = useCallback(() => setFilterState(EMPTY_FILTER), []);

  const addRoot = useCallback(() => {
    const id = newId();
    const node = M.createNode(id, M.rootType(modeRef.current), null, now());
    mutate((list) => M.insertRoot(list, node));
    setSelectedId(id);
    setDetailsOpenId(null);
  }, [mutate]);

  const addChild = useCallback(
    (parentId: string) => {
      const parent = M.getNode(itemsRef.current, parentId);
      const type = parent
        ? M.childType(modeRef.current, parent.type)
        : M.rootType(modeRef.current);
      const id = newId();
      const node = M.createNode(id, type, parentId, now());
      mutate((list) => M.insertChild(list, parentId, node));
      setSelectedId(id);
      setDetailsOpenId(null);
    },
    [mutate],
  );

  const addSibling = useCallback(
    (afterId: string) => {
      const after = M.getNode(itemsRef.current, afterId);
      if (!after) {
        addRoot();
        return;
      }
      const id = newId();
      const node = M.createNode(id, after.type, after.parentId, now());
      mutate((list) => M.insertSibling(list, afterId, node));
      setSelectedId(id);
      setDetailsOpenId(null);
    },
    [mutate, addRoot],
  );

  const rename = useCallback(
    (id: string, title: string) => mutate((list) => M.rename(list, id, title, now())),
    [mutate],
  );
  const setType = useCallback(
    (id: string, type: OutlineItemType) => mutate((list) => M.setNodeType(list, id, type, now())),
    [mutate],
  );
  const setNotes = useCallback(
    (id: string, notes: string) => mutate((list) => M.setNotes(list, id, notes, now())),
    [mutate],
  );
  const setStatus = useCallback(
    (id: string, status: OutlineStatus) => mutate((list) => M.setStatus(list, id, status, now())),
    [mutate],
  );
  const setColorLabel = useCallback(
    (id: string, color: OutlineColor) => mutate((list) => M.setColorLabel(list, id, color, now())),
    [mutate],
  );
  const toggleCompleted = useCallback(
    (id: string) => mutate((list) => M.toggleCompleted(list, id, now())),
    [mutate],
  );
  const addTag = useCallback(
    (id: string, tag: string) =>
      mutate((list) => {
        const node = M.getNode(list, id);
        const t = M.normalizeTag(tag);
        if (!node || !t) return list;
        return M.setTags(list, id, [...node.tags, t], now());
      }),
    [mutate],
  );
  const removeTag = useCallback(
    (id: string, tag: string) =>
      mutate((list) => {
        const node = M.getNode(list, id);
        if (!node) return list;
        const t = M.normalizeTag(tag);
        return M.setTags(list, id, node.tags.filter((x) => x !== t), now());
      }),
    [mutate],
  );
  const duplicate = useCallback(
    (id: string) => {
      const ids = [id, ...M.descendantIds(itemsRef.current, id)];
      const map = new Map(ids.map((sid) => [sid, newId()] as const));
      mutate((list) => M.cloneSubtreeWithMap(list, id, map, now()));
      const newRoot = map.get(id);
      if (newRoot) setSelectedId(newRoot);
    },
    [mutate],
  );

  const remove = useCallback(
    (id: string) => {
      const fallback = M.prevVisibleId(itemsRef.current, id) ?? M.nextVisibleId(itemsRef.current, id);
      mutate((list) => M.removeItem(list, id));
      setSelectedId(fallback);
      setDetailsOpenId((open) => (open === id ? null : open));
    },
    [mutate],
  );

  const indent = useCallback((id: string) => mutate((list) => M.indentItem(list, id)), [mutate]);
  const outdent = useCallback((id: string) => mutate((list) => M.outdentItem(list, id)), [mutate]);
  const moveUp = useCallback((id: string) => mutate((list) => M.moveUp(list, id)), [mutate]);
  const moveDown = useCallback((id: string) => mutate((list) => M.moveDown(list, id)), [mutate]);
  const toggleCollapse = useCallback(
    (id: string) => mutate((list) => M.toggleCollapsed(list, id)),
    [mutate],
  );
  const collapseBranch = useCallback(
    (id: string, collapsed: boolean) => mutate((list) => M.setBranchCollapsed(list, id, collapsed)),
    [mutate],
  );
  const collapseAll = useCallback(() => mutate((list) => M.setAllCollapsed(list, true)), [mutate]);
  const expandAll = useCallback(() => mutate((list) => M.setAllCollapsed(list, false)), [mutate]);

  return {
    items,
    loading,
    error,
    saveState,
    selectedId,
    setSelectedId,
    detailsOpenId,
    setDetailsOpenId,
    zoomRootId,
    zoomInto,
    zoomOut,
    setZoomRootId,
    filter,
    setFilter,
    clearFilter,
    addRoot,
    addChild,
    addSibling,
    rename,
    setType,
    setNotes,
    setStatus,
    setColorLabel,
    toggleCompleted,
    addTag,
    removeTag,
    duplicate,
    remove,
    indent,
    outdent,
    moveUp,
    moveDown,
    toggleCollapse,
    collapseBranch,
    collapseAll,
    expandAll,
  };
}
