/**
 * Editor Settings — a small, minimal popover for the optional Nerd Mode aids.
 * Available in every mode (line numbers / syntax work in prose too). This is NOT
 * the full Pro preferences system; it just toggles the editor view tools and a
 * few typography overrides, all of which default to off / mode-default.
 */

import { Popover } from '../../components/Popover';
import {
  FONT_SIZE_MAX,
  FONT_SIZE_MIN,
  LINE_HEIGHT_MAX,
  LINE_HEIGHT_MIN,
  type EditorLayout,
  type EditorTypeface,
} from './editorToolTypes';
import type { EditorToolsApi } from './useEditorTools';

interface Props {
  api: EditorToolsApi;
  /** Resets the editor view (tools + typography) and clears folds. */
  onReset: () => void;
}

const TYPEFACES: { value: EditorTypeface; label: string }[] = [
  { value: 'default', label: 'Mode default' },
  { value: 'serif', label: 'Serif' },
  { value: 'mono', label: 'Monospace' },
  { value: 'system', label: 'System' },
];

const FONT_SIZES = [13, 14, 15, 16, 17, 18, 20, 22, 24].filter(
  (n) => n >= FONT_SIZE_MIN && n <= FONT_SIZE_MAX,
);
const LINE_HEIGHTS = [1.3, 1.5, 1.7, 1.9, 2.1].filter(
  (n) => n >= LINE_HEIGHT_MIN && n <= LINE_HEIGHT_MAX,
);

export function EditorSettingsPopover({ api, onReset }: Props) {
  const { tools, update, toggle } = api;

  return (
    <Popover label="Editor" title="Editor Settings" align="right">
      {() => (
        <div className="wb-settings">
          <h3 className="wb-settings-title">Editor View</h3>

          <label className="wb-field wb-field-check">
            <input type="checkbox" checked={tools.lineNumbers} onChange={() => toggle('lineNumbers')} />
            <span>
              Show line numbers <kbd>⌘/Ctrl L</kbd>
            </span>
          </label>

          <label className="wb-field wb-field-check">
            <input
              type="checkbox"
              checked={tools.currentLineHighlight}
              onChange={() => toggle('currentLineHighlight')}
            />
            <span>Highlight current line</span>
          </label>

          <label className="wb-field wb-field-check">
            <input type="checkbox" checked={tools.folding} onChange={() => toggle('folding')} />
            <span>
              Enable folding <kbd>⌘/Ctrl ⇧ F</kbd>
            </span>
          </label>

          <label className="wb-field wb-field-check">
            <input type="checkbox" checked={tools.syntax} onChange={() => toggle('syntax')} />
            <span>
              Colour-code text <kbd>⌘/Ctrl ⇧ H</kbd>
            </span>
          </label>
          <p className="wb-field-hint">
            Off = plain black-and-white. Colours follow your theme (headings, dialogue, tags).
          </p>

          <label className="wb-field">
            <span>Font size</span>
            <select
              value={tools.fontSize ?? ''}
              onChange={(e) => update('fontSize', e.target.value === '' ? null : Number(e.target.value))}
            >
              <option value="">Default</option>
              {FONT_SIZES.map((n) => (
                <option key={n} value={n}>
                  {n}px
                </option>
              ))}
            </select>
          </label>

          <label className="wb-field">
            <span>Line height</span>
            <select
              value={tools.lineHeight ?? ''}
              onChange={(e) => update('lineHeight', e.target.value === '' ? null : Number(e.target.value))}
            >
              <option value="">Default</option>
              {LINE_HEIGHTS.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>

          <label className="wb-field">
            <span>Typeface</span>
            <select value={tools.typeface} onChange={(e) => update('typeface', e.target.value as EditorTypeface)}>
              {TYPEFACES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>

          <label className="wb-field">
            <span>Layout</span>
            <select value={tools.layout} onChange={(e) => update('layout', e.target.value as EditorLayout)}>
              <option value="flow">Continuous</option>
              <option value="paged">Pages</option>
            </select>
          </label>
          <p className="wb-field-hint">
            Pages frames your manuscript as a page sheet with page-break guides, instead of one
            continuous scroll.
          </p>

          <button type="button" className="wb-reset" onClick={onReset}>
            Reset editor view
          </button>
        </div>
      )}
    </Popover>
  );
}
