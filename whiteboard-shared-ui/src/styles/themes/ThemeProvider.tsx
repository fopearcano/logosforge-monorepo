/** Holds the selected theme + custom fields, applies CSS variables, persists. */

import { useCallback, useLayoutEffect, useMemo, useState, type ReactNode } from 'react';

import {
  loadCustomFields,
  loadThemeId,
  saveCustomFields,
  saveThemeId,
} from './customThemeStorage';
import { resolveTheme } from './predefinedThemes';
import { applySyntaxVars } from './syntaxThemes';
import { applyThemeVars, type CustomThemeFields } from './themeTokens';
import { ThemeContext, type ThemeContextValue } from './useTheme';

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [themeId, setThemeIdState] = useState<string>(loadThemeId);
  const [customFields, setCustomFields] = useState<CustomThemeFields>(loadCustomFields);

  const theme = useMemo(() => resolveTheme(themeId, customFields), [themeId, customFields]);

  // Apply before paint (and again on change). main.tsx also applies once before
  // React mounts, so there is no theme flash on startup.
  useLayoutEffect(() => {
    applyThemeVars(theme);
    // Base syntax/screenplay colours track the active theme; a Nerd-Mode syntax
    // override (editorTools) may still set --syn-* afterward.
    applySyntaxVars(theme.id);
  }, [theme]);

  const setThemeId = useCallback((id: string) => {
    saveThemeId(id);
    setThemeIdState(id);
  }, []);

  const setCustomField = useCallback((key: keyof CustomThemeFields, value: string) => {
    setCustomFields((prev) => {
      const next = { ...prev, [key]: value };
      saveCustomFields(next);
      return next;
    });
    // Editing a custom field implies the Custom theme is active.
    saveThemeId('custom');
    setThemeIdState('custom');
  }, []);

  const value = useMemo<ThemeContextValue>(
    () => ({ theme, themeId, setThemeId, customFields, setCustomField }),
    [theme, themeId, setThemeId, customFields, setCustomField],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
