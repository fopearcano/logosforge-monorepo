const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

const sourcePath = path.join(process.cwd(), 'renderer', 'src', 'skinPreference.ts');
const source = fs.readFileSync(sourcePath, 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2021, strict: true },
  fileName: sourcePath,
  reportDiagnostics: true,
});
if (compiled.diagnostics?.length) {
  throw new Error(compiled.diagnostics.map((item) => ts.flattenDiagnosticMessageText(item.messageText, '\n')).join('\n'));
}
const resolveSkin = (value) => ({ forge: 'forge', paper: 'paper', lamplit: 'lamplit', dark: 'forge', light: 'paper', warm: 'lamplit' }[value] ?? 'forge');
const moduleUnderTest = { exports: {} };
const localRequire = (request) => {
  if (request === '@logosforge/pro-shared-ui') return { resolveSkin };
  throw new Error(`Unexpected require: ${request}`);
};
Function('require', 'module', 'exports', compiled.outputText)(localRequire, moduleUnderTest, moduleUnderTest.exports);
const { readSkinPreference, writeSkinPreference, applySkinPreference } = moduleUnderTest.exports;

let passed = 0;
const check = (label, work) => {
  work();
  passed += 1;
  console.log(`  PASS: ${label}`);
};
const storage = (values) => ({ getItem: (key) => values[key] ?? null });

check('missing preference defaults to Forge', () => assert.equal(readSkinPreference(storage({})), 'forge'));
check('new Skin preference wins over legacy appearance', () => assert.equal(readSkinPreference(storage({ 'lf.skin.v1': 'paper', 'lf.theme': 'dark' })), 'paper'));
check('legacy dark migrates to Forge', () => assert.equal(readSkinPreference(storage({ 'lf.theme': 'dark' })), 'forge'));
check('legacy light migrates to Paper', () => assert.equal(readSkinPreference(storage({ 'lf.theme': 'light' })), 'paper'));
check('legacy warm migrates to Lamplit', () => assert.equal(readSkinPreference(storage({ 'lf.theme': 'warm' })), 'lamplit'));
check('invalid preference fails safe', () => assert.equal(readSkinPreference(storage({ 'lf.skin.v1': 'neon' })), 'forge'));
check('blocked storage read fails safe', () => assert.equal(readSkinPreference({ getItem: () => { throw new Error('blocked'); } }), 'forge'));
check('write uses the versioned key', () => {
  const writes = [];
  writeSkinPreference('paper', { setItem: (key, value) => writes.push([key, value]) });
  assert.deepEqual(writes, [['lf.skin.v1', 'paper']]);
});
check('blocked storage write does not interrupt switching', () => {
  assert.doesNotThrow(() => writeSkinPreference('lamplit', { setItem: () => { throw new Error('blocked'); } }));
});
check('application updates Skin and removes the legacy attribute', () => {
  const root = { dataset: { theme: 'light' } };
  applySkinPreference('paper', root);
  assert.deepEqual(root.dataset, { skin: 'paper' });
});

console.log(`Desktop Skin preference tests: ${passed} passed`);
