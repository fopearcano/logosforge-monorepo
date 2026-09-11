/** Project-save handoff barrier tests. */

import {
  flushPendingProjectSaves,
  markProjectSavePending,
  PendingProjectSaveError,
  prepareProjectHandoff,
  registerProjectFlusher,
  trackProjectWrite,
} from '../src/adapters/projectSaveCoordinator';

let passed = 0;
const failures: string[] = [];
const check = (label: string, condition: boolean): void => {
  if (condition) passed += 1;
  else failures.push(label);
};

{
  const calls: string[] = [];
  const offA = registerProjectFlusher(async () => { calls.push('a'); return true; });
  const offB = registerProjectFlusher(async () => { calls.push('b'); return true; });
  try { await flushPendingProjectSaves(); } finally { offA(); offB(); }
  check('handoff invokes every editor flusher', calls.join(',') === 'a,b');
}

{
  const calls: string[] = [];
  const caller = async () => { calls.push('caller'); return true; };
  const peer = async () => { calls.push('peer'); return true; };
  const offCaller = registerProjectFlusher(caller);
  const offPeer = registerProjectFlusher(peer);
  try { await flushPendingProjectSaves({ excludeFlusher: caller }); }
  finally { offCaller(); offPeer(); }
  check('nested drain excludes only its calling flusher', calls.join(',') === 'peer');
}

{
  const off = registerProjectFlusher(async () => false);
  let caught: unknown = null;
  try { await flushPendingProjectSaves(); } catch (error) { caught = error; } finally { off(); }
  check('unsaved editor blocks handoff', caught instanceof PendingProjectSaveError);
}

{
  let attempts = 0;
  const off = registerProjectFlusher(async () => {
    attempts += 1;
    return attempts > 1;
  });
  let firstBlocked = false;
  try {
    await flushPendingProjectSaves();
  } catch (error) {
    firstBlocked = error instanceof PendingProjectSaveError;
  }
  let retryPassed = false;
  try {
    await flushPendingProjectSaves();
    retryPassed = true;
  } finally {
    off();
  }
  check('failed draft blocks the first handoff', firstBlocked);
  check('same draft can be retried on the next handoff', retryPassed && attempts === 2);
}

{
  let release!: () => void;
  const write = new Promise<void>((resolve) => { release = resolve; });
  trackProjectWrite(write);
  let done = false;
  const flushing = flushPendingProjectSaves().then(() => { done = true; });
  await Promise.resolve();
  check('handoff waits for in-flight write', !done);
  release();
  await flushing;
  check('handoff resumes after in-flight write', done);
}

{
  const order: string[] = [];
  const off = registerProjectFlusher(async () => { order.push('flush'); return true; });
  try {
    const target = await prepareProjectHandoff(async () => { order.push('prepare'); return 42; });
    check('prepare handoff returns target', target === 42);
  } finally { off(); }
  check('prepare handoff drains on both sides', order.join(',') === 'flush,prepare,flush');
}

{
  let pass = 0;
  const off = registerProjectFlusher(async () => {
    pass += 1;
    if (pass === 1) markProjectSavePending();
    return true;
  });
  try { await flushPendingProjectSaves(); } finally { off(); }
  check('new edit during handoff causes another drain pass', pass === 2);
}

{
  let blurred = false;
  const originalDocument = globalThis.document;
  const originalHTMLElement = globalThis.HTMLElement;
  class FakeElement {
    matches(selector: string) { return selector.includes('input'); }
    blur() { blurred = true; }
  }
  Object.defineProperty(globalThis, 'HTMLElement', { value: FakeElement, configurable: true });
  Object.defineProperty(globalThis, 'document', {
    value: { activeElement: new FakeElement() }, configurable: true,
  });
  try {
    await flushPendingProjectSaves({ commitActiveField: true });
  } finally {
    Object.defineProperty(globalThis, 'document', { value: originalDocument, configurable: true });
    Object.defineProperty(globalThis, 'HTMLElement', { value: originalHTMLElement, configurable: true });
  }
  check('handoff commits the active inline field through blur', blurred);
}

console.log(`Project save coordinator tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} project save coordinator test(s) failed`);
console.log('PROJECT SAVE COORDINATOR TESTS: PASS');
