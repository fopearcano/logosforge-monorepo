import type { OutlineNode } from './outlineModel';
import {
  discardPendingDocSaves,
  flushPendingDocSavesForUnload,
  prepareDocumentHandoff,
  setCurrentDocId,
} from '../../state/currentDocument';
import {
  blockOutlineWrites,
  discardRetainedOutlineSnapshot,
  flushOutlineSnapshots,
  newestRetainedOutlineSnapshot,
  peekRetainedOutlineSnapshot,
  queueOutlineSnapshot,
  resumeOutlineWrites,
} from './pendingOutlineRecovery';
import { OutlineLoadCoordinator } from './outlineLoadCoordinator';

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
