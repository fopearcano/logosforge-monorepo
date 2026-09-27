const fs = require('node:fs');
const path = require('node:path');

const app = fs.readFileSync(path.join(process.cwd(), 'renderer', 'src', 'App.tsx'), 'utf8');
const main = fs.readFileSync(path.join(process.cwd(), 'electron', 'main.ts'), 'utf8');
const preload = fs.readFileSync(path.join(process.cwd(), 'electron', 'preload.ts'), 'utf8');
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
  'const operationQueue = useRef<Promise<void>>',
  'const targetProjectId = projectIdRef.current',
  'workspaceHydratedProjectRef.current !== targetProjectId',
  'const queuedOperations = operationQueue.current',
  'queuedOperations.then(() => flushPendingProjectSaves',
  'closingRef.current = true',
  'if (closingRef.current) return false',
  'setClosePending(true)',
  'setClosePending(false)',
  'onCloseCancelled',
  'sendCloseResult(attemptId, true)',
]) {
  if (!app.includes(marker)) failures.push(`App bootstrap ownership missing ${marker}`);
}
if (app.includes('window.setTimeout(() => setBootstrapAttempt')) {
  failures.push('App still creates an unowned bootstrap retry timer');
}
for (const marker of [
  'let nextCloseAttemptId = 1',
  "win.webContents.send('app:save-before-close', attemptId)",
  'pendingCloseResult?.attemptId !== attemptId',
  "win.webContents.send('app:close-cancelled')",
]) {
  if (!main.includes(marker)) failures.push(`Main close protocol missing ${marker}`);
}
for (const marker of [
  "subscribe<number>('app:save-before-close', cb)",
  "subscribe<void>('app:close-cancelled', () => cb())",
  "ipcRenderer.send('app:close-result', attemptId, saved)",
]) {
  if (!preload.includes(marker)) failures.push(`Preload close protocol missing ${marker}`);
}

console.log('Desktop lifecycle checks');
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} desktop lifecycle violation(s)`);
console.log('DESKTOP LIFECYCLE TESTS: PASS');
