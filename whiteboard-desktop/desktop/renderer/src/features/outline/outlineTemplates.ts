/**
 * Writing-method structure templates for the outline.
 *
 * Each template is a small tree of typed nodes (act / beat / …) describing a
 * well-known story structure. Applying one instantiates fresh nodes (new ids +
 * timestamps) that slot into the outline — either appended after the existing
 * top level or replacing the whole outline. Pure + data-only; no React/DOM.
 */

import { childrenOf, createNode, type OutlineItemType, type OutlineNode } from './outlineModel';

export interface TemplateNode {
  type: OutlineItemType;
  title: string;
  children?: TemplateNode[];
}

export interface OutlineTemplate {
  id: string;
  name: string;
  /** One-line summary shown in the picker. */
  description: string;
  nodes: TemplateNode[];
}

// --- helpers ---------------------------------------------------------------

const act = (title: string, children?: TemplateNode[]): TemplateNode => ({ type: 'act', title, children });
const beat = (title: string): TemplateNode => ({ type: 'beat', title });

/** Total node count (for the "N items" hint in the picker). */
export function countTemplateNodes(tpl: OutlineTemplate): number {
  const count = (ns: TemplateNode[]): number =>
    ns.reduce((s, n) => s + 1 + (n.children ? count(n.children) : 0), 0);
  return count(tpl.nodes);
}

/**
 * Build the flat OutlineNode list for `tpl`, ready to be merged with `[...items,
 * ...result]`. New roots are ordered after the existing children of `parentId`
 * (null = top level); every node gets a fresh id from `makeId`. Pure.
 */
export function instantiateTemplate(
  items: OutlineNode[],
  tpl: OutlineTemplate,
  makeId: () => string,
  now: string,
  parentId: string | null = null,
): OutlineNode[] {
  const out: OutlineNode[] = [];
  const baseOrder = childrenOf(items, parentId).reduce((m, n) => Math.max(m, n.order), -1) + 1;
  const walk = (tnodes: TemplateNode[], pId: string | null, startOrder: number) => {
    tnodes.forEach((t, i) => {
      const id = makeId();
      out.push({ ...createNode(id, t.type, pId, now), title: t.title, order: startOrder + i });
      if (t.children && t.children.length) walk(t.children, id, 0);
    });
  };
  walk(tpl.nodes, parentId, baseOrder);
  return out;
}

// --- the templates ---------------------------------------------------------

export const OUTLINE_TEMPLATES: OutlineTemplate[] = [
  {
    id: 'three-act',
    name: 'Three-Act Structure',
    description: 'The classic Setup · Confrontation · Resolution spine.',
    nodes: [
      act('Act I — Setup', [
        beat('Opening / Hook'),
        beat('Inciting Incident'),
        beat('Plot Point 1 — into Act II'),
      ]),
      act('Act II — Confrontation', [
        beat('Rising Action'),
        beat('Midpoint'),
        beat('Plot Point 2 — into Act III'),
      ]),
      act('Act III — Resolution', [
        beat('Climax'),
        beat('Falling Action'),
        beat('Resolution'),
      ]),
    ],
  },
  {
    id: 'save-the-cat',
    name: 'Save the Cat! Beat Sheet',
    description: "Blake Snyder's 15 beats, grouped into three acts.",
    nodes: [
      act('Act 1', [
        beat('Opening Image'),
        beat('Theme Stated'),
        beat('Set-Up'),
        beat('Catalyst'),
        beat('Debate'),
      ]),
      act('Act 2', [
        beat('Break into Two'),
        beat('B Story'),
        beat('Fun and Games'),
        beat('Midpoint'),
        beat('Bad Guys Close In'),
        beat('All Is Lost'),
        beat('Dark Night of the Soul'),
      ]),
      act('Act 3', [
        beat('Break into Three'),
        beat('Finale'),
        beat('Final Image'),
      ]),
    ],
  },
  {
    id: 'heros-journey',
    name: "The Hero's Journey",
    description: "Campbell / Vogler's 12 stages across Departure · Initiation · Return.",
    nodes: [
      act('Act I — Departure', [
        beat('Ordinary World'),
        beat('Call to Adventure'),
        beat('Refusal of the Call'),
        beat('Meeting the Mentor'),
        beat('Crossing the Threshold'),
      ]),
      act('Act II — Initiation', [
        beat('Tests, Allies, Enemies'),
        beat('Approach to the Inmost Cave'),
        beat('The Ordeal'),
        beat('The Reward'),
      ]),
      act('Act III — Return', [
        beat('The Road Back'),
        beat('Resurrection'),
        beat('Return with the Elixir'),
      ]),
    ],
  },
  {
    id: 'story-circle',
    name: 'Story Circle',
    description: "Dan Harmon's 8-step character arc.",
    nodes: [
      act('Story Circle', [
        beat('1. You — a character in their comfort zone'),
        beat('2. Need — but they want something'),
        beat('3. Go — they enter an unfamiliar situation'),
        beat('4. Search — and adapt to it'),
        beat('5. Find — getting what they wanted'),
        beat('6. Take — paying a heavy price'),
        beat('7. Return — to their familiar situation'),
        beat('8. Change — having changed'),
      ]),
    ],
  },
  {
    id: 'seven-point',
    name: 'Seven-Point Structure',
    description: "Dan Wells' hook-to-resolution skeleton, built from the ends in.",
    nodes: [
      act('Seven-Point Structure', [
        beat('Hook'),
        beat('Plot Turn 1'),
        beat('Pinch Point 1'),
        beat('Midpoint'),
        beat('Pinch Point 2'),
        beat('Plot Turn 2'),
        beat('Resolution'),
      ]),
    ],
  },
  {
    id: 'freytag',
    name: "Freytag's Pyramid",
    description: 'The five dramatic phases of classical tragedy.',
    nodes: [
      act('Exposition'),
      act('Rising Action'),
      act('Climax'),
      act('Falling Action'),
      act('Dénouement'),
    ],
  },
  {
    id: 'kishotenketsu',
    name: 'Kishōtenketsu',
    description: 'Four-act East-Asian structure — no central conflict required.',
    nodes: [
      act('Ki — Introduction'),
      act('Shō — Development'),
      act('Ten — Twist'),
      act('Ketsu — Conclusion'),
    ],
  },
];
