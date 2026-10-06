/** Headless coverage for the opt-in installed-font inventory. */

import {
  INSTALLED_FONT_FAMILY_MAX_LENGTH,
  InstalledFontInventoryError,
  dedupeInstalledFontFamilies,
  installedFontCssStack,
  normalizeInstalledFontFamily,
  queryInstalledFontFamiliesFromUserGesture,
  type LocalFontQueryHost,
} from './installedFonts';

let passed = 0;
const failures: string[] = [];
function check(label: string, condition: boolean) {
  if (condition) passed += 1;
  else failures.push(label);
}

async function rejectedCode(
  host: LocalFontQueryHost,
): Promise<string | null> {
  try {
    await queryInstalledFontFamiliesFromUserGesture(host);
    return null;
  } catch (error) {
    return error instanceof InstalledFontInventoryError ? error.code : 'wrong-error';
  }
}

async function run() {
  check(
    'normalizer keeps Unicode family names',
    normalizeInstalledFontFamily('  ヒラギノ角ゴシック ProN  ') === 'ヒラギノ角ゴシック ProN',
  );
  check(
    'normalizer canonicalizes spacing and Unicode composition',
    normalizeInstalledFontFamily('Cafe\u0301\u00a0  Serif') === 'Café Serif',
  );
  check(
    'normalizer rejects CSS delimiters and escapes',
    normalizeInstalledFontFamily('Arial"; color: red') === null
      && normalizeInstalledFontFamily('Arial\\Injected') === null
      && normalizeInstalledFontFamily('Arial{font-size:99px}') === null,
  );
  check(
    'normalizer rejects overlong names',
    normalizeInstalledFontFamily('A'.repeat(INSTALLED_FONT_FAMILY_MAX_LENGTH + 1)) === null,
  );

  const families = dedupeInstalledFontFamilies([
    { family: 'Courier 10' },
    { family: ' arial ' },
    { family: 'Courier 2' },
    { family: 'Arial' },
    { family: 'Noto Sans' },
    { family: 'Bad;Family' },
    { family: 42 },
  ]);
  check(
    'inventory is filtered, case-deduplicated, and naturally sorted',
    JSON.stringify(families) === JSON.stringify(['Arial', 'Courier 2', 'Courier 10', 'Noto Sans']),
  );
  check(
    'CSS stack quotes the family and retains the per-mode fallback',
    installedFontCssStack('Noto Sans') === '"Noto Sans", var(--wb-mode-typeface)',
  );
  check(
    'unsafe family never reaches the CSS sink',
    installedFontCssStack('Noto";background:red') === null,
  );

  let calledSynchronously = false;
  const pending = queryInstalledFontFamiliesFromUserGesture({
    queryLocalFonts: () => {
      calledSynchronously = true;
      return Promise.resolve([{ family: 'Zed' }, { family: 'Alpha' }, { family: 'zed' }]);
    },
  });
  check('queryLocalFonts is invoked synchronously in the adapter', calledSynchronously);
  check(
    'query adapter returns reduced family inventory',
    JSON.stringify(await pending) === JSON.stringify(['Alpha', 'Zed']),
  );

  check(
    'unsupported runtime has a stable error code',
    await rejectedCode({}) === 'unsupported',
  );
  check(
    'permission denial has a stable error code',
    await rejectedCode({
      queryLocalFonts: () => Promise.reject(Object.assign(new Error('denied'), { name: 'NotAllowedError' })),
    }) === 'denied',
  );
  check(
    'lost user activation has a stable error code',
    await rejectedCode({
      queryLocalFonts: () => {
        throw Object.assign(new Error('gesture required'), { name: 'SecurityError' });
      },
    }) === 'security',
  );
  check(
    'unknown inventory failure stays generic',
    await rejectedCode({ queryLocalFonts: () => Promise.reject(new Error('boom')) }) === 'failed',
  );

  console.log(`Installed-font tests: ${passed} passed, ${failures.length} failed`);
  for (const failure of failures) console.log('  FAIL: ' + failure);
  if (failures.length) throw new Error(`${failures.length} installed-font test(s) failed`);
  console.log('INSTALLED FONT TESTS: PASS');
}

void run();
