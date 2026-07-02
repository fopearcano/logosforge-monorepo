/**
 * Anchor math for comments: turning a selection into a draft, and reconciling
 * stored anchors against the live text so highlights stay on their words after
 * edits.
 *
 * An anchor is (blockIndex, charFrom, charTo) — ProseMirror does not keep block
 * ids — plus a W3C-style text-quote selector: the exact `quote` with short
 * `prefix`/`suffix` context windows. Relocation uses that context to (a) pick the
 * RIGHT occurrence when the quoted text repeats ("the", a character name) instead
 * of blindly taking the first match, and (b) keep the comment attached when the
 * quoted text itself is edited — re-anchoring between the surviving prefix/suffix
 * landmarks rather than orphaning (and deleting) it.
 *
 * `locate()` is the single source of truth: both reconcileMarks (paint) and
 * findOrphanIds (delete) call it, so they can never disagree about whether a
 * comment still has a home.
 */

import type { Editor } from '@tiptap/react';

import type { Comment, CommentDraft } from './commentsApi';
import type { CommentMark } from './commentsExtension';

const CONTEXT = 32; // chars of prefix/suffix context captured for disambiguation
const MIN_CONTEXT_MATCH = 4; // a landmark must match ≥ this many chars to be considered
const MIN_ONE_SIDED = 8; // a SINGLE surviving landmark must match ≥ this to anchor alone
const MAX_GAP_SLACK = 40; // how much an edited span may grow beyond the original quote

/** Build a draft from the current non-empty selection (one block, or spanning
 * several — the anchor records start + end edges and the quote joins blocks). */
export function selectionToDraft(editor: Editor): CommentDraft | null {
  const { state } = editor;
  const { from, to, empty } = state.selection;
  if (empty || to <= from) return null;
  const $from = state.selection.$from;
  const $to = state.selection.$to;
  const startBlock = $from.index(0);
  const endBlock = $to.index(0);
  const startBlockStart = $from.start();
  const fromOffset = from - startBlockStart;

  if (startBlock === endBlock) {
    const blockEnd = $from.end();
    const toOffset = to - startBlockStart;
    if (toOffset <= fromOffset) return null;
    const blockText = state.doc.textBetween(startBlockStart, blockEnd);
    return {
      anchor: {
        block_index: startBlock,
        from_offset: fromOffset,
        to_offset: toOffset,
        prefix: blockText.slice(Math.max(0, fromOffset - CONTEXT), fromOffset),
        suffix: blockText.slice(toOffset, toOffset + CONTEXT),
      },
      quote: blockText.slice(fromOffset, toOffset),
      body: '',
    };
  }

  // Multi-block: start edge in the first block, end edge in the last. The quote
  // joins the spanned block texts with '\n' (split back out when relocating).
  const endBlockStart = $to.start();
  const toOffset = to - endBlockStart;
  const startBlockText = state.doc.textBetween(startBlockStart, $from.end());
  const endBlockText = state.doc.textBetween(endBlockStart, $to.end());
  return {
    anchor: {
      block_index: startBlock,
      from_offset: fromOffset,
      end_block_index: endBlock,
      to_offset: toOffset,
      prefix: startBlockText.slice(Math.max(0, fromOffset - CONTEXT), fromOffset),
      suffix: endBlockText.slice(toOffset, toOffset + CONTEXT),
    },
    quote: state.doc.textBetween(from, to, '\n', '\n'),
    body: '',
  };
}

// --- relocation -------------------------------------------------------------

interface Located {
  blockIndex: number;
  from: number;
  to: number;
}

/** How many trailing chars of `a` match the trailing chars of `b`. */
function commonSuffix(a: string, b: string): number {
  let i = 0;
  const max = Math.min(a.length, b.length);
  while (i < max && a[a.length - 1 - i] === b[b.length - 1 - i]) i += 1;
  return i;
}

/** How many leading chars of `a` match the leading chars of `b`. */
function commonPrefix(a: string, b: string): number {
  let i = 0;
  const max = Math.min(a.length, b.length);
  while (i < max && a[i] === b[i]) i += 1;
  return i;
}

/** Every start offset of `needle` in `hay` (candidate occurrences of a quote). */
function allIndexesOf(hay: string, needle: string): number[] {
  const out: number[] = [];
  if (!needle) return out;
  let i = hay.indexOf(needle);
  while (i !== -1) {
    out.push(i);
    i = hay.indexOf(needle, i + 1);
  }
  return out;
}

/** Every end offset of `needle` in `hay` (occurrence start + needle length). */
function allEndsOf(hay: string, needle: string): number[] {
  return allIndexesOf(hay, needle).map((i) => i + needle.length);
}

/** The value in a non-empty `arr` closest to `target`. */
function nearest(arr: number[], target: number): number {
  let best = arr[0];
  for (const v of arr) if (Math.abs(v - target) < Math.abs(best - target)) best = v;
  return best;
}

/** Word character (letter/digit/underscore)? A missing char (span edge) is not. */
function isWord(ch: string | undefined): boolean {
  return ch != null && /\w/.test(ch);
}

/** 0–2: does [start,end) sit on word boundaries? Lets a standalone word win over
 * the same letters embedded in a longer word ("art" vs the "art" in "start"). */
function wordBoundaryScore(t: string, start: number, end: number): number {
  const leftOk = start <= 0 || !isWord(t[start - 1]);
  const rightOk = end >= t.length || !isWord(t[end]);
  return (leftOk ? 1 : 0) + (rightOk ? 1 : 0);
}

/**
 * Quote gone (edited away) — re-anchor between the surviving context landmarks.
 * Considers ALL occurrences of the longest matching prefix-tail and suffix-head
 * (not just the first/last), then picks the prefixEnd→suffixStart pair that is
 * ordered, within the gap budget, and closest to where the span used to be
 * (hintFrom/hintTo) — so a repeated landmark can't strand the comment or anchor it
 * onto unrelated text. Falls back to a single distinctive landmark (≥ MIN_ONE_SIDED)
 * at the occurrence nearest the old span when only one side survives.
 */
function bracketBetween(
  t: string,
  prefix: string,
  suffix: string,
  quoteLen: number,
  hintFrom: number,
  hintTo: number,
): { from: number; to: number; score: number } | null {
  let prefixEnds: number[] = [];
  let prefixScore = 0;
  for (let k = prefix.length; k >= MIN_CONTEXT_MATCH; k -= 1) {
    const ends = allEndsOf(t, prefix.slice(prefix.length - k));
    if (ends.length) {
      prefixEnds = ends;
      prefixScore = k;
      break;
    }
  }
  let suffixStarts: number[] = [];
  let suffixScore = 0;
  for (let k = suffix.length; k >= MIN_CONTEXT_MATCH; k -= 1) {
    const starts = allIndexesOf(t, suffix.slice(0, k));
    if (starts.length) {
      suffixStarts = starts;
      suffixScore = k;
      break;
    }
  }

  // Best two-sided bracket: ordered, within the gap budget, closest to the old
  // span. Two corroborating landmarks are trusted at MIN_CONTEXT_MATCH each.
  let best: { from: number; to: number; cost: number } | null = null;
  for (const pe of prefixEnds) {
    for (const ss of suffixStarts) {
      if (ss >= pe && ss - pe <= quoteLen + MAX_GAP_SLACK) {
        const cost = Math.abs(pe - hintFrom) + Math.abs(ss - hintTo);
        if (!best || cost < best.cost) best = { from: pe, to: ss, cost };
      }
    }
  }
  if (best) return { from: best.from, to: best.to, score: prefixScore + suffixScore };

  // Only one landmark survives → anchor at the occurrence nearest the old span,
  // spanning the original quote length — but only if that lone landmark is long
  // enough to be distinctive (a short common run like "The " would otherwise
  // re-home the comment onto unrelated text).
  if (prefixEnds.length && prefixScore >= MIN_ONE_SIDED) {
    const pe = nearest(prefixEnds, hintFrom);
    return { from: pe, to: Math.min(pe + quoteLen, t.length), score: prefixScore };
  }
  if (suffixStarts.length && suffixScore >= MIN_ONE_SIDED) {
    const ss = nearest(suffixStarts, hintTo);
    return { from: Math.max(0, ss - quoteLen), to: ss, score: suffixScore };
  }
  return null;
}

/**
 * Locate a single quoted span in the live block texts, or null if it's gone. Two
 * passes:
 *   A) the exact quote is still present somewhere → pick the occurrence whose
 *      surrounding text best matches `prefix`/`suffix`, tie-broken by word boundary
 *      then proximity to the stored (hintBlock, hintFrom). Fixes repeated/short
 *      quotes jumping to the first match.
 *   B) the exact quote is gone (the quoted text was edited) → re-anchor between the
 *      surviving context landmarks, so an in-span edit keeps the span alive.
 * The implicit end offset is hintFrom + quote.length (a selection's span length).
 */
function locateSpan(
  quote: string,
  hintBlock: number,
  hintFrom: number,
  prefix: string,
  suffix: string,
  texts: string[],
): Located | null {
  if (!quote) {
    const t = texts[hintBlock];
    return t == null ? null : { blockIndex: hintBlock, from: hintFrom, to: hintFrom };
  }
  const hintTo = hintFrom + quote.length;
  const stored = texts[hintBlock];

  // Fast path: still exactly where we left it, with its context intact. The context
  // check stops a coincidental same-text "ghost" at the stale offset from masking a
  // real move (Pass A then re-finds the true home).
  if (stored != null && stored.slice(hintFrom, hintTo) === quote) {
    const before = stored.slice(Math.max(0, hintFrom - prefix.length), hintFrom);
    const after = stored.slice(hintTo, hintTo + suffix.length);
    const ctxOk = (!prefix && !suffix) || commonSuffix(prefix, before) + commonPrefix(suffix, after) >= MIN_CONTEXT_MATCH;
    if (ctxOk) return { blockIndex: hintBlock, from: hintFrom, to: hintTo };
  }

  // Pass A — exact quote, disambiguated by context, then word-boundary, then proximity.
  let bestA: { score: number; wb: number; dist: number; loc: Located } | null = null;
  for (let bi = 0; bi < texts.length; bi += 1) {
    const t = texts[bi];
    if (typeof t !== 'string') continue; // tolerate a sparse texts[] during render
    for (const start of allIndexesOf(t, quote)) {
      const end = start + quote.length;
      const before = t.slice(Math.max(0, start - prefix.length), start);
      const after = t.slice(end, end + suffix.length);
      const score = commonSuffix(prefix, before) + commonPrefix(suffix, after);
      const wb = wordBoundaryScore(t, start, end);
      const dist = Math.abs(bi - hintBlock) * 100000 + Math.abs(start - hintFrom);
      const better =
        !bestA ||
        score > bestA.score ||
        (score === bestA.score && (wb > bestA.wb || (wb === bestA.wb && dist < bestA.dist)));
      if (better) bestA = { score, wb, dist, loc: { blockIndex: bi, from: start, to: end } };
    }
  }
  if (bestA) return bestA.loc;

  // Pass B — quote edited away → bracket between surviving context landmarks.
  if (prefix.length >= MIN_CONTEXT_MATCH || suffix.length >= MIN_CONTEXT_MATCH) {
    let bestB: { score: number; loc: Located } | null = null;
    for (let bi = 0; bi < texts.length; bi += 1) {
      const t = texts[bi];
      if (typeof t !== 'string') continue;
      const bracket = bracketBetween(t, prefix, suffix, quote.length, hintFrom, hintTo);
      if (bracket && (!bestB || bracket.score > bestB.score)) {
        bestB = { score: bracket.score, loc: { blockIndex: bi, from: bracket.from, to: bracket.to } };
      }
    }
    if (bestB) return bestB.loc;
  }

  return null; // genuinely gone
}

/**
 * Every per-block span a comment currently covers — one for a single-block comment,
 * several for a multi-block selection — or [] if it's orphaned. A multi-block anchor
 * is relocated by its EDGES: the start edge (real prefix, block boundary after) and
 * the end edge (block boundary before, real suffix); the blocks between are filled.
 */
export function commentSpans(comment: Comment, texts: string[]): Located[] {
  const a = comment.anchor;
  const prefix = a.prefix ?? '';
  const suffix = a.suffix ?? '';
  const endBlock = a.end_block_index ?? a.block_index;

  if (endBlock === a.block_index) {
    if (!comment.quote) {
      // No quote to relocate by — keep the stored span while its block exists.
      return texts[a.block_index] == null ? [] : [{ blockIndex: a.block_index, from: a.from_offset, to: a.to_offset }];
    }
    const loc = locateSpan(comment.quote, a.block_index, a.from_offset, prefix, suffix, texts);
    return loc ? [loc] : [];
  }

  const lines = comment.quote.split('\n');
  const start = locateSpan(lines[0], a.block_index, a.from_offset, prefix, '', texts);
  const end = locateSpan(lines[lines.length - 1], endBlock, 0, '', suffix, texts);

  if (start && end && end.blockIndex >= start.blockIndex) {
    const spans: Located[] = [];
    for (let bi = start.blockIndex; bi <= end.blockIndex; bi += 1) {
      const len = (texts[bi] ?? '').length;
      if (bi === start.blockIndex && bi === end.blockIndex) spans.push({ blockIndex: bi, from: start.from, to: end.to });
      else if (bi === start.blockIndex) spans.push({ blockIndex: bi, from: start.from, to: len });
      else if (bi === end.blockIndex) spans.push({ blockIndex: bi, from: 0, to: end.to });
      else spans.push({ blockIndex: bi, from: 0, to: len });
    }
    return spans;
  }
  // Only one edge survived → keep the comment anchored to that edge.
  if (start) return [start];
  if (end) return [end];
  return [];
}

/** The primary (start) span of a comment — used for popover/nav positioning. */
export function locate(comment: Comment, texts: string[]): Located | null {
  const spans = commentSpans(comment, texts);
  return spans.length ? spans[0] : null;
}

/**
 * Reconcile stored anchors to the current block texts: each comment follows its
 * quoted text across edits and block shifts (a multi-block comment paints one mark
 * per block it spans). A comment that can't be placed produces no mark (and is
 * cleaned up via findOrphanIds).
 */
export function reconcileMarks(comments: Comment[], texts: string[]): CommentMark[] {
  const out: CommentMark[] = [];
  for (const c of comments) {
    for (const s of commentSpans(c, texts)) {
      out.push({ id: c.id, blockIndex: s.blockIndex, from: s.from, to: s.to, resolved: c.resolved });
    }
  }
  return out;
}

/**
 * Ids of comments that no longer have a home anywhere in the document — commentSpans
 * is empty only when the quote AND its context are both gone (the block was deleted,
 * not merely edited). The parent deletes these so a comment can't outlive its anchor,
 * while an in-span edit (quote changed, context intact) is preserved. Returns [] when
 * there are no blocks at all, so a load/doc-switch transient can't flag everything.
 */
export function findOrphanIds(comments: Comment[], texts: string[]): string[] {
  if (!texts.length) return [];
  return comments.filter((c) => commentSpans(c, texts).length === 0).map((c) => c.id);
}
