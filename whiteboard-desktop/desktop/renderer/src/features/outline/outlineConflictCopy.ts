import {
  OUTLINE_COLORS,
  OUTLINE_STATUSES,
  OUTLINE_TYPES,
  type OutlineNode,
} from './outlineModel';

export interface OutlineConflictEnvelope {
  format: 'logosforge-whiteboard-outline-conflict';
  version: 1;
  document_id: string;
  incarnation: string;
  base_revision: string;
  exported_at: string;
  items: OutlineNode[];
}

const STABLE_ID_RE = /^[^\s\u0000-\u001f\u007f]{1,256}$/;
const MAX_OUTLINE_DEPTH = 512;

function canonicalTimestamp(value: unknown, fallback: string): string {
  if (typeof value !== 'string' || !Number.isFinite(Date.parse(value))) return fallback;
  return new Date(value).toISOString();
}

function contentString(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

/**
 * The outline API intentionally tolerates partial legacy rows. Conflict copies
 * must nevertheless satisfy the stricter recovery-file contract so an
 * app-created rescue is always importable. Preserve every row and repair only
 * invalid identity/structure/value fields; source identity remains provenance.
 */
export function canonicalizeOutlineConflictItems(
  values: OutlineNode[],
  exportedAt: string,
): OutlineNode[] {
  const canonicalBySource = new Map<string, string>();
  const usedIds = new Set<string>();
  const sourceIds = values.map((value, index) => {
    const rawId = typeof value?.id === 'string' ? value.id : '';
    const trimmed = rawId.trim();
    let id = STABLE_ID_RE.test(trimmed) && !usedIds.has(trimmed)
      ? trimmed
      : `recovered-outline-${index + 1}`;
    while (usedIds.has(id)) id = `${id}-copy`;
    usedIds.add(id);
    if (rawId && !canonicalBySource.has(rawId)) canonicalBySource.set(rawId, id);
    if (trimmed && !canonicalBySource.has(trimmed)) canonicalBySource.set(trimmed, id);
    return id;
  });

  const items = values.map((raw, index): OutlineNode => {
    const rawParent = typeof raw?.parentId === 'string' ? raw.parentId : null;
    const parentId = rawParent === null
      ? null
      : canonicalBySource.get(rawParent) ?? canonicalBySource.get(rawParent.trim()) ?? null;
    const rawLink = raw?.link && typeof raw.link === 'object' ? raw.link : null;
    const link = rawLink && Number.isSafeInteger(rawLink.blockIndex) && rawLink.blockIndex >= 0
      ? {
        blockIndex: rawLink.blockIndex,
        quote: contentString(rawLink.quote),
        ...(typeof rawLink.blockId === 'string' && STABLE_ID_RE.test(rawLink.blockId)
          ? { blockId: rawLink.blockId }
          : {}),
      }
      : null;
    const tags = Array.isArray(raw?.tags)
      ? raw.tags
        .filter((tag): tag is string => typeof tag === 'string')
        .filter((tag) => tag.length > 0)
      : [];
    return {
      id: sourceIds[index],
      parentId: parentId === sourceIds[index] ? null : parentId,
      type: (OUTLINE_TYPES as readonly unknown[]).includes(raw?.type) ? raw.type : 'custom',
      title: contentString(raw?.title),
      summary: contentString(raw?.summary),
      order: typeof raw?.order === 'number' && Number.isFinite(raw.order)
        ? raw.order
        : Number.MAX_SAFE_INTEGER,
      collapsed: raw?.collapsed === true,
      completed: raw?.completed === true,
      status: (OUTLINE_STATUSES as readonly unknown[]).includes(raw?.status) ? raw.status : 'none',
      tags,
      colorLabel: (OUTLINE_COLORS as readonly unknown[]).includes(raw?.colorLabel)
        ? raw.colorLabel
        : 'none',
      linkedLineId: typeof raw?.linkedLineId === 'string' && STABLE_ID_RE.test(raw.linkedLineId)
        ? raw.linkedLineId
        : null,
      link,
      createdAt: canonicalTimestamp(raw?.createdAt, exportedAt),
      updatedAt: canonicalTimestamp(raw?.updatedAt, exportedAt),
    };
  });

  // Break legacy orphan/cycle/over-depth relationships deterministically.
  const byId = new Map(items.map((item) => [item.id, item]));
  for (const item of items) {
    const seen = new Set<string>();
    let cursor: OutlineNode | undefined = item;
    let depth = 0;
    while (cursor?.parentId !== null) {
      if (seen.has(cursor.id) || depth >= MAX_OUTLINE_DEPTH) {
        item.parentId = null;
        break;
      }
      seen.add(cursor.id);
      cursor = byId.get(cursor.parentId);
      depth += 1;
      if (!cursor) {
        item.parentId = null;
        break;
      }
    }
  }

  const byParent = new Map<string | null, Array<{ node: OutlineNode; index: number }>>();
  items.forEach((node, index) => {
    const siblings = byParent.get(node.parentId) ?? [];
    siblings.push({ node, index });
    byParent.set(node.parentId, siblings);
  });
  for (const siblings of byParent.values()) {
    siblings
      .sort((left, right) => left.node.order - right.node.order || left.index - right.index)
      .forEach(({ node }, order) => { node.order = order; });
  }
  return items;
}

/** Complete, identity-bound outline rescue format used by Save conflict copy. */
export function outlineConflictEnvelope(
  documentId: string,
  incarnation: string,
  baseRevision: string,
  items: OutlineNode[],
  exportedAt: string = new Date().toISOString(),
): OutlineConflictEnvelope {
  const canonicalExportedAt = canonicalTimestamp(exportedAt, new Date().toISOString());
  return {
    format: 'logosforge-whiteboard-outline-conflict',
    version: 1,
    document_id: documentId,
    incarnation,
    base_revision: baseRevision,
    exported_at: canonicalExportedAt,
    items: canonicalizeOutlineConflictItems(items, canonicalExportedAt),
  };
}
