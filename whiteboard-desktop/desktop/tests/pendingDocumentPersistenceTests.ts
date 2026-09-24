import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';

import {
  buildPendingDocumentHttpRequest,
  PendingDocumentRevisionConflictError,
  PendingDocumentTerminalError,
  PendingDocumentPersistence,
  resourceEtag,
  validatePendingDocumentWrite,
  type PendingDocumentWrite,
  type PendingDocumentWriteSuccess,
  type PendingDocumentRecoveryJournal,
  type PendingDocumentRecoveryJournalSnapshot,
} from '../electron/pending-document-persistence';
import {
  FilePendingDocumentRecoveryJournal,
  MAX_PENDING_DOCUMENT_RECOVERY_JOURNAL_BYTES,
} from '../electron/pending-document-recovery-journal';

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
const tempRoots: string[] = [];
const makeTempRoot = (): string => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'logosforge-recovery-journal-'));
  tempRoots.push(root);
  return root;
};

if (MAX_PENDING_DOCUMENT_RECOVERY_JOURNAL_BYTES !== 256 * 1024 * 1024) {
  throw new Error('Recovery journal main-thread I/O cap changed without test review');
}

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

await test('disk journal survives a whole-process restart with exact receipt semantics', async () => {
  const root = makeTempRoot();
  const backendSecret = 'backend-auth-token-must-never-be-journaled';
  const conflictWriter = async (pending: PendingDocumentWrite): Promise<PendingDocumentWriteSuccess> => {
    void backendSecret;
    throw new PendingDocumentRevisionConflictError(
      'changed elsewhere',
      resourceRevision(9),
      resourceEtag(pending.kind, pending.incarnation, resourceRevision(9)),
    );
  };
  const firstJournal = new FilePendingDocumentRecoveryJournal(root);
  const firstProcess = new PendingDocumentPersistence(conflictWriter, 10_000, firstJournal);
  await firstProcess.enqueue(write(7, { title: 'Crash-safe local title' })).catch(() => {});
  const original = firstProcess.listConflicts()[0];
  if (!original) throw new Error('Initial conflict was not journaled');

  const journalFiles = fs.readdirSync(firstJournal.directoryPath)
    .filter((name) => /^journal-\d+\.json$/.test(name));
  if (journalFiles.length !== 1) {
    throw new Error(`Expected one committed journal generation, got ${journalFiles.join(',')}`);
  }
  const serialized = fs.readFileSync(path.join(firstJournal.directoryPath, journalFiles[0]), 'utf8');
  if (serialized.includes(backendSecret)) throw new Error('Backend credentials leaked into the journal');

  let restartedWriterCalls = 0;
  let restartedDispatch = 0;
  const secondJournal = new FilePendingDocumentRecoveryJournal(root);
  const secondProcess = new PendingDocumentPersistence(async (
    pending,
    _signal,
    dispatchSequence,
  ) => {
    restartedWriterCalls += 1;
    restartedDispatch = dispatchSequence;
    return conflictWriter(pending);
  }, 10_000, secondJournal);
  const restored = secondProcess.listConflicts()[0];
  if (
    !restored
    || restored.conflictId !== original.conflictId
    || restored.version !== original.version
    || restored.write.payload.title !== 'Crash-safe local title'
  ) throw new Error('Cold restart did not restore the exact recovery generation');

  const updated = secondProcess.retainConflict({
    recovery: restored,
    write: write(8, { title: 'Newest crash-safe title', blocks: [] }),
  });
  if (!updated.ok || !updated.recovery || updated.recovery.version !== restored.version + 1) {
    throw new Error('Restarted recovery update did not commit a new exact version');
  }

  const thirdProcess = new PendingDocumentPersistence(
    conflictWriter,
    10_000,
    new FilePendingDocumentRecoveryJournal(root),
  );
  const newest = thirdProcess.listConflicts()[0];
  if (
    !newest
    || newest.version !== updated.recovery.version
    || newest.write.payload.title !== 'Newest crash-safe title'
  ) throw new Error('Updated recovery generation was not durable across restart');
  if (thirdProcess.acknowledgeConflict(restored)) {
    throw new Error('A stale pre-restart receipt acknowledged a newer journal generation');
  }
  if (!thirdProcess.acknowledgeConflict(newest)) {
    throw new Error('The exact restarted recovery generation could not be acknowledged');
  }

  const fourthProcess = new PendingDocumentPersistence(
    async (pending, _signal, dispatchSequence) => {
      restartedWriterCalls += 1;
      restartedDispatch = dispatchSequence;
      return conflictWriter(pending);
    },
    10_000,
    new FilePendingDocumentRecoveryJournal(root),
  );
  if (fourthProcess.listConflicts().length) {
    throw new Error('Acknowledged recovery reappeared after restart');
  }
  await fourthProcess.enqueue({
    ...write(1, { title: 'Later conflict' }),
    sessionId: 'renderer_session_2',
  }).catch(() => {});
  const later = fourthProcess.listConflicts()[0];
  if (
    restartedWriterCalls !== 1
    || restartedDispatch !== 2
    || later?.conflictId !== 'main_conflict_2'
  ) {
    throw new Error(
      `Restart watermarks regressed: calls=${restartedWriterCalls}, order=${restartedDispatch}, id=${later?.conflictId}`,
    );
  }
});

await test('malformed newest generation is quarantined and the prior valid state is recovered', async () => {
  const root = makeTempRoot();
  const firstJournal = new FilePendingDocumentRecoveryJournal(root);
  const firstProcess = new PendingDocumentPersistence(async (pending) => {
    throw new PendingDocumentRevisionConflictError(
      'changed elsewhere',
      resourceRevision(9),
      resourceEtag(pending.kind, pending.incarnation, resourceRevision(9)),
    );
  }, 10_000, firstJournal);
  await firstProcess.enqueue(write(3, { title: 'Valid fallback' })).catch(() => {});
  const validName = fs.readdirSync(firstJournal.directoryPath)
    .find((name) => /^journal-\d+\.json$/.test(name));
  if (!validName) throw new Error('Valid journal generation is missing');
  const malformedEnvelope = JSON.parse(
    fs.readFileSync(path.join(firstJournal.directoryPath, validName), 'utf8'),
  ) as {
    generation: number;
    snapshot: PendingDocumentRecoveryJournalSnapshot;
  };
  malformedEnvelope.generation = 2;
  malformedEnvelope.snapshot.nextConflictId = Number.MAX_SAFE_INTEGER;
  malformedEnvelope.snapshot.entries[0].recovery.conflictId = 'main_conflict_9007199254740992';
  const malformedPath = path.join(
    firstJournal.directoryPath,
    'journal-0000000000000002.json',
  );
  fs.writeFileSync(malformedPath, JSON.stringify(malformedEnvelope), {
    encoding: 'utf8',
    mode: 0o600,
  });
  const staleTempPath = path.join(
    firstJournal.directoryPath,
    '.journal-0000000000000003.json.123.abcdef0123456789.tmp',
  );
  fs.writeFileSync(staleTempPath, 'partial', { encoding: 'utf8', mode: 0o600 });

  const restartedJournal = new FilePendingDocumentRecoveryJournal(root);
  const restarted = new PendingDocumentPersistence(async () => saved(10), 10_000, restartedJournal);
  const [recovered] = restarted.listConflicts();
  if (recovered?.write.payload.title !== 'Valid fallback') {
    throw new Error('Valid older generation was not recovered after quarantine');
  }
  if (
    restartedJournal.startupWarnings.length !== 1
    || fs.existsSync(malformedPath)
    || fs.existsSync(staleTempPath)
    || !fs.existsSync(restartedJournal.startupWarnings[0].quarantinedPath)
  ) throw new Error('Malformed journal generation was not safely quarantined');
});

await test('post-rename directory sync failure never reuses an immutable generation', () => {
  const root = makeTempRoot();
  let syncAttempts = 0;
  const journal = new FilePendingDocumentRecoveryJournal(root, {
    syncDirectory: () => {
      syncAttempts += 1;
      if (syncAttempts === 1) throw new Error('simulated post-rename directory sync failure');
    },
  });
  journal.load();
  let firstRejected = false;
  try {
    journal.replace({
      schemaVersion: 1,
      nextConflictId: 0,
      dispatchSequences: [],
      entries: [],
    });
  } catch {
    firstRejected = true;
  }
  journal.replace({
    schemaVersion: 1,
    nextConflictId: 1,
    dispatchSequences: [],
    entries: [],
  });
  const generations = fs.readdirSync(journal.directoryPath)
    .filter((name) => /^journal-\d+\.json$/.test(name));
  if (!firstRejected || syncAttempts !== 3 || generations.length !== 2) {
    throw new Error(`Post-rename retry reused a generation: ${generations.join(',')}`);
  }
  const loaded = new FilePendingDocumentRecoveryJournal(root).load();
  if (loaded?.nextConflictId !== 1) {
    throw new Error('Cold load did not select the later post-rename generation');
  }
});

await test('normal replacement retains one valid fallback for post-commit corruption', () => {
  const root = makeTempRoot();
  const journal = new FilePendingDocumentRecoveryJournal(root);
  journal.load();
  journal.replace({
    schemaVersion: 1,
    nextConflictId: 0,
    dispatchSequences: [],
    entries: [],
  });
  journal.replace({
    schemaVersion: 1,
    nextConflictId: 1,
    dispatchSequences: [],
    entries: [],
  });
  const generations = fs.readdirSync(journal.directoryPath)
    .filter((name) => /^journal-\d+\.json$/.test(name))
    .sort();
  if (generations.length !== 2) {
    throw new Error(`Normal cleanup did not retain one fallback: ${generations.join(',')}`);
  }
  fs.writeFileSync(
    path.join(journal.directoryPath, generations[1]),
    '{"corrupt":true}',
    'utf8',
  );
  const restartedJournal = new FilePendingDocumentRecoveryJournal(root);
  const fallback = restartedJournal.load();
  if (fallback?.nextConflictId !== 0 || restartedJournal.startupWarnings.length !== 1) {
    throw new Error('Cold start did not fall back after post-commit corruption');
  }
});

await test('durable delete cleanup removes only the matching document incarnation', async () => {
  const root = makeTempRoot();
  const incarnationA = write(1).incarnation;
  const incarnationB = 'abcdef0123456789abcdef0123456789';
  const journal = new FilePendingDocumentRecoveryJournal(root);
  const persistence = new PendingDocumentPersistence(async (pending) => {
    throw new PendingDocumentRevisionConflictError(
      'changed elsewhere',
      resourceRevision(9),
      resourceEtag(pending.kind, pending.incarnation, resourceRevision(9)),
    );
  }, 10_000, journal);
  await persistence.enqueue(write(1, { title: 'Old incarnation' })).catch(() => {});
  await persistence.enqueue({
    ...write(1, { title: 'Reused id incarnation' }),
    incarnation: incarnationB,
    sessionId: 'renderer_session_2',
  }).catch(() => {});
  persistence.commitDocumentDelete('42', incarnationA);

  const restarted = new PendingDocumentPersistence(
    async () => saved(10),
    10_000,
    new FilePendingDocumentRecoveryJournal(root),
  );
  const recoveries = restarted.listConflicts();
  if (
    recoveries.length !== 1
    || recoveries[0].incarnation !== incarnationB
    || recoveries[0].write.payload.title !== 'Reused id incarnation'
    || recoveries.some((recovery) => recovery.incarnation === incarnationA)
  ) throw new Error('Delete cleanup crossed the incarnation boundary after restart');
});

await test('journal write failures preserve authoritative memory and block close until local retry', async () => {
  class FaultJournal implements PendingDocumentRecoveryJournal {
    snapshot: PendingDocumentRecoveryJournalSnapshot | null = null;
    fail = true;

    load(): PendingDocumentRecoveryJournalSnapshot | null {
      return this.snapshot ? structuredClone(this.snapshot) : null;
    }

    replace(snapshot: PendingDocumentRecoveryJournalSnapshot): void {
      if (this.fail) throw new Error('simulated disk full');
      this.snapshot = structuredClone(snapshot);
    }
  }

  const journal = new FaultJournal();
  let writerCalls = 0;
  const persistence = new PendingDocumentPersistence(async () => {
    writerCalls += 1;
    throw new PendingDocumentTerminalError('rejected', 'request_rejected', 409);
  }, 10_000, journal);
  await persistence.enqueue(write(1, { title: 'Must not disappear' })).catch(() => {});
  if (persistence.listConflicts().length || persistence.conflictCount !== 1) {
    throw new Error('An uncommitted receipt was published or forgotten');
  }
  let drainRejected = false;
  try { await persistence.drainStrict(); } catch { drainRejected = true; }
  if (!drainRejected || writerCalls !== 1) {
    throw new Error('Journal fault did not block strict drain without retrying the backend');
  }

  journal.fail = false;
  await persistence.drain();
  const committed = persistence.listConflicts()[0];
  if (!committed || writerCalls !== 1) {
    throw new Error('Local journal retry did not publish the pending conflict safely');
  }

  journal.fail = true;
  let retainRejected = false;
  try {
    persistence.retainConflict({
      recovery: committed,
      write: write(2, { title: 'Uncommitted update' }),
    });
  } catch {
    retainRejected = true;
  }
  const stillCommitted = persistence.listConflicts()[0];
  if (
    !retainRejected
    || stillCommitted?.version !== committed.version
    || stillCommitted.write.payload.title !== 'Must not disappear'
    || journal.snapshot?.entries[0]?.recovery.version !== committed.version
  ) throw new Error('Failed recovery update changed an authoritative receipt');

  journal.fail = false;
  await persistence.drain();
  const silentlyCommitted = persistence.listConflicts()[0];
  if (
    silentlyCommitted?.version !== committed.version + 1
    || silentlyCommitted.write.payload.title !== 'Uncommitted update'
  ) throw new Error('Local retry did not commit the unreported recovery generation');
  if (
    persistence.acknowledgeConflict(committed)
    || !persistence.hasConflict(silentlyCommitted)
  ) throw new Error('A stranded stale receipt acknowledged a newer durable generation');

  journal.fail = true;
  let repeatedRetainRejected = false;
  try {
    persistence.retainConflict({
      recovery: committed,
      write: write(3, { title: 'Second uncommitted update' }),
    });
  } catch {
    repeatedRetainRejected = true;
  }
  if (!repeatedRetainRejected || persistence.listConflicts()[0]?.version !== silentlyCommitted.version) {
    throw new Error('Repeated journal failure changed the published recovery generation');
  }
  journal.fail = false;
  await persistence.drain();
  const twiceSilentlyCommitted = persistence.listConflicts()[0];
  if (
    twiceSilentlyCommitted?.version !== silentlyCommitted.version + 1
    || twiceSilentlyCommitted.write.payload.title !== 'Second uncommitted update'
  ) throw new Error('Second local retry did not preserve the newest recovery snapshot');

  // The renderer still owns `committed`: the failed synchronous retain could
  // not return the receipt that drain just made durable. Only a strictly newer
  // cumulative write from that exact session/base may resynchronize it.
  const equalRevision = persistence.retainConflict({
    recovery: committed,
    write: write(3, { title: 'Must reject equal revision' }),
  });
  const otherSession = persistence.retainConflict({
    recovery: committed,
    write: {
      ...write(4, { title: 'Must reject another session' }),
      sessionId: 'renderer_session_2',
    },
  });
  const otherBase = persistence.retainConflict({
    recovery: committed,
    write: {
      ...write(4, { title: 'Must reject another base' }),
      resourceRevision: resourceRevision(2),
    },
  });
  if (equalRevision.ok || otherSession.ok || otherBase.ok) {
    throw new Error('A genuinely stale recovery receipt bypassed exact resynchronization guards');
  }
  const resynchronized = persistence.retainConflict({
    recovery: committed,
    write: write(4, { title: 'Newest after disk recovery', blocks: [] }),
  });
  if (
    !resynchronized.ok
    || !resynchronized.recovery
    || resynchronized.recovery.version !== twiceSilentlyCommitted.version + 1
    || journal.snapshot?.entries[0]?.recovery.write.payload.title
      !== 'Newest after disk recovery'
  ) throw new Error('A stranded exact receipt could not safely publish the newest local snapshot');
  const updated = persistence.listConflicts()[0];
  const coldResynchronized = new PendingDocumentPersistence(
    async () => saved(2),
    10_000,
    journal,
  ).listConflicts()[0];
  if (
    updated?.version !== resynchronized.recovery.version
    || coldResynchronized?.version !== resynchronized.recovery.version
    || coldResynchronized.write.payload.title !== 'Newest after disk recovery'
  ) throw new Error('Resynchronized recovery did not survive a cold journal load');

  // A successful resync retires the temporary lineage exception.
  if (persistence.retainConflict({
    recovery: committed,
    write: write(5, { title: 'Old receipt after resync' }),
  }).ok) throw new Error('A stranded receipt remained valid after successful resynchronization');

  journal.fail = true;
  let acknowledgeRejected = false;
  try { persistence.acknowledgeConflict(updated); } catch { acknowledgeRejected = true; }
  if (
    !acknowledgeRejected
    || !persistence.hasConflict(updated)
    || journal.snapshot?.entries[0]?.recovery.version !== updated.version
  ) throw new Error('Failed acknowledgement erased authoritative recovery state');

  let deleteRejected = false;
  try { persistence.commitDocumentDelete(updated.documentId, updated.incarnation); } catch {
    deleteRejected = true;
  }
  if (!deleteRejected || !persistence.hasConflict(updated)) {
    throw new Error('Failed delete cleanup erased the in-memory recovery');
  }
  journal.fail = false;
  persistence.commitDocumentDelete(updated.documentId, updated.incarnation);
  const restarted = new PendingDocumentPersistence(
    async () => saved(2),
    10_000,
    journal,
  );
  if (restarted.listConflicts().length) {
    throw new Error('Successful durable delete cleanup reintroduced a recovery after restart');
  }
});

await test('bounded stranded-receipt history never evicts the renderer-owned generation', async () => {
  class FaultJournal implements PendingDocumentRecoveryJournal {
    snapshot: PendingDocumentRecoveryJournalSnapshot | null = null;
    fail = false;

    load(): PendingDocumentRecoveryJournalSnapshot | null {
      return this.snapshot ? structuredClone(this.snapshot) : null;
    }

    replace(snapshot: PendingDocumentRecoveryJournalSnapshot): void {
      if (this.fail) throw new Error('simulated disk full');
      this.snapshot = structuredClone(snapshot);
    }
  }

  const journal = new FaultJournal();
  const persistence = new PendingDocumentPersistence(async () => {
    throw new PendingDocumentTerminalError('rejected', 'request_rejected', 409);
  }, 10_000, journal);
  await persistence.enqueue(write(1, { title: 'Published recovery' })).catch(() => {});
  const rendererReceipt = persistence.listConflicts()[0];
  if (!rendererReceipt) throw new Error('Initial renderer recovery was not published');

  // Each failed journal replacement is later committed by a local-only drain,
  // so none of the 70 newer generations can have reached the renderer.
  for (let revision = 2; revision <= 71; revision += 1) {
    journal.fail = true;
    try {
      await persistence.enqueue(write(revision, { title: `Silent generation ${revision}` }));
    } catch {
      // Expected synchronous journal failure; no newer receipt was returned.
    }
    journal.fail = false;
    await persistence.drain();
  }

  const resynchronized = persistence.retainConflict({
    recovery: rendererReceipt,
    write: write(72, { title: 'Renderer still owns its original receipt' }),
  });
  if (
    !resynchronized.ok
    || journal.snapshot?.entries[0]?.recovery.write.payload.title
      !== 'Renderer still owns its original receipt'
  ) throw new Error('The bounded receipt history evicted the renderer-owned generation');
});

console.log(`Pending document persistence tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} pending persistence test(s) failed`);
console.log('PENDING DOCUMENT PERSISTENCE TESTS: PASS');

for (const root of tempRoots) fs.rmSync(root, { recursive: true, force: true });
