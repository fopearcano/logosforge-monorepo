/**
 * Story Map — a thin horizontal strip of nodes below the writing sheet, one per
 * derived outline item (section / scene / synopsis / note). Clicking a node
 * scrolls the editor to that block. Purely a navigation overview; it holds no
 * state and derives everything from the same OutlineItem[] the outline uses.
 *
 * Shape mapping (CSS classes are CD's restyle contract):
 *   section (top level) → wb-sm-actlg (large diamond, anchored/spaced)
 *   section (deeper)    → wb-sm-act   (medium diamond)
 *   scene               → wb-sm-scene (small diamond)
 *   synopsis / note     → wb-sm-beat  (dot)
 */

import type { OutlineItem } from '../outline/types';

export interface StoryMapNode {
  shape: string;
  anchor: boolean;
}

/** Pure: map an outline item to its node shape + whether it anchors a new run. */
export function storyMapNode(item: OutlineItem): StoryMapNode {
  if (item.kind === 'section') {
    const top = (item.level ?? 1) <= 1;
    return { shape: top ? 'wb-sm-actlg' : 'wb-sm-act', anchor: top };
  }
  if (item.kind === 'scene') return { shape: 'wb-sm-scene', anchor: false };
  return { shape: 'wb-sm-beat', anchor: false }; // synopsis, note
}

interface Props {
  items: OutlineItem[];
  /** Block index of the active scene (highlighted), if known. */
  activeIndex?: number | null;
  onNavigate: (blockIndex: number) => void;
}

export function StoryMap({ items, activeIndex, onNavigate }: Props) {
  if (items.length === 0) return null;
  return (
    <div className="wb-storymap" data-screen-label="story-map">
      <div className="wb-storymap-track">
        {items.map((it) => {
          const { shape, anchor } = storyMapNode(it);
          const active = activeIndex != null && it.blockIndex === activeIndex;
          return (
            <button
              key={it.id}
              type="button"
              className={`wb-sm-node${anchor ? ' is-anchor' : ''}${active ? ' is-active' : ''}`}
              title={it.label}
              aria-label={it.label}
              onClick={() => onNavigate(it.blockIndex)}
            >
              <span className={`wb-sm-shape ${shape}`} />
            </button>
          );
        })}
      </div>
    </div>
  );
}
