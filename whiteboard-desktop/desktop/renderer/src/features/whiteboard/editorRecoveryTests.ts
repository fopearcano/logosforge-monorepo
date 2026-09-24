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
  claimWhiteboardConflict,
  discardConflictedWhiteboardPatch,
  discardWhiteboardConflictRecovery,
  discardRetainedWhiteboardPatch,
  flushWhiteboardPatchThrough,
  flushWhiteboardPatches,
  newestRetainedWhiteboardPatch,
  peekRetainedWhiteboardPatch,
  queueWhiteboardPatch,
  restoreWhiteboardConflict,
  resumeWhiteboardWrites,
  seedWhiteboardRecoverySnapshot,
  whiteboardRevisionConflict,
} from './pendingWhiteboardRecovery';
import { RevisionConflictError } from '../../api/responseError';
import {
  saveWhiteboardConflictCopy,
  type WhiteboardConflictEnvelope,
} from './whiteboardConflictCopy';
import { eligibleOrphanCleanupIds } from './orphanCleanupGate';
import type { WhiteboardBlock } from './types';
import type { PendingDocumentConflictRecovery } from '../../api/backend';
import {
  coordinateRecoveryAbandonment,
  reconcilePendingDocumentRecoveries,
  recoveryTargetsActiveDocument,
} from '../../api/pendingRecoveryPolicy';
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
  revision: '11111111111111111111111111111111',
  title: 'Untitled',
  mode: 'novel',
  blocks: loaded,
  settings: {},
  updated_at: '2026-09-11T00:00:00Z',
});

const mainWhiteboardRecovery = (
  documentId: string,
  incarnation: string,
  payload: Record<string, unknown>,
  version = 1,
): PendingDocumentConflictRecovery => ({
  conflictId: 'main_conflict_1',
  version,
  kind: 'whiteboard',
  documentId,
  incarnation,
  write: {
    kind: 'whiteboard',
    documentId,
    incarnation,
    resourceRevision: '1'.repeat(32),
    revision: version,
    sessionId: 'renderer_recovery_session',
    payload,
  },
  error: {
    code: 'revision_conflict',
    status: 409,
    message: 'changed elsewhere',
    currentRevision: '2'.repeat(32),
    currentEtag: '"current"',
  },
});

test('render recovery prefers the current document live snapshot', () => {
  expectSame(editorRecoveryBlocks('doc-a:revision-1', 'doc-a:revision-1', live, loaded), live);
});

test('render recovery preserves an intentionally empty current snapshot', () => {
  const empty: WhiteboardBlock[] = [];
  expectSame(editorRecoveryBlocks('doc-a:revision-1', 'doc-a:revision-1', empty, loaded), empty);
});

test('document switches reject a live snapshot from the previous document', () => {
  expectSame(editorRecoveryBlocks('doc-b:revision-1', 'doc-a:revision-1', live, loaded), loaded);
});

test('same-document durable reload rejects the superseded live draft', () => {
  expectSame(editorRecoveryBlocks('doc-a:revision-2', 'doc-a:revision-1', live, loaded), loaded);
});

test('a not-yet-loaded document uses the backend-derived snapshot', () => {
  expectSame(editorRecoveryBlocks(null, null, live, loaded), loaded);
});

test('the global recovery surface detects when abandonment requires a workspace reload', () => {
  const recovery = mainWhiteboardRecovery('910', document('910').incarnation, {});
  if (!recoveryTargetsActiveDocument(recovery, recovery.documentId, recovery.incarnation)) {
    throw new Error('Active recovery did not require coordinated reload');
  }
  if (recoveryTargetsActiveDocument(recovery, '911', recovery.incarnation)) {
    throw new Error('Orphan recovery was mistaken for live editor state');
  }
});

test('a delayed empty main snapshot cannot hide a locally published conflict', () => {
  const recovery = mainWhiteboardRecovery('912', document('912').incarnation, {});
  const reconciled = reconcilePendingDocumentRecoveries(
    [recovery],
    [],
    0,
    new Map([[recovery.conflictId, 1]]),
  );
  if (reconciled.length !== 1 || reconciled[0] !== recovery) {
    throw new Error('The stale absence erased a newer local conflict');
  }
});

test('a delayed stale main snapshot cannot resurrect a locally acknowledged conflict', () => {
  const recovery = mainWhiteboardRecovery('913', document('913').incarnation, {});
  const reconciled = reconcilePendingDocumentRecoveries(
    [],
    [recovery],
    1,
    new Map([[recovery.conflictId, 2]]),
  );
  if (reconciled.length !== 0) {
    throw new Error('The stale response resurrected an acknowledged conflict');
  }
});

await testAsync('active recovery abandonment preserves the target when another store cannot flush', async () => {
  let targetPresent = true;
  let reloadRequested = false;
  let restored = false;
  let rejected = false;
  try {
    await coordinateRecoveryAbandonment({
      discardTarget: () => {
        targetPresent = false;
        return true;
      },
      flushOtherState: async () => {
        throw new Error('comment intent still pending');
      },
      requestCoordinatedReload: async () => {
        reloadRequested = true;
        return true;
      },
      restoreTarget: async () => {
        targetPresent = true;
        restored = true;
      },
    });
  } catch {
    rejected = true;
  }
  if (!rejected || !restored || !targetPresent) {
    throw new Error('Failed unrelated state did not restore the protected draft');
  }
  if (reloadRequested) throw new Error('Reload started despite an unrelated flusher failure');
});

await testAsync('conflict copy preserves every pending field without consuming the queue', async () => {
  const documentId = 'conflict-copy';
  const patch = {
    title: 'Local title',
    mode: 'screenplay',
    blocks: live,
    settings: { narrativeStyle: 'lyrical' },
  };
  queueWhiteboardPatch(documentId, patch);
  try {
    await flushWhiteboardPatches(documentId, async () => {
      throw new RevisionConflictError(
        'changed elsewhere',
        '22222222222222222222222222222222',
        '"current"',
      );
    });
  } catch {
    /* expected */
  }
  const retained = peekRetainedWhiteboardPatch(documentId);
  if (!retained) throw new Error('Expected a retained conflict snapshot');
  const base = { ...document(documentId), title: 'Saved title', settings: {} };

  const canceled = await saveWhiteboardConflictCopy(
    base,
    retained,
    async () => ({ ok: false, canceled: true }),
  );
  if (!canceled.canceled || peekRetainedWhiteboardPatch(documentId)?.revision !== retained.revision) {
    throw new Error('Canceling conflict export consumed the retained queue');
  }

  const exportedContents: string[] = [];
  const saved = await saveWhiteboardConflictCopy(
    base,
    retained,
    async (content) => {
      exportedContents.push(content);
      return { ok: true, filePath: 'conflict.json' };
    },
  );
  const exported = exportedContents[0]
    ? JSON.parse(exportedContents[0]) as WhiteboardConflictEnvelope
    : null;
  if (
    !saved.ok
    || !exported
    || exported.document.title !== patch.title
    || exported.document.mode !== patch.mode
    || exported.document.blocks[0]?.text !== live[0]?.text
    || (exported.document.settings as { narrativeStyle?: string }).narrativeStyle !== 'lyrical'
    || peekRetainedWhiteboardPatch(documentId)?.revision !== retained.revision
  ) {
    throw new Error('Successful conflict export was incomplete or consumed the queue');
  }
  discardRetainedWhiteboardPatch(documentId);
});

await testAsync('conflict copy uses live saved blocks and their current base revision', async () => {
  const documentId = 'conflict-copy-after-save';
  queueWhiteboardPatch(documentId, { blocks: live });
  await flushWhiteboardPatches(documentId, async () => {});
  queueWhiteboardPatch(documentId, { title: 'Conflicted title' });
  try {
    await flushWhiteboardPatches(documentId, async () => {
      throw new RevisionConflictError(
        'changed elsewhere',
        '33333333333333333333333333333333',
        '"current"',
      );
    });
  } catch {
    /* expected */
  }
  const retained = peekRetainedWhiteboardPatch(documentId);
  if (!retained || retained.patch.blocks !== live) {
    throw new Error('Expected the later title conflict to retain the complete local snapshot');
  }
  const currentBaseRevision = '22222222222222222222222222222222';
  const exportedContents: string[] = [];
  await saveWhiteboardConflictCopy(
    { ...document(documentId), revision: currentBaseRevision, blocks: live },
    retained,
    async (content) => {
      exportedContents.push(content);
      return { ok: true, filePath: 'conflict.json' };
    },
  );
  const exported = JSON.parse(exportedContents[0] ?? '{}') as WhiteboardConflictEnvelope;
  if (
    exported.base_revision !== currentBaseRevision
    || exported.document.revision !== currentBaseRevision
    || exported.document.blocks[0]?.text !== live[0]?.text
    || exported.document.title !== 'Conflicted title'
  ) {
    throw new Error('Conflict rescue did not use the current live document base');
  }
  discardRetainedWhiteboardPatch(documentId);
});

await testAsync('seeded title-only conflicts retain the complete local document across remounts', async () => {
  const documentId = '901';
  const base = {
    ...document(documentId),
    title: 'Local base',
    blocks: live,
    mode: 'screenplay',
    settings: { language: 'it' },
  };
  seedWhiteboardRecoverySnapshot(base);
  let retainedByMain: Record<string, unknown> | null = null;
  const recovery = mainWhiteboardRecovery(documentId, base.incarnation, {
    title: 'Local title',
    mode: base.mode,
    blocks: base.blocks,
    settings: base.settings,
  });
  queueWhiteboardPatch(documentId, { title: 'Local title' }, {
    incarnation: base.incarnation,
    write: async (_target, payload) => {
      retainedByMain = payload as Record<string, unknown>;
      throw new RevisionConflictError(
        'changed elsewhere',
        '2'.repeat(32),
        '"current"',
        recovery,
      );
    },
    retainConflict: (_target, payload) => {
      retainedByMain = payload as Record<string, unknown>;
      return recovery;
    },
  });
  try {
    await flushWhiteboardPatches(documentId);
  } catch {
    /* expected */
  }
  const retained = peekRetainedWhiteboardPatch(documentId, base.incarnation);
  const external = {
    ...base,
    revision: '3'.repeat(32),
    title: 'External title',
    blocks: loaded,
    mode: 'novel',
    settings: {},
  };
  const hydrated = applyRetainedWhiteboardPatch(external, retained);
  if (
    !retained
    || hydrated.title !== 'Local title'
    || hydrated.blocks !== live
    || hydrated.mode !== 'screenplay'
    || (hydrated.settings as { language?: string }).language !== 'it'
    || !retainedByMain
    || !('blocks' in retainedByMain)
    || !('settings' in retainedByMain)
  ) throw new Error('A title-only conflict lost fields from the complete local snapshot');
  discardRetainedWhiteboardPatch(documentId);
});

test('main conflict hydration is idempotent and incarnation-safe', () => {
  const documentId = '902';
  const incarnationA = document(documentId).incarnation;
  const incarnationB = 'abcdef0123456789abcdef0123456789';
  const recovery = mainWhiteboardRecovery(documentId, incarnationA, {
    title: 'Recovered A',
    mode: 'novel',
    blocks: live,
    settings: { source: 'A' },
  });
  restoreWhiteboardConflict(
    recovery,
    new RevisionConflictError('changed', '2'.repeat(32), '"current"', recovery),
  );
  const b = { ...document(documentId), incarnation: incarnationB, title: 'Document B' };
  seedWhiteboardRecoverySnapshot(b);
  if (peekRetainedWhiteboardPatch(documentId, incarnationB)) {
    throw new Error('Old-incarnation recovery was applied to a reused document id');
  }
  seedWhiteboardRecoverySnapshot(document(documentId));
  const first = peekRetainedWhiteboardPatch(documentId, incarnationA);
  if (!first) throw new Error('Matching-incarnation recovery was not claimed');
  restoreWhiteboardConflict(
    recovery,
    new RevisionConflictError('changed', '2'.repeat(32), '"current"', recovery),
  );
  const repeated = peekRetainedWhiteboardPatch(documentId, incarnationA);
  if (!repeated || repeated.revision !== first.revision) {
    throw new Error('Repeated hydration replaced the same recovery generation');
  }
  queueWhiteboardPatch(documentId, { title: 'Edit after hydration' }, {
    incarnation: incarnationA,
    write: async () => {},
  });
  const edited = peekRetainedWhiteboardPatch(documentId, incarnationA);
  restoreWhiteboardConflict(
    recovery,
    new RevisionConflictError('changed', '2'.repeat(32), '"current"', recovery),
  );
  const afterRepeat = peekRetainedWhiteboardPatch(documentId, incarnationA);
  if (
    !edited
    || !afterRepeat
    || afterRepeat.revision !== edited.revision
    || afterRepeat.patch.title !== 'Edit after hydration'
  ) throw new Error('Repeated hydration overwrote a newer local edit');
  discardRetainedWhiteboardPatch(documentId);
});

await testAsync('failed abandonment restores the complete captured draft before main refresh', async () => {
  const documentId = 'rollback-before-refresh';
  const incarnation = document(documentId).incarnation;
  const recovery = mainWhiteboardRecovery(documentId, incarnation, {
    title: 'Complete local title',
    mode: 'screenplay',
    blocks: live,
    settings: { language: 'it' },
  });
  const error = new RevisionConflictError('changed', '2'.repeat(32), '"current"', recovery);
  restoreWhiteboardConflict(recovery, error);
  claimWhiteboardConflict(documentId, incarnation);
  if (!discardWhiteboardConflictRecovery(recovery)) {
    throw new Error('Could not prepare the abandonment rollback');
  }

  // Rollback must be complete even when a separate main drain remains failed.
  restoreWhiteboardConflict(recovery, error);
  claimWhiteboardConflict(documentId, incarnation);
  await Promise.reject(new Error('unrelated main retry failed')).catch(() => {});

  const restored = peekRetainedWhiteboardPatch(documentId, incarnation)?.patch;
  if (
    restored?.title !== 'Complete local title'
    || restored.mode !== 'screenplay'
    || restored.blocks !== live
    || (restored.settings as { language?: string } | undefined)?.language !== 'it'
  ) throw new Error('Rollback depended on main drain and lost fields from the rescue');
  discardRetainedWhiteboardPatch(documentId);
});

await testAsync('revision conflicts retain local patches and pause retries', async () => {
  const documentId = 'revision-conflict-draft';
  let attempts = 0;
  queueWhiteboardPatch(documentId, { blocks: loaded });
  try {
    await flushWhiteboardPatches(documentId, async () => {
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
  queueWhiteboardPatch(documentId, { title: 'Still local' });
  try {
    await flushWhiteboardPatches(documentId, async () => {
      attempts += 1;
    });
  } catch {
    /* the original conflict is deliberately sticky */
  }
  if (attempts !== 1) throw new Error('A conflicted draft was retried automatically');
  if (!whiteboardRevisionConflict(documentId)) throw new Error('Conflict state was not retained');
  const retained = peekRetainedWhiteboardPatch(documentId)?.patch;
  if (!retained?.blocks || retained.title !== 'Still local') {
    throw new Error('Local changes were not merged into the retained conflict draft');
  }
  discardRetainedWhiteboardPatch(documentId);
});

await testAsync('an edit queued behind an in-flight conflict is handed to main before rejection returns', async () => {
  const documentId = '904';
  const incarnation = document(documentId).incarnation;
  const recovery = mainWhiteboardRecovery(documentId, incarnation, { blocks: loaded });
  let release!: () => void;
  let started!: () => void;
  const blocked = new Promise<void>((resolve) => { release = resolve; });
  const writeStarted = new Promise<void>((resolve) => { started = resolve; });
  const retainedByMain: {
    current: { patch: Record<string, unknown>; version: number } | null;
  } = { current: null };
  queueWhiteboardPatch(documentId, { blocks: loaded }, {
    incarnation,
    write: async () => {
      started();
      await blocked;
      throw new RevisionConflictError('changed', '2'.repeat(32), '"current"', recovery);
    },
    retainConflict: (_target, patch, _revision, receipt) => {
      retainedByMain.current = {
        patch: patch as Record<string, unknown>,
        version: receipt.version + 1,
      };
      return { ...receipt, version: receipt.version + 1 };
    },
  });
  const flushing = flushWhiteboardPatches(documentId).catch(() => {});
  await writeStarted;
  queueWhiteboardPatch(documentId, { title: 'Queued newest' }, {
    incarnation,
    write: async () => {},
  });
  release();
  await flushing;
  const retained = peekRetainedWhiteboardPatch(documentId, incarnation);
  if (
    !retainedByMain.current
    || retainedByMain.current.patch.title !== 'Queued newest'
    || !('blocks' in retainedByMain.current.patch)
    || retained?.mainRecovery?.version !== 2
  ) throw new Error('The newer in-flight edit was not copied into the main recovery ledger');
  discardRetainedWhiteboardPatch(documentId);
});

await testAsync('conflict reload discards only the exact captured draft', async () => {
  const documentId = 'revision-conflict-resolution';
  const captured = queueWhiteboardPatch(documentId, { blocks: loaded });
  if (!captured) throw new Error('Expected a captured draft');
  try {
    await flushWhiteboardPatches(documentId, async () => {
      throw new RevisionConflictError('changed elsewhere', '9'.repeat(32), '"current"');
    });
  } catch {
    /* expected */
  }
  queueWhiteboardPatch(documentId, { title: 'New edit during reload' });
  if (discardConflictedWhiteboardPatch(captured)) {
    throw new Error('Reload discarded an edit made after its snapshot');
  }
  const latest = peekRetainedWhiteboardPatch(documentId);
  if (!latest || !discardConflictedWhiteboardPatch(latest)) {
    throw new Error('Exact conflicted draft could not be discarded');
  }
  if (peekRetainedWhiteboardPatch(documentId) || whiteboardRevisionConflict(documentId)) {
    throw new Error('Resolved draft remained queued');
  }
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
    revision: '11111111111111111111111111111111',
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
    revision: '22222222222222222222222222222222',
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
