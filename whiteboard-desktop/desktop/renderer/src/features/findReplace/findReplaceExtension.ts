/** Non-destructive Find & Replace highlights for the TipTap writing surface. */

import { Extension } from '@tiptap/core';
import type { Node as ProseMirrorNode } from '@tiptap/pm/model';
import { Plugin, PluginKey, type Transaction } from '@tiptap/pm/state';
import { Decoration, DecorationSet } from '@tiptap/pm/view';

import type { FindMatch } from './findReplaceModel';

export interface FindReplaceDecorationMeta {
  matches: readonly FindMatch[];
  activeIndex: number | null;
  /** Index of matches[0] in the complete result set (for diagnostics/a11y). */
  matchIndexOffset: number;
}

export interface FindReplaceDecorationState {
  decorations: DecorationSet;
}

export const findReplaceKey = new PluginKey<FindReplaceDecorationState>('findReplace');
export const FIND_REPLACE_DECORATION_LIMIT = 500;

/**
 * Build a bounded highlight payload around the current result.
 *
 * Search/count/replacement retain the complete result list in React. Only the
 * DOM decorations are windowed: a one-character query in a novel can otherwise
 * create tens of thousands of inline spans and stall the editor.
 */
export function findReplaceMeta(
  matches: readonly FindMatch[],
  activeIndex: number | null,
): FindReplaceDecorationMeta {
  const normalizedActive = activeIndex !== null
    && activeIndex >= 0
    && activeIndex < matches.length
    ? activeIndex
    : null;
  if (matches.length <= FIND_REPLACE_DECORATION_LIMIT) {
    return { matches: [...matches], activeIndex: normalizedActive, matchIndexOffset: 0 };
  }

  const maximumStart = matches.length - FIND_REPLACE_DECORATION_LIMIT;
  const desiredStart = normalizedActive === null
    ? 0
    : normalizedActive - Math.floor(FIND_REPLACE_DECORATION_LIMIT / 2);
  const start = Math.max(0, Math.min(desiredStart, maximumStart));
  return {
    matches: matches.slice(start, start + FIND_REPLACE_DECORATION_LIMIT),
    activeIndex: normalizedActive === null ? null : normalizedActive - start,
    matchIndexOffset: start,
  };
}

function isInlineRange(doc: ProseMirrorNode, from: number, to: number): boolean {
  if (!Number.isInteger(from) || !Number.isInteger(to) || from < 0 || to <= from || to > doc.content.size) {
    return false;
  }
  try {
    const $from = doc.resolve(from);
    const $to = doc.resolve(to);
    return $from.parent === $to.parent && $from.parent.isTextblock;
  } catch {
    return false;
  }
}

/** Exported for focused headless tests and deterministic decoration inspection. */
export function buildFindReplaceDecorations(
  doc: ProseMirrorNode,
  meta: FindReplaceDecorationMeta,
): DecorationSet {
  if (!meta.matches.length) return DecorationSet.empty;

  const decorations: Decoration[] = [];
  meta.matches.forEach((match, index) => {
    if (!isInlineRange(doc, match.from, match.to)) return;
    const current = index === meta.activeIndex;
    decorations.push(
      Decoration.inline(
        match.from,
        match.to,
        {
          class: current ? 'wb-find-match wb-find-match-current' : 'wb-find-match',
          'data-find-match': String(meta.matchIndexOffset + index + 1),
          ...(current ? { 'data-find-match-current': 'true' } : {}),
        },
        {
          findMatchIndex: index,
          findMatchCurrent: current,
          inclusiveStart: false,
          inclusiveEnd: false,
        },
      ),
    );
  });
  return DecorationSet.create(doc, decorations);
}

export function emptyFindReplaceDecorationState(): FindReplaceDecorationState {
  return { decorations: DecorationSet.empty };
}

/**
 * Apply explicit result metadata, or map existing highlights through an editor
 * change until the React controller publishes its freshly recomputed results.
 */
export function applyFindReplaceDecorationState(
  transaction: Transaction,
  value: FindReplaceDecorationState,
): FindReplaceDecorationState {
  const meta = transaction.getMeta(findReplaceKey) as FindReplaceDecorationMeta | undefined;
  if (meta) return { decorations: buildFindReplaceDecorations(transaction.doc, meta) };
  if (transaction.docChanged) {
    return { decorations: value.decorations.map(transaction.mapping, transaction.doc) };
  }
  return value;
}

export const FindReplaceExtension = Extension.create({
  name: 'findReplace',

  addProseMirrorPlugins() {
    return [
      new Plugin<FindReplaceDecorationState>({
        key: findReplaceKey,
        state: {
          init: emptyFindReplaceDecorationState,
          apply: applyFindReplaceDecorationState,
        },
        props: {
          decorations(state) {
            return findReplaceKey.getState(state)?.decorations ?? null;
          },
        },
      }),
    ];
  },
});
