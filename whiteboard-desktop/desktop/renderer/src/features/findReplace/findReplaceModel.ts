/**
 * Pure Find & Replace model for the Whiteboard writing surface.
 *
 * Search is intentionally literal and scoped to each top-level text block. A
 * query can cross inline mark boundaries (bold/italic do not interrupt a
 * block's `textContent`), but it can never cross a paragraph/heading boundary.
 * That keeps every result a structurally safe ProseMirror replacement range.
 */

import type { Node as ProseMirrorNode } from '@tiptap/pm/model';

export interface FindOptions {
  matchCase: boolean;
  wholeWord: boolean;
}

export const DEFAULT_FIND_OPTIONS: Readonly<FindOptions> = Object.freeze({
  matchCase: false,
  wholeWord: false,
});

/** A top-level text block plus its absolute first-content position. */
export interface FindTextBlock {
  blockIndex: number;
  text: string;
  contentStart: number;
}

/** One non-overlapping literal match, in both block-local and PM positions. */
export interface FindMatch {
  blockIndex: number;
  fromOffset: number;
  toOffset: number;
  from: number;
  to: number;
  text: string;
}

export type FindDirection = 1 | -1;

export interface FindNavigation {
  index: number | null;
  wrapped: boolean;
}

const WORD_CHARACTER = /[\p{L}\p{M}\p{N}\p{Pc}]/u;

function isWordCharacter(value: string | undefined): boolean {
  return Boolean(value && WORD_CHARACTER.test(value));
}

function precedingCodePoint(value: string, offset: number): string | undefined {
  if (offset <= 0) return undefined;
  const finalUnit = value.charCodeAt(offset - 1);
  const startsWithSurrogatePair = finalUnit >= 0xdc00
    && finalUnit <= 0xdfff
    && offset >= 2
    && value.charCodeAt(offset - 2) >= 0xd800
    && value.charCodeAt(offset - 2) <= 0xdbff;
  return value.slice(startsWithSurrogatePair ? offset - 2 : offset - 1, offset);
}

function followingCodePoint(value: string, offset: number): string | undefined {
  if (offset >= value.length) return undefined;
  const point = value.codePointAt(offset);
  return point === undefined ? undefined : String.fromCodePoint(point);
}

function hasWholeWordBoundaries(text: string, from: number, to: number): boolean {
  // Treat Unicode letters, combining marks, numbers, and connector punctuation
  // as word constituents. A whole literal (even one with punctuation at an
  // edge) must not be immediately embedded in either kind of word character.
  return !isWordCharacter(precedingCodePoint(text, from))
    && !isWordCharacter(followingCodePoint(text, to));
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Extract searchable top-level text blocks from a ProseMirror document.
 *
 * Whiteboard's schema contains paragraph/heading textblocks with inline text
 * and marks. Their first text position is the top-level offset + 1, and PM text
 * offsets use the same UTF-16 indexing as JavaScript RegExp match indices.
 */
export function documentSearchBlocks(doc: ProseMirrorNode): FindTextBlock[] {
  const blocks: FindTextBlock[] = [];
  let blockIndex = 0;
  doc.forEach((node, offset) => {
    if (node.isTextblock) {
      blocks.push({ blockIndex, text: node.textContent, contentStart: offset + 1 });
    }
    blockIndex += 1;
  });
  return blocks;
}

/** Find literal, non-overlapping matches in document order. */
export function findMatchesInBlocks(
  blocks: readonly FindTextBlock[],
  query: string,
  options: FindOptions = DEFAULT_FIND_OPTIONS,
): FindMatch[] {
  if (!query || /[\r\n]/.test(query)) return [];

  const flags = options.matchCase ? 'gu' : 'giu';
  const pattern = new RegExp(escapeRegExp(query), flags);
  const matches: FindMatch[] = [];

  for (const block of blocks) {
    // A RegExp instance is stateful under `g`; reset it for every text block.
    pattern.lastIndex = 0;
    let hit: RegExpExecArray | null;
    while ((hit = pattern.exec(block.text)) !== null) {
      const fromOffset = hit.index;
      const toOffset = fromOffset + hit[0].length;
      if (
        (!options.wholeWord || hasWholeWordBoundaries(block.text, fromOffset, toOffset))
        && toOffset > fromOffset
      ) {
        matches.push({
          blockIndex: block.blockIndex,
          fromOffset,
          toOffset,
          from: block.contentStart + fromOffset,
          to: block.contentStart + toOffset,
          text: hit[0],
        });
      }
    }
  }

  return matches;
}

/** Convenience adapter for the active TipTap/ProseMirror document. */
export function findTextMatches(
  doc: ProseMirrorNode,
  query: string,
  options: FindOptions = DEFAULT_FIND_OPTIONS,
): FindMatch[] {
  return findMatchesInBlocks(documentSearchBlocks(doc), query, options);
}

/** Return the result that exactly corresponds to the current editor selection. */
export function matchIndexForRange(
  matches: readonly FindMatch[],
  from: number,
  to: number,
): number | null {
  const index = matches.findIndex((match) => match.from === from && match.to === to);
  return index === -1 ? null : index;
}

/**
 * Choose a result from a document position. Forward search starts at/after the
 * position; backward search ends at/before it. Both directions wrap.
 */
export function matchIndexFromPosition(
  matches: readonly FindMatch[],
  position: number,
  direction: FindDirection,
): FindNavigation {
  if (!matches.length) return { index: null, wrapped: false };

  if (direction === 1) {
    const index = matches.findIndex((match) => match.from >= position);
    return index === -1 ? { index: 0, wrapped: true } : { index, wrapped: false };
  }

  for (let index = matches.length - 1; index >= 0; index -= 1) {
    if (matches[index].to <= position) return { index, wrapped: false };
  }
  return { index: matches.length - 1, wrapped: true };
}

/** Step from the current result, wrapping at either end. */
export function stepMatchIndex(
  matchCount: number,
  currentIndex: number | null,
  direction: FindDirection,
): FindNavigation {
  if (matchCount <= 0) return { index: null, wrapped: false };
  if (currentIndex === null || currentIndex < 0 || currentIndex >= matchCount) {
    return { index: direction === 1 ? 0 : matchCount - 1, wrapped: false };
  }

  const candidate = currentIndex + direction;
  if (candidate >= matchCount) return { index: 0, wrapped: true };
  if (candidate < 0) return { index: matchCount - 1, wrapped: true };
  return { index: candidate, wrapped: false };
}

/**
 * Replacement ranges ordered from the end of the document to the beginning.
 * Applying this plan to one transaction keeps every lower position stable and
 * makes Replace All a single undo/autosave event.
 */
export function descendingReplacementPlan(matches: readonly FindMatch[]): FindMatch[] {
  return [...matches].sort((a, b) => b.from - a.from || b.to - a.to);
}
