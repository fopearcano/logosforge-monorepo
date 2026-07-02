/**
 * Comment anchoring tests — locate() / reconcileMarks (follow the quoted text
 * across edits, picking the RIGHT occurrence by context) and findOrphanIds (a
 * comment is deleted only when its quote AND context are both gone, not when the
 * quoted text was merely edited). Pure — no React/DOM/backend. Runs headlessly
 * (esbuild + node): `npm run test:comments`. Throws on failure.
 */

import { findOrphanIds, locate, reconcileMarks } from './commentsAnchor';
import type { Comment } from './commentsApi';

let passed = 0;
const failures: string[] = [];
function check(label: string, cond: boolean) {
  if (cond) passed += 1;
  else failures.push(label);
}

const NOW = '2026-01-01T00:00:00.000Z';
interface MkOpts {
  resolved?: boolean;
  prefix?: string;
  suffix?: string;
  end?: number; // end_block_index for a multi-block selection
}
function mk(
  id: string,
  block_index: number,
  from_offset: number,
  to_offset: number,
  quote: string,
  opts: MkOpts = {},
): Comment {
  return {
    id,
    anchor: { block_index, from_offset, to_offset, end_block_index: opts.end, prefix: opts.prefix ?? '', suffix: opts.suffix ?? '' },
    quote,
    body: '',
    resolved: opts.resolved ?? false,
    replies: [],
    created_at: NOW,
    updated_at: NOW,
  };
}

// 1. Stored offset still exactly valid → fast path, stays put.
{
  const texts = ['The rain fell', 'second block'];
  const marks = reconcileMarks([mk('a', 0, 4, 8, 'rain', { prefix: 'The ', suffix: ' fell' })], texts);
  check('stored offset kept', marks.length === 1 && marks[0].blockIndex === 0 && marks[0].from === 4 && marks[0].to === 8);
  check('no orphans when valid', findOrphanIds([mk('a', 0, 4, 8, 'rain')], texts).length === 0);
}

// 2. Text shifted within the stored block → relocate by exact quote.
{
  const texts = ['Oh, the rain fell']; // "rain" now at 8
  const marks = reconcileMarks([mk('a', 0, 4, 8, 'rain', { prefix: 'the ', suffix: ' fell' })], texts);
  check('relocate within block', marks.length === 1 && marks[0].from === 8 && marks[0].to === 12);
}

// 3. A block was deleted before it → the quoted text moved to a lower index.
{
  const texts = ['now first', 'the rain fell'];
  const marks = reconcileMarks([mk('a', 2, 4, 8, 'rain', { prefix: 'the ', suffix: ' fell' })], texts);
  check('relocate across blocks', marks.length === 1 && marks[0].blockIndex === 1 && texts[1].slice(marks[0].from, marks[0].to) === 'rain');
  check('not orphaned when found elsewhere', findOrphanIds([mk('a', 2, 4, 8, 'rain')], texts).length === 0);
}

// 4. The block holding the quote is gone (no context to fall back to) → orphan.
{
  const texts = ['unrelated one', 'unrelated two'];
  const marks = reconcileMarks([mk('a', 0, 4, 8, 'rain')], texts);
  check('orphan paints no mark', marks.length === 0);
  check('orphan flagged for delete', findOrphanIds([mk('a', 0, 4, 8, 'rain')], texts).join(',') === 'a');
}

// 5. Guard: no blocks at all (a load / doc-switch transient) → never orphan.
check('empty doc orphans nothing', findOrphanIds([mk('a', 0, 4, 8, 'rain')], []).length === 0);

// 6. resolved flag passes through reconcile.
{
  const marks = reconcileMarks([mk('a', 0, 4, 8, 'rain', { resolved: true })], ['The rain fell']);
  check('resolved flag preserved', marks.length === 1 && marks[0].resolved === true);
}

// 7. A no-quote comment keeps its stored anchor while its block exists.
{
  const texts = ['some text here'];
  const marks = reconcileMarks([mk('a', 0, 2, 6, '')], texts);
  check('no-quote keeps anchor', marks.length === 1 && marks[0].from === 2 && marks[0].to === 6);
  check('no-quote never orphaned', findOrphanIds([mk('a', 0, 2, 6, '')], texts).length === 0);
}

// 8. Mixed set: a survivor and an orphan, handled independently.
{
  const texts = ['kept the porthole', 'other'];
  const comments = [mk('keep', 0, 9, 17, 'porthole', { prefix: 'kept the ' }), mk('drop', 1, 0, 6, 'gonezo')];
  const marks = reconcileMarks(comments, texts);
  check('mixed: only the survivor paints', marks.length === 1 && marks[0].id === 'keep');
  check('mixed: only the orphan is flagged', findOrphanIds(comments, texts).join(',') === 'drop');
}

// 9. HIGH FIX #2 — a repeated quote re-anchors to the occurrence whose context
//    matches, NOT the first one. Text gained a leading "Oh! " so offsets shifted.
{
  const texts = ['Oh! the cat sat. the cat ran.']; // cats now at 8 and 21
  // Comment was on the SECOND cat: stored offset 17, suffix " ran".
  const c = mk('a', 0, 17, 20, 'cat', { prefix: 'the ', suffix: ' ran' });
  const marks = reconcileMarks([c], texts);
  check('duplicate quote: context picks 2nd occurrence', marks.length === 1 && marks[0].from === 21 && marks[0].to === 24);
}

// 10. Legacy comment (no context) with a repeated quote → proximity to the stored
//     offset still beats blind first-match.
{
  const texts = ['Oh! the cat sat. the cat ran.'];
  const c = mk('a', 0, 17, 20, 'cat'); // no prefix/suffix
  const marks = reconcileMarks([c], texts);
  check('duplicate quote: proximity picks nearer occurrence', marks.length === 1 && marks[0].from === 21);
}

// 11. HIGH FIX #1 — an in-span edit (rain → storm) re-anchors between the intact
//     context landmarks instead of orphaning (and being auto-deleted).
{
  const texts = ['The storm had not stopped'];
  const c = mk('a', 0, 4, 8, 'rain', { prefix: 'The ', suffix: ' had not' });
  const loc = locate(c, texts);
  check('in-span edit re-anchors (not null)', loc !== null && loc.blockIndex === 0 && loc.from === 4 && loc.to === 9);
  check('in-span edit covers the new word', loc !== null && texts[0].slice(loc.from, loc.to) === 'storm');
  check('in-span edit NOT orphaned (no data loss)', findOrphanIds([c], texts).length === 0);
}

// 12. One-sided context: the suffix was edited away too, but a distinctive prefix
//     survives → anchor at the prefix using the original quote length (kept alive).
{
  const texts = ['and the heavy mist drifted'];
  const c = mk('a', 0, 14, 18, 'rain', { prefix: 'and the heavy ', suffix: ' had not' });
  const loc = locate(c, texts);
  check('one-sided strong prefix re-anchors', loc !== null && loc.from === 14);
  check('one-sided NOT orphaned', findOrphanIds([c], texts).length === 0);
}

// 13. The quoted word was deleted outright but context is intact → zero-width
//     anchor between the landmarks; still kept (not orphaned).
{
  const texts = ['The  had not stopped']; // "rain" removed, double space remains
  const c = mk('a', 0, 4, 8, 'rain', { prefix: 'The ', suffix: ' had not' });
  const loc = locate(c, texts);
  check('deleted-quote brackets to empty span', loc !== null && loc.from === 4 && loc.to === 4);
  check('deleted-quote NOT orphaned', findOrphanIds([c], texts).length === 0);
}

// 14. Genuine removal — neither the quote nor the context exists anywhere → orphan.
{
  const texts = ['Totally different.', 'Another paragraph entirely.'];
  const c = mk('a', 0, 4, 8, 'rain', { prefix: 'The ', suffix: ' had not' });
  check('quote+context gone → located null', locate(c, texts) === null);
  check('quote+context gone → orphaned', findOrphanIds([c], texts).join(',') === 'a');
}

// 15. A weak (short) lone landmark must NOT keep a comment alive on unrelated text.
{
  const texts = ['The weather is calm today']; // shares only "The " with the anchor
  const c = mk('a', 0, 4, 8, 'rain', { prefix: 'The ', suffix: ' had not' });
  check('weak lone landmark does not falsely keep', locate(c, texts) === null);
}

// 16. locate() / findOrphanIds consistency — every painted comment has a home,
//     every orphan does not, with no overlap.
{
  const texts = ['The storm had not stopped', 'a wholly unrelated line'];
  const comments = [
    mk('paints', 0, 4, 8, 'rain', { prefix: 'The ', suffix: ' had not' }), // in-span edit → kept
    mk('gone', 1, 0, 4, 'zzzz', { prefix: 'qqqq', suffix: 'wwww' }), // nothing matches → orphan
  ];
  const markIds = reconcileMarks(comments, texts).map((m) => m.id);
  const orphanIds = findOrphanIds(comments, texts);
  check('consistency: painted ids', markIds.join(',') === 'paints');
  check('consistency: orphan ids', orphanIds.join(',') === 'gone');
  check('consistency: no overlap', !markIds.some((id) => orphanIds.includes(id)));
}

// 17. RED-TEAM FIX — a repeated prefix landmark must not strand the comment. The
//     quoted word was edited; the FIRST prefix occurrence pairs with the surviving
//     suffix, so it re-anchors onto the new word (the old lastIndexOf code grabbed
//     the late prefix, lost the suffix, and orphaned → deleted the comment).
{
  // was "the cat ran. the cat sat", comment on "ran"; user changed ran → fled.
  const texts = ['the cat fled. the cat sat'];
  const c = mk('a', 0, 8, 11, 'ran', { prefix: 'the cat ', suffix: '. the cat sat' });
  const loc = locate(c, texts);
  check('dup-landmark in-span edit re-anchors to new word', loc !== null && loc.from === 8 && texts[0].slice(loc.from, loc.to) === 'fled');
  check('dup-landmark in-span edit NOT orphaned', findOrphanIds([c], texts).length === 0);
}

// 18. RED-TEAM FIX — word boundary beats raw substring + proximity: a standalone
//     "art" is chosen over the "art" embedded in "restart", even in a nearer block.
{
  const texts = ['restart now', 'the art here'];
  const c = mk('a', 0, 0, 3, 'art'); // legacy: no context; home moved
  const marks = reconcileMarks([c], texts);
  check('word-boundary beats embedded substring', marks.length === 1 && marks[0].blockIndex === 1 && marks[0].from === 4);
}

// 19. RED-TEAM FIX — context-aware fast path: the stored offset still reads "ok"
//     but its surrounding context is wrong (a ghost); the real home is the 2nd "ok".
{
  const texts = ['ok start, really ok now'];
  const c = mk('a', 0, 0, 2, 'ok', { prefix: 'really ', suffix: ' now' });
  const marks = reconcileMarks([c], texts);
  check('fast-path ghost skipped for true home', marks.length === 1 && marks[0].from === 17);
}

// 20. MULTI-PARAGRAPH selection → one mark per spanned block (start edge, full
//     middle blocks, end edge), each block located by the two edges' context.
{
  const texts = ['Chapter starts here now', 'the middle line', 'and it ends right there'];
  const c = mk('m', 0, 8, 11, 'starts here now\nthe middle line\nand it ends', { prefix: 'Chapter ', suffix: ' right there', end: 2 });
  const marks = reconcileMarks([c], texts);
  check('multi-block paints 3 spans', marks.length === 3);
  check('multi-block start edge', marks[0].blockIndex === 0 && marks[0].from === 8 && marks[0].to === 23);
  check('multi-block middle full', marks[1].blockIndex === 1 && marks[1].from === 0 && marks[1].to === 15);
  check('multi-block end edge', marks[2].blockIndex === 2 && marks[2].from === 0 && marks[2].to === 11);
  check('multi-block not orphaned', findOrphanIds([c], texts).length === 0);
}

// 21. Multi-block follows a block inserted above (both edges shift down by one).
{
  const texts = ['NEW intro paragraph', 'Chapter starts here now', 'the middle line', 'and it ends right there'];
  const c = mk('m', 0, 8, 11, 'starts here now\nthe middle line\nand it ends', { prefix: 'Chapter ', suffix: ' right there', end: 2 });
  const marks = reconcileMarks([c], texts);
  check('multi-block re-anchors after insert', marks.length === 3 && marks[0].blockIndex === 1 && marks[2].blockIndex === 3);
}

// 22. Multi-block orphan: both edges gone → no marks, flagged for delete.
{
  const texts = ['totally different', 'nothing relevant here'];
  const c = mk('m', 0, 8, 11, 'starts here now\nmid\nand it ends', { prefix: 'Chapter ', suffix: ' right there', end: 2 });
  check('multi-block both edges gone → no marks', reconcileMarks([c], texts).length === 0);
  check('multi-block orphaned', findOrphanIds([c], texts).join(',') === 'm');
}

// --- report ---
console.log(`Comment anchor tests: ${passed} passed, ${failures.length} failed`);
for (const f of failures) console.log('  FAIL: ' + f);
if (failures.length) throw new Error(`${failures.length} comment anchor test(s) failed`);
console.log('COMMENTS TESTS: PASS');
