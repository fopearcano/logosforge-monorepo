/**
 * Nerd Mode editor-tools tests. Pure — no editor/DOM. Runs headlessly
 * (esbuild + node): `npm run test:editor-tools`. Throws (non-zero) on failure.
 */

import type { FountainBlock } from '../screenplay/fountainTypes';
import { findFoldableRegions, headingLevel, hiddenBlocks, isFoldHead } from './folding/foldingModel';
import { gutterDigits, lineNumbersForCount } from './lineNumbers/lineNumbers';
import { classifySyntax } from './syntax/syntaxClassifier';

let passed = 0;
const failures: string[] = [];
function check(label: string, cond: boolean) {
  if (cond) passed += 1;
  else failures.push(label);
}
const json = (v: unknown) => JSON.stringify(v);

const line = (text: string): FountainBlock => ({ text, isHeading: false });
const lines = (...t: string[]): FountainBlock[] => t.map(line);
const heading = (text: string, level: number): FountainBlock => ({ text, isHeading: true, level });
const tokens = (blocks: FountainBlock[], mode: string) =>
  classifySyntax(blocks, mode).map((b) => b.token);
const inlineOf = (text: string, mode: string) =>
  classifySyntax([line(text)], mode)[0].inline.map((s) => s.token);

// 1. Line numbers
check('line numbers 1..3', json(lineNumbersForCount(3)) === json([1, 2, 3]));
check('line numbers empty', json(lineNumbersForCount(0)) === json([]));
check('gutter digits 9', gutterDigits(9) === 1);
check('gutter digits 10', gutterDigits(10) === 2);
check('gutter digits 0 -> 1', gutterDigits(0) === 1);

// 2. Heading level
check('headingLevel node', headingLevel(heading('Act', 2)) === 2);
check('headingLevel hash', headingLevel(line('## Foo')) === 2);
check('headingLevel hash1', headingLevel(line('# Foo')) === 1);
check('headingLevel plain', headingLevel(line('plain text')) === 0);

// 3. Foldable regions — headings (novel)
{
  const blocks = [heading('Chapter One', 1), line('a'), line('b'), heading('Chapter Two', 1), line('c')];
  const regions = findFoldableRegions(blocks, 'novel');
  check('novel: two heading regions', regions.length === 2);
  check('novel: first region body', regions[0].head === 0 && regions[0].end === 2);
  check('novel: second region body', regions[1].head === 3 && regions[1].end === 4);
  check('fold head 0 hides 1,2', json([...hiddenBlocks(regions, new Set([0]))]) === json([1, 2]));
  check('no fold hides nothing', hiddenBlocks(regions, new Set()).size === 0);
  check('isFoldHead 0', isFoldHead(regions, 0) && !isFoldHead(regions, 1));
}

// 4. Nested headings — folding the parent hides the child + content
{
  const blocks = [heading('Act', 1), heading('Seq', 2), line('x'), heading('Act 2', 1)];
  const regions = findFoldableRegions(blocks, 'screenplay');
  const top = regions.find((r) => r.head === 0)!;
  const sub = regions.find((r) => r.head === 1)!;
  check('nested: parent ends at 2', top.end === 2);
  check('nested: child ends at 2', sub.end === 2);
  check('nested: fold parent hides child+content', json([...hiddenBlocks(regions, new Set([0]))]) === json([1, 2]));
}

// 5. Screenplay multi-block note + boneyard regions
{
  const note = findFoldableRegions(lines('action', '[[', 'a note', ']]', 'more'), 'screenplay').find(
    (r) => r.kind === 'note',
  );
  check('note region head/end', !!note && note.head === 1 && note.end === 3);
  const bone = findFoldableRegions(lines('/*', 'cut', '*/', 'keep'), 'screenplay').find(
    (r) => r.kind === 'boneyard',
  );
  check('boneyard region head/end', !!bone && bone.head === 0 && bone.end === 2);
  // Novel mode has no note/boneyard folding.
  check('novel: no note folding', !findFoldableRegions(lines('[[', 'x', ']]'), 'novel').some((r) => r.kind === 'note'));
}

// 6. Screenplay syntax categories
{
  const blocks = [
    heading('Act One', 1),
    line('INT. HOUSE - DAY'),
    line('He runs.'),
    line('JOHN'),
    line('Hello.'),
    line('(softly)'),
    line('Bye.'),
    line('CUT TO:'),
    line('= a synopsis'),
    line('[[a note]]'),
  ];
  check(
    'screenplay tokens',
    json(tokens(blocks, 'screenplay')) ===
      json([
        'section',
        'scene_heading',
        'action',
        'character',
        'dialogue',
        'parenthetical',
        'dialogue',
        'transition',
        'synopsis',
        'note',
      ]),
  );
  check('screenplay title field', tokens(lines('Title: My Film', '', 'INT. X'), 'screenplay')[0] === 'title_field');
  check('screenplay boneyard token', tokens(lines('/*', 'cut', '*/'), 'screenplay').every((t) => t === 'boneyard'));
}

// 7. Novel / Notes syntax categories
{
  const blocks = [heading('Chapter', 1), heading('Section', 2), heading('Sub', 3), line('prose'), line('- item'), line('- [ ] todo')];
  check(
    'novel tokens',
    json(tokens(blocks, 'novel')) === json(['chapter', 'heading', 'subheading', 'plain', 'bullet', 'checkbox']),
  );
}

// 8. Inline tokens (shared)
check('inline emphasis', inlineOf('a **b** c', 'screenplay').includes('emphasis'));
check('inline note', inlineOf('see [[this]] ok', 'novel').includes('note'));
check('inline todo', inlineOf('remember TODO later', 'novel').includes('todo'));
check('inline tag (notes)', inlineOf('a #idea and @bob', 'notes').filter((t) => t === 'tag').length === 2);
check('inline link', inlineOf('see [t](http://x.com) here', 'notes').includes('link'));
check('inline checkbox (notes)', inlineOf('- [x] done', 'notes').includes('checkbox'));
check('no tags in screenplay', !inlineOf('a #idea here', 'screenplay').includes('tag'));

// --- report ---
console.log(`Editor tools tests: ${passed} passed, ${failures.length} failed`);
for (const f of failures) console.log('  FAIL: ' + f);
if (failures.length) throw new Error(`${failures.length} editor-tools test(s) failed`);
console.log('EDITOR TOOLS TESTS: PASS');
