import { editorRecoveryBlocks } from './editorRecovery';
import { loadInitialDocumentOnce } from './documentBootstrap';
import {
  discardPendingDocSaves,
  flushPendingDocSavesForUnload,
  setCurrentDocId,
} from '../../state/currentDocument';
import {
  applyRetainedWhiteboardPatch,
  blockWhiteboardWrites,
  discardRetainedWhiteboardPatch,
  flushWhiteboardPatchThrough,
  flushWhiteboardPatches,
  newestRetainedWhiteboardPatch,
  peekRetainedWhiteboardPatch,
  queueWhiteboardPatch,
  resumeWhiteboardWrites,
} from './pendingWhiteboardRecovery';
import { eligibleOrphanCleanupIds } from './orphanCleanupGate';
import type { WhiteboardBlock } from './types';
import {
  acquireTrackedDocumentOperation,
  beginDocumentCloseBarrier,
  beginTrackedDocumentOperation,
  canStartDocumentMutationDuringClose,
  createDocumentOperationOwner,
  DocumentCloseInProgressError,
  isActiveDocumentOperationOwner,
  lockDocumentInteraction,
  releaseDocumentCloseBarrier,
  waitForTrackedDocumentOperations,
} from './documentOperationGuard';

let passed = 0;
let failed = 0;

function test(name: string, run: () => void): void {
  try {
    run();
    passed += 1;
  } catch (error) {
    failed += 1;
    console.error(`FAIL: ${name}`);
    console.error(error);
  }
}

async function testAsync(name: string, run: () => Promise<void>): Promise<void> {
  try {
    await run();
    passed += 1;
  } catch (error) {
    failed += 1;
    console.error(`FAIL: ${name}`);
    console.error(error);
  }
}

function expectSame(actual: unknown, expected: unknown): void {
  if (actual !== expected) throw new Error('Expected the selected snapshot to preserve array identity');
}

const loaded: WhiteboardBlock[] = [{ id: 'loaded', type: 'paragraph', text: 'Load-time text' }];
const live: WhiteboardBlock[] = [{ id: 'live', type: 'paragraph', text: 'Latest unsaved text' }];
const document = (id: string) => ({
  id,
  incarnation: '0123456789abcdef0123456789abcdef',
  title: 'Untitled',
  mode: 'novel',
  blocks: loaded,
  settings: {},
  updated_at: '2026-09-11T00:00:00Z',
});

test('render recovery prefers the current document live snapshot', () => {
  expectSame(editorRecoveryBlocks('doc-a', 'doc-a', live, loaded), live);
});

test('render recovery preserves an intentionally empty current snapshot', () => {
  const empty: WhiteboardBlock[] = [];
  expectSame(editorRecoveryBlocks('doc-a', 'doc-a', empty, loaded), empty);
});

test('document switches reject a live snapshot from the previous document', () => {
  expectSame(editorRecoveryBlocks('doc-b', 'doc-a', live, loaded), loaded);
});

test('a not-yet-loaded document uses the backend-derived snapshot', () => {
  expectSame(editorRecoveryBlocks(null, null, live, loaded), loaded);
});

test('the root-boundary outbox merges fields and retains the newest values', () => {
  const documentId = 'recovery-merge';
  queueWhiteboardPatch(documentId, { blocks: loaded });
  const newest = queueWhiteboardPatch(documentId, {
    settings: { language: 'it' },
    blocks: live,
    title: 'Recovered title',
    mode: 'screenplay',
  });
  const retained = peekRetainedWhiteboardPatch(documentId);
  if (!newest || !retained) throw new Error('Expected a retained patch');
  expectSame(retained.patch.blocks, live);
  if ((retained.patch.settings as { language?: string }).language !== 'it') {
    throw new Error('Expected settings to be merged into the retained patch');
  }
  if (retained.patch.title !== 'Recovered title' || retained.patch.mode !== 'screenplay') {
    throw new Error('Expected title and mode to share the retained save queue');
  }
  discardRetainedWhiteboardPatch(documentId);
});

await testAsync('old and replacement hooks share one ordered per-document writer', async () => {
  const documentId = 'recovery-serialized';
  let releaseFirst!: () => void;
  const firstBlocked = new Promise<void>((resolve) => { releaseFirst = resolve; });
  const writes: Array<{ documentId: string; blocks: WhiteboardBlock[] | undefined }> = [];
  const writer = async (targetId: string, patch: { blocks?: WhiteboardBlock[] }) => {
    writes.push({ documentId: targetId, blocks: patch.blocks });
    if (writes.length === 1) await firstBlocked;
  };

  queueWhiteboardPatch(documentId, { blocks: loaded });
  const retiringFlush = flushWhiteboardPatches(documentId, writer);
  queueWhiteboardPatch(documentId, { blocks: live });
  const replacementFlush = flushWhiteboardPatches(documentId, writer);
  if (writes.length !== 1) throw new Error('A concurrent replacement writer started');
  releaseFirst();
  await Promise.all([retiringFlush, replacementFlush]);
  const completedWrites = writes.slice();
  if (completedWrites.length !== 2) {
    throw new Error(`Expected two serialized snapshots, got ${completedWrites.length}`);
  }
  if (completedWrites.some((write) => write.documentId !== documentId)) {
    throw new Error('A queued save changed document ownership');
  }
  expectSame(completedWrites[1]?.blocks, live);
  if (peekRetainedWhiteboardPatch(documentId)) throw new Error('Expected the latest completed save to clear');
});

await testAsync('a failed save is restored and merges a newer field before retry', async () => {
  const documentId = 'recovery-failure';
  queueWhiteboardPatch(documentId, { blocks: live });
  try {
    await flushWhiteboardPatches(documentId, async () => { throw new Error('offline'); });
  } catch {
    // Expected: the coordinator retains the failed snapshot.
  }
  queueWhiteboardPatch(documentId, { settings: { language: 'it' } });
  const retries: Array<{ blocks?: WhiteboardBlock[]; settings?: object }> = [];
  await flushWhiteboardPatches(documentId, async (_targetId, patch) => { retries.push(patch); });
  const retried = retries[0];
  if (!retried) throw new Error('Expected the failed snapshot to be retried');
  expectSame(retried?.blocks, live);
  if ((retried?.settings as { language?: string }).language !== 'it') {
    throw new Error('Retry did not include the newer settings field');
  }
  if (peekRetainedWhiteboardPatch(documentId)) throw new Error('Successful retry did not clear');
});

await testAsync('a destructive cleanup receipt acknowledges only a successful save', async () => {
  const documentId = 'recovery-orphan-ack';
  let releaseWrite!: () => void;
  const delayedWrite = new Promise<void>((resolve) => { releaseWrite = resolve; });
  const receipt = queueWhiteboardPatch(documentId, { blocks: live }, {
    write: async () => delayedWrite,
  });
  if (!receipt) throw new Error('Expected a persistence receipt');

  let acknowledged = false;
  const waiting = flushWhiteboardPatchThrough(receipt).then((saved) => {
    acknowledged = saved;
    return saved;
  });
  await Promise.resolve();
  if (acknowledged) throw new Error('Receipt acknowledged before its writer completed');
  releaseWrite();
  if (!(await waiting)) throw new Error('Successful writer did not acknowledge its receipt');
  discardRetainedWhiteboardPatch(documentId);
});

await testAsync('a failed manuscript receipt can never authorize destructive cleanup', async () => {
  const documentId = 'recovery-orphan-failure';
  const receipt = queueWhiteboardPatch(documentId, { blocks: live }, {
    write: async () => { throw new Error('disk full'); },
  });
  if (!receipt) throw new Error('Expected a persistence receipt');
  let rejected = false;
  try {
    await flushWhiteboardPatchThrough(receipt);
  } catch {
    rejected = true;
  }
  if (!rejected) throw new Error('Failed writer was treated as a durable receipt');
  if (!peekRetainedWhiteboardPatch(documentId)) throw new Error('Failed snapshot was not retained');
  discardRetainedWhiteboardPatch(documentId);
});

await testAsync('same-id queue reuse cannot acknowledge an old cleanup receipt', async () => {
  const documentId = 'recovery-orphan-reused-id';
  const oldReceipt = queueWhiteboardPatch(documentId, { blocks: loaded }, {
    write: async () => {},
  });
  if (!oldReceipt) throw new Error('Expected an old persistence receipt');
  discardRetainedWhiteboardPatch(documentId);

  const newReceipt = queueWhiteboardPatch(documentId, { blocks: live }, {
    write: async () => {},
  });
  if (!newReceipt) throw new Error('Expected a replacement persistence receipt');
  if (await flushWhiteboardPatchThrough(oldReceipt)) {
    throw new Error('Replacement queue acknowledged the deleted incarnation receipt');
  }
  if (!(await flushWhiteboardPatchThrough(newReceipt))) {
    throw new Error('Replacement queue did not acknowledge its own receipt');
  }
  discardRetainedWhiteboardPatch(documentId);
});

test('orphan cleanup revalidates document generation and restored anchors', () => {
  const captured = {
    documentId: 'doc-a',
    incarnation: 'inc-a',
    generation: 4,
    orphanIds: ['still-gone', 'restored'],
  };
  const sameSnapshot = { documentId: 'doc-a', incarnation: 'inc-a', generation: 4 };
  const eligible = eligibleOrphanCleanupIds(captured, sameSnapshot, ['still-gone']);
  if (eligible.join(',') !== 'still-gone') {
    throw new Error('A restored anchor remained eligible for deletion');
  }
  if (eligibleOrphanCleanupIds(captured, { ...sameSnapshot, generation: 5 }, ['still-gone']).length) {
    throw new Error('A superseding block snapshot did not cancel cleanup');
  }
  if (eligibleOrphanCleanupIds(captured, { ...sameSnapshot, incarnation: 'inc-b' }, ['still-gone']).length) {
    throw new Error('A reused document id did not cancel cleanup');
  }
});

await testAsync('a snapshot captured before a racing GET still hydrates root recovery', async () => {
  const documentId = 'recovery-load-race';
  const captured = queueWhiteboardPatch(documentId, { blocks: live });
  if (!captured) throw new Error('Expected a retained patch');
  // Simulate the retiring hook completing its PUT while the replacement GET is in flight.
  await flushWhiteboardPatches(documentId, async () => {});
  const recovery = newestRetainedWhiteboardPatch(captured, peekRetainedWhiteboardPatch(documentId));
  const hydrated = applyRetainedWhiteboardPatch({
    id: documentId,
    incarnation: '0123456789abcdef0123456789abcdef',
    title: 'Draft',
    mode: 'novel',
    blocks: loaded,
    settings: {},
    updated_at: '2026-09-11T00:00:00Z',
  }, recovery);
  expectSame(hydrated.blocks, live);
});

test('retained patches never cross document boundaries', () => {
  const retained = queueWhiteboardPatch('recovery-doc-a', { blocks: live });
  if (!retained) throw new Error('Expected a retained patch');
  const document = {
    id: 'recovery-doc-b',
    incarnation: 'fedcba9876543210fedcba9876543210',
    title: 'Other',
    mode: 'novel',
    blocks: loaded,
    settings: {},
    updated_at: '2026-09-11T00:00:00Z',
  };
  expectSame(applyRetainedWhiteboardPatch(document, retained), document);
  discardRetainedWhiteboardPatch('recovery-doc-a');
});

test('the app-lifetime unload hook survives without the document hook', () => {
  const documentId = 'recovery-root-unload';
  let unloaded: unknown = null;
  setCurrentDocId(documentId);
  queueWhiteboardPatch(documentId, { blocks: live }, {
    write: async () => {},
    writeOnUnload: (_targetId, patch) => { unloaded = patch.blocks; },
  });
  flushPendingDocSavesForUnload();
  expectSame(unloaded, live);
  discardPendingDocSaves();
  setCurrentDocId('');
});

await testAsync('StrictMode replays share the whole staggered LIST and CREATE transaction', async () => {
  let listCalls = 0;
  let createCalls = 0;
  let resolveList!: (value: ReturnType<typeof document>[]) => void;
  const delayedList = new Promise<ReturnType<typeof document>[]>((resolve) => { resolveList = resolve; });
  const load = async () => {
    listCalls += 1;
    const list = await delayedList;
    if (list.length) return list[0];
    createCalls += 1;
    return document('created-once');
  };
  const first = loadInitialDocumentOnce('strict-mode-base', load);
  await Promise.resolve(); // the first LIST is now in flight when replay arrives
  const replay = loadInitialDocumentOnce('strict-mode-base', load);
  if (listCalls !== 1 || first !== replay) throw new Error('StrictMode launched duplicate LIST requests');
  resolveList([]);
  const [a, b] = await Promise.all([first, replay]);
  if (createCalls !== 1) throw new Error('Staggered empty LIST responses launched duplicate CREATEs');
  if (a.id !== 'created-once' || b.id !== 'created-once') throw new Error('Replays did not share the result');
});

await testAsync('a failed bootstrap releases the single-flight slot for retry', async () => {
  let calls = 0;
  const load = async () => {
    calls += 1;
    if (calls === 1) throw new Error('temporary failure');
    return document('retry-created');
  };
  try {
    await loadInitialDocumentOnce('strict-mode-retry', load);
  } catch {
    // Expected.
  }
  const recovered = await loadInitialDocumentOnce('strict-mode-retry', load);
  if (calls !== 2 || recovered.id !== 'retry-created') throw new Error('Bootstrap retry stayed poisoned');
});

await testAsync('delete tombstones retain edits without starting a late whiteboard PUT', async () => {
  const documentId = 'recovery-delete-block';
  const writes: string[] = [];
  const transport = { write: async () => { writes.push(documentId); } };
  blockWhiteboardWrites(documentId);
  queueWhiteboardPatch(documentId, { blocks: live }, transport);
  await flushWhiteboardPatches(documentId);
  if (writes.length !== 0) throw new Error('A blocked document launched a PUT');
  if (!peekRetainedWhiteboardPatch(documentId)) throw new Error('Blocked edit was not retained');
  resumeWhiteboardWrites(documentId);
  await flushWhiteboardPatches(documentId);
  if (Number(writes.length) !== 1) {
    throw new Error('Failed-delete recovery did not restart the retained PUT');
  }
  discardRetainedWhiteboardPatch(documentId);
});

await testAsync('a replacement owner rejects a retiring hook continuation and waits for its operation', async () => {
  const oldOwner = createDocumentOperationOwner();
  const finishOldOperation = beginTrackedDocumentOperation();
  const replacementOwner = createDocumentOperationOwner();
  let waitFinished = false;
  const waiting = waitForTrackedDocumentOperations().then(() => { waitFinished = true; });
  await Promise.resolve();
  if (isActiveDocumentOperationOwner(oldOwner)) {
    throw new Error('Retiring hook kept document ownership');
  }
  if (!isActiveDocumentOperationOwner(replacementOwner)) {
    throw new Error('Replacement hook did not own document commits');
  }
  if (waitFinished) throw new Error('Replacement load did not wait for retiring operation');
  finishOldOperation();
  await waiting;
  if (!waitFinished) throw new Error('Replacement load stayed blocked after operation completion');
});

await testAsync('tracked document transactions acquire a serial navigation lease', async () => {
  const finishFirst = await acquireTrackedDocumentOperation();
  let finishSecond: (() => void) | null = null;
  const second = acquireTrackedDocumentOperation().then((finish) => {
    finishSecond = finish;
  });
  await Promise.resolve();
  if (finishSecond) throw new Error('A second document transaction overlapped the first');
  finishFirst();
  await second;
  if (!finishSecond) throw new Error('The queued document transaction never acquired its lease');
  (finishSecond as () => void)();
});

await testAsync('a correlated close barrier rejects new work but lets active work finish', async () => {
  const finishExisting = beginTrackedDocumentOperation();
  if (!beginDocumentCloseBarrier(91)) throw new Error('Could not start close barrier');
  if (!canStartDocumentMutationDuringClose()) {
    throw new Error('The barrier interrupted an already-tracked operation');
  }
  finishExisting();
  if (canStartDocumentMutationDuringClose()) {
    throw new Error('Fresh mutations remained enabled after operations drained');
  }
  let rejected = false;
  try {
    await acquireTrackedDocumentOperation();
  } catch (error) {
    rejected = error instanceof DocumentCloseInProgressError;
  }
  if (!rejected) throw new Error('A new transaction crossed the close barrier');
  let finishWaiting: (() => void) | null = null;
  const waitingRetry = acquireTrackedDocumentOperation({ waitForCloseBarrier: true }).then((finish) => {
    finishWaiting = finish;
  });
  await Promise.resolve();
  if (finishWaiting) throw new Error('A recovery transaction crossed an active close barrier');
  if (releaseDocumentCloseBarrier(90)) throw new Error('A stale cancellation released the barrier');
  if (!releaseDocumentCloseBarrier(91)) throw new Error('Matching cancellation did not release the barrier');
  await waitingRetry;
  if (!finishWaiting) throw new Error('Recovery did not resume after close cancellation');
  (finishWaiting as () => void)();
});

test('nested interaction locks keep body portals frozen until the final release', () => {
  const globals = globalThis as unknown as { document?: Document };
  const previousDocument = globals.document;
  const fakeDocument = { body: { inert: false } } as unknown as Document;
  globals.document = fakeDocument;
  try {
    const releaseImport = lockDocumentInteraction();
    const releaseClose = lockDocumentInteraction();
    if (!fakeDocument.body.inert) throw new Error('Interaction lock did not freeze the body');
    releaseImport();
    if (!fakeDocument.body.inert) throw new Error('Nested close lock was released by import cleanup');
    releaseClose();
    if (fakeDocument.body.inert) throw new Error('Final interaction lock did not restore the body');
  } finally {
    if (previousDocument) globals.document = previousDocument;
    else delete globals.document;
  }
});

console.log(`Editor recovery tests: ${passed} passed, ${failed} failed`);
if (failed) throw new Error(`${failed} editor recovery test(s) failed`);
console.log('EDITOR RECOVERY TESTS: PASS');
