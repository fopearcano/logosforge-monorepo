/** Stable manuscript-block identities for outline links and future anchors. */

import { Extension } from '@tiptap/core';
import { Plugin, PluginKey } from '@tiptap/pm/state';

let fallbackCounter = 0;

export function newBlockId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `block-${crypto.randomUUID()}`;
  }
  fallbackCounter += 1;
  return `block-${Date.now().toString(36)}-${fallbackCounter.toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function cleanId(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

/** Preserve valid first occurrences and replace blank/duplicate ids. */
export function normalizeBlockIds(values: unknown[]): string[] {
  const seen = new Set<string>();
  return values.map((value) => {
    let id = cleanId(value);
    if (!id || seen.has(id)) id = newBlockId();
    seen.add(id);
    return id;
  });
}

/** Assign a wholly new identity set when replacing content from a text file. */
export function freshBlockIds(count: number): string[] {
  return Array.from({ length: Math.max(0, count) }, () => newBlockId());
}

export interface IdentityCandidate {
  text: string;
  position: number;
}

/** Pick which duplicate retains the old id after split/paste. */
export function chooseIdentityKeeper(
  oldText: string,
  expectedPosition: number,
  candidates: IdentityCandidate[],
): number {
  let best = 0;
  let bestScore = -Infinity;
  candidates.forEach((candidate, index) => {
    const text = candidate.text;
    let score = -Math.abs(candidate.position - expectedPosition);
    if (text === oldText) score += 1_000_000;
    else {
      // A split-in-the-middle keeps the id on the first (prefix) half. A split
      // at the very start gives the unchanged text to the second half, whose
      // exact-match score above correctly wins over the new empty paragraph.
      if (text && oldText.startsWith(text)) score += 100_000 + text.length;
      if (text && oldText.endsWith(text)) score += 50_000 + text.length;
    }
    if (score > bestScore) {
      best = index;
      bestScore = score;
    }
  });
  return best;
}

const key = new PluginKey('logosforgeBlockIdentity');

/**
 * Adds `lfId` to every top-level paragraph/heading and repairs ids after insert,
 * paste, split, or duplicate. The attribute travels with the ProseMirror node,
 * so inserting content above a block no longer changes that block's identity.
 */
export const BlockIdentity = Extension.create({
  name: 'blockIdentity',

  addGlobalAttributes() {
    return [
      {
        types: ['paragraph', 'heading'],
        attributes: {
          lfId: {
            default: null,
            parseHTML: (element: HTMLElement) => element.getAttribute('data-lf-block-id'),
            renderHTML: (attributes: Record<string, unknown>) => {
              const id = cleanId(attributes.lfId);
              return id ? { 'data-lf-block-id': id } : {};
            },
          },
        },
      },
    ];
  },

  addProseMirrorPlugins() {
    return [
      new Plugin({
        key,
        appendTransaction(transactions, oldState, newState) {
          if (!transactions.some((transaction) => transaction.docChanged)) return null;
          const oldById = new Map<string, {
            text: string;
            expectedPosition: number;
            searchRadius: number;
          }>();
          oldState.doc.forEach((node, offset) => {
            const id = cleanId(node.attrs.lfId);
            if (!id) return;
            let expectedPosition = offset;
            for (const transaction of transactions) {
              expectedPosition = transaction.mapping.map(expectedPosition, 1);
            }
            oldById.set(id, {
              text: node.textContent,
              expectedPosition,
              searchRadius: Math.max(4, node.nodeSize + 2),
            });
          });

          const records: Array<{
            node: typeof newState.doc;
            offset: number;
            originalId: string;
            desiredId: string;
            claimed: boolean;
          }> = [];
          newState.doc.forEach((node, offset) => {
            if (node.type.name !== 'paragraph' && node.type.name !== 'heading') return;
            const id = cleanId(node.attrs.lfId);
            records.push({ node, offset, originalId: id, desiredId: id, claimed: false });
          });

          // Reconcile every old identity against both its current holder(s) and
          // nearby id-less nodes. splitBlock gives the old attrs to the first
          // half and no id to the second; at a split-at-start, the second half is
          // the one that retains all original text and must inherit the id.
          for (const [id, old] of oldById) {
            const candidates = records.filter((record) =>
              record.desiredId === id ||
              (!record.desiredId && !record.claimed &&
                Math.abs(record.offset - old.expectedPosition) <= old.searchRadius),
            );
            if (!candidates.length) continue;
            const keeperIndex = chooseIdentityKeeper(
              old.text,
              old.expectedPosition,
              candidates.map((record) => ({
                text: record.node.textContent,
                position: record.offset,
              })),
            );
            candidates.forEach((record, index) => {
              if (index === keeperIndex) {
                record.desiredId = id;
                record.claimed = true;
              } else if (record.desiredId === id) {
                record.desiredId = newBlockId();
              }
            });
          }

          // Finish with a global uniqueness pass for ordinary inserts and pasted
          // HTML carrying an id that never belonged to this document.
          const seen = new Set<string>();
          for (const record of records) {
            if (!record.desiredId || seen.has(record.desiredId)) record.desiredId = newBlockId();
            seen.add(record.desiredId);
          }

          const tr = newState.tr;
          let changed = false;
          for (const record of records) {
            if (record.desiredId === record.originalId) continue;
            tr.setNodeMarkup(record.offset, undefined, {
              ...record.node.attrs,
              lfId: record.desiredId,
            });
            changed = true;
          }
          return changed ? tr : null;
        },
      }),
    ];
  },
});
