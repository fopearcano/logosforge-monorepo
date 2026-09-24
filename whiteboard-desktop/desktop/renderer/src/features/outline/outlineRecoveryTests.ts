import type { OutlineNode } from './outlineModel';
import {
  discardPendingDocSaves,
  flushPendingDocSavesForUnload,
  prepareDocumentHandoff,
  setCurrentDocId,
} from '../../state/currentDocument';
import {
  blockOutlineWrites,
  claimOutlineConflict,
  discardConflictedOutlineSnapshot,
  discardRetainedOutlineSnapshot,
  flushOutlineSnapshots,
  newestRetainedOutlineSnapshot,
  outlineRevisionConflict,
  peekRetainedOutlineSnapshot,
  queueOutlineSnapshot,
  restoreOutlineConflict,
  resumeOutlineWrites,
} from './pendingOutlineRecovery';
import { RevisionConflictError } from '../../api/responseError';
import { OutlineLoadCoordinator } from './outlineLoadCoordinator';
import type { PendingDocumentConflictRecovery } from '../../api/backend';

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

const node = (id: string, title: string): OutlineNode => ({
  id,
  parentId: null,
  type: 'custom',
  title,
  summary: '',
  order: 0,
  collapsed: false,
  completed: false,
  status: 'none',
  tags: [],
  colorLabel: 'none',
  linkedLineId: null,
  link: null,
  createdAt: '2026-09-11T00:00:00Z',
  updatedAt: '2026-09-11T00:00:00Z',
});

const mainOutlineRecovery = (
  documentId: string,
  incarnation: string,
  items: OutlineNode[],
  version = 1,
): PendingDocumentConflictRecovery => ({
  conflictId: 'main_conflict_2',
  version,
  kind: 'outline',
  documentId,
  incarnation,
  write: {
    kind: 'outline',
    documentId,
    incarnation,
    resourceRevision: '1'.repeat(32),
    revision: version,
    sessionId: 'outline_recovery_session',
    payload: { items },
  },
  error: {
    code: 'revision_conflict',
    status: 409,
    message: 'changed elsewhere',
    currentRevision: '2'.repeat(32),
    currentEtag: '"current"',
  },
});

await test('newer complete snapshots replace older pending snapshots', () => {
  const documentId = 'outline-latest';
  const first = [node('one', 'First')];
  const latest = [node('one', 'Latest')];
  queueOutlineSnapshot(documentId, first);
  queueOutlineSnapshot(documentId, latest);
  if (peekRetainedOutlineSnapshot(documentId)?.items !== latest) {
    throw new Error('Latest snapshot was not retained');
  }
  discardRetainedOutlineSnapshot(documentId);
});

await test('revision conflicts retain the local outline and pause retries', async () => {
  const documentId = 'outline-revision-conflict';
  const first = [node('one', 'Local')];
  const latest = [node('one', 'Still local')];
  let attempts = 0;
  queueOutlineSnapshot(documentId, first);
  try {
    await flushOutlineSnapshots(documentId, async () => {
      attempts += 1;
      throw new RevisionConflictError(
        'changed elsewhere',
        '99999999999999999999999999999999',
        '"current"',
      );
    });
  } catch {
    /* expected */
  }
  queueOutlineSnapshot(documentId, latest);
  try {
    await flushOutlineSnapshots(documentId, async () => {
      attempts += 1;
    });
  } catch {
    /* sticky conflict */
  }
  if (attempts !== 1) throw new Error('A conflicted outline was retried automatically');
  if (!outlineRevisionConflict(documentId)) throw new Error('Conflict state was not retained');
  if (peekRetainedOutlineSnapshot(documentId)?.items !== latest) {
    throw new Error('The newest local outline snapshot was not retained');
  }
  discardRetainedOutlineSnapshot(documentId);
});

await test('an outline edit queued behind an in-flight conflict is handed to main', async () => {
  const documentId = '905';
  const incarnation = '0123456789abcdef0123456789abcdef';
  const first = [node('one', 'First')];
  const newest = [node('one', 'Newest')];
  const recovery = mainOutlineRecovery(documentId, incarnation, first);
  let release!: () => void;
  let started!: () => void;
  const blocked = new Promise<void>((resolve) => { release = resolve; });
  const writeStarted = new Promise<void>((resolve) => { started = resolve; });
  let retainedByMain: OutlineNode[] | null = null;
  queueOutlineSnapshot(documentId, first, {
    incarnation,
    write: async () => {
      started();
      await blocked;
      throw new RevisionConflictError('changed', '2'.repeat(32), '"current"', recovery);
    },
    retainConflict: (_target, items, _revision, receipt) => {
      retainedByMain = items;
      return { ...receipt, version: receipt.version + 1 };
    },
  });
  const flushing = flushOutlineSnapshots(documentId).catch(() => {});
  await writeStarted;
  queueOutlineSnapshot(documentId, newest, { incarnation, write: async () => {} });
  release();
  await flushing;
  const retained = peekRetainedOutlineSnapshot(documentId, incarnation);
  if (retainedByMain !== newest || retained?.mainRecovery?.version !== 2) {
    throw new Error('The newer in-flight outline was not copied into main recovery');
  }
  discardRetainedOutlineSnapshot(documentId);
});

await test('main outline hydration is sticky, idempotent, and incarnation-safe', async () => {
  const documentId = '903';
  const incarnationA = '0123456789abcdef0123456789abcdef';
  const incarnationB = 'abcdef0123456789abcdef0123456789';
  const local = [node('one', 'Recovered A')];
  const recovery = mainOutlineRecovery(documentId, incarnationA, local);
  const error = new RevisionConflictError('changed', '2'.repeat(32), '"current"', recovery);
  restoreOutlineConflict(recovery, error);
  if (claimOutlineConflict(documentId, incarnationB)) {
    throw new Error('Old-incarnation outline was applied to a reused document id');
  }
  const first = claimOutlineConflict(documentId, incarnationA);
  if (!first || first.items !== local || !outlineRevisionConflict(documentId)) {
    throw new Error('Matching main outline recovery was not claimed as a sticky conflict');
  }
  restoreOutlineConflict(recovery, error);
  const repeated = peekRetainedOutlineSnapshot(documentId, incarnationA);
  if (!repeated || repeated.revision !== first.revision) {
    throw new Error('Repeated outline hydration replaced the same generation');
  }
  const edited = [node('one', 'Edited after hydration')];
  let retainedByMain: OutlineNode[] | null = null;
  queueOutlineSnapshot(documentId, edited, {
    incarnation: incarnationA,
    write: async () => {},
    retainConflict: (_target, items) => {
      retainedByMain = items;
      return recovery;
    },
  });
  restoreOutlineConflict(recovery, error);
  const afterRepeat = peekRetainedOutlineSnapshot(documentId, incarnationA);
  let writerCalled = false;
  try {
    await flushOutlineSnapshots(documentId, async () => { writerCalled = true; });
  } catch {
    /* sticky recovery */
  }
  if (
    !afterRepeat
    || afterRepeat.items !== edited
    || retainedByMain !== edited
    || writerCalled
  ) throw new Error('A repeated hydration lost or retried the newer local outline');
  discardRetainedOutlineSnapshot(documentId);
});

await test('conflict reload discards only the exact captured outline', async () => {
  const documentId = 'outline-conflict-resolution';
  const first = [node('one', 'Local')];
  const captured = queueOutlineSnapshot(documentId, first);
  if (!captured) throw new Error('Expected a captured outline');
  try {
    await flushOutlineSnapshots(documentId, async () => {
      throw new RevisionConflictError('changed elsewhere', '9'.repeat(32), '"current"');
    });
  } catch {
    /* expected */
  }
  queueOutlineSnapshot(documentId, [node('one', 'Edited during reload')]);
  if (discardConflictedOutlineSnapshot(captured)) {
    throw new Error('Reload discarded an edit made after its snapshot');
  }
  const latest = peekRetainedOutlineSnapshot(documentId);
  if (!latest || !discardConflictedOutlineSnapshot(latest)) {
    throw new Error('Exact conflicted outline could not be discarded');
  }
  if (peekRetainedOutlineSnapshot(documentId) || outlineRevisionConflict(documentId)) {
    throw new Error('Resolved outline remained queued');
  }
});

await test('old and replacement hooks serialize writes to the owning document', async () => {
  const documentId = 'outline-serialized';
  const first = [node('one', 'First')];
  const latest = [node('one', 'Latest')];
  let release!: () => void;
  const blocked = new Promise<void>((resolve) => { release = resolve; });
  const writes: Array<{ documentId: string; items: OutlineNode[] }> = [];
  const writer = async (targetId: string, items: OutlineNode[]) => {
    writes.push({ documentId: targetId, items });
    if (writes.length === 1) await blocked;
  };
  queueOutlineSnapshot(documentId, first);
  const retiring = flushOutlineSnapshots(documentId, writer);
  queueOutlineSnapshot(documentId, latest);
  const replacement = flushOutlineSnapshots(documentId, writer);
  if (writes.length !== 1) throw new Error('A concurrent writer started');
  release();
  await Promise.all([retiring, replacement]);
  const completed = writes.slice();
  if (completed.length !== 2) throw new Error(`Expected two writes, got ${completed.length}`);
  if (completed.some((write) => write.documentId !== documentId)) {
    throw new Error('A snapshot changed document ownership');
  }
  if (completed[1]?.items !== latest) throw new Error('Latest snapshot was not written last');
  if (peekRetainedOutlineSnapshot(documentId)) throw new Error('Completed snapshot was retained');
});

await test('failed outline writes remain available to a replacement hook', async () => {
  const documentId = 'outline-failure';
  const latest = [node('one', 'Unsaved')];
  queueOutlineSnapshot(documentId, latest);
  try {
    await flushOutlineSnapshots(documentId, async () => { throw new Error('offline'); });
  } catch {
    // Expected.
  }
  if (peekRetainedOutlineSnapshot(documentId)?.items !== latest) {
    throw new Error('Failed snapshot was not retained');
  }
  let retried: OutlineNode[] | null = null;
  await flushOutlineSnapshots(documentId, async (_targetId, items) => { retried = items; });
  if (retried !== latest) throw new Error('Retry did not write the retained snapshot');
});

await test('a pre-GET snapshot survives acknowledgement during the request', async () => {
  const documentId = 'outline-load-race';
  const latest = [node('one', 'Unsaved')];
  const before = queueOutlineSnapshot(documentId, latest);
  if (!before) throw new Error('Expected retained state');
  await flushOutlineSnapshots(documentId, async () => {});
  const recovered = newestRetainedOutlineSnapshot(before, peekRetainedOutlineSnapshot(documentId));
  if (recovered?.items !== latest) throw new Error('Racing GET lost the pre-request snapshot');
});

await test('the app-lifetime flusher blocks handoff after the panel unmounts', async () => {
  const documentId = 'outline-hidden-handoff';
  const latest = [node('one', 'Unsaved while hidden')];
  let release!: () => void;
  let started!: () => void;
  const writeStarted = new Promise<void>((resolve) => { started = resolve; });
  const blocked = new Promise<void>((resolve) => { release = resolve; });
  let prepareCalled = false;
  setCurrentDocId(documentId);
  queueOutlineSnapshot(documentId, latest, {
    write: async () => {
      started();
      await blocked;
    },
  });
  const handoff = prepareDocumentHandoff(async () => {
    prepareCalled = true;
    return true;
  });
  await writeStarted;
  if (prepareCalled) throw new Error('Handoff started before the hidden snapshot settled');
  release();
  await handoff;
  if (!prepareCalled) throw new Error('Handoff did not resume after the save');
  discardPendingDocSaves();
  setCurrentDocId('');
});

await test('the app-lifetime unload hook survives without an Outline component', () => {
  const documentId = 'outline-hidden-unload';
  const latest = [node('one', 'Keepalive')];
  let unloaded: OutlineNode[] | null = null;
  setCurrentDocId(documentId);
  queueOutlineSnapshot(documentId, latest, {
    write: async () => {},
    writeOnUnload: (_targetId, items) => { unloaded = items; },
  });
  flushPendingDocSavesForUnload();
  if (unloaded !== latest) throw new Error('Hidden outline was omitted from unload recovery');
  discardPendingDocSaves();
  setCurrentDocId('');
});

await test('delete tombstones retain edits without starting a late outline PUT', async () => {
  const documentId = 'outline-delete-block';
  const latest = [node('one', 'Typed during delete')];
  const writes: string[] = [];
  blockOutlineWrites(documentId);
  queueOutlineSnapshot(documentId, latest, {
    write: async () => { writes.push(documentId); },
  });
  await flushOutlineSnapshots(documentId);
  if (writes.length !== 0) throw new Error('A blocked document launched an outline PUT');
  if (peekRetainedOutlineSnapshot(documentId)?.items !== latest) {
    throw new Error('Blocked outline edit was not retained');
  }
  resumeOutlineWrites(documentId);
  await flushOutlineSnapshots(documentId);
  if (Number(writes.length) !== 1) {
    throw new Error('Failed-delete recovery did not restart the outline PUT');
  }
  discardRetainedOutlineSnapshot(documentId);
});

await test('a newer refresh wins when the older initial load resolves last', async () => {
  const coordinator = new OutlineLoadCoordinator();
  const documentId = 'outline-load-order';
  const initial = coordinator.begin(documentId);
  const refresh = coordinator.begin(documentId);
  const applied: string[] = [];

  // Refresh resolves first and is accepted.
  if (coordinator.isCurrent(refresh, documentId)) applied.push('imported');
  coordinator.finish(refresh);
  // The older initial response arrives afterwards but was invalidated/aborted.
  if (coordinator.isCurrent(initial, documentId)) applied.push('stale-initial');

  if (!initial.signal.aborted) throw new Error('Refresh did not abort the initial request');
  if (applied.length !== 1 || applied[0] !== 'imported') {
    throw new Error(`Unexpected load application order: ${applied.join(', ')}`);
  }
});

await test('a local save invalidates a GET that resolves after its PUT acknowledgement', () => {
  const coordinator = new OutlineLoadCoordinator();
  const documentId = 'outline-read-write-order';
  const staleGet = coordinator.begin(documentId);
  // scheduleSave uses this cancellation before queuing/persisting the edit.
  coordinator.cancel();
  if (!staleGet.signal.aborted || coordinator.isCurrent(staleGet, documentId)) {
    throw new Error('An acknowledged local edit could be overwritten by a stale GET');
  }
});

console.log(`Outline recovery tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} outline recovery test(s) failed`);
console.log('OUTLINE RECOVERY TESTS: PASS');
