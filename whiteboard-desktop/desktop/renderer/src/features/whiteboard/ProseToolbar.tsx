/** Compact prose toolbar (Novel / Graphic Novel / Stage): a block Format menu
 *  (heading levels ↔ body) + view scale. The prose-mode counterpart to the
 *  Screenplay toolbar's Format menu, which is Fountain-specific. */

import type { Editor } from '@tiptap/react';

import { Popover } from '../../components/Popover';
import { scaleToPct, type ScaleAction } from './editorScale';

interface Props {
  editor: Editor | null;
  scale: number;
  onScale: (action: ScaleAction) => void;
}

type Level = 0 | 1 | 2 | 3;

const BLOCKS: { label: string; hint: string; level: Level }[] = [
  { label: 'Title', hint: 'H1', level: 1 },
  { label: 'Heading', hint: 'H2', level: 2 },
  { label: 'Subheading', hint: 'H3', level: 3 },
  { label: 'Body text', hint: '¶', level: 0 },
];

export function ProseToolbar({ editor, scale, onScale }: Props) {
  const setBlock = (level: Level, close: () => void) => {
    if (editor) {
      const chain = editor.chain().focus();
      if (level === 0) chain.setParagraph().run();
      else chain.setHeading({ level }).run();
    }
    close();
  };
  const isActive = (level: Level) =>
    !!editor && (level === 0 ? editor.isActive('paragraph') : editor.isActive('heading', { level }));

  return (
    <div className="wb-toolbar" role="toolbar" aria-label="Prose tools">
      <Popover label="Format ▾" title="Format">
        {(close) => (
          <div className="wb-menu">
            {BLOCKS.map((b) => (
              <button
                key={b.label}
                type="button"
                className={`wb-menu-item${isActive(b.level) ? ' is-active' : ''}`}
                disabled={!editor}
                onClick={() => setBlock(b.level, close)}
              >
                {b.label}
                <span className="wb-menu-soon"> · {b.hint}</span>
              </button>
            ))}
          </div>
        )}
      </Popover>

      <span className="wb-tool-group" aria-label="View scale">
        <button type="button" className="wb-tool" title="Smaller (Ctrl/Cmd+-)" onClick={() => onScale('smaller')}>
          −
        </button>
        <button
          type="button"
          className="wb-tool wb-scale-pct"
          title="Actual size (Ctrl/Cmd+0)"
          onClick={() => onScale('actual')}
        >
          {scaleToPct(scale)}%
        </button>
        <button type="button" className="wb-tool" title="Bigger (Ctrl/Cmd+=)" onClick={() => onScale('bigger')}>
          +
        </button>
      </span>
    </div>
  );
}
