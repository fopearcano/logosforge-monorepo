/**
 * Frontend API client for the manual story outliner.
 *
 *   - GET /api/outline/items  → load the persisted node list
 *   - PUT /api/outline/items  → replace the persisted node list
 *
 * The backend stores the node shape opaquely (the frontend owns it), so we
 * normalize loaded rows defensively to tolerate partial/legacy data.
 */

import { captureDocumentIdentity, captureDocumentIncarnation, withDoc } from '../../state/currentDocument';
import {
  backendFetch,
  withDocumentIncarnation,
  withExpectedDocumentIncarnation,
} from '../../api/backendAuth';
import { responseError } from '../../api/responseError';
import {
  OUTLINE_COLORS,
  OUTLINE_STATUSES,
  OUTLINE_TYPES,
  type OutlineColor,
  type OutlineItemType,
  type OutlineLink,
  type OutlineNode,
  type OutlineStatus,
} from './outlineModel';

const DEFAULT_BASE_URL = 'http://127.0.0.1:8777';

interface OutlineItemsResponse {
  items?: unknown;
}

const asString = (v: unknown, fallback = ''): string => (typeof v === 'string' ? v : fallback);

function parseLink(v: unknown): OutlineLink | null {
  if (!v || typeof v !== 'object') return null;
  const o = v as Record<string, unknown>;
  if (typeof o.blockIndex !== 'number' || o.blockIndex < 0) return null;
  return {
    blockIndex: o.blockIndex,
    quote: typeof o.quote === 'string' ? o.quote : '',
    ...(typeof o.blockId === 'string' && o.blockId.trim() ? { blockId: o.blockId.trim() } : {}),
  };
}

function normalize(raw: unknown): OutlineNode | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  if (typeof r.id !== 'string' || !r.id) return null;
  const type = typeof r.type === 'string' && (OUTLINE_TYPES as string[]).includes(r.type)
    ? (r.type as OutlineItemType)
    : 'custom';
  const status = typeof r.status === 'string' && (OUTLINE_STATUSES as string[]).includes(r.status)
    ? (r.status as OutlineStatus)
    : 'none';
  const colorLabel = typeof r.colorLabel === 'string' && (OUTLINE_COLORS as string[]).includes(r.colorLabel)
    ? (r.colorLabel as OutlineColor)
    : 'none';
  const tags = Array.isArray(r.tags)
    ? r.tags.filter((t): t is string => typeof t === 'string')
    : [];
  const now = new Date().toISOString();
  return {
    id: r.id,
    parentId: typeof r.parentId === 'string' ? r.parentId : null,
    type,
    title: asString(r.title),
    summary: asString(r.summary),
    order: typeof r.order === 'number' ? r.order : 0,
    collapsed: r.collapsed === true,
    completed: r.completed === true,
    status,
    tags,
    colorLabel,
    linkedLineId: typeof r.linkedLineId === 'string' ? r.linkedLineId : null,
    link: parseLink(r.link),
    createdAt: asString(r.createdAt, now),
    updatedAt: asString(r.updatedAt, now),
  };
}

function toNodes(data: OutlineItemsResponse): OutlineNode[] {
  const list = Array.isArray(data.items) ? data.items : [];
  return list.map(normalize).filter((n): n is OutlineNode => n !== null);
}

export async function getOutlineItems(
  baseUrl: string = DEFAULT_BASE_URL,
  signal?: AbortSignal,
): Promise<OutlineNode[]> {
  const identity = captureDocumentIdentity();
  const res = await backendFetch(withDoc(`${baseUrl}/api/outline/items`), {
    headers: withExpectedDocumentIncarnation(identity.incarnation),
    signal,
  });
  if (!res.ok) throw await responseError(res, 'Could not load the outline');
  return toNodes((await res.json()) as OutlineItemsResponse);
}

export async function getOutlineItemsForDocument(
  baseUrl: string,
  documentId: string,
  signal?: AbortSignal,
  incarnation: string = captureDocumentIncarnation(documentId),
): Promise<OutlineNode[]> {
  const res = await backendFetch(
    `${baseUrl}/api/outline/items?doc=${encodeURIComponent(documentId)}`,
    { headers: withExpectedDocumentIncarnation(incarnation), signal },
  );
  if (!res.ok) throw await responseError(res, 'Could not load the outline');
  return toNodes((await res.json()) as OutlineItemsResponse);
}

export async function saveOutlineItems(
  baseUrl: string = DEFAULT_BASE_URL,
  items: OutlineNode[],
  signal?: AbortSignal,
): Promise<OutlineNode[]> {
  const identity = captureDocumentIdentity();
  const res = await backendFetch(withDoc(`${baseUrl}/api/outline/items`), {
    method: 'PUT',
    headers: withDocumentIncarnation(identity.incarnation, { 'Content-Type': 'application/json' }),
    body: JSON.stringify({ items }),
    signal,
  });
  if (!res.ok) throw await responseError(res, 'Could not save the outline');
  return toNodes((await res.json()) as OutlineItemsResponse);
}

export async function saveOutlineItemsForDocument(
  baseUrl: string,
  documentId: string,
  items: OutlineNode[],
  signal?: AbortSignal,
  incarnation: string = captureDocumentIncarnation(documentId),
): Promise<OutlineNode[]> {
  const res = await backendFetch(
    `${baseUrl}/api/outline/items?doc=${encodeURIComponent(documentId)}`,
    {
      method: 'PUT',
      headers: withDocumentIncarnation(incarnation, { 'Content-Type': 'application/json' }),
      body: JSON.stringify({ items }),
      signal,
    },
  );
  if (!res.ok) throw await responseError(res, 'Could not save the outline');
  return toNodes((await res.json()) as OutlineItemsResponse);
}

// --- external-change signal -------------------------------------------------
// The manual outline lives in its own store (OutlinePanel). When something else
// rewrites the persisted list out-of-band (e.g. a LogosForge import), it emits
// the exact versioned-by-document snapshot so an older GET cannot flash/apply.

const OUTLINE_REFRESH_EVENT = 'lf:outline-refresh';

export interface OutlineRefreshSnapshot {
  documentId: string;
  items: OutlineNode[];
}

export function emitOutlineRefresh(documentId: string, items: OutlineNode[]): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent<OutlineRefreshSnapshot>(OUTLINE_REFRESH_EVENT, {
      detail: { documentId, items },
    }));
  }
}

export function onOutlineRefresh(cb: (snapshot: OutlineRefreshSnapshot) => void): () => void {
  if (typeof window === 'undefined') return () => {};
  const listener = (event: Event) => {
    if (!(event instanceof CustomEvent)) return;
    const snapshot = event.detail as OutlineRefreshSnapshot;
    if (!snapshot || typeof snapshot.documentId !== 'string' || !Array.isArray(snapshot.items)) return;
    cb(snapshot);
  };
  window.addEventListener(OUTLINE_REFRESH_EVENT, listener);
  return () => window.removeEventListener(OUTLINE_REFRESH_EVENT, listener);
}
