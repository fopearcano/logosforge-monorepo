/**
 * Pending document-save coordination tests. Pure/headless:
 * `npm run test:document-state`.
 */

import {
  captureDocumentIdentity,
  discardPendingDocSaves,
  flushPendingDocSaves,
  PendingDocumentSaveError,
  prepareDocumentHandoff,
  registerDocDiscarder,
  registerDocFlusher,
  blockDocumentMutations,
  resumeDocumentMutations,
  runPendingDocWrite,
  runSerializedPendingDocWrite,
  setCurrentDocId,
  setCurrentDocumentIdentity,
  trackPendingDocWrite,
  waitForPendingDocWrites,
} from './currentDocument';
import {
  beginDocumentCloseBarrier,
  releaseDocumentCloseBarrier,
} from '../features/whiteboard/documentOperationGuard';

let passed = 0;
const failures: string[] = [];

function check(label: string, condition: boolean): void {
  if (condition) passed += 1;
  else failures.push(label);
}

// A captured identity remains tied to the old generation even when SQLite
// later reuses the same numeric id for a different project.
{
  const original = '11111111111111111111111111111111';
  const replacement = '22222222222222222222222222222222';
  setCurrentDocumentIdentity('42', original);
  const captured = captureDocumentIdentity();
  setCurrentDocumentIdentity('42', replacement);
  check(
    'captured document identity survives numeric id reuse',
    captured.documentId === '42' && captured.incarnation === original,
  );
  check(
    'active identity rotates for the replacement document',
    captureDocumentIdentity().incarnation === replacement,
  );
  setCurrentDocId('');
}

// Same-comment mutations are last-action-wins FIFO and queued work participates
// in the document handoff barrier before its transport starts.
{
  const calls: string[] = [];
  let releaseFirst!: () => void;
  let markFirstStarted!: () => void;
  const firstGate = new Promise<void>((resolve) => { releaseFirst = resolve; });
  const firstStarted = new Promise<void>((resolve) => { markFirstStarted = resolve; });
  const first = runSerializedPendingDocWrite('comment:c1', async () => {
    calls.push('resolve');
    markFirstStarted();
    await firstGate;
  }, '42');
  await firstStarted;
  const second = runSerializedPendingDocWrite('comment:c1', async () => {
    calls.push('unresolve');
  }, '42');
  check('same-comment second mutation waits for the first', calls.join(',') === 'resolve');
  let drained = false;
  const draining = waitForPendingDocWrites().then(() => { drained = true; });
  await Promise.resolve();
  check('queued comment mutation holds the read/handoff barrier', !drained);
  releaseFirst();
  await Promise.all([first, second, draining]);
  check('same-comment mutations execute in user order', calls.join(',') === 'resolve,unresolve');
}

// Same-document recovery waits for direct writes but ignores their failure so a
// failed comment/PSYKE mutation cannot blank the manuscript recovery surface.
{
  let release!: () => void;
  const direct = new Promise<void>((resolve) => { release = resolve; });
  trackPendingDocWrite(direct);
  let recovered = false;
  const recovery = waitForPendingDocWrites().then(() => { recovered = true; });
  await Promise.resolve();
  check('same-document recovery waits for an immediate write', !recovered);
  release();
  await recovery;
  check('same-document recovery continues after the write settles', recovered);
}

// A newly mounted read (comments/PSYKE) cannot take its GET snapshot before the
// retiring view's direct PUT has settled.
{
  let release!: () => void;
  const order: string[] = [];
  const retiringWrite = new Promise<void>((resolve) => { release = resolve; })
    .then(() => { order.push('PUT settled'); });
  trackPendingDocWrite(retiringWrite);
  const freshRead = waitForPendingDocWrites().then(() => { order.push('GET started'); });
  await Promise.resolve();
  check('remount read stays behind the retiring mutation', order.length === 0);
  release();
  await freshRead;
  check('remount read starts only after the mutation settles', order.join(',') === 'PUT settled,GET started');
}

// A deletion tombstone rejects a direct mutation before its transport starts.
{
  const documentId = '42';
  let started = false;
  blockDocumentMutations(documentId);
  await runPendingDocWrite(async () => { started = true; }, documentId).catch(() => {});
  check('delete tombstone blocks direct document mutation transport', !started);
  resumeDocumentMutations(documentId);
  await runPendingDocWrite(async () => { started = true; }, documentId);
  check('failed delete re-enables direct document mutations', started);
}

// A close/reload barrier rejects a fresh direct mutation before transport.
{
  let started = false;
  beginDocumentCloseBarrier(701);
  await runPendingDocWrite(async () => { started = true; }, '42').catch(() => {});
  check('close barrier blocks direct document mutation transport', !started);
  releaseDocumentCloseBarrier(701);
}

// Immediate doc-scoped writes participate in the same handoff barrier.
{
  let release!: () => void;
  const deferred = new Promise<void>((resolve) => {
    release = resolve;
  });
  trackPendingDocWrite(deferred);
  let drained = false;
  const draining = flushPendingDocSaves().then(() => {
    drained = true;
  });
  await Promise.resolve();
  check('handoff waits for an immediate write', !drained);
  release();
  await draining;
  check('handoff continues after the immediate write settles', drained);
}

// A failing immediate write blocks the handoff just like a failing store flush.
{
  const failed = Promise.reject(new Error('comment write failed'));
  // Attach the caller-side handler too; the coordinator still observes the raw
  // write without causing an unhandled-rejection warning in Node.
  void failed.catch(() => {});
  trackPendingDocWrite(failed);
  let caught: unknown = null;
  try {
    await flushPendingDocSaves();
  } catch (err) {
    caught = err;
  }
  check('failed immediate write rejects the handoff', caught instanceof PendingDocumentSaveError);
}

// Writes spawned while an earlier write is settling are drained in the same
// barrier, rather than leaking past the final active-id handoff.
{
  let releaseFirst!: () => void;
  let releaseSecond!: () => void;
  const first = new Promise<void>((resolve) => {
    releaseFirst = resolve;
  });
  const second = new Promise<void>((resolve) => {
    releaseSecond = resolve;
  });
  trackPendingDocWrite(first);
  void first.then(() => {
    trackPendingDocWrite(second);
  });
  let drained = false;
  const draining = flushPendingDocSaves().then(() => {
    drained = true;
  });
  releaseFirst();
  await Promise.resolve();
  await Promise.resolve();
  check('handoff notices a write spawned during draining', !drained);
  releaseSecond();
  await draining;
  check('handoff completes after the spawned write', drained);
}

// A store mounted while another store is flushing also joins the active
// barrier; this covers opening/editing a previously hidden panel mid-handoff.
{
  let releaseFirst!: () => void;
  const firstDone = new Promise<void>((resolve) => {
    releaseFirst = resolve;
  });
  const calls: string[] = [];
  const unregisterFirst = registerDocFlusher(async () => {
    calls.push('first');
    await firstDone;
  });
  const draining = flushPendingDocSaves();
  await Promise.resolve();
  const unregisterLate = registerDocFlusher(async () => {
    calls.push('late');
  });
  releaseFirst();
  try {
    await draining;
  } finally {
    unregisterFirst();
    unregisterLate();
  }
  check(
    'handoff drains a store registered while it was waiting',
    calls.includes('late') && calls[0] === 'first',
  );
}

// Async target preparation gets a drain on both sides, covering edits made
// while the target document is being fetched/created.
{
  const calls: string[] = [];
  const unregister = registerDocFlusher(async () => {
    calls.push(`flush-${calls.filter((call) => call.startsWith('flush')).length + 1}`);
  });
  let value = '';
  try {
    value = await prepareDocumentHandoff(async () => {
      calls.push('prepare');
      return 'target';
    });
  } finally {
    unregister();
  }
  check('handoff drains before and after target preparation', calls.join(',') === 'flush-1,prepare,flush-2');
  check('handoff returns the prepared target', value === 'target');
}

// Explicit deletion clears every participant and tolerates one bad cleanup.
{
  const calls: string[] = [];
  const unregisterFirst = registerDocDiscarder(() => {
    calls.push('first');
    throw new Error('cleanup failed');
  });
  const unregisterSecond = registerDocDiscarder(() => {
    calls.push('second');
  });
  try {
    discardPendingDocSaves();
    check('discard invokes every store despite a cleanup error', calls.join(',') === 'first,second');
  } finally {
    unregisterFirst();
    unregisterSecond();
  }
}

// Writes that belonged to an explicitly deleted document no longer hold up the
// replacement document; their own callers still observe their eventual result.
{
  let release!: () => void;
  const staleWrite = new Promise<void>((resolve) => {
    release = resolve;
  });
  trackPendingDocWrite(staleWrite);
  discardPendingDocSaves();
  let drained = false;
  await flushPendingDocSaves().then(() => {
    drained = true;
  });
  check('discard removes deleted-document writes from the handoff barrier', drained);
  release();
  await staleWrite;
}

// All registered stores are drained on the successful path.
{
  const calls: string[] = [];
  const unregisterManuscript = registerDocFlusher(async () => {
    calls.push('manuscript');
  });
  const unregisterOutline = registerDocFlusher(async () => {
    calls.push('outline');
  });
  try {
    await flushPendingDocSaves();
    check('successful flush invokes every store', calls.join(',') === 'manuscript,outline');
  } finally {
    unregisterManuscript();
    unregisterOutline();
  }
}

// A failed first drain blocks target preparation entirely.
{
  const unregister = registerDocFlusher(async () => {
    throw new Error('offline');
  });
  let prepared = false;
  let rejected = false;
  try {
    await prepareDocumentHandoff(async () => {
      prepared = true;
      return 'unreachable';
    });
  } catch {
    rejected = true;
  } finally {
    unregister();
  }
  check('handoff rejects when its first drain fails', rejected);
  check('failed first drain prevents target preparation', !prepared);
}

// A failed second drain rejects after preparation, so the caller never commits
// the new active id while edits made during preparation remain unsaved.
{
  let flushCount = 0;
  const unregister = registerDocFlusher(async () => {
    flushCount += 1;
    if (flushCount === 2) throw new Error('late save failed');
  });
  let prepared = false;
  let rejected = false;
  try {
    await prepareDocumentHandoff(async () => {
      prepared = true;
      return 'prepared target';
    });
  } catch {
    rejected = true;
  } finally {
    unregister();
  }
  check('handoff prepares its target before the second drain', prepared);
  check('failed second drain prevents handoff completion', rejected);
}

// A rejection is propagated only after every store has had a chance to flush.
{
  const calls: string[] = [];
  const diskError = new Error('disk full');
  const unregisterFailing = registerDocFlusher(async () => {
    calls.push('failing');
    throw diskError;
  });
  const unregisterSuccessful = registerDocFlusher(async () => {
    await Promise.resolve();
    calls.push('successful');
  });
  let caught: unknown = null;
  try {
    await flushPendingDocSaves();
  } catch (err) {
    caught = err;
  } finally {
    unregisterFailing();
    unregisterSuccessful();
  }

  check('failed flush still waits for every store', calls.includes('failing') && calls.includes('successful'));
  check('failed flush rejects with the coordinator error', caught instanceof PendingDocumentSaveError);
  check(
    'coordinator error retains the underlying failure',
    caught instanceof PendingDocumentSaveError && caught.errors.length === 1 && caught.errors[0] === diskError,
  );
}

// Even a contract-violating synchronous throw cannot skip later flushers.
{
  const calls: string[] = [];
  const unregisterThrowing = registerDocFlusher(() => {
    calls.push('sync-throw');
    throw new Error('synchronous failure');
  });
  const unregisterLater = registerDocFlusher(async () => {
    calls.push('later');
  });
  try {
    await flushPendingDocSaves().catch(() => {});
  } finally {
    unregisterThrowing();
    unregisterLater();
  }
  check('synchronous flusher failure cannot skip another store', calls.join(',') === 'sync-throw,later');
}

console.log(`Document state tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} document state test(s) failed`);
console.log('DOCUMENT STATE TESTS: PASS');
