/**
 * Comment anchoring tests — locate() / reconcileMarks (follow the quoted text
 * across edits, picking the RIGHT occurrence by context) and findOrphanIds (a
 * comment is deleted only when its quote AND context are both gone, not when the
 * quoted text was merely edited). Pure — no React/DOM/backend. Runs headlessly
 * (esbuild + node): `npm run test:comments`. Throws on failure.
 */

import { findOrphanIds, locate, reconcileMarks } from './commentsAnchor';
import type { Comment } from './commentsApi';
import {
  acknowledgeCommentPatch,
  acknowledgeOptimisticCommentReplies,
  applyRetainedCommentIntent,
  configureRetainedCommentIntentWriter,
  discardRetainedCommentIntent,
  flushRetainedCommentIntent,
  hasRetainedCommentIntent,
  pendingCommentPatch,
  retainCommentPatch,
  retainOptimisticCommentReplies,
} from './commentMutationIntent';
import type { CapturedDocumentIdentity } from '../../state/currentDocument';
import {
  flushPendingDocSaves,
  runSerializedPendingDocWrite,
  setCurrentDocumentIdentity,
} from '../../state/currentDocument';

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
  blockId?: string;
  endBlockId?: string;
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
    anchor: {
      block_index,
      block_id: opts.blockId,
      from_offset,
      to_offset,
      end_block_index: opts.end,
      end_block_id: opts.endBlockId,
      prefix: opts.prefix ?? '',
      suffix: opts.suffix ?? '',
    },
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

// 23. Stable block id beats duplicate quote/context after a block insertion.
{
  const texts = ['The rain fell', 'inserted', 'The rain fell'];
  const ids = ['duplicate', 'new', 'comment-home'];
  const c = mk('stable', 0, 4, 8, 'rain', {
    prefix: 'The ',
    suffix: ' fell',
    blockId: 'comment-home',
  });
  const loc = locate(c, texts, ids);
  check('stable comment id chooses the intended duplicate block', loc?.blockIndex === 2);
}

// 24. Empty/no-quote anchors follow their stable block instead of a stale index.
{
  const texts = ['new', 'target'];
  const ids = ['new-id', 'target-id'];
  const c = mk('empty', 0, 0, 0, '', { blockId: 'target-id' });
  const loc = locate(c, texts, ids);
  check('stable no-quote comment follows its block', loc?.blockIndex === 1);
}

// 25. RETAINED INTENT — if an earlier disjoint field write fails, the next
//     serialized edit carries both values. Acknowledging that retry clears only
//     the exact values it persisted.
{
  const identity: CapturedDocumentIdentity = { documentId: '42', incarnation: 'inc-a' };
  retainCommentPatch(identity, 'intent-fields', { resolved: true });
  const failedFirst = pendingCommentPatch(identity, 'intent-fields');
  retainCommentPatch(identity, 'intent-fields', { body: 'new body' });
  // No acknowledgement models the first transport failure.
  const retry = pendingCommentPatch(identity, 'intent-fields');
  check(
    'failed resolve intent is merged into later body edit',
    failedFirst.resolved === true && retry.resolved === true && retry.body === 'new body',
  );
  acknowledgeCommentPatch(identity, 'intent-fields', retry);
  check(
    'successful merged retry acknowledges both field intents',
    !hasRetainedCommentIntent(identity, 'intent-fields'),
  );
}

// 26. A response may acknowledge an older value while the writer changes the
//     same field in flight. The newer value must remain retained and overlaid.
{
  const identity: CapturedDocumentIdentity = { documentId: '42', incarnation: 'inc-b' };
  retainCommentPatch(identity, 'intent-newer', { body: 'first' });
  const sent = pendingCommentPatch(identity, 'intent-newer');
  retainCommentPatch(identity, 'intent-newer', { body: 'second' });
  acknowledgeCommentPatch(identity, 'intent-newer', sent);
  const server = { ...mk('intent-newer', 0, 0, 4, 'rain'), body: 'first' };
  check(
    'acknowledging an older body preserves the newer overlay',
    pendingCommentPatch(identity, 'intent-newer').body === 'second'
      && applyRetainedCommentIntent(identity, server).body === 'second',
  );
  discardRetainedCommentIntent(identity, 'intent-newer');
}

// 27. A failed optimistic reply followed by a successful scalar edit must not be
//     erased when the edit endpoint returns its full (reply-free) Comment.
{
  const identity: CapturedDocumentIdentity = { documentId: '42', incarnation: 'inc-c' };
  const optimistic = {
    id: 'tmp-reply',
    body: 'Please keep this reply',
    author: 'you',
    created_at: NOW,
  };
  retainOptimisticCommentReplies(identity, 'intent-reply', [optimistic]);
  retainCommentPatch(identity, 'intent-reply', { resolved: true });
  const sent = pendingCommentPatch(identity, 'intent-reply');
  acknowledgeCommentPatch(identity, 'intent-reply', sent);
  const server = { ...mk('intent-reply', 0, 0, 4, 'rain'), resolved: true, replies: [] };
  const overlaid = applyRetainedCommentIntent(identity, server);
  check(
    'failed reply survives a later full-object edit response',
    overlaid.resolved === true
      && overlaid.replies.length === 1
      && overlaid.replies[0].id === optimistic.id
      && hasRetainedCommentIntent(identity, 'intent-reply'),
  );
  acknowledgeOptimisticCommentReplies(identity, 'intent-reply', [optimistic.id]);
  check(
    'server acknowledgement clears the optimistic reply overlay',
    !hasRetainedCommentIntent(identity, 'intent-reply'),
  );
}

// 28. Retained intent is scoped to the durable incarnation, not merely a SQLite
//     numeric id that can be reused after deletion.
{
  const oldIdentity: CapturedDocumentIdentity = { documentId: '42', incarnation: 'old' };
  const newIdentity: CapturedDocumentIdentity = { documentId: '42', incarnation: 'new' };
  retainCommentPatch(oldIdentity, 'same-comment-id', { body: 'old incarnation edit' });
  const current = { ...mk('same-comment-id', 0, 0, 4, 'rain'), body: 'new document body' };
  check(
    'same numeric id in a new incarnation receives no stale intent',
    applyRetainedCommentIntent(newIdentity, current).body === 'new document body',
  );
  discardRetainedCommentIntent(oldIdentity, 'same-comment-id');
}

// 29. Full async regression: the first disjoint PUT fails after the second user
//     action is queued. FIFO continues, and the second transport receives both
//     retained fields rather than silently losing the first action.
{
  const identity: CapturedDocumentIdentity = { documentId: 'intent-doc-a', incarnation: 'inc' };
  const commentId = 'async-fields';
  let releaseFirst!: () => void;
  let markFirstStarted!: () => void;
  const firstGate = new Promise<void>((resolve) => { releaseFirst = resolve; });
  const firstStarted = new Promise<void>((resolve) => { markFirstStarted = resolve; });
  retainCommentPatch(identity, commentId, { resolved: true });
  const first = runSerializedPendingDocWrite(`comment:${commentId}`, async () => {
    const sent = pendingCommentPatch(identity, commentId);
    markFirstStarted();
    await firstGate;
    check('async first mutation sent only its then-current field', sent.resolved === true && sent.body === undefined);
    throw new Error('first write failed');
  }, identity.documentId);
  await firstStarted;
  retainCommentPatch(identity, commentId, { body: 'second action' });
  let retry: ReturnType<typeof pendingCommentPatch> = {};
  const second = runSerializedPendingDocWrite(`comment:${commentId}`, async () => {
    retry = pendingCommentPatch(identity, commentId);
    acknowledgeCommentPatch(identity, commentId, retry);
  }, identity.documentId);
  releaseFirst();
  await first.catch(() => {});
  await second;
  check(
    'first-fails second-succeeds transport carries disjoint retained intent',
    retry.resolved === true && retry.body === 'second action'
      && !hasRetainedCommentIntent(identity, commentId),
  );
}

// 30. Full async reply+edit regression: a failed reply remains visible after the
//     following scalar PUT succeeds and returns a full reply-free Comment.
{
  const identity: CapturedDocumentIdentity = { documentId: 'intent-doc-b', incarnation: 'inc' };
  const commentId = 'async-reply';
  const optimistic = {
    id: 'tmp-async-reply',
    body: 'Retain me',
    author: 'you',
    created_at: NOW,
  };
  let releaseReply!: () => void;
  let markReplyStarted!: () => void;
  const replyGate = new Promise<void>((resolve) => { releaseReply = resolve; });
  const replyStarted = new Promise<void>((resolve) => { markReplyStarted = resolve; });
  retainOptimisticCommentReplies(identity, commentId, [optimistic]);
  const reply = runSerializedPendingDocWrite(`comment:${commentId}`, async () => {
    markReplyStarted();
    await replyGate;
    throw new Error('reply failed');
  }, identity.documentId);
  await replyStarted;
  retainCommentPatch(identity, commentId, { resolved: true });
  let updated = { ...mk(commentId, 0, 0, 4, 'rain'), replies: [] };
  const edit = runSerializedPendingDocWrite(`comment:${commentId}`, async () => {
    const sent = pendingCommentPatch(identity, commentId);
    updated = { ...updated, ...sent };
    acknowledgeCommentPatch(identity, commentId, sent);
  }, identity.documentId);
  releaseReply();
  await reply.catch(() => {});
  await edit;
  const overlaid = applyRetainedCommentIntent(identity, updated);
  check(
    'failed reply remains overlaid after subsequent full edit response',
    overlaid.resolved === true && overlaid.replies.some((candidate) => candidate.id === optimistic.id),
  );
  acknowledgeOptimisticCommentReplies(identity, commentId, [optimistic.id]);
}

// 31. A lone failed scalar mutation has no later UI action to piggyback on.
//     The close/handoff flusher retries the retained snapshot and clears it only
//     after the retry is acknowledged.
{
  const identity: CapturedDocumentIdentity = { documentId: 'intent-doc-close', incarnation: 'inc' };
  const commentId = 'close-patch';
  let attempts = 0;
  retainCommentPatch(identity, commentId, { body: 'persist on close', resolved: true });
  const transport = {
    update: async (patch: ReturnType<typeof pendingCommentPatch>) => {
      attempts += 1;
      if (attempts === 1) throw new Error('lost connection');
      return { ...mk(commentId, 0, 0, 4, 'rain'), ...patch };
    },
    addReply: async () => { throw new Error('unexpected reply'); },
  };
  await flushRetainedCommentIntent(identity, commentId, transport).catch(() => {});
  check(
    'failed close flush keeps lone scalar intent retained',
    hasRetainedCommentIntent(identity, commentId),
  );
  const saved = await flushRetainedCommentIntent(identity, commentId, transport);
  check(
    'close flush retries and acknowledges lone scalar intent',
    attempts === 2
      && saved?.body === 'persist on close'
      && saved.resolved === true
      && !hasRetainedCommentIntent(identity, commentId),
  );
}

// 32. Reply retry uses the same client-generated id. If the first response is
//     lost after the backend write, its idempotency key prevents a duplicate;
//     retained intent clears only after a response is observed.
{
  const identity: CapturedDocumentIdentity = { documentId: 'intent-doc-close', incarnation: 'inc' };
  const commentId = 'close-reply';
  const reply = {
    id: 'reply-stable-id',
    body: 'persist this reply',
    author: 'you',
    created_at: NOW,
  };
  const attemptedIds: string[] = [];
  retainOptimisticCommentReplies(identity, commentId, [reply]);
  const transport = {
    update: async () => { throw new Error('unexpected patch'); },
    addReply: async (candidate: typeof reply) => {
      attemptedIds.push(candidate.id);
      if (attemptedIds.length === 1) throw new Error('response lost');
      return { ...mk(commentId, 0, 0, 4, 'rain'), replies: [candidate] };
    },
  };
  await flushRetainedCommentIntent(identity, commentId, transport).catch(() => {});
  check(
    'failed close flush keeps lone reply intent retained',
    hasRetainedCommentIntent(identity, commentId),
  );
  await flushRetainedCommentIntent(identity, commentId, transport);
  check(
    'close flush retries reply with stable id and acknowledges it',
    attemptedIds.join(',') === 'reply-stable-id,reply-stable-id'
      && !hasRetainedCommentIntent(identity, commentId),
  );
}

// 33. The retained owner is registered with the shared document coordinator,
//     not only a mounted React hook. Therefore its rejection blocks handoff and
//     a later coordinator pass retries both scalar and reply-only failures.
{
  const identity: CapturedDocumentIdentity = {
    documentId: 'intent-doc-lifetime',
    incarnation: 'inc-lifetime',
  };
  const commentId = 'lifetime-comment';
  let failNext = true;
  const server = { ...mk(commentId, 0, 0, 4, 'rain'), replies: [] as Comment['replies'] };
  configureRetainedCommentIntentWriter((captured, id) => (
    flushRetainedCommentIntent(captured, id, {
      update: async (patch) => {
        if (failNext) {
          failNext = false;
          throw new Error('offline');
        }
        Object.assign(server, patch);
        return { ...server };
      },
      addReply: async (reply) => {
        if (failNext) {
          failNext = false;
          throw new Error('offline');
        }
        if (!server.replies.some((candidate) => candidate.id === reply.id)) {
          server.replies.push(reply);
        }
        return { ...server, replies: [...server.replies] };
      },
    })
  ));
  setCurrentDocumentIdentity(identity.documentId, identity.incarnation);

  retainCommentPatch(identity, commentId, { body: 'lifetime patch' });
  let blockedPatchHandoff = false;
  await flushPendingDocSaves().catch(() => { blockedPatchHandoff = true; });
  check(
    'registered comment flusher blocks handoff on lone patch failure',
    blockedPatchHandoff && hasRetainedCommentIntent(identity, commentId),
  );
  await flushPendingDocSaves();
  check(
    'registered comment flusher retries lone patch on next handoff',
    server.body === 'lifetime patch' && !hasRetainedCommentIntent(identity, commentId),
  );

  const reply = {
    id: 'reply-lifetime-stable',
    body: 'lifetime reply',
    author: 'you',
    created_at: NOW,
  };
  failNext = true;
  retainOptimisticCommentReplies(identity, commentId, [reply]);
  let blockedReplyHandoff = false;
  await flushPendingDocSaves().catch(() => { blockedReplyHandoff = true; });
  check(
    'registered comment flusher blocks handoff on lone reply failure',
    blockedReplyHandoff && hasRetainedCommentIntent(identity, commentId),
  );
  await flushPendingDocSaves();
  check(
    'registered comment flusher retries lone reply on next handoff',
    server.replies.filter((candidate) => candidate.id === reply.id).length === 1
      && !hasRetainedCommentIntent(identity, commentId),
  );
  setCurrentDocumentIdentity('', '');
}

// --- report ---
console.log(`Comment anchor tests: ${passed} passed, ${failures.length} failed`);
for (const f of failures) console.log('  FAIL: ' + f);
if (failures.length) throw new Error(`${failures.length} comment anchor test(s) failed`);
console.log('COMMENTS TESTS: PASS');
