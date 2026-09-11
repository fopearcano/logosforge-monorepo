const fs = require('node:fs');
const path = require('node:path');

const app = fs.readFileSync(path.join(process.cwd(), 'renderer', 'src', 'App.tsx'), 'utf8');
const failures = [];
for (const marker of [
  'bootstrapRetryTimerRef',
  'window.clearTimeout(bootstrapRetryTimerRef.current)',
  'appMountedRef.current',
  'bootstrapRunRef.current === run',
  'const ps = await api.listProjects()',
  'liveEventSeen',
  'return () => { active = false; unsubscribe(); }',
  'Preparing your project…',
  'createDeferredDisposer<ApiClient>',
  'apiDisposer.acquire(api)',
]) {
  if (!app.includes(marker)) failures.push(`App bootstrap ownership missing ${marker}`);
}
if (app.includes('window.setTimeout(() => setBootstrapAttempt')) {
  failures.push('App still creates an unowned bootstrap retry timer');
}

console.log('Desktop lifecycle checks');
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} desktop lifecycle violation(s)`);
console.log('DESKTOP LIFECYCLE TESTS: PASS');
