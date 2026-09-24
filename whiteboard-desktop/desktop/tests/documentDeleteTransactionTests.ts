import { runDocumentDeleteTransaction } from '../electron/document-delete-transaction';

let passed = 0;
const failures: string[] = [];
const test = async (name: string, run: () => Promise<void>): Promise<void> => {
  try {
    await run();
    passed += 1;
  } catch (error) {
    failures.push(`${name}: ${error instanceof Error ? error.message : String(error)}`);
  }
};

const floor = { whiteboard: 7, outline: 4 };

await test('successful delete commits the main fence', async () => {
  const events: string[] = [];
  await runDocumentDeleteTransaction({
    begin: async () => { events.push('begin'); return floor; },
    deleteBackend: async (received) => {
      events.push(`delete:${received.whiteboard}:${received.outline}`);
    },
    backendDocumentExists: async () => { throw new Error('unexpected reconcile'); },
    commit: () => events.push('commit'),
    cancel: () => events.push('cancel'),
  });
  if (events.join(',') !== 'begin,delete:7:4,commit') {
    throw new Error(`Unexpected transaction: ${events.join(',')}`);
  }
});

await test('lost delete responses reconcile absence and commit', async () => {
  let attempts = 0;
  let committed = false;
  let canceled = false;
  await runDocumentDeleteTransaction({
    begin: async () => floor,
    deleteBackend: async () => { attempts += 1; throw new Error('lost response'); },
    backendDocumentExists: async () => false,
    commit: () => { committed = true; },
    cancel: () => { canceled = true; },
  });
  if (attempts !== 2 || !committed || canceled) {
    throw new Error('An authoritatively absent document did not commit after retry');
  }
});

await test('durable local commit retries without repeating a successful backend delete', async () => {
  let deleteAttempts = 0;
  let commitAttempts = 0;
  const waits: number[] = [];
  await runDocumentDeleteTransaction({
    begin: async () => floor,
    deleteBackend: async () => { deleteAttempts += 1; },
    backendDocumentExists: async () => { throw new Error('unexpected reconcile'); },
    commit: () => {
      commitAttempts += 1;
      if (commitAttempts < 3) throw new Error('journal temporarily unavailable');
    },
    cancel: () => { throw new Error('unexpected cancel'); },
    waitBeforeCommitRetry: async (attempt) => { waits.push(attempt); },
  });
  if (deleteAttempts !== 1 || commitAttempts !== 3 || waits.join(',') !== '1,2') {
    throw new Error(
      `Local commit retry crossed the backend boundary: deletes=${deleteAttempts}, commits=${commitAttempts}`,
    );
  }
});

await test('permanent local commit failure is bounded and keeps the delete fence fail-closed', async () => {
  let deleteAttempts = 0;
  let commitAttempts = 0;
  let canceled = false;
  let rejected = false;
  try {
    await runDocumentDeleteTransaction({
      begin: async () => floor,
      deleteBackend: async () => { deleteAttempts += 1; },
      backendDocumentExists: async () => { throw new Error('unexpected reconcile'); },
      commit: () => { commitAttempts += 1; throw new Error('disk remains full'); },
      cancel: () => { canceled = true; },
      waitBeforeCommitRetry: async () => {},
    });
  } catch {
    rejected = true;
  }
  if (!rejected || deleteAttempts !== 1 || commitAttempts !== 3 || canceled) {
    throw new Error(
      `Permanent local failure was not bounded safely: deletes=${deleteAttempts}, commits=${commitAttempts}`,
    );
  }
});

await test('confirmed live document cancels the fence after two failures', async () => {
  let canceled = false;
  let rejected = false;
  try {
    await runDocumentDeleteTransaction({
      begin: async () => floor,
      deleteBackend: async () => { throw new Error('offline'); },
      backendDocumentExists: async () => true,
      commit: () => { throw new Error('unexpected commit'); },
      cancel: () => { canceled = true; },
    });
  } catch {
    rejected = true;
  }
  if (!rejected || !canceled) throw new Error('Failed delete did not cancel its fence');
});

await test('an uncertain probe keeps the fence until a deferred delete settles', async () => {
  const events: string[] = [];
  let backendDeleted = false;
  let releaseDeferredDelete!: () => void;
  const deferredDelete = new Promise<void>((resolve) => {
    releaseDeferredDelete = () => {
      backendDeleted = true;
      events.push('server-delete-settled');
      resolve();
    };
  });
  let deleteAttempts = 0;
  let probeAttempts = 0;
  let deferredDeleteStarted = false;
  let fenceActive = false;
  let resumedWrites = 0;
  let canceled = false;
  let committed = false;

  await runDocumentDeleteTransaction({
    begin: async () => {
      fenceActive = true;
      events.push('begin');
      return floor;
    },
    deleteBackend: async () => {
      deleteAttempts += 1;
      events.push(`delete-${deleteAttempts}`);
      if (backendDeleted) return;
      // Model a client deadline: the request reports timeout while its server
      // handler remains capable of completing later.
      if (deleteAttempts === 1) deferredDeleteStarted = true;
      throw new Error('timeout');
    },
    backendDocumentExists: async () => {
      probeAttempts += 1;
      events.push(`probe-${probeAttempts}`);
      if (probeAttempts === 1) throw new Error('backend temporarily unavailable');
      return !backendDeleted;
    },
    commit: () => {
      committed = true;
      fenceActive = false;
      events.push('commit');
    },
    cancel: () => {
      canceled = true;
      fenceActive = false;
      events.push('cancel');
    },
    waitBeforeRetry: async (attempt) => {
      events.push(`wait-${attempt}`);
      // Renderer queues may only resume after cancel. The uncertain state must
      // therefore reject this simulated write while the server DELETE settles.
      if (!fenceActive) resumedWrites += 1;
      if (!deferredDeleteStarted) throw new Error('No deferred server DELETE was active');
      releaseDeferredDelete();
      await deferredDelete;
    },
  });

  if (!committed || canceled || resumedWrites !== 0 || fenceActive) {
    throw new Error('Uncertain delete released its fence before terminal reconciliation');
  }
  if (deleteAttempts !== 3 || probeAttempts !== 1) {
    throw new Error(`Unexpected retry counts: deletes=${deleteAttempts}, probes=${probeAttempts}`);
  }
  if (events.join(',') !== (
    'begin,delete-1,delete-2,probe-1,wait-1,server-delete-settled,delete-3,commit'
  )) {
    throw new Error(`Unexpected uncertain-delete transaction: ${events.join(',')}`);
  }
});

console.log(`Document delete transaction tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} document delete transaction test(s) failed`);
console.log('DOCUMENT DELETE TRANSACTION TESTS: PASS');
