/** localStorage persistence for the selected theme id + Custom theme fields. */

import { DEFAULT_CUSTOM_FIELDS, DEFAULT_THEME_ID, resolveTheme } from './predefinedThemes';
import { applySyntaxVars } from './syntaxThemes';
import { applyThemeVars, type CustomThemeFields } from './themeTokens';

const ID_KEY = 'lf-theme-id';
const CUSTOM_KEY = 'lf-theme-custom';

export function loadThemeId(): string {
  try {
    return localStorage.getItem(ID_KEY) || DEFAULT_THEME_ID;
  } catch {
    return DEFAULT_THEME_ID;
  }
}

export function saveThemeId(id: string): void {
  try {
    localStorage.setItem(ID_KEY, id);
  } catch {
    /* ignore */
  }
}

export function loadCustomFields(): CustomThemeFields {
  try {
    const raw = localStorage.getItem(CUSTOM_KEY);
    if (raw) return { ...DEFAULT_CUSTOM_FIELDS, ...(JSON.parse(raw) as Partial<CustomThemeFields>) };
  } catch {
    /* ignore */
  }
  return DEFAULT_CUSTOM_FIELDS;
}

export function saveCustomFields(fields: CustomThemeFields): void {
  try {
    localStorage.setItem(CUSTOM_KEY, JSON.stringify(fields));
  } catch {
    /* ignore */
  }
}

/** Apply the persisted theme immediately (call before React renders → no flash). */
export function applyStoredTheme(): void {
  const id = loadThemeId();
  applyThemeVars(resolveTheme(id, loadCustomFields()));
  applySyntaxVars(id);
}
