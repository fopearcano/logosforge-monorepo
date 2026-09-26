export interface TitleCommentHighlight {
  commentId: number;
  fromOffset: number;
  toOffset: number;
  resolved: boolean;
}

export interface TitleCommentTextToken {
  kind: "text";
  fromOffset: number;
  toOffset: number;
  text: string;
  commentIds: number[];
  resolved: boolean;
}

export interface TitleCommentPointToken {
  kind: "point";
  fromOffset: number;
  toOffset: number;
  text: "";
  commentIds: number[];
  resolved: boolean;
}

export type TitleCommentOverlayToken = TitleCommentTextToken | TitleCommentPointToken;

interface NormalizedHighlight extends TitleCommentHighlight {
  fromOffset: number;
  toOffset: number;
}

const clampOffset = (offset: number, length: number): number => {
  if (!Number.isFinite(offset)) return 0;
  return Math.min(length, Math.max(0, Math.trunc(offset)));
};

/**
 * Return the painted title threads under a collapsed native-input caret.
 * Interior hits win. At an exact edge (where a browser caret has no visual
 * affinity) include every touching mark so adjacent/overlapping threads remain
 * reachable instead of guessing which side of the glyph the user intended.
 */
export function titleCommentIdsAtOffset(
  highlights: readonly TitleCommentHighlight[],
  offset: number,
): number[] {
  if (!Number.isFinite(offset)) return [];
  const caret = Math.trunc(offset);
  const valid = highlights.filter((highlight) => (
    Number.isInteger(highlight.commentId)
    && Number.isFinite(highlight.fromOffset)
    && Number.isFinite(highlight.toOffset)
    && highlight.toOffset >= highlight.fromOffset
  ));
  const interior = valid.filter((highlight) => (
    highlight.fromOffset === highlight.toOffset
      ? highlight.fromOffset === caret
      : highlight.fromOffset < caret && caret < highlight.toOffset
  ));
  const matches = interior.length ? interior : valid.filter((highlight) => (
    highlight.fromOffset <= caret && caret <= highlight.toOffset
  ));
  return [...new Set(matches.map((highlight) => highlight.commentId))]
    .sort((left, right) => left - right);
}

const commentState = (
  highlights: readonly NormalizedHighlight[],
): Pick<TitleCommentTextToken, "commentIds" | "resolved"> => {
  const byId = new Map<number, boolean>();
  for (const highlight of highlights) {
    const previous = byId.get(highlight.commentId);
    byId.set(highlight.commentId, previous == null ? highlight.resolved : previous && highlight.resolved);
  }
  const entries = [...byId.entries()].sort(([left], [right]) => left - right);
  return {
    commentIds: entries.map(([id]) => id),
    resolved: entries.length > 0 && entries.every(([, resolved]) => resolved),
  };
};

/**
 * Split a scene title into visual runs without converting its coordinates.
 *
 * Browser input selection offsets, the core comment API, and JavaScript string
 * slicing all use UTF-16 code units. Keeping that coordinate system here means a
 * valid emoji range (for example 6..8 around a surrogate pair) remains exact.
 * The core validates that persisted offsets do not split a surrogate pair; this
 * renderer only clamps stale/out-of-bounds values so it cannot damage editing.
 */
export function buildTitleCommentOverlayTokens(
  value: string,
  highlights: readonly TitleCommentHighlight[],
): TitleCommentOverlayToken[] {
  const normalized = highlights
    .filter((highlight) => (
      Number.isInteger(highlight.commentId)
      && Number.isFinite(highlight.fromOffset)
      && Number.isFinite(highlight.toOffset)
    ))
    .map((highlight): NormalizedHighlight => ({
      ...highlight,
      fromOffset: clampOffset(highlight.fromOffset, value.length),
      toOffset: clampOffset(highlight.toOffset, value.length),
    }))
    .filter((highlight) => highlight.toOffset >= highlight.fromOffset);

  const ranges = normalized.filter((highlight) => highlight.toOffset > highlight.fromOffset);
  const points = normalized.filter((highlight) => highlight.toOffset === highlight.fromOffset);
  const boundaries = new Set<number>([0, value.length]);
  for (const highlight of normalized) {
    boundaries.add(highlight.fromOffset);
    boundaries.add(highlight.toOffset);
  }
  const offsets = [...boundaries].sort((left, right) => left - right);
  const tokens: TitleCommentOverlayToken[] = [];

  const appendPoints = (offset: number) => {
    const active = points.filter((highlight) => highlight.fromOffset === offset);
    if (!active.length) return;
    tokens.push({
      kind: "point",
      fromOffset: offset,
      toOffset: offset,
      text: "",
      ...commentState(active),
    });
  };

  for (let index = 0; index < offsets.length - 1; index += 1) {
    const fromOffset = offsets[index]!;
    const toOffset = offsets[index + 1]!;
    appendPoints(fromOffset);
    if (toOffset <= fromOffset) continue;
    const active = ranges.filter((highlight) => (
      highlight.fromOffset < toOffset && highlight.toOffset > fromOffset
    ));
    tokens.push({
      kind: "text",
      fromOffset,
      toOffset,
      text: value.slice(fromOffset, toOffset),
      ...commentState(active),
    });
  }
  appendPoints(value.length);

  return tokens;
}
