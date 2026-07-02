/**
 * Theme token tests (pure — no DOM). Runs headlessly: `npm run test:themes`.
 * Verifies the 5 palettes, the readability invariant (Part 7), and custom-theme
 * derivation. Throws (non-zero) on failure.
 */

import {
  DEFAULT_CUSTOM_FIELDS,
  PREDEFINED_THEMES,
  getPredefinedTheme,
  resolveTheme,
} from './predefinedThemes';
import { customToTheme, isDark, rgba } from './themeTokens';

let passed = 0;
const failures: string[] = [];
function check(label: string, cond: boolean) {
  if (cond) passed += 1;
  else failures.push(label);
}

// 1. Colour helpers
check('rgba long hex', rgba('#3b6fd4', 0.2) === 'rgba(59, 111, 212, 0.2)');
check('rgba short hex', rgba('#fff', 1) === 'rgba(255, 255, 255, 1)');
check('isDark navy', isDark('#101e36'));
check('isDark black', isDark('#070504'));
check('isLight parchment', !isDark('#f3ead3'));
check('isLight white-ish', !isDark('#faf5ef'));

// 2. Six predefined themes exist, unique, valid hex
check('six themes', PREDEFINED_THEMES.length === 6);
check('unique ids', new Set(PREDEFINED_THEMES.map((t) => t.id)).size === 6);
check(
  'valid hex backgrounds',
  PREDEFINED_THEMES.every((t) => /^#[0-9a-f]{6}$/i.test(t.appBg) && /^#[0-9a-f]{6}$/i.test(t.editorBg)),
);

// 3. Readability invariant (Part 7): text must contrast its background
check(
  'editor ink contrasts editor bg',
  PREDEFINED_THEMES.every((t) => isDark(t.editorBg) !== isDark(t.editorText)),
);
check(
  'ui text contrasts panel bg',
  PREDEFINED_THEMES.every((t) => isDark(t.panelBg) !== isDark(t.text)),
);

// 4. resolveTheme
check('resolve predefined', resolveTheme('violet', DEFAULT_CUSTOM_FIELDS).id === 'violet');
check('resolve custom', resolveTheme('custom', DEFAULT_CUSTOM_FIELDS).id === 'custom');
check('resolve unknown -> first', resolveTheme('nope', DEFAULT_CUSTOM_FIELDS).id === PREDEFINED_THEMES[0].id);
check('getPredefinedTheme', getPredefinedTheme('forge')?.name === 'Forge');

// 5. Custom theme derives a readable editor ink + mode from luminance
{
  const lightEditor = customToTheme({ ...DEFAULT_CUSTOM_FIELDS, editorBg: '#ffffff' });
  check('custom light editor -> dark ink', isDark(lightEditor.editorText));
  const darkEditor = customToTheme({ ...DEFAULT_CUSTOM_FIELDS, editorBg: '#000000' });
  check('custom dark editor -> light ink', !isDark(darkEditor.editorText));
  check('custom mode from appBg (light)', customToTheme({ ...DEFAULT_CUSTOM_FIELDS, appBg: '#ffffff' }).mode === 'light');
  check('custom mode from appBg (dark)', customToTheme({ ...DEFAULT_CUSTOM_FIELDS, appBg: '#101010' }).mode === 'dark');
  check('custom caret follows accent', customToTheme(DEFAULT_CUSTOM_FIELDS).caret === DEFAULT_CUSTOM_FIELDS.accent);
}

// --- report ---
console.log(`Theme tests: ${passed} passed, ${failures.length} failed`);
for (const f of failures) console.log('  FAIL: ' + f);
if (failures.length) throw new Error(`${failures.length} theme test(s) failed`);
console.log('THEME TESTS: PASS');
