import {
  buildPendingDocumentHttpRequest,
  PendingDocumentPersistence,
  validatePendingDocumentWrite,
  type PendingDocumentWrite,
} from '../electron/pending-document-persistence';

let passed = 0;
const failures: string[] = [];
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
  });
  const newer = persistence.enqueue(write(2));
  const older = persistence.enqueue(write(1));
  await Promise.all([newer, older]);
  if (calls.join(',') !== '2') throw new Error(`Stale write was persisted: ${calls.join(',')}`);
});

await test('a failed write does not poison a later retry', async () => {
  const calls: number[] = [];
  const persistence = new PendingDocumentPersistence(async (pending) => {
    calls.push(pending.revision);
    if (pending.revision === 1) throw new Error('offline');
  });
  await persistence.enqueue(write(1)).catch(() => {});
  await persistence.enqueue(write(2));
  if (calls.join(',') !== '1,2') throw new Error('Later write did not run after rejection');
});

await test('a failed unload snapshot is retained for a later successful drain', async () => {
  let attempts = 0;
  const persistence = new PendingDocumentPersistence(async () => {
    attempts += 1;
    if (attempts === 1) throw new Error('backend restarting');
  });
  await persistence.enqueue(write(7)).catch(() => {});
  await persistence.drain();
  if (attempts !== 2 || persistence.pendingCount !== 0) {
    throw new Error(`Retained snapshot was not retried exactly once (${attempts} attempts)`);
  }
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
  });
  const first = persistence.enqueue(write(11));
  await started;
  const queued = persistence.enqueue(write(12)).catch(() => {});
  const begun = persistence.beginDocumentDelete('42');
  releaseFirst();
  const [, , floor] = await Promise.all([first, queued, begun]);
  if (attempts !== 1) throw new Error('A queued write crossed the DELETE fence');
  if (floor.whiteboard !== 2 || floor.outline !== 0) {
    throw new Error(`DELETE did not expose issued dispatch floors: ${JSON.stringify(floor)}`);
  }
  persistence.commitDocumentDelete('42');
  await persistence.drain();
  if (attempts !== 1 || persistence.pendingCount !== 0) {
    throw new Error(`Deleted document was retried (${attempts} writer calls)`);
  }
  await persistence.enqueue(write(12));
  if (attempts !== 1) throw new Error('A delayed deleted-incarnation write was persisted');
  await persistence.enqueue(write(13));
  if (attempts !== 2) throw new Error('A reused numeric document id stayed tombstoned');
});

await test('canceling a failed delete preserves and retries its newest snapshot', async () => {
  let attempts = 0;
  const persistence = new PendingDocumentPersistence(async () => { attempts += 1; });
  await persistence.beginDocumentDelete('42');
  await persistence.enqueue(write(21)).catch(() => {});
  if (attempts !== 0) throw new Error('Writer ran while DELETE fence was active');
  persistence.cancelDocumentDelete('42');
  await persistence.drain();
  if (attempts !== 1) throw new Error('Canceled DELETE did not restore the retained snapshot');
});

await test('a stalled writer times out, aborts, and cannot poison a later revision', async () => {
  let shouldHang = true;
  let aborted = false;
  const calls: number[] = [];
  const dispatches: number[] = [];
  const persistence = new PendingDocumentPersistence(async (pending, signal, dispatchSequence) => {
    calls.push(pending.revision);
    dispatches.push(dispatchSequence);
    if (!shouldHang) return;
    await new Promise<void>(() => {
      signal.addEventListener('abort', () => { aborted = true; }, { once: true });
    });
  }, 20);
  await persistence.enqueue(write(31)).catch(() => {});
  if (!aborted) throw new Error('Timed-out writer was not aborted');
  shouldHang = false;
  await persistence.enqueue(write(32));
  await persistence.drain();
  if (calls.join(',') !== '31,32' || dispatches.join(',') !== '1,2') {
    throw new Error(
      `Later revision was poisoned: revisions=${calls.join(',')} orders=${dispatches.join(',')}`,
    );
  }
});

console.log(`Pending document persistence tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} pending persistence test(s) failed`);
console.log('PENDING DOCUMENT PERSISTENCE TESTS: PASS');
