/** Theme context + consumer hook. Provided by ThemeProvider. */

import { createContext, useContext } from 'react';

import type { CustomThemeFields, WhiteboardTheme } from './themeTokens';

export interface ThemeContextValue {
  /** The resolved active theme. */
  theme: WhiteboardTheme;
  /** Selected id: a predefined id or 'custom'. */
  themeId: string;
  setThemeId: (id: string) => void;
  customFields: CustomThemeFields;
  setCustomField: (key: keyof CustomThemeFields, value: string) => void;
}

export const ThemeContext = createContext<ThemeContextValue | null>(null);

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used within <ThemeProvider>');
  return ctx;
}
