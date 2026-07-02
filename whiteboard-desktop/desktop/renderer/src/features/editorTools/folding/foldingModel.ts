/**
 * Foldable-block detection (pure, testable).
 *
 * Folding is VISUAL ONLY — it never edits the document. This model finds the
 * foldable regions; the editor-tools extension hides a region's body blocks
 * (via a decoration class) when its head index is in the folded set, so the
 * hidden text always stays in the document and is saved/restored normally.
 *
 * Regions (all modes): heading blocks (heading nodes, or `#`/`##`/`###` text)
 * fold everything until the next heading of equal-or-higher rank.
 * Screenplay also folds multi-block Notes (`[[ … ]]`) and boneyard (`/* … *​/`).
 */

import type { FountainBlock } from '../../screenplay/fountainTypes';

export type FoldKind = 'heading' | 'note' | 'boneyard';

export interface FoldRegion {
  /** Block index the writer toggles (heading / note-open / boneyard-open). */
  head: number;
  /** Inclusive index of the last block belonging to the region. */
  end: number;
  kind: FoldKind;
  /** Heading depth (1–6); 0 for note/boneyard. */
  level: number;
}

/** Heading depth for a block: heading-node level, or leading `#` count, else 0. */
export function headingLevel(b: FountainBlock): number {
  if (b.isHeading) return b.level ?? 1;
  const m = b.text.trim().match(/^(#{1,6})\s/);
  return m ? m[1].length : 0;
}

function scanWrapped(
  blocks: FountainBlock[],
  open: string,
  close: string,
  kind: FoldKind,
): FoldRegion[] {
  const out: FoldRegion[] = [];
  let i = 0;
  while (i < blocks.length) {
    const t = blocks[i].text;
    const o = t.indexOf(open);
    // Opens on this block but does NOT close on the same block → spans blocks.
    if (o !== -1 && t.indexOf(close, o + open.length) === -1) {
      let j = i + 1;
      while (j < blocks.length && !blocks[j].text.includes(close)) j += 1;
      if (j < blocks.length) {
        out.push({ head: i, end: j, kind, level: 0 });
        i = j + 1;
        continue;
      }
    }
    i += 1;
  }
  return out;
}

export function findFoldableRegions(blocks: FountainBlock[], mode: string): FoldRegion[] {
  const regions: FoldRegion[] = [];

  // 1. Heading-based regions (every mode).
  for (let i = 0; i < blocks.length; i += 1) {
    const level = headingLevel(blocks[i]);
    if (level === 0) continue;
    let end = i;
    for (let j = i + 1; j < blocks.length; j += 1) {
      const jl = headingLevel(blocks[j]);
      if (jl !== 0 && jl <= level) break; // a sibling/ancestor heading closes it
      end = j;
    }
    if (end > i) regions.push({ head: i, end, kind: 'heading', level });
  }

  // 2. Screenplay: multi-block Notes + boneyard.
  if (mode === 'screenplay') {
    regions.push(...scanWrapped(blocks, '[[', ']]', 'note'));
    regions.push(...scanWrapped(blocks, '/*', '*/', 'boneyard'));
  }

  return regions;
}

/** Block indices hidden when the given heads are collapsed. */
export function hiddenBlocks(regions: FoldRegion[], folded: ReadonlySet<number>): Set<number> {
  const hidden = new Set<number>();
  for (const r of regions) {
    if (!folded.has(r.head)) continue;
    for (let i = r.head + 1; i <= r.end; i += 1) hidden.add(i);
  }
  return hidden;
}

/** Is a block index a foldable region head? */
export function isFoldHead(regions: FoldRegion[], index: number): boolean {
  return regions.some((r) => r.head === index);
}
