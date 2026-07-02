/**
 * Real bold/italic for prose modes (Novel / Graphic Novel / Stage).
 *
 * StarterKit's own bold/italic are kept DISABLED because their `**`/`*` input
 * rules would fight the Screenplay's Fountain markers. Instead we register minimal
 * marks here — schema + render only, NO input rules and NO keymap. Toggling is
 * driven from the screenplay keyboard (Mod-b/i → toggleMark in prose); Screenplay
 * keeps inserting literal Fountain `**`/`*`. Marks persist via each block's
 * `marks` field (char offsets into the plain text), so the block contract stays
 * plain-text for the classifier / outline / AI / exports.
 */

import { Mark } from '@tiptap/core';

import type { InlineMark } from './types';

export const Bold = Mark.create({
  name: 'bold',
  parseHTML() {
    return [{ tag: 'strong' }, { tag: 'b' }];
  },
  renderHTML() {
    return ['strong', 0];
  },
});

export const Italic = Mark.create({
  name: 'italic',
  parseHTML() {
    return [{ tag: 'em' }, { tag: 'i' }];
  },
  renderHTML() {
    return ['em', 0];
  },
});

interface InlineNode {
  type: 'text';
  text: string;
  marks?: { type: string }[];
}

/** ProseMirror inline content for a block's text + its bold/italic marks. */
export function inlineFromText(text: string, marks?: InlineMark[] | null): InlineNode[] {
  if (!text) return [];
  const ms = (marks ?? []).filter((m) => m.to > m.from);
  if (!ms.length) return [{ type: 'text', text }];
  const cuts = new Set<number>([0, text.length]);
  for (const m of ms) {
    if (m.from > 0 && m.from < text.length) cuts.add(m.from);
    if (m.to > 0 && m.to < text.length) cuts.add(m.to);
  }
  const points = [...cuts].sort((a, b) => a - b);
  const out: InlineNode[] = [];
  for (let i = 0; i < points.length - 1; i++) {
    const from = points[i];
    const to = points[i + 1];
    if (to <= from) continue;
    const seg = ms.filter((m) => m.from <= from && m.to >= to).map((m) => ({ type: m.type }));
    out.push(
      seg.length
        ? { type: 'text', text: text.slice(from, to), marks: seg }
        : { type: 'text', text: text.slice(from, to) },
    );
  }
  return out;
}

/** Plain text + merged bold/italic marks (char offsets) extracted from a PM node. */
export function textAndMarks(node: unknown): { text: string; marks?: InlineMark[] } {
  let text = '';
  const raw: InlineMark[] = [];
  const walk = (n: any) => {
    if (n?.type === 'text' && typeof n.text === 'string') {
      const from = text.length;
      text += n.text;
      for (const mk of n.marks ?? []) {
        if (mk.type === 'bold' || mk.type === 'italic') {
          raw.push({ type: mk.type, from, to: text.length });
        }
      }
    } else if (Array.isArray(n?.content)) {
      n.content.forEach(walk);
    }
  };
  const root = node as { content?: unknown[] };
  if (Array.isArray(root?.content)) root.content.forEach(walk);
  if (!raw.length) return { text };
  const byType: Record<string, InlineMark[]> = {};
  for (const m of raw) (byType[m.type] ??= []).push(m);
  const merged: InlineMark[] = [];
  for (const type of Object.keys(byType)) {
    const sorted = byType[type].sort((a, b) => a.from - b.from);
    let cur: InlineMark | null = null;
    for (const m of sorted) {
      if (cur && m.from <= cur.to) cur.to = Math.max(cur.to, m.to);
      else {
        cur = { type: m.type, from: m.from, to: m.to };
        merged.push(cur);
      }
    }
  }
  return { text, marks: merged };
}
