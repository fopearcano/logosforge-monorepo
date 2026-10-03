const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

const sourcePath = path.join(process.cwd(), 'renderer', 'src', 'coreGeneration.ts');
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
const { CoreGenerationTracker } = moduleUnderTest.exports;

const failures = [];
const check = (label, condition) => {
  if (!condition) failures.push(label);
};

const connected = {
  state: 'connected', baseUrl: 'http://127.0.0.1:8765', managed: true, authToken: 'old-token',
};
const tracker = new CoreGenerationTracker();
const firstGeneration = tracker.observe(connected);
check('first observed status establishes a generation', firstGeneration > 0);
check('identical status does not invalidate work', tracker.observe({ ...connected, detail: 'ignored' }) === firstGeneration);
check('the captured generation starts current', tracker.isCurrent(firstGeneration));

let resolveOldOpen;
const oldOpen = new Promise((resolve) => { resolveOldOpen = resolve; });
let publishedProjectId = null;
let persistedProjectId = null;
const oldCompletion = oldOpen.then((project) => {
  if (!tracker.isCurrent(firstGeneration)) return false;
  publishedProjectId = project.id;
  persistedProjectId = project.id;
  return true;
});

tracker.observe({ ...connected, state: 'error' });
resolveOldOpen({ id: 41 });

async function main() {
  check('lifecycle change invalidates the old generation', !tracker.isCurrent(firstGeneration));
  check('deferred old open is discarded', await oldCompletion === false);
  check('deferred old open publishes no project', publishedProjectId === null);
  check('deferred old open persists no resume selection', persistedProjectId === null);

  const errorGeneration = tracker.current();
  tracker.observe({ ...connected, authToken: 'new-token' });
  check('new core identity advances the generation', tracker.current() > errorGeneration);

  console.log('Desktop core-generation checks');
  for (const failure of failures) console.error(`  FAIL: ${failure}`);
  if (failures.length) throw new Error(`${failures.length} core-generation test(s) failed`);
  console.log('DESKTOP CORE-GENERATION TESTS: PASS');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
