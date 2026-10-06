/**
 * Editor Settings — a small, minimal popover for the optional Nerd Mode aids.
 * Available in every mode (line numbers / syntax work in prose too). This is NOT
 * the full Pro preferences system; it just toggles the editor view tools and a
 * few typography overrides, all of which default to off / mode-default.
 */

import { useEffect, useState } from 'react';

import { Popover } from '../../components/Popover';
import { useTheme } from '../../styles/themes/useTheme';
import {
  FONT_SIZE_MAX,
  FONT_SIZE_MIN,
  LINE_HEIGHT_MAX,
  LINE_HEIGHT_MIN,
  normalizeSystemFontFamily,
  SYSTEM_FONT_FAMILY_MAX_LENGTH,
  type EditorLayout,
  type EditorTypeface,
} from './editorToolTypes';
import {
  InstalledFontInventoryError,
  queryInstalledFontFamiliesFromUserGesture,
} from './installedFonts';
import type { EditorToolsApi } from './useEditorTools';

interface Props {
  api: EditorToolsApi;
  /** Resets the editor view (tools + typography) and clears folds. */
  onReset: () => void;
}

const TYPEFACE_GROUPS: { label: string; options: { value: EditorTypeface; label: string }[] }[] = [
  { label: 'General', options: [
    { value: 'default', label: 'Mode default' },
    { value: 'installed', label: 'Installed system font…' },
  ] },
  { label: 'Serif', options: [
    { value: 'serif', label: 'Literary · Spectral' },
    { value: 'book', label: 'Book · Palatino' },
    { value: 'classic', label: 'Classic · Georgia' },
    { value: 'transitional', label: 'Transitional · Charter' },
    { value: 'editorial', label: 'Editorial · Didot / Bodoni' },
    { value: 'slab', label: 'Slab · Rockwell' },
  ] },
  { label: 'Sans serif', options: [
    { value: 'sans', label: 'IBM Plex' },
    { value: 'system', label: 'System UI' },
    { value: 'humanist', label: 'Humanist · Optima / Candara' },
    { value: 'geometric', label: 'Geometric · Futura / Avenir' },
    { value: 'rounded', label: 'Rounded · Rounded / Quicksand' },
  ] },
  { label: 'Mono & typewriter', options: [
    { value: 'mono', label: 'Modern mono · IBM Plex' },
    { value: 'coding', label: 'Coding · Cascadia / JetBrains' },
    { value: 'courier-prime', label: 'Screenplay · Courier Prime' },
    { value: 'typewriter', label: 'Vintage typewriter' },
    { value: 'typewriter-modern', label: 'Modern typewriter' },
  ] },
  { label: 'Handwritten', options: [
    { value: 'handwritten', label: 'Print' },
    { value: 'handwritten-casual', label: 'Casual' },
    { value: 'script', label: 'Script' },
    { value: 'chalkboard', label: 'Chalkboard' },
    { value: 'marker', label: 'Marker' },
  ] },
];

const FONT_SIZES = [13, 14, 15, 16, 17, 18, 20, 22, 24].filter(
  (n) => n >= FONT_SIZE_MIN && n <= FONT_SIZE_MAX,
);
const LINE_HEIGHTS = [1.3, 1.5, 1.7, 1.9, 2.1].filter(
  (n) => n >= LINE_HEIGHT_MIN && n <= LINE_HEIGHT_MAX,
);

export function EditorSettingsPopover({ api, onReset }: Props) {
  const { tools, update, toggle } = api;
  const { theme } = useTheme();
  const [systemFontDraft, setSystemFontDraft] = useState(tools.systemFontFamily ?? '');
  const [installedFamilies, setInstalledFamilies] = useState<string[]>([]);
  const [fontInventoryStatus, setFontInventoryStatus] = useState('');
  const [loadingFonts, setLoadingFonts] = useState(false);
  useEffect(() => setSystemFontDraft(tools.systemFontFamily ?? ''), [tools.systemFontFamily]);
  const normalizedSystemFont = normalizeSystemFontFamily(systemFontDraft);
  const systemFontValid = systemFontDraft.trim() === '' || normalizedSystemFont !== null;
  const selectedFontMissing = Boolean(
    normalizedSystemFont
      && installedFamilies.length
      && !installedFamilies.some(
        (family) => family.toLocaleLowerCase() === normalizedSystemFont.toLocaleLowerCase(),
      ),
  );
  const visibleFontInventoryStatus = selectedFontMissing
    ? `${normalizedSystemFont} was not found in the loaded list. Whiteboard will use the mode default if the operating system cannot resolve it.`
    : fontInventoryStatus;
  const applySystemFont = () => {
    if (!systemFontValid) return;
    update('systemFontFamily', normalizedSystemFont);
  };
  const loadInstalledFonts = async () => {
    // Keep this call directly inside the click turn: Local Font Access requires
    // explicit user activation and the adapter performs no permission preflight.
    const pending = queryInstalledFontFamiliesFromUserGesture();
    setLoadingFonts(true);
    setFontInventoryStatus('Reading installed fonts…');
    try {
      const families = await pending;
      setInstalledFamilies(families);
      setFontInventoryStatus(
        families.length
          ? `${families.length} installed font ${families.length === 1 ? 'family' : 'families'} available.`
          : 'No installed font families were returned.',
      );
    } catch (error) {
      setFontInventoryStatus(
        error instanceof InstalledFontInventoryError
          ? error.message
          : 'Whiteboard could not read the installed-font list.',
      );
    } finally {
      setLoadingFonts(false);
    }
  };

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
              {TYPEFACE_GROUPS.map((group) => (
                <optgroup key={group.label} label={group.label}>
                  {group.options.map((typeface) => (
                    <option key={typeface.value} value={typeface.value}>
                      {typeface.label}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>

          {tools.typeface === 'installed' && (
            <div className="wb-system-font">
              <label htmlFor="wb-system-font-family">Installed font family</label>
              <div className="wb-system-font-row">
                <input
                  id="wb-system-font-family"
                  type="text"
                  value={systemFontDraft}
                  maxLength={SYSTEM_FONT_FAMILY_MAX_LENGTH}
                  placeholder="e.g. Garamond"
                  list="wb-installed-font-families"
                  aria-invalid={!systemFontValid}
                  aria-describedby={systemFontValid
                    ? 'wb-system-font-help wb-system-font-status'
                    : 'wb-system-font-status'}
                  aria-errormessage={!systemFontValid ? 'wb-system-font-error' : undefined}
                  onChange={(e) => setSystemFontDraft(e.target.value)}
                  onBlur={applySystemFont}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      applySystemFont();
                      e.currentTarget.blur();
                    }
                  }}
                />
                <datalist id="wb-installed-font-families">
                  {installedFamilies.map((family) => (
                    <option key={family} value={family} />
                  ))}
                </datalist>
                <button type="button" onClick={applySystemFont} disabled={!systemFontValid}>
                  Apply
                </button>
              </div>
              {!systemFontValid ? (
                <p id="wb-system-font-error" className="wb-field-error">
                  Enter one font family name, without CSS or a fallback list.
                </p>
              ) : (
                <p id="wb-system-font-help" className="wb-field-hint">
                  Uses a font installed on this computer. Install it in your OS, then refresh the list; you can also type its exact family name.
                </p>
              )}
              <div className="wb-system-font-inventory">
                <button type="button" onClick={() => void loadInstalledFonts()} disabled={loadingFonts}>
                  {loadingFonts
                    ? 'Loading…'
                    : installedFamilies.length
                      ? 'Refresh installed fonts'
                      : 'Load installed fonts'}
                </button>
                <span id="wb-system-font-status" role="status" aria-live="polite">
                  {visibleFontInventoryStatus}
                </span>
              </div>
            </div>
          )}

          <div className="wb-field wb-color-field">
            <label htmlFor="wb-editor-text-color">Manuscript text</label>
            <input
              id="wb-editor-text-color"
              type="color"
              value={tools.textColor ?? theme.editorText}
              onChange={(e) => update('textColor', e.target.value)}
              aria-label="Manuscript text color"
            />
            <button
              type="button"
              className="wb-color-reset"
              onClick={() => update('textColor', null)}
              disabled={tools.textColor === null}
            >
              Theme default
            </button>
          </div>

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
