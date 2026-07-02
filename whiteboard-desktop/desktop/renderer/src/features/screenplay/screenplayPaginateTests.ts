/**
 * Screenplay paginator tests. Pure — runs headlessly (esbuild + node):
 * `npm run test:paginate`. Throws on failure.
 */

import type { FountainBlock } from './fountainTypes';
import { LINES_PER_PAGE, paginateScreenplay, wrapText } from './screenplayPaginate';

let passed = 0;
const failures: string[] = [];
function check(label: string, cond: boolean) {
  if (cond) passed += 1;
  else failures.push(label);
}

const b = (text: string): FountainBlock => ({ text, isHeading: false });

// 1. wrapText
check('wrap by words', JSON.stringify(wrapText('hello world foo', 9)) === JSON.stringify(['hello', 'world foo']));
check('wrap fits on one line', JSON.stringify(wrapText('a b c', 10)) === JSON.stringify(['a b c']));
check('wrap hard-breaks a long word', wrapText('abcdefghij', 4).join('|') === 'abcd|efgh|ij');
check('wrap empty -> single empty line', JSON.stringify(wrapText('   ', 10)) === JSON.stringify(['']));

// 2. Element columns (industry positions from the text-area left edge)
{
  const pages = paginateScreenplay([
    b('INT. SONAR SHACK - NIGHT'),
    b('She enters quietly, soaked.'),
    b('MARA'),
    b('(whispering)'),
    b('There it is again.'),
    b('SMASH CUT TO:'),
  ]);
  check('short scene fits one page', pages.length === 1);
  const lines = pages[0].lines.filter(Boolean) as { text: string; col: number; align?: string }[];
  const find = (re: RegExp) => lines.find((l) => re.test(l.text));
  check('scene heading at col 0 + uppercased', find(/^INT\. SONAR SHACK/)?.col === 0);
  check('action at col 0', find(/^She enters/)?.col === 0);
  check('character cue at col 22', find(/^MARA$/)?.col === 22);
  check('parenthetical at col 16', find(/^\(whispering\)/)?.col === 16);
  check('dialogue at col 10', find(/^There it is/)?.col === 10);
  check('transition right-aligned', find(/SMASH CUT TO:/)?.align === 'right');
}

// 3. Page-break MORE / CONT'D on long dialogue
{
  const longLine = Array.from({ length: 320 }, (_, i) => `word${i % 7}`).join(' ');
  const pages = paginateScreenplay([b('MARA'), b(longLine)]);
  check('long dialogue spans multiple pages', pages.length >= 2);
  check('a page ends with (MORE)', pages[0].lines.some((l) => l && l.text === '(MORE)'));
  check("next page repeats the cue as (CONT'D)", pages[1].lines.some((l) => l && /^MARA \(CONT'D\)$/.test(l.text)));
  check('every page within the line budget', pages.every((p) => p.lines.length <= LINES_PER_PAGE));
  check('page numbers increment from 1', pages[0].number === 1 && pages[1].number === 2);
}

// 4. A scene heading is not orphaned at the very foot of a page
{
  const blocks: FountainBlock[] = [];
  for (let i = 0; i < 52; i += 1) blocks.push(b(`Action line number ${i}.`));
  blocks.push(b('INT. NEW ROOM - DAY'));
  blocks.push(b('Someone waits.'));
  const pages = paginateScreenplay(blocks);
  const lastSceneOnP1 = pages[0].lines.some((l) => l && /INT\. NEW ROOM/.test(l.text));
  check('scene heading pushed off a full first page', !lastSceneOnP1 || pages.length === 1);
}

// --- report ---
console.log(`Screenplay paginator tests: ${passed} passed, ${failures.length} failed`);
for (const f of failures) console.log('  FAIL: ' + f);
if (failures.length) throw new Error(`${failures.length} paginator test(s) failed`);
console.log('PAGINATE TESTS: PASS');
