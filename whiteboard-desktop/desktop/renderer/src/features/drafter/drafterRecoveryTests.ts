import type { PendingDocumentConflictRecovery } from '../../api/backend';
import { RevisionConflictError } from '../../api/responseError';
import { pendingDocumentRecoveryEnvelope } from '../files/pendingRecoveryCopy';
import {
  discardPendingDocSaves,
  flushPendingDocSavesForUnload,
  prepareDocumentHandoff,
  setCurrentDocId,
} from '../../state/currentDocument';
import {
  blockDrafterWrites,
  claimDrafterConflict,
  discardConflictedDrafterSnapshot,
  discardRetainedDrafterSnapshot,
  drafterRevisionConflict,
  flushDrafterSnapshots,
  peekRetainedDrafterSnapshot,
  queueDrafterSnapshot,
  restoreDrafterConflict,
  resumeDrafterWrites,
} from './pendingDrafterRecovery';
import type { DrafterPage } from './types';

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

const page = (id: string, title: string): DrafterPage => ({
  id,
  title,
  blocks: [{ id: `${id}-block`, type: 'paragraph', text: title }],
  created_at: '2026-09-26T00:00:00Z',
  updated_at: '2026-09-26T00:00:00Z',
});

const mainDrafterRecovery = (
  documentId: string,
  incarnation: string,
  pages: DrafterPage[],
  version = 1,
): PendingDocumentConflictRecovery => ({
  conflictId: 'main_conflict_7',
  version,
  kind: 'drafter',
  documentId,
  incarnation,
  write: {
    kind: 'drafter',
    documentId,
    incarnation,
    resourceRevision: '1'.repeat(32),
    revision: version,
    sessionId: 'drafter_recovery_session',
    payload: { pages },
  },
  error: {
    code: 'revision_conflict',
    status: 409,
    message: 'changed elsewhere',
    currentRevision: '2'.repeat(32),
    currentEtag: '"current"',
  },
});

await test('newer complete collections replace older pending Drafter state', () => {
  const documentId = 'drafter-latest';
  const first = [page('one', 'First')];
  const latest = [page('one', 'Latest')];
  queueDrafterSnapshot(documentId, first);
  queueDrafterSnapshot(documentId, latest);
  if (peekRetainedDrafterSnapshot(documentId)?.pages !== latest) {
    throw new Error('Latest collection was not retained');
  }
  discardRetainedDrafterSnapshot(documentId);
});

await test('portable recovery copy preserves the exact Drafter collection payload', () => {
  const pages = [{
    ...page('one', 'Exact local page'),
    future_metadata: { authoringHint: 'preserve me' },
  }];
  const recovery = mainDrafterRecovery(
    '904',
    '0123456789abcdef0123456789abcdef',
    pages,
  );
  const envelope = pendingDocumentRecoveryEnvelope(recovery, '2026-09-26T01:00:00Z');
  if (JSON.stringify(envelope.recovery.write.payload) !== JSON.stringify({ pages })) {
    throw new Error('Portable recovery export reshaped Drafter pages');
  }
});

await test('old and replacement hooks serialize complete Drafter collections', async () => {
  const documentId = 'drafter-serialized';
  const first = [page('one', 'First')];
  const latest = [page('one', 'Latest')];
  let release!: () => void;
  const blocked = new Promise<void>((resolve) => { release = resolve; });
  const writes: DrafterPage[][] = [];
  const writer = async (_target: string, pages: DrafterPage[]) => {
    writes.push(pages);
    if (writes.length === 1) await blocked;
  };
  queueDrafterSnapshot(documentId, first);
  const retiring = flushDrafterSnapshots(documentId, writer);
  queueDrafterSnapshot(documentId, latest);
  const replacement = flushDrafterSnapshots(documentId, writer);
  if (writes.length !== 1) throw new Error('A concurrent writer started');
  release();
  await Promise.all([retiring, replacement]);
  if (Number(writes.length) !== 2 || writes[1] !== latest) {
    throw new Error('Latest complete collection was not persisted last');
  }
  if (peekRetainedDrafterSnapshot(documentId)) throw new Error('Saved state stayed retained');
});

await test('main recovery is staged by incarnation and remains a sticky conflict', async () => {
  const documentId = '903';
  const incarnationA = '0123456789abcdef0123456789abcdef';
  const incarnationB = 'abcdef0123456789abcdef0123456789';
  const pages = [page('one', 'Recovered')];
  const recovery = mainDrafterRecovery(documentId, incarnationA, pages);
  const error = new RevisionConflictError('changed', '2'.repeat(32), '"current"', recovery);
  restoreDrafterConflict(recovery, error);
  if (claimDrafterConflict(documentId, incarnationB)) {
    throw new Error('Old-incarnation recovery attached to a reused document id');
  }
  const claimed = claimDrafterConflict(documentId, incarnationA);
  if (!claimed || claimed.pages !== pages || !drafterRevisionConflict(documentId)) {
    throw new Error('Matching Drafter recovery was not claimed');
  }
  let wrote = false;
  try {
    await flushDrafterSnapshots(documentId, async () => { wrote = true; });
  } catch {
    /* the recovery must remain blocked */
  }
  if (wrote) throw new Error('Stale recovered pages were retried automatically');
  discardRetainedDrafterSnapshot(documentId);
});

await test('conflict discard requires the exact latest Drafter collection', async () => {
  const documentId = 'drafter-conflict-discard';
  const captured = queueDrafterSnapshot(documentId, [page('one', 'Local')]);
  if (!captured) throw new Error('Expected a retained collection');
  try {
    await flushDrafterSnapshots(documentId, async () => {
      throw new RevisionConflictError('changed', '9'.repeat(32), '"current"');
    });
  } catch {
    /* expected */
  }
  queueDrafterSnapshot(documentId, [page('one', 'Edited during reload')]);
  if (discardConflictedDrafterSnapshot(captured)) {
    throw new Error('An older receipt discarded newer Drafter edits');
  }
  const latest = peekRetainedDrafterSnapshot(documentId);
  if (!latest || !discardConflictedDrafterSnapshot(latest)) {
    throw new Error('Exact latest conflicted collection could not be discarded');
  }
});

await test('the app-lifetime Drafter flusher survives a hidden surface', async () => {
  const documentId = 'drafter-hidden-handoff';
  let release!: () => void;
  let started!: () => void;
  const blocked = new Promise<void>((resolve) => { release = resolve; });
  const writeStarted = new Promise<void>((resolve) => { started = resolve; });
  let prepared = false;
  setCurrentDocId(documentId);
  queueDrafterSnapshot(documentId, [page('one', 'Hidden')], {
    write: async () => { started(); await blocked; },
  });
  const handoff = prepareDocumentHandoff(async () => { prepared = true; return true; });
  await writeStarted;
  if (prepared) throw new Error('Handoff started before hidden Drafter state settled');
  release();
  await handoff;
  discardPendingDocSaves();
  setCurrentDocId('');
});

await test('the app-lifetime unload hook copies the latest full collection', () => {
  const documentId = 'drafter-hidden-unload';
  const latest = [page('one', 'Keepalive')];
  let unloaded: DrafterPage[] | null = null;
  setCurrentDocId(documentId);
  queueDrafterSnapshot(documentId, latest, {
    write: async () => {},
    writeOnUnload: (_target, pages) => { unloaded = pages; },
  });
  flushPendingDocSavesForUnload();
  if (unloaded !== latest) throw new Error('Hidden Drafter state was omitted from unload recovery');
  discardPendingDocSaves();
  setCurrentDocId('');
});

await test('DELETE blocking retains Drafter edits without launching a late PUT', async () => {
  const documentId = 'drafter-delete-block';
  const latest = [page('one', 'Typed during delete')];
  let writes = 0;
  blockDrafterWrites(documentId);
  queueDrafterSnapshot(documentId, latest, { write: async () => { writes += 1; } });
  await flushDrafterSnapshots(documentId);
  if (writes !== 0 || peekRetainedDrafterSnapshot(documentId)?.pages !== latest) {
    throw new Error('Blocked Drafter state was not retained safely');
  }
  resumeDrafterWrites(documentId);
  await flushDrafterSnapshots(documentId);
  if (Number(writes) !== 1) throw new Error('Failed-delete recovery did not resume the Drafter PUT');
});

console.log(`Drafter recovery tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} Drafter recovery test(s) failed`);
console.log('DRAFTER RECOVERY TESTS: PASS');
