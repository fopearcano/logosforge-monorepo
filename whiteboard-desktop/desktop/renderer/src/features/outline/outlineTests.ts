/**
 * Manual story-outliner model tests. Pure — no React/DOM/backend. Runs
 * headlessly (esbuild + node): `npm run test:outline`. Throws on failure.
 */

import {
  ancestorChain,
  buildRows,
  childrenOf,
  childType,
  cloneSubtreeWithMap,
  createNode,
  descendantIds,
  EMPTY_FILTER,
  extractHashtags,
  firstChildId,
  getNode,
  hasChildren,
  indentItem,
  insertChild,
  insertRoot,
  insertSibling,
  matchesFilter,
  moveDown,
  moveUp,
  nextVisibleId,
  nodeTags,
  normalizeTag,
  outdentItem,
  prevVisibleId,
  removeItem,
  rename,
  rootType,
  setAllCollapsed,
  setBranchCollapsed,
  setCollapsed,
  setColorLabel,
  setNodeType,
  setNotes,
  setStatus,
  setTags,
  toggleCompleted,
  toggleCollapsed,
  visibleRows,
  type OutlineItemType,
  type OutlineNode,
} from './outlineModel';
import { storyMapNode } from '../whiteboard/StoryMap';
import type { OutlineItem } from './types';

let passed = 0;
const failures: string[] = [];
function check(label: string, cond: boolean) {
  if (cond) passed += 1;
  else failures.push(label);
}

const NOW = '2026-01-01T00:00:00.000Z';
let idc = 0;
const mk = (type: OutlineItemType): OutlineNode => createNode(`id${++idc}`, type, null, NOW);
const ids = (nodes: OutlineNode[]) => nodes.map((n) => n.id).join(',');

// 1. Mode-aware defaults (Part 8)
check('rootType screenplay', rootType('screenplay') === 'act');
check('rootType novel', rootType('novel') === 'chapter');
// series is no longer a Whiteboard mode → falls back to the default (chapter)
check('rootType series -> default', rootType('series') === 'chapter');
check('rootType scene', rootType('scene') === 'scene');
check('rootType notes', rootType('notes') === 'note');
check('rootType default', rootType('graphic_novel') === 'chapter');
check('childType screenplay act→sequence', childType('screenplay', 'act') === 'sequence');
check('childType screenplay sequence→scene', childType('screenplay', 'sequence') === 'scene');
check('childType screenplay scene→beat', childType('screenplay', 'scene') === 'beat');
check('childType novel part→chapter', childType('novel', 'part') === 'chapter');
check('childType novel chapter→scene', childType('novel', 'chapter') === 'scene');
check('childType scene scene→beat', childType('scene', 'scene') === 'beat');
check('childType notes fallback', childType('notes', 'note') === 'note');

// 2. createNode defaults
{
  const c = createNode('x', 'scene', null, NOW);
  check(
    'createNode defaults',
    c.title === '' &&
      c.notes === '' &&
      c.order === 0 &&
      c.collapsed === false &&
      c.parentId === null &&
      c.linkedLineId === null &&
      c.createdAt === NOW &&
      c.updatedAt === NOW,
  );
}

// 3. insertRoot appends + reindexes
{
  let items: OutlineNode[] = [];
  const r1 = mk('chapter');
  const r2 = mk('chapter');
  items = insertRoot(items, r1);
  items = insertRoot(items, r2);
  const roots = childrenOf(items, null);
  check(
    'insertRoot append + order',
    roots.length === 2 && roots[0].id === r1.id && roots[0].order === 0 && roots[1].order === 1,
  );
}

// 4. insertChild nests + expands a collapsed parent
{
  let items: OutlineNode[] = [];
  const p = mk('act');
  items = insertRoot(items, p);
  items = setCollapsed(items, p.id, true);
  const c = mk('scene');
  items = insertChild(items, p.id, c);
  check('insertChild nests', getNode(items, c.id)?.parentId === p.id);
  check('insertChild expands parent', getNode(items, p.id)?.collapsed === false);
}

// 5. insertSibling places directly after the anchor
{
  let items: OutlineNode[] = [];
  const p = mk('act');
  items = insertRoot(items, p);
  const c1 = mk('scene');
  const c2 = mk('scene');
  items = insertChild(items, p.id, c1);
  items = insertChild(items, p.id, c2);
  const s = mk('scene');
  items = insertSibling(items, c1.id, s);
  check('insertSibling order', ids(childrenOf(items, p.id)) === ids([c1, s, c2]));
}

// 6. rename / setNodeType / setNotes (and updatedAt)
{
  let items = insertRoot([], mk('scene'));
  const id = items[0].id;
  items = rename(items, id, 'Hello', '2026-02-02T00:00:00.000Z');
  check('rename', getNode(items, id)?.title === 'Hello');
  check('rename bumps updatedAt', getNode(items, id)?.updatedAt === '2026-02-02T00:00:00.000Z');
  items = setNodeType(items, id, 'beat', NOW);
  check('setNodeType', getNode(items, id)?.type === 'beat');
  items = setNotes(items, id, 'note text', NOW);
  check('setNotes', getNode(items, id)?.notes === 'note text');
}

// 7. collapse toggles + collapse/expand all (parents only)
{
  let items: OutlineNode[] = [];
  const p = mk('act');
  const c = mk('scene');
  items = insertRoot(items, p);
  items = insertChild(items, p.id, c);
  items = toggleCollapsed(items, p.id);
  check('toggleCollapsed on', getNode(items, p.id)?.collapsed === true);
  items = toggleCollapsed(items, p.id);
  check('toggleCollapsed off', getNode(items, p.id)?.collapsed === false);
  items = setAllCollapsed(items, true);
  check(
    'collapse all sets parents only',
    getNode(items, p.id)?.collapsed === true && getNode(items, c.id)?.collapsed === false,
  );
  items = setAllCollapsed(items, false);
  check('expand all', getNode(items, p.id)?.collapsed === false);
}

// 8. queries: descendantIds / hasChildren
{
  let items: OutlineNode[] = [];
  const p = mk('act');
  const c1 = mk('sequence');
  const g = mk('scene');
  items = insertRoot(items, p);
  items = insertChild(items, p.id, c1);
  items = insertChild(items, c1.id, g);
  check('descendantIds', descendantIds(items, p.id).sort().join(',') === [c1.id, g.id].sort().join(','));
  check('hasChildren true', hasChildren(items, p.id) === true);
  check('hasChildren false', hasChildren(items, g.id) === false);
}

// 9. removeItem deletes the whole subtree + reindexes siblings
{
  let items: OutlineNode[] = [];
  const p = mk('act');
  const c1 = mk('sequence');
  const c2 = mk('sequence');
  const g = mk('scene');
  items = insertRoot(items, p);
  items = insertChild(items, p.id, c1);
  items = insertChild(items, p.id, c2);
  items = insertChild(items, c1.id, g);
  items = removeItem(items, c1.id);
  check('remove subtree', getNode(items, c1.id) === undefined && getNode(items, g.id) === undefined);
  const kids = childrenOf(items, p.id);
  check('remove reindexes', kids.length === 1 && kids[0].id === c2.id && kids[0].order === 0);
}

// 10. indent nests under the previous sibling; no-op for a first child
{
  let items: OutlineNode[] = [];
  const p = mk('act');
  const c1 = mk('sequence');
  const c2 = mk('sequence');
  items = insertRoot(items, p);
  items = insertChild(items, p.id, c1);
  items = insertChild(items, p.id, c2);
  items = indentItem(items, c2.id);
  check('indent nests under prev sibling', getNode(items, c2.id)?.parentId === c1.id);
  check('indent removes from old parent', childrenOf(items, p.id).length === 1);

  let solo: OutlineNode[] = [];
  const sp = mk('act');
  const sc = mk('scene');
  solo = insertRoot(solo, sp);
  solo = insertChild(solo, sp.id, sc);
  const before = JSON.stringify(solo);
  solo = indentItem(solo, sc.id);
  check('indent no-op for first child', JSON.stringify(solo) === before);
}

// 11. outdent reparents to the grandparent, ordered just after the old parent
{
  let items: OutlineNode[] = [];
  const p = mk('act');
  const c1 = mk('sequence');
  const g = mk('scene');
  items = insertRoot(items, p);
  items = insertChild(items, p.id, c1);
  items = insertChild(items, c1.id, g);
  items = outdentItem(items, g.id);
  check('outdent reparents to grandparent', getNode(items, g.id)?.parentId === p.id);
  check('outdent order after old parent', ids(childrenOf(items, p.id)) === ids([c1, g]));

  let root = insertRoot([], mk('act'));
  const before = JSON.stringify(root);
  root = outdentItem(root, root[0].id);
  check('outdent no-op at root', JSON.stringify(root) === before);
}

// 12. moveUp / moveDown + bounds
{
  let items: OutlineNode[] = [];
  const p = mk('act');
  const c1 = mk('scene');
  const c2 = mk('scene');
  const c3 = mk('scene');
  items = insertRoot(items, p);
  items = insertChild(items, p.id, c1);
  items = insertChild(items, p.id, c2);
  items = insertChild(items, p.id, c3);
  items = moveDown(items, c1.id);
  check('moveDown swaps', ids(childrenOf(items, p.id)) === ids([c2, c1, c3]));
  items = moveUp(items, c1.id);
  check('moveUp swaps back', ids(childrenOf(items, p.id)) === ids([c1, c2, c3]));
  const beforeTop = JSON.stringify(items);
  items = moveUp(items, c1.id);
  check('moveUp bound at top', JSON.stringify(items) === beforeTop);
  const beforeBot = JSON.stringify(items);
  items = moveDown(items, c3.id);
  check('moveDown bound at bottom', JSON.stringify(items) === beforeBot);
}

// 13. visibleRows (depth + hasChildren + collapse skipping) and navigation
{
  let items: OutlineNode[] = [];
  const p = mk('act');
  const c1 = mk('sequence');
  const g = mk('scene');
  const c2 = mk('sequence');
  items = insertRoot(items, p);
  items = insertChild(items, p.id, c1);
  items = insertChild(items, c1.id, g);
  items = insertChild(items, p.id, c2);
  let rows = visibleRows(items);
  check('visibleRows count', rows.length === 4);
  check('visibleRows depth', rows[0].depth === 0 && rows[1].depth === 1 && rows[2].depth === 2);
  check('visibleRows hasChildren', rows[0].hasChildren === true && rows[2].hasChildren === false);
  check('firstChildId', firstChildId(items, p.id) === c1.id);
  check('firstChildId none', firstChildId(items, g.id) === null);
  check('nextVisibleId', nextVisibleId(items, p.id) === c1.id);
  check('prevVisibleId', prevVisibleId(items, g.id) === c1.id);
  check('prevVisibleId none at top', prevVisibleId(items, p.id) === null);

  items = setCollapsed(items, c1.id, true);
  rows = visibleRows(items);
  check('collapsed hides descendants', ids(rows.map((r) => r.node)) === ids([p, c1, c2]));
  check('nextVisibleId skips collapsed subtree', nextVisibleId(items, c1.id) === c2.id);
}

// 14. New fields default + setters (status / color / completed / tags)
{
  const c = createNode('x', 'note', null, NOW);
  check('createNode new defaults', c.completed === false && c.status === 'none' && c.colorLabel === 'none' && c.tags.length === 0);
  let items = insertRoot([], mk('scene'));
  const id = items[0].id;
  items = setStatus(items, id, 'drafting', NOW);
  check('setStatus', getNode(items, id)?.status === 'drafting');
  items = setColorLabel(items, id, 'purple', NOW);
  check('setColorLabel', getNode(items, id)?.colorLabel === 'purple');
  items = toggleCompleted(items, id, NOW);
  check('toggleCompleted on', getNode(items, id)?.completed === true);
  items = toggleCompleted(items, id, NOW);
  check('toggleCompleted off', getNode(items, id)?.completed === false);
  items = setTags(items, id, ['#Revision', 'revision', ' Theme '], NOW);
  check('setTags normalizes + dedupes', JSON.stringify(getNode(items, id)?.tags) === JSON.stringify(['revision', 'theme']));
}

// 15. Tag helpers
check('normalizeTag strips # + lowercases', normalizeTag('#Revision') === 'revision');
check('normalizeTag spaces → dash', normalizeTag('To Do') === 'to-do');
check('extractHashtags from title', JSON.stringify(extractHashtags('fix #motivation and #Arc')) === JSON.stringify(['motivation', 'arc']));
{
  const n = { ...createNode('x', 'note', null, NOW), title: 'beat #climax', tags: ['theme'] };
  check('nodeTags merges title + structured', JSON.stringify(nodeTags(n).sort()) === JSON.stringify(['climax', 'theme']));
}

// 16. matchesFilter (query / type / status / color / tag)
{
  const n: OutlineNode = {
    ...createNode('x', 'scene', null, NOW),
    title: 'Opening on the beach',
    notes: 'protagonist refuses the call',
    status: 'todo',
    colorLabel: 'blue',
    tags: ['revision'],
  };
  check('match query title', matchesFilter(n, { ...EMPTY_FILTER, query: 'beach' }));
  check('match query notes', matchesFilter(n, { ...EMPTY_FILTER, query: 'protagonist' }));
  check('match query tag', matchesFilter(n, { ...EMPTY_FILTER, query: 'revision' }));
  check('no match query', !matchesFilter(n, { ...EMPTY_FILTER, query: 'spaceship' }));
  check('match type', matchesFilter(n, { ...EMPTY_FILTER, type: 'scene' }));
  check('no match type', !matchesFilter(n, { ...EMPTY_FILTER, type: 'beat' }));
  check('match status', matchesFilter(n, { ...EMPTY_FILTER, status: 'todo' }));
  check('match color', matchesFilter(n, { ...EMPTY_FILTER, color: 'blue' }));
  check('match tag', matchesFilter(n, { ...EMPTY_FILTER, tag: 'revision' }));
  check('no match tag', !matchesFilter(n, { ...EMPTY_FILTER, tag: 'theme' }));
}

// 17. ancestorChain + buildRows (zoom)
{
  let items: OutlineNode[] = [];
  const act = mk('act');
  const seq = mk('sequence');
  const sc = mk('scene');
  const beat = mk('beat');
  items = insertRoot(items, act);
  items = insertChild(items, act.id, seq);
  items = insertChild(items, seq.id, sc);
  items = insertChild(items, sc.id, beat);
  check('ancestorChain', ids(ancestorChain(items, sc.id)) === ids([act, seq, sc]));

  // Zoom into seq → rows start at its children (scene, beat) with depth 0 at scene.
  const zoomed = buildRows(items, seq.id, EMPTY_FILTER);
  check('zoom rows start below zoom root', ids(zoomed.map((r) => r.node)) === ids([sc, beat]));
  check('zoom depth resets', zoomed[0].depth === 0 && zoomed[1].depth === 1);
  // No zoom → full tree.
  check('no-zoom rows', buildRows(items, null, EMPTY_FILTER).length === 4);
}

// 18. buildRows (filter shows matches + ancestors, ignoring collapse)
{
  let items: OutlineNode[] = [];
  const act = mk('act');
  const seq = mk('sequence');
  const sc = mk('scene');
  items = insertRoot(items, act);
  items = insertChild(items, act.id, seq);
  items = insertChild(items, seq.id, sc);
  items = setNotes(items, sc.id, 'the protagonist arrives', NOW);
  items = setAllCollapsed(items, true); // everything collapsed
  const rows = buildRows(items, null, { ...EMPTY_FILTER, query: 'protagonist' });
  // The matching scene + its ancestors are revealed despite being collapsed.
  check('filter reveals match + ancestors', ids(rows.map((r) => r.node)) === ids([act, seq, sc]));
  check('filter excludes non-matches', buildRows(items, null, { ...EMPTY_FILTER, query: 'zzz' }).length === 0);
}

// 19. duplicate (cloneSubtreeWithMap) — fresh ids, includes children, after original
{
  let items: OutlineNode[] = [];
  const act = mk('act');
  const seq = mk('sequence');
  items = insertRoot(items, act);
  items = insertChild(items, act.id, seq);
  const map = new Map([[act.id, 'dup-act'], [seq.id, 'dup-seq']]);
  items = cloneSubtreeWithMap(items, act.id, map, NOW);
  const roots = childrenOf(items, null);
  check('duplicate adds a sibling after original', ids(roots) === ids([act, { id: 'dup-act' } as OutlineNode]));
  check('duplicate clones children with new ids', getNode(items, 'dup-seq')?.parentId === 'dup-act');
  check('duplicate keeps original intact', getNode(items, seq.id)?.parentId === act.id);
}

// 20. setBranchCollapsed (Alt+click recursive)
{
  let items: OutlineNode[] = [];
  const act = mk('act');
  const seq = mk('sequence');
  const sc = mk('scene');
  items = insertRoot(items, act);
  items = insertChild(items, act.id, seq);
  items = insertChild(items, seq.id, sc); // act>seq>sc (act + seq are parents)
  items = setBranchCollapsed(items, act.id, true);
  check('branch collapse sets parents', getNode(items, act.id)?.collapsed === true && getNode(items, seq.id)?.collapsed === true);
  check('branch collapse skips leaves', getNode(items, sc.id)?.collapsed === false);
}

// --- Story Map node mapping (derived-outline → shape) ---
{
  const node = (kind: OutlineItem['kind'], level = 0) =>
    storyMapNode({ id: 'x', label: 'x', kind, level, blockIndex: 0 });
  check('storymap section L1 -> actlg anchor', node('section', 1).shape === 'wb-sm-actlg' && node('section', 1).anchor === true);
  check('storymap section L2 -> act', node('section', 2).shape === 'wb-sm-act' && node('section', 2).anchor === false);
  check('storymap scene -> scene', node('scene').shape === 'wb-sm-scene');
  check('storymap synopsis -> beat', node('synopsis').shape === 'wb-sm-beat');
  check('storymap note -> beat', node('note').shape === 'wb-sm-beat');
}

// --- report ---
console.log(`Outline model tests: ${passed} passed, ${failures.length} failed`);
for (const f of failures) console.log('  FAIL: ' + f);
if (failures.length) throw new Error(`${failures.length} outline test(s) failed`);
console.log('OUTLINE TESTS: PASS');
