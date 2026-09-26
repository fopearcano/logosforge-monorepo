/**
 * Pure inline-comment anchor math for the Pro manuscript.
 *
 * Pro stores offsets in UTF-16 code units (the units used by JavaScript strings
 * and ProseMirror) and scopes each edge to a stable scene + field.  Reconciliation
 * treats the manuscript as an ordered sequence of fields — title, then content,
 * for every scene — while always returning spans in those concrete scopes.
 *
 * The TextQuote relocation strategy mirrors the proven Whiteboard algorithm:
 * exact quote, context score, word-boundary score, proximity, then a conservative
 * prefix/suffix bracket fallback when the selected text itself was edited.
 */

import type {
  InlineCommentAnchorDTO,
  InlineCommentCreateDTO,
  InlineCommentDTO,
  InlineCommentField,
  InlineCommentUpdateDTO,
  SceneDTO,
} from "@logosforge/ui-contracts";

const CONTEXT_UNITS = 32;
const MIN_CONTEXT_MATCH = 4;
const MIN_ONE_SIDED_MATCH = 8;
const MAX_GAP_SLACK = 40;

export type CommentAnchorDraft = Pick<InlineCommentCreateDTO, "anchor" | "quote">;

export interface CommentSelectionEndpoint {
  sceneId: number;
  field: InlineCommentField;
  offset: number;
}

/** A live highlight range, expressed in UTF-16 offsets into one scene field. */
export interface CommentSpan {
  commentId: number;
  sceneId: number;
  field: InlineCommentField;
  fromOffset: number;
  toOffset: number;
  resolved: boolean;
}

interface FieldSlot {
  sceneId: number;
  field: InlineCommentField;
  text: string;
}

interface LocatedSpan {
  slotIndex: number;
  fromOffset: number;
  toOffset: number;
}

interface Bracket {
  fromOffset: number;
  toOffset: number;
  score: number;
}

interface CommentResolution {
  spans: CommentSpan[];
  /** Both stored edges were located in document order (not an edge-only rescue). */
  complete: boolean;
}

function orderValue(value: number): number {
  return Number.isFinite(value) ? value : Number.MAX_SAFE_INTEGER;
}

/** Build the canonical manuscript field order without mutating the caller's list. */
function fieldSlots(scenes: readonly SceneDTO[]): FieldSlot[] {
  const ordered = [...scenes].sort((left, right) => (
    orderValue(left.sort_order) - orderValue(right.sort_order)
    || orderValue(left.order_index) - orderValue(right.order_index)
    || left.id - right.id
  ));
  const slots: FieldSlot[] = [];
  for (const scene of ordered) {
    slots.push({ sceneId: scene.id, field: "title", text: scene.title ?? "" });
    slots.push({ sceneId: scene.id, field: "content", text: scene.content ?? "" });
  }
  return slots;
}

function slotKey(sceneId: number, field: InlineCommentField): string {
  return `${sceneId}:${field}`;
}

function slotIndexes(slots: readonly FieldSlot[]): Map<string, number> {
  const result = new Map<string, number>();
  slots.forEach((slot, index) => {
    const key = slotKey(slot.sceneId, slot.field);
    if (!result.has(key)) result.set(key, index);
  });
  return result;
}

function isHighSurrogate(unit: number): boolean {
  return unit >= 0xd800 && unit <= 0xdbff;
}

function isLowSurrogate(unit: number): boolean {
  return unit >= 0xdc00 && unit <= 0xdfff;
}

/** Whether `offset` is a legal UTF-16 boundary rather than the middle of a pair. */
export function isUtf16Boundary(text: string, offset: number): boolean {
  if (!Number.isInteger(offset) || offset < 0 || offset > text.length) return false;
  return !(
    offset > 0
    && offset < text.length
    && isHighSurrogate(text.charCodeAt(offset - 1))
    && isLowSurrogate(text.charCodeAt(offset))
  );
}

function hasUnpairedSurrogate(text: string): boolean {
  for (let index = 0; index < text.length; index += 1) {
    const unit = text.charCodeAt(index);
    if (isHighSurrogate(unit)) {
      if (index + 1 >= text.length || !isLowSurrogate(text.charCodeAt(index + 1))) return true;
      index += 1;
    } else if (isLowSurrogate(unit)) {
      return true;
    }
  }
  return false;
}

function floorBoundary(text: string, offset: number): number {
  let bounded = Math.max(0, Math.min(text.length, Math.trunc(offset)));
  if (!isUtf16Boundary(text, bounded)) bounded -= 1;
  return bounded;
}

function ceilBoundary(text: string, offset: number): number {
  let bounded = Math.max(0, Math.min(text.length, Math.trunc(offset)));
  if (!isUtf16Boundary(text, bounded)) bounded += 1;
  return bounded;
}

function contextBefore(text: string, offset: number): string {
  const rawStart = Math.max(0, offset - CONTEXT_UNITS);
  return text.slice(floorBoundary(text, rawStart), offset);
}

function contextAfter(text: string, offset: number): string {
  const rawEnd = Math.min(text.length, offset + CONTEXT_UNITS);
  return text.slice(offset, ceilBoundary(text, rawEnd));
}

/**
 * Create the portable anchor payload for a native selection inside one field.
 * Offsets are JavaScript/ProseMirror UTF-16 offsets. Invalid, collapsed, or
 * surrogate-splitting selections are rejected instead of creating an anchor the
 * core would later reject.
 */
export function createSingleFieldCommentDraft(
  scene: SceneDTO,
  field: InlineCommentField,
  fromOffset: number,
  toOffset: number,
): CommentAnchorDraft | null {
  const text = scene[field] ?? "";
  if (
    !Number.isInteger(fromOffset)
    || !Number.isInteger(toOffset)
    || fromOffset < 0
    || toOffset > text.length
    || toOffset <= fromOffset
    || !isUtf16Boundary(text, fromOffset)
    || !isUtf16Boundary(text, toOffset)
  ) return null;

  const quote = text.slice(fromOffset, toOffset);
  if (!quote || hasUnpairedSurrogate(quote)) return null;
  const anchor: InlineCommentAnchorDTO = {
    start_scene_id: scene.id,
    start_field: field,
    from_offset: fromOffset,
    end_scene_id: scene.id,
    end_field: field,
    to_offset: toOffset,
    prefix: contextBefore(text, fromOffset),
    suffix: contextAfter(text, toOffset),
  };
  return { anchor, quote };
}

/**
 * Create a portable draft for an ordered selection that traverses scene fields.
 * Each crossed field contributes its selected slice and adjacent fields are
 * separated by one newline, matching the reconciliation model. Passing two
 * endpoints in the same field has the same semantics as the single-field helper.
 */
export function createMultiFieldCommentDraft(
  scenes: readonly SceneDTO[],
  start: CommentSelectionEndpoint,
  end: CommentSelectionEndpoint,
): CommentAnchorDraft | null {
  const slots = fieldSlots(scenes);
  const indexes = slotIndexes(slots);
  const startIndex = indexes.get(slotKey(start.sceneId, start.field));
  const endIndex = indexes.get(slotKey(end.sceneId, end.field));
  if (startIndex == null || endIndex == null || startIndex > endIndex) return null;
  const startSlot = slots[startIndex]!;
  const endSlot = slots[endIndex]!;
  if (
    !Number.isInteger(start.offset)
    || !Number.isInteger(end.offset)
    || !isUtf16Boundary(startSlot.text, start.offset)
    || !isUtf16Boundary(endSlot.text, end.offset)
    || (startIndex === endIndex && end.offset <= start.offset)
  ) return null;

  const quoteParts: string[] = [];
  for (let index = startIndex; index <= endIndex; index += 1) {
    const slot = slots[index]!;
    const fromOffset = index === startIndex ? start.offset : 0;
    const toOffset = index === endIndex ? end.offset : slot.text.length;
    quoteParts.push(slot.text.slice(fromOffset, toOffset));
  }
  const quote = quoteParts.join("\n");
  const prefix = contextBefore(startSlot.text, start.offset);
  const suffix = contextAfter(endSlot.text, end.offset);
  if (
    !quoteParts.some((part) => part.length > 0)
    || hasUnpairedSurrogate(quote)
    || hasUnpairedSurrogate(prefix)
    || hasUnpairedSurrogate(suffix)
  ) return null;
  return {
    anchor: {
      start_scene_id: start.sceneId,
      start_field: start.field,
      from_offset: start.offset,
      end_scene_id: end.sceneId,
      end_field: end.field,
      to_offset: end.offset,
      prefix,
      suffix,
    },
    quote,
  };
}

function commonSuffix(left: string, right: string): number {
  let matched = 0;
  const limit = Math.min(left.length, right.length);
  while (
    matched < limit
    && left[left.length - 1 - matched] === right[right.length - 1 - matched]
  ) matched += 1;
  return matched;
}

function commonPrefix(left: string, right: string): number {
  let matched = 0;
  const limit = Math.min(left.length, right.length);
  while (matched < limit && left[matched] === right[matched]) matched += 1;
  return matched;
}

function allIndexesOf(haystack: string, needle: string): number[] {
  if (!needle || hasUnpairedSurrogate(needle)) return [];
  const result: number[] = [];
  let index = haystack.indexOf(needle);
  while (index !== -1) {
    const end = index + needle.length;
    if (isUtf16Boundary(haystack, index) && isUtf16Boundary(haystack, end)) result.push(index);
    index = haystack.indexOf(needle, index + 1);
  }
  return result;
}

function allEndsOf(haystack: string, needle: string): number[] {
  return allIndexesOf(haystack, needle).map((index) => index + needle.length);
}

function nearest(values: readonly number[], target: number): number {
  let best = values[0]!;
  for (const value of values) {
    if (Math.abs(value - target) < Math.abs(best - target)) best = value;
  }
  return best;
}

function isWordCharacter(character: string | undefined): boolean {
  return character != null && /\w/.test(character);
}

function wordBoundaryScore(text: string, start: number, end: number): number {
  const left = start <= 0 || !isWordCharacter(text[start - 1]);
  const right = end >= text.length || !isWordCharacter(text[end]);
  return (left ? 1 : 0) + (right ? 1 : 0);
}

function bracketBetween(
  text: string,
  prefix: string,
  suffix: string,
  quoteLength: number,
  hintFrom: number,
  hintTo: number,
): Bracket | null {
  let prefixEnds: number[] = [];
  let prefixScore = 0;
  for (let length = prefix.length; length >= MIN_CONTEXT_MATCH; length -= 1) {
    const start = prefix.length - length;
    if (!isUtf16Boundary(prefix, start)) continue;
    const ends = allEndsOf(text, prefix.slice(start));
    if (ends.length) {
      prefixEnds = ends;
      prefixScore = length;
      break;
    }
  }

  let suffixStarts: number[] = [];
  let suffixScore = 0;
  for (let length = suffix.length; length >= MIN_CONTEXT_MATCH; length -= 1) {
    if (!isUtf16Boundary(suffix, length)) continue;
    const starts = allIndexesOf(text, suffix.slice(0, length));
    if (starts.length) {
      suffixStarts = starts;
      suffixScore = length;
      break;
    }
  }

  let best: { fromOffset: number; toOffset: number; cost: number } | null = null;
  for (const prefixEnd of prefixEnds) {
    for (const suffixStart of suffixStarts) {
      if (suffixStart < prefixEnd || suffixStart - prefixEnd > quoteLength + MAX_GAP_SLACK) continue;
      const cost = Math.abs(prefixEnd - hintFrom) + Math.abs(suffixStart - hintTo);
      if (
        !best
        || cost < best.cost
        || (cost === best.cost && (
          prefixEnd < best.fromOffset
          || (prefixEnd === best.fromOffset && suffixStart < best.toOffset)
        ))
      ) best = { fromOffset: prefixEnd, toOffset: suffixStart, cost };
    }
  }
  if (best) {
    return {
      fromOffset: best.fromOffset,
      toOffset: best.toOffset,
      score: prefixScore + suffixScore,
    };
  }

  if (prefixEnds.length && prefixScore >= MIN_ONE_SIDED_MATCH) {
    const fromOffset = nearest(prefixEnds, hintFrom);
    return {
      fromOffset,
      toOffset: ceilBoundary(text, Math.min(fromOffset + quoteLength, text.length)),
      score: prefixScore,
    };
  }
  if (suffixStarts.length && suffixScore >= MIN_ONE_SIDED_MATCH) {
    const toOffset = nearest(suffixStarts, hintTo);
    return {
      fromOffset: floorBoundary(text, Math.max(0, toOffset - quoteLength)),
      toOffset,
      score: suffixScore,
    };
  }
  return null;
}

function closerLocation(
  candidate: LocatedSpan,
  incumbent: LocatedSpan,
  hintSlot: number | null,
  hintFrom: number,
): boolean {
  const candidateSlotDistance = hintSlot == null ? 0 : Math.abs(candidate.slotIndex - hintSlot);
  const incumbentSlotDistance = hintSlot == null ? 0 : Math.abs(incumbent.slotIndex - hintSlot);
  if (candidateSlotDistance !== incumbentSlotDistance) return candidateSlotDistance < incumbentSlotDistance;
  const candidateOffsetDistance = Math.abs(candidate.fromOffset - hintFrom);
  const incumbentOffsetDistance = Math.abs(incumbent.fromOffset - hintFrom);
  if (candidateOffsetDistance !== incumbentOffsetDistance) return candidateOffsetDistance < incumbentOffsetDistance;
  return candidate.slotIndex < incumbent.slotIndex
    || (candidate.slotIndex === incumbent.slotIndex && candidate.fromOffset < incumbent.fromOffset);
}

/** Locate one edge/span against all live fields. */
function locateSpan(
  quote: string,
  hintSlot: number | null,
  hintFrom: number,
  prefix: string,
  suffix: string,
  slots: readonly FieldSlot[],
): LocatedSpan | null {
  if (!quote) {
    if (hintSlot == null) return null;
    const text = slots[hintSlot]?.text;
    if (text == null) return null;
    const point = floorBoundary(text, hintFrom);
    return { slotIndex: hintSlot, fromOffset: point, toOffset: point };
  }
  if (hasUnpairedSurrogate(quote)) return null;

  const safeHintFrom = Math.max(0, Math.trunc(hintFrom));
  const hintTo = safeHintFrom + quote.length;
  const stored = hintSlot == null ? undefined : slots[hintSlot]?.text;
  if (
    stored != null
    && isUtf16Boundary(stored, safeHintFrom)
    && isUtf16Boundary(stored, hintTo)
    && stored.slice(safeHintFrom, hintTo) === quote
  ) {
    const before = stored.slice(Math.max(0, safeHintFrom - prefix.length), safeHintFrom);
    const after = stored.slice(hintTo, hintTo + suffix.length);
    const contextScore = commonSuffix(prefix, before) + commonPrefix(suffix, after);
    if ((!prefix && !suffix) || contextScore >= MIN_CONTEXT_MATCH) {
      return { slotIndex: hintSlot!, fromOffset: safeHintFrom, toOffset: hintTo };
    }
  }

  let exact: { contextScore: number; boundaryScore: number; location: LocatedSpan } | null = null;
  for (let index = 0; index < slots.length; index += 1) {
    const slot = slots[index]!;
    for (const fromOffset of allIndexesOf(slot.text, quote)) {
      const toOffset = fromOffset + quote.length;
      const before = slot.text.slice(Math.max(0, fromOffset - prefix.length), fromOffset);
      const after = slot.text.slice(toOffset, toOffset + suffix.length);
      const contextScore = commonSuffix(prefix, before) + commonPrefix(suffix, after);
      const boundaryScore = wordBoundaryScore(slot.text, fromOffset, toOffset);
      const location = { slotIndex: index, fromOffset, toOffset };
      if (
        !exact
        || contextScore > exact.contextScore
        || (contextScore === exact.contextScore && (
          boundaryScore > exact.boundaryScore
          || (boundaryScore === exact.boundaryScore
            && closerLocation(location, exact.location, hintSlot, safeHintFrom))
        ))
      ) exact = { contextScore, boundaryScore, location };
    }
  }
  if (exact) return exact.location;

  if (prefix.length < MIN_CONTEXT_MATCH && suffix.length < MIN_CONTEXT_MATCH) return null;
  let fallback: { score: number; location: LocatedSpan } | null = null;
  for (let index = 0; index < slots.length; index += 1) {
    const slot = slots[index]!;
    const bracket = bracketBetween(slot.text, prefix, suffix, quote.length, safeHintFrom, hintTo);
    if (!bracket) continue;
    const location = {
      slotIndex: index,
      fromOffset: bracket.fromOffset,
      toOffset: bracket.toOffset,
    };
    if (
      !fallback
      || bracket.score > fallback.score
      || (bracket.score === fallback.score
        && closerLocation(location, fallback.location, hintSlot, safeHintFrom))
    ) fallback = { score: bracket.score, location };
  }
  return fallback?.location ?? null;
}

function asCommentSpan(comment: InlineCommentDTO, slot: FieldSlot, located: LocatedSpan): CommentSpan {
  return {
    commentId: comment.id,
    sceneId: slot.sceneId,
    field: slot.field,
    fromOffset: located.fromOffset,
    toOffset: located.toOffset,
    resolved: comment.resolved,
  };
}

function structuralRange(
  comment: InlineCommentDTO,
  slot: FieldSlot,
  slotIndex: number,
): CommentSpan[] {
  const fromOffset = floorBoundary(slot.text, comment.anchor.from_offset);
  if (comment.anchor.from_offset === comment.anchor.to_offset) {
    return [asCommentSpan(comment, slot, { slotIndex, fromOffset, toOffset: fromOffset })];
  }
  const toOffset = ceilBoundary(slot.text, comment.anchor.to_offset);
  if (toOffset < fromOffset) return [];
  return [asCommentSpan(comment, slot, { slotIndex, fromOffset, toOffset })];
}

function resolutionResult(
  comment: InlineCommentDTO,
  spans: CommentSpan[],
  complete: boolean,
): CommentResolution {
  // A quoted selection that only survives as an empty bracket has lost all of
  // its selected text and is an orphan. Quote-less legacy point anchors are
  // intentionally exempt: their zero-width position is their durable identity.
  if (comment.quote && spans.length > 0 && !spans.some((span) => span.toOffset > span.fromOffset)) {
    return { spans: [], complete: false };
  }
  return { spans, complete };
}

/**
 * Resolve one stored thread into the live per-scene/per-field spans it covers.
 * Cross-field and cross-scene selections relocate their two edges independently;
 * if only one edge survives, that edge remains attached instead of orphaning the
 * entire discussion.
 */
function resolveComment(
  comment: InlineCommentDTO,
  scenes: readonly SceneDTO[],
): CommentResolution {
  const slots = fieldSlots(scenes);
  if (!slots.length) return { spans: [], complete: false };
  const indexes = slotIndexes(slots);
  const anchor = comment.anchor;
  const startSlot = indexes.get(slotKey(anchor.start_scene_id, anchor.start_field)) ?? null;
  const endSlot = indexes.get(slotKey(anchor.end_scene_id, anchor.end_field)) ?? null;
  const sameField = anchor.start_scene_id === anchor.end_scene_id
    && anchor.start_field === anchor.end_field;

  if (sameField) {
    if (startSlot == null) return { spans: [], complete: false };
    if (!comment.quote) {
      const spans = structuralRange(comment, slots[startSlot]!, startSlot);
      return resolutionResult(comment, spans, spans.length > 0);
    }
    const located = locateSpan(
      comment.quote,
      startSlot,
      anchor.from_offset,
      anchor.prefix ?? "",
      anchor.suffix ?? "",
      slots,
    );
    const spans = located ? [asCommentSpan(comment, slots[located.slotIndex]!, located)] : [];
    return resolutionResult(comment, spans, located != null);
  }

  const quoteParts = comment.quote.split("\n");
  // A real multi-field selection has a separator. If a legacy payload does not,
  // preserve its stable structural edges instead of searching the same opaque
  // quote twice and risking a confident-looking but incorrect relocation.
  const hasSeparatedEdges = quoteParts.length > 1;
  const startQuote = hasSeparatedEdges ? quoteParts[0]! : "";
  const endQuote = hasSeparatedEdges ? quoteParts[quoteParts.length - 1]! : "";
  const start = locateSpan(
    startQuote,
    startSlot,
    anchor.from_offset,
    anchor.prefix ?? "",
    "",
    slots,
  );
  const endHint = Math.max(0, anchor.to_offset - endQuote.length);
  const end = locateSpan(
    endQuote,
    endSlot,
    endHint,
    "",
    anchor.suffix ?? "",
    slots,
  );

  if (start && end && end.slotIndex >= start.slotIndex) {
    if (start.slotIndex === end.slotIndex) {
      if (end.toOffset < start.fromOffset) {
        return resolutionResult(
          comment,
          [asCommentSpan(comment, slots[start.slotIndex]!, start)],
          false,
        );
      }
      return resolutionResult(comment, [asCommentSpan(comment, slots[start.slotIndex]!, {
          slotIndex: start.slotIndex,
          fromOffset: start.fromOffset,
          toOffset: end.toOffset,
        })], true);
    }
    const result: CommentSpan[] = [];
    for (let index = start.slotIndex; index <= end.slotIndex; index += 1) {
      const slot = slots[index]!;
      const located: LocatedSpan = index === start.slotIndex
        ? { slotIndex: index, fromOffset: start.fromOffset, toOffset: slot.text.length }
        : index === end.slotIndex
          ? { slotIndex: index, fromOffset: 0, toOffset: end.toOffset }
          : { slotIndex: index, fromOffset: 0, toOffset: slot.text.length };
      result.push(asCommentSpan(comment, slot, located));
    }
    return resolutionResult(comment, result, true);
  }
  if (start) return resolutionResult(comment, [asCommentSpan(comment, slots[start.slotIndex]!, start)], false);
  if (end) return resolutionResult(comment, [asCommentSpan(comment, slots[end.slotIndex]!, end)], false);
  return { spans: [], complete: false };
}

export function commentSpans(
  comment: InlineCommentDTO,
  scenes: readonly SceneDTO[],
): CommentSpan[] {
  return resolveComment(comment, scenes).spans;
}

/**
 * Build the minimal persistence patch after a complete reconciliation. The
 * helper intentionally declines orphaned and one-edge-only ranges: painting a
 * surviving edge is safe, but overwriting the durable second edge would lose
 * information that a later scene refresh could restore.
 */
export function reconciledCommentPatch(
  comment: InlineCommentDTO,
  scenes: readonly SceneDTO[],
): InlineCommentUpdateDTO | null {
  const resolution = resolveComment(comment, scenes);
  if (!resolution.complete || !resolution.spans.length) return null;

  const first = resolution.spans[0]!;
  const last = resolution.spans[resolution.spans.length - 1]!;
  const slots = fieldSlots(scenes);
  const indexes = slotIndexes(slots);
  const firstSlotIndex = indexes.get(slotKey(first.sceneId, first.field));
  const lastSlotIndex = indexes.get(slotKey(last.sceneId, last.field));
  if (firstSlotIndex == null || lastSlotIndex == null || lastSlotIndex < firstSlotIndex) return null;
  const firstSlot = slots[firstSlotIndex]!;
  const lastSlot = slots[lastSlotIndex]!;

  // Resolution already guarantees field-local, boundary-safe offsets. Recheck
  // here before producing data that will cross the API boundary.
  if (
    !isUtf16Boundary(firstSlot.text, first.fromOffset)
    || !isUtf16Boundary(lastSlot.text, last.toOffset)
  ) return null;

  const nextAnchor: InlineCommentAnchorDTO = {
    start_scene_id: first.sceneId,
    start_field: first.field,
    from_offset: first.fromOffset,
    end_scene_id: last.sceneId,
    end_field: last.field,
    to_offset: last.toOffset,
    prefix: contextBefore(firstSlot.text, first.fromOffset),
    suffix: contextAfter(lastSlot.text, last.toOffset),
  };
  const stored = comment.anchor;
  const sameRange = stored.start_scene_id === nextAnchor.start_scene_id
    && stored.start_field === nextAnchor.start_field
    && stored.from_offset === nextAnchor.from_offset
    && stored.end_scene_id === nextAnchor.end_scene_id
    && stored.end_field === nextAnchor.end_field
    && stored.to_offset === nextAnchor.to_offset;

  const quoteParts: string[] = [];
  for (const span of resolution.spans) {
    const slotIndex = indexes.get(slotKey(span.sceneId, span.field));
    const slot = slotIndex == null ? undefined : slots[slotIndex];
    if (
      !slot
      || !isUtf16Boundary(slot.text, span.fromOffset)
      || !isUtf16Boundary(slot.text, span.toOffset)
      || span.toOffset < span.fromOffset
    ) return null;
    quoteParts.push(slot.text.slice(span.fromOffset, span.toOffset));
  }
  const rebuiltQuote = quoteParts.join("\n");
  if (sameRange) {
    // Imported cross-field comments can intentionally retain a source quote whose
    // segmentation is not byte-for-byte identical to joining every Pro field. An
    // unchanged live range must never rewrite that durable TextQuote. When the
    // quote does match, however, refreshing changed context is safe and improves
    // the next relocation pass without sending a redundant `quote` field.
    if (rebuiltQuote !== comment.quote) {
      const sameStoredField = stored.start_scene_id === stored.end_scene_id
        && stored.start_field === stored.end_field;
      // Same-field quotes are canonical Pro field slices. Native cross-field
      // drafts are canonical too; imported cross-field quotes may preserve finer
      // source segmentation, identified by their non-empty provenance id.
      const mayRefreshQuote = sameStoredField || !comment.source_id;
      if (mayRefreshQuote && rebuiltQuote && !hasUnpairedSurrogate(rebuiltQuote)) {
        return { anchor: nextAnchor, quote: rebuiltQuote };
      }
      return null;
    }
    if (stored.prefix !== nextAnchor.prefix || stored.suffix !== nextAnchor.suffix) {
      return { anchor: nextAnchor };
    }
    return null;
  }
  const quote = rebuiltQuote;
  if (!quote || hasUnpairedSurrogate(quote)) return null;
  return { anchor: nextAnchor, quote };
}

/** The first live span, useful for navigation and popover positioning. */
export function locateComment(
  comment: InlineCommentDTO,
  scenes: readonly SceneDTO[],
): CommentSpan | null {
  return commentSpans(comment, scenes)[0] ?? null;
}

/** Resolve every thread into paintable field-local spans. */
export function reconcileCommentSpans(
  comments: readonly InlineCommentDTO[],
  scenes: readonly SceneDTO[],
): CommentSpan[] {
  return comments.flatMap((comment) => commentSpans(comment, scenes));
}

/**
 * Threads whose quote and usable context have genuinely disappeared. An empty
 * scene list is treated as a loading/document-switch transient, never as proof
 * that every comment should be deleted.
 */
export function findOrphanedCommentIds(
  comments: readonly InlineCommentDTO[],
  scenes: readonly SceneDTO[],
): number[] {
  if (!scenes.length) return [];
  return comments
    .filter((comment) => commentSpans(comment, scenes).length === 0)
    .map((comment) => comment.id);
}
