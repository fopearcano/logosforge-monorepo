const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

const sourcePath = path.join(process.cwd(), 'renderer', 'src', 'projectResume.ts');
const source = fs.readFileSync(sourcePath, 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2021,
    strict: true,
  },
  fileName: sourcePath,
  reportDiagnostics: true,
});
const diagnostics = compiled.diagnostics ?? [];
if (diagnostics.length) {
  throw new Error(diagnostics.map((item) => ts.flattenDiagnosticMessageText(item.messageText, '\n')).join('\n'));
}
const moduleUnderTest = { exports: {} };
Function('module', 'exports', compiled.outputText)(moduleUnderTest, moduleUnderTest.exports);
const {
  PROJECT_SESSION_VERSION,
  projectIdFromSessionState,
  selectStartupProjectId,
} = moduleUnderTest.exports;

const failures = [];
const check = (label, condition) => {
  if (!condition) failures.push(label);
};

check('host session project id parses', projectIdFromSessionState({
  version: PROJECT_SESSION_VERSION,
  lastActiveProjectId: 42,
}) === 42);
for (const value of [
  null,
  {},
  [],
  { version: PROJECT_SESSION_VERSION + 1, lastActiveProjectId: 2 },
  { version: PROJECT_SESSION_VERSION, lastActiveProjectId: 0 },
  { version: PROJECT_SESSION_VERSION, lastActiveProjectId: -1 },
  { version: PROJECT_SESSION_VERSION, lastActiveProjectId: 1.5 },
  { version: PROJECT_SESSION_VERSION, lastActiveProjectId: '2' },
  { version: PROJECT_SESSION_VERSION, lastActiveProjectId: Number.MAX_SAFE_INTEGER + 1 },
]) {
  check(`invalid host session is rejected: ${JSON.stringify(value)}`, projectIdFromSessionState(value) === null);
}
check('an explicitly cleared host session has no project', projectIdFromSessionState({
  version: PROJECT_SESSION_VERSION,
  lastActiveProjectId: null,
}) === null);

const projects = [{ id: 3 }, { id: 8 }, { id: 13 }];
check('persisted project wins over list order', selectStartupProjectId(projects, 8) === 8);
check('missing persisted project falls back safely', selectStartupProjectId(projects, 21) === 3);
check('no persisted project uses first library entry', selectStartupProjectId(projects, null) === 3);
check('empty library returns no selection', selectStartupProjectId([], 8) === null);

console.log('Desktop project-resume checks');
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} project-resume test(s) failed`);
console.log('DESKTOP PROJECT-RESUME TESTS: PASS');
