import {
  createTrackSubjects,
  progressionKindsForEntry,
  resolvedAnchorCoverage,
  tracksForEntry,
} from './progressionModel';
import {
  abandonPendingProgressionCommand,
  hasPendingProgressionCommand,
  progressionCommandRequestDigest,
  ProgressionRecoveryPendingError,
  resumePendingProgressionCommand,
  runProgressionCommand,
} from './progressionsApi';
import {
  validateProgressionReceipt,
  validateProgressionSnapshot,
} from './progressionValidation';
import { setCurrentDocumentIdentity } from '../../state/currentDocument';
import type {
  ProgressionCommand,
  ProgressionCommandReceipt,
  ProgressionSnapshot,
  ProgressionTrack,
} from './types';

let passed = 0;
const failures: string[] = [];

function test(name: string, fn: () => void): void {
  try {
    fn();
    passed += 1;
  } catch (error) {
    failures.push(`${name}: ${error instanceof Error ? error.message : String(error)}`);
  }
}

async function asyncTest(name: string, fn: () => Promise<void>): Promise<void> {
  try {
    await fn();
    passed += 1;
  } catch (error) {
    failures.push(`${name}: ${error instanceof Error ? error.message : String(error)}`);
  }
}

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

const TRACK: ProgressionTrack = {
  id: 10,
  project_id: 7,
  kind: 'character',
  title: 'Mara accepts command',
  description: '',
  color_label: 'amber',
  sort_order: 0,
  legacy_compatibility: false,
  primary_psyke_entry_id: 4,
  primary_psyke_entry_name: 'Mara',
  primary_psyke_entry_type: 'character',
  secondary_psyke_entry_id: null,
  secondary_psyke_entry_name: '',
  secondary_psyke_entry_type: '',
  beats: [{
    id: 20,
    track_id: 10,
    text: 'She answers the call.',
    sort_order: 0,
    anchor_kind: 'document_block',
    scene_id: null,
    scene_title: '',
    anchor_ref: 'block-stable-01',
    anchor_label: 'Chapter Three',
  }],
  coverage: {
    total_beats: 1,
    anchored_beats: 1,
    unanchored_beats: 0,
    scene_anchored_beats: 0,
    document_anchored_beats: 1,
    coverage_percent: 100,
    status: 'complete',
    out_of_order_beat_ids: [],
  },
};

const SNAPSHOT: ProgressionSnapshot = {
  project_id: 7,
  revision: 'a'.repeat(64),
  tracks: [TRACK],
  summary: {
    total_tracks: 1,
    total_beats: 1,
    anchored_beats: 1,
    unanchored_beats: 0,
    coverage_percent: 100,
    by_kind: { character: 1 },
    by_status: { complete: 1 },
  },
};

const CREATE_COMMAND: ProgressionCommand = {
  kind: 'create_track',
  expected_revision: 'a'.repeat(64),
  track_kind: 'story',
  title: 'Arc',
};

function receipt(
  requestDigest: string,
  overrides: Partial<ProgressionCommandReceipt> = {},
): ProgressionCommandReceipt {
  return {
    project_id: 7,
    request_digest: requestDigest,
    command_kind: 'create_track',
    expected_revision: CREATE_COMMAND.expected_revision,
    applied_revision: 'b'.repeat(64),
    original_changed: true,
    original_affected_track_ids: [10],
    original_affected_beat_ids: [],
    original_created_track_id: 10,
    original_created_beat_id: null,
    committed_at: '2026-10-09T10:00:00Z',
    ...overrides,
  };
}

function snapshotAt(revision: string): ProgressionSnapshot {
  const value = structuredClone(SNAPSHOT);
  value.revision = revision;
  return value;
}

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function receiptMiss(): Response {
  return jsonResponse({
    error: {
      code: 'progression_receipt_not_found',
      message: 'No committed Progressions command exists for this Idempotency-Key.',
    },
  }, 404);
}

test('runtime validator accepts canonical document-block anchors', () => {
  assert(validateProgressionSnapshot(SNAPSHOT, 7).tracks[0].beats[0].anchor_ref === 'block-stable-01', 'anchor lost');
});

test('runtime validator requires the canonical compatibility discriminator', () => {
  const missing = structuredClone(SNAPSHOT) as unknown as {
    tracks: Array<Record<string, unknown>>;
  };
  delete missing.tracks[0].legacy_compatibility;
  let rejected = false;
  try { validateProgressionSnapshot(missing, 7); } catch { rejected = true; }
  assert(rejected, 'snapshot without legacy_compatibility was accepted');
});

test('runtime validator preserves an empty canonical legacy compatibility track', () => {
  const legacy = structuredClone(SNAPSHOT);
  legacy.tracks[0] = {
    ...legacy.tracks[0],
    kind: 'custom',
    title: 'Legacy notes',
    legacy_compatibility: true,
    primary_psyke_entry_type: 'other',
    beats: [],
    coverage: {
      total_beats: 0,
      anchored_beats: 0,
      unanchored_beats: 0,
      scene_anchored_beats: 0,
      document_anchored_beats: 0,
      coverage_percent: 0,
      status: 'empty',
      out_of_order_beat_ids: [],
    },
  };
  assert(validateProgressionSnapshot(legacy, 7).tracks[0].legacy_compatibility, 'compatibility flag was lost');
});

test('runtime validator rejects a subject-linked custom track without the compatibility flag', () => {
  const invalid = structuredClone(SNAPSHOT);
  invalid.tracks[0] = {
    ...invalid.tracks[0],
    kind: 'custom',
    primary_psyke_entry_type: 'other',
  };
  let rejected = false;
  try { validateProgressionSnapshot(invalid, 7); } catch { rejected = true; }
  assert(rejected, 'ambiguous custom track was accepted');
});

test('runtime validator preserves blank migrated legacy beat text', () => {
  const legacy = structuredClone(SNAPSHOT);
  legacy.tracks[0].beats[0].text = '';
  assert(validateProgressionSnapshot(legacy, 7).tracks[0].beats[0].text === '', 'blank legacy beat was rejected');
});

test('runtime validator rejects blank document-block identities', () => {
  const invalid = structuredClone(SNAPSHOT);
  invalid.tracks[0].beats[0].anchor_ref = '';
  let rejected = false;
  try { validateProgressionSnapshot(invalid, 7); } catch { rejected = true; }
  assert(rejected, 'blank stable anchor was accepted');
});

test('runtime validator binds snapshots to the active document project', () => {
  let rejected = false;
  try { validateProgressionSnapshot(SNAPSHOT, 8); } catch { rejected = true; }
  assert(rejected, 'cross-document snapshot was accepted');
});

test('creation subject policy never sends subjects for global tracks', () => {
  assert(Object.keys(createTrackSubjects('story', 4)).length === 0, 'story received a subject');
  assert(Object.keys(createTrackSubjects('custom', 4)).length === 0, 'custom received a subject');
});

test('relationship creation requires two distinct subjects', () => {
  let missingRejected = false;
  let sameRejected = false;
  try { createTrackSubjects('relationship', 4); } catch { missingRejected = true; }
  try { createTrackSubjects('relationship', 4, 4); } catch { sameRejected = true; }
  const valid = createTrackSubjects('relationship', 4, 5);
  assert(missingRejected && sameRejected, 'invalid relationship subjects were accepted');
  assert(valid.primary_psyke_entry_id === 4 && valid.secondary_psyke_entry_id === 5, 'subjects were not preserved');
});

test('entry type gates native track kinds but always allows global and relationship tracks', () => {
  assert(progressionKindsForEntry('character').includes('character'), 'character kind missing');
  assert(!progressionKindsForEntry('theme').includes('character'), 'character kind exposed for theme');
  assert(progressionKindsForEntry('theme').includes('story'), 'global story kind missing');
  assert(progressionKindsForEntry('theme').includes('relationship'), 'relationship kind missing');
});

test('selected-entry view includes global tracks and subject-linked tracks only', () => {
  const global = { ...TRACK, id: 11, kind: 'story' as const, primary_psyke_entry_id: null };
  const unrelated = { ...TRACK, id: 12, primary_psyke_entry_id: 99 };
  const visible = tracksForEntry([global, TRACK, unrelated], {
    id: '4', name: 'Mara', entry_type: 'character', aliases: [],
  });
  assert(visible.map((track) => track.id).join(',') === '11,10', 'entry visibility was incorrect');
});

test('legacy custom compatibility tracks stay scoped to their PSYKE subject', () => {
  const global = {
    ...TRACK,
    id: 11,
    kind: 'custom' as const,
    legacy_compatibility: false,
    primary_psyke_entry_id: null,
  };
  const legacy = {
    ...TRACK,
    id: 12,
    kind: 'custom' as const,
    legacy_compatibility: true,
    primary_psyke_entry_id: 99,
    primary_psyke_entry_type: 'other',
  };
  const visible = tracksForEntry([global, legacy], {
    id: '4', name: 'Mara', entry_type: 'character', aliases: [],
  });
  assert(visible.map((track) => track.id).join(',') === '11', 'another entry\'s legacy custom track leaked into the view');
});

test('local coverage distinguishes live and deleted manuscript block references', () => {
  const live = resolvedAnchorCoverage(TRACK, new Set(['block-stable-01']));
  const missing = resolvedAnchorCoverage(TRACK, new Set());
  assert(live.resolvedAnchors === 1 && live.missingDocumentAnchors === 0, 'live block was not resolved');
  assert(
    missing.resolvedAnchors === 0
      && missing.unresolvedAnchors === 1
      && missing.missingDocumentAnchors === 1,
    'deleted block still counted as locally resolved',
  );
});

await asyncTest('browser request digest matches the Core canonical digest', async () => {
  const digest = await progressionCommandRequestDigest(7, CREATE_COMMAND);
  assert(
    digest === '319ea57fc8a4ff9430a55219cd89d897e63e28a91b02529f6d6a4fb028c41fa1',
    `unexpected digest ${digest}`,
  );
});

await asyncTest('receipt validation binds digest, command kind, revision, and outcome', async () => {
  const digest = await progressionCommandRequestDigest(7, CREATE_COMMAND);
  assert(validateProgressionReceipt(receipt(digest), 7, CREATE_COMMAND, digest).request_digest === digest, 'valid receipt rejected');
  for (const invalid of [
    receipt('c'.repeat(64)),
    receipt(digest, { command_kind: 'delete_track' }),
    receipt(digest, { expected_revision: 'd'.repeat(64) }),
    receipt(digest, { original_created_track_id: null }),
    receipt(digest, { applied_revision: CREATE_COMMAND.expected_revision }),
  ]) {
    let rejected = false;
    try { validateProgressionReceipt(invalid, 7, CREATE_COMMAND, digest); } catch { rejected = true; }
    assert(rejected, 'mismatched or impossible receipt was accepted');
  }
});

await asyncTest('429 after commit recovers from the exact durable receipt without a resend', async () => {
  const baseUrl = 'http://127.0.0.1:8777';
  const identity = { documentId: '7', incarnation: '0123456789abcdef0123456789abcdef' };
  setCurrentDocumentIdentity(identity.documentId, identity.incarnation);
  abandonPendingProgressionCommand(baseUrl, identity);
  const digest = await progressionCommandRequestDigest(7, CREATE_COMMAND);
  const originalFetch = globalThis.fetch;
  let posts = 0;
  let receiptReads = 0;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const requestUrl = String(input);
    if (requestUrl.includes('/commands')) {
      posts += 1;
      return jsonResponse({ detail: 'try later' }, 429);
    }
    if (requestUrl.includes('/command-receipt')) {
      receiptReads += 1;
      return jsonResponse(receipt(digest));
    }
    if (!init?.method && requestUrl.includes('/api/progressions')) {
      return jsonResponse(snapshotAt('b'.repeat(64)));
    }
    throw new Error(`Unexpected request ${requestUrl}`);
  }) as typeof fetch;
  try {
    const recovered = await runProgressionCommand(baseUrl, CREATE_COMMAND);
    assert(recovered.revision === 'b'.repeat(64), 'committed snapshot was not loaded');
    assert(posts === 1 && receiptReads === 1, 'ambiguous commit was resent instead of recovered');
    assert(!hasPendingProgressionCommand(baseUrl, identity), 'resolved attempt remained pending');
  } finally {
    globalThis.fetch = originalFetch;
    abandonPendingProgressionCommand(baseUrl, identity);
  }
});

await asyncTest('inconclusive retries retain one key across document switches and never mint a fresh command', async () => {
  const baseUrl = 'http://127.0.0.1:8777';
  const identity = { documentId: '7', incarnation: '0123456789abcdef0123456789abcdef' };
  const otherIdentity = { documentId: '8', incarnation: 'fedcba9876543210fedcba9876543210' };
  setCurrentDocumentIdentity(identity.documentId, identity.incarnation);
  abandonPendingProgressionCommand(baseUrl, identity);
  const digest = await progressionCommandRequestDigest(7, CREATE_COMMAND);
  const originalFetch = globalThis.fetch;
  let posts = 0;
  let receiptReads = 0;
  const keys: string[] = [];
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const requestUrl = String(input);
    if (requestUrl.includes('/commands')) {
      posts += 1;
      keys.push(new Headers(init?.headers).get('Idempotency-Key') ?? '');
      return jsonResponse({ detail: 'temporarily unavailable' }, 503);
    }
    if (requestUrl.includes('/command-receipt')) {
      receiptReads += 1;
      if (receiptReads <= 2) return receiptMiss();
      return jsonResponse(receipt(digest));
    }
    if (!init?.method && requestUrl.includes('/api/progressions')) {
      return jsonResponse(snapshotAt('b'.repeat(64)));
    }
    throw new Error(`Unexpected request ${requestUrl}`);
  }) as typeof fetch;
  try {
    let pendingError: unknown;
    try { await runProgressionCommand(baseUrl, CREATE_COMMAND); } catch (error) { pendingError = error; }
    assert(pendingError instanceof ProgressionRecoveryPendingError, 'inconclusive delivery was not retained');
    assert(posts === 2 && new Set(keys).size === 1 && Boolean(keys[0]), 'retry did not reuse one exact Idempotency-Key');
    assert(hasPendingProgressionCommand(baseUrl, identity), 'unresolved command was dropped');
    assert(
      hasPendingProgressionCommand('http://127.0.0.1:9999', identity),
      'backend address change hid the unresolved document command',
    );

    setCurrentDocumentIdentity(otherIdentity.documentId, otherIdentity.incarnation);
    assert(hasPendingProgressionCommand(baseUrl, identity), 'document switch erased the unresolved command');
    assert(!hasPendingProgressionCommand(baseUrl, otherIdentity), 'pending command leaked into another document');
    setCurrentDocumentIdentity(identity.documentId, identity.incarnation);

    const recovered = await resumePendingProgressionCommand('http://127.0.0.1:9999', identity);
    assert(recovered?.revision === 'b'.repeat(64), 'same-key receipt recovery did not finish');
    assert(posts === 2 && receiptReads === 3, 'recovery issued another POST after its bounded resend');
    assert(!hasPendingProgressionCommand(baseUrl, identity), 'receipt recovery did not clear pending state');
  } finally {
    globalThis.fetch = originalFetch;
    abandonPendingProgressionCommand(baseUrl, identity);
    setCurrentDocumentIdentity('', '');
  }
});

console.log(`Progressions tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} Progressions test(s) failed`);
console.log('PROGRESSIONS TESTS: PASS');
