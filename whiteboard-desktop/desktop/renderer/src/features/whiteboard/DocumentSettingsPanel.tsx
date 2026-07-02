/** The Document Settings form (Screenplay) — rendered inside a Popover. */

import type { DocumentSettings, SceneHeadingStyle, Typeface } from './documentSettings';

interface Props {
  settings: DocumentSettings;
  update: <K extends keyof DocumentSettings>(key: K, value: DocumentSettings[K]) => void;
}

const SCENE_STYLES: { value: SceneHeadingStyle; label: string }[] = [
  { value: 'normal', label: 'Normal' },
  { value: 'bold', label: 'Bold' },
  { value: 'underline', label: 'Underline' },
  { value: 'bold-underline', label: 'Bold + Underline' },
];

const TYPEFACES: { value: Typeface; label: string }[] = [
  { value: 'courier-prime', label: 'Courier Prime' },
  { value: 'courier', label: 'Courier' },
  { value: 'monospace', label: 'Monospace' },
];

export function DocumentSettingsPanel({ settings, update }: Props) {
  return (
    <div className="wb-settings">
      <h3 className="wb-settings-title">Document Settings</h3>

      <label className="wb-field">
        <span>Scene Heading</span>
        <select
          value={settings.sceneHeadingStyle}
          onChange={(e) => update('sceneHeadingStyle', e.target.value as SceneHeadingStyle)}
        >
          {SCENE_STYLES.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </label>

      <label className="wb-field">
        <span>Blank lines before Scene</span>
        <select
          value={settings.blankLinesBeforeScene}
          onChange={(e) => update('blankLinesBeforeScene', Number(e.target.value) === 2 ? 2 : 1)}
        >
          <option value={1}>One</option>
          <option value={2}>Two</option>
        </select>
      </label>

      <label className="wb-field">
        <span>Typeface</span>
        <select value={settings.typeface} onChange={(e) => update('typeface', e.target.value as Typeface)}>
          {TYPEFACES.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </label>

      <label className="wb-field wb-field-check">
        <input
          type="checkbox"
          checked={settings.includeOutline}
          onChange={(e) => update('includeOutline', e.target.checked)}
        />
        <span>Include outline elements in Preview</span>
      </label>

      <label className="wb-field wb-field-check">
        <input
          type="checkbox"
          checked={settings.showInvisibles}
          onChange={(e) => update('showInvisibles', e.target.checked)}
        />
        <span>Show invisible Fountain markers</span>
      </label>
    </div>
  );
}
