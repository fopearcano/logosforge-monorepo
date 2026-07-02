/** Theme picker: 6 predefined themes + Custom (with minimal colour inputs). */

import { Popover } from '../../components/Popover';
import { PREDEFINED_THEMES } from './predefinedThemes';
import type { CustomThemeFields } from './themeTokens';
import { useTheme } from './useTheme';

const CUSTOM_ROWS: { key: keyof CustomThemeFields; label: string }[] = [
  { key: 'appBg', label: 'Chrome' },
  { key: 'editorBg', label: 'Page' },
  { key: 'text', label: 'UI text' },
  { key: 'mutedText', label: 'Muted text' },
  { key: 'accent', label: 'Accent' },
  { key: 'border', label: 'Border' },
];

export function ThemeSelector() {
  const { theme, themeId, setThemeId, customFields, setCustomField } = useTheme();

  return (
    <Popover
      align="right"
      title="Theme"
      label={
        <span className="theme-trigger">
          <span className="theme-dot" style={{ background: theme.accent }} />
          Theme
        </span>
      }
    >
      {() => (
        <div className="theme-menu">
          <div className="theme-grid">
            {PREDEFINED_THEMES.map((t) => (
              <button
                key={t.id}
                type="button"
                className={`theme-option${themeId === t.id ? ' is-active' : ''}`}
                onClick={() => setThemeId(t.id)}
                title={t.name}
              >
                <span className="theme-option-name">{t.name}</span>
              </button>
            ))}
            <button
              type="button"
              className={`theme-option${themeId === 'custom' ? ' is-active' : ''}`}
              onClick={() => setThemeId('custom')}
              title="Custom"
            >
              <span className="theme-option-name">Custom</span>
            </button>
          </div>

          {themeId === 'custom' && (
            <div className="theme-custom">
              <div className="theme-custom-title">Custom colors</div>
              {CUSTOM_ROWS.map((f) => (
                <label key={f.key} className="theme-custom-row">
                  <span>{f.label}</span>
                  <input
                    type="color"
                    value={customFields[f.key]}
                    onChange={(e) => setCustomField(f.key, e.target.value)}
                    aria-label={f.label}
                  />
                </label>
              ))}
              <p className="theme-custom-note">
                These six colours drive the whole theme — panels, page ink and selection are
                derived from them automatically.
              </p>
            </div>
          )}
        </div>
      )}
    </Popover>
  );
}
