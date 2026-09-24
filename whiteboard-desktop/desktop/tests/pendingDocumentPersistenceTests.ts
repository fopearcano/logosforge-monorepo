import {
  buildPendingDocumentHttpRequest,
  PendingDocumentRevisionConflictError,
  PendingDocumentTerminalError,
  PendingDocumentPersistence,
  resourceEtag,
  validatePendingDocumentWrite,
  type PendingDocumentWrite,
  type PendingDocumentWriteSuccess,
} from '../electron/pending-document-persistence';

let passed = 0;
const failures: string[] = [];
const resourceRevision = (value: number): string => value.toString(16).padStart(32, '0');
const saved = (value: number): PendingDocumentWriteSuccess => ({
  ok: true,
  resourceRevision: resourceRevision(value),
});
const test = async (name: string, run: () => void | Promise<void>): Promise<void> => {
  try {
    await run();
    passed += 1;
  } catch (error) {
    failures.push(`${name}: ${error instanceof Error ? error.message : String(error)}`);
  }
};

const write = (
  revision: number,
  payload: Record<string, unknown> = { blocks: [] },
): PendingDocumentWrite => ({
  kind: 'whiteboard',
  documentId: '42',
  incarnation: '0123456789abcdef0123456789abcdef',
  resourceRevision: resourceRevision(1),
  revision,
  sessionId: 'renderer_session_1',
  payload,
});

await test('payloads above Chromium keepalive quota are accepted intact', () => {
  const manuscript = 'x'.repeat(256 * 1024);
  const validated = validatePendingDocumentWrite(write(1, {
    blocks: [{ id: 'large', type: 'paragraph', text: manuscript }],
  }));
  if (((validated.payload.blocks as Array<{ text: string }>)[0]?.text.length) !== manuscript.length) {
    throw new Error('Large manuscript was truncated');
  }
  const outline = validatePendingDocumentWrite({
    ...write(1),
    kind: 'outline',
    payload: { items: [{ id: 'large', summary: manuscript }] },
  });
  if (((outline.payload.items as Array<{ summary: string }>)[0]?.summary.length) !== manuscript.length) {
    throw new Error('Large outline was truncated');
  }
});

await test('endpoint and authorization are derived only from backend status', () => {
  const request = buildPendingDocumentHttpRequest(write(1), {
    state: 'connected',
    baseUrl: 'http://127.0.0.1:9123/ignored/path',
    authToken: 'main-secret',
  });
  if (request.url !== 'http://127.0.0.1:9123/api/whiteboard?doc=42') {
    throw new Error(`Unexpected endpoint ${request.url}`);
  }
  if (request.headers.Authorization !== 'Bearer main-secret') {
    throw new Error('Main-process authorization was omitted');
  }
  if (request.headers['X-LogosForge-Document-Incarnation'] !== '0123456789abcdef0123456789abcdef') {
    throw new Error('Captured document incarnation was omitted');
  }
  if (request.headers['If-Match'] !== resourceEtag(
    'whiteboard',
    '0123456789abcdef0123456789abcdef',
    resourceRevision(1),
  )) {
    throw new Error('Resource revision precondition was omitted');
  }
  if (request.headers['X-LogosForge-Mutation-Id'] !== 'renderer_session_1_1') {
    throw new Error('Stable mutation id was omitted');
  }
  const orderedRequest = buildPendingDocumentHttpRequest(write(1), {
    state: 'connected',
    baseUrl: 'http://127.0.0.1:9123',
    authToken: 'main-secret',
  }, 17);
  if (orderedRequest.headers['X-LogosForge-Persistence-Order'] !== '17') {
    throw new Error('Main-process persistence order was omitted');
  }
});

await test('invalid ids, kinds, and shapes are rejected synchronously', () => {
  const invalid = [
    { ...write(1), documentId: '../other' },
    { ...write(1), kind: 'arbitrary-route' },
    { ...write(1), incarnation: '../reused' },
    { ...write(1), resourceRevision: 'not-a-revision' },
    { ...write(1), sessionId: 's'.repeat(111) },
    { ...write(1), payload: { url: 'https://example.com' } },
  ];
  for (const value of invalid) {
    let rejected = false;
    try {
      validatePendingDocumentWrite(value);
    } catch {
      rejected = true;
    }
    if (!rejected) throw new Error('Invalid IPC payload was accepted');
  }
});

await test('same-document writes are FIFO and drain waits for the active request', async () => {
  let release!: () => void;
  let markStarted!: () => void;
  const blocked = new Promise<void>((resolve) => { release = resolve; });
  const firstStarted = new Promise<void>((resolve) => { markStarted = resolve; });
  const calls: number[] = [];
  const persistence = new PendingDocumentPersistence(async (pending) => {
    calls.push(pending.revision);
    if (pending.revision === 1) {
      markStarted();
      await blocked;
    }
    return saved(pending.revision + 1);
  });
  const first = persistence.enqueue(write(1));
  await firstStarted;
  const second = persistence.enqueue(write(2));
  const draining = persistence.drain();
  if (calls.join(',') !== '1' || persistence.pendingCount !== 2) {
    throw new Error('Second write was not held behind the first');
  }
  release();
  await Promise.all([first, second, draining]);
  if (calls.join(',') !== '1,2' || persistence.pendingCount !== 0) {
    throw new Error(`Unexpected FIFO result ${calls.join(',')}`);
  }
});

await test('a newer revision suppresses an older message delivered late', async () => {
  const calls: number[] = [];
  const persistence = new PendingDocumentPersistence(async (pending) => {
    calls.push(pending.revision);
    return saved(pending.revision + 1);
  });
  const newer = persistence.enqueue(write(2));
  const older = persistence.enqueue(write(1));
  await Promise.all([newer, older]);
  if (calls.join(',') !== '2') throw new Error(`Stale write was persisted: ${calls.join(',')}`);
});

await test('a failed write does not poison a later retry', async () => {
  const calls: number[] = [];
  let firstAttempt = true;
  const persistence = new PendingDocumentPersistence(async (pending) => {
    calls.push(pending.revision);
    if (pending.revision === 1 && firstAttempt) {
      firstAttempt = false;
      throw new Error('offline');
    }
    return saved(pending.revision + 1);
  });
  await persistence.enqueue(write(1)).catch(() => {});
  await persistence.enqueue(write(2));
  if (calls.join(',') !== '1,1,2') throw new Error('Later write did not run after recovery');
});

await test('a failed unload snapshot is retained for a later successful drain', async () => {
  let attempts = 0;
  const dispatches: number[] = [];
  const persistence = new PendingDocumentPersistence(async (_pending, _signal, dispatchSequence) => {
    attempts += 1;
    dispatches.push(dispatchSequence);
    if (attempts === 1) throw new Error('backend restarting');
    return saved(8);
  });
  await persistence.enqueue(write(7)).catch(() => {});
  await persistence.drain();
  if (attempts !== 2 || dispatches.join(',') !== '1,1' || persistence.pendingCount !== 0) {
    throw new Error(
      `Retained snapshot was not retried idempotently (${attempts}; ${dispatches.join(',')})`,
    );
  }
});

await test('a deferred latest failure is promoted and retried by the next drain', async () => {
  const calls: number[] = [];
  let oldAttempts = 0;
  let latestAttempts = 0;
  const persistence = new PendingDocumentPersistence(async (pending) => {
    calls.push(pending.revision);
    if (pending.revision === 1) {
      oldAttempts += 1;
      if (oldAttempts < 3) throw new Error('old response uncertain');
    } else if (pending.revision === 2) {
      latestAttempts += 1;
      if (latestAttempts === 1) throw new Error('latest response uncertain');
    }
    return saved(pending.revision + 1);
  });
  await persistence.enqueue(write(1)).catch(() => {});
  await persistence.enqueue(write(2)).catch(() => {});
  await persistence.drain().catch(() => {});
  await persistence.drain();
  if (calls.join(',') !== '1,1,1,2,2' || persistence.pendingCount !== 0) {
    throw new Error(`Deferred snapshot was stranded: ${calls.join(',')}`);
  }
});

await test('renderer retry of the same write reuses the recovered acknowledgement', async () => {
  let attempts = 0;
  const persistence = new PendingDocumentPersistence(async (pending) => {
    attempts += 1;
    if (attempts === 1) throw new Error('response lost');
    return saved(pending.revision + 1);
  });
  await persistence.enqueue(write(4)).catch(() => {});
  const result = await persistence.enqueue(write(4));
  if (attempts !== 2 || result.resourceRevision !== resourceRevision(5)) {
    throw new Error(`Exact retry was dispatched again (${attempts})`);
  }
});

await test('successful writes chain the returned resource revision', async () => {
  const expected: string[] = [];
  const persistence = new PendingDocumentPersistence(async (pending, _signal, _order, revision) => {
    expected.push(revision);
    return saved(pending.revision + 1);
  });
  await persistence.enqueue(write(1));
  await persistence.enqueue(write(2));
  if (expected.join(',') !== `${resourceRevision(1)},${resourceRevision(2)}`) {
    throw new Error(`Writes did not chain validators: ${expected.join(',')}`);
  }
});

await test('revision conflicts are terminal and never blindly retried by drain', async () => {
  let attempts = 0;
  const persistence = new PendingDocumentPersistence(async () => {
    attempts += 1;
    throw new PendingDocumentRevisionConflictError(
      'The document changed outside this window.',
      resourceRevision(9),
      resourceEtag('whiteboard', '0123456789abcdef0123456789abcdef', resourceRevision(9)),
    );
  });
  await persistence.enqueue(write(3)).catch(() => {});
  await persistence.drain();
  if (attempts !== 1) throw new Error(`Conflict was retried ${attempts} times`);
  const [conflict] = persistence.listConflicts();
  if (
    !conflict
    || conflict.write.revision !== 3
    || conflict.error.currentRevision !== resourceRevision(9)
    || conflict.error.currentEtag !== resourceEtag(
      'whiteboard',
      write(3).incarnation,
      resourceRevision(9),
    )
  ) throw new Error('Conflict recovery did not preserve the rejected snapshot and validators');
  const again = persistence.listConflicts()[0];
  if (!again || again.conflictId !== conflict.conflictId || again.version !== conflict.version) {
    throw new Error('Repeated recovery enumeration changed the receipt');
  }
  let strictRejected = false;
  try {
    await persistence.drainStrict();
  } catch {
    strictRejected = true;
  }
  if (!strictRejected) throw new Error('Strict drain ignored an unresolved recovery');

  const updated = persistence.retainConflict({
    recovery: conflict,
    write: write(4, { title: 'Newest local title' }),
  });
  if (!updated.ok || !updated.recovery || updated.recovery.version <= conflict.version) {
    throw new Error('Conflict update did not advance its main-owned generation');
  }
  if (!persistence.hasConflict(updated.recovery) || persistence.hasConflict(conflict)) {
    throw new Error('Exact conflict validation did not track the newest receipt');
  }
  if (persistence.acknowledgeConflict(conflict)) {
    throw new Error('A stale receipt acknowledged a newer recovery');
  }
  if (!persistence.acknowledgeConflict(updated.recovery)) {
    throw new Error('The exact newest recovery could not be acknowledged');
  }
  await persistence.drainStrict();
});

await test('retry-time conflict retains the deferred newest cumulative snapshot', async () => {
  let attempts = 0;
  const persistence = new PendingDocumentPersistence(async () => {
    attempts += 1;
    if (attempts === 1) throw new Error('response uncertain');
    throw new PendingDocumentRevisionConflictError(
      'changed elsewhere',
      resourceRevision(9),
      resourceEtag('whiteboard', write(1).incarnation, resourceRevision(9)),
    );
  });
  await persistence.enqueue(write(1, { title: 'Old' })).catch(() => {});
  await persistence.enqueue(write(2, {
    title: 'Newest',
    blocks: [{ id: 'local', type: 'paragraph', text: 'complete local view' }],
  })).catch(() => {});
  await persistence.drain();
  const [conflict] = persistence.listConflicts();
  if (
    attempts !== 2
    || conflict?.write.revision !== 2
    || conflict.write.payload.title !== 'Newest'
    || !Array.isArray(conflict.write.payload.blocks)
  ) throw new Error('Retry conflict did not promote the newest cumulative snapshot');
});

await test('stale and old-session conflict refreshes cannot overwrite the newest rescue', async () => {
  let attempts = 0;
  const persistence = new PendingDocumentPersistence(async () => {
    attempts += 1;
    throw new PendingDocumentRevisionConflictError(
      'changed elsewhere',
      resourceRevision(9),
      resourceEtag('whiteboard', write(1).incarnation, resourceRevision(9)),
    );
  });
  await persistence.enqueue(write(10, { title: 'Revision ten' })).catch(() => {});
  const first = persistence.listConflicts()[0];
  if (!first) throw new Error('Initial conflict was not retained');
  await persistence.enqueue(write(9, { title: 'Delayed revision nine' })).catch(() => {});
  let current = persistence.listConflicts()[0];
  if (current?.write.payload.title !== 'Revision ten') {
    throw new Error('A delayed older renderer revision overwrote the rescue');
  }
  const replacementWrite = {
    ...write(1, { title: 'Hydrated renderer edit' }),
    sessionId: 'renderer_session_2',
  };
  const replacement = persistence.retainConflict({ recovery: current, write: replacementWrite });
  if (!replacement.ok || !replacement.recovery) throw new Error('Hydrated renderer could not refresh recovery');
  await persistence.enqueue(write(11, { title: 'Retiring renderer pagehide' })).catch(() => {});
  current = persistence.listConflicts()[0];
  if (
    attempts !== 1
    || current?.write.sessionId !== 'renderer_session_2'
    || current.write.payload.title !== 'Hydrated renderer edit'
  ) throw new Error('A retiring renderer overwrote the hydrated renderer recovery');
});

await test('a queued newer write is promoted when its in-flight predecessor becomes terminal', async () => {
  let release!: () => void;
  let started!: () => void;
  const blocked = new Promise<void>((resolve) => { release = resolve; });
  const firstStarted = new Promise<void>((resolve) => { started = resolve; });
  const calls: number[] = [];
  const persistence = new PendingDocumentPersistence(async (pending) => {
    calls.push(pending.revision);
    if (pending.revision === 1) {
      started();
      await blocked;
      throw new PendingDocumentTerminalError('rejected', 'request_rejected', 409);
    }
    return saved(3);
  });
  const first = persistence.enqueue(write(1, { title: 'First' })).catch(() => {});
  await firstStarted;
  const newest = persistence.enqueue(write(2, { title: 'Newest queued' })).catch(() => {});
  release();
  await Promise.all([first, newest]);
  const [conflict] = persistence.listConflicts();
  if (calls.join(',') !== '1' || conflict?.write.payload.title !== 'Newest queued') {
    throw new Error(`Queued write escaped the terminal ledger: ${calls.join(',')}`);
  }
});

await test('deterministic protocol failures are terminal and never retried by drain', async () => {
  let attempts = 0;
  const persistence = new PendingDocumentPersistence(async () => {
    attempts += 1;
    throw new PendingDocumentTerminalError(
      'This mutation id was already used for a different request. (HTTP 409).',
      'mutation_id_conflict',
      409,
    );
  });
  await persistence.enqueue(write(4)).catch(() => {});
  await persistence.drain();
  await persistence.drain();
  if (attempts !== 1) throw new Error(`Terminal protocol failure was retried ${attempts} times`);
});

await test('two-phase delete fences queued writes and commits without retrying them', async () => {
  let attempts = 0;
  let releaseFirst!: () => void;
  let firstStarted!: () => void;
  const blocked = new Promise<void>((resolve) => { releaseFirst = resolve; });
  const started = new Promise<void>((resolve) => { firstStarted = resolve; });
  const persistence = new PendingDocumentPersistence(async (pending) => {
    attempts += 1;
    if (pending.revision === 11) {
      firstStarted();
      await blocked;
    }
    return saved(pending.revision + 1);
  });
  const first = persistence.enqueue(write(11));
  await started;
  const queued = persistence.enqueue(write(12)).catch(() => {});
  const begun = persistence.beginDocumentDelete('42', write(1).incarnation);
  releaseFirst();
  const [, , floor] = await Promise.all([first, queued, begun]);
  if (attempts !== 1) throw new Error('A queued write crossed the DELETE fence');
  if (floor.whiteboard !== 2 || floor.outline !== 0) {
    throw new Error(`DELETE did not expose issued dispatch floors: ${JSON.stringify(floor)}`);
  }
  persistence.commitDocumentDelete('42', write(1).incarnation);
  await persistence.drain();
  if (attempts !== 1 || persistence.pendingCount !== 0) {
    throw new Error(`Deleted document was retried (${attempts} writer calls)`);
  }
  await persistence.enqueue(write(12));
  if (attempts !== 1) throw new Error('A delayed deleted-incarnation write was persisted');
  await persistence.enqueue({
    ...write(13),
    incarnation: 'abcdef0123456789abcdef0123456789',
  });
  if (attempts !== 2) throw new Error('A reused numeric document id stayed tombstoned');
});

await test('canceling a failed delete preserves and retries its newest snapshot', async () => {
  let attempts = 0;
  const persistence = new PendingDocumentPersistence(async () => {
    attempts += 1;
    return saved(attempts + 1);
  });
  await persistence.beginDocumentDelete('42', write(1).incarnation);
  await persistence.enqueue(write(21)).catch(() => {});
  if (attempts !== 0) throw new Error('Writer ran while DELETE fence was active');
  persistence.cancelDocumentDelete('42', write(1).incarnation);
  await persistence.drain();
  if (attempts !== 1) throw new Error('Canceled DELETE did not restore the retained snapshot');
});

await test('a stale-incarnation delete cannot erase or suppress a reused-id write', async () => {
  const incarnationA = write(1).incarnation;
  const incarnationB = 'abcdef0123456789abcdef0123456789';
  let attempts = 0;
  const dispatches: number[] = [];
  const persistence = new PendingDocumentPersistence(async (_pending, _signal, dispatchSequence) => {
    attempts += 1;
    dispatches.push(dispatchSequence);
    if (attempts === 1) throw new Error('new incarnation temporarily offline');
    return saved(attempts + 1);
  });
  await persistence.beginDocumentDelete('42', incarnationA);
  const reused = { ...write(1, { title: 'New incarnation' }), incarnation: incarnationB };
  await persistence.enqueue(reused).catch(() => {});
  persistence.commitDocumentDelete('42', incarnationA);
  await persistence.drain();
  await persistence.enqueue(reused);
  await persistence.enqueue({ ...reused, revision: 2, payload: { title: 'Second edit' } });
  if (attempts !== 3 || dispatches.join(',') !== '1,1,3') {
    throw new Error(
      `Stale delete corrupted reused-id retry/order state: ${attempts}; ${dispatches.join(',')}`,
    );
  }
});

await test('deleting a reused id clears only the matching incarnation conflict', async () => {
  const incarnationA = write(1).incarnation;
  const incarnationB = 'abcdef0123456789abcdef0123456789';
  const persistence = new PendingDocumentPersistence(async () => {
    throw new PendingDocumentRevisionConflictError(
      'old incarnation changed',
      resourceRevision(9),
      resourceEtag('whiteboard', incarnationA, resourceRevision(9)),
    );
  });
  await persistence.enqueue(write(1, { title: 'Old incarnation rescue' })).catch(() => {});
  await persistence.beginDocumentDelete('42', incarnationB);
  persistence.commitDocumentDelete('42', incarnationB);
  const [conflict] = persistence.listConflicts();
  if (conflict?.incarnation !== incarnationA || conflict.write.payload.title !== 'Old incarnation rescue') {
    throw new Error('Deleting the reused id erased the old-incarnation rescue');
  }
});

await test('a stalled writer times out, aborts, and cannot poison a later revision', async () => {
  let shouldHang = true;
  let aborted = false;
  const calls: number[] = [];
  const dispatches: number[] = [];
  const persistence = new PendingDocumentPersistence(async (pending, signal, dispatchSequence) => {
    calls.push(pending.revision);
    dispatches.push(dispatchSequence);
    if (!shouldHang) return saved(pending.revision + 1);
    await new Promise<void>(() => {
      signal.addEventListener('abort', () => { aborted = true; }, { once: true });
    });
    return saved(pending.revision + 1);
  }, 20);
  await persistence.enqueue(write(31)).catch(() => {});
  if (!aborted) throw new Error('Timed-out writer was not aborted');
  shouldHang = false;
  await persistence.enqueue(write(32));
  await persistence.drain();
  if (calls.join(',') !== '31,31,32' || dispatches.join(',') !== '1,1,2') {
    throw new Error(
      `Later revision was poisoned: revisions=${calls.join(',')} orders=${dispatches.join(',')}`,
    );
  }
});

console.log(`Pending document persistence tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} pending persistence test(s) failed`);
console.log('PENDING DOCUMENT PERSISTENCE TESTS: PASS');
