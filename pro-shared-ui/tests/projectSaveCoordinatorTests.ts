/** Project-save handoff barrier tests. */

import {
  flushPendingProjectSaves,
  getProjectSaveStatusSnapshot,
  discardProjectSavePending,
  markProjectSavePending,
  PendingProjectSaveError,
  prepareProjectHandoff,
  registerProjectFlusher,
  trackProjectOperation,
  trackProjectWrite,
} from '../src/adapters/projectSaveCoordinator';
import { registerPanelHostDocument } from '../src/components/common/panelHostDocuments';

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
  markProjectSavePending();
  let caught: unknown = null;
  try { await flushPendingProjectSaves(); } catch (error) { caught = error; }
  check('unkeyed pending edit without an owner flusher blocks handoff', caught instanceof PendingProjectSaveError);
  const off = registerProjectFlusher(async () => true);
  try { await flushPendingProjectSaves(); } finally { off(); }
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
  let blocked = true;
  const off = registerProjectFlusher(async () => !blocked);
  let caught: unknown = null;
  try { await flushPendingProjectSaves(); } catch (error) { caught = error; }
  check('unsaved editor blocks handoff', caught instanceof PendingProjectSaveError);
  blocked = false;
  try { await flushPendingProjectSaves(); } finally { off(); }
}

{
  const saveKey = 'editor:keyed-noop';
  markProjectSavePending(saveKey);
  const off = registerProjectFlusher(async () => true);
  let caught: unknown = null;
  try { await flushPendingProjectSaves(); } catch (error) { caught = error; }
  finally { off(); }
  check('unrelated successful flusher cannot clear a keyed draft', caught instanceof PendingProjectSaveError);
  discardProjectSavePending(saveKey);
}

{
  const saveKey = 'voice-insert:1:2';
  await trackProjectWrite(Promise.reject(new Error('insert failed')), { saveKey }).catch(() => undefined);
  markProjectSavePending(saveKey);
  const offPeer = registerProjectFlusher(async () => true);
  let peerDrainPassed = false;
  try {
    await flushPendingProjectSaves({ retrySaveKey: saveKey });
    peerDrainPassed = true;
  } finally { offPeer(); }
  check('failed owner can drain peers before its retry write', peerDrainPassed);
  await trackProjectWrite(Promise.resolve(), { saveKey });
  let retryCleared = true;
  try { await flushPendingProjectSaves(); } catch { retryCleared = false; }
  check('same-owner retry clears its retained failure and dirty revisions', retryCleared);
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
  let rejectOlder!: (error: Error) => void;
  let resolveNewer!: () => void;
  const saveKey = 'editor:superseded-during-drain';
  trackProjectWrite(
    new Promise<void>((_resolve, reject) => { rejectOlder = reject; }),
    { saveKey },
  ).catch(() => undefined);
  trackProjectWrite(
    new Promise<void>((resolve) => { resolveNewer = resolve; }),
    { saveKey },
  );
  let blocked = false;
  const flushing = flushPendingProjectSaves().catch(() => { blocked = true; });
  rejectOlder(new Error('superseded request failed'));
  resolveNewer();
  await flushing;
  const snapshot = getProjectSaveStatusSnapshot();
  check(
    'active drain ignores an older keyed failure superseded by newer owner success',
    !blocked && !snapshot.dirty && snapshot.lastError === null && snapshot.inFlightCount === 0,
  );
}

{
  let release!: () => void;
  const operation = trackProjectOperation(new Promise<void>((resolve) => { release = resolve; }));
  let done = false;
  const flushing = flushPendingProjectSaves().then(() => { done = true; });
  await Promise.resolve();
  check('handoff waits for an ownerless barrier operation', !done);
  release();
  await Promise.all([operation, flushing]);
  check('handoff resumes after an ownerless barrier operation', done);
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
  let ambientBlurred = false;
  let hostBlurred = false;
  const originalDocument = globalThis.document;
  const originalHTMLElement = globalThis.HTMLElement;
  class FakeElement {
    matches(selector: string) { return selector.includes('input'); }
    blur() { ambientBlurred = true; }
  }
  class HostElement {
    matches(selector: string) { return selector.includes('textarea'); }
    blur() { hostBlurred = true; }
  }
  Object.defineProperty(globalThis, 'HTMLElement', { value: FakeElement, configurable: true });
  Object.defineProperty(globalThis, 'document', {
    value: { activeElement: new FakeElement() }, configurable: true,
  });
  const unregisterHost = registerPanelHostDocument({
    activeElement: new HostElement(),
    defaultView: { HTMLElement: HostElement },
  } as unknown as Document);
  try {
    await flushPendingProjectSaves({ commitActiveField: true });
  } finally {
    unregisterHost();
    Object.defineProperty(globalThis, 'document', { value: originalDocument, configurable: true });
    Object.defineProperty(globalThis, 'HTMLElement', { value: originalHTMLElement, configurable: true });
  }
  check(
    'handoff commits active inline fields in ambient and cross-realm panel documents',
    ambientBlurred && hostBlurred,
  );
}

console.log(`Project save coordinator tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} project save coordinator test(s) failed`);
console.log('PROJECT SAVE COORDINATOR TESTS: PASS');
