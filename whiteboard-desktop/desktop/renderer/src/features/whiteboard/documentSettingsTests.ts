/** Pure project-scoped document-settings tests. */

import {
  DEFAULT_SETTINGS,
  clearLegacySettingsMigration,
  legacySettingsForDocument,
  normalizeDocumentSettings,
} from './documentSettings';
import { mergeWhiteboardPatch, restoreWhiteboardPatch } from './whiteboardPatch';

let passed = 0;
const failures: string[] = [];
const check = (label: string, condition: boolean): void => {
  if (condition) passed += 1;
  else failures.push(label);
};

const normalized = normalizeDocumentSettings({
  narrativePerson: 'first',
  narrativeStyle: 'lyrical',
  narrativeRegister: 'vernacular',
  slangLevel: 'moderate',
  sceneHeadingStyle: 'bold-underline',
  blankLinesBeforeScene: 2,
  includeOutline: true,
  typeface: 'monospace',
  showInvisibles: false,
  injectedUnknownKey: 'ignored',
});
check('valid narrative person retained', normalized.narrativePerson === 'first');
check('valid narrative style retained', normalized.narrativeStyle === 'lyrical');
check('valid register retained', normalized.narrativeRegister === 'vernacular');
check('valid slang retained', normalized.slangLevel === 'moderate');
check('valid formatting retained', normalized.sceneHeadingStyle === 'bold-underline');
check('numeric formatting retained', normalized.blankLinesBeforeScene === 2);
check('booleans retained', normalized.includeOutline && !normalized.showInvisibles);
check('typeface retained', normalized.typeface === 'monospace');
check('unknown keys discarded', !('injectedUnknownKey' in normalized));

const malformed = normalizeDocumentSettings({
  narrativePerson: 'second',
  narrativeStyle: 42,
  blankLinesBeforeScene: 99,
  includeOutline: 'yes',
  showInvisibles: null,
});
check('bad enums fall back safely', malformed.narrativePerson === DEFAULT_SETTINGS.narrativePerson);
check('bad scalar values fall back safely', malformed.narrativeStyle === DEFAULT_SETTINGS.narrativeStyle);
check('bad line count falls back safely', malformed.blankLinesBeforeScene === 1);
check('bad booleans fall back safely', malformed.includeOutline === false && malformed.showInvisibles === true);

const blocks = [{ id: 'b1', type: 'paragraph', text: 'Draft' }];
const combined = mergeWhiteboardPatch({ blocks }, { settings: { narrativePerson: 'first' } });
check('save queue combines manuscript and settings', combined.blocks === blocks && !!combined.settings);
const latest = mergeWhiteboardPatch(combined, { settings: { narrativePerson: 'third-limited' } });
check(
  'newer queued field wins',
  (latest.settings as { narrativePerson?: string }).narrativePerson === 'third-limited',
);
const restored = restoreWhiteboardPatch(
  { settings: { narrativeStyle: 'literary' }, title: 'Old title' },
  { title: 'New title', blocks },
);
check(
  'failed patch restore preserves newer edits',
  restored.title === 'New title' && restored.blocks === blocks && !!restored.settings,
);

// One-time migration from the pre-project-scoping localStorage key.
const values = new Map<string, string>();
values.set('logosforge-doc-settings', JSON.stringify({ narrativePerson: 'third-limited' }));
const originalStorage = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  value: {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => { values.delete(key); },
  },
});
try {
  const legacy = legacySettingsForDocument('doc-a');
  check('legacy settings normalized', legacy?.narrativePerson === 'third-limited');
  check('legacy bytes retained until backend confirmation', values.has('logosforge-doc-settings'));
  check('legacy migration target recorded', values.get('logosforge-doc-settings-migration-target') === 'doc-a');
  check('legacy value cannot leak to another document', legacySettingsForDocument('doc-b') === null);
  clearLegacySettingsMigration('doc-b');
  check('wrong document cannot clear legacy migration', values.has('logosforge-doc-settings'));
  clearLegacySettingsMigration('doc-a');
  check(
    'confirmed target clears legacy migration',
    !values.has('logosforge-doc-settings') && !values.has('logosforge-doc-settings-migration-target'),
  );
} finally {
  if (originalStorage) Object.defineProperty(globalThis, 'localStorage', originalStorage);
  else Reflect.deleteProperty(globalThis, 'localStorage');
}

console.log(`Document settings tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} document settings test(s) failed`);
console.log('DOCUMENT SETTINGS TESTS: PASS');
