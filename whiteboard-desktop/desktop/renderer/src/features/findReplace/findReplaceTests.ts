/** Focused headless tests for the Find & Replace model and highlight state. */

import { Schema } from '@tiptap/pm/model';
import { EditorState } from '@tiptap/pm/state';

import {
  applyFindReplaceDecorationState,
  buildFindReplaceDecorations,
  emptyFindReplaceDecorationState,
  FIND_REPLACE_DECORATION_LIMIT,
  findReplaceKey,
  findReplaceMeta,
} from './findReplaceExtension';
import {
  descendingReplacementPlan,
  documentSearchBlocks,
  findMatchesInBlocks,
  findTextMatches,
  matchIndexForRange,
  matchIndexFromPosition,
  stepMatchIndex,
  type FindMatch,
} from './findReplaceModel';

let passed = 0;
const failures: string[] = [];
function check(label: string, condition: boolean): void {
  if (condition) passed += 1;
  else failures.push(label);
}
const json = (value: unknown): string => JSON.stringify(value);

const schema = new Schema({
  nodes: {
    doc: { content: 'block+' },
    paragraph: { content: 'inline*', group: 'block' },
    heading: { attrs: { level: { default: 1 } }, content: 'inline*', group: 'block' },
    text: { group: 'inline' },
  },
  marks: {
    strong: {},
    em: {},
  },
});

const strong = schema.marks.strong.create();
const markedDoc = schema.node('doc', null, [
  schema.node('paragraph', null, [schema.text('Ra', [strong]), schema.text('in RAIN')]),
  schema.node('heading', { level: 1 }, schema.text('After rain')),
]);

// Top-level extraction and searches can cross inline mark boundaries, but never
// cross a structural paragraph/heading boundary.
{
  const blocks = documentSearchBlocks(markedDoc);
  check('extracts top-level text blocks', blocks.length === 2 && blocks[0].text === 'Rain RAIN');
  check('first PM text starts at 1', blocks[0].contentStart === 1);
  check('second PM position follows first nodeSize', blocks[1].contentStart === 12);

  const insensitive = findTextMatches(markedDoc, 'rain');
  check('case-insensitive search finds all inline-mark variants', insensitive.length === 3);
  check('match crossing an inline mark boundary has a stable PM range', insensitive[0].from === 1 && insensitive[0].to === 5);
  check('second match retains its PM range', insensitive[1].from === 6 && insensitive[1].to === 10);
  check('case-sensitive search filters variants', findTextMatches(markedDoc, 'Rain', { matchCase: true, wholeWord: false }).length === 1);
  check('query cannot cross blocks', findTextMatches(markedDoc, 'RAINAfter').length === 0);
  check('newline query is rejected', findTextMatches(markedDoc, 'Rain\nAfter').length === 0);
}

// Literal metacharacters and Unicode-aware whole-word boundaries.
{
  const blocks = [{
    blockIndex: 0,
    contentStart: 1,
    text: 'a+b A+B; élan élanes _élan βeta-βeta; [note] [note]x; 😀orbit😀',
  }];
  check('regex metacharacters stay literal', findMatchesInBlocks(blocks, 'a+b').length === 2);
  check(
    'match-case applies to literal metacharacters',
    findMatchesInBlocks(blocks, 'a+b', { matchCase: true, wholeWord: false }).length === 1,
  );
  check(
    'Unicode whole-word excludes letter and connector continuations',
    findMatchesInBlocks(blocks, 'élan', { matchCase: false, wholeWord: true }).length === 1,
  );
  check(
    'Unicode whole-word recognizes Greek boundaries around punctuation',
    findMatchesInBlocks(blocks, 'βeta', { matchCase: false, wholeWord: true }).length === 2,
  );
  check(
    'whole literal boundaries also protect punctuation-edged queries',
    findMatchesInBlocks(blocks, '[note]', { matchCase: false, wholeWord: true }).length === 1,
  );
  check(
    'astral punctuation preserves adjacent Unicode boundaries',
    findMatchesInBlocks(blocks, 'orbit', { matchCase: false, wholeWord: true }).length === 1,
  );
  check('empty query has no matches', findMatchesInBlocks(blocks, '').length === 0);
}

const navigationMatches: FindMatch[] = [
  { blockIndex: 0, fromOffset: 0, toOffset: 2, from: 1, to: 3, text: 'aa' },
  { blockIndex: 0, fromOffset: 4, toOffset: 6, from: 5, to: 7, text: 'aa' },
  { blockIndex: 1, fromOffset: 0, toOffset: 2, from: 10, to: 12, text: 'aa' },
];

// Navigation always wraps and exposes that fact to the live-status UI.
check('step from no active result chooses first', json(stepMatchIndex(3, null, 1)) === json({ index: 0, wrapped: false }));
check('next wraps at end', json(stepMatchIndex(3, 2, 1)) === json({ index: 0, wrapped: true }));
check('previous wraps at start', json(stepMatchIndex(3, 0, -1)) === json({ index: 2, wrapped: true }));
check('empty navigation remains empty', stepMatchIndex(0, 0, 1).index === null);
check('forward position chooses match at caret', matchIndexFromPosition(navigationMatches, 5, 1).index === 1);
check('forward position wraps after last', matchIndexFromPosition(navigationMatches, 99, 1).wrapped);
check('backward position chooses result ending at caret', matchIndexFromPosition(navigationMatches, 7, -1).index === 1);
check('backward position wraps before first', matchIndexFromPosition(navigationMatches, 0, -1).wrapped);
check('exact selection resolves active index', matchIndexForRange(navigationMatches, 5, 7) === 1);
check('non-match selection has no active index', matchIndexForRange(navigationMatches, 5, 6) === null);
check(
  'replacement plan is descending without mutating input',
  json(descendingReplacementPlan(navigationMatches).map((match) => match.from)) === json([10, 5, 1])
    && navigationMatches[0].from === 1,
);

// Large result sets keep their complete model/count outside the decoration
// plugin, while the rendered window stays bounded and always includes current.
{
  const manyMatches: FindMatch[] = Array.from({ length: 20_000 }, (_, index) => ({
    blockIndex: index,
    fromOffset: 0,
    toOffset: 1,
    from: index * 3 + 1,
    to: index * 3 + 2,
    text: 'a',
  }));
  const activeIndex = 15_000;
  const meta = findReplaceMeta(manyMatches, activeIndex);
  check('large decoration payload is bounded', meta.matches.length === FIND_REPLACE_DECORATION_LIMIT);
  check(
    'bounded payload retains the global current match',
    meta.matchIndexOffset + (meta.activeIndex ?? -1) === activeIndex
      && meta.matches[meta.activeIndex ?? -1] === manyMatches[activeIndex],
  );
  check('large decoration window exposes its global offset', meta.matchIndexOffset > 0);
}

// Decoration metadata paints all/current matches, rejects structural ranges,
// and maps safely until the controller recomputes after a document transaction.
{
  const matches = findTextMatches(markedDoc, 'rain');
  const decorations = buildFindReplaceDecorations(markedDoc, findReplaceMeta(matches, 1)).find();
  check('decorates every valid result', decorations.length === 3);
  check('marks exactly one result current', decorations.filter((item) => item.spec.findMatchCurrent).length === 1);
  check('current decoration carries active result index', decorations.find((item) => item.spec.findMatchCurrent)?.spec.findMatchIndex === 1);

  const crossBlock: FindMatch = {
    blockIndex: 0,
    fromOffset: 0,
    toOffset: 20,
    from: 1,
    to: markedDoc.content.size,
    text: 'invalid',
  };
  check(
    'structurally invalid decoration is ignored',
    buildFindReplaceDecorations(markedDoc, findReplaceMeta([crossBlock], 0)).find().length === 0,
  );

  const editorState = EditorState.create({ doc: markedDoc });
  let decorationState = emptyFindReplaceDecorationState();
  const publish = editorState.tr.setMeta(findReplaceKey, findReplaceMeta(matches, 0));
  decorationState = applyFindReplaceDecorationState(publish, decorationState);
  const insertBefore = editorState.tr.insertText('X', 1);
  decorationState = applyFindReplaceDecorationState(insertBefore, decorationState);
  const mapped = decorationState.decorations.find();
  check('decorations map through interim document edits', mapped[0].from === 2 && mapped[0].to === 6);
}

console.log(`Find & Replace tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} Find & Replace test(s) failed`);
console.log('FIND & REPLACE TESTS: PASS');
