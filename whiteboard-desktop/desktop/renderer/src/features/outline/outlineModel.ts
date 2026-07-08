/**
 * Manual story-outliner model (pure, testable).
 *
 * Items are a flat list, each carrying `parentId` + `order`; the tree is derived
 * for rendering. All mutations are pure (return a new, re-indexed list). No
 * editor/DOM/backend imports.
 */

export type OutlineItemType =
  | 'act'
  | 'part'
  | 'chapter'
  | 'sequence'
  | 'scene'
  | 'beat'
  | 'custom';

export const OUTLINE_TYPES: OutlineItemType[] = [
  'act',
  'part',
  'chapter',
  'sequence',
  'scene',
  'beat',
  'custom',
];

export const TYPE_LABELS: Record<OutlineItemType, string> = {
  act: 'Act',
  part: 'Part',
  chapter: 'Chapter',
  sequence: 'Sequence',
  scene: 'Scene',
  beat: 'Beat',
  custom: 'Custom',
};

// --- status (story progress) ------------------------------------------------

export type OutlineStatus = 'none' | 'todo' | 'drafting' | 'revised' | 'done';

export const OUTLINE_STATUSES: OutlineStatus[] = ['none', 'todo', 'drafting', 'revised', 'done'];

export const STATUS_LABELS: Record<OutlineStatus, string> = {
  none: 'No status',
  todo: 'To do',
  drafting: 'Drafting',
  revised: 'Revised',
  done: 'Done',
};

/** Short badge text (kept tiny for the compact panel). */
export const STATUS_BADGE: Record<OutlineStatus, string> = {
  none: '',
  todo: 'To do',
  drafting: 'Draft',
  revised: 'Rev',
  done: 'Done',
};

// --- color labels (writing/planning aid; user assigns meaning) --------------

export type OutlineColor =
  | 'none'
  | 'red'
  | 'orange'
  | 'yellow'
  | 'green'
  | 'blue'
  | 'purple'
  | 'gray';

export const OUTLINE_COLORS: OutlineColor[] = [
  'none',
  'red',
  'orange',
  'yellow',
  'green',
  'blue',
  'purple',
  'gray',
];

export const COLOR_LABELS: Record<OutlineColor, string> = {
  none: 'No color',
  red: 'Red',
  orange: 'Orange',
  yellow: 'Yellow',
  green: 'Green',
  blue: 'Blue',
  purple: 'Purple',
  gray: 'Gray',
};

/**
 * A hard link from an outline node to a place in the manuscript. Anchored by
 * block INDEX (blocks have no stable id) plus a `quote` snapshot of that block's
 * text, so the index can be re-located after edits shift it (see reanchorLinks).
 */
export interface OutlineLink {
  blockIndex: number;
  quote: string;
}

export interface OutlineNode {
  id: string;
  parentId: string | null;
  type: OutlineItemType;
  title: string;
  order: number;
  collapsed: boolean;
  completed: boolean;
  status: OutlineStatus;
  tags: string[];
  colorLabel: OutlineColor;
  linkedLineId?: string | null;
  /** Optional binding to a manuscript block (the section this node "owns"). */
  link?: OutlineLink | null;
  createdAt: string;
  updatedAt: string;
}

export function createNode(
  id: string,
  type: OutlineItemType,
  parentId: string | null,
  now: string,
): OutlineNode {
  return {
    id,
    parentId,
    type,
    title: '',
    order: 0,
    collapsed: false,
    completed: false,
    status: 'none',
    tags: [],
    colorLabel: 'none',
    linkedLineId: null,
    link: null,
    createdAt: now,
    updatedAt: now,
  };
}

// --- mode-aware defaults (Part 8) ------------------------------------------

export function rootType(mode: string): OutlineItemType {
  switch (mode) {
    case 'screenplay':
      return 'act';
    case 'novel':
      return 'chapter';
    case 'scene':
      return 'scene';
    default:
      return 'chapter';
  }
}

export function childType(mode: string, parentType: OutlineItemType): OutlineItemType {
  const chains: Record<string, Partial<Record<OutlineItemType, OutlineItemType>>> = {
    screenplay: { act: 'sequence', sequence: 'scene', scene: 'beat' },
    novel: { part: 'chapter', chapter: 'scene', scene: 'beat' },
    scene: { scene: 'beat' },
  };
  return chains[mode]?.[parentType] ?? 'custom';
}

/**
 * Structural depth of each type, mode-independent. `act`/`part` are top-level
 * containers (0); `chapter`/`sequence` the next level (1); `scene` (2); `beat`
 * (3). They share ranks because they don't co-occur across modes (screenplay
 * act→sequence→scene→beat; novel part→chapter→scene→beat). `custom` is treated
 * as a leaf so it always nests under whatever is selected.
 */
export const TYPE_RANK: Record<OutlineItemType, number> = {
  act: 0,
  part: 0,
  chapter: 1,
  sequence: 1,
  scene: 2,
  beat: 3,
  custom: 99,
};

export interface TypedPlacement {
  parentId: string | null;
  afterId: string | null;
}

/**
 * Where a newly-added node of `type` should land, given the current selection —
 * the "auto-structure" rule. Walking up from the selected node (inclusive):
 *   - the first ancestor SHALLOWER than the new type → nest as its child
 *     (e.g. add a Scene while an Act is selected → Scene under the Act);
 *   - the first ancestor at the SAME rank → add as its sibling
 *     (add a Scene while a Scene/Beat is selected → a sibling Scene);
 *   - deeper ancestors are skipped (you're adding something higher-level).
 * Nothing selected, or the walk reaches the top → a new root. Pure.
 */
export function placeForType(
  items: OutlineNode[],
  selectedId: string | null,
  type: OutlineItemType,
): TypedPlacement {
  if (!selectedId || !getNode(items, selectedId)) return { parentId: null, afterId: null };
  const newRank = TYPE_RANK[type];
  const chain = ancestorChain(items, selectedId); // root → … → selected
  for (let i = chain.length - 1; i >= 0; i--) {
    const n = chain[i];
    const r = TYPE_RANK[n.type];
    if (r < newRank) return { parentId: n.id, afterId: null };
    if (r === newRank) return { parentId: n.parentId, afterId: n.id };
  }
  return { parentId: null, afterId: null };
}

// --- queries ----------------------------------------------------------------

export function childrenOf(items: OutlineNode[], parentId: string | null): OutlineNode[] {
  return items.filter((i) => i.parentId === parentId).sort((a, b) => a.order - b.order);
}

export function getNode(items: OutlineNode[], id: string): OutlineNode | undefined {
  return items.find((i) => i.id === id);
}

export function hasChildren(items: OutlineNode[], id: string): boolean {
  return items.some((i) => i.parentId === id);
}

export function descendantIds(items: OutlineNode[], id: string): string[] {
  const out: string[] = [];
  const stack = childrenOf(items, id).map((c) => c.id);
  while (stack.length) {
    const cur = stack.pop() as string;
    out.push(cur);
    for (const c of childrenOf(items, cur)) stack.push(c.id);
  }
  return out;
}

export interface VisibleRow {
  node: OutlineNode;
  depth: number;
  hasChildren: boolean;
}

/** Depth-first list of rows that are currently visible (collapsed subtrees skipped). */
export function visibleRows(items: OutlineNode[]): VisibleRow[] {
  const out: VisibleRow[] = [];
  const walk = (parentId: string | null, depth: number) => {
    for (const node of childrenOf(items, parentId)) {
      const kids = hasChildren(items, node.id);
      out.push({ node, depth, hasChildren: kids });
      if (kids && !node.collapsed) walk(node.id, depth + 1);
    }
  };
  walk(null, 0);
  return out;
}

export function prevVisibleId(items: OutlineNode[], id: string): string | null {
  const rows = visibleRows(items);
  const i = rows.findIndex((r) => r.node.id === id);
  return i > 0 ? rows[i - 1].node.id : null;
}
export function nextVisibleId(items: OutlineNode[], id: string): string | null {
  const rows = visibleRows(items);
  const i = rows.findIndex((r) => r.node.id === id);
  return i >= 0 && i < rows.length - 1 ? rows[i + 1].node.id : null;
}
export function firstChildId(items: OutlineNode[], id: string): string | null {
  const c = childrenOf(items, id);
  return c.length ? c[0].id : null;
}

// --- mutations (pure; re-index orders to 0..n per sibling group) -------------

function reindex(items: OutlineNode[]): OutlineNode[] {
  const byParent = new Map<string | null, OutlineNode[]>();
  for (const i of items) {
    const group = byParent.get(i.parentId);
    if (group) group.push(i);
    else byParent.set(i.parentId, [i]);
  }
  const result: OutlineNode[] = [];
  for (const group of byParent.values()) {
    group.sort((a, b) => a.order - b.order);
    group.forEach((n, idx) => result.push(n.order === idx ? n : { ...n, order: idx }));
  }
  return result;
}

const maxOrder = (items: OutlineNode[], parentId: string | null): number =>
  childrenOf(items, parentId).reduce((m, n) => Math.max(m, n.order), -1);

export function insertRoot(items: OutlineNode[], node: OutlineNode): OutlineNode[] {
  return reindex([...items, { ...node, parentId: null, order: maxOrder(items, null) + 1 }]);
}

export function insertChild(items: OutlineNode[], parentId: string, node: OutlineNode): OutlineNode[] {
  const expanded = items.map((i) => (i.id === parentId && i.collapsed ? { ...i, collapsed: false } : i));
  return reindex([...expanded, { ...node, parentId, order: maxOrder(items, parentId) + 1 }]);
}

export function insertSibling(items: OutlineNode[], afterId: string, node: OutlineNode): OutlineNode[] {
  const after = getNode(items, afterId);
  if (!after) return insertRoot(items, node);
  return reindex([...items, { ...node, parentId: after.parentId, order: after.order + 0.5 }]);
}

export function rename(items: OutlineNode[], id: string, title: string, now: string): OutlineNode[] {
  return items.map((i) => (i.id === id ? { ...i, title, updatedAt: now } : i));
}
export function setNodeType(items: OutlineNode[], id: string, type: OutlineItemType, now: string): OutlineNode[] {
  return items.map((i) => (i.id === id ? { ...i, type, updatedAt: now } : i));
}

export function toggleCollapsed(items: OutlineNode[], id: string): OutlineNode[] {
  return items.map((i) => (i.id === id ? { ...i, collapsed: !i.collapsed } : i));
}
export function setCollapsed(items: OutlineNode[], id: string, collapsed: boolean): OutlineNode[] {
  return items.map((i) => (i.id === id ? { ...i, collapsed } : i));
}
export function setAllCollapsed(items: OutlineNode[], collapsed: boolean): OutlineNode[] {
  const parents = new Set(items.map((i) => i.parentId).filter((p): p is string => p !== null));
  return items.map((i) => (parents.has(i.id) ? { ...i, collapsed } : i));
}

/** Collapse/expand a node and all its descendant parents (Alt+click disclosure). */
export function setBranchCollapsed(items: OutlineNode[], id: string, collapsed: boolean): OutlineNode[] {
  const branch = new Set([id, ...descendantIds(items, id)]);
  return items.map((i) => (branch.has(i.id) && hasChildren(items, i.id) ? { ...i, collapsed } : i));
}

export function removeItem(items: OutlineNode[], id: string): OutlineNode[] {
  const doomed = new Set([id, ...descendantIds(items, id)]);
  return reindex(items.filter((i) => !doomed.has(i.id)));
}

export function indentItem(items: OutlineNode[], id: string): OutlineNode[] {
  const node = getNode(items, id);
  if (!node) return items;
  const sibs = childrenOf(items, node.parentId);
  const idx = sibs.findIndex((s) => s.id === id);
  if (idx <= 0) return items; // no previous sibling to nest under
  const newParent = sibs[idx - 1];
  const order = maxOrder(items, newParent.id) + 1;
  return reindex(
    items.map((i) => {
      if (i.id === id) return { ...i, parentId: newParent.id, order };
      if (i.id === newParent.id && i.collapsed) return { ...i, collapsed: false };
      return i;
    }),
  );
}

export function outdentItem(items: OutlineNode[], id: string): OutlineNode[] {
  const node = getNode(items, id);
  if (!node || node.parentId === null) return items; // already top-level
  const parent = getNode(items, node.parentId);
  if (!parent) return items;
  return reindex(
    items.map((i) => (i.id === id ? { ...i, parentId: parent.parentId, order: parent.order + 0.5 } : i)),
  );
}

export function moveUp(items: OutlineNode[], id: string): OutlineNode[] {
  const node = getNode(items, id);
  if (!node) return items;
  const sibs = childrenOf(items, node.parentId);
  const idx = sibs.findIndex((s) => s.id === id);
  if (idx <= 0) return items;
  const prev = sibs[idx - 1];
  return reindex(
    items.map((i) => {
      if (i.id === id) return { ...i, order: prev.order };
      if (i.id === prev.id) return { ...i, order: node.order };
      return i;
    }),
  );
}

export function moveDown(items: OutlineNode[], id: string): OutlineNode[] {
  const node = getNode(items, id);
  if (!node) return items;
  const sibs = childrenOf(items, node.parentId);
  const idx = sibs.findIndex((s) => s.id === id);
  if (idx === -1 || idx >= sibs.length - 1) return items;
  const next = sibs[idx + 1];
  return reindex(
    items.map((i) => {
      if (i.id === id) return { ...i, order: next.order };
      if (i.id === next.id) return { ...i, order: node.order };
      return i;
    }),
  );
}

// --- drag-to-reorder --------------------------------------------------------

export type DropPosition = 'before' | 'after' | 'child';

/** True if `candidateId` is `id` itself or an ancestor of `id`. */
export function isSelfOrAncestor(items: OutlineNode[], candidateId: string, id: string): boolean {
  let cur: OutlineNode | undefined = getNode(items, id);
  while (cur) {
    if (cur.id === candidateId) return true;
    cur = cur.parentId ? getNode(items, cur.parentId) : undefined;
  }
  return false;
}

/**
 * Move `dragId` relative to `targetId` (drag-and-drop). `before`/`after` make it
 * a sibling of the target; `child` nests it as the target's last child (and
 * expands the target). Reparents + reorders, then reindexes. No-op when the drop
 * would place a branch inside itself (target is the dragged node or a descendant).
 */
export function moveNode(
  items: OutlineNode[],
  dragId: string,
  targetId: string,
  position: DropPosition,
  now: string,
): OutlineNode[] {
  if (dragId === targetId) return items;
  const drag = getNode(items, dragId);
  const target = getNode(items, targetId);
  if (!drag || !target) return items;
  if (isSelfOrAncestor(items, dragId, targetId)) return items; // can't nest into own subtree

  let parentId: string | null;
  let order: number;
  if (position === 'child') {
    parentId = target.id;
    order = maxOrder(items, target.id) + 1;
  } else {
    parentId = target.parentId;
    order = position === 'before' ? target.order - 0.5 : target.order + 0.5;
  }

  const withExpand =
    position === 'child'
      ? items.map((i) => (i.id === target.id && i.collapsed ? { ...i, collapsed: false } : i))
      : items;
  return reindex(
    withExpand.map((i) => (i.id === dragId ? { ...i, parentId, order, updatedAt: now } : i)),
  );
}

/** Which drop zone a pointer at `offsetY` (from the row top) of a row `height`
 *  tall lands in: top third = before, bottom third = after, middle = child. */
export function dropZone(offsetY: number, height: number): DropPosition {
  if (height <= 0) return 'child';
  const r = offsetY / height;
  if (r < 0.3) return 'before';
  if (r > 0.7) return 'after';
  return 'child';
}

/** Inclusive id range between `anchor` and `target` within the ordered visible
 *  ids (shift-select). Falls back to just `[target]` if either isn't present. */
export function rangeSlice(order: string[], anchor: string, target: string): string[] {
  const ai = order.indexOf(anchor);
  const bi = order.indexOf(target);
  if (ai === -1 || bi === -1) return [target];
  const [lo, hi] = ai <= bi ? [ai, bi] : [bi, ai];
  return order.slice(lo, hi + 1);
}

// --- status / color / checkbox / tags --------------------------------------

export function setStatus(items: OutlineNode[], id: string, status: OutlineStatus, now: string): OutlineNode[] {
  return items.map((i) => (i.id === id ? { ...i, status, updatedAt: now } : i));
}
export function setColorLabel(items: OutlineNode[], id: string, colorLabel: OutlineColor, now: string): OutlineNode[] {
  return items.map((i) => (i.id === id ? { ...i, colorLabel, updatedAt: now } : i));
}

// --- manuscript hard link ---------------------------------------------------

/** Bind (or, with null, unbind) a node to a manuscript block. */
export function setLink(items: OutlineNode[], id: string, link: OutlineLink | null, now: string): OutlineNode[] {
  return items.map((i) => (i.id === id ? { ...i, link, updatedAt: now } : i));
}

/**
 * The node whose linked block is the closest one at-or-before `blockIndex` — i.e.
 * the manuscript section the caret currently sits in ("you are here"). Returns
 * null when the caret is before every linked node (or nothing is linked).
 *
 * If two nodes link the SAME block, the first in `items` order wins. That's a
 * rare, cosmetic-only tie (it only affects which row highlights — never data),
 * so we don't pay to resolve it against visible outline order.
 */
export function activeLinkedNodeId(items: OutlineNode[], blockIndex: number | null): string | null {
  if (blockIndex === null || blockIndex < 0) return null;
  let bestId: string | null = null;
  let bestBlock = -1;
  for (const n of items) {
    const b = n.link?.blockIndex;
    if (typeof b === 'number' && b <= blockIndex && b > bestBlock) {
      bestBlock = b;
      bestId = n.id;
    }
  }
  return bestId;
}

/**
 * Re-locate every link's blockIndex after the manuscript changed: if the block
 * at the stored index no longer matches the stored quote, find the block whose
 * text equals the quote nearest the old index and move the link there. Best-effort
 * and non-destructive — a link whose quote can't be found keeps its old index
 * rather than being dropped. Returns the SAME array when nothing moved (so callers
 * can skip a needless save). A blank quote (empty block) is never re-located.
 *
 * When several blocks share the quote's exact text (e.g. repeated scene slugs),
 * the nearest to the old index wins, ties resolving to the lower index. That can
 * pick a sibling duplicate, but it's cosmetic (the badge/breadcrumb jump one
 * identical-looking block off) and self-corrects the moment the texts diverge.
 */
export function reanchorLinks(items: OutlineNode[], blockTexts: string[], now: string): OutlineNode[] {
  let changed = false;
  const next = items.map((n) => {
    const link = n.link;
    if (!link || !link.quote) return n; // unlinked, or an un-relocatable blank anchor
    if (blockTexts[link.blockIndex] === link.quote) return n; // still correct
    let best = -1;
    let bestDist = Infinity;
    for (let i = 0; i < blockTexts.length; i += 1) {
      if (blockTexts[i] === link.quote) {
        const d = Math.abs(i - link.blockIndex);
        if (d < bestDist) {
          bestDist = d;
          best = i;
        }
      }
    }
    if (best === -1 || best === link.blockIndex) return n; // not found (keep) / unchanged
    changed = true;
    return { ...n, link: { ...link, blockIndex: best }, updatedAt: now };
  });
  return changed ? next : items;
}
export function setCompleted(items: OutlineNode[], id: string, completed: boolean, now: string): OutlineNode[] {
  return items.map((i) => (i.id === id ? { ...i, completed, updatedAt: now } : i));
}
export function toggleCompleted(items: OutlineNode[], id: string, now: string): OutlineNode[] {
  return items.map((i) => (i.id === id ? { ...i, completed: !i.completed, updatedAt: now } : i));
}
export function setTags(items: OutlineNode[], id: string, tags: string[], now: string): OutlineNode[] {
  const clean = normalizeTags(tags);
  return items.map((i) => (i.id === id ? { ...i, tags: clean, updatedAt: now } : i));
}

/** Lowercase, strip a leading '#', drop spaces/empties. */
export function normalizeTag(raw: string): string {
  return raw.replace(/^#+/, '').trim().toLowerCase().replace(/\s+/g, '-');
}
export function normalizeTags(tags: string[]): string[] {
  const out: string[] = [];
  for (const t of tags) {
    const n = normalizeTag(t);
    if (n && !out.includes(n)) out.push(n);
  }
  return out;
}
/** Hashtags typed inline in a title (the "#tag in title" affordance). */
export function extractHashtags(text: string): string[] {
  return normalizeTags((text.match(/#[\p{L}\p{N}_-]+/gu) ?? []).map((m) => m.slice(1)));
}
/** All tags for search/filter: structured tags + any #tags in the title. */
export function nodeTags(node: OutlineNode): string[] {
  return normalizeTags([...(node.tags ?? []), ...extractHashtags(node.title)]);
}

// --- duplicate (subtree, fresh ids) ----------------------------------------

/**
 * Clone the subtree rooted at `id`, using `idMap` (every subtree id → a fresh
 * id). The clone is inserted right after the original (same parent); descendants
 * keep their structure. Pure: the caller supplies the id map.
 */
export function cloneSubtreeWithMap(
  items: OutlineNode[],
  id: string,
  idMap: Map<string, string>,
  now: string,
): OutlineNode[] {
  const root = getNode(items, id);
  if (!root) return items;
  const subtree = [id, ...descendantIds(items, id)];
  const clones = subtree.map((sid) => {
    const n = getNode(items, sid) as OutlineNode;
    const parentId = sid === id ? n.parentId : (idMap.get(n.parentId as string) as string);
    return {
      ...n,
      id: idMap.get(sid) as string,
      parentId,
      order: sid === id ? root.order + 0.5 : n.order,
      createdAt: now,
      updatedAt: now,
    };
  });
  return reindex([...items, ...clones]);
}

// --- search / filter -------------------------------------------------------

export interface OutlineFilter {
  query: string;
  type: OutlineItemType | 'all';
  status: OutlineStatus | 'all';
  color: OutlineColor | 'all';
  tag: string | null;
}

export const EMPTY_FILTER: OutlineFilter = {
  query: '',
  type: 'all',
  status: 'all',
  color: 'all',
  tag: null,
};

export function isFilterActive(f: OutlineFilter): boolean {
  return !!f.query.trim() || f.type !== 'all' || f.status !== 'all' || f.color !== 'all' || !!f.tag;
}

export function matchesFilter(node: OutlineNode, f: OutlineFilter): boolean {
  if (f.type !== 'all' && node.type !== f.type) return false;
  if (f.status !== 'all' && node.status !== f.status) return false;
  if (f.color !== 'all' && node.colorLabel !== f.color) return false;
  const tags = nodeTags(node);
  if (f.tag && !tags.includes(f.tag)) return false;
  const q = f.query.trim().toLowerCase();
  if (q) {
    const hay = `${node.title}\n${tags.map((t) => '#' + t).join(' ')}`.toLowerCase();
    if (!hay.includes(q)) return false;
  }
  return true;
}

// --- zoom + view rows ------------------------------------------------------

/** Root → … → node (used for breadcrumbs). */
export function ancestorChain(items: OutlineNode[], id: string): OutlineNode[] {
  const chain: OutlineNode[] = [];
  let cur = getNode(items, id);
  while (cur) {
    chain.unshift(cur);
    cur = cur.parentId ? getNode(items, cur.parentId) : undefined;
  }
  return chain;
}

/**
 * Visible rows for the panel, honoring a zoom root and an active filter.
 *  - zoom: rows start at the children of `zoomRootId` (the root itself is the
 *    breadcrumb, not a row); `null` = whole outline.
 *  - filter: only matching nodes + their ancestors are shown, and collapse is
 *    ignored so matches are revealed.
 */
export function buildRows(
  items: OutlineNode[],
  zoomRootId: string | null,
  filter: OutlineFilter,
): VisibleRow[] {
  const base = zoomRootId && getNode(items, zoomRootId) ? zoomRootId : null;
  let includeIds: Set<string> | null = null;
  if (isFilterActive(filter)) {
    includeIds = new Set<string>();
    const scope = base ? descendantIds(items, base) : items.map((i) => i.id);
    for (const sid of scope) {
      const n = getNode(items, sid) as OutlineNode;
      if (matchesFilter(n, filter)) {
        includeIds.add(sid);
        let p = n.parentId;
        while (p && p !== base) {
          includeIds.add(p);
          p = getNode(items, p)?.parentId ?? null;
        }
      }
    }
  }
  const out: VisibleRow[] = [];
  const walk = (parentId: string | null, depth: number) => {
    for (const node of childrenOf(items, parentId)) {
      if (includeIds && !includeIds.has(node.id)) continue;
      const kids = hasChildren(items, node.id);
      out.push({ node, depth, hasChildren: kids });
      const expand = includeIds ? true : !node.collapsed;
      if (kids && expand) walk(node.id, depth + 1);
    }
  };
  walk(base, 0);
  return out;
}
